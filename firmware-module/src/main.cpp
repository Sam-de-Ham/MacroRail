// MacroRail scan module controller firmware.
//
// Drives two 28BYJ-48 steppers through ULN2003 boards in half-step mode (tilt and yaw), reads
// the tilt homing switch and the yaw hall sensor. The host talks to it with the line protocol
// in docs/protocol-module.md, which follows the rail's (docs/protocol.md).

#include <AccelStepper.h>
#include <Arduino.h>
#include <errno.h>

#include "config.h"

namespace {

// ---------------------------------------------------------------------------------------------
// Motors
//
// AccelStepper's half-step mode takes a 28BYJ-48's pins in the order IN1, IN3, IN2, IN4.
// Reversing that order reverses the coil sequence, which is how an axis is inverted.
// In 4-wire modes the coil pattern follows the position (position & 7), so a motor's position
// is never reset: each axis keeps an `origin` instead, and the protocol position is the
// difference. Re-zeroing AccelStepper would jump the coils by up to four half-steps.
// For the same reason, a motor whose coils were off is energised at the pattern of its held
// position before it steps: AccelStepper's enableOutputs() only makes the pins outputs, so the
// first step would otherwise switch on the neighbouring pattern straight from off.

constexpr uint8_t HALF4WIRE_ORDER[4] = {0, 2, 1, 3};  // IN1, IN3, IN2, IN4

constexpr uint8_t motorPin(const uint8_t (&in)[4], uint8_t index, bool invert) {
  return in[invert ? 3 - HALF4WIRE_ORDER[index] : HALF4WIRE_ORDER[index]];
}

class Stepper : public AccelStepper {
 public:
  using AccelStepper::AccelStepper;
  void hold() {  // energise the coil pattern of the current position
    enableOutputs();
    step(currentPosition());
  }
};

struct Motor {
  Motor(const uint8_t (&in)[4], bool invert)
      : stepper(AccelStepper::HALF4WIRE, motorPin(in, 0, invert), motorPin(in, 1, invert),
                motorPin(in, 2, invert), motorPin(in, 3, invert)) {}

  Stepper stepper;
  long origin = 0;  // stepper position of the protocol's 0
  bool homed = false;
  bool energised = false;
  float accel = 0;  // last acceleration set (setAcceleration is comparatively expensive)

  long position() { return stepper.currentPosition() - origin; }
};

Motor yaw(YAW_IN, YAW_INVERT);
Motor tilt(TILT_IN, TILT_INVERT);

enum class Motion : uint8_t {
  None, Move, Jog, TiltSeek, TiltBackoff, TiltProbe, YawSweep, YawBack, YawApproach
};
enum class Abort : uint8_t { None, Stopped, Link };

struct {
  long minLimit = 0;  // tilt soft limits
  long maxLimit = 0;
} limits;

struct {
  uint16_t id = 0;
  Motion motion = Motion::None;
  Abort abort = Abort::None;
  Motor* motor = nullptr;     // the axis that moves
  bool ignoreSwitch = false;  // backing off a pressed switch: its release bounce must not stop us
  float fast = 0;
  float slow = 0;
  float accel = 0;
  long clearance = 0;   // tilt homing: how far past the release point to back off
  long releaseMax = 0;  // tilt homing: give up if the switch hasn't released by then
  long tripPos = 0;     // tilt homing: where the seek tripped the switch (stepper position)
  long releasePos = 0;  // tilt homing: where it released again, once `released`
  bool released = false;
  bool sought = false;  // tilt homing: the seek has run (one starting pressed backs off first)
  long seekMax = 0;     // tilt homing: `max`
  long sweepStart = 0;   // yaw homing: stepper position where the sweep began
  long sweepLength = 0;  // yaw homing: `max`
  long takeup = 0;       // yaw homing: approach the peak from this far before it
  long peak = 0;         // yaw homing: the field peak (stepper position)
  uint16_t peakDev = 0;  // yaw homing: its deviation from the baseline, ADC counts
  long peakWidth = 0;    // yaw homing: its width at half height, half-steps
} pending;

uint32_t lastRxMs = 0;
uint32_t lastPosMs = 0;
uint32_t idleSinceMs = 0;

// ---------------------------------------------------------------------------------------------
// Tilt switch
//
// A pin-change interrupt latches the very first contact, so even a brief touch stops a tilt
// motion before its next step, whatever the direction of travel.
// Two latches: `switchTouched` takes any closing edge at all, `switchTripped` only one that is
// still closed when the interrupt runs (a few µs later), which rejects motor-noise spikes.
// The homing seek expects the switch and uses the first touch, so a chattering contact counts
// from its very first blip; every other motion, the homing probe included, uses the filtered
// trip.
// A pin-change interrupt fires on both edges, so the handler keeps the level it saw last: a
// change from released is a closing edge, and so is one that ends pressed.
// While tilt moves toward the switch, its level stops it too: a contact that closed just before
// the motion started has no edge left to latch.
// `switchActive` is the debounced level, reported to the host on every change. Whether a move
// may start is decided from it or the raw level, whichever reads pressed, since the debounced
// level lags a fresh contact.

static_assert(digitalPinToPCICRbit(PIN_TILT_SWITCH) == 0, "the handler is PCINT0_vect");

volatile bool switchTouched = false;
volatile bool switchTripped = false;
volatile bool switchLevelSeen = false;  // the interrupt's last reading
bool switchActive = false;
bool switchRaw = false;
uint32_t switchChangedUs = 0;
uint32_t switchSeenUs = 0;  // last time the raw input read "pressed"

bool readSwitchRaw() { return digitalRead(PIN_TILT_SWITCH) == SWITCH_ACTIVE_LEVEL; }

bool switchPressed() { return switchActive || readSwitchRaw(); }

void updateSwitch() {
  const bool raw = readSwitchRaw();
  const uint32_t now = micros();
  if (raw) switchSeenUs = now;
  if (raw != switchRaw) {
    switchRaw = raw;
    switchChangedUs = now;
  } else if (raw != switchActive && now - switchChangedUs >= SWITCH_DEBOUNCE_US) {
    switchActive = raw;
    Serial.print(F("! SWITCH pressed="));
    Serial.println(switchActive);
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

void replyOkPos(uint16_t id, Motor& motor) {
  beginReply(id);
  Serial.print(F("OK pos="));
  Serial.println(motor.position());
}

void replyErr(uint16_t id, const __FlashStringHelper* code) {
  beginReply(id);
  Serial.print(F("ERR "));
  Serial.println(code);
}

void replyErrPos(uint16_t id, const __FlashStringHelper* code, Motor& motor) {
  beginReply(id);
  Serial.print(F("ERR "));
  Serial.print(code);
  Serial.print(F(" pos="));
  Serial.println(motor.position());
}

void printIdentity() {
  Serial.print(F("fw=" FIRMWARE_VERSION " proto="));
  Serial.print(PROTOCOL_VERSION);
  Serial.println(F(" role=module"));
}

// ---------------------------------------------------------------------------------------------
// Hall sensor (yaw homing)
//
// The sensor is read once at every position of the sweep, from its start (before the first
// step) to its end, and the readings are averaged per bin of HALL_BIN_STEPS half-steps (one
// byte each, ADC/4): bin i holds offsets 8i … 8i+7, so its centre is 8i + 3.5. Sampling by
// position rather than by time keeps the bins even through the speed ramps.

struct {
  uint8_t bins[HALL_BINS];
  uint16_t count = 0;   // index of the bin being filled = number of finished bins
  uint16_t sum = 0;     // readings of the bin being filled
  uint8_t samples = 0;
  long sampled = -1;    // offset into the sweep of the last reading
  uint16_t baseline = 0;  // ADC counts
} hall;

void startHallSampling() {
  hall.count = 0;
  hall.sum = 0;
  hall.samples = 0;
  hall.sampled = -1;
}

void closeHallBin() {
  uint8_t mean;
  if (hall.samples > 0) {
    mean = min(255U, (hall.sum + 2U * hall.samples) / (4U * hall.samples));
  } else {  // a bin skipped between two loop passes repeats its predecessor
    mean = hall.count > 0 ? hall.bins[hall.count - 1] : 128;
  }
  hall.bins[hall.count++] = mean;
  hall.sum = 0;
  hall.samples = 0;
}

void sampleHall() {
  const long offset = yaw.stepper.currentPosition() - pending.sweepStart;
  if (offset == hall.sampled || offset < 0 || offset > pending.sweepLength) return;
  hall.sampled = offset;
  const uint16_t bin = offset / HALL_BIN_STEPS;
  while (hall.count < bin) closeHallBin();
  hall.sum += analogRead(PIN_HALL);
  ++hall.samples;
}

uint16_t hallDeviation(uint16_t bin) {
  const int d = static_cast<int>(hall.bins[bin]) * 4 - static_cast<int>(hall.baseline);
  return d < 0 ? -d : d;
}

// The contiguous run of bins around `top` whose deviation is at least half of its deviation.
void hallRun(uint16_t top, uint16_t& lo, uint16_t& hi) {
  const uint16_t peak = hallDeviation(top);
  lo = hi = top;
  while (lo > 0 && 2 * hallDeviation(lo - 1) >= peak) --lo;
  while (hi + 1 < hall.count && 2 * hallDeviation(hi + 1) >= peak) ++hi;
}

// Finds the magnet's field peak in the sampled bins (docs/protocol-module.md, "Finding the
// magnet"). Sets pending.peak, peakDev and peakWidth; false if there is no peak.
bool findHallPeak() {
  // Close the bins the sweep covered fully; a last, partial bin is dropped (its centre isn't
  // 8i + 3.5).
  while (hall.count < (pending.sweepLength + 1) / HALL_BIN_STEPS) closeHallBin();
  const uint16_t n = hall.count;
  if (n < HALL_MIN_BINS) return false;

  // Baseline: the most common value, from a histogram of bins / 4; then the mean of the bins
  // in that bucket.
  uint16_t histogram[HALL_HISTOGRAM_BUCKETS] = {};
  for (uint16_t i = 0; i < n; ++i) ++histogram[hall.bins[i] / (256 / HALL_HISTOGRAM_BUCKETS)];
  uint8_t mode = 0;
  for (uint8_t b = 1; b < HALL_HISTOGRAM_BUCKETS; ++b) {
    if (histogram[b] > histogram[mode]) mode = b;
  }
  uint32_t sum = 0;
  for (uint16_t i = 0; i < n; ++i) {
    if (hall.bins[i] / (256 / HALL_HISTOGRAM_BUCKETS) == mode) sum += hall.bins[i];
  }
  hall.baseline = (sum * 4 + histogram[mode] / 2) / histogram[mode];

  uint16_t top = 0;
  for (uint16_t i = 1; i < n; ++i) {
    if (hallDeviation(i) > hallDeviation(top)) top = i;
  }
  if (hallDeviation(top) < HALL_MIN_DEVIATION) return false;

  uint16_t lo, hi;
  hallRun(top, lo, hi);
  // A run cut off by either end of the sweep has a biased centre. If the sweep covered more
  // than a turn, the magnet passed twice: use the next-highest peak whose run lies fully
  // inside, i.e. the highest bin of at least HALL_MIN_DEVIATION whose run touches neither end
  // (the first of equal ones). Every bin of a cut-off run has a cut-off run itself (its run
  // contains that one), so this is the same as trying the peaks highest first. If there is
  // none, the first run is kept.
  if (pending.sweepLength > YAW_TURN_NOMINAL && (lo == 0 || hi == n - 1)) {
    uint16_t best = n, bestLo = 0, bestHi = 0;
    for (uint16_t i = 0; i < n; ++i) {
      const uint16_t d = hallDeviation(i);
      if (d < HALL_MIN_DEVIATION || (best < n && d <= hallDeviation(best))) continue;
      uint16_t iLo, iHi;
      hallRun(i, iLo, iHi);
      if (iLo > 0 && iHi < n - 1) {
        best = i;
        bestLo = iLo;
        bestHi = iHi;
      }
    }
    if (best < n) {
      top = best;
      lo = bestLo;
      hi = bestHi;
    }
  }

  // Deviation-weighted centroid of the run, at the bins' centres.
  float weighted = 0;
  float total = 0;
  for (uint16_t i = lo; i <= hi; ++i) {
    const float d = hallDeviation(i);
    weighted += d * (i * HALL_BIN_STEPS + (HALL_BIN_STEPS - 1) / 2.0f);
    total += d;
  }
  pending.peak = pending.sweepStart + lround(weighted / total);
  pending.peakDev = hallDeviation(top);
  pending.peakWidth = static_cast<long>(hi - lo + 1) * HALL_BIN_STEPS;
  return true;
}

// ---------------------------------------------------------------------------------------------
// Motion

void setProfile(Motor& motor, float speed, float accel) {
  motor.stepper.setMaxSpeed(speed);
  if (accel != motor.accel) {
    motor.stepper.setAcceleration(accel);
    motor.accel = accel;
  }
}

// Make `motor` the moving axis of a new motion and energise it. If its coils were off, they
// hold its position for COIL_SETTLE_MS first (nothing else moves meanwhile: one motion at a
// time).
void beginMotion(uint16_t id, Motion motion, Motor& motor) {
  pending.id = id;
  pending.motion = motion;
  pending.motor = &motor;
  if (!motor.energised) {
    motor.stepper.hold();
    motor.energised = true;
    delay(COIL_SETTLE_MS);
  }
  lastPosMs = millis();
}

void haltNow(Motor& motor) { motor.stepper.setCurrentPosition(motor.stepper.currentPosition()); }

// Decelerate to a stop, like AccelStepper::stop(), but never past the motion's own target (so a
// tilt move never past the limits), and at once if the motor hasn't started stepping yet.
void decelerate(Motor& motor) {
  AccelStepper& s = motor.stepper;
  const float speed = s.speed();
  const long here = s.currentPosition();
  const long toStop = static_cast<long>(speed * speed / (2.0f * motor.accel)) + 1;
  long stopAt = here;
  if (speed > 0) stopAt = min(here + toStop, s.targetPosition());
  else if (speed < 0) stopAt = max(here - toStop, s.targetPosition());
  s.moveTo(stopAt);
}

void abortMotion(Abort reason) {
  pending.abort = reason;
  decelerate(*pending.motor);
}

void finish() {
  pending.id = 0;
  pending.motion = Motion::None;
  pending.abort = Abort::None;
  pending.ignoreSwitch = false;
  idleSinceMs = millis();
}

void finishOk() {
  replyOkPos(pending.id, *pending.motor);
  finish();
}

void finishErr(const __FlashStringHelper* code) {
  replyErrPos(pending.id, code, *pending.motor);
  finish();
}

void startTiltSeek() {
  setProfile(tilt, pending.fast, pending.accel);
  tilt.stepper.move(-pending.seekMax);
  pending.motion = Motion::TiltSeek;
  pending.ignoreSwitch = false;
  pending.sought = true;
}

// Back away until the switch has stayed released for the debounce time, then `clearance`
// further. Roller-lever switches release well past the point where they trip, so a fixed
// back-off distance can end with the switch still closed.
void startTiltBackoff() {
  pending.tripPos = tilt.stepper.currentPosition();
  pending.released = false;
  switchSeenUs = micros();  // it is pressed now, even if the debounced level hasn't caught up
  setProfile(tilt, pending.fast, pending.accel);
  tilt.stepper.move(pending.releaseMax);
  pending.motion = Motion::TiltBackoff;
  pending.ignoreSwitch = true;
}

void serviceTiltBackoff(bool done) {
  const bool released = micros() - switchSeenUs >= SWITCH_DEBOUNCE_US;
  if (!pending.released && released) {
    pending.released = true;
    pending.releasePos = tilt.stepper.currentPosition();
    tilt.stepper.moveTo(pending.releasePos + pending.clearance);
    return;
  }
  if (!done) return;
  if (!pending.released) return finishErr(F("SWITCH_STUCK"));
  // Homing that started on the pressed switch has no trip point yet: seek it now.
  if (!pending.sought) return startTiltSeek();
  // Probe slowly back toward the switch; it should trip near tripPos.
  setProfile(tilt, pending.slow, pending.accel);
  tilt.stepper.moveTo(pending.tripPos - pending.clearance);
  pending.motion = Motion::TiltProbe;
  pending.ignoreSwitch = false;
}

// The probe's contact is 0 if it lies where the seek tripped the switch, give or take: at most
// clearance/2 before it (the probe comes from the positive side). An earlier contact is noise
// or a switch that moved, and homing there would put 0 in the wrong place.
void finishTiltHome() {
  if (tilt.stepper.currentPosition() > pending.tripPos + pending.clearance / 2) {
    return finishErr(F("SWITCH_EARLY"));
  }
  const long release = pending.releasePos - pending.tripPos;
  tilt.origin = tilt.stepper.currentPosition();
  tilt.homed = true;
  beginReply(pending.id);
  Serial.print(F("OK pos=0 release="));
  Serial.println(release);
  finish();
}

void serviceYawSweep(bool done) {
  sampleHall();
  if (!done) return;
  if (!findHallPeak()) return finishErr(F("NO_MAGNET"));
  // Turn back to `takeup` before the peak, so the approach ends in the positive direction.
  yaw.stepper.moveTo(pending.peak - pending.takeup);
  pending.motion = Motion::YawBack;
}

void finishYawHome() {
  const long from = pending.peak - yaw.origin;
  yaw.origin = pending.peak;
  yaw.homed = true;
  beginReply(pending.id);
  Serial.print(F("OK pos=0 from="));
  Serial.print(from);
  Serial.print(F(" dev="));
  Serial.print(pending.peakDev);
  Serial.print(F(" width="));
  Serial.println(pending.peakWidth);
  finish();
}

void serviceMotion() {
  // Consume a latched trip first, so a touch stops tilt before its next step.
  noInterrupts();  // read-and-clear must not lose a trip that lands in between
  const bool touched = switchTouched;
  const bool filtered = switchTripped;
  switchTouched = switchTripped = false;
  interrupts();
  if (pending.motion == Motion::None) return;  // a touch while idle stops nothing

  Motor& motor = *pending.motor;
  const bool linearMove = pending.motion == Motion::Move || pending.motion == Motion::Jog;
  // A move that started on the pressed switch ignores it only until it has released.
  if (linearMove && pending.ignoreSwitch && micros() - switchSeenUs >= SWITCH_DEBOUNCE_US) {
    pending.ignoreSwitch = false;
  }
  bool tripped = false;
  if (&motor == &tilt && !pending.ignoreSwitch) {
    const bool level = tilt.stepper.distanceToGo() < 0 && readSwitchRaw();  // toward it
    tripped = level || (pending.motion == Motion::TiltSeek ? touched : filtered);
  }
  if (tripped) haltNow(motor);
  else motor.stepper.run();

  const bool done = !motor.stepper.isRunning();
  if (tripped && linearMove) {  // also while aborting: the host must learn that homed is lost
    tilt.homed = false;
    return finishErr(F("ENDSTOP"));
  }

  if (pending.abort != Abort::None) {
    if (done || tripped) finishErr(pending.abort == Abort::Stopped ? F("STOPPED") : F("LINK"));
    return;
  }

  switch (pending.motion) {
    case Motion::TiltSeek:
      if (tripped) startTiltBackoff();
      else if (done) finishErr(F("NO_SWITCH"));
      break;
    case Motion::TiltBackoff:
      serviceTiltBackoff(done);
      break;
    case Motion::TiltProbe:
      if (tripped) finishTiltHome();
      else if (done) finishErr(F("NO_SWITCH"));
      break;
    case Motion::YawSweep:
      serviceYawSweep(done);
      break;
    case Motion::YawBack:
      if (done) {
        yaw.stepper.moveTo(pending.peak);
        pending.motion = Motion::YawApproach;
      }
      break;
    case Motion::YawApproach:
      if (done) finishYawHome();
      break;
    case Motion::Move:
    case Motion::Jog:
      if (done) finishOk();
      break;
    case Motion::None:
      break;
  }
}

// ---------------------------------------------------------------------------------------------
// Commands

bool parseLong(const char* text, long& out) {
  char* end = nullptr;
  errno = 0;
  out = strtol(text, &end, 10);
  return end != text && *end == '\0' && errno != ERANGE;
}

// Argument checks: they look only at the arguments, and run before the BUSY check.

bool validProfile(long speed, long accel) {
  return speed > 0 && speed <= SPEED_MAX && accel > 0 && accel <= ACCEL_MAX;
}

bool within(long value, long max) { return value >= -max && value <= max; }

bool validDistance(long distance) { return distance > 0 && distance <= DISTANCE_MAX; }

bool argsLimits(const long* args) {
  return args[0] <= args[1] && within(args[0], POSITION_MAX) && within(args[1], POSITION_MAX);
}

// fast, slow, clearance, max, release_max, accel
bool argsHomeTilt(const long* args) {
  return validProfile(args[0], args[5]) && validProfile(args[1], args[5]) &&
         validDistance(args[2]) && validDistance(args[3]) && validDistance(args[4]) &&
         args[4] > args[2];
}

// speed, accel, max, takeup
bool argsHomeYaw(const long* args) {
  return validProfile(args[0], args[1]) && args[2] >= YAW_SWEEP_MIN &&
         args[2] <= YAW_SWEEP_MAX && validDistance(args[3]);
}

bool argsMove(const long* args) {
  return within(args[0], POSITION_MAX) && validProfile(args[1], args[2]);
}

bool argsJog(const long* args) {
  return within(args[0], DISTANCE_MAX) && validProfile(args[1], args[2]);
}

bool withinLimits(long target) { return target >= limits.minLimit && target <= limits.maxLimit; }

void cmdInfo(uint16_t id, Motor*, const long*) {
  beginReply(id);
  Serial.print(F("OK "));
  printIdentity();
}

void cmdStatus(uint16_t id, Motor*, const long*) {
  beginReply(id);
  Serial.print(F("OK yaw="));
  Serial.print(yaw.position());
  Serial.print(F(" tilt="));
  Serial.print(tilt.position());
  Serial.print(F(" yhomed="));
  Serial.print(yaw.homed);
  Serial.print(F(" thomed="));
  Serial.print(tilt.homed);
  Serial.print(F(" moving="));
  Serial.print(pending.motion == Motion::None ? F("none")
               : pending.motor == &tilt       ? F("tilt")
                                              : F("yaw"));
  Serial.print(F(" switch="));
  Serial.print(switchActive);
  Serial.print(F(" hall="));
  Serial.println(analogRead(PIN_HALL));
}

void cmdHall(uint16_t id, Motor*, const long*) {
  beginReply(id);
  Serial.print(F("OK hall="));
  Serial.println(analogRead(PIN_HALL));
}

void cmdStop(uint16_t id, Motor*, const long*) {
  if (pending.motion != Motion::None && pending.abort == Abort::None) {
    abortMotion(Abort::Stopped);
  }
  replyOk(id);
}

void cmdLimits(uint16_t id, Motor*, const long* args) {
  limits.minLimit = args[0];
  limits.maxLimit = args[1];
  replyOk(id);
}

// If the switch is pressed at the start, back off first, then seek and probe as usual: the
// probe's contact is checked against the seek's.
void cmdHomeTilt(uint16_t id, Motor*, const long* args) {
  tilt.homed = false;
  pending.fast = args[0];
  pending.slow = args[1];
  pending.clearance = args[2];
  pending.seekMax = args[3];
  pending.releaseMax = args[4];
  pending.accel = args[5];
  pending.sought = false;
  beginMotion(id, Motion::TiltSeek, tilt);
  if (switchPressed()) startTiltBackoff();
  else startTiltSeek();
}

void cmdHomeYaw(uint16_t id, Motor*, const long* args) {
  yaw.homed = false;
  pending.sweepLength = args[2];
  pending.takeup = args[3];
  setProfile(yaw, args[0], args[1]);
  beginMotion(id, Motion::YawSweep, yaw);
  pending.sweepStart = yaw.stepper.currentPosition();
  yaw.stepper.moveTo(pending.sweepStart + pending.sweepLength);
  startHallSampling();
  sampleHall();  // offset 0, before the first step
}

// Starts a move or jog. While the tilt switch is pressed only tilt moves away from it may
// start (one toward it is refused with PRESSED, homed kept); those ignore it until it has
// released (bounce included), then it is armed again. Every other tilt move stops on the first
// contact. Yaw moves don't look at the switch.
void startLinear(uint16_t id, Motion motion, Motor& motor, long target, long speed, long accel) {
  const bool onSwitch = &motor == &tilt && switchPressed();
  if (onSwitch && target < motor.position()) return replyErrPos(id, F("PRESSED"), motor);
  if (target == motor.position()) return replyOkPos(id, motor);
  setProfile(motor, speed, accel);
  motor.stepper.moveTo(target + motor.origin);
  beginMotion(id, motion, motor);
  pending.ignoreSwitch = onSwitch;
  if (onSwitch) switchSeenUs = micros();  // pressed now, even if updateSwitch hasn't seen it
}

void cmdMove(uint16_t id, Motor* motor, const long* args) {
  const long target = args[0];
  if (!motor->homed) return replyErr(id, F("NOT_HOMED"));
  if (motor == &tilt && !withinLimits(target)) return replyErr(id, F("LIMIT"));
  startLinear(id, Motion::Move, *motor, target, args[1], args[2]);
}

// Before tilt is homed its jogs are short (TILT_UNHOMED_JOG_MAX); once homed, the limits apply.
void cmdJog(uint16_t id, Motor* motor, const long* args) {
  const long delta = args[0];
  const long target = motor->position() + delta;
  if (motor == &tilt && !tilt.homed && !within(delta, TILT_UNHOMED_JOG_MAX)) {
    return replyErr(id, F("LIMIT"));
  }
  if (motor == &tilt && tilt.homed && !withinLimits(target)) return replyErr(id, F("LIMIT"));
  startLinear(id, Motion::Jog, *motor, target, args[1], args[2]);
}

// Which axis word a command takes as its first argument.
enum AxisArg : uint8_t { NO_AXIS = 0, YAW_AXIS = 1, TILT_AXIS = 2, ANY_AXIS = 3 };

struct Command {
  const char* name;  // in flash
  AxisArg axis;
  uint8_t arity;  // number arguments after the axis word
  bool allowedWhileMoving;
  bool (*valid)(const long* args);  // the argument check, or nullptr
  void (*run)(uint16_t id, Motor* motor, const long* args);
};

const char N_INFO[] PROGMEM = "INFO";
const char N_STATUS[] PROGMEM = "STATUS";
const char N_HALL[] PROGMEM = "HALL";
const char N_STOP[] PROGMEM = "STOP";
const char N_LIMITS[] PROGMEM = "LIMITS";
const char N_HOME[] PROGMEM = "HOME";
const char N_MOVE[] PROGMEM = "MOVE";
const char N_JOG[] PROGMEM = "JOG";
const char W_YAW[] PROGMEM = "YAW";
const char W_TILT[] PROGMEM = "TILT";

// A name may appear more than once, for different axes (HOME takes different arguments).
// The table is in flash; handleLine copies one entry at a time.
const Command COMMANDS[] PROGMEM = {
    {N_INFO, NO_AXIS, 0, true, nullptr, cmdInfo},
    {N_STATUS, NO_AXIS, 0, true, nullptr, cmdStatus},
    {N_HALL, NO_AXIS, 0, true, nullptr, cmdHall},
    {N_STOP, NO_AXIS, 0, true, nullptr, cmdStop},
    {N_LIMITS, TILT_AXIS, 2, false, argsLimits, cmdLimits},
    {N_HOME, TILT_AXIS, 6, false, argsHomeTilt, cmdHomeTilt},
    {N_HOME, YAW_AXIS, 4, false, argsHomeYaw, cmdHomeYaw},
    {N_MOVE, ANY_AXIS, 3, false, argsMove, cmdMove},
    {N_JOG, ANY_AXIS, 3, false, argsJog, cmdJog},
};

void handleLine(char* text) {
  constexpr uint8_t MAX_ARGS = 6;
  constexpr uint8_t MAX_TOKENS = MAX_ARGS + 1;  // the axis word, then numbers
  char* save = nullptr;
  const char* idText = strtok_r(text, " ", &save);
  const char* name = strtok_r(nullptr, " ", &save);
  long id = 0;
  if (!idText || !name || !parseLong(idText, id) || id < 1 || id > 65535) {
    return replyErr(0, F("SYNTAX"));
  }

  const char* tokens[MAX_TOKENS];
  uint8_t count = 0;
  for (const char* tok; (tok = strtok_r(nullptr, " ", &save));) {
    if (count == MAX_TOKENS) return replyErr(id, F("ARG"));
    tokens[count++] = tok;
  }

  bool known = false;
  for (const Command& entry : COMMANDS) {
    Command command;
    memcpy_P(&command, &entry, sizeof command);
    if (strcmp_P(name, command.name) != 0) continue;
    known = true;
    Motor* motor = nullptr;
    uint8_t first = 0;
    if (command.axis != NO_AXIS) {
      if (count == 0) continue;
      if (strcmp_P(tokens[0], W_YAW) == 0 && (command.axis & YAW_AXIS)) motor = &yaw;
      else if (strcmp_P(tokens[0], W_TILT) == 0 && (command.axis & TILT_AXIS)) motor = &tilt;
      else continue;  // another entry may take this axis
      first = 1;
    }
    if (count - first != command.arity) return replyErr(id, F("ARG"));
    long args[MAX_ARGS];
    for (uint8_t i = 0; i < command.arity; ++i) {
      if (!parseLong(tokens[first + i], args[i])) return replyErr(id, F("ARG"));
    }
    if (command.valid && !command.valid(args)) return replyErr(id, F("ARG"));
    if (pending.motion != Motion::None && !command.allowedWhileMoving) {
      return replyErr(id, F("BUSY"));
    }
    return command.run(id, motor, args);
  }
  replyErr(id, known ? F("ARG") : F("UNKNOWN"));  // ARG: a missing or unknown axis
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
    if (pending.abort == Abort::None && now - lastRxMs > LINK_TIMEOUT_MS) {
      abortMotion(Abort::Link);
    }
    if (now - lastPosMs >= POS_REPORT_MS) {
      lastPosMs = now;
      Serial.print(pending.motor == &tilt ? F("! POS axis=tilt pos=") : F("! POS axis=yaw pos="));
      Serial.println(pending.motor->position());
    }
  } else if ((yaw.energised || tilt.energised) && now - idleSinceMs >= COIL_OFF_MS) {
    yaw.stepper.disableOutputs();
    tilt.stepper.disableOutputs();
    yaw.energised = tilt.energised = false;
  }
}

}  // namespace

ISR(PCINT0_vect) {
  const bool pressed = readSwitchRaw();
  if (pressed || !switchLevelSeen) switchTouched = true;  // a closing edge happened
  if (pressed) switchTripped = true;  // still pressed on entry: not a noise spike
  switchLevelSeen = pressed;
}

void setup() {
  yaw.stepper.disableOutputs();  // coils off until the first motion
  tilt.stepper.disableOutputs();
  pinMode(PIN_TILT_SWITCH, INPUT_PULLUP);

  Serial.begin(SERIAL_BAUD);

  switchRaw = switchActive = switchLevelSeen = readSwitchRaw();
  *digitalPinToPCMSK(PIN_TILT_SWITCH) |= _BV(digitalPinToPCMSKbit(PIN_TILT_SWITCH));
  PCIFR = _BV(digitalPinToPCICRbit(PIN_TILT_SWITCH));  // drop a change seen while setting up
  *digitalPinToPCICR(PIN_TILT_SWITCH) |= _BV(digitalPinToPCICRbit(PIN_TILT_SWITCH));
  lastRxMs = millis();

  Serial.print(F("! READY "));
  printIdentity();
}

void loop() {
  serviceMotion();
  pollSerial();
  serviceMotion();
  updateSwitch();
  serviceTimers();
}
