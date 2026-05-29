"""
hw_test_criteria.py  –  Pass/fail limits for Stage 1 analog channel readings.

Channel-ID map is taken from the HW-test firmware on the B-sample branch
(feature/hw_testing_B2_sample):

  sf_hal_board/analog_measurements_hal/analog_measurements.h
      ── measurements_t enum (IDs 0..21)
  sf_app/HW_testing/hw_testing.c
      ── meas_report_pwm_ai_t   (IDs 22..27)
      ── meas_report_i2c_t      (IDs 28..29)
      ── meas_report_added_t    (IDs 30..39)

Note about HW_TEST_ALL_ADC_MEASUREMENTS (0x03): the firmware substitutes the
on-wire channel ID before sending the analog report:
    PUMP_SNS1  (11) → PWM_PUMP_HSSWITCH1_TEMPERATURE (32)
    PUMP_SNS2  (12) → PWM_PUMP_HSSWITCH2_TEMPERATURE (34)
    EXT_TEMP1..4 (7..10) → ADC_EXT_TEMP_1..4 (35..38)
That is why the limits below for those magnitudes are placed at the
"reported" IDs, not the internal enum IDs.
"""

from typing import Optional, Tuple, Set


# ── Hardware version → board info ─────────────────────────────────────────
# HW_VERSION is reported on ANLG[0] (channel 0) of HW_TEST_ALL_ADC_MEASUREMENTS.
# It is an integer 0–15 encoded by an on-board voltage divider. The mapping
# from index to board sample is StarkFuture's convention:
#
#   index   board     external NTCs populated    notes
#   -----   -------   -------------------------   -------------------------
#   3       B1        2  (EXT_TEMP1, EXT_TEMP2)   current bench sample
#                                                 (board reports HW_VERSION=3).
#                                                 PM-temp readings on B1 use
#                                                 the same legacy duty-decode
#                                                 chain (Infineon 1EDI3035AS)
#                                                 which gives valid readings
#                                                 when the NTC is correctly
#                                                 placed in parallel with the
#                                                 909 Ω pulldown.
#
# Add other versions here when you confirm them (TBD: A0, A1, B0, B2, …).

HW_VERSION_NAMES: dict[int, str] = {
    3: "B1",
}

# Channels whose limit check should be SKIPPED on a given board because the
# corresponding sensor is not populated on that revision. Skipped channels are
# still reported in the xlsx; they just don't contribute a FAIL verdict.
SKIP_CHANNELS_BY_HW_VERSION: dict[int, Set[int]] = {
    # B1: EXT_TEMP3 / EXT_TEMP4 (the firmware iterates EXT_TEMP1..4 but only
    # the first two are physically present on B1).
    3: {37, 38},
}

# Active HW version — set by hw_test_runner at campaign start (auto-detect)
# or via the CLI --hw-version override. None means "no skips" (legacy).
_ACTIVE_HW_VERSION: Optional[int] = None


def set_active_hw_version(version: Optional[int]) -> None:
    """Tell the criteria module which HW version we're running against.
    Called by the runner once it has read ANLG[0] from the board."""
    global _ACTIVE_HW_VERSION
    _ACTIVE_HW_VERSION = version


def active_hw_version() -> Optional[int]:
    return _ACTIVE_HW_VERSION


def active_board_name() -> str:
    if _ACTIVE_HW_VERSION is None:
        return "unknown"
    return HW_VERSION_NAMES.get(_ACTIVE_HW_VERSION,
                                 f"HW_VERSION={_ACTIVE_HW_VERSION}")


# ── Per-test channel relevance ────────────────────────────────────────────
# The firmware always streams a fixed set of ANLG[] channels for each test,
# but some of those channels are "carry-through" defaults that are NOT
# actually measured by that particular test (e.g. test 0x05 emits the pump
# HS-switch temps as 0 °C even though it only measures the PWM-driver
# isolated ADCs). Python should only apply its limit check to the channels
# this test actively measures — everything else should be reported but not
# limit-checked.
#
# Format: { test_key: set_of_channel_ids_to_limit_check }
# If a test is not listed here, ALL channels with defined limits are checked
# (the legacy behaviour).
TEST_RELEVANT_CHANNELS: dict[str, set] = {
    # 0x03 — full main-ADC scan; checks everything the firmware reports
    # (HW_VERSION, currents, DC link, AC voltages, temps, supplies, encoder
    # bias, MCU internals, pump HS temps via remap, ext temps via remap).
    "HW_TEST_ALL_ADC_MEASUREMENTS": {
        1, 2, 3, 4, 13, 14, 15, 16, 17, 18, 19, 20, 21,
        32, 34, 35, 36, 37, 38,
    },

    # 0x04 — MCU internal measurements only
    "HW_TEST_MCU_INTER_MEASUREMENTS": {
        18, 19, 20, 21,
    },

    # 0x05 — gate-driver isolated ADC scan: only PCB_TEMP0/1 + power-module
    # phase temperatures. Pump HS-switch temps, ext temps and pump speed
    # are streamed as default zeros in this test's frame buffer and must
    # not be limit-checked here.
    "HW_TEST_PWM_DRIVERS_USER_MEASUREMENTS": {
        22, 23, 24, 25, 26,
    },

    # 0x2F — pump auto test: pump HS-switch currents (peak, ON phase) + temps
    # + tach. The pump coil current is the sum of HS1 (31) + HS2 (33).
    "HW_TEST_PUMP_AUTO": {
        31, 32, 33, 34, 39,
    },
}


# ── Manual-setup instructions ─────────────────────────────────────────────
# Tests that need the operator to wire the MCU's DAC outputs into a
# specific isolated-input pin pair before the test runs. Keyed by test key.
# The string is displayed verbatim by the runner just before SET_TEST is
# sent, followed by an Enter-to-continue prompt.
MANUAL_SETUP_INSTRUCTIONS: dict[str, str] = {
    "HW_TEST_LEDS":
        "Visually verify LED1 and LED2 on the PCBA. They should blink "
        "continuously while this test is running. Press ENTER to start the "
        "test, then watch the LEDs. The firmware reports completion; "
        "operator confirms the LEDs blinked.",
    "HW_TEST_ENC_SINCOS_SIN_LOOPBACK":
        "Connect DAC1 (MCU pin PA4) to encoder SIN+ analog input "
        "and DAC2 (PA5) to encoder SIN- analog input.",
    "HW_TEST_ENC_SINCOS_COS_LOOPBACK":
        "Connect DAC1 (MCU pin PA4) to encoder COS+ analog input "
        "and DAC2 (PA5) to encoder COS- analog input.",
    "HW_TEST_POWER_UNIPLR_V_LOOPBACK":
        "Connect DAC1 (MCU pin PA4) to the DC-link voltage-sense "
        "isolated input (unipolar conditioning chain).",
    "HW_TEST_POWER_BIPLR_V_LOOPBACK":
        "Connect DAC1 (MCU pin PA4) to UV/WV phase voltage-sense "
        "isolated input (+ leg) and DAC2 (PA5) to the (- leg) "
        "(bipolar conditioning chain).",
}


# ── Channel name lookup ────────────────────────────────────────────────────
ANLG_CHANNEL_NAMES: dict[int, str] = {
    # Internal-ADC group (firmware measurements_t)
    0:  "HW_VERSION",
    1:  "I_Ph_U",
    2:  "I_Ph_V",
    3:  "I_Ph_W",
    4:  "DC_LINK",
    5:  "UV_VOLTAGE",
    6:  "WV_VOLTAGE",
    # 7..10  EXT_TEMP1..4 are remapped on the wire → see 35..38 below
    # 11,12  PUMP_SNS1/2   are remapped on the wire → see 32, 34 below
    13: "PCB_TEMP",
    14: "SUPPLY_28V",
    15: "SUPPLY_5V",
    16: "ENC_SIN",
    17: "ENC_COS",
    18: "VDD_CORE",
    19: "MCU_TEMP",
    20: "VREF_INT",
    21: "VBAT_INT",

    # PWM-driver isolated ADC group (meas_report_pwm_ai_t)
    22: "PCB_TEMP0",
    23: "PCB_TEMP1",
    24: "POWER_MODULE_U_TEMP",
    25: "POWER_MODULE_V_TEMP",
    26: "POWER_MODULE_W_TEMP",
    # 27 PMW_DCLINK — obsolete, kept for legacy logs

    # I2C sensor group
    28: "I2C_AMBIENT_TEMP",
    29: "I2C_AMBIENT_HUMIDITY",

    # "Added" group (meas_report_added_t)
    30: "PCB_TEMP3",
    31: "PUMP_HS1_CURRENT",
    32: "PUMP_HS1_TEMP",
    33: "PUMP_HS2_CURRENT",
    34: "PUMP_HS2_TEMP",
    35: "EXT_TEMP1",
    36: "EXT_TEMP2",
    37: "EXT_TEMP3",
    38: "EXT_TEMP4",
    39: "PUMP_SPEED_TACH",
}

# ── Pass/fail limits ───────────────────────────────────────────────────────
# Format: { channel_id: (min_value, max_value, unit, description) }
# Use None for a bound that should not be checked.
ANLG_LIMITS: dict[int, Tuple[Optional[float], Optional[float], str, str]] = {
    # — Phase currents (idle, no motor attached) ————————————————————————
    1:  (-5.0,   5.0,   "A",  "Phase U current (idle)"),
    2:  (-5.0,   5.0,   "A",  "Phase V current (idle)"),
    3:  (-5.0,   5.0,   "A",  "Phase W current (idle)"),

    # — DC link (bench supply nominal; tune to your setup) —————————————————
    4:  (None,  None,   "V",  "DC-link voltage"),

    # — PCB temperature from MCU ADC ——————————————————————————————————————
    13: (10.0,  60.0,   "°C", "PCB temperature (MCU ADC)"),

    # — LV main supply: 28 V nominal on B-sample (was 12 V on A-sample) ————
    14: (25.0,  31.0,   "V",  "LV 28 V supply rail"),

    # — 5 V rail ————————————————————————————————————————————————————————
    15: (4.75,  5.25,   "V",  "5 V supply rail"),

    # — Encoder sin/cos front-end (bias-pin idle voltage) ———————————————————
    16: (None,  None,   "V",  "Encoder SIN (idle)"),
    17: (None,  None,   "V",  "Encoder COS (idle)"),

    # — MCU internals (only reported by HW_TEST_MCU_INTER_MEASUREMENTS 0x04) ——
    18: (1.30,  1.40,   "V",  "MCU VDDCORE"),
    19: (10.0,  60.0,   "°C", "MCU core temperature"),
    20: (3.00,  3.60,   "V",  "MCU VREFINT"),
    21: (2.80,  3.60,   "V",  "MCU VBAT"),

    # — PWM-driver isolated ADCs ——————————————————————————————————————————
    22: (10.0,  60.0,   "°C", "PCB temperature 0 (PWM-AI)"),
    23: (10.0,  60.0,   "°C", "PCB temperature 1 (PWM-AI)"),
    24: (10.0,  60.0,   "°C", "Power module U temperature"),
    25: (10.0,  60.0,   "°C", "Power module V temperature"),
    26: (10.0,  60.0,   "°C", "Power module W temperature"),

    # — Pump HS-switch current/temperature (B-sample pump driver) —————————————
    32: (10.0,  60.0,   "°C", "Pump HS-switch 1 temperature"),
    34: (10.0,  60.0,   "°C", "Pump HS-switch 2 temperature"),

    # — External NTCs (special — external fixed resistor on the bench, NOT
    #    a real thermistor, so the equivalent temperature reading is very
    #    low and constant. Tighten to a narrow [0, 10] °C window so we
    #    detect proper resistor presence without false-failing on what
    #    looks like "cold" to the firmware) ————————————————————————————————
    35: (0.0,   10.0,   "°C", "External temperature 1 (fixed-resistor bench fixture)"),
    36: (0.0,   10.0,   "°C", "External temperature 2 (fixed-resistor bench fixture)"),
    37: (0.0,   10.0,   "°C", "External temperature 3 (fixed-resistor bench fixture)"),
    38: (0.0,   10.0,   "°C", "External temperature 4 (fixed-resistor bench fixture)"),
}


# ── Public API ─────────────────────────────────────────────────────────────

def channel_name(channel_id: int) -> str:
    """Return a human-readable name for *channel_id*."""
    return ANLG_CHANNEL_NAMES.get(channel_id, f"ANLG[{channel_id}]")


def check_analog(channel_id: int, value: float) -> Tuple[bool, str]:
    """
    Check an analog channel reading against the defined limits, taking the
    active HW version into account.

    Returns
    -------
    (passed, message)
        passed  – True if value is within limits, no limit is defined, or
                  the channel is marked "not populated" on the active board.
        message – Short human-readable verdict string.
    """
    name = channel_name(channel_id)

    # HW-version-aware skip: channels not populated on this board are reported
    # but not limit-checked.
    if (_ACTIVE_HW_VERSION is not None
            and channel_id in SKIP_CHANNELS_BY_HW_VERSION.get(
                _ACTIVE_HW_VERSION, set())):
        return (True,
                f"{name} = {value:.4g}  SKIPPED  "
                f"[not populated on {active_board_name()}]")

    if channel_id not in ANLG_LIMITS:
        return True, f"{name} = {value:.4g}  [no limit defined]"

    lo, hi, unit, desc = ANLG_LIMITS[channel_id]

    if lo is not None and value < lo:
        return (False,
                f"{name} = {value:.4g} {unit}  FAIL  (< min {lo} {unit})  [{desc}]")
    if hi is not None and value > hi:
        return (False,
                f"{name} = {value:.4g} {unit}  FAIL  (> max {hi} {unit})  [{desc}]")

    bounds = f"[{lo if lo is not None else '-∞'}, {hi if hi is not None else '+∞'}] {unit}"
    return (True,
            f"{name} = {value:.4g} {unit}  PASS  {bounds}  [{desc}]")
