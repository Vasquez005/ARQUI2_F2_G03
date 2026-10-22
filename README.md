# PORTUS Fase 2 - Integrado A+B (base) + C/D

Integracion de los 3 Arduinos de PORTUS con la Raspberry Pi:

- Protocolo serial propio (delimitacion + checksum + secuencia + ACK/REJECT).
- Bridge serial multi-puerto (3 Arduinos) <-> MQTT.
- Backend FastAPI con base SQLite: eventos, estado de enlace, comandos remotos
  y la logica de negocio de Fase 2 (manifiestos, turnos, pesaje, patio,
  parqueo, retenciones y alarmas).
- Firmware para:
  - UNO garita entrada (+ pesaje)
  - UNO garita salida
  - Mega grua/pesaje

- Web (Persona C): login, permisos por rol y API de las 4 interfaces, sobre el backend de B.
- Bot de Telegram (Persona D): vinculacion, citas y avisos al transportista, sobre la misma base de B.

> Estado y pendientes por fase: `docs originales/Plan_de_trabajo_final.md`.

---

## Estructura

```text
.
  backend/
    app.py            # API FastAPI + cliente MQTT
    models.py         # modelos SQLAlchemy y make_db()
    servicios.py      # reglas de negocio (turnos, patio, parqueo, retenciones, alarmas)
    catalogos.py      # roles, dispositivos, causas de retencion, umbrales
    security.py       # hash/verificacion de contrasenas
    orquestador.py    # eventos de la maqueta -> avance del turno (garitas, pesaje, grua, salida)
    grua.py           # trabajos de la grua, ciclos, inventario, remociones y politica de patio
    reportes.py       # las 8 metricas de la sec. 13, CSV y consulta de carga
    seed.py           # usuarios, transportistas y tarjetas RFID (--demo: manifiestos de prueba)
    test_orquestador.py
    test_alarmas.py
    test_terminal.py
    test_citas.py
    test_grua.py
    test_vivo.py      # avisos en vivo por rol y bot que siempre responde
    requirements.txt
  web_c/
    app/main.py       # web: sesion, permisos por rol, proxy hacia B, MQTT -> WebSocket
    app/templates/    # login + interfaces TERMINAL, NAVIERA, AGENTE, AUTORIDAD
    app/static/
  bot_d/
    app/main.py       # bot de Telegram (o modo CLI sin token)
  bridge/
    bridge.py         # serial <-> MQTT
    protocol.py       # encode/parse de frames PORTUS
    test_protocol.py  # pruebas unitarias del protocolo
    requirements.txt
  firmware/
    uno_garita_entrada/ENTRADAP1_ARQ2.ino
    uno_garita_salida/SALIDAP1_ARQ2.ino
    mega_grua_pesaje/PORTUS_Fase1_v2.ino
  mosquitto/
    mosquitto.conf    # config minima de desarrollo (anonimo, puerto 1883)
  docs/
    protocolo_serial.md
    puertos_raspberry.md
    mosquitto.md
  docs originales/    # enunciado, plan original y plan de trabajo final
  run_all.sh
  status_all.sh
  stop_all.sh
```

---

## Flujo de arquitectura

1. Los Arduinos envian eventos por serial usando el frame `PORTUS`
   (ver `docs/protocolo_serial.md`).
2. `bridge.py` valida checksum y secuencia.
3. El bridge publica los eventos en MQTT `portus/evt/<topic>`.
4. El backend consume `portus/evt/#` y guarda los eventos. La web tambien se
   suscribe y los reenvia por WebSocket al sinoptico (sin polling). Naviera,
   agente y autoridad reciben por `/ws/rol` solo el nombre de lo que cambio y
   recargan su pestaña.
5. Los comandos remotos salen de la web -> backend (`POST /commands/send`) y se
   publican en `portus/cmd/solicitud`.
6. El bridge envia el comando al Arduino correcto y espera ACK/REJ.
7. La respuesta se publica en `portus/cmd/respuesta`.
8. El backend redacta los avisos al transportista en la tabla `notificaciones`
   y el bot los envia.

9. `backend/orquestador.py` convierte los eventos de garitas y pesaje en avances
   del turno: la garita manda el UID, el servidor decide y responde
   `AbrirTalanquera` / `RechazarIngreso` (y lo mismo en la salida). Ver
   `docs/protocolo_serial.md`.
10. El backend genera las alarmas del catalogo (AL01, AL09-AL14 y las que
    mandan las placas por `portus/evt/alarma`) y anuncia cada una nueva en
    `portus/srv/alarma`; la web la reenvia por WebSocket.

---

## Topicos MQTT

- `portus/evt/garita`
- `portus/evt/pesaje`
- `portus/evt/aguja`
- `portus/evt/transferencia`
- `portus/evt/grua`
- `portus/evt/patio`
- `portus/evt/salida`
- `portus/evt/alarma`
- `portus/evt/estado`
- `portus/cmd/solicitud`
- `portus/cmd/respuesta`
- `portus/srv/alarma` (del backend: cada alarma nueva, ya guardada)
- `portus/srv/cambio` (del backend y del bot: `{entidad, id}` de cada turno, retencion, plaza, posicion, intento, cita, franja, ciclo, manifiesto, declaracion, transportista o vehiculo que cambio)

---

## Requisitos

- Python 3 (los scripts crean un `.venv` en `backend/` y en `bridge/`).
- Mosquitto (`brew install mosquitto` o `sudo apt install mosquitto mosquitto-clients`).
- Arduino IDE con las librerias `MFRC522`, `LiquidCrystal_I2C`, `Servo` y `Stepper`.

---

## Ejecucion

### Arranque unificado (recomendado)

Desde la raiz del repo:

```bash
UNO_ENTRADA_PORT=/dev/ttyACM0 \
UNO_SALIDA_PORT=/dev/ttyACM1 \
MEGA_GRUA_PORT=/dev/ttyACM2 \
PORTUS_BOT_TOKEN="TOKEN_DE_TELEGRAM" \
PORTUS_SECRET_KEY="una_clave_larga" \
bash run_all.sh
```

El bridge solo se inicia si estan definidos los tres puertos, y el bot solo si
hay `PORTUS_BOT_TOKEN`. Sin nada de eso, `bash run_all.sh` levanta Mosquitto,
el backend y la web.

Variables opcionales:

| Variable | Default | Uso |
| --- | --- | --- |
| `PORTUS_MQTT_HOST` | `localhost` | Broker MQTT |
| `PORTUS_MQTT_PORT` | `1883` | Puerto MQTT |
| `PORTUS_START_LOCAL_MOSQUITTO` | `auto` | `auto`/`yes`/`no`: arranca Mosquitto con `mosquitto/mosquitto.conf` |
| `ARDUINO_BAUD` | `9600` | Baud rate del bridge (igual que los firmwares) |
| `PORTUS_BOT_TOKEN` | vacio | Token del bot de Telegram (Persona D) |
| `PORTUS_SECRET_KEY` | clave de ejemplo | Firma de las cookies de sesion de la web. Cambiarla en la Pi |
| `PORTUS_BACKEND_BIND` | `127.0.0.1` | Donde escucha el backend. Dejarlo local: la web aplica los permisos |
| `PORTUS_MIN_AL12` | `30` | Minutos de retencion abierta para AL12 (bajarlo para la demostracion) |
| `PORTUS_MIN_AL13` | `120` | Minutos de un contenedor en patio para AL13 (bajarlo para la demostracion) |
| `PORTUS_HORARIO_AGENDA` | `06:00-22:00` | Horario (hora local) que muestra la agenda de citas de la terminal |
| `PORTUS_CONTENEDORES` | `MSCU0000001..MSCU0000008` | Catalogo de contenedores de la maqueta (separados por coma) |
| `PORTUS_CM_POR_TRAMO` | `0` | Centimetros entre posiciones del riel, para reportar la distancia de la grua en cm |

Servicios:

- Web: http://<ip-de-la-pi>:8000
- Backend: http://localhost:8100 (health en `/health`, docs en `/docs`), solo desde la propia Pi

Estado y logs resumidos (los logs quedan en `.runtime/logs/`):

```bash
bash status_all.sh
```

Detener todo:

```bash
bash stop_all.sh
```

### Ejecucion manual

```bash
# Broker
mosquitto -c mosquitto/mosquitto.conf -d

# Backend
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python3 -m uvicorn app:app --host 0.0.0.0 --port 8100

# Bridge
cd bridge
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python3 -u bridge.py \
  --uno-entrada /dev/ttyACM0 --uno-salida /dev/ttyACM1 --mega-grua /dev/ttyACM2

# Web
cd web_c
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Bot (sin PORTUS_BOT_TOKEN entra en modo CLI para probar comandos)
cd bot_d
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
PORTUS_BOT_TOKEN=... .venv/bin/python3 app/main.py
```

### Usuarios de prueba

```bash
cd backend
.venv/bin/python3 seed.py          # usuarios, transportistas y tarjetas RFID
.venv/bin/python3 seed.py --demo   # ademas, manifiestos con levante para probar la maqueta
```

Crea (sin duplicar) los usuarios `terminal1`, `naviera1`, `naviera2`, `agente1`,
`autoridad1` y dos transportistas, todos con la contrasena de demostracion
definida en `seed.py`. `run_all.sh` lo corre solo. Estos son los usuarios con
los que se entra a la web. Los transportistas no tienen usuario web: se vinculan
al bot con un codigo que genera la terminal.

Tarjetas RFID de la maqueta:

| UID | Transportista | Vehiculo | Uso en la demo |
| --- | --- | --- | --- |
| `E1 69 73 15` | Transportista Uno | C-001 | ciclo normal |
| `E1 67 7F 15` | Transportista Dos | C-002 | ciclo normal |
| `E1 8E 3C 53` | Transportista Uno | C-003 | peso fuera de tolerancia (RT01) |
| `90 C7 3D 5F` | - | - | no registrada: rechazo en garita (E03) |

Con `--demo` cada tarjeta registrada recibe un manifiesto con levante otorgado
(canal verde), de modo que la garita puede abrir la talanquera.

### Pruebas

```bash
# Protocolo serial
cd bridge
python3 -m unittest test_protocol.py

# Ciclo fisico del orquestador y alarmas (sin MQTT ni Arduinos)
cd backend
.venv/bin/python3 -m unittest test_orquestador test_alarmas test_terminal test_citas test_grua test_vivo -v
```

---

## API del backend (resumen)

| Area | Endpoints |
| --- | --- |
| Sistema | `GET /health`, `GET /events/recent`, `POST /commands/send` |
| Usuarios | `POST /auth/login`, `GET /usuarios` |
| Transportistas y vehiculos | `GET/POST /transportistas`, `POST /transportistas/{id}/codigo-vinculacion`, `GET/POST /vehiculos` |
| Citas | `GET /citas/agenda`, `GET /citas/{id}/franjas-disponibles`, `POST /citas/{id}/cancelar`, `POST /citas/{id}/reprogramar`, `POST /franjas/bloquear`, `POST /franjas/desbloquear` |
| Manifiestos y carga | `GET/POST /manifiestos`, `GET /manifiestos/{id}`, `POST /manifiestos/{id}/observaciones`, `POST /manifiestos/{id}/anular`, `POST /manifiestos/{id}/solicitar-levante`, `POST /manifiestos/{id}/levante`, `GET /contenedores`, `GET /carga` |
| Declaraciones | `GET/POST /declaraciones` |
| Garita y turnos | `POST /garita/ingreso`, `GET /garita/intentos`, `GET /turnos`, `GET /turnos/{id}`, `POST /turnos/{id}/pesaje-entrada`, `POST /turnos/{id}/pesaje-salida`, `POST /turnos/{id}/avanzar`, `POST /turnos/{id}/cerrar`, `POST /turnos/{id}/anular`, `POST /turnos/{id}/retener` |
| Retenciones | `GET /retenciones`, `POST /retenciones/{id}/resolver` |
| Patio y parqueo | `GET /patio`, `GET /patio/inventario`, `POST /patio/{id}/bloquear`, `POST /patio/{id}/liberar`, `GET /parqueo`, `POST /parqueo/{id}/liberar` |
| Alarmas | `GET /alarmas`, `POST /alarmas/{id}/reconocer`, `POST /alarmas/reconocer-todas` |
| Grua | `GET /grua/estado`, `GET /grua/ciclos`, `GET /grua/ciclos.csv`, `GET/POST /config/politica-patio` |
| Reportes | `GET/POST /reportes`, `GET /reportes/{id}.csv` |

El detalle de cada endpoint esta en http://localhost:8100/docs (Swagger de FastAPI).

---

## Documentacion

- `docs/protocolo_serial.md`: formato del frame, checksum y ejemplos.
- `docs/puertos_raspberry.md`: conexion USB y alias udev en la Raspberry.
- `docs/mosquitto.md`: broker local y configuracion con usuario/contrasena para produccion.
