import json
import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

logger = logging.getLogger(__name__)

# Where the fitted scaler lives. Training writes it; inference reads it.
DEFAULT_SCALER_PATH = Path(__file__).resolve().parents[2] / "models" / "feature_scaler.json"

# The 13 features, in the exact order the model's input tensor expects.
#
# NOTE: this list is the ground truth. An older draft of the feature set — with
# geo_velocity_flag, merchant_category_code, beneficiary_risk_score and
# session_entropy at positions 5, 6, 10 and 12 — was never what got trained.
# Anything constructing a tensor by hand must follow the names below, or four of
# the twelve original inputs carry the wrong meaning and the model's output is
# noise. `geo_velocity_kmh` (position 13) is unrelated to that abandoned draft
# — see its docstring on `synthesize_geo_velocity` below: it is a deliberately
# fabricated feature, since PaySim carries no real location data at all.
FEATURE_COLS = [
    'amount_delta', 'balance_utilisation_ratio', 'channel_type_encoded',
    'time_of_day_flag', 'balance_drop_to_zero', 'amount_to_balance_ratio',
    'transaction_frequency_1h', 'transaction_frequency_24h',
    'cumulative_spend_ratio', 'dest_received_ratio', 'amount_zscore',
    'step_norm', 'geo_velocity_kmh'
]

SEQ_LEN = 5

# Fixed city coordinates used to synthesize a per-customer "home" location.
# Sydney-centric AU cities plus two international ones, so a "jump" between
# them produces a plausible-looking but entirely fabricated impossible-travel
# signal. See `synthesize_geo_velocity`.
_GEO_CITIES = [
    ("Sydney", -33.8688, 151.2093),
    ("Melbourne", -37.8136, 144.9631),
    ("Brisbane", -27.4698, 153.0251),
    ("Perth", -31.9505, 115.8605),
    ("Adelaide", -34.9285, 138.6007),
    ("Darwin", -12.4634, 130.8456),
    ("London", 51.5074, -0.1278),
    ("Singapore", 1.3521, 103.8198),
]
_GEO_LATS = np.array([c[1] for c in _GEO_CITIES])
_GEO_LONS = np.array([c[2] for c in _GEO_CITIES])
_N_CITIES = len(_GEO_CITIES)
_EARTH_RADIUS_KM = 6371.0


def synthesize_geo_velocity(df: pd.DataFrame) -> np.ndarray:
    """Fabricate a per-transaction geo-velocity (km/h) feature.

    SYNTHETIC. PaySim (the real training data) carries no location columns at
    all — only ``step, type, amount, nameOrig, oldbalanceOrg, newbalanceOrig,
    nameDest, oldbalanceDest, newbalanceDest, isFraud, isFlaggedFraud``. There
    is no real per-transaction geography to learn from. This manufactures one
    so "impossible travel" can be *learned* by the LSTM rather than only
    checked live by SIEM Rule 2 (``_rule_geo_velocity`` in
    ``src/siem/rule_engine.py``), whose Haversine formula this mirrors.

    Every customer (``nameOrig``) gets a deterministic "home" city, and each
    transaction has a small, hashed chance of "jumping" to a different one.
    That jump probability is deliberately biased toward transactions that
    already look risky by PaySim's own real fraud signature — ``TRANSFER``/
    ``CASH_OUT`` channel draining most of the origin balance, the same
    real-world pattern ``balance_drop_to_zero`` and ``amount_to_balance_ratio``
    already capture — rather than reading the ``isFraud`` label directly. That
    distinction matters: a feature computed from the true label could never be
    reproduced at serving time, when the label is exactly what's being
    predicted. Biasing on an observable proxy instead keeps this feature
    computable identically in training and at live inference, while still
    ending up correlated with ``isFraud`` in the training data — genuine,
    deployable signal, just built from a fabricated map rather than real GPS.

    All hashing uses ``pandas.util.hash_array`` — vectorised and stable across
    runs and process restarts, unlike Python's randomised built-in ``hash()``.
    This keeps the feature deterministic and order-invariant, the same
    requirement the PII obfuscation step already relies on.

    Args:
        df: Rows already sorted by ``['nameOrig', 'step']`` with a 0-based
            positional index — the same precondition every other feature in
            this module relies on.

    Returns:
        1-D array of length ``len(df)``: synthetic geo-velocity in km/h
        between each transaction and the previous one for the same customer
        (0.0 for a customer's first transaction, which has no "previous").
    """
    name_orig = df['nameOrig'].astype(str)
    step = df['step'].to_numpy(dtype=float)

    home_hash = pd.util.hash_array(name_orig.to_numpy(dtype=object))
    home_idx = (home_hash % _N_CITIES).astype(np.int64)

    # Observable-at-inference proxy for "looks risky" — never the isFraud
    # label itself. See the leakage note in the docstring above.
    balance_drain_ratio = df['amount'] / (df['oldbalanceOrg'] + 1e-6)
    looks_risky = df['type'].isin(['TRANSFER', 'CASH_OUT']) & (balance_drain_ratio > 0.90)
    jump_prob = np.where(looks_risky, 0.70, 0.02)

    jump_key = (name_orig + '|' + df['step'].astype(str)).to_numpy(dtype=object)
    jump_roll = (pd.util.hash_array(jump_key) % 10_000) / 10_000.0
    is_jump = jump_roll < jump_prob

    # Deterministic "other" city for a jump: offset the home index by a second
    # stable hash (1..N-1) so a jump never lands back on the home city.
    offset_key = ('jump:' + name_orig + '|' + df['step'].astype(str)).to_numpy(dtype=object)
    offset = 1 + (pd.util.hash_array(offset_key) % (_N_CITIES - 1)).astype(np.int64)
    dest_idx = np.where(is_jump, (home_idx + offset) % _N_CITIES, home_idx)

    geo = pd.DataFrame({
        'nameOrig': name_orig.to_numpy(),
        'step': step,
        'lat': _GEO_LATS[dest_idx],
        'lon': _GEO_LONS[dest_idx],
    })
    grp = geo.groupby('nameOrig', sort=False)
    prev_lat = grp['lat'].shift(1).to_numpy()
    prev_lon = grp['lon'].shift(1).to_numpy()
    prev_step = grp['step'].shift(1).to_numpy()
    has_prev = ~np.isnan(prev_lat)

    lat1, lat2 = np.radians(prev_lat), np.radians(geo['lat'].to_numpy())
    dlat = np.radians(geo['lat'].to_numpy() - prev_lat)
    dlon = np.radians(geo['lon'].to_numpy() - prev_lon)
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    a = np.clip(a, 0.0, 1.0)  # guards float error pushing slightly outside [0,1] before sqrt
    distance_km = _EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(a))

    delta_hours = np.clip(step - prev_step, 0.1, None)  # avoid divide-by-near-zero spikes
    velocity = np.where(has_prev, distance_km / delta_hours, 0.0)
    return np.nan_to_num(velocity, nan=0.0, posinf=0.0, neginf=0.0)


def save_scaler(scaler: MinMaxScaler, path: Path | str = DEFAULT_SCALER_PATH) -> None:
    """Persist a fitted scaler's per-feature range as JSON.

    Written as plain JSON rather than a pickle so it survives scikit-learn
    version changes and can be read by eye when a score looks wrong.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "feature_cols": FEATURE_COLS,
        "data_min": scaler.data_min_.tolist(),
        "data_max": scaler.data_max_.tolist(),
    }, indent=2), encoding="utf-8")
    logger.info("Feature scaler saved to %s", path)


def load_scaler(path: Path | str = DEFAULT_SCALER_PATH) -> Optional[MinMaxScaler]:
    """Rebuild the fitted scaler from disk, or return None if it is not there.

    Returns None rather than raising: the caller decides whether the absence is
    fatal. Training does not need it; inference does.
    """
    path = Path(path)
    if not path.exists():
        return None

    spec = json.loads(path.read_text(encoding="utf-8"))
    if spec.get("feature_cols") != FEATURE_COLS:
        raise ValueError(
            f"Scaler at {path} was fitted on a different feature set. "
            "Re-run training to regenerate it."
        )

    scaler = MinMaxScaler()
    data_min = np.asarray(spec["data_min"], dtype=float)
    data_max = np.asarray(spec["data_max"], dtype=float)
    # Reconstruct the attributes fit() would have produced. Guarding the range
    # against zero mirrors sklearn's own handling of constant features.
    scaler.data_min_ = data_min
    scaler.data_max_ = data_max
    scaler.data_range_ = np.where(data_max - data_min == 0, 1.0, data_max - data_min)
    scaler.scale_ = 1.0 / scaler.data_range_
    scaler.min_ = -data_min * scaler.scale_
    scaler.n_features_in_ = len(FEATURE_COLS)
    # Deliberately no `feature_names_in_`: transform() is always handed a plain
    # ndarray here, and setting it makes sklearn warn about missing names on
    # every call.
    return scaler


def compute_feature_matrix(
    df: pd.DataFrame,
    scaler_path: Path | str | None = None,
    fit: bool = True,
) -> Tuple[np.ndarray, pd.DataFrame]:
    """
    Computes and MinMax-scales the 13 engineered features, one row per transaction.

    Split out of ``engineer_features`` so that callers needing per-transaction
    features — scoring a live batch, for instance — share exactly this code
    rather than reimplementing the feature maths and drifting away from what
    the model was trained on.

    Args:
        df (pd.DataFrame): Raw PaySim-shaped data (post-PII obfuscation).
        scaler_path: Where the fitted scaler lives. When ``fit`` is True and this
                     is given, the newly-fitted scaler is saved there. When
                     ``fit`` is False it is loaded and applied.
        fit: True to fit on ``df`` (training). False to reuse the saved scaler
             (inference) — required for a small batch, whose own min/max carry
             no relation to the range the model was trained against.

    Returns:
        Tuple[np.ndarray, pd.DataFrame]:
            X_scaled of shape [num_rows, 13], every value in [0, 1]
            the sorted, positionally-indexed frame the rows correspond to

    Raises:
        ValueError: If input DataFrame is empty or missing required columns.
        FileNotFoundError: If ``fit`` is False and no saved scaler is found.
    """
    if df.empty:
        raise ValueError("Input DataFrame is empty.")

    required_cols = ['step', 'type', 'amount', 'nameOrig', 'oldbalanceOrg',
                     'newbalanceOrig', 'isFraud']
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    logger.info("Computing engineered features...")
    df = df.copy()
    
    # Sort logically by time (step) to ensure sequential operations make sense.
    # reset_index is critical: group.index must be 0-based positional so it can safely
    # index into X_scaled (a positional numpy array). Without this, scrambled index values
    # from the sort cause X_scaled[group_idx] to fetch completely wrong feature rows.
    df = df.sort_values(['nameOrig', 'step']).reset_index(drop=True)
    
    # 1. amount_delta = transaction amount - customer rolling average (window=10)
    df['amount_delta'] = df['amount'] - df.groupby('nameOrig')['amount'].transform(
        lambda x: x.rolling(10, min_periods=1).mean()
    )
    
    # 2. balance_utilisation_ratio = newbalanceOrig / (oldbalanceOrg + 1e-6),
    #    clipped to [0, 5]. oldbalanceOrg == 0 is common in PaySim (not a rare
    #    freak row), so the +1e-6 guard turns any transaction against a
    #    zero-balance origin into amount * 1e6 — one $69.9M CASH_OUT against a
    #    zero-balance account fit the training scaler's max at ~69.9 trillion,
    #    which compresses every ordinary ratio (including genuine fraud at
    #    ~1.0) down to ~0 after MinMax scaling. Clipping before scaling keeps
    #    the signal's dynamic range meaningful; 5x is generous headroom above
    #    the fraud signal (~1.0) while discarding the divide-by-near-zero tail.
    df['balance_utilisation_ratio'] = (
        df['newbalanceOrig'] / (df['oldbalanceOrg'] + 1e-6)
    ).clip(upper=5.0)
    
    # 3. channel_type_encoded
    channel_map = {'PAYMENT': 0, 'TRANSFER': 1, 'CASH_OUT': 2, 'DEBIT': 3, 'CASH_IN': 4}
    df['channel_type_encoded'] = df['type'].map(channel_map).fillna(0)
    
    # 4. time_of_day_flag (0 if 08:00-22:00 AEST, else 1). Assume step = hour.
    tod = df['step'] % 24
    df['time_of_day_flag'] = np.where((tod >= 8) & (tod <= 22), 0, 1)
    
    # 5. balance_drop_to_zero: 1 if origin balance is wiped to ~0 (strongest PaySim fraud signal)
    df['balance_drop_to_zero'] = (
        (df['newbalanceOrig'] < 1.0) & (df['oldbalanceOrg'] > 100)
    ).astype(float)

    # 6. amount_to_balance_ratio: fraud typically takes the full balance (ratio
    #    ≈ 1.0), clipped to [0, 5] for the same reason as feature 2 above —
    #    same +1e-6 guard, same zero-balance-origin blowup, same fix.
    df['amount_to_balance_ratio'] = (
        df['amount'] / (df['oldbalanceOrg'] + 1e-6)
    ).clip(upper=5.0)
    
    # 7. transaction_frequency_1h (count in last 1 step)
    df['transaction_frequency_1h'] = df.groupby(['nameOrig', 'step'])['step'].transform('count')
    
    # 8. transaction_frequency_24h (mock approximation: rolling count)
    df['transaction_frequency_24h'] = df.groupby('nameOrig')['step'].transform(
        lambda x: x.rolling(24, min_periods=1).count()
    )
    
    # 9. cumulative_spend_ratio (amount / customer 30-day average)
    overall_avg = df.groupby('nameOrig')['amount'].transform('mean') + 1e-6
    df['cumulative_spend_ratio'] = df['amount'] / overall_avg
    
    # 10. dest_received_ratio: how much the destination received vs amount sent
    #     legitimate ≈ 1.0; fraud mules often already moved money so dest balance doesn't match
    df['dest_received_ratio'] = (df['newbalanceDest'] - df['oldbalanceDest']) / (df['amount'] + 1e-6)
    
    # 11. amount_zscore = (amount - customer_mean) / customer_std
    df['amount_zscore'] = df.groupby('nameOrig')['amount'].transform(
        lambda x: (x - x.mean()) / (x.std() + 1e-6)
    ).fillna(0)
    
    # 12. step_norm: normalised time position within the simulation (continuous temporal signal)
    df['step_norm'] = df['step'] / (df['step'].max() + 1e-6)

    # 13. geo_velocity_kmh: SYNTHETIC — see synthesize_geo_velocity's docstring.
    df['geo_velocity_kmh'] = synthesize_geo_velocity(df)

    # Fill any remaining NaNs/Infs
    X_raw = df[FEATURE_COLS].replace([np.inf, -np.inf], np.nan).fillna(0).values

    # Normalise features to [0, 1].
    #
    # Two things ride on this. The LSTM saturates on out-of-range inputs — hand
    # it a raw feature value like 8.0 and every window collapses to the same
    # near-zero probability. And the scaling must be the *training* scaling:
    # refitting on a small batch sets min/max from that batch's own extremes, so
    # an identical transaction scales to a different number than it did during
    # training and the model's answer is confidently wrong rather than absent.
    if fit:
        scaler = MinMaxScaler()
        X_scaled = scaler.fit_transform(X_raw)
        if scaler_path is not None:
            save_scaler(scaler, scaler_path)
    else:
        scaler = load_scaler(scaler_path or DEFAULT_SCALER_PATH)
        if scaler is None:
            raise FileNotFoundError(
                f"No fitted scaler at {scaler_path or DEFAULT_SCALER_PATH}. "
                "Inference needs the range the model was trained on; re-run "
                "training against the PaySim dataset to regenerate it."
            )
        X_scaled = scaler.transform(X_raw)

    return X_scaled, df


def engineer_features(
    df: pd.DataFrame,
    scaler_path: Path | str | None = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Engineers 13 features from raw PaySim data, normalises them, and returns
    a sliding window (sequence_length=5) representation for LSTM input.

    Args:
        df (pd.DataFrame): The raw PaySim dataset (post-PII obfuscation).
        scaler_path: If given, the fitted scaler is saved here. A training run
                     should always pass this — without the saved range, nothing
                     downstream can scale a live transaction the way the model
                     expects, and inference silently produces wrong answers.

    Returns:
        Tuple[np.ndarray, np.ndarray]:
            X array of shape [num_sequences, 5, 13]
            y array of shape [num_sequences]

    Raises:
        ValueError: If input DataFrame is empty or missing required columns.
    """
    X_scaled, df = compute_feature_matrix(df, scaler_path=scaler_path, fit=True)

    logger.info("Building sequences of 5 transactions per customer...")
    seq_len = SEQ_LEN
    X_seq = []
    y_seq = []

    for _, group in df.groupby('nameOrig'):
        group_idx = group.index
        x_group = X_scaled[group_idx]
        y_group = group['isFraud'].values
        
        # Sliding window
        if len(x_group) >= seq_len:
            for i in range(len(x_group) - seq_len + 1):
                X_seq.append(x_group[i:i+seq_len])
                # Target is whether the last transaction in the window is fraud
                y_seq.append(y_group[i+seq_len-1])
        else:
            # If customer has fewer than 5 transactions, pad with zeros at the beginning
            pad_len = seq_len - len(x_group)
            pad_x = np.zeros((pad_len, len(FEATURE_COLS)))
            padded_x = np.vstack([pad_x, x_group])
            X_seq.append(padded_x)
            y_seq.append(y_group[-1])

    X_out = np.array(X_seq)
    y_out = np.array(y_seq)
    
    logger.info(f"Engineered sequences: shape {X_out.shape}. Fraud ratio: {np.mean(y_out):.4%}")
    return X_out, y_out
