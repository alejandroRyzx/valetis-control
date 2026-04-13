// ============================================================
// VALETIS CONTROL v2 — Arduino Sketch
// ============================================================
// Pines:
//   SERVO1 (Entrada)  → Pin 10
//   SERVO2 (Salida)   → Pin 6
//   SENSOR1 (Entrada) → Pin 7  (IR / Ultrasónico)
//   SENSOR2 (Salida)  → Pin 8  (IR / Ultrasónico)
//   PULSADOR1 (Entrada) → Pin 2
//   PULSADOR2 (Pago)    → Pin 3  ← NUEVO
//
// Protocolo Serial (entrada desde Python):
//   'A' → Abrir barrera entrada (Servo 1)
//   'B' → Abrir barrera salida  (Servo 2)
//
// Protocolo Serial (salida hacia Python):
//   "PULSADOR_ENTRADA"  → Botón de entrada presionado
//   "PULSADOR_PAGO"     → Botón de pago presionado   ← NUEVO
//   "SENSOR_ENTRADA"    → Carro pasó por sensor entrada
//   "ENTRADA_ABIERTA"   → Barrera entrada abierta
//   "ENTRADA_CERRADA"   → Barrera entrada cerrada
//   "SALIDA_ABIERTA"    → Barrera salida abierta
//   "SALIDA_CERRADA"    → Barrera salida cerrada
//   "ARDUINO_LISTO"     → Boot completo
// ============================================================

#include <Servo.h>

Servo barrera1;
Servo barrera2;

// ── PINES ────────────────────────────────────────────────────
const int SERVO1    = 10;
const int SERVO2    = 6;
const int SENSOR1   = 7;
const int SENSOR2   = 8;
const int PULSADOR1 = 3;   // Botón ENTRADA
const int PULSADOR2 = 2;   // Botón PAGO

// ── CONSTANTES ──────────────────────────────────────────────
const int CERRADO = 0;
const int ABIERTO = 90;
const unsigned long TIEMPO_CIERRE = 3000;
const unsigned long DEBOUNCE_MS   = 300;  // Anti-rebote botones

// ── ESTADO BARRERAS ─────────────────────────────────────────
bool abierta1   = false;
bool abierta2   = false;
bool esperando1 = false;
bool esperando2 = false;
bool detecto1   = false;
bool detecto2   = false;
bool avisado1   = false;
unsigned long tiempo1 = 0;
unsigned long tiempo2 = 0;

// ── ESTADO PULSADORES ───────────────────────────────────────
bool estadoAnteriorBtn1 = HIGH;
bool estadoAnteriorBtn2 = HIGH;
unsigned long lastPressBtn1 = 0;
unsigned long lastPressBtn2 = 0;

// ── HELPERS ─────────────────────────────────────────────────
bool detecta(int pin) {
  return digitalRead(pin) == LOW;
}

// ── BARRERA 1 — ENTRADA ─────────────────────────────────────
void abrir1() {
  barrera1.write(ABIERTO);
  abierta1   = true;
  esperando1 = false;
  detecto1   = false;
  avisado1   = false;
  Serial.println("ENTRADA_ABIERTA");
}

void cerrar1() {
  barrera1.write(CERRADO);
  abierta1   = false;
  esperando1 = false;
  detecto1   = false;
  avisado1   = false;
  Serial.println("ENTRADA_CERRADA");
}

// ── BARRERA 2 — SALIDA ──────────────────────────────────────
void abrir2() {
  barrera2.write(ABIERTO);
  abierta2   = true;
  esperando2 = false;
  detecto2   = false;
  Serial.println("SALIDA_ABIERTA");
}

void cerrar2() {
  barrera2.write(CERRADO);
  abierta2   = false;
  esperando2 = false;
  detecto2   = false;
  Serial.println("SALIDA_CERRADA");
}

// ── SETUP ───────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);

  pinMode(SENSOR1,   INPUT_PULLUP);
  pinMode(SENSOR2,   INPUT_PULLUP);
  pinMode(PULSADOR1, INPUT_PULLUP);
  pinMode(PULSADOR2, INPUT_PULLUP);  // ← NUEVO

  barrera1.attach(SERVO1);
  barrera2.attach(SERVO2);

  delay(500);
  barrera1.write(CERRADO);
  delay(200);
  barrera2.write(CERRADO);
  delay(200);

  Serial.println("ARDUINO_LISTO");
}

// ── LOOP ────────────────────────────────────────────────────
void loop() {

  // ─── Comandos desde Python ────────────────────────────────
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == 'A') abrir1();
    else if (c == 'B') abrir2();
  }

  unsigned long ahora = millis();

  // ─── PULSADOR 1 — ENTRADA ────────────────────────────────
  // Avisa a Valetis que alguien presionó el botón de entrada.
  // Valetis decide si emitir ticket y abrir barrera.
  bool estadoBtn1 = digitalRead(PULSADOR1);
  if (estadoBtn1 == LOW && estadoAnteriorBtn1 == HIGH) {
    if (ahora - lastPressBtn1 > DEBOUNCE_MS) {
      Serial.println("PULSADOR_ENTRADA");
      lastPressBtn1 = ahora;
    }
  }
  estadoAnteriorBtn1 = estadoBtn1;

  // ─── PULSADOR 2 — PAGO ──────────────────────────────────
  // Avisa a Valetis que alguien presionó el botón de pago.
  // Valetis busca el ticket activo más reciente y lo cobra.
  bool estadoBtn2 = digitalRead(PULSADOR2);
  if (estadoBtn2 == LOW && estadoAnteriorBtn2 == HIGH) {
    if (ahora - lastPressBtn2 > DEBOUNCE_MS) {
      Serial.println("PULSADOR_PAGO");
      lastPressBtn2 = ahora;
    }
  }
  estadoAnteriorBtn2 = estadoBtn2;

  // ─── AUTO-CIERRE ENTRADA ─────────────────────────────────
  if (abierta1) {
    if (detecta(SENSOR1)) {
      if (!avisado1) {
        Serial.println("SENSOR_ENTRADA");
        avisado1 = true;
      }
      detecto1   = true;
      esperando1 = false;
    } else {
      if (detecto1) {
        if (!esperando1) {
          esperando1 = true;
          tiempo1    = millis();
        } else if (millis() - tiempo1 >= TIEMPO_CIERRE) {
          cerrar1();
        }
      }
    }
  }

  // ─── AUTO-CIERRE SALIDA ──────────────────────────────────
  if (abierta2) {
    if (detecta(SENSOR2)) {
      detecto2   = true;
      esperando2 = false;
    } else {
      if (detecto2) {
        if (!esperando2) {
          esperando2 = true;
          tiempo2    = millis();
        } else if (millis() - tiempo2 >= TIEMPO_CIERRE) {
          cerrar2();
        }
      }
    }
  }
}
