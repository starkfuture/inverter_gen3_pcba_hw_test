"""
ea_supply.py  –  EA laboratory power supply driver (pyvisa / USB).

Compatible with EA PSI and PSB series (SCPI over USB).
Use as a context manager – the output is ALWAYS disabled on __exit__ for safety.

Usage:
    with EASupply(visa_resource="USB0::0x2184::...") as ea:
        ea.set_voltage(48.0)
        ea.enable()
        time.sleep(1)
        v = ea.measure_voltage()
"""

import time
import threading
from typing import Optional

try:
    import pyvisa
    _PYVISA_AVAILABLE = True
except ImportError:
    _PYVISA_AVAILABLE = False


class EASupplyNotAvailable(Exception):
    """Raised when pyvisa is not installed or the resource is not found."""


# Substrings that identify an EA supply in a *IDN? reply.
_EA_IDN_MARKERS = ("ELEKTRO-AUTOMATIK", "PS 9500", "PS 9000", "EA-PS",
                   "9500-20")


def _configure_session(inst, resource: str, baud: int, timeout_ms: int):
    """Apply timeout + transport-specific I/O settings to a freshly
    opened VISA session. Handles all three transports we support:
      - ASRL<n>::INSTR        (USB-CDC serial): baud + \\n terminations
      - TCPIP::<ip>::<p>::SOCKET (raw LAN socket): \\n terminations
      - TCPIP::<ip>::INSTR    (VXI-11 LAN): protocol handles framing
    LAN is the recommended transport — it is galvanically isolated and
    immune to the HV-switching EMI that crashes the USB-CDC link."""
    inst.timeout = timeout_ms
    up = resource.upper()
    if up.startswith("ASRL"):
        inst.baud_rate = baud
        inst.write_termination = "\n"
        inst.read_termination = "\n"
    elif up.startswith("TCPIP") and up.endswith("SOCKET"):
        inst.write_termination = "\n"
        inst.read_termination = "\n"
    # TCPIP...INSTR (VXI-11): leave terminations at VISA defaults.


def _probe_idn(resource: str, backend: str, baud: int,
               timeout_ms: int = 1500) -> bool:
    """Open `resource`, query *IDN?, return True iff it answers as an EA.
    Short timeout so a non-EA / silent port fails fast."""
    if not _PYVISA_AVAILABLE:
        return False
    rm = inst = None
    try:
        rm = pyvisa.ResourceManager(backend) if backend \
            else pyvisa.ResourceManager()
        inst = rm.open_resource(resource)
        _configure_session(inst, resource, baud, timeout_ms)
        idn = (inst.query("*IDN?") or "").upper()
        return any(m in idn for m in _EA_IDN_MARKERS)
    except Exception:
        return False
    finally:
        try:
            if inst is not None:
                inst.close()
        except Exception:
            pass
        try:
            if rm is not None:
                rm.close()
        except Exception:
            pass


def discover_ea_resource(preferred: str, backend: str = "",
                         baud: int = 115200, timeout_ms: int = 1500) -> str:
    """Return a VISA resource string that actually answers as an EA.

    Strategy:
      1. Probe `preferred` first (the common, healthy case — one quick
         *IDN?).
      2. If that fails, enumerate the host's serial ports and probe each
         ASRL<n>::INSTR by *IDN?, skipping Bluetooth ports (their open()
         blocks for seconds). Return the first EA match.
      3. If nothing matches, return `preferred` unchanged so the normal
         open() path surfaces the original error.

    This makes the bench resilient to the EA-PS USB-CDC stack
    re-enumerating onto a different COM number after a drop (observed
    2026-05-27: COM6 -> gone -> reappears, sometimes renumbered)."""
    if not preferred:
        return preferred
    if _probe_idn(preferred, backend, baud, timeout_ms):
        return preferred
    # LAN resources have no COM-port equivalent to scan — return as-is so
    # the normal open() path surfaces the real connection error.
    if preferred.upper().startswith("TCPIP"):
        return preferred
    # Preferred serial port didn't answer as an EA — scan the others.
    candidates = []
    try:
        from serial.tools import list_ports
        for p in list_ports.comports():
            desc = (p.description or "")
            if "bluetooth" in desc.lower():
                continue  # opening a BT serial port blocks for seconds
            digits = "".join(ch for ch in p.device if ch.isdigit())
            if not digits:
                continue
            res = f"ASRL{digits}::INSTR"
            if res != preferred:
                candidates.append(res)
    except Exception:
        return preferred
    for res in candidates:
        if _probe_idn(res, backend, baud, timeout_ms):
            print(f"[EA] Auto-discovered EA on {res} "
                  f"(configured {preferred} did not respond).")
            return res
    return preferred


class EASupply:
    """
    SCPI driver for EA PSI / PSB series power supplies.

    Parameters
    ----------
    visa_resource : str
        pyvisa resource string, e.g. "USB0::0x2184::0x0041::XXXXX::INSTR"
    voltage_limit : float
        Hard ceiling – set_voltage() clamps to this value (default 60 V).
    current_limit : float
        Current limit sent to the supply at open() (default 5 A).
    """

    def __init__(self,
                 visa_resource: str,
                 voltage_limit: float = 60.0,
                 current_limit: float = 5.0,
                 backend: str = "",
                 baud_rate: int = 115200,
                 timeout_ms: int = 30000,
                 cmd_interval_ms: int = 50):
        if not _PYVISA_AVAILABLE:
            raise EASupplyNotAvailable(
                "pyvisa is not installed. Run: pip install pyvisa pyvisa-py")
        self._resource_str   = visa_resource
        self._voltage_limit  = voltage_limit
        self._current_limit  = current_limit
        self._backend        = backend          # e.g. "@py" for pyvisa-py
        self._baud_rate      = baud_rate
        self._timeout_ms     = int(timeout_ms)
        self._inst           = None
        self._rm             = None
        self._lock           = threading.Lock()
        self._output_enabled = False
        # Last commanded voltage setpoint (V). Tracked so a reconnect can
        # RE-ASSERT it — the EA-PS SCPI wedge previously left the bus
        # pinned at the old voltage because _reconnect() never re-sent
        # VOLT, so the sweep produced garbage (setpoint never applied).
        self._last_voltage   = 0.0
        # Minimum spacing between SCPI commands (s). The EA-PS 9500-20
        # SCPI parser overruns under TC-HV-01's rapid set_voltage +
        # MEAS:VOLT? bursts; pacing the traffic prevents the wedge.
        self._cmd_interval_s = max(0.0, cmd_interval_ms / 1000.0)
        self._last_cmd_t     = 0.0

    # ── connection ────────────────────────────────────────────────────────────

    def open(self) -> "EASupply":
        # Open the CONFIGURED port directly first (the common case). Only
        # if that fails do we scan other COM ports for the EA. This avoids
        # the redundant open/close churn of an unconditional discovery
        # probe — on the fragile USB-CDC stack, extra open/close cycles can
        # themselves trip the SCPI wedge.
        rm = pyvisa.ResourceManager(self._backend) if self._backend \
             else pyvisa.ResourceManager()
        self._rm = rm
        try:
            self._inst = rm.open_resource(self._resource_str)
        except Exception:
            # Configured port didn't open — it may have re-enumerated onto
            # a different COM number. Scan for it (skips the just-failed
            # port's probe internally) and retry once.
            resolved = discover_ea_resource(
                self._resource_str, self._backend, self._baud_rate)
            if resolved != self._resource_str:
                print(f"[EA] Using {resolved} (was {self._resource_str}).")
                self._resource_str = resolved
            self._inst = rm.open_resource(self._resource_str)
        # Use the configured timeout (default 30 s). Some EA-PS units
        # park their SCPI parser for several seconds during fast V/I
        # transitions; the previous 3-second value surfaced as spurious
        # VI_ERROR_TMO mid-test. _configure_session() also applies the
        # transport-specific I/O settings (serial baud / socket
        # terminations).
        _configure_session(self._inst, self._resource_str,
                            self._baud_rate, self._timeout_ms)
        # Identify
        idn = self._query("*IDN?")
        print(f"[EA] Connected: {idn.strip()}")
        # Take remote control (required by EA-PS series before SET commands
        # are accepted; otherwise SYST:ERR? returns "-221 Settings conflict").
        try:
            self._write("SYST:LOCK ON")
        except Exception:
            pass
        # Set safety limits. NOTE (2026-05-22): we deliberately do NOT
        # issue OUTP OFF here any more. open() can be called with the
        # bus capacitor still charged from a prior crashed session, and
        # toggling OUTP under load wedges the EA-PS 9500-20 SCPI parser.
        # Instead we force the setpoint to 0 V — if OUTP is currently
        # ON, the bidirectional EA will actively sink the bus charge
        # down to 0; if OUTP is OFF, the setpoint takes effect on the
        # next ea.enable() call. Tests that need HV explicitly call
        # ea.enable() when ready.
        self._write(f"CURR {self._current_limit:.3f}")
        self._write(f"VOLT 0.000")
        self._last_voltage = 0.0
        # Output state reflects whatever the EA was in before open();
        # we'll re-affirm via enable()/disable() as the test demands.
        return self

    def close(self):
        """Close the VISA session.

        IMPORTANT (2026-05-22): we deliberately do NOT issue OUTP OFF
        here any more. Toggling OUTP while the inverter's DC-link cap
        is still charged was identified as the primary cause of the
        EA-PS 9500-20 SCPI parser wedge — the in-rush reverse current
        when the contactor opens locks up the front-end MCU. Callers
        that need to disable the output cleanly should:
            ea.set_voltage(0); wait for bus to discharge; ea.disable()
        (see _maybe_shutdown_ea in conftest.py). close() now ONLY
        releases remote lock + closes the VISA serial session."""
        try:
            self._write("SYST:LOCK OFF")    # release remote control
        except Exception:
            pass
        if self._inst:
            try:
                self._inst.close()
            except Exception:
                pass
        if self._rm:
            try:
                self._rm.close()
            except Exception:
                pass
        self._inst = None
        self._rm   = None
        # Leave self._output_enabled alone — reflects last set state.

    def __enter__(self) -> "EASupply":
        return self.open()

    def __exit__(self, *_):
        self.close()

    # ── control ───────────────────────────────────────────────────────────────

    def set_voltage(self, volts: float) -> float:
        """Set output voltage.  Clamps to voltage_limit.  Returns actual setpoint."""
        v = min(float(volts), self._voltage_limit)
        if v < 0:
            v = 0.0
        with self._lock:
            self._last_voltage = v          # remember BEFORE the write so a
            self._write(f"VOLT {v:.3f}")    # reconnect mid-write re-asserts it
        return v

    def set_current_limit(self, amps: float):
        with self._lock:
            self._write(f"CURR {amps:.3f}")

    def enable(self):
        with self._lock:
            self._write("OUTP ON")
            self._output_enabled = True

    def disable(self):
        with self._lock:
            self._write("OUTP OFF")
            self._output_enabled = False

    def ramp_to(self, target_v: float, step_v: float = 5.0, dwell_s: float = 1.0):
        """Ramp voltage from current setpoint to *target_v* in *step_v* steps."""
        current_v = self.measure_voltage()
        if current_v is None:
            current_v = 0.0
        target_v = min(target_v, self._voltage_limit)

        if target_v >= current_v:
            v = current_v
            while v < target_v - 0.5:
                v = min(v + step_v, target_v)
                self.set_voltage(v)
                time.sleep(dwell_s)
        else:
            v = current_v
            while v > target_v + 0.5:
                v = max(v - step_v, target_v)
                self.set_voltage(v)
                time.sleep(dwell_s)
        self.set_voltage(target_v)

    # ── measurements ──────────────────────────────────────────────────────────

    @staticmethod
    def _parse_float_with_unit(resp: str) -> Optional[float]:
        """EA-PS replies include the unit, e.g. '12.345 V', '0.000 A'.
        Strip everything after the first space and parse the leading number."""
        try:
            token = resp.strip().split()[0]
            return float(token)
        except (ValueError, IndexError, AttributeError):
            return None

    def measure_voltage(self) -> Optional[float]:
        """Query actual output voltage (V)."""
        try:
            with self._lock:
                resp = self._query("MEAS:VOLT?")
            return self._parse_float_with_unit(resp)
        except Exception:
            return None

    def measure_current(self) -> Optional[float]:
        """Query actual output current (A)."""
        try:
            with self._lock:
                resp = self._query("MEAS:CURR?")
            return self._parse_float_with_unit(resp)
        except Exception:
            return None

    @property
    def is_enabled(self) -> bool:
        return self._output_enabled

    # ── internal ──────────────────────────────────────────────────────────────

    def _reconnect(self):
        """Tear down and re-open the VISA session. Used when a SCPI
        command times out (the EA-PS SCPI parser has been observed to
        wedge after sustained traffic; the only reliable recovery is to
        close the serial session, wait, and re-open). Re-applies the
        standard bench configuration on the new session."""
        if not _PYVISA_AVAILABLE:
            return
        print("[EA] SCPI timeout — attempting reconnect...")
        try:
            if self._inst is not None:
                try:
                    self._inst.close()
                except Exception:
                    pass
            self._inst = None
            if self._rm is not None:
                try:
                    self._rm.close()
                except Exception:
                    pass
            self._rm = None
        except Exception:
            pass
        time.sleep(0.5)
        try:
            rm = pyvisa.ResourceManager(self._backend) if self._backend \
                 else pyvisa.ResourceManager()
            self._rm = rm
            self._inst = rm.open_resource(self._resource_str)
            _configure_session(self._inst, self._resource_str,
                               self._baud_rate, self._timeout_ms)
            try: self._inst.write("SYST:LOCK ON")
            except Exception: pass
            self._inst.write(f"CURR {self._current_limit:.3f}")
            # CRITICAL: re-assert the last commanded setpoint + output
            # state. Without this the bus stayed pinned at the previous
            # voltage after a mid-sweep wedge (TC-HV-01 reported the same
            # ~150 V at every setpoint => garbage sweep). Re-issuing VOLT
            # makes the new session honour the value the test asked for.
            try:
                self._inst.write(f"VOLT {self._last_voltage:.3f}")
                if self._output_enabled:
                    self._inst.write("OUTP ON")
            except Exception:
                pass
            print(f"[EA] Reconnect OK (re-asserted "
                  f"VOLT={self._last_voltage:.1f} "
                  f"OUTP={'ON' if self._output_enabled else 'OFF'})")
        except Exception as e:
            print(f"[EA] Reconnect FAILED: {e}")

    def _pace(self):
        """Throttle SCPI traffic to >= self._cmd_interval_s between
        commands. The EA-PS 9500-20 SCPI parser wedges under back-to-back
        bursts (TC-HV-01 set_voltage + MEAS:VOLT? at every sweep step);
        spacing the commands keeps the parser from overrunning."""
        if self._cmd_interval_s <= 0:
            return
        dt = time.monotonic() - self._last_cmd_t
        if dt < self._cmd_interval_s:
            time.sleep(self._cmd_interval_s - dt)

    def _write(self, cmd: str):
        if self._inst is None:
            raise EASupplyNotAvailable("Supply not open")
        self._pace()
        try:
            self._inst.write(cmd)
        except pyvisa.errors.VisaIOError:
            # SCPI parser likely wedged; reconnect and retry ONCE.
            self._reconnect()
            if self._inst is None:
                raise
            self._inst.write(cmd)
        finally:
            self._last_cmd_t = time.monotonic()

    def _query(self, cmd: str) -> str:
        if self._inst is None:
            raise EASupplyNotAvailable("Supply not open")
        self._pace()
        try:
            return self._inst.query(cmd)
        except pyvisa.errors.VisaIOError:
            self._reconnect()
            if self._inst is None:
                raise
            return self._inst.query(cmd)
        finally:
            self._last_cmd_t = time.monotonic()


# ─────────────────────────────────────────────────────────────────────────────
# Dummy supply (used when EA_VISA_RESOURCE is None)
# ─────────────────────────────────────────────────────────────────────────────

class DummyEASupply:
    """No-op supply used when pyvisa or the EA resource is not available.
    All HV tests that require this supply will be skipped."""

    def __init__(self, *_, **__):
        self._v = 0.0
        self._enabled = False

    def open(self):  return self
    def close(self): pass
    def __enter__(self): return self.open()
    def __exit__(self, *_): self.close()

    def set_voltage(self, v): self._v = v; return v
    def set_current_limit(self, _): pass
    def enable(self):  self._enabled = True
    def disable(self): self._enabled = False
    def ramp_to(self, *_, **__): pass
    def measure_voltage(self): return self._v if self._enabled else 0.0
    def measure_current(self): return 0.0

    @property
    def is_enabled(self): return self._enabled


def make_supply(visa_resource: Optional[str],
                voltage_limit: float = 60.0,
                current_limit: float = 5.0,
                backend: str = "",
                baud_rate: int = 115200,
                timeout_ms: int = 30000,
                cmd_interval_ms: int = 50):
    """Factory: return a real EASupply if visa_resource is set, else DummyEASupply."""
    if visa_resource:
        return EASupply(visa_resource, voltage_limit, current_limit,
                         backend=backend, baud_rate=baud_rate,
                         timeout_ms=timeout_ms,
                         cmd_interval_ms=cmd_interval_ms)
    return DummyEASupply()
