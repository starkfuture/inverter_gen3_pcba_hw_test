---
name: can-open-not-connected
description: PCAN channel opens even with no board attached — check_can_link() now warns
metadata:
  type: project
---

`python-can`'s PCAN backend (and PCANBasic) opens `PCAN_USBBUS1` successfully
even when the board is not connected / unpowered / the link dropped — a
successful `open()` does NOT mean the board is talking. This caused a whole
bench session of all-NaN scope readings (the gate was never driven) that looked
like a probe/isolation problem but was just the CAN cable down.

Fix: `check_can_link(bus, protocol)` in `code/hw_can_utils.py` actively probes —
enables reporting, runs HW_TEST_SUPPLY_VOLTAGES (no actuation), listens for any
0x100 frame, returns to NO_TEST. Prints "[CAN] Board link OK" or a loud warning.
Wired into `run_gate_scope_check._open_can()` (covers all power-module tools)
and `hw_test_runner.execute_campaign()` (covers verify_pcba / run_tests).

Related: [[power-module-parallel-probe-flow]].
