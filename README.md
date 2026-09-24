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

> Web (Persona C) y bot (Persona D) todavia no estan en este repo. `run_all.sh`
> los arranca solo si existen las carpetas `fase2_persona_c/` y `fase2_persona_d/`.

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
    seed.py           # crea los usuarios y transportistas minimos
    requirements.txt
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
  docs originales/    # enunciado, plan y observaciones de las personas A/B
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
4. El backend consume `portus/evt/#`, guarda los eventos y expone una API HTTP
   para la web y el bot.
5. Los comandos remotos salen del backend (`POST /commands/send`) y se publican
   en `portus/cmd/solicitud`.
6. El bridge envia el comando al Arduino correcto y espera ACK/REJ.
7. La respuesta se publica en `portus/cmd/respuesta`.

> Estado del firmware: `SALIDAP1_ARQ2.ino` y `PORTUS_Fase1_v2.ino` ya envian y
> reciben frames `PORTUS`. `ENTRADAP1_ARQ2.ino` todavia solo imprime logs de texto,
> asi que el bridge no recibe eventos de la garita de entrada.

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
ARDUINO_BAUD=9600 \
bash run_all.sh
```

> **Baud rate:** los tres firmwares usan `Serial.begin(9600)`, pero `run_all.sh`
> y `bridge.py` usan 115200 si no se indica otro valor. Pasa `ARDUINO_BAUD=9600`
> o el bridge no va a poder leer los frames.

El bridge solo se inicia si estan definidos los tres puertos. Sin Arduinos
conectados, `bash run_all.sh` levanta solo Mosquitto y el backend.

Variables opcionales:

| Variable | Default | Uso |
| --- | --- | --- |
| `PORTUS_MQTT_HOST` | `localhost` | Broker MQTT |
| `PORTUS_MQTT_PORT` | `1883` | Puerto MQTT |
| `PORTUS_START_LOCAL_MOSQUITTO` | `auto` | `auto`/`yes`/`no`: arranca Mosquitto con `mosquitto/mosquitto.conf` |
| `ARDUINO_BAUD` | `115200` | Baud rate del bridge (usar `9600`) |
| `PORTUS_BOT_TOKEN` | vacio | Token del bot (Persona D) |

Servicios:

- Backend: http://localhost:8100 (health en `/health`, docs en `/docs`)
- Web C: http://localhost:8000 (cuando exista)

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
  --uno-entrada /dev/ttyACM0 --uno-salida /dev/ttyACM1 --mega-grua /dev/ttyACM2 \
  --baud 9600
```

### Usuarios de prueba

```bash
cd backend
.venv/bin/python3 seed.py
```

Crea (sin duplicar) los usuarios `terminal1`, `naviera1`, `naviera2`, `agente1`,
`autoridad1` y dos transportistas, todos con la contrasena de demostracion
definida en `seed.py`. Cambiarla antes de usarla como credencial real.

### Pruebas del protocolo

```bash
cd bridge
python3 -m unittest test_protocol.py
```

---

## API del backend (resumen)

| Area | Endpoints |
| --- | --- |
| Sistema | `GET /health`, `GET /events/recent`, `POST /commands/send` |
| Transportistas | `GET/POST /transportistas` |
| Manifiestos | `GET/POST /manifiestos`, `POST /manifiestos/{id}/anular`, `POST /manifiestos/{id}/solicitar-levante`, `POST /manifiestos/{id}/levante` |
| Declaraciones | `POST /declaraciones` |
| Garita y turnos | `POST /garita/ingreso`, `GET /turnos`, `GET /turnos/{id}`, `POST /turnos/{id}/pesaje-entrada`, `POST /turnos/{id}/pesaje-salida`, `POST /turnos/{id}/avanzar`, `POST /turnos/{id}/cerrar`, `POST /turnos/{id}/retener` |
| Retenciones | `GET /retenciones`, `POST /retenciones/{id}/resolver` |
| Patio y parqueo | `GET /patio`, `POST /patio/{id}/bloquear`, `POST /patio/{id}/liberar`, `GET /parqueo` |
| Alarmas | `GET /alarmas`, `POST /alarmas/{id}/reconocer`, `POST /alarmas/reconocer-todas` |

El detalle de cada endpoint esta en http://localhost:8100/docs (Swagger de FastAPI).

---

## Documentacion

- `docs/protocolo_serial.md`: formato del frame, checksum y ejemplos.
- `docs/puertos_raspberry.md`: conexion USB y alias udev en la Raspberry.
- `docs/mosquitto.md`: broker local y configuracion con usuario/contrasena para produccion.
