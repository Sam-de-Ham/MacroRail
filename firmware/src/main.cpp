// MacroRail rail controller firmware.
//
// Drives one stepper through a TMC2209 (STEP/DIR for motion, UART for configuration) and
// reads one homing switch. The host talks to it with the line protocol in docs/protocol.md.

#include <AccelStepper.h>
#include <Arduino.h>
#include <TMCStepper.h>

#include "config.h"

namespace {

TMC2209Stepper driver(PIN_UART_RX, PIN_UART_TX, DRIVER_RSENSE_OHM, DRIVER_ADDRESS);
AccelStepper stepper(AccelStepper::DRIVER, PIN_STEP, PIN_DIR);

enum class Motion : uint8_t { None, Move, Jog, HomeSeek, HomeBackoff, HomeProbe };
enum class Interrupt : uint8_t { None, Stopped, Halted, Link };

struct {
  bool enabled = false;
  bool homed = false;
  bool driverOk = false;
  long minLimit = 0;
  long maxLimit = 0;
  uint16_t runMa = 600;
  uint16_t holdMa = 200;
} state;

struct {
  uint16_t id = 0;
  Motion motion = Motion::None;
  Interrupt interrupt = Interrupt::None;
  float fast = 0;
  float slow = 0;
  float accel = 0;
  long backoff = 0;
} pending;

uint32_t lastRxMs = 0;
uint32_t lastPosMs = 0;
uint32_t lastDriverCheckMs = 0;
float currentAccel = 0;

// ---------------------------------------------------------------------------------------------
// Endstop (debounced in both directions)

bool endstopActive = false;
bool endstopRaw = false;
uint32_t endstopChangedUs = 0;

bool readEndstopRaw() { return digitalRead(PIN_ENDSTOP) == ENDSTOP_ACTIVE_LEVEL; }

void updateEndstop() {
  const bool raw = readEndstopRaw();
  const uint32_t now = micros();
  if (raw != endstopRaw) {
    endstopRaw = raw;
    endstopChangedUs = now;
  } else if (raw != endstopActive && now - endstopChangedUs >= ENDSTOP_DEBOUNCE_US) {
    endstopActive = raw;
  }
}

// ---------------------------------------------------------------------------------------------
// Replies and events

void beginReply(uint16_t id) {
  Serial.print(id);
  Serial.print(' ');
}

void replyOk(uint16_t id) {
  beginReply(id);
  Serial.println(F("OK"));
}

void replyOkPos(uint16_t id) {
  beginReply(id);
  Serial.print(F("OK pos="));
  Serial.println(stepper.currentPosition());
}

void replyErr(uint16_t id, const __FlashStringHelper* code) {
  beginReply(id);
  Serial.print(F("ERR "));
  Serial.println(code);
}

void replyErrPos(uint16_t id, const __FlashStringHelper* code) {
  beginReply(id);
  Serial.print(F("ERR "));
  Serial.print(code);
  Serial.print(F(" pos="));
  Serial.println(stepper.currentPosition());
}

void printIdentity() {
  Serial.print(F("fw=" FIRMWARE_VERSION " proto="));
  Serial.print(PROTOCOL_VERSION);
  Serial.print(F(" driver="));
  Serial.println(state.driverOk ? F("ok") : F("missing"));
}

// ---------------------------------------------------------------------------------------------
// Driver

void applyCurrent() {
  driver.rms_current(state.runMa, static_cast<float>(state.holdMa) / state.runMa);
}

bool configureDriver() {
  if (driver.version() != TMC2209_VERSION) return false;
  driver.GSTAT(0);  // clear reset/error flags (write-1-to-clear)
  driver.pdn_disable(true);       // PDN_UART pin is UART, not power-down
  driver.mstep_reg_select(true);  // microsteps from register, not MS1/MS2
  driver.I_scale_analog(false);   // current from register, not VREF
  driver.toff(4);
  driver.microsteps(MICROSTEPS);
  driver.intpol(true);            // interpolate to 256 microsteps
  driver.en_spreadCycle(false);   // StealthChop
  driver.pwm_autoscale(true);
  driver.pwm_autograd(true);
  driver.TCOOLTHRS(0);            // StallGuard/CoolStep unused
  driver.SGTHRS(0);
  driver.semin(0);
  driver.iholddelay(8);
  driver.TPOWERDOWN(20);
  applyCurrent();
  return driver.microsteps() == MICROSTEPS;
}

void disableMotor() {
  stepper.disableOutputs();
  state.enabled = false;
  state.homed = false;
}

void fault(const __FlashStringHelper* code) {
  disableMotor();
  Serial.print(F("! FAULT code="));
  Serial.println(code);
}

// Runs only while no motion is in flight: UART reads stall the step loop for a few ms.
void checkDriver() {
  if (driver.version() != TMC2209_VERSION) {
    if (state.driverOk) {
      state.driverOk = false;
      fault(F("driver_lost"));
    }
    return;
  }
  if (!state.driverOk) {  // came back (e.g. 12 V switched on): configure, motor stays off
    state.driverOk = configureDriver();
    return;
  }
  const uint8_t gstat = driver.GSTAT();
  if (gstat & 0x01) {  // reset: registers lost power
    state.driverOk = configureDriver();
    fault(F("driver_reset"));
  } else if (driver.ot()) {
    fault(F("overtemp"));
  } else if (driver.s2ga() || driver.s2gb() || driver.s2vsa() || driver.s2vsb()) {
    fault(F("short"));
  }
}

// ---------------------------------------------------------------------------------------------
// Motion

void setProfile(float speed, float accel) {
  stepper.setMaxSpeed(speed);
  if (accel != currentAccel) {  // setAcceleration is comparatively expensive
    stepper.setAcceleration(accel);
    currentAccel = accel;
  }
}

void haltNow() { stepper.setCurrentPosition(stepper.currentPosition()); }

void finish() {
  pending.id = 0;
  pending.motion = Motion::None;
  pending.interrupt = Interrupt::None;
}

void finishOk() {
  replyOkPos(pending.id);
  finish();
}

void finishErr(const __FlashStringHelper* code) {
  replyErrPos(pending.id, code);
  finish();
}

void startHomeSeek(long maxSteps) {
  setProfile(pending.fast, pending.accel);
  stepper.move(-maxSteps);
  pending.motion = Motion::HomeSeek;
}

void startHomeBackoff() {
  setProfile(pending.fast, pending.accel);
  stepper.move(pending.backoff);
  pending.motion = Motion::HomeBackoff;
}

void startHomeProbe() {
  setProfile(pending.slow, pending.accel);
  stepper.move(-2 * pending.backoff);
  pending.motion = Motion::HomeProbe;
}

void serviceMotion() {
  if (pending.motion == Motion::None) return;

  stepper.run();
  updateEndstop();

  const bool towardSwitch = stepper.targetPosition() < stepper.currentPosition();
  const bool hitSwitch = endstopActive && towardSwitch;
  if (hitSwitch) haltNow();
  const bool done = !stepper.isRunning();
  const bool linearMove = pending.motion == Motion::Move || pending.motion == Motion::Jog;

  if (hitSwitch && linearMove) state.homed = false;

  if (pending.interrupt != Interrupt::None) {
    if (!(done || hitSwitch)) return;
    switch (pending.interrupt) {
      case Interrupt::Stopped: finishErr(F("STOPPED")); break;
      case Interrupt::Halted: finishErr(F("HALTED")); break;
      case Interrupt::Link: finishErr(F("LINK")); break;
      case Interrupt::None: break;
    }
    return;
  }

  switch (pending.motion) {
    case Motion::HomeSeek:
      if (hitSwitch) startHomeBackoff();
      else if (done) finishErr(F("NO_SWITCH"));
      break;
    case Motion::HomeBackoff:
      if (!done) break;
      if (endstopActive) finishErr(F("SWITCH_STUCK"));
      else startHomeProbe();
      break;
    case Motion::HomeProbe:
      if (hitSwitch) {
        stepper.setCurrentPosition(0);
        state.homed = true;
        finishOk();
      } else if (done) {
        finishErr(F("NO_SWITCH"));
      }
      break;
    case Motion::Move:
    case Motion::Jog:
      if (hitSwitch) finishErr(F("ENDSTOP"));
      else if (done) finishOk();
      break;
    case Motion::None:
      break;
  }
}

// ---------------------------------------------------------------------------------------------
// Commands

bool parseLong(const char* text, long& out) {
  char* end = nullptr;
  out = strtol(text, &end, 10);
  return end != text && *end == '\0';
}

bool validProfile(long speed, long accel) {
  return speed > 0 && speed <= SPEED_MAX && accel > 0 && accel <= ACCEL_MAX;
}

bool withinLimits(long target) { return target >= state.minLimit && target <= state.maxLimit; }

void cmdInfo(uint16_t id, const long*) {
  beginReply(id);
  Serial.print(F("OK "));
  printIdentity();
}

void cmdStatus(uint16_t id, const long*) {
  beginReply(id);
  Serial.print(F("OK pos="));
  Serial.print(stepper.currentPosition());
  Serial.print(F(" homed="));
  Serial.print(state.homed);
  Serial.print(F(" enabled="));
  Serial.print(state.enabled);
  Serial.print(F(" moving="));
  Serial.print(pending.motion != Motion::None);
  Serial.print(F(" endstop="));
  Serial.print(endstopActive);
  Serial.print(F(" driver="));
  Serial.println(state.driverOk ? F("ok") : F("missing"));
}

void interrupt(uint16_t id, Interrupt kind) {
  if (pending.motion != Motion::None && pending.interrupt == Interrupt::None) {
    pending.interrupt = kind;
    if (kind == Interrupt::Halted) haltNow();
    else stepper.stop();
  }
  replyOk(id);
}

void cmdStop(uint16_t id, const long*) { interrupt(id, Interrupt::Stopped); }

void cmdHalt(uint16_t id, const long*) { interrupt(id, Interrupt::Halted); }

void cmdEnable(uint16_t id, const long*) {
  if (!state.driverOk) state.driverOk = configureDriver();
  if (!state.driverOk) return replyErr(id, F("DRIVER"));
  if (!state.enabled) {
    // StealthChop calibrates (AT#1) at standstill with run current: hold IRUN for >130 ms.
    driver.rms_current(state.runMa, 1.0f);
    stepper.enableOutputs();
    delay(200);
    applyCurrent();
    state.enabled = true;
  }
  replyOk(id);
}

void cmdDisable(uint16_t id, const long*) {
  disableMotor();
  replyOk(id);
}

void cmdCurrent(uint16_t id, const long* args) {
  const long run = args[0];
  const long hold = args[1];
  if (run < CURRENT_MIN_MA || run > CURRENT_MAX_MA || hold < 0 || hold > run) {
    return replyErr(id, F("ARG"));
  }
  state.runMa = run;
  state.holdMa = hold;
  if (state.driverOk) applyCurrent();
  replyOk(id);
}

void cmdLimits(uint16_t id, const long* args) {
  if (args[0] > args[1]) return replyErr(id, F("ARG"));
  state.minLimit = args[0];
  state.maxLimit = args[1];
  replyOk(id);
}

void cmdHome(uint16_t id, const long* args) {
  const long fast = args[0], slow = args[1], backoff = args[2], maxSteps = args[3], accel = args[4];
  if (!validProfile(fast, accel) || !validProfile(slow, accel) || backoff <= 0 || maxSteps <= 0) {
    return replyErr(id, F("ARG"));
  }
  if (!state.enabled) return replyErr(id, F("DISABLED"));
  state.homed = false;
  pending.id = id;
  pending.fast = fast;
  pending.slow = slow;
  pending.accel = accel;
  pending.backoff = backoff;
  lastPosMs = millis();
  if (endstopActive) startHomeBackoff();
  else startHomeSeek(maxSteps);
}

void startLinear(uint16_t id, Motion motion, long target, long speed, long accel) {
  pending.id = id;
  pending.motion = motion;
  setProfile(speed, accel);
  stepper.moveTo(target);
  lastPosMs = millis();
}

void cmdMove(uint16_t id, const long* args) {
  const long target = args[0];
  if (!validProfile(args[1], args[2])) return replyErr(id, F("ARG"));
  if (!state.enabled) return replyErr(id, F("DISABLED"));
  if (!state.homed) return replyErr(id, F("NOT_HOMED"));
  if (!withinLimits(target)) return replyErr(id, F("LIMIT"));
  if (target == stepper.currentPosition()) return replyOkPos(id);
  startLinear(id, Motion::Move, target, args[1], args[2]);
}

void cmdJog(uint16_t id, const long* args) {
  const long delta = args[0];
  const long target = stepper.currentPosition() + delta;
  if (!validProfile(args[1], args[2])) return replyErr(id, F("ARG"));
  if (!state.enabled) return replyErr(id, F("DISABLED"));
  if (state.homed && !withinLimits(target)) return replyErr(id, F("LIMIT"));
  if (delta < 0 && endstopActive) return replyErrPos(id, F("ENDSTOP"));
  if (delta == 0) return replyOkPos(id);
  startLinear(id, Motion::Jog, target, args[1], args[2]);
}

struct Command {
  const char* name;  // in flash
  uint8_t arity;
  bool allowedWhileMoving;
  void (*run)(uint16_t id, const long* args);
};

const char N_INFO[] PROGMEM = "INFO";
const char N_STATUS[] PROGMEM = "STATUS";
const char N_STOP[] PROGMEM = "STOP";
const char N_HALT[] PROGMEM = "HALT";
const char N_ENABLE[] PROGMEM = "ENABLE";
const char N_DISABLE[] PROGMEM = "DISABLE";
const char N_CURRENT[] PROGMEM = "CURRENT";
const char N_LIMITS[] PROGMEM = "LIMITS";
const char N_HOME[] PROGMEM = "HOME";
const char N_MOVE[] PROGMEM = "MOVE";
const char N_JOG[] PROGMEM = "JOG";

const Command COMMANDS[] = {
    {N_INFO, 0, true, cmdInfo},          {N_STATUS, 0, true, cmdStatus},
    {N_STOP, 0, true, cmdStop},          {N_HALT, 0, true, cmdHalt},
    {N_ENABLE, 0, false, cmdEnable},     {N_DISABLE, 0, false, cmdDisable},
    {N_CURRENT, 2, false, cmdCurrent},   {N_LIMITS, 2, false, cmdLimits},
    {N_HOME, 5, false, cmdHome},         {N_MOVE, 3, false, cmdMove},
    {N_JOG, 3, false, cmdJog},
};

void handleLine(char* text) {
  constexpr uint8_t MAX_ARGS = 5;
  char* save = nullptr;
  const char* idText = strtok_r(text, " ", &save);
  const char* name = strtok_r(nullptr, " ", &save);
  long id = 0;
  if (!idText || !name || !parseLong(idText, id) || id < 1 || id > 65535) {
    return replyErr(0, F("SYNTAX"));
  }

  long args[MAX_ARGS];
  uint8_t argc = 0;
  for (const char* tok; (tok = strtok_r(nullptr, " ", &save));) {
    if (argc == MAX_ARGS || !parseLong(tok, args[argc++])) return replyErr(id, F("ARG"));
  }

  for (const Command& command : COMMANDS) {
    if (strcmp_P(name, command.name) != 0) continue;
    if (argc != command.arity) return replyErr(id, F("ARG"));
    if (pending.motion != Motion::None && !command.allowedWhileMoving) {
      return replyErr(id, F("BUSY"));
    }
    return command.run(id, args);
  }
  replyErr(id, F("UNKNOWN"));
}

// ---------------------------------------------------------------------------------------------
// Host link

char line[LINE_MAX];
uint8_t lineLength = 0;
bool lineOverflow = false;

void pollSerial() {
  while (Serial.available() > 0) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\r') continue;
    if (c != '\n') {
      if (lineLength < LINE_MAX - 1) line[lineLength++] = c;
      else lineOverflow = true;
      continue;
    }
    lastRxMs = millis();
    if (lineOverflow) {
      replyErr(0, F("TOOLONG"));
    } else if (lineLength > 0) {
      line[lineLength] = '\0';
      handleLine(line);
    }
    lineLength = 0;
    lineOverflow = false;
  }
}

void serviceTimers() {
  const uint32_t now = millis();
  if (pending.motion != Motion::None) {
    if (pending.interrupt == Interrupt::None && now - lastRxMs > LINK_TIMEOUT_MS) {
      pending.interrupt = Interrupt::Link;
      stepper.stop();
    }
    if (now - lastPosMs >= POS_REPORT_MS) {
      lastPosMs = now;
      Serial.print(F("! POS pos="));
      Serial.println(stepper.currentPosition());
    }
  } else if (now - lastDriverCheckMs >= DRIVER_CHECK_MS) {
    lastDriverCheckMs = now;
    checkDriver();
  }
}

}  // namespace

void setup() {
  pinMode(PIN_ENDSTOP, INPUT_PULLUP);
  stepper.setPinsInverted(INVERT_DIRECTION, false, true);  // EN is active low
  stepper.setEnablePin(PIN_ENABLE);
  stepper.disableOutputs();

  Serial.begin(SERIAL_BAUD);
  driver.beginSerial(DRIVER_UART_BAUD);
  state.driverOk = configureDriver();

  endstopRaw = endstopActive = readEndstopRaw();
  lastRxMs = lastDriverCheckMs = millis();

  Serial.print(F("! READY "));
  printIdentity();
}

void loop() {
  serviceMotion();
  pollSerial();
  serviceMotion();
  updateEndstop();
  serviceTimers();
}
