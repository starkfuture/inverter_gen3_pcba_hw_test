# 3-Phase test catalog + protocol cheat-sheet

Companion to SKILL.md. Read this when adding a new test, extending a sequence,
or decoding a CAN frame by hand.

## Phase 1 — Self auto-verification (16 tests)

Sequence name: `B0_SELF` / `B1_SELF` / `B2_SELF` (all aliased to the same list
on B-sample; `B_SELF` works too). Dispatched in `hw_test_runner.py` ~line 689.
Returned by `HwTestProtocol.sfHwTestProtocolGetBSampleSelfTestsList()`.

| # | Code | Test key | Timeout (ms) | Notes |
|---|---|---|---|---|
| 1 | 0x02 | `HW_TEST_SUPPLY_VOLTAGES` | 500 | |
| 2 | 0x03 | `HW_TEST_ALL_ADC_MEASUREMENTS` | 500 | Streams ANLG[] for every channel; PASS only if all channels in `ANLG_LIMITS` |
| 3 | 0x04 | `HW_TEST_MCU_INTER_MEASUREMENTS` | 500 | VDD_CORE, MCU_TEMP, VREF_INT, VBAT |
| 4 | 0x05 | `HW_TEST_PWM_DRIVERS_USER_MEASUREMENTS` | 500 | Isolated ADC group (PCB_TEMP0..2, PM temps) |
| 5 | 0x08 | `HW_TEST_MEASUREMENTS_DIAGNOSTICS` | 1000 | |
| 6 | 0x0C | `HW_TEST_ALL_PWM_SUPPLIES` | 1500 | |
| 7 | 0x10 | `HW_TEST_ALL_DRIVERS_STATUS` | 3500 | |
| 8 | 0x14 | `HW_TEST_ALL_DRIVERS_SETTING` | 3500 | |
| 9 | 0x18 | `HW_TEST_ALL_DRIVERS_FREQUENCY` | 4000 | Firmware freq sweep (no scope check in this phase) |
| 10 | 0x19 | `HW_TEST_ALL_DRIVERS_DUTY` | 4000 | Firmware duty sweep |
| 11 | 0x1E | `HW_TEST_CAN_ECHO` | 1000 | Runner sends ECHO request (config `STIMULUS_DELAY_MS=50`) |
| 12 | 0x21 | `HW_TEST_UART_CHECK_LOOPBACK` | 1000 | Needs TX-RX jumper on fixture |
| 13 | 0x22 | `HW_TEST_I2C_TEMP_HUMID_AUTO_TX` | 1000 | |
| 14 | 0x23 | `HW_TEST_SPI_FLASH_MEM_AUTO_TX` | 1000 | |
| 15 | 0x29 | `HW_TEST_EXTRA_GPIOs_LOOPBACK` | 500 | Needs GPIO jumper on fixture |
| 16 | 0x2F | `HW_TEST_PUMP_AUTO` | 5000 | FAIL expected if no pump |

## Phase 2 — Power modules (1 test, 6 switches × 9 setpoints)

| Code | Test key |
|---|---|
| 0x1B | `HW_TEST_ALL_POWER_MODULE` |

Driver: `code/run_power_module_sweep.py` (helpers `_start_pm_test`,
`_stop_pm_test`, `_pin_setpoint`, `measure_pm_setpoint`, `expected_duty_pct`,
`recompute_verdict`); orchestration in `code/pm_step_session.py` and
`code/verify_pcba.py::run_power_module_phase`.

Default sweep: `freq [10, 20, 30] kHz × duty [25, 50, 75] %` at 1 µs dead-band
→ **9 setpoints/switch × 6 switches = 54 measurements**. Switch list:
`["UTOP", "UBOT", "VTOP", "VBOT", "WTOP", "WBOT"]`.

## Phase 3 — Operator-verified (5 tests)

Sequence name: `B<x>_LOOPBACK` (alias kept; the set is "operator-verified").
Returned by `HwTestProtocol.sfHwTestProtocolGetBSampleOperatorVerifiedTestsList()`
(legacy alias `sfHwTestProtocolGetBSampleLoopbackTestsList`). Set:
`BSAMPLE_OPERATOR_VERIFIED_KEYS`.

| Code | Test key | Operator prompt (`MANUAL_SETUP_INSTRUCTIONS`) |
|---|---|---|
| 0x01 | `HW_TEST_LEDS` | Visually verify LED1/LED2 blink |
| 0x25 | `HW_TEST_ENC_SINCOS_SIN_LOOPBACK` | DAC1 (PA4) → SIN+, DAC2 (PA5) → SIN− |
| 0x26 | `HW_TEST_ENC_SINCOS_COS_LOOPBACK` | DAC1 (PA4) → COS+, DAC2 (PA5) → COS− |
| 0x2A | `HW_TEST_POWER_UNIPLR_V_LOOPBACK` | DAC1 (PA4) → DC-link voltage-sense isolated input |
| 0x2B | `HW_TEST_POWER_BIPLR_V_LOOPBACK` | DAC1 → UV/WV + leg, DAC2 → − leg |

## Protocol byte layout (8-byte standard CAN frame, ID 0x100)

```
data[0]   = command code           (see table below)
data[1]   = object info            (((obj_type & 0x7) << 5) | (obj_instance & 0x1F))
data[2:6] = 4-byte value           (FLOAT little-endian, OR UINT32 big-endian — depends on cmd)
data[6:8] = flags                  (2 bytes big-endian)
```

**Command codes** (hw_test_comm_commands_t enum in `sf_app/HW_testing/hw_testing.c`):

| Cmd | Code | Object type | Value semantics |
|---|---|---|---|
| NOP | 0x00 | EMPTY | — |
| SET_TEST_ENV | 0x01 | UINT32 (BE) | bit0 = clear reboot, bit1 = report enable |
| SET_TEST | 0x02 | UINT32 (BE) | `hw_test_type_t` code |
| ECHO | 0x03 | BUFFER | 4-byte pattern |
| SET_PWM_FREQ | 0x04 | FLOAT (LE) | kHz |
| SET_PWM_DUTY | 0x05 | FLOAT (LE) | per-unit 0.0–1.0 |
| SET_DIG_OUT | 0x06 | UINT32 (BE) | output state |
| SET_PWM_DT | 0x07 | FLOAT (LE) | ns |
| SET_PWM_PULSES | 0x08 | UINT32 (BE) | pulse count |
| EN_DIS_PHASE | 0x09 | UINT32 (BE) | 0/1, object index 0 = all phases, 1/2/3 = U/V/W |
| SET_PUMP_DUTY | 0x0A | FLOAT (LE) | per-unit |
| SET_PUMP_FREQ | 0x0B | FLOAT (LE) | kHz |

**Response codes** (returned by board on the same ID):

| Code | Response | Payload |
|---|---|---|
| 0x80 | RSPN_NONE | — |
| 0x81 | TEST_STATUS | test code + flags (BT/RN/V/V+/S/S+) |
| 0x82 | ANALOG | channel ID + value + flags (incl. OUT_OF_RANGE bit, EXT_ID_BIT0/1 for extended channel IDs) |
| 0x83 | ECHO | 4-byte echo of the ECHO request |
| 0x84 | BUFFER | user buffer |

**TEST_STATUS flag bits** (`flags` byte in 0x81):
- 0x01 BT — boot
- 0x02 RN — running
- 0x04 V — verification attempted
- 0x08 V+ — verification passed (PASS indicator)
- 0x10 S — self-test attempted
- 0x20 S+ — self-test passed (PASS indicator)

**Pass criterion** (`config.PASS_REQUIRED_OK_FRAMES = 3`): a test PASSes only if
the **last 3** TEST_STATUS frames received before timeout/early-exit all carry
either V+ or S+. Implemented in `hw_test_runner._evaluate_firmware_flags()`.

## ANLG channel ID extension

Standard channel IDs are 5 bits (0–31). Extended IDs are encoded in the ANLG
response's flags byte:
- `flags & 0x02` (EXT_ID_BIT0) → `channel_id += 0x20`
- `flags & 0x04` (EXT_ID_BIT1) → `channel_id += 0x40`

After extension, channel IDs map to names in `hw_test_criteria.ANLG_CHANNEL_NAMES`
(e.g. 13=PCB_TEMP, 14=SUPPLY_28V, 22=PCB_TEMP0, 32=PUMP_HS1_TEMP,
35=EXT_TEMP1, etc.).

## HW-version awareness

Channel 0 of `HW_TEST_ALL_ADC_MEASUREMENTS` (0x03) is `HW_VERSION`. Currently:

| HW_VERSION | Name | Notes |
|---|---|---|
| 3 | B1 | 2 external NTCs populated; channels 37/38 (EXT_TEMP3/4) are skipped in limit checks |

Override via `--hw-version`, or auto-detected from the first ANLG[0] reading.
See `hw_test_criteria.SKIP_CHANNELS_BY_HW_VERSION`.

## Where to add a new test

1. **Firmware test ID** — add to `hw_protocol.HwTestProtocol.sfHwTestProtocolGetTestsDictionary()` (one line: `"HW_TEST_<NAME>": (0x<code>, "<description>")`).
2. **Sequence membership** — append the `(key, stimulus_type, stimulus_value, timeout_ms)` tuple to the appropriate sequence list:
   - Self-only: nothing extra needed — it'll inherit from
     `sfHwTestProtocolGetMinimumBSampleTestsList()` minus
     `BSAMPLE_OPERATOR_VERIFIED_KEYS`.
   - Operator-verified: add the key to `BSAMPLE_OPERATOR_VERIFIED_KEYS` AND
     add a `MANUAL_SETUP_INSTRUCTIONS` entry in `hw_test_criteria.py`.
3. **Analog limits** — if the test reports new channels, add them to
   `ANLG_LIMITS` in `hw_test_criteria.py` and (if needed) to the relevant
   `TEST_RELEVANT_CHANNELS[<code>]` set so the runner only limit-checks the
   channels that test is supposed to drive.
4. **Plan doc** — add a `5.x HW_TEST_<NAME> (0x<code>)` section in
   `plan/InvGen3_HW_PCBA_TestByTest_Plan.docx`, then regenerate the PDF
   (`SaveAs ..., 17`).
