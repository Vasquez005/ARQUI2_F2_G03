# Estacion meteorologica PORTUS (WeMos D1 Mini / ESP8266)

## Cableado

Alimenta el D1 Mini por USB (powerbank o cargador propio).  
GND comun para todos los sensores.

| Sensor | Cable | Pin D1 Mini |
|---|---|---|
| DHT22 VCC | rojo | **3V3** (no 5V) |
| DHT22 GND | negro | **G** |
| DHT22 DATA | amarillo | **D2** |
| DHT22 | resistencia 10 kΩ entre DATA y 3V3 si no trae modulo |
| YL-83 VCC | | **3V3** |
| YL-83 GND | | **G** |
| YL-83 **DO** (digital) | | **D5** |
| YL-83 AO | no se usa |
| LDR una pata | | **3V3** |
| LDR otra pata | | **A0** |
| Resistencia 10 kΩ | entre **A0** y **G** | divisor |

No uses D3, D4 ni D8: son pines de arranque.

## Arduino IDE

1. Archivo → Preferencias → URLs adicionales:
   `https://arduino.esp8266.com/stable/package_esp8266com_index.json`
2. Herramientas → Placa → Gestor: instala **esp8266**.
3. Placa: **LOLIN(WEMOS) D1 R2 & mini**.
4. Librerias: `DHT sensor library`, `Adafruit Unified Sensor`, `PubSubClient`.
5. En el `.ino` cambia `WIFI_SSID`, `WIFI_PASS` y `MQTT_HOST` (IP de la Pi).
6. Puerto COM del D1 Mini y Subir.

## Probar

En la Raspberry:

```bash
mosquitto_sub -h localhost -t "portus/estacion/#" -v
```

En el Monitor Serie (115200) debes ver `[LECTURA]` aunque MQTT falle.

## Calibracion

- **Lluvia:** echa agua al YL-83. Si imprime al reves, en el codigo pon `LLUVIA_EN_LOW = false`.
- Ajusta el potenciómetro del modulo YL-83 hasta que seco = 0 y mojado = 1.
- **Luz:** tapa el LDR y anota el `raw` del Serial; ilumina y anota el otro. Pon esos valores en `LUZ_RAW_OSCURO` y `LUZ_RAW_CLARO`.
