# Integración A + B + C + D — estado al 2026-09-24

## 1. Garita de entrada: barrera de pesaje (cambio nuevo)

**Qué se pidió:** el servo de la barrera de pesaje lo controla el UNO de entrada. Al leer una tarjeta autorizada, el vehículo tiene 10 s para llegar al pesaje (que no pesa de verdad) y luego se abre la barrera. Una tarjeta especial siempre se rechaza en el pesaje y la barrera no se abre.

**Validación de la lógica del commit `feat: barrera`:** ✅ hace lo pedido.
- Tarjeta autorizada → talanquera arriba → 10 s → barrera de pesaje arriba 8 s, flecha verde → baja.
- Tarjeta `E1 8E 3C 53` (`rechazarEnPesaje[3] = true`) → pasa la garita → a los 10 s la barrera **no** se abre, flecha ámbar y "RT01 RECHAZADO" por 10 s.
- La tarjeta `90 C7 3D 5F` se sigue rechazando en la garita (`camionAutorizado[2] = false`).

**Problema grave encontrado: regresión.** Ese commit se hizo sobre una versión vieja del `.ino` y **borró** todo lo de Fase 2 que ya tenía la garita (ver `Observaciones_Firmware_PersonaA.md`): frames PORTUS, latido cada 5 s, modo degradado, comandos `AbrirTalanquera`/`CerrarTalanquera` y el rechazo sin `delay(2500)`. Con esa versión, el bridge no recibía nada de la garita de entrada.

**Corrección aplicada** (`firmware/uno_garita_entrada/ENTRADAP1_ARQ2.ino`): se unió la versión con protocolo (`HEAD~1`) con la lógica nueva de la barrera y los UIDs nuevos. Además:
- **Un vehículo a la vez en el pesaje.** Antes, si llegaba otra tarjeta mientras el primer vehículo seguía en su cuenta de 10 s, `autorizar()` pisaba `camionEnPesaje` y reiniciaba el tiempo: el primer camión perdía su pesaje. Ahora la garita no lee tarjetas hasta que el pesaje termina, y el LCD muestra "Espere pesaje".
- **Eventos nuevos** al tópico `pesaje`: `evento=en_camino`, `evento=meseta;resultado=ok|fuera_tolerancia` (con `causa=RT01` si se rechaza), `evento=aguja_abajo`, `evento=fin_rechazo`. El latido incluye `pesaje=libre|en_camino|aprobado|rechazado`.
- La talanquera se cierra por tiempo (20 s) también cuando se abre con el comando remoto.
- **RAM:** al unir las dos versiones el sketch quedaba en 87 % de RAM (riesgo de cuelgues con tantos `String`). Se movieron los textos a flash con `F()`: queda en **51 %**.
- Compila con `arduino-cli` para `arduino:avr:uno`. **No se probó en la placa.**

**A tener en cuenta:**
- Tras un rechazo en el pesaje, la barrera queda cerrada y a los 10 s la garita vuelve a aceptar tarjetas. Si el vehículo rechazado sigue físicamente frente a la barrera, el siguiente autorizado le abrirá la barrera a los dos. En el flujo real ese vehículo iría al parqueo (comando `AgujaParqueo` del Mega), que todavía no está conectado.
- La validación de acceso sigue en la tabla local del Arduino. El enunciado (sec. 12) pide que la decida el servidor (ver punto 3).
- El Mega no se tocó (a pedido). Hoy el Mega **también** tiene su lógica de pesaje con HX711 y su propia aguja. Hay que decidir cuál de los dos manda sobre el pesaje cuando llegue el documento del Mega.

## 2. Cómo quedaron conectadas las partes

```
Arduinos --serial PORTUS--> bridge (A+B) --MQTT portus/evt/#--> backend B  ---> portus_core.db
                                        \--MQTT------------------> web C (WebSocket al sinoptico)
navegador --HTTP :8000--> web C (sesion + permisos) --HTTP 127.0.0.1:8100--> backend B
Telegram <--> bot D --------------------------------------------> portus_core.db (misma BD)
                  ^-- tabla notificaciones <-- B redacta los avisos
```

- **Una sola base de datos** (`backend/portus_core.db`). C y D ya no tienen bases propias.
- **B escucha solo en 127.0.0.1** (`run_all.sh`, `PORTUS_BACKEND_BIND`). Los endpoints de B reciben el rol como parámetro, así que si quedaran expuestos cualquiera podría decir "soy AUTORIDAD". La web es la única entrada HTTP y pone el rol desde la sesión.
- `run_all.sh` ahora arranca `web_c/` y `bot_d/` (buscaba carpetas `fase2_persona_c/` y `fase2_persona_d/` que no existían) y corre `seed.py` antes del backend.
- Baud rate por defecto cambiado a **9600** en `run_all.sh` y `bridge.py` (los 3 firmwares usan 9600; con 115200 el bridge no leía nada).

**Cambios hechos en B para esto:** `POST /auth/login`, `GET /usuarios`, `POST /transportistas/{id}/codigo-vinculacion`, `POST /turnos/{id}/anular`, tabla `notificaciones` con avisos reales, el turno toma el transportista del manifiesto, la garita marca la cita `cumplida`/`vencida`, se actualiza `estacion_actual` en cada paso, y la alarma **AL11** ahora sí queda guardada (antes el `rollback()` del rechazo la borraba). `PORTUS_DB_PATH` permite apuntar a otra base para pruebas.

**Probado de punta a punta por HTTP** (base temporal, sin Arduinos ni Mosquitto): E01, E02, E03 (parte documental y aviso), E04 (cita por el bot), E07 + E08 (RT01 → Corregir → cierre), E09 + E10 (canal rojo → solo AUTORIDAD → Rechazar con motivo obligatorio), E11 (parqueo lleno + AL11), E12 (permisos en servidor y aislamiento de navieras y transportistas), RT04 por llegada fuera de ventana.

## 3. Lo que falta para cerrar el ciclo físico (siguiente paso)

**El eslabón que falta es B: nada convierte los eventos del bridge en acciones sobre los turnos.** `backend/app.py:on_message` guarda los eventos en `event_log` y actualiza el latido, pero un `evento=autorizado` de la garita no crea un turno y un `evento=meseta` del pesaje no llama a `procesar_pesaje_entrada`. Hoy los turnos solo avanzan si alguien llama a los endpoints a mano (como en las pruebas). Para cerrar el ciclo hay que:

1. **Asociar tarjeta ↔ contenedor.** La garita solo conoce el UID RFID del vehículo; el manifiesto conoce el contenedor. Hace falta una tabla (o un campo en el manifiesto o la cita) que diga qué vehículo trae qué contenedor.
2. **Mover la decisión de acceso al servidor (sec. 12).** La garita manda `evento=rfid;uid=...`, B llama a `procesar_ingreso_garita` y responde con `AbrirTalanquera` o con un rechazo que la garita muestre en el LCD (E03 pide "la pantalla indica la causa"). Esto cambia el firmware de entrada: dejar de decidir con `camionAutorizado[]`.
3. **Pesaje:** con `resultado=ok|fuera_tolerancia` del UNO, B necesita un peso para `procesar_pesaje_entrada`. Como no hay báscula, se puede mandar un peso simulado (declarado si ok, declarado × 1.5 si no) o cambiar B para aceptar el resultado directamente. Hay que decidirlo.
4. El resto de estaciones (transferencia, salida) depende del Mega y la garita de salida.

**Pendiente del enunciado que no es de C ni D:** registro de intentos de ingreso rechazados (sec. 7.1), búfer de eventos durante la desconexión (sec. 12.1.4), paro de emergencia/AL02, métricas y reportes (sec. 13).

## 4. Limpieza del repo

- ✅ Se quitaron las copias viejas (`backend2/`, `bridge2/`, `firmware2/`, `docs C y D/`, `README2.md`, `*_all2.sh`) y las bases que C y D ya no usan. Queda un solo `backend/`, `bridge/`, `firmware/`, `web_c/`, `bot_d/` y un solo `run_all.sh` / `status_all.sh` / `stop_all.sh`.
- ✅ `backend/portus_core.db` ya no está en git (`*.db` en `.gitignore`); `seed.py` lo crea al arrancar.
