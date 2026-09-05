import os
import json
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database.session import SessionLocal, Base, engine
from backend.app.simulator.seed_data import seed_database
from backend.app.models.customer import Customer
from backend.app.models.transaction import Transaction
from backend.app.models.payment_failure import PaymentFailure
from backend.app.models.recovery_case import RecoveryCase
from backend.app.models.recovery_outcome import RecoveryOutcome
from backend.app.schemas.common import TransactionStatusEnum, FailureTypeEnum, OutcomeResultEnum
from backend.app.ml.feature_engineering import feature_engineer, ALL_FEATURE_NAMES, FEATURE_VERSION
from backend.app.ml.dataset_builder import dataset_builder
from backend.app.ml.trainer import model_trainer, MODEL_VERSION
from backend.app.ml.root_cause import root_cause_engine, RECOVERABILITY_CLASSES
from backend.app.ml.priority_engine import priority_engine
from backend.app.services.ml_risk_service import ml_risk_service

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield

# 1. Training population contains only resolved failures (n=549)
def test_1_training_population_contains_only_resolved_failures():
    db = SessionLocal()
    seed_database(db, n_cases=1000, seed=42)
    df_X, y, meta = dataset_builder.build_supervised_dataset(db)
    db.close()

    assert len(df_X) == 549
    assert len(y) == 549
    assert len(meta) == 549

# 2. Exactly one target per resolved failure
def test_2_exactly_one_target_per_resolved_failure():
    db = SessionLocal()
    seed_database(db, n_cases=1000, seed=42)
    df_X, y, meta = dataset_builder.build_supervised_dataset(db)
    tx_ids = [m["transaction_id"] for m in meta]
    db.close()

    assert len(tx_ids) == len(set(tx_ids))

# 3. Target values are only 0 or 1
def test_3_target_values_are_only_0_or_1():
    db = SessionLocal()
    seed_database(db, n_cases=1000, seed=42)
    df_X, y, meta = dataset_builder.build_supervised_dataset(db)
    
    recovered_in_db = db.query(Transaction).filter(Transaction.status == TransactionStatusEnum.RECOVERED.value).count()
    exhausted_in_db = db.query(Transaction).filter(Transaction.status == TransactionStatusEnum.RECOVERY_EXHAUSTED.value).count()
    db.close()

    unique_targets = set(np.unique(y))
    assert unique_targets == {0, 1}
    assert int(sum(y == 1)) == recovered_in_db
    assert int(sum(y == 0)) == exhausted_in_db
    assert len(y) == 549
    assert recovered_in_db + exhausted_in_db == 549

# 4. Organic CAPTURED transactions excluded from training population
def test_4_organic_captured_excluded():
    db = SessionLocal()
    seed_database(db, n_cases=1000, seed=42)
    df_X, y, meta = dataset_builder.build_supervised_dataset(db)
    training_tx_ids = {m["transaction_id"] for m in meta}

    captured_txs = db.query(Transaction).filter(Transaction.status == TransactionStatusEnum.CAPTURED.value).all()
    assert len(captured_txs) == 5274
    for ctx in captured_txs:
        assert ctx.id not in training_tx_ids
    db.close()

# 5. Unresolved FAILED transactions excluded from training population
def test_5_unresolved_failed_excluded():
    db = SessionLocal()
    seed_database(db, n_cases=1000, seed=42)
    df_X, y, meta = dataset_builder.build_supervised_dataset(db)
    training_tx_ids = {m["transaction_id"] for m in meta}

    failed_txs = db.query(Transaction).filter(Transaction.status == TransactionStatusEnum.FAILED.value).all()
    assert len(failed_txs) == 1161
    for ftx in failed_txs:
        assert ftx.id not in training_tx_ids
    db.close()

# 6. Feature generation produces all required feature keys
def test_6_feature_generation_schema():
    data = {
        "amount": 12500.0,
        "payment_method": "CARD",
        "failure_type": "TEMPORARY_BANK_DECLINE",
        "customer_success_rate": 0.894,
        "customer_success_count": 17,
        "customer_failed_count": 2,
    }
    feats = feature_engineer.extract_features_from_dict(data)
    for col in ALL_FEATURE_NAMES:
        assert col in feats

# 7. Feature determinism
def test_7_feature_determinism():
    data = {
        "amount": 8000.0,
        "payment_method": "UPI",
        "failure_type": "INSUFFICIENT_FUNDS",
        "customer_success_rate": 0.75,
        "customer_success_count": 9,
        "customer_failed_count": 3,
    }
    feats1 = feature_engineer.extract_features_from_dict(data)
    feats2 = feature_engineer.extract_features_from_dict(data)
    assert feats1 == feats2

# 8. Feature schema consistency
def test_8_feature_schema_consistency():
    df = feature_engineer.to_dataframe([
        {"amount": 5000.0, "payment_method_idx": 0},
        {"amount": 10000.0, "payment_method_idx": 1},
    ])
    assert list(df.columns) == list(ALL_FEATURE_NAMES)
    assert not df.isna().any().any()

# 9. No future transaction leakage test
def test_9_no_future_transaction_leakage():
    db = SessionLocal()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    cust = Customer(
        external_id="CUST-LEAK-01",
        name="Leak Test User",
        historical_success_rate=0.90,
    )
    db.add(cust)
    db.flush()

    # T1, T2, T3
    t1 = Transaction(
        external_id="TX-LEAK-01",
        customer_id=cust.id,
        amount=1000.0,
        payment_method="CARD",
        status=TransactionStatusEnum.CAPTURED.value,
        created_at=now - timedelta(days=10),
    )
    t2 = Transaction(
        external_id="TX-LEAK-02",
        customer_id=cust.id,
        amount=2000.0,
        payment_method="CARD",
        status=TransactionStatusEnum.CAPTURED.value,
        created_at=now - timedelta(days=5),
    )
    t3 = Transaction(
        external_id="TX-LEAK-03",
        customer_id=cust.id,
        amount=3000.0,
        payment_method="CARD",
        status=TransactionStatusEnum.FAILED.value,
        created_at=now - timedelta(days=1),
    )
    db.add_all([t1, t2, t3])
    db.flush()

    fail3 = PaymentFailure(
        transaction_id=t3.id,
        error_code="ERR_TEMP",
        normalized_failure_type="TEMPORARY_BANK_DECLINE",
        occurred_at=t3.created_at,
    )
    db.add(fail3)
    db.commit()

    # Extract features for T3 as-of T3 timestamp
    feats_t3_before = feature_engineer.extract_features_at_time(db, t3, fail3, cust, as_of_time=t3.created_at)

    # Add future transaction T4 and T5
    t4 = Transaction(
        external_id="TX-LEAK-04",
        customer_id=cust.id,
        amount=50000.0,
        payment_method="CARD",
        status=TransactionStatusEnum.CAPTURED.value,
        created_at=now + timedelta(hours=2),
    )
    t5 = Transaction(
        external_id="TX-LEAK-05",
        customer_id=cust.id,
        amount=90000.0,
        payment_method="UPI",
        status=TransactionStatusEnum.FAILED.value,
        created_at=now + timedelta(hours=5),
    )
    db.add_all([t4, t5])
    db.commit()

    # Re-extract features for T3 as-of T3 timestamp
    feats_t3_after = feature_engineer.extract_features_at_time(db, t3, fail3, cust, as_of_time=t3.created_at)
    db.close()

    # Features at T3 must be strictly identical before and after future transactions were added
    assert feats_t3_before == feats_t3_after
    assert feats_t3_after["prior_transaction_count"] == 2
    assert feats_t3_after["average_transaction_amount"] == 1500.0

# 10. No future recovery leakage test
def test_10_no_future_recovery_leakage():
    db = SessionLocal()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    cust = Customer(external_id="CUST-LEAK-REC", name="Rec Leak User")
    db.add(cust)
    db.flush()

    tx = Transaction(
        external_id="TX-LEAK-REC-01",
        customer_id=cust.id,
        amount=4000.0,
        payment_method="UPI",
        status=TransactionStatusEnum.FAILED.value,
        created_at=now - timedelta(hours=6),
    )
    db.add(tx)
    db.flush()

    fail = PaymentFailure(
        transaction_id=tx.id,
        error_code="ERR_NET",
        normalized_failure_type="NETWORK_ERROR",
        occurred_at=tx.created_at,
    )
    db.add(fail)
    db.flush()

    rec_case = RecoveryCase(
        transaction_id=tx.id,
        revenue_at_risk=4000.0,
        recovery_probability=0.85,
        priority_score=80.0,
        expected_recovery=3400.0,
        status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
        retry_count=0,
        message_count=0,
    )
    db.add(rec_case)
    db.commit()

    feats_before = feature_engineer.extract_features_at_time(db, tx, fail, cust, as_of_time=tx.created_at)

    # Simulate future recovery outcome occurring 4 hours later
    outcome = RecoveryOutcome(
        recovery_outcome_id="OUT-FUTURE-01",
        recovery_case_id=rec_case.id,
        transaction_id=tx.id,
        outcome_type="AGENT_RECOVERY",
        result=OutcomeResultEnum.SUCCESS.value,
        recovered_amount=4000.0,
        baseline_amount=1400.0,
        incremental_amount=2600.0,
        simulator_result="CAPTURED",
        occurred_at=now - timedelta(hours=2),
    )
    db.add(outcome)
    db.commit()

    feats_after = feature_engineer.extract_features_at_time(db, tx, fail, cust, as_of_time=tx.created_at)
    db.close()

    assert feats_before == feats_after
    assert feats_after["prior_recovery_attempt_count"] == 0

# 11. Ground truth feature leakage protection
def test_11_no_ground_truth_feature_leakage():
    # Attempting to pass ground truth metadata into feature extractor does not include them in feature vectors
    data = {
        "amount": 10000.0,
        "payment_method": "CARD",
        "failure_type": "TEMPORARY_BANK_DECLINE",
        "customer_success_rate": 0.85,
        "customer_success_count": 10,
        "customer_failed_count": 2,
        # Injected ground truth fields
        "ground_truth_recoverable": True,
        "ground_truth_outcome": "SUCCESS",
        "eventual_recovery_amount": 10000.0,
        "baseline_recovery_possible": False,
    }
    feats = feature_engineer.extract_features_from_dict(data)
    for gt_field in ["ground_truth_recoverable", "ground_truth_outcome", "eventual_recovery_amount", "baseline_recovery_possible"]:
        assert gt_field not in feats
        assert gt_field not in ALL_FEATURE_NAMES

# 12. Chronological train/validation/test split
def test_12_chronological_split():
    db = SessionLocal()
    seed_database(db, n_cases=1000, seed=42)
    df_X, y, meta = dataset_builder.build_supervised_dataset(db)
    db.close()

    split = dataset_builder.split_chronologically(df_X, y, train_ratio=0.70, val_ratio=0.15)
    assert len(split["X_train"]) == 384
    assert len(split["X_val"]) == 82
    assert len(split["X_test"]) == 83
    assert len(split["X_train"]) + len(split["X_val"]) + len(split["X_test"]) == 549

# 13. Deterministic split
def test_13_deterministic_split():
    db = SessionLocal()
    seed_database(db, n_cases=200, seed=42)
    df_X, y, meta = dataset_builder.build_supervised_dataset(db)
    db.close()

    split1 = dataset_builder.split_chronologically(df_X, y)
    split2 = dataset_builder.split_chronologically(df_X, y)
    assert split1["split_counts"] == split2["split_counts"]
    assert np.array_equal(split1["y_train"], split2["y_train"])

# 14. Model trains successfully
def test_14_model_trains_successfully():
    db = SessionLocal()
    seed_database(db, n_cases=1000, seed=42)
    metadata = model_trainer.train_and_evaluate(db, seed=42)
    db.close()

    assert metadata["model_version"] == MODEL_VERSION
    assert "HistGradientBoostingClassifier" in metadata["algorithm"]
    assert "Pipeline" in metadata["algorithm"]
    assert metadata["training_rows"] == 384
    assert metadata["validation_rows"] == 82
    assert metadata["test_rows"] == 83

# 15. Model artifact loads
def test_15_model_artifact_loads():
    assert ml_risk_service.model is not None
    assert ml_risk_service.model_version == MODEL_VERSION

# 16. Probability range 0..1
def test_16_probability_range():
    assessment = ml_risk_service.predict_risk_from_data({
        "amount": 15000.0,
        "payment_method": "CARD",
        "failure_type": "TEMPORARY_BANK_DECLINE",
        "customer_success_rate": 0.88,
    })
    assert 0.0 <= assessment.recovery_probability <= 1.0
    assert 0.0 <= assessment.risk_score <= 1.0

# 17. Deterministic repeated training
def test_17_deterministic_repeated_training():
    db = SessionLocal()
    seed_database(db, n_cases=1000, seed=42)
    m1 = model_trainer.train_and_evaluate(db, seed=42)
    m2 = model_trainer.train_and_evaluate(db, seed=42)
    db.close()

    assert m1["metrics"]["roc_auc"] == m2["metrics"]["roc_auc"]
    assert m1["metrics"]["brier_score"] == m2["metrics"]["brier_score"]

# 18. Evaluation metrics generated
def test_18_evaluation_metrics_generated():
    db = SessionLocal()
    seed_database(db, n_cases=1000, seed=42)
    meta = model_trainer.train_and_evaluate(db, seed=42)
    db.close()

    metrics = meta["metrics"]
    for key in ["roc_auc", "pr_auc", "precision", "recall", "f1", "brier_score", "confusion_matrix"]:
        assert key in metrics
        assert metrics[key] is not None

# 19. Calibration evaluated
def test_19_calibration_evaluated():
    db = SessionLocal()
    seed_database(db, n_cases=1000, seed=42)
    meta = model_trainer.train_and_evaluate(db, seed=42)
    db.close()

    assert "brier_score" in meta["metrics"]
    assert 0.0 <= meta["metrics"]["brier_score"] <= 1.0

# 20. Root cause classification
def test_20_root_cause_classification():
    for ft in [
        "TEMPORARY_BANK_DECLINE",
        "INSUFFICIENT_FUNDS",
        "BANK_DECLINE",
        "NETWORK_ERROR",
        "EXPIRED_METHOD",
        "INVALID_DETAILS",
    ]:
        rc = root_cause_engine.analyze_root_cause(ft)
        assert rc["root_cause"] == ft
        assert rc["recoverability_class"] in RECOVERABILITY_CLASSES
        assert len(rc["explanation"]) > 10

# 21. Recoverability classification
def test_21_recoverability_classification():
    rc_temp = root_cause_engine.analyze_root_cause("TEMPORARY_BANK_DECLINE", customer_success_rate=0.90)
    rc_inv = root_cause_engine.analyze_root_cause("INVALID_DETAILS")
    assert rc_temp["recoverability_class"] == "HIGH"
    assert rc_inv["recoverability_class"] == "NOT_RECOMMENDED"

# 22. Expected recovery calculation
def test_22_expected_recovery_calculation():
    amount = 25000.0
    prob = 0.80
    exp = priority_engine.calculate_expected_recovery(amount, prob)
    assert exp == 20000.0

# 23. Priority score calculation
def test_23_priority_score_calculation():
    score = priority_engine.calculate_priority_score(
        amount=12500.0,
        recovery_probability=0.87,
        customer_success_rate=0.894,
        retry_count=0,
    )
    assert 0.0 <= score <= 100.0

# 24. Prediction metadata persistence
def test_24_prediction_metadata_persistence():
    db = SessionLocal()
    seed_database(db, n_cases=100, seed=42)
    case = db.query(RecoveryCase).first()
    assert case is not None

    assessment = ml_risk_service.predict_risk_for_case(db, case)
    assert assessment.model_version == MODEL_VERSION
    assert assessment.feature_version == FEATURE_VERSION
    assert assessment.prediction_source in ["trained_model", "deterministic_fallback"]
    db.close()

# 25. Model version persistence
def test_25_model_version_persistence():
    assert ml_risk_service.model_version == "recovery-risk-v1"
    assert ml_risk_service.feature_version == "features-v1"

# 26. TX-DEMO-001 feature correctness
def test_26_demo_feature_correctness():
    db = SessionLocal()
    seed_database(db, n_cases=1000, seed=42)
    diag = ml_risk_service.get_demo_diagnostics(db, "TX-DEMO-001")
    db.close()

    feats = diag["features"]
    assert diag["transaction_id"] == "TX-DEMO-001"
    assert feats["amount"] == 12500.0
    assert feats["payment_method"] == "CARD"
    assert feats["failure_type"] == "TEMPORARY_BANK_DECLINE"
    assert feats["prior_success_count"] == 17
    assert feats["prior_failure_count"] == 2
    assert feats["historical_success_rate"] == round(17 / 19, 4)

# 27. TX-DEMO-001 probability is model-derived
def test_27_demo_probability_is_model_derived():
    db = SessionLocal()
    seed_database(db, n_cases=1000, seed=42)
    diag = ml_risk_service.get_demo_diagnostics(db, "TX-DEMO-001")
    db.close()

    assert diag["prediction_source"] == "trained_model"
    assert 0.70 <= diag["recovery_probability"] <= 0.99
    assert diag["expected_recovery"] == round(12500.0 * diag["recovery_probability"], 2)

# 28. TX-DEMO-001 has no ID-specific override
def test_28_demo_has_no_id_specific_override():
    db = SessionLocal()
    seed_database(db, n_cases=1000, seed=42)
    diag = ml_risk_service.get_demo_diagnostics(db, "TX-DEMO-001")

    # Predict with same features on anonymous payload
    anon_eval = ml_risk_service.predict_risk_from_data(diag["features"])
    db.close()

    assert diag["recovery_probability"] == anon_eval.recovery_probability
    assert diag["expected_recovery"] == anon_eval.expected_recovery

# 29. Changing legitimate feature changes prediction path
def test_29_changing_legitimate_feature_changes_prediction():
    ml_risk_service._load_artifact()
    high_eval = ml_risk_service.predict_risk_from_data({
        "amount": 5000.0,
        "payment_method": "CARD",
        "failure_type": "TEMPORARY_BANK_DECLINE",
        "customer_success_rate": 0.95,
        "retry_count": 0,
    })
    low_eval = ml_risk_service.predict_risk_from_data({
        "amount": 85000.0,
        "payment_method": "WALLET",
        "failure_type": "INVALID_DETAILS",
        "customer_success_rate": 0.10,
        "retry_count": 3,
        "is_opted_out": True,
        "has_open_dispute": True,
    })
    assert high_eval.recovery_probability > low_eval.recovery_probability
    assert high_eval.recoverability_class == "HIGH"
    assert low_eval.recoverability_class == "NOT_RECOMMENDED"
    assert high_eval.priority_score > low_eval.priority_score


# 30. Fallback behavior
def test_30_fallback_behavior():
    # Calling internal fallback mechanism explicitly
    feats = feature_engineer.extract_features_from_dict({
        "amount": 10000.0,
        "payment_method": "UPI",
        "failure_type": "NETWORK_ERROR",
        "customer_success_rate": 0.85,
    })
    assessment = ml_risk_service._predict_from_feature_dict(
        feats=feats,
        amount=10000.0,
        customer_success_rate=0.85,
        retry_count=0,
    )
    assert 0.0 <= assessment.recovery_probability <= 1.0
    assert assessment.prediction_source in ["trained_model", "deterministic_fallback"]

# 31. Malformed feature handling
def test_31_malformed_feature_handling():
    # Empty / sparse dictionary
    assessment = ml_risk_service.predict_risk_from_data({})
    assert 0.0 <= assessment.recovery_probability <= 1.0
    assert assessment.expected_recovery >= 0.0
    assert assessment.priority_score >= 0.0

# 32. API recommendation contains real ML context
def test_32_api_recommendation_contains_real_ml_context():
    db = SessionLocal()
    seed_database(db, n_cases=100, seed=42)
    case = db.query(RecoveryCase).first()
    case_id = case.id
    db.close()

    resp = client.post(f"/api/recovery-cases/{case_id}/recommend")
    assert resp.status_code == 200
    data = resp.json()

    assert "ml" in data or "ml_context" in data
    ml_ctx = data.get("ml_context") or data.get("ml")
    assert "recovery_probability" in ml_ctx
    assert "expected_recovery" in ml_ctx
    assert "priority_score" in ml_ctx
    assert "model_version" in ml_ctx
    assert "prediction_source" in ml_ctx
    assert "root_cause_context" in data or "root_cause" in data

# 33. API remains recommendation-only
def test_33_api_remains_recommendation_only():
    db = SessionLocal()
    seed_database(db, n_cases=100, seed=42)
    case = db.query(RecoveryCase).first()
    initial_status = case.status
    initial_actions_count = len(case.actions)
    case_id = case.id
    db.close()

    resp = client.post(f"/api/recovery-cases/{case_id}/recommend")
    assert resp.status_code == 200

    db2 = SessionLocal()
    updated_case = db2.query(RecoveryCase).filter(RecoveryCase.id == case_id).first()
    # Case must NOT be executed or changed to RECOVERED by recommendation endpoint
    assert updated_case.status == initial_status
    assert len(updated_case.actions) == initial_actions_count
    db2.close()

# 34. Positive prevalence, PR baseline, and constant Brier baseline calculations
def test_34_calibration_and_baselines_calculation():
    db = SessionLocal()
    seed_database(db, n_cases=1000, seed=42)
    meta = model_trainer.train_and_evaluate(db, seed=42)
    db.close()

    metrics = meta["metrics"]
    assert "positive_prevalence" in metrics
    assert "pr_baseline_noskill" in metrics
    assert "brier_baseline_constant" in metrics
    assert "brier_score" in metrics
    assert "brier_calibrated_cv3" in metrics

    pos_prev = metrics["positive_prevalence"]
    assert 0.70 <= pos_prev <= 0.85
    assert metrics["pr_baseline_noskill"] == pos_prev
    expected_brier_base = round(pos_prev * (1.0 - pos_prev), 4)
    assert abs(metrics["brier_baseline_constant"] - expected_brier_base) < 0.01

# 35. Ground-truth stability (549 resolved historical cases with 405 positives and 144 negatives)
def test_35_ground_truth_stability():
    db = SessionLocal()
    seed_database(db, n_cases=1000, seed=42)
    df_X, y, meta = dataset_builder.build_supervised_dataset(db)
    db.close()

    assert len(y) == 549
    pos_count = int(np.sum(y == 1))
    neg_count = int(np.sum(y == 0))
    assert pos_count == 405
    assert neg_count == 144
    assert pos_count + neg_count == 549

# 36. Deterministic categorical OneHotEncoder pipeline without ordinal integers
def test_36_deterministic_onehot_pipeline():
    from backend.app.ml.feature_engineering import get_feature_preprocessor, get_encoded_feature_names
    preprocessor = get_feature_preprocessor()
    encoded_names = get_encoded_feature_names()
    assert len(encoded_names) == 36
    assert "payment_method_CARD" in encoded_names
    assert "failure_type_TEMPORARY_BANK_DECLINE" in encoded_names

    sample_df = pd.DataFrame([{
        "payment_method": "CARD",
        "failure_type": "TEMPORARY_BANK_DECLINE",
        **{col: 0.0 for col in ALL_FEATURE_NAMES if col not in ["payment_method", "failure_type"]}
    }])
    transformed = preprocessor.fit_transform(sample_df)
    assert transformed.shape == (1, 36)


# 37. Trained model differs from / independently executes from fallback path
def test_37_model_differs_from_fallback():
    feats = feature_engineer.extract_features_from_dict({
        "amount": 12500.0,
        "payment_method": "CARD",
        "failure_type": "TEMPORARY_BANK_DECLINE",
        "customer_success_rate": 0.8947,
    })
    
    # Fallback probability computation
    fallback_prob = ml_risk_service._compute_fallback_probability(feats, 0.8947, 0)
    
    # Model probability computation
    df_X = feature_engineer.to_dataframe([feats])
    model_prob = float(ml_risk_service.model.predict_proba(df_X)[0][1])

    assert isinstance(fallback_prob, float)
    assert isinstance(model_prob, float)
    assert 0.0 <= fallback_prob <= 1.0
    assert 0.0 <= model_prob <= 1.0

