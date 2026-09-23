# PORTUS — Fase 2

## Plan de trabajo, definiciones y división de tareas

**Arquitectura de Computadoras y Ensambladores 2**  
**Universidad de San Carlos de Guatemala — Ingeniería en Ciencias y Sistemas**

**Ponderación:** 15 pts  
**Tiempo estimado:** 100 horas  
**Equipo:** 4 integrantes (A, B, C, D)

## Punto de partida del equipo

Este plan asume que la maqueta de la Fase 1 ya funciona: las dos garitas operan correctamente, el pesaje funciona, y la grúa opera. El patio detecta únicamente si hay un contenedor en cada una de las 4 posiciones (**no se distingue el segundo nivel; el nivel se maneja de forma lógica en el servidor**).

Todo el esfuerzo de la Fase 2 se concentra en la capa digital: la Raspberry Pi, la base de datos, la web, MQTT y el bot.

## Distribución de hardware (heredada de Fase 1)

Por falta de pines, el control físico está repartido así: un **Arduino UNO por cada garita** (entrada y salida) y un **Arduino Mega** que controla la grúa junto con la zona de pesaje. En la Fase 2 estos tres microcontroladores deberán reportar sus eventos a la Raspberry Pi y obedecer sus comandos remotos.

---

# 1. Definiciones — qué es cada cosa

Antes del plan, conviene que todo el equipo entienda los términos nuevos de esta fase. Están explicados en lenguaje sencillo.

## Firmware

Es el programa que vive dentro de un microcontrolador (los Arduino). No es una app de computadora: es el código en C/C++ que se sube al Arduino y controla directamente los motores, sensores, servos y luces.

En la Fase 2, "trabajar el firmware" significa **AMPLIAR** el código de los Arduino para que además de controlar el hardware, envíen sus eventos a la Raspberry Pi por cable serial y obedezcan las órdenes que la Pi les mande.

## Raspberry Pi (computador de placa única / SBC)

Una computadora completa del tamaño de una tarjeta, con sistema operativo (Linux). Aquí vive TODO el "cerebro digital" de la Fase 2: la base de datos, la web, el broker MQTT y el bot. El PDF prohíbe usar una laptop en su lugar.

## Puente serial

El programa (del lado de la Raspberry Pi) que lee por el cable USB/serial lo que mandan los Arduino y traduce esos mensajes hacia el resto del sistema (los publica en MQTT). También toma los comandos de la plataforma y se los envía a los Arduino. Es el traductor entre el mundo Arduino y el mundo Raspberry Pi.

## Protocolo serial

El "idioma" acordado con el que los Arduino y la Pi se hablan por el cable. El PDF exige que cada mensaje tenga:

- Un delimitador (para saber dónde empieza y termina).
- Un checksum (verificación de que no llegó corrupto).
- Un número de secuencia (para detectar mensajes perdidos).
- Un ACK (confirmación de recibido) para los comandos.

## MQTT (broker / intermediario de mensajería)

Un sistema de "megáfono" que reparte los eventos a quien esté interesado. Cuando el pesaje mide un peso, se publica en un tópico (ej. `portus/evt/pesaje`) y todos los que estén suscritos lo reciben al instante.

El tablero web se actualiza así, **NO consultando la base de datos cada rato** (eso el PDF lo penaliza).

## HTTP / servidor web

El protocolo con el que las páginas web funcionan. Aquí es donde entran los actores (naviera, agente, autoridad, terminal) desde su navegador, con su usuario y contraseña.

## Base de datos

Donde se guarda todo de forma permanente: usuarios, manifiestos, turnos, inventario, citas, retenciones, alarmas y el historial de eventos.

## Bot de mensajería

Un servicio automatizado en una app de mensajería (por ejemplo Telegram) por donde el transportista pide citas, consulta el estado de su carga y recibe avisos. El transportista **NO usa la web, solo el bot**.

## Manifiesto

La "orden de trabajo" de una carga: qué contenedor, qué camión, qué operación (depósito o retiro), peso declarado y tolerancia. Lo declara la naviera.

## Levante / canal (verde o rojo)

El levante es el permiso que da la Autoridad para que la carga pueda moverse. Al darlo, asigna un canal:

- **VERDE:** pasa normal.
- **ROJO:** se revisa; el camión va al parqueo de retención tras el pesaje de entrada.

Sin levante, la talanquera físicamente no abre.

## Parqueo de retención

El antiguo ramal de la Fase 1. Ahora es un parqueo de 3 plazas (lógicas, sin sensores nuevos) donde un vehículo queda detenido cuando algo no cuadra (peso, canal rojo, fuera de horario, etc.), hasta que una persona lo resuelve desde la plataforma con **Aclarar, Corregir o Rechazar**.

## Turno

La operación viva de un camión dentro de la terminal. Tiene estados:

`Programado → EnGarita → EnPesajeEntrada → EnRuta → EnTransferencia → EnPesajeSalida → EnSalida → Retenido → Cerrado → Anulado`

Y avanza de uno a otro.

## Autonomía / modo degradado

Si se cae la comunicación con la Raspberry Pi, los Arduino **NO deben detenerse a media operación**. Terminan de forma segura lo que estaban haciendo, rechazan ingresos nuevos y guardan los eventos para enviarlos cuando se reconecte.

---

# 2. Alcance mínimo a desarrollar

Dado el tiempo limitado, este plan cubre lo obligatorio y evaluado (los **15 escenarios E01–E15**) y deja fuera todo el alcance opcional. Lo mínimo indispensable es:

- Los 3 Arduino (2 UNO de garitas + 1 Mega de grúa/pesaje) hablando por serial con la Raspberry Pi, con protocolo propio (delimitador, checksum, secuencia, ACK).
- Raspberry Pi con: broker MQTT + base de datos + servidor web + bot de mensajería.
- Las 4 interfaces web (Terminal, Naviera, Agente, Autoridad) con login y permisos por rol.
- El bot del transportista con sus 7 comandos y las notificaciones automáticas.
- La cadena documental completa: **declarar → presentar → solicitar levante → otorgar canal → cita → ingreso**.
- El parqueo de retención (3 plazas lógicas) con las causas **RT01–RT06** y las resoluciones **Aclarar / Corregir / Rechazar**.
- El sinóptico (tablero) actualizándose por MQTT en menos de 2 segundos, no por consultas periódicas.
- Autonomía ante pérdida de comunicación (modo degradado) en los Arduino.

> **Nota sobre el patio:** como el sensor solo detecta si hay o no un contenedor en cada una de las 4 posiciones (sin distinguir nivel), el nivel se maneja de forma lógica en el servidor. El servidor lleva la cuenta de cuántos contenedores depositó en cada posición. Esto se documenta y se mantiene así.

---

# 3. División del trabajo por persona

En la Fase 2 casi todo el trabajo es software de servidor, no hardware (el hardware ya funciona). Por eso cada persona conserva su zona física como mantenimiento menor, pero su carga principal es una parte de la plataforma.

| Persona | Zona física (menor) | Trabajo digital principal (mayor) |
|---|---|---|
| A | Su garita | Firmware de los Arduino + protocolo serial (el puente lado Arduino) |
| B | Zona de pesaje | Raspberry Pi: puente serial + base de datos + MQTT + lógica de turnos y retenciones |
| C | Apoya grúa | Las 4 interfaces web + login + sinóptico por MQTT |
| D | Apoya grúa | Bot de mensajería + citas + notificaciones |

## Persona A — Firmware y puente serial (lado Arduino)

Encargada de que los 3 microcontroladores (2 UNO de garitas + 1 Mega de grúa/pesaje) hablen con la Raspberry Pi. Es el enlace entre el mundo físico y el digital.

- Diseñar el protocolo serial junto con B: formato del mensaje, delimitadores, checksum, número de secuencia y ACK.
- En cada Arduino, agregar el envío de eventos a la Pi: la garita reporta identificación y validación; el pesaje reporta el peso medido; la grúa reporta cada paso de su ciclo.
- En cada Arduino, recibir y ejecutar los comandos remotos que le correspondan (`AbrirTalanquera`, `AbrirPuertaSalida` en las garitas; `AgujaParqueo`, `AgujaLiberar`, `GruaSuspender`, `GruaReanudar`, etc. en el Mega).
- Que el controlador rechace comandos inseguros y responda la causa (por ejemplo, no abrir la talanquera si hay un vehículo debajo).
- Implementar el modo degradado: si se pierde la conexión con la Pi, terminar seguro, rechazar ingresos nuevos y guardar eventos.
- Mantener el latido (heartbeat) periódico hacia la Pi cada pocos segundos.
- Que nada de esto bloquee las tareas críticas (motores, pesaje, paro de emergencia).

## Persona B — Raspberry Pi: servidor central, base de datos y MQTT

El cerebro del servidor. Recibe lo que mandan los Arduino, lo guarda, lo reparte por MQTT y maneja toda la lógica de turnos y retenciones.

- Montar la Raspberry Pi: sistema operativo, broker MQTT (por ejemplo Mosquitto) y base de datos.
- Programar el puente serial del lado Pi: leer los mensajes de los Arduino y publicarlos en los tópicos `portus/evt/...`; y enviar los comandos `portus/cmd/solicitud` a los Arduino.
- Diseñar la base de datos: usuarios, manifiestos, declaraciones, turnos, inventario, pesajes, citas, retenciones, alarmas y eventos.
- Implementar la máquina de estados del turno (`Programado → EnGarita → ... → Cerrado / Anulado`).
- Implementar las 6 causas de retención (RT01–RT06) y las 3 resoluciones (Aclarar, Corregir, Rechazar), incluyendo la asignación de plaza de parqueo.
- Validación de acceso en garita del lado servidor (levante otorgado, canal, ventana de cita).
- Asignación de posición de patio (misma política de Fase 1) manejando el nivel de forma lógica.

## Persona C — Interfaces web de los 4 roles

Todo lo que se ve en el navegador. Es mucho trabajo de front-end conectado al servidor de B.

- Login, sesión y permisos por rol. Las contraseñas no se guardan en texto plano (se usan hasheadas).
- Interfaz **TERMINAL** con sus pestañas mínimas: Sinóptico, Turnos, Retenciones, Patio y Alarmas (Citas y Reportes si da el tiempo).
- Interfaz **NAVIERA**: declarar manifiestos y ver únicamente sus propios contenedores (aislamiento entre las 2 navieras).
- Interfaz **AGENTE**: presentar la declaración y solicitar el levante.
- Interfaz **AUTORIDAD**: otorgar/retener el levante y elegir el canal (verde o rojo).
- Conectar el sinóptico a MQTT para que se actualice por suscripción en menos de 2 segundos (nunca por consultas periódicas).
- Mostrar el usuario y su rol de forma permanente en la interfaz.

## Persona D — Bot de mensajería, citas y notificaciones

El canal del transportista, que es un módulo bastante independiente. Además, la programación de citas vive aquí.

- Montar el bot (se recomienda Telegram por ser gratis y sencillo) conectado a la base de datos de B.
- Vinculación del transportista con código de 6 caracteres generado por la terminal (un solo uso, expira a los 60 minutos).
- Los 7 comandos: `/inicio`, `/vincular`, `/cita`, `/miscitas`, `/estado`, `/misturnos`, `/ayuda`.
- Programación de citas: agenda en franjas de 15 minutos, máximo 2 citas por franja, solo para contenedores con levante otorgado.
- Control de ventana: un vehículo está a tiempo si llega entre el inicio de su franja y hasta 5 minutos después del fin; si no, se genera **RT04**.
- Notificaciones automáticas: levante otorgado/retenido, cita asignada, recordatorio 1 hora antes, retención, resolución, cierre y anulación del turno.
- Aislamiento: un transportista nunca recibe información de carga que no es suya.

> **Dependencia crítica:** C y D no pueden avanzar de verdad hasta que B tenga la base de datos y MQTT andando, y A+B tengan el puente serial funcionando. Por eso la primera parte de la semana A y B trabajan juntas en la base, mientras C y D adelantan diseño con datos de prueba.

---

# 4. Plan de trabajo — de lunes a viernes

Plan de una semana intensiva. La idea es que la base (serial + Pi + BD + MQTT) quede lista al inicio para desbloquear a todos, y el resto de la semana se construya en paralelo y se integre al final.

## Lunes — Cimientos

**Meta del día:** Dejar el hardware verificado y arrancar la Raspberry Pi.

| Persona | Qué hace ese día |
|---|---|
| A | Verificar que las 2 garitas y la grúa/pesaje siguen funcionando. Junto con B, definir el protocolo serial (formato de mensaje, checksum, secuencia, ACK). |
| B | Instalar el sistema operativo de la Raspberry Pi, el broker MQTT y la base de datos. Definir el protocolo serial con A. Diseñar el esquema inicial de la base de datos. |
| C | Elegir el stack web y montar el esqueleto: proyecto, login y estructura de las 4 interfaces con datos de prueba (aún sin conectar al servidor real). |
| D | Crear el bot (Telegram), obtener el token, y dejar respondiendo `/inicio` y `/ayuda` con texto fijo. Diseñar la lógica de franjas de citas en papel. |

## Martes — El puente y la base

**Meta del día:** Que un Arduino y la Raspberry Pi se hablen de verdad.

| Persona | Qué hace ese día |
|---|---|
| A | Implementar en UN Arduino (empezar por una garita) el envío de un evento real y la recepción de un comando con ACK. Probar contra la Pi de B. |
| B | Programar el puente serial del lado Pi: leer el mensaje del Arduino y publicarlo en MQTT; recibir un comando de MQTT y mandarlo al Arduino. Verificar checksum y secuencia. |
| C | Terminar login real con permisos por rol y contraseñas hasheadas, conectado a la base de datos de B. |
| D | Programar la vinculación del transportista (`/vincular` con código de 6 caracteres) y dejarlo guardando en la base de datos. |

## Miércoles — Cadena documental y eventos

**Meta del día:** Que una declaración recorra naviera → agente → autoridad, y que los eventos fluyan por MQTT.

| Persona | Qué hace ese día |
|---|---|
| A | Extender el firmware a los 3 Arduino: garitas reportando identificación/validación, pesaje reportando peso, grúa reportando pasos. Recibir sus comandos (talanquera, aguja, grúa). |
| B | Implementar la máquina de estados del turno y la validación de acceso del lado servidor (levante + canal + ventana). Publicar eventos en los tópicos `portus/evt/...` |
| C | Interfaces NAVIERA (declarar manifiesto), AGENTE (presentar declaración, solicitar levante) y AUTORIDAD (otorgar levante + canal). Cadena documental funcionando. |
| D | Comando `/cita` completo: ofrecer franjas con capacidad, asignar la cita y guardarla. Comando `/estado` y `/misturnos` leyendo de la base de datos. |

## Jueves — Retenciones, sinóptico y notificaciones

**Meta del día:** Que las excepciones funcionen y el tablero se vea en tiempo real.

| Persona | Qué hace ese día |
|---|---|
| A | Implementar el modo degradado (pérdida de comunicación) y los rechazos de comandos inseguros con su causa. Latido periódico hacia la Pi. |
| B | Lógica de retenciones RT01–RT06, asignación de plaza de parqueo y resoluciones Aclarar / Corregir / Rechazar. Generación de alarmas (AL01–AL14). |
| C | Sinóptico (Terminal) actualizándose por MQTT en menos de 2 s. Pestañas Turnos, Retenciones, Patio y Alarmas con sus controles. |
| D | Notificaciones automáticas al transportista (levante, cita, retención, resolución, cierre). Recordatorio 1 hora antes. Aislamiento entre transportistas. |

## Viernes — Integración, pruebas y documentación

**Meta del día:** Correr los 15 escenarios de punta a punta y documentar.

| Persona | Qué hace ese día |
|---|---|
| A | Prueba de tolerancia a fallos: desconectar la Pi con una operación en curso (E14) y verificar el modo degradado. Apoyar la integración de la grúa. |
| B | Ensayar la reconciliación al reconectar, verificar métricas y reporte. Cerrar cabos de la base de datos y el puente. |
| C | Ensayar los escenarios que se ven en web (E01–E13). Ajustes visuales y de permisos. Pestañas Citas y Reportes si hay tiempo. |
| D | Ensayar los escenarios del bot (E04, E06, notificaciones). Preparar la demostración desde un teléfono real. |
| TODOS | Correr los 15 escenarios como los 4 bloques del guion del PDF. Documentar credenciales, protocolo serial e inventario 3D. Ensayo general de la presentación. |

---

# 5. Prioridades y advertencias

## Qué NO se puede dejar para el final

- **El puente serial (A + B):** si esto no funciona, nada de la plataforma se puede probar de verdad. Es lo primero.
- **La base de datos y MQTT (B):** C y D dependen de que exista. Debe estar el martes.
- **El sinóptico por MQTT (C):** es lo más revisado y penalizado si se hace por consultas periódicas.
- **La autonomía ante fallo (A):** el escenario E14 se demuestra desconectando la Pi en vivo.

## Reglas del PDF que se evalúan sí o sí

- Tres protocolos distintos: **Serial (Arduino↔Pi), MQTT (eventos), HTTP (web)**. Usar uno solo para todo se reprueba.
- El servidor corre en la Raspberry Pi, no en una laptop.
- El tablero se actualiza por suscripción a MQTT, no por consultas periódicas.
- Las contraseñas no se guardan en texto plano.
- Un usuario no puede ver datos de otro del mismo rol (2 navieras y 2 transportistas para probarlo).
- El paro de emergencia no se acciona ni rearma desde la plataforma: sigue siendo físico.

## Recomendación de stack (para ir rápido)

Sugerencia sencilla y bien documentada para el equipo:

- **Node.js o Python** en la Raspberry Pi para el servidor y el puente serial.
- **Mosquitto** como broker MQTT.
- Una base de datos ligera como **SQLite o PostgreSQL**.
- El front web con un framework simple.
- **Telegram** para el bot (gratis, con librerías fáciles).

Lo importante no es cuál elijan, sino que los tres protocolos (**serial, MQTT, HTTP**) estén separados como exige el PDF.

> **Idea final:** el hardware ya está resuelto. El éxito de la Fase 2 depende de montar bien la capa digital y de que los tres microcontroladores (2 UNO + 1 Mega) se integren a la Raspberry Pi. Prioricen el puente serial y la base de datos al inicio de la semana; todo lo demás se construye encima de eso.
