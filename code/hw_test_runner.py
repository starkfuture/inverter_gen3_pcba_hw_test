"""
hw_test_runner.py  –  Stage 1 HW PCBA automated test campaign engine.

Execution model
───────────────
Mirrors the state machine in _ThreadSequenceExecute() from the original
STARK_FUTURE_InvGen3_hw_test.py.  The original used three concurrent threads
(listening, sequence, macro).  Here the sequence is run synchronously (no
interactive UI needed), but the state transitions and timing are identical:

    State 0 — Send RQST_SET_TEST_ENV (REPORT_ENABLE flag).
              Sent once at the start of the full campaign.

    State 1 — Send RQST_SET_TEST with the test code.
              Clear m_reported_objects.
              Record the per-test timeout.

    State 2 — If the sequence item has a stimulus_type, send ONE stimulus
              frame immediately after SET_TEST.
              (Only HW_TEST_CAN_ECHO uses this: stimulus = RQST_ECHO, 0x55.)

    State 3 — Countdown: decrement timeout by SEQ_QUANTUM_MS (20 ms) each
              iteration.  Continuously receive CAN frames and accumulate them
              in m_reported_objects (keyed by object type+id).
              When timeout reaches 0, advance to evaluation.

    Evaluate — Read the latest 0x81 (TEST_STATUS) object from
               m_reported_objects.  Check V+ (bit 3) and/or S+ (bit 5).
               Check ANLG limits as secondary criterion.

Pass / fail logic
─────────────────
Primary   — firmware flags in the last received 0x81 frame:
            V+ (0x08) OR S+ (0x20) set  →  PASS
            V or S flag set but OK bit absent  →  FAIL
            Neither V nor S set  →  treated as monitoring-only, PASS assumed
Secondary — ANLG[] channel values vs. limits in hw_test_criteria.py.
            An out-of-range analog value promotes result to FAIL only if the
            firmware primary result was PASS.

Result record per test
──────────────────────
{
  "test_key":        str,
  "test_code":       int,
  "description":     str,
  "timeout_ms":      int,
  "result":          str,   # "PASS" | "FAIL" | "TIMEOUT" | "ERROR"
  "firmware_result": str,   # "PASS" | "FAIL" | "NO_RESULT"
  "flags":           int | None,
  "flags_str":       str,   # e.g. "BT V+ S+"
  "echo_received":   int,
  "analog_values":   {ch_id: float, ...},
  "analog_checks":   {ch_id: (passed: bool, message: str), ...},
  "analog_result":   str,   # "PASS" | "FAIL" | "N/A"
  "message":         str,
  "duration_s":      float,
}
"""

import time
import csv
import datetime
import os
from typing import List, Dict, Any, Optional

from hw_protocol      import HwTestProtocol
from hw_can_utils     import HwTestCANBus, send_frame, recv_frame, check_can_link
from hw_test_criteria import (
    check_analog, channel_name,
    set_active_hw_version, active_board_name,
    HW_VERSION_NAMES, MANUAL_SETUP_INSTRUCTIONS,
    TEST_RELEVANT_CHANNELS,
)

# Optional scope hook — inert by default; activates when
# scope_interface.SCOPE_CAPTURE_ENABLED is set to True.
try:
    from scope_interface import (
        SCOPE_CAPTURE_ENABLED, arm as scope_arm, collect as scope_collect,
    )
except ImportError:
    SCOPE_CAPTURE_ENABLED = False
    def scope_arm(_test_key):     pass
    def scope_collect(_tk, _res): pass
from config import (
    CAN_INTERFACE, CAN_CHANNEL, CAN_BITRATE,
    TEST_SEQUENCE, UNIT_SN, OPERATOR, RESULTS_CSV,
    BOOT_WAIT_S, ENV_SETUP_DELAY_S, INTER_TEST_DELAY_S,
    SEQ_QUANTUM_MS, CAN_RECV_TIMEOUT_S,
    EARLY_EXIT_ON_PASS, EARLY_EXIT_MIN_MS, EARLY_EXIT_GRACE_MS,
    STIMULUS_DELAY_MS, HW_VERSION_OVERRIDE, PASS_REQUIRED_OK_FRAMES,
    INTERACTIVE_PROMPTS,
)

# Alias: match original constant name
_APP_HW_TEST_SEQ_QUANTUM_TIME_IN_MS = SEQ_QUANTUM_MS


# ─────────────────────────────────────────────────────────────────────────────
# Protocol frame builders
# ─────────────────────────────────────────────────────────────────────────────

def _build_and_send(bus: HwTestCANBus,
                    protocol: HwTestProtocol,
                    rqst_type: str,
                    instance: int,
                    value: int) -> bool:
    """
    Build a protocol TX frame and send it.
    Mirrors _SendUserRequestByCAN() in the original.
    Returns True if the frame was built and sent.
    """
    result = protocol.sfHwTestProtocolProcessTxMessage(rqst_type, instance, value)
    if result and result[0] > 0:
        send_frame(bus, result[1])
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Single-test executor (States 1 → 2 → 3 → evaluate)
# ─────────────────────────────────────────────────────────────────────────────

def run_single_test(bus:        HwTestCANBus,
                    protocol:   HwTestProtocol,
                    test_key:   str,
                    stim_type:  str,
                    stim_value: int,
                    timeout_ms: int) -> Dict[str, Any]:
    """
    Execute one test following the original state machine.

    Parameters
    ----------
    bus        : open HwTestCANBus
    protocol   : HwTestProtocol instance
    test_key   : e.g. "HW_TEST_CAN_ECHO"
    stim_type  : stimulus request type string, or "" for none
                 (e.g. "SF_HW_TEST_PROTOCOL_RQST_ECHO")
    stim_value : integer value for the stimulus (e.g. 0x55)
    timeout_ms : milliseconds to wait before evaluating
    """
    tests_dict  = protocol.sfHwTestProtocolGetTestsDictionary()
    test_code   = tests_dict[test_key][0]
    description = tests_dict[test_key][1]

    result: Dict[str, Any] = {
        "test_key":        test_key,
        "test_code":       test_code,
        "description":     description,
        "timeout_ms":      timeout_ms,
        "result":          "TIMEOUT",
        "firmware_result": "NO_RESULT",
        "flags":           None,
        "flags_str":       "—",
        "echo_received":   0,
        "analog_values":   {},
        "analog_checks":   {},
        "analog_result":   "N/A",
        "analog_flags":    {},      # ch_id -> raw flags int (bit0 = FW OUT_OF_RANGE)
        "message":         "",
        "duration_s":      0.0,
        "early_exit":      False,
        "latched_flags":   0,       # OR-aggregate of every 0x81 flag seen
        "flags_history":   [],      # full list of 0x81 flag values seen
                                    #   during this test, in arrival order.
                                    #   Used for the "last-N must all be OK"
                                    #   pass criterion (cyclic tests like
                                    #   sin/cos report 3 status frames per
                                    #   cycle — one per sub-test — and we
                                    #   require all 3 to be S+).
    }

    t_start = time.monotonic()

    # Optional scope: configure / arm just before SET_TEST is issued.
    scope_arm(test_key)

    # ── State 1: Send SET_TEST, clear m_reported_objects ──────────────────
    _build_and_send(bus, protocol,
                    "SF_HW_TEST_PROTOCOL_RQST_SET_TEST", 0, test_key)

    m_reported_objects: Dict[str, Any] = {}   # cleared on each new test

    # ── State 2: Send ONE stimulus if required ────────────────────────────
    # Mirrors: if stimulus_type != "": send stimulus (once, not periodically)
    if stim_type:
        # The firmware only processes the ECHO request when test_type has
        # already been switched to HW_TEST_CAN_ECHO (see hw_testing.c
        # hw_test_comm_can_rqst_process_echo()). test_type is updated inside
        # testing_HW() which runs on a 20 ms quantum, so the stimulus must
        # wait at least one quantum after SET_TEST.
        if STIMULUS_DELAY_MS > 0:
            time.sleep(STIMULUS_DELAY_MS / 1000.0)
        _build_and_send(bus, protocol, stim_type, 0, stim_value)

    # ── State 3: Countdown with frame accumulation ────────────────────────
    # Each iteration = one quantum (20 ms).  Accumulate objects from the
    # listening path.  Mirrors _ThreadListeningExecute + _ThreadSequenceExecute.
    #
    # Early-exit logic (if EARLY_EXIT_ON_PASS): once the latest TEST_STATUS
    # frame reports V+ or S+, switch from "wait full timeout" to "wait one
    # short grace window" so trailing analog reports are still captured.
    remaining_ms       = timeout_ms
    grace_active       = False
    grace_remaining_ms = 0
    elapsed_ms         = 0
    test_status_key    = protocol.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_TEST + "0"

    def _firmware_already_passed():
        # Strict pass criterion: require the last N=PASS_REQUIRED_OK_FRAMES
        # status frames to all carry V+ or S+. Won't trigger early-exit
        # until at least N frames have arrived.
        hist = result["flags_history"]
        if len(hist) < PASS_REQUIRED_OK_FRAMES:
            return False
        return _evaluate_firmware_flags(
            protocol, hist[-1], hist) == "PASS"

    while remaining_ms > 0:
        # Listen for frames during one quantum
        quantum_deadline = time.monotonic() + _APP_HW_TEST_SEQ_QUANTUM_TIME_IN_MS / 1000.0

        while time.monotonic() < quantum_deadline:
            frame = recv_frame(bus, timeout_s=CAN_RECV_TIMEOUT_S)
            if frame is not None:
                _can_id, data = frame
                # Mirrors ProcessMessageCan → sfHwTestProtocolProcessRxMessage
                action, obj = protocol.sfHwTestProtocolProcessRxMessage(
                    len(data), list(data)
                )

                if action == protocol.SF_HW_TEST_PROTOCOL_ACTION_CLEAR_OBJECTS:
                    m_reported_objects.clear()

                elif action == protocol.SF_HW_TEST_PROTOCOL_ACTION_UPDATE_OBJECT:
                    # Detect echo response
                    if stim_type:
                        for k, v in obj.items():
                            if (v.get(protocol.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY) ==
                                    protocol.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_BUFFER):
                                result["echo_received"] += 1
                    # Record every TEST_STATUS frame's flags in arrival order
                    # so the pass criterion can require the last-N to all be
                    # OK (cyclic tests emit one status frame per sub-test
                    # completion; all of them must be S+/V+ for PASS).
                    for _k, v in obj.items():
                        if (v.get(protocol.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY) ==
                                protocol.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_TEST):
                            try:
                                f = int(v[protocol.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_TEST_STATUS_KEY][0])
                                result["latched_flags"] |= f
                                result["flags_history"].append(f)
                            except (KeyError, IndexError, TypeError):
                                pass
                    # Accumulate in m_reported_objects (latest value wins)
                    m_reported_objects.update(obj)

        remaining_ms -= _APP_HW_TEST_SEQ_QUANTUM_TIME_IN_MS
        elapsed_ms   += _APP_HW_TEST_SEQ_QUANTUM_TIME_IN_MS

        # ── Early-exit on firmware PASS ───────────────────────────────────
        if (EARLY_EXIT_ON_PASS
                and not grace_active
                and elapsed_ms >= EARLY_EXIT_MIN_MS
                and _firmware_already_passed()):
            grace_active       = True
            grace_remaining_ms = EARLY_EXIT_GRACE_MS

        if grace_active:
            grace_remaining_ms -= _APP_HW_TEST_SEQ_QUANTUM_TIME_IN_MS
            if grace_remaining_ms <= 0:
                break

    result["duration_s"] = time.monotonic() - t_start
    result["early_exit"] = grace_active

    # ── Evaluate: extract TEST_STATUS object ─────────────────────────────
    test_status_key = protocol.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_TEST + "0"

    if test_status_key in m_reported_objects:
        obj = m_reported_objects[test_status_key]
        raw_flags = int(obj[protocol.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_TEST_STATUS_KEY][0])
        result["flags"]     = raw_flags
        result["flags_str"] = _flags_to_string(protocol, raw_flags)

        fw_result = _evaluate_firmware_flags(
            protocol, raw_flags, result["flags_history"])
        result["firmware_result"] = fw_result

        # Build a compact "last N flags" string for the message so the
        # engineer can see whether the last cycle was all-OK or had a S-/V-.
        hist = result["flags_history"]
        n_check = min(PASS_REQUIRED_OK_FRAMES, len(hist))
        last_n_str = " | ".join(_flags_to_string(protocol, f)
                                 for f in hist[-n_check:]) if n_check else "—"

        if fw_result == "PASS":
            result["result"]  = "PASS"
            result["message"] = (f"{result['flags_str']}  "
                                  f"(last {n_check}: {last_n_str})")
        elif fw_result == "FAIL":
            result["result"]  = "FAIL"
            result["message"] = (f"Firmware reported failure in last "
                                  f"{n_check} frames: {last_n_str}")
        else:
            # NO_RESULT (no V/S bits): monitoring test — pass assumed
            result["result"]  = "PASS"
            result["message"] = "Monitoring test — no firmware verdict (PASS assumed)"
    else:
        result["result"]  = "TIMEOUT"
        result["message"] = "No TEST_STATUS frame (0x81) received within timeout"

    # ── Secondary: analog limit checks ───────────────────────────────────
    _extract_analog_values(protocol, m_reported_objects, result)
    _check_analog_limits(result)

    # ── ECHO secondary check ──────────────────────────────────────────────
    if stim_type and result["result"] == "PASS" and result["echo_received"] == 0:
        result["result"]  = "FAIL"
        result["message"] = (
            "CAN ECHO: firmware V+/S+ but zero echo responses — "
            "CAN RX path suspect"
        )

    # Optional scope: pull measurements / screenshots into the result.
    scope_collect(test_key, result)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Flag helpers (mirrors sfHwTestProtocol flag methods)
# ─────────────────────────────────────────────────────────────────────────────

def _flags_to_string(protocol: HwTestProtocol, flags: int) -> str:
    """Return a compact string like 'BT RN V+' from the raw status integer."""
    parts = []
    if flags & protocol.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_REBOOT:
        parts.append("BT")
    if flags & protocol.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_RUNNING:
        parts.append("RN")
    if flags & protocol.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_VERIF:
        if flags & protocol.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_VERIF_OK:
            parts.append("V+")
        else:
            parts.append("V-")
    if flags & protocol.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_SELFTEST:
        if flags & protocol.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_SELFTEST_OK:
            parts.append("S+")
        else:
            parts.append("S-")
    return " ".join(parts) if parts else "—"


def _frame_is_ok(protocol: HwTestProtocol, flags: int):
    """
    Classify a single TEST_STATUS frame.

    Returns one of:
        "OK"          — frame carries V+ or S+ (sub-test passed)
        "FAIL"        — frame carries V (without V+) or S (without S+)
        "NO_RESULT"   — neither V nor S set (monitoring frame)
    """
    bm = protocol
    v_set  = bool(flags & bm.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_VERIF)
    vp_set = bool(flags & bm.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_VERIF_OK)
    s_set  = bool(flags & bm.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_SELFTEST)
    sp_set = bool(flags & bm.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_SELFTEST_OK)
    if not v_set and not s_set:
        return "NO_RESULT"
    if (v_set and not vp_set) or (s_set and not sp_set):
        return "FAIL"
    return "OK" if (vp_set or sp_set) else "NO_RESULT"


def _evaluate_firmware_flags(protocol:       HwTestProtocol,
                              flags:         int,
                              flags_history: Optional[List[int]] = None,
                              required_ok:   int = None) -> str:
    """
    Evaluate the firmware verdict for a finished test.

    Pass criterion (strict, matches firmware semantics):

      - "OK"        → frame has V+ or S+
      - "FAIL"      → frame has V- (V set, V+ absent) or S- (S set, S+ absent)
      - "NO_RESULT" → frame has neither V nor S (pure monitoring)

    The test PASSes only if **the last N status frames** (N defaults to
    config.PASS_REQUIRED_OK_FRAMES, normally 3) are all "OK". This matches
    the cyclic firmware behaviour of the differential-analog loopback tests
    (sin/cos, ext-temp, unipolar/bipolar V) which emit one frame per
    sub-test boundary; all 3 sub-tests in a cycle must report S+ to pass.

    Single-shot tests (e.g. ALL_DRIVERS_SETTING) emit the same V+ frame
    repeatedly during the timeout window, so the same N-of-N criterion
    works without special-casing them.

    Fallback: if the test produced fewer than N status frames (very short
    firmware execution or interrupted), fall back to evaluating just the
    latest *flags* — i.e. the original single-frame behaviour.
    """
    if required_ok is None:
        required_ok = PASS_REQUIRED_OK_FRAMES

    # Per-frame fallback first: if we have no history yet, use the latest
    # flags directly (covers very-fast tests that finished before we
    # captured 3 frames).
    if not flags_history:
        return _frame_is_ok(protocol, flags)

    history = flags_history[-required_ok:]
    classifications = [_frame_is_ok(protocol, f) for f in history]

    # If every frame is monitoring-only, treat as NO_RESULT (assumed PASS
    # by caller for the LEDS-style continuous tests).
    if all(c == "NO_RESULT" for c in classifications):
        return "NO_RESULT"

    # Any FAIL in the last-N window → test FAIL
    if any(c == "FAIL" for c in classifications):
        return "FAIL"

    # All frames in the window are either OK or NO_RESULT, with at least
    # one OK → PASS only if every result-bearing frame in the window was OK
    # (the NO_RESULT entries are tolerated — they represent state-transition
    # ticks between sub-tests).
    return "PASS"


# ─────────────────────────────────────────────────────────────────────────────
# Analog extraction / limit helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_analog_values(protocol:          HwTestProtocol,
                            m_reported_objects: Dict[str, Any],
                            result:             Dict[str, Any]) -> None:
    for _key, obj in m_reported_objects.items():
        if (obj.get(protocol.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY) ==
                protocol.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_ANALOG):
            ch_id = obj[protocol.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_ID_KEY]
            value = obj[protocol.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_VALUE_KEY]
            flags = obj.get(protocol.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_FLAGS_KEY, 0)
            result["analog_values"][ch_id] = float(value)
            result["analog_flags"][ch_id]  = int(flags)


def _fw_out_of_range(result: Dict[str, Any], ch_id: int) -> bool:
    """True if the firmware tagged this channel with OUT_OF_RANGE (bit 0)."""
    return bool(result.get("analog_flags", {}).get(ch_id, 0) & 0x01)


def _check_analog_limits(result: Dict[str, Any]) -> None:
    if not result["analog_values"]:
        return

    # Per-test relevance: if the test is listed in TEST_RELEVANT_CHANNELS,
    # only limit-check those channels. The firmware streams other channels
    # as default-zero "carry-through" values that aren't actively measured
    # by this test (e.g. test 0x05 emits pump HS-switch temps at 0 °C even
    # though it doesn't measure them) — they should be reported but not
    # cause a limit failure.
    relevant = TEST_RELEVANT_CHANNELS.get(result["test_key"])

    all_pass = True
    for ch_id, value in result["analog_values"].items():
        if relevant is not None and ch_id not in relevant:
            # Channel reported but not actively measured by this test;
            # show the value but skip the limit check.
            result["analog_checks"][ch_id] = (
                True,
                f"{channel_name(ch_id)} = {value:.4g}  "
                f"[reported but not measured by {result['test_key']}]")
            continue
        passed, msg_txt = check_analog(ch_id, value)
        result["analog_checks"][ch_id] = (passed, msg_txt)
        if not passed:
            all_pass = False

    result["analog_result"] = "PASS" if all_pass else "FAIL"

    if not all_pass and result["result"] == "PASS":
        failed_channels = [channel_name(ch)
                           for ch, (ok, _) in result["analog_checks"].items()
                           if not ok]
        result["result"]  = "FAIL"
        result["message"] = "Analog limit violation on: " + ", ".join(failed_channels)


# ─────────────────────────────────────────────────────────────────────────────
# Full sequence runner
# ─────────────────────────────────────────────────────────────────────────────

def run_sequence(bus:               HwTestCANBus,
                 protocol:          HwTestProtocol,
                 sequence:          list,
                 verbose:           bool = True,
                 interactive_prompts: bool = None) -> List[Dict[str, Any]]:
    """
    Run a complete test sequence.

    Implements the State 0 (SET_TEST_ENV) + loop over State 1–3 logic from
    _ThreadSequenceExecute() in the original tool.

    Parameters
    ----------
    bus      : open HwTestCANBus
    protocol : HwTestProtocol instance
    sequence : list of (test_key, stim_type, stim_value, timeout_ms)
               as returned by sfHwTestProtocolGetMinimumASampleTestsList() etc.
    verbose  : print live progress to stdout
    """
    results: List[Dict[str, Any]] = []

    if interactive_prompts is None:
        interactive_prompts = INTERACTIVE_PROMPTS

    # ── State 0: Send SET_TEST_ENV once ───────────────────────────────────
    # Mirrors original: flags = SF_HW_TEST_PROTOCOL_TEST_SET_ENV_FLAGS_REPORT_ENABLE
    _build_and_send(
        bus, protocol,
        "SF_HW_TEST_PROTOCOL_RQST_SET_TEST_ENV",
        0,
        protocol.SF_HW_TEST_PROTOCOL_TEST_SET_ENV_FLAGS_REPORT_ENABLE,
    )
    time.sleep(ENV_SETUP_DELAY_S)

    total  = len(sequence)
    passed = failed = other = 0

    if verbose:
        print(f"\n{'─'*72}")
        print(f"  Inverter Gen3 — Stage 1 HW PCBA Test Campaign  ({total} tests)")
        print(f"{'─'*72}")

    for idx, (test_key, stim_type, stim_value, timeout_ms) in enumerate(sequence, 1):
        # Manual-setup prompt for tests that need the operator to wire
        # the DAC into a specific isolated-input pin pair.
        if interactive_prompts and test_key in MANUAL_SETUP_INSTRUCTIONS:
            print()
            print("  " + "═" * 70)
            print(f"  ⚠  MANUAL HOOKUP REQUIRED — {test_key}")
            print(f"     {MANUAL_SETUP_INSTRUCTIONS[test_key]}")
            print("  " + "═" * 70)
            try:
                input("  Press ENTER when the connection is ready, Ctrl+C to abort … ")
            except KeyboardInterrupt:
                print("\n  Campaign aborted by operator.")
                raise
            except EOFError:
                # stdin closed (e.g. running non-interactively) — skip prompt
                pass

        if verbose:
            label = test_key
            print(f"  [{idx:>2}/{total}]  {label:<48}  "
                  f"timeout={timeout_ms} ms", end="", flush=True)

        rec = run_single_test(
            bus, protocol, test_key, stim_type, stim_value, timeout_ms
        )
        results.append(rec)

        if rec["result"] == "PASS":
            passed += 1
        elif rec["result"] == "FAIL":
            failed += 1
        else:
            other  += 1

        if verbose:
            glyph  = {"PASS": "  PASS", "FAIL": "  FAIL"}.get(
                rec["result"], f"  {rec['result']}")
            flags  = f"  [{rec['flags_str']}]" if rec["flags_str"] != "—" else ""
            dur    = f"  {rec['duration_s']:.2f}s"
            print(f"{glyph}{flags}{dur}")

            # On PASS — show only out-of-limit lines (none expected).
            # On FAIL / TIMEOUT / ERROR — dump every collected ANLG reading
            # so the operator immediately sees what the firmware reported.
            if rec["result"] == "PASS":
                for ch_id, (ok, msg_txt) in rec["analog_checks"].items():
                    if not ok:
                        print(f"         !! {msg_txt}")
            else:
                if rec["analog_values"]:
                    print("         Analog readings collected during the test:")
                    print("         (* = firmware flagged OUT_OF_RANGE in its own check;")
                    print("          !! = exceeds Python limit; both can flag the same line)")
                    for ch_id in sorted(rec["analog_values"].keys()):
                        value = rec["analog_values"][ch_id]
                        ok, msg_txt = rec["analog_checks"].get(
                            ch_id, (True, channel_name(ch_id) +
                                    f" = {value:.4g}  [no limit defined]"))
                        fw_oor = _fw_out_of_range(rec, ch_id)
                        # 3-char prefix: '*' for FW OOR + '!!' for Python OOR
                        prefix = ("*" if fw_oor else " ") + ("!!" if not ok else "  ")
                        print(f"         {prefix} {msg_txt}")
                else:
                    print("         (no ANLG[] frames received — flag-only failure)")

        time.sleep(INTER_TEST_DELAY_S)

    # ── Cleanup: tell the firmware to stop whatever test is currently
    # running so we don't leave outputs (e.g. PUMP_AUTO's EN/LATCH/SEL
    # sweep) cycling after the campaign ends.
    _build_and_send(bus, protocol,
                    "SF_HW_TEST_PROTOCOL_RQST_SET_TEST", 0, "HW_TEST_NO_TEST")
    time.sleep(0.1)
    if verbose:
        print("  [cleanup] SET_TEST(HW_TEST_NO_TEST) sent — firmware idle.")

    if verbose:
        overall = "PASS" if (failed == 0 and other == 0) else "FAIL"
        print(f"{'─'*72}")
        print(f"  RESULT: {overall}   "
              f"PASS={passed}  FAIL={failed}  TIMEOUT/ERROR={other}")
        print(f"{'─'*72}\n")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# CSV output
# ─────────────────────────────────────────────────────────────────────────────

def write_results_csv(results: List[Dict[str, Any]], csv_path: str) -> None:
    """Write test results to *csv_path* (created / overwritten)."""
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
    ts = datetime.datetime.now().isoformat(timespec="seconds")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp", "test_key", "test_code",
            "result", "firmware_result", "flags_str",
            "duration_s", "echo_received", "message",
        ])
        for rec in results:
            writer.writerow([
                ts,
                rec["test_key"],
                f"0x{rec['test_code']:02X}",
                rec["result"],
                rec["firmware_result"],
                rec["flags_str"],
                f"{rec['duration_s']:.3f}",
                rec["echo_received"],
                rec["message"],
            ])

    print(f"[CSV] Results written → {csv_path}")


# ─────────────────────────────────────────────────────────────────────────────
# High-level entry point (called from run_tests.py)
# ─────────────────────────────────────────────────────────────────────────────

def execute_campaign(sequence_name: str  = TEST_SEQUENCE,
                     unit_sn:       str  = UNIT_SN,
                     operator:      str  = OPERATOR,
                     results_csv:   str  = RESULTS_CSV,
                     verbose:       bool = True,
                     hw_version:    Optional[int] = None,
                     interactive_prompts: Optional[bool] = None):
    """
    Open the CAN interface, run the selected sequence, write the CSV.
    Returns (session_meta, results_list).

    Parameters
    ----------
    sequence_name : "A0_A1" (or "A0"/"A1") | "B0"
    unit_sn       : board serial number for the report
    operator      : test engineer name for the report
    results_csv   : path for the CSV output
    verbose       : print live progress to stdout
    """
    protocol = HwTestProtocol()

    # Apply HW-version configuration (CLI > config.py > auto)
    effective_hw = hw_version if hw_version is not None else HW_VERSION_OVERRIDE
    set_active_hw_version(effective_hw)

    seq_upper = sequence_name.upper()
    if seq_upper in ("A0_A1", "A0", "A1"):
        sequence  = protocol.sfHwTestProtocolGetMinimumASampleTestsList()
        seq_label = "A0/A1-Sample (17 tests)"
    elif seq_upper in ("B0", "B1", "B2"):
        sequence  = protocol.sfHwTestProtocolGetMinimumBSampleTestsList()
        seq_label = f"{seq_upper}-Sample ({len(sequence)} tests, B0/B1/B2 share the same list)"
    elif seq_upper in ("B0_SELF", "B1_SELF", "B2_SELF", "B_SELF"):
        # Phase 1 — self auto-verification (no operator input)
        sequence  = protocol.sfHwTestProtocolGetBSampleSelfTestsList()
        seq_label = f"B-Sample Phase 1 — Self auto-verification ({len(sequence)} tests)"
    elif seq_upper in ("B0_LOOPBACK", "B1_LOOPBACK", "B2_LOOPBACK", "B_LOOPBACK"):
        # Phase 3 — DAC-injection loopback tests (operator hookups)
        sequence  = protocol.sfHwTestProtocolGetBSampleLoopbackTestsList()
        seq_label = f"B-Sample Phase 3 — Loopback DAC tests ({len(sequence)} tests)"
    else:
        raise ValueError(
            f"Unknown sequence: {sequence_name!r}. Use 'A0_A1', "
            f"'B0'/'B1'/'B2' (full), '<B>_SELF' (Phase 1) or "
            f"'<B>_LOOPBACK' (Phase 3)."
        )

    if effective_hw is None:
        hw_label = "auto (will use channel-0 reading)"
    else:
        name = HW_VERSION_NAMES.get(effective_hw, f"HW_VERSION={effective_hw}")
        hw_label = f"{name}  (HW_VERSION={effective_hw})"

    print(f"\n{'='*72}")
    print(f"  Inverter Gen3 — Stage 1 HW PCBA Automated Test")
    print(f"  Unit S/N  : {unit_sn}")
    print(f"  Operator  : {operator}")
    print(f"  Sequence  : {seq_label}")
    print(f"  HW board  : {hw_label}")
    print(f"  CAN       : PCAN_USBBUS1  250 kBit/s  ID=0x100")
    print(f"{'='*72}")

    with HwTestCANBus() as bus:
        print(f"[CAN] Bus open.  Waiting {BOOT_WAIT_S} s for board to stabilise…")
        time.sleep(BOOT_WAIT_S)
        check_can_link(bus, protocol)

        results = run_sequence(bus, protocol, sequence,
                                verbose=verbose,
                                interactive_prompts=interactive_prompts)

    # Write CSV
    write_results_csv(results, results_csv)

    session_meta = {
        "test_date":     datetime.datetime.now().isoformat(timespec="seconds"),
        "unit_sn":       unit_sn,
        "operator":      operator,
        "sequence":      sequence_name,
        "can_interface": CAN_INTERFACE,
        "can_channel":   CAN_CHANNEL,
        "can_bitrate":   CAN_BITRATE,
    }

    return session_meta, results
