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

SoftwareSerial commEntrada(A1, 8);

MFRC522 mfrc522(SS_PIN, RST_PIN);
LiquidCrystal_I2C lcd(0x27, 16, 2);
Servo puerta;
const char* SRC = "UNO_SALIDA";
long txSeq = 1;
unsigned long lastHeartbeatMs = 0;

// ── Modo degradado (Observaciones_Firmware_PersonaA.md, punto 5) ──
// A diferencia de la garita de entrada, aqui NO se bloquea la salida: el PDF
// pide dejar completar los turnos que ya estan dentro (sec. 12.1.2) aunque se
// haya perdido el enlace. Solo se reporta el estado (LCD + heartbeat).
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

// ── Autorizacion de salida en el SERVIDOR (fase 1 del plan) ──
// Se manda evento=rfid_salida y se espera AbrirPuertaSalida (mismo uid) o
// RechazarSalida. Sin respuesta, o en modo degradado, decide la lista local
// camionesDentro: sec. 12.1.2 pide dejar salir a los turnos que ya estan dentro.
bool esperandoServidor = false;
String uidPendiente = "";
unsigned long tEsperaMs = 0;
const unsigned long TIMEOUT_SERVIDOR_MS = 5000;
String uidSaliendo = "";  // para informar quien cruzo en salida_completada

const int MAX_DENTRO = 10;
String camionesDentro[MAX_DENTRO];
int totalDentro = 0;

void setup() {
  Serial.begin(9600);
  Serial.setTimeout(20);
  commEntrada.begin(9600);

  pinMode(PIN_IR_ANTES, INPUT);
  pinMode(PIN_IR_DESPUES, INPUT);
  pinMode(PIN_LED_ROJO, OUTPUT);
  pinMode(PIN_LED_AMARILLO, OUTPUT);
  pinMode(PIN_LED_VERDE, OUTPUT);

  lcd.init();
  lcd.backlight();

  puerta.attach(PIN_SERVO);
  puerta.write(BARRA_ABAJO);

  SPI.begin();
  mfrc522.PCD_Init();
  delay(4);
  mfrc522.PCD_DumpVersionToSerial();

  semaforoRojo();
  mostrarEstado();

  Serial.println(F("=== Garita SALIDA lista ==="));
  sendFrame("EVT", "salida", "estado=iniciando;garita=salida");
}

void loop() {
  procesarComandosRemotos();
  actualizarModoDegradado();
  if (millis() - lastHeartbeatMs >= 5000) {
    lastHeartbeatMs = millis();
    sendFrame("HBT", "estado", String("garita=salida;barra=") + (barraAbierta ? "abierta" : "cerrada") + ";dentro=" + String(totalDentro) + ";degradado=" + (modoDegradado ? "1" : "0"));
  }

  if (mostrandoRechazo) {
    if (millis() - tRechazoMs >= DURACION_MENSAJE_RECHAZO_MS) {
      mostrandoRechazo = false;
      mostrarEstado();
    }
    return;  // sigue mostrando el mensaje; no lee una tarjeta nueva todavia
  }

  if (commEntrada.available()) {
    String msg = commEntrada.readStringUntil('\n');
    msg.trim();

    if (msg.startsWith("ENTRO:")) {
      String uid = msg.substring(6);
      uid.trim();
      agregarDentro(uid);
      Serial.print(F("Entro camion UID: "));
      Serial.println(uid);
      sendFrame("EVT", "salida", String("evento=entro_desde_entrada;uid=") + uid);
      if (!barraAbierta) mostrarEstado();
    }
  }

  if (esperandoServidor) {
    if (millis() - tEsperaMs >= TIMEOUT_SERVIDOR_MS) {
      esperandoServidor = false;
      decidirLocal(uidPendiente);
    }
    return;
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

    Serial.print(F("UID salida: "));
    Serial.println(uid);
    sendFrame("EVT", "salida", String("evento=rfid_salida;uid=") + uid);

    mfrc522.PICC_HaltA();

    if (modoDegradado) {
      decidirLocal(uid);
      return;
    }

    esperandoServidor = true;
    uidPendiente = uid;
    tEsperaMs = millis();
  }

  else {
    bool hayAntes   = (digitalRead(PIN_IR_ANTES)   == LOW);
    bool hayDespues = (digitalRead(PIN_IR_DESPUES) == LOW);

    if (hayDespues) llegoAlDespues = true;

    if (llegoAlDespues && !hayAntes && !hayDespues) {
      puerta.write(BARRA_ABAJO);
      barraAbierta = false;
      llegoAlDespues = false;

      semaforoRojo();
      mostrarEstado();
      Serial.println(F("Camion salio completo"));
      sendFrame("EVT", "salida", String(F("evento=salida_completada;uid=")) + uidSaliendo);
      uidSaliendo = "";
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
  int p[7], idx = 0, from = 0;
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

// Valor de "clave=" dentro de un payload "a=1;b=2" ("" si no esta).
String paramValor(const String& payload, const char* clave) {
  String k = String(";") + clave + "=";
  int i = payload.indexOf(k);
  if (i < 0) return "";
  int ini = i + k.length();
  int fin = payload.indexOf(';', ini);
  return fin < 0 ? payload.substring(ini) : payload.substring(ini, fin);
}

bool hayVehiculoBajoPuerta() {
  return digitalRead(PIN_IR_ANTES) == LOW || digitalRead(PIN_IR_DESPUES) == LOW;
}

void handleCommand(const String& payload) {
  if (payload.indexOf("target=UNO_SALIDA") < 0) return;
  if (payload.indexOf("name=AbrirPuertaSalida") >= 0) {
    // Respuesta del servidor a la tarjeta pendiente: el vehiculo esta frente
    // a la puerta, no aplica el chequeo de "debajo".
    String uid = paramValor(payload, "uid");
    if (esperandoServidor && uid == uidPendiente) {
      esperandoServidor = false;
      autorizarSalida(uid, false);
      sendFrame("ACK", "cmd", F("name=AbrirPuertaSalida"));
      return;
    }
    if (uid.length()) {
      // Autorizacion que llego tarde (ya decidio la lista local): no repetir.
      sendFrame("REJ", "cmd", F("name=AbrirPuertaSalida;causa=sin_validacion_pendiente"));
      return;
    }
    // Apertura manual (terminal, o turno anulado): no se sabe quien sale.
    if (hayVehiculoBajoPuerta()) {
      sendFrame("REJ", "cmd", "name=AbrirPuertaSalida;causa=vehiculo_bajo_puerta");
      return;
    }
    puerta.write(BARRA_ARRIBA);
    barraAbierta = true;
    llegoAlDespues = false;
    uidSaliendo = "";
    semaforoVerde();
    sendFrame("ACK", "cmd", "name=AbrirPuertaSalida");
    return;
  }
  if (payload.indexOf("name=CerrarPuertaSalida") >= 0) {
    if (hayVehiculoBajoPuerta()) {
      sendFrame("REJ", "cmd", "name=CerrarPuertaSalida;causa=vehiculo_bajo_puerta");
      return;
    }
    puerta.write(BARRA_ABAJO);
    barraAbierta = false;
    semaforoRojo();
    sendFrame("ACK", "cmd", "name=CerrarPuertaSalida");
    return;
  }
  if (payload.indexOf("name=RechazarSalida") >= 0) {
    String uid = paramValor(payload, "uid");
    if (!esperandoServidor || uid != uidPendiente) {
      sendFrame("REJ", "cmd", F("name=RechazarSalida;causa=sin_validacion_pendiente"));
      return;
    }
    esperandoServidor = false;
    String motivo = paramValor(payload, "motivo");
    rechazar(uid, motivo.length() ? motivo : String(F("No autorizado")), false);
    sendFrame("ACK", "cmd", F("name=RechazarSalida"));
    return;
  }
  sendFrame("REJ", "cmd", "name=UNKNOWN;causa=comando_no_soportado");
}

// Sin servidor (degradado o sin respuesta): decide la lista local.
void decidirLocal(const String& uid) {
  if (estaDentro(uid)) autorizarSalida(uid, true);
  else rechazar(uid, F("No esta dentro"), true);
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

void agregarDentro(String uid) {
  if (totalDentro < MAX_DENTRO) {
    camionesDentro[totalDentro] = uid;
    totalDentro++;
  }
}

bool estaDentro(String uid) {
  for (int i = 0; i < totalDentro; i++) {
    if (camionesDentro[i] == uid) return true;
  }
  return false;
}

void quitarDentro(String uid) {
  for (int i = 0; i < totalDentro; i++) {
    if (camionesDentro[i] == uid) {
      for (int j = i; j < totalDentro - 1; j++) {
        camionesDentro[j] = camionesDentro[j + 1];
      }
      totalDentro--;
      return;
    }
  }
}

// local=true: lo decidio la garita; local=false: lo decidio el servidor.
void rechazar(const String& uid, const String& motivo, bool local) {
  semaforoRojo();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("RECHAZADO");
  lcd.setCursor(0, 1);
  lcd.print(motivo);

  Serial.print(F("RECHAZADO: "));
  Serial.println(motivo);
  sendFrame("EVT", "salida", String(F("evento=rechazado;motivo=")) + motivo + F(";uid=") + uid +
            F(";decision=") + (local ? F("local") : F("servidor")));
  // Antes: delay(2500) bloqueaba heartbeat/comandos/sensores por 2.5s (ver
  // Observaciones_Firmware_PersonaA.md, punto 5). Ahora no bloquea.
  mostrandoRechazo = true;
  tRechazoMs = millis();
}

void autorizarSalida(const String& uid, bool local) {
  Serial.print(F("SALIDA AUTORIZADA UID: "));
  Serial.println(uid);
  sendFrame("EVT", "salida", String(F("evento=salida_autorizada;uid=")) + uid +
            F(";decision=") + (local ? F("local") : F("servidor")));

  quitarDentro(uid);
  uidSaliendo = uid;

  puerta.write(BARRA_ARRIBA);
  barraAbierta = true;
  llegoAlDespues = false;

  semaforoVerde();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("SALIDA OK");
  lcd.setCursor(0, 1);
  lcd.print("Puede salir");
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

void mostrarEstado() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Garita salida");
  lcd.setCursor(0, 1);
  lcd.print("Dentro: ");
  lcd.print(totalDentro);
}