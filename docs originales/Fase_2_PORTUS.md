<!-- Convertido desde: Fase 2 portus.pdf -->

Universidad San Carlos de Guatemala Facultad de ingeniería. Ingeniería en Ciencias y Sistemas

**Título del Proyecto:**

# PORTUS - Fase 2

**PONDERACIÓN: 15 pts**

**Tiempo estimado: 100 horas**

# 1. Marco Formativo

## 1.1. Valor

| Nombre del valor | ¿Cómo se aplica en tu laboratorio? |
| --- | --- |
| Responsabilidad | Se promueve el desarrollo responsable de sistemas automatizados que<br>pueden recibir órdenes desde una plataforma externa. Los estudiantes<br>deberán garantizar que ninguna orden remota pueda poner la maqueta<br>en un estado inseguro, que el controlador conserve sus enclavamientos<br>aunque el servidor falle y que la información mostrada por la plataforma<br>sea coherente con el estado físico del sistema. |
| Trabajo en equipo | El proyecto requiere coordinar dos frentes simultáneos, que son la<br>extensión del firmware del controlador con su puente de comunicación<br>y el desarrollo completo de la plataforma con sus cuatro interfaces web<br>y su canal de mensajería. Cada integrante deberá asumir<br>responsabilidades definidas, documentar su trabajo y participar en la<br>integración final. Todos los integrantes deberán comprender cómo una<br>orden emitida desde una pantalla se convierte en un movimiento<br>verificado dentro de la maqueta. |
| Innovación | Se fomenta la aplicación creativa de conocimientos de sistemas<br>embebidos, comunicación entre dispositivos, supervisión y sistemas de<br>información para convertir una maqueta autónoma en una terminal<br>conectada y gobernable a distancia. Los estudiantes deberán integrar<br>procesos como la retención de un vehículo, la autorización aduanera, la<br>programación de citas y la consulta del estado de la carga en un sistema<br>coherente donde cada actor interviene únicamente en lo que le<br>corresponde. |

## 1.2. Competencia(s)

| Tipo de<br>Competencia | Competencia |
| --- | --- |
| Competencia<br>General | ● Aplica principios de ingeniería, ciencias de la computación y sistemas<br>de información para integrar un sistema embebido existente con una<br>plataforma de supervisión y control remoto.<br>● Implementa sistemas tecnológicos distribuidos considerando criterios<br>de seguridad, autonomía ante fallo de comunicación, trazabilidad,<br>consistencia de datos y correspondencia entre el estado físico de la<br>maqueta y su representación digital.<br>● Construye soluciones integrales de forma colaborativa, distribuyendo<br>responsabilidades entre el trabajo de control, el de comunicación y el de<br>aplicación hasta obtener un sistema funcional. |
| Competencia<br>Específica | ● Integra un computador de placa única con el controlador de la<br>maqueta mediante un enlace serial, definiendo un protocolo de<br>mensajes propio con verificación de integridad.<br>● Implementa un intermediario de mensajería que distribuye los eventos<br>de la terminal a varios consumidores, evitando que la supervisión<br>dependa de consultas repetidas a la base de datos.<br>● Distribuye el procesamiento entre el controlador y el servidor,<br>manteniendo en el controlador el filtrado de señales, el control de<br>movimiento y los enclavamientos de seguridad.<br>● Desarrolla una aplicación web con autenticación, sesión y control<br>efectivo de permisos por rol.<br>● Construye un tablero de supervisión que representa el estado real de<br>la terminal en tiempo real, conserva su historia y permite comandar el<br>sistema de forma remota.<br>● Mantiene un historial de los principales eventos de cada operación<br>para consultar su desarrollo desde el ingreso hasta la salida.<br>● Implementa una cadena de autorización documental en la que una<br>decisión tomada por una persona produce un efecto físico verificable<br>sobre la maqueta.<br>● Programa la demanda de acceso mediante ventanas de atención y<br>controla el cumplimiento de la ventana asignada a cada vehículo.<br>● Desarrolla un servicio conversacional de consulta y notificación sobre<br>un canal de mensajería, dirigido a un actor que opera fuera de la<br>terminal. |

## 1.3. Objetivo SMART

| SMART | Definición | Objetivo redactado |
| --- | --- | --- |
| Específico<br>(¿Qué?) | El objetivo es<br>concreto y<br>tangible. | Diseñar e implementar la segunda fase de PORTUS,<br>conectando la maqueta existente a una plataforma<br>completa de supervisión, control remoto y gestión<br>documental ejecutada sobre un computador de placa<br>única. La plataforma deberá contar con cuatro interfaces<br>web diferenciadas por rol y un canal de mensajería para el<br>transportista y deberá permitir que una decisión tomada<br>por una persona produzca un efecto físico verificable<br>sobre la terminal. |
| Medible<br>(¿Cuánto?) | El objetivo posee<br>condiciones<br>objetivas de<br>éxito. | El funcionamiento se comprobará mediante la ejecución<br>completa de los quince escenarios mínimos establecidos<br>en el alcance, todos originados desde la plataforma. Cada<br>escenario define su condición de entrada, la acción<br>esperada del sistema y el resultado observable y se<br>evaluará como cumplido o no cumplido sin grados<br>intermedios. |
| Alcanzable<br>(¿Cómo?) | El objetivo puede<br>lograrse con los<br>recursos y<br>conocimientos<br>disponibles. | La maqueta de la Fase 1 se conserva íntegra y no requiere<br>modificaciones estructurales. Todo el esfuerzo nuevo se<br>concentra en la capa digital. La aplicación, sus pestañas,<br>sus controles, los mensajes del protocolo, los comandos<br>remotos y las respuestas del canal de mensajería quedan<br>definidos de forma explícita en este documento, de modo<br>que el trabajo consiste en implementar una especificación<br>clara y comprobable. |
| Realista<br>(¿Para qué?) | El objetivo<br>contribuye a<br>metas más<br>amplias. | El proyecto busca que los estudiantes apliquen<br>comunicación entre dispositivos, reparto de<br>procesamiento entre controlador y servidor, supervisión en<br>tiempo real, control remoto, administración de<br>autorizaciones, programación de demanda y métricas<br>básicas de operación. La maqueta representará<br>funcionalmente una terminal portuaria conectada, sin<br>pretender reproducir las dimensiones, capacidades o<br>mecanismos completos de una instalación real. |
| A Tiempo<br>(¿Cuándo?) | El objetivo tiene<br>fecha límite o<br>mejor aún un<br>cronograma de<br>hitos de<br>progreso. | La segunda fase deberá completarse durante el periodo<br>establecido, incluyendo investigación, extensión del<br>firmware, desarrollo de la plataforma, remediación de<br>piezas fabricadas, integración, pruebas y documentación.<br>Al finalizar, la terminal deberá operar bajo supervisión<br>remota, sostener la cadena documental completa, medir<br>su propia operación y conservar su funcionamiento seguro<br>ante pérdida de comunicación. |

# 2. Resumen Ejecutivo

El proyecto PORTUS se desarrolla en el marco del curso de Arquitectura de Computadoras y Ensambladores 2. Su propósito es aplicar principios de sistemas embebidos, automatización, comunicación entre dispositivos y control en tiempo real mediante la construcción de una maqueta funcional inspirada en las operaciones logísticas de Puerto Quetzal, principal instalación portuaria del Pacífico guatemalteco.

En la Fase 1 se construyó el núcleo físico y operativo de la terminal. La maqueta quedó funcionando de forma autónoma, con identificación de vehículos, control de acceso, pesaje dinámico, desvío de ruta, zona de transferencia, grúa de dos grados de libertad, patio lineal apilable, salida y atención concurrente de varios camiones. Toda la información se manejaba de manera local mediante registros precargados, pantallas físicas y comunicación serial.

La Fase 2 conecta esa terminal al exterior. Sobre un computador de placa única se implementará una plataforma que recibirá la telemetría del controlador, representará el estado real de la maqueta, permitirá comandarla de forma remota y dará acceso diferenciado a los actores que intervienen en una operación portuaria real.

El cambio conceptual de esta fase es la aparición de decisiones que la maqueta no puede resolver sola. Un vehículo cuyo pesaje no corresponde al peso declarado ya no queda simplemente rechazado. Ahora es enviado a un parqueo de retención y permanece detenido hasta que una persona con autoridad revise el caso desde la plataforma y decida aclararlo, corregir el manifiesto o rechazar la operación. Lo mismo ocurre con la autorización aduanera, que sin ser otorgada impide físicamente que la talanquera se abra.

En esta fase la maqueta física no se modifica. El parqueo de retención se administra de forma lógica, aprovechando que es el propio sistema el que envía ahí al vehículo y por lo tanto conoce su identidad sin necesidad de instrumentación adicional. Todo el esfuerzo nuevo se concentra en la capa digital, que deberá quedar completa al cierre de la fase.

Este documento especifica la plataforma de forma cerrada. Define los roles, los usuarios, la matriz de permisos, las pestañas de cada interfaz, los controles de cada pestaña, los estados posibles de una operación, el catálogo de mensajes entre el controlador y el servidor, los comandos remotos admitidos con sus condiciones de rechazo, los comandos del canal de mensajería con sus respuestas, las métricas y los escenarios de evaluación. El objetivo es evitar ambigüedades sobre lo que debe demostrarse, manteniendo libertad en la implementación interna de cada grupo.

La construcción física restante, que comprende el parqueo instrumentado, la galera de carga especial y la instrumentación meteorológica, junto con la capa de decisión automática, se incorporarán en la tercera fase.

El controlador de la maqueta conserva su autonomía. La plataforma puede solicitar movimientos, pero es el controlador quien decide si son seguros y ante una pérdida de comunicación la terminal debe continuar operando de forma degradada sin dejar operaciones a medias ni inventario indeterminado.

# 3. Enunciado del Proyecto

## 3.1 Descripción del problema a resolver

Guatemala depende en gran medida del transporte marítimo para movilizar su comercio exterior. Dentro de este sistema, Puerto Quetzal constituye la principal instalación portuaria del Pacífico y concentra una parte importante del ingreso y salida de mercancías del país. El crecimiento de las operaciones ha incrementado la presión sobre los procesos de recepción, almacenamiento y despacho de carga, generando congestión, tiempos de espera elevados y sobrecostos para los participantes de la cadena logística.

La Fase 1 demostró que una terminal puede automatizar su operación interna. Sin embargo, dejó a la vista el límite de una automatización aislada. Una maqueta que decide sola es capaz de ejecutar un procedimiento, pero no de participar en una cadena logística, porque en una operación real las decisiones que determinan si una carga puede moverse no se toman dentro de la terminal.

El problema que esta fase aborda es la falta de coordinación e información compartida entre las entidades que intervienen en una operación portuaria. La naviera declara la carga, el agente aduanero presenta la documentación, la autoridad aduanera autoriza el retiro y asigna el nivel de revisión, el transportista solicita la cita y ejecuta el traslado y la terminal custodia y

entrega. Cinco actores con responsabilidades distintas que afectan a una misma carga y que habitualmente trabajan con información fragmentada.

De esa fragmentación se derivan cuatro consecuencias concretas.

La primera es la pérdida de trazabilidad. La información sobre un contenedor puede encontrarse distribuida entre varios registros, sin una fuente única que indique con certeza su ubicación, su estado, su tiempo de permanencia y su autorización para avanzar. Esto obliga a consultas adicionales o incluso a búsquedas físicas dentro del patio.

La segunda es que las excepciones no tienen a quién acudir. Cuando el peso medido no corresponde al declarado, cuando la autoridad ordena una revisión física o cuando la documentación está incompleta, el vehículo queda detenido sin un procedimiento definido de resolución. En un sistema sin plataforma, la única salida es rechazar la operación completa, lo que traslada el costo al transportista aunque la discrepancia sea menor o justificable.

La tercera es la dificultad para coordinar decisiones entre actores. Una autorización, una retención o una cita puede quedar aislada del resto de la operación, provocando que la terminal no conozca a tiempo si un vehículo o una carga puede continuar.

La cuarta es la imposibilidad de medir. Una terminal que no registra sus propios tiempos, sus movimientos improductivos ni el uso real de sus equipos no puede saber dónde pierde capacidad y por lo tanto no puede mejorarla.

Ante esta situación, la Fase 2 de PORTUS plantea conectar la terminal automatizada a una plataforma de supervisión y gestión, de modo que el funcionamiento físico, la cadena de autorizaciones, la resolución de excepciones y el registro de la operación formen parte de un mismo sistema. El proyecto representará cómo la integración entre automatización, sistemas embebidos y información compartida puede reducir movimientos innecesarios, tiempos de espera e inconsistencias dentro de una operación portuaria inspirada en el contexto de Puerto Quetzal.

## 3.2 Alcance del proyecto

La Fase 2 consistirá en conectar la maqueta construida en la Fase 1 a una plataforma completa de supervisión, control y gestión documental, ejecutada sobre un computador de placa única. No se requerirán modificaciones estructurales de la maqueta.

Todo lo construido en la Fase 1 se conserva y debe seguir funcionando. La grúa, el pesaje dinámico, el control de acceso, el patio apilable, la concurrencia de vehículos, la cola de trabajos y los mecanismos de seguridad forman parte del alcance evaluado de esta fase. Un grupo que haya perdido funcionalidad anterior deberá recuperarla antes de la entrega.

La báscula estática queda descartada de forma definitiva y no se implementará en ninguna fase. Una discrepancia de peso deja de resolverse con un segundo instrumento y pasa a resolverse de forma administrativa desde la plataforma, que es la manera en que se resuelve en una terminal real. El ramal construido en la Fase 1 cambia de función y se convierte en un parqueo de retención, donde el vehículo permanece detenido mientras su situación se aclara.

Los camiones seguirán siendo desplazados manualmente por el operador. El sistema continúa siendo el responsable de identificar cada operación, autorizar el ingreso, determinar la ruta, administrar la transferencia, controlar la grúa y permitir la salida.

Sobre la interpretación de este documento. Donde se indica un nombre, un valor, un formato o un texto literal, deberá implementarse exactamente como está escrito. Donde se indica una cantidad mínima, podrá superarse pero no reducirse. Ningún requisito de este documento es opcional salvo los listados en el apartado de alcance opcional.

## Alcance obligatorio

### 1. Continuidad de la terminal construida

La maqueta de la Fase 1 se conserva íntegra. Antes de integrar la plataforma, cada grupo deberá verificar y, cuando corresponda, corregir el funcionamiento de los siguientes elementos.

- Identificación de vehículos y control de acceso en garita.
- Pesaje dinámico con detección de meseta y decisión de ruta.
- Aguja desviadora y señalización luminosa.
- Zona de transferencia con guía asistida y detección de movimiento.
- Grúa de dos grados de libertad con referenciado, marcas de posición y confirmación de agarre.
- Patio lineal apilable a dos niveles con inventario consistente.
- Concurrencia de al menos tres vehículos y cola de trabajos de grúa.
- Paro de emergencia con rearme explícito.

La pérdida de cualquiera de estas funciones se evaluará como incumplimiento de la Fase 2, no de la fase anterior.

### 2. Roles, usuarios y permisos

El sistema contará con cinco roles y ningún otro. Cuatro de ellos operan desde la aplicación web y uno opera exclusivamente desde el canal de mensajería.

| Rol | Identificador | Interfaz | Descripción |
| --- | --- | --- | --- |
| Terminal | TERMINAL | Aplicación<br>web | Operador de la terminal portuaria. Supervisa la<br>maqueta, la comanda de forma remota y<br>resuelve las retenciones de origen operativo |
| Naviera | NAVIERA | Aplicación<br>web | Empresa dueña de la carga. Declara los<br>manifiestos y consulta el estado de sus<br>contenedores |
| Agente<br>aduanero | AGENTE | Aplicación<br>web | Intermediario documental. Presenta la<br>declaración de mercancías y solicita el levante<br>ante la autoridad |
| Autoridad<br>aduanera | AUTORIDAD | Aplicación<br>web | Entidad fiscalizadora. Otorga o retiene el<br>levante, asigna el canal de selectivo y resuelve<br>las retenciones de origen aduanero |
| Transportista | TRANSPORTISTA | Canal de<br>mensajería | Empresa de transporte terrestre. Solicita citas,<br>consulta el estado de su carga y recibe<br>notificaciones. No tiene acceso a la aplicación<br>web |

#### 2.1 Usuarios mínimos exigidos

El sistema deberá entregarse con los siguientes usuarios creados y funcionales. Las credenciales deberán incluirse en la documentación de entrega.

| Usuario | Rol | Cantidad mínima |
| --- | --- | --- |
| Operador de terminal | TERMINAL | 1 |
| Naviera | NAVIERA | 2 navieras distintas |
| Agente aduanero | AGENTE | 1 |
| Autoridad aduanera | AUTORIDAD | 1 |
| Transportista | TRANSPORTISTA | 2 transportistas distintos |

Se exigen dos navieras y dos transportistas para poder demostrar que un usuario no puede ver ni modificar la información de otro usuario del mismo rol.

#### 2.2 Autenticación y sesión

1. El acceso a la aplicación web requerirá usuario y contraseña.
2. Las contraseñas no podrán almacenarse en texto plano en la base de datos.
3. El nombre del usuario en sesión y su rol deberán mostrarse de forma permanente en la interfaz.
4. El acceso al canal de mensajería requerirá una vinculación previa mediante un código generado por el operador de terminal.

#### 2.3 Matriz de permisos

La siguiente matriz es de cumplimiento obligatorio. La letra S indica que el rol puede ejecutar la acción y la letra N indica que no puede.

Las columnas corresponden a los cinco roles en el orden TERMINAL, NAVIERA, AGENTE, AUTORIDAD y TRANSPORTISTA.

| Acción | TERM | NAV | AGEN | AUTO | TRANS |
| --- | --- | --- | --- | --- | --- |
| Crear manifiesto | N | S | N | N | N |
| Ver manifiesto completo | S | Solo los<br>propios | S | S | N |
| Presentar declaración y solicitar levante | N | N | S | N | N |
| Otorgar o retener levante | N | N | N | S | N |
| Asignar canal de selectivo | N | N | N | S | N |
| Solicitar cita | N | N | N | N | S |
| Ver agenda completa de citas | S | N | N | N | N |
| Ver sinóptico de la terminal | S | N | N | N | N |
| Emitir comandos remotos | S | N | N | N | N |
| Reconocer alarmas | S | N | N | N | N |
| Resolver retención de causa<br>operativa | S | N | N | N | N |
| Resolver retención de causa<br>aduanera | N | N | N | S | N |
| Corregir peso declarado en<br>manifiesto | S | N | N | N | N |
| Consultar ubicación de un<br>contenedor | S | Solo los<br>propios | S | S | Solo los<br>propios |
| Generar reporte de corrida | S | N | N | N | N |
| Generar código de vinculación<br>de transportista | S | N | N | N | N |

El control de permisos deberá aplicarse en el servidor y no únicamente en la interfaz. Ocultar un botón no se considerará control de permisos. Un intento de ejecutar una acción no permitida deberá ser rechazado por el servidor y deberá devolver un mensaje de error explícito.

### 3. Estructura de la aplicación

La aplicación será única y presentará al usuario únicamente las pestañas que corresponden a su rol. La cantidad y el nombre de las pestañas son de cumplimiento obligatorio.

| Rol | Pestañas de su interfaz |
| --- | --- |
| TERMINAL | 1. Operación<br>2. Turnos<br>3. Retenciones<br>4. Patio<br>5. Grúa<br>6. Alarmas<br>7. Citas<br>8. Reportes |
| NAVIERA | 1. Manifiestos<br>2. Mis contenedores |
| AGENTE | 1. Declaraciones<br>2. Seguimiento |
| AUTORIDAD | 1. Solicitudes de levante<br>2. Retenciones aduaneras<br>3. Consulta de carga |
| TRANSPORTISTA | No posee interfaz web. Opera desde el canal de mensajería |

Se permite agregar pestañas adicionales, pero no eliminar ni fusionar las aquí establecidas.

### 4. Interfaz del rol TERMINAL

Esta es la interfaz principal del sistema y concentra la mayor parte de la evaluación de esta fase. Cada pestaña se especifica a continuación indicando qué debe mostrar, qué controles debe tener y qué debe ocurrir al utilizarlos.

#### 4.1 Pestaña Operación

Es el sinóptico en vivo de la terminal. Representa el estado físico real de la maqueta en el momento actual.

**Qué debe mostrar.** Un esquema gráfico de la terminal donde cada elemento cambia de apariencia según su estado real. El esquema deberá contener, como mínimo, los siguientes elementos.

| Elemento del<br>sinóptico | Estados que debe representar |
| --- | --- |
| Zona de espera | Cantidad de vehículos en espera |
| Garita | Libre, validando, autorizada, rechazada. Vehículo presente |
| Talanquera | Abierta, cerrada, en movimiento |
| Plataforma de pesaje | Libre, midiendo, medición válida, medición fuera de tolerancia. Último<br>valor medido |
| Aguja desviadora | Recta, hacia parqueo, liberando parqueo |
| Parqueo de retención | Las tres plazas con su estado libre u ocupada, el vehículo que la<br>ocupa y su tiempo de retención |
| Zona de transferencia | Libre, vehículo posicionándose, vehículo alineado, transferencia en curso, operación abortada |
| Grúa | En reposo, referenciando, desplazándose, izando, trasladando,<br>depositando, suspendida, en falla. Posición actual y trabajo en curso |
| Cola de trabajos de<br>grúa | Cantidad de trabajos pendientes y tipo del trabajo en curso |
| Posiciones del patio | Cada posición con su estado libre, reservada, ocupada nivel uno,<br>ocupada nivel dos, bloqueada. Identificador del contenedor en cada<br>nivel |
| Puerta de salida | Abierta, cerrada, en movimiento |
| Estado del enlace | Conectado o desconectado, con la marca de tiempo del último<br>mensaje recibido del controlador |
| Modo del sistema | Operación normal, mantenimiento, degradado |

**Controles de esta pestaña.**

| Control | Qué hace | Condición de uso |
| --- | --- | --- |
| Botón Suspender<br>grúa | Envía el comando GruaSuspender. La<br>grúa termina el movimiento en curso y no<br>toma nuevos trabajos | Disponible siempre |
| Botón Reanudar<br>grúa | Envía el comando GruaReanudar | Disponible solo si la grúa<br>está suspendida |
| Botón Referenciar<br>grúa | Envía el comando GruaReferenciar | Disponible solo si la grúa<br>está en reposo o<br>suspendida |
| Botón Abrir<br>talanquera | Envía el comando AbrirTalanquera | Disponible siempre.<br>Requiere confirmación del<br>usuario |
| Botón Abrir puerta<br>de salida | Envía el comando AbrirPuertaSalida | Disponible siempre.<br>Requiere confirmación del<br>usuario |
| Botón Liberar<br>parqueo | Envía el comando AgujaLiberar para la<br>plaza seleccionada | Disponible solo si la plaza<br>está ocupada y su<br>retención fue resuelta |
| Botón Modo<br>mantenimiento | Envía el comando ModoMantenimiento<br>con valor activar o desactivar | Requiere confirmación del<br>usuario |
| Clic sobre una<br>posición del patio | Abre un panel con el detalle de la posición<br>y los botones Bloquear y Liberar | Disponible siempre |
| Clic sobre un<br>vehículo del<br>sinóptico | Abre el detalle del turno asociado a ese<br>vehículo | Disponible si hay turno<br>activo |

**Comportamiento obligatorio.** El sinóptico deberá actualizarse por suscripción a los eventos publicados por el intermediario de mensajería. Queda prohibido actualizarlo mediante consultas periódicas a la base de datos o al servidor. El retardo entre el evento físico y su reflejo en pantalla no deberá superar dos segundos.

Cuando el enlace con el controlador se pierda, el sinóptico deberá indicarlo de forma visible y deberá dejar de presentar los datos como actuales, mostrando la marca de tiempo del último estado conocido.

#### 4.2 Pestaña Turnos

Administra las operaciones en curso y consulta las ya cerradas.

**Qué debe mostrar.** Dos secciones claramente separadas, que son turnos activos y turnos históricos. Cada turno se presentará en una fila con las siguientes columnas.

- Identificador del turno.
- Identificador del vehículo y transportista al que pertenece.
- Identificador del contenedor.
- Tipo de operación, que puede ser depósito o retiro.
- Estado actual del turno.
- Estación actual.
- Peso declarado, peso medido al ingreso y peso medido a la salida.
- Posición de patio asignada.
- Hora de creación y tiempo transcurrido dentro de la terminal.

**Controles de esta pestaña.**

| Control | Qué hace |
| --- | --- |
| Filtro por estado | Muestra únicamente los turnos en el estado seleccionado |
| Filtro por tipo de operación | Muestra depósitos, retiros o ambos |
| Filtro por fecha | Acota los turnos históricos a un rango de fechas |
| Búsqueda por contenedor<br>o vehículo | Localiza un turno por identificador de contenedor o de vehículo |
| Botón Ver detalle | Abre la línea de tiempo completa del turno, descrita en el apartado<br>4.2.1 |
| Botón Retener | Retiene manualmente el turno seleccionado y envía el vehículo al<br>parqueo si se encuentra antes de la transferencia. Permite<br>agregar una observación opcional |
| Botón Anular | Anula el turno seleccionado y autoriza la salida del vehículo sin<br>completar la operación |

4.2.1 Línea de tiempo del turno. Al abrir el detalle de un turno, la aplicación deberá mostrar la totalidad de los eventos ocurridos durante ese turno, en orden cronológico, con la siguiente información por evento.

- Marca de tiempo con precisión de segundo.
- Origen del evento, que puede ser controlador, servidor o usuario.
- Descripción del evento.
- Valores asociados cuando existan, por ejemplo el peso medido o la posición asignada.

La línea de tiempo deberá poder consultarse también para turnos ya cerrados o anulados mientras permanezcan almacenados en la base de datos.

#### 4.3 Pestaña Retenciones

Es la bandeja de trabajo del operador para resolver los vehículos detenidos.

**Qué debe mostrar.** La lista de retenciones abiertas y la lista de retenciones ya resueltas. Cada retención deberá presentar la siguiente información.

| Campo | Contenido |
| --- | --- |
| Identificador de la<br>retención | Consecutivo único |
| Turno y vehículo | Identificadores asociados |
| Contenedor | Identificador del contenedor involucrado |
| Causa | Una de las causas definidas en el apartado 8.2 |
| Momento | Estación donde ocurrió la retención y marca de tiempo |
| Plaza del parqueo | Número de plaza ocupada, del uno al tres |
| Tiempo de retención | Tiempo transcurrido desde que se generó |
| Evidencia de peso | Peso declarado, peso medido, diferencia absoluta y diferencia<br>porcentual. Se muestra solo cuando la causa es de peso |
| Rol facultado | Indica qué rol puede resolverla |

**Controles de esta pestaña.**

| Control | Qué hace | Quién puede usarlo |
| --- | --- | --- |
| Botón Aclarar | Reanuda el turno sin modificar el manifiesto.<br>Permite agregar una observación opcional. Libera<br>la plaza y envía el comando AgujaLiberar | El rol facultado según la<br>causa |
| Botón Corregir | Sustituye el peso declarado del manifiesto por el<br>peso realmente medido. Conserva el valor anterior<br>en el historial del manifiesto y reanuda el turno con<br>el valor nuevo | Únicamente TERMINAL |
| Botón<br>Rechazar | Anula el turno. Solicita un motivo breve, libera la<br>plaza, autoriza la salida del vehículo sin completar<br>la operación y conserva el inventario en su estado<br>físico real | El rol facultado según la<br>causa |
| Filtro por<br>causa | Muestra únicamente las retenciones de la causa<br>seleccionada | Todos los que ven la<br>pestaña |
| Filtro por<br>estado | Muestra retenciones abiertas o resueltas | Todos los que ven la<br>pestaña |

**Reglas obligatorias de esta pestaña.**

1. La resolución Rechazar deberá incluir un motivo. En Aclarar y Corregir podrá agregarse una observación de forma opcional.
2. Un rol que no está facultado para una causa no verá los botones de resolución y, si intenta ejecutar la acción, el servidor deberá rechazarla.
3. Una retención resuelta no podrá volver a resolverse.
4. Toda resolución genera una notificación automática al transportista propietario del turno.

#### 4.4 Pestaña Patio

Presenta el inventario y el estado detallado de cada posición.

**Qué debe mostrar.** Una representación de las posiciones del patio con su contenido por nivel y una tabla de inventario con los siguientes campos por contenedor.

- Identificador del contenedor.
- Naviera propietaria.
- Posición y nivel donde se encuentra.
- Peso declarado del contenedor.
- Estado de autorización.
- Fecha y hora de ingreso a la terminal.
- Reloj de permanencia, expresado en horas y minutos transcurridos.
- Cantidad de veces que ha sido movido por remociones.

**Controles de esta pestaña.**

| Control | Qué hace |
| --- | --- |
| Botón Bloquear posición | Envía el comando PosicionBloquear |
| Botón Liberar posición | Envía el comando PosicionLiberar. Solo disponible si la posición está bloqueada |
| Ordenamiento por<br>permanencia | Ordena el inventario por tiempo de permanencia descendente |
| Indicador de permanencia<br>excesiva | Resalta los contenedores cuyo reloj de permanencia supera dos<br>horas |

#### 4.5 Pestaña Grúa

Presenta el estado de la grúa y el historial de sus operaciones.

**Qué debe mostrar.**

- Posición actual de la grúa y trabajo en ejecución.
- Cola de trabajos pendientes con su tipo y su orden de atención.
- Gráfica de tiempo de ciclo de las últimas cincuenta operaciones.
- Cantidad de ciclos completados y tiempo promedio de ciclo en el rango mostrado.
- Historial de eventos de falla, que incluye pérdida de referencia, agarre no confirmado, movimiento abortado y pérdida de carga.

**Controles de esta pestaña.**

| Control | Qué hace |
| --- | --- |
| Selector de rango de la<br>gráfica | Permite ver las últimas cincuenta, cien o doscientas operaciones |
| Botón Exportar historial | Descarga los eventos de la grúa del rango seleccionado en<br>formato de valores separados por coma |

#### 4.6 Pestaña Alarmas

Administra las condiciones anormales del sistema.

**Qué debe mostrar.** Dos listas separadas, que son alarmas activas y alarmas históricas. Cada alarma deberá presentar identificador, marca de tiempo de aparición, severidad, origen, descripción y estado de reconocimiento.

**Catálogo mínimo de alarmas que el sistema deberá generar.**

| Código | Descripción | Severidad |
| --- | --- | --- |
| AL01 | Enlace con el controlador perdido | Crítica |
| AL02 | Paro de emergencia accionado | Crítica |
| AL03 | Pérdida de referencia de posición de la grúa | Crítica |
| AL04 | Pérdida de carga durante el traslado | Crítica |
| AL05 | Agarre de contenedor no confirmado | Alta |
| AL06 | Trabajo de grúa abortado | Alta |
| AL07 | Inconsistencia entre altura física e inventario | Alta |
| AL08 | Movimiento del vehículo durante la transferencia | Alta |
| AL09 | Pesaje fuera de tolerancia | Media |
| AL10 | Vehículo incorrecto en la salida | Media |
| AL11 | Parqueo de retención lleno | Media |
| AL12 | Retención que supera treinta minutos | Media |
| AL13 | Permanencia de contenedor superior a dos horas | Baja |
| AL14 | Comando remoto rechazado por el controlador | Baja |

**Controles de esta pestaña.**

| Control | Qué hace |
| --- | --- |
| Botón Reconocer | Marca la alarma como reconocida. Permite agregar un comentario<br>opcional |
| Botón Reconocer todas | Reconoce todas las alarmas activas de severidad baja y media. No<br>aplica a alarmas críticas ni altas, que deben reconocerse una por<br>una |
| Filtro por severidad | Muestra únicamente las alarmas de la severidad seleccionada |

**Regla obligatoria.** Una alarma no desaparece por sí sola al cesar la condición que la originó. Permanece en la lista de activas hasta que un usuario la reconoce de forma explícita.

#### 4.7 Pestaña Citas

Administra la agenda de atención de la terminal.

**Qué debe mostrar.** Una vista de la agenda del día dividida en franjas, donde cada franja indica su hora de inicio, su hora de fin, su capacidad máxima, la cantidad de citas asignadas y la lista de citas con su transportista, su vehículo y su contenedor.

**Controles de esta pestaña.**

| Control | Qué hace |
| --- | --- |
| Selector de fecha | Cambia el día mostrado en la agenda |
| Botón Cancelar cita | Cancela la cita seleccionada y notifica al transportista |
| Botón Reprogramar cita | Mueve la cita a otra franja con capacidad disponible y notifica al transportista |
| Botón Bloquear franja | Impide que se asignen nuevas citas en esa franja |
| Indicador de<br>cumplimiento | Muestra el porcentaje de citas del día cumplidas dentro de su<br>ventana |

#### 4.8 Pestaña Reportes

Genera el resumen de una sesión de operación.

**Qué debe mostrar.** Un formulario para seleccionar el rango de fechas y horas de la corrida y el resultado con las ocho métricas definidas en el apartado 13.

**Controles de esta pestaña.**

| Control | Qué hace |
| --- | --- |
| Selector de rango | Define el periodo del reporte |
| Botón Generar | Calcula y muestra las métricas del periodo |
| Botón Exportar | Descarga el reporte en formato de valores separados por coma,<br>incluyendo el detalle de cada turno del periodo |
| Campo Etiqueta de corrida | Permite nombrar la corrida para identificarla después, por ejemplo<br>corrida de evaluación |

**Regla obligatoria.** El reporte generado durante la evaluación constituirá la línea base de comparación para la Fase 3 y deberá entregarse como parte de la documentación.

### 5. Interfaces de los roles NAVIERA, AGENTE y AUTORIDAD

#### 5.1 Rol NAVIERA, pestaña Manifiestos

**Qué debe mostrar.** La lista de manifiestos declarados por esa naviera, con su identificador, contenedor, tipo de operación, peso declarado, tolerancia, estado documental y estado operativo.

**Controles.**

| Control | Qué hace |
| --- | --- |
| Botón Nuevo manifiesto | Abre el formulario de declaración descrito a continuación |
| Botón Ver detalle | Muestra el manifiesto completo y su historial |
| Botón Anular manifiesto | Anula un manifiesto que aún no tiene turno asociado |

**Campos obligatorios del formulario de manifiesto.**

| Campo | Tipo | Validación |
| --- | --- | --- |
| Identificador del<br>contenedor | Texto | Obligatorio. Debe existir en el catálogo de<br>contenedores de la maqueta |
| Tipo de operación | Selección | Obligatorio. Depósito o retiro |
| Peso declarado | Número entero en<br>gramos | Obligatorio. Mayor que cero |
| Tolerancia | Número en<br>porcentaje | Opcional. Si se omite, se aplica una<br>tolerancia del 5 por ciento |
| Transportista asignado | Selección | Obligatorio. Debe ser uno de los<br>transportistas registrados |
| Observaciones | Texto libre | Opcional |

**Regla obligatoria.** Un contenedor no podrá tener dos manifiestos pendientes al mismo tiempo. El sistema deberá rechazar la declaración e informar la causa.

#### 5.2 Rol NAVIERA, pestaña Mis contenedores

**Qué debe mostrar.** Únicamente los contenedores cuyos manifiestos fueron declarados por esa naviera, con su ubicación actual, su estado, su autorización vigente y su reloj de permanencia.

**Controles.** Búsqueda por identificador de contenedor y filtro por estado. No posee controles de acción.

**Regla obligatoria.** Una naviera no podrá ver los contenedores de la otra naviera. Esta condición se demostrará durante la evaluación.

#### 5.3 Rol AGENTE, pestaña Declaraciones

**Qué debe mostrar.** La lista de manifiestos declarados por cualquier naviera que aún no cuentan con levante, con su identificador, contenedor, naviera, tipo de operación y peso declarado.

**Controles.**

| Control | Qué hace |
| --- | --- |
| Botón Presentar<br>declaración | Abre el formulario de declaración de mercancías. Al enviarlo, el<br>manifiesto cambia al estado declaración presentada |
| Botón Solicitar levante | Envía la solicitud a la autoridad aduanera. Solo disponible si la<br>declaración ya fue presentada. El manifiesto cambia al estado<br>levante solicitado |
| Botón Adjuntar<br>observación | Agrega una nota documental visible para la autoridad |

**Campos obligatorios de la declaración de mercancías.**

| Campo | Tipo | Validación |
| --- | --- | --- |
| Número de declaración | Texto | Obligatorio. Único en el sistema |
| Régimen | Selección | Obligatorio. Importación definitiva o depósito<br>temporal |
| Descripción de la<br>mercancía | Texto libre | Obligatorio, mínimo diez caracteres |
| Valor declarado | Número | Obligatorio, mayor que cero |

#### 5.4 Rol AGENTE, pestaña Seguimiento

**Qué debe mostrar.** El estado de todas las solicitudes presentadas por el agente, indicando si están pendientes, autorizadas o retenidas, con el canal asignado cuando corresponda y el motivo cuando fueron retenidas.

**Controles.** Filtro por estado y búsqueda por número de declaración. No posee controles de acción.

#### 5.5 Rol AUTORIDAD, pestaña Solicitudes de levante

**Qué debe mostrar.** La lista de solicitudes pendientes de resolución, con el manifiesto, el contenedor, la naviera, el agente solicitante, la declaración presentada y el peso declarado.

**Controles.**

| Control | Qué hace |
| --- | --- |
| Botón Otorgar levante | Autoriza el retiro o el depósito. Obliga a seleccionar el canal de<br>selectivo antes de confirmar |
| Selector de canal | Verde o rojo. Obligatorio al otorgar el levante |
| Botón Retener | Deniega temporalmente la autorización y solicita indicar la causa |
| Botón Ver declaración | Muestra la declaración de mercancías presentada por el agente |

**Efecto físico obligatorio.** Un manifiesto sin levante otorgado impide que la talanquera se abra. Un manifiesto con levante y canal rojo permite el ingreso pero envía el vehículo al parqueo de retención inmediatamente después del pesaje de entrada.

#### 5.6 Rol AUTORIDAD, pestaña Retenciones aduaneras

**Qué debe mostrar.** Únicamente las retenciones cuya causa es de origen aduanero, que son canal rojo y retención documental, con la misma información definida en el apartado 4.3.

**Controles.** Botón Aclarar y botón Rechazar. El botón Rechazar solicita indicar el motivo. La autoridad no dispone del botón Corregir, por corresponder exclusivamente al rol TERMINAL.

#### 5.7 Rol AUTORIDAD, pestaña Consulta de carga

**Qué debe mostrar.** La ubicación, el estado, la autorización y el reloj de permanencia de cualquier contenedor de la terminal, sin restricción de propietario.

**Controles.** Búsqueda por identificador de contenedor, por naviera y por estado de autorización. No posee controles de acción.

### 6. Canal de mensajería del transportista

El transportista opera exclusivamente desde un canal de mensajería y no tiene acceso a la aplicación web. El canal podrá implementarse sobre cualquier plataforma de mensajería que permita un servicio automatizado y deberá poder demostrarse desde un teléfono durante la evaluación.

#### 6.1 Vinculación del transportista

1. El operador de terminal genera un código de vinculación de seis caracteres desde la aplicación web, asociado a un transportista registrado.
2. El transportista escribe el comando de vinculación seguido del código.
3. El sistema asocia la cuenta de mensajería a ese transportista y responde confirmando la vinculación.
4. Un código de vinculación solo puede usarse una vez y expira a los sesenta minutos.
5. Un usuario no vinculado que escriba cualquier comando recibirá siempre la misma respuesta de solicitud de vinculación.

#### 6.2 Comandos obligatorios y respuestas exactas

El servicio deberá implementar los siguientes comandos. La respuesta deberá contener, como mínimo, la información indicada en la columna de respuesta.

| Comando | Qué hace | Respuesta que debe entregar |
| --- | --- | --- |
| /inicio | Presenta el servicio y<br>lista los comandos<br>disponibles | Saludo, nombre de la terminal y lista completa<br>de comandos con una línea de descripción cada<br>uno |
| /vincular<br>CODIGO | Asocia la cuenta de<br>mensajería a un<br>transportista | Confirmación con el nombre del transportista<br>vinculado, o mensaje de error si el código es<br>inválido o está vencido |
| /cita | Inicia la solicitud de una<br>cita | Lista de los contenedores del transportista que<br>tienen levante otorgado y aún no tienen cita. El<br>transportista elige uno y el sistema ofrece las<br>próximas franjas con capacidad disponible, con<br>su hora de inicio y fin. Al elegir una, confirma la<br>cita con contenedor, fecha, hora de inicio y hora<br>de fin |
| /miscitas | Lista las citas vigentes<br>del transportista | Para cada cita, el contenedor, la fecha, la<br>ventana asignada y el estado, que puede ser<br>programada, cumplida, vencida o cancelada |
| /estado<br>CONTENEDOR | Consulta el estado de<br>un contenedor | Identificador del contenedor, estado actual,<br>ubicación cuando está en patio, reloj de<br>permanencia en horas y minutos, estado de<br>autorización y canal asignado. Si el contenedor<br>no pertenece al transportista, responde que no<br>tiene carga asociada a ese identificador |
| /misturnos | Lista las operaciones en<br>curso del transportista | Para cada turno activo, el vehículo, el<br>contenedor, el tipo de operación, el estado<br>actual y la estación donde se encuentra |
| /ayuda | Repite la lista de<br>comandos | Lista completa de comandos con su descripción |

**Regla obligatoria.** Cualquier texto que no corresponda a un comando válido deberá recibir una respuesta indicando que el comando no fue reconocido y ofreciendo el comando de ayuda. El servicio nunca deberá quedar sin responder.

#### 6.3 Notificaciones automáticas obligatorias

El servicio deberá enviar los siguientes avisos sin que el transportista los solicite. Cada aviso se envía únicamente al transportista propietario de la carga involucrada.

| Evento que la dispara | Contenido mínimo del aviso |
| --- | --- |
| La autoridad otorga el<br>levante | Contenedor, confirmación de autorización y canal asignado. Si<br>el canal es rojo, indicación de que el vehículo será enviado a<br>verificación |
| La autoridad retiene el<br>levante | Contenedor, indicación de retención y motivo registrado |
| Se asigna una cita | Contenedor, fecha, hora de inicio y hora de fin de la ventana |
| Falta una hora para la<br>ventana asignada | Recordatorio con contenedor y ventana |
| El vehículo es retenido | Vehículo, contenedor, causa de la retención y, cuando la causa<br>es de peso, el peso declarado, el peso medido y la diferencia |
| La retención es resuelta | Vehículo, contenedor, tipo de resolución y, cuando la resolución<br>sea Corregir, el valor nuevo del peso declarado. Si fue<br>Rechazar, deberá incluir el motivo |
| La cita es cancelada o<br>reprogramada | Contenedor y situación. Si fue reprogramada, la ventana nueva |
| El turno se cierra | Vehículo, contenedor, tipo de operación y tiempo total dentro de<br>la terminal |
| El turno se anula | Vehículo, contenedor y causa de anulación cuando corresponda |

**Regla obligatoria.** Un transportista nunca deberá recibir información de carga que no le pertenece. Esta condición se demostrará durante la evaluación con los dos transportistas registrados.

### 7. Estados de una operación

El sistema deberá manejar exactamente los siguientes estados de turno. No se permite agregar estados intermedios que sustituyan a los aquí definidos, aunque sí pueden agregarse subestados internos del controlador.

| Estado | Significado | Transiciones posibles |
| --- | --- | --- |
| Programado | La cita fue asignada y el vehículo<br>aún no se presenta | A EnGarita o a Anulado |
| EnGarita | El vehículo fue identificado y está<br>siendo validado | A EnPesajeEntrada, a Retenido o<br>a Anulado |
| EnPesajeEntrada | El vehículo cruza la plataforma de<br>pesaje al ingreso | A EnRuta, a Retenido o a Anulado |
| EnRuta | El vehículo se dirige a la zona de<br>transferencia | A EnTransferencia o a Anulado |
| EnTransferencia | El vehículo está posicionado y la<br>grúa tiene trabajo asignado | A EnPesajeSalida, a<br>EnTransferencia tras un aborto, o<br>a Anulado |
| EnPesajeSalida | El vehículo cruza la plataforma de<br>pesaje antes de salir | A EnSalida, a Retenido o a<br>Anulado |
| EnSalida | El vehículo espera autorización de<br>salida | A Cerrado o a Retenido |
| Retenido | El vehículo está en el parqueo<br>esperando resolución | A EnRuta o a EnSalida si se aclara<br>o corrige, o a Anulado si se<br>rechaza |
| Cerrado | La operación se completó<br>correctamente | Estado final |
| Anulado | La operación se canceló sin<br>completarse | Estado final |

**Reglas obligatorias de la máquina de estados.**

1. Un turno solo se crea cuando la garita autoriza el ingreso. Un intento de ingreso rechazado no crea turno, pero sí genera un registro de intento con su causa.
2. El inventario del patio solo se modifica cuando el controlador confirma físicamente el movimiento, nunca al emitir el comando.
3. Un turno que pasa a Retenido conserva toda la información acumulada hasta ese momento, incluidos los pesajes ya realizados.
4. Un turno anulado después de que la grúa movió el contenedor deberá dejar el inventario reflejando la posición física real del contenedor.
5. Ningún turno podrá permanecer en un estado distinto de Cerrado o Anulado cuando el vehículo ya salió de la terminal.

### 8. Parqueo de retención

El ramal construido en la Fase 1 se convierte en un parqueo de retención con tres plazas administradas de forma lógica. No se requiere instrumentar las plazas, porque el sistema conoce la identidad del vehículo que envió al parqueo.

#### 8.1 Funcionamiento

1. Cuando un turno pasa al estado Retenido, el sistema asigna la plaza libre de menor número y envía el comando AgujaParqueo.
2. La plaza queda ocupada por ese vehículo hasta que la retención se resuelva.
3. El sistema lleva el tiempo de retención de cada plaza y lo muestra en el sinóptico y en la bandeja de retenciones.
4. Al resolverse la retención, el sistema envía el comando AgujaLiberar, la plaza queda libre y el vehículo regresa al carril principal por el mismo recorrido por el que entró.
5. La aguja desviadora opera en tres estados, que son recta hacia transferencia, desviada hacia el parqueo y liberación del parqueo.
6. Si las tres plazas están ocupadas, la garita deberá rechazar el ingreso de cualquier vehículo cuya operación presente riesgo de retención, entendido como canal rojo asignado o llegada fuera de la ventana asignada. El sistema deberá generar la alarma AL11.

#### 8.2 Causas de retención

| Código | Causa | Momento en que se genera | Rol facultado para<br>resolver |
| --- | --- | --- | --- |
| RT01 | Discrepancia de peso<br>al ingreso | Después del pesaje de entrada,<br>cuando la diferencia supera la<br>tolerancia | TERMINAL |
| RT02 | Discrepancia de peso<br>a la salida | Después del pesaje de salida,<br>antes de autorizar el cierre | TERMINAL |
| RT03 | Canal rojo de selectivo | Inmediatamente después del<br>pesaje de entrada | AUTORIDAD |
| RT04 | Llegada fuera de la<br>ventana asignada | Al presentarse en la garita | TERMINAL |
| RT05 | Retención documental | En cualquier momento, ordenada<br>por la autoridad | AUTORIDAD |
| RT06 | Retención manual<br>operativa | En cualquier momento, ordenada<br>por la terminal | TERMINAL |

#### 8.3 Resoluciones

| Resolución | Quién la dicta | Qué hace el sistema |
| --- | --- | --- |
| Aclarar | El rol facultado según la causa | Libera la plaza, envía AgujaLiberar y devuelve el turno al estado que tenía antes de la retención. El manifiesto no se<br>modifica. Puede agregarse una observación opcional |
| Corregir | Únicamente<br>TERMINAL | Sustituye el peso declarado del manifiesto por el peso<br>realmente medido, conserva el valor anterior en el historial<br>del manifiesto, libera la plaza, envía AgujaLiberar y devuelve<br>el turno al estado que tenía antes de la retención |
| Rechazar | El rol facultado<br>según la causa | Solicita un motivo, libera la plaza, envía AgujaLiberar, pasa<br>el turno al estado Anulado y autoriza la salida del vehículo<br>sin completar la operación. Si el contenedor ya fue movido<br>por la grúa, el inventario conserva su posición física real |

**Las tres resoluciones actualizan el estado del turno y generan una notificación automática al transportista. Solo la resolución Rechazar exige un motivo.**

### 9. Programación de citas

El transportista deberá solicitar una cita antes de presentarse en la terminal. La cita se solicita exclusivamente desde el canal de mensajería.

**Reglas obligatorias.**

1. La agenda se divide en franjas de quince minutos.
2. Cada franja admite como máximo dos citas.
3. Solo puede solicitarse cita para un contenedor que ya cuenta con levante otorgado.
4. Un contenedor no puede tener dos citas vigentes al mismo tiempo.
5. Una franja llena no se ofrece al transportista. El sistema deberá ofrecer la siguiente franja con capacidad disponible.
6. Un vehículo se considera dentro de su ventana si se presenta entre la hora de inicio de la franja y hasta cinco minutos después de la hora de fin.
7. Un vehículo que se presenta fuera de ese rango genera la retención RT04.
8. El cumplimiento de ventana se registra por cada cita y alimenta la métrica correspondiente.

La asignación automática de ventanas orientada a aplanar los picos de demanda no forma parte de esta fase. En esta fase la asignación se resuelve únicamente por capacidad de franja y la optimización se incorporará en la Fase 3.

### 10. Servidor, protocolos y catálogo de mensajes

El servidor se ejecutará sobre un computador de placa única y deberá contener los siguientes servicios.

| Servicio | Función |
| --- | --- |
| Puente de<br>comunicación | Enlace serial con el controlador. Traduce los eventos del controlador<br>a mensajes publicados en el intermediario y los comandos de la<br>plataforma a instrucciones del controlado |
| Intermediario de<br>mensajería | Distribuye los eventos a todos los consumidores interesados mediante<br>MQTT |
| Servicios web | Atiende las interfaces de los actores mediante HTTP, con<br>autenticación y control de permisos |
| Base de datos | Almacena usuarios, manifiestos, declaraciones, turnos, inventario,<br>pesajes, citas, retenciones, alarmas, eventos y telemetría |
| Servicio de<br>mensajería | Atiende los comandos del transportista y envía las notificaciones<br>automáticas |

#### 10.1 Sobre el enlace serial

El grupo deberá definir un protocolo de mensajes propio sobre el enlace serial, que deberá cumplir las siguientes condiciones.

1. Cada mensaje deberá delimitarse de forma inequívoca, de modo que una pérdida parcial no corrompa el mensaje siguiente.
2. Cada mensaje deberá incluir un campo de verificación de integridad.
3. Cada mensaje del controlador deberá incluir un número de secuencia creciente, que permita al servidor detectar pérdidas.
4. Cada comando enviado por el servidor deberá recibir una confirmación de aceptación o de rechazo por parte del controlador.
5. El envío de mensajes no podrá bloquear las tareas críticas del controlador.

#### 10.2 Espacio de tópicos del intermediario

El sistema deberá utilizar la siguiente organización de tópicos. El prefijo portus es obligatorio.

| Tópico | Dirección | Contenido |
| --- | --- | --- |
| portus/evt/garita | Del controlador | Identificación de vehículo, resultado de validación<br>y causa de rechazo |
| portus/evt/pesaje | Del controlador | Peso medido, cantidad de muestras de la meseta<br>y resultado de la comparación |
| portus/evt/aguja | Del controlador | Estado de la aguja desviadora |
| portus/evt/transferencia | Del controlador | Alineación, inicio, aborto y fin de la transferencia |
| portus/evt/grua | Del controlador | Cada paso del ciclo de grúa, con posición, estado<br>de agarre y resultado |
| portus/evt/patio | Del controlador | Cambio de estado de una posición, con su nivel y<br>el contenedor involucrado |
| portus/evt/salida | Del controlador | Identificación de vehículo y resultado de la<br>verificación de salida |
| portus/evt/alarma | Del controlador | Código de alarma, severidad y datos asociados |
| portus/evt/estado | Del controlador | Latido periódico con el estado general del sistema |
| portus/cmd/solicitud | Hacia el<br>controlador | Comando remoto emitido desde la plataforma |
| portus/cmd/respuesta | Del controlador | Aceptación o rechazo del comando, con la causa<br>del rechazo |

**Formato obligatorio del mensaje publicado.** Todo mensaje deberá contener, como mínimo, un identificador único, una marca de tiempo, el origen, el tipo de evento y los datos propios del evento. El formato deberá ser el mismo en todos los tópicos.

**Regla obligatoria.** El latido del tópico de estado deberá emitirse con una periodicidad no mayor a cinco segundos. Si el servidor deja de recibirlo durante tres periodos consecutivos, deberá declarar el enlace perdido y generar la alarma AL01.

### 11. Comandos remotos

El sistema deberá implementar exactamente los siguientes comandos. El controlador deberá evaluar cada comando contra sus condiciones de seguridad y responder aceptándolo o rechazándolo con su causa.

| Comando | Efecto | El controlador debe rechazarlo<br>si |
| --- | --- | --- |
| AbrirTalanquera | Abre la talanquera de ingreso | Hay un vehículo detectado bajo la<br>talanquera |
| CerrarTalanquera | Cierra la talanquera de ingreso | Hay un vehículo detectado bajo la<br>talanquera |
| AbrirPuertaSalida | Abre la puerta de salida | Hay un vehículo detectado bajo la<br>puerta |
| AgujaRecta | Coloca la aguja hacia<br>transferencia | Hay un vehículo sobre la aguja |
| AgujaParqueo | Coloca la aguja hacia el parqueo | Hay un vehículo sobre la aguja |
| AgujaLiberar | Coloca la aguja para devolver un<br>vehículo del parqueo al carril<br>principal | Hay un vehículo sobre la aguja o<br>no hay vehículo en el parqueo |
| GruaReferenciar | Ejecuta el procedimiento de<br>referenciado | La grúa tiene carga adherida o hay<br>un trabajo en ejecución |
| GruaSuspender | Impide que la grúa tome nuevos trabajos | Nunca se rechaza. El movimiento en curso se completa antes de<br>suspender |
| GruaReanudar | Permite que la grúa vuelva a tomar<br>trabajos | La grúa está en estado de falla sin<br>rearme |
| PosicionBloquear | Marca una posición del patio como<br>bloqueada | La posición es origen o destino de<br>un trabajo en ejecución |
| PosicionLiberar | Quita el bloqueo de una posición | La inconsistencia física que originó<br>el bloqueo persiste |
| ModoMantenimiento | Activa o desactiva el modo de<br>mantenimiento | Hay un trabajo de grúa en<br>ejecución o un vehículo en<br>transferencia |
| AlarmaSilenciar | Silencia la señal sonora sin borrar<br>la alarma | Nunca se rechaza |

**Reglas obligatorias.**

1. Todo comando deberá mostrar al usuario la respuesta del controlador, indicando si fue aceptado o rechazado.
2. Un comando rechazado deberá mostrarse al usuario con la causa exacta del rechazo y deberá generar la alarma AL14.
3. El paro de emergencia no es un comando remoto. No podrá accionarse ni rearmarse desde la plataforma.
4. En modo de mantenimiento, el controlador no admitirá trabajos de grúa originados por turnos, pero sí admitirá el comando de referenciado.

### 12. Reparto entre controlador y servidor

Las funciones del sistema deberán distribuirse entre el controlador y el servidor de acuerdo con la siguiente tabla.

| Función | Dónde se ejecuta |
| --- | --- |
| Generación de pulsos de los motores | Controlador |
| Muestreo y filtrado del pesaje | Controlador |
| Detección de la meseta de pesaje | Controlador |
| Enclavamientos de seguridad de la grúa | Controlador |
| Altura de pila y confirmación de agarre | Controlador |
| Paro de emergencia | Controlador |
| Cola de trabajos de la grúa | Controlador |
| Validación de acceso en garita | Servidor |
| Asignación de posición de patio | Servidor |
| Asignación de plaza de parqueo | Servidor |
| Resolución de retenciones | Servidor |
| Programación de citas | Servidor |
| Historial de operaciones y métricas | Servidor |

#### 12.1 Autonomía ante pérdida de comunicación

Ante pérdida de comunicación con el servidor, el controlador deberá comportarse de la siguiente manera.

1. Completar de forma segura la operación de grúa en ejecución.
2. Completar los turnos que ya se encuentran dentro de la terminal, utilizando la última información recibida.
3. Rechazar todo ingreso nuevo, indicando en la pantalla de garita que el sistema opera en modo degradado.
4. Conservar en memoria local los eventos ocurridos durante la desconexión.
5. Continuar atendiendo el paro de emergencia y todos los enclavamientos de seguridad.
6. Al restablecerse el enlace, transmitir su estado real y los eventos acumulados para que el servidor los reconcilie.

El sistema nunca deberá detenerse a media operación ni quedar con inventario indeterminado. Esta condición se demostrará durante la evaluación desconectando el servidor con una operación en curso.

### 13. Métricas de operación

**Las siguientes métricas deberán calcularse para el rango seleccionado en la pestaña Reportes:**

| Métrica | Cómo se calcula |
| --- | --- |
| Remociones por contenedor<br>retirado | Total de movimientos de remoción dividido entre la cantidad de<br>retiros completados en el periodo |
| Ciclos de grúa por operación<br>completada | Total de ciclos de grúa dividido entre la cantidad de turnos<br>cerrados |
| Distancia total recorrida por<br>la grúa | Suma de la distancia de traslación de todos los ciclos del periodo |
| Tiempo promedio de camión<br>en la terminal | Promedio del tiempo transcurrido entre la creación del turno y<br>su cierre, considerando únicamente turnos cerrados |
| Tiempo promedio de | Promedio del tiempo transcurrido entre la generación de una |
| retención | retención y su resolución |
| Longitud máxima de la fila de<br>espera | Valor máximo alcanzado por la cantidad de vehículos en espera<br>durante el periodo |
| Porcentaje de citas<br>cumplidas en ventana | Citas cumplidas dentro de su ventana dividido entre el total de<br>citas del periodo, expresado en porcentaje |
| Retenciones por causa y por<br>resolución | Conteo de retenciones agrupado por su código de causa y por<br>su tipo de resolución |

**Regla obligatoria.** La política de asignación de posiciones implementada en la Fase 1 deberá conservarse como modo seleccionable del sistema. En la Fase 3 se implementará una política optimizada y ambas deberán compararse sobre el mismo escenario. Un grupo que elimine la política original se quedará sin línea base de comparación.

### 14. Fabricación mediante impresión 3D

Se mantiene el requisito establecido en la Fase 1, según el cual al menos el 40 por ciento de los componentes constructivos y mecánicos identificables debe ser diseñado o adaptado por el grupo y fabricado mediante impresión 3D.

Dado que esta fase no incorpora módulos físicos nuevos, el requisito se aplica como remediación sobre la maqueta existente. Las piezas a fabricar o refabricar deberán ser aquellas de las que depende la confiabilidad del sistema, entre ellas las siguientes.

- Contenedores con alojamiento integrado para la placa ferrosa en la cara superior.
- Guías de autocentrado de cada celda del patio.
- Vehículos con distancia entre ejes consistente y base estable para el pesaje.
- Soporte del cabezal de la grúa y alojamiento del mecanismo de agarre.
- Soportes de sensores, marcas ópticas del riel y alojamientos de lectores.
- Estructura de señalización y soportes de pantallas.

Los grupos que ya alcanzaron el porcentaje en la Fase 1 únicamente deberán documentar el inventario y entregar los archivos correspondientes. Los grupos que no lo alcanzaron deberán regularizarlo en esta fase.

Se conservan las condiciones originales. Las piezas no deberán ser únicamente decorativas, deberán conservarse los archivos editables y de fabricación, los modelos de terceros deberán documentar su procedencia y sus adaptaciones y no se permitirá aumentar artificialmente el porcentaje dividiendo una pieza en elementos pequeños únicamente para incrementar el conteo.

### 15. Escenarios mínimos de funcionamiento

Durante la presentación deberán demostrarse los siguientes quince escenarios. Toda la operación deberá originarse desde la plataforma y no desde registros precargados en el controlador. Cada escenario se evaluará como cumplido o no cumplido, sin grados intermedios.

| Códi<br>go | Condición que se provoca | Resultado que debe observarse |
| --- | --- | --- |
| E01 | Una naviera declara un manifiesto de<br>depósito | El manifiesto aparece en la pestaña<br>Declaraciones del agente |
| E02 | El agente presenta la declaración y<br>solicita el levante | La solicitud aparece en la pestaña Solicitudes<br>de levante de la autoridad |
| E03 | La autoridad retiene el levante con<br>motivo registrado. El camión se<br>presenta en la garita | La talanquera no abre, la pantalla indica la<br>causa y el transportista recibe el aviso de<br>retención documental |
| E04 | La autoridad otorga el levante con<br>canal verde y el transportista solicita<br>cita desde el canal de mensajería | El transportista recibe su ventana asignada y<br>la cita aparece en la pestaña Citas de la<br>terminal |
| E05 | El camión se presenta dentro de su<br>ventana | La talanquera abre, se crea el turno y el<br>sinóptico refleja el cambio en menos de dos<br>segundos |
| E06 | Un segundo camión se presenta fuera<br>de su ventana asignada | El sistema genera la retención RT04, asigna<br>plaza de parqueo y notifica al transportista |
| E07 | Un camión con peso alterado cruza el<br>pesaje dinámico | El sistema genera la retención RT01, la aguja<br>desvía físicamente al vehículo y la bandeja<br>muestra el peso declarado, el peso medido y<br>la diferencia |
| E08 | La terminal resuelve esa retención<br>mediante Corregir | El manifiesto queda con el peso nuevo, se<br>conserva el valor anterior en su historial, la<br>aguja libera el parqueo y el turno continúa<br>hasta cerrarse |
| E09 | La autoridad otorga un levante con<br>canal rojo y el camión ingresa | El vehículo es enviado al parqueo<br>inmediatamente después del pesaje de<br>entrada y solo la autoridad puede resolver la<br>retención |
| E10 | Esa retención se resuelve mediante<br>Rechazar | El turno pasa a Anulado, el vehículo sale sin<br>completar la operación, el inventario conserva<br>su estado físico real y el transportista recibe el<br>aviso con el motivo |
| E11 | Se ocupan las tres plazas del parqueo<br>y se presenta un cuarto vehículo con<br>canal rojo | La garita rechaza el ingreso indicando parqueo<br>lleno y el sistema genera la alarma AL11 |
| E12 | Un usuario del rol NAVIERA intenta<br>resolver una retención y un<br>transportista consulta un contenedor<br>que no le pertenece | El servidor rechaza ambas acciones y muestra<br>el error correspondiente |
| E13 | El operador suspende la grúa desde la plataforma mientras existe un trabajo<br>en curso y luego la reanuda | La grúa completa el movimiento en curso, no toma nuevos trabajos mientras está<br>suspendida y continúa con la cola al<br>reanudarse |
| E14 | Se desconecta el servidor durante una<br>operación de grúa en curso | La maqueta completa la operación de forma<br>segura, rechaza nuevos ingresos y al<br>reconectar informa su estado real, el servidor<br>lo reconcilia y genera la alarma AL01 con su<br>reconocimiento |
| E15 | Se ejecuta un retiro que requiere<br>remoción y se genera el reporte de la<br>corrida | La línea de tiempo del turno muestra cada<br>movimiento, el reporte presenta las ocho<br>métricas y la pestaña Grúa actualiza su<br>historial y la gráfica de tiempos de ciclo |

## Alcance opcional

Las siguientes funciones no forman parte del alcance obligatorio. Un grupo que las implemente podrá optar a puntos adicionales, siempre que el alcance obligatorio esté completo.

- Representación tridimensional o animada del sinóptico de la terminal.
- Interfaz de consulta pública documentada que permita a un sistema externo obtener el estado de un contenedor.
- Panel de comparación entre dos corridas distintas de la misma secuencia de operaciones.
- Registro fotográfico asociado a cada retención resuelta.
- Notificación al transportista mediante mensaje de voz o llamada automatizada.
- Aplicación de consulta para dispositivo móvil dirigida al rol NAVIERA.

## Requerimientos técnicos

El control determinista de la maqueta deberá permanecer en el microcontrolador. La generación de pulsos para los motores, el muestreo del pesaje, la atención del paro de emergencia y los enclavamientos de seguridad deberán resolverse mediante interrupciones, temporizadores y manipulación directa de puertos. No se aceptarán esperas bloqueantes. Este requisito deberá comprobarse mediante la revisión del código fuente.

El servidor de la terminal deberá ejecutarse sobre un computador de placa única. No se aceptará sustituirlo por una computadora personal durante la evaluación, salvo autorización expresa.

La comunicación entre el controlador y el servidor deberá realizarse mediante enlace serial. La distribución de eventos dentro de la plataforma deberá realizarse mediante MQTT. Las interfaces de los actores deberán atenderse mediante HTTP. El uso de un solo protocolo para todo se evaluará como incumplimiento.

El tablero no deberá consultar la base de datos ni al servidor de forma periódica para actualizarse. Deberá suscribirse a los eventos publicados por el intermediario. Una implementación basada en consultas periódicas convierte al intermediario en un elemento decorativo y será penalizada.

La red deberá ser local y no se requerirá conexión a internet para operar el sistema, con excepción del canal de mensajería.

La estructura física deberá permanecer estable, ordenada y visualmente comprensible. El cableado deberá estar organizado y asegurado, sin conexiones expuestas ni elementos que interfieran con el recorrido del camión o de la grúa.

**En esta fase no se requerirá lo siguiente.**

- Báscula estática, que queda descartada de forma definitiva.
- Galera de carga especial.
- Instrumentación ambiental de temperatura y gases.
- Instrumentación física de las plazas del parqueo.
- Instrumentación meteorológica.
- Visión por computadora.
- Asignación optimizada de posiciones de patio.
- Predicción de permanencia.
- Reordenamiento del patio en tiempos ociosos.
- Asignación automática de ventanas para aplanar picos de demanda.

## 3.3 Entregables

| Tipo | Descripción |
| --- | --- |
| Documento<br>técnico | Documento que explique el propósito de la Fase 2, el alcance<br>implementado y la arquitectura general de la solución. Deberá describir la<br>comunicación entre el controlador y el servidor, el protocolo serial definido<br>por el grupo, el espacio de tópicos utilizado, el modelo de datos, el modelo<br>de usuarios y permisos, el cálculo de las métricas y el comportamiento del<br>sistema ante pérdida de comunicación. |
| Maqueta funcional | Maqueta de la Fase 1 en funcionamiento, con el ramal operando como<br>parqueo de retención de tres plazas y con la aguja desviadora en sus tres<br>estados. Todos los módulos deberán funcionar de manera integrada y<br>responder a los comandos emitidos desde la plataforma. |
| Plataforma<br>desplegada | Plataforma en ejecución sobre el computador de placa única, accesible<br>desde la red local, con las ocho pestañas del rol TERMINAL y las<br>interfaces de los tres roles web restantes. Deberá entregarse con<br>instrucciones de despliegue, credenciales de prueba de los usuarios<br>mínimos y un procedimiento de arranque desde cero. |
| Canal de<br>mensajería<br>operativo | Servicio de mensajería en funcionamiento, con los siete comandos y las<br>nueve notificaciones automáticas exigidas. Deberá entregarse el<br>procedimiento de vinculación y al menos dos cuentas de prueba. |
| Código fuente | Entrega organizada del firmware del controlador y del código de la<br>plataforma, con los archivos identificados, comentados y separados según<br>su función. Deberán incluirse el puente de comunicación, la definición del<br>protocolo serial, el esquema de la base de datos y las instrucciones para<br>compilar, cargar, configurar y ejecutar el sistema. |
| Bitácora de<br>desarrollo y<br>evidencias | Registro del avance del proyecto durante esta fase. Deberá incluir<br>fotografías, capturas de la plataforma, problemas encontrados, decisiones<br>tomadas, correcciones realizadas y resultados obtenidos durante las<br>pruebas. |
| Evidencia de<br>fabricación 3D | Inventario actualizado de los componentes constructivos y mecánicos de<br>la maqueta, indicando cuáles fueron fabricados mediante impresión 3D y<br>cuáles se refabricaron durante esta fase. Deberá incluir fotografías,<br>ubicación dentro del proyecto y los archivos de fabricación, con la<br>procedencia y las adaptaciones de los modelos obtenidos de terceros. |
| Reporte de la<br>corrida de<br>evaluación | Exportación del reporte generado desde la pestaña Reportes durante la<br>demostración, con las ocho métricas del periodo. Este documento<br>constituirá la línea base de comparación para la Fase 3. |

# 4. Material de apoyo

Para facilitar el desarrollo del proyecto, se recomienda a los estudiantes consultar los siguientes recursos técnicos y educativos. Estos materiales permitirán comprender la comunicación entre el microcontrolador y el computador de placa única, el uso del intermediario de mensajería y la construcción de servicios web para la plataforma.

## Documentación técnica y plataformas oficiales

- Arduino Reference. Guía oficial del lenguaje y las librerías más utilizadas en proyectos de automatización.
- Raspberry Pi Documentation. Documentación oficial sobre configuración del sistema, puertos serie, servicios y red.
- Eclipse Mosquitto. Documentación del intermediario de mensajería MQTT y de sus herramientas de línea de comandos.
- MQTT Essentials. Serie de artículos introductorios sobre el protocolo, el espacio de tópicos y las calidades de servicio.
- pySerial. Librería para la comunicación serial entre el computador de placa única y el microcontrolador.
- Flask o FastAPI. Marcos de trabajo para la construcción de los servicios web de la plataforma.
- SQLite o PostgreSQL. Documentación del motor de base de datos seleccionado.
- SparkFun Learning Portal. Tutoriales técnicos sobre sensores, actuadores y microcontroladores.
- Adafruit Learning System. Guías sobre módulos de control, conexión de componentes y ejemplos de código.

# 5. Metodología

La metodología de la Fase 2 se organizará en etapas progresivas que conducirán a los equipos desde el estudio de la comunicación entre dispositivos hasta la validación de una terminal conectada y gobernable de forma remota. Cada etapa deberá documentarse mediante una bitácora de trabajo, evidencias, diagramas, resultados de pruebas y registro de las decisiones adoptadas.

## 5.1 Investigación preliminar

Los equipos deberán estudiar los conceptos necesarios para desarrollar la solución. La investigación deberá incluir, como mínimo, los siguientes temas.

- Comunicación serial entre microcontrolador y computador de placa única.
- Diseño de un protocolo de mensajes delimitado, con verificación de integridad y número de secuencia.
- Arquitectura de publicación y suscripción y diseño de un espacio de tópicos.
- Construcción de servicios web, manejo de sesiones y control de acceso por rol.
- Modelado y persistencia de datos de operación.
- Sinópticos en tiempo real y gestión de alarmas con reconocimiento.
- Reparto de procesamiento entre dispositivos de borde y servidores.
- Comportamiento seguro ante pérdida de comunicación y reconciliación de estado.
- Servicios automatizados sobre canales de mensajería.
- Cadena documental de una importación y concepto de levante y selectivo aduanero.

La investigación deberá enfocarse en comprender la función de cada componente y la forma en que se integra con el resto del sistema.

## 5.2 Diseño de la arquitectura

Antes de escribir código, los equipos deberán definir la arquitectura de su solución. El diseño deberá incluir los siguientes elementos.

- Diagrama de despliegue con los dispositivos, los servicios y los enlaces entre ellos.
- Definición del protocolo serial, con el formato de cada mensaje, su delimitación, su verificación y su número de secuencia.
- Espacio de tópicos del intermediario y formato del mensaje publicado.
- Modelo de datos con usuarios, manifiestos, declaraciones, turnos, citas, retenciones, alarmas, eventos y telemetría.
- Matriz de permisos por rol y por acción.
- Máquina de estados del turno con sus diez estados y sus transiciones.
- Catálogo de comandos remotos con sus condiciones de rechazo.
- Tabla de reparto entre controlador y servidor.
- Comportamiento previsto ante pérdida de comunicación y procedimiento de reconciliación.
- Bosquejo de cada una de las pestañas exigidas, con sus controles.

La implementación no deberá iniciarse sin haber comprobado que la arquitectura propuesta conserva el control determinista en el microcontrolador y permite operar la maqueta cuando el servidor no está disponible.

## 5.3 Extensión del firmware

El firmware de la Fase 1 deberá extenderse sin alterar su estructura de control ni su comportamiento determinista. Las adiciones mínimas son las siguientes.

- Capa de comunicación con el servidor, con envío de eventos, recepción de comandos y confirmación de cada comando.
- Latido periódico de estado cada cinco segundos.
- Validación de comandos remotos contra las condiciones de seguridad vigentes.
- Administración de las plazas del parqueo y del tercer estado de la aguja.
- Modo de operación degradada ante pérdida de comunicación, con registro local de eventos.
- Reporte de estado real y de eventos acumulados al restablecerse el enlace.

La capa de comunicación no deberá interferir con las tareas críticas. El envío de mensajes no podrá bloquear la generación de pulsos, el muestreo del pesaje ni la atención del paro de emergencia.

## 5.4 Desarrollo de la plataforma

La plataforma deberá desarrollarse por módulos. Se recomienda implementar en el siguiente orden, verificando cada módulo antes de avanzar al siguiente.

1. Puente de comunicación y verificación del enlace con el controlador.
2. Intermediario de mensajería y publicación de eventos.
3. Persistencia de eventos y telemetría.
4. Autenticación, sesión y matriz de permisos.
5. Pestaña Operación con el sinóptico alimentado por suscripción.
6. Modelo de manifiestos, declaraciones y turnos.
7. Interfaces de NAVIERA, AGENTE y AUTORIDAD con la cadena de levante.
8. Pestaña Turnos con la línea de tiempo.
9. Pestaña Retenciones con las tres resoluciones.
10. Pestaña Alarmas con reconocimiento.
11. Pestaña Patio y pestaña Grúa.
12. Canal de mensajería con sus comandos y notificaciones.
13. Pestaña Citas y control de ventana.
14. Pestaña Reportes.

## 5.5 Pruebas individuales

Antes de la integración completa, deberán ejecutarse pruebas sobre cada subsistema. Como mínimo deberán comprobarse las siguientes condiciones.

- Continuidad del enlace serial durante una operación prolongada.
- Detección de una pérdida de mensaje mediante el número de secuencia.
- Recepción correcta de eventos bajo carga, sin pérdida ni duplicación.
- Actualización del sinóptico por suscripción dentro de los dos segundos exigidos.
- Rechazo de cada comando remoto en su condición de rechazo definida.
- Operación de la maqueta con el servidor apagado.
- Reconciliación de estado y de eventos acumulados al restablecer el enlace.
- Administración simultánea de las tres plazas del parqueo.
- Resolución correcta de cada tipo de retención según el rol autorizado.
- Rechazo de una acción fuera de los permisos del rol.
- Aislamiento de información entre las dos navieras y entre los dos transportistas.
- Respuesta de cada uno de los siete comandos del canal de mensajería.
- Envío de cada una de las nueve notificaciones automáticas.
- Cálculo correcto de cada métrica sobre una serie conocida.

Cada prueba deberá registrar la condición evaluada, el resultado esperado, el resultado obtenido y las correcciones aplicadas.

## 5.6 Integración del sistema

La integración deberá realizarse de forma progresiva, en el siguiente orden recomendado.

1. Enlace entre el controlador y el servidor.
2. Publicación de eventos y visualización en el sinóptico.
3. Operación completa originada desde la plataforma.
4. Cadena de autorización con levante y canal de selectivo.
5. Citas y control de ventana.
6. Retención, parqueo y resolución en sus tres formas.
7. Comandos remotos y alarmas con reconocimiento.
8. Canal de mensajería con sus notificaciones.
9. Cálculo de métricas y generación de reportes.
10. Comportamiento ante pérdida y restablecimiento de comunicación.

La integración no se considerará finalizada mientras la maqueta no pueda operar de forma segura con el servidor apagado y reconciliar correctamente su estado al reconectarse.

## 5.7 Validación del sistema completo

La validación final deberá realizarse ejecutando de forma continua los quince escenarios mínimos establecidos en el apartado 15 del alcance, en el orden en que están definidos.

Después de cada escenario deberá comprobarse que el inventario registrado coincida con la ubicación física de los contenedores, que el flujo de la operación haya finalizado en el estado esperado y que las métricas correspondan a lo realmente ocurrido.

## 5.8 Documentación y presentación final

Durante todo el desarrollo, cada equipo deberá mantener una bitácora actualizada con los avances realizados, los integrantes responsables, las evidencias del proceso, los problemas encontrados, los cambios de diseño, los resultados de pruebas y las versiones relevantes del software.

La presentación final deberá mostrar el sistema funcionando de manera continua e integrada. Los integrantes deberán explicar la comunicación entre el controlador y el servidor, el manejo de las autorizaciones, el procedimiento de resolución de retenciones y el comportamiento del sistema ante fallo de comunicación.

No será suficiente presentar la plataforma y la maqueta por separado. La evaluación deberá evidenciar que una decisión tomada en una pantalla produce un efecto verificable sobre la terminal física.

# 6. Recursos y herramientas a utilizar

Para el desarrollo del proyecto, los estudiantes deberán utilizar herramientas tecnológicas que faciliten la programación del controlador, la construcción de la plataforma, la comunicación entre dispositivos y la documentación del sistema.

**Software**

- Arduino IDE. Entorno principal para la programación del microcontrolador y la implementación de los subsistemas de control y seguridad.
- Sistema operativo del computador de placa única. Base de ejecución del servidor de la terminal.
- Mosquitto. Intermediario de mensajería para la distribución de eventos dentro de la plataforma.
- Python con pySerial. Implementación del puente de comunicación entre el controlador y el servidor.
- Flask, FastAPI o equivalente. Construcción de los servicios web y de las vistas de los actores.
- SQLite o PostgreSQL. Persistencia de manifiestos, turnos, eventos y telemetría.
- Software de diseño paramétrico. Modelado y adaptación de las piezas a refabricar durante esta fase.
- Fritzing. Elaboración de diagramas de conexión eléctricos y esquemas de montaje.
- Canva o PowerPoint. Elaboración de presentaciones de avance y documentación final.
- Microsoft Word o Google Docs. Redacción de la documentación técnica y de la bitácora.

**Plataformas de trabajo y gestión**

- UEDI. Plataforma institucional para la publicación de actividades, entregas y avisos del curso.
- GitHub. Control de versiones y almacenamiento del firmware, del código de la plataforma, de los diagramas y de la documentación.
- Google Drive. Espacio para compartir archivos, fotografías y evidencias del trabajo en equipo.
- Trello o Notion. Gestión de tareas y cronogramas del proyecto, permitiendo el seguimiento del progreso.

# 7. Desarrollo de Habilidades Blandas

Además de los conocimientos técnicos relacionados con sistemas embebidos, comunicación entre dispositivos y supervisión de sistemas, el proyecto PORTUS busca fortalecer competencias necesarias para el trabajo profesional en ingeniería. La integración entre la maqueta y la plataforma requerirá coordinación, comunicación constante y toma de decisiones conjunta.

**Trabajo en equipo**

El proyecto se desarrollará en grupos con responsabilidades distribuidas entre sus integrantes. Los equipos deberán coordinar el trabajo sobre el controlador, la comunicación, la plataforma y las pruebas, procurando que todos participen en la integración y comprendan el funcionamiento general del sistema.

**Comunicación efectiva**

Los estudiantes deberán presentar avances y comunicar con claridad los problemas encontrados y las soluciones implementadas. También deberán mantener organizada la información del proyecto mediante herramientas de seguimiento, documentación y control de versiones.

**Resolución de problemas y toma de decisiones**

Durante la integración podrán surgir fallos de comunicación, inconsistencias entre el estado físico y el estado registrado, o pérdidas de determinismo en el controlador. Los integrantes deberán analizar las causas, comparar alternativas y seleccionar soluciones que conserven la seguridad y el alcance establecido.

**Gestión y liderazgo**

Cada equipo deberá planificar sus actividades, distribuir tareas y establecer fechas internas para el desarrollo, la integración y las pruebas. Se espera que los estudiantes desarrollen responsabilidad compartida, capacidad de organización y liderazgo técnico durante el cumplimiento de los objetivos del proyecto.

# 8. Cronograma

| Tipo | Fecha Inicio | Fecha Fin |
| --- | --- | --- |
| Asignación de Proyecto | Por definir | Por definir |
| Elaboración | Por definir | Por definir |
| Calificación | Por definir | Por definir |

# 9. Rúbrica de Calificación

## 9.1 Requisitos para optar a la calificación

Un proyecto que no cumpla con las siguientes condiciones no será calificado.

1. La maqueta construida en la Fase 1 deberá estar operativa. La pérdida de funcionalidad anterior invalida la entrega.
2. El control determinista deberá permanecer en el microcontrolador. Un sistema en el que el servidor genere los pulsos de los motores, procese el pesaje o atienda el paro de emergencia no será calificado.
3. La maqueta deberá operar de forma segura con el servidor apagado.
4. La operación demostrada deberá originarse desde la plataforma y no desde registros precargados en el controlador.
5. Las ocho pestañas del rol TERMINAL deberán existir y ser funcionales.
6. El canal de mensajería deberá estar operativo y demostrarse desde un teléfono.
7. Deberá entregarse el código fuente completo del firmware y de la plataforma.
8. Deberá entregarse la evidencia de fabricación 3D actualizada.
9. Todos los integrantes deberán participar en la presentación y responder sobre cualquier parte del sistema.

## 9.2 Resumen de Puntuaciones

| Aspecto evaluado | Porcentaje |
| --- | --- |
| Integración y arquitectura de comunicación | 20 |
| Tablero de supervisión y control remoto | 20 |
| Roles, permisos y cadena de autorización | 15 |
| Retenciones y parqueo | 15 |
| Canal de mensajería y citas | 10 |
| Métricas y reportes | 10 |
| Documentación, evidencias y presentación | 10 |
| Total | 100 |

El punteo total de la fase se distribuirá de forma proporcional a los porcentajes anteriores sobre la ponderación establecida en la portada de este documento.

## Detalle de la Calificación

| Aspecto | Punteo | Criterios de evaluación |
| --- | --- | --- |
| Integración y<br>arquitectura de<br>comunicación | 20 | Enlace serial estable con protocolo delimitado, verificado<br>y con número de secuencia. Uso efectivo del<br>intermediario para distribuir eventos a varios<br>consumidores. Latido de estado con detección de enlace<br>perdido. Reparto de procesamiento conforme a lo<br>exigido, verificado mediante revisión de código.<br>Operación segura con el servidor apagado y<br>reconciliación correcta al restablecer el enlace |
| Tablero de supervisión<br>y control remoto | 20 | Sinóptico completo con todos los elementos exigidos,<br>alimentado por suscripción y con retardo menor a dos<br>segundos. Alarmas del catálogo generadas y<br>reconocidas correctamente. Los trece comandos remotos<br>implementados con sus condiciones de rechazo. Línea<br>de tiempo consultable para cualquier turno y pestañas<br>Patio y Grúa funcionales |
| Roles, permisos y<br>cadena de<br>autorización | 15 | Los cinco roles con los seis usuarios mínimos. Matriz de<br>permisos aplicada en el servidor y no solo en la interfaz.<br>Aislamiento de información entre navieras y entre<br>transportistas. Cadena completa de manifiesto,<br>declaración, solicitud, levante y canal, con efecto físico<br>verificable sobre la talanquera |
| Retenciones y<br>parqueo | 15 | Las seis causas de retención implementadas. Tres<br>plazas administradas con asignación y liberación<br>correcta. Tercer estado de la aguja funcional. Las tres<br>resoluciones con restricción por rol y motivo obligatorio<br>únicamente al rechazar. Rechazo de ingreso con<br>parqueo lleno |
| Canal de mensajería y<br>citas | 10 | Los siete comandos con las respuestas exigidas. Las<br>nueve notificaciones automáticas. Vinculación por código<br>con expiración. Agenda en franjas de quince minutos con<br>capacidad máxima de dos citas y control de ventana con<br>generación de retención |
| Métricas y reportes | 10 | Las ocho métricas de operación calculadas<br>correctamente para el rango seleccionado y reporte<br>exportable de la corrida |
| Documentación,<br>evidencias y<br>presentación | 10 | Documento técnico completo. Bitácora con evidencias.<br>Evidencia de fabricación 3D actualizada. Reporte de la<br>corrida de evaluación. Dominio del sistema por parte de<br>todos los integrantes |

## Penalizaciones

| Situación | Descuento |
| --- | --- |
| El tablero se actualiza mediante consultas periódicas en lugar de<br>suscribirse a los eventos publicados | 10 por ciento |
| Se utiliza un solo protocolo de comunicación para toda la plataforma | 10 por ciento |
| El control de permisos se aplica únicamente ocultando controles en la<br>interfaz | 10 por ciento |
| Una retención es resuelta por un rol que no está autorizado para esa<br>causa | 10 por ciento |
| Un comando remoto se ejecuta aun cuando se cumple su condición de<br>rechazo | 10 por ciento |
| El inventario queda inconsistente con el estado físico después de una<br>operación abortada o de un rechazo | 10 por ciento |
| Se utilizan esperas bloqueantes en las tareas críticas del controlador | 15 por ciento |
| La plataforma se ejecuta sobre una computadora personal sin<br>autorización expresa | 15 por ciento |

## Puntos adicionales

Un grupo con el alcance obligatorio completo podrá optar a hasta 10 puntos adicionales por la implementación de funciones del alcance opcional. Los puntos adicionales no compensan rubros incompletos del alcance obligatorio.

# 10. Flujo esperado de demostración

**Propósito del apartado.** Este apartado no incorpora funcionalidades adicionales al proyecto. Su objetivo es ordenar en una sola secuencia las funciones ya definidas y mostrar cómo se relacionan durante una operación completa. El flujo se presenta primero como una operación ideal, o happy path, y después se indican las principales ramas de excepción que deberán poder provocarse durante la evaluación. Lectura general del flujo. Una operación inicia con la preparación documental de la carga, continúa con la autorización y la programación de la cita, pasa a la interacción física del vehículo con la terminal y finaliza con el cierre del turno y la actualización de la información mostrada por la plataforma. NAVIERA → AGENTE → AUTORIDAD → TRANSPORTISTA → GARITA → PESAJE DE ENTRADA → TRANSFERENCIA / GRÚA → PESAJE DE SALIDA → SALIDA → CIERRE Y REPORTE Condición inicial recomendada. Antes de iniciar la demostración, el controlador y el computador de placa única deberán estar encendidos y comunicados, el intermediario MQTT y los servicios web deberán estar disponibles, el sinóptico deberá mostrar el estado real de la maqueta, la grúa deberá encontrarse referenciada y el inventario inicial del patio deberá coincidir con la disposición física.

## 10.1 Happy path de una operación de depósito

El siguiente recorrido representa una operación de depósito sin retenciones, con levante otorgado, canal verde, cita cumplida y pesajes dentro de tolerancia. Es la secuencia base que debería funcionar antes de provocar cualquier excepción.

| Paso | Acción esperada | Resultado observable |
| --- | --- | --- |
| 01 | La NAVIERA crea un manifiesto de<br>tipo Depósito e indica contenedor,<br>peso declarado y transportista. | El manifiesto queda disponible para el<br>AGENTE y puede consultarse desde la<br>interfaz de la naviera. |
| 02 | El AGENTE presenta la declaración de<br>mercancías y posteriormente solicita el<br>levante. | La solicitud aparece en la bandeja de<br>Solicitudes de levante de la AUTORIDAD. |
| 03 | La AUTORIDAD revisa la declaración,<br>otorga el levante y selecciona canal<br>verde. | La carga queda autorizada. El transportista<br>recibe la notificación con el canal asignado. |
| 04 | El operador genera el código de<br>vinculación y el TRANSPORTISTA<br>vincula su cuenta mediante /vincular<br>CODIGO. | El canal de mensajería queda asociado al<br>transportista correcto y permite utilizar los<br>comandos disponibles. |
| 05 | El TRANSPORTISTA utiliza /cita,<br>selecciona el contenedor y elige una<br>franja disponible. | La cita queda Programada, aparece en la<br>pestaña Citas y el transportista recibe la<br>ventana asignada. |
| 06 | El vehículo se presenta en la garita<br>dentro de su ventana y es identificado. | El servidor valida manifiesto, levante y cita. La<br>talanquera permite el ingreso y el turno pasa a<br>EnGarita. |
| 07 | El vehículo cruza la plataforma de<br>pesaje de entrada. | El controlador obtiene una medición válida. Si<br>la diferencia está dentro de la tolerancia, el<br>turno continúa a EnRuta. |
| 08 | La aguja permanece en ruta hacia<br>transferencia y el vehículo avanza<br>hasta la zona de transferencia. | El sinóptico refleja el recorrido y, al quedar el<br>vehículo correctamente posicionado, el turno<br>pasa a EnTransferencia. |
| 09 | El servidor asigna una posición de<br>patio y la grúa ejecuta el trabajo de<br>depósito. | La grúa toma el contenedor del vehículo y lo<br>coloca en la posición asignada. El inventario<br>se actualiza únicamente después de la<br>confirmación física del movimiento. |
| 10 | Finalizada la transferencia, el vehículo<br>continúa hacia el pesaje de salida. | El turno pasa a EnPesajeSalida y se registra<br>la segunda medición. |
| 11 | El pesaje de salida se encuentra<br>dentro de la tolerancia y el vehículo<br>llega al punto de salida. | El turno pasa a EnSalida y queda listo para la<br>verificación final. |
| 12 | El sistema verifica el vehículo y<br>autoriza la salida. | La puerta de salida se abre, el vehículo<br>abandona la terminal y el turno pasa a<br>Cerrado. |
| 13 | La plataforma procesa el cierre de la<br>operación. | El transportista recibe la notificación de cierre;<br>Turnos, Patio, Grúa y el sinóptico muestran el<br>estado final coherente con la maqueta. |
| 14 | El operador genera el reporte de la<br>corrida cuando corresponda. | Las métricas incorporan la operación<br>terminada y el reporte puede utilizarse como<br>evidencia de la demostración. |

## 10.2 Happy path de una operación de retiro

El retiro utiliza la misma cadena documental, autorización, cita, acceso y pesaje. La diferencia principal aparece en la zona de transferencia, donde la grúa debe recuperar un contenedor que ya se encuentra almacenado en el patio.

| Paso | Acción esperada | Resultado observable |
| --- | --- | --- |
| 01 | La NAVIERA crea un manifiesto de<br>tipo Retiro para un contenedor<br>existente en el patio. | El manifiesto queda disponible para continuar<br>la cadena documental. |
| 02 | El AGENTE presenta la declaración y<br>solicita el levante; la AUTORIDAD lo<br>otorga con canal verde. | La carga queda autorizada para retiro y el<br>transportista puede solicitar una cita. |
| 03 | El TRANSPORTISTA obtiene su cita y<br>se presenta dentro de la ventana<br>asignada. | La garita valida la operación, permite el<br>ingreso y se crea el turno correspondiente. |
| 04 | El vehículo realiza el pesaje de<br>entrada y continúa hacia transferencia. | Con una medición válida y dentro de<br>tolerancia, el turno avanza hasta<br>EnTransferencia. |
| 05 | El servidor determina la posición del<br>contenedor solicitado y genera los<br>trabajos necesarios para la grúa. | La cola de trabajos refleja el retiro. Si existen<br>contenedores que bloquean el acceso, se<br>realizan las remociones requeridas de acuerdo<br>con la lógica de patio de la Fase 1. |
| 06 | La grúa retira el contenedor objetivo<br>del patio y lo deposita sobre el<br>vehículo. | Cada movimiento confirmado físicamente<br>actualiza el inventario y la cantidad de<br>remociones del contenedor involucrado. |
| 07 | El vehículo realiza el pesaje de salida<br>y llega al punto de salida. | Si no existe discrepancia, el turno avanza a<br>EnSalida. |
| 08 | La salida se valida y el vehículo<br>abandona la terminal. | El turno pasa a Cerrado y el transportista<br>recibe la notificación correspondiente. |
| 09 | Se genera el reporte de la corrida. | Las métricas reflejan los ciclos de grúa, las<br>remociones, la distancia recorrida y el tiempo<br>total de la operación. |

## 10.3 Ramas de excepción y error

Las siguientes ramas parten del flujo principal. No es necesario que todas ocurran dentro de un mismo turno; pueden provocarse mediante operaciones independientes durante la demostración. Cuando una retención se resuelve mediante Aclarar o Corregir, el vehículo regresa al punto del flujo que corresponda. Cuando se resuelve mediante Rechazar, el turno pasa a Anulado y el vehículo sale sin completar la operación.

| ID | Condición provocada | Respuesta esperada del sistema |
| --- | --- | --- |
| R01 | El vehículo se presenta sin levante<br>otorgado o con el levante retenido. | La garita no autoriza el ingreso. No debe<br>iniciarse una operación física que permita<br>avanzar al vehículo. |
| R02 | El vehículo se presenta fuera de su<br>ventana asignada. | Se genera RT04. Si existe plaza disponible, el<br>turno pasa a Retenido y el vehículo se dirige al<br>parqueo; la resolución corresponde a<br>TERMINAL. |
| R03 | El pesaje de entrada supera la<br>tolerancia respecto del peso<br>declarado. | Se genera RT01, la aguja desvía el vehículo al<br>parqueo y TERMINAL puede Aclarar, Corregir<br>o Rechazar. |
| R04 | La carga posee levante otorgado con<br>canal rojo. | Después del pesaje de entrada se genera<br>RT03 y el vehículo se dirige al parqueo.<br>Únicamente AUTORIDAD puede Aclarar o<br>Rechazar la retención. |
| R05 | La AUTORIDAD ordena una retención<br>documental durante una operación. | Se genera RT05 y el turno pasa a Retenido.<br>La resolución corresponde a AUTORIDAD. |
| R06 | TERMINAL retiene manualmente un<br>turno por una situación operativa. | Se genera RT06 y el turno pasa a Retenido.<br>La resolución corresponde a TERMINAL. |
| R07 | El pesaje de salida supera la<br>tolerancia. | Se genera RT02 antes del cierre. Si se Aclara<br>o Corrige, el flujo regresa a EnSalida; si se<br>Rechaza, el turno pasa a Anulado. |
| R08 | Las tres plazas del parqueo están<br>ocupadas y se presenta un vehículo<br>con riesgo conocido de retención. | La garita rechaza el ingreso y se genera la<br>alarma AL11. El vehículo no debe entrar hasta<br>que exista una plaza disponible. |
| R09 | Durante la transferencia ocurre<br>pérdida de referencia, agarre no<br>confirmado, pérdida de carga,<br>movimiento del vehículo o aborto del<br>trabajo. | Se genera la alarma correspondiente. El<br>inventario no se modifica hasta que exista<br>confirmación física del movimiento y la<br>operación permanece controlada hasta<br>resolver la condición. |
| R10 | La plataforma envía un comando<br>remoto que incumple una condición de<br>seguridad. | El controlador rechaza el comando, no ejecuta<br>la acción física, devuelve la causa y se genera<br>AL14. |
| R11 | Se pierde la comunicación con el<br>servidor durante una operación. | El controlador completa de forma segura el<br>trabajo en curso, continúa con los turnos que<br>ya están dentro, rechaza nuevos ingresos,<br>conserva los eventos y al reconectar transmite<br>su estado para reconciliación. Se genera<br>AL01. |
| R12 | Se acciona el paro de emergencia. | El controlador atiende el paro localmente y<br>mantiene los enclavamientos de seguridad. El<br>paro no puede accionarse ni rearmarse desde<br>la plataforma y requiere el rearme definido<br>para la maqueta. |
| R13 | Un usuario intenta ejecutar una acción<br>fuera de los permisos de su rol o<br>consultar información que no le<br>pertenece. | El servidor rechaza la acción. Una naviera no<br>accede a la información de otra y un<br>transportista no recibe datos de carga ajena. |
| R14 | Se identifica un vehículo incorrecto<br>durante la verificación de salida. | La verificación de salida no se considera válida<br>y se genera la alarma AL10 hasta corregir la<br>situación. |

## 10.4 Cómo regresa una retención al flujo principal

Toda retención utiliza la misma lógica general: se identifica la causa, se asigna una plaza cuando corresponda, el vehículo permanece detenido y el rol facultado toma una decisión desde la plataforma. La decisión determina si la operación continúa o termina.

| Tipo | Decisión | Continuación del flujo |
| --- | --- | --- |
| Aclarar | La causa se<br>considera resuelta<br>sin modificar el<br>manifiesto. | La plaza se libera, se ejecuta AgujaLiberar y el turno regresa<br>al estado anterior a la retención. |
| Corregir | TERMINAL<br>sustituye el peso<br>declarado por el<br>peso realmente<br>medido. | Se conserva el valor anterior en el historial del manifiesto,<br>se libera el parqueo y el turno continúa desde el estado<br>correspondiente. |
| Rechazar | El rol facultado<br>decide que la<br>operación no debe<br>continuar e indica<br>el motivo. | La plaza se libera, el turno pasa a Anulado y el vehículo sale<br>sin completar la operación. El inventario conserva siempre<br>el estado físico real. |

## 10.5 Guion sugerido para la demostración

Para evitar reinicios innecesarios y facilitar la evaluación, los quince escenarios mínimos pueden demostrarse como una secuencia de cuatro bloques. Este orden no sustituye los resultados exigidos en el apartado 15; únicamente muestra una forma práctica de presentarlos como una historia continua.

| N.º | Qué se demuestra | Escenarios relacionados |
| --- | --- | --- |
| 1 | Cadena documental y happy path<br>inicial: manifiesto de depósito,<br>declaración, solicitud de levante,<br>retención documental, posterior<br>autorización con canal verde, cita e<br>ingreso correcto. | E01 a E05 |
| 2 | Excepciones operativas: llegada fuera<br>de ventana, discrepancia de peso al<br>ingreso y resolución mediante Corregir<br>hasta completar la operación. | E06 a E08 |
| 3 | Control aduanero y seguridad de<br>acceso: canal rojo, rechazo de la<br>retención, parqueo lleno y pruebas de<br>permisos y aislamiento de información. | E09 a E12 |
| 4 | Control de grúa, tolerancia a fallos y<br>cierre de la corrida: suspensión y<br>reanudación, pérdida del servidor<br>durante un trabajo y retiro con<br>remociones seguido de la generación<br>del reporte. | E13 a E15 |
