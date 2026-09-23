# Observaciones de revisión — Firmware (Persona A)

**Fecha de revisión original:** 2026-09-21
**Fecha de actualización (correcciones aplicadas):** 2026-09-22
**Archivos revisados/modificados:**
- `firmware/uno_garita_entrada/ENTRADAP1_ARQ2.ino`
- `firmware/uno_garita_salida/SALIDAP1_ARQ2.ino`
- `firmware/mega_grua_pesaje/PORTUS_Fase1_v2.ino`
- `bridge/bridge.py` (extensión necesaria para que el modo degradado funcione, ver punto 5)

**Contra qué se comparó:** tareas de Persona A en `docs originales/PORTUS_Fase2_Plan.md` (sección 3) y requisitos de `docs originales/Fase_2_PORTUS.md` (secciones 10, 11, 12 y "Requerimientos técnicos").

**Verificación realizada:** los 3 `.ino` se compilaron con `arduino-cli` (`arduino:avr:uno` para las garitas, `arduino:avr:mega` para el Mega) después de cada cambio — compilan sin errores. El flujo `bridge.py` se volvió a probar de punta a punta con puertos seriales virtuales (`socat`) simulando los 3 Arduinos, incluyendo el nuevo evento de pesaje y el nuevo ping periódico.

---

## Checklist contra las tareas de Persona A

| # | Tarea (según el plan) | Estado |
|---|---|---|
| 1 | Diseñar protocolo serial (delimitador, checksum, secuencia, ACK) | ✅ Cumplido |
| 2 | Enviar eventos a la Pi (garita, pesaje, grúa) | ✅ **Corregido** — ya se publica el pesaje |
| 3 | Recibir y ejecutar los 13 comandos remotos | ✅ Cumplido |
| 4 | Rechazar comandos inseguros con causa | ⚠️ Mejorado, con una limitación explícitamente aceptada (ver punto 4) |
| 5 | Modo degradado ante pérdida de comunicación | ✅ **Implementado** (garitas + Mega, requiere el ping nuevo en `bridge.py`) |
| 6 | Heartbeat periódico (≤5s) | ✅ Cumplido |
| 7 | No bloquear tareas críticas | ✅ **Corregido** — se quitó el `delay(2500)` |
| 8 | (Continuidad Fase 1) Paro de emergencia con rearme | ⏸️ Diferido a propósito (ver punto 8) |

---

## 1. Protocolo serial — OK (sin cambios)

Frame `<PORTUS|SRC|SEQ|KIND|TOPIC|PAYLOAD|CHK>` implementado igual en los 3 archivos. Checksum de 8 bits (suma ASCII mod 256, hex de 2 dígitos), número de secuencia incremental por dispositivo, ACK/REJ con causa. Coincide con lo que `bridge/protocol.py` espera parsear (verificado).

Nota menor sin cambios: el checksum es débil (no detecta bytes transpuestos); aceptable para el alcance del proyecto.

---

## 2. Eventos hacia la Pi — ✅ corregido (pesaje ahora se publica)

- ✅ Garita entrada/salida: sin cambios, ya reportaban `evento=rfid`, `evento=autorizado`, `evento=rechazado`, etc.
- ✅ Grúa: sin cambios, ya reportaba cada paso de su ciclo vía `cambiarEstado()`.
- ✅ **Pesaje: corregido.** Se agregó `emitirEventoPesajePortus()` en `PORTUS_Fase1_v2.ino`, llamada al final de `decidirRuta()`. Publica en el tópico `pesaje`: `medido`, `esperado`, `tolerancia`, `resultado` (`ok`/`fuera_tolerancia`) y `operacion` (`deposito`/`retiro`). Se verificó en vivo que el evento llega hasta el backend vía el bridge.

**Limitación que sigue pendiente (no resuelta en esta pasada, requiere trabajo de B y posiblemente rediseño conjunto):** el Mega sigue comparando contra la constante hardcodeada `PESO_DECLARADO`/`TOLERANCIA` para decidir la ruta física (mover la aguja) — solo se agregó el aviso a la Pi, no se movió la decisión de retención al servidor. Eso implica un rediseño más grande (que el servidor mande el peso declarado real del manifiesto antes del pesaje, o que decida la retención y comande la aguja después de recibir el evento) que no se hizo en esta sesión por ser un cambio de arquitectura, no un fix puntual.

---

## 3. Comandos remotos — los 13 están implementados (sin cambios)

Repartidos así:
- **UNO entrada:** `AbrirTalanquera`, `CerrarTalanquera`
- **UNO salida:** `AbrirPuertaSalida` (+ `CerrarPuertaSalida`, extra no exigido pero inofensivo)
- **Mega:** `GruaReferenciar`, `GruaSuspender`, `GruaReanudar`, `AgujaRecta`, `AgujaParqueo`, `AgujaLiberar`, `PosicionBloquear`, `PosicionLiberar`, `ModoMantenimiento`, `AlarmaSilenciar`

---

## 4. Condiciones de rechazo — mejorado parcialmente

| Comando | Condición de rechazo exigida | Estado |
|---|---|---|
| `AbrirTalanquera` / `CerrarTalanquera` | Vehículo bajo la talanquera | ✅ Sin cambios, ya válida |
| `AbrirPuertaSalida` | Vehículo bajo la puerta | ✅ Sin cambios, ya válida |
| `GruaReferenciar` | Carga adherida o trabajo en ejecución | ✅ Sin cambios, ya válida |
| `GruaSuspender` / `AlarmaSilenciar` | Nunca se rechazan | ✅ Sin cambios |
| `GruaReanudar` | Grúa en falla sin rearme | ✅ Sin cambios, ya válida |
| `PosicionBloquear` | Posición es origen/destino de trabajo activo | ✅ Sin cambios, ya válida |
| `ModoMantenimiento` | Trabajo de grúa en ejecución **o vehículo en transferencia** | ✅ **Corregido** — se agregó el chequeo de `camionPresente` |
| `PosicionLiberar` | La inconsistencia física que originó el bloqueo persiste | ⚠️ **Mejorado, no completo.** Ahora rechaza si la posición no está `BLOQUEADA` (`causa=posicion_no_bloqueada`, antes hacía un no-op silencioso) y si es origen/destino de trabajo activo (`causa=posicion_en_trabajo`, antes no lo validaba). **No** se agregó una revalidación contra el sensor físico de la celda: el firmware no guarda qué inconsistencia específica motivó el bloqueo (ese contexto vive en el manifiesto/servidor), así que inventar una heurística basada solo en "¿está ocupada ahora?" podía rechazar liberaciones legítimas (una celda puede estar físicamente ocupada de forma válida). Queda documentado como limitación conocida en el propio código. |
| `AgujaRecta` / `AgujaParqueo` / `AgujaLiberar` | Vehículo sobre la aguja | ⏸️ **Diferido a propósito** — decisión explícita: no existe sensor dedicado en el Mega para esto (los únicos sensores de presencia ahí son el ultrasónico de la zona de transferencia y los IR de patio). Se decidió no adivinar una aproximación y dejarlo pendiente hasta tener un sensor real o una decisión de diseño. |

---

## 5. Modo degradado — ✅ implementado

**Diseño:** el PDF solo exige el latido Controlador→Servidor (sección 10.2), pero eso no le sirve al controlador para saber si la Pi sigue viva — no hay nada que el controlador reciba periódicamente. Se agregó una extensión mínima al protocolo: `bridge.py` ahora manda un frame `PIN` (kind nuevo, tópico `estado`, payload vacío) a **cada** Arduino cada 3 segundos (`ping_loop()`, nuevo método en `PortusBridge`).

**En cada `.ino`:**
- `ultimaActividadPiMs` se actualiza con **cualquier** frame válido recibido de la Pi (`CMD` o `PIN`), dentro de `procesarComandosRemotos()`/`procesarComandosPortus()`.
- `actualizarModoDegradado()` compara `millis() - ultimaActividadPiMs` contra `UMBRAL_DEGRADADO_MS` (10000 ms, ~3x el periodo del ping) y actualiza la bandera `modoDegradado`.
- **Garita de entrada:** si `modoDegradado` es verdadero, cualquier tarjeta leída se rechaza con motivo "Modo degradado" (no autoriza ingresos nuevos, tal como pide la sección 12.1.3) y el LCD muestra "MODO DEGRADADO / Sin enlace a Pi" en vez de "Acerca tarjeta".
- **Garita de salida:** deliberadamente **no bloquea** la salida (la sección 12.1.2 pide dejar completar lo que ya está dentro de la terminal); solo reporta el estado en el heartbeat.
- **Mega:** se agregó el tracking (`modoDegradadoGrua`) y se refleja en el heartbeat (`degradado=1/0`); no se cambió el comportamiento de la grúa en sí en esta pasada (ver limitación abajo).

**Verificado en vivo:** con `bridge.py` corriendo contra 3 puertos seriales virtuales, se confirmó que el ping llega cada 3s al lado "Arduino" del puerto.

**Limitación conocida:** esto es una extensión de protocolo no descrita en el PDF (que solo define el heartbeat en un sentido). Si el profesor pregunta específicamente por el catálogo de tópicos "tal cual está en el PDF", hay que estar listos para explicar por qué se agregó `PIN` y que es necesario para que el controlador pueda detectar la ausencia del servidor (sin esto, "modo degradado" nunca se hubiera activado con el servidor realmente encendido pero inactivo). También falta la parte de "conservar en memoria local los eventos ocurridos durante la desconexión" (punto 4 de la sección 12.1) — eso no se implementó (requeriría buffer circular en RAM o EEPROM, es una pieza más grande que no entraba en esta pasada de correcciones puntuales).

---

## 6. Heartbeat — OK (sin cambios)

Los 3 archivos emiten `HBT` cada 5000 ms exactos. Cumple el límite de la sección 10.2 del PDF. El payload del Mega y de ambas garitas ahora incluye también `degradado=0/1`.

---

## 7. Tareas críticas no bloqueantes — ✅ corregido el punto pendiente

- ✅ **Pesaje:** sin cambios, ya usaba Timer2 CTC + `PORTB` directo.
- ⚠️ **Motores de la grúa:** sin cambios — sigue usando la librería `Stepper` gateada por `tickMotorListo()`. Se mantiene como nota (no como pendiente urgente): funciona en la práctica porque las constantes están sincronizadas, pero es un acoplamiento frágil si alguien las cambia sin coordinar.
- ✅ **`rechazar()` en ambas garitas: corregido.** Se quitó el `delay(2500)`. Ahora `rechazar()` solo arma una bandera (`mostrandoRechazo`) y guarda `millis()`; el propio `loop()` retira el mensaje después de `DURACION_MENSAJE_RECHAZO_MS` sin bloquear heartbeat, comandos remotos ni lectura de sensores mientras tanto.

---

## 8. Paro de emergencia — diferido a propósito

**Decisión tomada explícitamente (2026-09-22):** no se implementó todavía. El equipo no tenía claro si existe un pin del microcontrolador que lea el estado del paro de emergencia, así que se dejó pendiente de confirmar en vez de adivinar un pin (leer un pin flotante podría generar falsas alarmas AL02 constantes).

Sigue documentado el problema original: si el paro de emergencia es un circuito puramente físico (corta motores sin pasar por el microcontrolador), la plataforma nunca podrá generar la alarma obligatoria **AL02** sin al menos un pin de lectura (no de control) de su estado.

**Acción pendiente:** cuando el equipo confirme si existe (y en qué Arduino/pin) una señal legible del paro de emergencia, agregar la lectura y el evento `portus/evt/alarma` con código `AL02`.

---

## Resumen priorizado — estado actualizado

1. ~~Validar "vehículo sobre la aguja"~~ — ⏸️ Diferido a propósito (sin sensor dedicado, decisión explícita de no adivinar).
2. ~~Publicar el peso medido~~ — ✅ Hecho.
3. ~~Implementar modo degradado~~ — ✅ Hecho (garitas + Mega, con extensión de ping en `bridge.py`).
4. ~~Agregar lectura del paro de emergencia~~ — ⏸️ Diferido a propósito (falta confirmar si existe el pin).
5. ~~Quitar el `delay(2500)` bloqueante~~ — ✅ Hecho.
6. ~~Afinar `PosicionLiberar` y `ModoMantenimiento`~~ — ✅ `ModoMantenimiento` completo. `PosicionLiberar` mejorado parcialmente (ver punto 4, limitación documentada en el propio código).
7. ~~Confirmar `AgujaParqueo`/`AgujaLiberar`~~ — ✅ Hecho: se confirmó que deben ser distintas y se agregó `AGUJA_LIBERANDO` como tercera posición del servo, con un ángulo de ejemplo (`45`) marcado `TODO-AJUSTAR` para calibrar en banco de pruebas contra el mecanismo real.

## Pendientes reales que quedan abiertos

- Calibrar el ángulo real de `AGUJA_LIBERANDO` en el Mega (hoy es un valor de ejemplo).
- Confirmar con el equipo el pin (si existe) del paro de emergencia.
- Decidir cómo instrumentar (o no) "vehículo sobre la aguja".
- Mover la decisión de retención por peso (RT01/RT02) del firmware al servidor — el firmware ya avisa el peso medido, pero sigue decidiendo solo con una constante fija.
- Implementar el buffer local de eventos durante la desconexión (punto 4 de la sección 12.1 del PDF) — el modo degradado ya se detecta y bloquea ingresos, pero no se guardan eventos para reconciliar después.

---

## Pendiente para la siguiente sesión

Sigue Persona C (interfaces web) y Persona D (bot de mensajería) — no se encontró ningún código de ninguno de los dos en esta máquina; hay que ubicar dónde vive ese trabajo antes de revisarlo. B (`backend/app.py` + `models.py`) ya quedó revisado y documentado en `Observaciones_Backend_PersonaB.md`.
