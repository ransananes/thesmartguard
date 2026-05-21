/**
 * Motor Pin Tester — updated to find Motor B bits
 *
 * Motor A confirmed: A+ = bit0, A- = bit1
 * Now scanning all remaining bit pairs for Motor B.
 *
 * Commands (Serial Monitor at 57600 baud):
 *
 *   A+  / A-        Motor A forward / backward  (confirmed working)
 *
 *   B4+ / B4-       Try Motor B on bits 4,5
 *   B6+ / B6-       Try Motor B on bits 6,7
 *   B23+ / B23-     Retry bits 2,3 but using PWM1 instead of PWM2
 *                   (rules out a broken pin-6 / PWM2 issue)
 *
 *   F               Forward  (both motors, original byte 92)
 *   BK              Backward (both motors, original byte 163)
 *
 *   S               Stop
 *   0-9             Speed (0=off … 9=full)
 */

#define SHCP_PIN   2
#define STCP_PIN   4
#define PWM1_PIN   5
#define PWM2_PIN   6
#define EN_PIN     7
#define DATA_PIN   8

int spd = 200;

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

void stopAll() {
  digitalWrite(EN_PIN, HIGH);
  analogWrite(PWM1_PIN, 0);
  analogWrite(PWM2_PIN, 0);
  latch(0);
  Serial.println(">> Stopped");
}

// Run with explicit PWM on both channels + a shift-reg byte
void run(uint8_t reg, uint8_t p1, uint8_t p2) {
  analogWrite(PWM1_PIN, p1);
  analogWrite(PWM2_PIN, p2);
  latch(reg);
  digitalWrite(EN_PIN, LOW);
  Serial.print(">> reg=0b");
  for (int i = 7; i >= 0; i--) Serial.print((reg >> i) & 1);
  Serial.print("  (");
  Serial.print(reg);
  Serial.print(")  PWM1=");
  Serial.print(p1);
  Serial.print("  PWM2=");
  Serial.println(p2);
}

void setup() {
  Serial.begin(57600);
  pinMode(SHCP_PIN, OUTPUT);
  pinMode(STCP_PIN, OUTPUT);
  pinMode(DATA_PIN, OUTPUT);
  pinMode(EN_PIN,   OUTPUT);
  pinMode(PWM1_PIN, OUTPUT);
  pinMode(PWM2_PIN, OUTPUT);
  stopAll();

  Serial.println("=== Motor Pin Tester v2 ===");
  Serial.println("Commands: A+ A- | B4+ B4- | B6+ B6- | B23+ B23- | F BK | S | 0-9");
}

void loop() {
  if (!Serial.available()) return;

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  cmd.toUpperCase();
  if (cmd.length() == 0) return;

  // Speed
  if (cmd.length() == 1 && cmd[0] >= '0' && cmd[0] <= '9') {
    spd = map(cmd[0] - '0', 0, 9, 0, 255);
    Serial.print("Speed: "); Serial.println(spd);
    return;
  }

  if (cmd == "S")  { stopAll(); return; }

  // ── Motor A (bits 0,1 — confirmed) ──────────────────────────────────
  if (cmd == "A+") { run(0b00000001, spd, 0);   return; }
  if (cmd == "A-") { run(0b00000010, spd, 0);   return; }

  // ── Motor B — try bits 4,5 with PWM2 ────────────────────────────────
  if (cmd == "B4+") { run(0b00010000, 0, spd);  return; }
  if (cmd == "B4-") { run(0b00100000, 0, spd);  return; }

  // ── Motor B — try bits 6,7 with PWM2 ────────────────────────────────
  if (cmd == "B6+") { run(0b01000000, 0, spd);  return; }
  if (cmd == "B6-") { run(0b10000000, 0, spd);  return; }

  // ── Motor B — retry bits 2,3 but using PWM1 (tests if pin 6 is dead) ─
  if (cmd == "B23+") { run(0b00000100, spd, spd); return; }
  if (cmd == "B23-") { run(0b00001000, spd, spd); return; }

  // ── Full direction bytes (original values) ───────────────────────────
  if (cmd == "F")  { run(92,  spd, spd); return; }
  if (cmd == "BK") { run(163, spd, spd); return; }

  Serial.print("Unknown: "); Serial.println(cmd);
}
