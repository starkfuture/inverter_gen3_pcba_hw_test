"""
scope_rs.py  –  Rohde & Schwarz oscilloscope driver over USB (USBTMC).

Primary target: ROHDE & SCHWARZ RTM3004 (RTM3000 family). The same
HMx-derived SCPI command set also covers RTB2000 and RTA4000. (The newer
MXO4/MXO5 family uses a slightly different measurement-result query — see
the fallback list in _read_measurement().)

RTM3004 specifics handled here:
  • up to 8 parallel automatic measurements (MEASurement1..8) — this driver
    sets up the 7 gate parameters as on-screen measurement slots so the
    operator can also read them live on the scope during the manual probe
    moves;
  • MEASurement<m>:RESult:ACTual? for the numeric read-back;
  • PROBe<m>:SETup:ATTenuation:MANual for a passive 10:1 probe;
  • CHANnel<m>:SCALe / :OFFSet / :COUPling for the vertical setup.

Backend: pyvisa with the pure-Python pyvisa-py USBTMC layer, so no NI-VISA
or R&S-VISA installation is required.  Install once with:

    pip install pyvisa pyvisa-py pyusb

If a vendor VISA (R&S or NI) is installed, pass backend="@ivi" to use it.

Typical use
───────────
    from scope_rs import RohdeScope
    scope = RohdeScope().open()          # auto-discovers the R&S USB device
    print(scope.idn())
    scope.configure_channel(1, v_div=4.0, offset=7.5, probe_atten=10)
    scope.configure_timebase(20e-6)      # 20 µs/div
    scope.configure_trigger(1, level=5.0, slope="POSitive")
    m = scope.measure(1)                 # dict of the 7 parameters
    scope.close()

A SIMULATE mode (scope=RohdeScope(simulate=True)) returns canned readings
so the runner and report code can be exercised without hardware.
"""

import time
import random
from typing import Optional, Dict

try:
    import pyvisa
except ImportError:                       # pragma: no cover
    pyvisa = None

# Rohde & Schwarz USB vendor ID (used for auto-discovery)
RS_USB_VENDOR_ID = "0x0AAD"

# Measurement-type SCPI keywords for the RTB / RTM / RTA family.
# Each maps a friendly result key to the MEASurement:MAIN argument.
MEAS_TYPES = {
    "frequency": "FREQuency",
    "duty":      "PDCYcle",     # positive duty cycle (%)
    "rise_time": "RTIMe",
    "fall_time": "FTIMe",
    "v_high":    "HIGH",        # high-level voltage (top)
    "v_low":     "LOW",         # low-level voltage (base)
    "v_pp":      "PEAK",        # peak-to-peak
}


class RohdeScope:
    def __init__(self,
                 resource: Optional[str] = None,
                 backend:  str = "@py",
                 timeout_ms: int = 10000,
                 simulate: bool = False):
        self._resource   = resource
        self._backend    = backend
        self._timeout_ms = timeout_ms
        self._simulate   = simulate
        self._rm   = None
        self._inst = None
        self._idn  = "SIMULATED R&S RTM3004" if simulate else None
        self._meas_slots = {}   # key -> MEASurement slot number (set by setup)
        self._active_ch  = None
        self._last_t_div = None # last timebase set (for edge-zoom restore)
        self._trig_ch    = None
        self._trig_level = None

    # ── connection ────────────────────────────────────────────────────────
    def open(self) -> "RohdeScope":
        if self._simulate:
            return self
        if pyvisa is None:
            raise RuntimeError(
                "pyvisa not installed. Run:  pip install pyvisa pyvisa-py pyusb")
        self._rm = pyvisa.ResourceManager(self._backend)

        resource = self._resource or self._auto_discover()
        if resource is None:
            raise RuntimeError(
                "No R&S USB instrument found. Plug in the scope, or pass an "
                "explicit resource string (e.g. "
                "'USB0::0x0AAD::0x01D6::123456::INSTR').")

        self._inst = self._rm.open_resource(resource)
        self._inst.timeout = self._timeout_ms
        # Most R&S USBTMC instruments use line-feed termination.
        self._inst.read_termination  = "\n"
        self._inst.write_termination = "\n"
        self._idn = self._inst.query("*IDN?").strip()
        return self

    def _auto_discover(self) -> Optional[str]:
        for res in self._rm.list_resources():
            # USB resources look like USB0::0x0AAD::0x01D6::serial::INSTR
            if "USB" in res and RS_USB_VENDOR_ID.lower() in res.lower():
                return res
        # Fall back to the first USB instrument if exactly one is present
        usb = [r for r in self._rm.list_resources() if "USB" in r]
        return usb[0] if len(usb) == 1 else None

    def close(self):
        if self._inst is not None:
            try:
                self._inst.close()
            finally:
                self._inst = None
        if self._rm is not None:
            try:
                self._rm.close()
            finally:
                self._rm = None

    def __enter__(self): return self.open()
    def __exit__(self, *_): self.close()

    # ── low-level helpers ──────────────────────────────────────────────────
    def _w(self, cmd: str):
        if self._simulate:
            return
        self._inst.write(cmd)

    def _q(self, cmd: str) -> str:
        if self._simulate:
            return "0"
        return self._inst.query(cmd).strip()

    def _try_w(self, cmd: str):
        """Write a command, swallowing instrument errors (model-specific
        commands that may not exist on every family)."""
        try:
            self._w(cmd)
        except Exception:
            pass

    def idn(self) -> str:
        return self._idn or "(unknown)"

    # ── configuration ──────────────────────────────────────────────────────
    def reset(self):
        self._try_w("*RST")
        self._try_w("*CLS")
        time.sleep(0.5)

    def configure_channel(self, ch: int,
                          v_div: float,
                          offset: float = 0.0,
                          probe_atten: float = 10.0,
                          coupling: str = "DCLimit"):
        """Set up a vertical channel.

        v_div       : vertical scale, volts per division (real volts; the
                      probe attenuation is applied separately so values are
                      in actual gate-pin volts).
        offset      : voltage at the vertical centre (R&S CHAN:OFFSet).
        probe_atten : probe attenuation factor (10 for a standard 10:1 probe).
        coupling    : 'DCLimit' (DC, 1 MΩ) | 'ACLimit' | 'GND'.
        """
        self._w(f"CHANnel{ch}:STATe ON")
        # Probe attenuation — command differs slightly by model; try the
        # common forms.
        self._try_w(f"PROBe{ch}:SETup:ATTenuation:MANual {probe_atten}")
        self._try_w(f"PROBe{ch}:SETup:GAIN:MANual {1.0/probe_atten}")
        self._w(f"CHANnel{ch}:SCALe {v_div}")
        self._w(f"CHANnel{ch}:OFFSet {offset}")
        self._try_w(f"CHANnel{ch}:COUPling {coupling}")

    def configure_timebase(self, t_div: float):
        """Horizontal scale, seconds per division."""
        self._w(f"TIMebase:SCALe {t_div}")
        self._last_t_div = t_div

    def configure_trigger(self, ch: int, level: float,
                          slope: str = "POSitive"):
        self._try_w("TRIGger:A:MODE AUTO")
        self._try_w("TRIGger:A:TYPE EDGE")
        self._w(f"TRIGger:A:SOURce CH{ch}")
        self._try_w(f"TRIGger:A:EDGE:SLOPe {slope}")
        self._w(f"TRIGger:A:LEVel{ch} {level}")
        self._trig_ch    = ch
        self._trig_level = level

    def autoset(self):
        self._try_w("AUToscale")
        time.sleep(2.0)

    # ── parallel measurement slots (RTM3000: MEASurement1..8) ──────────────
    def setup_measurements(self, ch: int):
        """Configure the 7 gate parameters as parallel on-screen measurement
        slots (MEASurement1..7) on the RTM3004 so they update live and can
        be read back individually. Called once by full_setup()."""
        self._meas_slots = {}
        for slot, (key, scpi_type) in enumerate(MEAS_TYPES.items(), start=1):
            self._try_w(f"MEASurement{slot}:SOURce CH{ch}")
            self._try_w(f"MEASurement{slot}:MAIN {scpi_type}")
            self._try_w(f"MEASurement{slot}:ENABle ON")
            self._meas_slots[key] = slot
        time.sleep(0.3)

    def full_setup(self, ch: int,
                   v_div: float = 4.0,
                   offset: float = 7.5,
                   probe_atten: float = 10.0,
                   t_div: float = 20e-6,
                   trig_level: float = 5.0,
                   coupling: str = "DCLimit"):
        """One-shot complete pre-configuration of the RTM3004 before any
        measurement: reset, vertical channel, timebase, edge trigger and the
        7 parallel measurement slots. Defaults suit a +18/-3 V gate signal
        through a 10:1 probe."""
        self.reset()
        self.configure_channel(ch, v_div=v_div, offset=offset,
                               probe_atten=probe_atten, coupling=coupling)
        self.configure_timebase(t_div)
        self.configure_trigger(ch, level=trig_level)
        self.setup_measurements(ch)
        self._active_ch = ch

    # ── measurement ─────────────────────────────────────────────────────────
    def _read_measurement(self, slot: int = 1) -> float:
        """Query a measurement slot's actual result. Tries the RTB/RTM/RTA
        form first, then the older HMO form, then the MXO form."""
        for q in (f"MEASurement{slot}:RESult:ACTual?",
                  f"MEASurement{slot}:RESult?",
                  f"MEASurement{slot}:RESult:CURRent?"):
            try:
                val = float(self._q(q))
            except Exception:
                continue
            # R&S returns ~9.91e37 (and similar huge magnitudes) when a
            # measurement result is not available — treat as NaN.
            if abs(val) >= 1e30:
                return float("nan")
            return val
        return float("nan")

    def measure(self, ch: int, settle_s: float = 0.4,
                edge_t_div: float = None) -> Dict[str, float]:
        """
        Measure the 7 gate-signal parameters on *ch*.

        Returns a dict: frequency [Hz], duty [%], rise_time [s], fall_time [s],
                        v_high [V], v_low [V], v_pp [V].

        edge_t_div : if given, rise_time and fall_time are re-measured at this
                     (fast) horizontal scale so the edges span several
                     divisions — essential for accurate edge timing, since at
                     a wide PWM-period timebase the rise/fall reading collapses
                     to the sample-interval floor. The coarse timebase (used
                     for frequency/duty/levels) is restored afterwards.
        """
        if self._simulate:
            jit = lambda x, p: x * (1 + random.uniform(-p, p))
            return {
                "frequency": jit(16000.0, 0.002),
                "duty":      jit(50.0,    0.01),
                "rise_time": jit(45e-9,   0.05),
                "fall_time": jit(40e-9,   0.05),
                "v_high":    jit(18.0,    0.02),
                "v_low":     jit(-3.0,    0.05),
                "v_pp":      jit(21.0,    0.02),
            }

        results: Dict[str, float] = {}

        def _read_all():
            if self._meas_slots:
                out = {}
                for key, slot in self._meas_slots.items():
                    out[key] = self._read_measurement(slot)
                return out
            # Fallback: single-slot reconfigure per parameter
            out = {}
            for key, scpi_type in MEAS_TYPES.items():
                self._w(f"MEASurement1:SOURce CH{ch}")
                self._w(f"MEASurement1:MAIN {scpi_type}")
                self._try_w("MEASurement1:ENABle ON")
                time.sleep(settle_s)
                out[key] = self._read_measurement(1)
            return out

        # ── Pass 1: coarse timebase — frequency, duty, levels (and a first
        #            rise/fall that we may overwrite below).
        time.sleep(settle_s)
        results = _read_all()

        # ── Pass 2 (optional): fast timebase — accurate rise/fall.
        # At a fast timebase only the triggered edge is on screen, so we make
        # two acquisitions: rising-edge trigger for rise_time, falling-edge
        # trigger for fall_time. The coarse timebase + rising-edge trigger are
        # restored afterwards.
        if edge_t_div:
            coarse = self._last_t_div
            rise_slot = self._meas_slots.get("rise_time")
            fall_slot = self._meas_slots.get("fall_time")
            try:
                self.configure_timebase(edge_t_div)

                # rise: trigger on the rising edge
                if self._trig_ch is not None:
                    self.configure_trigger(self._trig_ch, self._trig_level, "POSitive")
                time.sleep(settle_s)
                rt = (self._read_measurement(rise_slot) if rise_slot
                      else _read_all().get("rise_time", float("nan")))
                if rt == rt:                       # not NaN
                    results["rise_time"] = rt

                # fall: trigger on the falling edge
                if self._trig_ch is not None:
                    self.configure_trigger(self._trig_ch, self._trig_level, "NEGative")
                time.sleep(settle_s)
                ft = (self._read_measurement(fall_slot) if fall_slot
                      else _read_all().get("fall_time", float("nan")))
                if ft == ft:
                    results["fall_time"] = ft
            finally:
                # restore coarse timebase + rising-edge trigger for next setpoint
                if self._trig_ch is not None:
                    self.configure_trigger(self._trig_ch, self._trig_level, "POSitive")
                if coarse is not None:
                    self.configure_timebase(coarse)
        return results

    def screenshot(self, path: str) -> bool:
        """Grab a PNG screenshot to *path*. Best-effort; returns success."""
        if self._simulate:
            return False
        try:
            self._w("HCOPy:LANGuage PNG")
            self._w("HCOPy:DATA?")
            raw = self._inst.read_raw()
            # Strip the IEEE-488.2 definite-length block header (#<n><len>)
            if raw[:1] == b"#":
                ndig = int(raw[1:2])
                data = raw[2 + ndig:]
            else:
                data = raw
            with open(path, "wb") as f:
                f.write(data)
            return True
        except Exception:
            return False
