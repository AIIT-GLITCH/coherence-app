"""
Coherence App — Intervention Modules
=====================================

Wike Coherence Framework implementation.

Modules:
    breathing_pacer     — 0.1 Hz cardiac coherence breathing
    gamma40_stimulation — 40 Hz audiovisual gamma entrainment
    geomag_monitor      — Geomagnetic storm cardiac risk monitoring (Paper 25)
    ace_assessment      — ACE questionnaire & coherence impact (Paper 24/25)
"""

from .breathing_pacer import BreathingSession, BreathingStats, generate_audio_guide, PATTERNS
from .gamma40_stimulation import GammaSession, GammaStats, generate_40hz_audio, generate_40hz_visual_timestamps
from .geomag_monitor import (
    GeomagReading, fetch_current_kp, fetch_forecast, manual_reading,
    gamma_geomag, get_alert, should_alert, get_status_summary, kp_to_storm_level,
)
from .ace_assessment import (
    ACEAssessment, coherence_at_ace, get_risk_profile, get_protective_factors,
    get_questions, format_question,
)
