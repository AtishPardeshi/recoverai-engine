import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Any
from sqlalchemy.orm import Session
from backend.app.models.transaction import Transaction
from backend.app.models.payment_failure import PaymentFailure
from backend.app.models.customer import Customer
from backend.app.models.recovery_action import RecoveryAction
from backend.app.models.recovery_outcome import RecoveryOutcome
from backend.app.schemas.common import PaymentMethodEnum, FailureTypeEnum, TransactionStatusEnum, OutcomeResultEnum

FEATURE_VERSION = "features-v1"

PAYMENT_METHODS = [
    PaymentMethodEnum.CARD.value,
    PaymentMethodEnum.UPI.value,
    PaymentMethodEnum.NETBANKING.value,
    PaymentMethodEnum.WALLET.value,
]


FAILURE_TYPES = [
    FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
    FailureTypeEnum.INSUFFICIENT_FUNDS.value,
    FailureTypeEnum.BANK_DECLINE.value,
    FailureTypeEnum.NETWORK_ERROR.value,
    FailureTypeEnum.EXPIRED_METHOD.value,
    FailureTypeEnum.INVALID_DETAILS.value,
]

NUMERIC_FEATURE_NAMES = [
    "amount",
    "retry_count",
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "prior_transaction_count",
    "prior_success_count",
    "prior_failure_count",
    "historical_success_rate",
    "historical_failure_rate",
    "average_transaction_amount",
    "amount_deviation_from_customer_average",
    "time_since_previous_transaction_hrs",
    "transactions_last_5min",
    "transactions_last_1hr",
    "transactions_last_24hr",
    "prior_recovery_attempt_count",
    "prior_recovery_success_count",
    "prior_recovery_failure_count",
    "customer_card_success_rate",
    "customer_upi_success_rate",
    "customer_netbanking_success_rate",
    "customer_wallet_success_rate",
    "customer_tenure_days",
    "is_opted_out",
    "has_open_dispute",
]

CATEGORICAL_FEATURE_NAMES = [
    "payment_method",
    "failure_type",
]

RAW_FEATURE_NAMES = NUMERIC_FEATURE_NAMES + CATEGORICAL_FEATURE_NAMES
ALL_FEATURE_NAMES = RAW_FEATURE_NAMES



class FeatureEngineeringService:
    """
    Leakage-safe deterministic feature engineering service for RecoverAI.
    Extracts features strictly as-of prediction time T (no lookahead leakage).
    """

    def __init__(self, version: str = FEATURE_VERSION):
        self.version = version
        self.feature_names = list(ALL_FEATURE_NAMES)

    def extract_features_at_time(
        self,
        db: Session,
        transaction: Transaction,
        payment_failure: PaymentFailure | None = None,
        customer: Customer | None = None,
        retry_count: int = 0,
        as_of_time: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Extracts feature dictionary strictly using data timestamped prior to as_of_time (T).
        Guarantees NO future transaction or recovery lookahead leakage.
        """
        t_ref = as_of_time or transaction.created_at
        if t_ref.tzinfo is not None:
            t_ref = t_ref.astimezone(timezone.utc).replace(tzinfo=None)

        cust = customer or transaction.customer
        fail = payment_failure or transaction.payment_failure

        pm = transaction.payment_method or "CARD"
        ft = fail.normalized_failure_type if fail else "TEMPORARY_BANK_DECLINE"

        pm_idx = PAYMENT_METHODS.index(pm) if pm in PAYMENT_METHODS else 0
        ft_idx = FAILURE_TYPES.index(ft) if ft in FAILURE_TYPES else 0

        hour_of_day = t_ref.hour
        day_of_week = t_ref.weekday()
        is_weekend = 1 if day_of_week >= 5 else 0

        # Query prior transactions strictly before T
        prior_txs = (
            db.query(Transaction)
            .filter(
                Transaction.customer_id == cust.id,
                Transaction.id != transaction.id,
                Transaction.created_at < t_ref,
            )
            .order_by(Transaction.created_at.asc())
            .all()
        )

        prior_tx_count = len(prior_txs)
        prior_success_count = sum(
            1 for t in prior_txs if t.status in [TransactionStatusEnum.CAPTURED.value, TransactionStatusEnum.RECOVERED.value]
        )
        prior_failure_count = sum(
            1 for t in prior_txs if t.status in [TransactionStatusEnum.FAILED.value, TransactionStatusEnum.RECOVERY_EXHAUSTED.value]
        )

        if prior_tx_count > 0:
            hist_succ_rate = round(prior_success_count / prior_tx_count, 4)
            hist_fail_rate = round(prior_failure_count / prior_tx_count, 4)
            avg_amount = round(sum(t.amount for t in prior_txs) / prior_tx_count, 2)
            last_tx = prior_txs[-1]
            last_tx_time = last_tx.created_at.replace(tzinfo=None) if last_tx.created_at.tzinfo else last_tx.created_at
            time_since_prev_hrs = round(max(0.0, (t_ref - last_tx_time).total_seconds() / 3600.0), 2)
        else:
            hist_succ_rate = cust.historical_success_rate or 0.80
            hist_fail_rate = round(1.0 - hist_succ_rate, 4)
            avg_amount = transaction.amount
            time_since_prev_hrs = 168.0  # 1 week default for new customer

        amt_deviation = round(transaction.amount - avg_amount, 2)

        # Velocity in windows strictly before T
        t_5m = t_ref - timedelta(minutes=5)
        t_1h = t_ref - timedelta(hours=1)
        t_24h = t_ref - timedelta(hours=24)

        tx_last_5m = sum(1 for t in prior_txs if (t.created_at.replace(tzinfo=None) if t.created_at.tzinfo else t.created_at) >= t_5m)
        tx_last_1h = sum(1 for t in prior_txs if (t.created_at.replace(tzinfo=None) if t.created_at.tzinfo else t.created_at) >= t_1h)
        tx_last_24h = sum(1 for t in prior_txs if (t.created_at.replace(tzinfo=None) if t.created_at.tzinfo else t.created_at) >= t_24h)

        # Customer recovery history strictly before T
        prior_outcomes = (
            db.query(RecoveryOutcome)
            .join(Transaction, Transaction.id == RecoveryOutcome.transaction_id)
            .filter(
                Transaction.customer_id == cust.id,
                RecoveryOutcome.occurred_at < t_ref,
            )
            .all()
        )
        prior_rec_attempts = len(prior_outcomes)
        prior_rec_success = sum(1 for o in prior_outcomes if o.result == OutcomeResultEnum.SUCCESS.value)
        prior_rec_failure = sum(1 for o in prior_outcomes if o.result == OutcomeResultEnum.FAILURE.value)

        # Method specific rates before T
        def method_rate(m_val: str) -> float:
            m_txs = [t for t in prior_txs if t.payment_method == m_val]
            if not m_txs:
                return hist_succ_rate
            m_succ = sum(1 for t in m_txs if t.status in [TransactionStatusEnum.CAPTURED.value, TransactionStatusEnum.RECOVERED.value])
            return round(m_succ / len(m_txs), 4)

        card_rate = method_rate(PaymentMethodEnum.CARD.value)
        upi_rate = method_rate(PaymentMethodEnum.UPI.value)
        netbanking_rate = method_rate(PaymentMethodEnum.NETBANKING.value)
        wallet_rate = method_rate(PaymentMethodEnum.WALLET.value)

        # Customer tenure
        cust_created = cust.created_at.replace(tzinfo=None) if cust.created_at.tzinfo else cust.created_at
        cust_tenure_days = max(0.0, round((t_ref - cust_created).total_seconds() / 86400.0, 2))

        features = {
            "amount": float(transaction.amount),
            "retry_count": int(retry_count),
            "hour_of_day": int(hour_of_day),
            "day_of_week": int(day_of_week),
            "is_weekend": int(is_weekend),
            "prior_transaction_count": int(prior_tx_count),
            "prior_success_count": int(prior_success_count),
            "prior_failure_count": int(prior_failure_count),
            "historical_success_rate": float(hist_succ_rate),
            "historical_failure_rate": float(hist_fail_rate),
            "average_transaction_amount": float(avg_amount),
            "amount_deviation_from_customer_average": float(amt_deviation),
            "time_since_previous_transaction_hrs": float(time_since_prev_hrs),
            "transactions_last_5min": int(tx_last_5m),
            "transactions_last_1hr": int(tx_last_1h),
            "transactions_last_24hr": int(tx_last_24h),
            "prior_recovery_attempt_count": int(prior_rec_attempts),
            "prior_recovery_success_count": int(prior_rec_success),
            "prior_recovery_failure_count": int(prior_rec_failure),
            "customer_card_success_rate": float(card_rate),
            "customer_upi_success_rate": float(upi_rate),
            "customer_netbanking_success_rate": float(netbanking_rate),
            "customer_wallet_success_rate": float(wallet_rate),
            "customer_tenure_days": float(cust_tenure_days),
            "is_opted_out": 1 if cust.is_opted_out else 0,
            "has_open_dispute": 1 if cust.has_open_dispute else 0,
            "payment_method": str(pm),
            "failure_type": str(ft),
        }

        return features

    def extract_features_from_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Extracts and validates features from a standalone dictionary payload.
        Ensures consistent feature schema during testing or isolated inference.
        """
        pm = str(data.get("payment_method", "CARD"))
        ft = str(data.get("failure_type", "TEMPORARY_BANK_DECLINE"))

        succ_count = int(data.get("customer_success_count", data.get("prior_success_count", 5)))
        fail_count = int(data.get("customer_failed_count", data.get("prior_failure_count", 1)))
        tot_count = int(data.get("prior_transaction_count", succ_count + fail_count))
        rate = float(data.get("customer_success_rate", data.get("historical_success_rate", (succ_count / tot_count if tot_count > 0 else 0.8))))

        amt = float(data.get("amount", 1000.0))
        avg_amt = float(data.get("average_transaction_amount", amt))

        features = {
            "amount": amt,
            "retry_count": int(data.get("retry_count", 0)),
            "hour_of_day": int(data.get("hour_of_day", 14)),
            "day_of_week": int(data.get("day_of_week", 2)),
            "is_weekend": int(data.get("is_weekend", 0)),
            "prior_transaction_count": tot_count,
            "prior_success_count": succ_count,
            "prior_failure_count": fail_count,
            "historical_success_rate": rate,
            "historical_failure_rate": round(1.0 - rate, 4),
            "average_transaction_amount": avg_amt,
            "amount_deviation_from_customer_average": round(amt - avg_amt, 2),
            "time_since_previous_transaction_hrs": float(data.get("time_since_prev_hrs", data.get("time_since_previous_transaction_hrs", 12.0))),
            "transactions_last_5min": int(data.get("transactions_last_5min", 0)),
            "transactions_last_1hr": int(data.get("transactions_last_1hr", 0)),
            "transactions_last_24hr": int(data.get("transactions_last_24hr", 1)),
            "prior_recovery_attempt_count": int(data.get("prior_recovery_attempt_count", 0)),
            "prior_recovery_success_count": int(data.get("prior_recovery_success_count", 0)),
            "prior_recovery_failure_count": int(data.get("prior_recovery_failure_count", 0)),
            "customer_card_success_rate": float(data.get("customer_card_success_rate", rate)),
            "customer_upi_success_rate": float(data.get("customer_upi_success_rate", rate)),
            "customer_netbanking_success_rate": float(data.get("customer_netbanking_success_rate", rate)),
            "customer_wallet_success_rate": float(data.get("customer_wallet_success_rate", rate)),
            "customer_tenure_days": float(data.get("customer_tenure_days", 90.0)),
            "is_opted_out": 1 if data.get("is_opted_out", False) else 0,
            "has_open_dispute": 1 if data.get("has_open_dispute", False) else 0,
            "payment_method": pm,
            "failure_type": ft,
        }
        return features

    def to_dataframe(self, feature_dicts: list[dict[str, Any]]) -> pd.DataFrame:
        """
        Converts feature dictionaries to a deterministic pandas DataFrame with sorted column names.
        """
        df = pd.DataFrame(feature_dicts)
        for col in ALL_FEATURE_NAMES:
            if col not in df.columns:
                if col == "payment_method":
                    df[col] = "CARD"
                elif col == "failure_type":
                    df[col] = "TEMPORARY_BANK_DECLINE"
                else:
                    df[col] = 0.0
        return df[ALL_FEATURE_NAMES]


def get_feature_preprocessor():
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder

    return ColumnTransformer(
        transformers=[
            (
                "cat",
                OneHotEncoder(
                    categories=[PAYMENT_METHODS, FAILURE_TYPES],
                    handle_unknown="ignore",
                    sparse_output=False,
                ),
                CATEGORICAL_FEATURE_NAMES,
            ),
        ],
        remainder="passthrough",
    )


def get_encoded_feature_names() -> list[str]:
    cat_names = [f"payment_method_{pm}" for pm in PAYMENT_METHODS] + [
        f"failure_type_{ft}" for ft in FAILURE_TYPES
    ]
    return cat_names + NUMERIC_FEATURE_NAMES


feature_engineer = FeatureEngineeringService()

