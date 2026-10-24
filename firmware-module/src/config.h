// Hardware wiring and fixed firmware constants of the scan module. See docs/protocol-module.md.
#pragma once

#include <Arduino.h>

#define FIRMWARE_VERSION "1.0.0"
#define PROTOCOL_VERSION 1

// Pins: ULN2003 inputs IN1..IN4 of each 28BYJ-48.
constexpr uint8_t YAW_IN[4] = {2, 3, 4, 5};
constexpr uint8_t TILT_IN[4] = {6, 7, 8, 9};
constexpr uint8_t PIN_TILT_SWITCH = 10;  // switch to GND, internal pull-up; pin-change interrupt
constexpr uint8_t PIN_HALL = A0;         // KY-024 analog output

// Tilt switch: C → GND, NO → pin, so the input reads LOW while pressed. If it is rewired
// normally-closed (C + NC), set HIGH: the input then also reads "pressed" when a wire breaks,
// which fails safe.
constexpr uint8_t SWITCH_ACTIVE_LEVEL = LOW;
// Settling time before a change of the switch's level is reported or used for decisions.
// Stopping does not wait for it: the interrupt reacts to the very first contact.
constexpr uint32_t SWITCH_DEBOUNCE_US = 2000;

// Motor wiring. Tilt: positive moves go away from the switch. Yaw: positive turns the head
// counter-clockwise seen from above, the direction HOME YAW turns. Flip one if its motor turns
// the wrong way. (In 4-wire mode AccelStepper's setPinsInverted inverts the coil levels, not
// the direction, so the firmware reverses the coil sequence instead.)
constexpr bool TILT_INVERT = false;
constexpr bool YAW_INVERT = false;

// Both motors' coils are switched off this long after a motion ends: the gearboxes hold the
// load, and no heat reaches the specimen.
constexpr uint32_t COIL_OFF_MS = 300;
// A motor whose coils were off is energised at the pattern of its held position this long
// before its first step, so the rotor has settled onto it.
constexpr uint32_t COIL_SETTLE_MS = 10;

// Host link
constexpr uint32_t SERIAL_BAUD = 115200;
constexpr uint8_t LINE_MAX = 64;  // including the terminator
constexpr uint32_t LINK_TIMEOUT_MS = 2000;
constexpr uint32_t POS_REPORT_MS = 100;

// Limits on host-supplied values (half-steps/s, half-steps/s²)
constexpr long SPEED_MAX = 1000;
constexpr long ACCEL_MAX = 4000;
// Positions and distances (half-steps). Bounding them keeps every sum the firmware forms far
// from overflowing. Absolute targets and limits: about 245 turns either way, room for any
// number of scan rings. Distances (a jog, a homing distance, the take-up): about 5 turns.
constexpr long POSITION_MAX = 1000000;
constexpr long DISTANCE_MAX = 20000;
// Tilt jogs before tilt is homed: at most about 15° (4075.77 half-steps per turn), since the
// soft limits that keep the specimen off the lens only apply once homed.
constexpr long TILT_UNHOMED_JOG_MAX = 170;

// Yaw homing: the hall sensor is sampled once at every position of the sweep, the first and
// the last included, and averaged per bin of HALL_BIN_STEPS half-steps, one byte (ADC/4) per
// bin. HALL_BINS bins bound the sweep to YAW_SWEEP_MAX half-steps, about 1.3 turns of a
// 28BYJ-48 (~4076 half-steps per turn); it must cover at least HALL_MIN_BINS bins.
constexpr uint8_t HALL_BIN_STEPS = 8;
constexpr uint16_t HALL_BINS = 672;
constexpr long YAW_SWEEP_MAX = static_cast<long>(HALL_BINS) * HALL_BIN_STEPS;  // 5376
constexpr uint8_t HALL_MIN_BINS = 2;
constexpr long YAW_SWEEP_MIN = static_cast<long>(HALL_MIN_BINS) * HALL_BIN_STEPS;  // 16
constexpr long YAW_TURN_NOMINAL = 4076;  // half-steps; only decides whether a sweep saw two passes
constexpr uint8_t HALL_HISTOGRAM_BUCKETS = 64;
constexpr uint16_t HALL_MIN_DEVIATION = 40;  // ADC counts; a smaller peak is NO_MAGNET
