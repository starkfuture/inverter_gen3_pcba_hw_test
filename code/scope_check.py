#!/usr/bin/env python3
"""
scope_check.py  –  Rohde & Schwarz scope connectivity / configuration self-test.

Use this BEFORE the full gate-scope verification to confirm the USB link,
the SCPI command set and the measurement read-back all work on your specific
scope — independent of the firmware / CAN / probe-move dance.

What it does
────────────
  1. Lists every VISA resource the PC can see (so you can spot the scope).
  2. Opens the R&S scope (auto-discovered, or --resource).
  3. Prints *IDN? (manufacturer / model / serial / firmware).
  4. Configures CH<n> for the +18/-3 V gate window (or your overrides).
  5. Takes ONE measurement set and prints the 7 parameters.
  6. With --watch, repeats the measurement every second so you can probe a
     live signal and watch the numbers update (Ctrl+C to stop).

Usage
─────
  python scope_check.py                       # auto-discover, one read
  python scope_check.py --watch               # continuous read (live probe)
  python scope_check.py --scope-ch 2 --probe-atten 10
  python scope_check.py --resource "USB0::0x0AAD::0x01D6::123456::INSTR"
  python scope_check.py --list-only           # just enumerate VISA resources
  python scope_check.py --simulate            # canned data, no hardware
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import time
import argparse

from scope_rs import RohdeScope

# Default scope setup for +18 V / -3 V gate drive, 10:1 probe.
DEFAULT_PROBE_ATT = 10.0
DEFAULT_V_DIV     = 4.0
DEFAULT_OFFSET    = 7.5
DEFAULT_TRIG_LVL  = 5.0
DEFAULT_T_DIV     = 20e-6   # 20 µs/div ≈ a few periods of a ~16 kHz PWM


def _fmt(key, value):
    if value != value:                      # NaN
        return "—  (no reading)"
    if key in ("rise_time", "fall_time"):
        return f"{value*1e9:8.1f} ns"
    if key == "frequency":
        return f"{value/1000:8.3f} kHz"
    if key == "duty":
        return f"{value:8.2f} %"
    return f"{value:8.3f} V"


def list_resources():
    try:
        import pyvisa
    except ImportError:
        print("  pyvisa not installed. Run: pip install pyvisa pyvisa-py pyusb")
        return []
    try:
        rm = pyvisa.ResourceManager("@py")
        res = list(rm.list_resources())
    except Exception as exc:
        print(f"  Could not enumerate VISA resources: {exc}")
        return []
    if not res:
        print("  (no VISA resources found — is the scope powered and on USB?)")
    else:
        for r in res:
            tag = "  <-- looks like R&S" if "0x0AAD" in r.lower() else ""
            print(f"    {r}{tag}")
    return res


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--resource", default=None,
                   help="Explicit VISA resource string, e.g. "
                        "'USB0::0x0AAD::0x01D6::123456::INSTR' or "
                        "'TCPIP::192.168.1.50::INSTR' (LAN).")
    p.add_argument("--backend", default="@ivi",
                   help="VISA backend: '@ivi' (installed R&S/NI VISA — required "
                        "for USB on this bench, default) or '@py' (pyvisa-py).")
    p.add_argument("--scope-ch", type=int, default=1)
    p.add_argument("--probe-atten", type=float, default=DEFAULT_PROBE_ATT)
    p.add_argument("--v-div", type=float, default=DEFAULT_V_DIV)
    p.add_argument("--offset", type=float, default=DEFAULT_OFFSET)
    p.add_argument("--trig-level", type=float, default=DEFAULT_TRIG_LVL)
    p.add_argument("--t-div", type=float, default=DEFAULT_T_DIV)
    p.add_argument("--watch", action="store_true",
                   help="Continuously re-measure every second (Ctrl+C to stop)")
    p.add_argument("--list-only", action="store_true",
                   help="Only enumerate VISA resources, then exit")
    p.add_argument("--simulate", action="store_true")
    args = p.parse_args()

    print("=" * 72)
    print("  R&S scope connectivity self-test")
    print("=" * 72)

    print("\n[1] VISA resources visible to this PC:")
    if not args.simulate:
        list_resources()
    else:
        print("    (simulate mode — skipping enumeration)")

    if args.list_only:
        return 0

    print("\n[2] Opening scope …")
    try:
        scope = RohdeScope(resource=args.resource, backend=args.backend,
                           simulate=args.simulate).open()
    except Exception as exc:
        print(f"    FAILED to open scope: {exc}")
        print("    • Confirm the scope is powered and on USB.")
        print("    • Try --resource with an explicit string from the list above.")
        print("    • Re-seat the USB cable; some scopes need 'USB device' mode "
              "(not 'USB host') in the I/O settings.")
        return 2

    print(f"    Connected. *IDN? → {scope.idn()}")

    print(f"\n[3] Full pre-configuration of CH{args.scope_ch}: "
          f"{args.v_div} V/div, offset {args.offset} V, "
          f"probe {args.probe_atten:g}:1, {args.t_div*1e6:g} µs/div, "
          f"trigger {args.trig_level} V, + 7 on-screen measurement slots")
    try:
        scope.full_setup(args.scope_ch, v_div=args.v_div, offset=args.offset,
                         probe_atten=args.probe_atten, t_div=args.t_div,
                         trig_level=args.trig_level)
    except Exception as exc:
        print(f"    Configuration error: {exc}")
        scope.close()
        return 3

    def _one_read():
        m = scope.measure(args.scope_ch)
        print(f"    frequency : {_fmt('frequency', m['frequency'])}")
        print(f"    duty      : {_fmt('duty',      m['duty'])}")
        print(f"    rise time : {_fmt('rise_time', m['rise_time'])}")
        print(f"    fall time : {_fmt('fall_time', m['fall_time'])}")
        print(f"    V-high    : {_fmt('v_high',    m['v_high'])}")
        print(f"    V-low     : {_fmt('v_low',     m['v_low'])}")
        print(f"    V-pp      : {_fmt('v_pp',       m['v_pp'])}")
        return m

    print(f"\n[4] Measuring CH{args.scope_ch} "
          f"{'(continuous — Ctrl+C to stop)' if args.watch else '(single read)'}:")
    try:
        if args.watch:
            while True:
                print("    " + "-" * 40)
                _one_read()
                time.sleep(1.0)
        else:
            _one_read()
    except KeyboardInterrupt:
        print("\n    stopped.")
    finally:
        scope.close()

    print("\n[5] Done. If the readings look right, the scope link is good and "
          "you can run verify_pcba.py --scope.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
