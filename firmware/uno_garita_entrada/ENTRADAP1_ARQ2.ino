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

// ===== PESAJE =====
#define PIN_AGUJA        A0
#define PIN_FLECHA_VERDE A2
#define PIN_FLECHA_AMBAR A3

SoftwareSerial commSalida(A1, 8);

MFRC522 mfrc522(SS_PIN, RST_PIN);
LiquidCrystal_I2C lcd(0x27, 16, 2);
Servo talanquera;
Servo agujaPesaje;
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
unsigned long tBarraAbierta = 0;

// ===== AGUJA: solo dos posiciones =====
const int AGUJA_ABAJO  = 0;    // cerrada, bloquea el paso  (posicion por defecto)
const int AGUJA_ARRIBA = 90;   // abierta, deja pasar

// ===== TIEMPOS =====
const unsigned long RETARDO_PESAJE   = 10000;  // 10 s tras abrir la garita
const unsigned long T_AGUJA_ABIERTA  = 8000;   // cuanto se queda arriba
const unsigned long T_RECHAZO        = 10000;  // cuanto dura el rechazo
const unsigned long TIMEOUT_BARRA    = 20000;  // cierre forzado de la talanquera

// ===== MAQUINA DE ESTADOS DEL PESAJE =====
enum FasePesaje { P_INACTIVO, P_CUENTA_ATRAS, P_ABIERTA, P_RECHAZADO };
FasePesaje fasePesaje = P_INACTIVO;
unsigned long tPesaje = 0;
bool pesoFueraEnPesaje = false;
String uidEnPesaje = "";
String opEnPesaje = "";

// ── Validacion de acceso en el SERVIDOR (sec. 12, fase 1 del plan) ──
// La garita ya no decide con una tabla local: manda evento=rfid y espera
// AbrirTalanquera (con el mismo uid) o RechazarIngreso (con el motivo para el
// LCD). Si no llega respuesta a tiempo, rechaza localmente "Sin respuesta".
bool esperandoServidor = false;
String uidPendiente = "";
unsigned long tEsperaMs = 0;
const unsigned long TIMEOUT_SERVIDOR_MS = 5000;

// ===== BASCULA SIMULADA =====
// No hay bascula real: esta tarjeta simula un peso fuera de tolerancia
// (la aguja NO se abre y el servidor genera RT01).
const char* const UID_PESO_FUERA = "E1 8E 3C 53";

void setup() {
  Serial.begin(9600);
  Serial.setTimeout(20);
  commSalida.begin(9600);

  pinMode(PIN_IR_ANTES, INPUT);
  pinMode(PIN_IR_DESPUES, INPUT);
  pinMode(PIN_LED_ROJO, OUTPUT);
  pinMode(PIN_LED_AMARILLO, OUTPUT);
  pinMode(PIN_LED_VERDE, OUTPUT);

  pinMode(PIN_FLECHA_VERDE, OUTPUT);
  pinMode(PIN_FLECHA_AMBAR, OUTPUT);
  flechas(false, false);

  lcd.init();
  lcd.backlight();

  talanquera.attach(PIN_SERVO);
  talanquera.write(BARRA_ABAJO);

  agujaPesaje.attach(PIN_AGUJA);
  agujaPesaje.write(AGUJA_ABAJO);     // arranca cerrada

  SPI.begin();
  mfrc522.PCD_Init();
  delay(4);
  mfrc522.PCD_DumpVersionToSerial();

  semaforoRojo();
  mostrarEspera();

  Serial.println(F("=== Garita ENTRADA + Pesaje lista ==="));
  sendFrame("EVT", "garita", F("estado=iniciando;garita=entrada"));
}

void loop() {
  procesarComandosRemotos();
  actualizarModoDegradado();
  actualizarPesaje();        // corre siempre, no bloquea

  if (millis() - lastHeartbeatMs >= 5000) {
    lastHeartbeatMs = millis();
    sendFrame("HBT", "estado", String(F("garita=entrada;barra=")) + (barraAbierta ? "abierta" : "cerrada") +
              ";pesaje=" + nombreFasePesaje() + ";degradado=" + (modoDegradado ? "1" : "0"));
  }

  if (mostrandoRechazo) {
    if (millis() - tRechazoMs >= DURACION_MENSAJE_RECHAZO_MS) {
      mostrandoRechazo = false;
      mostrarReposo();
    }
    return;  // sigue mostrando el mensaje; no lee una tarjeta nueva todavia
  }

  if (esperandoServidor) {
    if (millis() - tEsperaMs >= TIMEOUT_SERVIDOR_MS) {
      esperandoServidor = false;
      rechazar(uidPendiente, F("Sin respuesta"), true);
    }
    return;  // mientras el servidor decide no se lee otra tarjeta
  }

  if (!barraAbierta) {
    // Un solo vehiculo a la vez en la zona de pesaje: si el anterior todavia
    // no termina, la siguiente tarjeta espera (no se lee) en vez de pisar
    // los datos del pesaje en curso y reiniciar la cuenta de 10 s del anterior.
    if (fasePesaje != P_INACTIVO) return;

    if (!mfrc522.PICC_IsNewCardPresent()) return;
    if (!mfrc522.PICC_ReadCardSerial())   return;

    semaforoAmarillo();
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print(F("Validando..."));

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
    sendFrame("EVT", "garita", String(F("evento=rfid;uid=")) + uid);

    mfrc522.PICC_HaltA();

    if (modoDegradado) {
      // Sec. 12.1.3: sin servidor se rechaza todo ingreso nuevo.
      rechazar(uid, F("Modo degradado"), true);
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

    // cierre normal: el camion paso completo
    if (llegoAlDespues && !hayAntes && !hayDespues) {
      cerrarBarra(F("Barra ENTRADA ABAJO"), F("barra_abajo"));
    }
    // cierre forzado: pasaron 20 s sin detectar el paso
    else if (millis() - tBarraAbierta >= TIMEOUT_BARRA) {
      cerrarBarra(F("Barra ABAJO por tiempo"), F("barra_abajo_timeout"));
    }
  }
}

void cerrarBarra(const __FlashStringHelper* msg, const __FlashStringHelper* evento) {
  talanquera.write(BARRA_ABAJO);
  barraAbierta = false;
  llegoAlDespues = false;
  semaforoRojo();
  if (fasePesaje == P_INACTIVO) mostrarReposo();
  else if (fasePesaje == P_CUENTA_ATRAS) mostrarLCD(F("Garita entrada"), F("Espere pesaje"));
  Serial.println(msg);
  sendFrame("EVT", "garita", String(F("evento=")) + evento + F(";garita=entrada"));
}

// ════════════════════════════════════════════════
//  PESAJE - la aguja esta ABAJO por defecto
// ════════════════════════════════════════════════
void actualizarPesaje() {

  switch (fasePesaje) {

    case P_INACTIVO:
      break;

    // ── 10 s entre la garita y el pesaje ──
    case P_CUENTA_ATRAS:
      if (millis() - tPesaje >= RETARDO_PESAJE) {
        Serial.println(F("\n[PESAJE] Meseta detectada"));

        if (!pesoFueraEnPesaje) {
          agujaPesaje.write(AGUJA_ARRIBA);
          flechas(true, false);
          Serial.println(F("[PESAJE] Peso dentro de tolerancia"));
          Serial.println(F("[PESAJE] APROBADO -> AGUJA ARRIBA, flecha verde"));
          mostrarLCD(F("PESAJE OK"), F("Puede avanzar"));
          sendFrame("EVT", "pesaje", String(F("evento=meseta;resultado=ok;uid=")) + uidEnPesaje +
                    ";op=" + opEnPesaje + ";aguja=abierta");
          irAPesaje(P_ABIERTA);
        } else {
          agujaPesaje.write(AGUJA_ABAJO);     // se queda cerrada
          flechas(false, true);
          Serial.println(F("[PESAJE] RT01 discrepancia de peso"));
          Serial.println(F("[PESAJE] RECHAZADO -> AGUJA CERRADA, flecha ambar"));
          mostrarLCD(F("RT01 RECHAZADO"), F("Peso incorrecto"));
          sendFrame("EVT", "pesaje", String(F("evento=meseta;resultado=fuera_tolerancia;causa=RT01;uid=")) + uidEnPesaje +
                    ";op=" + opEnPesaje + ";aguja=cerrada");
          irAPesaje(P_RECHAZADO);
        }
      }
      break;

    // ── Aguja arriba, despues vuelve a cerrar ──
    case P_ABIERTA:
      if (millis() - tPesaje >= T_AGUJA_ABIERTA) {
        agujaPesaje.write(AGUJA_ABAJO);
        flechas(false, false);
        Serial.println(F("[PESAJE] AGUJA ABAJO - lista para el siguiente\n"));
        sendFrame("EVT", "pesaje", String(F("evento=aguja_abajo;uid=")) + uidEnPesaje);
        terminarPesaje();
      }
      break;

    // ── Rechazado: se mantiene cerrada ──
    case P_RECHAZADO:
      if (millis() - tPesaje >= T_RECHAZO) {
        flechas(false, false);
        Serial.println(F("[PESAJE] Fin del rechazo - aguja sigue ABAJO\n"));
        sendFrame("EVT", "pesaje", String(F("evento=fin_rechazo;uid=")) + uidEnPesaje);
        terminarPesaje();
      }
      break;
  }
}

void irAPesaje(FasePesaje f) {
  fasePesaje = f;
  tPesaje = millis();
}

void terminarPesaje() {
  irAPesaje(P_INACTIVO);
  pesoFueraEnPesaje = false;
  uidEnPesaje = "";
  opEnPesaje = "";
  if (!barraAbierta && !mostrandoRechazo) mostrarReposo();
}

const char* nombreFasePesaje() {
  switch (fasePesaje) {
    case P_CUENTA_ATRAS: return "en_camino";
    case P_ABIERTA:      return "aprobado";
    case P_RECHAZADO:    return "rechazado";
    default:             return "libre";
  }
}

void flechas(bool verde, bool ambar) {
  digitalWrite(PIN_FLECHA_VERDE, verde ? HIGH : LOW);
  digitalWrite(PIN_FLECHA_AMBAR, ambar ? HIGH : LOW);
}

void mostrarLCD(String l1, String l2) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(l1);
  lcd.setCursor(0, 1);
  lcd.print(l2);
}

// ════════════════════════════════════════════════
//  PROTOCOLO SERIAL PORTUS
// ════════════════════════════════════════════════
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
  Serial.flush();
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

// Valor de "clave=" dentro de un payload "a=1;b=2" ("" si no esta).
String paramValor(const String& payload, const char* clave) {
  String k = String(";") + clave + "=";
  int i = payload.indexOf(k);
  if (i < 0) return "";
  int ini = i + k.length();
  int fin = payload.indexOf(';', ini);
  return fin < 0 ? payload.substring(ini) : payload.substring(ini, fin);
}

bool hayVehiculoDebajoTalanquera() {
  return digitalRead(PIN_IR_ANTES) == LOW || digitalRead(PIN_IR_DESPUES) == LOW;
}

void handleCommand(const String& payload) {
  if (payload.indexOf("target=UNO_ENTRADA") < 0) return;

  if (payload.indexOf("name=AbrirTalanquera") >= 0) {
    // Respuesta del servidor a la tarjeta que se esta validando: el vehiculo
    // esta frente a la barrera, asi que no aplica el chequeo de "debajo".
    String uid = paramValor(payload, "uid");
    if (esperandoServidor && uid == uidPendiente) {
      esperandoServidor = false;
      autorizar(uid, paramValor(payload, "op"));
      sendFrame("ACK", "cmd", F("name=AbrirTalanquera"));
      return;
    }
    if (uid.length()) {
      // Autorizacion que llego tarde (ya se rechazo por "Sin respuesta"): no abrir.
      sendFrame("REJ", "cmd", F("name=AbrirTalanquera;causa=sin_validacion_pendiente"));
      return;
    }
    // Sin uid: apertura manual desde la terminal.
    if (hayVehiculoDebajoTalanquera()) {
      sendFrame("REJ", "cmd", F("name=AbrirTalanquera;causa=vehiculo_bajo_talanquera"));
      return;
    }
    talanquera.write(BARRA_ARRIBA);
    barraAbierta = true;
    llegoAlDespues = false;
    tBarraAbierta = millis();
    semaforoVerde();
    sendFrame("ACK", "cmd", F("name=AbrirTalanquera"));
    return;
  }

  if (payload.indexOf("name=CerrarTalanquera") >= 0) {
    if (hayVehiculoDebajoTalanquera()) {
      sendFrame("REJ", "cmd", F("name=CerrarTalanquera;causa=vehiculo_bajo_talanquera"));
      return;
    }
    talanquera.write(BARRA_ABAJO);
    barraAbierta = false;
    semaforoRojo();
    sendFrame("ACK", "cmd", F("name=CerrarTalanquera"));
    return;
  }

  if (payload.indexOf("name=RechazarIngreso") >= 0) {
    String uid = paramValor(payload, "uid");
    if (!esperandoServidor || uid != uidPendiente) {
      sendFrame("REJ", "cmd", F("name=RechazarIngreso;causa=sin_validacion_pendiente"));
      return;
    }
    esperandoServidor = false;
    String motivo = paramValor(payload, "motivo");
    rechazar(uid, motivo.length() ? motivo : String(F("No autorizado")), false);
    sendFrame("ACK", "cmd", F("name=RechazarIngreso"));
    return;
  }

  sendFrame("REJ", "cmd", F("name=UNKNOWN;causa=comando_no_soportado"));
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
  bool antes = modoDegradado;
  modoDegradado = (millis() - ultimaActividadPiMs) > UMBRAL_DEGRADADO_MS;
  if (antes != modoDegradado && !barraAbierta && !mostrandoRechazo && fasePesaje == P_INACTIVO) {
    mostrarReposo();
  }
}

// ════════════════════════════════════════════════
//  GARITA
// ════════════════════════════════════════════════
// local=true: lo decidio la garita (degradado / sin respuesta) y el servidor
// debe registrar el intento; local=false: el servidor ya lo registro.
void rechazar(const String& uid, const String& motivo, bool local) {
  semaforoRojo();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(F("RECHAZADO"));
  lcd.setCursor(0, 1);
  lcd.print(motivo);

  Serial.print(F("RECHAZADO: "));
  Serial.println(motivo);
  sendFrame("EVT", "garita", String(F("evento=rechazado;motivo=")) + motivo + F(";uid=") + uid +
            F(";decision=") + (local ? F("local") : F("servidor")));
  // Antes: delay(2500) bloqueaba heartbeat/comandos/sensores/pesaje por 2.5s
  // (ver Observaciones_Firmware_PersonaA.md, punto 7). Ahora el mensaje se
  // muestra sin bloquear y loop() lo retira solo tras DURACION_MENSAJE_RECHAZO_MS.
  mostrandoRechazo = true;
  tRechazoMs = millis();
}

void autorizar(const String& uid, const String& op) {
  Serial.print(F("AUTORIZADO por servidor - "));
  Serial.print(uid);
  Serial.print(F(" - "));
  Serial.println(op);

  commSalida.print("ENTRO:");
  commSalida.println(uid);
  sendFrame("EVT", "garita", String(F("evento=autorizado;uid=")) + uid + ";op=" + op);

  talanquera.write(BARRA_ARRIBA);
  barraAbierta   = true;
  llegoAlDespues = false;
  tBarraAbierta  = millis();

  semaforoVerde();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(F("AUTORIZADO"));
  lcd.setCursor(0, 1);
  lcd.print(op);

  pesoFueraEnPesaje = uid.equals(UID_PESO_FUERA);
  uidEnPesaje = uid;
  opEnPesaje = op;
  irAPesaje(P_CUENTA_ATRAS);
  Serial.println(F("[PESAJE] Vehiculo en camino, 10 s..."));
  sendFrame("EVT", "pesaje", String(F("evento=en_camino;uid=")) + uid + ";segundos=10");
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

void mostrarReposo() {
  if (modoDegradado) mostrarDegradado();
  else mostrarEspera();
}

void mostrarEspera() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(F("Garita entrada"));
  lcd.setCursor(0, 1);
  lcd.print(F("Acerca tarjeta"));
}

void mostrarDegradado() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(F("MODO DEGRADADO"));
  lcd.setCursor(0, 1);
  lcd.print(F("Sin enlace a Pi"));
}
