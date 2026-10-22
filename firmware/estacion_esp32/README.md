# Estación meteorológica – ESP32

Firmware de la estación independiente de la maqueta (Fase 3, sec. 3). Mide temperatura,
humedad, lluvia y luz, y publica por MQTT sobre WiFi. No tiene cables hacia el Mega.

## 1. Conexiones

| Componente | Pin ESP32 | Alimentación | Notas |
|---|---|---|---|
| DHT11 DATA | GPIO 4 | 3.3V / GND | Pull-up de 10 kΩ entre DATA y 3.3V si el módulo no la trae |
| YL-83 lluvia DO | GPIO 27 | 3.3V / GND | DO en LOW = lloviendo. Ajustar sensibilidad con el potenciómetro. AO sin conectar |
| BH1750 SDA | GPIO 21 | 3.3V / GND | I2C. ADDR a GND (dirección 0x23) |
| BH1750 SCL | GPIO 22 | | I2C |

Alimentación de la estación: USB de 5V o batería. Sin conexión con el Mega.

## 2. Librerías (Arduino IDE → Gestor de librerías)

- **PubSubClient** (Nick O'Leary)
- **DHT sensor library** (Adafruit) y **Adafruit Unified Sensor**

Placa: paquete **esp32** de Espressif, placa "ESP32 Dev Module".

## 3. Configurar antes de cargar

En `estacion_esp32.ino`, sección CONFIGURACION:

- `WIFI_SSID` y `WIFI_PASSWORD`: la red de la terminal.
- `MQTT_HOST`: IP de la Raspberry Pi donde corre Mosquitto.
- `ID_ESTACION`: identificador del cliente.
- `LUX_ESCALA_100`: lux que equivalen a 100 en la escala de luz. Calibrar con la luz real de la maqueta.

## 4. Verificar

1. Cargar el sketch y abrir el monitor serie a **115200**.
2. Debe aparecer `[WIFI]`, `[MQTT] conectado` y, cada 5 s, una línea JSON como:
   `{"temperatura":24.1,"humedad":61.3,"lluvia":false,"luz":42,"ts":...,"uptime_s":...}`
3. Tapar el BH1750 con la mano: `luz` debe bajar. Mojar el YL-83: `lluvia` debe pasar a `true`.
4. Si `luz` sale `null`, el BH1750 no responde (revisar SDA/SCL y alimentación).
5. Si `temperatura` o `humedad` salen `null`, revisar el DHT11 y su pull-up.
6. En la Raspberry, `mosquitto_sub -t "portus/estacion/#" -v` debe mostrar las lecturas.

## 5. Topics

| Topic | Dirección | Contenido |
|---|---|---|
| `portus/estacion/lectura` | estación → servidor | temperatura, humedad, lluvia, luz (0–100), ts, uptime_s |
| `portus/estacion/estado` | estación → servidor | latido cada `SegundosLatidoEstacion` (10 s) |
| `portus/estacion/config` | servidor → estación | `SegundosLecturaEstacion=5;SegundosLatidoEstacion=10` |

Parámetros (sec. 8.7): `SegundosLecturaEstacion` 5 s (rango 2–60), `SegundosLatidoEstacion` 10 s
(rango 5–60). Se guardan en memoria no volátil y sobreviven a un corte de energía.

## 6. Comportamiento ante fallas

- Sin WiFi o sin broker: sigue midiendo y reconecta solo cada 5 s, sin reiniciar.
- Al recuperar la conexión, reanuda la publicación.
- El backend apaga o enciende la tira según `luz`; si `luz` es `null`, ignora la lectura.
