# Feature Engineering & Class Imbalance Strategy

## Engineered Features (12-Feature Pipeline)
The transaction data is modeled sequentially. We group events per customer (`nameOrig`) and create an [Nx5x12] tensor representing rolling windows of 5 transactions per customer. The 12 features chosen are:

1. **`amount_delta`**: Difference between current transaction amount and customer's rolling 10-transaction average.
2. **`balance_utilisation_ratio`**: `newbalanceOrig` divided by `oldbalanceOrg` (normalized). Detects sudden account sweeping. 
3. **`channel_type_encoded`**: Ordinal mapping (`PAYMENT=0`, `TRANSFER=1`, `CASH_OUT=2`, `DEBIT=3`, `CASH_IN=4`).
4. **`time_of_day_flag`**: Derived from simulation steps. 0 for business hours (8am - 10pm), 1 for off-hours.
5. **`geo_velocity_flag`**: Binary flag indicating physically impossible jumping behaviour (>500km/h).
6. **`merchant_category_code`**: Label-encoded. Risk profile depends on category (e.g. 5732=electronics, 5812=restaurants).
7. **`transaction_frequency_1h`**: Quick-fire transaction rate limit using a 1-step window.
8. **`transaction_frequency_24h`**: Total events observed in the rolling 24-step window. 
9. **`cumulative_spend_ratio`**: The transaction amount scaled by the customer's overall 30-day average. 
10. **`beneficiary_risk_score`**: Pre-computed baseline risk probability. 
11. **`amount_zscore`**: Amount scaled into Z-Score tracking standard deviations away from the customer's typical behaviour. 
12. **`session_entropy`**: Information entropy modeling the diversity of channels and merchants used in a narrow window. 

*All features are scaled using `MinMaxScaler` into the `[0,1]` range before passing into the LSTM.*

## Personal Identifiable Information (PII) Obfuscation
The PaySim dataset includes customer (`nameOrig`) and merchant/destination account (`nameDest`) strings. Before writing any data to `meridian-transactions-raw` in Elasticsearch, or extracting `.npy` sequences:
- We use SHA-256 to hash these IDs.
- Deterministic hashing retains analytical properties without leaking raw customer banking details.
- See `src/pipeline/pii_obfuscation.py`.

## Class Imbalance Strategy
Our raw target (`isFraud`) evaluates to roughly ~0.1%. Rather than over-sampling with SMOTE, we account for class imbalance directly via our objective function:
- During LSTM training, we use PyTorch's `BCEWithLogitsLoss`.
- `pos_weight` is set to ~800 to equally penalize the model when missing rare fraudulent patterns. 
