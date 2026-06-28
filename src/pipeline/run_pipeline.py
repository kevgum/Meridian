import os
import argparse
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from src.pipeline.pii_obfuscation import obfuscate_pii
from src.pipeline.feature_engineering import engineer_features
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PAYSIM_CSV = 'data/PS_20174392719_1491204439457_log.csv'
PAYSIM_COLUMNS = ['step', 'type', 'amount', 'nameOrig', 'oldbalanceOrg',
                  'newbalanceOrig', 'nameDest', 'oldbalanceDest', 'newbalanceDest',
                  'isFraud', 'isFlaggedFraud']


def load_paysim(csv_path: str, sample: int = 0) -> pd.DataFrame:
    logger.info(f"Loading PaySim CSV from {csv_path} ...")
    # float32 halves memory vs default float64
    float_cols = {'amount': 'float32', 'oldbalanceOrg': 'float32', 'newbalanceOrig': 'float32',
                  'oldbalanceDest': 'float32', 'newbalanceDest': 'float32'}
    df = pd.read_csv(csv_path, dtype=float_cols)
    df.columns = df.columns.str.strip()
    missing = [c for c in PAYSIM_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"PaySim CSV missing columns: {missing}")
    if sample and sample < len(df):
        df = df.groupby('isFraud', group_keys=False).apply(
            lambda g: g.sample(min(len(g), int(sample * len(g) / len(df))), random_state=42)
        ).reset_index(drop=True)
        logger.info(f"Sampled to {len(df):,} rows (stratified). Fraud ratio: {df['isFraud'].mean():.4%}")
    else:
        logger.info(f"Loaded {len(df):,} rows. Fraud ratio: {df['isFraud'].mean():.4%}")
    return df[PAYSIM_COLUMNS]


def generate_mock(n_samples: int = 15000) -> pd.DataFrame:
    logger.info(f"Generating {n_samples:,} mock transactions ...")
    np.random.seed(42)
    return pd.DataFrame({
        'step': np.random.randint(1, 100, n_samples),
        'type': np.random.choice(['PAYMENT', 'TRANSFER', 'CASH_OUT', 'DEBIT', 'CASH_IN'], n_samples),
        'amount': np.random.uniform(10, 15000, n_samples),
        'nameOrig': [f'C{i}' for i in np.random.randint(1000, 2000, n_samples)],
        'oldbalanceOrg': np.random.uniform(0, 50000, n_samples),
        'newbalanceOrig': np.random.uniform(0, 50000, n_samples),
        'nameDest': [f'M{i}' for i in np.random.randint(5000, 6000, n_samples)],
        'isFraud': np.random.choice([0, 1], size=n_samples, p=[0.99, 0.01]),
    })


def main():
    parser = argparse.ArgumentParser(description='Meridian Sentinel data pipeline')
    parser.add_argument(
        '--csv', metavar='PATH', default=None,
        help=f'Path to PaySim CSV. Defaults to {PAYSIM_CSV} if it exists, otherwise mock data.'
    )
    parser.add_argument('--mock', action='store_true', help='Force mock data even if CSV exists')
    parser.add_argument('--sample', type=int, default=0,
                        help='Stratified row sample from CSV (0 = use all rows). Use 2000000 on Colab free tier.')
    args = parser.parse_args()

    # Resolve data source
    if args.mock:
        df = generate_mock()
    elif args.csv:
        df = load_paysim(args.csv, sample=args.sample)
    elif os.path.exists(PAYSIM_CSV):
        df = load_paysim(PAYSIM_CSV, sample=args.sample)
    else:
        logger.warning(f"PaySim CSV not found at {PAYSIM_CSV}. Using mock data.")
        logger.warning("To use real data: python -m src.pipeline.run_pipeline --csv <path>")
        df = generate_mock()

    logger.info("Obfuscating PII ...")
    df = obfuscate_pii(df, ['nameOrig', 'nameDest'])

    logger.info("Engineering features ...")
    X, y = engineer_features(df)
    logger.info(f"Features shape: {X.shape}  Target shape: {y.shape}")

    fraud_ratio = y.mean()
    logger.info(f"Fraud ratio: {fraud_ratio:.4%}")
    if fraud_ratio > 0:
        pos_weight = (1 - fraud_ratio) / fraud_ratio
        logger.info(f"Suggested pos_weight for BCEWithLogitsLoss: {pos_weight:.1f}")

    logger.info("Splitting data (70% train / 15% val / 15% test, stratified) ...")
    try:
        X_tmp, X_test, y_tmp, y_test = train_test_split(
            X, y, test_size=0.15, stratify=y, random_state=42)
        X_train, X_val, y_train, y_val = train_test_split(
            X_tmp, y_tmp, test_size=0.15 / 0.85, stratify=y_tmp, random_state=42)
    except ValueError:
        logger.warning("Stratification failed — falling back to random split.")
        X_tmp, X_test, y_tmp, y_test = train_test_split(X, y, test_size=0.15, random_state=42)
        X_train, X_val, y_train, y_val = train_test_split(
            X_tmp, y_tmp, test_size=0.15 / 0.85, random_state=42)

    os.makedirs('data/processed', exist_ok=True)
    for name, arr in [('X_train', X_train), ('y_train', y_train),
                      ('X_val', X_val),   ('y_val', y_val),
                      ('X_test', X_test), ('y_test', y_test)]:
        np.save(f'data/processed/{name}.npy', arr)
    logger.info("Saved arrays to data/processed/")
    logger.info(f"  Train: {X_train.shape}  Val: {X_val.shape}  Test: {X_test.shape}")


if __name__ == '__main__':
    main()
