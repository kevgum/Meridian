import hashlib
import pandas as pd
from typing import List


def obfuscate_pii(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    """
    Obfuscates Personal Identifiable Information (PII) columns using SHA-256 hashing.
    
    Args:
        df (pd.DataFrame): The input transaction DataFrame.
        columns (List[str]): List of column names containing PII to hash.
        
    Returns:
        pd.DataFrame: A new DataFrame with the specified PII columns hashed.
        
    Raises:
        ValueError: If any of the specified columns are not found in the DataFrame.
    """
    df_clean = df.copy()
    
    for col in columns:
        if col not in df_clean.columns:
            raise ValueError(f"Column '{col}' not found in the DataFrame.")
            
        df_clean[col] = df_clean[col].apply(
            lambda x: hashlib.sha256(str(x).encode('utf-8')).hexdigest() if pd.notnull(x) else x
        )
        
    return df_clean
