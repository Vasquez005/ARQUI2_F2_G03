#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <Wire.h>
#include <Preferences.h>
#include <time.h>
#include <math.h>

const char*    WIFI_SSID     = "Estudio";
const char*    WIFI_PASSWORD = "9067047cc0";
const char*    MQTT_HOST     = "192.168.1.100";
const uint16_t MQTT_PORT     = 1883;
const char*    ID_ESTACION   = "ESTACION_1";

const int     PIN_DHT        = 4;
const int     PIN_LLUVIA     = 27;
const int     LLUVIA_ACTIVA  = LOW;
const int     PIN_I2C_SDA    = 21;
const int     PIN_I2C_SCL    = 22;
const uint8_t BH1750_ADDR    = 0x23;

const float LUX_ESCALA_100 = 1000.0;

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

DHT dht(PIN_DHT, DHT11);
WiFiClient wifiCliente;
PubSubClient mqtt(wifiCliente);
Preferences prefs;

uint32_t segLectura = LECTURA_DEFECTO_S;
uint32_t segLatido  = LATIDO_DEFECTO_S;

unsigned long ultimaLecturaMs     = 0;
unsigned long ultimoLatidoMs      = 0;
unsigned long ultimoIntentoWifiMs = 0;
unsigned long ultimoIntentoMqttMs = 0;

bool bh1750Iniciar() {
  Wire.beginTransmission(BH1750_ADDR);
  Wire.write(0x01);
  if (Wire.endTransmission() != 0) return false;
  Wire.beginTransmission(BH1750_ADDR);
  Wire.write(0x10);
  return Wire.endTransmission() == 0;
}

bool bh1750Leer(float& lux) {
  if (Wire.requestFrom(BH1750_ADDR, (uint8_t)2) != 2) return false;
  uint16_t crudo = ((uint16_t)Wire.read() << 8) | (uint16_t)Wire.read();
  lux = crudo / 1.2;
  return true;
}

int luzEscala(float lux) {
  float escala = lux * 100.0 / LUX_ESCALA_100;
  if (escala < 0) escala = 0;
  if (escala > 100) escala = 100;
  return (int)lround(escala);
}

void leerYPublicar() {
  float temperatura = dht.readTemperature();
  float humedad     = dht.readHumidity();
  bool  lloviendo   = digitalRead(PIN_LLUVIA) == LLUVIA_ACTIVA;
  float lux         = 0;
  bool  luzOk       = bh1750Leer(lux);

  char tempS[16], humS[16], luzS[16];
  if (isnan(temperatura)) strcpy(tempS, "null");
  else snprintf(tempS, sizeof tempS, "%.1f", temperatura);
  if (isnan(humedad)) strcpy(humS, "null");
  else snprintf(humS, sizeof humS, "%.1f", humedad);
  if (luzOk) snprintf(luzS, sizeof luzS, "%d", luzEscala(lux));
  else strcpy(luzS, "null");

  char payload[256];
  snprintf(payload, sizeof payload,
           "{\"temperatura\":%s,\"humedad\":%s,\"lluvia\":%s,\"luz\":%s,\"ts\":%ld,\"uptime_s\":%lu}",
           tempS, humS, lloviendo ? "true" : "false", luzS,
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
  if (WiFi.status() == WL_CONNECTED) return;
  if (millis() - ultimoIntentoWifiMs < MS_REINTENTO_WIFI) return;
  ultimoIntentoWifiMs = millis();
  Serial.println("[WIFI] reconectando...");
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void mantenerMqtt() {
  if (mqtt.connected()) return;
  if (WiFi.status() != WL_CONNECTED) return;
  if (millis() - ultimoIntentoMqttMs < MS_REINTENTO_MQTT) return;
  ultimoIntentoMqttMs = millis();
  Serial.println("[MQTT] conectando...");
  if (mqtt.connect(ID_ESTACION)) {
    mqtt.subscribe(TOPIC_CONFIG);
    Serial.println("[MQTT] conectado");
  } else {
    Serial.printf("[MQTT] fallo, rc=%d\n", mqtt.state());
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println(F("=== PORTUS Fase 3 - Estacion meteorologica ==="));

  dht.begin();
  pinMode(PIN_LLUVIA, INPUT);
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  if (!bh1750Iniciar()) Serial.println(F("[AVISO] BH1750 no responde: revisar SDA/SCL y alimentacion"));

  prefs.begin("estacion", true);
  segLectura = prefs.getUInt("lectura", LECTURA_DEFECTO_S);
  segLatido  = prefs.getUInt("latido", LATIDO_DEFECTO_S);
  prefs.end();

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  configTime(0, 0, "pool.ntp.org");

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(alRecibirMensaje);
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
