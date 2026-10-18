// Hardware wiring and fixed firmware constants. See docs/wiring.md.
#pragma once

#include <Arduino.h>

#define FIRMWARE_VERSION "1.0.0"
#define PROTOCOL_VERSION 1

// Pins
constexpr uint8_t PIN_STEP = 3;
constexpr uint8_t PIN_DIR = 4;
constexpr uint8_t PIN_ENABLE = 5;    // TMC2209 EN, active low
constexpr uint8_t PIN_ENDSTOP = 6;   // switch to GND, internal pull-up
constexpr uint8_t PIN_UART_RX = 10;  // TMC2209 PDN_UART (direct)
constexpr uint8_t PIN_UART_TX = 11;  // TMC2209 PDN_UART (through 1 kΩ)

// Endstop: the switch is wired normally-closed to GND, so the input reads LOW while the
// carriage is clear and HIGH when pressed or when a wire breaks (fails safe).
constexpr uint8_t ENDSTOP_ACTIVE_LEVEL = HIGH;
constexpr uint32_t ENDSTOP_DEBOUNCE_US = 500;

// Positive moves go away from the switch. Flip if the motor is wired the other way round.
constexpr bool INVERT_DIRECTION = false;

// TMC2209
constexpr float DRIVER_RSENSE_OHM = 0.11f;  // common TMC2209 modules (BTT, FYSETC)
constexpr uint8_t DRIVER_ADDRESS = 0;       // MS1 = MS2 = GND
constexpr uint32_t DRIVER_UART_BAUD = 57600;
constexpr uint16_t MICROSTEPS = 16;
constexpr uint8_t TMC2209_VERSION = 0x21;

// Host link
constexpr uint32_t SERIAL_BAUD = 115200;
constexpr uint8_t LINE_MAX = 64;  // including the terminator
constexpr uint32_t LINK_TIMEOUT_MS = 2000;
constexpr uint32_t POS_REPORT_MS = 100;
constexpr uint32_t DRIVER_CHECK_MS = 1000;

// Limits on host-supplied values
constexpr uint16_t CURRENT_MIN_MA = 100;
constexpr uint16_t CURRENT_MAX_MA = 1500;
constexpr float SPEED_MAX = 4000.0f;   // microsteps/s (10 mm/s at 400 steps/mm)
constexpr float ACCEL_MAX = 40000.0f;  // microsteps/s²
