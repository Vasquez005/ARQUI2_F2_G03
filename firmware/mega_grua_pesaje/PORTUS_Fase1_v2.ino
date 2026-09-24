/*
 * PORTUS - Fase 1 | Grua/Patio (sin pesaje)
 * Arduino Mega 2560
 *
 * COMANDOS SERIAL (115200):
 *   P0 / HOME  -> regresar grua a transferencia
 *   RESET      -> releer patio desde sensores
 *   RETIRO     -> modo retiro (toma primera celda ocupada)
 *   DEPOSITO   -> modo deposito (toma camion y busca primera celda libre)
 */

#include <Stepper.h>

// ════════════════════════════════════════════════════════════════════════════
//  PINES
// ════════════════════════════════════════════════════════════════════════════

// --- GRUA ---
const int PIN_ELECTROIMAN = 30;
const int PIN_IR_CELDA[4] = {31, 32, 33, 34};
const int PIN_OPTICO      = 35;
const int PIN_US_TRIG     = 36;
const int PIN_US_ECHO     = 37;

// --- Semaforo de transferencia ---
const int PIN_LED_SEMAFORO_ROJO     = 47;
const int PIN_LED_SEMAFORO_AMARILLO = 48;
const int PIN_LED_SEMAFORO_VERDE    = 49;

// --- LEDs por celda ---
const int PIN_LED_CELDA_LIBRE[4]   = {22, 25, 28, 44};  // P1..P4
const int PIN_LED_CELDA_OCUPADA[4] = {23, 26, 29, 45};  // P1..P4

bool esDeposito = true;


// ════════════════════════════════════════════════════════════════════════════
//  CALIBRACION Y PARAMETROS - GRUA
// ════════════════════════════════════════════════════════════════════════════
const int   PASOS_POR_REVOLUCION      = 2048;
const long  PASOS_BAJADA_ORIGEN       = 2560;
const long  PASOS_SUBIDA_SEGURA       = 2560;
const long  PASOS_BAJADA_DESTINO      = 2560;
const int   VELOCIDAD_MOTORES         = 12;
const int   DISTANCIA_CAMION_CM       = 15;
const unsigned long INTERVALO_US_MS   = 150;
const unsigned long INTERVALO_PATIO_MS = 500;
const unsigned long INTERVALO_STEP_US  = 2500;
const unsigned long TIEMPO_IMAN_MS    = 800;
const unsigned long TIEMPO_CAMION_ESTABLE_MS = 400;
const unsigned long TIEMPO_CAMION_AUSENTE_MS = 600;
const unsigned long DEBOUNCE_MARCA_MS = 40;
const long  PASOS_MAX_SIN_MARCA       = 12000;
const long  PASOS_MAX_REFERENCIA      = 15000;
const bool  ARRANQUE_MANUAL_EN_P0     = true;
const bool  RECUPERAR_A_P0_EN_FALLO   = true;

bool irOcupadoEnHigh = true;

Stepper motorHorizontal(PASOS_POR_REVOLUCION, 8, 10, 9, 11);
Stepper motorVertical  (PASOS_POR_REVOLUCION, 4, 6, 5, 7);
const char* SRC_PORTUS = "MEGA_GRUA";


// ════════════════════════════════════════════════════════════════════════════
//  TIPOS
// ════════════════════════════════════════════════════════════════════════════
enum EstadoCelda { LIBRE, RESERVADA, OCUPADA, BLOQUEADA };

enum EstadoGrua {
  ST_REFERENCIANDO, ST_ESPERANDO_CAMION, ST_REVISANDO_PATIO,
  ST_BAJANDO_ORIGEN, ST_ACTIVANDO_IMAN, ST_SUBIENDO_CARGA,
  ST_MOVIENDO_DESTINO, ST_BAJANDO_DESTINO, ST_LIBERANDO_CARGA,
  ST_VERIFICANDO_DEPOSITO, ST_SUBIENDO_CABEZAL, ST_REGRESANDO_P0,
  ST_FINALIZADO, ST_ERROR
};

enum CodigoError {
  ERR_NINGUNO, ERR_SIN_REFERENCIA, ERR_SIN_MARCA,
  ERR_DEPOSITO, ERR_CAMION_MOVIDO, ERR_PATIO_LLENO
};


// ════════════════════════════════════════════════════════════════════════════
//  ESTADO - GRUA
// ════════════════════════════════════════════════════════════════════════════
EstadoGrua  estadoGrua  = ST_REFERENCIANDO;
CodigoError ultimoError = ERR_NINGUNO;
EstadoCelda estadoPatio[4];

int  posicionActual  = -1;
int  posicionDestino = 0;
bool referenciada      = false;
bool alturaSegura      = false;
bool electroimanActivo = false;
bool camionPresente    = false;
bool camionEstable     = false;
bool moviendoHaciaP0   = false;
bool optSobreMarca     = false;
bool refBuscandoP0     = false;
bool cicloCamionArmado = false;
bool patioRechazadoEsteCamion = false;
bool necesitaHomingP0  = false;
bool regresoPostDeposito = false;
bool retiroTomandoDesdePatio = false;
bool omitirPrimeraMarcaRetorno = false;
bool gruaSuspendidaRemota = false;
bool modoMantenimientoRemoto = false;
int  posicionOrigenRetiro = 0;

bool vertActivo   = false;
bool vertSubiendo = false;
long vertObjetivo = 0;
long vertHechos   = 0;

bool horizActivo   = false;
long pasosSinMarca = 0;

unsigned long ultimoStepUs    = 0;
unsigned long ultimoUsMs      = 0;
unsigned long ultimoPatioMs   = 0;
unsigned long faseInicioMs    = 0;
unsigned long camionOkDesdeMs = 0;
unsigned long camionAusenteDesdeMs = 0;
unsigned long ultimoParpadeoSemaforoMs = 0;
bool semaforoParpadeoOn = false;
unsigned long ultimoParpadeoReservaMs = 0;
bool parpadeoReservaOn = false;
unsigned long ultimoHeartbeatPortusMs = 0;
long txSeqPortus = 1;

int           optLectura  = HIGH;
int           optEstable  = HIGH;
unsigned long optCambioMs = 0;


// ════════════════════════════════════════════════════════════════════════════
//  DECLARACIONES
// ════════════════════════════════════════════════════════════════════════════
void apagarBobinas();
void cambiarEstado(EstadoGrua s);
void detenerTodo();
void abortarOperacion(CodigoError e);
bool tickMotorListo();
int  posicionTrasMarca(int pos, bool haciaP0);
bool requiereCamion();
long medirDistanciaCm();
void actualizarCamion();
void actualizarMarcaOptica();
void sincronizarPatioFisico();
void imprimirPatio();
void inicializarPatioDesdeSensores();
int  buscarPrimeraCeldaLibre();
int  buscarPrimeraCeldaOcupada();
void reservarCelda(int p);
void liberarReserva(int p);
bool confirmarDepositoFisico(int p);
bool celdaFisicamenteOcupada(int p);
const char* nombreEstadoCelda(EstadoCelda e);
void activarElectroiman();
void desactivarElectroiman();
void iniciarMovimientoVertical(bool subir, long pasos);
void actualizarMovimientoVertical();
void iniciarMovimientoHorizontal(bool haciaP0);
void actualizarMovimientoHorizontal();
void detenerHorizontal();
void ejecutarEstadoGrua();
void procesarComandoSerial();
void autoDetectarPolaridadIR();
void reiniciarPatioLogicoDesdeSensores();
void iniciarRegresoP0();
void procesarComandosPortus();
void emitirHeartbeatPortus();
void emitirEventoGruaPortus(const char* evt);
void responderCmdPortus(bool ok, const String& name, const String& extra);
bool parseFramePortus(String line, String& src, long& seq, String& kind, String& topic, String& payload);
String framePortus(const String& kind, const String& topic, const String& payload, long seq);
String checksumPortus(const String& base);
String hex2Portus(uint8_t v);
String fieldPortus(const String& payload, const String& key);
void handleCmdPortus(const String& payload);
void inicializarLedsEstado();
void actualizarLedsSemaforo();
void actualizarLedsCeldas();
void actualizarLedsEstado();


// ════════════════════════════════════════════════════════════════════════════
//  SETUP
// ════════════════════════════════════════════════════════════════════════════
void setup() {
<<<<<<< HEAD
  Serial.begin(115200);
  Serial.setTimeout(50);
=======
  Serial.begin(9600);
  Serial.setTimeout(50);            // evita bloqueo en readStringUntil

  // --- Pesaje: DT como entrada CON PULLUP, SCK como salida (PORTB) ---
  // El pullup es obligatorio: el HX711 deja DT en alta impedancia mientras
  // convierte, y sin resistencia el pin flota y se lee como LOW permanente.
  DDRB  &= ~(BIT_DT_A | BIT_DT_B);
  PORTB |=  (BIT_DT_A | BIT_DT_B);   // <<< PULLUP INTERNO
  DDRB  |=   BIT_SCK;
  PORTB &=  ~BIT_SCK;

  pinMode(PIN_LED_VERDE, OUTPUT);
  pinMode(PIN_LED_AMBAR, OUTPUT);
  digitalWrite(PIN_LED_VERDE, LOW);
  digitalWrite(PIN_LED_AMBAR, LOW);

  aguja.attach(PIN_AGUJA);
  aguja.write(AGUJA_ABIERTA);       // default: paso libre (fail-safe)
>>>>>>> 1348ba4f1a40eb2667a17f9fe0263de328e7cd50

  // --- Grua ---
  motorHorizontal.setSpeed(VELOCIDAD_MOTORES);
  motorVertical.setSpeed(VELOCIDAD_MOTORES);

  pinMode(PIN_ELECTROIMAN, OUTPUT);
  digitalWrite(PIN_ELECTROIMAN, LOW);

  for (int i = 0; i < 4; i++) pinMode(PIN_IR_CELDA[i], INPUT_PULLUP);
  pinMode(PIN_OPTICO, INPUT);
  pinMode(PIN_US_TRIG, OUTPUT);
  pinMode(PIN_US_ECHO, INPUT);
  digitalWrite(PIN_US_TRIG, LOW);
  inicializarLedsEstado();

  Serial.println(F("=== PORTUS Fase 1 - Grua + Patio (sin pesaje) ==="));
  Serial.println(F("Riel: P1-P2-P3-P4-P0"));

  autoDetectarPolaridadIR();
  inicializarPatioDesdeSensores();
  imprimirPatio();

  optLectura  = digitalRead(PIN_OPTICO);
  optEstable  = optLectura;
  optCambioMs = millis();

  if (ARRANQUE_MANUAL_EN_P0 && digitalRead(PIN_OPTICO) == LOW) {
    posicionActual = 0;
    referenciada   = true;
    optSobreMarca  = true;
    Serial.println(F("[OK] Arranque manual: marca actual asumida como P0."));
  } else {
    posicionActual = -1;
    referenciada   = false;
    refBuscandoP0  = true;
    Serial.println(F("Referenciando: buscando marca P0..."));
  }

  necesitaHomingP0 = (posicionActual != 0);
  if (necesitaHomingP0) {
    Serial.println(F("[AVISO] Grua no en P0. Regresando..."));
    alturaSegura = true;
    cambiarEstado(ST_REGRESANDO_P0);
  } else {
    cambiarEstado(ST_ESPERANDO_CAMION);
  }

  Serial.println(F("Comandos: P0 | RESET | RETIRO | DEPOSITO"));
  Serial.println(framePortus("EVT", "grua", "evt=inicio;estado=boot", txSeqPortus++));
}


// ════════════════════════════════════════════════════════════════════════════
//  LOOP
// ════════════════════════════════════════════════════════════════════════════
void loop() {
  procesarComandosPortus();
  emitirHeartbeatPortus();
  procesarComandoSerial();
  actualizarCamion();
  actualizarLedsEstado();

  if (millis() - ultimoPatioMs >= INTERVALO_PATIO_MS) {
    sincronizarPatioFisico();
    imprimirPatio();
  }

  if (requiereCamion() && !camionEstable) {
    abortarOperacion(ERR_CAMION_MOVIDO);
    return;
  }

  actualizarMarcaOptica();

  if (vertActivo)  actualizarMovimientoVertical();
  if (horizActivo) actualizarMovimientoHorizontal();

  ejecutarEstadoGrua();
}


// ════════════════════════════════════════════════════════════════════════════
//  LEDs
// ════════════════════════════════════════════════════════════════════════════
void inicializarLedsEstado() {
  pinMode(PIN_LED_SEMAFORO_ROJO, OUTPUT);
  pinMode(PIN_LED_SEMAFORO_AMARILLO, OUTPUT);
  pinMode(PIN_LED_SEMAFORO_VERDE, OUTPUT);
  digitalWrite(PIN_LED_SEMAFORO_ROJO, LOW);
  digitalWrite(PIN_LED_SEMAFORO_AMARILLO, LOW);
  digitalWrite(PIN_LED_SEMAFORO_VERDE, LOW);

  for (int i = 0; i < 4; i++) {
    pinMode(PIN_LED_CELDA_LIBRE[i], OUTPUT);
    pinMode(PIN_LED_CELDA_OCUPADA[i], OUTPUT);
    digitalWrite(PIN_LED_CELDA_LIBRE[i], LOW);
    digitalWrite(PIN_LED_CELDA_OCUPADA[i], LOW);
  }
}

void actualizarLedsSemaforo() {
  bool rojo = false, amarillo = false, verde = false;

  if (estadoGrua == ST_ERROR) {
    if (millis() - ultimoParpadeoSemaforoMs >= 350) {
      ultimoParpadeoSemaforoMs = millis();
      semaforoParpadeoOn = !semaforoParpadeoOn;
    }
    rojo = semaforoParpadeoOn;
  } else if (estadoGrua == ST_ESPERANDO_CAMION) {
    verde = true;
    semaforoParpadeoOn = false;
  } else if (estadoGrua == ST_REVISANDO_PATIO || estadoGrua == ST_FINALIZADO) {
    amarillo = true;
    semaforoParpadeoOn = false;
  } else {
    rojo = true;
    semaforoParpadeoOn = false;
  }

  digitalWrite(PIN_LED_SEMAFORO_ROJO, rojo ? HIGH : LOW);
  digitalWrite(PIN_LED_SEMAFORO_AMARILLO, amarillo ? HIGH : LOW);
  digitalWrite(PIN_LED_SEMAFORO_VERDE, verde ? HIGH : LOW);
}

void actualizarLedsCeldas() {
  if (millis() - ultimoParpadeoReservaMs >= 350) {
    ultimoParpadeoReservaMs = millis();
    parpadeoReservaOn = !parpadeoReservaOn;
  }

  // En arranque/reposo: mostrar estado fisico puro (sin parpadeo de reserva).
  // El parpadeo solo debe aparecer cuando la grua ya esta en ciclo activo.
  bool cicloGruaActivo =
      (estadoGrua == ST_REVISANDO_PATIO)   ||
      (estadoGrua == ST_BAJANDO_ORIGEN)    ||
      (estadoGrua == ST_ACTIVANDO_IMAN)    ||
      (estadoGrua == ST_SUBIENDO_CARGA)    ||
      (estadoGrua == ST_MOVIENDO_DESTINO)  ||
      (estadoGrua == ST_BAJANDO_DESTINO)   ||
      (estadoGrua == ST_LIBERANDO_CARGA)   ||
      (estadoGrua == ST_VERIFICANDO_DEPOSITO) ||
      (estadoGrua == ST_SUBIENDO_CABEZAL)  ||
      (estadoGrua == ST_REGRESANDO_P0)     ||
      (estadoGrua == ST_FINALIZADO);

  for (int i = 0; i < 4; i++) {
    bool ledLibre = false, ledOcupado = false;

    if (!cicloGruaActivo) {
      // Inicio/espera: libre=azul fijo, ocupada=rojo fijo, sin parpadeo.
      bool fisicaOcupada = celdaFisicamenteOcupada(i + 1);
      ledLibre = !fisicaOcupada;
      ledOcupado = fisicaOcupada;
    } else {
      // Durante ciclo: aplicar estados logicos de patio (incluye reserva parpadeando).
      switch (estadoPatio[i]) {
        case LIBRE:     ledLibre = true; break;
        case RESERVADA: ledLibre = parpadeoReservaOn; break;
        case OCUPADA:   ledOcupado = true; break;
        case BLOQUEADA: ledOcupado = true; ledLibre = parpadeoReservaOn; break;
      }
    }

    digitalWrite(PIN_LED_CELDA_LIBRE[i], ledLibre ? HIGH : LOW);
    digitalWrite(PIN_LED_CELDA_OCUPADA[i], ledOcupado ? HIGH : LOW);
  }
}

void actualizarLedsEstado() {
  actualizarLedsSemaforo();
  actualizarLedsCeldas();
}

// ════════════════════════════════════════════════════════════════════════════
//  PROTOCOLO PORTUS (Serial <-> Raspberry)
// ════════════════════════════════════════════════════════════════════════════
String hex2Portus(uint8_t v) {
  const char* h = "0123456789ABCDEF";
  String s = "";
  s += h[(v >> 4) & 0xF];
  s += h[v & 0xF];
  return s;
}

String checksumPortus(const String& base) {
  uint16_t sum = 0;
  for (size_t i = 0; i < base.length(); i++) sum += (uint8_t)base[i];
  return hex2Portus((uint8_t)(sum % 256));
}

String framePortus(const String& kind, const String& topic, const String& payload, long seq) {
  String base = "PORTUS|" + String(SRC_PORTUS) + "|" + String(seq) + "|" + kind + "|" + topic + "|" + payload;
  return "<" + base + "|" + checksumPortus(base) + ">";
}

bool parseFramePortus(String line, String& src, long& seq, String& kind, String& topic, String& payload) {
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
  return checksumPortus(base) == chk;
}

String fieldPortus(const String& payload, const String& key) {
  String token = key + "=";
  int start = payload.indexOf(token);
  if (start < 0) return "";
  start += token.length();
  int end = payload.indexOf(';', start);
  if (end < 0) end = payload.length();
  return payload.substring(start, end);
}

void responderCmdPortus(bool ok, const String& name, const String& extra) {
  String payload = "name=" + name;
  if (extra.length()) payload += ";" + extra;
  Serial.println(framePortus(ok ? "ACK" : "REJ", "cmd", payload, txSeqPortus++));
}

void emitirHeartbeatPortus() {
  if (millis() - ultimoHeartbeatPortusMs < 5000) return;
  ultimoHeartbeatPortusMs = millis();
  String payload = "estado=" + String((int)estadoGrua) +
                   ";suspendida=" + String(gruaSuspendidaRemota ? "1" : "0") +
                   ";mantenimiento=" + String(modoMantenimientoRemoto ? "1" : "0");
  Serial.println(framePortus("HBT", "estado", payload, txSeqPortus++));
}

void emitirEventoGruaPortus(const char* evt) {
  String payload = "evt=" + String(evt) + ";estado=" + String((int)estadoGrua) + ";pos=" + String(posicionActual);
  Serial.println(framePortus("EVT", "grua", payload, txSeqPortus++));
}

void handleCmdPortus(const String& payload) {
  String target = fieldPortus(payload, "target");
  if (target.length() && target != "MEGA_GRUA") return;

  String name = fieldPortus(payload, "name");
  if (name == "GruaSuspender") {
    gruaSuspendidaRemota = true;
    responderCmdPortus(true, name, "");
    return;
  }
  if (name == "GruaReanudar") {
    if (estadoGrua == ST_ERROR) {
      responderCmdPortus(false, name, "causa=falla_sin_rearme");
      return;
    }
    gruaSuspendidaRemota = false;
    responderCmdPortus(true, name, "");
    return;
  }
  if (name == "GruaReferenciar") {
    if (electroimanActivo || horizActivo || vertActivo) {
      responderCmdPortus(false, name, "causa=carga_o_trabajo_activo");
      return;
    }
    posicionActual = -1;
    referenciada = false;
    refBuscandoP0 = true;
    cambiarEstado(ST_REFERENCIANDO);
    responderCmdPortus(true, name, "");
    return;
  }
  if (name == "ModoMantenimiento") {
    if (horizActivo || vertActivo || estadoGrua == ST_BAJANDO_ORIGEN || estadoGrua == ST_ACTIVANDO_IMAN ||
        estadoGrua == ST_SUBIENDO_CARGA || estadoGrua == ST_MOVIENDO_DESTINO || estadoGrua == ST_BAJANDO_DESTINO) {
      responderCmdPortus(false, name, "causa=trabajo_activo");
      return;
    }
    String valor = fieldPortus(payload, "valor");
    modoMantenimientoRemoto = (valor == "activar");
    responderCmdPortus(true, name, "");
    return;
  }
  if (name == "AgujaRecta") {
    responderCmdPortus(false, name, "causa=pesaje_externo");
    return;
  }
  if (name == "AgujaParqueo" || name == "AgujaLiberar") {
    responderCmdPortus(false, name, "causa=pesaje_externo");
    return;
  }
  if (name == "PosicionBloquear") {
    int p = fieldPortus(payload, "pos").toInt();
    if (p < 1 || p > 4) {
      responderCmdPortus(false, name, "causa=posicion_invalida");
      return;
    }
    if ((horizActivo || vertActivo) && (p == posicionActual || p == posicionDestino)) {
      responderCmdPortus(false, name, "causa=posicion_en_trabajo");
      return;
    }
    estadoPatio[p - 1] = BLOQUEADA;
    responderCmdPortus(true, name, "");
    return;
  }
  if (name == "PosicionLiberar") {
    int p = fieldPortus(payload, "pos").toInt();
    if (p < 1 || p > 4) {
      responderCmdPortus(false, name, "causa=posicion_invalida");
      return;
    }
    if (estadoPatio[p - 1] == BLOQUEADA) estadoPatio[p - 1] = LIBRE;
    responderCmdPortus(true, name, "");
    return;
  }
  if (name == "AlarmaSilenciar") {
    responderCmdPortus(true, name, "");
    return;
  }

  responderCmdPortus(false, name.length() ? name : "UNKNOWN", "causa=comando_no_soportado");
}

void procesarComandosPortus() {
  if (!Serial.available()) return;
  if (Serial.peek() != '<') return;  // ignora consola local no protocolar
  String line = Serial.readStringUntil('\n');
  if (!line.startsWith("<PORTUS|")) return;

  String src, kind, topic, payload;
  long seq = 0;
  if (!parseFramePortus(line, src, seq, kind, topic, payload)) return;
  if (kind == "CMD" && topic == "cmd") handleCmdPortus(payload);
}


// ════════════════════════════════════════════════════════════════════════════
//  CONSOLA SERIAL
// ════════════════════════════════════════════════════════════════════════════
void procesarComandoSerial() {
  if (!Serial.available()) return;
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  cmd.toUpperCase();
  if (cmd.length() == 0) return;

  if (cmd == "P0" || cmd == "0" || cmd == "HOME") {
    Serial.println(F("[CMD] Forzando regreso a P0..."));
    if (digitalRead(PIN_OPTICO) == LOW) {
      posicionActual = 0;
      referenciada   = true;
      optSobreMarca  = true;
      detenerTodo();
      necesitaHomingP0 = false;
      Serial.println(F("[OK] Ya sobre marca P0."));
      cambiarEstado(ST_ESPERANDO_CAMION);
      return;
    }
    posicionActual      = -1;
    referenciada        = false;
    regresoPostDeposito = false;
    iniciarRegresoP0();
  }
  else if (cmd == "RESET") {
    Serial.println(F("[CMD] Releyendo patio desde sensores..."));
    autoDetectarPolaridadIR();
    reiniciarPatioLogicoDesdeSensores();
    patioRechazadoEsteCamion = false;
    imprimirPatio();
  }
  else if (cmd == "RETIRO") {
    esDeposito = false;
    Serial.println(F("[CMD] Modo RETIRO activado."));
  }
  else if (cmd == "DEPOSITO") {
    esDeposito = true;
    Serial.println(F("[CMD] Modo DEPOSITO activado."));
  }
}


void iniciarRegresoP0() {
  detenerTodo();
  desactivarElectroiman();
  posicionDestino   = 0;
  alturaSegura      = true;
  refBuscandoP0     = false;
  cicloCamionArmado = false;
  cambiarEstado(ST_REGRESANDO_P0);
}


// ════════════════════════════════════════════════════════════════════════════
//  MAQUINA DE ESTADOS DE LA GRUA
// ════════════════════════════════════════════════════════════════════════════
void ejecutarEstadoGrua() {
  switch (estadoGrua) {

    case ST_REFERENCIANDO:
      if (referenciada && posicionActual == 0) {
        detenerHorizontal();
        cambiarEstado(ST_ESPERANDO_CAMION);
        break;
      }
      if (!horizActivo) {
        refBuscandoP0 = true;
        iniciarMovimientoHorizontal(true);
      }
      if (pasosSinMarca > PASOS_MAX_REFERENCIA) abortarOperacion(ERR_SIN_REFERENCIA);
      break;

    case ST_ESPERANDO_CAMION:
      if (gruaSuspendidaRemota || modoMantenimientoRemoto) break;
      if (camionAusenteDesdeMs > 0 &&
          millis() - camionAusenteDesdeMs >= TIEMPO_CAMION_AUSENTE_MS) {
        cicloCamionArmado        = false;
        patioRechazadoEsteCamion = false;
        camionAusenteDesdeMs     = 0;
      }
      if (!camionEstable) break;

      if (!cicloCamionArmado && !patioRechazadoEsteCamion) {
        cicloCamionArmado = true;
        Serial.println(F("[OK] Camion detectado en transferencia."));
        reiniciarPatioLogicoDesdeSensores();
        cambiarEstado(ST_REVISANDO_PATIO);
      }
      break;

    case ST_REVISANDO_PATIO:
      if (esDeposito) {
        posicionDestino = buscarPrimeraCeldaLibre();
        if (posicionDestino == 0) {
          Serial.println(F("[ERROR] PATIO SIN POSICIONES DISPONIBLES"));
          Serial.println(F("  Escribe RESET si las celdas estan vacias."));
          ultimoError              = ERR_PATIO_LLENO;
          patioRechazadoEsteCamion = true;
          cicloCamionArmado        = true;
          cambiarEstado(ST_ESPERANDO_CAMION);
        } else {
          reservarCelda(posicionDestino);
          Serial.print(F("[OK] Destino P"));
          Serial.print(posicionDestino);
          Serial.println(F(" RESERVADA"));
          retiroTomandoDesdePatio = false;
          posicionOrigenRetiro = 0;
          alturaSegura = false;
          vertHechos   = 0;
          cambiarEstado(ST_BAJANDO_ORIGEN);
        }
      } else {
        posicionOrigenRetiro = buscarPrimeraCeldaOcupada();
        if (posicionOrigenRetiro == 0) {
          Serial.println(F("[ERROR] RETIRO SIN CELDAS OCUPADAS"));
          ultimoError              = ERR_PATIO_LLENO;
          patioRechazadoEsteCamion = true;
          cicloCamionArmado        = true;
          cambiarEstado(ST_ESPERANDO_CAMION);
        } else {
          reservarCelda(posicionOrigenRetiro);
          posicionDestino = posicionOrigenRetiro;   // Primer tramo: ir a celda ocupada.
          retiroTomandoDesdePatio = true;
          Serial.print(F("[OK] Retiro origen P"));
          Serial.print(posicionOrigenRetiro);
          Serial.println(F(" RESERVADA"));
          cambiarEstado(ST_MOVIENDO_DESTINO);
        }
      }
      break;

    case ST_BAJANDO_ORIGEN:
      if (esDeposito && posicionActual != 0) { abortarOperacion(ERR_SIN_REFERENCIA); break; }
      if (!vertActivo && vertHechos == 0) {
        if (esDeposito) Serial.println(F("Bajando cabezal en P0..."));
        else            Serial.println(F("Bajando cabezal en celda de retiro..."));
        iniciarMovimientoVertical(false, PASOS_BAJADA_ORIGEN);
      }
      if (!vertActivo && vertHechos >= PASOS_BAJADA_ORIGEN) {
        vertHechos = 0;
        cambiarEstado(ST_ACTIVANDO_IMAN);
      }
      break;

    case ST_ACTIVANDO_IMAN:
      if (!electroimanActivo) {
        activarElectroiman();
        faseInicioMs = millis();
        Serial.println(F("Electroiman ON"));
      }
      if (millis() - faseInicioMs >= TIEMPO_IMAN_MS) cambiarEstado(ST_SUBIENDO_CARGA);
      break;

    case ST_SUBIENDO_CARGA:
      if (!vertActivo && !alturaSegura) {
        Serial.println(F("Subiendo a altura segura..."));
        iniciarMovimientoVertical(true, PASOS_SUBIDA_SEGURA);
      }
      if (!vertActivo && alturaSegura) {
        Serial.println(F("[OK] Altura segura alcanzada"));
        if (!esDeposito && retiroTomandoDesdePatio) {
          // Retiro: al terminar la toma en patio, liberar celda origen y volver a P0.
          retiroTomandoDesdePatio = false;
          if (posicionOrigenRetiro >= 1 && posicionOrigenRetiro <= 4) {
            estadoPatio[posicionOrigenRetiro - 1] = LIBRE;
          }
          posicionDestino = 0;
        }
        cambiarEstado(ST_MOVIENDO_DESTINO);
      }
      break;

    case ST_MOVIENDO_DESTINO:
      if (!alturaSegura) {
        if (!vertActivo) {
          Serial.println(F("Subiendo a altura segura para traslado..."));
          iniciarMovimientoVertical(true, PASOS_SUBIDA_SEGURA);
        }
        break;
      }
      if (!horizActivo && posicionActual != posicionDestino) {
        Serial.print(F("Traslado hacia P"));
        Serial.println(posicionDestino);
        // En retiro, cuando ya lleva carga y vuelve a transferencia, destino=0.
        iniciarMovimientoHorizontal(posicionDestino == 0);
      }
      if (!horizActivo && posicionActual == posicionDestino) {
        Serial.print(F("[OK] Posicion destino P"));
        Serial.println(posicionActual);
        vertHechos = 0;
        if (!esDeposito && retiroTomandoDesdePatio) cambiarEstado(ST_BAJANDO_ORIGEN);
        else                                        cambiarEstado(ST_BAJANDO_DESTINO);
      }
      break;

    case ST_BAJANDO_DESTINO:
      if (!vertActivo && vertHechos == 0) {
        Serial.println(F("Bajando para depositar..."));
        alturaSegura = false;
        iniciarMovimientoVertical(false, PASOS_BAJADA_DESTINO);
      }
      if (!vertActivo && vertHechos >= PASOS_BAJADA_DESTINO)
        cambiarEstado(ST_LIBERANDO_CARGA);
      break;

    case ST_LIBERANDO_CARGA:
      if (electroimanActivo) {
        desactivarElectroiman();
        Serial.println(F("Electroiman OFF"));
      }
      faseInicioMs = millis();
      if (!esDeposito && posicionDestino == 0) {
        // Retiro final en transferencia: no existe sensor de celda en P0 para confirmar.
        cambiarEstado(ST_SUBIENDO_CABEZAL);
      } else {
        cambiarEstado(ST_VERIFICANDO_DEPOSITO);
      }
      break;

    case ST_VERIFICANDO_DEPOSITO:
      if (millis() - faseInicioMs >= 200) {
        if (confirmarDepositoFisico(posicionDestino)) {
          Serial.print(F("[OK] Deposito confirmado en P"));
          Serial.println(posicionDestino);
          posicionActual = posicionDestino;
          vertHechos     = 0;
          cambiarEstado(ST_SUBIENDO_CABEZAL);
        } else {
          abortarOperacion(ERR_DEPOSITO);
        }
      }
      break;

    case ST_SUBIENDO_CABEZAL:
      if (!vertActivo && !alturaSegura) {
        Serial.println(F("Subiendo cabezal..."));
        iniciarMovimientoVertical(true, PASOS_SUBIDA_SEGURA);
      }
      if (!vertActivo && alturaSegura) {
        regresoPostDeposito = true;
        optSobreMarca = (optEstable == LOW);
        cambiarEstado(ST_REGRESANDO_P0);
      }
      break;

    case ST_REGRESANDO_P0:
      if (!alturaSegura && !vertActivo) {
        Serial.println(F("Subiendo para regreso seguro a P0..."));
        iniciarMovimientoVertical(true, PASOS_SUBIDA_SEGURA);
        break;
      }
      if (!alturaSegura) break;
      if (!horizActivo && posicionActual != 0) {
        Serial.print(F("Regresando a P0 desde P"));
        Serial.println(posicionActual);
        iniciarMovimientoHorizontal(true);
      }
      if (!horizActivo && posicionActual == 0) {
        referenciada     = true;
        necesitaHomingP0 = false;
        Serial.println(F("[OK] Grua en P0."));
        if (regresoPostDeposito) {
          regresoPostDeposito = false;
          cambiarEstado(ST_FINALIZADO);
        } else {
          cambiarEstado(ST_ESPERANDO_CAMION);
        }
      }
      break;

    case ST_FINALIZADO:
      if (esDeposito) {
        Serial.print(F("DEPOSITO COMPLETADO | POSICION: P"));
        Serial.print(posicionDestino);
        Serial.println(F(" | GRUA EN P0"));
      } else {
        Serial.print(F("RETIRO COMPLETADO | ORIGEN: P"));
        Serial.print(posicionOrigenRetiro);
        Serial.println(F(" | ENTREGA EN P0"));
      }
      posicionDestino = 0;
      posicionOrigenRetiro = 0;
      retiroTomandoDesdePatio = false;
      cambiarEstado(ST_ESPERANDO_CAMION);
      break;

    case ST_ERROR:
      detenerTodo();
      Serial.println(F("Sistema en ERROR. Esperando camion para reintentar..."));
      if (camionEstable && !horizActivo && !vertActivo) {
        posicionActual = -1;
        referenciada   = false;
        refBuscandoP0  = true;
        ultimoError    = ERR_NINGUNO;
        cambiarEstado(ST_REFERENCIANDO);
      }
      break;
  }
}

void cambiarEstado(EstadoGrua s) {
  estadoGrua   = s;
  faseInicioMs = millis();
  emitirEventoGruaPortus("estado");
}


// ════════════════════════════════════════════════════════════════════════════
//  MOTORES (no bloqueantes)
// ════════════════════════════════════════════════════════════════════════════
bool tickMotorListo() {
  if (micros() - ultimoStepUs < INTERVALO_STEP_US) return false;
  ultimoStepUs = micros();
  return true;
}

bool requiereCamion() {
  return estadoGrua == ST_BAJANDO_ORIGEN || estadoGrua == ST_ACTIVANDO_IMAN;
}

void iniciarMovimientoVertical(bool subir, long pasos) {
  vertActivo   = true;
  vertSubiendo = subir;
  vertObjetivo = pasos;
  vertHechos   = 0;
  if (!subir) alturaSegura = false;
}

void actualizarMovimientoVertical() {
  if (!tickMotorListo()) return;

  motorVertical.step(vertSubiendo ? -1 : 1);   // -1=SUBIR, +1=BAJAR
  vertHechos++;

  if (vertHechos >= vertObjetivo) {
    vertActivo = false;
    apagarBobinas();
    if (vertSubiendo) alturaSegura = true;
  }
}

void iniciarMovimientoHorizontal(bool haciaP0) {
  moviendoHaciaP0 = haciaP0;
  horizActivo     = true;
  pasosSinMarca   = 0;
  if (!haciaP0) omitirPrimeraMarcaRetorno = false;
  if (
      haciaP0 &&
      (estadoGrua == ST_REGRESANDO_P0 || (estadoGrua == ST_MOVIENDO_DESTINO && posicionDestino == 0)) &&
      posicionActual >= 1 && posicionActual <= 4
  ) {
    // Si salimos desde una celda y estamos sobre la marca actual, primero
    // esperar a liberarla antes de volver a contar marcas.
    omitirPrimeraMarcaRetorno = (digitalRead(PIN_OPTICO) == LOW || optEstable == LOW);
  }
}

void actualizarMovimientoHorizontal() {
  if (!tickMotorListo()) return;

  int dir = moviendoHaciaP0 ? -1 : 1;
  motorHorizontal.step(dir);
  pasosSinMarca++;

  if (pasosSinMarca > PASOS_MAX_SIN_MARCA) {
    detenerHorizontal();
    abortarOperacion(ERR_SIN_MARCA);
    return;
  }

  if (posicionActual == posicionDestino && !moviendoHaciaP0 && !refBuscandoP0) {
    detenerHorizontal();
    return;
  }
  if (posicionActual == 0 && moviendoHaciaP0 && !refBuscandoP0) {
    detenerHorizontal();
    return;
  }
}

void detenerHorizontal() {
  horizActivo   = false;
  refBuscandoP0 = false;
  apagarBobinas();
}

void detenerTodo() {
  vertActivo  = false;
  horizActivo = false;
  apagarBobinas();
}

void apagarBobinas() {
  digitalWrite(8,  LOW); digitalWrite(9,  LOW);
  digitalWrite(10, LOW); digitalWrite(11, LOW);
  digitalWrite(4,  LOW); digitalWrite(5,  LOW);
  digitalWrite(6,  LOW); digitalWrite(7,  LOW);
}


// ════════════════════════════════════════════════════════════════════════════
//  MARCA OPTICA
// ════════════════════════════════════════════════════════════════════════════
int posicionTrasMarca(int pos, bool haciaP0) {
  if (haciaP0) {
    if (pos == 4) return 0;
    if (pos >= 1 && pos <= 3) return pos + 1;
  } else {
    if (pos == 0) return 4;
    if (pos >= 2 && pos <= 4) return pos - 1;
  }
  return pos;
}

void actualizarMarcaOptica() {
  int lectura = digitalRead(PIN_OPTICO);

  if (lectura != optLectura) {
    optLectura  = lectura;
    optCambioMs = millis();
  }
  if ((millis() - optCambioMs) >= DEBOUNCE_MARCA_MS) optEstable = optLectura;

  // Solo contar marcas si hay movimiento horizontal real
  if (!horizActivo) {
    if (optEstable == HIGH) optSobreMarca = false;
    return;
  }

  if (omitirPrimeraMarcaRetorno && moviendoHaciaP0) {
    if (optEstable == HIGH) {
      omitirPrimeraMarcaRetorno = false;
      optSobreMarca = false;
      Serial.println(F("  Marca inicial liberada, conteo retorno habilitado"));
    } else {
      optSobreMarca = true;
      return;
    }
  }

  if (optEstable == LOW && !optSobreMarca) {
    optSobreMarca = true;

    int posAnterior = posicionActual;
    if (posicionActual >= 0) posicionActual = posicionTrasMarca(posicionActual, moviendoHaciaP0);
    else                     posicionActual = 4;

    if (refBuscandoP0 && posicionActual == 0) referenciada = true;

    Serial.print(F("  Marca OK | "));
    Serial.print(moviendoHaciaP0 ? F("->P0") : F("->Patio"));
    Serial.print(F(" | "));
    Serial.print(posAnterior);
    Serial.print(F(" -> P"));
    Serial.println(posicionActual);

    pasosSinMarca = 0;

    if (!moviendoHaciaP0 && posicionActual == posicionDestino) detenerHorizontal();
    if (moviendoHaciaP0  && posicionActual == 0)               detenerHorizontal();
  }

  if (optEstable == HIGH) optSobreMarca = false;
}


// ════════════════════════════════════════════════════════════════════════════
//  ULTRASONIDO / CAMION
// ════════════════════════════════════════════════════════════════════════════
long medirDistanciaCm() {
  digitalWrite(PIN_US_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_US_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_US_TRIG, LOW);
  unsigned long d = pulseIn(PIN_US_ECHO, HIGH, 30000UL);
  if (d == 0) return -1;
  return (long)(d * 0.034 / 2.0);
}

void actualizarCamion() {
  if (millis() - ultimoUsMs < INTERVALO_US_MS) return;
  ultimoUsMs = millis();

  long dist  = medirDistanciaCm();
  bool ahora = (dist > 0 && dist <= DISTANCIA_CAMION_CM);

  if (ahora) {
    if (camionOkDesdeMs == 0) camionOkDesdeMs = millis();
    camionAusenteDesdeMs = 0;
    camionPresente = true;
    if (millis() - camionOkDesdeMs >= TIEMPO_CAMION_ESTABLE_MS) camionEstable = true;
  } else {
    if (camionAusenteDesdeMs == 0) camionAusenteDesdeMs = millis();
    if (millis() - camionAusenteDesdeMs >= TIEMPO_CAMION_AUSENTE_MS) {
      camionPresente  = false;
      camionEstable   = false;
      camionOkDesdeMs = 0;
    }
  }
}


// ════════════════════════════════════════════════════════════════════════════
//  PATIO
// ════════════════════════════════════════════════════════════════════════════
void autoDetectarPolaridadIR() {
  int altos = 0;
  for (int i = 0; i < 4; i++) if (digitalRead(PIN_IR_CELDA[i]) == LOW) altos++;

  if (altos == 4) {
    irOcupadoEnHigh = true;
    Serial.println(F("[AUTO] IR: 4 celdas en HIGH -> HIGH=ocupado"));
  } else if (altos == 0) {
    irOcupadoEnHigh = false;
    Serial.println(F("[AUTO] IR: 4 celdas en LOW -> LOW=ocupado"));
  } else {
    irOcupadoEnHigh = true;
    Serial.println(F("[AUTO] IR: lecturas mixtas, usando HIGH=ocupado"));
  }
}

bool celdaFisicamenteOcupada(int p) {
  if (p < 1 || p > 4) return false;
  return digitalRead(PIN_IR_CELDA[p - 1]) == HIGH;
}

void reiniciarPatioLogicoDesdeSensores() {
  for (int i = 0; i < 4; i++)
    estadoPatio[i] = celdaFisicamenteOcupada(i + 1) ? OCUPADA : LIBRE;
}

const char* nombreEstadoCelda(EstadoCelda e) {
  switch (e) {
    case LIBRE:     return "LIBRE";
    case RESERVADA: return "RESERVADA";
    case OCUPADA:   return "OCUPADA";
    case BLOQUEADA: return "BLOQUEADA";
  }
  return "?";
}

void inicializarPatioDesdeSensores() { reiniciarPatioLogicoDesdeSensores(); }

void sincronizarPatioFisico() {
  ultimoPatioMs = millis();
  for (int i = 0; i < 4; i++) {
    bool fisico = celdaFisicamenteOcupada(i + 1);
    if (estadoPatio[i] == OCUPADA && !fisico) {
      estadoPatio[i] = BLOQUEADA;
      Serial.print(F("[AVISO] P"));
      Serial.print(i + 1);
      Serial.println(F(" BLOQUEADA: contenedor no detectado"));
    }
  }
}

void imprimirPatio() {
  Serial.print(F("PATIO | "));
  for (int i = 0; i < 4; i++) {
    Serial.print(F("P"));
    Serial.print(i + 1);
    Serial.print(F(":"));
    Serial.print(nombreEstadoCelda(estadoPatio[i]));
    Serial.print(celdaFisicamenteOcupada(i + 1) ? F("(F:OCUP)") : F("(F:LIB)"));
    if (i < 3) Serial.print(F(" | "));
  }
  Serial.println();
}

int buscarPrimeraCeldaLibre() {
  for (int i = 0; i < 4; i++) {
    if (estadoPatio[i] == BLOQUEADA) continue;
    if (!celdaFisicamenteOcupada(i + 1)) return i + 1;
  }
  return 0;
}

int buscarPrimeraCeldaOcupada() {
  for (int i = 0; i < 4; i++) {
    if (estadoPatio[i] == BLOQUEADA) continue;
    if (celdaFisicamenteOcupada(i + 1)) return i + 1;
  }
  return 0;
}

void reservarCelda(int p) {
  if (p >= 1 && p <= 4) estadoPatio[p - 1] = RESERVADA;
}

void liberarReserva(int p) {
  if (p >= 1 && p <= 4 && estadoPatio[p - 1] == RESERVADA) estadoPatio[p - 1] = LIBRE;
}

bool confirmarDepositoFisico(int p) {
  if (p < 1 || p > 4) return false;
  if (celdaFisicamenteOcupada(p)) {
    estadoPatio[p - 1] = OCUPADA;
    return true;
  }
  liberarReserva(p);
  return false;
}


// ════════════════════════════════════════════════════════════════════════════
//  ELECTROIMAN / ERRORES
// ════════════════════════════════════════════════════════════════════════════
void activarElectroiman() {
  digitalWrite(PIN_ELECTROIMAN, HIGH);
  electroimanActivo = true;
}

void desactivarElectroiman() {
  digitalWrite(PIN_ELECTROIMAN, LOW);
  electroimanActivo = false;
}

void abortarOperacion(CodigoError e) {
  ultimoError = e;
  detenerTodo();
  desactivarElectroiman();
  alturaSegura = false;

  if (posicionDestino >= 1 && posicionDestino <= 4) liberarReserva(posicionDestino);

  switch (e) {
    case ERR_SIN_REFERENCIA:
      Serial.println(F("[ERROR] Perdida de referencia"));
      posicionActual = -1; referenciada = false; break;
    case ERR_SIN_MARCA:
      Serial.println(F("[ERROR] Marca esperada no detectada"));
      posicionActual = -1; referenciada = false; break;
    case ERR_DEPOSITO:
      Serial.println(F("[ERROR] Deposito no confirmado por sensor")); break;
    case ERR_CAMION_MOVIDO:
      Serial.println(F("[ERROR] Camion movido durante transferencia - ABORT")); break;
    case ERR_PATIO_LLENO:
      Serial.println(F("[ERROR] Patio lleno")); break;
    default: break;
  }

  if (RECUPERAR_A_P0_EN_FALLO) {
    bool recuperable = (e == ERR_DEPOSITO || e == ERR_CAMION_MOVIDO ||
                        e == ERR_SIN_REFERENCIA || e == ERR_SIN_MARCA);
    if (recuperable) {
      if (e == ERR_SIN_REFERENCIA || e == ERR_SIN_MARCA) {
        posicionActual = -1;
        referenciada   = false;
      }
      Serial.println(F("[RECUP] Intentando retorno seguro a P0..."));
      regresoPostDeposito = false;
      iniciarRegresoP0();
      return;
    }
  }

  cambiarEstado(ST_ERROR);
}