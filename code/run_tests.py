#!/usr/bin/env python3
"""
run_tests.py  –  Stage 1 HW PCBA automated test campaign entry point.

Usage
-----
  # Run the default sequence (from config.py) and generate an Excel report:
  python run_tests.py

  # Specify sequence, unit S/N and operator explicitly:
  python run_tests.py --sequence A0_A1 --unit-sn PCB-002 --operator "Jane Smith"

  # B-sample (B0/B1/B2 are equivalent aliases):
  python run_tests.py --sequence B2

  # Skip report generation (CSV only):
  python run_tests.py --no-report

  # Quiet mode (no live progress):
  python run_tests.py --quiet

Prerequisites
-------------
  pip install -r requirements.txt
  PEAK PCAN-USB driver must be installed and the board powered and
  flashed with the HW-test firmware image.
"""

import argparse
import os
import sys
import datetime

# Ensure stdout/stderr can print box-drawing Unicode characters on Windows
# consoles (default cp1252 codec otherwise crashes).
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

# ── Add the code/ directory to the module search path ─────────────────────
_CODE_DIR    = os.path.dirname(os.path.abspath(__file__))
_RESULTS_DIR = os.path.join(_CODE_DIR, "..", "results")
os.makedirs(_RESULTS_DIR, exist_ok=True)

from config import (
    TEST_SEQUENCE, UNIT_SN, OPERATOR, RESULTS_CSV,
    CAN_INTERFACE, CAN_CHANNEL, CAN_ID, HW_VERSION_OVERRIDE,
)
from hw_test_runner import execute_campaign


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Inverter Gen3 Stage 1 HW PCBA automated test runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--sequence", "-s",
        default=TEST_SEQUENCE,
        choices=["A0_A1", "A0", "A1", "B0", "B1", "B2"],
        help=f"Test sequence to run (default: {TEST_SEQUENCE}). "
             "B0/B1/B2 are aliases for the same B-sample list.",
    )
    p.add_argument(
        "--unit-sn", "-u",
        default=UNIT_SN,
        help=f"Board serial number for the report (default: {UNIT_SN})",
    )
    p.add_argument(
        "--operator", "-o",
        default=OPERATOR,
        help=f"Operator name for the report (default: {OPERATOR})",
    )
    p.add_argument(
        "--csv",
        default=os.path.join(_RESULTS_DIR, RESULTS_CSV),
        help="Output CSV path",
    )
    p.add_argument(
        "--no-report",
        action="store_true",
        help="Skip Excel report generation",
    )
    p.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress live test progress output",
    )
    p.add_argument(
        "--no-prompts",
        action="store_true",
        help=("Don't pause for manual-setup prompts on the loopback tests "
              "that need a DAC injection (0x25, 0x26, 0x2A, 0x2B)."),
    )
    p.add_argument(
        "--hw-version",
        type=int,
        default=HW_VERSION_OVERRIDE,
        help=(f"Board HW-version index (0–15) reported on ANLG[0]; "
              f"used to skip limit checks on unpopulated channels. "
              f"Default: {HW_VERSION_OVERRIDE} (B0). Pass any int to override."),
    )
    return p.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # ── Run test campaign ─────────────────────────────────────────────────
    try:
        session_meta, results = execute_campaign(
            sequence_name        = args.sequence,
            unit_sn              = args.unit_sn,
            operator             = args.operator,
            results_csv          = args.csv,
            verbose              = not args.quiet,
            hw_version           = args.hw_version,
            interactive_prompts  = not args.no_prompts,
        )
    except Exception as exc:
        print(f"\n[ERROR] Campaign aborted: {exc}", file=sys.stderr)
        raise

    # ── Summary ───────────────────────────────────────────────────────────
    n_pass    = sum(1 for r in results if r["result"] == "PASS")
    n_fail    = sum(1 for r in results if r["result"] == "FAIL")
    n_other   = len(results) - n_pass - n_fail
    overall   = "PASS" if (n_fail == 0 and n_other == 0) else "FAIL"

    print(f"\n{'='*70}")
    print(f"  CAMPAIGN RESULT : {overall}")
    print(f"  Tests run       : {len(results)}")
    print(f"  PASS            : {n_pass}")
    print(f"  FAIL            : {n_fail}")
    print(f"  TIMEOUT / ERROR : {n_other}")
    print(f"  CSV             : {args.csv}")
    print(f"{'='*70}\n")

    # ── Generate Excel report ──────────────────────────────────────────────
    if not args.no_report:
        try:
            from generate_report import generate_validation_report
        except ImportError as e:
            print(f"[WARN] openpyxl not available — skipping report: {e}")
        else:
            ts_str  = datetime.datetime.now().strftime("%Y%m%d_%H%M")
            sn_safe = args.unit_sn.replace("/", "-").replace(" ", "_")
            xlsx_name = f"ValidationReport_{sn_safe}_{ts_str}.xlsx"
            xlsx_path = os.path.join(_RESULTS_DIR, xlsx_name)

            xlsx_path = generate_validation_report(
                results      = results,
                session_meta = session_meta,
                output_path  = xlsx_path,
            )
            print(f"[REPORT] Written → {xlsx_path}")

    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
