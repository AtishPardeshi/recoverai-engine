import pandas as pd
import numpy as np
from typing import Any
from sqlalchemy.orm import Session
from backend.app.models.transaction import Transaction
from backend.app.models.payment_failure import PaymentFailure
from backend.app.models.customer import Customer
from backend.app.models.recovery_case import RecoveryCase
from backend.app.models.recovery_outcome import RecoveryOutcome
from backend.app.schemas.common import TransactionStatusEnum, OutcomeResultEnum
from backend.app.ml.feature_engineering import feature_engineer, ALL_FEATURE_NAMES

class DatasetBuilder:
    """
    Deterministic dataset builder for RecoverAI supervised ML recovery model.
    Constructs train/validation/test matrices strictly from resolved historical failures (n=549).
    Excludes organic CAPTURED (5,274) and unresolved FAILED (1,161).
    """

    @staticmethod
    def build_supervised_dataset(db: Session) -> tuple[pd.DataFrame, np.ndarray, list[dict[str, Any]]]:
        """
        Builds complete supervised feature matrix X and target vector y from persisted DB records.
        """
        # 1. Query resolved historical cases ordered chronologically
        resolved_cases = (
            db.query(RecoveryCase)
            .join(Transaction, Transaction.id == RecoveryCase.transaction_id)
            .filter(
                Transaction.status.in_([
                    TransactionStatusEnum.RECOVERED.value,
                    TransactionStatusEnum.RECOVERY_EXHAUSTED.value,
                ])
            )
            .order_by(Transaction.created_at.asc(), Transaction.id.asc())
            .all()
        )

        total_resolved = len(resolved_cases)
        if total_resolved == 0:
            raise ValueError("No resolved historical recovery cases found in database.")

        feature_dicts = []
        targets = []
        metadata = []

        for case in resolved_cases:
            tx = case.transaction
            fail = tx.payment_failure
            cust = tx.customer

            # Ground truth target: 1 for RECOVERED, 0 for RECOVERY_EXHAUSTED
            y_val = 1 if tx.status == TransactionStatusEnum.RECOVERED.value else 0

            # Strict no-lookahead features extracted at failure time T
            feats = feature_engineer.extract_features_at_time(
                db=db,
                transaction=tx,
                payment_failure=fail,
                customer=cust,
                retry_count=0,
                as_of_time=tx.created_at,
            )

            feature_dicts.append(feats)
            targets.append(y_val)
            metadata.append({
                "case_id": case.id,
                "transaction_id": tx.id,
                "external_id": tx.external_id,
                "customer_id": cust.id,
                "created_at": tx.created_at.isoformat(),
                "status": tx.status,
                "target": y_val,
            })

        df_X = feature_engineer.to_dataframe(feature_dicts)
        y = np.array(targets, dtype=int)

        return df_X, y, metadata

    @staticmethod
    def split_chronologically(
        df_X: pd.DataFrame,
        y: np.ndarray,
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
    ) -> dict[str, Any]:
        """
        Splits dataset chronologically into train, validation, and test splits.
        """
        n = len(df_X)
        n_train = int(n * train_ratio)
        n_val = int(n * val_ratio)
        n_test = n - n_train - n_val

        X_train, y_train = df_X.iloc[:n_train], y[:n_train]
        X_val, y_val = df_X.iloc[n_train : n_train + n_val], y[n_train : n_train + n_val]
        X_test, y_test = df_X.iloc[n_train + n_val :], y[n_train + n_val :]

        return {
            "X_train": X_train,
            "y_train": y_train,
            "X_val": X_val,
            "y_val": y_val,
            "X_test": X_test,
            "y_test": y_test,
            "split_counts": {
                "total": n,
                "train": n_train,
                "validation": n_val,
                "test": n_test,
                "train_positives": int(sum(y_train)),
                "train_negatives": int(len(y_train) - sum(y_train)),
                "val_positives": int(sum(y_val)),
                "val_negatives": int(len(y_val) - sum(y_val)),
                "test_positives": int(sum(y_test)),
                "test_negatives": int(len(y_test) - sum(y_test)),
            },
        }

dataset_builder = DatasetBuilder()
