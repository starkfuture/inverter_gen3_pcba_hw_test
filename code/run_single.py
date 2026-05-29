#!/usr/bin/env python3
"""
run_single.py  –  run ONE HW_TEST over CAN and report the firmware verdict.

Used for operator-paced Phase-4 tests (encoder sin/cos loopback, etc.) where
each test is run individually after the operator confirms the hookup.

Usage:
  python run_single.py --test HW_TEST_ENC_SINCOS_SIN_LOOPBACK
  python run_single.py --test HW_TEST_ENC_SINCOS_COS_LOOPBACK --timeout-ms 1500
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
from hw_can_utils import send_frame
from hv_iv_session import _open_can, _enable_report


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--test", required=True, help="HW_TEST_* key to run")
    p.add_argument("--timeout-ms", type=int, default=1500)
    args = p.parse_args()

    proto = HwTestProtocol()
    if args.test not in proto.sfHwTestProtocolGetTestsDictionary():
        print(f"Unknown test key: {args.test}")
        return 2

    bus = _open_can()
    _enable_report(bus, proto)
    rec = run_single_test(bus, proto, args.test, "", 0, args.timeout_ms)
    stop = proto.sfHwTestProtocolProcessTxMessage(
        "SF_HW_TEST_PROTOCOL_RQST_SET_TEST", 0, "HW_TEST_NO_TEST")
    send_frame(bus, stop[1])
    time.sleep(0.1)
    bus.close()

    code = proto.sfHwTestProtocolGetTestsDictionary()[args.test][0]
    print("=" * 60)
    print(f"{args.test} (0x{code:02X})")
    print(f"  Firmware verdict : {rec['firmware_result']}")
    print(f"  Result           : {rec['result']}   flags: {rec['flags_str']}")
    print(f"  Message          : {rec['message']}")
    if rec["analog_values"]:
        print("  Reported channels:")
        for ch in sorted(rec["analog_values"]):
            print(f"    ANLG[{ch:>2}] {channel_name(ch):<18} = "
                  f"{rec['analog_values'][ch]:.4g}")
    print("=" * 60)
    return 0 if rec["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
