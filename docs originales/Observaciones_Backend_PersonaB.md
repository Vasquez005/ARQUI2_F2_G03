# Observaciones de revisión — Backend / BD / MQTT (Persona B)

**Fecha de revisión original:** 2026-09-21
**Fecha de actualización (correcciones aplicadas):** 2026-09-23
**Archivos nuevos/modificados:**
- `backend/models.py` (12 tablas nuevas de dominio)
- `backend/catalogos.py` (nuevo — constantes: roles, estados, causas RT, alarmas)
- `backend/security.py` (nuevo — hash de contraseñas)
- `backend/servicios.py` (nuevo — máquina de estados, retenciones, parqueo, patio, alarmas, garita)
- `backend/seed.py` (nuevo — usuarios/transportistas mínimos)
- `backend/app.py` (reescrito: watchdog por dispositivo, ~30 endpoints nuevos, corrección de correlación)
- `run_all.sh`, `status_all.sh` (rutas corregidas)
- `docs/mosquitto.md` (nuevo)

**Verificación realizada:** todo se probó en vivo (Mosquitto local + backend real + SQLite), no solo se escribió y se asumió que funciona. En el proceso aparecieron **3 bugs reales** que se detectaron y corrigieron durante las pruebas (detallados abajo) — ninguno se hubiera visto solo leyendo el código.

---

## Checklist contra las tareas de Persona B

| # | Tarea | Estado |
|---|---|---|
| 1 | Montar SO + Mosquitto + BD | ✅ Mosquitto documentado y con config de desarrollo |
| 2 | Puente serial lado Pi | ✅ Ya revisado en sesión anterior |
| 3 | Diseñar la BD (usuarios, manifiestos, declaraciones, turnos, inventario, pesajes, citas, retenciones, alarmas, eventos) | ✅ **Hecho** — 12 tablas nuevas |
| 4 | Máquina de estados del turno | ✅ **Hecho** — 10 estados, transiciones validadas, línea de tiempo |
| 5 | RT01–RT06, resoluciones (Aclarar/Corregir/Rechazar), parqueo | ✅ **Hecho** y probado en vivo |
| 6 | Validación de acceso en garita del lado servidor | ✅ **Hecho** — falta que el firmware la llame (ver limitación) |
| 7 | Asignación de posición de patio | ✅ **Hecho** — política secuencial, con bloqueo/liberación |

---

## 1. Base de datos — 12 tablas nuevas

`backend/models.py` ahora incluye, además de las 3 de infraestructura que ya existían (`event_log`, `link_status`, `command_audit`):

`usuarios`, `transportistas`, `manifiestos`, `declaraciones`, `citas`, `turnos`, `eventos_turno` (línea de tiempo), `patio` (4 posiciones), `parqueo_plazas` (3 plazas), `retenciones`, `alarmas`, `link_devices` (enlace por dispositivo).

**Alcance recortado a propósito:** las **citas** solo tienen lo mínimo para poder generar RT04 (contenedor, ventana, estado). La lógica completa de franjas de 15 min / capacidad de 2 / oferta de horarios **es tarea de Persona D** según el propio `PORTUS_Fase2_Plan.md` — no se construyó aquí para no invadir esa división de trabajo.

**Permisos:** como Persona C (login/sesión) no existe todavía, los endpoints que necesitan saber el rol de quien llama lo reciben como parámetro explícito en el body (`rol_usuario`). Esto es una solución provisional, pero cumple lo que el PDF exige de fondo: **la regla de qué rol puede resolver qué causa se valida en el servidor**, no ocultando un botón en una interfaz que todavía no existe. Falta conectar esto a una sesión real cuando C empiece.

---

## 2. Máquina de estados del turno y garita — `backend/servicios.py`

- `transicionar_turno()` valida cada salto contra el mapa de transiciones de la sección 7 del PDF; un salto no permitido devuelve error en vez de ejecutarse.
- `procesar_ingreso_garita()`: valida manifiesto existente, levante otorgado, y si hay una cita fuera de ventana o canal rojo con el parqueo lleno, rechaza el ingreso y genera AL11. Si todo está en orden, crea el turno y comanda `AbrirTalanquera`.
- `procesar_pesaje_entrada()` / `procesar_pesaje_salida()`: comparan contra el peso declarado del manifiesto (no una constante fija) y generan RT01/RT02/RT03 según corresponda.
- Línea de tiempo completa (`eventos_turno`) con origen (controlador/servidor/usuario), verificada end-to-end en las pruebas.

**Limitación conocida (dependencia con A):** el endpoint `POST /garita/ingreso` es la pieza de servidor de la validación de acceso, pero el firmware de la garita **todavía decide solo con su tabla local** (ver `Observaciones_Firmware_PersonaA.md`, punto 2). Falta cambiar el firmware para que le pregunte al servidor en vez de decidir por su cuenta — eso no se resolvió en esta pasada de B ni en la de A.

---

## 3. Retenciones, parqueo y alarmas

- Las 6 causas (RT01–RT06) implementadas, cada una con su rol facultado (`ROL_FACULTADO_POR_CAUSA` en `catalogos.py`) validado en `resolver_retencion()` — un rol equivocado recibe `403` con el motivo exacto, verificado en vivo (AUTORIDAD intentando resolver RT01 → rechazado).
- Las 3 resoluciones (Aclarar/Corregir/Rechazar): `Corregir` actualiza el manifiesto conservando el peso anterior, solo lo puede hacer TERMINAL y solo aplica a causas de peso (RT01/RT02) — verificado. `Rechazar` exige motivo — verificado (falla con 409 si no se manda). Una retención resuelta no se puede volver a resolver — verificado (409 `retencion_ya_resuelta`).
- Parqueo: asignación de la plaza libre de menor número, liberación al resolver, y AL11 si las 3 están ocupadas — verificado en vivo con 3 turnos simultáneos.
- Alarmas: catálogo completo de 14 códigos, `reconocer-todas` respeta que las críticas y altas deben reconocerse una por una (verificado: con una AL01 crítica activa, `reconocer-todas` devolvió `0` reconocidas).

---

## 4. Watchdog de enlace por dispositivo (AL01)

Antes, `link_status` era una sola fila global. Ahora `link_devices` trackea cada uno de los 3 microcontroladores por separado, y un hilo de fondo (`link_watchdog_loop`, cada 5s) compara el último heartbeat de cada uno contra un umbral de 15s (3× el periodo de 5s del latido, sección 10.2 del PDF) y genera AL01 automáticamente.

**Verificado en vivo:** se simuló un heartbeat de `MEGA_GRUA`, se esperó 18 segundos sin mandar otro, y se confirmó que `GET /health` marcó ese dispositivo como desconectado y apareció la alarma AL01 en `GET /alarmas`.

---

## 5. Bugs reales encontrados al probar (no se veían leyendo el código)

Estos tres aparecieron exclusivamente al ejecutar de verdad, no en la revisión de código — quedan documentados porque son la evidencia de por qué probar en vivo importa:

1. **`database is locked` en `/garita/ingreso`.** La primera versión de `publish_and_audit()` abría su propia sesión de SQLAlchemy (`with SessionLocal() as db: ... db.commit()`) independiente de la sesión del endpoint que la llamaba. Cuando el endpoint todavía tenía una transacción abierta (el `INSERT` del turno sin commitear) y, dentro de esa misma llamada, `servicios.py` invocaba el callback para mandar `AbrirTalanquera`, la sesión nueva intentaba escribir en el mismo archivo SQLite mientras la primera seguía abierta. **Corregido:** ahora `make_publish_and_audit(db)` recibe la sesión de la petición en curso y todo se confirma junto, en una sola transacción.
2. **La máquina de estados saltaba pasos.** `procesar_pesaje_entrada()` intentaba pasar de `EnGarita` directo a `EnRuta`, sin pasar por `EnPesajeEntrada` — el propio `transicionar_turno()` lo rechazaba (`Transicion no permitida`). Lo mismo en `procesar_pesaje_salida()` (`EnTransferencia` → `EnSalida` sin pasar por `EnPesajeSalida`). **Corregido:** ambas funciones ahora hacen explícito el "cruce de la plataforma de pesaje" como paso intermedio antes de evaluar el resultado.
3. **`/commands/send` no tenía sesión de base de datos.** Al centralizar `publish_and_audit` para que use la sesión de quien la llama, este endpoint en particular nunca abría una — se cayó con `NameError: name 'db' is not defined` la primera vez que se probó. **Corregido**, ahora abre su propia sesión como los demás.

Después de las 3 correcciones se volvió a correr la batería completa de pruebas (happy path completo hasta cierre, RT01 con Corregir, RT03 con Rechazar, validaciones de rol, motivo obligatorio, doble resolución, patio, correlación de comandos, manifiesto duplicado) y todo pasó.

---

## 6. Scripts de arranque — corregidos

`run_all.sh` ya no sube un nivel de más ni busca `portus_fase2_integrado/` (carpeta que nunca existió en la estructura real). Ahora:
- Calcula la raíz correctamente (donde vive el propio script).
- Arranca Mosquitto local automáticamente si detecta `mosquitto/mosquitto.conf` y el puerto está libre.
- Usa `.venv/bin/python3 -m pip`/`-m uvicorn` en vez de `source .venv/bin/activate` (más confiable en distintos shells).
- `web_c`/`bot_d` solo se intentan levantar si sus carpetas existen (siguen sin existir en este repo).

`status_all.sh` incluye ahora el proceso `mosquitto` en el resumen. `stop_all.sh` no necesitó cambios (ya recorría cualquier `.pid` genéricamente).

---

## 7. Mosquitto — documentado

`docs/mosquitto.md` (nuevo) explica instalación, la config de desarrollo (`mosquitto/mosquitto.conf`, `allow_anonymous true` para la red cerrada del laboratorio), y el camino a usuario/contraseña para la entrega si se quiere algo más serio (con la advertencia de que el bridge y el backend tendrían que agregar `.username_pw_set(...)`, hoy no lo hacen).

---

## Pendientes reales que quedan abiertos

- **Dependencia con A:** el firmware de la garita sigue decidiendo el ingreso solo; falta conectarlo a `POST /garita/ingreso`.
- **Persona C no existe:** los endpoints no tienen sesión/autenticación real, solo el parámetro `rol_usuario` explícito como solución provisional.
- **Persona D no existe:** las notificaciones automáticas al transportista quedan como una línea en la línea de tiempo del turno (`[pendiente bot D] notificacion '...'`) en vez de un mensaje real. La lógica completa de citas (franjas, oferta de horarios) tampoco se construyó aquí, es de D.
- **Corrección de retenciones de peso:** el firmware del Mega sigue sin recibir el peso declarado real del manifiesto antes de pesar (ver `Observaciones_Firmware_PersonaA.md`) — el servidor ya compara correctamente, pero appalancado en lo que el Mega reporta con su propia constante hoy. Cuando A conecte el pesaje real del manifiesto, esta parte del servidor ya está lista para recibirlo.
- **Citas (D):** falta toda la lógica de franjas de 15 min, capacidad de 2 por franja, y oferta de la siguiente franja disponible.

---

## Pendiente para la siguiente sesión

Sigue Persona C (interfaces web) y Persona D (bot de mensajería) — no se encontró ningún código de ninguno de los dos en esta máquina.
