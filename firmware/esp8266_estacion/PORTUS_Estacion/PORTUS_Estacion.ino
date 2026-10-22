/*
 * PORTUS Fase 3 - Estacion meteorologica
 * Placa: NodeMCU ESP-12 / WeMos D1 Mini (ESP8266)
 *
 * Publica:
 *   portus/estacion/lectura  cada SegundosLecturaEstacion (default 5 s)
 *   portus/estacion/estado   cada SegundosLatidoEstacion  (default 10 s)
 *
 * Librerias (Arduino IDE -> Administrar bibliotecas):
 *   - DHT sensor library (Adafruit)
 *   - Adafruit Unified Sensor
 *   - PubSubClient (Nick O'Leary)
 *
 * Placa IDE: NodeMCU 1.0 (ESP-12E Module)
 */

#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <EEPROM.h>
#include <DHT.h>

// ════════════════════════════════════════════════════════════════════════════
//  RED - CAMBIA ESTO
// ════════════════════════════════════════════════════════════════════════════
const char* WIFI_SSID  = "TU_WIFI";
const char* WIFI_PASS  = "TU_PASSWORD";
const char* MQTT_HOST  = "192.168.1.65";   // IP de la Raspberry
const uint16_t MQTT_PORT = 1883;

const char* MQTT_CLIENT_ID = "PORTUS_ESTACION";
const char* TOPIC_LECTURA  = "portus/estacion/lectura";
const char* TOPIC_ESTADO   = "portus/estacion/estado";
const char* TOPIC_CFG      = "portus/estacion/config";

// ════════════════════════════════════════════════════════════════════════════
//  PINES WeMos D1 Mini
// ════════════════════════════════════════════════════════════════════════════
const int PIN_DHT    = D2;   // GPIO4  DHT22 DATA
const int PIN_LLUVIA = D5;   // GPIO14 YL-83 DO (digital)
const int PIN_LDR    = A0;   // unico ADC

#define DHTTYPE DHT11
DHT dht(PIN_DHT, DHTTYPE);

// YL-83: en la mayoria LOW = mojado. Si te queda al reves, cambia a false.
const bool LLUVIA_EN_LOW = true;

// Calibracion de luz (ajusta con Serial: tapa el LDR y luego iluminalo)
int LUZ_RAW_OSCURO = 50;
int LUZ_RAW_CLARO  = 900;

// ════════════════════════════════════════════════════════════════════════════
//  PARAMETROS (Fase 3) - se guardan en EEPROM
// ════════════════════════════════════════════════════════════════════════════
const int EEPROM_MAGIC = 0x53;  // 'S'
int segundosLectura = 5;        // 2..60
int segundosLatido  = 10;       // 5..60

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

unsigned long ultimoLecturaMs = 0;
unsigned long ultimoLatidoMs  = 0;
unsigned long ultimoWifiMs    = 0;

// ════════════════════════════════════════════════════════════════════════════
void cargarParametros() {
  EEPROM.begin(16);
  if (EEPROM.read(0) != EEPROM_MAGIC) {
    guardarParametros();
    return;
  }
  int lec = EEPROM.read(1);
  int lat = EEPROM.read(2);
  if (lec >= 2 && lec <= 60) segundosLectura = lec;
  if (lat >= 5 && lat <= 60) segundosLatido  = lat;
}

void guardarParametros() {
  EEPROM.write(0, EEPROM_MAGIC);
  EEPROM.write(1, (uint8_t)segundosLectura);
  EEPROM.write(2, (uint8_t)segundosLatido);
  EEPROM.commit();
}

int luz0a100() {
  int raw = analogRead(PIN_LDR);
  if (LUZ_RAW_CLARO == LUZ_RAW_OSCURO) return 0;
  long v = map(raw, LUZ_RAW_OSCURO, LUZ_RAW_CLARO, 0, 100);
  if (v < 0) v = 0;
  if (v > 100) v = 100;
  return (int)v;
}

bool hayLluvia() {
  int v = digitalRead(PIN_LLUVIA);
  return LLUVIA_EN_LOW ? (v == LOW) : (v == HIGH);
}

void imprimirLocal() {
  int crudo = digitalRead(PIN_LLUVIA);
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  Serial.print(F("[LOCAL] lluvia="));
  Serial.print(hayLluvia() ? 1 : 0);
  Serial.print(F("  DO="));
  Serial.print(crudo == LOW ? F("LOW") : F("HIGH"));
  Serial.print(F("  luz="));
  Serial.print(luz0a100());
  Serial.print(F("  rawA0="));
  Serial.print(analogRead(PIN_LDR));
  Serial.print(F("  temp="));
  if (isnan(t)) Serial.print(F("ERR"));
  else Serial.print(t, 1);
  Serial.print(F("  hum="));
  if (isnan(h)) Serial.print(F("ERR"));
  else Serial.print(h, 1);
  Serial.println();
}

void publicarLectura() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  bool lluvia = hayLluvia();
  int luz = luz0a100();

  if (isnan(t)) t = -99;
  if (isnan(h)) h = -99;

  char payload[160];
  snprintf(payload, sizeof(payload),
           "{\"temp\":%.1f,\"hum\":%.1f,\"lluvia\":%d,\"luz\":%d,\"ts\":%lu}",
           t, h, lluvia ? 1 : 0, luz, millis() / 1000UL);

  mqtt.publish(TOPIC_LECTURA, payload, false);

  Serial.print(F("[LECTURA] "));
  Serial.println(payload);
}

void publicarEstado() {
  char payload[120];
  snprintf(payload, sizeof(payload),
           "{\"ok\":1,\"wifi\":1,\"lectura_s\":%d,\"latido_s\":%d,\"rssi\":%d}",
           segundosLectura, segundosLatido, WiFi.RSSI());
  mqtt.publish(TOPIC_ESTADO, payload, false);
  Serial.print(F("[ESTADO] "));
  Serial.println(payload);
}

void aplicarConfig(const String& msg) {
  // Ej: lectura=5;latido=10
  int lec = segundosLectura;
  int lat = segundosLatido;
  int i = msg.indexOf("lectura=");
  if (i >= 0) lec = msg.substring(i + 8).toInt();
  i = msg.indexOf("latido=");
  if (i >= 0) lat = msg.substring(i + 7).toInt();

  if (lec < 2 || lec > 60 || lat < 5 || lat > 60) {
    Serial.println(F("[CFG] valores fuera de rango, se ignoran"));
    return;
  }
  segundosLectura = lec;
  segundosLatido  = lat;
  guardarParametros();
  Serial.println(F("[CFG] parametros guardados en EEPROM"));
}

void onMqttMessage(char* topic, byte* payload, unsigned int len) {
  String msg;
  for (unsigned int i = 0; i < len; i++) msg += (char)payload[i];
  if (String(topic) == TOPIC_CFG) aplicarConfig(msg);
}

const char* nombreEstadoWifi(int s) {
  switch (s) {
    case WL_IDLE_STATUS:    return "idle";
    case WL_NO_SSID_AVAIL:  return "no encuentra esa red (SSID mal o es 5GHz)";
    case WL_SCAN_COMPLETED: return "scan ok";
    case WL_CONNECTED:      return "conectado";
    case WL_CONNECT_FAILED: return "password incorrecta";
    case WL_CONNECTION_LOST:return "se perdio";
    case WL_DISCONNECTED:   return "desconectado";
    default:                return "desconocido";
  }
}

void asegurarWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  if (millis() - ultimoWifiMs < 8000) return;
  ultimoWifiMs = millis();

  Serial.print(F("[WIFI] conectando a '"));
  Serial.print(WIFI_SSID);
  Serial.println(F("' (solo 2.4 GHz)"));
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 12000) {
    delay(400);
    Serial.print('.');
  }
  Serial.println();
  Serial.print(F("[WIFI] estado="));
  Serial.println(nombreEstadoWifi(WiFi.status()));
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print(F("[WIFI] IP="));
    Serial.println(WiFi.localIP());
  }
}

void asegurarMqtt() {
  if (mqtt.connected()) return;
  if (WiFi.status() != WL_CONNECTED) return;

  Serial.print(F("[MQTT] conectando a "));
  Serial.println(MQTT_HOST);
  if (mqtt.connect(MQTT_CLIENT_ID)) {
    mqtt.subscribe(TOPIC_CFG);
    Serial.println(F("[MQTT] OK"));
    publicarEstado();
  } else {
    Serial.print(F("[MQTT] fallo rc="));
    Serial.println(mqtt.state());
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  pinMode(PIN_LLUVIA, INPUT);
  dht.begin();
  cargarParametros();

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
  mqtt.setKeepAlive(20);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.println(F("=== PORTUS estacion ESP8266 ==="));
}

void loop() {
  asegurarWifi();
  if (WiFi.status() == WL_CONNECTED) {
    asegurarMqtt();
    mqtt.loop();
  }

  unsigned long ahora = millis();
  if (ahora - ultimoLecturaMs >= (unsigned long)segundosLectura * 1000UL) {
    ultimoLecturaMs = ahora;
    if (mqtt.connected()) publicarLectura();
    else imprimirLocal();
  }

  if (mqtt.connected() && ahora - ultimoLatidoMs >= (unsigned long)segundosLatido * 1000UL) {
    ultimoLatidoMs = ahora;
    publicarEstado();
  }
}
