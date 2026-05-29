"""
pcan_interface.py  –  CAN interface layer for Stage 1 HW PCBA tests.

Attempts to use PCANBasic.dll directly through the PCANBasic Python wrapper
(the same approach as STARK_FUTURE_InvGen3_hw_test.py).  Falls back to
python-can with the pcan backend if PCANBasic.py is not on the path.

Usage
-----
    from pcan_interface import open_can, close_can, write_message, read_message

    handle = open_can()          # opens PCAN_USBBUS1 @ 250 kBit/s
    write_message(handle, 0x100, [0x01,0x20,0x02,0x00,0x00,0x00,0x00,0x00])
    msg = read_message(handle)   # returns (can_id, data_bytes) or None
    close_can(handle)
"""

import sys
import time
from typing import Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Try to import PCANBasic (matches original code)
# ─────────────────────────────────────────────────────────────────────────────

_USE_PCAN_BASIC = False

try:
    from PCANBasic import (
        PCANBasic,
        TPCANMsg,
        TPCANTimestamp,
        PCAN_USBBUS1,
        PCAN_BAUD_250K,
        PCAN_ERROR_OK,
        PCAN_ERROR_QRCVEMPTY,
        PCAN_MESSAGE_STANDARD,
    )
    _USE_PCAN_BASIC = True
except ImportError:
    # PCANBasic.py is not on the Python path – fall back to python-can
    try:
        import can as _can
    except ImportError as e:
        raise ImportError(
            "Neither PCANBasic.py nor python-can is available.\n"
            "Install the PEAK driver (PCANBasic.py) or run: "
            "pip install python-can"
        ) from e


# ─────────────────────────────────────────────────────────────────────────────
# Constants (same values as in PCANBasic.py, kept here for the fallback path)
# ─────────────────────────────────────────────────────────────────────────────

_PCAN_USBBUS1   = 0x0051   # PCAN-USB first port
_PCAN_BAUD_250K = 0x011A   # 250 kBit/s
_PCAN_MSG_STD   = 0x00     # PCAN_MESSAGE_STANDARD (11-bit ID)
_FRAME_LEN      = 8        # all HW-test frames are exactly 8 bytes
_CAN_BITRATE    = 250_000


# ─────────────────────────────────────────────────────────────────────────────
# PCANBasic path (native driver, matches original code exactly)
# ─────────────────────────────────────────────────────────────────────────────

class _PcanBasicHandle:
    """
    Thin stateful wrapper around a PCANBasic session.
    Returned by open_can() when PCANBasic.py is available.
    """
    __slots__ = ("_obj", "_handle")

    def __init__(self):
        self._obj    = PCANBasic()
        self._handle = PCAN_USBBUS1

    def initialize(self):
        result = self._obj.Initialize(self._handle, PCAN_BAUD_250K)
        if result != PCAN_ERROR_OK:
            raise RuntimeError(
                f"PCANBasic.Initialize failed with status 0x{result:08X}. "
                "Check that the PCAN-USB adapter is connected and the driver is installed."
            )

    def uninitialize(self):
        try:
            self._obj.Uninitialize(self._handle)
        except Exception:
            pass

    def write(self, can_id: int, data: bytes):
        msg = TPCANMsg()
        msg.ID      = can_id
        msg.LEN     = _FRAME_LEN
        msg.MSGTYPE = PCAN_MESSAGE_STANDARD.value
        for i, b in enumerate(data):
            msg.DATA[i] = b
        status = self._obj.Write(self._handle, msg)
        if status != PCAN_ERROR_OK:
            raise IOError(
                f"PCANBasic.Write failed with status 0x{status:08X}"
            )

    def read(self) -> Optional[Tuple[int, bytes]]:
        """
        Non-blocking read.  Returns (can_id, data) or None if no frame waiting.
        Mirrors original ReadMessage() logic.
        """
        status, msg, _ts = self._obj.Read(self._handle)
        if status == PCAN_ERROR_OK:
            if (msg.MSGTYPE == PCAN_MESSAGE_STANDARD.value and
                    msg.LEN == _FRAME_LEN):
                return msg.ID, bytes(msg.DATA[:_FRAME_LEN])
        return None


# ─────────────────────────────────────────────────────────────────────────────
# python-can fallback path
# ─────────────────────────────────────────────────────────────────────────────

class _PythonCanHandle:
    """
    python-can Bus wrapped to present the same read/write interface as
    _PcanBasicHandle, so the rest of the code is backend-agnostic.
    """
    __slots__ = ("_bus",)

    def __init__(self):
        self._bus = None

    def initialize(self):
        self._bus = _can.Bus(
            interface="pcan",
            channel="PCAN_USBBUS1",
            bitrate=_CAN_BITRATE,
        )

    def uninitialize(self):
        try:
            if self._bus is not None:
                self._bus.shutdown()
        except Exception:
            pass
        self._bus = None

    def write(self, can_id: int, data: bytes):
        msg = _can.Message(
            arbitration_id=can_id,
            data=data,
            is_extended_id=False,
            is_fd=False,
        )
        self._bus.send(msg, timeout=1.0)

    def read(self) -> Optional[Tuple[int, bytes]]:
        """
        Non-blocking read (0 s timeout).
        Returns (can_id, data) or None.
        """
        msg = self._bus.recv(timeout=0)
        if msg is not None:
            if (not msg.is_extended_id and len(msg.data) == _FRAME_LEN):
                return msg.arbitration_id, bytes(msg.data)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Public API — mirrors original code's open/read/write/close pattern
# ─────────────────────────────────────────────────────────────────────────────

def open_can():
    """
    Open the CAN interface and return an opaque handle.
    Uses PCANBasic.dll if available, otherwise python-can.

    Raises RuntimeError if the adapter cannot be opened.
    """
    if _USE_PCAN_BASIC:
        handle = _PcanBasicHandle()
        backend = "PCANBasic.dll"
    else:
        handle = _PythonCanHandle()
        backend = "python-can (pcan)"

    handle.initialize()
    print(f"[CAN] Opened via {backend}  (PCAN_USBBUS1 @ 250 kBit/s)")
    return handle


def close_can(handle) -> None:
    """Close the CAN interface previously opened with open_can()."""
    handle.uninitialize()
    print("[CAN] Interface closed.")


def write_message(handle, can_id: int, payload) -> None:
    """
    Transmit one standard 8-byte CAN frame.

    Parameters
    ----------
    handle  : value returned by open_can()
    can_id  : 11-bit arbitration ID
    payload : list[int] or bytes, exactly 8 bytes
    """
    data = bytes(payload)
    assert len(data) == _FRAME_LEN, (
        f"HW-test frames must be 8 bytes (got {len(data)})"
    )
    handle.write(can_id, data)


def read_message(handle) -> Optional[Tuple[int, bytes]]:
    """
    Non-blocking read.  Returns (can_id, data_bytes) or None.
    Mirrors original ReadMessage() behaviour.
    """
    return handle.read()


def flush_rx(handle, duration_s: float = 0.05) -> int:
    """
    Discard pending frames for *duration_s* seconds.
    Returns the count of frames discarded.
    """
    count    = 0
    deadline = time.monotonic() + duration_s
    while time.monotonic() < deadline:
        if handle.read() is not None:
            count += 1
        else:
            time.sleep(0.001)
    return count
