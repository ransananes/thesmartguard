/**
 * SmartGuard Robot — Arduino Uno Motor Controller
 *
 * Wiring
 * ──────
 * ESP32-CAM GPIO1 (TX)  →  Arduino pin 10  (SoftwareSerial RX)
 * ESP32-CAM GND         →  Arduino GND
 *
 * 74HCT595N:
 *   pin 2 → SHCP   pin 4 → STCP   pin 8 → DATA   pin 7 → OE (active-LOW)
 * Motor PWM:
 *   pin 5 → ENA    pin 6 → ENB
 */

#include <SoftwareSerial.h>

// ── SoftwareSerial from ESP32 GPIO1 ───────────────────────────────────
#define ESP_RX_PIN  10
#define ESP_TX_PIN  11
SoftwareSerial espSerial(ESP_RX_PIN, ESP_TX_PIN);

// ── Shift register & motor pins ────────────────────────────────────────
#define SHCP_PIN   2
#define STCP_PIN   4
#define PWM1_PIN   5    // Motor A speed (ENA)
#define PWM2_PIN   6    // Motor B speed (ENB)
#define EN_PIN     7    // 74HCT595 OE — active-LOW (LOW = outputs enabled)
#define DATA_PIN   8
#define LED_PIN   13    // blinks on every received command

// ── Direction bytes (verified by physical observation) ─────────────────
//   82  → robot goes forward
//   161 → robot goes backward
//   162 → robot turns left
//   81  → robot turns right
#define DIR_STOP      0b00000000   //   0
#define DIR_FORWARD   0b01010010   //  82
#define DIR_BACKWARD  0b10100001   // 161
#define DIR_LEFT      0b10100010   // 162
#define DIR_RIGHT     0b01010001   //  81

// ── Speeds (0–255) ─────────────────────────────────────────────────────
// Forward uses two separate values so you can trim out a drift:
//   Robot turns RIGHT → reduce SPEED_FWD_A  (or raise SPEED_FWD_B)
//   Robot turns LEFT  → reduce SPEED_FWD_B  (or raise SPEED_FWD_A)
#define SPEED_FWD_A        180   // Motor A (PWM1 / ENA) during forward
#define SPEED_FWD_B        200   // Motor B (PWM2 / ENB) during forward — raised to correct right drift
#define SPEED_BACK         160
#define SPEED_TURN         130
// Fast return-to-home speeds (lowercase commands: f b l r)
#define SPEED_RETURN_BWD   220
#define SPEED_RETURN_TURN  185

// ── Auto-stop timeout (milliseconds) ───────────────────────────────────
#define AUTO_STOP_TIMEOUT 600  // Stop after 600ms of no new commands


// ── Low-level helpers ──────────────────────────────────────────────────

void shiftOut595(uint8_t val) {
  for (int i = 7; i >= 0; i--) {
    digitalWrite(DATA_PIN, (val >> i) & 1);
    digitalWrite(SHCP_PIN, HIGH);
    digitalWrite(SHCP_PIN, LOW);
  }
}

void latch(uint8_t val) {
  digitalWrite(STCP_PIN, LOW);
  shiftOut595(val);
  digitalWrite(STCP_PIN, HIGH);
}

void motor(uint8_t direction, uint8_t speed1, uint8_t speed2) {
  if (direction == DIR_STOP) {
    digitalWrite(EN_PIN, HIGH);      // disable outputs first
    analogWrite(PWM1_PIN, 0);
    analogWrite(PWM2_PIN, 0);
    latch(DIR_STOP);
    return;
  }
  analogWrite(PWM1_PIN, speed1);
  analogWrite(PWM2_PIN, speed2);
  latch(direction);
  digitalWrite(EN_PIN, LOW);         // enable after data is latched
}


// ── Command handler with auto-stop ────────────────────────────────────

unsigned long lastCommandTime = 0;
char lastCommand = 'S';

void executeCommand(char cmd) {
  digitalWrite(LED_PIN, HIGH);       // visual confirmation
  lastCommandTime = millis();
  lastCommand = cmd;

  switch (cmd) {
    case 'F':
      motor(DIR_FORWARD,  SPEED_FWD_A,       SPEED_FWD_B);
      Serial.println(">> Forward");
      break;
    case 'B':
      motor(DIR_BACKWARD, SPEED_BACK,        SPEED_BACK);
      Serial.println(">> Backward");
      break;
    case 'L':
      motor(DIR_LEFT,     SPEED_TURN,        SPEED_TURN);
      Serial.println(">> Left");
      break;
    case 'R':
      motor(DIR_RIGHT,    SPEED_TURN,        SPEED_TURN);
      Serial.println(">> Right");
      break;
    case 'S':
      motor(DIR_STOP, 0, 0);
      Serial.println(">> Stop");
      break;
    // Fast return-to-home commands (lowercase) — higher PWM, duration-adjusted by backend
    case 'f':
      motor(DIR_FORWARD,  SPEED_RETURN_BWD,  SPEED_RETURN_BWD);
      Serial.println(">> Fast Forward (return)");
      break;
    case 'b':
      motor(DIR_BACKWARD, SPEED_RETURN_BWD,  SPEED_RETURN_BWD);
      Serial.println(">> Fast Backward (return)");
      break;
    case 'l':
      motor(DIR_LEFT,     SPEED_RETURN_TURN, SPEED_RETURN_TURN);
      Serial.println(">> Fast Left (return)");
      break;
    case 'r':
      motor(DIR_RIGHT,    SPEED_RETURN_TURN, SPEED_RETURN_TURN);
      Serial.println(">> Fast Right (return)");
      break;
    default:
      break;
  }

  delay(30);
  digitalWrite(LED_PIN, LOW);
}

void checkAutoStop() {
  // Auto-stop if no command received for AUTO_STOP_TIMEOUT ms
  if (lastCommand != 'S' && (millis() - lastCommandTime) > AUTO_STOP_TIMEOUT) {
    motor(DIR_STOP, 0, 0);
    lastCommand = 'S';
    Serial.println(">> Auto-stop");
  }
}


// ── Startup self-test ──────────────────────────────────────────────────

void selfTest() {
  Serial.println("=== Self-test: F B L R ===");

  Serial.println("Forward...");   motor(DIR_FORWARD,  SPEED_FWD_A,  SPEED_FWD_B);  delay(800);
  motor(DIR_STOP, 0, 0); delay(300);

  Serial.println("Backward...");  motor(DIR_BACKWARD, SPEED_BACK,   SPEED_BACK);   delay(800);
  motor(DIR_STOP, 0, 0); delay(300);

  Serial.println("Left...");      motor(DIR_LEFT,     SPEED_TURN,   SPEED_TURN);   delay(600);
  motor(DIR_STOP, 0, 0); delay(300);

  Serial.println("Right...");     motor(DIR_RIGHT,    SPEED_TURN,   SPEED_TURN);   delay(600);
  motor(DIR_STOP, 0, 0);

  Serial.println("=== Self-test done ===\n");
}


void setup() {
  Serial.begin(57600);
  espSerial.begin(57600);

  pinMode(SHCP_PIN, OUTPUT);
  pinMode(STCP_PIN, OUTPUT);
  pinMode(DATA_PIN, OUTPUT);
  pinMode(EN_PIN,   OUTPUT);
  pinMode(PWM1_PIN, OUTPUT);
  pinMode(PWM2_PIN, OUTPUT);
  pinMode(LED_PIN,  OUTPUT);

  motor(DIR_STOP, 0, 0);
  delay(500);
  selfTest();

  Serial.println("Ready — listening on pin 10 (ESP32) and USB Serial.");
}


void loop() {
  if (espSerial.available()) {
    String line = espSerial.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      Serial.print("[ESP32] ");
      Serial.println(line);
      executeCommand(line.charAt(0));
    }
  }

  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      Serial.print("[USB] ");
      Serial.println(line);
      executeCommand(line.charAt(0));
    }
  }


  checkAutoStop();
}
