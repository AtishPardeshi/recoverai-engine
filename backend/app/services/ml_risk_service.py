import os
import json
from typing import Any, Optional
import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from backend.app.models.transaction import Transaction
from backend.app.models.payment_failure import PaymentFailure
from backend.app.models.customer import Customer
from backend.app.models.recovery_case import RecoveryCase
from backend.app.ml.feature_engineering import feature_engineer, ALL_FEATURE_NAMES, FEATURE_VERSION
from backend.app.ml.root_cause import root_cause_engine
from backend.app.ml.priority_engine import priority_engine

MODEL_VERSION = "recovery-risk-v1"
ARTIFACT_PATHS = [
    "backend/artifacts/recovery_model.joblib",
    "backend/app/ml/recovery_model.joblib",
]
METADATA_PATHS = [
    "backend/artifacts/model_metadata.json",
    "backend/app/ml/model_metadata.json",
]


class MLRiskAssessment:
    def __init__(
        self,
        recovery_probability: float,
        risk_score: float,
        expected_recovery: float,
        priority_score: float,
        root_cause: str,
        root_cause_explanation: str,
        recoverability_class: str,
        confidence: float,
        model_version: str,
        feature_version: str,
        prediction_source: str,
        features: dict[str, Any],
    ):
        self.recovery_probability = recovery_probability
        self.risk_score = risk_score
        self.expected_recovery = expected_recovery
        self.priority_score = priority_score
        self.root_cause = root_cause
        self.root_cause_explanation = root_cause_explanation
        self.recoverability_class = recoverability_class
        self.confidence = confidence
        self.model_version = model_version
        self.feature_version = feature_version
        self.prediction_source = prediction_source
        self.features = features

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovery_probability": self.recovery_probability,
            "risk_score": self.risk_score,
            "expected_recovery": self.expected_recovery,
            "priority_score": self.priority_score,
            "root_cause": self.root_cause,
            "root_cause_explanation": self.root_cause_explanation,
            "recoverability_class": self.recoverability_class,
            "confidence": self.confidence,
            "model_version": self.model_version,
            "feature_version": self.feature_version,
            "prediction_source": self.prediction_source,
        }


class MLRiskService:
    """
    ML Risk & Root-Cause Intelligence Service.
    Loads trained HistGradientBoostingClassifier, constructs leakage-safe features at T,
    evaluates probability, expected recovery, priority scoring, and root-cause taxonomy.
    """

    def __init__(self):
        self.model = None
        self.metadata = {}
        self.model_version = MODEL_VERSION
        self.feature_version = FEATURE_VERSION
        self._load_artifact()

    def _load_artifact(self):
        for path in ARTIFACT_PATHS:
            if os.path.exists(path):
                try:
                    self.model = joblib.load(path)
                    break
                except Exception:
                    continue

        for path in METADATA_PATHS:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        self.metadata = json.load(f)
                    break
                except Exception:
                    continue

    def predict_risk_for_case(
        self,
        db: Session,
        case: RecoveryCase,
        as_of_time: Optional[Any] = None,
    ) -> MLRiskAssessment:
        """
        Extracts prediction-time features for a RecoveryCase and evaluates full ML risk intelligence.
        """
        tx = case.transaction
        fail = tx.payment_failure
        cust = tx.customer

        t_ref = as_of_time or tx.created_at

        # 1. Leakage-safe feature extraction as-of T
        feats = feature_engineer.extract_features_at_time(
            db=db,
            transaction=tx,
            payment_failure=fail,
            customer=cust,
            retry_count=case.retry_count,
            as_of_time=t_ref,
        )

        return self._predict_from_feature_dict(feats, tx.amount, cust.historical_success_rate, case.retry_count)

    def predict_risk_from_data(self, data: dict[str, Any]) -> MLRiskAssessment:
        """
        Extracts features from dictionary payload and evaluates ML risk intelligence.
        """
        feats = feature_engineer.extract_features_from_dict(data)
        amt = float(data.get("amount", 1000.0))
        cust_rate = float(data.get("customer_success_rate", 0.80))
        retries = int(data.get("retry_count", 0))

        return self._predict_from_feature_dict(feats, amt, cust_rate, retries)

    def _predict_from_feature_dict(
        self,
        feats: dict[str, Any],
        amount: float,
        customer_success_rate: float,
        retry_count: int,
    ) -> MLRiskAssessment:
        prediction_source = "trained_model"
        raw_prob = None

        if self.model is None:
            self._load_artifact()

        if self.model is not None:
            try:
                df_X = feature_engineer.to_dataframe([feats])
                proba = self.model.predict_proba(df_X)[0]
                raw_prob = float(proba[1])
            except Exception:
                raw_prob = None

        if raw_prob is None:
            prediction_source = "deterministic_fallback"
            raw_prob = self._compute_fallback_probability(feats, customer_success_rate, retry_count)

        prob = round(max(0.01, min(0.99, raw_prob)), 2)
        risk_score = round(1.0 - prob, 2)

        # Expected recovery formula
        exp_rec = priority_engine.calculate_expected_recovery(amount, prob)

        # Priority score (0-100)
        p_score = priority_engine.calculate_priority_score(
            amount=amount,
            recovery_probability=prob,
            customer_success_rate=customer_success_rate,
            retry_count=retry_count,
        )

        # Root cause analysis
        ft_name = str(feats.get("failure_type", "TEMPORARY_BANK_DECLINE"))
        rc_info = root_cause_engine.analyze_root_cause(
            failure_type=ft_name,
            error_description=None,
            customer_success_rate=customer_success_rate,
            retry_count=retry_count,
            recovery_probability=prob,
        )

        return MLRiskAssessment(
            recovery_probability=prob,
            risk_score=risk_score,
            expected_recovery=exp_rec,
            priority_score=p_score,
            root_cause=rc_info["root_cause"],
            root_cause_explanation=rc_info["explanation"],
            recoverability_class=rc_info["recoverability_class"],
            confidence=rc_info["confidence"],
            model_version=self.model_version,
            feature_version=self.feature_version,
            prediction_source=prediction_source,
            features=feats,
        )

    def _compute_fallback_probability(
        self,
        feats: dict[str, Any],
        customer_success_rate: float,
        retry_count: int,
    ) -> float:
        """
        Deterministic fallback matrix when trained model artifact is unavailable.
        """
        fallback_map = {
            "TEMPORARY_BANK_DECLINE": 0.88,
            "INSUFFICIENT_FUNDS": 0.62,
            "BANK_DECLINE": 0.48,
            "NETWORK_ERROR": 0.85,
            "EXPIRED_METHOD": 0.38,
            "INVALID_DETAILS": 0.05,
        }
        ft_name = str(feats.get("failure_type", "TEMPORARY_BANK_DECLINE"))
        base = fallback_map.get(ft_name, 0.50)
        adj = (customer_success_rate - 0.5) * 0.20 - (retry_count * 0.15)
        return float(max(0.01, min(0.99, base + adj)))


    def get_demo_diagnostics(self, db: Session, external_id: str = "TX-DEMO-001") -> dict[str, Any]:
        """
        Generates explicit feature audit and prediction diagnostics for demo transaction.
        """
        tx = db.query(Transaction).filter(Transaction.external_id == external_id).first()
        if not tx:
            raise ValueError(f"Transaction {external_id} not found in database.")

        case = db.query(RecoveryCase).filter(RecoveryCase.transaction_id == tx.id).first()
        if not case:
            raise ValueError(f"Recovery case for {external_id} not found.")

        assessment = self.predict_risk_for_case(db, case)

        return {
            "transaction_id": tx.external_id,
            "feature_version": assessment.feature_version,
            "features": assessment.features,
            "recovery_probability": assessment.recovery_probability,
            "expected_recovery": assessment.expected_recovery,
            "priority_score": assessment.priority_score,
            "root_cause": assessment.root_cause,
            "recoverability_class": assessment.recoverability_class,
            "model_version": assessment.model_version,
            "prediction_source": assessment.prediction_source,
        }

ml_risk_service = MLRiskService()
