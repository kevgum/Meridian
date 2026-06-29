import numpy as np
import pandas as pd
from typing import Tuple
from sklearn.preprocessing import MinMaxScaler
import logging

logger = logging.getLogger(__name__)

def engineer_features(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    """
    Engineers 12 features from raw PaySim data, normalises them, and returns 
    a sliding window (sequence_length=5) representation for LSTM input.
    
    Args:
        df (pd.DataFrame): The raw PaySim dataset (post-PII obfuscation).
        
    Returns:
        Tuple[np.ndarray, np.ndarray]: 
            X array of shape [num_sequences, 5, 12]
            y array of shape [num_sequences]
            
    Raises:
        ValueError: If input DataFrame is empty or missing required columns.
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
    
    # 2. balance_utilisation_ratio = newbalanceOrig / (oldbalanceOrg + 1e-6)
    df['balance_utilisation_ratio'] = df['newbalanceOrig'] / (df['oldbalanceOrg'] + 1e-6)
    
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

    # 6. amount_to_balance_ratio: fraud typically takes the full balance (ratio ≈ 1.0)
    df['amount_to_balance_ratio'] = df['amount'] / (df['oldbalanceOrg'] + 1e-6)
    
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
    
    # Select features
    feature_cols = [
        'amount_delta', 'balance_utilisation_ratio', 'channel_type_encoded',
        'time_of_day_flag', 'balance_drop_to_zero', 'amount_to_balance_ratio',
        'transaction_frequency_1h', 'transaction_frequency_24h',
        'cumulative_spend_ratio', 'dest_received_ratio', 'amount_zscore',
        'step_norm'
    ]
    
    # Fill any remaining NaNs/Infs
    X_raw = df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0).values
    
    # Normalise features to [0, 1] using MinMaxScaler
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X_raw)
    
    logger.info("Building sequences of 5 transactions per customer...")
    seq_len = 5
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
            pad_x = np.zeros((pad_len, 12))
            padded_x = np.vstack([pad_x, x_group])
            X_seq.append(padded_x)
            y_seq.append(y_group[-1])

    X_out = np.array(X_seq)
    y_out = np.array(y_seq)
    
    logger.info(f"Engineered sequences: shape {X_out.shape}. Fraud ratio: {np.mean(y_out):.4%}")
    return X_out, y_out
