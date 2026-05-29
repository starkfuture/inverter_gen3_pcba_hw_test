"""
build_unified_report.py  –  Produce ONE unified ValidationReport that contains
both Phase 1 (self auto-verification, run fresh over CAN now) and Phase 2
(power-module sweep, loaded from an existing pm_step_session pickle).

This is the glue for the documented hybrid flow where Phase 2 was driven
switch-by-switch with pm_step_session.py (because the Bash harness can't feed
ENTER to the in-process probe-move prompt), so the sweep data never made it
into a unified workbook. We re-run Phase 1 (fast, unattended) and merge.

Usage:
    python build_unified_report.py --unit-sn PCB-B1 --sequence B1 \
        --pm-session B1_campaign
"""
import argparse, datetime, os, pickle

from hw_test_runner import execute_campaign
from generate_report import generate_validation_report
import run_power_module_sweep as pm
from config import HW_VERSION_OVERRIDE, OPERATOR

SWITCHES = ["UTOP", "UBOT", "VTOP", "VBOT", "WTOP", "WBOT"]
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")


def load_pm_records(session_name):
    path = os.path.join(RESULTS_DIR, f".pm_session_{session_name}.pkl")
    with open(path, "rb") as f:
        data = pickle.load(f)
    records = []
    for sw in SWITCHES:
        for rec in data["switches"].get(sw, []):
            rec.setdefault("switch", sw)
            pm.recompute_verdict(rec)        # switch-aware (bottom = complement)
            records.append(rec)
    return data.get("meta", {}), records


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--unit-sn", default="PCB-B1")
    p.add_argument("--sequence", default="B1")
    p.add_argument("--operator", default=OPERATOR)
    p.add_argument("--hw-version", type=int, default=HW_VERSION_OVERRIDE)
    p.add_argument("--pm-session", default="B1_campaign")
    args = p.parse_args()

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    sn_safe = args.unit_sn.replace("/", "-").replace(" ", "_")
    csv_path = os.path.join(RESULTS_DIR, f"test_results_{sn_safe}_{ts}.csv")
    xlsx_path = os.path.join(RESULTS_DIR, f"ValidationReport_{sn_safe}_{ts}.xlsx")

    # ── Phase 1: fresh self auto-verification (unattended) ───────────────
    print("=" * 72)
    print("  PHASE 1 — Self auto-verification (fresh run over CAN)")
    print("=" * 72)
    session_meta, results = execute_campaign(
        sequence_name=f"{args.sequence}_SELF",
        unit_sn=args.unit_sn,
        operator=args.operator,
        results_csv=csv_path,
        verbose=True,
        hw_version=args.hw_version,
        interactive_prompts=False,
    )
    for r in results:
        r["phase"] = 1

    # ── Phase 2: load existing sweep records ─────────────────────────────
    pm_meta, pm_records = load_pm_records(args.pm_session)
    npass = sum(1 for r in pm_records if r.get("verdict"))
    print(f"\n[Phase 2] Loaded {len(pm_records)} setpoints from session "
          f"'{args.pm_session}' ({npass}/{len(pm_records)} PASS)")

    session_meta["power_module_sweep"] = pm_meta.get(
        "power_module_sweep",
        "freq 10-10-30 kHz, duty 25-25-75 %, dead-band 1000 ns")
    session_meta["phases_run"] = (
        f"P1:Self({len(results)}) + P2:PowerModule({len(pm_records)})")

    # ── Unified report ───────────────────────────────────────────────────
    out = generate_validation_report(
        results=results,
        session_meta=session_meta,
        output_path=xlsx_path,
        pm_records=pm_records,
    )
    print("\n" + "=" * 72)
    print(f"  UNIFIED REPORT (Phase 1 + Phase 2) → {out}")
    print("=" * 72)


if __name__ == "__main__":
    main()
