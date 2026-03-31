"""
breathing_pacer.py — 0.1 Hz Cardiac Coherence Breathing Pacer
=============================================================

Wike Coherence Framework — Intervention Module 1

WHY 0.1 Hz?
-----------
The human baroreflex — the feedback loop between blood pressure sensors
in the carotid sinus and the vagal brake on the heart — has a resonance
frequency of approximately 0.1 Hz (one full cycle every 10 seconds,
i.e. 6 breaths per minute).

When you breathe at this frequency, you drive the baroreflex into
resonance. The result is maximum heart rate variability (HRV) coherence:
the oscillation in beat-to-beat interval becomes a single, large-amplitude
sine wave at 0.1 Hz, instead of the usual noisy broadband signal.

This is not mysticism. It is a driven harmonic oscillator at resonance.

CONVERGENT EVIDENCE
-------------------
Bernardi et al. (BMJ 323:1446, 2001):
    Measured breathing rates during the Catholic rosary (Ave Maria in
    Latin), yoga mantras (om mani padme hum), and Buddhist chanting.
    ALL converged on ~0.1 Hz (6 breaths/min). Five independent prayer
    traditions arrived at the same frequency by trial and error over
    centuries. The frequency was selected by evolution of practice,
    not by physiology textbooks.

HeartMath Institute (1.8 million sessions):
    Peak HRV coherence ratio occurs at 0.1 Hz. The distribution is
    sharply peaked — not a broad optimum, but a resonance.

Lehrer & Gevirtz (Applied Psychophysiology & Biofeedback, 2014):
    Comprehensive review: 0.1 Hz breathing maximizes baroreflex gain,
    vagal tone, and autonomic flexibility.

Wike Coherence Framework — Paper 23:
    The cardiac coherence frequency gamma_c IS 0.1 Hz. Breathing at
    this frequency forces gamma_eff below gamma_c, preventing the
    autonomic decoherence that drives chronic disease. The same
    physics (phase transition at a critical coupling) governs neural,
    cardiac, and immune coherence.

    HRV at 0.1 Hz -> vagal tone optimization -> autonomic-immune
    coupling -> reduced gamma_eff systemically.

REFERENCES
----------
[1] Bernardi L et al. BMJ 323:1446-1449 (2001)
[2] Lehrer PM, Gevirtz R. Appl Psychophysiol Biofeedback 39:209-228 (2014)
[3] McCraty R et al. HeartMath Research Center (2009)
[4] Vaschillo EG et al. Appl Psychophysiol Biofeedback 27:1-27 (2002)
[5] Wike Coherence Framework, Paper 23: Neural Coherence

Author: Coherence App / Wike Framework
License: Open for clinical and research use
"""

import time
import json
from datetime import datetime, date
from dataclasses import dataclass, field, asdict
from typing import Optional


# ============================================================================
# BREATHING PATTERNS
# ============================================================================
# Each pattern is a list of (phase_name, duration_seconds) tuples.
# A full cycle = one complete breath.
# Frequency = 1 / sum(durations).

PATTERNS = {
    "resonance": [
        # Standard 0.1 Hz cardiac coherence.
        # 4s inhale + 6s exhale = 10s cycle = 0.1 Hz.
        # The asymmetry (longer exhale) activates parasympathetic dominance
        # during the exhale phase, when the vagal brake is engaged.
        ("inhale", 4.0),
        ("exhale", 6.0),
    ],
    "box": [
        # Box breathing / tactical breathing.
        # Used by US Navy SEALs, Special Forces, first responders.
        # 4+4+4+4 = 16s cycle = 0.0625 Hz.
        # Not at baroreflex resonance, but the holds add interoceptive
        # awareness and CO2 tolerance. Good for acute stress.
        ("inhale", 4.0),
        ("hold", 4.0),
        ("exhale", 4.0),
        ("hold", 4.0),
    ],
    "calm": [
        # Extended exhale for maximum parasympathetic activation.
        # 4s in + 7s out = 11s cycle = 0.0909 Hz.
        # Close to 0.1 Hz, but the extended exhale maximizes the
        # duration of vagal engagement per cycle. Best for anxiety,
        # insomnia, acute panic.
        ("inhale", 4.0),
        ("exhale", 7.0),
    ],
    "prayer": [
        # Exact 0.1 Hz with equal phases.
        # 5s in + 5s out = 10s = 0.1 Hz.
        # This is the rosary timing measured by Bernardi (2001).
        # The Ave Maria in Latin, recited at the traditional pace,
        # takes ~10 seconds per prayer — forcing exactly 0.1 Hz.
        # Equal inhale/exhale is slightly less parasympathetic than
        # the "resonance" pattern but easier to learn.
        ("inhale", 5.0),
        ("exhale", 5.0),
    ],
}


def get_pattern_frequency(pattern_name: str) -> float:
    """Return the breathing frequency in Hz for a given pattern."""
    phases = PATTERNS[pattern_name]
    cycle_duration = sum(dur for _, dur in phases)
    return 1.0 / cycle_duration


def get_pattern_info(pattern_name: str) -> dict:
    """Return full info about a breathing pattern."""
    phases = PATTERNS[pattern_name]
    cycle_duration = sum(dur for _, dur in phases)
    return {
        "name": pattern_name,
        "phases": [(name, dur) for name, dur in phases],
        "cycle_seconds": cycle_duration,
        "frequency_hz": 1.0 / cycle_duration,
        "breaths_per_minute": 60.0 / cycle_duration,
    }


# ============================================================================
# SESSION LOG ENTRY
# ============================================================================

@dataclass
class SessionLog:
    """Record of a single breathing session."""
    start_time: str
    end_time: Optional[str] = None
    pattern: str = "resonance"
    target_duration_seconds: float = 300.0
    actual_duration_seconds: float = 0.0
    completed: bool = False
    cycles_completed: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ============================================================================
# BREATHING SESSION
# ============================================================================

class BreathingSession:
    """
    Real-time breathing pacer session.

    Usage:
        session = BreathingSession(pattern="resonance", duration_minutes=5)
        session.start()

        # In your UI loop:
        phase_info = session.get_current_phase()
        # -> {"phase": "inhale", "progress": 0.45, "seconds_remaining": 2.2,
        #     "cycle": 3, "elapsed": 32.5, "total_duration": 300.0}

        session.stop()
        log = session.get_log()
    """

    def __init__(self, pattern: str = "resonance", duration_minutes: float = 5.0):
        if pattern not in PATTERNS:
            raise ValueError(
                f"Unknown pattern '{pattern}'. "
                f"Available: {list(PATTERNS.keys())}"
            )

        self.pattern_name = pattern
        self.phases = PATTERNS[pattern]
        self.cycle_duration = sum(dur for _, dur in self.phases)
        self.frequency_hz = 1.0 / self.cycle_duration
        self.duration_seconds = duration_minutes * 60.0

        # Session state
        self._start_time: Optional[float] = None
        self._stop_time: Optional[float] = None
        self._running = False

        # Pre-compute phase boundaries within a single cycle.
        # boundaries[i] = cumulative seconds at end of phase i.
        self._phase_boundaries = []
        cumulative = 0.0
        for _, dur in self.phases:
            cumulative += dur
            self._phase_boundaries.append(cumulative)

    def start(self) -> None:
        """Begin the session. Call this when the user starts breathing."""
        self._start_time = time.time()
        self._running = True

    def stop(self) -> None:
        """End the session."""
        self._stop_time = time.time()
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def elapsed(self) -> float:
        """Seconds elapsed since session start."""
        if self._start_time is None:
            return 0.0
        end = self._stop_time if self._stop_time else time.time()
        return end - self._start_time

    def get_current_phase(self, elapsed_seconds: Optional[float] = None) -> dict:
        """
        Get the current breathing phase and progress.

        Parameters
        ----------
        elapsed_seconds : float, optional
            If provided, compute phase for this elapsed time instead of
            the actual wall-clock elapsed time. Useful for testing,
            pre-computation, and audio guide generation.

        Returns
        -------
        dict with keys:
            phase : str
                "inhale", "exhale", or "hold"
            progress : float
                0.0 to 1.0 within the current phase
            seconds_remaining : float
                Seconds until this phase ends
            cycle : int
                Which breath cycle we're in (0-indexed)
            elapsed : float
                Total elapsed seconds
            total_duration : float
                Total session duration in seconds
            session_progress : float
                0.0 to 1.0 overall session progress
            session_complete : bool
                True if elapsed >= total duration
        """
        if elapsed_seconds is None:
            elapsed_seconds = self.elapsed

        # Clamp to session duration
        session_complete = elapsed_seconds >= self.duration_seconds
        clamped = min(elapsed_seconds, self.duration_seconds)

        # Which cycle are we in?
        cycle = int(clamped // self.cycle_duration)
        time_in_cycle = clamped % self.cycle_duration

        # Handle exact boundary (end of cycle)
        if time_in_cycle == 0.0 and clamped > 0:
            # We're at the exact start of a new cycle
            pass

        # Find which phase within the cycle
        phase_name = self.phases[-1][0]  # default to last phase
        phase_duration = self.phases[-1][1]
        phase_elapsed = time_in_cycle
        for i, (pname, pdur) in enumerate(self.phases):
            if time_in_cycle < self._phase_boundaries[i]:
                phase_name = pname
                phase_duration = pdur
                phase_start = self._phase_boundaries[i] - pdur
                phase_elapsed = time_in_cycle - phase_start
                break

        progress = phase_elapsed / phase_duration if phase_duration > 0 else 1.0
        seconds_remaining = phase_duration - phase_elapsed

        return {
            "phase": phase_name,
            "progress": round(min(progress, 1.0), 4),
            "seconds_remaining": round(max(seconds_remaining, 0.0), 3),
            "cycle": cycle,
            "elapsed": round(elapsed_seconds, 3),
            "total_duration": self.duration_seconds,
            "session_progress": round(clamped / self.duration_seconds, 4),
            "session_complete": session_complete,
        }

    def get_log(self) -> SessionLog:
        """Return a SessionLog for this session."""
        start_str = (
            datetime.fromtimestamp(self._start_time).isoformat()
            if self._start_time else ""
        )
        end_str = (
            datetime.fromtimestamp(self._stop_time).isoformat()
            if self._stop_time else ""
        )
        actual = self.elapsed
        cycles = int(actual // self.cycle_duration)
        completed = actual >= self.duration_seconds * 0.95  # 95% = completed

        return SessionLog(
            start_time=start_str,
            end_time=end_str,
            pattern=self.pattern_name,
            target_duration_seconds=self.duration_seconds,
            actual_duration_seconds=round(actual, 2),
            completed=completed,
            cycles_completed=cycles,
        )


# ============================================================================
# AUDIO GUIDE GENERATION
# ============================================================================

def generate_audio_guide(
    pattern: str = "resonance",
    duration_minutes: float = 5.0,
    include_countdown: bool = True,
) -> list:
    """
    Generate a list of timestamped audio cues for a breathing session.

    This produces the data structure a UI or audio engine needs to play
    audio prompts ("inhale", "exhale", "hold") at the correct times.

    Parameters
    ----------
    pattern : str
        One of the PATTERNS keys.
    duration_minutes : float
        Total session length in minutes.
    include_countdown : bool
        If True, include 3-2-1 countdown cues before the first breath.

    Returns
    -------
    list of dict, each with:
        time : float       — seconds from session start
        cue : str          — "inhale", "exhale", "hold", "countdown", "complete"
        duration : float   — how long this phase lasts
        cycle : int        — which breath cycle (0-indexed)
    """
    if pattern not in PATTERNS:
        raise ValueError(f"Unknown pattern '{pattern}'.")

    phases = PATTERNS[pattern]
    cycle_duration = sum(dur for _, dur in phases)
    total_seconds = duration_minutes * 60.0
    cues = []

    # Optional countdown
    offset = 0.0
    if include_countdown:
        for i in [3, 2, 1]:
            cues.append({
                "time": round(offset, 3),
                "cue": "countdown",
                "value": i,
                "duration": 1.0,
                "cycle": -1,
            })
            offset += 1.0

    # Breathing cues
    t = offset
    cycle = 0
    while t < total_seconds + offset:
        for phase_name, phase_dur in phases:
            if t >= total_seconds + offset:
                break
            cues.append({
                "time": round(t, 3),
                "cue": phase_name,
                "duration": phase_dur,
                "cycle": cycle,
            })
            t += phase_dur
        cycle += 1

    # Session complete marker
    cues.append({
        "time": round(total_seconds + offset, 3),
        "cue": "complete",
        "duration": 0.0,
        "cycle": cycle,
    })

    return cues


# ============================================================================
# SESSION STATISTICS
# ============================================================================

class BreathingStats:
    """
    Tracks cumulative statistics across multiple sessions.

    In a real app, this would persist to disk/database. Here we provide
    the in-memory data structure and computation logic.
    """

    def __init__(self):
        self.sessions: list[SessionLog] = []

    def add_session(self, log: SessionLog) -> None:
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
    def total_cycles(self) -> int:
        return sum(s.cycles_completed for s in self.sessions)

    @property
    def streak_days(self) -> int:
        """
        Count consecutive days with at least one completed session,
        going backwards from today.
        """
        if not self.sessions:
            return 0

        # Collect unique dates of completed sessions
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

        # Count backwards from today
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
            "total_cycles": self.total_cycles,
            "streak_days": self.streak_days,
        }


# ============================================================================
# SELF-TESTS
# ============================================================================

def _self_test():
    """
    Verify core functionality. Run with: python breathing_pacer.py
    """
    print("=" * 60)
    print("BREATHING PACER — SELF-TEST")
    print("=" * 60)

    errors = 0

    # ------ Test 1: Pattern frequencies ------
    print("\n--- Test 1: Pattern frequencies ---")
    expected_freqs = {
        "resonance": 0.1,    # 4+6 = 10s
        "box": 0.0625,       # 4+4+4+4 = 16s
        "calm": 1.0 / 11.0,  # 4+7 = 11s
        "prayer": 0.1,       # 5+5 = 10s
    }
    for name, expected in expected_freqs.items():
        actual = get_pattern_frequency(name)
        ok = abs(actual - expected) < 1e-9
        status = "PASS" if ok else "FAIL"
        print(f"  {name}: {actual:.4f} Hz (expected {expected:.4f}) [{status}]")
        if not ok:
            errors += 1

    # ------ Test 2: Phase tracking (resonance) ------
    print("\n--- Test 2: Phase tracking (resonance pattern) ---")
    session = BreathingSession(pattern="resonance", duration_minutes=1)

    test_cases = [
        # (elapsed_seconds, expected_phase, expected_cycle)
        (0.0, "inhale", 0),
        (2.0, "inhale", 0),
        (3.99, "inhale", 0),
        (4.0, "exhale", 0),    # Transition to exhale at 4s
        (7.0, "exhale", 0),
        (9.99, "exhale", 0),
        (10.0, "inhale", 1),   # New cycle
        (14.0, "exhale", 1),
        (20.0, "inhale", 2),
    ]

    for elapsed, exp_phase, exp_cycle in test_cases:
        result = session.get_current_phase(elapsed_seconds=elapsed)
        phase_ok = result["phase"] == exp_phase
        cycle_ok = result["cycle"] == exp_cycle
        ok = phase_ok and cycle_ok
        status = "PASS" if ok else "FAIL"
        print(
            f"  t={elapsed:5.1f}s -> phase={result['phase']:7s} "
            f"cycle={result['cycle']} progress={result['progress']:.2f} "
            f"[{status}]"
        )
        if not ok:
            errors += 1
            if not phase_ok:
                print(f"    EXPECTED phase={exp_phase}")
            if not cycle_ok:
                print(f"    EXPECTED cycle={exp_cycle}")

    # ------ Test 3: Phase tracking (box breathing) ------
    print("\n--- Test 3: Phase tracking (box pattern) ---")
    session_box = BreathingSession(pattern="box", duration_minutes=1)

    box_tests = [
        (0.0, "inhale", 0),
        (4.0, "hold", 0),      # First hold after inhale
        (8.0, "exhale", 0),
        (12.0, "hold", 0),     # Second hold after exhale
        (16.0, "inhale", 1),   # New cycle
    ]
    for elapsed, exp_phase, exp_cycle in box_tests:
        result = session_box.get_current_phase(elapsed_seconds=elapsed)
        ok = result["phase"] == exp_phase and result["cycle"] == exp_cycle
        status = "PASS" if ok else "FAIL"
        print(
            f"  t={elapsed:5.1f}s -> phase={result['phase']:7s} "
            f"cycle={result['cycle']} [{status}]"
        )
        if not ok:
            errors += 1

    # ------ Test 4: Progress values ------
    print("\n--- Test 4: Progress boundary values ---")
    # At t=0, inhale progress should be 0
    r = session.get_current_phase(elapsed_seconds=0.0)
    ok = r["progress"] == 0.0
    print(f"  t=0.0: progress={r['progress']} [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # At t=2.0, inhale progress should be 0.5 (2/4)
    r = session.get_current_phase(elapsed_seconds=2.0)
    ok = abs(r["progress"] - 0.5) < 0.001
    print(f"  t=2.0: progress={r['progress']} (expect 0.5) [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # seconds_remaining at t=2.0 should be 2.0
    ok = abs(r["seconds_remaining"] - 2.0) < 0.01
    print(f"  t=2.0: remaining={r['seconds_remaining']}s (expect 2.0) [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # ------ Test 5: Session completion ------
    print("\n--- Test 5: Session completion ---")
    r = session.get_current_phase(elapsed_seconds=60.0)
    ok = r["session_complete"]
    print(f"  t=60s (1min session): complete={r['session_complete']} [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    r = session.get_current_phase(elapsed_seconds=30.0)
    ok = not r["session_complete"]
    print(f"  t=30s: complete={r['session_complete']} [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # ------ Test 6: Audio guide ------
    print("\n--- Test 6: Audio guide generation ---")
    cues = generate_audio_guide("resonance", duration_minutes=1, include_countdown=True)
    # Should start with 3 countdown cues
    countdown_cues = [c for c in cues if c["cue"] == "countdown"]
    ok = len(countdown_cues) == 3
    print(f"  Countdown cues: {len(countdown_cues)} [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # 1 minute / 10s cycle = 6 cycles. Each cycle has 2 phases (inhale, exhale).
    breath_cues = [c for c in cues if c["cue"] in ("inhale", "exhale")]
    ok = len(breath_cues) == 12  # 6 cycles * 2 phases
    print(f"  Breath cues for 1min resonance: {len(breath_cues)} (expect 12) [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # Should end with "complete"
    ok = cues[-1]["cue"] == "complete"
    print(f"  Final cue: {cues[-1]['cue']} [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # ------ Test 7: Session log ------
    print("\n--- Test 7: Session logging ---")
    session2 = BreathingSession(pattern="prayer", duration_minutes=2)
    session2._start_time = time.time() - 120  # Simulate 2 minutes ago
    session2._stop_time = time.time()
    log = session2.get_log()
    ok = log.pattern == "prayer" and log.completed and log.cycles_completed == 12
    print(
        f"  Log: pattern={log.pattern}, completed={log.completed}, "
        f"cycles={log.cycles_completed} [{'PASS' if ok else 'FAIL'}]"
    )
    if not ok:
        errors += 1

    # ------ Test 8: Stats ------
    print("\n--- Test 8: Cumulative statistics ---")
    stats = BreathingStats()
    stats.add_session(log)
    summary = stats.summary()
    ok = summary["total_sessions"] == 1 and summary["total_minutes"] > 1.9
    print(f"  Summary: {summary} [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        errors += 1

    # ------ Test 9: Pattern info ------
    print("\n--- Test 9: Pattern info ---")
    for name in PATTERNS:
        info = get_pattern_info(name)
        print(
            f"  {name}: {info['breaths_per_minute']:.1f} breaths/min, "
            f"{info['frequency_hz']:.4f} Hz, {info['cycle_seconds']}s/cycle"
        )

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
