# Inverter Gen3 — PCBA HW Automated Test

End-to-end Python toolchain for verifying the **StarkFuture Inverter Gen3 PCBA**
on the bench. Drives the board's HW-test firmware over **CAN** (PEAK PCAN-USB,
250 kBit/s, ID `0x100`), measures the isolated gate-driver signals on a
**Rohde & Schwarz RTM3000** scope (USB-TMC), and produces one unified Excel
**ValidationReport** per board.

The full engineering specification lives in
[`plan/InvGen3_HW_PCBA_TestByTest_Plan.pdf`](plan/InvGen3_HW_PCBA_TestByTest_Plan.pdf)
(currently **v3.2**).

## Quick start

```bash
pip install -r code/requirements.txt
cd code
python verify_pcba.py --unit-sn PCB-B1 --all
```

That single command runs the whole 3-phase campaign:

| Phase | What it does | Operator action |
|---|---|---|
| **1 — Self auto-verification** | 16 firmware self-checks (supplies, ADC, drivers, CAN/UART/I2C/SPI, GPIO loopback, pump, …) | None (unattended) |
| **2 — Power modules (`HW_TEST_ALL_POWER_MODULE` 0x1B)** | Scope sweep across 6 switches × 9 setpoints (10/20/30 kHz × 25/50/75 % @ 1 µs dead-band). Per-switch driver reset on probe move. | Move the scope probe to each of UTOP/UBOT/VTOP/VBOT/WTOP/WBOT and press ENTER |
| **3 — Operator-verified** | LED visual check + 4 DAC-injection loopbacks (encoder SIN/COS, unipolar/bipolar voltage sense) | Wire DAC↔input per test prompt; for LEDS visually confirm the blinks |

Output: `results/ValidationReport_PCB-B1_<timestamp>.xlsx` with one sheet per
phase plus `Summary`, `Analog Readings`, and `Conclusions`.

## Hardware bench

- Inverter Gen3 board flashed with **HW-test firmware** (B0/B1/B2 share the
  same 21-test list, split here into Phase 1 + Phase 3).
- **PCAN-USB** on `PCAN_USBBUS1`. Uses `PCANBasic.dll` if installed, otherwise
  falls back to `python-can` (`interface='pcan', channel='PCAN_USBBUS1',
  bitrate=250000`).
- **R&S RTM3000** scope in **USB-TMC** mode (not WPD/MTP). On Windows install
  R&S VISA (free RsVisaSetup) and use `--backend @ivi` (default). `pyvisa-py`
  cannot enumerate USB for this scope on Windows.
- 10:1 passive probe on CH1.
- Test-fixture jumpers: UART TX↔RX, GPIO loopback (required by Phase 1).

## Repo layout

```
code/                            All Python tools (see SKILL.md for per-file role)
plan/                            Engineering reference (TestByTest_Plan .docx + .pdf)
original_code/                   Historical STARK_FUTURE_* interactive tool (reference only)
results/                         Per-run outputs — git-ignored, kept by .gitkeep
.claude/skills/                  Claude skill for AI-assisted operation
```

## Common entry points

| Command | What it does |
|---|---|
| `python verify_pcba.py --unit-sn <SN> --all` | Full 3-phase PCBA campaign → unified report |
| `python verify_pcba.py --unit-sn <SN>` | Phase 1 only (unattended) |
| `python verify_pcba.py --unit-sn <SN> --power-module` | Phases 1 + 2 |
| `python verify_pcba.py --unit-sn <SN> --loopback` | Phases 1 + 3 |
| `python pm_step_session.py measure --switch <SW> --session <name>` | Single switch Phase 2 sweep (chat-driven) |
| `python pm_step_session.py report --session <name>` | Generate Phase 2 standalone report |
| `python pm_compare.py --sessions A B --switch <SW>` | Compare two Phase 2 sessions point-by-point |
| `python scope_check.py` | Scope connectivity self-test (verify VISA + IDN) |
| `python pm_poke.py` | CAN-poke diagnostic for `SET_PWM_FREQ` / `SET_PWM_DUTY` (watch firmware vars) |
| `python run_campaign_multi.py --runs 10` | N-run repeatability over Phase 1 |

Full flag reference: `python <tool>.py --help`.

## Phase 2 — Power-module sweep details

Per switch, after the operator confirms the probe move:
1. `SET_TEST(HW_TEST_NO_TEST)` — stop the test (drivers de-init, clears
   "not ready" caused by the physical probe change).
2. `SET_TEST(HW_TEST_ALL_POWER_MODULE)` — re-enter the test (drivers re-init).
3. `SET_PWM_DT(<deadband_ns>)` — re-pin the dead-band (start hook resets it).
4. Walk the 9 setpoints live: pin freq via `SET_PWM_FREQ` (kHz), duty via
   `SET_PWM_DUTY` (per-unit, 0.25/0.50/0.75), 2 s settle, measure the 7
   scope parameters per point.

The verdict is **switch-aware**: top switches' measured duty = commanded; bottom
switches read the complement (`100 − commanded`, minus the dead-band offset).
The report ends with **Mean / Std(abs) / Std(rel)** summary rows over
rise/fall/V-high/V-low/V-pp (frequency and duty excluded because they're
swept by design).

## Critical gotchas (bench bring-up learnings)

See [`.claude/skills/inverter-gen3-pcba-hw-test/references/bench-lessons.md`](.claude/skills/inverter-gen3-pcba-hw-test/references/bench-lessons.md)
for the full story. Headline items:

- **Do NOT send `EN_DIS_PHASE` during `ALL_POWER_MODULE`** — it disturbs the
  test's own enable-transition logic. The test enables phases itself.
  `_start_pm_test()` and `run_power_module_phase()` default to
  `enable_phases=False`.
- **Bottom switches measure the duty complement** (`100 − cmd`, minus dead-band).
  This is correct, not a fault — the report handles it via `expected_duty_pct()`.
- **Per-switch test reset** is mandatory after a probe move (gotcha #3) — both
  `verify_pcba` (built-in) and `pm_step_session` (one invocation per switch).
- **R&S RTM3004 must be in USB-TMC mode** on Windows + R&S VISA installed +
  `--backend @ivi`. `pyvisa-py` won't see it.

## Using Claude with this repo

This repo ships with a Claude skill at
[`.claude/skills/inverter-gen3-pcba-hw-test/SKILL.md`](.claude/skills/inverter-gen3-pcba-hw-test/SKILL.md).
When you run Claude Code (or any Claude-with-skills environment) in this repo,
the skill auto-triggers on mentions of `Inverter Gen3`, `verify_pcba`,
`HW_TEST_*`, `pm_step_session`, `power module sweep`, etc., so the model
already knows the hardware setup, the 3-phase model, the gotchas, and the
proper command flow without you having to brief it.

## License / use

Internal StarkFuture engineering tooling. Treat raw bench reports in
`results/` as confidential — they're git-ignored by default.
