"""Crea los usuarios minimos exigidos (Fase_2_PORTUS.md sec. 2.1):
1 TERMINAL, 2 NAVIERA, 1 AGENTE, 1 AUTORIDAD, 2 TRANSPORTISTA.

Uso:
    cd backend
    .venv/bin/python3 seed.py          # usuarios, transportistas y tarjetas RFID
    .venv/bin/python3 seed.py --demo   # ademas, manifiestos con levante para probar la maqueta
    .venv/bin/python3 seed.py --presentacion  # 2 tarjetas listas para el ciclo limpio (deposito + salida)

Es idempotente: si el username ya existe, no lo vuelve a crear. Las
contrasenas de ejemplo son solo para desarrollo/demostracion — cambiarlas
antes de la entrega si se van a usar como credenciales reales.
"""

import os
import sys

from models import Declaracion, Manifiesto, Transportista, Turno, Usuario, Vehiculo, make_db
from security import hash_password

DB_PATH = os.getenv("PORTUS_DB_PATH", os.path.abspath(os.path.join(os.path.dirname(__file__), "portus_core.db")))

USUARIOS_MINIMOS = [
    ("terminal1", "TERMINAL", "Operador de Terminal"),
    ("naviera1", "NAVIERA", "Naviera Uno"),
    ("naviera2", "NAVIERA", "Naviera Dos"),
    ("agente1", "AGENTE", "Agente Aduanero"),
    ("autoridad1", "AUTORIDAD", "Autoridad Aduanera"),
]

TRANSPORTISTAS_MINIMOS = ["Transportista Uno", "Transportista Dos"]

PASSWORD_DEMO = "Portus2026!"

# Tarjetas de la maqueta -> transportista (fase 1: tarjeta -> contenedor).
# "90 C7 3D 5F" NO se registra a proposito: sirve para demostrar el rechazo
# "RFID no registrado" en la garita (E03).
# "E1 8E 3C 53" es la que el UNO de entrada simula fuera de tolerancia (RT01).
VEHICULOS = [
    ("E1 69 73 15", "Transportista Uno", "C-001"),
    ("E1 67 7F 15", "Transportista Dos", "C-002"),
    ("E1 8E 3C 53", "Transportista Uno", "C-003"),
]

# --demo: un manifiesto con levante otorgado (canal verde) por tarjeta.
MANIFIESTOS_DEMO = [
    ("MSCU0000001", "DEPOSITO", 1000, "E1 69 73 15", "naviera1"),
    ("MSCU0000002", "RETIRO", 1200, "E1 67 7F 15", "naviera2"),
    ("MSCU0000003", "DEPOSITO", 1500, "E1 8E 3C 53", "naviera1"),
]


# --presentacion: dos tarjetas "quemadas" con el ciclo limpio completo
# (ingreso -> 10 s -> pesaje OK -> grua DEPOSITO -> salida), sin que la
# naviera/agente/autoridad tengan que crear manifiesto ni dar levante.
# "E1 8E 3C 53" no va aqui: el UNO de entrada la fuerza a RT01 (aguja cerrada).
TARJETAS_PRESENTACION = ["E1 69 73 15", "E1 67 7F 15"]
MANIFIESTOS_LISTOS_POR_TARJETA = 3  # pasadas seguidas sin volver a correr el seed
PESO_PRESENTACION_G = 1000


def _manifiestos_pendientes(db, uid: str) -> list:
    """Manifiestos no anulados de la tarjeta que todavia no tienen turno."""
    return [m for m in db.query(Manifiesto).filter_by(vehiculo_uid=uid, anulado=False).order_by(Manifiesto.id)
            if db.query(Turno.id).filter_by(manifiesto_id=m.id).first() is None]


def _siguiente_contenedor(db) -> str:
    usados = {c for (c,) in db.query(Manifiesto.contenedor_id).filter(Manifiesto.contenedor_id.like("PRES%"))}
    n = 1
    while f"PRES{n:07d}" in usados:
        n += 1
    return f"PRES{n:07d}"


def sembrar_presentacion(db) -> None:
    naviera = db.query(Usuario).filter_by(username="naviera1").first()
    for uid in TARJETAS_PRESENTACION:
        vehiculo = db.get(Vehiculo, uid)
        if vehiculo is not None and not vehiculo.activo:
            vehiculo.activo = True
            print(f"[OK] vehiculo {uid} reactivado")
        pendientes = _manifiestos_pendientes(db, uid)
        # La garita toma el pendiente de menor id: un RETIRO o uno sin levante
        # (p. ej. de --demo) se colaria antes que el deposito de la presentacion.
        for m in pendientes:
            if m.tipo_operacion != "DEPOSITO" or m.estado_documental != "levante_otorgado":
                m.anulado = True
                print(f"[OK] manifiesto {m.contenedor_id} ({m.tipo_operacion}) anulado para no estorbar a {uid}")
        listos = sum(1 for m in pendientes if not m.anulado)
        for _ in range(MANIFIESTOS_LISTOS_POR_TARJETA - listos):
            contenedor = _siguiente_contenedor(db)
            m = Manifiesto(contenedor_id=contenedor, tipo_operacion="DEPOSITO", peso_declarado_g=PESO_PRESENTACION_G,
                           naviera_usuario_id=naviera.id if naviera else None,
                           transportista_id=vehiculo.transportista_id if vehiculo else None,
                           vehiculo_uid=uid, estado_documental="levante_otorgado", canal="verde")
            db.add(m)
            db.flush()
            db.add(Declaracion(manifiesto_id=m.id, numero_declaracion=f"PRES-{contenedor}",
                               regimen="importacion_definitiva", descripcion="Carga de presentacion",
                               valor_declarado=1000.0))
            print(f"[OK] manifiesto {contenedor} (DEPOSITO, levante verde) -> tarjeta {uid}")
        print(f"[OK] tarjeta {uid}: {max(listos, MANIFIESTOS_LISTOS_POR_TARJETA)} ingresos listos")


def main():
    SessionLocal = make_db(DB_PATH)
    with SessionLocal() as db:
        for username, rol, nombre in USUARIOS_MINIMOS:
            existente = db.query(Usuario).filter_by(username=username).first()
            if existente:
                print(f"[SKIP] {username} ya existe")
                continue
            db.add(Usuario(username=username, password_hash=hash_password(PASSWORD_DEMO),
                            rol=rol, nombre=nombre, activo=True))
            print(f"[OK] usuario {username} ({rol}) creado, password: {PASSWORD_DEMO}")

        for nombre in TRANSPORTISTAS_MINIMOS:
            existente = db.query(Transportista).filter_by(nombre=nombre).first()
            if existente:
                print(f"[SKIP] transportista {nombre} ya existe")
                continue
            db.add(Transportista(nombre=nombre))
            print(f"[OK] transportista {nombre} creado")

        db.flush()
        for uid, nombre_transportista, placa in VEHICULOS:
            if db.get(Vehiculo, uid):
                print(f"[SKIP] vehiculo {uid} ya existe")
                continue
            t = db.query(Transportista).filter_by(nombre=nombre_transportista).first()
            db.add(Vehiculo(uid=uid, transportista_id=t.id if t else None, placa=placa))
            print(f"[OK] vehiculo {uid} -> {nombre_transportista}")

        if "--demo" in sys.argv:
            db.flush()
            for contenedor, operacion, peso, uid, naviera in MANIFIESTOS_DEMO:
                if db.query(Manifiesto).filter_by(contenedor_id=contenedor).first():
                    print(f"[SKIP] manifiesto {contenedor} ya existe")
                    continue
                vehiculo = db.get(Vehiculo, uid)
                usuario = db.query(Usuario).filter_by(username=naviera).first()
                m = Manifiesto(contenedor_id=contenedor, tipo_operacion=operacion, peso_declarado_g=peso,
                               naviera_usuario_id=usuario.id if usuario else None,
                               transportista_id=vehiculo.transportista_id if vehiculo else None,
                               vehiculo_uid=uid, estado_documental="levante_otorgado", canal="verde")
                db.add(m)
                db.flush()
                db.add(Declaracion(manifiesto_id=m.id, numero_declaracion=f"DEMO-{contenedor}",
                                   regimen="importacion_definitiva", descripcion="Carga de demostracion",
                                   valor_declarado=1000.0))
                print(f"[OK] manifiesto demo {contenedor} ({operacion}) -> tarjeta {uid}")

        if "--presentacion" in sys.argv:
            db.flush()
            sembrar_presentacion(db)

        db.commit()
    print("\nListo. Guardar estas credenciales en la documentacion de entrega (sec. 2.1 del PDF).")


if __name__ == "__main__":
    main()
