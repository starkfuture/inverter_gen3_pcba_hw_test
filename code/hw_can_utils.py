"""
hw_can_utils.py  –  CAN bus utilities for Stage 1 HW PCBA tests.

Wraps pcan_interface.py to provide the same helper functions used by
hw_test_runner.py.  The communication backend (PCANBasic.dll or python-can)
is selected automatically by pcan_interface.py.

All communication uses standard 11-bit frames on CAN ID 0x100.
Frame length is always exactly 8 bytes.
"""

import time
from typing import Optional, List, Tuple

from pcan_interface import (
    open_can,
    close_can,
    write_message,
    read_message,
    flush_rx as _flush_rx,
)
from config import CAN_ID


# ─────────────────────────────────────────────────────────────────────────────
# Bus context manager
# ─────────────────────────────────────────────────────────────────────────────

class HwTestCANBus:
    """
    Context manager that opens/closes the CAN interface.

    Usage::

        with HwTestCANBus() as bus:
            send_frame(bus, payload)
            msg = recv_frame(bus, timeout_s=0.5)
    """

    def __init__(self):
        self._handle = None

    def open(self) -> "HwTestCANBus":
        self._handle = open_can()
        return self

    def close(self):
        if self._handle is not None:
            close_can(self._handle)
            self._handle = None

    def __enter__(self) -> "HwTestCANBus":
        return self.open()

    def __exit__(self, *_):
        self.close()

    @property
    def handle(self):
        if self._handle is None:
            raise RuntimeError("HwTestCANBus is not open — call open() first")
        return self._handle


# ─────────────────────────────────────────────────────────────────────────────
# Send / receive helpers
# ─────────────────────────────────────────────────────────────────────────────

def send_frame(bus: HwTestCANBus, payload) -> None:
    """
    Transmit a single standard (11-bit) CAN frame on CAN_ID 0x100.

    Parameters
    ----------
    bus     : open HwTestCANBus
    payload : list[int] or bytes, exactly 8 bytes
    """
    write_message(bus.handle, CAN_ID, bytes(payload))


def recv_frame(bus: HwTestCANBus,
               timeout_s: float = 0.02) -> Optional[Tuple[int, bytes]]:
    """
    Poll for one frame (matching CAN_ID 0x100) for up to *timeout_s* seconds.

    Returns (can_id, data) or None on timeout.
    Only accepts standard 8-byte frames on CAN_ID.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = read_message(bus.handle)
        if result is not None:
            can_id, data = result
            if can_id == CAN_ID and len(data) == 8:
                return can_id, data
        # brief sleep to avoid 100% CPU — matches original ReadMessages() loop
        remaining = deadline - time.monotonic()
        if remaining > 0.001:
            time.sleep(0.001)
    return None


def collect_frames(bus: HwTestCANBus,
                   duration_s: float) -> List[Tuple[int, bytes]]:
    """
    Collect all standard 8-byte frames with CAN_ID for *duration_s* seconds.
    Returns a list ordered by arrival time.
    """
    frames: List[Tuple[int, bytes]] = []
    deadline = time.monotonic() + duration_s
    while time.monotonic() < deadline:
        result = read_message(bus.handle)
        if result is not None:
            can_id, data = result
            if can_id == CAN_ID and len(data) == 8:
                frames.append((can_id, data))
        else:
            remaining = deadline - time.monotonic()
            if remaining > 0.001:
                time.sleep(0.001)
    return frames


def flush_rx(bus: HwTestCANBus, duration_s: float = 0.05) -> int:
    """
    Discard all pending frames for *duration_s* seconds.
    Returns the number of frames discarded.
    """
    return _flush_rx(bus.handle, duration_s)


# ─────────────────────────────────────────────────────────────────────────────
# Link check
# ─────────────────────────────────────────────────────────────────────────────

def check_can_link(bus: HwTestCANBus, protocol=None,
                   timeout_s: float = 1.5, verbose: bool = True) -> bool:
    """Verify the HW-test board is actually responding on CAN.

    Opening the PCAN channel succeeds even when nothing is connected on the
    other end (the USB dongle opens regardless of bus state), so a successful
    open() does NOT prove the board is there. This actively probes it: enable
    status reporting, start a harmless monitoring test (SUPPLY_VOLTAGES — pure
    measurement, no gate/actuation), and listen for any status frame on
    CAN_ID. Frames back → board alive; silence → channel open but board not
    answering (cable unplugged, board unpowered, wrong firmware, or the PCAN
    link dropped). The firmware is returned to NO_TEST before returning.

    Returns True if the board responded, False otherwise.
    """
    if protocol is None:
        from hw_protocol import HwTestProtocol
        protocol = HwTestProtocol()

    def _tx(rqst, instance, value):
        res = protocol.sfHwTestProtocolProcessTxMessage(rqst, instance, value)
        if res and res[0] > 0:
            send_frame(bus, res[1])

    flush_rx(bus, 0.05)
    flags = (protocol.SF_HW_TEST_PROTOCOL_TEST_SET_ENV_FLAGS_REPORT_ENABLE
             | protocol.SF_HW_TEST_PROTOCOL_TEST_SET_ENV_FLAGS_CLEAR_REBOOT)
    _tx("SF_HW_TEST_PROTOCOL_RQST_SET_TEST_ENV", 0, flags)
    time.sleep(0.2)
    _tx("SF_HW_TEST_PROTOCOL_RQST_SET_TEST", 0, "HW_TEST_SUPPLY_VOLTAGES")

    alive = recv_frame(bus, timeout_s=timeout_s) is not None

    _tx("SF_HW_TEST_PROTOCOL_RQST_SET_TEST", 0, "HW_TEST_NO_TEST")
    time.sleep(0.05)

    if verbose:
        if alive:
            print("[CAN] Board link OK — board is responding on ID 0x100.")
        else:
            bang = "!" * 68
            print("\n  " + bang)
            print("  ⚠  NO RESPONSE FROM THE BOARD ON CAN (ID 0x100).")
            print("     The PCAN channel opened, but the board is NOT answering.")
            print("     Any measurement will be meaningless (the firmware isn't")
            print("     driving anything). Check:")
            print("        • CAN cable seated  (board  ↔  PCAN-USB)")
            print("        • board powered and flashed with the HW-test firmware")
            print("        • PCAN dongle link  (unplug/replug if it dropped)")
            print("  " + bang + "\n")
    return alive
