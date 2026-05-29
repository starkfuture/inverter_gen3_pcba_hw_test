#!/usr/bin/env python3
"""
pm_step_session.py  –  step-by-step (one switch at a time) bench session for
the power-module sweep (HW_TEST_ALL_POWER_MODULE 0x1B).

Designed for an operator-paced flow where you confirm each probe move yourself
before any measurement runs:

    measure  → run the full defined sweep on ONE switch, append to a session
    report   → write the single unified PowerModuleSweep workbook for all
               switches measured so far
    status   → show which switches have been captured

Each `measure` call opens the CAN bus + scope, enters the power-module test,
pins the dead-band, walks the frequency × duty grid for the named switch,
stores the records in a session file, then releases the hardware. Because you
drive the probe moves between calls, no in-process ENTER prompt is used.

Examples
────────
  python pm_step_session.py measure --switch UTOP --session B1run1
  python pm_step_session.py measure --switch UBOT --session B1run1
  ...
  python pm_step_session.py report  --session B1run1
  python pm_step_session.py status  --session B1run1
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import time
import pickle
import argparse
import datetime

import run_power_module_sweep as pm
import run_gate_scope_check as gsc
from hw_protocol import HwTestProtocol
from scope_rs import RohdeScope

SWITCHES = gsc.SWITCHES
_RESULTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results"))


def _session_path(name):
    return os.path.join(_RESULTS_DIR, f".pm_session_{name}.pkl")


def _load_session(name):
    path = _session_path(name)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return pickle.load(f)
    return {"meta": {}, "switches": {}}


def _save_session(name, data):
    os.makedirs(_RESULTS_DIR, exist_ok=True)
    with open(_session_path(name), "wb") as f:
        pickle.dump(data, f)


def _grids(args):
    freq_points = (args.freq_points if args.freq_points is not None
                   else gsc.gen_points(args.freq_min, args.freq_max, args.freq_step))
    duty_points = (args.duty_points if args.duty_points is not None
                   else gsc.gen_points(args.duty_min, args.duty_max, args.duty_step))
    return freq_points, duty_points


# ── measure one switch ─────────────────────────────────────────────────────

def cmd_measure(args):
    freq_points, duty_points = _grids(args)
    grid = pm.build_grid(freq_points, duty_points)
    edge_t_div = args.edge_tdiv if args.edge_tdiv and args.edge_tdiv > 0 else None

    protocol = HwTestProtocol()
    bus = None if args.simulate else gsc._open_can()
    scope = RohdeScope(resource=args.resource, backend=args.backend,
                       simulate=args.simulate).open()

    print("=" * 72)
    print(f"  POWER-MODULE SWEEP — switch {args.switch}")
    print(f"  Scope     : {scope.idn()}")
    print(f"  Scope ch  : CH{args.scope_ch}  probe {args.probe_atten:g}:1")
    print(f"  Dead-band : {args.deadband_ns:g} ns")
    print(f"  Sweep     : freq {freq_points} kHz × duty {duty_points} %  "
          f"({len(grid)} pts)")
    print("=" * 72)

    scope.full_setup(args.scope_ch, v_div=gsc.DEFAULT_V_DIV,
                     offset=gsc.DEFAULT_OFFSET, probe_atten=args.probe_atten,
                     t_div=pm._tdiv_for(freq_points[0]),
                     trig_level=gsc.DEFAULT_TRIG_LVL)
    # Default (live-sweep) model — mirrors the original interactive tool:
    # start the test ONCE, wait a real warm-up so the isolated gate-driver
    # supplies/bootstraps come up and the stage is switching, then change
    # setpoints live (no stop/restart). clean_restart is the opposite (kills
    # the warm-up each point) and is usually worse — kept only as an option.
    if not args.simulate and not args.clean_restart:
        # EN_DIS_PHASE is not needed for ALL_POWER_MODULE (the test drives the
        # branches itself), so don't send it.
        pm._start_pm_test(bus, protocol, args.deadband_ns, enable_phases=False)
        if args.warmup > 0:
            print(f"  Warming up the power stage for {args.warmup:g}s "
                  f"(supplies/bootstraps) before measuring …")
            time.sleep(args.warmup)

    recs = []
    try:
        for freq_khz, duty_pct in grid:
            rec = pm.measure_pm_setpoint(scope, bus, protocol, args.scope_ch,
                                         freq_khz, duty_pct, args.deadband_ns,
                                         args.simulate, edge_t_div=edge_t_div,
                                         settle_s=args.settle,
                                         clean_restart=args.clean_restart,
                                         switch=args.switch)
            rec["switch"] = args.switch
            recs.append(rec)
            m = rec["meas"]
            print(f"    [f={freq_khz:>5g} kHz duty={duty_pct:>5g} %]  "
                  f"f={pm._fmt('frequency', m['frequency'])}  "
                  f"duty={pm._fmt('duty', m['duty'])}  "
                  f"Vhi={pm._fmt('v_high', m['v_high'])}  "
                  f"Vlo={pm._fmt('v_low', m['v_low'])}  "
                  f"rise={pm._fmt('rise_time', m['rise_time'])}  "
                  f"fall={pm._fmt('fall_time', m['fall_time'])}  "
                  f"→ {'PASS' if rec['verdict'] else 'FAIL'}")
        idn = scope.idn()
    finally:
        if not args.simulate:
            pm._stop_pm_test(bus, protocol)
            bus.close()
        scope.close()

    # accumulate into the session
    data = _load_session(args.session)
    data["switches"][args.switch] = recs
    data["meta"].update(dict(
        unit_sn=args.unit_sn, operator=args.operator, scope_idn=idn,
        probe_atten=f"{args.probe_atten:g}:1",
        deadband=f"{args.deadband_ns:g} ns ({args.deadband_ns/1000:g} µs)",
        sweep_str=(f"freq {freq_points} kHz × duty {duty_points} %  "
                   f"({len(freq_points)}×{len(duty_points)} = {len(grid)} pts/switch)"),
        date=datetime.datetime.now().isoformat(timespec="seconds")))
    _save_session(args.session, data)

    n_pass = sum(1 for r in recs if r["verdict"])
    done = [s for s in SWITCHES if s in data["switches"]]
    todo = [s for s in SWITCHES if s not in data["switches"]]
    print("-" * 72)
    print(f"  {args.switch}: {n_pass}/{len(recs)} setpoints PASS  →  saved to session '{args.session}'")
    print(f"  Captured : {', '.join(done)}")
    if todo:
        print(f"  Remaining: {', '.join(todo)}  (move the probe, then run the next switch)")
    else:
        print(f"  All 6 switches captured — run:  python pm_step_session.py report --session {args.session}")
    print("=" * 72)
    return 0


# ── status ─────────────────────────────────────────────────────────────────

def cmd_status(args):
    data = _load_session(args.session)
    print(f"Session '{args.session}':")
    if not data["switches"]:
        print("  (no switches captured yet)")
        return 0
    for sw in SWITCHES:
        if sw in data["switches"]:
            recs = data["switches"][sw]
            npass = sum(1 for r in recs if r["verdict"])
            print(f"  {sw:5s}  {npass}/{len(recs)} PASS")
        else:
            print(f"  {sw:5s}  — not captured")
    return 0


# ── report ─────────────────────────────────────────────────────────────────

def cmd_report(args):
    data = _load_session(args.session)
    if not data["switches"]:
        print("No switches captured — nothing to report.")
        return 1
    records = []
    for sw in SWITCHES:
        for rec in data["switches"].get(sw, []):
            rec.setdefault("switch", sw)
            pm.recompute_verdict(rec)   # switch-aware (bottom = complement)
            records.append(rec)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    sn_safe = data["meta"].get("unit_sn", "PCB").replace("/", "-").replace(" ", "_")
    out = os.path.join(_RESULTS_DIR, f"PowerModuleSweep_{sn_safe}_{ts}.xlsx")
    out = pm.write_report(records, data["meta"], out)

    npass = sum(1 for r in records if r["verdict"])
    print("=" * 72)
    print(f"  POWER-MODULE SWEEP REPORT — {npass}/{len(records)} setpoints PASS "
          f"({len(data['switches'])} switch(es))")
    print(f"  Report: {out}")
    print("=" * 72)
    return 0


# ── main ─────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--session", default="pm", help="Session name (default 'pm')")

    # measure
    m = sub.add_parser("measure", help="Run the sweep on one switch")
    add_common(m)
    m.add_argument("--switch", required=True, choices=SWITCHES)
    # sweep (defaults match the bench request: 10-2-30 kHz, 25/50/75 %, 1 µs)
    m.add_argument("--freq-min", type=float, default=10.0)
    m.add_argument("--freq-step", type=float, default=10.0)   # 10,20,30 kHz
    m.add_argument("--freq-max", type=float, default=30.0)
    m.add_argument("--freq-points", nargs="+", type=float, default=None)
    m.add_argument("--duty-min", type=float, default=25.0)
    m.add_argument("--duty-step", type=float, default=25.0)
    m.add_argument("--duty-max", type=float, default=75.0)
    m.add_argument("--duty-points", nargs="+", type=float, default=None)
    m.add_argument("--deadband-ns", type=float, default=1000.0)
    m.add_argument("--edge-tdiv", type=float, default=100e-9)
    # Warm-up + settle (live-sweep model — mirrors the original interactive
    # tool, which changes setpoints on an already-warm running stage).
    m.add_argument("--warmup", type=float, default=60.0,
                   help="Seconds to let the power stage warm up (supplies/"
                        "bootstraps) AFTER starting the test, BEFORE the first "
                        "measurement (default 60). Only used in live-sweep mode.")
    m.add_argument("--settle", type=float, default=2.0,
                   help="Seconds to settle after pinning each setpoint, before "
                        "measuring (default 2.0).")
    # Optional clean-restart-per-point mode (stop+start each setpoint). This
    # re-inits the gate-driver supplies every point, so they never finish
    # charging — empirically worse than the warm-up live sweep. Off by default.
    m.add_argument("--clean-restart", action="store_true",
                   help="Stop+restart the test for each setpoint instead of the "
                        "warm-up live sweep. Usually worse (re-kills warm-up).")
    m.set_defaults(clean_restart=False)
    # scope / io
    m.add_argument("--scope-ch", type=int, default=1)
    m.add_argument("--resource", default=None)
    m.add_argument("--backend", default="@ivi")
    m.add_argument("--probe-atten", type=float, default=gsc.DEFAULT_PROBE_ATT)
    m.add_argument("--unit-sn", default="PCB-B1")
    m.add_argument("--operator", default="Carlos Miguel Espinar")
    m.add_argument("--simulate", action="store_true")
    m.set_defaults(func=cmd_measure)

    # report
    r = sub.add_parser("report", help="Write the unified workbook")
    add_common(r)
    r.set_defaults(func=cmd_report)

    # status
    s = sub.add_parser("status", help="Show captured switches")
    add_common(s)
    s.set_defaults(func=cmd_status)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
