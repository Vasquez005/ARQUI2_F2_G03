# PORTUS Fase 2 - Integrado A+B (base) + C/D

Este paquete agrega el trabajo base de **Persona A y B** para integrar los 3 Arduinos con la Raspberry Pi:

- Protocolo serial propio (delimitacion + checksum + secuencia + ACK/REJECT).
- Bridge serial multi-puerto (3 Arduinos) <-> MQTT.
- Backend FastAPI con almacenamiento de eventos, estado de enlace y comandos remotos.
- Firmware base para:
  - UNO garita entrada
  - UNO garita salida
  - Mega grua/pesaje (plantilla de integracion con tu logica actual)

> No reemplaza tu firmware funcional actual de grua (`ARQUI2/ARQUI2.ino`), sino que lo complementa con una plantilla de capa de comunicacion para Fase 2.

---

## Estructura

```text
portus_fase2_integrado/
  backend/
    app.py
    models.py
    requirements.txt
  bridge/
    bridge.py
    protocol.py
    requirements.txt
  firmware/
    uno_garita_entrada/uno_garita_entrada.ino
    uno_garita_salida/uno_garita_salida.ino
    mega_grua_pesaje/mega_grua_pesaje.ino
  docs/
    protocolo_serial.md
    puertos_raspberry.md
```

---

## Flujo de arquitectura

1. Arduino(s) envian eventos serial usando frame `PORTUS`.
2. `bridge.py` valida checksum + secuencia.
3. Bridge publica eventos a MQTT `portus/evt/...`.
4. Backend consume y persiste eventos, expone API HTTP para web/bot.
5. Comandos remotos salen por backend/terminal y se publican en `portus/cmd/solicitud`.
6. Bridge enruta comando al Arduino correcto y espera ACK/REJECT.
7. Respuesta publica en `portus/cmd/respuesta`.

---

## Topicos MQTT usados

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

## Ejecucion rapida (Raspberry)

1. Iniciar Mosquitto.
2. Ejecutar `bridge/bridge.py` con los 3 puertos serial.
3. Ejecutar `backend/app.py`.
4. Apuntar Persona C al backend y MQTT local.
5. Ejecutar Persona D (bot) contra DB/API central segun integracion final.

### Arranque unificado (recomendado)

Desde `portus_fase2_integrado`:

```bash
UNO_ENTRADA_PORT=/dev/ttyACM0 \
UNO_SALIDA_PORT=/dev/ttyACM1 \
MEGA_GRUA_PORT=/dev/ttyACM2 \
PORTUS_BOT_TOKEN="TU_TOKEN" \
bash run_all.sh
```

Si aun no tienen Arduinos conectados o token del bot, igual puedes correr:

```bash
bash run_all.sh
```

Detener todo:

```bash
bash stop_all.sh
```

Ver estado y logs resumidos:

```bash
bash status_all.sh
```

Detalles en `docs/`.
