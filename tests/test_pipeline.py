import pandas as pd
import numpy as np
import pytest
from src.pipeline.pii_obfuscation import obfuscate_pii
from src.pipeline.feature_engineering import engineer_features

@pytest.fixture
def mock_paysim_data():
    """Generates a mock dataframe shaped like a typical PaySim dataset."""
    data = {
        'step': [1, 2, 3, 4, 5, 6, 7],
        'type': ['PAYMENT', 'TRANSFER', 'CASH_OUT', 'DEBIT', 'CASH_IN', 'PAYMENT', 'TRANSFER'],
        'amount': [100.0, 500.0, 200.0, 50.0, 1000.0, 150.0, 3000.0],
        'nameOrig': ['C123', 'C123', 'C123', 'C123', 'C123', 'C456', 'C456'],
        'oldbalanceOrg': [1000.0, 900.0, 400.0, 200.0, 150.0, 5000.0, 4850.0],
        'newbalanceOrig': [900.0, 400.0, 200.0, 150.0, 1150.0, 4850.0, 1850.0],
        'nameDest': ['M123', 'C789', 'C789', 'M456', 'C222', 'M789', 'C333'],
        'oldbalanceDest': [0.0, 0.0, 500.0, 0.0, 200.0, 0.0, 100.0],
        'newbalanceDest': [0.0, 500.0, 700.0, 0.0, 1200.0, 0.0, 3100.0],
        'isFraud': [0, 0, 0, 0, 0, 0, 1],
        'isFlaggedFraud': [0, 0, 0, 0, 0, 0, 0]
    }
    return pd.DataFrame(data)

def test_pii_obfuscation(mock_paysim_data):
    df_clean = obfuscate_pii(mock_paysim_data, columns=['nameOrig', 'nameDest'])
    
    # Original should be untouched (though mock_paysim_data fixture is fresh each time anyway)
    assert 'C123' in mock_paysim_data['nameOrig'].values
    
    # Hashed df should not have original IDs
    assert 'C123' not in df_clean['nameOrig'].values
    assert 'M123' not in df_clean['nameDest'].values
    
    # Check length and deterministic hashing
    assert len(df_clean['nameOrig'][0]) == 64  # SHA-256 length

def test_feature_engineering_shapes_and_values(mock_paysim_data):
    # Process
    df_clean = obfuscate_pii(mock_paysim_data, columns=['nameOrig', 'nameDest'])
    X, y = engineer_features(df_clean)
    
    # 2 customers means 2 sequences
    assert X.shape[0] == 2
    assert X.shape[1] == 5  # sequence length
    assert X.shape[2] == 12 # num features
    
    assert y.shape[0] == 2
    
    # Assert values in [0, 1] range (allow epsilon for float precision)
    assert np.all(X >= -1e-6)
    assert np.all(X <= 1.0 + 1e-6)
    
    # Assert no NaNs
    assert not np.isnan(X).any()
    assert not np.isnan(y).any()
