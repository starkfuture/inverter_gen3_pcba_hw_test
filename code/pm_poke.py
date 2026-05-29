#!/usr/bin/env python3
"""
pm_poke.py  –  live diagnostic: send SET_PWM_FREQ / SET_PWM_DUTY frames and
let you watch pwm_freq_forced_in_khz / pwm_duty_phase_*_forced_unitary in the
debugger watch window to confirm whether the firmware variables update.

It steps through a few distinct frequency and duty values, holding each for a
couple of seconds and printing the exact 8 bytes transmitted, so you can see
the watch-window values track (or not).

By default NO test is started — this isolates the command decode from the
test logic (nothing can reset the forced variables). Use --with-test to also
enter HW_TEST_ALL_POWER_MODULE first.

Usage
─────
  python pm_poke.py                       # poke freq+duty, no test running
  python pm_poke.py --with-test           # enter 0x1B first, then poke
  python pm_poke.py --hold 3              # hold each value 3 s
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import time
import argparse

from hw_protocol import HwTestProtocol
import run_gate_scope_check as gsc


def _send_show(bus, protocol, rqst, inst, val, label):
    n, payload = protocol.sfHwTestProtocolProcessTxMessage(rqst, inst, val)
    bts = bytes(int(x) & 0xFF for x in payload)
    print(f"  TX {label:28s} → {' '.join(f'{b:02X}' for b in bts)}")
    if n > 0:
        from hw_can_utils import send_frame
        send_frame(bus, payload)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--with-test", action="store_true",
                   help="Enter HW_TEST_ALL_POWER_MODULE (0x1B) before poking")
    p.add_argument("--hold", type=float, default=2.5,
                   help="Seconds to hold each value (default 2.5)")
    p.add_argument("--freqs", nargs="+", type=float, default=[20.0, 25.0, 30.0],
                   help="Frequencies to step through (kHz)")
    p.add_argument("--duties", nargs="+", type=float, default=[0.30, 0.50, 0.70],
                   help="Duties to step through (per-unit 0..1)")
    args = p.parse_args()

    protocol = HwTestProtocol()
    bus = gsc._open_can()
    print("=" * 72)
    print("  PWM-poke diagnostic — watch pwm_freq_forced_in_khz / "
          "pwm_duty_phase_u_forced_unitary")
    print("=" * 72)

    try:
        if args.with_test:
            flags = (protocol.SF_HW_TEST_PROTOCOL_TEST_SET_ENV_FLAGS_REPORT_ENABLE
                     | protocol.SF_HW_TEST_PROTOCOL_TEST_SET_ENV_FLAGS_CLEAR_REBOOT)
            _send_show(bus, protocol, "SF_HW_TEST_PROTOCOL_RQST_SET_TEST_ENV", 0, flags,
                       "SET_TEST_ENV")
            time.sleep(0.3)
            _send_show(bus, protocol, "SF_HW_TEST_PROTOCOL_RQST_SET_TEST", 0,
                       "HW_TEST_ALL_POWER_MODULE", "SET_TEST 0x1B")
            time.sleep(0.5)

        print("\n[Frequency] watch pwm_freq_forced_in_khz:")
        for f in args.freqs:
            _send_show(bus, protocol, "SF_HW_TEST_PROTOCOL_RQST_SET_PWM_FREQ", 0, f,
                       f"SET_PWM_FREQ {f:g} kHz")
            print(f"     → expect pwm_freq_forced_in_khz = {f:g}   (holding {args.hold:g}s)")
            time.sleep(args.hold)

        print("\n[Duty] watch pwm_duty_phase_u/v/w_forced_unitary (all phases, index 0):")
        for d in args.duties:
            _send_show(bus, protocol, "SF_HW_TEST_PROTOCOL_RQST_SET_PWM_DUTY", 0, d,
                       f"SET_PWM_DUTY {d:g}")
            print(f"     → expect pwm_duty_phase_*_forced_unitary = {d:g}   (holding {args.hold:g}s)")
            time.sleep(args.hold)

        print("\nDone. Did the watch-window variables track the TX values above?")
    finally:
        bus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
