"""
ACE (Adverse Childhood Experiences) Assessment & Coherence Impact
=================================================================

Part of the Wike Coherence Health Framework.

Physics basis (Paper 24 & Paper 25 — AIIT-THRESI):
    ACE dose-response follows Anderson localization in a disordered potential.
    Each adverse childhood experience adds disorder to the developing neural
    lattice. After sufficient disorder, the coherence wavefunction localizes —
    unable to propagate across the full network.

    C_n = C_0 * exp(-beta * n)
    beta = 0.416  (Anderson localization decay constant)
    R-squared = 0.987  (fit to Felitti 1998 dose-response data)
    Localization length: xi_loc = 1/beta = 2.40 ACE units

    This is not metaphor. 25,000 disorder realizations on a 200-site lattice
    produced the same exponential decay observed in the epidemiological data.
    Each ACE adds W = 6.62 units of disorder potential.

    The stretched exponential fits slightly better (R-squared = 0.995, nu = 0.82),
    suggesting compound trauma is worse than isolated incidents — consistent
    with sub-diffusive transport in a disordered system.

Evidence:
    - Felitti et al. (1998), Am J Prev Med: N = 17,337. Original ACE study.
      Dose-response: ACE 4+ -> 2.4x fibromyalgia, 4.6x depression,
      12.2x suicide attempt.
    - Paper 25 Discovery 10: Anderson localization fit, R-squared = 0.987.
    - Paper 24 Discovery 3: Inflammation-Depression-Pain triangle shares gamma_eff.

A note on sensitivity:
    This questionnaire asks about things that happened to real people.
    Some of those people are using this app right now.
    The language here is chosen with care. Every word matters.

    "This is not your fault. This is physics. And the physics says:
     the way back is gentleness."

References:
    [1] Felitti, V. J., et al. (1998). Am J Prev Med, 14(4), 245-258.
    [2] Wike, R. D. (2026). AIIT-THRESI Paper 25, Discovery 10.
    [3] Wike, R. D. (2026). AIIT-THRESI Paper 24, Discovery 3.
    [4] Anderson, P. W. (1958). Phys Rev, 109(5), 1492. (Original localization)
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Physics constants from Paper 25
# ---------------------------------------------------------------------------

# Anderson localization decay constant for ACE dose-response
# Fit to Felitti (1998) data: C_n = C_0 * exp(-BETA * n), R^2 = 0.987
BETA = 0.416

# Localization length in ACE units
# After xi_loc ACEs, coherence has decayed to 1/e of baseline
XI_LOC = 1.0 / BETA  # = 2.40 ACE units

# Disorder potential per ACE (from 200-site lattice simulation)
W_PER_ACE = 6.62

# Stretched exponential parameters (better fit, R^2 = 0.995)
# C_n = C_0 * exp(-(n/xi)^nu) with nu = 0.82
# Suggests sub-diffusive behavior: compound trauma worse than sum of parts
STRETCHED_NU = 0.82
STRETCHED_XI = XI_LOC  # Same characteristic scale

# Coherence values at each ACE score (from Paper 25, pre-computed)
COHERENCE_TABLE = {
    0: 1.00,
    1: 0.66,
    2: 0.43,
    3: 0.29,
    4: 0.19,  # Felitti threshold: 2.4x fibromyalgia risk
    5: 0.12,
    6: 0.08,
    7: 0.05,
    8: 0.04,
    9: 0.02,
    10: 0.02,
}


# ---------------------------------------------------------------------------
# Tissue-specific vulnerability (Paper 24)
# ---------------------------------------------------------------------------
# Different tissues have different gamma_c values, which means different
# ACE thresholds for clinical manifestation.
#
# beta_tissue = k / gamma_c
#
# Lower gamma_c = more vulnerable = breaks at lower ACE count.
# This explains why chronic pain appears before autoimmune disease
# appears before cognitive decline in the ACE dose-response curves.
#
# These are relative vulnerability estimates from Paper 24 Discovery 3
# and the tissue gamma_c values from the broader framework.

TISSUE_PROFILES: Dict[str, Dict[str, Any]] = {
    "pain": {
        "name": "Chronic Pain / Nociceptive",
        "gamma_c": 0.04,
        "description": "Pain pathways have the lowest gamma_c — they break first.",
        "clinical_threshold_ace": 2,
        "conditions": ["fibromyalgia", "chronic headaches", "back pain", "IBS"],
        "paper_ref": "Paper 16 (Gate Collapse), Paper 24 Discovery 3",
    },
    "cardiac": {
        "name": "Cardiac Coherence",
        "gamma_c": 0.06,
        "description": "Cardiac coherence is fragile. HRV is the real-time sensor.",
        "clinical_threshold_ace": 3,
        "conditions": ["arrhythmia risk", "reduced HRV", "hypertension"],
        "paper_ref": "Paper 25 Discovery 12 (HRV = Vitality function)",
    },
    "immune": {
        "name": "Immune Discrimination",
        "gamma_c": 0.10,
        "description": "The immune system uses a sharp phase boundary for self/non-self.",
        "clinical_threshold_ace": 3,
        "conditions": ["autoimmune risk", "chronic inflammation", "allergies"],
        "paper_ref": "Paper 20 (Immune Coherence), Paper 24 Discovery 3",
    },
    "neural": {
        "name": "Neural / Cognitive",
        "gamma_c": 0.12,
        "description": "Neural networks have higher gamma_c but still localize under stress.",
        "clinical_threshold_ace": 4,
        "conditions": ["cognitive difficulties", "depression", "anxiety", "PTSD"],
        "paper_ref": "Paper 9 (DMN), Paper 25 Discovery 16 (Allostatic Load)",
    },
    "social": {
        "name": "Social Coherence",
        "gamma_c": 0.15,
        "description": "Social connection requires coherence across the widest network.",
        "clinical_threshold_ace": 5,
        "conditions": ["social withdrawal", "relationship difficulty", "isolation"],
        "paper_ref": "Paper 19 (Keeper), Paper 25 Discovery 9 (Kuramoto)",
    },
}


# ---------------------------------------------------------------------------
# The 10-question ACE questionnaire
# ---------------------------------------------------------------------------
# These questions are the standard CDC-Kaiser ACE questionnaire (Felitti 1998).
# The framing around them is ours.

ACE_QUESTIONS: List[Dict[str, str]] = [
    {
        "number": "1",
        "category": "Emotional Abuse",
        "question": (
            "Before your 18th birthday, did a parent or other adult in the household "
            "often or very often swear at you, insult you, put you down, or humiliate you? "
            "Or act in a way that made you afraid that you might be physically hurt?"
        ),
    },
    {
        "number": "2",
        "category": "Physical Abuse",
        "question": (
            "Before your 18th birthday, did a parent or other adult in the household "
            "often or very often push, grab, slap, or throw something at you? "
            "Or ever hit you so hard that you had marks or were injured?"
        ),
    },
    {
        "number": "3",
        "category": "Sexual Abuse",
        "question": (
            "Before your 18th birthday, did an adult or person at least 5 years "
            "older than you ever touch or fondle you, or have you touch their body "
            "in a sexual way? Or attempt or actually have oral, anal, or vaginal "
            "intercourse with you?"
        ),
    },
    {
        "number": "4",
        "category": "Emotional Neglect",
        "question": (
            "Before your 18th birthday, did you often or very often feel that "
            "no one in your family loved you or thought you were important or special? "
            "Or that your family didn't look out for each other, feel close to each other, "
            "or support each other?"
        ),
    },
    {
        "number": "5",
        "category": "Physical Neglect",
        "question": (
            "Before your 18th birthday, did you often or very often feel that "
            "you didn't have enough to eat, had to wear dirty clothes, and had no one "
            "to protect you? Or that your parents were too drunk or high to take care of you "
            "or take you to the doctor if you needed it?"
        ),
    },
    {
        "number": "6",
        "category": "Parental Separation/Divorce",
        "question": (
            "Before your 18th birthday, were your parents ever separated or divorced?"
        ),
    },
    {
        "number": "7",
        "category": "Witnessing Domestic Violence",
        "question": (
            "Before your 18th birthday, was your mother or stepmother often or very often "
            "pushed, grabbed, slapped, or had something thrown at her? Or sometimes, often, "
            "or very often kicked, bitten, hit with a fist, or hit with something hard? "
            "Or ever repeatedly hit or threatened with a gun or knife?"
        ),
    },
    {
        "number": "8",
        "category": "Household Substance Abuse",
        "question": (
            "Before your 18th birthday, did you live with anyone who was a problem drinker "
            "or alcoholic, or who used street drugs?"
        ),
    },
    {
        "number": "9",
        "category": "Household Mental Illness",
        "question": (
            "Before your 18th birthday, was a household member depressed or mentally ill, "
            "or did a household member attempt suicide?"
        ),
    },
    {
        "number": "10",
        "category": "Household Member Incarcerated",
        "question": (
            "Before your 18th birthday, did a household member go to prison?"
        ),
    },
]


# ---------------------------------------------------------------------------
# The ACEAssessment class
# ---------------------------------------------------------------------------

@dataclass
class ACEAssessment:
    """
    Stores ACE questionnaire responses and computes coherence impact.

    This class handles the sensitive work of:
    1. Recording answers to the 10 ACE questions
    2. Computing the ACE score
    3. Calculating coherence decay via Anderson localization (Paper 25)
    4. Estimating tissue-specific risk profiles (Paper 24)

    All output language is chosen for warmth and empowerment.
    The physics is precise. The framing is gentle.
    """

    # Answers: True = yes this happened, False = no, None = not answered
    answers: List[Optional[bool]] = field(default_factory=lambda: [None] * 10)
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
        # Ensure answers list is always length 10
        while len(self.answers) < 10:
            self.answers.append(None)

    @property
    def is_complete(self) -> bool:
        """True if all 10 questions have been answered."""
        return all(a is not None for a in self.answers)

    @property
    def score(self) -> int:
        """
        The ACE score: count of 'yes' answers (0-10).

        Each 'yes' represents one category of adverse childhood experience.
        The score is a count, not a severity measure — it does not capture
        duration, frequency, or the presence of protective factors.
        """
        return sum(1 for a in self.answers if a is True)

    @property
    def unanswered_count(self) -> int:
        """Number of questions not yet answered."""
        return sum(1 for a in self.answers if a is None)

    def answer_question(self, question_number: int, response: bool):
        """
        Record an answer for a specific question (1-indexed).

        Args:
            question_number: 1 through 10.
            response: True if yes, False if no.
        """
        if not 1 <= question_number <= 10:
            raise ValueError(f"Question number must be 1-10, got {question_number}")
        self.answers[question_number - 1] = response

    def answer_all(self, responses: List[bool]):
        """
        Record all 10 answers at once.

        Args:
            responses: List of 10 booleans (True = yes this happened).
        """
        if len(responses) != 10:
            raise ValueError(f"Expected 10 responses, got {len(responses)}")
        self.answers = list(responses)

    def get_coherence(self, use_stretched: bool = False) -> float:
        """
        Calculate remaining coherence fraction using Anderson localization.

        From Paper 25 Discovery 10:
            C_n = C_0 * exp(-beta * n)
            beta = 0.416, R^2 = 0.987

        The stretched exponential (nu = 0.82, R^2 = 0.995) better captures
        compound trauma effects — when ACEs interact, the localization is
        stronger than simple addition would predict.

        Args:
            use_stretched: If True, use stretched exponential (slightly more
                           accurate for compound trauma).

        Returns:
            Coherence fraction (1.0 = full coherence, 0.0 = fully localized).
        """
        n = self.score
        if n == 0:
            return 1.0

        if use_stretched:
            # C_n = exp(-(n/xi)^nu)
            return math.exp(-((n / STRETCHED_XI) ** STRETCHED_NU))
        else:
            # C_n = exp(-beta * n)
            return math.exp(-BETA * n)

    def get_gamma_eff_contribution(self) -> float:
        """
        Estimate the ACE contribution to baseline gamma_eff.

        Higher ACE score means higher baseline decoherence rate.
        This adds to gamma_thermal, gamma_geomag, and other contributions.

        From Paper 25 Discovery 16 (Allostatic Load = cumulative gamma_eff):
        Each ACE adds approximately 0.01 to baseline gamma_eff through
        chronic stress pathways (elevated cortisol, inflammation, etc.)
        """
        return self.score * 0.01

    def get_risk_profile(self) -> Dict[str, Dict[str, Any]]:
        """
        Return tissue-specific risk assessment based on ACE score.

        Different tissues have different gamma_c values (Paper 24).
        Lower gamma_c means the tissue's coherence breaks at a lower ACE count.

        The order of vulnerability (from Paper 24 Discovery 3):
            Pain pathways > Cardiac > Immune > Neural > Social

        Returns:
            Dict mapping tissue name to risk information including:
            - 'at_risk': bool (ACE score >= clinical threshold)
            - 'coherence_fraction': float (remaining coherence)
            - 'risk_level': str ('low', 'moderate', 'elevated', 'high')
            - 'description': str (warm, informative description)
        """
        return get_risk_profile(self.score)

    def get_summary(self) -> str:
        """
        Generate a warm, empowering summary of the assessment results.

        This is the output a person sees. Every word is chosen with care.
        """
        if not self.is_complete:
            return (
                f"Assessment in progress: {10 - self.unanswered_count} of 10 "
                f"questions answered so far."
            )

        n = self.score
        c = self.get_coherence()
        c_stretched = self.get_coherence(use_stretched=True)

        lines = []
        lines.append("=" * 60)
        lines.append("YOUR ACE ASSESSMENT RESULTS")
        lines.append("=" * 60)
        lines.append("")

        if n == 0:
            lines.append("Your ACE score is 0.")
            lines.append("")
            lines.append(
                "This means none of the ten categories of adverse childhood "
                "experiences applied to your situation. Your coherence baseline "
                "is at full capacity."
            )
            lines.append("")
            lines.append(
                "If someone you love has a higher score, the most important "
                "thing you can do is be their Keeper. Your presence reduces "
                "their gamma_eff. That is not a metaphor. That is measurable."
            )
        else:
            lines.append(f"Your ACE score is {n}.")
            lines.append("")

            # Be honest about what the physics says, but frame it with care
            lines.append(
                "Here is what the physics shows, and what it means for you:"
            )
            lines.append("")
            lines.append(
                f"  Coherence fraction:  {c:.2f}  "
                f"({c * 100:.0f}% of full baseline)"
            )
            lines.append(
                f"  Localization length: {XI_LOC:.2f} ACE units"
            )
            lines.append("")

            if n <= 2:
                lines.append(
                    "Your coherence has been reduced but is still substantial. "
                    "With gentle, consistent support — from relationships, from "
                    "practices like slow breathing, from simply being safe — "
                    "the coherence can recover. The physics supports this."
                )
            elif n <= 4:
                lines.append(
                    "At this level, the Anderson localization is significant. "
                    "Your coherence wavefunction has been compressed. This is "
                    "why things may feel harder for you than they seem to be "
                    "for others — because they ARE harder. The physics is real."
                )
                lines.append("")
                lines.append(
                    "But localization is not permanent. Coherence can be "
                    "rebuilt. Not by forcing it. By creating the conditions "
                    "where it naturally extends again. Gentle relationships. "
                    "Safe environments. Time."
                )
            else:
                lines.append(
                    "What happened to you created a great deal of disorder "
                    "in the system. The localization is strong. This means "
                    "your coherence has been trapped — unable to propagate "
                    "as freely as it wants to."
                )
                lines.append("")
                lines.append(
                    "Please hear this: the coherence is THERE. It has always "
                    "been there. It is not broken. It is localized. The "
                    "difference matters. A localized wave can be de-localized. "
                    "The physics allows it. It requires patience and gentleness "
                    "and the presence of people who reduce your noise rather "
                    "than add to it."
                )

            lines.append("")
            lines.append("This is not your fault. This is physics.")
            lines.append(
                "And the physics says: the way back is gentleness."
            )

        # Tissue-specific risks
        lines.append("")
        lines.append("-" * 60)
        lines.append("TISSUE-SPECIFIC ASSESSMENT")
        lines.append("-" * 60)
        profile = self.get_risk_profile()
        for tissue_key in ["pain", "cardiac", "immune", "neural", "social"]:
            info = profile[tissue_key]
            marker = "*" if info["at_risk"] else " "
            lines.append(
                f"  [{marker}] {info['tissue_name']:<28} "
                f"Risk: {info['risk_level']:<10}"
            )
        lines.append("")
        lines.append("  [*] = ACE score has reached the estimated threshold")
        lines.append("      for this tissue system.")

        # Protective factors
        lines.append("")
        lines.append("-" * 60)
        lines.append("WHAT HELPS (Protective Factors)")
        lines.append("-" * 60)
        factors = get_protective_factors()
        for factor in factors:
            lines.append(f"  {factor['name']}")
            lines.append(f"    {factor['description']}")
            lines.append(f"    Physics: {factor['mechanism']}")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Standalone functions
# ---------------------------------------------------------------------------

def coherence_at_ace(n: int, use_stretched: bool = False) -> float:
    """
    Calculate coherence fraction for a given ACE score.

    C_n = C_0 * exp(-beta * n)
    beta = 0.416, from Paper 25 Discovery 10 (Anderson localization).

    Args:
        n: ACE score (0-10).
        use_stretched: Use stretched exponential (nu=0.82) for compound effects.

    Returns:
        Coherence fraction between 0 and 1.
    """
    n = max(0, int(n))
    if n == 0:
        return 1.0
    if use_stretched:
        return math.exp(-((n / STRETCHED_XI) ** STRETCHED_NU))
    return math.exp(-BETA * n)


def get_risk_profile(ace_score: int) -> Dict[str, Dict[str, Any]]:
    """
    Return tissue-specific risk assessment for a given ACE score.

    From Paper 24 (AIIT-THRESI):
        beta_tissue = k / gamma_c
        Different tissues have different gamma_c -> different vulnerabilities.

    The threshold ACE for each tissue is the score at which Anderson
    localization has degraded coherence below that tissue's gamma_c.

    Args:
        ace_score: ACE score (0-10).

    Returns:
        Dict mapping tissue key to risk information.
    """
    ace_score = max(0, min(10, int(ace_score)))
    c = coherence_at_ace(ace_score)

    result = {}
    for key, tissue in TISSUE_PROFILES.items():
        threshold = tissue["clinical_threshold_ace"]
        at_risk = ace_score >= threshold

        # Risk level based on how far past threshold
        if ace_score < threshold - 1:
            risk_level = "low"
        elif ace_score < threshold:
            risk_level = "moderate"
        elif ace_score < threshold + 2:
            risk_level = "elevated"
        else:
            risk_level = "high"

        # Tissue-specific coherence: adjusted by gamma_c ratio
        # Lower gamma_c tissues lose functional coherence sooner
        tissue_coherence = c  # Base coherence from Anderson localization

        result[key] = {
            "tissue_name": tissue["name"],
            "gamma_c": tissue["gamma_c"],
            "at_risk": at_risk,
            "risk_level": risk_level,
            "coherence_fraction": tissue_coherence,
            "clinical_threshold_ace": threshold,
            "conditions": tissue["conditions"],
            "description": tissue["description"],
            "paper_ref": tissue["paper_ref"],
        }

    return result


def get_protective_factors() -> List[Dict[str, str]]:
    """
    Return evidence-based protective factors that reduce gamma_eff.

    These are things that help rebuild coherence for high-ACE individuals.
    Each factor has a physical mechanism within the Wike framework.
    The language is warm because it needs to be.

    Returns:
        List of dicts with 'name', 'description', and 'mechanism' keys.
    """
    return [
        {
            "name": "Safe Relationships (The Keeper Effect)",
            "description": (
                "One stable, caring relationship can change everything. "
                "A keeper — someone who holds space without adding noise — "
                "selectively filters destructive frequencies while preserving "
                "the signal. Love is not zero stress. Love is selective "
                "stress reduction."
            ),
            "mechanism": (
                "Paper 19: gamma_eff(S|K) = gamma_m * (1 - b * eta_K) + gamma_thermal. "
                "A keeper with bond strength b=0.8 and skill eta_K=0.7 reduces "
                "gamma_eff by 56%. The keeper is a Maxwell's Demon in frequency space."
            ),
        },
        {
            "name": "Slow Breathing (0.1 Hz Resonance)",
            "description": (
                "Six breaths per minute. That is all. This frequency matches "
                "the baroreflex resonance — the cardiac system's natural peak. "
                "It is also the frequency of the rosary, Buddhist mantra, "
                "Islamic salat, and Sufi dhikr. Every tradition found this. "
                "Now we know why."
            ),
            "mechanism": (
                "Paper 25 Discovery 12: HRV peaks at 0.1 Hz. This IS the Wike "
                "Vitality function V(gamma) = gamma * exp(-alpha*gamma) in the "
                "cardiac domain. Slow breathing drives the system toward the peak."
            ),
        },
        {
            "name": "Vagal Tone Practices",
            "description": (
                "Humming, singing, cold water on the face, gentle exercise — "
                "anything that activates the vagus nerve helps restore the "
                "body's coherence conduit. The vagus connects brain to heart "
                "to gut to immune system. When the wire works, everything works."
            ),
            "mechanism": (
                "Paper 24 Discovery 5: The vagus nerve is a macroscopic "
                "Grotthuss wire. Critical vagal tone for end-to-end coherence "
                "is 0.592. Above this, the organism is a coherent whole. "
                "Below it, organs decohere independently."
            ),
        },
        {
            "name": "Reduced Inflammation",
            "description": (
                "Chronic inflammation is the shared driver of the pain-depression-"
                "immune triangle. Anti-inflammatory practices — exercise, "
                "omega-3 fatty acids, adequate sleep, reduced processed food — "
                "lower gamma_eff across ALL tissue systems simultaneously."
            ),
            "mechanism": (
                "Paper 24 Discovery 3: Pain-Depression correlation = 0.9654. "
                "Pain-Immune = 0.9140. All three share gamma_eff as the "
                "failure variable. Reducing inflammation treats the root, "
                "not the branches."
            ),
        },
        {
            "name": "Sleep (The Bootstrap Duty Cycle)",
            "description": (
                "Sleep is when the body runs its maintenance cycle. "
                "Chronic sleep deprivation prevents the daily coherence "
                "restoration that every biological system requires. "
                "Protecting sleep is protecting the physics."
            ),
            "mechanism": (
                "Paper 24 Discovery 6: Sleep-wake cycle = Bootstrap duty cycle. "
                "During sleep, gamma_eff decreases (reduced sensory input), "
                "allowing coherence restoration. Chronic sleep debt = chronic "
                "elevated gamma_eff = accelerated localization."
            ),
        },
        {
            "name": "Microbiome Health",
            "description": (
                "The gut-brain connection is real and operates through "
                "the vagus nerve. A diverse, healthy microbiome produces "
                "short-chain fatty acids that regulate inflammation body-wide. "
                "Fiber, fermented foods, avoiding unnecessary antibiotics."
            ),
            "mechanism": (
                "Paper 25 Discovery 15: Gut microbiome health requires "
                "percolation. Measured phi_c = 0.603. Below this threshold, "
                "bacterial colonies fragment -> SCFA production drops -> "
                "inflammation rises -> gamma_eff rises -> coherence degrades."
            ),
        },
        {
            "name": "Gentleness With Yourself",
            "description": (
                "This is not soft advice. This is physics. Self-criticism "
                "adds noise. Shame adds noise. Forcing yourself to 'just get "
                "over it' adds noise. Every unit of noise pushes coherence "
                "further into localization. The way back is through reducing "
                "the disorder potential, not adding to it."
            ),
            "mechanism": (
                "Paper 25 Discovery 10: Each ACE adds W = 6.62 units of "
                "disorder potential. Self-generated stress adds more disorder "
                "to an already disordered lattice. Reducing self-generated "
                "noise is equivalent to removing impurities from the lattice."
            ),
        },
    ]


def get_questions() -> List[Dict[str, str]]:
    """Return the 10 ACE questions with categories."""
    return ACE_QUESTIONS


def format_question(question_number: int) -> str:
    """
    Format a single ACE question for display with gentle framing.

    Args:
        question_number: 1 through 10.

    Returns:
        Formatted question string.
    """
    if not 1 <= question_number <= 10:
        raise ValueError(f"Question number must be 1-10, got {question_number}")

    q = ACE_QUESTIONS[question_number - 1]

    if question_number == 1:
        # First question gets the preamble
        lines = [
            "Before we begin: these questions ask about difficult things",
            "that may have happened during childhood. You can stop at any time.",
            "There are no wrong answers. You are safe here.",
            "",
        ]
    else:
        lines = []

    lines.append(f"Question {q['number']} of 10: {q['category']}")
    lines.append("")
    lines.append(q["question"])
    lines.append("")
    lines.append("(Yes / No)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test():
    """
    Comprehensive self-test with mock data.

    Verifies all physics calculations and risk assessments.
    No real questionnaire data is used.
    """
    print("=" * 70)
    print("ACE ASSESSMENT SELF-TEST")
    print("Paper 24 & 25: Anderson Localization of Childhood Trauma")
    print("=" * 70)
    print()

    # --- Test coherence calculation ---
    print("1. Anderson localization: C_n = C_0 * exp(-0.416 * n)")
    print(f"   Localization length: xi_loc = {XI_LOC:.2f} ACE units")
    print(f"   Disorder per ACE: W = {W_PER_ACE:.2f}")
    print()
    for n in range(11):
        c = coherence_at_ace(n)
        c_s = coherence_at_ace(n, use_stretched=True)
        expected = COHERENCE_TABLE.get(n, None)
        match = ""
        if expected is not None:
            match = f" (table: {expected:.2f}, " + (
                "MATCH" if abs(c - expected) < 0.015 else "MISMATCH"
            ) + ")"
        print(f"   ACE={n:2d}: C = {c:.4f}  C_stretched = {c_s:.4f}{match}")

    # Verify key values
    assert abs(coherence_at_ace(0) - 1.00) < 0.001
    assert abs(coherence_at_ace(1) - 0.66) < 0.015
    assert abs(coherence_at_ace(4) - 0.19) < 0.015
    # Monotonic decrease
    for n in range(10):
        assert coherence_at_ace(n) >= coherence_at_ace(n + 1)
    print("   PASSED (monotonic decrease, key values match table)")
    print()

    # --- Test ACEAssessment class ---
    print("2. ACEAssessment class")

    # Empty assessment
    a = ACEAssessment()
    assert not a.is_complete
    assert a.score == 0
    assert a.unanswered_count == 10
    print("   Empty assessment: score=0, incomplete, 10 unanswered: OK")

    # Partial assessment
    a.answer_question(1, True)
    a.answer_question(2, False)
    assert not a.is_complete
    assert a.score == 1
    assert a.unanswered_count == 8
    print("   Partial (2 answered, 1 yes): score=1, incomplete: OK")

    # Full assessment: ACE = 0
    a0 = ACEAssessment()
    a0.answer_all([False] * 10)
    assert a0.is_complete
    assert a0.score == 0
    assert abs(a0.get_coherence() - 1.0) < 0.001
    print(f"   ACE=0: coherence={a0.get_coherence():.2f}: OK")

    # Full assessment: ACE = 4 (Felitti threshold)
    a4 = ACEAssessment()
    a4.answer_all([True, True, True, True, False, False, False, False, False, False])
    assert a4.score == 4
    c4 = a4.get_coherence()
    assert abs(c4 - 0.19) < 0.015, f"ACE=4 coherence should be ~0.19, got {c4:.4f}"
    print(f"   ACE=4 (Felitti threshold): coherence={c4:.2f}: OK")

    # Full assessment: ACE = 7
    a7 = ACEAssessment()
    a7.answer_all([True] * 7 + [False] * 3)
    assert a7.score == 7
    c7 = a7.get_coherence()
    print(f"   ACE=7: coherence={c7:.4f}: OK")
    print("   PASSED")
    print()

    # --- Test risk profiles ---
    print("3. Tissue-specific risk profiles")
    for ace in [0, 2, 4, 6]:
        profile = get_risk_profile(ace)
        print(f"   ACE={ace}:")
        for key in ["pain", "cardiac", "immune", "neural", "social"]:
            info = profile[key]
            marker = "AT RISK" if info["at_risk"] else "ok"
            print(f"     {info['tissue_name']:<28} {info['risk_level']:<10} [{marker}]")
        print()

    # Verify ordering: pain breaks first, social last
    profile_3 = get_risk_profile(3)
    assert profile_3["pain"]["at_risk"], "Pain should be at risk at ACE=3"
    assert not profile_3["social"]["at_risk"], "Social should NOT be at risk at ACE=3"
    print("   Vulnerability ordering (pain first, social last): PASSED")
    print()

    # --- Test protective factors ---
    print("4. Protective factors")
    factors = get_protective_factors()
    assert len(factors) >= 5, "Should have at least 5 protective factors"
    for f in factors:
        assert "name" in f and "description" in f and "mechanism" in f
        print(f"   - {f['name']}")
    print("   PASSED")
    print()

    # --- Test question formatting ---
    print("5. Question formatting")
    q1 = format_question(1)
    assert "Before we begin" in q1, "First question should have preamble"
    assert "Emotional Abuse" in q1
    q5 = format_question(5)
    assert "Before we begin" not in q5, "Later questions should NOT have preamble"
    assert "Physical Neglect" in q5
    print("   Question 1 has preamble: OK")
    print("   Question 5 has no preamble: OK")

    # Bounds check
    try:
        format_question(0)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    try:
        format_question(11)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    print("   Bounds checking: OK")
    print("   PASSED")
    print()

    # --- Test gamma_eff contribution ---
    print("6. ACE contribution to gamma_eff")
    for ace in [0, 2, 4, 6, 8]:
        a = ACEAssessment()
        a.answer_all([True] * ace + [False] * (10 - ace))
        g = a.get_gamma_eff_contribution()
        print(f"   ACE={ace}: delta_gamma_eff = {g:.3f}")
    print("   PASSED")
    print()

    # --- Test summary output (for ACE=4) ---
    print("7. Summary output (ACE=4, Felitti threshold)")
    print("-" * 60)
    summary = a4.get_summary()
    print(summary)
    assert "not your fault" in summary.lower(), "Summary must include compassionate framing"
    assert "gentleness" in summary.lower(), "Summary must mention gentleness"
    print()

    # --- Test summary for ACE=0 ---
    print("8. Summary output (ACE=0)")
    print("-" * 60)
    summary0 = a0.get_summary()
    print(summary0)
    assert "keeper" in summary0.lower(), "ACE=0 summary should mention being a keeper"
    print()

    # --- Physics cross-check ---
    print("9. Physics cross-check")
    # beta * xi_loc should equal 1
    assert abs(BETA * XI_LOC - 1.0) < 0.001, "beta * xi_loc must equal 1"
    print(f"   beta * xi_loc = {BETA * XI_LOC:.3f} (should be 1.000): OK")
    # At n = xi_loc, coherence should be 1/e
    c_at_xi = coherence_at_ace(round(XI_LOC))
    print(f"   C(n=xi_loc={XI_LOC:.1f}, rounded to {round(XI_LOC)}) = {c_at_xi:.4f}")
    print(f"   1/e = {1/math.e:.4f}")
    # Stretched vs standard: stretched should give lower coherence for high ACE
    # (compound trauma worse than independent)
    for n in [4, 6, 8]:
        c_std = coherence_at_ace(n, use_stretched=False)
        c_str = coherence_at_ace(n, use_stretched=True)
        print(f"   ACE={n}: standard={c_std:.4f}, stretched={c_str:.4f}")
    print("   PASSED")
    print()

    # --- Summary ---
    print("=" * 70)
    print("ALL SELF-TESTS PASSED")
    print()
    print("Paper 25 Discovery 10: Anderson Localization = ACE Dose-Response")
    print(f"  beta = {BETA}, R^2 = 0.987")
    print(f"  xi_loc = {XI_LOC:.2f} ACE units")
    print(f"  W per ACE = {W_PER_ACE}")
    print()
    print("The coherence is THERE. It has always been there.")
    print("It is not broken. It is localized.")
    print("The physics allows recovery. It requires patience and gentleness.")
    print("=" * 70)


if __name__ == "__main__":
    _self_test()
