import os
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from src.pipeline.pii_obfuscation import obfuscate_pii
from src.pipeline.feature_engineering import engineer_features
import logging

logging.basicConfig(level=logging.INFO)

def main():
    print("Starting data pipeline...")
    # Generate mock data since real PaySim dataset is too large
    np.random.seed(42)
    n_samples = 15000
    
    df = pd.DataFrame({
        'step': np.random.randint(1, 100, n_samples),
        'type': np.random.choice(['PAYMENT', 'TRANSFER', 'CASH_OUT', 'DEBIT', 'CASH_IN'], n_samples),
        'amount': np.random.uniform(10, 15000, n_samples),
        'nameOrig': [f'C{i}' for i in np.random.randint(1000, 2000, n_samples)],
        'oldbalanceOrg': np.random.uniform(0, 50000, n_samples),
        'newbalanceOrig': np.random.uniform(0, 50000, n_samples),
        'nameDest': [f'M{i}' for i in np.random.randint(5000, 6000, n_samples)],
        'isFraud': np.random.choice([0, 1], size=n_samples, p=[0.99, 0.01])
    })
    
    print("Obfuscating PII...")
    df = obfuscate_pii(df, ['nameOrig', 'nameDest'])
    
    print("Engineering features...")
    X, y = engineer_features(df)
    
    print(f"Features shape: {X.shape}, Target shape: {y.shape}")
    
    fraud_ratio = y.sum() / len(y) if len(y) > 0 else 0
    print(f"Fraud ratio: {fraud_ratio:.4%}")
    if fraud_ratio > 0:
        pos_weight = (1 - fraud_ratio) / fraud_ratio
        print(f"Suggested class weight (pos_weight): {pos_weight:.2f}")
    
    print("Splitting data (70% train, 15% val, 15% test)...")
    try:
        X_temp, X_test, y_temp, y_test = train_test_split(X, y, test_size=0.15, stratify=y, random_state=42)
        X_train, X_val, y_train, y_val = train_test_split(X_temp, y_temp, test_size=0.15/0.85, stratify=y_temp, random_state=42)
    except ValueError:
        print("Warning: Stratification failed, falling back to random split.")
        X_temp, X_test, y_temp, y_test = train_test_split(X, y, test_size=0.15, random_state=42)
        X_train, X_val, y_train, y_val = train_test_split(X_temp, y_temp, test_size=0.15/0.85, random_state=42)
        
    os.makedirs('data/processed', exist_ok=True)
    np.save('data/processed/X_train.npy', X_train)
    np.save('data/processed/y_train.npy', y_train)
    np.save('data/processed/X_val.npy', X_val)
    np.save('data/processed/y_val.npy', y_val)
    np.save('data/processed/X_test.npy', X_test)
    np.save('data/processed/y_test.npy', y_test)
    print("Saved Numpy array distributions to /data/processed/")

if __name__ == "__main__":
    main()
