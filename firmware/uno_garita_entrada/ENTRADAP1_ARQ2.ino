#include <SPI.h>
#include <MFRC522.h>
#include <LiquidCrystal_I2C.h>
#include <Servo.h>
#include <SoftwareSerial.h>

#define SS_PIN    10
#define RST_PIN   9
#define PIN_SERVO 3
#define PIN_IR_ANTES   2
#define PIN_IR_DESPUES 4
#define PIN_LED_ROJO     6
#define PIN_LED_AMARILLO 5
#define PIN_LED_VERDE    7

SoftwareSerial commSalida(A1, 8);

MFRC522 mfrc522(SS_PIN, RST_PIN);
LiquidCrystal_I2C lcd(0x27, 16, 2);
Servo talanquera;
const char* SRC = "UNO_ENTRADA";
long txSeq = 1;
unsigned long lastHeartbeatMs = 0;

// ── Modo degradado (Observaciones_Firmware_PersonaA.md, punto 5) ──
// La Pi manda un ping ("PIN") periodico; si no llega nada de ella en
// UMBRAL_DEGRADADO_MS se asume enlace perdido y se rechazan ingresos nuevos
// (Fase_2_PORTUS.md sec. 12.1.3). Requiere que bridge.py mande ese ping.
unsigned long ultimaActividadPiMs = 0;
const unsigned long UMBRAL_DEGRADADO_MS = 10000;
bool modoDegradado = false;

// ── Mensaje de rechazo no bloqueante (antes usaba delay(2500)) ──
bool mostrandoRechazo = false;
unsigned long tRechazoMs = 0;
const unsigned long DURACION_MENSAJE_RECHAZO_MS = 2500;

const int BARRA_ABAJO  = 90;
const int BARRA_ARRIBA = 0;
bool barraAbierta = false;
bool llegoAlDespues = false;

const int NUM_CAMIONES = 4;

String camionesRegistrados[NUM_CAMIONES] = {
  "D3 E8 8E FC",
  "43 E9 2E 10",
  "A4 C8 98 07",
  "03 56 29 10"
};

bool camionAutorizado[NUM_CAMIONES] = {
  true,
  true,
  false,
  true
};

String manifiestoOperacion[NUM_CAMIONES] = {
  "DEPOSITO",
  "RETIRO",
  "DEPOSITO",
  "DEPOSITO"
};

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(20);
  commSalida.begin(9600);

  pinMode(PIN_IR_ANTES, INPUT);
  pinMode(PIN_IR_DESPUES, INPUT);
  pinMode(PIN_LED_ROJO, OUTPUT);
  pinMode(PIN_LED_AMARILLO, OUTPUT);
  pinMode(PIN_LED_VERDE, OUTPUT);

  lcd.init();
  lcd.backlight();

  talanquera.attach(PIN_SERVO);
  talanquera.write(BARRA_ABAJO);

  SPI.begin();
  mfrc522.PCD_Init();
  delay(4);
  mfrc522.PCD_DumpVersionToSerial();

  semaforoRojo();
  mostrarEspera();

  Serial.println(F("=== Garita ENTRADA lista ==="));
  sendFrame("EVT", "garita", "estado=iniciando;garita=entrada");
}

void loop() {
  procesarComandosRemotos();
  actualizarModoDegradado();

  if (millis() - lastHeartbeatMs >= 5000) {
    lastHeartbeatMs = millis();
    sendFrame("HBT", "estado", String("garita=entrada;barra=") + (barraAbierta ? "abierta" : "cerrada") + ";degradado=" + (modoDegradado ? "1" : "0"));
  }

  if (mostrandoRechazo) {
    if (millis() - tRechazoMs >= DURACION_MENSAJE_RECHAZO_MS) {
      mostrandoRechazo = false;
      if (modoDegradado) mostrarDegradado(); else mostrarEspera();
    }
    return;  // sigue mostrando el mensaje; no lee una tarjeta nueva todavia
  }

  if (!barraAbierta) {
    if (!mfrc522.PICC_IsNewCardPresent()) return;
    if (!mfrc522.PICC_ReadCardSerial())   return;

    semaforoAmarillo();
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Validando...");

    String uid = "";
    for (byte i = 0; i < mfrc522.uid.size; i++) {
      if (mfrc522.uid.uidByte[i] < 0x10) uid += "0";
      uid += String(mfrc522.uid.uidByte[i], HEX);
      uid += " ";
    }
    uid.toUpperCase();
    uid.trim();

    Serial.print(F("UID leido: "));
    Serial.println(uid);
    sendFrame("EVT", "garita", String("evento=rfid;uid=") + uid);

    if (modoDegradado) {
      rechazar("Modo degradado");
      return;
    }

    int idx = buscarCamion(uid);

    if (idx == -1) {
      rechazar("RFID no reconoc");
      return;
    }

    if (!camionAutorizado[idx]) {
      rechazar("No autorizado");
      return;
    }

    if (manifiestoOperacion[idx] == "") {
      rechazar("Sin manifiesto");
      return;
    }

    if (manifiestoOperacion[idx] != "DEPOSITO" && manifiestoOperacion[idx] != "RETIRO") {
      rechazar("Op invalida");
      return;
    }

    autorizar(idx, uid);
  }

  else {
    bool hayAntes   = (digitalRead(PIN_IR_ANTES)   == LOW);
    bool hayDespues = (digitalRead(PIN_IR_DESPUES) == LOW);

    if (hayDespues) {
      llegoAlDespues = true;
    }

    if (llegoAlDespues && !hayAntes && !hayDespues) {
      talanquera.write(BARRA_ABAJO);
      barraAbierta = false;
      llegoAlDespues = false;

      semaforoRojo();
      mostrarEspera();
      Serial.println(F("Barra ENTRADA ABAJO"));
      sendFrame("EVT", "garita", "evento=barra_abajo;garita=entrada");
    }
  }
}

String toHex2(uint8_t v) {
  const char* h = "0123456789ABCDEF";
  String s = "";
  s += h[(v >> 4) & 0xF];
  s += h[v & 0xF];
  return s;
}

String checksumBase(const String& base) {
  uint16_t sum = 0;
  for (size_t i = 0; i < base.length(); i++) sum += (uint8_t)base[i];
  return toHex2((uint8_t)(sum % 256));
}

String makeFrame(const String& kind, const String& topic, const String& payload, long seq) {
  String base = "PORTUS|" + String(SRC) + "|" + String(seq) + "|" + kind + "|" + topic + "|" + payload;
  return "<" + base + "|" + checksumBase(base) + ">";
}

void sendFrame(const String& kind, const String& topic, const String& payload) {
  Serial.println(makeFrame(kind, topic, payload, txSeq++));
}

bool parseFrame(String line, String& src, long& seq, String& kind, String& topic, String& payload) {
  line.trim();
  if (!line.startsWith("<") || !line.endsWith(">")) return false;
  line = line.substring(1, line.length() - 1);

  int p[7];
  int idx = 0, from = 0;
  while (idx < 6) {
    int at = line.indexOf('|', from);
    if (at < 0) return false;
    p[idx++] = at;
    from = at + 1;
  }
  if (line.substring(0, p[0]) != "PORTUS") return false;
  src = line.substring(p[0] + 1, p[1]);
  seq = line.substring(p[1] + 1, p[2]).toInt();
  kind = line.substring(p[2] + 1, p[3]);
  topic = line.substring(p[3] + 1, p[4]);
  payload = line.substring(p[4] + 1, p[5]);
  String chk = line.substring(p[5] + 1);

  String base = "PORTUS|" + src + "|" + String(seq) + "|" + kind + "|" + topic + "|" + payload;
  return checksumBase(base) == chk;
}

bool hayVehiculoDebajoTalanquera() {
  return digitalRead(PIN_IR_ANTES) == LOW || digitalRead(PIN_IR_DESPUES) == LOW;
}

void handleCommand(const String& payload) {
  if (payload.indexOf("target=UNO_ENTRADA") < 0) return;

  if (payload.indexOf("name=AbrirTalanquera") >= 0) {
    if (hayVehiculoDebajoTalanquera()) {
      sendFrame("REJ", "cmd", "name=AbrirTalanquera;causa=vehiculo_bajo_talanquera");
      return;
    }
    talanquera.write(BARRA_ARRIBA);
    barraAbierta = true;
    llegoAlDespues = false;
    semaforoVerde();
    sendFrame("ACK", "cmd", "name=AbrirTalanquera");
    return;
  }

  if (payload.indexOf("name=CerrarTalanquera") >= 0) {
    if (hayVehiculoDebajoTalanquera()) {
      sendFrame("REJ", "cmd", "name=CerrarTalanquera;causa=vehiculo_bajo_talanquera");
      return;
    }
    talanquera.write(BARRA_ABAJO);
    barraAbierta = false;
    semaforoRojo();
    sendFrame("ACK", "cmd", "name=CerrarTalanquera");
    return;
  }

  sendFrame("REJ", "cmd", "name=UNKNOWN;causa=comando_no_soportado");
}

void procesarComandosRemotos() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  if (!line.startsWith("<PORTUS|")) return;
  String src, kind, topic, payload;
  long seq = 0;
  if (!parseFrame(line, src, seq, kind, topic, payload)) return;
  ultimaActividadPiMs = millis();  // cualquier frame valido (CMD o PIN) cuenta como "hay enlace"
  if (kind == "CMD" && topic == "cmd") handleCommand(payload);
}

void actualizarModoDegradado() {
  modoDegradado = (millis() - ultimaActividadPiMs) > UMBRAL_DEGRADADO_MS;
}

int buscarCamion(String uid) {
  for (int i = 0; i < NUM_CAMIONES; i++) {
    if (camionesRegistrados[i] == uid) {
      return i;
    }
  }
  return -1;
}

void rechazar(String motivo) {
  semaforoRojo();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("RECHAZADO");
  lcd.setCursor(0, 1);
  lcd.print(motivo);

  Serial.print(F("RECHAZADO: "));
  Serial.println(motivo);
  sendFrame("EVT", "garita", String("evento=rechazado;motivo=") + motivo);

  mfrc522.PICC_HaltA();
  // Antes: delay(2500) bloqueaba heartbeat/comandos/sensores por 2.5s (ver
  // Observaciones_Firmware_PersonaA.md, punto 5). Ahora el mensaje se muestra
  // sin bloquear y loop() lo retira solo tras DURACION_MENSAJE_RECHAZO_MS.
  mostrandoRechazo = true;
  tRechazoMs = millis();
}

void autorizar(int idx, String uid) {
  Serial.print(F("AUTORIZADO - Camion "));
  Serial.print(idx + 1);
  Serial.print(F(" - "));
  Serial.println(manifiestoOperacion[idx]);

  commSalida.print("ENTRO:");
  commSalida.println(uid);
  sendFrame("EVT", "garita", String("evento=autorizado;uid=") + uid + ";op=" + manifiestoOperacion[idx]);

  talanquera.write(BARRA_ARRIBA);
  barraAbierta = true;
  llegoAlDespues = false;

  semaforoVerde();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("AUTORIZADO");
  lcd.setCursor(0, 1);
  lcd.print(manifiestoOperacion[idx]);

  mfrc522.PICC_HaltA();
}

void semaforoRojo() {
  digitalWrite(PIN_LED_ROJO, HIGH);
  digitalWrite(PIN_LED_AMARILLO, LOW);
  digitalWrite(PIN_LED_VERDE, LOW);
}
void semaforoAmarillo() {
  digitalWrite(PIN_LED_ROJO, LOW);
  digitalWrite(PIN_LED_AMARILLO, HIGH);
  digitalWrite(PIN_LED_VERDE, LOW);
}
void semaforoVerde() {
  digitalWrite(PIN_LED_ROJO, LOW);
  digitalWrite(PIN_LED_AMARILLO, LOW);
  digitalWrite(PIN_LED_VERDE, HIGH);
}

void mostrarEspera() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Garita entrada");
  lcd.setCursor(0, 1);
  lcd.print("Acerca tarjeta");
}

void mostrarDegradado() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("MODO DEGRADADO");
  lcd.setCursor(0, 1);
  lcd.print("Sin enlace a Pi");
}