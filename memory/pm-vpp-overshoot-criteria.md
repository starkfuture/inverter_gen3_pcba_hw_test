---
name: pm-vpp-overshoot-criteria
description: Why the power-module v_pp limit was raised to 28 V and v_pp_avg (AMPLitude) was added
metadata:
  type: project
---

The scope `v_pp` measurement is the R&S **PEAK** (max−min), so it captures the
transient edge overshoot/ringing of the gate. On B1 the bottoms read a clean
+18.4 / −3.2 V (swing ~21.6 V) but the PEAK hit ~25.1–25.3 V, tripping the old
`v_pp` ceiling of 25.0 V and FAILing every otherwise-good setpoint.

Fix (decided by Carlos, 2026-05-29):
- Raised `v_pp` max 25 → **28 V** in `code/run_gate_scope_check.py` PARAM_LIMITS
  (the PEAK must allow headroom over the nominal V-high(20)−V-low(−5)=25 swing).
- Added `v_pp_avg` = R&S **AMPLitude** (HIGH−LOW) as the 8th scope measurement
  slot (`code/scope_rs.py` MEAS_TYPES), limit **18–25 V** — the clean
  overshoot-free swing. New "V-pp avg" column in both report builders
  (`run_power_module_sweep.write_report`, `generate_report._build_power_module_sheet`).

The RTM3004 has exactly 8 measurement slots; we now use all 8.

Related: [[power-module-parallel-probe-flow]].
