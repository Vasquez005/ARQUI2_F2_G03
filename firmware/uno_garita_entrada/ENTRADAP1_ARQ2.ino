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
int camionEnPesaje = -1;

const int NUM_CAMIONES = 4;

String camionesRegistrados[NUM_CAMIONES] = {
  "E1 69 73 15",
  "E1 67 7F 15",
  "90 C7 3D 5F",
  "E1 8E 3C 53"
};

bool camionAutorizado[NUM_CAMIONES] = {
  true,
  true,
  false,     // rechazada en la GARITA
  true
};

String manifiestoOperacion[NUM_CAMIONES] = {
  "DEPOSITO",
  "RETIRO",
  "DEPOSITO",
  "DEPOSITO"
};

// ===== Cual se rechaza EN EL PESAJE =====
bool rechazarEnPesaje[NUM_CAMIONES] = {
  false,
  false,
  false,
  true       // pasa la garita pero la aguja NO se abre
};


void setup() {
  Serial.begin(9600);
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
}


void loop() {

  actualizarPesaje();        // corre siempre, no bloquea

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

    int idx = buscarCamion(uid);

    if (idx == -1)                        { rechazar("RFID no reconoc"); return; }
    if (!camionAutorizado[idx])           { rechazar("No autorizado");   return; }
    if (manifiestoOperacion[idx] == "")   { rechazar("Sin manifiesto");  return; }
    if (manifiestoOperacion[idx] != "DEPOSITO" &&
        manifiestoOperacion[idx] != "RETIRO") { rechazar("Op invalida"); return; }

    autorizar(idx, uid);
  }

  else {
    bool hayAntes   = (digitalRead(PIN_IR_ANTES)   == LOW);
    bool hayDespues = (digitalRead(PIN_IR_DESPUES) == LOW);

    if (hayDespues) llegoAlDespues = true;

    // cierre normal: el camion paso completo
    if (llegoAlDespues && !hayAntes && !hayDespues) {
      cerrarBarra("Barra ENTRADA ABAJO");
    }
    // cierre forzado: pasaron 20 s sin detectar el paso
    else if (millis() - tBarraAbierta >= TIMEOUT_BARRA) {
      cerrarBarra("Barra ABAJO por tiempo");
    }
  }
}


void cerrarBarra(const char* msg) {
  talanquera.write(BARRA_ABAJO);
  barraAbierta = false;
  llegoAlDespues = false;
  semaforoRojo();
  mostrarEspera();
  Serial.println(msg);
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

        if (!rechazarEnPesaje[camionEnPesaje]) {
          agujaPesaje.write(AGUJA_ARRIBA);
          flechas(true, false);
          Serial.println(F("[PESAJE] Peso dentro de tolerancia"));
          Serial.println(F("[PESAJE] APROBADO -> AGUJA ARRIBA, flecha verde"));
          mostrarLCD("PESAJE OK", "Puede avanzar");
          irAPesaje(P_ABIERTA);
        } else {
          agujaPesaje.write(AGUJA_ABAJO);     // se queda cerrada
          flechas(false, true);
          Serial.println(F("[PESAJE] RT01 discrepancia de peso"));
          Serial.println(F("[PESAJE] RECHAZADO -> AGUJA CERRADA, flecha ambar"));
          mostrarLCD("RT01 RECHAZADO", "Peso incorrecto");
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
        if (!barraAbierta) mostrarEspera();
        irAPesaje(P_INACTIVO);
      }
      break;

    // ── Rechazado: se mantiene cerrada ──
    case P_RECHAZADO:
      if (millis() - tPesaje >= T_RECHAZO) {
        flechas(false, false);
        Serial.println(F("[PESAJE] Fin del rechazo - aguja sigue ABAJO\n"));
        if (!barraAbierta) mostrarEspera();
        irAPesaje(P_INACTIVO);
      }
      break;
  }
}

void irAPesaje(FasePesaje f) {
  fasePesaje = f;
  tPesaje = millis();
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
//  GARITA
// ════════════════════════════════════════════════
int buscarCamion(String uid) {
  for (int i = 0; i < NUM_CAMIONES; i++) {
    if (camionesRegistrados[i] == uid) return i;
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

  mfrc522.PICC_HaltA();
  delay(2500);
  mostrarEspera();
}

void autorizar(int idx, String uid) {
  Serial.print(F("AUTORIZADO - Camion "));
  Serial.print(idx + 1);
  Serial.print(F(" - "));
  Serial.println(manifiestoOperacion[idx]);

  commSalida.print("ENTRO:");
  commSalida.println(uid);

  talanquera.write(BARRA_ARRIBA);
  barraAbierta   = true;
  llegoAlDespues = false;
  tBarraAbierta  = millis();

  semaforoVerde();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("AUTORIZADO");
  lcd.setCursor(0, 1);
  lcd.print(manifiestoOperacion[idx]);

  mfrc522.PICC_HaltA();

  camionEnPesaje = idx;
  irAPesaje(P_CUENTA_ATRAS);
  Serial.println(F("[PESAJE] Vehiculo en camino, 10 s..."));
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
