# Bench bring-up lessons (Phase 2 / HW_TEST_ALL_POWER_MODULE 0x1B)

These are the non-obvious behaviours discovered when bringing Phase 2 up on real
hardware. Each one wasted real bench time; they're listed so the next person
doesn't repeat them. The fixes are already baked into the tools — the notes
explain **why** so the code makes sense and so you know what to look for if
something deviates.

## 1. EN_DIS_PHASE during ALL_POWER_MODULE is disruptive — don't send it

**Symptom:** Gate latches high (V-high ≈ V-low ≈ +18 V, no switching) at every
setpoint after the first. Or stuck low (~−3 V, off) when probes were re-init'd.

**Cause:** The firmware's `test_do_all_power_modules()`
(`sf_app/HW_testing/hw_testing.c` ~line 3937) reads `pwm_en_phase_u/v/w_forced`
every cycle and only toggles the driver-enable GPIOs on a *transition*. Sending
`EN_DIS_PHASE` (cmd 0x09) writes those variables and causes an unintended
toggle, putting the drivers into an inconsistent state mid-test.

**Fix:** The test enables the branches itself. `_start_pm_test()` and
`verify_pcba.run_power_module_phase()` both pass `enable_phases=False`. **Do not
re-enable this without strong evidence that the firmware behaviour has changed.**

## 2. Bottom switches measure the complement of the commanded duty

**Symptom:** "All UBOT/VBOT/WBOT verdicts fail with measured duty ≈ 75 % when
I commanded 25 %." (And mirror image for 75 %→25 %.)

**Cause:** `SET_PWM_DUTY` commands the high-side (top-switch) on-time. The
bottom switch is its complement, minus the dead-band. On a 1 µs dead-band:
- 10 kHz period 100 µs → ~1 % dead-band → bottom-duty ≈ 100 − cmd − 1
- 30 kHz period 33 µs → ~3 % dead-band → bottom-duty ≈ 100 − cmd − 3

So commanded 25 % on UBOT reads 74 % at 10 kHz, 72 % at 30 kHz. **This is
correct.**

**Fix:** `run_power_module_sweep.expected_duty_pct(switch, duty)` returns
`(100 - duty)` for `BOTTOM_SWITCHES = {UBOT, VBOT, WBOT}` and `duty` for the
top switches. The ±5 pp tolerance absorbs the dead-band offset. Verdict
recomputation is done at capture time (when `switch=` is passed to
`measure_pm_setpoint`) AND at report time (`pm.recompute_verdict(rec)`).

## 3. Per-switch driver reset clears the "not ready" condition

**Symptom:** After moving the voltage probe to the next switch, the next
sweep returns NaN or stuck values for the first several setpoints.

**Cause:** Physical probe change perturbs the gate signal momentarily and
the gate driver's READY/FLT monitoring latches a "not ready" state until
the test is restarted.

**Fix:** After each probe-move confirmation in
`verify_pcba.run_power_module_phase()`:
```
SET_TEST(HW_TEST_NO_TEST)            # stop test, drivers de-init
sleep 0.2 s
SET_TEST(HW_TEST_ALL_POWER_MODULE)   # re-enter test, drivers re-init
SET_PWM_DT(deadband_ns)              # re-pin (start hook resets to default)
```
`pm_step_session.py measure --switch <SW>` does the same naturally — each
invocation does its own `_start_pm_test` because the previous one ended with
`_stop_pm_test`.

## 4. SET_PWM_FREQ / SET_PWM_DUTY DO work — earlier "stuck at 30 kHz / 0 %" was misleading

**Symptom:** Watch window showed `pwm_freq_forced_in_khz=10` and
`pwm_duty_*_forced_unitary=0.5` regardless of what was sent.

**Cause:** When the watch was inspected, no `ALL_POWER_MODULE` test was running
(the test had been stopped, or had just started so its start hook reset
forced freq → 30 (DEFAULT) and duty → 0). Once we sent SET_PWM_FREQ(20) /
SET_PWM_DUTY(0.5) into the running test, the firmware variables tracked
exactly (proven by watch showing 30 kHz / 0.7 after our pm_poke stepped
through 20/25/30 and 0.3/0.5/0.7 — the last poked values stuck).

**Conclusion:** The Python protocol layer is correct. Symptoms that look like
"my command didn't land" are usually one of the gotchas above (#1, #3) or
the start hook resetting forced values to defaults right before the read.

**Debug tool:** `python pm_poke.py --hold 3` cycles SET_PWM_FREQ through
20→25→30 kHz and SET_PWM_DUTY through 0.3→0.5→0.7 with 3 s holds, printing
the exact 8-byte CAN frames. Watch `pwm_freq_forced_in_khz` and
`pwm_duty_phase_*_forced_unitary` in the debugger — they should track.

## 5. Protocol encoding correctness (verified against the firmware)

The firmware (`sf_general_tools/tools/type_tools.c`) decodes:
- **`uint8_t_array_to_uint32_t`** — manually byte-reverses `{data[3],data[2],data[1],data[0]}` then memcpy → it expects **BIG-ENDIAN** uint32. The Python tool packs uint32 values via `int(value).to_bytes(4, byteorder='big')` ✓.
- **`uint8_t_array_to_float`** — straight `memcpy(&value, data, sizeof(float))` on a little-endian MCU → it expects **LITTLE-ENDIAN** float. The Python tool packs floats via `struct.pack("<f", value)` ✓.

The hw_protocol command-type table per the original interactive tool:
| Cmd | Code | Object type | Notes |
|---|---|---|---|
| NOP | 0x00 | EMPTY | |
| SET_TEST_ENV | 0x01 | UINT32 | flags bitfield |
| SET_TEST | 0x02 | UINT32 | test code |
| ECHO | 0x03 | BUFFER | 4-byte pattern |
| SET_PWM_FREQ | 0x04 | **FLOAT** | kHz |
| SET_PWM_DUTY | 0x05 | **FLOAT** | per-unit 0.0..1.0 |
| SET_DIG_OUT | 0x06 | UINT32 | |
| SET_PWM_DT | 0x07 | **FLOAT** | ns |
| SET_PWM_PULSES | 0x08 | UINT32 | |
| EN_DIS_PHASE | 0x09 | **UINT32** | (NOT float) |
| SET_PUMP_DUTY | 0x0A | FLOAT | |
| SET_PUMP_FREQ | 0x0B | FLOAT | kHz |

If you find a discrepancy with the firmware's `hw_test_comm_can_rqst_process()`
switch in `sf_app/HW_testing/hw_testing.c`, the firmware is the source of
truth — fix `hw_protocol.py`.

## 6. The R&S RTM3004 setup (USB-TMC)

- Must be in **USB-TMC** mode, not WPD/MTP. Setup → Interfaces → USB → TMC.
- Class becomes `USBTestAndMeasurementDevice`, PID `0x01D6`.
- VISA resource: `USB0::0x0AAD::0x01D6::<6-digit serial>::INSTR`
- On Windows, install **R&S VISA** (RsVisaSetup, free) and use `--backend @ivi`.
- `pyvisa-py` (`--backend @py`) **cannot** enumerate USB on this Windows bench
  (only ASRL ports). Use `@py` only for LAN: `--resource "TCPIP::<ip>::INSTR"`.
- The driver in `code/scope_rs.py` does an edge-zoom second pass for accurate
  rise/fall: coarse timebase for freq/duty/levels, then 100 ns/div with
  POSitive trigger for rise, NEGative for fall. Read values matching
  `|v| >= 1e30` are the R&S "no result" sentinel and become NaN.
- Default gate setup: CH1, 10:1 probe, 4 V/div, +7.5 V offset (centred on +18/−3),
  DC coupling, edge trigger at +5 V, MEAS1..7 slots configured for the 7
  parameters so they show live on the scope screen during the sweep.

## 7. Cold-start "warm-up" appearance is a side effect, not a real warm-up

In an earlier (buggy) Phase 2 implementation, the first ~13 setpoints would
read garbage / NaN before "coming alive". We initially attributed this to
gate-driver supply bootstrapping (~60–80 s of charging). It turned out to be
mostly Gotcha #1 (EN_DIS_PHASE disrupting the start) plus Gotcha #3 (probe
move latching not-ready). **With those fixed, no warm-up is needed** — the
per-switch driver reset (#3) is sufficient. The `--pm-warmup` CLI flag was
kept for back-compat but defaults to 0 in both `verify_pcba` and
`pm_step_session`.

## When something still looks wrong in Phase 2

A short triage flow:

1. Are the gate levels healthy (+17.9 V / −2.7 V) but the duty is the
   complement of commanded? → **Bottom switch, normal** (Gotcha #2).
2. Are levels both ~+18 V (latched high) or both ~−3 V (off)? → Driver was
   left in a bad state. Check Gotcha #1 (EN_DIS_PHASE) and Gotcha #3 (probe
   move without reset).
3. NaN everywhere? → Scope can't trigger. Probe not on gate, or signal
   not switching (test not in `ALL_POWER_MODULE`, or duty=0/100).
4. Frequency stuck at the START default (30 kHz) regardless of command? →
   `pwm_freq_forced_in_khz` not being updated. Run `pm_poke.py` to confirm
   the SET_PWM_FREQ frames reach the firmware. If poke works but the live
   test doesn't, you may have a different firmware version where the start
   hook re-runs.
5. Cross-run flakiness (works sometimes, not others)? →
   `python pm_compare.py --sessions <A> <B> --switch <SW>` does a per-point
   run-to-run diff with an Excel report flagging mismatches.
