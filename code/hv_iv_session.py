#!/usr/bin/env python3
"""
hv_iv_session.py  –  step-by-step (one terminal placement at a time) bench
session for the Phase-3 HV-supply characterization of the inverter PCBA.

This replaces the old DAC-injection unipolar/bipolar voltage loopbacks
(HW_TEST_POWER_UNIPLR_V / _BIPLR_V, 0x2A / 0x2B) with a real source-driven
characterization that uses an EA laboratory supply (see ea_supply.py):

    voltage  → place the supply on a sense input, ramp 0→400 V in 50 V steps,
               read back what the PCB reports over CAN, compare to the supply
               setpoint (modifiable limits) and measure the dispersion over
               N repeats per step.
    current  → drive the EA in CC mode through the phase shunts, sweep the
               magnitude 0→20 A in 5 A steps, read all 3 phase-current
               channels at once; flip the terminals to cover the negative
               orientation (-20→0 A).

Designed for an operator-paced flow where you confirm each terminal move
yourself before any measurement runs (same model as pm_step_session.py):

    voltage  --point DC_LINK|UV|WV   → sweep one placement, append to session
    current  --orientation pos|neg   → sweep one orientation, append to session
    report                           → write the unified ValidationReport sheet(s)
    status                           → show what has been captured so far

The supply output is ALWAYS driven back to 0 V / 0 A and disabled at the end
of every sweep (and on abort), so the bench is never left energised between
terminal moves.

Examples
────────
  python hv_iv_session.py voltage --point DC_LINK --session B1hv --ea-resource ASRL6::INSTR
  python hv_iv_session.py voltage --point UV      --session B1hv --ea-resource ASRL6::INSTR
  python hv_iv_session.py voltage --point WV      --session B1hv --ea-resource ASRL6::INSTR
  python hv_iv_session.py current --orientation pos --session B1hv --ea-resource ASRL6::INSTR
  python hv_iv_session.py current --orientation neg --session B1hv --ea-resource ASRL6::INSTR
  python hv_iv_session.py report  --session B1hv

  # Dry-run with no hardware (canned EA + canned CAN readings):
  python hv_iv_session.py voltage --point DC_LINK --session demo --simulate
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import time
import math
import pickle
import random
import argparse
import datetime
import statistics
from typing import Dict, Any, List, Optional

from hw_protocol import HwTestProtocol
from hw_test_criteria import channel_name
from ea_supply import make_supply

_RESULTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results"))


# ── what we measure ─────────────────────────────────────────────────────────
# Voltage: one CAN channel per terminal placement. The operator places the
# supply terminals on the named sense input; we read this channel back.
VOLTAGE_POINTS: Dict[str, int] = {
    "DC_LINK": 4,   # ANLG[4]  DC-link voltage sense
    "UV":      5,   # ANLG[5]  UV phase voltage sense  ("phase U")
    "WV":      6,   # ANLG[6]  WV phase voltage sense  ("phase V")
}
# Default placement order the bench operator is prompted through: phase U,
# then phase V, then DC-link last (matches the bench cabling workflow).
VOLTAGE_POINT_ORDER = ["UV", "WV", "DC_LINK"]

# Current: all three phase-current channels are read at once.
CURRENT_CHANNELS = [1, 2, 3]   # ANLG[1..3]  I_Ph_U / I_Ph_V / I_Ph_W

# During the VOLTAGE test the supply only feeds the high-impedance sense
# dividers, so its output current is hard-limited to this ceiling — protects
# the board if a terminal is mis-placed onto a low-impedance node.
VOLTAGE_TEST_CURRENT_LIMIT_A = 0.5   # 500 mA

ADC_TEST_KEY = "HW_TEST_ALL_ADC_MEASUREMENTS"   # 0x03 — streams ch 1..6


# ── session persistence ─────────────────────────────────────────────────────

def _session_path(name):
    return os.path.join(_RESULTS_DIR, f".hv_session_{name}.pkl")


def _load_session(name):
    path = _session_path(name)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return pickle.load(f)
    return {"meta": {}, "voltage": {}, "current": {}}


def _save_session(name, data):
    os.makedirs(_RESULTS_DIR, exist_ok=True)
    with open(_session_path(name), "wb") as f:
        pickle.dump(data, f)


# ── CAN read helper ─────────────────────────────────────────────────────────

def _open_can():
    from run_gate_scope_check import _open_can as _gsc_open_can
    return _gsc_open_can()


def _enable_report(bus, protocol):
    """Send SET_TEST_ENV(REPORT_ENABLE | CLEAR_REBOOT) once so the firmware
    streams ANLG[] frames during the subsequent ALL_ADC_MEASUREMENTS reads."""
    from hw_can_utils import send_frame
    flags = (protocol.SF_HW_TEST_PROTOCOL_TEST_SET_ENV_FLAGS_REPORT_ENABLE
             | protocol.SF_HW_TEST_PROTOCOL_TEST_SET_ENV_FLAGS_CLEAR_REBOOT)
    res = protocol.sfHwTestProtocolProcessTxMessage(
        "SF_HW_TEST_PROTOCOL_RQST_SET_TEST_ENV", 0, flags)
    if res and res[0] > 0:
        send_frame(bus, res[1])
    time.sleep(0.2)


def _read_channels(bus, protocol, channels, timeout_ms=400):
    """Run ONE HW_TEST_ALL_ADC_MEASUREMENTS cycle and return {ch: value} for
    the requested channels (value None if the channel was not reported)."""
    from hw_test_runner import run_single_test
    rec = run_single_test(bus, protocol, ADC_TEST_KEY, "", 0, timeout_ms)
    av = rec.get("analog_values", {})
    return {ch: av.get(ch) for ch in channels}


# ── verdict helpers ─────────────────────────────────────────────────────────

def _tol_band(setpoint, tol_pct, tol_abs):
    """Symmetric tolerance band around |setpoint|: the wider of ±tol_pct·|sp|
    and ±tol_abs. Returns (half_width)."""
    return max(abs(setpoint) * tol_pct / 100.0, tol_abs)


def _stats(reads):
    """(mean, std_abs, std_rel_pct) over a list of floats (NaN-tolerant)."""
    vals = [v for v in reads if v is not None and v == v]
    if not vals:
        return float("nan"), float("nan"), float("nan")
    mean = sum(vals) / len(vals)
    std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    rel = (std / abs(mean) * 100.0) if mean else float("nan")
    return mean, std, rel


# ── voltage characterization ────────────────────────────────────────────────

def _sim_voltage_read(set_v):
    """Canned PCB reading for --simulate: setpoint + small gaussian noise."""
    return set_v + random.gauss(0.0, max(0.3, 0.004 * set_v))


def measure_voltage_point(point, ea, bus, protocol, *, set_points,
                          tol_pct, tol_abs, repeats, settle_s, read_gap_s,
                          simulate):
    """Sweep the EA voltage over `set_points` on one terminal placement,
    reading channel VOLTAGE_POINTS[point] back `repeats` times per step.

    The supply is enabled at the start, driven 0 V→…, and forced back to 0 V
    and disabled at the end (even on exception)."""
    ch = VOLTAGE_POINTS[point]
    ch_name = channel_name(ch)
    records = []

    if not simulate:
        ea.set_current_limit(VOLTAGE_TEST_CURRENT_LIMIT_A)   # 500 mA ceiling
        ea.set_voltage(0.0)
        ea.enable()
    try:
        for set_v in set_points:
            if not simulate:
                ea.set_voltage(set_v)
                time.sleep(settle_s)
            reads = []
            for _ in range(repeats):
                if simulate:
                    reads.append(_sim_voltage_read(set_v))
                else:
                    vals = _read_channels(bus, protocol, [ch])
                    reads.append(vals.get(ch))
                    time.sleep(read_gap_s)
            mean, std, rel = _stats(reads)
            band = _tol_band(set_v, tol_pct, tol_abs)
            lo, hi = set_v - band, set_v + band
            err_abs = (mean - set_v) if mean == mean else float("nan")
            err_pct = (err_abs / set_v * 100.0) if set_v else float("nan")
            verdict = bool(mean == mean and lo <= mean <= hi)
            rec = dict(kind="voltage", point=point, channel=ch,
                       channel_name=ch_name, set_v=set_v, reads=reads,
                       mean=mean, std=std, std_rel=rel,
                       err_abs=err_abs, err_pct=err_pct, lo=lo, hi=hi,
                       tol_str=f"±{tol_pct:g}% (min ±{tol_abs:g} V)",
                       verdict=verdict)
            records.append(rec)
            print(f"    [{point} set={set_v:>6.1f} V]  "
                  f"read={mean:7.2f} V  std={std:5.2f}  "
                  f"err={err_abs:+6.2f} V  "
                  f"→ {'PASS' if verdict else 'FAIL'}")
    finally:
        if not simulate:
            ea.set_voltage(0.0)
            ea.disable()
    return records


# ── current characterization ────────────────────────────────────────────────

def _sim_current_read(set_a, ch):
    """Canned phase reading for --simulate. Phase U (ch1) carries the injected
    current; the other phases sit near zero (a plausible single-leg path)."""
    base = set_a if ch == 1 else 0.0
    return base + random.gauss(0.0, max(0.05, 0.01 * abs(set_a)))


def measure_current_orientation(orientation, ea, bus, protocol, *,
                                set_mags, compliance_v, tol_pct, tol_abs,
                                repeats, settle_s, read_gap_s, simulate):
    """Drive the EA in CC mode through the phase shunts at each magnitude in
    `set_mags` (A) and read all 3 phase-current channels `repeats` times.

    `orientation` is "pos" or "neg"; the signed setpoint is +mag / -mag. The
    operator physically flips the terminals to change orientation (prompted by
    the caller). Output is forced to 0 A and disabled at the end."""
    sign = -1.0 if orientation == "neg" else +1.0
    records = []

    if not simulate:
        ea.set_voltage(compliance_v)   # low compliance ceiling
        ea.set_current_limit(0.0)
        ea.enable()
    try:
        for mag in set_mags:
            set_a = sign * mag
            if not simulate:
                ea.set_current_limit(mag)   # CC: regulate to this current
                ea.set_voltage(compliance_v)
                time.sleep(settle_s)
            phases = {}
            for _ in range(repeats):
                if simulate:
                    vals = {ch: _sim_current_read(set_a, ch)
                            for ch in CURRENT_CHANNELS}
                else:
                    vals = _read_channels(bus, protocol, CURRENT_CHANNELS)
                for ch in CURRENT_CHANNELS:
                    phases.setdefault(ch, []).append(vals.get(ch))
                time.sleep(read_gap_s)

            band = _tol_band(set_a, tol_pct, tol_abs)
            per_phase = {}
            best_ok = False
            for ch in CURRENT_CHANNELS:
                mean, std, rel = _stats(phases[ch])
                # Phase "matches" the injected current if its magnitude lands
                # within the tolerance band of |set_a| (sign depends on which
                # leg the operator wired, so compare on magnitude).
                ok = bool(mean == mean and
                          abs(abs(mean) - abs(set_a)) <= band)
                per_phase[ch] = dict(mean=mean, std=std, std_rel=rel, ok=ok)
                best_ok = best_ok or ok
            # At 0 A every phase should read ~0 (within the band): verdict is
            # all-phases-near-zero. Otherwise at least one phase must carry the
            # injected current.
            if mag == 0.0:
                verdict = all(abs(per_phase[ch]["mean"]) <= band
                              for ch in CURRENT_CHANNELS
                              if per_phase[ch]["mean"] == per_phase[ch]["mean"])
            else:
                verdict = best_ok
            rec = dict(kind="current", orientation=orientation, set_a=set_a,
                       compliance_v=compliance_v, phases=per_phase,
                       tol_str=f"±{tol_pct:g}% (min ±{tol_abs:g} A)",
                       verdict=bool(verdict))
            records.append(rec)
            means = "  ".join(f"{channel_name(ch).replace('I_Ph_','I')}="
                              f"{per_phase[ch]['mean']:+6.2f}"
                              for ch in CURRENT_CHANNELS)
            print(f"    [I set={set_a:+6.1f} A]  {means}  "
                  f"→ {'PASS' if verdict else 'FAIL'}")
    finally:
        if not simulate:
            ea.set_current_limit(0.0)
            ea.set_voltage(0.0)
            ea.disable()
    return records


# ── commands ────────────────────────────────────────────────────────────────

def _make_ea(args, voltage_limit, current_limit):
    if args.simulate:
        return make_supply(None)          # DummyEASupply
    return make_supply(args.ea_resource, voltage_limit=voltage_limit,
                       current_limit=current_limit, backend=args.ea_backend)


def _open_hw(args, voltage_limit, current_limit):
    """Open the EA supply (+ CAN bus unless simulating). Returns (ea, bus)."""
    ea = _make_ea(args, voltage_limit, current_limit).open()
    if not args.simulate:
        print(f"[EA] {ea.__class__.__name__} ready.")
        bus = _open_can()
        protocol = HwTestProtocol()
        _enable_report(bus, protocol)
        return ea, bus
    return ea, None


def cmd_voltage(args):
    args._part_number = resolve_part_number(args)
    set_points = _gen_points(args.v_min, args.v_max, args.v_step)
    protocol = HwTestProtocol()
    ea, bus = _open_hw(args, voltage_limit=args.v_max + 20.0,
                       current_limit=VOLTAGE_TEST_CURRENT_LIMIT_A)

    print("=" * 72)
    print(f"  HV VOLTAGE CHARACTERIZATION — placement {args.point} "
          f"(ANLG[{VOLTAGE_POINTS[args.point]}] {channel_name(VOLTAGE_POINTS[args.point])})")
    print(f"  Sweep     : {set_points} V   ({len(set_points)} steps)")
    print(f"  I-limit   : {VOLTAGE_TEST_CURRENT_LIMIT_A*1000:.0f} mA "
          f"(supply current ceiling during the voltage test)")
    print(f"  Tolerance : ±{args.tol_pct:g}%  (min ±{args.tol_abs:g} V)   "
          f"repeats={args.repeats}")
    print("=" * 72)
    print(f"  ⚠  Connect the supply VOLTAGE cables to the  {args.point}  "
          f"sense input (ANLG[{VOLTAGE_POINTS[args.point]}]).")
    _confirm(f"  Press ENTER when the cables are on {args.point} … ",
             args.simulate, getattr(args, "yes", False))

    try:
        recs = measure_voltage_point(
            args.point, ea, bus, protocol,
            set_points=set_points, tol_pct=args.tol_pct, tol_abs=args.tol_abs,
            repeats=args.repeats, settle_s=args.settle, read_gap_s=args.read_gap,
            simulate=args.simulate)
    finally:
        ea.close()
        if bus is not None:
            bus.close()

    data = _load_session(args.session)
    data["voltage"][args.point] = recs
    data["meta"].update(_meta(args, set_points))
    _save_session(args.session, data)

    n_pass = sum(1 for r in recs if r["verdict"])
    done = [p for p in VOLTAGE_POINT_ORDER if p in data["voltage"]]
    todo = [p for p in VOLTAGE_POINT_ORDER if p not in data["voltage"]]
    print("-" * 72)
    print(f"  {args.point}: {n_pass}/{len(recs)} steps PASS  →  session '{args.session}'")
    print(f"  Voltage placements captured : {', '.join(done) or '—'}")
    if todo:
        print(f"  Remaining placements        : {', '.join(todo)}  "
              f"(move the terminals, then run the next --point)")
    print("=" * 72)
    return 0


def cmd_current(args):
    args._part_number = resolve_part_number(args)
    set_mags = _gen_points(0.0, args.i_max, args.i_step)
    protocol = HwTestProtocol()
    ea, bus = _open_hw(args, voltage_limit=max(args.compliance_v + 5.0, 10.0),
                       current_limit=args.i_max + 2.0)

    pass_label = "PASS 1 (first sense)" if args.orientation == "pos" \
        else "PASS 2 (flipped sense)"
    print("=" * 72)
    print(f"  PHASE-CURRENT CHARACTERIZATION — {pass_label}")
    print(f"  Magnitudes : {set_mags} A   ({len(set_mags)} steps, CC mode, "
          f"compliance {args.compliance_v:g} V)")
    print(f"  Reading    : ANLG[1/2/3]  I_Ph_U / I_Ph_V / I_Ph_W (all at once; "
          f"sign recorded as measured — no need to know the wiring sense)")
    print(f"  Tolerance  : ±{args.tol_pct:g}%  (min ±{args.tol_abs:g} A)   "
          f"repeats={args.repeats}")
    print("=" * 72)
    if args.orientation == "neg":
        print("  ⚠  CHANGE THE SENSE: flip the supply current cables (reverse "
              "polarity) vs. the first pass, then this sweep will run.")
    else:
        print("  ⚠  Connect the supply CURRENT cables through the phase shunts "
              "(CC mode). Either sense is fine — the measured sign is recorded.")
    _confirm(f"  Press ENTER when wired for {pass_label} … ",
             args.simulate, getattr(args, "yes", False))

    try:
        recs = measure_current_orientation(
            args.orientation, ea, bus, protocol,
            set_mags=set_mags, compliance_v=args.compliance_v,
            tol_pct=args.tol_pct, tol_abs=args.tol_abs, repeats=args.repeats,
            settle_s=args.settle, read_gap_s=args.read_gap,
            simulate=args.simulate)
    finally:
        ea.close()
        if bus is not None:
            bus.close()

    data = _load_session(args.session)
    data["current"][args.orientation] = recs
    data["meta"].update(_meta(args, None))
    data["meta"]["current_sweep"] = (
        f"±{args.i_max:g} A step {args.i_step:g} A, CC compliance "
        f"{args.compliance_v:g} V")
    _save_session(args.session, data)

    n_pass = sum(1 for r in recs if r["verdict"])
    done = [o for o in ("pos", "neg") if o in data["current"]]
    todo = [o for o in ("pos", "neg") if o not in data["current"]]
    print("-" * 72)
    print(f"  {args.orientation}: {n_pass}/{len(recs)} steps PASS  →  session '{args.session}'")
    print(f"  Current orientations captured : {', '.join(done) or '—'}")
    if todo:
        print(f"  Remaining orientations        : {', '.join(todo)}  "
              f"(flip the terminals, then run --orientation {todo[0]})")
    print("=" * 72)
    return 0


def cmd_status(args):
    data = _load_session(args.session)
    print(f"Session '{args.session}':")
    print("  Voltage placements:")
    for p in VOLTAGE_POINT_ORDER:
        if p in data["voltage"]:
            recs = data["voltage"][p]
            npass = sum(1 for r in recs if r["verdict"])
            print(f"    {p:8s}  {npass}/{len(recs)} PASS")
        else:
            print(f"    {p:8s}  — not captured")
    print("  Current orientations:")
    for o in ("pos", "neg"):
        if o in data["current"]:
            recs = data["current"][o]
            npass = sum(1 for r in recs if r["verdict"])
            print(f"    {o:8s}  {npass}/{len(recs)} PASS")
        else:
            print(f"    {o:8s}  — not captured")
    return 0


def collect_records(data):
    """Flatten a session into (voltage_records, current_records) ordered for
    the report (placements in DC_LINK/UV/WV order; currents neg→pos so the
    table reads -20…0…+20 A)."""
    v_recs = []
    for p in VOLTAGE_POINT_ORDER:
        v_recs.extend(data["voltage"].get(p, []))
    i_recs = []
    for r in reversed(data["current"].get("neg", [])):
        i_recs.append(r)
    for r in data["current"].get("pos", []):
        i_recs.append(r)
    return v_recs, i_recs


def cmd_report(args):
    from report_store import update_report
    data = _load_session(args.session)
    v_recs, i_recs = collect_records(data)
    if not v_recs and not i_recs:
        print("Nothing captured — run a voltage/current sweep first.")
        return 1

    part = (getattr(args, "part_number", None)
            or data["meta"].get("part_number")
            or data["meta"].get("unit_sn", "PCB"))

    meta = dict(data["meta"])
    meta.setdefault("sequence", "Phase 3 — HV voltage + phase current")
    meta.setdefault("test_date",
                    datetime.datetime.now().isoformat(timespec="seconds"))
    meta.setdefault("can_interface", "pcan")
    meta.setdefault("can_channel", "PCAN_USBBUS1")
    meta.setdefault("can_bitrate", 250_000)
    meta["phases_run"] = (
        f"P3:HV-Voltage({len(v_recs)}) + P3:Current({len(i_recs)})")

    out, version = update_report(
        part, _RESULTS_DIR, session_meta=meta,
        hv_v_records=v_recs, hv_i_records=i_recs)

    nvp = sum(1 for r in v_recs if r["verdict"])
    nip = sum(1 for r in i_recs if r["verdict"])
    print("=" * 72)
    print(f"  HV CHARACTERIZATION REPORT — {part}  (V{version})")
    print(f"  Voltage : {nvp}/{len(v_recs)} steps PASS")
    print(f"  Current : {nip}/{len(i_recs)} steps PASS")
    print(f"  Report  : {out}")
    print("=" * 72)
    return 0


# ── shared helpers ───────────────────────────────────────────────────────────

def resolve_part_number(args):
    """Return the PCB part number. Use --part-number if given; else (at the
    bench) prompt for it; else fall back to the unit S/N."""
    pn = getattr(args, "part_number", None)
    if pn:
        return pn.strip()
    if getattr(args, "simulate", False):
        return "SIMPCB-00"
    try:
        pn = input("  PCB part number (e.g. INVGEN3B1-01): ").strip()
    except EOFError:
        pn = ""
    return pn or getattr(args, "unit_sn", "PCB")


def _confirm(msg, simulate, yes=False):
    """Block until the operator confirms a physical connection. Mandatory at
    the bench (real stdin). Bypassed when:
      • --simulate (no hardware), or
      • --yes      (caller already confirmed the connection in chat), or
      • there is no stdin (piped/chat-driven call → EOFError)."""
    if simulate or yes:
        if yes:
            print(f"{msg}[--yes: connection assumed confirmed]")
        return
    try:
        input(msg)
    except EOFError:
        print("  (no stdin — proceeding; assuming the connection is confirmed)")


def _gen_points(mn, mx, step):
    """Inclusive list mn..mx in `step` increments (rounded to 6 dp)."""
    if step <= 0 or mx < mn:
        return [mn]
    pts, v = [], mn
    while v <= mx + 1e-9:
        pts.append(round(v, 6))
        v += step
    if pts[-1] < mx - 1e-9:
        pts.append(mx)
    return pts


def _meta(args, set_points):
    m = dict(part_number=getattr(args, "_part_number", None) or
             getattr(args, "part_number", None) or args.unit_sn,
             unit_sn=args.unit_sn, operator=args.operator,
             ea_resource=("(simulated)" if args.simulate else args.ea_resource),
             date=datetime.datetime.now().isoformat(timespec="seconds"))
    if set_points is not None:
        m["voltage_sweep"] = (f"{args.v_min:g}-{args.v_step:g}-{args.v_max:g} V "
                              f"({len(set_points)} steps)")
    return m


# ── argparse ─────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--session", default="hv", help="Session name (default 'hv')")
        sp.add_argument("--part-number", "--pn", default=None,
                        help="PCB part number, e.g. INVGEN3B1-01 (prompted if omitted)")
        sp.add_argument("--unit-sn", default="PCB-B1")
        sp.add_argument("--operator", default="Carlos Miguel Espinar")
        sp.add_argument("--ea-resource", default=None,
                        help="EA supply VISA resource (e.g. ASRL6::INSTR, "
                             "USB0::0x2184::..., TCPIP::ip::INSTR)")
        sp.add_argument("--ea-backend", default="",
                        help="VISA backend for the EA ('' = system VISA, "
                             "'@py' = pyvisa-py)")
        sp.add_argument("--repeats", type=int, default=5,
                        help="Readings per step for dispersion (default 5)")
        sp.add_argument("--settle", type=float, default=1.5,
                        help="Seconds to settle after each setpoint (default 1.5)")
        sp.add_argument("--read-gap", type=float, default=0.1,
                        help="Seconds between repeat reads (default 0.1)")
        sp.add_argument("--yes", "-y", action="store_true",
                        help="Skip the connection-confirmation prompt "
                             "(connection already confirmed)")
        sp.add_argument("--simulate", action="store_true",
                        help="No hardware: canned EA + canned CAN readings")

    # voltage
    v = sub.add_parser("voltage", help="Sweep one HV terminal placement")
    add_common(v)
    v.add_argument("--point", required=True, choices=VOLTAGE_POINT_ORDER)
    v.add_argument("--v-min", type=float, default=0.0)
    v.add_argument("--v-step", type=float, default=50.0)
    v.add_argument("--v-max", type=float, default=400.0)
    v.add_argument("--tol-pct", type=float, default=5.0,
                   help="Tolerance as %% of setpoint (default 5)")
    v.add_argument("--tol-abs", type=float, default=5.0,
                   help="Absolute tolerance floor in V (default 5)")
    v.set_defaults(func=cmd_voltage)

    # current
    c = sub.add_parser("current", help="Sweep one current orientation")
    add_common(c)
    c.add_argument("--orientation", required=True, choices=["pos", "neg"])
    c.add_argument("--i-max", type=float, default=20.0)
    c.add_argument("--i-step", type=float, default=5.0)
    c.add_argument("--compliance-v", type=float, default=5.0,
                   help="CC-mode voltage compliance ceiling in V (default 5)")
    c.add_argument("--tol-pct", type=float, default=5.0,
                   help="Tolerance as %% of setpoint (default 5)")
    c.add_argument("--tol-abs", type=float, default=1.0,
                   help="Absolute tolerance floor in A (default 1)")
    c.set_defaults(func=cmd_current)

    # report
    r = sub.add_parser("report", help="Write the unified ValidationReport")
    r.add_argument("--session", default="hv")
    r.add_argument("--part-number", "--pn", default=None,
                   help="Override PCB part number (else taken from the session)")
    r.set_defaults(func=cmd_report)

    # status
    s = sub.add_parser("status", help="Show captured placements/orientations")
    s.add_argument("--session", default="hv")
    s.set_defaults(func=cmd_status)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
