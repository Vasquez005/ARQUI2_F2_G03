# PORTUS Fase 2 - Persona D

Implementacion base de **Persona D**:

- Bot de mensajeria (Telegram) con comandos obligatorios:
  - `/inicio`
  - `/vincular CODIGO`
  - `/cita [CONTENEDOR]`
  - `/miscitas`
  - `/estado CONTENEDOR`
  - `/misturnos`
  - `/ayuda`
- Vinculacion por codigo de 6 caracteres (un uso, expira en 60 min).
- Agenda de citas:
  - Franjas de 15 minutos
  - Maximo 2 citas por franja
  - Solo contenedores con levante otorgado
- Recordatorio automatico de cita 1 hora antes.
- Aislamiento por transportista (no ve carga ajena).

> Usa la misma base de datos y modelos que el backend de B (`backend/portus_core.db`,
> `backend/models.py`). Detalle y pendientes: `docs originales/Observaciones_Bot_PersonaD.md`.

## Estructura

```text
bot_d/
  app/
    main.py
  requirements.txt
```

## Ejecucion

1. Crear entorno e instalar:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configurar token de Telegram (opcional):

```bash
export PORTUS_BOT_TOKEN="tu_token"
```

3. Correr:

```bash
python app/main.py
```

Si no hay token configurado, inicia en **modo simulacion CLI** para probar comandos en consola.

## Prueba rapida (simulacion)

Al iniciar en CLI:

1. `transportistas` para ver ids y si estan vinculados.
2. `gen-code 1` genera un codigo (lo mismo que el boton de la terminal en la web).
3. `chat <id> <texto>` simula un mensaje de ese chat:
   - `chat 111 /vincular ABC123`
   - `chat 111 /cita`, luego `chat 111 /cita C1` y `chat 111 /cita C1 1`
   - `chat 111 /miscitas`, `chat 111 /estado C1`, `chat 111 /misturnos`
4. `notifs` imprime los avisos pendientes (levante, retencion, cierre...).

Los contenedores con levante salen de los manifiestos reales que crea la naviera en la web.
