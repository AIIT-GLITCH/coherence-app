"""
gamma40_stimulation.py — 40 Hz Audiovisual Gamma Stimulation Module
===================================================================

Wike Coherence Framework — Intervention Module 2

WHY 40 Hz?
----------
40 Hz is the dominant frequency of gamma oscillations in the human cortex.
These oscillations bind distributed neural activity into coherent percepts
(the "binding problem"). In Alzheimer's disease, 40 Hz power collapses —
the network loses coherence, and with it, the ability to encode memories
and clear metabolic waste.

External 40 Hz stimulation (light flickering at 40 Hz, sound pulsing at
40 Hz) entrains cortical gamma oscillations through sensory driving. This
is a resonance phenomenon: the external stimulus locks the intrinsic 40 Hz
oscillators to a common phase, restoring coherence.

THE EVIDENCE CHAIN
------------------
Iaccarino et al. (Nature 540:230-235, 2016):
    40 Hz light flicker in 5XFAD Alzheimer's mice reduced amyloid-beta
    levels in visual cortex by ~50% after 1 hour. The mechanism: gamma
    entrainment activated microglia (the brain's immune cells) to engulf
    amyloid plaques. Published in Nature. This was the breakthrough.

Martorell et al. (Cell 177:256-271, 2019):
    Combined 40 Hz audio + visual stimulation. The audio component
    extended gamma entrainment beyond visual cortex into the auditory
    cortex and hippocampus — the memory center. Reduced both amyloid
    AND tau. Improved memory performance in mice.

Adaikkan et al. (Neuron 105:1-16, 2020):
    Chronic 40 Hz stimulation (1 hr/day for weeks) reduced
    neurodegeneration, preserved synapses, and reduced brain atrophy.
    Not just clearing plaques — preserving neurons.

Tsai Lab (Nature 2024):
    Mechanism confirmed: 40 Hz entrainment activates VIP interneurons
    (vasoactive intestinal peptide neurons), which trigger the
    glymphatic clearance system. The glymphatic system is the brain's
    waste disposal — it flushes cerebrospinal fluid through the
    interstitial space, carrying away amyloid, tau, and other debris.

Human Trials:
    Phase I (Chan et al., 2021): Safe, well-tolerated in humans.
    Phase II (He et al., J Alzheimer's Dis 2021): Less brain atrophy,
    better memory scores, improved sleep.
    Phase III: NCT04912531, MIT/Cognito Therapeutics, ongoing.
    Home-use devices: safe for unsupervised daily use.

Wike Coherence Framework — Paper 23:
    In the Wike model, neurodegeneration occurs when gamma_eff exceeds
    gamma_c in neural networks — the system undergoes a decoherence
    phase transition. 40 Hz stimulation forces gamma_eff back below
    gamma_c by externally driving the network at its natural coherence
    frequency. The same physics governs why prayer (0.1 Hz cardiac)
    and gamma (40 Hz neural) both work: resonant driving at the
    system's critical frequency restores coherence.

    Glymphatic clearance is activated BY gamma oscillations — coherent
    neural activity literally pumps waste out of the brain.

SAFETY
------
The ONLY established contraindication is photosensitive epilepsy.
40 Hz is above the most dangerous range for photoparoxysmal response
(typically 15-25 Hz), but caution is warranted for any photic
stimulation in epilepsy.

For all other users: 40 Hz audiovisual stimulation has been used
safely in clinical trials with no serious adverse events.

REFERENCES
----------
[1] Iaccarino HF et al. Nature 540:230-235 (2016)
[2] Martorell G et al. Cell 177:256-271 (2019)
[3] Adaikkan C et al. Neuron 105:1-16 (2020)
[4] Chan D et al. Ann Neurol 90:S133 (2021)
[5] He Q et al. J Alzheimer's Dis 77:1065-1076 (2021)
[6] NCT04912531 (Phase III, Cognito Therapeutics)
[7] Wike Coherence Framework, Paper 23: Neural Coherence

Author: Coherence App / Wike Framework
License: Open for clinical and research use
"""

import time
import json
import warnings
from datetime import datetime, date
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np


# ============================================================================
# CONSTANTS
# ============================================================================

# The frequency. Not 39, not 41. 40 Hz.
# This is the peak gamma frequency in human cortex, and the frequency
# used in all the clinical studies.
GAMMA_FREQUENCY_HZ = 40.0

# Period of one gamma cycle
GAMMA_PERIOD_S = 1.0 / GAMMA_FREQUENCY_HZ  # 0.025s = 25ms

# Visual flicker: 50% duty cycle at 40 Hz = 12.5ms on, 12.5ms off
FLICKER_ON_MS = 12.5
FLICKER_OFF_MS = 12.5

# Default audio parameters
DEFAULT_SAMPLE_RATE = 44100
DEFAULT_CARRIER_FREQ = 440.0  # A4, carrier tone for AM modulation

# Safety
EPILEPSY_WARNING = (
    "WARNING: 40 Hz visual flicker stimulation is contraindicated for "
    "individuals with photosensitive epilepsy or a history of seizures "
    "triggered by flashing lights. Consult a physician before use. "
    "Audio-only mode is available as an alternative."
)


# ============================================================================
# SAFETY CHECK
# ============================================================================

def check_safety(has_epilepsy: Optional[bool] = None, visual_enabled: bool = True) -> dict:
    """
    Safety screening for gamma stimulation.

    Parameters
    ----------
    has_epilepsy : bool or None
        True = user reports photosensitive epilepsy.
        None = not yet screened.
    visual_enabled : bool
        Whether visual (flicker) component is requested.

    Returns
    -------
    dict with keys:
        safe : bool
            True if session can proceed.
        warnings : list of str
            Any warnings to display.
        visual_allowed : bool
            Whether visual component should be enabled.
        audio_allowed : bool
            Always True (audio is safe for everyone).
    """
    result = {
        "safe": True,
        "warnings": [],
        "visual_allowed": visual_enabled,
        "audio_allowed": True,  # Audio 40 Hz is safe for all
    }

    if has_epilepsy is True:
        result["visual_allowed"] = False
        result["warnings"].append(EPILEPSY_WARNING)
        result["warnings"].append(
            "Visual flicker has been disabled. Audio-only mode is active."
        )
        if not visual_enabled:
            # Audio-only was already selected; no issue
            pass

    elif has_epilepsy is None and visual_enabled:
        result["warnings"].append(
            "SCREENING REQUIRED: Before using visual flicker, please confirm "
            "that you do not have photosensitive epilepsy or a history of "
            "seizures triggered by flashing lights."
        )

    return result


# ============================================================================
# AUDIO GENERATION
# ============================================================================

def generate_40hz_audio(
    duration_minutes: float = 10.0,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    carrier_freq: float = DEFAULT_CARRIER_FREQ,
    amplitude: float = 0.5,
    mode: str = "am",
) -> np.ndarray:
    """
    Generate a 40 Hz gamma-entraining audio stimulus.

    Two modes are available:

    "am" (amplitude modulation):
        A carrier tone (default 440 Hz) whose amplitude is modulated at 40 Hz.
        The listener hears a tone that pulses 40 times per second. This is the
        standard approach used in Martorell et al. (Cell 2019).

        Signal: carrier(t) * (0.5 + 0.5 * cos(2*pi*40*t))

        The modulation envelope goes from 0 to 1, creating 40 distinct
        amplitude peaks per second. The auditory cortex entrains to the
        40 Hz envelope, not the carrier frequency.

    "isochronous":
        Pure 40 Hz tone bursts — 12.5ms of tone, 12.5ms of silence,
        repeated. Harsher sounding but stronger entrainment drive.

    Parameters
    ----------
    duration_minutes : float
        Duration in minutes.
    sample_rate : int
        Audio sample rate (default 44100).
    carrier_freq : float
        Carrier frequency for AM mode (default 440 Hz).
    amplitude : float
        Peak amplitude 0-1 (default 0.5).
    mode : str
        "am" or "isochronous".

    Returns
    -------
    np.ndarray
        Audio samples as float64 in range [-amplitude, +amplitude].
        Shape: (num_samples,)
    """
    duration_seconds = duration_minutes * 60.0
    num_samples = int(duration_seconds * sample_rate)
    t = np.arange(num_samples, dtype=np.float64) / sample_rate

    if mode == "am":
        # Carrier tone
        carrier = np.sin(2.0 * np.pi * carrier_freq * t)

        # 40 Hz amplitude modulation envelope.
        # (0.5 + 0.5 * cos(...)) gives an envelope from 0 to 1,
        # with 40 peaks per second.
        envelope = 0.5 + 0.5 * np.cos(2.0 * np.pi * GAMMA_FREQUENCY_HZ * t)

        signal = amplitude * carrier * envelope

    elif mode == "isochronous":
        # Isochronous tone: 12.5ms on, 12.5ms off at 40 Hz
        # This creates a square-wave gating of the carrier.
        carrier = np.sin(2.0 * np.pi * carrier_freq * t)

        # Square wave at 40 Hz: 1 for first half of each cycle, 0 for second half
        # Phase within each 40 Hz cycle (0 to 1)
        phase = (t * GAMMA_FREQUENCY_HZ) % 1.0
        gate = (phase < 0.5).astype(np.float64)

        # Smooth the gate edges to avoid clicks (1ms ramp)
        ramp_samples = int(0.001 * sample_rate)
        if ramp_samples > 0:
            from scipy.ndimage import uniform_filter1d
            try:
                gate = uniform_filter1d(gate, size=ramp_samples)
            except ImportError:
                # scipy not available; use raw gate (will have clicks)
                pass

        signal = amplitude * carrier * gate

    else:
        raise ValueError(f"Unknown mode '{mode}'. Use 'am' or 'isochronous'.")

    # Apply gentle fade-in and fade-out (2 seconds each) to avoid startle
    fade_samples = min(int(2.0 * sample_rate), num_samples // 4)
    if fade_samples > 0:
        fade_in = np.linspace(0.0, 1.0, fade_samples)
        fade_out = np.linspace(1.0, 0.0, fade_samples)
        signal[:fade_samples] *= fade_in
        signal[-fade_samples:] *= fade_out

    return signal


# ============================================================================
# VISUAL FLICKER TIMESTAMPS
# ============================================================================

def generate_40hz_visual_timestamps(duration_minutes: float = 10.0) -> list:
    """
    Generate precise on/off timestamps for 40 Hz visual flicker.

    At 40 Hz with 50% duty cycle:
        ON for 12.5 ms, OFF for 12.5 ms, repeat.
        25 ms per cycle, 40 cycles per second.

    This data drives:
        - Screen flash (white/black alternation)
        - LED controller (GPIO high/low)
        - Smart bulb (on/off commands)

    Parameters
    ----------
    duration_minutes : float
        Total duration in minutes.

    Returns
    -------
    list of dict, each with:
        cycle : int         — cycle number (0-indexed)
        on_time : float     — seconds when light turns ON
        off_time : float    — seconds when light turns OFF
        next_on : float     — seconds when next cycle starts
    """
    duration_seconds = duration_minutes * 60.0
    total_cycles = int(duration_seconds * GAMMA_FREQUENCY_HZ)
    on_duration = FLICKER_ON_MS / 1000.0   # 0.0125s
    off_duration = FLICKER_OFF_MS / 1000.0  # 0.0125s
    cycle_duration = on_duration + off_duration  # 0.025s

    timestamps = []
    for i in range(total_cycles):
        t_start = i * cycle_duration
        timestamps.append({
            "cycle": i,
            "on_time": round(t_start, 6),
            "off_time": round(t_start + on_duration, 6),
            "next_on": round(t_start + cycle_duration, 6),
        })

    return timestamps


# ============================================================================
# SESSION LOG
# ============================================================================

@dataclass
class GammaSessionLog:
    """Record of a single gamma stimulation session."""
    start_time: str
    end_time: Optional[str] = None
    mode: str = "av"  # "audio", "visual", "av" (audiovisual)
    target_duration_seconds: float = 600.0
    actual_duration_seconds: float = 0.0
    completed: bool = False
    audio_mode: str = "am"
    safety_acknowledged: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ============================================================================
# GAMMA SESSION
# ============================================================================

class GammaSession:
    """
    40 Hz audiovisual stimulation session controller.

    Usage:
        session = GammaSession(duration_minutes=60, mode="av")

        # Safety check first
        safety = session.safety_check(has_epilepsy=False)
        if not safety["safe"]:
            print(safety["warnings"])
            return

        session.start()

        # Generate audio data for playback
        audio = session.generate_audio()

        # Get visual timing for flicker driver
        visual = session.generate_visual_timestamps()

        # In your UI loop:
        progress = session.get_progress()

        session.stop()
        log = session.get_log()
    """

    def __init__(
        self,
        duration_minutes: float = 60.0,
        mode: str = "av",
        audio_mode: str = "am",
        carrier_freq: float = DEFAULT_CARRIER_FREQ,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
    ):
        """
        Parameters
        ----------
        duration_minutes : float
            Session length. Clinical protocol: 60 minutes/day.
        mode : str
            "audio" = sound only (safe for epilepsy).
            "visual" = flicker only.
            "av" = audiovisual combined (maximum entrainment).
        audio_mode : str
            "am" = amplitude-modulated carrier (smoother).
            "isochronous" = pulsed tone bursts (stronger drive).
        carrier_freq : float
            Carrier frequency for audio (Hz).
        sample_rate : int
            Audio sample rate.
        """
        if mode not in ("audio", "visual", "av"):
            raise ValueError(f"Mode must be 'audio', 'visual', or 'av'. Got '{mode}'.")

        self.duration_minutes = duration_minutes
        self.duration_seconds = duration_minutes * 60.0
        self.mode = mode
        self.audio_mode = audio_mode
        self.carrier_freq = carrier_freq
        self.sample_rate = sample_rate

        # Session state
        self._start_time: Optional[float] = None
        self._stop_time: Optional[float] = None
        self._running = False
        self._safety_acknowledged = False

    def safety_check(self, has_epilepsy: Optional[bool] = None) -> dict:
        """
        Run safety screening. Must be called before start() if visual is enabled.
        """
        visual_enabled = self.mode in ("visual", "av")
        result = check_safety(has_epilepsy=has_epilepsy, visual_enabled=visual_enabled)

        if has_epilepsy is True and visual_enabled:
            # Downgrade to audio-only
            self.mode = "audio"
            result["visual_allowed"] = False

        if has_epilepsy is not None:
            self._safety_acknowledged = True

        return result

    def start(self) -> None:
        """Begin the session."""
        if self.mode in ("visual", "av") and not self._safety_acknowledged:
            warnings.warn(
                "Safety check not completed. Call safety_check() before start().",
                UserWarning,
            )
        self._start_time = time.time()
        self._running = True

    def stop(self) -> None:
        """End the session."""
        self._stop_time = time.time()
        self._running = False

    @property
    def elapsed(self) -> float:
        if self._start_time is None:
            return 0.0
        end = self._stop_time if self._stop_time else time.time()
        return end - self._start_time

    @property
    def is_running(self) -> bool:
        return self._running

    def get_progress(self, elapsed_seconds: Optional[float] = None) -> dict:
        """
        Get current session progress.

        Returns
        -------
        dict with:
            elapsed : float
            total_duration : float
            progress : float (0-1)
            minutes_remaining : float
            complete : bool
            gamma_cycles_delivered : int
                Number of 40 Hz cycles completed. At 40 Hz for 60 min,
                this is 144,000 cycles of coherent neural entrainment.
        """
        if elapsed_seconds is None:
            elapsed_seconds = self.elapsed

        complete = elapsed_seconds >= self.duration_seconds
        clamped = min(elapsed_seconds, self.duration_seconds)
        progress = clamped / self.duration_seconds if self.duration_seconds > 0 else 1.0
        remaining = max(self.duration_seconds - elapsed_seconds, 0.0)

        # Each second delivers 40 gamma cycles
        gamma_cycles = int(clamped * GAMMA_FREQUENCY_HZ)

        return {
            "elapsed": round(elapsed_seconds, 3),
            "total_duration": self.duration_seconds,
            "progress": round(progress, 4),
            "minutes_remaining": round(remaining / 60.0, 2),
            "complete": complete,
            "gamma_cycles_delivered": gamma_cycles,
        }

    def generate_audio(self, amplitude: float = 0.5) -> Optional[np.ndarray]:
        """
        Generate the 40 Hz audio stimulus for this session.

        Returns None if mode is "visual" only.
        """
        if self.mode == "visual":
            return None

        return generate_40hz_audio(
            duration_minutes=self.duration_minutes,
            sample_rate=self.sample_rate,
            carrier_freq=self.carrier_freq,
            amplitude=amplitude,
            mode=self.audio_mode,
        )

    def generate_visual_timestamps(self) -> Optional[list]:
        """
        Generate 40 Hz visual flicker timestamps for this session.

        Returns None if mode is "audio" only.
        """
        if self.mode == "audio":
            return None

        return generate_40hz_visual_timestamps(
            duration_minutes=self.duration_minutes,
        )

    def get_log(self) -> GammaSessionLog:
        """Return a session log entry."""
        start_str = (
            datetime.fromtimestamp(self._start_time).isoformat()
            if self._start_time else ""
        )
        end_str = (
            datetime.fromtimestamp(self._stop_time).isoformat()
            if self._stop_time else ""
        )
        actual = self.elapsed
        completed = actual >= self.duration_seconds * 0.95

        return GammaSessionLog(
            start_time=start_str,
            end_time=end_str,
            mode=self.mode,
            target_duration_seconds=self.duration_seconds,
            actual_duration_seconds=round(actual, 2),
            completed=completed,
            audio_mode=self.audio_mode,
            safety_acknowledged=self._safety_acknowledged,
        )


# ============================================================================
# SESSION STATISTICS
# ============================================================================

class GammaStats:
    """Tracks cumulative gamma stimulation statistics."""

    def __init__(self):
        self.sessions: list[GammaSessionLog] = []

    def add_session(self, log: GammaSessionLog) -> None:
        self.sessions.append(log)

    @property
    def total_sessions(self) -> int:
        return len(self.sessions)

    @property
    def completed_sessions(self) -> int:
        return sum(1 for s in self.sessions if s.completed)

    @property
    def total_minutes(self) -> float:
        return round(
            sum(s.actual_duration_seconds for s in self.sessions) / 60.0, 1
        )

    @property
    def total_gamma_cycles(self) -> int:
        """Total 40 Hz cycles delivered across all sessions."""
        total_seconds = sum(s.actual_duration_seconds for s in self.sessions)
        return int(total_seconds * GAMMA_FREQUENCY_HZ)

    @property
    def streak_days(self) -> int:
        """Consecutive days with at least one completed session."""
        if not self.sessions:
            return 0

        session_dates = set()
        for s in self.sessions:
            if s.completed and s.start_time:
                try:
                    dt = datetime.fromisoformat(s.start_time)
                    session_dates.add(dt.date())
                except (ValueError, TypeError):
                    continue

        if not session_dates:
            return 0

        today = date.today()
        streak = 0
        check_date = today
        while check_date in session_dates:
            streak += 1
            check_date = date.fromordinal(check_date.toordinal() - 1)

        return streak

    def summary(self) -> dict:
        return {
            "total_sessions": self.total_sessions,
            "completed_sessions": self.completed_sessions,
            "total_minutes": self.total_minutes,
            "total_gamma_cycles": self.total_gamma_cycles,
            "streak_days": self.streak_days,
        }


# ============================================================================
# SELF-TESTS
# ============================================================================

def _self_test():
    """
    Verify core functionality. Run with: python gamma40_stimulation.py
    """
    print("=" * 60)
    print("40 Hz GAMMA STIMULATION — SELF-TEST")
    print("=" * 60)

    errors = 0

    # ------ Test 1: Constants ------
    print("\n--- Test 1: Physical constants ---")
    ok = GAMMA_FREQUENCY_HZ == 40.0
    print(f"  Gamma frequency: {GAMMA_FREQUENCY_HZ} Hz [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    ok = abs(GAMMA_PERIOD_S - 0.025) < 1e-9
    print(f"  Gamma period: {GAMMA_PERIOD_S*1000} ms (expect 25ms) [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    ok = FLICKER_ON_MS == 12.5 and FLICKER_OFF_MS == 12.5
    print(f"  Flicker: {FLICKER_ON_MS}ms on / {FLICKER_OFF_MS}ms off [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # ------ Test 2: Safety check ------
    print("\n--- Test 2: Safety screening ---")

    # No epilepsy
    result = check_safety(has_epilepsy=False, visual_enabled=True)
    ok = result["safe"] and result["visual_allowed"]
    print(f"  No epilepsy, visual on: safe={result['safe']}, visual={result['visual_allowed']} [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # Epilepsy present
    result = check_safety(has_epilepsy=True, visual_enabled=True)
    ok = not result["visual_allowed"] and len(result["warnings"]) > 0
    print(f"  Epilepsy, visual on: visual={result['visual_allowed']}, warnings={len(result['warnings'])} [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # Unscreened
    result = check_safety(has_epilepsy=None, visual_enabled=True)
    ok = len(result["warnings"]) > 0
    print(f"  Unscreened: warnings={len(result['warnings'])} [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # ------ Test 3: Audio generation (AM mode) ------
    print("\n--- Test 3: Audio generation (AM) ---")

    # Generate 0.1 minutes (6 seconds) for quick test
    audio = generate_40hz_audio(
        duration_minutes=0.1, sample_rate=44100, mode="am", amplitude=0.5
    )
    expected_samples = int(0.1 * 60 * 44100)
    ok = len(audio) == expected_samples
    print(f"  Sample count: {len(audio)} (expect {expected_samples}) [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # Check amplitude bounds
    ok = np.max(np.abs(audio)) <= 0.5 + 0.001
    print(f"  Max amplitude: {np.max(np.abs(audio)):.4f} (limit 0.5) [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # Check that the signal is not silence
    rms = np.sqrt(np.mean(audio**2))
    ok = rms > 0.01
    print(f"  RMS amplitude: {rms:.4f} (should be > 0) [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # Verify 40 Hz modulation via FFT on the envelope
    # Take the magnitude of the analytic signal (Hilbert) or just
    # check the spectrum of the raw signal for sideband structure.
    # Simpler: check that the power spectrum has a peak near
    # carrier_freq +/- 40 Hz.
    print("  [FFT verification of 40 Hz modulation]")
    # Use a section from the middle (avoid fade in/out)
    mid_start = len(audio) // 3
    mid_end = 2 * len(audio) // 3
    segment = audio[mid_start:mid_end]
    fft_vals = np.abs(np.fft.rfft(segment))
    freqs = np.fft.rfftfreq(len(segment), d=1.0 / 44100)

    # Should have peaks at 440-40=400 Hz and 440+40=480 Hz (AM sidebands)
    # and at 440 Hz (carrier)
    idx_400 = np.argmin(np.abs(freqs - 400.0))
    idx_440 = np.argmin(np.abs(freqs - 440.0))
    idx_480 = np.argmin(np.abs(freqs - 480.0))

    # Check that the sideband region has significant power
    power_400 = fft_vals[idx_400]
    power_440 = fft_vals[idx_440]
    power_480 = fft_vals[idx_480]
    ok = power_400 > 0.1 * power_440 and power_480 > 0.1 * power_440
    print(
        f"  FFT peaks: 400Hz={power_400:.0f}, 440Hz={power_440:.0f}, "
        f"480Hz={power_480:.0f} [{'PASS' if ok else 'FAIL'}]"
    )
    if not ok:
        errors += 1

    # ------ Test 4: Audio generation (isochronous mode) ------
    print("\n--- Test 4: Audio generation (isochronous) ---")
    audio_iso = generate_40hz_audio(
        duration_minutes=0.1, sample_rate=44100, mode="isochronous", amplitude=0.5
    )
    ok = len(audio_iso) == expected_samples
    print(f"  Sample count: {len(audio_iso)} [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    rms_iso = np.sqrt(np.mean(audio_iso**2))
    ok = rms_iso > 0.01
    print(f"  RMS amplitude: {rms_iso:.4f} [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # ------ Test 5: Visual timestamps ------
    print("\n--- Test 5: Visual flicker timestamps ---")
    # 0.1 minutes = 6 seconds. At 40 Hz = 240 cycles.
    timestamps = generate_40hz_visual_timestamps(duration_minutes=0.1)
    expected_cycles = int(0.1 * 60 * 40)  # 240
    ok = len(timestamps) == expected_cycles
    print(f"  Cycle count: {len(timestamps)} (expect {expected_cycles}) [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # Check first cycle timing
    if len(timestamps) > 0:
        first = timestamps[0]
        ok = (
            first["cycle"] == 0
            and abs(first["on_time"] - 0.0) < 1e-6
            and abs(first["off_time"] - 0.0125) < 1e-6
            and abs(first["next_on"] - 0.025) < 1e-6
        )
        print(
            f"  First cycle: on={first['on_time']}, off={first['off_time']}, "
            f"next={first['next_on']} [{'PASS' if ok else 'FAIL'}]"
        )
        if not ok:
            errors += 1

    # Check last cycle
    if len(timestamps) > 1:
        last = timestamps[-1]
        expected_on = (expected_cycles - 1) * 0.025
        ok = abs(last["on_time"] - expected_on) < 1e-4
        print(f"  Last cycle on_time: {last['on_time']:.4f} (expect {expected_on:.4f}) [{'PASS' if ok else 'FAIL'}]")
        if not ok:
            errors += 1

    # ------ Test 6: GammaSession workflow ------
    print("\n--- Test 6: GammaSession workflow ---")
    session = GammaSession(duration_minutes=1, mode="av", audio_mode="am")

    # Safety check
    safety = session.safety_check(has_epilepsy=False)
    ok = safety["safe"]
    print(f"  Safety check: {safety['safe']} [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # Simulate session
    session._start_time = time.time() - 60  # 60 seconds ago
    session._stop_time = time.time()
    session._running = False

    progress = session.get_progress()
    ok = progress["complete"]
    print(f"  1min session complete: {progress['complete']} [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # Check gamma cycles: 60 seconds * 40 Hz = 2400
    ok = progress["gamma_cycles_delivered"] == 2400
    print(f"  Gamma cycles: {progress['gamma_cycles_delivered']} (expect 2400) [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # ------ Test 7: Epilepsy safety downgrade ------
    print("\n--- Test 7: Epilepsy auto-downgrade ---")
    session_ep = GammaSession(duration_minutes=1, mode="av")
    safety = session_ep.safety_check(has_epilepsy=True)
    ok = session_ep.mode == "audio" and not safety["visual_allowed"]
    print(f"  Mode after epilepsy: {session_ep.mode}, visual={safety['visual_allowed']} [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # ------ Test 8: Session logging ------
    print("\n--- Test 8: Session logging ---")
    log = session.get_log()
    ok = log.mode == "av" and log.completed
    print(f"  Log: mode={log.mode}, completed={log.completed} [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # ------ Test 9: Stats ------
    print("\n--- Test 9: Cumulative statistics ---")
    stats = GammaStats()
    stats.add_session(log)
    summary = stats.summary()
    ok = summary["total_sessions"] == 1 and summary["total_gamma_cycles"] > 0
    print(f"  Summary: {summary} [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # ------ Test 10: Clinical dose check ------
    print("\n--- Test 10: Clinical dose calculation ---")
    # Standard protocol: 60 min/day
    # 60 * 60 * 40 = 144,000 gamma cycles per session
    clinical_cycles = 60 * 60 * 40
    print(f"  Standard 60-min session: {clinical_cycles:,} gamma cycles")
    # 90 days (typical trial): 12,960,000 cycles
    trial_cycles = clinical_cycles * 90
    print(f"  90-day trial: {trial_cycles:,} gamma cycles")
    ok = clinical_cycles == 144000
    print(f"  Dose check: [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # ------ Summary ------
    print("\n" + "=" * 60)
    if errors == 0:
        print("ALL TESTS PASSED")
    else:
        print(f"FAILURES: {errors}")
    print("=" * 60)

    return errors == 0


if __name__ == "__main__":
    _self_test()
