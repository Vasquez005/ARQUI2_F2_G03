# PORTUS Fase 2 - Persona C

Implementacion base de la parte de **Persona C**:

- Login + sesion
- Control de acceso por rol (server-side)
- 4 interfaces web (TERMINAL, NAVIERA, AGENTE, AUTORIDAD)
- Sinoptico TERMINAL actualizado por MQTT (sin polling)

## Stack

- FastAPI
- Jinja2 templates
- SQLite (SQLAlchemy)
- MQTT subscriber (paho-mqtt)
- WebSocket para actualizar UI en tiempo real

## Estructura

```text
web_c/
  app/
    main.py
    static/
      app.js
      styles.css
    templates/
      base.html
      login.html
      terminal.html
      naviera.html
      agente.html
      autoridad.html
  requirements.txt
```

## Ejecutar

1. Crear entorno:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configurar variables opcionales:

```bash
export PORTUS_SECRET_KEY="cambiar_esta_clave"
export PORTUS_MQTT_HOST="localhost"
export PORTUS_MQTT_PORT="1883"
```

3. Correr:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

4. Abrir:

- http://localhost:8000

## Usuarios

La web ya no tiene usuarios propios: valida contra la tabla `usuarios` del
backend de B (`POST /auth/login`). Se crean con `backend/seed.py`
(`terminal1`, `naviera1`, `naviera2`, `agente1`, `autoridad1`).

## Integracion con B

- Necesita el backend corriendo (`PORTUS_BACKEND_URL`, por defecto `http://127.0.0.1:8100`).
- Las rutas `/api/<rol>/...` revisan el rol de la sesion y llaman a B. La lista
  completa esta en `app/main.py`; lo que falta de interfaz: `docs originales/Plan_de_trabajo_final.md`.
- Escucha `portus/evt/#`, `portus/cmd/respuesta` y `portus/srv/#` y los reenvia
  por `/ws/terminal` (solo sesiones TERMINAL). Al conectarse, el WebSocket manda
  los eventos recientes y el ultimo mensaje de cada placa para armar el sinoptico.
- La terminal (`static/app.js`) no consulta periodicamente: cambia con los eventos
  de las placas y, cuando llega `portus/srv/cambio`, vuelve a pedir solo lo que
  cambio (turnos, retenciones, parqueo, patio o intentos).
