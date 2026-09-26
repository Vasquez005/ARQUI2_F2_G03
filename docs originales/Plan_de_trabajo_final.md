# PORTUS Fase 2: plan de trabajo final

**Fecha:** 2026-09-25
**Reemplaza a:** `Pendientes_C_D_y_Alarmas.md`, `analisis_final_pendientes.md` y los cinco `Observaciones_*.md` (siguen en el historial de git si hace falta consultarlos).
**Referencia:** `Fase_2_PORTUS.md` (enunciado). Las secciones citadas (sec. X) son de ese documento.

Responsables: **A** firmware, **B** backend, **C** web, **D** bot.

---

## Estado al 2026-09-25

| Parte | Qué funciona | Qué falta (resumen) |
|---|---|---|
| Firmware (A) | Protocolo PORTUS, latido de 5 s, modo degradado con ping de la Pi, 13 comandos. **Desde la fase 1, las garitas le preguntan al servidor.** | Eventos de ciclo y fallas del Mega, AL02, búfer local, calibración |
| Bridge | Serial ↔ MQTT de las 3 placas, ping cada 3 s | — |
| Backend (B) | Cadena documental, turnos, RT01–RT06, parqueo, patio, avisos al bot. **Desde la fase 1, los eventos de la maqueta mueven el turno solos. Desde la fase 2, genera AL01 y AL09–AL14, guarda las alarmas de las placas y las anuncia en vivo.** | Rutas para Grúa, Citas y Reportes; AL03–AL08 esperan los eventos del Mega (fase 5) |
| Web (C) | Login y permisos en servidor. **Desde la fase 3:** sinóptico en vivo con los 13 elementos, controles con confirmación y ACK/REJ legible; Turnos, Retenciones, Patio y Alarmas completas, todo por WebSocket | Grúa, Citas y Reportes (fases 4 y 5); ver detalle en naviera / agente / autoridad (5.5) |
| Bot (D) | Vinculación, 7 comandos, citas, los 9 avisos, aislamiento entre transportistas. **Desde la fase 4:** respeta las franjas bloqueadas y anuncia sus citas en vivo | Demostración con 2 teléfonos (4.5, manual) |

---

## Fase 1: cerrar el ciclo físico (B + A) — ✅ HECHA (2026-09-25)

**Objetivo:** que pasar una tarjeta por la maqueta cree y avance el turno sin llamar a la API a mano.

### Lo que se hizo

1. **Asociar la tarjeta al contenedor.** Tabla nueva `vehiculos` (UID → transportista) y campo opcional `manifiestos.vehiculo_uid`. El servidor busca primero los manifiestos que nombran ese vehículo; si no hay, busca los del transportista dueño de la tarjeta. Entre varios candidatos, prefiere el que tiene levante y una cita en ventana. Rutas: `GET/POST /vehiculos`. El `POST /manifiestos` acepta `vehiculo_uid`.
2. **Procesador de eventos** (`backend/orquestador.py`, llamado desde `on_message`):
   - `garita evento=rfid` → el servidor valida (manifiesto, levante, turno activo, parqueo lleno, RT04) y responde `AbrirTalanquera;uid;op` o `RechazarIngreso;uid;motivo`.
   - `pesaje evento=meseta` → `procesar_pesaje_entrada` (EnRuta, RT01 o RT03).
   - `salida evento=rfid_salida` → el servidor valida (si está retenido, si no tiene turno o si le falta el pesaje) y responde `AbrirPuertaSalida;uid` o `RechazarSalida;uid;motivo`. Si el turno no está en EnSalida, lo avanza hasta ahí.
   - `salida evento=salida_completada;uid` → cierra el turno (sec. 7, regla 5).
   - Los comandos se publican **después** del commit. Si la transacción se deshace, no sale ninguna apertura.
3. **Decisión de peso:** no hay báscula. La garita manda `resultado=ok|fuera_tolerancia`, y el servidor usa el peso declarado si fue `ok` o `declarado × 1.5` si no (se cambia con `PORTUS_FACTOR_PESO_FUERA`). Si algún día llega `peso=<g>`, se usa ese valor. En la línea de tiempo queda anotado que el peso es simulado.
4. **Firmware de entrada:** se quitó la tabla local `camionAutorizado[]`. La garita manda el UID y espera hasta 5 s. Si no hay respuesta o está en modo degradado, rechaza localmente con `decision=local`. En el LCD aparece la causa que manda el servidor (E03). La tarjeta `E1 8E 3C 53` sigue simulando un peso fuera de tolerancia. RAM: 51 % → 48 %.
5. **Firmware de salida:** también le pregunta al servidor. Sin respuesta o en modo degradado, decide con su lista local de vehículos que están dentro (sec. 12.1.2). `salida_completada` ahora incluye el `uid`.
6. **Intentos rechazados** (sec. 7, regla 1): tabla `intentos_ingreso` y ruta `GET /garita/intentos`, para las dos garitas, indicando si lo decidió el servidor o el controlador.
7. **Datos de prueba:** `seed.py` registra las tarjetas de la maqueta; `seed.py --demo` crea un manifiesto con levante por tarjeta. `90 C7 3D 5F` queda sin registrar a propósito, para demostrar el rechazo.

### Verificación

- `backend/test_orquestador.py`: 10 pruebas pasan (depósito de punta a punta, tarjeta desconocida, sin levante, doble lectura, RT01 y salida bloqueada, salida sin turno, timeout, parqueo lleno con AL11, nada se publica si la transacción se deshace).
- La migración (`ALTER TABLE`) se probó sobre una copia de una `portus_core.db` existente.
- Los 2 `.ino` de garita compilan con `arduino-cli` para `arduino:avr:uno`. **No se han probado en las placas.**

### Pendiente de la fase 1 (probar en la maqueta)

- [ ] Subir los 2 firmwares y correr: tarjeta autorizada → pesaje → salida → turno Cerrado.
- [ ] Riesgo conocido: los comandos con `uid` miden ~96–107 bytes y el búfer de recepción del UNO es de 64. Si aparecen rechazos "Sin respuesta" sin motivo, quitar el `Serial.flush()` de `sendFrame` en la entrada (ver `docs/protocolo_serial.md`).
- [ ] RT03 (canal rojo) y RT04: el servidor retiene el turno, pero la aguja del UNO de entrada igual se abre si el pesaje fue `ok`. Se resuelve con la decisión de la aguja (fase 6).
- [x] RT04 en garita: el pesaje físico llega con el turno retenido. **Resuelto en la fase 2:** el servidor guarda ese peso y lo aplica al Aclarar (puede terminar en EnRuta o en una retención nueva RT01 / RT03). Si se Rechaza, no se aplica.
- [ ] La grúa todavía no informa la transferencia. Al llegar a la salida, el servidor pasa por EnTransferencia y lo anota en la línea de tiempo. Se completa en la fase 5.

---

## Fase 2: alarmas en el backend (B), sin tocar firmware — ✅ HECHA (2026-09-25)

Todo en el servidor. Las alarmas quedan guardadas aunque la web esté cerrada y **no desaparecen solas** (sec. 4.6).

| # | Alarma | De dónde sale | Cambio |
|---|---|---|---|
| 2.1 | AL09 Pesaje fuera de tolerancia | `pesaje meseta resultado=fuera_tolerancia` | Generarla en `_pesaje_meseta` / `procesar_pesaje_entrada` |
| 2.2 | AL10 Vehículo incorrecto en la salida | `RechazarSalida` por `sin_turno` | Generarla en `_salida_rfid` |
| 2.3 | AL14 Comando rechazado | `portus/cmd/respuesta` tipo REJ | En `on_message`; obligatoria por la sec. 11.2 |
| 2.4 | AL12 Retención de más de 30 min | Temporizador | Hilo como `link_watchdog_loop`, sin repetir la alarma |
| 2.5 | AL13 Más de 2 h en patio | Temporizador | Guardar la **fecha de ingreso** de cada contenedor en `patio` (nivel 1 y 2) |
| 2.6 | Alarmas que manden las placas | `portus/evt/alarma` | Procesar el tópico y guardar en `alarmas` |

### Lo que se hizo

1. **AL09** en `procesar_pesaje_entrada` y `procesar_pesaje_salida` (junto con RT01 / RT02), con el declarado, el medido y la diferencia en %. También sale si el pesaje llega por la API.
2. **AL10** cuando la salida rechaza por `sin_turno`. Una sola alarma activa por vehículo aunque pase la tarjeta varias veces; si se reconoce y vuelve a pasar, sale otra.
3. **AL14** con cada `REJ` de `portus/cmd/respuesta`: "MEGA_GRUA rechazo GruaReferenciar: grua_en_movimiento". La correlación con `command_audit` se movió a `servicios.registrar_respuesta_comando`.
4. **AL12 y AL13**: hilo `alarmas_por_tiempo_loop` cada 30 s. Cada retención y cada estancia de un contenedor en el patio generan su alarma **una sola vez**. Los umbrales se bajan con `PORTUS_MIN_AL12` y `PORTUS_MIN_AL13` para la demostración.
5. **Patio:** columnas `nivel1_desde` y `nivel2_desde`, que se llenan en `confirmar_deposito_patio` y se borran en `confirmar_remocion_patio`. `GET /patio` las devuelve (sirve también para 3.5, ordenar por permanencia). De paso se corrigió `liberar_posicion_patio`, que dejaba OCUPADA_1 una posición con dos contenedores.
6. **Alarmas de las placas:** `portus/evt/alarma` con `codigo=ALxx`. La severidad sale del catálogo, un código desconocido se ignora y no se duplica mientras siga activa. Formato en `docs/protocolo_serial.md`.
7. **Aviso en vivo:** toda alarma confirmada en la base sale por `portus/srv/alarma` (si la transacción se deshace, no sale). La web ya se suscribe y la reenvía por el WebSocket de la terminal; la pestaña Alarmas (3.3) puede usarlo sin polling.
8. Columna nueva `alarmas.referencia` (`turno:5`, `retencion:3`, `contenedor:X`, `comando:12`) y `GET /alarmas` devuelve también `referencia`, `ackAt` y `ackComentario` (para el historial de 3.3).

### Verificación

- `backend/test_alarmas.py`: 18 pruebas nuevas; con las 10 de `test_orquestador.py`, 28 pasan.
- Migración probada sobre una copia de `portus_core.db`.
- `on_message` probado con un `REJ` y un `portus/evt/alarma` simulados: se guardan y se anuncian.

### Pendiente de la fase 2

- [ ] **AL14 en cada retención y resolución:** el servidor manda `AgujaParqueo` / `AgujaLiberar` al Mega, que hoy los rechaza con `causa=pesaje_externo`. Cada retención y cada resolución generan una AL14 baja. Es correcto según la sec. 11.2 pero ensucia la demostración: se resuelve con la decisión de la aguja (6.3).
- [ ] **AL13** funciona, pero el patio solo se llena cuando la grúa informe los depósitos (5.1). Hasta entonces no se puede ver en la maqueta.
- [ ] AL02 todavía no lo emite ninguna placa (6.1). AL03, AL06, AL07 y AL08 ya están en el firmware del Mega (fase 5, falta probarlo en la placa).

---

## Fase 3: terminal web (C). Es lo más evaluado — ✅ HECHA (2026-09-25)

Regla general: nada de `setInterval` + `fetch` para el estado en vivo (se penaliza); todo por WebSocket.

| # | Pestaña | Qué falta |
|---|---|---|
| 3.1 | **Operación** | Sinóptico con los 13 elementos (garita, talanquera, pesaje, aguja, 3 plazas, transferencia, grúa, cola, patio, salida, enlace, modo), actualizado por WebSocket. Aviso de enlace perdido con la hora del último dato. Botones Suspender / Reanudar / Referenciar grúa, Abrir talanquera y Abrir puerta **con confirmación**, Liberar parqueo, Modo mantenimiento con confirmación. ACK/REJ legible con la causa (sec. 11.1), no JSON crudo. |
| 3.2 | **Retenciones** | Abiertas y resueltas, evidencia de peso (declarado, medido, diferencia absoluta y %), rol facultado, Aclarar / Corregir / Rechazar (Rechazar pide motivo), filtros. |
| 3.3 | **Alarmas** | Activas e históricas, Reconocer con comentario, Reconocer todas (solo media y baja), filtro por severidad. |
| 3.4 | **Turnos** | Activos e históricos por separado, filtros (estado, tipo, fecha, búsqueda), Ver detalle con línea de tiempo, Retener, Anular. **B:** agregar el transportista, el tiempo transcurrido y el filtro de fecha en `GET /turnos`. |
| 3.5 | **Patio** | 4 posiciones × 2 niveles, Bloquear / Liberar, ordenar por permanencia, resaltar los de más de 2 h (depende de 2.5). |
| 3.6 | Intentos y vehículos | Mostrar `GET /garita/intentos` (Operación o Turnos) y un formulario para registrar tarjetas (`POST /vehiculos`). Hace falta el proxy en `web_c`. |
| 3.7 | Permisos en la interfaz | Ocultar los botones a los roles que no pueden usarlos (el servidor ya los rechaza). |

### Lo que se hizo

1. **Tiempo real sin polling.** El backend anuncia en `portus/srv/cambio` (`{entidad, id}`) cada cambio confirmado de turnos, retenciones, plazas, posiciones del patio e intentos; la web se suscribe a `portus/srv/#` y recarga **solo** lo que cambió cuando llega el aviso. El único temporizador de la página redibuja relojes y la antigüedad del enlace; no consulta nada.
2. **3.1 Operación:** sinóptico con los 13 elementos. Garita, talanquera, pesaje, aguja, puerta de salida, grúa y modo salen de los eventos y latidos de las placas; parqueo y patio, del servidor. Transferencia, zona de espera y cola de grúa se deducen de los turnos (rotulado en pantalla) hasta la fase 5. Enlace por placa con la hora del último mensaje: sin latido por 15 s, esa parte se pone gris con un aviso de "último estado conocido" y el modo pasa a Degradado. Botones Suspender / Reanudar (solo suspendida) / Referenciar (solo en reposo o suspendida), Abrir talanquera, Abrir puerta y Modo mantenimiento con confirmación, Liberar parqueo por plaza, clic en posición (Bloquear / Liberar) y en vehículo (detalle del turno). Respuestas "MEGA_GRUA RECHAZO AgujaLiberar: pesaje_externo" o "sin respuesta en 6 s". Se conserva un formulario con los 13 comandos y sus parámetros.
3. **3.2 Retenciones:** abiertas y resueltas, evidencia de peso (declarado, medido, diferencia en g y %), tiempo de retención en vivo, rol facultado, Aclarar / Corregir (solo RT01-RT02) / Rechazar (pide motivo), filtros por causa y estado.
4. **3.3 Alarmas:** activas e históricas, Reconocer con comentario, Reconocer todas (media y baja), filtro por severidad, contador en la pestaña y aviso emergente al llegar una nueva.
5. **3.4 Turnos:** activos e históricos, filtros por estado, tipo, fecha (históricos) y búsqueda; transportista, pesos y tiempo en terminal; Ver detalle con la línea de tiempo al segundo; Retener (observación) y Anular. **B:** `GET /turnos` acepta `activos`, `desde`, `hasta` y `q`, y devuelve `transportistaNombre` y `tiempoEnTerminalS`.
6. **3.5 Patio:** 4 posiciones × 2 niveles con Bloquear / Liberar, inventario (`GET /patio/inventario`) con naviera, peso, autorización, ingreso, reloj de permanencia, remociones, orden por permanencia y resaltado de más de 2 h.
7. **3.6:** tabla de intentos rechazados y registro de tarjetas RFID en la pestaña Turnos (proxies nuevos en `web_c`).
8. **3.7:** en Retenciones, las causas aduaneras muestran "Resuelve AUTORIDAD" en lugar de los botones.

### Correcciones de fases anteriores en este sprint

- **Plaza del parqueo (fase 1):** Aclarar liberaba la plaza aunque el camión seguía estacionado, así que el botón Liberar parqueo (plaza ocupada con retención resuelta) nunca podía habilitarse. Ahora la plaza queda ocupada hasta que el vehículo sale del parqueo: ACK de `AgujaLiberar`, llegada a la garita de salida o cierre del turno. Si el mismo turno vuelve a retenerse, reutiliza su plaza. Nueva ruta `POST /parqueo/{id}/liberar`.
- **Retención manual (fase 1):** RT05 / RT06 fallaban con 409 en EnRuta y EnTransferencia porque el mapa de transiciones no permitía pasar a Retenido; ahora se puede "en cualquier momento" (sec. 8.2). Solo manda el vehículo al parqueo si todavía no llegó a la transferencia (sec. 4.2), y la observación se guarda.
- **Horas en la web:** el backend manda UTC sin zona y el navegador lo tomaba como hora local (6 h de diferencia). `roles.js` lo interpreta como UTC; aplica también a naviera, agente y autoridad.

### Verificación

- `backend/test_terminal.py`: 12 pruebas nuevas; con `test_orquestador` y `test_alarmas`, 40 pasan.
- Prueba de punta a punta con Mosquitto, backend y web reales y un simulador del bridge: depósito, RT01 con AL09, AL14 por la aguja, AL10, intentos, Aclarar desde la web (la plaza pasa a "resuelta" en vivo), Liberar parqueo, Suspender / Reanudar y pérdida de enlace (gris, Degradado y AL01 en vivo). Sin errores en la consola del navegador.

### Pendiente de la fase 3

- [ ] Con el Mega actual, `AgujaLiberar` siempre recibe REJ: la plaza se libera cuando el vehículo llega a la salida. Se resuelve con 6.3.
- [ ] Las confirmaciones y motivos usan los diálogos nativos del navegador (`confirm` / `prompt`); funcionan, pero se pueden reemplazar por formularios propios si hay tiempo.
- [ ] La pestaña Grúa muestra estado y eventos en vivo; historial, gráfica y CSV quedan para la fase 5. Reportes (fase 5) sigue como marcador. (Citas: hecha en la fase 4.)

---

## Fase 4: citas (D + B + C) — ✅ HECHA (2026-09-25), salvo 4.5 que es manual

| # | Tarea | Responsable |
|---|---|---|
| 4.1 | Tabla o columna de **franjas bloqueadas**; `proximas_franjas()` se las salta | D + B |
| 4.2 | Ruta de **agenda del día**: capacidad, ocupación y citas por franja, y % de citas cumplidas | B |
| 4.3 | **Cancelar y reprogramar** cita, con el aviso al transportista (el único que falta de la sec. 6.3) | D + B |
| 4.4 | Pestaña **Citas** en la terminal; mover ahí la vinculación del bot | C |
| 4.5 | Demostración con 2 teléfonos: vincular a los 2 transportistas y mostrar el aislamiento (E12) | D |

### Lo que se hizo

1. **Lógica compartida.** Franjas, capacidad, cita vigente y "vencida" pasaron del bot a `servicios.py` (`proximas_franjas`, `franja_disponible`, `asignar_cita`, `estado_cita`, `texto_franja`); el bot y la terminal usan las mismas reglas.
2. **4.1 Franjas bloqueadas:** tabla `franjas_bloqueadas`. Una franja bloqueada no se ofrece ni se asigna; las citas que ya tenía se conservan. Solo se bloquean franjas que no han empezado.
3. **4.2 Agenda del día:** `GET /citas/agenda?fecha=YYYY-MM-DD` con cada franja del horario (`PORTUS_HORARIO_AGENDA`, 06:00-22:00 por defecto) más las que tengan citas o bloqueos: capacidad, asignadas, estado (disponible, llena, bloqueada, en curso, pasada) y las citas con transportista, vehículo y contenedor. Cumplimiento = cumplidas / (cumplidas + vencidas), contando como vencidas las que no se presentaron.
4. **4.3 Cancelar y reprogramar:** `POST /citas/{id}/cancelar` y `/reprogramar` (solo a una franja futura con capacidad y sin bloqueo; `GET /citas/{id}/franjas-disponibles` da las opciones). Cada una deja su aviso al transportista dueño, con la ventana nueva si fue reprogramada. Con esto salen los 9 avisos de la sec. 6.3.
5. **4.4 Pestaña Citas:** selector de fecha, indicador de cumplimiento, "solo franjas con citas", Cancelar (motivo opcional), Reprogramar (diálogo con las franjas disponibles), Bloquear / Desbloquear franja. La vinculación del bot se movió aquí.
6. **En vivo:** las citas y los bloqueos se anuncian en `portus/srv/cambio`; el bot también se conecta a MQTT para anunciar las citas que se piden por Telegram, así la agenda de la terminal cambia sin recargar.

### Correcciones de fases anteriores en este sprint

- **Bot, carrera al confirmar:** la cita se creaba sin volver a revisar la franja; si otro la llenaba entre la oferta y la elección, quedaban 3 citas. Ahora `asignar_cita` revalida y el bot responde "Esa franja ya no está disponible".
- **Bot, recordatorio:** se marcaba una vez por cita, así que una cita reprogramada no volvía a recibir recordatorio. La referencia ahora incluye la ventana.
- **Bot, `/estado`:** la permanencia se calculaba desde el cierre del turno de depósito; ahora usa la fecha de ingreso al patio (fase 2).
- **Web, caché del navegador:** durante la prueba el navegador siguió usando un `app.js` viejo. Las plantillas piden los archivos con `?v=<fecha del archivo>`, así que cada cambio se descarga solo.

### Verificación

- `backend/test_citas.py`: 16 pruebas (reglas de la sec. 9, agenda, cancelar / reprogramar con aviso solo al dueño, bloqueos, bot con 2 transportistas, carrera, recordatorio, `/estado`). En total 56 pasan.
- Punta a punta con Mosquitto, backend, web y el bot en modo CLI: 2 transportistas vinculados, cada uno pide su cita por el bot y la agenda se actualiza en vivo; desde la web se cancela, se reprograma y se bloquea una franja; el bot ya no ofrece la bloqueada y cada aviso llega solo al chat de su dueño.

### 4.5 Guion para la demostración con 2 teléfonos (manual)

1. `seed.py --demo` y levantar todo con `PORTUS_BOT_TOKEN`.
2. Terminal → Citas → Vinculación: generar un código para cada transportista; en cada teléfono, `/vincular CODIGO`.
3. En cada teléfono, `/cita`, elegir su contenedor y una franja. La agenda muestra las dos citas sin recargar.
4. Aislamiento (E12): desde el teléfono 1, `/estado` con el contenedor del 2 → "No tienes carga asociada a ese identificador"; `/miscitas` solo lista lo propio.
5. Desde la web, reprogramar la cita del teléfono 2: solo ese teléfono recibe el aviso con la ventana nueva.

### Pendiente de la fase 4

- [ ] 4.5 se hace con los teléfonos y el token real de Telegram; no se puede automatizar.
- [ ] Las citas que no se presentan quedan "programadas" en la base y se muestran como vencidas por tiempo (para que la garita pueda aplicar RT04 si llegan tarde). La métrica ya las cuenta como vencidas.

---

## Fase 5: grúa, reportes y el resto de roles (A + B + C) — ✅ HECHA en software (2026-09-25); el firmware del Mega falta probarlo en la maqueta

| # | Tarea | Responsable |
|---|---|---|
| 5.1 | Mega: emitir eventos de inicio y fin de trabajo, transferencia confirmada y fallas (hoy solo manda `evt=estado`). Con eso: EnTransferencia real, tiempos de ciclo y AL03 a AL08 | A (+B para procesarlos) |
| 5.2 | Rutas de historial y tiempos de ciclo de la grúa, métricas de la sec. 13, exportar CSV | B |
| 5.3 | Pestaña **Grúa**: posición, trabajo actual, cola, gráfica de tiempos de ciclo (50/100/200), fallas, CSV | C |
| 5.4 | Pestaña **Reportes**: rango, etiqueta de corrida, las 8 métricas, CSV | C |
| 5.5 | Naviera, agente y autoridad: Ver detalle con historial, filtros y búsqueda, campo de tarjeta RFID en el manifiesto | C |
| 5.6 | **Adjuntar observación** (agente) y **Ver declaración** (autoridad), con sus rutas nuevas | B + C |

### Lo que se hizo

1. **5.1 Mega (compila; sin probar en la placa):** acepta `TrabajoGrua;op=DEPOSITO|RETIRO[;pos=N]` del servidor (en mantenimiento lo rechaza, sec. 11 regla 4) y emite `transferencia evento=alineado`, `grua evt=trabajo_inicio;op;pos`, `patio evento=deposito|retiro;pos` (confirmado por el sensor de la celda), `grua evt=trabajo_fin;op;pos;ms;tramos` y, al abortar, `transferencia evento=aborto;causa` con AL03 (referencia o marca), AL07 (depósito no confirmado), AL08 (camión movido) y AL06. Sin `pos`, o si la celda no sirve, la grúa usa la política de la fase 1 (primera libre / ocupada). Flash 8 %, RAM 17 %.
2. **Backend (`grua.py`):** el servidor manda el trabajo al turno más antiguo que espera la grúa (uno a la vez; al terminar, el siguiente; si la grúa lo rechaza, vuelve a la cola y se reenvía con GruaReanudar o al salir de mantenimiento). `trabajo_inicio` pasa el turno a **EnTransferencia de verdad** y abre el ciclo; el inventario solo cambia con la confirmación física (R09); `trabajo_fin` guarda duración y tramos; un aborto no toca el inventario y la grúa reintenta con el mismo turno. Cada paso queda en la línea de tiempo (E15).
3. **Remociones:** en la maqueta hay un bloque por celda y el nivel 2 es lógico. Si al retirar un contenedor había otro encima en el inventario, el servidor registra la remoción (ciclo `REMOCION`, el de arriba pasa a la posición que da la política) y la línea de tiempo lo muestra. Si la grúa retira de otra posición que la del inventario, AL07.
4. **Política de patio seleccionable (sec. 13):** `secuencial` (la de la fase 1) queda como modo del sistema, se elige en Reportes y cada corrida guarda con qué política se hizo. Para la Fase 3 se agrega la optimizada en `grua.POLITICAS`.
5. **5.2 Métricas (`reportes.py`):** las 8 de la sec. 13 sobre un rango. La fila de espera sale de un historial nuevo de estados del turno (`turno_estados`, lo llena un listener de `Turno.estado`): vehículos en EnGarita o EnRuta al mismo tiempo. La distancia se reporta en tramos del riel (`PORTUS_CM_POR_TRAMO` la pasa a cm).
6. **5.3 Pestaña Grúa:** estado y posición en vivo, trabajo en ejecución, cola con orden de atención, gráfica SVG de tiempos de ciclo (50 / 100 / 200) con promedio, historial, fallas (AL02–AL08 y ciclos abortados) y exportar CSV. Se actualiza con `portus/srv/cambio` (entidad `ciclo`).
7. **5.4 Pestaña Reportes:** etiqueta, rango, Generar (guarda la corrida), las 8 métricas en tarjetas, retenciones por causa y resolución, Exportar CSV con el detalle de cada turno, y la lista de corridas guardadas.
8. **5.5 y 5.6 Roles:** naviera, agente y autoridad ahora tienen **las pestañas con los nombres exactos de la sec. 3** (antes eran secciones sueltas). Naviera: Nuevo manifiesto con catálogo y tarjeta RFID, Ver detalle con historial, estado operativo, Mis contenedores con búsqueda, filtro, ubicación y reloj. Agente: Presentar declaración, Solicitar levante, Adjuntar observación; Seguimiento con filtro y búsqueda (pendiente / autorizada / retenida, canal y motivo). Autoridad: solicitudes con naviera, agente, declaración y peso; el canal es obligatorio antes de otorgar; Ver declaración con las observaciones del agente; Retenciones aduaneras con la información de la sec. 4.3; Consulta de carga con búsqueda por contenedor, naviera y autorización.

### Correcciones de fases anteriores en este sprint

- **Catálogo de contenedores (sec. 5.1):** el manifiesto aceptaba cualquier identificador. Tabla `contenedores` (se siembra al arrancar; `PORTUS_CONTENEDORES` la cambia) y el manifiesto se rechaza si el contenedor no está.
- **Número de declaración repetido:** reventaba con un error 500 de la base; ahora es un 409 claro.
- **Remociones mal contadas:** sacar el contenedor de arriba contaba como remoción; ahora solo cuenta la remoción real.
- **Motivo de retención del levante:** se pegaba en las observaciones del manifiesto; ahora tiene su campo y aparece en Seguimiento y en el detalle.
- **Historial del manifiesto (E08):** al Corregir se guardaba el peso anterior pero no había dónde verlo; ahora queda en el historial con los dos valores.
- **Web:** la clase `hidden` no ocultaba los formularios con `grid-form` (el de nuevo manifiesto se veía siempre). Zona de espera del sinóptico = misma definición que la métrica.

### Verificación

- `backend/test_grua.py`: 17 pruebas (ciclo de depósito de punta a punta, cola, aborto y reintento, rechazo en mantenimiento, retiro con remoción, retiro del de arriba sin remoción, AL07, historial y CSV, política, las 8 métricas y su CSV, historial de estados, catálogo, declaración repetida, historial del manifiesto, seguimiento y carga por naviera). En total 73 pasan.
- Punta a punta con Mosquitto, backend, web y un simulador que se porta como el Mega: el servidor asignó P1 al depósito (política) y P3 al retiro (inventario); el retiro registró la remoción de P3 a P2; el sinóptico, la pestaña Grúa (gráfica, historial) y el patio cambiaron en vivo; el reporte "prueba e2e fase 5" mostró las 8 métricas y el CSV se descargó. La cadena documental naviera → agente → autoridad se probó con los permisos (naviera 2 no ve lo de naviera 1; el agente no puede otorgar levante).

### Pendiente de la fase 5 (para la sesión con la maqueta)

- [ ] Subir el firmware del Mega y confirmar que los eventos salen en el momento físico correcto. El frame `TrabajoGrua` mide ~70 bytes y el búfer del Mega es de 64: mismo riesgo que en las garitas.
- [ ] **Decidir el apilado físico.** Hoy el nivel 2 es lógico: la grúa física deja un bloque por celda. Para demostrar E15 con una remoción real, la grúa tendría que poder apilar (bajar menos en una celda ocupada) y hacer el movimiento de remoción; si no, la remoción se demuestra como registro del servidor.
- [ ] AL04 (pérdida de carga) y AL05 (agarre no confirmado) no tienen sensor en la maqueta: documentarlo o agregar uno (fase 6).

---

## Fase 6: decisiones de hardware y robustez

| # | Tema | Decisión o trabajo |
|---|---|---|
| 6.1 | **AL02** paro de emergencia | Confirmar si existe un pin que lea el paro. Si existe: leerlo y publicar en `portus/evt/alarma`. Si no: documentarlo. |
| 6.2 | **Zumbador** para `AlarmaSilenciar` | Agregar uno (por ejemplo, en el Mega) o documentar que no hay señal sonora. |
| 6.3 | **Aguja** | Hoy el Mega responde `REJ causa=pesaje_externo` a los comandos de aguja, y la aguja del UNO de entrada solo sabe abrir o cerrar. Decidir quién la controla para que RT03 y RT04 manden físicamente el vehículo al parqueo. Calibrar el ángulo de `AGUJA_LIBERANDO`. |
| 6.4 | **Búfer local de eventos** (sec. 12.1.4 y 12.1.6) | Búfer circular mínimo en RAM y reenvío al reconectar. Ojo con la RAM (entrada 48 %, salida 61 %). |
| 6.5 | `PosicionLiberar` | Hoy no vuelve a comprobar el sensor físico de la celda. Documentarlo o mejorarlo. |
| 6.6 | Calibración | Ángulos y tiempos de los servos, sensores en la maqueta real. |

---

## Fase 7: pruebas y evidencia

1. Correr E01–E15 con la maqueta y guardar evidencia: `status_all.sh`, capturas por rol, depósito y retiro completos, RT01–RT06, AL01 (y AL02 si se implementa), desconexión con una operación en curso (sec. 12.1).
2. Demostración con 2 teléfonos (E12).
3. Credenciales de `seed.py` en la documentación de entrega (sec. 2.1).

### Qué desbloquea cada escenario

| Escenario | Depende de |
|---|---|
| E01, E02, E03, E09, E10 | Pantallas de roles (ya básicas) + fase 1 para E03 en la maqueta |
| E04 | Fase 4 |
| E05, E13 | Fase 1 + 3.1 (sinóptico y botones de grúa) |
| E06, E07, E08, E11 | Fase 1 + 3.2 y 3.3 |
| E12 | Pantalla de naviera + 4.5 |
| E14 | 3.3 (reconocer AL01) |
| E15 | Fase 5 |

---

## Decisiones para defender ante el catedrático

- **Frame `PIN` (extensión del protocolo):** el enunciado solo define el latido del controlador al servidor. El bridge manda un ping cada 3 s para que la placa detecte que la Pi dejó de responder y entre en modo degradado.
- **Validación de acceso en el servidor (sec. 12):** las garitas solo leen la tarjeta y muestran la respuesta; la decisión la toma `orquestador.py`. Sin servidor, la entrada rechaza todo y la salida deja salir a los vehículos que ya están dentro.
- **Báscula simulada:** la garita informa el resultado; el servidor aplica la regla de tolerancia con un peso simulado y lo deja anotado en la línea de tiempo.
- **Pendientes explícitos:** AL02 (falta el pin), búfer local, aguja y zumbador (fase 6).
