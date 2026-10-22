# Estación meteorológica – ESP32-S3

Firmware de la estación independiente de la maqueta (Fase 3, sec. 3). Mide temperatura,
humedad, lluvia y luz (0–100), y publica por MQTT sobre WiFi. No tiene cables hacia el Mega.

## 1. Conexiones (maqueta actual)

| Componente | Pin (silkscreen) | Alimentación | Notas |
|---|---|---|---|
| DHT11 DATA (`out`) | **4** | 3.3V / GND | Módulo `+` → 3V3, `-` → GND |
| YL-83 lluvia **DO** | **9** | 3.3V / GND | DO en **LOW** = lloviendo. Potenciómetro en el módulo azul. **AO** sin cable |
| LDR (fotoresistor) | **10** | divisor | `3.3V — LDR — pin 10 — 10 kΩ — GND` |

Alimentación: **3V3** y **GND** del ESP32 (no usar 5V IN para sensores). Programación por USB-C.

> En el enunciado genérico la lluvia va a GPIO **27** y la luz es sensor **BH1750** (I2C 21/22).
> Esta placa **ESP32-S3** y el hardware del equipo usan **9** y **LDR en 10** (ver comentarios en el `.ino`).

## 2. Arduino IDE

- Paquete **esp32** (Espressif Systems).
- Placa: **ESP32S3 Dev Module**.
- **USB CDC On Boot:** Enabled (monitor serie por USB).
- Monitor serie: **115200**.

Librerías (Gestor de librerías):

- **PubSubClient** (Nick O'Leary)
- **DHT sensor library** (Adafruit) + **Adafruit Unified Sensor**

## 3. Configurar antes de cargar

En `estacion_esp32.ino`:

| Constante | Uso |
|---|---|
| `WIFI_SSID` / `WIFI_PASSWORD` | Red WiFi de la terminal / PC con Mosquitto |
| `MQTT_HOST` | IP del host donde corre Mosquitto (ej. Raspberry o PC) |
| `ID_ESTACION` | Cliente MQTT (ej. `ESTACION_1`) |
| `LUZ_RAW_OSCURO` / `LUZ_RAW_CLARO` | Calibración LDR → escala **luz** 0–100 |

Calibración LDR: con el sketch cargado, anota el valor ADC (puedes usar una lectura JSON o monitor)
con el LDR tapado (oscuro) y con luz fuerte (claro), y actualiza las dos constantes.

## 4. Verificar

1. Cargar el sketch y abrir el monitor serie a **115200**.
2. Debe aparecer `[WIFI] conectado`, `[MQTT] conectado` y, cada `SegundosLecturaEstacion` (5 s por defecto), JSON como:
   `{"temperatura":24.1,"humedad":61.3,"lluvia":false,"luz":42,"ts":...,"uptime_s":...}`
3. Tapar el LDR: `luz` debe bajar. Mojar la **placa negra** del YL-83: `lluvia` debe pasar a `true`.
4. Si `temperatura` o `humedad` salen `null`, revisar DHT11 (pin 4, 3.3V, GND).
5. En el broker: `mosquitto_sub -t "portus/estacion/#" -v`

## 5. Topics MQTT (sec. 3 / 8.7)

| Topic | Dirección | Contenido |
|---|---|---|
| `portus/estacion/lectura` | estación → servidor | `temperatura`, `humedad`, `lluvia`, `luz` (0–100), `ts`, `uptime_s` |
| `portus/estacion/estado` | estación → servidor | latido: `estado`, `id`, `rssi`, `uptime_s` |
| `portus/estacion/config` | servidor → estación | `SegundosLecturaEstacion=5;SegundosLatidoEstacion=10` |

Parámetros (sec. 8.7):

- `SegundosLecturaEstacion`: default **5** s, rango **2–60**
- `SegundosLatidoEstacion`: default **10** s, rango **5–60**

Se guardan en **Preferences** (`estacion`) y sobreviven a un corte de energía.

Ejemplo de config manual:

```bash
mosquitto_pub -t portus/estacion/config -m "SegundosLecturaEstacion=5;SegundosLatidoEstacion=10"
```

## 6. Comportamiento ante fallas

- Sin WiFi o sin broker: **sigue midiendo** e imprime JSON en serie; reconecta cada **5 s**, **sin reiniciar**.
- Al recuperar MQTT, **reanuda** publicación en los topics.
- Campo `luz`: siempre entero **0–100** (LDR calibrado). El servidor ignora lecturas sin `luz` válida si viniera `null` (este firmware no envía `null` en luz).
