/*
 * PORTUS Fase 3 — Estación meteorológica (ESP32-S3)
 * WiFi + MQTT. Independiente del Mega.
 *
 * Cableado maqueta (ESP32-S3-WROOM-1, silkscreen):
 *   DHT11 DATA  → GPIO 4  (3.3V, GND)
 *   YL-83 DO    → GPIO 9  (3.3V, GND; LOW = lluvia; AO sin cable)
 *   LDR + 10kΩ  → GPIO 10 (3.3V — LDR — GPIO10 — 10k — GND)
 *
 * En placa genérica del curso: lluvia GPIO 27 + BH1750 I2C; aquí LDR en GPIO 10.
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <Preferences.h>
#include <time.h>

// ─── CONFIGURACIÓN (editar antes de cargar) ───────────────────────────────
const char*    WIFI_SSID     = "Estudio";
const char*    WIFI_PASSWORD = "9067047cc0";
const char*    MQTT_HOST     = "192.168.1.100";
const uint16_t MQTT_PORT     = 1883;
const char*    ID_ESTACION   = "ESTACION_1";

const int PIN_DHT    = 4;
const int PIN_LLUVIA = 9;
const int PIN_LDR    = 10;

#define DHTTYPE DHT11
const int LLUVIA_ACTIVA = LOW;

// Calibrar con el monitor: tapa LDR → anota raw; luz fuerte → anota raw.
int LUZ_RAW_OSCURO = 800;
int LUZ_RAW_CLARO  = 3200;

const uint32_t LECTURA_DEFECTO_S = 5;
const uint32_t LECTURA_MIN_S     = 2;
const uint32_t LECTURA_MAX_S     = 60;
const uint32_t LATIDO_DEFECTO_S  = 10;
const uint32_t LATIDO_MIN_S      = 5;
const uint32_t LATIDO_MAX_S      = 60;

const char* TOPIC_LECTURA = "portus/estacion/lectura";
const char* TOPIC_ESTADO  = "portus/estacion/estado";
const char* TOPIC_CONFIG  = "portus/estacion/config";

const unsigned long MS_REINTENTO_WIFI = 5000;
const unsigned long MS_REINTENTO_MQTT = 5000;

DHT dht(PIN_DHT, DHTTYPE);
WiFiClient wifiCliente;
PubSubClient mqtt(wifiCliente);
Preferences prefs;

uint32_t segLectura = LECTURA_DEFECTO_S;
uint32_t segLatido  = LATIDO_DEFECTO_S;

unsigned long ultimaLecturaMs     = 0;
unsigned long ultimoLatidoMs      = 0;
unsigned long ultimoIntentoWifiMs = 0;
unsigned long ultimoIntentoMqttMs = 0;
bool wifiInformado                = false;

int leerLdrRaw() {
  return analogRead(PIN_LDR);
}

int luzPorCiento(int raw) {
  if (raw <= LUZ_RAW_OSCURO) return 0;
  if (raw >= LUZ_RAW_CLARO) return 100;
  return (raw - LUZ_RAW_OSCURO) * 100 / (LUZ_RAW_CLARO - LUZ_RAW_OSCURO);
}

void leerYPublicar() {
  float temperatura = dht.readTemperature();
  float humedad     = dht.readHumidity();
  bool  lloviendo   = digitalRead(PIN_LLUVIA) == LLUVIA_ACTIVA;
  int   luz         = luzPorCiento(leerLdrRaw());

  char tempS[16], humS[16];
  if (isnan(temperatura)) strcpy(tempS, "null");
  else snprintf(tempS, sizeof tempS, "%.1f", temperatura);
  if (isnan(humedad)) strcpy(humS, "null");
  else snprintf(humS, sizeof humS, "%.1f", humedad);

  char payload[256];
  snprintf(payload, sizeof payload,
           "{\"temperatura\":%s,\"humedad\":%s,\"lluvia\":%s,\"luz\":%d,\"ts\":%ld,\"uptime_s\":%lu}",
           tempS, humS, lloviendo ? "true" : "false", luz,
           (long)time(nullptr), millis() / 1000UL);

  Serial.println(payload);
  if (mqtt.connected()) mqtt.publish(TOPIC_LECTURA, payload);
}

void publicarLatido() {
  if (!mqtt.connected()) return;
  char payload[128];
  snprintf(payload, sizeof payload,
           "{\"estado\":\"ok\",\"id\":\"%s\",\"rssi\":%d,\"uptime_s\":%lu}",
           ID_ESTACION, WiFi.RSSI(), millis() / 1000UL);
  mqtt.publish(TOPIC_ESTADO, payload);
}

uint32_t leerParametro(const String& msg, const char* clave, uint32_t actual,
                       uint32_t minimo, uint32_t maximo) {
  String buscado = String(clave) + "=";
  int ini = msg.indexOf(buscado);
  if (ini < 0) return actual;
  ini += buscado.length();
  int fin = msg.indexOf(';', ini);
  if (fin < 0) fin = msg.length();
  long valor = msg.substring(ini, fin).toInt();
  if (valor < (long)minimo || valor > (long)maximo) return actual;
  return (uint32_t)valor;
}

void alRecibirMensaje(char* topic, byte* payload, unsigned int len) {
  if (String(topic) != TOPIC_CONFIG) return;

  String msg;
  msg.reserve(len);
  for (unsigned int i = 0; i < len; i++) msg += (char)payload[i];

  uint32_t nuevaLectura = leerParametro(msg, "SegundosLecturaEstacion", segLectura, LECTURA_MIN_S, LECTURA_MAX_S);
  uint32_t nuevoLatido  = leerParametro(msg, "SegundosLatidoEstacion", segLatido, LATIDO_MIN_S, LATIDO_MAX_S);

  if (nuevaLectura != segLectura || nuevoLatido != segLatido) {
    segLectura = nuevaLectura;
    segLatido  = nuevoLatido;
    prefs.begin("estacion", false);
    prefs.putUInt("lectura", segLectura);
    prefs.putUInt("latido", segLatido);
    prefs.end();
    Serial.printf("[CONFIG] SegundosLecturaEstacion=%lu SegundosLatidoEstacion=%lu\n",
                  (unsigned long)segLectura, (unsigned long)segLatido);
  }
}

void mantenerWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiInformado) {
      wifiInformado = true;
      Serial.print(F("[WIFI] conectado, IP "));
      Serial.println(WiFi.localIP());
    }
    return;
  }
  wifiInformado = false;
  if (millis() - ultimoIntentoWifiMs < MS_REINTENTO_WIFI) return;
  ultimoIntentoWifiMs = millis();
  Serial.println(F("[WIFI] reconectando..."));
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void mantenerMqtt() {
  if (mqtt.connected()) return;
  if (WiFi.status() != WL_CONNECTED) return;
  if (millis() - ultimoIntentoMqttMs < MS_REINTENTO_MQTT) return;
  ultimoIntentoMqttMs = millis();
  Serial.println(F("[MQTT] conectando..."));
  if (mqtt.connect(ID_ESTACION)) {
    mqtt.subscribe(TOPIC_CONFIG);
    Serial.println(F("[MQTT] conectado"));
  } else {
    Serial.printf("[MQTT] fallo, rc=%d\n", mqtt.state());
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println(F("=== PORTUS Fase 3 - Estacion meteorologica (ESP32-S3) ==="));

#if CONFIG_IDF_TARGET_ESP32 || CONFIG_IDF_TARGET_ESP32S2 || CONFIG_IDF_TARGET_ESP32S3
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
#endif

  dht.begin();
  pinMode(PIN_LLUVIA, INPUT);
  pinMode(PIN_LDR, INPUT);

  prefs.begin("estacion", true);
  segLectura = prefs.getUInt("lectura", LECTURA_DEFECTO_S);
  segLatido  = prefs.getUInt("latido", LATIDO_DEFECTO_S);
  prefs.end();

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  configTime(0, 0, "pool.ntp.org");

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(alRecibirMensaje);
  mqtt.setBufferSize(512);
}

void loop() {
  mantenerWifi();
  mantenerMqtt();
  if (mqtt.connected()) mqtt.loop();

  unsigned long ahora = millis();
  if (ahora - ultimaLecturaMs >= segLectura * 1000UL) {
    ultimaLecturaMs = ahora;
    leerYPublicar();
  }
  if (ahora - ultimoLatidoMs >= segLatido * 1000UL) {
    ultimoLatidoMs = ahora;
    publicarLatido();
  }
}
