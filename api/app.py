"""
Coherence API — Flask backend for the Wike Coherence Framework health app.

"Find your edge."

VERSION: 1.0.0
AUTHOR: AIIT-THRESI | Rhet Dillard Wike

This app does NOT optimize for engagement.
It optimizes for the user's gamma_eff approaching gamma_c.
If the user is at the edge, this app tells them to PUT IT DOWN.

The physics:
    C(t) = C_0 * exp(-alpha * gamma_eff * t)       -- Wike Coherence Law
    V(gamma) = C_0 * gamma * exp(-alpha * gamma)    -- Vitality function
    gamma_c = 0.0622                                -- coherence threshold (Berry Phase)
    W = gamma_c - gamma_eff                         -- the window
    alpha = 1 / gamma_c = 16.08                     -- vacuum coupling at 310K

Papers: 50 papers, 13.8M+ data points. Every constant derived, none fitted.
"""

import os
import sys
import json
import math
import uuid
import time
import sqlite3
import logging
import hashlib
from datetime import datetime, timedelta, timezone
from functools import wraps
from contextlib import contextmanager

from flask import Flask, request, jsonify, g, send_from_directory

# ---------------------------------------------------------------------------
# APP CONFIG
# ---------------------------------------------------------------------------

APP_NAME = "Coherence"
APP_TAGLINE = "Find your edge."
VERSION = "1.0.0"
AUTHOR = "AIIT-THRESI | Rhet Dillard Wike"

# ENGAGEMENT_WEIGHT = 0. This app does NOT optimize for engagement.
# It optimizes for the user's gamma_eff approaching gamma_c.
# If the user is at the edge, the app should tell them to PUT IT DOWN.
ENGAGEMENT_WEIGHT = 0

# ---------------------------------------------------------------------------
# PHYSICS CONSTANTS (all derived — see WIKE_COMPLETE_MATHEMATICS.md)
# ---------------------------------------------------------------------------

GAMMA_C = 0.0622          # coherence threshold (Berry Phase, QuTiP 5.2.3)
ALPHA = 1.0 / GAMMA_C     # vacuum coupling at 310K = 16.08
T_BODY = 310.0             # body temperature in Kelvin
T_C = 330.0                # hydrogen bond critical temperature
W_GINZBURG = T_BODY / T_C  # 0.9394 — the Wike-Ginzburg number
ISING_SUSCEPTIBILITY = 1.2372  # 3D Ising susceptibility exponent
ACE_BETA = 0.416           # ACE decay constant per ACE (Paper 24)
ACE_NU = 0.82              # stretched exponent (sub-diffusive)
KEEPER_MAX_BOND = 0.9      # maximum b * eta_K
RESONANCE_HZ = 0.1         # baroreflex resonance frequency
GAMMA_40HZ = 40.0          # gamma stimulation frequency
CYTOKINE_TIPPING = 0.010   # cytokine storm tipping point

# Anti-Zeno guard (Paper 50)
ANTI_ZENO_MAX_CHECKS_PER_DAY = 6
ANTI_ZENO_MESSAGE = (
    "The physics says: the more you measure, the more you collapse. "
    "Trust the edge. You are doing well. Put it down."
)

# Breathing patterns
BREATHING_PATTERNS = {
    "resonance": {
        "name": "Resonance Breathing",
        "inhale_sec": 5.0,
        "exhale_sec": 5.0,
        "hold_in_sec": 0.0,
        "hold_out_sec": 0.0,
        "rate_hz": RESONANCE_HZ,
        "description": (
            "6 breaths per minute. Baroreflex resonance at 0.1 Hz. "
            "Bernardi (BMJ, 2001): 5 prayer traditions converge here. "
            "Cost: $0. Risk: zero."
        ),
    },
    "box": {
        "name": "Box Breathing",
        "inhale_sec": 4.0,
        "exhale_sec": 4.0,
        "hold_in_sec": 4.0,
        "hold_out_sec": 4.0,
        "rate_hz": 0.0625,
        "description": "Navy SEAL protocol. 4-4-4-4. Sympathetic suppression.",
    },
    "calm": {
        "name": "Calm Breathing",
        "inhale_sec": 4.0,
        "exhale_sec": 6.0,
        "hold_in_sec": 0.0,
        "hold_out_sec": 0.0,
        "rate_hz": 0.1,
        "description": (
            "Extended exhale activates vagal brake. "
            "Parasympathetic dominance in 90 seconds."
        ),
    },
    "prayer": {
        "name": "Prayer Breath",
        "inhale_sec": 5.0,
        "exhale_sec": 5.0,
        "hold_in_sec": 0.0,
        "hold_out_sec": 0.0,
        "rate_hz": RESONANCE_HZ,
        "description": (
            "Identical to resonance. The Ave Maria, the rosary, "
            "the Om Mani Padme Hum — they all converge on 0.1 Hz. "
            "Bernardi proved it. The physics was always in the prayer."
        ),
    },
    "4-7-8": {
        "name": "4-7-8 Breathing",
        "inhale_sec": 4.0,
        "exhale_sec": 8.0,
        "hold_in_sec": 7.0,
        "hold_out_sec": 0.0,
        "rate_hz": round(1.0 / 19.0, 4),
        "description": (
            "Andrew Weil protocol. 4s inhale, 7s hold, 8s exhale. "
            "Extended exhale and hold maximize parasympathetic activation."
        ),
    },
}

# Gamma 40 Hz modes
GAMMA40_MODES = {
    "audio": {
        "name": "40 Hz Audio",
        "frequency_hz": GAMMA_40HZ,
        "description": (
            "40 Hz binaural or isochronic audio. "
            "Martorell (Cell, 2019): extends gamma entrainment to hippocampus."
        ),
    },
    "visual": {
        "name": "40 Hz Visual",
        "frequency_hz": GAMMA_40HZ,
        "description": (
            "40 Hz LED flicker. "
            "Iaccarino (Nature, 2016): amyloid reduced in mice. "
            "Contraindication: photosensitive epilepsy ONLY."
        ),
    },
    "both": {
        "name": "40 Hz Audio + Visual",
        "frequency_hz": GAMMA_40HZ,
        "description": (
            "Combined audiovisual 40 Hz entrainment. "
            "Tsai Lab (Nature, 2024): VIP interneuron mechanism confirmed. "
            "Phase III ongoing: NCT04912531. "
            "1 hour/day, 3 months minimum for Alzheimer's protocol."
        ),
    },
}

# Geomag storm levels (NOAA scale)
STORM_LEVELS = {
    0: {"label": "G0", "description": "Quiet", "gamma_delta": 0.000},
    1: {"label": "G0", "description": "Quiet", "gamma_delta": 0.001},
    2: {"label": "G0", "description": "Unsettled", "gamma_delta": 0.002},
    3: {"label": "G1", "description": "Minor storm", "gamma_delta": 0.005},
    4: {"label": "G1", "description": "Minor storm", "gamma_delta": 0.008},
    5: {"label": "G2", "description": "Moderate storm", "gamma_delta": 0.012},
    6: {"label": "G2", "description": "Moderate storm", "gamma_delta": 0.018},
    7: {"label": "G3", "description": "Strong storm", "gamma_delta": 0.025},
    8: {"label": "G4", "description": "Severe storm", "gamma_delta": 0.030},
    9: {"label": "G5", "description": "Extreme storm", "gamma_delta": 0.035},
}

# ---------------------------------------------------------------------------
# STUB IMPORTS — modules being built in parallel
# ---------------------------------------------------------------------------

try:
    from core.coherence_engine import CoherenceEngine, UserProfile, DailyReading
    _HAS_ENGINE = True
except ImportError:
    _HAS_ENGINE = False

try:
    from modules.hrv_analyzer import HRVAnalyzer
    _HAS_HRV = True
except ImportError:
    _HAS_HRV = False

try:
    from modules.breathing_pacer import BreathingSession
    _HAS_BREATHING = True
except ImportError:
    _HAS_BREATHING = False

try:
    from modules.gamma40_stimulation import GammaSession
    _HAS_GAMMA40 = True
except ImportError:
    _HAS_GAMMA40 = False

try:
    from modules.geomag_monitor import GeomagMonitor
    _HAS_GEOMAG = True
except ImportError:
    _HAS_GEOMAG = False

try:
    from modules.ace_assessment import ACEAssessment
    _HAS_ACE = True
except ImportError:
    _HAS_ACE = False

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("coherence")

# ---------------------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------------------

DB_DIR = os.path.expanduser("~/coherence_app")
DB_PATH = os.path.join(DB_DIR, "coherence.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT DEFAULT 'User',
    ace_score   INTEGER DEFAULT 0,
    age         INTEGER DEFAULT 30,
    has_keeper  INTEGER DEFAULT 0,
    keeper_bond REAL DEFAULT 0.0,
    cardiac_history INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS readings (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER DEFAULT 1,
    timestamp           TEXT DEFAULT (datetime('now')),
    hrv_rmssd           REAL,
    hrv_sdnn            REAL,
    hrv_sampen          REAL,
    sleep_hours         REAL,
    sleep_quality       REAL,
    stress_level        REAL,
    inflammation        REAL,
    exercise_minutes    REAL,
    meditation_minutes  REAL,
    breathing_sessions  INTEGER DEFAULT 0,
    nir_sessions        INTEGER DEFAULT 0,
    gamma40_sessions    INTEGER DEFAULT 0,
    gamma_eff           REAL,
    gamma_c             REAL,
    coherence           REAL,
    vitality            REAL,
    window              REAL,
    state               TEXT,
    lambda_l            TEXT,
    recommendations     TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS breathing_sessions (
    id              TEXT PRIMARY KEY,
    user_id         INTEGER DEFAULT 1,
    pattern         TEXT NOT NULL,
    duration_minutes REAL,
    started_at      TEXT DEFAULT (datetime('now')),
    completed_at    TEXT,
    completed       INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS gamma40_sessions (
    id              TEXT PRIMARY KEY,
    user_id         INTEGER DEFAULT 1,
    mode            TEXT NOT NULL,
    duration_minutes REAL,
    started_at      TEXT DEFAULT (datetime('now')),
    completed_at    TEXT,
    completed       INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS geomag_cache (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT DEFAULT (datetime('now')),
    kp          REAL,
    storm_level TEXT,
    alert       TEXT,
    raw_data    TEXT
);

CREATE TABLE IF NOT EXISTS app_checks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER DEFAULT 1,
    timestamp   TEXT DEFAULT (datetime('now')),
    endpoint    TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""


def _ensure_db():
    """Create database directory and tables if they do not exist."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_SQL)
    # Ensure at least one user row exists.
    cursor = conn.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO users (name, ace_score, age) VALUES (?, ?, ?)",
            ("User", 0, 30),
        )
    conn.commit()
    conn.close()
    log.info("Database initialized at %s", DB_PATH)


@contextmanager
def get_db():
    """Yield a SQLite connection with row_factory, auto-close on exit."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# PHYSICS ENGINE (inline fallback when core module not ready)
# ---------------------------------------------------------------------------

class _CoherencePhysics:
    """
    Pure-math implementation of the Wike Coherence Framework.

    Every constant is derived from first principles.
    No free parameters. No fitting. No engagement optimization.
    """

    @staticmethod
    def compute_gamma_eff(
        hrv_rmssd=40.0,
        hrv_sdnn=50.0,
        hrv_sampen=1.5,
        sleep_hours=7.0,
        sleep_quality=0.7,
        stress_level=0.3,
        inflammation=0.1,
        exercise_minutes=30.0,
        meditation_minutes=0.0,
        breathing_sessions=0,
        nir_sessions=0,
        gamma40_sessions=0,
        ace_score=0,
        has_keeper=False,
        keeper_bond=0.0,
        geomag_kp=2.0,
    ):
        """
        Compute effective decoherence rate from all noise sources.

        gamma_eff = gamma_measurement + gamma_thermal(T) + gamma_stress
                    + gamma_inflammatory + gamma_ACE + gamma_geomag
                    - delta_interventions - delta_keeper

        All terms are additive (Paper II.2) — stress weakens immunity
        through the same equation as infection.
        """
        # --- NOISE SOURCES (increase gamma_eff) ---

        # HRV-derived baseline noise: lower HRV = higher gamma
        # RMSSD < 20 ms is high risk; > 60 ms is excellent
        hrv_rmssd_clamped = max(5.0, min(hrv_rmssd, 120.0))
        gamma_hrv = 0.04 * (50.0 / hrv_rmssd_clamped)

        # SampEn contribution: healthy SampEn ~ 1.5-2.0 (edge state)
        # Low SampEn = frozen; very high = chaotic
        sampen_clamped = max(0.1, min(hrv_sampen, 3.0))
        if sampen_clamped < 0.5:
            # Frozen state — approaching cliff from below
            gamma_sampen = 0.01 * (0.5 / sampen_clamped)
        elif sampen_clamped > 2.5:
            # Chaotic state — approaching cliff from above
            gamma_sampen = 0.01 * (sampen_clamped / 2.5)
        else:
            # Edge state — minimal contribution
            gamma_sampen = 0.002

        # Sleep debt: Landauer erasure deficit (Paper 45)
        # 7-9 hours optimal; below 5 is catastrophic
        sleep_factor = max(0.0, min(sleep_hours, 10.0))
        sleep_quality_clamped = max(0.0, min(sleep_quality, 1.0))
        effective_sleep = sleep_factor * sleep_quality_clamped
        if effective_sleep >= 6.0:
            gamma_sleep = 0.002 * (7.0 / max(effective_sleep, 1.0))
        else:
            # Landauer debt accumulating
            gamma_sleep = 0.005 * (6.0 / max(effective_sleep, 0.5))

        # Stress: emotional/psychological noise (Paper 08)
        stress_clamped = max(0.0, min(stress_level, 1.0))
        gamma_stress = 0.03 * stress_clamped

        # Inflammation: IL-6, TNF-alpha, cytokine load (Paper 20)
        inflammation_clamped = max(0.0, min(inflammation, 1.0))
        gamma_inflammatory = 0.025 * inflammation_clamped
        # Check for cytokine storm tipping point
        if inflammation_clamped > 0.8:
            gamma_inflammatory += 0.01 * (inflammation_clamped - 0.8) / 0.2

        # ACE: accumulated adverse childhood experiences (Paper 24)
        # C_n = C_0 * exp(-(beta * n)^nu) — stretched exponential
        ace_clamped = max(0, min(ace_score, 10))
        if ace_clamped > 0:
            gamma_ace = 0.005 * (1.0 - math.exp(-((ACE_BETA * ace_clamped) ** ACE_NU)))
        else:
            gamma_ace = 0.0

        # Geomagnetic: shield degradation (Paper 25)
        kp_clamped = max(0.0, min(geomag_kp, 9.0))
        kp_int = min(int(kp_clamped), 9)
        gamma_geomag = STORM_LEVELS[kp_int]["gamma_delta"]

        # --- PROTECTIVE FACTORS (decrease gamma_eff) ---

        # Exercise: reduces inflammatory noise, improves HRV
        exercise_clamped = max(0.0, min(exercise_minutes, 120.0))
        delta_exercise = 0.005 * min(exercise_clamped / 30.0, 1.0)

        # Meditation: direct gamma_measurement reduction (REQMT principle)
        meditation_clamped = max(0.0, min(meditation_minutes, 60.0))
        delta_meditation = 0.003 * min(meditation_clamped / 15.0, 1.0)

        # Breathing sessions: baroreflex resonance at 0.1 Hz (Paper XIV.3)
        breathing_clamped = max(0, min(breathing_sessions, 5))
        delta_breathing = 0.004 * min(breathing_clamped / 2.0, 1.0)

        # NIR sessions: Bootstrap loop restart (Paper XIV.1)
        nir_clamped = max(0, min(nir_sessions, 3))
        delta_nir = 0.003 * min(nir_clamped / 1.0, 1.0)

        # 40 Hz gamma sessions: glymphatic + VIP interneurons (Paper XIV.2)
        gamma40_clamped = max(0, min(gamma40_sessions, 3))
        delta_gamma40 = 0.003 * min(gamma40_clamped / 1.0, 1.0)

        # Keeper: frequency-selective filter (Paper IX)
        # gamma_eff(S|K) = gamma_m * (1 - b * eta_K) + gamma_thermal
        keeper_bond_clamped = max(0.0, min(keeper_bond, 1.0))
        if has_keeper and keeper_bond_clamped > 0:
            delta_keeper = 0.008 * keeper_bond_clamped
        else:
            delta_keeper = 0.0

        # --- TOTAL ---
        gamma_eff = (
            gamma_hrv
            + gamma_sampen
            + gamma_sleep
            + gamma_stress
            + gamma_inflammatory
            + gamma_ace
            + gamma_geomag
            - delta_exercise
            - delta_meditation
            - delta_breathing
            - delta_nir
            - delta_gamma40
            - delta_keeper
        )

        # Floor at 0.001 — even a perfect day has thermal noise
        gamma_eff = max(0.001, gamma_eff)

        return gamma_eff

    @staticmethod
    def coherence(gamma_eff, c0=1.0, t=1.0):
        """C(t) = C_0 * exp(-alpha * gamma_eff * t)  -- Wike Coherence Law"""
        return c0 * math.exp(-ALPHA * gamma_eff * t)

    @staticmethod
    def vitality(gamma_eff, c0=1.0):
        """V(gamma) = C_0 * gamma * exp(-alpha * gamma) -- Paper 30"""
        return c0 * gamma_eff * math.exp(-ALPHA * gamma_eff)

    @staticmethod
    def vitality_max():
        """Maximum vitality at gamma_c = 1/alpha"""
        return GAMMA_C * math.exp(-1.0)  # V_max = gamma_c * e^(-1)

    @staticmethod
    def window(gamma_eff):
        """W = gamma_c - gamma_eff. Positive = inside window."""
        return GAMMA_C - gamma_eff

    @staticmethod
    def classify_state(gamma_eff):
        """
        Three states (Paper VII.1):
            frozen:    gamma_eff << gamma_c (lambda_L < 0)
            edge:      gamma_eff ~ gamma_c  (lambda_L ~ 0)
            collapsed: gamma_eff >> gamma_c  (lambda_L > 0)
        """
        ratio = gamma_eff / GAMMA_C
        if ratio < 0.5:
            return "frozen", "negative"
        elif ratio < 0.85:
            return "approaching", "near_zero"
        elif ratio <= 1.15:
            return "edge", "near_zero"
        elif ratio <= 1.5:
            return "warning", "positive"
        else:
            return "collapsed", "positive"

    @staticmethod
    def susceptibility(gamma_eff):
        """chi ~ |gamma - gamma_c|^(-1.2372) -- 3D Ising exponent"""
        delta = abs(gamma_eff - GAMMA_C)
        if delta < 1e-6:
            return 1e6  # cap near-singular
        return delta ** (-ISING_SUSCEPTIBILITY)

    @staticmethod
    def ace_coherence(ace_score, c0=1.0):
        """C_n = C_0 * exp(-(beta * n)^nu) -- Paper 24 stretched exponential"""
        if ace_score <= 0:
            return c0
        return c0 * math.exp(-((ACE_BETA * ace_score) ** ACE_NU))

    @staticmethod
    def keeper_gamma_reduction(gamma_measurement, bond, eta_k=0.8):
        """gamma_eff(S|K) = gamma_m * (1 - b * eta_K) -- Paper 19"""
        b_eta = max(0.0, min(bond * eta_k, KEEPER_MAX_BOND))
        return gamma_measurement * (1.0 - b_eta)

    @staticmethod
    def time_to_cliff(gamma_eff, gamma_eff_trend_per_day):
        """
        Estimate days until gamma_eff reaches gamma_c.
        Returns None if stable or improving.
        """
        w = GAMMA_C - gamma_eff
        if w <= 0:
            return 0.0  # already past cliff
        if gamma_eff_trend_per_day <= 0:
            return None  # stable or improving
        return w / gamma_eff_trend_per_day


physics = _CoherencePhysics()

# ---------------------------------------------------------------------------
# RECOMMENDATION ENGINE
# ---------------------------------------------------------------------------

def generate_recommendations(gamma_eff, state, lambda_l, today_data, profile):
    """
    Generate prioritized intervention list based on current state.

    The Five-Intervention Protocol (Paper XIV.5):
        1. 40 Hz audiovisual stimulation
        2. NIR photobiomodulation (810-870nm)
        3. HRV coherence training (0.1 Hz breathing)
        4. Maximize sleep quality
        5. Minimize inflammatory burden
    PLUS: Keeper presence whenever possible.
    """
    recs = []
    priority = 1

    # --- STATE-DEPENDENT top message ---
    if state == "edge":
        recs.append({
            "priority": 0,
            "category": "state",
            "message": (
                "You are at the edge. This is where life happens. "
                "Maximum vitality. Respect it. Protect it."
            ),
            "action": "maintain",
            "urgency": "none",
        })
    elif state == "collapsed":
        recs.append({
            "priority": 0,
            "category": "state",
            "message": (
                "You are past the cliff. gamma_eff > gamma_c. "
                "Every intervention below is physics — use them. "
                "This is reversible."
            ),
            "action": "intervene_now",
            "urgency": "high",
        })
    elif state == "warning":
        recs.append({
            "priority": 0,
            "category": "state",
            "message": (
                "Warning zone. gamma_eff is above gamma_c. "
                "The window is closing. Act on the interventions below."
            ),
            "action": "intervene",
            "urgency": "medium",
        })
    elif state == "approaching":
        recs.append({
            "priority": 0,
            "category": "state",
            "message": (
                "Approaching the edge. You are inside the window. "
                "Keep doing what you are doing. "
                "Susceptibility is enhanced — interventions work at amplified power."
            ),
            "action": "continue",
            "urgency": "low",
        })
    elif state == "frozen":
        recs.append({
            "priority": 0,
            "category": "state",
            "message": (
                "You are frozen — too little noise. "
                "Life needs some chaos to find the edge. "
                "Move. Challenge yourself gently."
            ),
            "action": "increase_stimulation",
            "urgency": "low",
        })

    # --- Sleep ---
    sleep_hours = today_data.get("sleep_hours", 7.0)
    sleep_quality = today_data.get("sleep_quality", 0.7)
    if sleep_hours < 6 or sleep_quality < 0.5:
        recs.append({
            "priority": priority,
            "category": "sleep",
            "message": (
                f"Sleep: {sleep_hours:.1f}h at {sleep_quality:.0%} quality. "
                "Sleep is Landauer erasure — your brain clears decoherence debt "
                "during SWS. Amyloid-beta accumulation IS incomplete neural erasure. "
                "Non-negotiable."
            ),
            "action": "improve_sleep",
            "urgency": "high" if sleep_hours < 5 else "medium",
        })
        priority += 1

    # --- Breathing ---
    breathing_today = today_data.get("breathing_sessions", 0)
    if breathing_today < 2:
        recs.append({
            "priority": priority,
            "category": "breathing",
            "message": (
                f"Breathing sessions today: {breathing_today}. "
                "Target: 2+. Resonance breathing at 0.1 Hz activates "
                "baroreflex resonance and vagal tone optimization. "
                "Cost: $0. Risk: zero. Time: 10 minutes."
            ),
            "action": "start_breathing",
            "urgency": "medium" if state in ("warning", "collapsed") else "low",
        })
        priority += 1

    # --- 40 Hz Gamma ---
    gamma40_today = today_data.get("gamma40_sessions", 0)
    if gamma40_today < 1:
        recs.append({
            "priority": priority,
            "category": "gamma40",
            "message": (
                f"40 Hz sessions today: {gamma40_today}. "
                "Target: 1+. 40 Hz flicker activates VIP interneurons and "
                "glymphatic clearance. Tsai Lab (Nature, 2024) confirmed mechanism. "
                "Phase III trial ongoing. Cost: $15-30 DIY."
            ),
            "action": "start_gamma40",
            "urgency": "medium" if state in ("warning", "collapsed") else "low",
        })
        priority += 1

    # --- Exercise ---
    exercise = today_data.get("exercise_minutes", 0)
    if exercise < 20:
        recs.append({
            "priority": priority,
            "category": "exercise",
            "message": (
                f"Exercise today: {exercise} minutes. "
                "Movement reduces inflammatory noise and improves HRV. "
                "Even 20 minutes of walking shifts the equation."
            ),
            "action": "exercise",
            "urgency": "low",
        })
        priority += 1

    # --- Stress ---
    stress = today_data.get("stress_level", 0.3)
    if stress > 0.6:
        recs.append({
            "priority": priority,
            "category": "stress",
            "message": (
                f"Stress level: {stress:.0%}. "
                "Stress is additive noise — gamma_stress enters the same equation "
                "as infection and inflammation (Paper II.2). "
                "Breathing, meditation, or keeper contact will reduce it."
            ),
            "action": "reduce_stress",
            "urgency": "high" if stress > 0.8 else "medium",
        })
        priority += 1

    # --- Inflammation ---
    inflammation = today_data.get("inflammation", 0.1)
    if inflammation > 0.4:
        urgency = "high" if inflammation > 0.7 else "medium"
        msg = (
            f"Inflammation: {inflammation:.0%}. "
            "Cytokine load directly raises gamma_eff. "
        )
        if inflammation > 0.8:
            msg += (
                "APPROACHING CYTOKINE TIPPING POINT (gamma_0 = 0.010). "
                "Reduce inflammatory burden immediately: anti-inflammatory diet, "
                "movement, sleep, stress reduction."
            )
        else:
            msg += "Diet, movement, and sleep will lower this."
        recs.append({
            "priority": priority,
            "category": "inflammation",
            "message": msg,
            "action": "reduce_inflammation",
            "urgency": urgency,
        })
        priority += 1

    # --- Keeper ---
    if not profile.get("has_keeper"):
        recs.append({
            "priority": priority,
            "category": "keeper",
            "message": (
                "No keeper registered. A bonded human is a frequency-selective filter. "
                "Love = the willing payment of Landauer cost for another. "
                "Not metaphor. Thermodynamics (Paper 45)."
            ),
            "action": "find_keeper",
            "urgency": "low",
        })
        priority += 1

    # --- ACE awareness ---
    ace = profile.get("ace_score", 0)
    if ace >= 4:
        ace_coh = physics.ace_coherence(ace)
        recs.append({
            "priority": priority,
            "category": "ace",
            "message": (
                f"ACE score: {ace}. Baseline coherence: {ace_coh:.2f}. "
                "Each ACE is a permanent increase in tissue-specific gamma_eff "
                "(Anderson localization, Paper 24). The window is narrower but "
                "NOT closed. Every intervention helps MORE for you because "
                "susceptibility is enhanced at 94% of T_c."
            ),
            "action": "acknowledge",
            "urgency": "info",
        })
        priority += 1

    # --- Cardiac history + geomag ---
    if profile.get("cardiac_history"):
        recs.append({
            "priority": priority,
            "category": "cardiac_geomag",
            "message": (
                "Cardiac history flagged. "
                "Geomagnetic storms (G2+) increase cardiac gamma_eff. "
                "NOAA data is FREE. Check /api/geomag before high-exertion days."
            ),
            "action": "monitor_geomag",
            "urgency": "info",
        })
        priority += 1

    return recs


# ---------------------------------------------------------------------------
# GEOMAG STUB (until modules.geomag_monitor is ready)
# ---------------------------------------------------------------------------

def _get_geomag_data():
    """
    Get geomagnetic data. Uses module if available, otherwise returns
    cached data or defaults.
    """
    if _HAS_GEOMAG:
        try:
            monitor = GeomagMonitor()
            return monitor.get_current()
        except Exception as exc:
            log.warning("GeomagMonitor failed: %s — using cache/defaults", exc)

    # Check cache
    with get_db() as conn:
        row = conn.execute(
            "SELECT kp, storm_level, alert, raw_data FROM geomag_cache "
            "ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        if row:
            age_check = conn.execute(
                "SELECT timestamp FROM geomag_cache ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
            if age_check:
                try:
                    cached_time = datetime.fromisoformat(age_check["timestamp"])
                    now = datetime.now()
                    if (now - cached_time).total_seconds() < 3600:
                        return {
                            "kp": row["kp"],
                            "storm": row["storm_level"],
                            "alert": row["alert"],
                            "source": "cache",
                        }
                except (ValueError, TypeError):
                    pass

    # Default: quiet conditions
    return {
        "kp": 2.0,
        "storm": "G0",
        "alert": None,
        "source": "default",
        "note": "Live NOAA feed not yet connected. Install geomag_monitor module.",
    }


def _geomag_cardiac_risk(kp, has_cardiac_history=False, ace_score=0):
    """
    Compute cardiac risk factor from geomagnetic activity.
    Paper 25: 1.29x population-averaged relative risk during storms.
    High-ACE + cardiac history patients are near gamma_c.
    """
    kp_int = min(int(kp), 9)
    gamma_delta = STORM_LEVELS[kp_int]["gamma_delta"]
    base_risk = 1.0 + (gamma_delta / GAMMA_C) * 2.0

    if has_cardiac_history:
        base_risk *= 1.5
    if ace_score >= 4:
        base_risk *= 1.2

    return round(base_risk, 3)


# ---------------------------------------------------------------------------
# ANTI-ZENO GUARD (Paper 50)
# ---------------------------------------------------------------------------

def _record_app_check(user_id, endpoint):
    """Record that the user checked the app."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO app_checks (user_id, endpoint) VALUES (?, ?)",
            (user_id, endpoint),
        )


def _get_check_count_today(user_id):
    """Count how many times the user has checked the app today."""
    today_start = datetime.now().strftime("%Y-%m-%d 00:00:00")
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM app_checks "
            "WHERE user_id = ? AND timestamp >= ?",
            (user_id, today_start),
        ).fetchone()
        return row["cnt"] if row else 0


def _anti_zeno_check(user_id):
    """
    Return anti-Zeno warning if user is checking too frequently.

    Paper 50: Frequent observation can accelerate collapse (anti-Zeno effect).
    The more you measure, the more you collapse.
    """
    count = _get_check_count_today(user_id)
    if count > ANTI_ZENO_MAX_CHECKS_PER_DAY:
        return {
            "anti_zeno_warning": True,
            "checks_today": count,
            "max_recommended": ANTI_ZENO_MAX_CHECKS_PER_DAY,
            "message": ANTI_ZENO_MESSAGE,
            "paper": "Paper 50: The Anti-Zeno Effect and the Coherence Trap",
        }
    return None


# ---------------------------------------------------------------------------
# FLASK APP
# ---------------------------------------------------------------------------

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
app = Flask(__name__, template_folder=TEMPLATE_DIR)
app.config["JSON_SORT_KEYS"] = False


@app.route("/")
@app.route("/dashboard")
def serve_dashboard():
    """Serve the Coherence dashboard."""
    return send_from_directory(TEMPLATE_DIR, "index.html")


def json_response(data, status=200):
    """Standardized JSON response wrapper."""
    resp = {
        "app": APP_NAME,
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    resp.update(data)
    return jsonify(resp), status


def error_response(message, status=400, details=None):
    """Standardized error response."""
    payload = {"error": True, "message": message}
    if details:
        payload["details"] = details
    return json_response(payload, status)


def require_json(f):
    """Decorator to ensure request has JSON body."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not request.is_json:
            return error_response("Request must be JSON", 415)
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------------

# ---- POST /api/check (Anti-Zeno server-side tracking, Paper 50) ----

@app.route("/api/check", methods=["POST"])
def record_check():
    """
    Record that the user opened the app. Returns daily count and limit.
    Paper 50: frequent measurement accelerates decoherence (anti-Zeno).
    The 6-check/day limit is a physics constraint, not a UX nudge.
    """
    try:
        user_id = 1  # single-user for now
        _record_app_check(user_id, "/api/check")
        count = _get_check_count_today(user_id)
        return json_response({
            "count": count,
            "limit": ANTI_ZENO_MAX_CHECKS_PER_DAY,
            "at_limit": count >= ANTI_ZENO_MAX_CHECKS_PER_DAY,
            "message": ANTI_ZENO_MESSAGE if count >= ANTI_ZENO_MAX_CHECKS_PER_DAY else None,
        })
    except Exception as exc:
        log.exception("Error recording check")
        return error_response(f"Internal error: {exc}", 500)


# ---- POST /api/reading ----

@app.route("/api/reading", methods=["POST"])
@require_json
def post_reading():
    """
    Submit a daily reading. Computes full CoherenceReport.

    Body: {hrv_rmssd, hrv_sdnn, hrv_sampen, sleep_hours, sleep_quality,
           stress_level, inflammation, exercise_minutes, meditation_minutes,
           breathing_sessions, nir_sessions, gamma40_sessions}

    Returns: {gamma_eff, gamma_c, C, V, W, state, lambda_l, recommendations}
    """
    try:
        data = request.get_json()

        # Fetch user profile for ACE, keeper info
        with get_db() as conn:
            user = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()

        ace_score = user["ace_score"] if user else 0
        has_keeper = bool(user["has_keeper"]) if user else False
        keeper_bond = user["keeper_bond"] if user else 0.0

        # Get geomag
        geomag = _get_geomag_data()
        geomag_kp = geomag.get("kp", 2.0)

        # Extract reading values with defaults
        hrv_rmssd = float(data.get("hrv_rmssd", 40.0))
        hrv_sdnn = float(data.get("hrv_sdnn", 50.0))
        hrv_sampen = float(data.get("hrv_sampen", 1.5))
        sleep_hours = float(data.get("sleep_hours", 7.0))
        sleep_quality = float(data.get("sleep_quality", 0.7))
        stress_level = float(data.get("stress_level", 0.3))
        inflammation = float(data.get("inflammation", 0.1))
        exercise_minutes = float(data.get("exercise_minutes", 0.0))
        meditation_minutes = float(data.get("meditation_minutes", 0.0))
        breathing_sess = int(data.get("breathing_sessions", 0))
        nir_sess = int(data.get("nir_sessions", 0))
        gamma40_sess = int(data.get("gamma40_sessions", 0))

        # Compute physics
        gamma_eff = physics.compute_gamma_eff(
            hrv_rmssd=hrv_rmssd,
            hrv_sdnn=hrv_sdnn,
            hrv_sampen=hrv_sampen,
            sleep_hours=sleep_hours,
            sleep_quality=sleep_quality,
            stress_level=stress_level,
            inflammation=inflammation,
            exercise_minutes=exercise_minutes,
            meditation_minutes=meditation_minutes,
            breathing_sessions=breathing_sess,
            nir_sessions=nir_sess,
            gamma40_sessions=gamma40_sess,
            ace_score=ace_score,
            has_keeper=has_keeper,
            keeper_bond=keeper_bond,
            geomag_kp=geomag_kp,
        )

        C = physics.coherence(gamma_eff)
        V = physics.vitality(gamma_eff)
        W = physics.window(gamma_eff)
        state, lambda_l = physics.classify_state(gamma_eff)

        # Today data for recommendations
        today_data = {
            "sleep_hours": sleep_hours,
            "sleep_quality": sleep_quality,
            "stress_level": stress_level,
            "inflammation": inflammation,
            "exercise_minutes": exercise_minutes,
            "breathing_sessions": breathing_sess,
            "gamma40_sessions": gamma40_sess,
        }

        profile = {
            "ace_score": ace_score,
            "has_keeper": has_keeper,
            "cardiac_history": bool(user["cardiac_history"]) if user else False,
        }

        recommendations = generate_recommendations(
            gamma_eff, state, lambda_l, today_data, profile
        )

        # Store reading
        recs_json = json.dumps(recommendations)
        with get_db() as conn:
            conn.execute(
                """INSERT INTO readings
                   (user_id, hrv_rmssd, hrv_sdnn, hrv_sampen,
                    sleep_hours, sleep_quality, stress_level, inflammation,
                    exercise_minutes, meditation_minutes,
                    breathing_sessions, nir_sessions, gamma40_sessions,
                    gamma_eff, gamma_c, coherence, vitality, window,
                    state, lambda_l, recommendations)
                   VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    hrv_rmssd, hrv_sdnn, hrv_sampen,
                    sleep_hours, sleep_quality, stress_level, inflammation,
                    exercise_minutes, meditation_minutes,
                    breathing_sess, nir_sess, gamma40_sess,
                    gamma_eff, GAMMA_C, C, V, W,
                    state, lambda_l, recs_json,
                ),
            )

        # Anti-Zeno check
        _record_app_check(1, "/api/reading")
        anti_zeno = _anti_zeno_check(1)

        result = {
            "reading": {
                "gamma_eff": round(gamma_eff, 6),
                "gamma_c": GAMMA_C,
                "C": round(C, 6),
                "V": round(V, 6),
                "W": round(W, 6),
                "state": state,
                "lambda_l": lambda_l,
                "susceptibility": round(physics.susceptibility(gamma_eff), 2),
                "vitality_pct": round(V / physics.vitality_max() * 100, 1),
            },
            "recommendations": recommendations,
            "geomag": {
                "kp": geomag_kp,
                "storm": geomag.get("storm", "G0"),
                "cardiac_risk_factor": _geomag_cardiac_risk(
                    geomag_kp,
                    has_cardiac_history=profile.get("cardiac_history", False),
                    ace_score=ace_score,
                ),
            },
        }

        if anti_zeno:
            result["anti_zeno"] = anti_zeno

        log.info(
            "Reading: gamma_eff=%.4f, C=%.4f, V=%.6f, W=%.4f, state=%s",
            gamma_eff, C, V, W, state,
        )

        return json_response(result)

    except (ValueError, TypeError, KeyError) as exc:
        log.error("Bad reading data: %s", exc)
        return error_response(f"Invalid reading data: {exc}", 400)
    except Exception as exc:
        log.exception("Error processing reading")
        return error_response(f"Internal error: {exc}", 500)


# ---- GET /api/profile ----

@app.route("/api/profile", methods=["GET"])
def get_profile():
    """Return user profile including ACE, baseline, keeper info."""
    try:
        with get_db() as conn:
            user = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()

        if not user:
            return error_response("No profile found", 404)

        ace_score = user["ace_score"]
        ace_coh = physics.ace_coherence(ace_score)

        profile = {
            "profile": {
                "name": user["name"],
                "age": user["age"],
                "ace_score": ace_score,
                "ace_baseline_coherence": round(ace_coh, 4),
                "ace_localization_length": round(1.0 / ACE_BETA, 2) if ace_score > 0 else None,
                "has_keeper": bool(user["has_keeper"]),
                "keeper_bond": user["keeper_bond"],
                "cardiac_history": bool(user["cardiac_history"]),
                "created_at": user["created_at"],
                "updated_at": user["updated_at"],
            },
            "constants": {
                "gamma_c": GAMMA_C,
                "alpha": round(ALPHA, 4),
                "T_body": T_BODY,
                "T_c": T_C,
                "W_ginzburg": round(W_GINZBURG, 4),
                "ace_beta": ACE_BETA,
                "ace_nu": ACE_NU,
            },
        }

        return json_response(profile)

    except Exception as exc:
        log.exception("Error fetching profile")
        return error_response(f"Internal error: {exc}", 500)


# ---- POST /api/profile ----

@app.route("/api/profile", methods=["POST"])
@require_json
def update_profile():
    """
    Update user profile.
    Body: {ace_score, age, has_keeper, keeper_bond, cardiac_history, name}
    """
    try:
        data = request.get_json()

        fields = []
        values = []

        for field, col_type in [
            ("name", str),
            ("ace_score", int),
            ("age", int),
            ("has_keeper", lambda x: 1 if x else 0),
            ("keeper_bond", float),
            ("cardiac_history", lambda x: 1 if x else 0),
        ]:
            if field in data:
                fields.append(f"{field} = ?")
                values.append(col_type(data[field]))

        if not fields:
            return error_response("No valid fields provided", 400)

        fields.append("updated_at = datetime('now')")
        values.append(1)  # user_id

        sql = f"UPDATE users SET {', '.join(fields)} WHERE id = ?"

        with get_db() as conn:
            conn.execute(sql, values)

        log.info("Profile updated: %s", list(data.keys()))
        return json_response({"updated": True, "fields": list(data.keys())})

    except Exception as exc:
        log.exception("Error updating profile")
        return error_response(f"Internal error: {exc}", 500)


# ---- GET /api/geomag ----

@app.route("/api/geomag", methods=["GET"])
def get_geomag():
    """
    Return current geomagnetic conditions.
    Kp index, storm level, alert status, cardiac risk factor.

    Paper 25: Earth's magnetosphere is a planetary-scale Debye shield.
    During storms, shield degrades -> ELF/VLF noise increases in
    0.001-100 Hz band -> overlaps cardiac pacemaker frequency (1 Hz).
    """
    try:
        geomag = _get_geomag_data()

        with get_db() as conn:
            user = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()

        has_cardiac = bool(user["cardiac_history"]) if user else False
        ace_score = user["ace_score"] if user else 0
        kp = geomag.get("kp", 2.0)

        kp_int = min(int(kp), 9)
        storm_info = STORM_LEVELS[kp_int]

        alert = None
        if kp >= 5 and has_cardiac:
            alert = (
                "CARDIAC ALERT: Geomagnetic storm G2+. "
                "Your cardiac history puts you near gamma_c. "
                "Avoid high exertion. Stay hydrated. Breathe at 0.1 Hz."
            )
        elif kp >= 7:
            alert = (
                "GEOMAGNETIC STORM G3+. All users: monitor symptoms. "
                "HRV may decrease. Susceptibility enhanced at 94% of T_c."
            )

        result = {
            "geomag": {
                "kp": kp,
                "storm": storm_info["label"],
                "storm_description": storm_info["description"],
                "gamma_delta": storm_info["gamma_delta"],
                "alert": alert,
                "cardiac_risk_factor": _geomag_cardiac_risk(
                    kp, has_cardiac, ace_score
                ),
                "source": geomag.get("source", "unknown"),
            },
            "physics": {
                "mechanism": (
                    "Magnetosphere degradation during storms increases "
                    "ELF/VLF noise in 0.001-100 Hz band, overlapping "
                    "cardiac pacemaker frequency (1 Hz) and neural oscillations."
                ),
                "paper": "Paper 25: Geomagnetic Cardiac Shield",
                "data": "44M deaths analyzed. Correlation CONFIRMED.",
                "note": (
                    "Direct quantum coupling excluded by 15 orders of magnitude. "
                    "Indirect mechanisms (atmospheric electricity, cosmic ray flux) "
                    "are the pathway."
                ),
            },
        }

        return json_response(result)

    except Exception as exc:
        log.exception("Error fetching geomag data")
        return error_response(f"Internal error: {exc}", 500)


# ---- GET /api/history ----

@app.route("/api/history", methods=["GET"])
def get_history():
    """Return last 30 days of readings with trends."""
    try:
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime(
            "%Y-%m-%d 00:00:00"
        )

        with get_db() as conn:
            rows = conn.execute(
                """SELECT timestamp, gamma_eff, gamma_c, coherence, vitality,
                          window, state, lambda_l, sleep_hours, sleep_quality,
                          stress_level, exercise_minutes, breathing_sessions,
                          gamma40_sessions
                   FROM readings
                   WHERE user_id = 1 AND timestamp >= ?
                   ORDER BY timestamp ASC""",
                (thirty_days_ago,),
            ).fetchall()

        readings = []
        gamma_effs = []
        coherences = []
        vitalities = []

        for row in rows:
            entry = dict(row)
            readings.append(entry)
            if entry["gamma_eff"] is not None:
                gamma_effs.append(entry["gamma_eff"])
            if entry["coherence"] is not None:
                coherences.append(entry["coherence"])
            if entry["vitality"] is not None:
                vitalities.append(entry["vitality"])

        # Compute trends
        trends = {}
        if len(gamma_effs) >= 2:
            recent = gamma_effs[-min(7, len(gamma_effs)):]
            older = gamma_effs[: max(1, len(gamma_effs) - 7)]
            avg_recent = sum(recent) / len(recent)
            avg_older = sum(older) / len(older)
            delta = avg_recent - avg_older

            if delta > 0.003:
                trends["gamma_eff"] = "worsening"
            elif delta < -0.003:
                trends["gamma_eff"] = "improving"
            else:
                trends["gamma_eff"] = "stable"

            trends["gamma_eff_delta_per_day"] = round(
                delta / max(len(recent), 1), 6
            )

            # Time to cliff estimate
            ttc = physics.time_to_cliff(avg_recent, max(delta, 0) / max(len(recent), 1))
            trends["time_to_cliff_days"] = round(ttc, 1) if ttc is not None else None

        if len(coherences) >= 2:
            recent_c = coherences[-min(7, len(coherences)):]
            older_c = coherences[: max(1, len(coherences) - 7)]
            delta_c = sum(recent_c) / len(recent_c) - sum(older_c) / len(older_c)
            if delta_c > 0.01:
                trends["coherence"] = "improving"
            elif delta_c < -0.01:
                trends["coherence"] = "worsening"
            else:
                trends["coherence"] = "stable"

        result = {
            "history": {
                "days": len(readings),
                "readings": readings,
                "trends": trends,
            },
            "summary": {
                "avg_gamma_eff": round(sum(gamma_effs) / len(gamma_effs), 6) if gamma_effs else None,
                "avg_coherence": round(sum(coherences) / len(coherences), 4) if coherences else None,
                "avg_vitality": round(sum(vitalities) / len(vitalities), 6) if vitalities else None,
                "min_gamma_eff": round(min(gamma_effs), 6) if gamma_effs else None,
                "max_gamma_eff": round(max(gamma_effs), 6) if gamma_effs else None,
                "best_state": "edge" if any(r.get("state") == "edge" for r in readings) else "none",
            },
        }

        return json_response(result)

    except Exception as exc:
        log.exception("Error fetching history")
        return error_response(f"Internal error: {exc}", 500)


# ---- POST /api/breathing/start ----

@app.route("/api/breathing/start", methods=["POST"])
@require_json
def breathing_start():
    """
    Start a breathing session.
    Body: {pattern: "resonance"/"box"/"calm"/"prayer", duration_minutes}

    Returns session config with timing and physics explanation.
    """
    try:
        data = request.get_json()
        pattern = data.get("pattern", "resonance")
        duration = float(data.get("duration_minutes", 10.0))

        if pattern not in BREATHING_PATTERNS:
            return error_response(
                f"Unknown pattern: {pattern}. "
                f"Available: {', '.join(BREATHING_PATTERNS.keys())}",
                400,
            )

        duration = max(1.0, min(duration, 60.0))
        session_id = str(uuid.uuid4())
        config = BREATHING_PATTERNS[pattern].copy()

        # Calculate total cycles
        cycle_sec = (
            config["inhale_sec"]
            + config["hold_in_sec"]
            + config["exhale_sec"]
            + config["hold_out_sec"]
        )
        total_cycles = int((duration * 60) / cycle_sec)

        with get_db() as conn:
            conn.execute(
                """INSERT INTO breathing_sessions
                   (id, user_id, pattern, duration_minutes)
                   VALUES (?, 1, ?, ?)""",
                (session_id, pattern, duration),
            )

        result = {
            "session": {
                "id": session_id,
                "pattern": pattern,
                "config": config,
                "duration_minutes": duration,
                "total_cycles": total_cycles,
                "cycle_seconds": cycle_sec,
            },
            "physics": {
                "mechanism": (
                    "0.1 Hz breathing activates baroreflex resonance. "
                    "Vagal tone optimization reduces gamma_eff systemically. "
                    "Autonomic-immune coupling pathway confirmed."
                ),
                "evidence": "Bernardi (BMJ, 2001), HeartMath (1.8M sessions)",
                "cost": "$0",
                "risk": "zero",
            },
        }

        log.info("Breathing session started: %s, pattern=%s", session_id, pattern)
        return json_response(result)

    except Exception as exc:
        log.exception("Error starting breathing session")
        return error_response(f"Internal error: {exc}", 500)


# ---- POST /api/breathing/complete ----

@app.route("/api/breathing/complete", methods=["POST"])
@require_json
def breathing_complete():
    """
    Log breathing session completion.
    Body: {session_id, completed}
    """
    try:
        data = request.get_json()
        session_id = data.get("session_id")
        completed = bool(data.get("completed", True))

        if not session_id:
            return error_response("session_id required", 400)

        with get_db() as conn:
            existing = conn.execute(
                "SELECT * FROM breathing_sessions WHERE id = ?", (session_id,)
            ).fetchone()

            if not existing:
                return error_response("Session not found", 404)

            conn.execute(
                """UPDATE breathing_sessions
                   SET completed = ?, completed_at = datetime('now')
                   WHERE id = ?""",
                (1 if completed else 0, session_id),
            )

        status = "completed" if completed else "abandoned"
        log.info("Breathing session %s: %s", status, session_id)

        return json_response({
            "session_id": session_id,
            "status": status,
            "message": (
                "Session logged. Your vagal tone thanks you."
                if completed
                else "Session logged. Any breathing is better than none."
            ),
        })

    except Exception as exc:
        log.exception("Error completing breathing session")
        return error_response(f"Internal error: {exc}", 500)


# ---- POST /api/gamma40/start ----

@app.route("/api/gamma40/start", methods=["POST"])
@require_json
def gamma40_start():
    """
    Start a 40 Hz gamma stimulation session.
    Body: {duration_minutes, mode: "audio"/"visual"/"both"}

    Returns session config.
    """
    try:
        data = request.get_json()
        mode = data.get("mode", "both")
        duration = float(data.get("duration_minutes", 30.0))

        if mode not in GAMMA40_MODES:
            return error_response(
                f"Unknown mode: {mode}. Available: {', '.join(GAMMA40_MODES.keys())}",
                400,
            )

        duration = max(5.0, min(duration, 120.0))
        session_id = str(uuid.uuid4())
        config = GAMMA40_MODES[mode].copy()

        with get_db() as conn:
            conn.execute(
                """INSERT INTO gamma40_sessions
                   (id, user_id, mode, duration_minutes)
                   VALUES (?, 1, ?, ?)""",
                (session_id, mode, duration),
            )

        result = {
            "session": {
                "id": session_id,
                "mode": mode,
                "config": config,
                "duration_minutes": duration,
            },
            "physics": {
                "mechanism": (
                    "40 Hz flicker entrains VIP interneurons, activating "
                    "glymphatic clearance. Amyloid-beta and tau cleared. "
                    "Hippocampal coherence restored. Bootstrap loop restarts."
                ),
                "evidence": (
                    "Iaccarino (Nature, 2016), Martorell (Cell, 2019), "
                    "Tsai Lab (Nature, 2024). Phase III: NCT04912531."
                ),
                "contraindication": "Photosensitive epilepsy ONLY (visual mode).",
                "protocol": "1 hour/day, 3 months minimum for Alzheimer's protocol.",
            },
            "safety": {
                "epilepsy_check": (
                    "If you have photosensitive epilepsy, use audio-only mode. "
                    "If unsure, consult your physician before visual stimulation."
                ),
            },
        }

        log.info("Gamma40 session started: %s, mode=%s", session_id, mode)
        return json_response(result)

    except Exception as exc:
        log.exception("Error starting gamma40 session")
        return error_response(f"Internal error: {exc}", 500)


# ---- POST /api/gamma40/complete ----

@app.route("/api/gamma40/complete", methods=["POST"])
@require_json
def gamma40_complete():
    """
    Log gamma40 session completion.
    Body: {session_id, completed}
    """
    try:
        data = request.get_json()
        session_id = data.get("session_id")
        completed = bool(data.get("completed", True))

        if not session_id:
            return error_response("session_id required", 400)

        with get_db() as conn:
            existing = conn.execute(
                "SELECT * FROM gamma40_sessions WHERE id = ?", (session_id,)
            ).fetchone()

            if not existing:
                return error_response("Session not found", 404)

            conn.execute(
                """UPDATE gamma40_sessions
                   SET completed = ?, completed_at = datetime('now')
                   WHERE id = ?""",
                (1 if completed else 0, session_id),
            )

        status = "completed" if completed else "abandoned"
        log.info("Gamma40 session %s: %s", status, session_id)

        return json_response({
            "session_id": session_id,
            "status": status,
            "message": (
                "Session logged. Glymphatic clearance activated."
                if completed
                else "Session logged. Partial sessions still provide benefit."
            ),
        })

    except Exception as exc:
        log.exception("Error completing gamma40 session")
        return error_response(f"Internal error: {exc}", 500)


# ---- GET /api/phase_diagram ----

@app.route("/api/phase_diagram", methods=["GET"])
def get_phase_diagram():
    """
    Return current position on Wike phase diagram with history trail.

    Three states:
        Frozen:    gamma_eff << gamma_c, lambda_L < 0
        Edge:      gamma_eff ~ gamma_c,  lambda_L ~ 0
        Collapsed: gamma_eff >> gamma_c,  lambda_L > 0

    Phase diagram axes:
        X = gamma_eff (decoherence rate)
        Y = coherence C
    """
    try:
        with get_db() as conn:
            # Get last reading
            latest = conn.execute(
                """SELECT gamma_eff, coherence, vitality, state, lambda_l
                   FROM readings WHERE user_id = 1
                   ORDER BY timestamp DESC LIMIT 1"""
            ).fetchone()

            # Get trail (last 30 readings)
            trail = conn.execute(
                """SELECT timestamp, gamma_eff, coherence, state
                   FROM readings WHERE user_id = 1
                   ORDER BY timestamp DESC LIMIT 30"""
            ).fetchall()

        if not latest:
            return json_response({
                "phase_diagram": {
                    "position": None,
                    "message": "No readings yet. Submit a reading first.",
                },
            })

        gamma_eff = latest["gamma_eff"]
        C = latest["coherence"]

        # Compute the full phase curve for reference
        phase_curve = []
        for g in [i * 0.002 for i in range(1, 80)]:
            phase_curve.append({
                "gamma_eff": round(g, 4),
                "coherence": round(physics.coherence(g), 6),
                "vitality": round(physics.vitality(g), 6),
            })

        # History trail
        trail_points = []
        for row in reversed(list(trail)):
            trail_points.append({
                "timestamp": row["timestamp"],
                "x": row["gamma_eff"],
                "y": row["coherence"],
                "state": row["state"],
            })

        result = {
            "phase_diagram": {
                "position": {
                    "x": round(gamma_eff, 6),
                    "y": round(C, 6),
                    "state": latest["state"],
                    "lambda_l": latest["lambda_l"],
                },
                "critical_point": {
                    "x": GAMMA_C,
                    "y": round(physics.coherence(GAMMA_C), 6),
                    "label": "gamma_c = 0.0622 (Berry Phase threshold)",
                },
                "trail": trail_points,
                "reference_curve": phase_curve,
                "zones": {
                    "frozen": {
                        "range": "gamma_eff < 0.031",
                        "description": (
                            "Crystal. Coma. Depression. Laminar flow. "
                            "Too little noise. Lambda_L < 0."
                        ),
                    },
                    "edge": {
                        "range": "0.053 < gamma_eff < 0.072",
                        "description": (
                            "Life. Consciousness. Flow state. Fractal 1/f. "
                            "Maximum vitality. Lambda_L ~ 0."
                        ),
                    },
                    "collapsed": {
                        "range": "gamma_eff > 0.093",
                        "description": (
                            "Fire. Seizure. Panic. Fibrillation. Turbulence. "
                            "Too much noise. Lambda_L > 0."
                        ),
                    },
                },
            },
        }

        _record_app_check(1, "/api/phase_diagram")
        anti_zeno = _anti_zeno_check(1)
        if anti_zeno:
            result["anti_zeno"] = anti_zeno

        return json_response(result)

    except Exception as exc:
        log.exception("Error fetching phase diagram")
        return error_response(f"Internal error: {exc}", 500)


# ---- GET /api/window ----

@app.route("/api/window", methods=["GET"])
def get_window():
    """
    Return the window: W = gamma_c - gamma_eff.

    Paper VII.3:
        W > 0: inside the window. Restoring forces at 33x power.
        W = 0: at the cliff. Metastable.
        W < 0: outside the window. Collapse underway.
    """
    try:
        with get_db() as conn:
            latest = conn.execute(
                """SELECT gamma_eff, gamma_c, window, state, timestamp
                   FROM readings WHERE user_id = 1
                   ORDER BY timestamp DESC LIMIT 1"""
            ).fetchone()

            # Get recent for trend
            recent = conn.execute(
                """SELECT gamma_eff, timestamp
                   FROM readings WHERE user_id = 1
                   ORDER BY timestamp DESC LIMIT 7"""
            ).fetchall()

        if not latest:
            return json_response({
                "window": {
                    "W": None,
                    "message": "No readings yet.",
                },
            })

        gamma_eff = latest["gamma_eff"]
        W = latest["window"]

        # Trend
        trend = "unknown"
        ttc = None
        if len(recent) >= 2:
            gammas = [r["gamma_eff"] for r in reversed(list(recent))]
            if len(gammas) >= 3:
                recent_avg = sum(gammas[-3:]) / 3
                older_avg = sum(gammas[:max(1, len(gammas) - 3)]) / max(
                    1, len(gammas) - 3
                )
                delta = recent_avg - older_avg
                if delta > 0.002:
                    trend = "narrowing"
                elif delta < -0.002:
                    trend = "widening"
                else:
                    trend = "stable"

                daily_rate = delta / max(len(gammas) - 1, 1)
                ttc = physics.time_to_cliff(gamma_eff, max(daily_rate, 0))

        # Susceptibility at current position
        chi = physics.susceptibility(gamma_eff)

        result = {
            "window": {
                "W": round(W, 6),
                "W_pct": round(W / GAMMA_C * 100, 1),
                "gamma_eff": round(gamma_eff, 6),
                "gamma_c": GAMMA_C,
                "trend": trend,
                "time_to_cliff_days": round(ttc, 1) if ttc is not None else None,
                "susceptibility": round(chi, 2),
                "state": latest["state"],
            },
            "interpretation": {
                "inside": W > 0,
                "message": (
                    _window_message(W, trend)
                ),
            },
            "physics": {
                "equation": "W = gamma_c - gamma_eff",
                "gamma_c_source": "Berry Phase simulation (QuTiP 5.2.3)",
                "susceptibility_note": (
                    f"At W={W_GINZBURG:.4f} of T_c, susceptibility is enhanced "
                    f"{round(chi, 1)}x. Inside the window, interventions work at "
                    "amplified power."
                ),
            },
        }

        return json_response(result)

    except Exception as exc:
        log.exception("Error fetching window")
        return error_response(f"Internal error: {exc}", 500)


def _window_message(W, trend):
    """Generate human-readable window interpretation."""
    if W > 0.02:
        msg = "Wide window. Strong restoring forces. You have margin."
    elif W > 0.01:
        msg = "Moderate window. Interventions amplified at 33x."
    elif W > 0.005:
        msg = "Narrow window. Approaching the edge. Focus on the Five Interventions."
    elif W > 0:
        msg = (
            "Very narrow window. Near the cliff. "
            "Every intervention matters. Breathing, sleep, keeper contact."
        )
    elif W > -0.01:
        msg = (
            "Just past the cliff. This is reversible. "
            "Activate all five interventions. Get keeper contact."
        )
    else:
        msg = (
            "Outside the window. Collapse region. "
            "Immediate intervention needed: sleep, breathing, "
            "reduce all stressors. Contact your keeper."
        )

    if trend == "narrowing" and W > 0:
        msg += " TREND: Window is narrowing. Pay attention."
    elif trend == "widening":
        msg += " TREND: Window is widening. What you are doing is working."

    return msg


# ---- GET /api/recommendations ----

@app.route("/api/recommendations", methods=["GET"])
def get_recommendations():
    """Return prioritized intervention list based on current state."""
    try:
        with get_db() as conn:
            latest = conn.execute(
                """SELECT gamma_eff, state, lambda_l, sleep_hours, sleep_quality,
                          stress_level, inflammation, exercise_minutes,
                          breathing_sessions, gamma40_sessions
                   FROM readings WHERE user_id = 1
                   ORDER BY timestamp DESC LIMIT 1"""
            ).fetchone()

            user = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()

        if not latest:
            return json_response({
                "recommendations": [{
                    "priority": 0,
                    "category": "onboarding",
                    "message": (
                        "No readings yet. Submit your first reading to get "
                        "personalized recommendations based on your physics."
                    ),
                    "action": "submit_reading",
                    "urgency": "info",
                }],
            })

        today_data = {
            "sleep_hours": latest["sleep_hours"],
            "sleep_quality": latest["sleep_quality"],
            "stress_level": latest["stress_level"],
            "inflammation": latest["inflammation"],
            "exercise_minutes": latest["exercise_minutes"],
            "breathing_sessions": latest["breathing_sessions"],
            "gamma40_sessions": latest["gamma40_sessions"],
        }

        profile = {
            "ace_score": user["ace_score"] if user else 0,
            "has_keeper": bool(user["has_keeper"]) if user else False,
            "cardiac_history": bool(user["cardiac_history"]) if user else False,
        }

        recs = generate_recommendations(
            latest["gamma_eff"],
            latest["state"],
            latest["lambda_l"],
            today_data,
            profile,
        )

        return json_response({"recommendations": recs})

    except Exception as exc:
        log.exception("Error generating recommendations")
        return error_response(f"Internal error: {exc}", 500)


# ---- GET /api/dashboard ----

@app.route("/api/dashboard", methods=["GET"])
def get_dashboard():
    """
    Return everything the frontend needs for the main dashboard.

    This is the primary endpoint. One call gets it all.
    """
    try:
        with get_db() as conn:
            # Latest reading
            latest = conn.execute(
                """SELECT * FROM readings WHERE user_id = 1
                   ORDER BY timestamp DESC LIMIT 1"""
            ).fetchone()

            # User profile
            user = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()

            # Today's sessions
            today_start = datetime.now().strftime("%Y-%m-%d 00:00:00")

            breathing_today = conn.execute(
                """SELECT COUNT(*) as cnt FROM breathing_sessions
                   WHERE user_id = 1 AND completed = 1
                   AND started_at >= ?""",
                (today_start,),
            ).fetchone()["cnt"]

            gamma40_today = conn.execute(
                """SELECT COUNT(*) as cnt FROM gamma40_sessions
                   WHERE user_id = 1 AND completed = 1
                   AND started_at >= ?""",
                (today_start,),
            ).fetchone()["cnt"]

            # 7-day history
            seven_days_ago = (datetime.now() - timedelta(days=7)).strftime(
                "%Y-%m-%d 00:00:00"
            )
            history_7d = conn.execute(
                """SELECT timestamp, gamma_eff, coherence, vitality, window, state
                   FROM readings WHERE user_id = 1 AND timestamp >= ?
                   ORDER BY timestamp ASC""",
                (seven_days_ago,),
            ).fetchall()

        # Geomag
        geomag = _get_geomag_data()

        # Build dashboard
        if latest:
            gamma_eff = latest["gamma_eff"]
            C = latest["coherence"]
            V = latest["vitality"]
            W_val = latest["window"]
            state = latest["state"]
            lambda_l = latest["lambda_l"]

            today_data = {
                "breathing_sessions": breathing_today,
                "gamma40_sessions": gamma40_today,
                "exercise_minutes": latest["exercise_minutes"] or 0,
                "sleep_quality": latest["sleep_quality"] or 0,
                "sleep_hours": latest["sleep_hours"] or 0,
                "stress_level": latest["stress_level"] or 0,
                "inflammation": latest["inflammation"] or 0,
            }

            profile = {
                "ace_score": user["ace_score"] if user else 0,
                "has_keeper": bool(user["has_keeper"]) if user else False,
                "cardiac_history": bool(user["cardiac_history"]) if user else False,
            }

            recs = generate_recommendations(
                gamma_eff, state, lambda_l, today_data, profile
            )

            history_list = []
            for row in history_7d:
                history_list.append({
                    "timestamp": row["timestamp"],
                    "gamma_eff": row["gamma_eff"],
                    "coherence": row["coherence"],
                    "vitality": row["vitality"],
                    "window": row["window"],
                    "state": row["state"],
                })

            dashboard = {
                "coherence": round(C, 4),
                "vitality": round(V, 6),
                "gamma_eff": round(gamma_eff, 6),
                "gamma_c": GAMMA_C,
                "window": round(W_val, 6),
                "state": state,
                "lambda_l": lambda_l,
                "geomag": {
                    "kp": geomag.get("kp", 2.0),
                    "storm": geomag.get("storm", "G0"),
                    "alert": geomag.get("alert"),
                },
                "today": today_data,
                "recommendations": recs,
                "history_7d": history_list,
                "phase_diagram_position": {
                    "x": round(gamma_eff, 6),
                    "y": round(C, 4),
                },
                "vitality_pct": round(V / physics.vitality_max() * 100, 1),
                "susceptibility": round(physics.susceptibility(gamma_eff), 2),
                "last_reading": latest["timestamp"],
            }

        else:
            dashboard = {
                "coherence": None,
                "vitality": None,
                "gamma_eff": None,
                "gamma_c": GAMMA_C,
                "window": None,
                "state": "unknown",
                "lambda_l": None,
                "geomag": {
                    "kp": geomag.get("kp", 2.0),
                    "storm": geomag.get("storm", "G0"),
                    "alert": None,
                },
                "today": {
                    "breathing_sessions": breathing_today,
                    "gamma40_sessions": gamma40_today,
                    "exercise_minutes": 0,
                    "sleep_quality": 0,
                },
                "recommendations": [{
                    "priority": 0,
                    "category": "onboarding",
                    "message": "Welcome to Coherence. Submit your first reading.",
                    "action": "submit_reading",
                    "urgency": "info",
                }],
                "history_7d": [],
                "phase_diagram_position": None,
                "last_reading": None,
            }

        # Anti-Zeno
        _record_app_check(1, "/api/dashboard")
        anti_zeno = _anti_zeno_check(1)
        if anti_zeno:
            dashboard["anti_zeno"] = anti_zeno

        return json_response({"dashboard": dashboard})

    except Exception as exc:
        log.exception("Error building dashboard")
        return error_response(f"Internal error: {exc}", 500)


# ---- GET / (root) ----

@app.route("/", methods=["GET"])
def root():
    """App info and health check."""
    return json_response({
        "name": APP_NAME,
        "tagline": APP_TAGLINE,
        "version": VERSION,
        "author": AUTHOR,
        "engagement_weight": ENGAGEMENT_WEIGHT,
        "philosophy": (
            "This app does NOT optimize for engagement. "
            "It optimizes for the user's gamma_eff approaching gamma_c. "
            "If you are at the edge, the app tells you to put it down."
        ),
        "physics": {
            "coherence_law": "C(t) = C_0 * exp(-alpha * gamma_eff * t)",
            "vitality": "V(gamma) = C_0 * gamma * exp(-alpha * gamma)",
            "gamma_c": GAMMA_C,
            "alpha": round(ALPHA, 4),
            "W_ginzburg": round(W_GINZBURG, 4),
            "T_body": T_BODY,
            "T_c": T_C,
            "source": "51 papers, 13.8M+ data points, zero free parameters",
        },
        "endpoints": [
            "POST /api/reading",
            "GET  /api/profile",
            "POST /api/profile",
            "GET  /api/geomag",
            "GET  /api/history",
            "POST /api/breathing/start",
            "POST /api/breathing/complete",
            "POST /api/gamma40/start",
            "POST /api/gamma40/complete",
            "GET  /api/phase_diagram",
            "GET  /api/window",
            "GET  /api/recommendations",
            "GET  /api/dashboard",
        ],
        "status": "operational",
    })


# ---------------------------------------------------------------------------
# SELF-TEST
# ---------------------------------------------------------------------------

def _self_test():
    """
    Create a mock user and run through all endpoints.
    Validates physics computations, database operations, and endpoint responses.
    """
    print("\n" + "=" * 70)
    print(f"  {APP_NAME} v{VERSION} — Self-Test")
    print(f"  {APP_TAGLINE}")
    print(f"  {AUTHOR}")
    print("=" * 70)

    _ensure_db()

    test_client = app.test_client()
    passed = 0
    failed = 0
    total = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed, total
        total += 1
        if condition:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name} — {detail}")

    # --- Physics unit tests ---
    print("\n--- Physics Engine ---")

    # Coherence law
    C = physics.coherence(GAMMA_C)
    check(
        "Coherence at gamma_c",
        0.35 < C < 0.40,
        f"C={C:.4f}, expected ~0.368 (e^-1)",
    )

    # Vitality at gamma_c is maximum
    V_at_gc = physics.vitality(GAMMA_C)
    V_below = physics.vitality(GAMMA_C * 0.5)
    V_above = physics.vitality(GAMMA_C * 1.5)
    check(
        "Vitality maximum at gamma_c",
        V_at_gc > V_below and V_at_gc > V_above,
        f"V(gc)={V_at_gc:.6f}, V(0.5gc)={V_below:.6f}, V(1.5gc)={V_above:.6f}",
    )

    # V(gamma) = gamma * exp(-alpha * gamma) should have max at gamma = 1/alpha = gamma_c
    V_max = physics.vitality_max()
    check(
        "Vitality max = gamma_c * e^(-1)",
        abs(V_max - GAMMA_C * math.exp(-1)) < 1e-10,
        f"V_max={V_max}, expected={GAMMA_C * math.exp(-1)}",
    )

    # State classification
    state_frozen, ll_frozen = physics.classify_state(0.01)
    state_edge, ll_edge = physics.classify_state(GAMMA_C)
    state_collapsed, ll_collapsed = physics.classify_state(0.15)
    check("State: frozen at gamma=0.01", state_frozen == "frozen")
    check("State: edge at gamma_c", state_edge == "edge")
    check("State: collapsed at gamma=0.15", state_collapsed == "collapsed")
    check("Lambda_L negative when frozen", ll_frozen == "negative")
    check("Lambda_L near_zero at edge", ll_edge == "near_zero")
    check("Lambda_L positive when collapsed", ll_collapsed == "positive")

    # Window
    W = physics.window(GAMMA_C * 0.8)
    check("Window positive inside", W > 0, f"W={W}")
    W_out = physics.window(GAMMA_C * 1.5)
    check("Window negative outside", W_out < 0, f"W={W_out}")

    # ACE coherence
    ace_0 = physics.ace_coherence(0)
    ace_4 = physics.ace_coherence(4)
    ace_8 = physics.ace_coherence(8)
    check("ACE=0 gives full coherence", ace_0 == 1.0)
    check("ACE=4 reduces coherence", ace_4 < 1.0, f"C={ace_4:.4f}")
    check("ACE=8 reduces more", ace_8 < ace_4, f"C8={ace_8:.4f} < C4={ace_4:.4f}")

    # Susceptibility diverges near gamma_c
    chi_far = physics.susceptibility(0.03)
    chi_near = physics.susceptibility(0.06)
    check(
        "Susceptibility increases near gamma_c",
        chi_near > chi_far,
        f"chi_near={chi_near:.1f}, chi_far={chi_far:.1f}",
    )

    # Gamma_eff computation
    gamma_good = physics.compute_gamma_eff(
        hrv_rmssd=60, hrv_sdnn=70, hrv_sampen=1.8,
        sleep_hours=8, sleep_quality=0.9,
        stress_level=0.1, inflammation=0.05,
        exercise_minutes=45, meditation_minutes=20,
        breathing_sessions=2, nir_sessions=1, gamma40_sessions=1,
        ace_score=0, has_keeper=True, keeper_bond=0.8,
    )
    gamma_bad = physics.compute_gamma_eff(
        hrv_rmssd=15, hrv_sdnn=20, hrv_sampen=0.3,
        sleep_hours=4, sleep_quality=0.3,
        stress_level=0.9, inflammation=0.7,
        exercise_minutes=0, meditation_minutes=0,
        breathing_sessions=0, nir_sessions=0, gamma40_sessions=0,
        ace_score=6, has_keeper=False, keeper_bond=0.0,
    )
    check(
        "Good day < bad day gamma_eff",
        gamma_good < gamma_bad,
        f"good={gamma_good:.4f}, bad={gamma_bad:.4f}",
    )
    check(
        "Good day gamma_eff reasonable",
        0.001 < gamma_good < 0.10,
        f"gamma={gamma_good:.4f}",
    )
    check(
        "Bad day gamma_eff higher",
        gamma_bad > gamma_good * 1.5,
        f"bad={gamma_bad:.4f} vs good={gamma_good:.4f}",
    )

    # --- Endpoint tests ---
    print("\n--- Endpoints ---")

    # Root
    resp = test_client.get("/")
    data = resp.get_json()
    check("GET / returns 200", resp.status_code == 200)
    check("Root has app name", data.get("name") == APP_NAME)
    check("Root has endpoints list", len(data.get("endpoints", [])) >= 10)

    # Profile POST
    resp = test_client.post(
        "/api/profile",
        json={
            "name": "Test User",
            "ace_score": 3,
            "age": 42,
            "has_keeper": True,
            "keeper_bond": 0.7,
            "cardiac_history": False,
        },
    )
    check("POST /api/profile returns 200", resp.status_code == 200)

    # Profile GET
    resp = test_client.get("/api/profile")
    data = resp.get_json()
    check("GET /api/profile returns 200", resp.status_code == 200)
    profile_data = data.get("profile", {})
    check("Profile has name", profile_data.get("name") == "Test User")
    check("Profile has ACE", profile_data.get("ace_score") == 3)
    check("Profile has gamma_c constant", data.get("constants", {}).get("gamma_c") == GAMMA_C)

    # Reading POST
    reading_data = {
        "hrv_rmssd": 45.0,
        "hrv_sdnn": 55.0,
        "hrv_sampen": 1.6,
        "sleep_hours": 7.5,
        "sleep_quality": 0.8,
        "stress_level": 0.35,
        "inflammation": 0.15,
        "exercise_minutes": 30,
        "meditation_minutes": 10,
        "breathing_sessions": 2,
        "nir_sessions": 1,
        "gamma40_sessions": 1,
    }
    resp = test_client.post("/api/reading", json=reading_data)
    data = resp.get_json()
    check("POST /api/reading returns 200", resp.status_code == 200)
    reading = data.get("reading", {})
    check("Reading has gamma_eff", reading.get("gamma_eff") is not None)
    check("Reading has gamma_c", reading.get("gamma_c") == GAMMA_C)
    check("Reading has coherence C", reading.get("C") is not None)
    check("Reading has vitality V", reading.get("V") is not None)
    check("Reading has window W", reading.get("W") is not None)
    check("Reading has state", reading.get("state") is not None)
    check("Reading has recommendations", len(data.get("recommendations", [])) > 0)

    # Submit a second reading (worse day) for trend data
    bad_reading = {
        "hrv_rmssd": 20.0, "hrv_sdnn": 25.0, "hrv_sampen": 0.8,
        "sleep_hours": 5.0, "sleep_quality": 0.4,
        "stress_level": 0.7, "inflammation": 0.5,
        "exercise_minutes": 0, "meditation_minutes": 0,
        "breathing_sessions": 0, "nir_sessions": 0, "gamma40_sessions": 0,
    }
    resp = test_client.post("/api/reading", json=bad_reading)
    check("Second reading returns 200", resp.status_code == 200)
    bad_data = resp.get_json().get("reading", {})
    check(
        "Bad day gamma_eff > good day",
        bad_data.get("gamma_eff", 0) > reading.get("gamma_eff", 0),
        f"bad={bad_data.get('gamma_eff')}, good={reading.get('gamma_eff')}",
    )

    # Geomag
    resp = test_client.get("/api/geomag")
    data = resp.get_json()
    check("GET /api/geomag returns 200", resp.status_code == 200)
    check("Geomag has kp", data.get("geomag", {}).get("kp") is not None)
    check("Geomag has physics explanation", "mechanism" in data.get("physics", {}))

    # History
    resp = test_client.get("/api/history")
    data = resp.get_json()
    check("GET /api/history returns 200", resp.status_code == 200)
    check("History has readings", data.get("history", {}).get("days", 0) >= 2)

    # Breathing start
    resp = test_client.post(
        "/api/breathing/start",
        json={"pattern": "resonance", "duration_minutes": 10},
    )
    data = resp.get_json()
    check("POST /api/breathing/start returns 200", resp.status_code == 200)
    session_id = data.get("session", {}).get("id")
    check("Breathing session has ID", session_id is not None)
    check(
        "Breathing has resonance rate",
        data.get("session", {}).get("config", {}).get("rate_hz") == RESONANCE_HZ,
    )

    # Breathing complete
    if session_id:
        resp = test_client.post(
            "/api/breathing/complete",
            json={"session_id": session_id, "completed": True},
        )
        check("POST /api/breathing/complete returns 200", resp.status_code == 200)

    # Breathing with invalid pattern
    resp = test_client.post(
        "/api/breathing/start",
        json={"pattern": "hyperventilate"},
    )
    check("Invalid breathing pattern returns 400", resp.status_code == 400)

    # Gamma40 start
    resp = test_client.post(
        "/api/gamma40/start",
        json={"mode": "both", "duration_minutes": 30},
    )
    data = resp.get_json()
    check("POST /api/gamma40/start returns 200", resp.status_code == 200)
    g40_session_id = data.get("session", {}).get("id")
    check("Gamma40 session has ID", g40_session_id is not None)

    # Gamma40 complete
    if g40_session_id:
        resp = test_client.post(
            "/api/gamma40/complete",
            json={"session_id": g40_session_id, "completed": True},
        )
        check("POST /api/gamma40/complete returns 200", resp.status_code == 200)

    # Phase diagram
    resp = test_client.get("/api/phase_diagram")
    data = resp.get_json()
    check("GET /api/phase_diagram returns 200", resp.status_code == 200)
    pd = data.get("phase_diagram", {})
    check("Phase diagram has position", pd.get("position") is not None)
    check("Phase diagram has critical point", pd.get("critical_point") is not None)
    check("Phase diagram has zones", pd.get("zones") is not None)
    check("Phase diagram has trail", isinstance(pd.get("trail"), list))

    # Window
    resp = test_client.get("/api/window")
    data = resp.get_json()
    check("GET /api/window returns 200", resp.status_code == 200)
    check("Window has W value", data.get("window", {}).get("W") is not None)
    check("Window has trend", data.get("window", {}).get("trend") is not None)

    # Recommendations
    resp = test_client.get("/api/recommendations")
    data = resp.get_json()
    check("GET /api/recommendations returns 200", resp.status_code == 200)
    check(
        "Recommendations not empty",
        len(data.get("recommendations", [])) > 0,
    )

    # Dashboard
    resp = test_client.get("/api/dashboard")
    data = resp.get_json()
    check("GET /api/dashboard returns 200", resp.status_code == 200)
    dash = data.get("dashboard", {})
    check("Dashboard has coherence", dash.get("coherence") is not None)
    check("Dashboard has gamma_eff", dash.get("gamma_eff") is not None)
    check("Dashboard has window", dash.get("window") is not None)
    check("Dashboard has state", dash.get("state") is not None)
    check("Dashboard has geomag", dash.get("geomag") is not None)
    check("Dashboard has today", dash.get("today") is not None)
    check("Dashboard has recommendations", len(dash.get("recommendations", [])) > 0)
    check("Dashboard has history_7d", isinstance(dash.get("history_7d"), list))
    check("Dashboard has phase position", dash.get("phase_diagram_position") is not None)

    # Anti-Zeno: submit many checks and verify warning triggers
    print("\n--- Anti-Zeno Guard ---")
    for i in range(ANTI_ZENO_MAX_CHECKS_PER_DAY + 2):
        _record_app_check(1, "/api/selftest")
    anti_zeno = _anti_zeno_check(1)
    check("Anti-Zeno triggers after excess checks", anti_zeno is not None)
    if anti_zeno:
        check(
            "Anti-Zeno message present",
            "collapse" in anti_zeno.get("message", "").lower(),
        )
        check(
            "Anti-Zeno references Paper 50",
            "50" in anti_zeno.get("paper", ""),
        )

    # Error handling
    print("\n--- Error Handling ---")
    resp = test_client.post("/api/reading", data="not json")
    check("Non-JSON body returns 415", resp.status_code == 415)

    resp = test_client.post(
        "/api/breathing/complete",
        json={"session_id": "nonexistent-id", "completed": True},
    )
    check("Unknown session returns 404", resp.status_code == 404)

    resp = test_client.post(
        "/api/breathing/complete",
        json={"completed": True},
    )
    check("Missing session_id returns 400", resp.status_code == 400)

    # --- Summary ---
    print("\n" + "=" * 70)
    print(f"  RESULTS: {passed}/{total} passed, {failed} failed")
    if failed == 0:
        print(f"  ALL TESTS PASSED.")
        print(f"  gamma_c = {GAMMA_C}. Find your edge.")
    else:
        print(f"  {failed} TESTS FAILED. Review above.")
    print("=" * 70 + "\n")

    return failed == 0


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} v{VERSION} — {APP_TAGLINE}"
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Run self-test suite",
    )
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="Host to bind (default: 0.0.0.0 for network access)",
    )
    parser.add_argument(
        "--port", type=int, default=5000,
        help="Port to bind (default: 5000)",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable Flask debug mode",
    )

    args = parser.parse_args()

    _ensure_db()

    if args.test:
        success = _self_test()
        sys.exit(0 if success else 1)
    else:
        print(f"\n  {APP_NAME} v{VERSION}")
        print(f"  {APP_TAGLINE}")
        print(f"  {AUTHOR}")
        print(f"  gamma_c = {GAMMA_C}")
        print(f"  Database: {DB_PATH}")
        print(f"  Listening: http://{args.host}:{args.port}")
        print(f"  ENGAGEMENT_WEIGHT = {ENGAGEMENT_WEIGHT}\n")
        ssl_cert = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cert.pem")
        ssl_key = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "key.pem")
        if os.path.exists(ssl_cert) and os.path.exists(ssl_key):
            app.run(host=args.host, port=args.port, debug=args.debug, ssl_context=(ssl_cert, ssl_key))
        else:
            app.run(host=args.host, port=args.port, debug=args.debug)
