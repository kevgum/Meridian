# Feature Engineering & Class Imbalance Strategy

## Engineered Features (13-Feature Pipeline)
The transaction data is modeled sequentially. We group events per customer (`nameOrig`) and create an [Nx5x13] tensor representing rolling windows of 5 transactions per customer.

> **This list previously named a draft feature set** (`geo_velocity_flag`, `merchant_category_code`, `beneficiary_risk_score`, `session_entropy`) that was never what got trained — see `CLAUDE.md`'s Model Details section. The 13 features below are `FEATURE_COLS` in `src/pipeline/feature_engineering.py`, the actual ground truth.

1. **`amount_delta`**: Difference between current transaction amount and customer's rolling 10-transaction average.
2. **`balance_utilisation_ratio`**: `newbalanceOrig` divided by `oldbalanceOrg` (normalized). Detects sudden account sweeping.
3. **`channel_type_encoded`**: Ordinal mapping (`PAYMENT=0`, `TRANSFER=1`, `CASH_OUT=2`, `DEBIT=3`, `CASH_IN=4`).
4. **`time_of_day_flag`**: Derived from simulation steps. 0 for business hours (8am - 10pm), 1 for off-hours.
5. **`balance_drop_to_zero`**: 1 if the origin balance was emptied (`newbalanceOrig < 1` and `oldbalanceOrg > 100`) — the strongest raw PaySim fraud signal.
6. **`amount_to_balance_ratio`**: `amount / oldbalanceOrg`; fraud typically takes the whole balance (≈ 1.0).
7. **`transaction_frequency_1h`**: Quick-fire transaction rate limit using a 1-step window.
8. **`transaction_frequency_24h`**: Total events observed in the rolling 24-step window.
9. **`cumulative_spend_ratio`**: The transaction amount scaled by the customer's overall average.
10. **`dest_received_ratio`**: `(newbalanceDest - oldbalanceDest) / amount`; legitimate ≈ 1.0, fraud mules often already moved the money on.
11. **`amount_zscore`**: Amount scaled into Z-Score tracking standard deviations away from the customer's typical behaviour.
12. **`step_norm`**: Normalised time position within the simulation.
13. **`geo_velocity_kmh`**: **SYNTHETIC.** PaySim carries no real location data, so this is fabricated: a deterministic, hashed per-customer travel pattern, biased toward `TRANSFER`/`CASH_OUT` transactions draining most of the balance (an observable proxy for risk, not the `isFraud` label — a feature built from the label couldn't be reproduced at serving time). Full construction in `synthesize_geo_velocity`, `src/pipeline/feature_engineering.py`.

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
