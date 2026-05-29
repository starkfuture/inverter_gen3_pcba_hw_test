---
name: inverter-gen3-pcba-hw-test
description: How to run the StarkFuture Inverter Gen3 PCBA hardware-test campaign — a 3-phase automated/operator-assisted verification of the inverter PCBA over CAN (PCAN-USB, 250 kBit/s, ID 0x100) and a Rohde & Schwarz RTM3000 scope (USB TMC). Use this skill whenever the user mentions Inverter Gen3, the PCBA HW-test, verify_pcba.py, pm_step_session.py, run_power_module_sweep.py, HW_TEST_* tests (LEDS, ALL_ADC_MEASUREMENTS, ALL_POWER_MODULE 0x1B, ENC_SINCOS_*, POWER_UNIPLR/BIPLR_V_LOOPBACK, PUMP_AUTO, etc.), power-module scope sweep, gate-signal verification on this inverter, DAC-injection loopbacks, the B0/B1/B2 sample test sequence, the Phase 1/2/3 campaign model, or asks how to set up / execute / debug / extend this PCBA verification on this hardware. Also use it if the user asks how to drive the firmware HW_TEST protocol over CAN, configure the RTM3004 scope for the +18/-3 V gate measurement, or interpret a ValidationReport_*.xlsx / PowerModuleSweep_*.xlsx.
---

# Inverter Gen3 PCBA Hardware Test

This skill documents the **StarkFuture Inverter Gen3 PCBA verification campaign**. The repo provides Python tools that drive the inverter board's HW-test firmware over CAN, measure the isolated gate-driver signals with an R&S RTM3000 oscilloscope, and produce a single unified Excel validation report per board.

The canonical detailed specification is `plan/InvGen3_HW_PCBA_TestByTest_Plan.pdf` (v3.2+). This SKILL.md is the operating manual; the plan is the engineering reference.

## What you (Claude) should help the user do

- Run the full PCBA verification campaign (single command, three phases).
- Run individual phases when interactive prompts can't be driven (drive Phase 2 / Phase 3 step-by-step in chat instead).
- Generate, regenerate, or compare validation reports.
- Diagnose firmware HW_TEST behaviour (driver "not ready", PWM latching, warm-up).
- Extend the test plan or add new tests / sweeps.

## Hardware prerequisites

| Item | Notes |
|---|---|
| Inverter Gen3 board flashed with **HW-test firmware** | B0/B1/B2 share the same test list |
| **PCAN-USB** | 250 kBit/s, 11-bit ID `0x100`. Uses PCANBasic.dll if installed, falls back to `python-can` |
| **R&S RTM3000** scope (RTM3004 verified) on **USB-TMC** mode | NOT WPD/MTP; resource looks like `USB0::0x0AAD::0x01D6::<serial>::INSTR` |
| 10:1 passive voltage probe on **CH1** | For +18 V / −3 V isolated gate measurement |
| Test-fixture jumpers: UART TX↔RX, GPIO loopback | Required for Phase 1 to pass `UART_CHECK_LOOPBACK` and `EXTRA_GPIOs_LOOPBACK` |
| (Phase 3 only) MCU DAC pins PA4/PA5 wires | Operator wires DAC→analog input per DAC-injection test |

Python deps: `pip install -r code/requirements.txt` — needs `python-can`, `pyvisa`, `openpyxl`, `python-docx`. For USB-TMC on Windows install **R&S VISA** (free, RsVisaSetup) and use `--backend @ivi`. `pyvisa-py` (`@py`) **cannot** enumerate USB on Windows for this scope.

## Repo layout

```
inverter_gen3_pcba_hw_test/
├── code/                          # All Python tools
│   ├── verify_pcba.py             # PRIMARY ENTRY POINT — runs the 3-phase campaign
│   ├── pm_step_session.py         # Step-by-step power-module sweep (chat-driven Phase 2)
│   ├── run_power_module_sweep.py  # Standalone power-module sweep (own report)
│   ├── pm_compare.py              # Compare two pm sessions for run-to-run consistency
│   ├── pm_poke.py                 # CAN poke diagnostic (send freq/duty, watch FW vars)
│   ├── run_gate_scope_check.py    # Legacy 0x18/0x19 gate scope tool (optional)
│   ├── run_tests.py               # Phase-1-only campaign runner (no scope)
│   ├── run_campaign_multi.py      # N-run repeatability over Phase 1
│   ├── scope_check.py             # Scope connectivity self-test
│   ├── hw_protocol.py             # sf_hw_test_protocol encoder/decoder + sequence lists
│   ├── hw_test_runner.py          # Campaign engine (execute_campaign, run_sequence)
│   ├── hw_test_criteria.py        # Analog limits + MANUAL_SETUP_INSTRUCTIONS (prompts)
│   ├── hw_can_utils.py            # CAN bus wrapper (PCANBasic / python-can fallback)
│   ├── pcan_interface.py          # Lower-level PCAN access
│   ├── scope_rs.py                # R&S RTM3000 SCPI driver (open, full_setup, measure)
│   ├── scope_interface.py         # Scope abstraction
│   ├── generate_report.py         # Unified ValidationReport_*.xlsx builder
│   ├── config.py                  # Defaults: sequence, SN, timeouts, HW version, pass criterion
│   └── requirements.txt
├── plan/
│   ├── InvGen3_HW_PCBA_TestByTest_Plan.docx      # Canonical engineering reference
│   └── InvGen3_HW_PCBA_TestByTest_Plan.pdf
├── original_code/                  # Historical: STARK_FUTURE original interactive tool
│   ├── STARK_FUTURE_InvGen3_hw_test.py
│   ├── STARK_FUTURE_hw_test_protocol.py
│   └── ...
├── results/                        # Per-run outputs (CSV + xlsx). Git-ignored, kept by .gitkeep.
└── .claude/skills/inverter-gen3-pcba-hw-test/    # THIS skill
    ├── SKILL.md
    └── references/
        ├── bench-lessons.md        # Hard-won bring-up gotchas; read when debugging
        └── three-phase-model.md    # Detailed per-test list + protocol encoding cheat-sheet
```

## The 3-phase campaign model

**`python verify_pcba.py --unit-sn <SN> --all`** runs all three phases and writes one unified `results/ValidationReport_<SN>_<ts>.xlsx`.

### Phase 1 — Self auto-verification (16 tests, unattended)

Sequence `B<x>_SELF` in the protocol. No operator input. All firmware self-checks: `SUPPLY_VOLTAGES, ALL_ADC_MEASUREMENTS, MCU_INTER_MEASUREMENTS, PWM_DRIVERS_USER_MEASUREMENTS, MEASUREMENTS_DIAGNOSTICS, ALL_PWM_SUPPLIES, ALL_DRIVERS_STATUS, ALL_DRIVERS_SETTING, ALL_DRIVERS_FREQUENCY (0x18), ALL_DRIVERS_DUTY (0x19), CAN_ECHO, UART_CHECK_LOOPBACK, I2C_TEMP_HUMID_AUTO_TX, SPI_FLASH_MEM_AUTO_TX, EXTRA_GPIOs_LOOPBACK, PUMP_AUTO`. Bash-drivable end to end.

CLI: `--self` (default on) / `--no-self` to skip.

### Phase 2 — Power modules (HW_TEST_ALL_POWER_MODULE 0x1B, scope-assisted)

For each of the 6 switches (UTOP, UBOT, VTOP, VBOT, WTOP, WBOT) the operator moves a probe to that gate, then the tool walks a **9-point sweep**: frequency 10/20/30 kHz × duty 25/50/75 % at a fixed **1 µs dead-band**. Per-setpoint measurements: frequency, duty, rise, fall, V-high, V-low, V-pp. Each setpoint is verdict-checked switch-aware (top = commanded duty; bottom = `100 − commanded`).

**After every probe move** the tool cycles the test (`SET_TEST(NO_TEST) → SET_TEST(ALL_POWER_MODULE) + re-pin dead-band`) to clear the gate-driver "not ready" condition caused by the physical probe change.

CLI: `--power-module`.

### Phase 3 — Operator-verified (5 tests, prompted)

Sequence `B<x>_LOOPBACK` (legacy name; the set is "operator-verified"). Each test prints its instruction from `MANUAL_SETUP_INSTRUCTIONS` (in `code/hw_test_criteria.py`) and waits for ENTER. **Always interactive** — `--no-prompts` does not suppress these.

| Code | Test | Operator action |
|---|---|---|
| 0x01 | `HW_TEST_LEDS` | Visually verify LED1 and LED2 blink during the test |
| 0x25 | `HW_TEST_ENC_SINCOS_SIN_LOOPBACK` | DAC1→SIN+, DAC2→SIN− |
| 0x26 | `HW_TEST_ENC_SINCOS_COS_LOOPBACK` | DAC1→COS+, DAC2→COS− |
| 0x2A | `HW_TEST_POWER_UNIPLR_V_LOOPBACK` | DAC1→DC-link voltage-sense isolated input |
| 0x2B | `HW_TEST_POWER_BIPLR_V_LOOPBACK` | DAC1→UV/WV + leg, DAC2→− leg |

CLI: `--loopback`.

### Other flags worth knowing
- `--all` — Phase 1 + Phase 2 + Phase 3
- `--no-prompts` — skips DAC-test prompts in Phase 1 invocations (they then FAIL because hookup isn't done); does NOT suppress Phase 3 prompts
- `--unit-sn <SN>` — board serial → filename
- `--hw-version <n>` — 3 = B1 (2 external NTCs populated, channels 37/38 skipped). Auto-detected from ANLG[0] if omitted.
- `--resource "USB0::0x0AAD::0x01D6::<serial>::INSTR"` — explicit scope VISA resource
- `--backend @ivi` (default) — required for USB-TMC on Windows
- `--pm-freq-min/step/max`, `--pm-duty-min/step/max`, `--deadband-ns` — override Phase 2 sweep

## How to drive a campaign

### Fully unattended (no operator) — only Phase 1
```
python verify_pcba.py --unit-sn PCB-B1
```
DAC tests (0x25/26/2A/2B) are NOT in Phase 1, so this doesn't need hookups. PUMP_AUTO will FAIL on a bench with no pump (this is expected and recorded).

### Full PCBA campaign (interactive, recommended at the bench)
```
python verify_pcba.py --unit-sn PCB-B1 --all
```
The operator confirms probes (Phase 2 ×6) and hookups (Phase 3 ×5).

### Driving from Claude when stdin can't be piped to the running process
If you're orchestrating from an environment whose Bash tool **cannot feed keystrokes** to a hanging `input()` call (typical for Claude Code's Bash, Anthropic API agents, etc.), do this hybrid:

1. **Phase 1**: `python verify_pcba.py --unit-sn <SN>` (no flags → Phase 1 only). Runs end-to-end via Bash.
2. **Phase 2**: drive switch-by-switch with chat confirmations using `pm_step_session.py`:
   ```
   python pm_step_session.py measure --switch UBOT --session <name> --unit-sn <SN> --warmup 0
   # → repeat for UTOP, VTOP, VBOT, WTOP, WBOT
   python pm_step_session.py report --session <name>
   ```
   Use the model's question-asking ability to confirm each probe move before running the next switch. Each invocation does its own `_start_pm_test` (which is `SET_TEST(NO_TEST)→SET_TEST(ALL_POWER_MODULE)+SET_PWM_DT`), giving the per-switch driver reset Phase 2 needs.
3. **Phase 3**: drive one test at a time the same way (run a single-test sequence with operator confirming the hookup via chat first).

## Critical gotchas (read `references/bench-lessons.md` for full story)

These are non-obvious. **Always check this list when something behaves unexpectedly during Phase 2.**

1. **Do NOT send `EN_DIS_PHASE` during `HW_TEST_ALL_POWER_MODULE`.** It's disruptive (writes `pwm_en_phase_*_forced`, which causes the test's enable-transition logic to toggle the driver GPIOs at unexpected moments). The test enables the phases itself. Both `_start_pm_test()` and `verify_pcba.run_power_module_phase()` already default to `enable_phases=False`.
2. **Bottom switches read complementary duty.** Probing UBOT/VBOT/WBOT, commanded 25 % reads ≈ 74–75 % (the complement minus the dead-band). The switch-aware verdict in `run_power_module_sweep.expected_duty_pct()` handles this; reports built via `pm_step_session.py report` recompute it (see `recompute_verdict()`).
3. **Per-switch driver reset after a probe move.** Physically changing the voltage probe causes the gate driver to flag "not ready". Phase 2 sends `SET_TEST(NO_TEST) → SET_TEST(ALL_POWER_MODULE) + SET_PWM_DT(1000 ns)` after each probe-move confirmation to clear it. This is built into `verify_pcba.run_power_module_phase()` and naturally happens in `pm_step_session` (one invocation per switch).
4. **Don't send `EN_DIS_PHASE` as FLOAT.** The firmware reads it as UINT32. `hw_protocol.py` now encodes it correctly as UINT32 (along with `SET_PWM_PULSES` and `SET_DIG_OUT`) to match the original tool.
5. **First-time scope on USB**: must be in **USB-TMC** mode (Setup → Interfaces → USB, NOT WPD/MTP). Use `python scope_check.py --list-only` to enumerate; should see `USB0::0x0AAD::0x01D6::<serial>::INSTR`.
6. **PCAN dongle can drop intermittently** — symptom is `PcanCanInitializationError`. Replug fixes it. Not a code bug.
7. **`PUMP_AUTO` (0x2F) FAIL on a bench with no pump** is expected — report records it as such.

## Reports

- **`results/ValidationReport_<SN>_<ts>.xlsx`** — single unified workbook from `verify_pcba.py`. Sheets: `Summary`, `Test Results`, `Analog Readings`, `Power Module Sweep` (if Phase 2 ran), `Conclusions`.
- **`results/PowerModuleSweep_<SN>_<ts>.xlsx`** — Phase 2 standalone (from `pm_step_session.py report` or `run_power_module_sweep.py`). One row per setpoint, ends with **Mean / Std(abs) / Std(rel)** summary rows over rise / fall / V-high / V-low / V-pp (frequency and duty are excluded because they're swept by design).
- **`results/PowerModuleSweep_Compare_<SW>_<ts>.xlsx`** — `pm_compare.py` output for two-session run-to-run diff (catch intermittent "stuck variable" firmware behaviour).

All reports: **Arial throughout, 2-decimal standardised formatting**. The polished format is built into both `run_power_module_sweep.write_report()` (standalone) and `generate_report._build_power_module_sheet()` (unified).

## Reference files

- `references/bench-lessons.md` — the bench bring-up history with the WHY behind each gotcha above. Read this if anything in Phase 2 behaves weirdly (gate latches high, freq stays at 10 kHz, duty stays at 50 %, etc.).
- `references/three-phase-model.md` — full per-test catalog with codes, timeouts, channels, firmware enum, and protocol byte-layout cheat sheet. Read this when adding a new test or extending the sequence lists.

For the authoritative engineering specification (firmware-side test definitions, ANLG channel maps, expected ranges per HW version), open `plan/InvGen3_HW_PCBA_TestByTest_Plan.pdf` — it's kept in lockstep with the code.
