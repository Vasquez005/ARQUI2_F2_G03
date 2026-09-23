# Mosquitto (broker MQTT)

Ver Observaciones_Backend_PersonaB.md punto 3: no habia ninguna configuracion
ni documentacion de Mosquitto en el repo, y Mosquitto 2.x rechaza conexiones
anonimas por defecto salvo que el listener lo permita explicitamente.

## Desarrollo local (Mac/Linux del equipo, antes de tener la Raspberry lista)

```bash
brew install mosquitto        # macOS
# o: sudo apt install mosquitto mosquitto-clients   # Linux/Raspberry Pi OS
```

Este repo ya trae una config minima de desarrollo en `mosquitto/mosquitto.conf`:

```conf
listener 1883 0.0.0.0
allow_anonymous true
```

Arrancarlo:

```bash
mosquitto -c mosquitto/mosquitto.conf -d
```

`run_all.sh` ya lo arranca solo si detecta esta config y nadie esta escuchando
todavia en el puerto (ver `PORTUS_START_LOCAL_MOSQUITTO=no` para desactivarlo).

Probar que funciona:

```bash
mosquitto_sub -h localhost -t "portus/#" -v &
mosquitto_pub -h localhost -t "portus/evt/prueba" -m "hola"
```

## Produccion (Raspberry Pi, para la entrega)

`allow_anonymous true` esta bien para una red local cerrada de laboratorio,
pero si se quiere algo minimamente mas serio para la entrega, la alternativa
mas simple sin cambiar el codigo del bridge/backend es un usuario y contrasena
compartidos:

```bash
sudo mosquitto_passwd -c /etc/mosquitto/passwd portus
# pide la contrasena por consola
```

Y en `/etc/mosquitto/conf.d/portus.conf`:

```conf
listener 1883 0.0.0.0
allow_anonymous false
password_file /etc/mosquitto/passwd
```

Si se hace esto, `bridge/bridge.py` y `backend/app.py` necesitan pasarle
usuario/password al `mqtt.Client` (`.username_pw_set(...)`) — hoy no lo hacen,
porque asumen `allow_anonymous true`. Es un cambio pequeno pero hay que
recordarlo si se activa autenticacion.

## Verificar que Mosquitto esta corriendo

```bash
bash status_all.sh   # incluye el proceso "mosquitto" en el resumen
```
