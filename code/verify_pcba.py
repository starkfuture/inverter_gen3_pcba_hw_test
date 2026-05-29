#!/usr/bin/env python3
"""
verify_pcba.py  –  One-shot full PCBA verification for Inverter Gen3.

Runs the entire verification of a single board and writes ONE report file
that contains every result — both the firmware-automated test campaign and
the manual scope-assisted gate checks. Some steps are automatic; others ask
you to move a probe. It is all one PCBA verification → one workbook.

Phases (3-phase B-sample campaign)
──────────────────────────────────
  Phase 1 — Self auto-verification (default ON; --no-self to skip)
            ~17 firmware tests over CAN, no operator input required (assumes
            UART / GPIO loopback jumpers are on the fixture). Sequence
            "B<x>_SELF" in the protocol. Runs unattended.

  Phase 2 — Power modules (--power-module)
            HW_TEST_ALL_POWER_MODULE (0x1B). Scope-assisted: 6 switches × 9
            setpoints (10/20/30 kHz × 25/50/75 %) at a fixed dead-band.
            Operator moves the probe per switch; after each probe move the
            test is cycled (NO_TEST → ALL_POWER_MODULE) to clear the driver
            "not ready" condition caused by the probe change.

  Phase 3 — Operator-verified tests (--loopback)
            5 tests: HW_TEST_LEDS (0x01, LED visual check) +
            ENC_SINCOS_SIN/COS (0x25/0x26), POWER_UNIPLR_V (0x2A),
            POWER_BIPLR_V (0x2B) — operator wires a DAC output to an
            analog input before each DAC test; for LEDS the operator
            visually confirms LED1/LED2 blink. Always interactive
            (--no-prompts does not suppress these hookups). Sequence
            "B<x>_LOOPBACK" in the protocol (aliased; see hw_protocol.py).

  --all      Shorthand: Phase 1 + Phase 2 + Phase 3.
  --scope    Optional legacy gate-scope check (0x18/0x19), separate from
             the 3 main phases.

Output
──────
  results/ValidationReport_<SN>_<timestamp>.xlsx   ← single file, sheets:
      Summary | Test Results | Analog Readings |
      [Gate Scope Checks] | Conclusions

Usage
─────
  # Automated campaign only:
  python verify_pcba.py --unit-sn PCB-B1

  # Full verification incl. manual gate scope checks (scope on CH1, 16 kHz / 50 %):
  python verify_pcba.py --unit-sn PCB-B1 --scope --freq-khz 16 --duty 50

  # Everything non-interactive (skip ALL prompts; scope uses --simulate):
  python verify_pcba.py --unit-sn PCB-B1 --no-prompts
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import time
import argparse
import datetime

from config import TEST_SEQUENCE, UNIT_SN, OPERATOR, HW_VERSION_OVERRIDE
from hw_test_runner import execute_campaign
from generate_report import generate_validation_report

_RESULTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results"))


# ── Phase 2 helpers (gate scope) ──────────────────────────────────────────

SWITCHES = ["UTOP", "UBOT", "VTOP", "VBOT", "WTOP", "WBOT"]


def run_gate_scope_phase(args):
    """Run the manual gate scope checks and return a flat list of records.

    For each switch the operator moves the probe ONCE; we then run the
    frequency sweep and the duty sweep, measuring the gate each time.
    """
    import run_gate_scope_check as gsc
    from hw_protocol import HwTestProtocol
    from scope_rs import RohdeScope

    protocol = HwTestProtocol()
    simulate = args.simulate
    bus = None if simulate else gsc._open_can()
    scope = RohdeScope(resource=args.resource, backend=args.backend,
                       simulate=simulate).open()

    print("\n" + "=" * 72)
    print("  PHASE 2 — Manual gate scope checks")
    print(f"  Scope     : {scope.idn()}")
    print(f"  Scope ch  : CH{args.scope_ch}  probe {args.probe_atten:g}:1")
    print(f"  Setpoints : freq {args.freq_khz} kHz, duty {args.duty} %")
    print("=" * 72)

    # Full scope pre-configuration (reset + vertical + trigger + the 7
    # on-screen measurement slots). Timebase is adjusted per setpoint below.
    if args.freq_khz:
        period = 1.0 / (args.freq_khz * 1000.0)
        t_div = max(period * 3 / 10.0, 1e-7)
    else:
        t_div = 20e-6
    scope.full_setup(args.scope_ch, v_div=gsc.DEFAULT_V_DIV,
                     offset=gsc.DEFAULT_OFFSET, probe_atten=args.probe_atten,
                     t_div=t_div, trig_level=gsc.DEFAULT_TRIG_LVL)

    # Frequency points: explicit list or the parametric min/max/step sweep.
    freq_points = args.freq_points
    if freq_points is None:
        freq_points = gsc.gen_points(args.freq_min, args.freq_max, args.freq_step)
    edge_t_div = args.edge_tdiv if args.edge_tdiv and args.edge_tdiv > 0 else None

    # Build the measurement plan (both freq & duty; single setpoint or
    # range-verify across the sweep range).
    plan = gsc.build_plan("both", args.range_verify,
                          args.freq_khz, args.duty,
                          freq_points, args.duty_points)

    def _tdiv_for(entry):
        f_hz = (entry["freq_khz"] * 1000.0) if entry["freq_khz"] else None
        return max((1.0 / f_hz) * 3 / 10.0, 1e-7) if f_hz else 20e-6

    records = []
    try:
        for sw in args.switches:
            print("\n  " + "═" * 68)
            print(f"  ⚠  Move the voltage probe to the  {sw}  gate (isolated PWM).")
            print("  " + "═" * 68)
            if not simulate and not args.no_prompts:
                try:
                    input(f"  Press ENTER when the probe is on {sw} … ")
                except (EOFError, KeyboardInterrupt):
                    print("\n  Gate scope phase aborted by operator."); break

            for entry in plan:
                scope.configure_timebase(_tdiv_for(entry))
                rec = gsc.measure_one_setpoint(scope, bus, protocol,
                                               args.scope_ch, entry, simulate,
                                               edge_t_div=edge_t_div)
                rec["switch"] = sw
                records.append(rec)
                m = rec["meas"]
                print(f"    [{entry['test_type']} @ {entry['label']:>7}]  "
                      f"f={gsc._fmt('frequency', m['frequency'])}  "
                      f"duty={gsc._fmt('duty', m['duty'])}  "
                      f"Vhi={gsc._fmt('v_high', m['v_high'])}  "
                      f"Vlo={gsc._fmt('v_low', m['v_low'])}  "
                      f"→ {'PASS' if rec['verdict'] else 'FAIL'}")
    finally:
        if not simulate:
            bus.close()
        scope.close()

    return records


def run_power_module_phase(args):
    """Run the manual power-module sweep (HW_TEST_ALL_POWER_MODULE 0x1B) and
    return a flat list of per-setpoint records.

    For each switch the operator moves the probe ONCE; we then walk the full
    frequency × duty grid at the fixed dead-band, measuring the gate each time.
    """
    import run_power_module_sweep as pm
    import run_gate_scope_check as gsc
    from hw_protocol import HwTestProtocol
    from scope_rs import RohdeScope

    protocol = HwTestProtocol()
    simulate = args.simulate
    bus = None if simulate else gsc._open_can()
    scope = RohdeScope(resource=args.resource, backend=args.backend,
                       simulate=simulate).open()

    freq_points = (args.pm_freq_points if args.pm_freq_points is not None
                   else gsc.gen_points(args.pm_freq_min, args.pm_freq_max,
                                       args.pm_freq_step))
    duty_points = (args.pm_duty_points if args.pm_duty_points is not None
                   else gsc.gen_points(args.pm_duty_min, args.pm_duty_max,
                                       args.pm_duty_step))
    grid = pm.build_grid(freq_points, duty_points)
    edge_t_div = args.edge_tdiv if args.edge_tdiv and args.edge_tdiv > 0 else None

    print("\n" + "=" * 72)
    print("  PHASE 3 — Manual power-module sweep (HW_TEST_ALL_POWER_MODULE 0x1B)")
    print(f"  Scope     : {scope.idn()}")
    print(f"  Scope ch  : CH{args.scope_ch}  probe {args.probe_atten:g}:1")
    print(f"  Dead-band : {args.deadband_ns:g} ns")
    print(f"  Sweep     : freq {freq_points} kHz × duty {duty_points} %  "
          f"({len(grid)} pts/switch)")
    print("=" * 72)

    scope.full_setup(args.scope_ch, v_div=gsc.DEFAULT_V_DIV,
                     offset=gsc.DEFAULT_OFFSET, probe_atten=args.probe_atten,
                     t_div=pm._tdiv_for(freq_points[0]),
                     trig_level=gsc.DEFAULT_TRIG_LVL)

    # No warm-up and no initial _start_pm_test — instead, every time the
    # operator changes the voltage probe the gate-drivers report a "not ready"
    # condition. We reset the drivers per switch by cycling the test:
    #     SET_TEST(HW_TEST_NO_TEST)  →  SET_TEST(HW_TEST_ALL_POWER_MODULE)
    # (+ re-pin the dead-band, because the start hook resets it to default).
    # This is done after each probe-move confirmation.

    records = []
    try:
        for sw in args.switches:
            print("\n  " + "═" * 68)
            print(f"  ⚠  Move the voltage probe to the  {sw}  gate (isolated PWM).")
            print("  " + "═" * 68)
            if not simulate and not args.no_prompts:
                try:
                    input(f"  Press ENTER when the probe is on {sw} … ")
                except (EOFError, KeyboardInterrupt):
                    print("\n  Power-module phase aborted by operator."); break

            if not simulate:
                # Per-switch driver reset (clears the "not ready" condition
                # caused by the probe change): stop the test, then re-enter
                # ALL_POWER_MODULE which re-initialises the drivers; re-pin
                # the dead-band (reset to default by the start hook).
                print(f"  Resetting drivers for {sw}: NO_TEST → ALL_POWER_MODULE …")
                pm._stop_pm_test(bus, protocol)
                time.sleep(0.2)
                pm._start_pm_test(bus, protocol, args.deadband_ns,
                                  enable_phases=False, startup_delay=0.0)

            for freq_khz, duty_pct in grid:
                # switch=sw → switch-aware duty verdict (bottom = complement)
                rec = pm.measure_pm_setpoint(scope, bus, protocol, args.scope_ch,
                                             freq_khz, duty_pct, args.deadband_ns,
                                             simulate, edge_t_div=edge_t_div,
                                             switch=sw)
                rec["switch"] = sw
                records.append(rec)
                m = rec["meas"]
                print(f"    [f={freq_khz:>5g} kHz duty={duty_pct:>5g} %]  "
                      f"f={gsc._fmt('frequency', m['frequency'])}  "
                      f"duty={gsc._fmt('duty', m['duty'])}  "
                      f"Vhi={gsc._fmt('v_high', m['v_high'])}  "
                      f"Vlo={gsc._fmt('v_low', m['v_low'])}  "
                      f"→ {'PASS' if rec['verdict'] else 'FAIL'}")
    finally:
        if not simulate:
            pm._stop_pm_test(bus, protocol)
            bus.close()
        scope.close()

    return records


# ── main ───────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sequence", "-s", default=TEST_SEQUENCE,
                   choices=["A0_A1", "A0", "A1", "B0", "B1", "B2"])
    p.add_argument("--unit-sn", "-u", default=UNIT_SN)
    p.add_argument("--operator", "-o", default=OPERATOR)
    p.add_argument("--hw-version", type=int, default=HW_VERSION_OVERRIDE)
    p.add_argument("--no-prompts", action="store_true",
                   help="Skip all manual-hookup prompts (campaign + scope phase)")
    p.add_argument("--quiet", "-q", action="store_true")

    # Phase 2 (gate scope) options
    p.add_argument("--scope", action="store_true",
                   help="Also run the manual gate scope checks (phase 2)")
    p.add_argument("--scope-ch", type=int, default=1)
    p.add_argument("--resource", default=None,
                   help="Explicit VISA resource (USB or TCPIP)")
    p.add_argument("--backend", default="@ivi",
                   help="VISA backend: '@ivi' (vendor VISA — required for USB "
                        "on this bench, default) or '@py' (pyvisa-py)")
    p.add_argument("--freq-khz", type=float, default=16.0)
    p.add_argument("--duty", type=float, default=50.0)
    p.add_argument("--range-verify", action="store_true",
                   help="Scope phase measures several points across each sweep "
                        "instead of a single setpoint")
    p.add_argument("--freq-points", nargs="+", type=float, default=None,
                   help="Explicit frequency points (kHz) for --range-verify")
    p.add_argument("--freq-min", type=float, default=10.0,
                   help="Frequency sweep min (kHz) (FW range 10)")
    p.add_argument("--freq-max", type=float, default=30.0,
                   help="Frequency sweep max (kHz) (FW range 30)")
    p.add_argument("--freq-step", type=float, default=5.0,
                   help="Frequency sweep step (kHz)")
    p.add_argument("--duty-points", nargs="+", type=float, default=None,
                   help="Duty points (%%) for --range-verify")
    p.add_argument("--edge-tdiv", type=float, default=100e-9,
                   help="Fast timebase (s/div) for accurate rise/fall "
                        "(default 100e-9). 0 disables edge-zoom.")
    p.add_argument("--probe-atten", type=float, default=10.0)
    p.add_argument("--switches", nargs="+", default=SWITCHES)
    p.add_argument("--simulate", action="store_true",
                   help="Gate scope phase uses canned scope data (no scope HW)")

    # Phase 3 (power-module sweep, HW_TEST_ALL_POWER_MODULE 0x1B) options
    p.add_argument("--power-module", action="store_true",
                   help="Also run the manual power-module sweep (phase 3): "
                        "sweeps frequency × duty at a fixed dead-band while "
                        "you probe each switch gate.")
    p.add_argument("--deadband-ns", type=float, default=1000.0,
                   help="Power-module dead-band in ns (default 1000 = 1 µs)")
    p.add_argument("--pm-freq-min", type=float, default=10.0,
                   help="Power-module freq sweep min (kHz)")
    p.add_argument("--pm-freq-step", type=float, default=10.0,
                   help="Power-module freq sweep step (kHz) (default 10 → 10,20,30)")
    p.add_argument("--pm-freq-max", type=float, default=30.0,
                   help="Power-module freq sweep max (kHz)")
    p.add_argument("--pm-freq-points", nargs="+", type=float, default=None,
                   help="Explicit power-module freq points (kHz)")
    p.add_argument("--pm-duty-min", type=float, default=25.0,
                   help="Power-module duty sweep min (%%, sent per-unit)")
    p.add_argument("--pm-duty-step", type=float, default=25.0,
                   help="Power-module duty sweep step (%%)")
    p.add_argument("--pm-duty-max", type=float, default=75.0,
                   help="Power-module duty sweep max (%%)")
    p.add_argument("--pm-duty-points", nargs="+", type=float, default=None,
                   help="Explicit power-module duty points (%%)")
    p.add_argument("--pm-warmup", type=float, default=0.0,
                   help="(Deprecated/unused) Power-stage warm-up is no longer "
                        "required because Phase 2 now performs a per-switch "
                        "driver reset (NO_TEST → ALL_POWER_MODULE) after each "
                        "probe move. Kept for CLI back-compat; default 0.")

    # ── 3-phase campaign control ────────────────────────────────────────────
    # Phase 1 — Self auto-verification (default ON; --no-self to skip).
    # Phase 2 — Power modules scope sweep (--power-module to enable; above).
    # Phase 3 — DAC-injection loopback tests (--loopback to enable; always
    #           interactive even with --no-prompts because hookups are required).
    # --all = enable all three phases (Phase 1 + Phase 2 + Phase 3).
    p.add_argument("--no-self", action="store_true",
                   help="Skip Phase 1 (self auto-verification tests)")
    p.add_argument("--loopback", action="store_true",
                   help="Run Phase 3 (DAC-injection loopback tests, interactive)")
    p.add_argument("--all", action="store_true",
                   help="Shorthand: Phase 1 (self) + Phase 2 (power module) + Phase 3 (loopback)")
    args = p.parse_args()
    if args.all:
        args.power_module = True
        args.loopback = True
        # --no-self can still suppress Phase 1 even with --all

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    sn_safe = args.unit_sn.replace("/", "-").replace(" ", "_")
    os.makedirs(_RESULTS_DIR, exist_ok=True)
    csv_path  = os.path.join(_RESULTS_DIR, f"test_results_{sn_safe}_{ts}.csv")
    xlsx_path = os.path.join(_RESULTS_DIR, f"ValidationReport_{sn_safe}_{ts}.xlsx")

    # Derive the per-phase sequence names from the base sequence.
    # B-sample is split into <X>_SELF (Phase 1) and <X>_LOOPBACK (Phase 3);
    # A-sample has no split, so the whole list runs as Phase 1.
    base_seq = args.sequence.upper()
    if base_seq in ("B0", "B1", "B2"):
        seq_self = f"{base_seq}_SELF"
        seq_loop = f"{base_seq}_LOOPBACK"
    else:
        seq_self = base_seq
        seq_loop = None
    phase_labels = []

    # ── Phase 1: Self auto-verification (no operator input) ──────────────
    session_meta = None
    results = []
    if not args.no_self:
        print("=" * 72)
        print("  PHASE 1 — Self auto-verification (firmware tests, no operator input)")
        print("=" * 72)
        session_meta, results_p1 = execute_campaign(
            sequence_name        = seq_self,
            unit_sn              = args.unit_sn,
            operator             = args.operator,
            results_csv          = csv_path,
            verbose              = not args.quiet,
            hw_version           = args.hw_version,
            interactive_prompts  = False,        # Phase 1 is always unattended
        )
        for r in results_p1:
            r["phase"] = 1
        results.extend(results_p1)
        phase_labels.append(f"P1:Self({len(results_p1)})")

    # ── Optional: legacy gate scope checks (--scope) ─────────────────────
    scope_records = None
    if args.scope:
        scope_records = run_gate_scope_phase(args)
        if session_meta is not None:
            session_meta["scope_setpoints"] = (
                f"freq {args.freq_khz} kHz, duty {args.duty} %")

    # ── Phase 2: Power-modules sweep (HW_TEST_ALL_POWER_MODULE, scope) ──
    pm_records = None
    if args.power_module:
        print("=" * 72)
        print("  PHASE 2 — Power modules (HW_TEST_ALL_POWER_MODULE 0x1B, scope)")
        print("=" * 72)
        pm_records = run_power_module_phase(args)
        if session_meta is not None:
            session_meta["power_module_sweep"] = (
                f"freq {args.pm_freq_min}-{args.pm_freq_step}-{args.pm_freq_max} kHz, "
                f"duty {args.pm_duty_min}-{args.pm_duty_step}-{args.pm_duty_max} %, "
                f"dead-band {args.deadband_ns:g} ns")
        phase_labels.append(f"P2:PowerModule({len(pm_records) if pm_records else 0})")

    # ── Phase 3: DAC-injection loopback tests (operator hookups) ─────────
    if args.loopback:
        if seq_loop is None:
            print(f"[Phase 3] Loopback split is only defined for B-sample "
                  f"sequences; skipping (--sequence={args.sequence}).")
        else:
            print("=" * 72)
            print("  PHASE 3 — Operator-verified tests (LED visual + DAC hookups)")
            print("=" * 72)
            csv_loop = csv_path[:-4] + "_loopback.csv"
            meta_p3, results_p3 = execute_campaign(
                sequence_name        = seq_loop,
                unit_sn              = args.unit_sn,
                operator             = args.operator,
                results_csv          = csv_loop,
                verbose              = not args.quiet,
                hw_version           = args.hw_version,
                interactive_prompts  = True,    # ALWAYS prompt — hookups required
            )
            for r in results_p3:
                r["phase"] = 3
            results.extend(results_p3)
            if session_meta is None:
                session_meta = meta_p3
            else:
                session_meta["sequence"] = (
                    f"{session_meta['sequence']} + {meta_p3['sequence']}")
            phase_labels.append(f"P3:Loopback({len(results_p3)})")

    # Fallback meta in case all phases were skipped (avoid crash on report)
    if session_meta is None:
        session_meta = {
            "test_date":     datetime.datetime.now().isoformat(timespec="seconds"),
            "unit_sn":       args.unit_sn,
            "operator":      args.operator,
            "sequence":      "(no phase enabled)",
            "can_interface": "—", "can_channel": "—", "can_bitrate": "—",
        }
    session_meta["phases_run"] = " + ".join(phase_labels) if phase_labels else "(none)"

    # ── Single unified report ────────────────────────────────────────────
    out = generate_validation_report(
        results=results,
        session_meta=session_meta,
        output_path=xlsx_path,
        scope_records=scope_records,
        pm_records=pm_records,
    )

    # ── Summary (per-phase + overall) ────────────────────────────────────
    def _phase_counts(phase_n):
        rs = [r for r in results if r.get("phase") == phase_n]
        return (sum(1 for r in rs if r["result"] == "PASS"),
                sum(1 for r in rs if r["result"] == "FAIL"),
                len(rs))
    n1p, n1f, n1t = _phase_counts(1)
    n3p, n3f, n3t = _phase_counts(3)
    print("\n" + "=" * 72)
    print(f"  PCBA VERIFICATION COMPLETE — Unit {args.unit_sn}")
    if n1t:
        print(f"  Phase 1 — Self auto-verif : PASS={n1p}  FAIL={n1f}  ({n1t} tests)")
    if pm_records is not None:
        pp = sum(1 for r in pm_records if r["verdict"])
        print(f"  Phase 2 — Power modules   : PASS={pp}/{len(pm_records)} "
              f"({len(args.switches)} switches × freq×duty grid)")
    if n3t:
        print(f"  Phase 3 — Operator-verif. : PASS={n3p}  FAIL={n3f}  ({n3t} tests)")
    if scope_records is not None:
        sp = sum(1 for r in scope_records if r["verdict"])
        print(f"  Gate scope (legacy)       : PASS={sp}/{len(scope_records)}")
    print(f"  Report                    : {out}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
