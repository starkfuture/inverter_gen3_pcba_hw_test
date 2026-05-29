"""
report_store.py  –  per-PCB accumulation of the Validation Report.

Each inverter PCBA has a part number (e.g. "INVGEN3B1-01"). All reports for one
board live in their own folder:

    results/<part-number>/
        ValidationReport_<part>_V1.xlsx
        .campaign_V1.pkl          (raw phase data, so re-runs can regenerate)

Accumulation rules (what the bench asked for):
  • Running a phase MERGES its data into the current version's workbook and
    regenerates it — so doing Phase 1 first, then Phase 2/3 later, keeps adding
    to the SAME file (append).
  • Once a version already holds all three campaign blocks (firmware tests +
    power-module sweep + HV characterization), the next write starts a NEW
    version (V2, V3, …) instead of overwriting.

The pickle stores the exact inputs to generate_validation_report() so a later
phase can regenerate the full, consistent workbook (Summary counts included).
"""
import os
import pickle

from generate_report import generate_validation_report


def sanitize(name: str) -> str:
    """Filesystem-safe version of a part number / SN."""
    out = (name or "UNKNOWN").strip()
    for ch in '/\\: *?"<>|':
        out = out.replace(ch, "-")
    return out or "UNKNOWN"


def pcb_folder(part_number: str, results_dir: str) -> str:
    d = os.path.join(results_dir, sanitize(part_number))
    os.makedirs(d, exist_ok=True)
    return d


def _campaign_pkl(folder: str, version: int) -> str:
    return os.path.join(folder, f".campaign_V{version}.pkl")


def _report_xlsx(folder: str, part_number: str, version: int) -> str:
    return os.path.join(folder, f"ValidationReport_{sanitize(part_number)}_V{version}.xlsx")


def _empty_campaign() -> dict:
    return {"meta": {}, "results": [], "pm_records": None,
            "scope_records": None, "hv_v_records": None, "hv_i_records": None}


def _has_all_three(data: dict) -> bool:
    """True once the version holds firmware tests + power-module sweep + HV."""
    has_fw = bool(data.get("results"))
    has_pm = bool(data.get("pm_records"))
    has_hv = bool(data.get("hv_v_records") or data.get("hv_i_records"))
    return has_fw and has_pm and has_hv


def _existing_versions(folder: str):
    vs = []
    for fn in os.listdir(folder):
        if fn.startswith(".campaign_V") and fn.endswith(".pkl"):
            try:
                vs.append(int(fn[len(".campaign_V"):-len(".pkl")]))
            except ValueError:
                pass
    return sorted(vs)


def _load(path):
    with open(path, "rb") as f:
        return pickle.load(f)


def _save(path, data):
    with open(path, "wb") as f:
        pickle.dump(data, f)


def update_report(part_number: str, results_dir: str, *, session_meta: dict,
                  results=None, pm_records=None, scope_records=None,
                  hv_v_records=None, hv_i_records=None):
    """Merge the provided phase data into the current report version for this
    PCB and regenerate the workbook. Returns (output_path, version).

    `results` are merged BY PHASE: any phase number present in the new list
    replaces that phase's rows in the accumulated set (re-running Phase 1
    overwrites the old Phase 1 rows, etc.).
    """
    folder = pcb_folder(part_number, results_dir)
    versions = _existing_versions(folder)

    if not versions:
        version, data = 1, _empty_campaign()
    else:
        latest = versions[-1]
        data = _load(_campaign_pkl(folder, latest))
        if _has_all_three(data):
            version, data = latest + 1, _empty_campaign()   # start a new version
        else:
            version = latest                                 # append to current

    # ── merge the new phase data ───────────────────────────────────────────
    if results is not None:
        new_phases = {r.get("phase") for r in results}
        kept = [r for r in data["results"] if r.get("phase") not in new_phases]
        data["results"] = kept + list(results)
    if pm_records is not None:
        data["pm_records"] = pm_records
    if scope_records is not None:
        data["scope_records"] = scope_records
    if hv_v_records is not None:
        data["hv_v_records"] = hv_v_records
    if hv_i_records is not None:
        data["hv_i_records"] = hv_i_records

    data["meta"].update(session_meta or {})
    data["meta"]["part_number"] = part_number
    data["meta"]["report_version"] = version

    _save(_campaign_pkl(folder, version), data)

    out = _report_xlsx(folder, part_number, version)
    generate_validation_report(
        results=data["results"], session_meta=data["meta"], output_path=out,
        scope_records=data["scope_records"], pm_records=data["pm_records"],
        hv_v_records=data["hv_v_records"], hv_i_records=data["hv_i_records"])
    return os.path.abspath(out), version
