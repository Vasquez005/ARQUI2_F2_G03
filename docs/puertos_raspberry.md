# Puertos serial en Raspberry Pi

## Conexion recomendada

Conectar por USB:

- UNO entrada
- UNO salida
- Mega grua/pesaje

## Identificacion rapida

```bash
ls /dev/ttyACM* /dev/ttyUSB*
```

## Recomendacion estable (udev)

Crear aliases:

- `/dev/portus_uno_entrada`
- `/dev/portus_uno_salida`
- `/dev/portus_mega_grua`

Y usar esos nombres en el bridge, no `ttyACM0/1/2` directos.

## Energia

Usar hub USB alimentado para evitar desconexiones por consumo.
