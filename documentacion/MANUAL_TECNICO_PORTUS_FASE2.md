## Propósito y objetivos

PORTUS Fase 2 conecta la maqueta autónoma de la Fase 1 con una plataforma de supervisión, control remoto y gestión documental ejecutada sobre un computador de placa única. El sistema integra controladores Arduino, un puente serial-MQTT, un backend con persistencia, interfaces web por rol y un canal de mensajería para el transportista.

El objetivo general es conservar el control físico y los enclavamientos en los microcontroladores, mientras el servidor coordina las decisiones administrativas y mantiene una representación digital trazable de la terminal. Los objetivos técnicos de la implementación son:

- Transportar eventos y comandos mediante un protocolo serial delimitado, con checksum, secuencia y respuestas.
- Distribuir la telemetría mediante MQTT y actualizar el sinóptico por suscripción, sin consultas periódicas.
- Validar accesos, manifiestos, levantes, citas, retenciones y permisos en el servidor.
- Mantener la máquina de estados de cada turno y su línea de tiempo.
- Administrar el patio, la cola de trabajos de grúa, las alarmas y las métricas de operación.
- Permitir que el transportista solicite citas y consulte únicamente su carga mediante Telegram.
- Continuar de forma segura ante pérdida de comunicación.

## Alcance implementado

| Subsistema        | Comportamiento implementado                                                                                                      |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Enlace serial     | Puertos independientes a 9600 baudios, frames PORTUS, checksum, secuencia por emisor y decodificación de tramas fragmentadas.    |
| Puente MQTT       | Traduce eventos y latidos seriales a `portus/evt/#`, comandos MQTT a serial y respuestas a `portus/cmd/respuesta`.               |
| Backend           | FastAPI, SQLite y SQLAlchemy para usuarios, manifiestos, turnos, citas, retenciones, patio, alarmas, eventos, ciclos y reportes. |
| Web TERMINAL      | Ocho pestañas: Operación, Turnos, Retenciones, Patio, Grúa, Alarmas, Citas y Reportes.                                           |
| Otros roles web   | NAVIERA con dos pestañas, AGENTE con dos y AUTORIDAD con tres.                                                                   |
| Transportista     | Bot de Telegram con vinculación temporal, siete comandos, citas, aislamiento de información y notificaciones automáticas.        |
| Tiempo real       | MQTT hacia WebSocket, el navegador recibe eventos y solicitudes de recarga selectiva mediante `portus/srv/cambio`.               |
| Cadena documental | Manifiesto, declaración, solicitud de levante, decisión de autoridad y canal verde o rojo.                                       |
| Turnos            | Diez estados, eventos cronológicos, pesajes, estación, posición y cierre o anulación.                                            |
| Retenciones       | RT01 a RT06, tres plazas, autorización por rol y resoluciones Aclarar, Corregir y Rechazar.                                      |
| Patio y grúa      | Cuatro posiciones, dos niveles, política secuencial, ciclos, cola, remociones e inventario actualizado por confirmación física.  |
| Alarmas           | Catálogo AL01 a AL14, persistencia, reconocimiento y generación automática de varias alarmas.                                    |
| Reportes          | Ocho métricas por rango, corridas guardadas y exportación CSV.                                                                   |

## Arquitectura y distribución física

### Controladores y relación entre módulos

~~~mermaid
flowchart LR
    UE[UNO entrada<br/>RFID, barrera y pesaje]
    US[UNO salida<br/>RFID y puerta]
    MG[Mega 2560<br/>grúa, transferencia y patio]

    UE -->|USB serial PORTUS| BR[Puente serial-MQTT]
    US -->|USB serial PORTUS| BR
    MG -->|USB serial PORTUS| BR

    BR <-->|MQTT 1883| MQ[Broker Mosquitto]
    MQ --> BE[Backend FastAPI<br/>127.0.0.1:8100]
    MQ --> WEB[Web FastAPI<br/>0.0.0.0:8000]
    MQ --> BOT[Bot Telegram]

    BE <--> DB[(SQLite<br/>portus_core.db)]
    WEB -->|HTTP local| BE
    BOT <--> DB
    WEB -->|WebSocket /ws/terminal| T[Operador TERMINAL]
    WEB --> N[Naviera / Agente / Autoridad]
    BOT --> TR[Transportista]
~~~

### Distribución de responsabilidades

| Capa | Responsabilidad |
| --- | --- |
| Microcontroladores | Sensores, motores, servos, señalización, temporización local, enclavamientos y confirmación física. |
| Puente | Integridad del frame, separación de flujos seriales y traducción serial-MQTT. |
| Broker | Distribución de eventos a backend, web y otros consumidores. |
| Backend | Reglas de negocio, persistencia, auditoría, estado digital, alarmas y reportes. |
| Web | Autenticación, sesión, permisos por rol, visualización y emisión de solicitudes válidas. |
| Bot | Interacción del transportista, citas y entrega de notificaciones. |

### Flujo integrado de una operación

~~~mermaid
sequenceDiagram
    participant N as NAVIERA
    participant A as AGENTE
    participant U as AUTORIDAD
    participant T as TRANSPORTISTA
    participant W as Plataforma
    participant C as Controladores

    N->>W: Crear manifiesto
    A->>W: Presentar declaración y solicitar levante
    U->>W: Otorgar levante y canal
    W-->>T: Notificación
    T->>W: Solicitar cita
    C->>W: RFID de entrada
    W->>C: AbrirTalanquera o RechazarIngreso
    C->>W: Pesaje / transferencia / grúa / patio
    W->>C: TrabajoGrua y comandos seguros
    C->>W: RFID y salida completada
    W-->>T: Turno cerrado
~~~

## Hardware y conexiones

### Componentes

| Elemento                       | Uso                                                                            |
| ------------------------------ | ------------------------------------------------------------------------------ |
| Arduino Uno de entrada         | RFID, LCD, talanquera, sensores IR, semáforo, aguja y procesamiento de pesaje. |
| Arduino Uno de salida          | RFID, LCD, puerta, sensores IR, semáforo y lista local de vehículos.           |
| Arduino Mega 2560              | Grúa, sensores del patio, marca óptica, ultrasonido, electroimán y LEDs.       |
| Computador de placa única      | Mosquitto, backend, web, puente y bot.                                         |
| MFRC522, uno por garita        | Lectura de UID por SPI.                                                        |
| LCD I2C 16 x 2, uno por garita | Estado y causa de rechazo, dirección `0x27`.                                   |
| Servos                         | Talanquera de entrada, puerta de salida y aguja.                               |
| Dos motores paso a paso        | Traslación horizontal e izaje de la grúa.                                      |
| Electroimán                    | Agarre de la carga mediante una etapa de potencia externa.                     |
| Sensores IR de patio           | Estado físico de P1 a P4.                                                      |
| Sensor óptico                  | Marcas de posición del riel.                                                   |
| Sensor ultrasónico             | Presencia estable del camión en transferencia.                                 |
| Hub USB alimentado             | Recomendado para evitar desconexiones de las tres placas.                      |

### Pines del UNO de entrada

| Dispositivo o señal | Pin |
| --- | --- |
| MFRC522 SS / RST | D10 / D9 |
| Servo de talanquera | D3 |
| IR antes / después | D2 / D4 |
| LED rojo / amarillo / verde | D6 / D5 / D7 |
| Servo de aguja | A0 |
| Flecha verde / ámbar | A2 / A3 |
| Comunicación a salida RX / TX | A1 / D8 mediante `SoftwareSerial` |
| LCD | I2C `0x27` |
| Enlace a Raspberry Pi | `Serial` USB a 9600 baudios |
### Pines del UNO de salida

| Dispositivo o señal | Pin |
| --- | --- |
| MFRC522 SS / RST | D10 / D9 |
| Servo de puerta | D3 |
| IR antes / después | D2 / D4 |
| LED rojo / amarillo / verde | D6 / D5 / D7 |
| Comunicación desde entrada RX / TX | A1 / D8 mediante `SoftwareSerial` |
| LCD | I2C `0x27` |
| Enlace a Raspberry Pi | `Serial` USB a 9600 baudios |
### Pines del Mega de grúa

| Dispositivo o señal | Pines |
| --- | --- |
| Motor horizontal | 8, 10, 9, 11 |
| Motor vertical | 4, 6, 5, 7 |
| Electroimán | 30 |
| IR de P1, P2, P3 y P4 | 31, 32, 33 y 34 |
| Marca óptica | 35 |
| Ultrasonido TRIG / ECHO | 36 / 37 |
| Semáforo rojo / amarillo / verde | 47 / 48 / 49 |
| LED libre P1 a P4 | 22, 25, 28 y 44 |
| LED ocupada P1 a P4 | 23, 26, 29 y 45 |
| Enlace a Raspberry Pi | `Serial` USB a 9600 baudios |
### Enlaces de red y puertos

| Puerto o medio           | Servicio                        |
| ------------------------ | ------------------------------- |
| USB serial, 9600 baudios | Tres Arduinos hacia `bridge.py` |
| TCP 1883                 | Mosquitto MQTT                  |
| TCP 8100                 | Backend FastAPI                 |
| TCP 8000                 | Aplicación web                  |
| Internet                 | API de Telegram                 |

## Organización del proyecto

~~~text
ARQUI2_F2_G03/
├── backend/
│   ├── app.py                 API, MQTT y procesos de vigilancia
│   ├── models.py              Modelo SQLAlchemy y migración incremental
│   ├── servicios.py           Reglas de negocio
│   ├── orquestador.py         Eventos físicos -> cambios de turno
│   ├── grua.py                Cola, ciclos, inventario y remociones
│   ├── reportes.py            Métricas y CSV
│   ├── catalogos.py           Estados, alarmas, roles y parámetros
│   ├── security.py            PBKDF2-HMAC-SHA256
│   └── seed.py                Usuarios, transportistas, tarjetas y demo
├── bridge/
│   ├── bridge.py              Tres seriales <-> MQTT
│   └── protocol.py            Codificador, parser y checksum
├── web_c/
│   └── app/
│       ├── main.py            Sesión, permisos, proxies y WebSocket
│       ├── templates/         Cinco páginas HTML
│       └── static/            Interacción, estilos y vistas por rol
├── bot_d/
│   └── app/main.py            Bot Telegram y modo CLI
├── firmware/
│   ├── uno_garita_entrada/
│   ├── uno_garita_salida/
│   └── mega_grua_pesaje/
├── mosquitto/mosquitto.conf
├── docs/
├── run_all.sh
├── status_all.sh
└── stop_all.sh
~~~

### Dependencias

| Módulo | Dependencias principales |
| --- | --- |
| Backend | FastAPI 0.116.1, Uvicorn 0.35.0, SQLAlchemy 2.0.43, Paho MQTT 2.1.0 |
| Web | FastAPI, Jinja2, itsdangerous, Paho MQTT y WebSockets |
| Bot | python-telegram-bot 21.6, SQLAlchemy y Paho MQTT |
| Bridge | pyserial 3.5 y Paho MQTT |
| Firmware | SPI, MFRC522, LiquidCrystal_I2C, Servo, SoftwareSerial y Stepper |

## Modelo de datos y comunicación

### Entidades persistentes

| Tabla | Propósito |
| --- | --- |
| `usuarios` | Usuario web, rol, nombre, contraseña con hash y estado. |
| `transportistas` | Transportista, código de vinculación, expiración y chat de Telegram. |
| `vehiculos` | UID RFID, placa y transportista propietario. |
| `contenedores` | Catálogo permitido de contenedores de la maqueta. |
| `manifiestos` | Operación, peso, tolerancia, naviera, transportista, vehículo, estado y canal. |
| `declaraciones` | Número, régimen, descripción, valor y agente. |
| `citas` / `franjas_bloqueadas` | Ventanas de 15 minutos, capacidad y bloqueos. |
| `turnos` / `turno_estados` | Estado actual y evolución temporal. |
| `eventos_turno` | Línea de tiempo con origen, descripción y valores. |
| `intentos_ingreso` | Rechazos de entrada y salida sin crear turno. |
| `retenciones` / `parqueo_plazas` | Causa, resolución, evidencia de peso y plaza. |
| `patio` | Estado, dos niveles, permanencia y remociones por posición. |
| `grua_ciclos` | Depósito, retiro o remoción, duración, distancia y resultado. |
| `alarmas` | Código, severidad, referencia, estado y reconocimiento. |
| `event_log` | Copia de cada mensaje MQTT recibido por el backend. |
| `link_devices` / `link_status` | Estado de enlace global y por controlador. |
| `command_audit` | Solicitud, resultado y respuesta de comandos remotos. |
| `notificaciones` | Bandeja persistente del bot. |
| `corridas` / `configuracion` | Reportes guardados y política de patio. |

La base se almacena por defecto en `backend/portus_core.db`. `make_db()` crea tablas y aplica adiciones de columnas requeridas por versiones anteriores.

### Estados del turno

~~~mermaid
stateDiagram-v2
    [*] --> Programado
    Programado --> EnGarita
    EnGarita --> EnPesajeEntrada
    EnPesajeEntrada --> EnRuta
    EnRuta --> EnTransferencia
    EnTransferencia --> EnPesajeSalida
    EnPesajeSalida --> EnSalida
    EnSalida --> Cerrado
    EnGarita --> Retenido
    EnPesajeEntrada --> Retenido
    EnRuta --> Retenido
    EnTransferencia --> Retenido
    EnPesajeSalida --> Retenido
    EnSalida --> Retenido
    Retenido --> EnRuta
    Retenido --> EnSalida
    Retenido --> Anulado
    Programado --> Anulado
    EnGarita --> Anulado
    EnPesajeEntrada --> Anulado
    EnRuta --> Anulado
    EnTransferencia --> Anulado
    EnPesajeSalida --> Anulado
~~~
### Protocolo serial PORTUS

Cada frame usa una línea con siete campos:

~~~text
<PORTUS|SRC|SEQ|KIND|TOPIC|PAYLOAD|CHK>
~~~

| Campo | Descripción |
| --- | --- |
| `SRC` | `UNO_ENTRADA`, `UNO_SALIDA`, `MEGA_GRUA` o `RPI`. |
| `SEQ` | Secuencia incremental por emisor. |
| `KIND` | `EVT`, `CMD`, `ACK`, `REJ`, `HBT` o la extensión `PIN`. |
| `TOPIC` | Área lógica: `garita`, `pesaje`, `grua`, `patio`, `estado` o `cmd`. |
| `PAYLOAD` | Pares `clave=valor` separados por punto y coma. |
| `CHK` | Suma ASCII del cuerpo módulo 256, hexadecimal de dos dígitos. |

### Latidos y detección de enlace

- Cada placa emite `HBT` cada cinco segundos.
- El puente envía `PIN` a cada placa cada tres segundos.
- Los UNO declaran modo degradado después de diez segundos sin un frame válido de la Pi.
- El backend marca perdido un dispositivo después de quince segundos sin latido y genera AL01.
- La web muestra la hora del último dato y deja de presentarlo como actual.

### Tópicos MQTT

| Tópico | Contenido |
| --- | --- |
| `portus/evt/garita` | RFID, validación y rechazo de entrada. |
| `portus/evt/pesaje` | Meseta, resultado y peso si está disponible. |
| `portus/evt/aguja` | Estado de la aguja. |
| `portus/evt/transferencia` | Alineación, aborto e inicio de transferencia. |
| `portus/evt/grua` | Estado, inicio, fin y fallo del ciclo. |
| `portus/evt/patio` | Depósito o retiro confirmado. |
| `portus/evt/salida` | RFID, autorización y salida completada. |
| `portus/evt/alarma` | Alarma originada por una placa. |
| `portus/evt/estado` | Latido y estado general. |
| `portus/cmd/solicitud` | Solicitud de comando hacia una placa. |
| `portus/cmd/respuesta` | `ACK` o `REJ` del controlador. |
| `portus/srv/alarma` | Alarma nueva ya confirmada en la base. |
| `portus/srv/cambio` | Entidad e identificador que cambiaron. |

Los mensajes MQTT enviados por el puente contienen `id`, `ts`, `origin`, `type`, `seq` y `data`. El backend confirma primero sus transacciones y después publica comandos o avisos de cambio cuando usa el orquestador diferido.

## Control de acceso y salida

### Roles e interfaces

| Rol | Pestañas o canal |
| --- | --- |
| TERMINAL | Operación, Turnos, Retenciones, Patio, Grúa, Alarmas, Citas y Reportes |
| NAVIERA | Manifiestos y Mis contenedores |
| AGENTE | Declaraciones y Seguimiento |
| AUTORIDAD | Solicitudes de levante, Retenciones aduaneras y Consulta de carga |
| TRANSPORTISTA | Telegram, sin acceso web |

Las rutas `/api/terminal`, `/api/naviera`, `/api/agente` y `/api/autoridad` verifican el rol de la cookie en el servidor. 
### Entrada

El UNO publica `evento=rfid;uid=...`. `orquestador.py` resuelve el vehículo y el manifiesto, valida levante, cita, parqueo y turno activo, y publica:

~~~text
AbrirTalanquera target=UNO_ENTRADA uid=<UID> op=<DEPOSITO|RETIRO>
RechazarIngreso target=UNO_ENTRADA uid=<UID> motivo=<texto LCD>
~~~

La respuesta válida debe llegar en breve tiempo. Una respuesta tardía con UID se rechaza como `sin_validacion_pendiente`. Si no existe enlace, el UNO rechaza el nuevo ingreso y lo reporta como decisión local.

### Salida

El UNO de entrada comunica `ENTRO:<UID>` al UNO de salida por `SoftwareSerial`. La salida conserva hasta diez UID.

Al leer RFID en salida, el controlador publica `evento=rfid_salida`. El servidor autoriza únicamente un turno elegible. Ante pérdida del servidor, el UNO permite salir a un UID presente en la lista local. `salida_completada` cierra el turno, libera plazas asociadas y conserva la posición física del inventario.

### Canal del transportista

El operador genera un código de seis caracteres, de un uso y con expiración de sesenta minutos. El bot implementa:

- `/inicio`
- `/vincular CODIGO`
- `/cita`
- `/miscitas`
- `/estado CONTENEDOR`
- `/misturnos`
- `/ayuda`

Un chat no vinculado recibe siempre la instrucción de vinculación. Un texto no reconocido recibe una respuesta de ayuda. El bot puede ejecutarse sin token en modo CLI para probar los mismos comandos.

## Grúa, depósito e inventario

### Política de asignación

La política `secuencial` conserva el comportamiento de Fase 1:

1. Primera posición libre P1 a P4.
2. Si todas tienen nivel 1, primera posición no bloqueada con nivel 2 libre.
3. Una posición origen o destino no puede bloquearse durante un movimiento.

El backend reserva la posición antes de enviar `TrabajoGrua`, pero actualiza el inventario únicamente al recibir `patio evento=deposito` o `patio evento=retiro`.

### Cola y ciclos

El turno más antiguo en `EnRuta` recibe un único trabajo:

~~~text
TrabajoGrua target=MEGA_GRUA op=DEPOSITO pos=2
TrabajoGrua target=MEGA_GRUA op=RETIRO pos=3
~~~

El Mega puede responder `modo_mantenimiento`, `trabajo_en_curso` u `op_invalida`. Un rechazo devuelve el turno a la cola. `trabajo_inicio` abre un `GruaCiclo` y mueve el turno a `EnTransferencia`. `trabajo_fin` registra duración y tramos.

### Depósito

1. El servidor elige y reserva una posición.
2. El Mega espera el camión estable.
3. Baja, activa el electroimán, sube y se traslada.
4. Deposita y verifica la celda.
5. Publica `patio evento=deposito;pos=N`.
6. El servidor coloca el contenedor en nivel 1 o 2 y registra la hora.
7. El Mega regresa a P0 y publica el fin del trabajo.

### Retiro y remociones

El servidor localiza el contenedor y envía su posición. Si el contenedor solicitado está en nivel 1 y existe otro en nivel 2, `grua.py` registra un ciclo `REMOCION` para el superior, elige un destino y después retira el contenedor objetivo.

### Aborto e inventario

Un aborto marca el ciclo como `abortado`, libera reservas y conserva el inventario previo. Las causas del Mega se relacionan con:

- `sin_referencia` o `sin_marca`: AL03.
- `deposito_no_confirmado`: AL07.
- `camion_movido`: AL08.
- Todo aborto de trabajo: AL06.

## Pesaje, retiro, remociones y cola de trabajos

### Adquisición de peso

Después de la autorización, el controlador de entrada ejecuta la secuencia de pesaje y publica una meseta con su resultado:

~~~text
evento=meseta;resultado=ok;uid=...;op=...
evento=meseta;resultado=fuera_tolerancia;uid=...;op=...
~~~

Cuando el evento incluye `peso=<gramos>`, el backend utiliza ese valor. El resultado `ok` continúa el flujo y `fuera_tolerancia` activa la evaluación de discrepancia.

### Validación de tolerancia

~~~text
diferencia_pct = abs(peso_medido - peso_declarado) / peso_declarado * 100
~~~

Si la diferencia supera la tolerancia del manifiesto:

- entrada: genera AL09 y RT01
- salida: genera AL09 y RT02.

Si el peso de entrada es válido pero el canal es rojo, se genera RT03.

### Retenciones

| Código | Causa | Rol facultado |
| --- | --- | --- |
| RT01 | Discrepancia de peso al ingreso | TERMINAL |
| RT02 | Discrepancia de peso a la salida | TERMINAL |
| RT03 | Canal rojo | AUTORIDAD |
| RT04 | Llegada fuera de ventana | TERMINAL |
| RT05 | Retención documental | AUTORIDAD |
| RT06 | Retención manual operativa | TERMINAL |

La plaza de menor número se asigna primero. Si las tres están ocupadas y el riesgo se conoce antes del ingreso, se rechaza la entrada y se genera AL11.

Las resoluciones son:

| Resolución | Resultado                                                                 |
| ---------- | ------------------------------------------------------------------------- |
| Aclarar | Conserva el manifiesto y devuelve el turno al estado previo.              |
| Corregir | Solo TERMINAL y solo RT01/RT02 conserva el peso anterior en el historial. |
| Rechazar | Exige motivo, anula el turno y conserva el inventario físico.             |

La plaza permanece ocupada hasta recibir el `ACK` de `AgujaLiberar` o hasta que el vehículo llegue a salida. 

### Métricas

| Métrica | Implementación                                                   |
| ---------------------------------- | ---------------------------------------------------------------- |
| Remociones por contenedor retirado | Ciclos `REMOCION` completados / retiros cerrados.                |
| Ciclos por operación | Ciclos completados / turnos cerrados.                            |
| Distancia de grúa | Suma de tramos puede convertirse a cm con `PORTUS_CM_POR_TRAMO`. |
| Tiempo promedio en terminal | Promedio entre creación y cierre de turnos cerrados.             |
| Tiempo promedio de retención | Promedio entre creación y resolución.                            |
| Fila máxima | Máximo simultáneo de turnos en `EnGarita` o `EnRuta`.            |
| Citas en ventana | Citas cumplidas / citas no canceladas del periodo.               |
| Retenciones por causa y resolución | Conteo agrupado por RT y resolución.                             |

El reporte usa un intervalo `[desde, hasta)` convertido de hora de Guatemala a UTC y exporta las métricas junto con el detalle de turnos.

## Temporización, seguridad y errores

### Temporizaciones principales

| Parámetro                        | Valor                    |
| -------------------------------- | ------------------------ |
| Heartbeat de placas              | 5 s                      |
| Ping de puente a placas          | 3 s                      |
| AL01 en backend                  | 15 s sin latido          |
| Timeout de respuesta de garita   | 5 s                      |
| Retardo de evaluación del pesaje | 10 s                     |
| Cierre forzado de talanquera     | 20 s                     |
| Estabilidad de camión            | 400 ms                   |
| Ausencia de camión               | 600 ms                   |
| Revisión AL12/AL13               | cada 30 s                |
| AL12                             | 30 min, configurable     |
| AL13                             | 120 min, configurable    |

### Comandos remotos

| Comando | Destino | Función                                                  |
| --- | --- | --- |
| `AbrirTalanquera` | UNO_ENTRADA | Rechaza apertura manual si hay vehículo bajo la barrera. |
| `CerrarTalanquera` | UNO_ENTRADA | Rechaza si hay vehículo bajo la barrera.                 |
| `AbrirPuertaSalida` | UNO_SALIDA | Rechaza apertura manual si hay vehículo bajo la puerta.  |
| `AgujaRecta` | MEGA_GRUA | Orienta la ruta hacia transferencia.                     |
| `AgujaParqueo` | MEGA_GRUA | Orienta la ruta hacia el parqueo de retención.           |
| `AgujaLiberar` | MEGA_GRUA | Devuelve un vehículo del parqueo al carril principal.    |
| `GruaReferenciar` | MEGA_GRUA | Rechaza si existe carga o movimiento activo.             |
| `GruaSuspender` | MEGA_GRUA | Se acepta, no toma trabajo nuevo.                        |
| `GruaReanudar` | MEGA_GRUA | Rechaza una falla sin rearme.                            |
| `PosicionBloquear` | MEGA_GRUA | Rechaza posición inválida o involucrada en trabajo.      |
| `PosicionLiberar` | MEGA_GRUA | Libera una posición bloqueada.                           |
| `ModoMantenimiento` | MEGA_GRUA | Rechaza durante trabajo activo.                          |
| `AlarmaSilenciar` | MEGA_GRUA | Silencia la señal sonora sin borrar la alarma.           |
### Catálogo de alarmas

| Código | Severidad | Descripción                                     |
| ------ | --------- | ----------------------------------------------- |
| AL01   | Crítica   | Enlace con controlador perdido                  |
| AL02   | Crítica   | Paro de emergencia accionado                    |
| AL03   | Crítica   | Pérdida de referencia de grúa                   |
| AL04   | Crítica   | Pérdida de carga                                |
| AL05   | Alta      | Agarre no confirmado                            |
| AL06   | Alta      | Trabajo de grúa abortado                        |
| AL07   | Alta      | Inconsistencia entre altura física e inventario |
| AL08   | Alta      | Movimiento durante transferencia                |
| AL09   | Media     | Pesaje fuera de tolerancia                      |
| AL10   | Media     | Vehículo incorrecto en salida                   |
| AL11   | Media     | Parqueo lleno                                   |
| AL12   | Media     | Retención superior a 30 minutos                 |
| AL13   | Baja      | Permanencia superior a dos horas                |
| AL14   | Baja      | Comando remoto rechazado                        |

Las alarmas no desaparecen al cesar la condición. Deben reconocerse el botón masivo solo reconoce severidad media y baja.

### Seguridad de datos y operación

- Las contraseñas no se guardan en texto plano.
- Los permisos se validan en rutas del servidor web.
- El WebSocket de TERMINAL verifica la sesión antes de aceptar la conexión.
- El inventario cambia únicamente con confirmaciones de patio.
- Los comandos generados por un evento físico se publican después del commit.
- Los rechazos, comandos y eventos conservan auditoría.
- El backend y el bot usan UTC en la base y presentan `America/Guatemala`.

## Compilación, carga y puesta en marcha

### Requisitos

- Raspberry Pi OS o Linux equivalente sobre un computador de placa única.
- Python 3 y soporte para `venv`.
- Mosquitto y sus herramientas.
- Arduino IDE o Arduino CLI.
- Tres puertos USB estables.
- Librerías Arduino MFRC522, LiquidCrystal_I2C, Servo y Stepper.
- Token de Telegram para la demostración real del bot.

### Carga del firmware

1. Cargar `firmware/uno_garita_entrada/ENTRADAP1_ARQ2.ino` en el UNO de entrada.
2. Cargar `firmware/uno_garita_salida/SALIDAP1_ARQ2.ino` en el UNO de salida.
3. Cargar `firmware/mega_grua_pesaje/PORTUS_Fase1_v2.ino` en el Mega 2560.
4. Cerrar el monitor serial antes de iniciar el puente, dos procesos no deben consumir el mismo puerto.
5. Verificar que los tres sketches usen 9600 baudios.
### Variables de entorno

| Variable | Predeterminado | Uso |
| --- | --- | --- |
| `UNO_ENTRADA_PORT` | vacío | Puerto del UNO de entrada |
| `UNO_SALIDA_PORT` | vacío | Puerto del UNO de salida |
| `MEGA_GRUA_PORT` | vacío | Puerto del Mega |
| `ARDUINO_BAUD` | 9600 | Velocidad serial |
| `PORTUS_MQTT_HOST` | localhost | Broker |
| `PORTUS_MQTT_PORT` | 1883 | Puerto del broker |
| `PORTUS_BOT_TOKEN` | vacío | Token de Telegram |
| `PORTUS_SECRET_KEY` | clave de ejemplo | Firma de sesión |
| `PORTUS_BACKEND_BIND` | 127.0.0.1 | Dirección del backend |
| `PORTUS_DB_PATH` | `backend/portus_core.db` | Base SQLite |
| `PORTUS_MIN_AL12` | 30 | Minutos para AL12 |
| `PORTUS_MIN_AL13` | 120 | Minutos para AL13 |
| `PORTUS_HORARIO_AGENDA` | 06:00-22:00 | Agenda visible |
| `PORTUS_CONTENEDORES` | MSCU0000001 a 8 | Catálogo |
| `PORTUS_CM_POR_TRAMO` | 0 | Conversión de distancia |

### Arranque unificado

Desde la raíz `ARQUI2_F2_G03`:

~~~bash
UNO_ENTRADA_PORT=/dev/portus_uno_entrada \
UNO_SALIDA_PORT=/dev/portus_uno_salida \
MEGA_GRUA_PORT=/dev/portus_mega_grua \
PORTUS_BOT_TOKEN="TOKEN_DE_TELEGRAM" \
PORTUS_SECRET_KEY="una_clave_larga_y_aleatoria" \
bash run_all.sh
~~~

`run_all.sh` crea entornos virtuales, instala dependencias, ejecuta `seed.py` e inicia Mosquitto, backend, puente, web y bot.
### Usuarios de demostración

| Usuario | Rol | Contraseña inicial |
| --- | --- | --- |
| `terminal1` | TERMINAL | `Portus2026!` |
| `naviera1` | NAVIERA | `Portus2026!` |
| `naviera2` | NAVIERA | `Portus2026!` |
| `agente1` | AGENTE | `Portus2026!` |
| `autoridad1` | AUTORIDAD | `Portus2026!` |

### Tarjetas y datos de demostración

| UID | Transportista | Vehículo | Uso |
| --- | --- | --- | --- |
| `E1 69 73 15` | Transportista Uno | C-001 | Ciclo normal |
| `E1 67 7F 15` | Transportista Dos | C-002 | Ciclo normal |
| `E1 8E 3C 53` | Transportista Uno | C-003 | Prueba de RT01 |
| `90 C7 3D 5F` | No registrado | - | Rechazo |

### Verificación de servicios

~~~bash
bash status_all.sh
curl http://localhost:8100/health
~~~

- Web: `http://<ip-de-la-pi>:8000`
- Backend local: `http://127.0.0.1:8100`
- Swagger local: `http://127.0.0.1:8100/docs`
- Logs: `.runtime/logs/`

Para detener:

~~~bash
bash stop_all.sh
~~~
## Bitácora de desarrollo

### Integración del ciclo físico

- Se reemplazó la autorización local de entrada por una consulta al servidor.
- Se agregó la tabla de vehículos y la relación UID-transportista-manifiesto.
- Se automatizó la progresión por eventos de garita, pesaje y salida.
- Se conservaron decisiones locales de salida durante el modo degradado.

### Alarmas y persistencia

- Se implementaron AL09, AL10, AL12, AL13 y AL14 en el backend.
- Se agregó recepción de alarmas desde las placas.
- Se incorporó reconocimiento, referencia única y anuncio en vivo.

### Interfaz TERMINAL

- Se construyeron las ocho pestañas obligatorias.
- El sinóptico recibe MQTT mediante WebSocket.
- Se agregaron turnos, retenciones, patio, grúa, alarmas, citas y reportes.
- Se eliminó la necesidad de polling para el estado operativo.

### Citas y transportista

- La lógica de franjas se centralizó en `servicios.py`.
- Se implementaron capacidad, bloqueo, cancelación y reprogramación.
- El bot comparte la misma base y anuncia citas por MQTT.
- Se implementaron siete comandos y nueve tipos de aviso.

### Grúa y reportes

- Se añadieron `TrabajoGrua`, eventos de ciclo y confirmaciones de patio.
- Se implementó la cola, la política secuencial y las remociones.
- Se agregaron las ocho métricas y exportaciones CSV.
- Se completaron las vistas de NAVIERA, AGENTE y AUTORIDAD.
