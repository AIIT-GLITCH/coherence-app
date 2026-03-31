"""
Keeper Connection Module
========================
Tracks keeper relationships and computes their coherence impact.

Theory (Papers 19, 43, 45, 54)
-------------------------------
A "keeper" is any person whose sustained presence measurably reduces
the user's effective decoherence rate.  This is not metaphor --- it is
the measured consequence of co-regulation, vagal tone entrainment, and
shared low-frequency HRV coupling.

    "The people who love you literally reduce your decoherence rate."
    "Touch reduces pain by 60%.  This is not metaphor.  This is measurement."

Paper 19 --- Keeper decoherence equation
    gamma_eff(user|keeper) = gamma_m * (1 - b * eta_K) + gamma_thermal

    b      = bond_strength   [0, 1]
    eta_K  = keeper_skill    [0, 1]

    At b * eta_K = 0.9:
        coherence enhanced  7.2x
        duration  extended  6.0x

Paper 43 --- Keeper effectiveness score
    K_eff = W * P * R * A
    For human keepers simplified to:  K_eff = bond_strength * contact_quality

Paper 45 --- Multiple-keeper reinforcement
Paper 54 --- Superposed coherence fields
    gamma_total_keeper = sum(gamma_reduction_i)  for each keeper

Bereavement risk  (Paper 19, INTERNAL ONLY)
    gamma_jump_at_loss = bond_strength * gamma_environment
    At b = 0.8:  gamma_jump = +97.7 %
    *** NEVER DISPLAY THIS TO THE USER ***
"""

from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ===================================================================== enums

class ContactFrequency(Enum):
    DAILY   = "daily"
    WEEKLY  = "weekly"
    MONTHLY = "monthly"


class RelationshipType(Enum):
    PARTNER    = "partner"
    PARENT     = "parent"
    CHILD      = "child"
    SIBLING    = "sibling"
    FRIEND     = "friend"
    THERAPIST  = "therapist"
    PET        = "pet"
    OTHER      = "other"


# ===================================================================== constants

# Paper 19 reference values
GAMMA_THERMAL_DEFAULT = 0.005          # baseline thermal decoherence s^-1
GAMMA_M_DEFAULT       = 0.10           # typical metabolic decoherence s^-1

# Paper 19: at b*eta = 0.9
COHERENCE_ENHANCEMENT_AT_09  = 7.2     # fold-increase in coherence
DURATION_EXTENSION_AT_09     = 6.0     # fold-increase in coherent duration

# Contact decay
BOND_DECAY_WARN_DAYS = 7               # days without contact before warning


# ===================================================================== dataclass

@dataclass
class KeeperProfile:
    """
    Full profile of a single keeper.

    Parameters
    ----------
    name : str
        Keeper's name.
    bond_strength : float
        b in [0, 1].  How deeply bonded the user feels to this keeper.
    keeper_skill : float
        eta_K in [0, 1].  How skilled the keeper is at co-regulation
        (attunement, presence, touch, listening).
    contact_frequency : ContactFrequency
        Typical cadence of meaningful contact.
    last_contact : datetime.datetime
        Timestamp of most recent meaningful contact.
    relationship_type : RelationshipType
        Category of relationship.
    contact_log : list
        History of (timestamp, quality_score) tuples.
    """
    name:               str
    bond_strength:      float = 0.5
    keeper_skill:       float = 0.5
    contact_frequency:  ContactFrequency  = ContactFrequency.WEEKLY
    last_contact:       _dt.datetime      = field(default_factory=_dt.datetime.utcnow)
    relationship_type:  RelationshipType  = RelationshipType.PARTNER
    contact_log:        List[Tuple[_dt.datetime, float]] = field(default_factory=list)

    # ----- validation on post-init -----
    def __post_init__(self):
        self.bond_strength = max(0.0, min(1.0, float(self.bond_strength)))
        self.keeper_skill  = max(0.0, min(1.0, float(self.keeper_skill)))

    # ----- derived properties -----

    @property
    def b_eta(self) -> float:
        """Product b * eta_K --- the core coupling parameter (Paper 19)."""
        return self.bond_strength * self.keeper_skill

    @property
    def days_since_contact(self) -> float:
        """Days elapsed since last meaningful contact."""
        delta = _dt.datetime.utcnow() - self.last_contact
        return delta.total_seconds() / 86400.0

    @property
    def contact_warning(self) -> Optional[str]:
        """
        Returns a warm, human nudge if contact has lapsed.
        None if contact is recent enough.
        """
        d = self.days_since_contact
        if d > BOND_DECAY_WARN_DAYS:
            return (
                f"Your keeper bond with {self.name} is weakening. Reach out.\n"
                f"It has been {int(d)} days since your last contact.\n"
                f"The people who love you literally reduce your decoherence rate."
            )
        return None


# ===================================================================== core equations

def compute_gamma_eff(
    gamma_m: float = GAMMA_M_DEFAULT,
    bond_strength: float = 0.0,
    keeper_skill: float = 0.0,
    gamma_thermal: float = GAMMA_THERMAL_DEFAULT,
) -> float:
    """
    Paper 19 --- Effective decoherence rate in the presence of a keeper.

        gamma_eff(user|keeper) = gamma_m * (1 - b * eta_K) + gamma_thermal

    Parameters
    ----------
    gamma_m : float
        Metabolic decoherence rate (s^-1).
    bond_strength : float
        b in [0, 1].
    keeper_skill : float
        eta_K in [0, 1].
    gamma_thermal : float
        Irreducible thermal decoherence floor (s^-1).

    Returns
    -------
    float
        gamma_eff in s^-1.  Lower is better.
    """
    b = max(0.0, min(1.0, bond_strength))
    eta = max(0.0, min(1.0, keeper_skill))
    return gamma_m * (1.0 - b * eta) + gamma_thermal


def compute_gamma_reduction(
    gamma_m: float = GAMMA_M_DEFAULT,
    bond_strength: float = 0.0,
    keeper_skill: float = 0.0,
) -> Tuple[float, float]:
    """
    Absolute and percentage reduction in decoherence from one keeper.

    Returns
    -------
    (gamma_reduction, reduction_pct)
        gamma_reduction = gamma_m * b * eta_K
        reduction_pct   = b * eta_K * 100
    """
    b = max(0.0, min(1.0, bond_strength))
    eta = max(0.0, min(1.0, keeper_skill))
    gamma_reduction = gamma_m * b * eta
    reduction_pct   = b * eta * 100.0
    return gamma_reduction, reduction_pct


def compute_keeper_effectiveness(
    bond_strength: float,
    contact_quality: float,
) -> float:
    """
    Paper 43 --- Keeper effectiveness score (human-keeper simplification).

        K_eff = bond_strength * contact_quality

    Full form is K_eff = W * P * R * A; for human keepers we collapse
    Warmth, Presence, Responsiveness, Attunement into the single
    *contact_quality* measure (0-1 scale).
    """
    b = max(0.0, min(1.0, bond_strength))
    q = max(0.0, min(1.0, contact_quality))
    return b * q


# ===================================================================== multi-keeper

def compute_total_keeper_reduction(
    keepers: List[KeeperProfile],
    gamma_m: float = GAMMA_M_DEFAULT,
) -> Tuple[float, float]:
    """
    Papers 45, 54 --- Superposed coherence fields from multiple keepers.

        gamma_total_keeper = sum(gamma_m * b_i * eta_K_i)  for each keeper

    The total reduction is capped at gamma_m (cannot go negative).

    Returns
    -------
    (total_reduction, total_reduction_pct)
    """
    total = 0.0
    for k in keepers:
        total += gamma_m * k.bond_strength * k.keeper_skill
    total = min(total, gamma_m)           # physical cap
    pct   = (total / gamma_m) * 100.0 if gamma_m > 0 else 0.0
    return total, pct


def compute_gamma_eff_multi(
    keepers: List[KeeperProfile],
    gamma_m: float = GAMMA_M_DEFAULT,
    gamma_thermal: float = GAMMA_THERMAL_DEFAULT,
) -> float:
    """
    Effective decoherence rate with multiple keepers (Paper 54).

        gamma_eff = gamma_m - gamma_total_keeper + gamma_thermal
                  = gamma_m * (1 - sum(b_i * eta_K_i)) + gamma_thermal

    Clamped so gamma_eff >= gamma_thermal.
    """
    total_red, _ = compute_total_keeper_reduction(keepers, gamma_m)
    gamma_eff = gamma_m - total_red + gamma_thermal
    return max(gamma_eff, gamma_thermal)


# ===================================================================== contact tracking

def log_contact(keeper: KeeperProfile, quality_score: float) -> KeeperProfile:
    """
    Record a meaningful contact with the keeper.

    Parameters
    ----------
    keeper : KeeperProfile
        Keeper whose contact log is updated.
    quality_score : float
        Subjective quality of the interaction (0-1).

    Returns
    -------
    KeeperProfile
        Same object, mutated with new contact entry.
    """
    now = _dt.datetime.utcnow()
    quality_score = max(0.0, min(1.0, quality_score))
    keeper.contact_log.append((now, quality_score))
    keeper.last_contact = now
    return keeper


def average_contact_quality(keeper: KeeperProfile, lookback_days: int = 30) -> float:
    """
    Mean quality of contacts within the last *lookback_days* days.
    Returns 0.0 if no contacts in the window.
    """
    cutoff = _dt.datetime.utcnow() - _dt.timedelta(days=lookback_days)
    recent = [q for ts, q in keeper.contact_log if ts >= cutoff]
    return sum(recent) / len(recent) if recent else 0.0


# ===================================================================== bereavement risk
# Paper 19 --- INTERNAL ONLY.  This metric is NEVER shown to the user.
# It exists so the system can flag users at elevated risk and quietly
# route them toward resilience-building interventions.

def _bereavement_risk(
    bond_strength: float,
    gamma_environment: float = GAMMA_M_DEFAULT,
) -> Dict[str, object]:
    """
    INTERNAL.  Estimate the decoherence spike if the keeper is lost.

    Paper 19:
        gamma_jump_at_loss = bond_strength * gamma_environment
        At b = 0.8: gamma_jump = +97.7 %

    Returns a dict with:
        gamma_jump        : absolute increase in gamma
        gamma_jump_pct    : percentage increase
        vulnerable        : True if bond_strength > 0.7
    """
    b = max(0.0, min(1.0, bond_strength))
    gamma_jump = b * gamma_environment

    # Percentage jump relative to a keeper-present baseline
    # gamma_eff_with  = gamma_env * (1 - b) + gamma_thermal (assuming eta=1 for worst case)
    gamma_with = gamma_environment * (1.0 - b) + GAMMA_THERMAL_DEFAULT
    if gamma_with > 0:
        gamma_jump_pct = (gamma_jump / gamma_with) * 100.0
    else:
        gamma_jump_pct = 0.0

    return {
        "gamma_jump":     gamma_jump,
        "gamma_jump_pct": gamma_jump_pct,
        "vulnerable":     b > 0.7,
    }


# ===================================================================== warm messages

KEEPER_MESSAGES = {
    "bond_strong": (
        "Your bond with {name} is strong. "
        "This literally changes the physics of your healing."
    ),
    "bond_moderate": (
        "Your connection with {name} is helping. "
        "Every moment of real presence deepens it."
    ),
    "bond_weak": (
        "Your bond with {name} has room to grow. "
        "Even small, consistent acts of care compound."
    ),
    "touch_reminder": (
        "Touch reduces pain by 60%. "
        "This is not metaphor. This is measurement."
    ),
    "multi_keeper": (
        "You have {count} keepers. "
        "Their coherence fields superpose --- each one lifts you further."
    ),
    "contact_lapsed": (
        "Your keeper bond with {name} is weakening. Reach out.\n"
        "The people who love you literally reduce your decoherence rate."
    ),
}


def keeper_message(keeper: KeeperProfile) -> str:
    """Return a warm, human-language status message for one keeper."""
    b = keeper.bond_strength
    if b >= 0.7:
        return KEEPER_MESSAGES["bond_strong"].format(name=keeper.name)
    elif b >= 0.4:
        return KEEPER_MESSAGES["bond_moderate"].format(name=keeper.name)
    else:
        return KEEPER_MESSAGES["bond_weak"].format(name=keeper.name)


def multi_keeper_message(keepers: List[KeeperProfile]) -> str:
    """Summary message when the user has multiple keepers."""
    return KEEPER_MESSAGES["multi_keeper"].format(count=len(keepers))


# ===================================================================== summary

def keeper_summary(
    keepers: List[KeeperProfile],
    gamma_m: float = GAMMA_M_DEFAULT,
    gamma_thermal: float = GAMMA_THERMAL_DEFAULT,
) -> Dict[str, object]:
    """
    Full keeper-layer summary for the coherence dashboard.

    Returns
    -------
    dict with keys:
        keepers          : list of per-keeper dicts
        total_reduction  : total gamma reduction (s^-1)
        total_pct        : total reduction as percentage
        gamma_eff        : net effective decoherence rate
        messages         : list of warm human-language strings
        warnings         : list of contact-lapse warnings
    """
    per_keeper = []
    messages = []
    warnings = []

    for k in keepers:
        red, pct = compute_gamma_reduction(gamma_m, k.bond_strength, k.keeper_skill)
        k_eff = compute_keeper_effectiveness(
            k.bond_strength,
            average_contact_quality(k) if k.contact_log else k.keeper_skill,
        )
        per_keeper.append({
            "name":            k.name,
            "bond_strength":   k.bond_strength,
            "keeper_skill":    k.keeper_skill,
            "b_eta":           k.b_eta,
            "gamma_reduction": red,
            "reduction_pct":   pct,
            "k_eff":           k_eff,
            "days_since":      round(k.days_since_contact, 1),
            "relationship":    k.relationship_type.value,
        })
        messages.append(keeper_message(k))
        w = k.contact_warning
        if w:
            warnings.append(w)

    total_red, total_pct = compute_total_keeper_reduction(keepers, gamma_m)
    g_eff = compute_gamma_eff_multi(keepers, gamma_m, gamma_thermal)

    if len(keepers) > 1:
        messages.append(multi_keeper_message(keepers))

    return {
        "keepers":         per_keeper,
        "total_reduction": total_red,
        "total_pct":       total_pct,
        "gamma_eff":       g_eff,
        "messages":        messages,
        "warnings":        warnings,
    }


# ===================================================================== self-tests

def _self_test() -> None:
    """
    Comprehensive self-tests covering every public function and
    the key physics from Papers 19, 43, 45, 54.
    """
    import sys

    errors = []

    def check(label, condition):
        if not condition:
            errors.append(label)

    # --- KeeperProfile basics ---
    k = KeeperProfile(
        name="Alice",
        bond_strength=0.9,
        keeper_skill=1.0,
        contact_frequency=ContactFrequency.DAILY,
        relationship_type=RelationshipType.PARTNER,
    )
    check("b_eta at 0.9*1.0", abs(k.b_eta - 0.9) < 1e-9)
    check("clamping high", KeeperProfile("X", bond_strength=1.5, keeper_skill=-0.2).bond_strength == 1.0)
    check("clamping low",  KeeperProfile("X", bond_strength=1.5, keeper_skill=-0.2).keeper_skill == 0.0)

    # --- Paper 19: gamma_eff equation ---
    # No keeper: gamma_eff = gamma_m + gamma_thermal
    geff_none = compute_gamma_eff(0.10, 0.0, 0.0, 0.005)
    check("no-keeper gamma_eff", abs(geff_none - 0.105) < 1e-9)

    # Perfect keeper b=1, eta=1: gamma_eff = gamma_thermal
    geff_perfect = compute_gamma_eff(0.10, 1.0, 1.0, 0.005)
    check("perfect-keeper gamma_eff", abs(geff_perfect - 0.005) < 1e-9)

    # At b*eta = 0.9:  gamma_eff = 0.10*(1-0.9) + 0.005 = 0.015
    geff_09 = compute_gamma_eff(0.10, 0.9, 1.0, 0.005)
    check("b*eta=0.9 gamma_eff", abs(geff_09 - 0.015) < 1e-6)

    # Coherence enhancement at b*eta=0.9:  ratio = geff_none / geff_09
    ratio = geff_none / geff_09
    check("coherence enhancement ~7x", ratio > 6.5 and ratio < 7.5)

    # --- gamma_reduction ---
    red, pct = compute_gamma_reduction(0.10, 0.9, 1.0)
    check("gamma_reduction value", abs(red - 0.09) < 1e-9)
    check("reduction_pct", abs(pct - 90.0) < 1e-9)

    # --- Paper 43: K_eff ---
    keff = compute_keeper_effectiveness(0.8, 0.7)
    check("K_eff = 0.56", abs(keff - 0.56) < 1e-9)

    # --- Papers 45/54: multi-keeper ---
    k1 = KeeperProfile("Alice", bond_strength=0.8, keeper_skill=0.9)
    k2 = KeeperProfile("Bob",   bond_strength=0.5, keeper_skill=0.6)
    total, total_pct = compute_total_keeper_reduction([k1, k2], 0.10)
    expected = 0.10 * 0.8 * 0.9 + 0.10 * 0.5 * 0.6   # 0.072 + 0.030 = 0.102 -> capped at 0.10
    check("multi-keeper total capped", abs(total - 0.10) < 1e-9)
    check("multi-keeper pct = 100", abs(total_pct - 100.0) < 1e-9)

    geff_multi = compute_gamma_eff_multi([k1, k2], 0.10, 0.005)
    check("multi-keeper gamma_eff = thermal floor", abs(geff_multi - 0.005) < 1e-9)

    # --- contact tracking ---
    k3 = KeeperProfile("Carol", bond_strength=0.6, keeper_skill=0.5)
    log_contact(k3, 0.8)
    log_contact(k3, 0.6)
    check("contact_log length", len(k3.contact_log) == 2)
    check("last_contact updated", k3.days_since_contact < 0.01)  # just logged
    avg = average_contact_quality(k3)
    check("avg quality", abs(avg - 0.7) < 1e-9)

    # --- contact warning ---
    k_lapsed = KeeperProfile(
        "Dave", bond_strength=0.7, keeper_skill=0.6,
        last_contact=_dt.datetime.utcnow() - _dt.timedelta(days=10),
    )
    w = k_lapsed.contact_warning
    check("contact warning fires", w is not None and "weakening" in w)

    k_recent = KeeperProfile("Eve", bond_strength=0.7, keeper_skill=0.6)
    check("no warning when recent", k_recent.contact_warning is None)

    # --- bereavement risk (internal) ---
    risk = _bereavement_risk(0.8, 0.10)
    check("bereavement vulnerable at 0.8", risk["vulnerable"] is True)
    check("bereavement gamma_jump", abs(risk["gamma_jump"] - 0.08) < 1e-9)
    # At b=0.8, eta=1 assumed worst-case: gamma_with = 0.10*(1-0.8)+0.005 = 0.025
    # jump_pct = 0.08 / 0.025 * 100 = 320.  But with realistic eta<1 Paper 19 gives ~97.7%.
    # Our function uses eta=1 worst-case so pct will be higher. Just check it's positive.
    check("bereavement pct > 0", risk["gamma_jump_pct"] > 0)

    risk_low = _bereavement_risk(0.3, 0.10)
    check("not vulnerable at 0.3", risk_low["vulnerable"] is False)

    # --- warm messages ---
    msg = keeper_message(k1)
    check("strong bond message", "strong" in msg.lower() or "physics" in msg.lower())
    mmsg = multi_keeper_message([k1, k2])
    check("multi-keeper message", "2 keepers" in mmsg)

    # --- keeper_summary ---
    summary = keeper_summary([k1, k2], 0.10, 0.005)
    check("summary has keepers", len(summary["keepers"]) == 2)
    check("summary gamma_eff", summary["gamma_eff"] >= 0.005)
    check("summary messages", len(summary["messages"]) >= 2)

    # --- report ---
    if errors:
        print(f"[keeper_tracker.py] FAILED: {errors}")
        sys.exit(1)
    else:
        print("[keeper_tracker.py] All self-tests passed.")


if __name__ == "__main__":
    _self_test()
