#!/usr/bin/env python3
"""
pump_check.py  –  run HW_TEST_PUMP_AUTO (0x2F) and CONTINUOUSLY sample the
reported pump-HS currents over CAN while the firmware cycles the pump switch
ON/OFF (~0.5–1 Hz). The current only flows during the ON phase, so we capture
the per-channel PEAK (and a binned timeline) instead of the final value.

The pump coil is emulated by a resistor network; pass each leg with --r (they
are placed in parallel). Default: 100 || 4700 || 4700 ohm.

Usage:
  python pump_check.py                     # sample 12 s
  python pump_check.py --sample-s 16 --r 100 4700 4700
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import time
import argparse

from hw_protocol import HwTestProtocol
from hw_test_runner import run_single_test
from hw_test_criteria import channel_name
from hw_can_utils import send_frame, recv_frame
from hv_iv_session import _open_can, _enable_report

CUR_CHANS = [31, 33]            # PUMP_HS1_CURRENT / PUMP_HS2_CURRENT
WATCH = [14, 31, 32, 33, 34, 39]   # supply, currents, temps, tach
ON_THRESHOLD_A = 0.02           # |current| above this = switch ON sample


def _tx(bus, proto, rqst, value):
    res = proto.sfHwTestProtocolProcessTxMessage(rqst, 0, value)
    if res and res[0] > 0:
        send_frame(bus, res[1])


def sample_pump(bus, proto, sample_s):
    """Run PUMP_AUTO and collect a (t, value) series per watched channel."""
    flags = (proto.SF_HW_TEST_PROTOCOL_TEST_SET_ENV_FLAGS_REPORT_ENABLE
             | proto.SF_HW_TEST_PROTOCOL_TEST_SET_ENV_FLAGS_CLEAR_REBOOT)
    _tx(bus, proto, "SF_HW_TEST_PROTOCOL_RQST_SET_TEST_ENV", flags)
    time.sleep(0.2)
    _tx(bus, proto, "SF_HW_TEST_PROTOCOL_RQST_SET_TEST", "HW_TEST_PUMP_AUTO")

    series = {ch: [] for ch in WATCH}
    t0 = time.monotonic()
    TYPE_K = proto.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY
    ANALOG = proto.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_ANALOG
    ID_K   = proto.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_ID_KEY
    VAL_K  = proto.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_VALUE_KEY
    while time.monotonic() - t0 < sample_s:
        fr = recv_frame(bus, timeout_s=0.02)
        if not fr:
            continue
        _id, data = fr
        action, obj = proto.sfHwTestProtocolProcessRxMessage(len(data), list(data))
        if action != proto.SF_HW_TEST_PROTOCOL_ACTION_UPDATE_OBJECT:
            continue
        t = time.monotonic() - t0
        for _k, v in obj.items():
            if v.get(TYPE_K) == ANALOG:
                ch = v[ID_K]
                if ch in series:
                    series[ch].append((t, float(v[VAL_K])))

    _tx(bus, proto, "SF_HW_TEST_PROTOCOL_RQST_SET_TEST", "HW_TEST_NO_TEST")
    time.sleep(0.1)
    return series


def _stats(vals):
    if not vals:
        return None
    return dict(n=len(vals), mn=min(vals), mx=max(vals),
                mean=sum(vals) / len(vals))


def _timeline(samples, bin_s=0.5, dur=None):
    """Max-per-bin string to visualise the ON/OFF cycling."""
    if not samples:
        return "(no samples)"
    dur = dur or samples[-1][0]
    nbins = max(1, int(dur / bin_s) + 1)
    bins = [0.0] * nbins
    for t, v in samples:
        i = min(nbins - 1, int(t / bin_s))
        bins[i] = max(bins[i], abs(v))
    return " ".join(f"{b:4.2f}" for b in bins)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--r", nargs="+", type=float, default=[100.0, 4700.0, 4700.0],
                   help="Load resistor legs in ohm, in parallel (default 100 4700 4700)")
    p.add_argument("--sample-s", type=float, default=12.0,
                   help="Seconds to sample while the pump switch cycles (default 12)")
    args = p.parse_args()

    proto = HwTestProtocol()
    bus = _open_can()
    _enable_report(bus, proto)

    # Supply voltage (28 V rail, ANLG[14]) from a quick ADC scan first.
    adc = run_single_test(bus, proto, "HW_TEST_ALL_ADC_MEASUREMENTS", "", 0, 700)
    vsup_idle = adc["analog_values"].get(14)

    print(f"Sampling PUMP_AUTO for {args.sample_s:g} s "
          f"(watching the switch cycle) …")
    series = sample_pump(bus, proto, args.sample_s)
    bus.close()

    r_parallel = 1.0 / sum(1.0 / r for r in args.r if r > 0)
    legs = " || ".join(f"{r:g}" for r in args.r)

    print("=" * 64)
    print("PUMP_AUTO continuous sampling")
    print(f"  Load R = {legs} = {r_parallel:.2f} ohm")
    vref = vsup_idle
    sup = series.get(14) or []
    if sup:
        vmax = max(v for _, v in sup); vmin = min(v for _, v in sup)
        print(f"  Supply (ANLG[14]) idle={vsup_idle:.2f} V  "
              f"during run min={vmin:.2f} max={vmax:.2f} V")
        vref = vmax
    elif vsup_idle is not None:
        print(f"  Supply (ANLG[14]) = {vsup_idle:.2f} V")
    if vref is not None:
        print(f"  Expected coil current (V/R) = {vref / r_parallel:.3f} A")
    print("-" * 64)

    for ch in CUR_CHANS:
        vals = [v for _, v in series[ch]]
        st = _stats(vals)
        if not st:
            print(f"  ANLG[{ch}] {channel_name(ch):<18}: no samples")
            continue
        n_on = sum(1 for v in vals if abs(v) > ON_THRESHOLD_A)
        print(f"  ANLG[{ch}] {channel_name(ch):<18}: "
              f"PEAK={st['mx']:.3f} A  min={st['mn']:.3f}  "
              f"mean={st['mean']:.3f}  n={st['n']}  on-samples={n_on}")
        print(f"      timeline (max |I| per 0.5 s): {_timeline(series[ch])}")

    for ch in (32, 34, 39):
        vals = [v for _, v in series[ch]]
        if vals:
            print(f"  ANLG[{ch}] {channel_name(ch):<18}: "
                  f"last={vals[-1]:.2f}  (n={len(vals)})")
    print("=" * 64)


if __name__ == "__main__":
    main()
