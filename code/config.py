"""
config.py  –  Centralised configuration for Inverter Gen3 Stage 1 HW PCBA
              automated tests.

Run against the HW-test firmware image (NOT the production firmware).
The HW-test firmware communicates exclusively on CAN ID 0x100 using the
sf_hw_test_protocol proprietary frame format.

Edit this file to match your bench setup before running any test.
"""

# ── CAN interface ─────────────────────────────────────────────────────────
# pcan_interface.py uses PCANBasic.dll directly when available (matching
# the original STARK_FUTURE_InvGen3_hw_test.py), falling back to python-can.
CAN_INTERFACE  = "pcan"          # used by python-can fallback path
CAN_CHANNEL    = "PCAN_USBBUS1"  # PEAK PCAN USB first channel
CAN_BITRATE    = 250_000         # 250 kBit/s (PCAN_BAUD_250K)

# ── Protocol CAN ID ────────────────────────────────────────────────────────
CAN_ID         = 0x100           # sf_hw_test_protocol: all frames on this ID

# ── Test sequence ──────────────────────────────────────────────────────────
# "A0_A1"        → minimum test list for A0/A1-sample boards (17 tests)
# "B0"/"B1"/"B2" → minimum test list for B-sample boards     (19 tests)
#                  Same list for B0/B1/B2; ABI removed, pump/MCU/ext-temp added.
TEST_SEQUENCE  = "B2"

# ── Unit identification ────────────────────────────────────────────────────
UNIT_SN        = "PCB-001"                # Board serial number
OPERATOR       = "Carlos Miguel Espinar"  # Test operator name

# ── Timing ────────────────────────────────────────────────────────────────
BOOT_WAIT_S              = 1.0   # Seconds to wait after opening the CAN bus
                                  # before sending the first command
ENV_SETUP_DELAY_S        = 0.3   # Wait after SET_TEST_ENV before first test
INTER_TEST_DELAY_S       = 0.2   # Wait between consecutive tests
SEQ_QUANTUM_MS           = 20    # Sequence thread quantum (ms) — matches
                                  # APP_HW_TEST_SEQ_QUANTUM_TIME_IN_MS = 20
CAN_RECV_TIMEOUT_S       = 0.02  # Per-poll receive timeout (s) during countdown

# Delay between SET_TEST and the stimulus frame (CAN_ECHO is the only test
# that uses a stimulus, and the firmware only processes the ECHO request when
# test_type has already been switched. The firmware's testing_HW() loop runs
# on a 20 ms quantum, so we need at least one full quantum of margin to be
# safe across the race window. 50 ms = 2.5 × quantum is comfortable.
STIMULUS_DELAY_MS        = 50

# ── Early-exit (campaign time optimisation) ──────────────────────────────
# When True, the runner stops counting down as soon as the firmware has
# delivered PASS_REQUIRED_OK_FRAMES consecutive OK frames (V+/S+) on the
# test under execution, plus a short grace window. This typically cuts
# campaign duration by ~50 % without losing data.
# Monitoring-only tests (no V/S bits set) still wait the full timeout.
EARLY_EXIT_ON_PASS       = True
EARLY_EXIT_MIN_MS        = 100   # Don't even consider early-exit before this
                                  #   elapsed time (firmware needs time to start).
EARLY_EXIT_GRACE_MS      = 200   # After PASS observed, keep collecting frames
                                  #   for this many ms then exit.

# ── Interactive prompts (manual fixture setup) ───────────────────────────
# Some tests in the differential-loopback family need the operator to wire
# the MCU's DAC outputs into specific isolated-input pins before the test
# starts (encoder sin/cos analog front-end, unipolar/bipolar voltage
# conditioning loopbacks). When True, the runner pauses just before those
# tests and prints the required hookup, waiting for the operator to press
# Enter to confirm. Override at the CLI with --no-prompts.
INTERACTIVE_PROMPTS      = True


# ── Pass criterion ───────────────────────────────────────────────────────
# A test PASSes only if the LAST PASS_REQUIRED_OK_FRAMES status frames all
# carry V+ or S+. Cyclic tests like the sin/cos loopback emit one status
# frame per sub-test (positive, negative, common-mode → 3 frames per cycle)
# and the firmware drops back to V-/S- between sub-tests, so we need to
# inspect the full cycle to declare PASS. The default of 3 covers the
# differential-loopback family without breaking single-shot tests (which
# emit the same V+ frame repeatedly during the timeout window).
PASS_REQUIRED_OK_FRAMES  = 3

# ── Hardware version ──────────────────────────────────────────────────────
# Index 0–15 reported on ANLG[0] by the firmware. See HW_VERSION_NAMES in
# hw_test_criteria.py for the StarkFuture board-sample mapping.
#   3     → B1 (current bench sample; only EXT_TEMP1/EXT_TEMP2 populated)
#   None  → auto-detect from ANLG[0] during the campaign
HW_VERSION_OVERRIDE = 3

# ── Results output ─────────────────────────────────────────────────────────
RESULTS_CSV    = "test_results.csv"   # Written next to run_tests.py
