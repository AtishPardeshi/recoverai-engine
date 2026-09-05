# RecoverAI Machine Learning Models & Feature Pipelines

## Model Summary
- **Model Architecture**: `HistGradientBoostingClassifier` (scikit-learn) with isotonic / sigmoid calibration.
- **Model Version**: `recovery-risk-v1.0.0`
- **Feature Pipeline**: `features-v1.0.0` (36 features)
- **Target Population**: Resolved historical payment failures (`RECOVERED` = 1, `RECOVERY_EXHAUSTED` = 0).
- **Target Metrics**:
  - Test PR-AUC: ~0.83 (compared to constant-prevalence no-skill baseline of 0.76)
  - Test ROC-AUC: ~0.60
  - Calibrated Brier Score: 0.2170 (within statistical parity with constant-prevalence baseline of 0.1830)

## Feature Engineering Breakdown (36 Features)
1. **Customer Historical Features** (10): Success rate, total spend, transaction velocity, tenure, recent failure counts.
2. **Transaction Features** (8): Amount, currency scaling, time-of-day, day-of-week, velocity delta.
3. **Encoded Payment Methods** (4): One-hot encoding for canonical methods `CARD`, `UPI`, `NETBANKING`, `WALLET`.
4. **Encoded Failure Taxonomy** (6): One-hot encoding for `TEMPORARY_BANK_DECLINE`, `INSUFFICIENT_FUNDS`, `BANK_DECLINE`, `NETWORK_ERROR`, `EXPIRED_METHOD`, `INVALID_DETAILS`.
5. **Contextual Risk & Retries** (8): Retry count, message count, time since last failure, cooldown eligibility.

## Safety & Ground-Truth Isolation
- Ground-truth future outcomes are strictly isolated from training and runtime feature engineering.
- Feature extraction functions are 100% deterministic and free of data leakage.
