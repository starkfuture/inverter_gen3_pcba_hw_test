---
name: power-module-parallel-probe-flow
description: How Carlos wants the Phase-2 power-module gate validation driven (bottom-then-top, 3 parallel probes)
metadata:
  type: feedback
---

For a real Phase-2 power-module validation Carlos wants this operator flow,
not one switch at a time:

1. Prompt: "place the 3 probes on the BOTTOM gates" → measure UBOT/VBOT/WBOT on CH1/CH2/CH3.
2. Prompt: "move the 3 probes to the TOP gates" → measure UTOP/VTOP/WTOP on CH1/CH2/CH3.
3. One unified report over all 6.

**Why it's safe:** probing all 3 of one half in parallel (3 common-ground probes
at once) is electrically OK **only because the bench is de-energized** — no HV
DC-link, so the isolated gate domains sit at the same potential and tying the
probe grounds together shorts nothing. With the DC-link **energized this would
NOT be safe** (the tops float on their phase nodes); fall back to one probe at
a time then.

**How to apply:** drive it with `pm_step_session.py measure --switch <SW>
--scope-ch <N> --probe-atten 10` (one invocation per channel — the proven,
stable path). Do NOT use the per-setpoint slot-juggling in `pm_multi.py`: the
RTM3004 only has 8 measurement slots, so re-pointing 7 slots per channel each
setpoint is fragile. The bench probes are **10:1** (Carlos may call them "x1",
but the data is 10× — V-high reads ~18 V only with `--probe-atten 10`).

Related: [[pm-vpp-overshoot-criteria]], [[can-open-not-connected]].
