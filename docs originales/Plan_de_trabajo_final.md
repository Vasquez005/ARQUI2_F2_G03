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
| Web (C) | Login y permisos en servidor, las 8 pestañas de la terminal ya se pueden abrir, naviera, agente y autoridad tienen tablas y acciones básicas | 7 de las 8 pestañas de la terminal muestran JSON crudo; falta el sinóptico y los filtros |
| Bot (D) | Vinculación, 7 comandos, citas, 8 de 9 avisos, aislamiento entre transportistas | Cancelar y reprogramar citas, bloquear franjas |

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

- [ ] **AL14 en cada retención:** el servidor manda `AgujaParqueo` / `AgujaLiberar` al Mega, que hoy los rechaza con `causa=pesaje_externo`. Cada retención y cada resolución generan una AL14 baja. Es correcto según la sec. 11.2 pero ensucia la demostración: se resuelve con la decisión de la aguja (6.3).
- [ ] **AL13** funciona, pero el patio solo se llena cuando la grúa informe los depósitos (5.1). Hasta entonces no se puede ver en la maqueta.
- [ ] Ninguna placa emite todavía `portus/evt/alarma` (AL02 en 6.1; AL03–AL08 en 5.1).

---

## Fase 3: terminal web (C). Es lo más evaluado

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

---

## Fase 4: citas (D + B + C)

| # | Tarea | Responsable |
|---|---|---|
| 4.1 | Tabla o columna de **franjas bloqueadas**; `proximas_franjas()` se las salta | D + B |
| 4.2 | Ruta de **agenda del día**: capacidad, ocupación y citas por franja, y % de citas cumplidas | B |
| 4.3 | **Cancelar y reprogramar** cita, con el aviso al transportista (el único que falta de la sec. 6.3) | D + B |
| 4.4 | Pestaña **Citas** en la terminal; mover ahí la vinculación del bot | C |
| 4.5 | Demostración con 2 teléfonos: vincular a los 2 transportistas y mostrar el aislamiento (E12) | D |

---

## Fase 5: grúa, reportes y el resto de roles (A + B + C)

| # | Tarea | Responsable |
|---|---|---|
| 5.1 | Mega: emitir eventos de inicio y fin de trabajo, transferencia confirmada y fallas (hoy solo manda `evt=estado`). Con eso: EnTransferencia real, tiempos de ciclo y AL03 a AL08 | A (+B para procesarlos) |
| 5.2 | Rutas de historial y tiempos de ciclo de la grúa, métricas de la sec. 13, exportar CSV | B |
| 5.3 | Pestaña **Grúa**: posición, trabajo actual, cola, gráfica de tiempos de ciclo (50/100/200), fallas, CSV | C |
| 5.4 | Pestaña **Reportes**: rango, etiqueta de corrida, las 8 métricas, CSV | C |
| 5.5 | Naviera, agente y autoridad: Ver detalle con historial, filtros y búsqueda, campo de tarjeta RFID en el manifiesto | C |
| 5.6 | **Adjuntar observación** (agente) y **Ver declaración** (autoridad), con sus rutas nuevas | B + C |

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
