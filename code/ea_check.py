#!/usr/bin/env python3
"""
ea_check.py  –  quick bench diagnostic for the EA laboratory supply.

Opens the supply, prints *IDN?, then exercises control so you can WATCH the
front panel react:
  • voltage : alternates between two setpoints (default 5 V / 10 V)
  • current : alternates the current limit between two setpoints
              (default 100 mA / 200 mA) at a fixed compliance voltage

Reads back MEAS:VOLT? / MEAS:CURR? each step. Output is forced to 0 and
disabled at the end (and on Ctrl+C).

Usage:
  python ea_check.py --ea-resource ASRL4::INSTR
  python ea_check.py --ea-resource ASRL4::INSTR --cycles 4 --dwell 2.0
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import time
import argparse

from ea_supply import EASupply


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ea-resource", default="ASRL4::INSTR")
    p.add_argument("--ea-backend", default="",
                   help="'' = system VISA (default), '@py' = pyvisa-py")
    p.add_argument("--v-lo", type=float, default=5.0)
    p.add_argument("--v-hi", type=float, default=10.0)
    p.add_argument("--i-lo", type=float, default=0.1)   # 100 mA
    p.add_argument("--i-hi", type=float, default=0.2)   # 200 mA
    p.add_argument("--compliance-v", type=float, default=10.0,
                   help="Voltage during the current-toggle phase")
    p.add_argument("--cycles", type=int, default=4)
    p.add_argument("--dwell", type=float, default=1.5)
    args = p.parse_args()

    ea = EASupply(args.ea_resource, voltage_limit=max(args.v_hi, args.compliance_v) + 2,
                  current_limit=args.i_hi, backend=args.ea_backend).open()
    try:
        print("\n── Voltage toggle "
              f"({args.v_lo:g} V ↔ {args.v_hi:g} V, I-limit {args.i_hi*1000:.0f} mA) ──")
        ea.set_current_limit(args.i_hi)
        ea.set_voltage(0.0)
        ea.enable()
        for i in range(args.cycles):
            v_set = args.v_hi if i % 2 else args.v_lo
            ea.set_voltage(v_set)
            time.sleep(args.dwell)
            print(f"  set {v_set:5.1f} V  →  meas {ea.measure_voltage():6.3f} V"
                  f"   {ea.measure_current()*1000:6.1f} mA")

        print(f"\n── Current toggle "
              f"({args.i_lo*1000:.0f} mA ↔ {args.i_hi*1000:.0f} mA, "
              f"compliance {args.compliance_v:g} V) ──")
        ea.set_voltage(args.compliance_v)
        for i in range(args.cycles):
            i_set = args.i_hi if i % 2 else args.i_lo
            ea.set_current_limit(i_set)
            time.sleep(args.dwell)
            print(f"  lim {i_set*1000:5.0f} mA  →  meas {ea.measure_current()*1000:6.1f} mA"
                  f"   {ea.measure_voltage():6.3f} V")
    finally:
        ea.set_voltage(0.0)
        ea.set_current_limit(0.0)
        ea.disable()
        ea.close()
        print("\n  Output set to 0 and disabled.")


if __name__ == "__main__":
    sys.exit(main())
