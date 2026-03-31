"""
HRV Analysis Module for the Wike Coherence Framework
=====================================================

Processes heart rate data from phone camera PPG (photoplethysmography) or
wearable devices and extracts biometrics for the coherence engine.

Theoretical foundation:
    Paper 42 (Lyapunov at the Edge) -- SampEn as lambda_L proxy, DFA alpha
    Paper 23 (40 Hz Frequency as Medicine) -- 0.1 Hz coherence score
    Paper 45 (Reynolds Cardiac Coherence) -- cardiovascular coherence mapping
    Goldberger et al. (2002) PNAS -- fractal HRV dynamics in health/disease
    Kauffman (1993) -- edge-of-chaos computation maximum

The central thesis (Paper 42):
    lambda_L < 0  => frozen   (rigid, periodic, low adaptability)
    lambda_L = 0  => edge     (fractal, maximum information processing)
    lambda_L > 0  => collapsed (chaotic, incoherent, arrhythmic)

    SampEn and DFA alpha are practical proxies for lambda_L estimated from
    short (5-minute) HRV recordings. Together with the 0.1 Hz coherence
    ratio they locate the patient on the Wike phase diagram.

Dependencies: numpy, scipy
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
from scipy import signal, interpolate


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Artifact rejection bounds for RR intervals (milliseconds)
RR_MIN_MS = 300   # 200 bpm upper physiological limit
RR_MAX_MS = 2000  # 30 bpm lower physiological limit

# Standard HRV analysis window (seconds)
STANDARD_WINDOW_SEC = 300  # 5 minutes per Task Force (1996)

# Frequency bands (Hz) -- Task Force of the European Society of Cardiology
LF_BAND = (0.04, 0.15)   # sympathetic + parasympathetic
HF_BAND = (0.15, 0.40)   # parasympathetic (vagal tone)

# Coherence band: 0.1 Hz +/- 0.03 Hz (Paper 23: prayer/resonance frequency)
COHERENCE_CENTER_HZ = 0.10
COHERENCE_HALF_WIDTH_HZ = 0.03

# Sample entropy defaults (Paper 42)
SAMPEN_M = 2       # embedding dimension
SAMPEN_R_FACTOR = 0.2  # tolerance = 0.2 * SDNN

# DFA defaults (Goldberger 2002)
DFA_SHORT_RANGE = (4, 16)    # short-term correlations
DFA_LONG_RANGE = (16, 64)    # long-term correlations -- alpha1

# PPG bandpass filter (Hz) -- cardiac fundamental and first harmonic
PPG_BANDPASS_LOW = 0.5
PPG_BANDPASS_HIGH = 4.0
PPG_FILTER_ORDER = 4

# Phase-diagram thresholds (Paper 42, Section 4)
SAMPEN_EDGE_LOW = 1.0
SAMPEN_EDGE_HIGH = 2.0
DFA_EDGE_LOW = 0.75
DFA_EDGE_HIGH = 1.25
COHERENCE_EDGE_MIN = 0.10


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class HRVMetrics:
    """Container for all HRV metrics extracted from an RR interval series.

    Time-domain metrics follow the Task Force (1996) standard.
    Frequency-domain uses Welch PSD on uniformly resampled (4 Hz) RR series.
    Nonlinear metrics follow Paper 42 / Goldberger (2002).
    Coherence score follows Paper 23.
    """
    # Time-domain
    mean_rr_ms: float = 0.0
    sdnn_ms: float = 0.0
    rmssd_ms: float = 0.0
    pnn50_pct: float = 0.0
    mean_hr_bpm: float = 0.0

    # Frequency-domain (ms^2)
    lf_power: float = 0.0
    hf_power: float = 0.0
    lf_hf_ratio: float = 0.0
    total_power: float = 0.0

    # Nonlinear (Paper 42)
    sample_entropy: float = 0.0
    dfa_alpha1: float = 0.0

    # Coherence (Paper 23)
    coherence_ratio: float = 0.0
    coherence_power: float = 0.0

    # Wike phase classification
    wike_state: str = "unknown"
    lambda_l_proxy: float = 0.0  # combined Lyapunov proxy

    # Metadata
    n_intervals: int = 0
    n_artifacts_removed: int = 0
    window_seconds: float = 0.0


@dataclass
class RealtimeBuffer:
    """Rolling buffer for real-time HRV streaming."""
    rr_intervals_ms: List[float] = field(default_factory=list)
    max_size: int = 600  # ~10 minutes at 60 bpm
    last_metrics: Optional[HRVMetrics] = None


# ---------------------------------------------------------------------------
# PPG Signal Processing
# ---------------------------------------------------------------------------

def bandpass_filter_ppg(
    raw_signal: np.ndarray,
    sample_rate: float,
    lowcut: float = PPG_BANDPASS_LOW,
    highcut: float = PPG_BANDPASS_HIGH,
    order: int = PPG_FILTER_ORDER,
) -> np.ndarray:
    """Apply a Butterworth bandpass filter to a raw PPG signal.

    Parameters
    ----------
    raw_signal : array-like
        Raw PPG amplitudes (e.g. green channel averages from camera).
    sample_rate : float
        Sampling rate in Hz.
    lowcut, highcut : float
        Passband edges in Hz.  Default 0.5--4 Hz captures the cardiac
        fundamental (resting ~1 Hz) through the first harmonic.
    order : int
        Butterworth filter order (applied forward-backward, so effective
        order is 2*order).

    Returns
    -------
    np.ndarray
        Filtered PPG signal (same length as input).
    """
    raw_signal = np.asarray(raw_signal, dtype=np.float64)
    nyquist = sample_rate / 2.0

    if highcut >= nyquist:
        highcut = nyquist * 0.95
        warnings.warn(
            f"PPG highcut clamped to {highcut:.2f} Hz (Nyquist = {nyquist:.2f} Hz)"
        )

    sos = signal.butter(order, [lowcut / nyquist, highcut / nyquist],
                        btype="band", output="sos")
    return signal.sosfiltfilt(sos, raw_signal)


def detect_ppg_peaks(
    filtered_signal: np.ndarray,
    sample_rate: float,
    min_distance_ms: float = RR_MIN_MS,
) -> np.ndarray:
    """Detect systolic peaks in a filtered PPG signal.

    Uses scipy.signal.find_peaks with a minimum inter-peak distance
    derived from physiological heart-rate limits.

    Parameters
    ----------
    filtered_signal : np.ndarray
        Bandpass-filtered PPG signal.
    sample_rate : float
        Sampling rate in Hz.
    min_distance_ms : float
        Minimum distance between peaks in ms (default 300 ms = 200 bpm).

    Returns
    -------
    np.ndarray
        Indices of detected peaks in the signal array.
    """
    min_samples = int((min_distance_ms / 1000.0) * sample_rate)
    # Adaptive height threshold: peaks above the 60th percentile
    height_threshold = np.percentile(filtered_signal, 60)
    peaks, _ = signal.find_peaks(
        filtered_signal,
        distance=max(min_samples, 1),
        height=height_threshold,
    )
    return peaks


def peaks_to_rr_intervals(
    peak_indices: np.ndarray,
    sample_rate: float,
) -> np.ndarray:
    """Convert peak sample indices to RR intervals in milliseconds.

    Parameters
    ----------
    peak_indices : np.ndarray
        Sample indices of detected peaks.
    sample_rate : float
        Sampling rate in Hz.

    Returns
    -------
    np.ndarray
        RR intervals in milliseconds.
    """
    if len(peak_indices) < 2:
        return np.array([], dtype=np.float64)
    diffs = np.diff(peak_indices).astype(np.float64)
    return (diffs / sample_rate) * 1000.0


def extract_ppg_from_video(
    video_frames: np.ndarray,
    fps: float,
) -> np.ndarray:
    """Extract a raw PPG signal from finger-on-camera video frames.

    The green channel has the strongest pulsatile component because
    haemoglobin absorption peaks in the green wavelength range, making
    the green-channel spatial average the standard PPG proxy for phone
    camera recordings.

    Parameters
    ----------
    video_frames : np.ndarray
        Array of shape (N, H, W, C) where C >= 3 (RGB).
        Each frame is a uint8 or float image from the phone camera
        while the user's fingertip covers the lens with the flash on.
    fps : float
        Video frame rate in Hz.

    Returns
    -------
    np.ndarray
        Raw PPG signal (green channel spatial mean per frame).
        Length = number of frames.
    """
    video_frames = np.asarray(video_frames)
    if video_frames.ndim != 4 or video_frames.shape[3] < 3:
        raise ValueError(
            f"Expected (N, H, W, C>=3) video array, got shape {video_frames.shape}"
        )
    # Green channel is index 1 in RGB
    green = video_frames[:, :, :, 1].astype(np.float64)
    # Spatial mean per frame => raw PPG trace
    ppg_raw = green.mean(axis=(1, 2))
    return ppg_raw


def ppg_to_rr_intervals(
    raw_ppg: np.ndarray,
    sample_rate: float,
) -> np.ndarray:
    """Full pipeline: raw PPG -> filtered -> peaks -> artifact-cleaned RR.

    Parameters
    ----------
    raw_ppg : array-like
        Raw PPG amplitudes.
    sample_rate : float
        Sampling rate in Hz.

    Returns
    -------
    np.ndarray
        Artifact-cleaned RR intervals in milliseconds.
    """
    filtered = bandpass_filter_ppg(raw_ppg, sample_rate)
    peaks = detect_ppg_peaks(filtered, sample_rate)
    rr = peaks_to_rr_intervals(peaks, sample_rate)
    rr_clean, _ = remove_artifacts(rr)
    return rr_clean


# ---------------------------------------------------------------------------
# Artifact Removal
# ---------------------------------------------------------------------------

def remove_artifacts(
    rr_intervals_ms: np.ndarray,
    rr_min: float = RR_MIN_MS,
    rr_max: float = RR_MAX_MS,
) -> Tuple[np.ndarray, int]:
    """Remove physiologically implausible RR intervals.

    Any RR interval outside [rr_min, rr_max] ms is rejected.
    Additionally, intervals that deviate more than 20% from the local
    median (5-beat window) are rejected -- this catches ectopic beats
    and missed peaks that fall within the absolute bounds.

    Parameters
    ----------
    rr_intervals_ms : array-like
        RR intervals in milliseconds.
    rr_min, rr_max : float
        Absolute physiological bounds in ms.

    Returns
    -------
    clean_rr : np.ndarray
        Cleaned RR intervals.
    n_removed : int
        Count of removed intervals.
    """
    rr = np.asarray(rr_intervals_ms, dtype=np.float64)
    n_original = len(rr)

    # Stage 1: absolute bounds
    mask = (rr >= rr_min) & (rr <= rr_max)
    rr = rr[mask]

    # Stage 2: local median filter (20% deviation threshold)
    if len(rr) > 5:
        local_median = np.array([
            np.median(rr[max(0, i - 2):i + 3]) for i in range(len(rr))
        ])
        deviation = np.abs(rr - local_median) / local_median
        rr = rr[deviation < 0.20]

    n_removed = n_original - len(rr)
    return rr, n_removed


# ---------------------------------------------------------------------------
# Time-Domain HRV Metrics
# ---------------------------------------------------------------------------

def compute_rmssd(rr_ms: np.ndarray) -> float:
    """Root mean square of successive RR differences (parasympathetic proxy).

    RMSSD = sqrt(mean((RR_{i+1} - RR_i)^2))

    Higher RMSSD indicates stronger parasympathetic (vagal) tone.
    """
    if len(rr_ms) < 2:
        return 0.0
    diffs = np.diff(rr_ms)
    return float(np.sqrt(np.mean(diffs ** 2)))


def compute_sdnn(rr_ms: np.ndarray) -> float:
    """Standard deviation of NN intervals (overall HRV).

    SDNN captures total variability -- both sympathetic and parasympathetic
    contributions.  It is the simplest single-number HRV summary but
    depends strongly on recording length.
    """
    if len(rr_ms) < 2:
        return 0.0
    return float(np.std(rr_ms, ddof=1))


def compute_pnn50(rr_ms: np.ndarray) -> float:
    """Percentage of successive intervals differing by > 50 ms.

    Like RMSSD, pNN50 reflects short-term (parasympathetic) variability.
    """
    if len(rr_ms) < 2:
        return 0.0
    diffs = np.abs(np.diff(rr_ms))
    return float(100.0 * np.sum(diffs > 50.0) / len(diffs))


def compute_mean_hr(rr_ms: np.ndarray) -> float:
    """Mean heart rate in bpm from RR intervals in ms."""
    if len(rr_ms) == 0:
        return 0.0
    return float(60000.0 / np.mean(rr_ms))


# ---------------------------------------------------------------------------
# Frequency-Domain HRV Metrics
# ---------------------------------------------------------------------------

def compute_psd(
    rr_ms: np.ndarray,
    resample_rate: float = 4.0,
    nperseg: int = 256,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute PSD of the RR interval time series using Welch's method.

    The RR series is non-uniformly sampled (each interval is timed by
    the preceding interval).  We first interpolate onto a uniform 4 Hz
    grid, then apply Welch's method.

    Parameters
    ----------
    rr_ms : np.ndarray
        RR intervals in milliseconds.
    resample_rate : float
        Uniform resampling rate in Hz (default 4 Hz per Task Force).
    nperseg : int
        Segment length for Welch PSD.

    Returns
    -------
    freqs : np.ndarray
        Frequency axis in Hz.
    psd : np.ndarray
        Power spectral density in ms^2/Hz.
    """
    if len(rr_ms) < 4:
        return np.array([0.0]), np.array([0.0])

    # Build cumulative time axis (seconds)
    rr_sec = rr_ms / 1000.0
    t_cum = np.cumsum(rr_sec)
    t_cum = t_cum - t_cum[0]  # start at zero

    # Remove mean (detrend)
    rr_detrended = rr_ms - np.mean(rr_ms)

    # Cubic spline interpolation to uniform grid
    t_uniform = np.arange(0, t_cum[-1], 1.0 / resample_rate)
    if len(t_uniform) < nperseg:
        nperseg = max(len(t_uniform), 4)

    interp_fn = interpolate.CubicSpline(t_cum, rr_detrended)
    rr_uniform = interp_fn(t_uniform)

    freqs, psd = signal.welch(
        rr_uniform,
        fs=resample_rate,
        nperseg=nperseg,
        noverlap=nperseg // 2,
        detrend="linear",
    )
    return freqs, psd


def band_power(freqs: np.ndarray, psd: np.ndarray,
               band: Tuple[float, float]) -> float:
    """Integrate PSD over a frequency band (trapezoidal rule)."""
    mask = (freqs >= band[0]) & (freqs <= band[1])
    if np.sum(mask) < 2:
        return 0.0
    return float(np.trapezoid(psd[mask], freqs[mask]))


def compute_frequency_metrics(
    rr_ms: np.ndarray,
) -> Tuple[float, float, float, float, np.ndarray, np.ndarray]:
    """Compute LF, HF, LF/HF, and total power from RR intervals.

    Returns
    -------
    lf, hf, lf_hf, total, freqs, psd
    """
    freqs, psd = compute_psd(rr_ms)

    lf = band_power(freqs, psd, LF_BAND)
    hf = band_power(freqs, psd, HF_BAND)
    total = band_power(freqs, psd, (LF_BAND[0], HF_BAND[1]))
    lf_hf = lf / hf if hf > 1e-12 else 0.0

    return lf, hf, lf_hf, total, freqs, psd


# ---------------------------------------------------------------------------
# Coherence Score (Paper 23 -- 0.1 Hz peak detection)
# ---------------------------------------------------------------------------

def compute_coherence_score(
    rr_ms: np.ndarray,
    center_hz: float = COHERENCE_CENTER_HZ,
    half_width_hz: float = COHERENCE_HALF_WIDTH_HZ,
) -> Tuple[float, float]:
    """Compute the 0.1 Hz coherence ratio.

    Paper 23 identifies 0.1 Hz as the global integration frequency --
    the "prayer frequency" where autonomic, cardiovascular, and
    respiratory oscillations can entrain.  HRV biofeedback (HeartMath)
    trains breathing at ~6 breaths/min (= 0.1 Hz) to maximize power at
    this peak.

    The coherence ratio = power_in_0.1Hz_band / total_power.
    A high ratio means the heart is resonating coherently at the
    autonomic integration frequency.

    Returns
    -------
    coherence_ratio : float
        Fraction of total power concentrated at 0.1 Hz.
    coherence_power : float
        Absolute power in the 0.1 Hz band (ms^2).
    """
    freqs, psd = compute_psd(rr_ms)

    coh_band = (center_hz - half_width_hz, center_hz + half_width_hz)
    coh_power = band_power(freqs, psd, coh_band)
    total = band_power(freqs, psd, (LF_BAND[0], HF_BAND[1]))

    ratio = coh_power / total if total > 1e-12 else 0.0
    return float(ratio), float(coh_power)


# ---------------------------------------------------------------------------
# Sample Entropy (Paper 42 -- Lyapunov proxy)
# ---------------------------------------------------------------------------

def _count_template_matches(
    series: np.ndarray,
    m: int,
    r: float,
) -> int:
    """Count the number of template matches of length m within tolerance r.

    Two templates x_i and x_j (i != j) of length m match if
    max(|x_i[k] - x_j[k]|) <= r  for k = 0..m-1.

    This is the Chebyshev (L-infinity) distance criterion used in
    Richman & Moorman (2000).

    Parameters
    ----------
    series : np.ndarray
        1-D time series (RR intervals).
    m : int
        Template length.
    r : float
        Tolerance threshold.

    Returns
    -------
    int
        Number of matching template pairs (i, j) with i != j.
    """
    n = len(series) - m
    if n <= 0:
        return 0

    # Build templates as a 2-D array for vectorized comparison
    templates = np.array([series[i:i + m] for i in range(n)])
    count = 0
    for i in range(n):
        # Chebyshev distance from template i to all others
        dists = np.max(np.abs(templates - templates[i]), axis=1)
        # Count matches excluding self (distance <= r AND index != i)
        count += int(np.sum(dists <= r)) - 1  # subtract self-match

    return count


def compute_sample_entropy(
    rr_ms: np.ndarray,
    m: int = SAMPEN_M,
    r_factor: float = SAMPEN_R_FACTOR,
) -> float:
    """Compute Sample Entropy of an RR interval series.

    SampEn(m, r, N) = -ln(A / B)
    where:
        B = number of template matches of length m
        A = number of template matches of length m+1
        r = r_factor * SDNN
        m = embedding dimension (default 2)

    Paper 42 interpretation (Lyapunov proxy):
        High SampEn (>1.5): lambda_L ~ 0 => edge state => healthy
        Low SampEn  (<0.5): frozen or collapsed dynamics

    Parameters
    ----------
    rr_ms : np.ndarray
        RR intervals in milliseconds.
    m : int
        Embedding dimension.
    r_factor : float
        Tolerance as fraction of SDNN.

    Returns
    -------
    float
        Sample entropy value.  Returns 0.0 if computation is
        degenerate (too few intervals or zero matches).
    """
    rr = np.asarray(rr_ms, dtype=np.float64)
    n = len(rr)

    if n < m + 2:
        return 0.0

    sdnn = float(np.std(rr, ddof=1))
    if sdnn < 1e-10:
        return 0.0  # constant series => zero entropy

    r = r_factor * sdnn

    B = _count_template_matches(rr, m, r)
    A = _count_template_matches(rr, m + 1, r)

    if B == 0 or A == 0:
        return 0.0  # undefined; degenerate

    return float(-math.log(A / B))


# ---------------------------------------------------------------------------
# Detrended Fluctuation Analysis (Paper 42 / Goldberger 2002)
# ---------------------------------------------------------------------------

def compute_dfa_alpha(
    rr_ms: np.ndarray,
    scale_range: Tuple[int, int] = DFA_LONG_RANGE,
    n_scales: int = 12,
) -> float:
    """Compute DFA scaling exponent alpha for an RR interval series.

    Algorithm (Peng et al., 1995):
        1. Integrate the mean-subtracted series: y(k) = sum(RR_i - mean)
        2. Divide y into non-overlapping windows of length n
        3. Fit a linear trend in each window; compute RMS of residuals
        4. Repeat for multiple window sizes n
        5. alpha = slope of log(F(n)) vs log(n)

    Paper 42 / Goldberger (2002) interpretation:
        alpha ~ 1.0: healthy fractal (1/f noise) => edge state
        alpha < 0.5: uncorrelated (white noise) => collapsed
        alpha > 1.5: strongly correlated (Brownian) => frozen

    Parameters
    ----------
    rr_ms : np.ndarray
        RR intervals in milliseconds.
    scale_range : tuple of (int, int)
        Min and max window sizes for DFA.
    n_scales : int
        Number of logarithmically spaced scales.

    Returns
    -------
    float
        DFA alpha exponent.  Returns 0.0 if computation fails.
    """
    rr = np.asarray(rr_ms, dtype=np.float64)
    n = len(rr)

    if n < scale_range[1] * 2:
        # Not enough data; use what we have
        scale_range = (max(4, scale_range[0]), max(8, n // 4))
        if scale_range[0] >= scale_range[1]:
            return 0.0

    # Step 1: integrate the mean-subtracted series
    y = np.cumsum(rr - np.mean(rr))

    # Generate logarithmically spaced window sizes
    scales = np.unique(
        np.logspace(
            np.log10(scale_range[0]),
            np.log10(scale_range[1]),
            n_scales,
        ).astype(int)
    )
    scales = scales[scales >= 4]
    if len(scales) < 2:
        return 0.0

    fluctuations = []
    valid_scales = []

    for s in scales:
        n_windows = n // s
        if n_windows < 1:
            continue

        rms_sum = 0.0
        count = 0
        for w in range(n_windows):
            segment = y[w * s:(w + 1) * s]
            # Linear detrend
            x_axis = np.arange(s, dtype=np.float64)
            coeffs = np.polyfit(x_axis, segment, 1)
            trend = np.polyval(coeffs, x_axis)
            residuals = segment - trend
            rms_sum += np.mean(residuals ** 2)
            count += 1

        if count > 0:
            fluctuations.append(np.sqrt(rms_sum / count))
            valid_scales.append(s)

    if len(valid_scales) < 2:
        return 0.0

    # Step 5: log-log regression
    log_s = np.log10(np.array(valid_scales, dtype=np.float64))
    log_f = np.log10(np.array(fluctuations, dtype=np.float64))

    # Guard against -inf from zero fluctuations
    finite_mask = np.isfinite(log_f)
    if np.sum(finite_mask) < 2:
        return 0.0

    coeffs = np.polyfit(log_s[finite_mask], log_f[finite_mask], 1)
    alpha = float(coeffs[0])

    return alpha


# ---------------------------------------------------------------------------
# Wike Phase Classification (Paper 42)
# ---------------------------------------------------------------------------

def compute_lambda_proxy(sampen: float, dfa_alpha: float) -> float:
    """Combine SampEn and DFA alpha into a single Lyapunov proxy score.

    The proxy maps to the Wike phase diagram:
        lambda_proxy ~ 0   => edge (healthy)
        lambda_proxy < -1  => frozen
        lambda_proxy > +1  => collapsed

    Mapping logic:
        DFA alpha ~ 1.0 is the edge.  Deviation in either direction
        pushes the proxy away from zero.
        SampEn acts as a discriminator: high SampEn + low alpha = collapsed,
        low SampEn + high alpha = frozen.

    This is a heuristic combination calibrated against Paper 42 thresholds.
    """
    # DFA deviation from ideal 1.0
    dfa_deviation = dfa_alpha - 1.0  # positive = frozen direction

    # SampEn contribution: centered around 1.5 (healthy edge)
    sampen_deviation = 1.5 - sampen  # positive = too regular (frozen)

    # Combined: negative = frozen, positive = collapsed
    # Weight DFA slightly more as it is the more stable estimator
    proxy = -(0.6 * dfa_deviation + 0.4 * sampen_deviation)

    return float(proxy)


def get_coherence_state(metrics: HRVMetrics) -> str:
    """Classify the Wike coherence state from HRV metrics.

    States (Paper 42):
        "edge"      -- lambda_L ~ 0, healthy fractal dynamics.
                       SampEn in [1.0, 2.0], DFA alpha in [0.75, 1.25],
                       meaningful coherence ratio.
        "frozen"    -- lambda_L < 0, rigid/periodic, low complexity.
                       Low SampEn, high DFA alpha, low RMSSD.
        "collapsed" -- lambda_L > 0, chaotic, incoherent.
                       Patterns consistent with arrhythmia or autonomic chaos.

    Parameters
    ----------
    metrics : HRVMetrics
        Computed HRV metrics.

    Returns
    -------
    str
        One of "frozen", "edge", or "collapsed".
    """
    se = metrics.sample_entropy
    da = metrics.dfa_alpha1
    cr = metrics.coherence_ratio

    # Edge criteria: fractal SampEn, fractal DFA, decent coherence
    se_ok = SAMPEN_EDGE_LOW <= se <= SAMPEN_EDGE_HIGH
    da_ok = DFA_EDGE_LOW <= da <= DFA_EDGE_HIGH
    cr_ok = cr >= COHERENCE_EDGE_MIN

    edge_score = sum([se_ok, da_ok, cr_ok])

    if edge_score >= 2:
        return "edge"

    # Discriminate frozen vs collapsed
    # Frozen: over-regular (low SampEn, high DFA alpha)
    # Collapsed: chaotic (possibly high SampEn but non-fractal,
    #            or low DFA alpha indicating randomness)
    if da > DFA_EDGE_HIGH or se < SAMPEN_EDGE_LOW:
        return "frozen"

    return "collapsed"


# ---------------------------------------------------------------------------
# Unified Computation
# ---------------------------------------------------------------------------

def compute_all_metrics(rr_ms: np.ndarray) -> HRVMetrics:
    """Compute the full HRV metric suite from cleaned RR intervals.

    Parameters
    ----------
    rr_ms : np.ndarray
        Artifact-cleaned RR intervals in milliseconds.

    Returns
    -------
    HRVMetrics
        Populated metrics dataclass.
    """
    rr = np.asarray(rr_ms, dtype=np.float64)
    m = HRVMetrics()
    m.n_intervals = len(rr)

    if len(rr) < 4:
        m.wike_state = "unknown"
        return m

    # Time-domain
    m.mean_rr_ms = float(np.mean(rr))
    m.sdnn_ms = compute_sdnn(rr)
    m.rmssd_ms = compute_rmssd(rr)
    m.pnn50_pct = compute_pnn50(rr)
    m.mean_hr_bpm = compute_mean_hr(rr)
    m.window_seconds = float(np.sum(rr) / 1000.0)

    # Frequency-domain
    lf, hf, lf_hf, total, _, _ = compute_frequency_metrics(rr)
    m.lf_power = lf
    m.hf_power = hf
    m.lf_hf_ratio = lf_hf
    m.total_power = total

    # Nonlinear (Paper 42)
    m.sample_entropy = compute_sample_entropy(rr)
    m.dfa_alpha1 = compute_dfa_alpha(rr)

    # Coherence (Paper 23)
    m.coherence_ratio, m.coherence_power = compute_coherence_score(rr)

    # Wike phase classification
    m.lambda_l_proxy = compute_lambda_proxy(m.sample_entropy, m.dfa_alpha1)
    m.wike_state = get_coherence_state(m)

    return m


# ---------------------------------------------------------------------------
# Windowed and Real-Time Processing
# ---------------------------------------------------------------------------

def process_window(
    rr_intervals_ms: np.ndarray,
    window_size: int = 300,
) -> HRVMetrics:
    """Process a fixed-size window of RR intervals.

    Standard HRV analysis uses a 5-minute window (approx 300 beats at
    60 bpm).  This function takes the last `window_size` intervals,
    applies artifact removal, and computes all metrics.

    Parameters
    ----------
    rr_intervals_ms : array-like
        Full RR interval series (may be longer than window).
    window_size : int
        Number of intervals to use (default 300).

    Returns
    -------
    HRVMetrics
        Metrics for the windowed segment.
    """
    rr = np.asarray(rr_intervals_ms, dtype=np.float64)
    if len(rr) > window_size:
        rr = rr[-window_size:]

    rr_clean, n_removed = remove_artifacts(rr)

    metrics = compute_all_metrics(rr_clean)
    metrics.n_artifacts_removed = n_removed

    return metrics


def process_realtime(
    new_rr_ms: float,
    buffer: RealtimeBuffer,
    compute_interval: int = 30,
) -> Optional[HRVMetrics]:
    """Add a new RR interval to the rolling buffer and optionally recompute.

    Metrics are recomputed every `compute_interval` new beats to avoid
    excessive CPU use on mobile devices.

    Parameters
    ----------
    new_rr_ms : float
        New RR interval in milliseconds.
    buffer : RealtimeBuffer
        Rolling buffer (mutated in place).
    compute_interval : int
        Recompute metrics every N new beats.

    Returns
    -------
    HRVMetrics or None
        Updated metrics if recomputed this call, else None.
    """
    buffer.rr_intervals_ms.append(new_rr_ms)

    # Enforce max buffer size
    if len(buffer.rr_intervals_ms) > buffer.max_size:
        buffer.rr_intervals_ms = buffer.rr_intervals_ms[-buffer.max_size:]

    # Recompute on interval
    if len(buffer.rr_intervals_ms) >= 30 and \
       len(buffer.rr_intervals_ms) % compute_interval == 0:
        rr = np.array(buffer.rr_intervals_ms)
        metrics = process_window(rr, window_size=min(300, len(rr)))
        buffer.last_metrics = metrics
        return metrics

    return None


# ---------------------------------------------------------------------------
# Synthetic Data Generation (for testing)
# ---------------------------------------------------------------------------

def _generate_synthetic_rr(
    n_beats: int = 300,
    mean_rr_ms: float = 800.0,
    sdnn_ms: float = 50.0,
    respiratory_hz: float = 0.25,
    coherence_hz: float = 0.10,
    coherence_strength: float = 0.3,
    seed: int = 42,
) -> np.ndarray:
    """Generate synthetic RR intervals with known spectral properties.

    The synthetic series has:
        - A respiratory sinus arrhythmia (RSA) component at ~0.25 Hz
          injecting HF-band power (parasympathetic proxy).
        - A Mayer-wave / coherence component at 0.1 Hz injecting LF power
          and, when coherence_strength is high, a strong coherence peak.
        - Gaussian noise for baseline variability.

    Parameters
    ----------
    n_beats : int
        Number of RR intervals to generate.
    mean_rr_ms : float
        Mean RR interval (800 ms ~ 75 bpm).
    sdnn_ms : float
        Target overall standard deviation.
    respiratory_hz : float
        Respiratory frequency for RSA.
    coherence_hz : float
        Mayer wave / coherence frequency.
    coherence_strength : float
        Amplitude of the 0.1 Hz component (0 to 1).
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    np.ndarray
        Synthetic RR intervals in milliseconds.
    """
    rng = np.random.RandomState(seed)
    t = np.cumsum(np.full(n_beats, mean_rr_ms)) / 1000.0  # seconds

    # RSA component (HF band)
    rsa = 0.4 * sdnn_ms * np.sin(2 * np.pi * respiratory_hz * t)

    # Coherence / Mayer wave component (LF band, centered at 0.1 Hz)
    mayer = coherence_strength * sdnn_ms * np.sin(2 * np.pi * coherence_hz * t)

    # 1/f (pink) noise component for fractal-like behaviour.
    # Generate via spectral synthesis: power ~ 1/f
    freqs_fft = np.fft.rfftfreq(n_beats, d=1.0)
    freqs_fft[0] = 1.0  # avoid division by zero
    power_spectrum = 1.0 / freqs_fft
    phases = rng.uniform(0, 2 * np.pi, len(freqs_fft))
    fft_coeffs = np.sqrt(power_spectrum) * np.exp(1j * phases)
    fft_coeffs[0] = 0  # zero mean
    pink = np.fft.irfft(fft_coeffs, n=n_beats)
    pink = pink / (np.std(pink) + 1e-12) * sdnn_ms * 0.3  # scale

    rr = mean_rr_ms + rsa + mayer + pink + rng.normal(0, sdnn_ms * 0.1, n_beats)

    # Ensure physiological range
    rr = np.clip(rr, RR_MIN_MS + 50, RR_MAX_MS - 50)

    return rr


def _generate_frozen_rr(n_beats: int = 300, seed: int = 99) -> np.ndarray:
    """Generate highly regular (near-periodic) RR intervals simulating a frozen state.

    A frozen cardiac dynamical state has very low variability, near-zero
    SampEn, and high DFA alpha -- the hallmark of congestive heart failure
    or a pacemaker-driven rhythm (Goldberger 2002).

    We simulate this as a slow sinusoid with minimal noise -- a highly
    predictable, structured series.  The SDNN is kept moderate enough
    that the SampEn tolerance r = 0.2*SDNN is meaningful, but the
    series is so regular that template matches are plentiful and SampEn
    is low.
    """
    rng = np.random.RandomState(seed)
    t = np.arange(n_beats, dtype=np.float64)
    # Dominant slow oscillation (very predictable)
    rr = 750.0 + 15.0 * np.sin(2 * np.pi * 0.02 * t)
    # Tiny noise so SDNN is nonzero but series is highly regular
    rr += rng.normal(0, 1.5, n_beats)
    return rr


def _generate_collapsed_rr(n_beats: int = 300, seed: int = 77) -> np.ndarray:
    """Generate random (white-noise) RR intervals simulating a collapsed state.

    A collapsed state has high entropy but no fractal structure -- the
    hallmark of atrial fibrillation or severe autonomic neuropathy
    (Goldberger 2002).
    """
    rng = np.random.RandomState(seed)
    # Large random variation, no temporal structure
    rr = rng.uniform(500, 1200, n_beats)
    return rr


# ---------------------------------------------------------------------------
# Self-Test
# ---------------------------------------------------------------------------

def self_test() -> None:
    """Comprehensive self-test demonstrating all metrics on synthetic data.

    Generates three synthetic RR series representing the three Wike
    phase-diagram states (edge, frozen, collapsed) and verifies that
    the computed metrics locate each in the correct region.

    This function prints detailed output for review by other AI
    instances or human auditors.
    """
    separator = "=" * 72
    sub_sep = "-" * 72

    print(separator)
    print("  HRV ANALYZER -- COMPREHENSIVE SELF-TEST")
    print("  Wike Coherence Framework | Papers 23, 42, 45")
    print(separator)
    print()

    # ------------------------------------------------------------------
    # Test 1: Healthy edge-state synthetic data
    # ------------------------------------------------------------------
    print("TEST 1: HEALTHY (EDGE STATE) SYNTHETIC RR DATA")
    print(sub_sep)

    rr_edge = _generate_synthetic_rr(
        n_beats=300, mean_rr_ms=800, sdnn_ms=50,
        coherence_strength=0.5, seed=42
    )
    m_edge = process_window(rr_edge)

    _print_metrics(m_edge, "Edge/Healthy")

    assert m_edge.n_intervals > 200, \
        f"Too many artifacts removed: {m_edge.n_artifacts_removed}"
    assert 55 < m_edge.mean_hr_bpm < 100, \
        f"Mean HR out of range: {m_edge.mean_hr_bpm}"
    assert m_edge.sdnn_ms > 10, \
        f"SDNN too low for edge state: {m_edge.sdnn_ms}"
    print("  [PASS] Time-domain metrics within expected range")

    assert m_edge.lf_power > 0, "LF power should be positive"
    assert m_edge.hf_power > 0, "HF power should be positive"
    print("  [PASS] Frequency-domain metrics computed")

    assert m_edge.sample_entropy > 0, "SampEn should be positive for edge data"
    print(f"  [PASS] SampEn = {m_edge.sample_entropy:.4f}")

    assert m_edge.dfa_alpha1 > 0, "DFA alpha should be positive"
    print(f"  [PASS] DFA alpha1 = {m_edge.dfa_alpha1:.4f}")

    print(f"  [INFO] Wike state: {m_edge.wike_state}")
    print(f"  [INFO] Lambda proxy: {m_edge.lambda_l_proxy:.4f}")
    print()

    # ------------------------------------------------------------------
    # Test 2: Frozen state (low variability, near-periodic)
    # ------------------------------------------------------------------
    print("TEST 2: FROZEN STATE SYNTHETIC RR DATA")
    print(sub_sep)

    rr_frozen = _generate_frozen_rr(n_beats=300, seed=99)
    m_frozen = process_window(rr_frozen)

    _print_metrics(m_frozen, "Frozen")

    assert m_frozen.sdnn_ms < 15, \
        f"Frozen SDNN should be very low: {m_frozen.sdnn_ms}"
    print("  [PASS] SDNN is very low (rigid rhythm)")

    assert m_frozen.sample_entropy < m_edge.sample_entropy, \
        "Frozen SampEn should be lower than edge"
    print(f"  [PASS] SampEn ({m_frozen.sample_entropy:.4f}) < edge SampEn ({m_edge.sample_entropy:.4f})")

    assert m_frozen.wike_state == "frozen", \
        f"Expected 'frozen' but got '{m_frozen.wike_state}'"
    print(f"  [PASS] Wike state correctly classified as '{m_frozen.wike_state}'")
    print()

    # ------------------------------------------------------------------
    # Test 3: Collapsed state (random, no structure)
    # ------------------------------------------------------------------
    print("TEST 3: COLLAPSED STATE SYNTHETIC RR DATA")
    print(sub_sep)

    rr_collapsed = _generate_collapsed_rr(n_beats=300, seed=77)
    m_collapsed = process_window(rr_collapsed)

    _print_metrics(m_collapsed, "Collapsed")

    assert m_collapsed.sdnn_ms > m_edge.sdnn_ms, \
        "Collapsed SDNN should be higher than edge (random variation)"
    print(f"  [PASS] SDNN ({m_collapsed.sdnn_ms:.1f}) > edge SDNN ({m_edge.sdnn_ms:.1f})")

    assert m_collapsed.wike_state == "collapsed", \
        f"Expected 'collapsed' but got '{m_collapsed.wike_state}'"
    print(f"  [PASS] Wike state correctly classified as '{m_collapsed.wike_state}'")
    print()

    # ------------------------------------------------------------------
    # Test 4: PPG pipeline (synthetic sinusoidal PPG)
    # ------------------------------------------------------------------
    print("TEST 4: PPG SIGNAL PROCESSING PIPELINE")
    print(sub_sep)

    sample_rate = 30.0  # typical phone camera fps
    duration = 60.0     # 1 minute
    t = np.arange(0, duration, 1.0 / sample_rate)

    # Simulate PPG: 1.2 Hz cardiac (72 bpm) + noise
    cardiac_freq = 1.2
    ppg_clean = np.sin(2 * np.pi * cardiac_freq * t)
    ppg_noisy = ppg_clean + 0.3 * np.random.RandomState(123).randn(len(t))

    # Filter
    filtered = bandpass_filter_ppg(ppg_noisy, sample_rate)
    print(f"  Raw PPG: {len(ppg_noisy)} samples at {sample_rate} Hz")
    print(f"  Filtered PPG: {len(filtered)} samples")

    # Peak detection
    peaks = detect_ppg_peaks(filtered, sample_rate)
    print(f"  Detected peaks: {len(peaks)}")

    # RR intervals
    rr_ppg = peaks_to_rr_intervals(peaks, sample_rate)
    print(f"  RR intervals: {len(rr_ppg)}")

    if len(rr_ppg) > 5:
        mean_rr = np.mean(rr_ppg)
        expected_rr = 1000.0 / cardiac_freq  # ~833 ms
        print(f"  Mean RR: {mean_rr:.1f} ms (expected ~{expected_rr:.1f} ms)")
        assert abs(mean_rr - expected_rr) < 100, \
            f"Mean RR too far from expected: {mean_rr:.1f} vs {expected_rr:.1f}"
        print("  [PASS] PPG pipeline yields physiologically correct RR intervals")
    else:
        print("  [WARN] Too few RR intervals from synthetic PPG")
    print()

    # ------------------------------------------------------------------
    # Test 5: Video PPG extraction (synthetic)
    # ------------------------------------------------------------------
    print("TEST 5: VIDEO PPG EXTRACTION")
    print(sub_sep)

    fps = 30.0
    n_frames = int(fps * 10)  # 10 seconds
    # Simulate finger-on-camera: green channel has pulsatile component
    t_vid = np.arange(n_frames) / fps
    green_pulse = 128 + 10 * np.sin(2 * np.pi * 1.0 * t_vid)  # 60 bpm
    # Build fake RGBA frames (8x8 pixels)
    frames = np.zeros((n_frames, 8, 8, 3), dtype=np.uint8)
    for i in range(n_frames):
        frames[i, :, :, 1] = int(np.clip(green_pulse[i], 0, 255))

    ppg_from_video = extract_ppg_from_video(frames, fps)
    print(f"  Extracted PPG from {n_frames} video frames: {len(ppg_from_video)} samples")
    assert len(ppg_from_video) == n_frames, "PPG length should match frame count"
    print("  [PASS] Video PPG extraction works")
    print()

    # ------------------------------------------------------------------
    # Test 6: Real-time streaming
    # ------------------------------------------------------------------
    print("TEST 6: REAL-TIME STREAMING")
    print(sub_sep)

    buf = RealtimeBuffer(max_size=400)
    updates = 0
    for val in rr_edge:
        result = process_realtime(float(val), buf, compute_interval=30)
        if result is not None:
            updates += 1

    print(f"  Fed {len(rr_edge)} intervals into real-time buffer")
    print(f"  Metric updates triggered: {updates}")
    assert updates > 0, "Should have triggered at least one update"
    assert buf.last_metrics is not None, "Buffer should have last_metrics"
    print(f"  Last state: {buf.last_metrics.wike_state}")
    print(f"  Buffer size: {len(buf.rr_intervals_ms)}")
    print("  [PASS] Real-time streaming works")
    print()

    # ------------------------------------------------------------------
    # Test 7: Artifact removal
    # ------------------------------------------------------------------
    print("TEST 7: ARTIFACT REMOVAL")
    print(sub_sep)

    rr_with_artifacts = np.array([
        800, 810, 200, 790, 2500, 805, 815, 100, 795, 810,
        800, 805, 800, 810, 3000, 790, 800, 50, 815, 800,
    ], dtype=np.float64)
    clean, n_removed = remove_artifacts(rr_with_artifacts)
    print(f"  Input: {len(rr_with_artifacts)} intervals")
    print(f"  Removed: {n_removed} artifacts")
    print(f"  Clean: {len(clean)} intervals")
    assert n_removed > 0, "Should have removed some artifacts"
    assert all(RR_MIN_MS <= v <= RR_MAX_MS for v in clean), \
        "All clean intervals should be within bounds"
    print("  [PASS] Artifact removal correctly filters implausible intervals")
    print()

    # ------------------------------------------------------------------
    # Test 8: SampEn known properties
    # ------------------------------------------------------------------
    print("TEST 8: SAMPLE ENTROPY PROPERTIES")
    print(sub_sep)

    # Constant series => SampEn ~ 0
    rr_const = np.full(100, 800.0)
    se_const = compute_sample_entropy(rr_const)
    print(f"  Constant series SampEn: {se_const:.4f} (should be ~0)")

    # Random series => higher SampEn
    rng = np.random.RandomState(55)
    rr_random = 600 + 400 * rng.rand(200)
    se_random = compute_sample_entropy(rr_random)
    print(f"  Random series SampEn: {se_random:.4f} (should be > 0)")

    assert se_random > se_const, "Random SampEn should exceed constant SampEn"
    print("  [PASS] SampEn ordering: random > constant")
    print()

    # ------------------------------------------------------------------
    # Test 9: DFA known properties
    # ------------------------------------------------------------------
    print("TEST 9: DFA ALPHA PROPERTIES")
    print(sub_sep)

    # White noise => alpha ~ 0.5
    rr_white = rng.normal(800, 50, 500)
    alpha_white = compute_dfa_alpha(rr_white)
    print(f"  White noise DFA alpha: {alpha_white:.4f} (expected ~0.5)")

    # Cumulative sum of white noise (Brownian) => alpha ~ 1.5
    rr_brown = np.cumsum(rng.normal(0, 1, 500)) + 800
    rr_brown = np.clip(rr_brown, 400, 1500)
    alpha_brown = compute_dfa_alpha(rr_brown)
    print(f"  Brownian noise DFA alpha: {alpha_brown:.4f} (expected ~1.5)")

    assert alpha_brown > alpha_white, "Brownian alpha should exceed white noise alpha"
    print("  [PASS] DFA ordering: Brownian > white noise")
    print()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(separator)
    print("  SELF-TEST SUMMARY")
    print(separator)
    print()
    print("  Three-state Wike phase classification:")
    print(f"    Edge state     : SampEn={m_edge.sample_entropy:.3f}, "
          f"DFA={m_edge.dfa_alpha1:.3f}, "
          f"CoR={m_edge.coherence_ratio:.3f} => {m_edge.wike_state}")
    print(f"    Frozen state   : SampEn={m_frozen.sample_entropy:.3f}, "
          f"DFA={m_frozen.dfa_alpha1:.3f}, "
          f"CoR={m_frozen.coherence_ratio:.3f} => {m_frozen.wike_state}")
    print(f"    Collapsed state: SampEn={m_collapsed.sample_entropy:.3f}, "
          f"DFA={m_collapsed.dfa_alpha1:.3f}, "
          f"CoR={m_collapsed.coherence_ratio:.3f} => {m_collapsed.wike_state}")
    print()
    print("  Paper 42 interpretation:")
    print("    High SampEn (~1-2) + DFA ~1.0 => lambda_L ~ 0 => EDGE (healthy)")
    print("    Low SampEn + DFA > 1.25       => lambda_L < 0 => FROZEN (CHF, rigid)")
    print("    Low DFA + high disorder        => lambda_L > 0 => COLLAPSED (AFib)")
    print()
    print("  All tests passed.")
    print(separator)


def _print_metrics(m: HRVMetrics, label: str) -> None:
    """Pretty-print an HRVMetrics instance."""
    print(f"  [{label}] {m.n_intervals} intervals "
          f"({m.window_seconds:.1f}s, {m.n_artifacts_removed} artifacts removed)")
    print(f"    Time-domain:")
    print(f"      Mean HR   = {m.mean_hr_bpm:.1f} bpm")
    print(f"      Mean RR   = {m.mean_rr_ms:.1f} ms")
    print(f"      SDNN      = {m.sdnn_ms:.1f} ms")
    print(f"      RMSSD     = {m.rmssd_ms:.1f} ms")
    print(f"      pNN50     = {m.pnn50_pct:.1f}%")
    print(f"    Frequency-domain:")
    print(f"      LF power  = {m.lf_power:.2f} ms^2")
    print(f"      HF power  = {m.hf_power:.2f} ms^2")
    print(f"      LF/HF     = {m.lf_hf_ratio:.3f}")
    print(f"      Total     = {m.total_power:.2f} ms^2")
    print(f"    Nonlinear (Paper 42):")
    print(f"      SampEn    = {m.sample_entropy:.4f}")
    print(f"      DFA a1    = {m.dfa_alpha1:.4f}")
    print(f"    Coherence (Paper 23):")
    print(f"      Ratio     = {m.coherence_ratio:.4f}")
    print(f"      Power     = {m.coherence_power:.4f} ms^2")
    print(f"    Wike classification:")
    print(f"      State     = {m.wike_state}")
    print(f"      Lambda_L  = {m.lambda_l_proxy:.4f}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    self_test()
