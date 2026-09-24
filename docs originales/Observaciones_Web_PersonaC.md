# Observaciones de revisión — Web (Persona C)

**Fecha de revisión:** 2026-09-24
**Archivos revisados/modificados:**
- `web_c/app/main.py` (reescrito para integrarse con B)
- `web_c/app/templates/terminal.html`, `web_c/app/static/app.js` (bugs puntuales)
- `web_c/requirements.txt`

**Contra qué se comparó:** tareas de Persona C en `docs originales/PORTUS_Fase2_Plan.md` (sección 3) y `docs originales/Fase_2_PORTUS.md` (secciones 2, 3, 4, 5 y 11).

**Verificación realizada:** backend de B + web levantados con una base temporal y probados por HTTP con los 5 usuarios de `seed.py`. Se recorrió la cadena documental completa (E01–E04), los permisos (E12), el WebSocket por rol y las resoluciones de retención (E07–E11) a través de `/api/...` de la web.

---

## Checklist contra las tareas de Persona C

| # | Tarea (según el plan) | Estado |
|---|---|---|
| 1 | Login, sesión y permisos por rol, contraseñas hasheadas | ✅ **Integrado** — ahora valida contra la tabla `usuarios` de B |
| 2 | TERMINAL: Operación, Turnos, Retenciones, Patio, Alarmas (+ Grúa, Citas, Reportes) | ❌ Solo hay nombres de pestañas. La API ya existe, falta la interfaz |
| 3 | NAVIERA: declarar manifiestos y ver solo los propios | ⚠️ API lista y aislada; falta la interfaz |
| 4 | AGENTE: presentar declaración y solicitar levante | ⚠️ API lista; falta la interfaz |
| 5 | AUTORIDAD: otorgar/retener levante y elegir canal | ⚠️ API lista; falta la interfaz |
| 6 | Sinóptico por MQTT en < 2 s, sin polling | ⚠️ Canal MQTT→WebSocket funciona (arreglado); falta el dibujo del sinóptico |
| 7 | Usuario y rol visibles siempre | ✅ Cumplido (`base.html`) |

---

## 1. Lo que se encontró y se corrigió

1. **Base de usuarios propia.** C creaba sus propios usuarios (`terminal123`, `naviera123`...) en `portus_persona_c.db`, separados de los de B. Ahora el login llama a `POST /auth/login` de B, así hay una sola tabla de usuarios. Las credenciales válidas son las de `backend/seed.py`.
2. **Escribía directo en la base del bot.** Generaba los códigos de vinculación en `bot_d/portus_persona_d.db`. Ahora usa `POST /transportistas/{id}/codigo-vinculacion` de B.
3. **El sinóptico nunca se conectaba.** En `terminal.html` se cargaba `app.js` **antes** de definir `window.PORTUS_WS_URL`, así que el script salía en la primera línea. Se invirtió el orden.
4. **Faltaba `websockets` en `requirements.txt`.** Funcionaba en la máquina de C porque la tenía instalada a mano; en una instalación limpia en la Pi, uvicorn rechaza el WebSocket. Se agregó.
5. **El WebSocket no pedía sesión.** Cualquiera podía conectarse a `/ws/terminal`. Ahora solo entra una sesión TERMINAL (la matriz 2.3 dice que solo TERMINAL ve el sinóptico). Verificado: naviera y anónimo son rechazados.
6. **El comando remoto era falso.** `/api/terminal/comando` respondía "ok" sin mandar nada. Ahora valida contra los 13 comandos de la sección 11, pone el `target` correcto y lo publica por B. La web también se suscribe a `portus/cmd/respuesta` para mostrar el ACK/REJ.
7. **El log mostraba cada evento dos veces** (`app.js`). Corregido.

## 2. API ya disponible para construir las interfaces

Todas las rutas revisan el rol **de la sesión** en el servidor y rellenan `rol_usuario`, `naviera_usuario_id` y `agente_usuario_id` desde la sesión, nunca desde lo que mande el navegador.

| Rol | Rutas |
|---|---|
| TERMINAL | `GET /api/terminal/turnos`, `GET /api/terminal/turnos/{id}` (con línea de tiempo), `POST .../turnos/{id}/retener` (RT06), `POST .../turnos/{id}/anular`, `GET /api/terminal/retenciones`, `POST .../retenciones/{id}/resolver`, `GET /api/terminal/patio` (patio + parqueo), `POST .../patio/{id}/bloquear\|liberar`, `GET /api/terminal/alarmas`, `POST .../alarmas/{id}/reconocer`, `POST .../alarmas/reconocer-todas`, `POST /api/terminal/comando`, `GET /api/terminal/transportistas`, `POST /api/terminal/vinculacion/generar` |
| NAVIERA | `GET/POST /api/naviera/manifiestos`, `POST .../manifiestos/{id}/anular` (solo los propios), `GET /api/naviera/transportistas` |
| AGENTE | `GET /api/agente/declaraciones`, `POST /api/agente/declaraciones`, `POST /api/agente/manifiestos/{id}/solicitar-levante` |
| AUTORIDAD | `GET /api/autoridad/solicitudes`, `POST .../manifiestos/{id}/levante`, `GET /api/autoridad/retenciones` (solo RT03/RT05), `POST .../retenciones/{id}/resolver` (sin Corregir), `GET /api/autoridad/carga` |

Eventos en vivo: `ws://<pi>:8000/ws/terminal` entrega un `snapshot` al conectar y luego cada mensaje de `portus/evt/#` y `portus/cmd/respuesta`.

## 3. Pendiente para C (lo que el enunciado exige y todavía no existe)

**TERMINAL (sección 4), es lo más evaluado:**
- **Operación (4.1):** el dibujo del sinóptico con los 13 elementos de la tabla (garita, talanquera, pesaje, aguja, parqueo con sus 3 plazas y tiempo, transferencia, grúa, cola, patio por nivel, puerta de salida, enlace, modo). Tiene que actualizarse **solo** con los mensajes del WebSocket; nada de `setInterval` + `fetch`. Si se pierde el enlace, mostrarlo y marcar los datos como viejos, con la hora del último estado.
- **Botones de Operación:** Suspender / Reanudar / Referenciar grúa (según estado), Abrir talanquera y Abrir puerta **con confirmación**, Liberar parqueo, Modo mantenimiento con confirmación, clic en posición de patio y en vehículo.
- **Turnos (4.2):** activos e históricos separados, columnas completas, filtros (estado, tipo, fecha, búsqueda), Ver detalle con línea de tiempo, Retener y Anular.
- **Retenciones (4.3):** abiertas y resueltas, evidencia de peso (declarado, medido, diferencia absoluta y %), rol facultado, Aclarar / Corregir / Rechazar (Rechazar pide motivo), filtros. Ocultar los botones al rol no facultado (el servidor ya lo rechaza).
- **Patio (4.4), Grúa (4.5), Alarmas (4.6), Citas (4.7), Reportes (4.8):** nada hecho. Grúa, Citas y Reportes necesitan además endpoints nuevos en B (ver "Pendiente de B" abajo).
- **Vinculación:** ya funciona el botón, falta moverlo a una pestaña (el enunciado no dice cuál; sugerencia: Citas).

**NAVIERA / AGENTE / AUTORIDAD (sección 5):** las 7 pestañas con sus tablas y formularios. La API ya está.

## 4. Pendiente de B que bloquea partes de C

- `GET /turnos` no devuelve el transportista ni el tiempo transcurrido, y no filtra por fecha.
- No hay endpoints para la pestaña Grúa (historial, tiempos de ciclo, CSV), Citas (agenda del día, cancelar, reprogramar, bloquear franja) ni Reportes (las 8 métricas + CSV).
- El inventario del patio no guarda fecha de ingreso por contenedor, así que no se puede calcular el reloj de permanencia (4.4 y 5.2).
- Ningún evento MQTT del puente actualiza los turnos todavía (ver `Observaciones_Integracion.md`).

## 5. Notas

- `PORTUS_SECRET_KEY` tiene un valor por defecto; en la Pi hay que definir uno propio (la web avisa al arrancar).
- `web_c/portus_persona_c.db` ya no se usa y se puede borrar.
