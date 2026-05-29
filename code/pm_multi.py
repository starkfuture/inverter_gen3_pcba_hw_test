"""
pm_multi.py  –  power-module sweep with a CONFIGURABLE number of parallel
scope probes and per-probe gain (attenuation).

Same firmware test as pm_step_session.py (HW_TEST_ALL_POWER_MODULE 0x1B, which
drives every branch synchronously). You choose how many switches to probe at
once (1..4) and the probe attenuation of each. Because all branches switch
together, the channels are read back-to-back on the same free-running
acquisition; the 7 measurement slots and the trigger source follow each channel
in turn (the RTM3004 has only 8 measurement slots, so 3×7 can't all coexist).

Defaults to a SINGLE probe (one switch, one channel) — i.e. the proven
one-probe-at-a-time behaviour. Add more switches to probe in parallel.

⚠  Parallel probing only works when the probed gates share a common ground
   reference. These gate drives are ISOLATED; tying several ground-referenced
   probes to independent isolated domains shorts their grounds through the
   scope chassis and collapses the gate drive. Probe in parallel only switches
   that share a reference, or use one probe at a time.

Probe count / gain
──────────────────
    --switches UBOT                 → 1 probe  on CH1            (default mode)
    --switches UBOT VBOT WBOT       → 3 probes on CH1/CH2/CH3
    --group bottom                  → shortcut for UBOT VBOT WBOT
    --group top                     → shortcut for UTOP VTOP WTOP
    --probe-atten 10                → x10 on every probe (default)
    --probe-atten 1                 → x1  on every probe
    --probe-atten 10 1 10           → per-channel gain (must match #switches)
    --channels 1 3 4                → explicit channel numbers (default 1..N)

Records are saved in the SAME session-pickle format as pm_step_session.py, so
the existing report tooling works unchanged:

    python pm_multi.py --switches UBOT VBOT WBOT --probe-atten 1 --session B1_multi
    python pm_step_session.py report --session B1_multi
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

from hw_protocol import HwTestProtocol
from scope_rs import RohdeScope
import run_power_module_sweep as pm
from run_gate_scope_check import (
    gen_points, _open_can, DEFAULT_PROBE_ATT, DEFAULT_V_DIV, DEFAULT_OFFSET,
    DEFAULT_TRIG_LVL,
)

SWITCHES = ["UTOP", "UBOT", "VTOP", "VBOT", "WTOP", "WBOT"]
GROUPS = {
    "bottom": ["UBOT", "VBOT", "WBOT"],
    "top":    ["UTOP", "VTOP", "WTOP"],
}
_RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")


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


def _resolve_probes(args):
    """Return [(channel, switch, atten), ...] from the CLI options.

    Default (nothing specified): a single probe on the first switch, CH1, at
    the standard gate-probe attenuation."""
    if args.switches:
        switches = args.switches
    elif args.group:
        switches = GROUPS[args.group]
    else:
        switches = ["UTOP"]            # default: single probe

    n = len(switches)
    if n < 1 or n > 4:
        raise SystemExit("Choose between 1 and 4 switches (the scope has 4 channels).")

    channels = args.channels if args.channels else list(range(1, n + 1))
    if len(channels) != n:
        raise SystemExit(f"--channels must list exactly {n} channel(s) for "
                         f"{n} switch(es); got {channels}.")

    attens = args.probe_atten
    if len(attens) == 1:
        attens = attens * n
    elif len(attens) != n:
        raise SystemExit(f"--probe-atten must be one value (applied to all) or "
                         f"exactly {n} values; got {attens}.")

    return list(zip(channels, switches, attens))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    # Probe selection / gain
    p.add_argument("--switches", nargs="+", default=None, choices=SWITCHES,
                   help="Switch(es) to probe, mapped to channels in order. "
                        "Default: a single probe on UTOP.")
    p.add_argument("--group", choices=list(GROUPS), default=None,
                   help="Shortcut: 'bottom'=UBOT VBOT WBOT, 'top'=UTOP VTOP WTOP")
    p.add_argument("--channels", nargs="+", type=int, default=None,
                   help="Explicit scope channel numbers (default 1..N)")
    p.add_argument("--probe-atten", nargs="+", type=float, default=[DEFAULT_PROBE_ATT],
                   help="Probe attenuation: one value for all, or one per switch "
                        f"(default {DEFAULT_PROBE_ATT:g} = 10:1)")
    p.add_argument("--session", default="B1_multi")
    # Sweep grid (same defaults as the single-switch sweep)
    p.add_argument("--freq-min", type=float, default=10.0)
    p.add_argument("--freq-step", type=float, default=10.0)
    p.add_argument("--freq-max", type=float, default=30.0)
    p.add_argument("--freq-points", nargs="+", type=float, default=None)
    p.add_argument("--duty-min", type=float, default=25.0)
    p.add_argument("--duty-step", type=float, default=25.0)
    p.add_argument("--duty-max", type=float, default=75.0)
    p.add_argument("--duty-points", nargs="+", type=float, default=None)
    p.add_argument("--deadband-ns", type=float, default=1000.0)
    p.add_argument("--edge-tdiv", type=float, default=100e-9,
                   help="Fast timebase (s/div) for rise/fall; 0 disables")
    p.add_argument("--settle", type=float, default=0.8)
    p.add_argument("--warmup", type=float, default=0.0)
    # Scope vertical (real gate volts; probe attenuation applied separately)
    p.add_argument("--v-div", type=float, default=DEFAULT_V_DIV)
    p.add_argument("--offset", type=float, default=DEFAULT_OFFSET)
    p.add_argument("--trig-level", type=float, default=DEFAULT_TRIG_LVL)
    p.add_argument("--resource", default=None)
    p.add_argument("--backend", default="@ivi")
    p.add_argument("--unit-sn", default="PCB-B1")
    p.add_argument("--operator", default="Carlos Miguel Espinar")
    p.add_argument("--simulate", action="store_true")
    args = p.parse_args()

    probes = _resolve_probes(args)            # [(ch, switch, atten), ...]
    freq_points = (args.freq_points if args.freq_points is not None
                   else gen_points(args.freq_min, args.freq_max, args.freq_step))
    duty_points = (args.duty_points if args.duty_points is not None
                   else gen_points(args.duty_min, args.duty_max, args.duty_step))
    edge_t_div = args.edge_tdiv if args.edge_tdiv and args.edge_tdiv > 0 else None
    grid = pm.build_grid(freq_points, duty_points)

    protocol = HwTestProtocol()
    bus = None if args.simulate else _open_can()
    scope = RohdeScope(resource=args.resource, backend=args.backend,
                       simulate=args.simulate).open()

    mode = "single probe" if len(probes) == 1 else f"{len(probes)} parallel probes"
    print("=" * 72)
    print(f"  POWER-MODULE SWEEP — {mode}")
    print(f"  Scope     : {scope.idn()}")
    print(f"  Probes    : " +
          "  ".join(f"CH{c}={s}@{a:g}:1" for c, s, a in probes))
    print(f"  Dead-band : {args.deadband_ns:g} ns")
    print(f"  Sweep     : freq {freq_points} kHz × duty {duty_points} %  "
          f"({len(grid)} pts)")
    print("=" * 72)

    # Configure each vertical once (full_setup would *RST per channel and
    # disable the others, so do it by hand). Trigger initially on the first ch.
    if not args.simulate:
        scope.reset()
        for ch, _sw, atten in probes:
            scope.configure_channel(ch, v_div=args.v_div, offset=args.offset,
                                    probe_atten=atten)
        scope.configure_timebase(pm._tdiv_for(freq_points[0]))
        scope.configure_trigger(probes[0][0], level=args.trig_level)

        # Live-sweep model (same as pm_step_session): start once, optional
        # warm-up, then change setpoints live. enable_phases=False —
        # ALL_POWER_MODULE drives the branches itself (see bench-lessons #1).
        pm._start_pm_test(bus, protocol, args.deadband_ns, enable_phases=False)
        if args.warmup > 0:
            print(f"  Warming up the power stage for {args.warmup:g}s …")
            time.sleep(args.warmup)

    recs_by_sw = {sw: [] for _c, sw, _a in probes}
    try:
        for freq_khz, duty_pct in grid:
            duty_pu = duty_pct / 100.0
            if not args.simulate:
                pm._pin_setpoint(bus, protocol, freq_khz, duty_pu)
            scope.configure_timebase(pm._tdiv_for(freq_khz))
            time.sleep(args.settle)

            line = [f"    [f={freq_khz:>5g} kHz duty={duty_pct:>5g} %]"]
            for ch, sw, _atten in probes:
                if not args.simulate:
                    scope.setup_measurements(ch)            # point 7 slots to CHx
                    scope.configure_trigger(ch, level=args.trig_level)
                meas = scope.measure(ch, settle_s=args.settle, edge_t_div=edge_t_div)
                checks, verdict = pm._eval_checks(sw, freq_khz, duty_pct, meas)
                rec = dict(freq_khz=freq_khz, duty_pct=duty_pct,
                           deadband_ns=args.deadband_ns, meas=meas,
                           checks=checks, verdict=verdict, switch=sw)
                recs_by_sw[sw].append(rec)
                line.append(f"{sw}:{'PASS' if verdict else 'FAIL'} "
                            f"d={pm._fmt('duty', meas['duty'])} "
                            f"Vhi={pm._fmt('v_high', meas['v_high'])}")
            print("  ".join(line))
        idn = scope.idn()
    finally:
        if not args.simulate:
            pm._stop_pm_test(bus, protocol)
            bus.close()
        scope.close()

    # Save into the shared session format (pm_step_session-compatible).
    data = _load_session(args.session)
    for _ch, sw, _a in probes:
        data["switches"][sw] = recs_by_sw[sw]
    atten_str = ", ".join(f"CH{c}:{a:g}:1" for c, _s, a in probes)
    data["meta"].update(dict(
        unit_sn=args.unit_sn, operator=args.operator, scope_idn=idn,
        probe_atten=atten_str,
        deadband=f"{args.deadband_ns:g} ns ({args.deadband_ns/1000:g} µs)",
        sweep_str=(f"freq {freq_points} kHz × duty {duty_points} %  "
                   f"({len(freq_points)}×{len(duty_points)} = {len(grid)} pts/switch)"),
        date=datetime.datetime.now().isoformat(timespec="seconds")))
    _save_session(args.session, data)

    print("-" * 72)
    for _ch, sw, _a in probes:
        recs = recs_by_sw[sw]
        np_ = sum(1 for r in recs if r["verdict"])
        print(f"  {sw}: {np_}/{len(recs)} setpoints PASS")
    done = [s for s in SWITCHES if s in data["switches"]]
    todo = [s for s in SWITCHES if s not in data["switches"]]
    print(f"  Captured : {', '.join(done)}")
    if todo:
        print(f"  Remaining: {', '.join(todo)}")
    else:
        print(f"  All 6 captured — run:  python pm_step_session.py report --session {args.session}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
