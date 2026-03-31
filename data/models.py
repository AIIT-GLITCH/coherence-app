"""
Coherence Health App — Data Models
===================================
SQLAlchemy ORM models backed by SQLite.

Tables
------
- User              : demographics, ACE score, keeper info, cardiac baseline
- DailyReading      : HRV / sleep / stress / session counts / computed state
- BreathingLog      : per-session breathing pattern log
- GammaLog          : per-session 40 Hz gamma / NIR log
- GeomagCache       : cached Kp / storm-level geomagnetic data
- KeeperConnection  : keeper bond metadata

References
----------
Paper 19  — Keeper decoherence reduction (gamma_eff equation)
Paper 43  — Keeper effectiveness score  (K_eff = W * P * R * A)
Paper 45  — Multi-keeper superposition
Paper 54  — Superposed coherence fields
"""

from __future__ import annotations

import os
import datetime as _dt
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Float,
    String,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
)
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    relationship,
    Session,
)

# ---------------------------------------------------------------------------
# Database location
# ---------------------------------------------------------------------------
DB_DIR = Path.home() / "coherence_app"
DB_PATH = DB_DIR / "coherence.db"
DB_URL = f"sqlite:///{DB_PATH}"

Base = declarative_base()
_engine = None
_SessionFactory = None


# ===================================================================== models

class User(Base):
    """Core user profile including ACE score and keeper basics."""
    __tablename__ = "users"

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    name                  = Column(String(128), nullable=False)
    age                   = Column(Integer, nullable=True)
    ace_score             = Column(Integer, default=0, doc="Adverse Childhood Experiences score (0-10)")
    has_keeper            = Column(Boolean, default=False)
    keeper_name           = Column(String(128), nullable=True)
    keeper_bond_strength  = Column(Float, default=0.0, doc="Bond strength b in [0, 1]")
    cardiac_history       = Column(Boolean, default=False, doc="Pre-existing cardiac condition flag")
    baseline_rmssd        = Column(Float, nullable=True, doc="Baseline RMSSD in ms")
    baseline_sampen       = Column(Float, nullable=True, doc="Baseline sample entropy")
    created_at            = Column(DateTime, default=_dt.datetime.utcnow)

    # Relationships
    daily_readings      = relationship("DailyReading", back_populates="user", cascade="all, delete-orphan")
    breathing_logs      = relationship("BreathingLog", back_populates="user", cascade="all, delete-orphan")
    gamma_logs          = relationship("GammaLog", back_populates="user", cascade="all, delete-orphan")
    keeper_connections  = relationship("KeeperConnection", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, name={self.name!r}, ace={self.ace_score})>"


class DailyReading(Base):
    """
    One row per measurement snapshot.

    Raw HRV metrics come from the sensor layer; computed fields
    (gamma_eff, coherence, vitality, window_width, state) are filled
    by the coherence engine before persistence.
    """
    __tablename__ = "daily_readings"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    user_id             = Column(Integer, ForeignKey("users.id"), nullable=False)
    timestamp           = Column(DateTime, default=_dt.datetime.utcnow, nullable=False)

    # --- Raw HRV ---
    hrv_rmssd           = Column(Float, nullable=True, doc="Root mean square of successive RR differences (ms)")
    hrv_sdnn            = Column(Float, nullable=True, doc="Std dev of NN intervals (ms)")
    hrv_sampen          = Column(Float, nullable=True, doc="Sample entropy of RR series")
    hrv_coherence_ratio = Column(Float, nullable=True, doc="LF-peak power / total LF power")

    # --- Lifestyle ---
    sleep_hours         = Column(Float, nullable=True)
    sleep_quality       = Column(Float, nullable=True, doc="Subjective 0-10 scale")
    stress_level        = Column(Float, nullable=True, doc="Subjective 0-10 scale")
    inflammation_level  = Column(Float, nullable=True, doc="Estimated 0-10 or CRP proxy")

    # --- Activity ---
    exercise_minutes    = Column(Integer, default=0)
    meditation_minutes  = Column(Integer, default=0)

    # --- Session counts ---
    breathing_sessions  = Column(Integer, default=0)
    gamma40_sessions    = Column(Integer, default=0)
    nir_sessions        = Column(Integer, default=0)

    # --- Computed by coherence engine ---
    gamma_eff           = Column(Float, nullable=True, doc="Effective decoherence rate (Paper 19)")
    gamma_c             = Column(Float, nullable=True, doc="Critical decoherence threshold")
    coherence           = Column(Float, nullable=True, doc="Coherence index 0-1")
    vitality            = Column(Float, nullable=True, doc="Vitality score 0-100")
    window_width        = Column(Float, nullable=True, doc="Therapeutic window width (seconds)")
    state               = Column(String(32), nullable=True, doc="coherent | partially_coherent | decoherent")

    # Relationships
    user = relationship("User", back_populates="daily_readings")

    def __repr__(self) -> str:
        return (
            f"<DailyReading(id={self.id}, user={self.user_id}, "
            f"coherence={self.coherence}, state={self.state!r})>"
        )


class BreathingLog(Base):
    """Per-session log for structured breathing exercises."""
    __tablename__ = "breathing_logs"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=False)
    timestamp        = Column(DateTime, default=_dt.datetime.utcnow, nullable=False)
    pattern          = Column(String(64), nullable=True, doc="e.g. '4-7-8', '5-5', 'box'")
    duration_seconds = Column(Integer, default=0)
    completed        = Column(Boolean, default=False)

    user = relationship("User", back_populates="breathing_logs")

    def __repr__(self) -> str:
        return f"<BreathingLog(id={self.id}, pattern={self.pattern!r}, completed={self.completed})>"


class GammaLog(Base):
    """Per-session log for 40 Hz gamma entrainment / NIR sessions."""
    __tablename__ = "gamma_logs"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=False)
    timestamp        = Column(DateTime, default=_dt.datetime.utcnow, nullable=False)
    mode             = Column(String(32), nullable=True, doc="'gamma40' | 'nir' | 'combined'")
    duration_seconds = Column(Integer, default=0)
    completed        = Column(Boolean, default=False)

    user = relationship("User", back_populates="gamma_logs")

    def __repr__(self) -> str:
        return f"<GammaLog(id={self.id}, mode={self.mode!r}, completed={self.completed})>"


class GeomagCache(Base):
    """
    Cached geomagnetic / space-weather data.

    Kp index and storm level affect the environmental decoherence rate
    (gamma_environment).  forecast_json stores the raw upstream payload.
    """
    __tablename__ = "geomag_cache"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    timestamp     = Column(DateTime, default=_dt.datetime.utcnow, nullable=False)
    kp_value      = Column(Float, nullable=True, doc="Planetary K-index 0-9")
    storm_level   = Column(String(16), nullable=True, doc="'quiet' | 'minor' | 'moderate' | 'severe'")
    forecast_json = Column(Text, nullable=True, doc="Raw JSON from upstream API")

    def __repr__(self) -> str:
        return f"<GeomagCache(id={self.id}, kp={self.kp_value}, storm={self.storm_level!r})>"


class KeeperConnection(Base):
    """
    Tracks a keeper relationship for a given user.

    Paper 19: gamma_eff(user|keeper) = gamma_m * (1 - b * eta_K) + gamma_thermal
    Paper 43: K_eff = W * P * R * A  (simplified: bond_strength * contact_quality)
    """
    __tablename__ = "keeper_connections"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    user_id             = Column(Integer, ForeignKey("users.id"), nullable=False)
    keeper_name         = Column(String(128), nullable=False)
    bond_strength       = Column(Float, default=0.0, doc="b in [0, 1]")
    gamma_reduction_pct = Column(Float, default=0.0, doc="b * eta_K * 100")
    connected_since     = Column(DateTime, default=_dt.datetime.utcnow)

    user = relationship("User", back_populates="keeper_connections")

    def __repr__(self) -> str:
        return (
            f"<KeeperConnection(id={self.id}, keeper={self.keeper_name!r}, "
            f"bond={self.bond_strength})>"
        )


# ============================================================ engine helpers

def _get_engine():
    """Lazily create and cache the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(DB_URL, echo=False, future=True)
    return _engine


def _get_session_factory() -> sessionmaker:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=_get_engine(), expire_on_commit=False)
    return _SessionFactory


# ============================================================ public API

def init_db() -> None:
    """Create all tables if they do not already exist."""
    engine = _get_engine()
    Base.metadata.create_all(engine)


def get_session() -> Session:
    """Return a new SQLAlchemy Session bound to the coherence database."""
    init_db()  # ensure tables exist
    return _get_session_factory()()


@contextmanager
def session_scope():
    """Context manager that commits on success and rolls back on error."""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ============================================================ helper functions

def get_user(user_id: int = 1) -> Optional[User]:
    """Fetch a User by id (defaults to the primary user, id=1)."""
    with session_scope() as s:
        return s.query(User).filter(User.id == user_id).first()


def update_user(user_id: int = 1, **kwargs) -> Optional[User]:
    """
    Update arbitrary fields on a User row.

    Usage::

        update_user(1, ace_score=3, has_keeper=True)
    """
    with session_scope() as s:
        user = s.query(User).filter(User.id == user_id).first()
        if user is None:
            return None
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        s.flush()
        # Eagerly load before session closes
        s.refresh(user)
        return user


def save_reading(user_id: int, **data) -> DailyReading:
    """
    Persist a new DailyReading for *user_id*.

    Accepts any column name as a keyword argument::

        save_reading(1, hrv_rmssd=42.5, sleep_hours=7.2, state='coherent')
    """
    with session_scope() as s:
        reading = DailyReading(user_id=user_id, **data)
        s.add(reading)
        s.flush()
        s.refresh(reading)
        return reading


def get_history(user_id: int = 1, days: int = 30) -> List[DailyReading]:
    """
    Return DailyReadings for the last *days* days, most recent first.
    """
    cutoff = _dt.datetime.utcnow() - _dt.timedelta(days=days)
    with session_scope() as s:
        rows = (
            s.query(DailyReading)
            .filter(DailyReading.user_id == user_id)
            .filter(DailyReading.timestamp >= cutoff)
            .order_by(DailyReading.timestamp.desc())
            .all()
        )
        # Detach from session so caller can use them freely
        s.expunge_all()
        return rows


# ============================================================ self-test

def _self_test() -> None:
    """
    Quick smoke test: create tables in-memory, insert a user and a reading,
    then query them back.
    """
    import tempfile, json

    # Use a throwaway in-memory DB so we never touch the real file
    global _engine, _SessionFactory
    _engine = create_engine("sqlite:///:memory:", echo=False, future=True)
    _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False)
    Base.metadata.create_all(_engine)

    with session_scope() as s:
        user = User(name="Test User", age=35, ace_score=2, has_keeper=True,
                     keeper_name="Alice", keeper_bond_strength=0.85,
                     cardiac_history=False, baseline_rmssd=42.0, baseline_sampen=1.6)
        s.add(user)
        s.flush()
        uid = user.id

        reading = DailyReading(
            user_id=uid, hrv_rmssd=45.0, hrv_sdnn=55.0,
            hrv_sampen=1.7, hrv_coherence_ratio=0.62,
            sleep_hours=7.5, sleep_quality=8.0,
            stress_level=3.0, inflammation_level=2.0,
            exercise_minutes=30, meditation_minutes=15,
            breathing_sessions=2, gamma40_sessions=1, nir_sessions=1,
            gamma_eff=0.03, gamma_c=0.05, coherence=0.78,
            vitality=72.0, window_width=12.5, state="coherent",
        )
        s.add(reading)

        blog = BreathingLog(user_id=uid, pattern="4-7-8", duration_seconds=240, completed=True)
        glog = GammaLog(user_id=uid, mode="gamma40", duration_seconds=600, completed=True)
        geo  = GeomagCache(kp_value=2.3, storm_level="quiet", forecast_json='{"status":"ok"}')
        kc   = KeeperConnection(user_id=uid, keeper_name="Alice",
                                 bond_strength=0.85, gamma_reduction_pct=76.5)
        s.add_all([blog, glog, geo, kc])
        s.flush()

    # Query back
    with session_scope() as s:
        u = s.query(User).first()
        assert u is not None and u.name == "Test User", "User insert/query failed"
        assert u.ace_score == 2, "ACE score mismatch"

        r = s.query(DailyReading).first()
        assert r is not None and r.state == "coherent", "DailyReading insert/query failed"
        assert abs(r.coherence - 0.78) < 1e-6, "Coherence value mismatch"

        bl = s.query(BreathingLog).first()
        assert bl is not None and bl.pattern == "4-7-8", "BreathingLog failed"

        gl = s.query(GammaLog).first()
        assert gl is not None and gl.mode == "gamma40", "GammaLog failed"

        gc = s.query(GeomagCache).first()
        assert gc is not None and abs(gc.kp_value - 2.3) < 1e-6, "GeomagCache failed"

        kc = s.query(KeeperConnection).first()
        assert kc is not None and kc.keeper_name == "Alice", "KeeperConnection failed"
        assert abs(kc.bond_strength - 0.85) < 1e-6, "Bond strength mismatch"

    # Reset globals so real usage gets the file-backed DB
    _engine = None
    _SessionFactory = None

    print("[models.py] All self-tests passed.")


if __name__ == "__main__":
    _self_test()
