"""Web de PORTUS (Persona C) — Fase_2_PORTUS.md sec. 2, 3, 4 y 5.

Integrada con el backend de B (backend/app.py, puerto 8100):
- El login valida contra la tabla `usuarios` de B (POST /auth/login). Ya no
  hay base de usuarios propia ni copia de la base del bot.
- Todas las acciones pasan por /api/... de esta app, que revisa el rol de la
  SESION y recien entonces llama a B, rellenando rol_usuario / naviera /
  agente desde la sesion. El navegador nunca decide su propio rol (sec. 2.3:
  "el control de permisos debera aplicarse en el servidor").
- B debe escuchar solo en 127.0.0.1 (run_all.sh) para que nadie se salte esta
  capa llamando directo al puerto 8100.
"""

import asyncio
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import paho.mqtt.client as mqtt
from fastapi import Depends, FastAPI, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel


class Role(str, Enum):
    TERMINAL = "TERMINAL"
    NAVIERA = "NAVIERA"
    AGENTE = "AGENTE"
    AUTORIDAD = "AUTORIDAD"


BACKEND_URL = os.getenv("PORTUS_BACKEND_URL", "http://127.0.0.1:8100").rstrip("/")
secret_key = os.getenv("PORTUS_SECRET_KEY", "portus_cambiar_clave")
signer = URLSafeSerializer(secret_key, salt="portus-session")

# Sec. 11: exactamente estos comandos, cada uno con el controlador que lo ejecuta.
COMANDOS_REMOTOS = {
    "AbrirTalanquera": "UNO_ENTRADA",
    "CerrarTalanquera": "UNO_ENTRADA",
    "AbrirPuertaSalida": "UNO_SALIDA",
    "AgujaRecta": "MEGA_GRUA",
    "AgujaParqueo": "MEGA_GRUA",
    "AgujaLiberar": "MEGA_GRUA",
    "GruaReferenciar": "MEGA_GRUA",
    "GruaSuspender": "MEGA_GRUA",
    "GruaReanudar": "MEGA_GRUA",
    "PosicionBloquear": "MEGA_GRUA",
    "PosicionLiberar": "MEGA_GRUA",
    "ModoMantenimiento": "MEGA_GRUA",
    "AlarmaSilenciar": "MEGA_GRUA",
}

CAUSAS_ADUANERAS = ("RT03", "RT05")
CAUSAS_RETENCION = ("RT01", "RT02", "RT03", "RT04", "RT05", "RT06")
ESTADOS_TURNO = ("Programado", "EnGarita", "EnPesajeEntrada", "EnRuta", "EnTransferencia", "EnPesajeSalida",
                 "EnSalida", "Retenido", "Cerrado", "Anulado")
ESTADOS_SIN_LEVANTE = ("declarado", "declaracion_presentada", "levante_solicitado")

# Que cambios de portus/srv/cambio le interesan a cada rol (sin la terminal).
# Solo se reenvia el NOMBRE de la entidad, nunca el id ni datos: la pagina
# vuelve a pedir su lista por /api/<rol>/..., que ya filtra lo que le toca ver.
ENTIDADES_POR_ROL = {
    "NAVIERA": {"manifiesto", "turno", "patio", "retencion"},
    "AGENTE": {"manifiesto", "declaracion"},
    "AUTORIDAD": {"manifiesto", "declaracion", "retencion", "turno", "patio"},
}


# ══════════════════════════════════════════════════════════════════════════
#  Cliente HTTP hacia B (urllib: sin dependencias nuevas)
# ══════════════════════════════════════════════════════════════════════════

def backend(method: str, path: str, body: Optional[dict] = None, params: Optional[dict] = None):
    url = BACKEND_URL + path
    if params:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail", exc.reason)
        except Exception:
            detail = exc.reason
        raise HTTPException(status_code=exc.code, detail=detail)
    except urllib.error.URLError:
        raise HTTPException(status_code=503, detail="backend_no_disponible")


def backend_csv(path: str, params: Optional[dict] = None) -> PlainTextResponse:
    """Reenvia un CSV de B como descarga (Exportar historial / Exportar reporte)."""
    url = BACKEND_URL + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            texto = resp.read().decode("utf-8")
            disposicion = resp.headers.get("Content-Disposition", 'attachment; filename="portus.csv"')
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=exc.code, detail="no_se_pudo_generar_el_csv")
    except urllib.error.URLError:
        raise HTTPException(status_code=503, detail="backend_no_disponible")
    return PlainTextResponse(texto, media_type="text/csv", headers={"Content-Disposition": disposicion})


# ══════════════════════════════════════════════════════════════════════════
#  Tiempo real: MQTT -> WebSocket (sin polling, sec. 4.1)
# ══════════════════════════════════════════════════════════════════════════

class EventBus:
    def __init__(self) -> None:
        self.clients: set = set()
        self.role_clients: dict = {}  # ws -> rol (naviera, agente, autoridad)
        self.last_heartbeat_iso: Optional[str] = None
        self.connected = False
        self.recent_events: deque = deque(maxlen=100)
        # Ultimo mensaje por topico y origen: el sinoptico arma el estado de
        # cada placa al abrir la pagina aunque el evento sea viejo (ej. la barra).
        self.last_by_key: dict = {}
        self.lock = threading.Lock()

    async def register(self, ws: WebSocket) -> None:
        await ws.accept()
        with self.lock:
            self.clients.add(ws)
        await ws.send_json(
            {
                "kind": "snapshot",
                "connected": self.connected,
                "lastHeartbeat": self.last_heartbeat_iso,
                "events": list(self.recent_events),
                "ultimos": sorted(self.last_by_key.values(), key=lambda e: e["ts"]),
            }
        )

    def unregister(self, ws: WebSocket) -> None:
        with self.lock:
            self.clients.discard(ws)
            self.role_clients.pop(ws, None)

    async def register_role(self, ws: WebSocket, role: str) -> None:
        await ws.accept()
        with self.lock:
            self.role_clients[ws] = role
        await ws.send_json({"kind": "status", "connected": self.connected})

    async def broadcast_roles(self, payload: dict, entidad: Optional[str] = None) -> None:
        """A las paginas de rol: el estado del broker y el nombre de lo que cambio."""
        with self.lock:
            destinos = [ws for ws, role in self.role_clients.items()
                        if entidad is None or entidad in ENTIDADES_POR_ROL.get(role, ())]
        for ws in destinos:
            try:
                await ws.send_json(payload)
            except Exception:
                self.unregister(ws)

    def store_event(self, topic: str, payload: dict) -> None:
        event = {
            "topic": topic,
            "ts": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        origin = payload.get("origin", "") if isinstance(payload, dict) else ""
        with self.lock:
            self.recent_events.appendleft(event)
            self.last_by_key[f"{topic}|{origin}"] = event

    async def broadcast(self, payload: dict) -> None:
        with self.lock:
            clients = list(self.clients)
        dead_clients = []
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead_clients.append(ws)
        for ws in dead_clients:
            self.unregister(ws)


event_bus = EventBus()
app = FastAPI(title="PORTUS Fase 2 - Web (Persona C)")
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


def version_estaticos() -> str:
    """?v= en los <script> y <link>: al cambiar un archivo cambia la URL y el
    navegador no sigue usando la copia vieja de su cache (paso al probar la fase 4)."""
    carpeta = os.path.join(os.path.dirname(__file__), "static")
    return str(int(max(os.path.getmtime(os.path.join(carpeta, f)) for f in os.listdir(carpeta))))


templates.env.globals["v"] = version_estaticos()
main_loop: Optional[asyncio.AbstractEventLoop] = None


# ══════════════════════════════════════════════════════════════════════════
#  Sesion y permisos
# ══════════════════════════════════════════════════════════════════════════

def make_session_cookie(user: dict) -> str:
    return signer.dumps({"uid": user["id"], "username": user["username"], "role": user["rol"],
                         "nombre": user.get("nombre", "")})


def read_session_cookie(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    try:
        return signer.loads(raw)
    except BadSignature:
        return None


def get_current_user(request: Request) -> Optional[dict]:
    return read_session_cookie(request.cookies.get("portus_session"))


def require_role(*roles: Role):
    def dependency(request: Request) -> dict:
        user = get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Sesion requerida")
        if user["role"] not in [r.value for r in roles]:
            raise HTTPException(status_code=403, detail="Accion no permitida para este rol")
        return user

    return dependency


def terminal_tab_list() -> list:
    return ["Operacion", "Turnos", "Retenciones", "Patio", "Grua", "Alarmas", "Citas", "Reportes"]


@app.on_event("startup")
async def startup() -> None:
    global main_loop
    main_loop = asyncio.get_running_loop()
    if secret_key == "portus_cambiar_clave":
        print("[WARN] PORTUS_SECRET_KEY no definida: las cookies de sesion se firman con la clave por defecto.")
    start_mqtt_listener()


# ══════════════════════════════════════════════════════════════════════════
#  Paginas
# ══════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    try:
        user = backend("POST", "/auth/login", {"username": username, "password": password})
    except HTTPException as exc:
        error = "Credenciales invalidas" if exc.status_code == 401 else "Servidor no disponible"
        return templates.TemplateResponse("login.html", {"request": request, "error": error},
                                          status_code=exc.status_code)
    if user.get("rol") not in [r.value for r in Role]:
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Este rol no tiene acceso web"}, status_code=403
        )

    response = RedirectResponse("/dashboard", status_code=302)
    response.set_cookie("portus_session", make_session_cookie(user), httponly=True, samesite="lax")
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("portus_session")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    role = user["role"]
    if role == Role.TERMINAL.value:
        return RedirectResponse("/terminal", status_code=302)
    if role == Role.NAVIERA.value:
        return RedirectResponse("/naviera", status_code=302)
    if role == Role.AGENTE.value:
        return RedirectResponse("/agente", status_code=302)
    if role == Role.AUTORIDAD.value:
        return RedirectResponse("/autoridad", status_code=302)
    raise HTTPException(status_code=403, detail="Rol no soportado")


@app.get("/terminal", response_class=HTMLResponse)
def terminal_page(request: Request, user: dict = Depends(require_role(Role.TERMINAL))):
    return templates.TemplateResponse(
        "terminal.html",
        {"request": request, "user": user, "tabs": terminal_tab_list(), "comandos": list(COMANDOS_REMOTOS),
         "estados_turno": ESTADOS_TURNO, "causas_retencion": CAUSAS_RETENCION},
    )


@app.get("/naviera", response_class=HTMLResponse)
def naviera_page(request: Request, user: dict = Depends(require_role(Role.NAVIERA))):
    return templates.TemplateResponse("naviera.html", {"request": request, "user": user})


@app.get("/agente", response_class=HTMLResponse)
def agente_page(request: Request, user: dict = Depends(require_role(Role.AGENTE))):
    return templates.TemplateResponse("agente.html", {"request": request, "user": user})


@app.get("/autoridad", response_class=HTMLResponse)
def autoridad_page(request: Request, user: dict = Depends(require_role(Role.AUTORIDAD))):
    return templates.TemplateResponse("autoridad.html", {"request": request, "user": user})


# ══════════════════════════════════════════════════════════════════════════
#  API TERMINAL
# ══════════════════════════════════════════════════════════════════════════

class ComandoIn(BaseModel):
    name: str
    params: dict = {}


@app.post("/api/terminal/comando")
def comando_terminal(body: ComandoIn, user: dict = Depends(require_role(Role.TERMINAL))):
    target = COMANDOS_REMOTOS.get(body.name)
    if target is None:
        raise HTTPException(status_code=400, detail=f"comando_desconocido:{body.name}")
    # La respuesta ACK/REJ del controlador llega despues por portus/cmd/respuesta (WebSocket)
    return backend("POST", "/commands/send", {"name": body.name, "target": target, "params": body.params})


@app.get("/api/terminal/transportistas")
def list_transportistas(user: dict = Depends(require_role(Role.TERMINAL))):
    return {"ok": True, "transportistas": backend("GET", "/transportistas")}


class LinkCodeRequest(BaseModel):
    transportistaId: int


@app.post("/api/terminal/vinculacion/generar")
def generar_codigo_vinculacion(req: LinkCodeRequest, user: dict = Depends(require_role(Role.TERMINAL))):
    return {"ok": True, **backend("POST", f"/transportistas/{req.transportistaId}/codigo-vinculacion")}


@app.get("/api/terminal/turnos")
def terminal_turnos(estado: Optional[str] = None, tipo_operacion: Optional[str] = None,
                    activos: Optional[bool] = None, desde: Optional[str] = None, hasta: Optional[str] = None,
                    q: Optional[str] = None, user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("GET", "/turnos", params={"estado": estado, "tipo_operacion": tipo_operacion,
                                             "activos": None if activos is None else str(activos).lower(),
                                             "desde": desde, "hasta": hasta, "q": q})


@app.get("/api/terminal/intentos")
def terminal_intentos(estacion: Optional[str] = None, user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("GET", "/garita/intentos", params={"estacion": estacion})


@app.get("/api/terminal/vehiculos")
def terminal_vehiculos(user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("GET", "/vehiculos")


class VehiculoIn(BaseModel):
    uid: str
    transportista_id: Optional[int] = None
    placa: str = ""
    activo: bool = True


@app.post("/api/terminal/vehiculos")
def terminal_registrar_vehiculo(body: VehiculoIn, user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("POST", "/vehiculos", body.model_dump())


@app.get("/api/terminal/turnos/{turno_id}")
def terminal_turno_detalle(turno_id: int, user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("GET", f"/turnos/{turno_id}")


class ObservacionIn(BaseModel):
    observacion: Optional[str] = None


@app.post("/api/terminal/turnos/{turno_id}/retener")
def terminal_retener(turno_id: int, body: ObservacionIn, user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("POST", f"/turnos/{turno_id}/retener",
                   {"causa": "RT06", "rol_usuario": user["role"], "observacion": body.observacion})


class AnularIn(BaseModel):
    causa: Optional[str] = None


@app.post("/api/terminal/turnos/{turno_id}/anular")
def terminal_anular(turno_id: int, body: AnularIn, user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("POST", f"/turnos/{turno_id}/anular", {"causa": body.causa})


@app.get("/api/terminal/retenciones")
def terminal_retenciones(estado: Optional[str] = None, causa: Optional[str] = None,
                         user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("GET", "/retenciones", params={"estado": estado, "causa": causa})


class ResolverIn(BaseModel):
    resolucion: str
    motivo: Optional[str] = None
    observacion: Optional[str] = None


def _resolver(retencion_id: int, body: ResolverIn, user: dict) -> dict:
    # rol_usuario sale de la sesion; B valida si ese rol esta facultado para la causa
    return backend("POST", f"/retenciones/{retencion_id}/resolver",
                   {"resolucion": body.resolucion, "rol_usuario": user["role"],
                    "motivo": body.motivo, "observacion": body.observacion})


@app.post("/api/terminal/retenciones/{retencion_id}/resolver")
def terminal_resolver(retencion_id: int, body: ResolverIn, user: dict = Depends(require_role(Role.TERMINAL))):
    return _resolver(retencion_id, body, user)


@app.get("/api/terminal/patio")
def terminal_patio(user: dict = Depends(require_role(Role.TERMINAL))):
    return {"patio": backend("GET", "/patio"), "parqueo": backend("GET", "/parqueo")}


# ── Citas (sec. 4.7): "Ver agenda completa de citas" es solo de TERMINAL (sec. 2.3) ──

@app.get("/api/terminal/citas/agenda")
def terminal_agenda(fecha: Optional[str] = None, user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("GET", "/citas/agenda", params={"fecha": fecha})


@app.get("/api/terminal/citas/{cita_id}/franjas")
def terminal_franjas_reprogramar(cita_id: int, user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("GET", f"/citas/{cita_id}/franjas-disponibles")


class CitaMotivoIn(BaseModel):
    motivo: Optional[str] = None


class ReprogramarIn(BaseModel):
    inicio: str
    motivo: Optional[str] = None


@app.post("/api/terminal/citas/{cita_id}/cancelar")
def terminal_cancelar_cita(cita_id: int, body: CitaMotivoIn, user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("POST", f"/citas/{cita_id}/cancelar", body.model_dump())


@app.post("/api/terminal/citas/{cita_id}/reprogramar")
def terminal_reprogramar_cita(cita_id: int, body: ReprogramarIn, user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("POST", f"/citas/{cita_id}/reprogramar", body.model_dump())


class FranjaIn(BaseModel):
    inicio: str
    motivo: Optional[str] = None


@app.post("/api/terminal/franjas/{accion}")
def terminal_franja(accion: str, body: FranjaIn, user: dict = Depends(require_role(Role.TERMINAL))):
    if accion not in ("bloquear", "desbloquear"):
        raise HTTPException(status_code=400, detail="accion_invalida")
    return backend("POST", f"/franjas/{accion}", body.model_dump())


@app.get("/api/terminal/patio/inventario")
def terminal_inventario(user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("GET", "/patio/inventario")


@app.post("/api/terminal/parqueo/{plaza_id}/liberar")
def terminal_liberar_parqueo(plaza_id: int, user: dict = Depends(require_role(Role.TERMINAL))):
    # B valida que la plaza este ocupada y su retencion resuelta (sec. 4.1)
    return backend("POST", f"/parqueo/{plaza_id}/liberar")


@app.post("/api/terminal/patio/{posicion_id}/{accion}")
def terminal_patio_accion(posicion_id: int, accion: str, user: dict = Depends(require_role(Role.TERMINAL))):
    if accion not in ("bloquear", "liberar"):
        raise HTTPException(status_code=400, detail="accion_invalida")
    return backend("POST", f"/patio/{posicion_id}/{accion}")


@app.get("/api/terminal/alarmas")
def terminal_alarmas(estado: Optional[str] = None, severidad: Optional[str] = None,
                     user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("GET", "/alarmas", params={"estado": estado, "severidad": severidad})


class AckIn(BaseModel):
    comentario: Optional[str] = None


@app.post("/api/terminal/alarmas/{alarma_id}/reconocer")
def terminal_reconocer(alarma_id: int, body: AckIn, user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("POST", f"/alarmas/{alarma_id}/reconocer", {"comentario": body.comentario})


@app.post("/api/terminal/alarmas/reconocer-todas")
def terminal_reconocer_todas(user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("POST", "/alarmas/reconocer-todas")


# ── Grua (sec. 4.5) ──

@app.get("/api/terminal/grua/estado")
def terminal_grua_estado(user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("GET", "/grua/estado")


@app.get("/api/terminal/grua/ciclos")
def terminal_grua_ciclos(limit: int = 50, user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("GET", "/grua/ciclos", params={"limit": limit})


@app.get("/api/terminal/grua/ciclos.csv")
def terminal_grua_csv(limit: int = 50, user: dict = Depends(require_role(Role.TERMINAL))):
    return backend_csv("/grua/ciclos.csv", {"limit": limit})


# ── Reportes (sec. 4.8): "Generar reporte de corrida" es solo de TERMINAL ──

class ReporteIn(BaseModel):
    desde: str
    hasta: str
    etiqueta: str


@app.get("/api/terminal/reportes")
def terminal_reportes(user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("GET", "/reportes")


@app.post("/api/terminal/reportes")
def terminal_generar_reporte(body: ReporteIn, user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("POST", "/reportes", body.model_dump())


@app.get("/api/terminal/reportes/{corrida_id}.csv")
def terminal_reporte_csv(corrida_id: int, user: dict = Depends(require_role(Role.TERMINAL))):
    return backend_csv(f"/reportes/{corrida_id}.csv")


class PoliticaIn(BaseModel):
    politica: str


@app.get("/api/terminal/politica-patio")
def terminal_politica(user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("GET", "/config/politica-patio")


@app.post("/api/terminal/politica-patio")
def terminal_cambiar_politica(body: PoliticaIn, user: dict = Depends(require_role(Role.TERMINAL))):
    return backend("POST", "/config/politica-patio", body.model_dump())


# ══════════════════════════════════════════════════════════════════════════
#  API NAVIERA (solo lo propio — sec. 5.1, 5.2)
# ══════════════════════════════════════════════════════════════════════════

class ManifiestoIn(BaseModel):
    contenedor_id: str
    tipo_operacion: str
    peso_declarado_g: int
    tolerancia_pct: Optional[float] = None
    transportista_id: int
    vehiculo_uid: Optional[str] = None  # tarjeta RFID; si falta, se deduce por el transportista
    observaciones: Optional[str] = None


@app.get("/api/naviera/manifiestos")
def naviera_manifiestos(user: dict = Depends(require_role(Role.NAVIERA))):
    return backend("GET", "/manifiestos", params={"naviera_usuario_id": user["uid"]})


@app.post("/api/naviera/manifiestos")
def naviera_crear_manifiesto(body: ManifiestoIn, user: dict = Depends(require_role(Role.NAVIERA))):
    data = body.model_dump()
    if data["tolerancia_pct"] is None:
        data["tolerancia_pct"] = 5.0  # sec. 5.1: si se omite, 5 por ciento
    data["naviera_usuario_id"] = user["uid"]  # la naviera no puede declarar a nombre de otra
    return backend("POST", "/manifiestos", data)


@app.post("/api/naviera/manifiestos/{manifiesto_id}/anular")
def naviera_anular_manifiesto(manifiesto_id: int, user: dict = Depends(require_role(Role.NAVIERA))):
    propios = backend("GET", "/manifiestos", params={"naviera_usuario_id": user["uid"]})
    if not any(m["id"] == manifiesto_id for m in propios):
        raise HTTPException(status_code=403, detail="El manifiesto no pertenece a esta naviera")
    return backend("POST", f"/manifiestos/{manifiesto_id}/anular")


def _manifiesto_propio(manifiesto_id: int, user: dict) -> dict:
    detalle = backend("GET", f"/manifiestos/{manifiesto_id}")
    if detalle.get("navieraUsuarioId") != user["uid"]:
        raise HTTPException(status_code=403, detail="El manifiesto no pertenece a esta naviera")
    return detalle


@app.get("/api/naviera/manifiestos/{manifiesto_id}")
def naviera_detalle(manifiesto_id: int, user: dict = Depends(require_role(Role.NAVIERA))):
    return _manifiesto_propio(manifiesto_id, user)


@app.get("/api/naviera/contenedores")
def naviera_contenedores(q: Optional[str] = None, estado_documental: Optional[str] = None,
                         user: dict = Depends(require_role(Role.NAVIERA))):
    # Sec. 5.2: el filtro por naviera lo pone el servidor, no el navegador
    return backend("GET", "/carga", params={"naviera_usuario_id": user["uid"], "q": q,
                                            "estado_documental": estado_documental})


@app.get("/api/naviera/catalogo")
def naviera_catalogo(user: dict = Depends(require_role(Role.NAVIERA))):
    return [c for c in backend("GET", "/contenedores") if c["activo"]]


@app.get("/api/naviera/transportistas")
def naviera_transportistas(user: dict = Depends(require_role(Role.NAVIERA))):
    # Para el selector "Transportista asignado" del formulario (sec. 5.1)
    return [{"id": t["id"], "nombre": t["nombre"]} for t in backend("GET", "/transportistas")]


# ══════════════════════════════════════════════════════════════════════════
#  API AGENTE (sec. 5.3, 5.4)
# ══════════════════════════════════════════════════════════════════════════

class DeclaracionIn(BaseModel):
    manifiesto_id: int
    numero_declaracion: str
    regimen: str
    descripcion: str
    valor_declarado: float


@app.get("/api/agente/declaraciones")
def agente_declaraciones(user: dict = Depends(require_role(Role.AGENTE))):
    return [m for m in backend("GET", "/manifiestos")
            if not m["anulado"] and m["estadoDocumental"] in ESTADOS_SIN_LEVANTE]


@app.post("/api/agente/declaraciones")
def agente_presentar(body: DeclaracionIn, user: dict = Depends(require_role(Role.AGENTE))):
    return backend("POST", "/declaraciones", {**body.model_dump(), "agente_usuario_id": user["uid"]})


@app.get("/api/agente/seguimiento")
def agente_seguimiento(q: Optional[str] = None, estado: Optional[str] = None,
                       user: dict = Depends(require_role(Role.AGENTE))):
    return backend("GET", "/declaraciones", params={"agente_usuario_id": user["uid"], "q": q, "estado": estado})


class ObservacionAgenteIn(BaseModel):
    texto: str


@app.post("/api/agente/manifiestos/{manifiesto_id}/observaciones")
def agente_observacion(manifiesto_id: int, body: ObservacionAgenteIn, user: dict = Depends(require_role(Role.AGENTE))):
    return backend("POST", f"/manifiestos/{manifiesto_id}/observaciones",
                   {"texto": body.texto, "agente_usuario_id": user["uid"]})


@app.post("/api/agente/manifiestos/{manifiesto_id}/solicitar-levante")
def agente_solicitar_levante(manifiesto_id: int, user: dict = Depends(require_role(Role.AGENTE))):
    return backend("POST", f"/manifiestos/{manifiesto_id}/solicitar-levante")


# ══════════════════════════════════════════════════════════════════════════
#  API AUTORIDAD (sec. 5.5, 5.6, 5.7)
# ══════════════════════════════════════════════════════════════════════════

class LevanteIn(BaseModel):
    otorgar: bool
    canal: Optional[str] = None
    motivo_retencion: Optional[str] = None


@app.get("/api/autoridad/solicitudes")
def autoridad_solicitudes(user: dict = Depends(require_role(Role.AUTORIDAD))):
    return [m for m in backend("GET", "/manifiestos") if m["estadoDocumental"] == "levante_solicitado"]


@app.post("/api/autoridad/manifiestos/{manifiesto_id}/levante")
def autoridad_levante(manifiesto_id: int, body: LevanteIn, user: dict = Depends(require_role(Role.AUTORIDAD))):
    return backend("POST", f"/manifiestos/{manifiesto_id}/levante", body.model_dump())


@app.get("/api/autoridad/retenciones")
def autoridad_retenciones(user: dict = Depends(require_role(Role.AUTORIDAD))):
    return [r for r in backend("GET", "/retenciones") if r["causa"] in CAUSAS_ADUANERAS]


@app.post("/api/autoridad/retenciones/{retencion_id}/resolver")
def autoridad_resolver(retencion_id: int, body: ResolverIn, user: dict = Depends(require_role(Role.AUTORIDAD))):
    if body.resolucion not in ("aclarar", "rechazar"):
        raise HTTPException(status_code=403, detail="Corregir es exclusivo del rol TERMINAL")
    return _resolver(retencion_id, body, user)


@app.get("/api/autoridad/carga")
def autoridad_carga(q: Optional[str] = None, naviera: Optional[str] = None, estado_documental: Optional[str] = None,
                    user: dict = Depends(require_role(Role.AUTORIDAD))):
    # Sec. 5.7: cualquier contenedor, sin restriccion de propietario
    return backend("GET", "/carga", params={"q": q, "naviera": naviera, "estado_documental": estado_documental})


@app.get("/api/autoridad/manifiestos/{manifiesto_id}")
def autoridad_ver_declaracion(manifiesto_id: int, user: dict = Depends(require_role(Role.AUTORIDAD))):
    return backend("GET", f"/manifiestos/{manifiesto_id}")


# ══════════════════════════════════════════════════════════════════════════
#  WebSocket del sinoptico (solo TERMINAL — matriz sec. 2.3)
# ══════════════════════════════════════════════════════════════════════════

@app.websocket("/ws/terminal")
async def terminal_ws(websocket: WebSocket):
    user = read_session_cookie(websocket.cookies.get("portus_session"))
    if not user or user.get("role") != Role.TERMINAL.value:
        await websocket.close(code=4403)
        return
    await event_bus.register(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        event_bus.unregister(websocket)


@app.websocket("/ws/rol")
async def rol_ws(websocket: WebSocket):
    """Naviera, agente y autoridad: avisos de cambio para recargar su lista en vivo."""
    user = read_session_cookie(websocket.cookies.get("portus_session"))
    if not user or user.get("role") not in ENTIDADES_POR_ROL:
        await websocket.close(code=4403)
        return
    await event_bus.register_role(websocket, user["role"])
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        event_bus.unregister(websocket)


def _safe_json_decode(raw: bytes) -> dict:
    try:
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return {"raw": ""}
        return json.loads(text)
    except Exception:
        return {"raw": raw.decode("utf-8", errors="replace")}


def _publish_to_ws_from_thread(payload: dict) -> None:
    if main_loop is None:
        return
    asyncio.run_coroutine_threadsafe(event_bus.broadcast(payload), main_loop)


def _publish_to_roles_from_thread(payload: dict, entidad: Optional[str] = None) -> None:
    if main_loop is None:
        return
    asyncio.run_coroutine_threadsafe(event_bus.broadcast_roles(payload, entidad), main_loop)


def start_mqtt_listener() -> None:
    mqtt_host = os.getenv("PORTUS_MQTT_HOST", "localhost")
    mqtt_port = int(os.getenv("PORTUS_MQTT_PORT", "1883"))

    def on_connect(client, userdata, flags, rc, properties=None):
        event_bus.connected = rc == 0
        client.subscribe("portus/evt/#")
        client.subscribe("portus/cmd/respuesta")  # ACK/REJ que se le muestra al operador (sec. 11.1)
        # Del backend: alarmas nuevas y cambios de turnos, retenciones, parqueo y patio
        client.subscribe("portus/srv/#")
        _publish_to_ws_from_thread({"kind": "status", "connected": event_bus.connected})
        _publish_to_roles_from_thread({"kind": "status", "connected": event_bus.connected})

    def on_disconnect(client, userdata, flags, rc, properties=None):
        event_bus.connected = False
        _publish_to_ws_from_thread({"kind": "status", "connected": event_bus.connected})
        _publish_to_roles_from_thread({"kind": "status", "connected": event_bus.connected})

    def on_message(client, userdata, msg):
        payload = _safe_json_decode(msg.payload)
        topic = msg.topic
        event_bus.store_event(topic, payload)
        if topic == "portus/evt/estado":
            event_bus.last_heartbeat_iso = datetime.now(timezone.utc).isoformat()
        _publish_to_ws_from_thread(
            {
                "kind": "event",
                "topic": topic,
                "payload": payload,
                "connected": event_bus.connected,
                "lastHeartbeat": event_bus.last_heartbeat_iso,
            }
        )
        if topic == "portus/srv/cambio" and isinstance(payload, dict) and payload.get("entidad"):
            entidad = str(payload["entidad"])
            _publish_to_roles_from_thread({"kind": "cambio", "entidad": entidad}, entidad)

    def loop_thread() -> None:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message
        while True:
            try:
                client.connect(mqtt_host, mqtt_port, keepalive=30)
                client.loop_forever()
            except Exception:
                event_bus.connected = False
                time.sleep(3)

    threading.Thread(target=loop_thread, daemon=True).start()
