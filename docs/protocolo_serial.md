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
