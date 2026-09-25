# Protocolo serial PORTUS (A <-> B)

## Formato de frame

Cada mensaje va en una linea:

```text
<PORTUS|SRC|SEQ|KIND|TOPIC|PAYLOAD|CHK>
```

- Delimitadores: `<` y `>`
- Campos separados por `|`
- `SRC`: `UNO_ENTRADA`, `UNO_SALIDA`, `MEGA_GRUA`, `RPI`
- `SEQ`: entero incremental por emisor
- `KIND`:
  - `EVT` (evento)
  - `CMD` (comando)
  - `ACK` (aceptado)
  - `REJ` (rechazado)
  - `HBT` (heartbeat)
- `TOPIC`: subruta (ej `garita`, `grua`, `estado`, `cmd`)
- `PAYLOAD`: `k1=v1;k2=v2` (sin `|`)
- `CHK`: checksum hex de 2 bytes (mod 256)

## Checksum

Se calcula sobre:

```text
PORTUS|SRC|SEQ|KIND|TOPIC|PAYLOAD
```

Algoritmo:

1. Sumar ASCII de todos los caracteres.
2. Tomar modulo 256.
3. Convertir a HEX de 2 digitos (mayuscula).

## Ejemplos

Evento grua:

```text
<PORTUS|MEGA_GRUA|120|EVT|grua|estado=trasladando;pos=P3|7A>
```

Comando desde RPI:

```text
<PORTUS|RPI|55|CMD|cmd|name=GruaSuspender;target=MEGA_GRUA|E1>
```

Respuesta aceptada:

```text
<PORTUS|MEGA_GRUA|121|ACK|cmd|name=GruaSuspender|34>
```

Respuesta rechazada:

```text
<PORTUS|MEGA_GRUA|122|REJ|cmd|name=AbrirTalanquera;causa=vehiculo_bajo_talanquera|9F>
```

Heartbeat:

```text
<PORTUS|MEGA_GRUA|123|HBT|estado|modo=normal|01>
```

## Garitas: el servidor decide el acceso (fase 1)

La garita ya no autoriza con una tabla local. Manda el UID de la tarjeta y
espera la respuesta del servidor (`backend/orquestador.py`). El vehiculo se
asocia a su contenedor con la tabla `vehiculos` (tarjeta -> transportista) y el
campo opcional `manifiestos.vehiculo_uid`.

### Entrada (`UNO_ENTRADA`)

| Paso | Frame |
|---|---|
| Lee tarjeta | `EVT garita evento=rfid;uid=E1 69 73 15` |
| Servidor autoriza | `CMD cmd name=AbrirTalanquera;target=UNO_ENTRADA;uid=E1 69 73 15;op=DEPOSITO` |
| Servidor rechaza | `CMD cmd name=RechazarIngreso;target=UNO_ENTRADA;uid=E1 69 73 15;motivo=Sin levante` |
| Garita muestra el rechazo | `EVT garita evento=rechazado;motivo=...;uid=...;decision=servidor` |
| Sin respuesta en 5 s o modo degradado | `EVT garita evento=rechazado;motivo=Sin respuesta;uid=...;decision=local` |
| Pesaje (bascula simulada) | `EVT pesaje evento=meseta;resultado=ok;uid=...;op=...` (o `resultado=fuera_tolerancia`) |

- `AbrirTalanquera` **sin** `uid` sigue siendo la apertura manual desde la terminal.
- `motivo` llega ya recortado a 16 caracteres para el LCD.
- El servidor convierte `resultado` en un peso (declarado si `ok`, declarado x
  `PORTUS_FACTOR_PESO_FUERA`, 1.5 por defecto, si no). Si el controlador manda
  `peso=<gramos>`, se usa ese valor.

### Salida (`UNO_SALIDA`)

| Paso | Frame |
|---|---|
| Lee tarjeta | `EVT salida evento=rfid_salida;uid=...` |
| Servidor autoriza | `CMD cmd name=AbrirPuertaSalida;target=UNO_SALIDA;uid=...` |
| Servidor rechaza | `CMD cmd name=RechazarSalida;target=UNO_SALIDA;uid=...;motivo=Retenido` |
| Garita abre | `EVT salida evento=salida_autorizada;uid=...;decision=servidor` (o `local`) |
| Vehiculo cruzo | `EVT salida evento=salida_completada;uid=...` (cierra el turno) |

- Sin respuesta en 5 s, o en modo degradado, la salida decide con su lista local
  de vehiculos dentro (sec. 12.1.2) y lo informa con `decision=local`.
- `AbrirPuertaSalida` sin `uid` es apertura manual (por ejemplo, turno anulado).

### Limitacion conocida

Los comandos con `uid` miden ~96-107 bytes y el bufer de recepcion del UNO es
de 64. Si el comando llega mientras el loop esta bloqueado (por ejemplo en el
`Serial.flush()` de un latido), el frame puede cortarse, el checksum falla y la
garita termina en "Sin respuesta". Si pasa en las pruebas: quitar el
`Serial.flush()` de `sendFrame` en la entrada o acortar los parametros.

## Alarmas desde las placas (fase 2)

Una placa reporta una alarma con un `EVT` de topico `alarma`; el bridge lo
publica en `portus/evt/alarma` y el backend lo guarda en `alarmas`:

```text
<PORTUS|MEGA_GRUA|130|EVT|alarma|codigo=AL02;detalle=boton|..>
```

- `codigo` es obligatorio y debe estar en el catalogo (AL01-AL14); uno
  desconocido se ignora.
- La severidad la pone el servidor segun el catalogo (sec. 4.6); si la placa
  manda `severidad`, no se usa.
- Los demas campos se anexan a la descripcion (`detalle=boton`).
- Mientras la alarma siga activa, repetirla desde la misma placa no crea otra.

Un `REJ` en `portus/cmd/respuesta` genera AL14 con la `causa` del rechazo.
