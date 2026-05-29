# Repository context for Claude

This repo is the **StarkFuture Inverter Gen3 PCBA hardware-test toolchain**.
Python tools drive the inverter board's HW-test firmware over CAN (PCAN-USB,
250 kBit/s, ID `0x100`) and measure isolated gate signals on an R&S RTM3000
scope (USB-TMC). One unified Excel `ValidationReport_<SN>_<ts>.xlsx` per board.

The canonical reference is **`plan/InvGen3_HW_PCBA_TestByTest_Plan.pdf`**
(v3.2+) and the operating manual is the skill at
**`.claude/skills/inverter-gen3-pcba-hw-test/SKILL.md`** — that skill loads
automatically when the user mentions anything Inverter-Gen3-related and
covers hardware setup, the 4-phase campaign, commands, and the bench gotchas.
**Read the skill first when in doubt.**

## Primary entry point

```
python code/verify_pcba.py --unit-sn <SN> --all
```
Runs Phase 1 (16 self auto-verification tests, unattended), Phase 2
(`HW_TEST_ALL_POWER_MODULE` 0x1B scope sweep — 6 switches × 9 setpoints, with
a `NO_TEST → ALL_POWER_MODULE` driver reset after each probe move), Phase 3
(EA-supply HV characterization — voltage 0→400 V/50 V on DC_LINK/UV/WV sense
inputs + phase current ±20 A/5 A CC-mode on the shunts, read over CAN; needs
`--ea-resource`), and Phase 4 (3 operator-verified tests: LEDs + encoder
sin/cos loopbacks). Phase 3 replaced the old DAC unipolar/bipolar loopbacks
(`0x2A`/`0x2B`); the chat/step-driven equivalent is `code/hv_iv_session.py`.

## Top gotchas (full story in `.claude/skills/.../references/bench-lessons.md`)

- **Do NOT send `EN_DIS_PHASE` during `ALL_POWER_MODULE`** — disruptive; the
  test enables phases itself.
- **Bottom switches (UBOT/VBOT/WBOT) measure the duty complement** —
  commanded 25 % reads ≈74 %. Verdict is switch-aware.
- **Per-switch driver reset is mandatory after a probe move** (clears the
  driver "not ready" latched by the physical perturbation).
- **R&S RTM3004 on Windows** needs **USB-TMC mode** + R&S VISA installed
  + `--backend @ivi`. `pyvisa-py` cannot enumerate USB on this bench.
- **`PUMP_AUTO` (0x2F) FAIL is expected on a bench with no pump.**

## User & working style

- **Carlos Miguel Espinar**, FW / motor-control engineer at StarkFuture.
- Bench-driven, action-oriented: prefers progress over planning chatter,
  picks the obvious default and goes. Confirm only on destructive ops or
  genuinely ambiguous scope.
- **Commit style**: brief subject + ≤10-line body; expand only on request.
- **Docs convention**: any generated `.md`/`.docx` must produce a matching
  PDF next to it (use Word COM `SaveAs(..., 17)`).
- **Test output**: per-test PASS/FAIL summary in console is enough; assertion
  detail belongs in the report file, not the chat.
- **Run batched tool calls in parallel** when independent (single message,
  multiple tool blocks) to minimise permission prompts.

## Bench session state (transient — git-ignored, kept locally)

`results/.pm_session_B1_campaign.pkl` holds the most recent in-progress
power-module session. Inspect or resume with:

```
python code/pm_step_session.py status --session B1_campaign
python code/pm_step_session.py measure --switch <SW> --session B1_campaign --warmup 0 \
    --resource "USB0::0x0AAD::0x01D6::112060::INSTR"   # then repeat per switch
python code/pm_step_session.py report  --session B1_campaign
```

## Don't touch (until firmware-side change is confirmed)

- `_start_pm_test(..., enable_phases=False)` — keep `False`.
- `pm_step_session` and `verify_pcba.run_power_module_phase` — the per-switch
  reset sequence is load-bearing; don't optimise it away.
- Float-vs-uint32 type table in `hw_protocol.py` — matches firmware decoder
  in `sf_general_tools/tools/type_tools.c`.
