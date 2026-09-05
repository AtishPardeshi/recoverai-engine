import os
import json
from datetime import datetime, timezone
from typing import Any
import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    precision_score,
    recall_score,
    f1_score,
    brier_score_loss,
    confusion_matrix,
)
from sqlalchemy.orm import Session
from backend.app.ml.feature_engineering import (
    RAW_FEATURE_NAMES,
    FEATURE_VERSION,
    get_feature_preprocessor,
    get_encoded_feature_names,
)
from backend.app.ml.dataset_builder import dataset_builder

MODEL_VERSION = "recovery-risk-v1"
DATASET_VERSION = "v1.0.1"
DEFAULT_ARTIFACT_DIR = "backend/artifacts"
DEFAULT_MODEL_PATH = os.path.join(DEFAULT_ARTIFACT_DIR, "recovery_model.joblib")
DEFAULT_METADATA_PATH = os.path.join(DEFAULT_ARTIFACT_DIR, "model_metadata.json")

class ModelTrainer:
    """
    Supervised model training, evaluation, and artifact management for RecoverAI.
    Trains Pipeline(ColumnTransformer(OneHotEncoder) + HistGradientBoostingClassifier)
    on resolved historical failures with chronological split.
    """

    def __init__(
        self,
        artifact_dir: str = DEFAULT_ARTIFACT_DIR,
        model_path: str = DEFAULT_MODEL_PATH,
        metadata_path: str = DEFAULT_METADATA_PATH,
    ):
        self.artifact_dir = artifact_dir
        self.model_path = model_path
        self.metadata_path = metadata_path

    def train_and_evaluate(self, db: Session, seed: int = 42) -> dict[str, Any]:
        """
        Builds supervised dataset, performs chronological split, trains pipeline,
        evaluates metrics against rigorous baselines, computes feature importance,
        and persists artifact and metadata.
        """
        os.makedirs(self.artifact_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)

        # 1. Build dataset from DB (n=549)
        df_X, y, meta = dataset_builder.build_supervised_dataset(db)
        split = dataset_builder.split_chronologically(df_X, y, train_ratio=0.70, val_ratio=0.15)

        X_train, y_train = split["X_train"], split["y_train"]
        X_val, y_val = split["X_val"], split["y_val"]
        X_test, y_test = split["X_test"], split["y_test"]

        # 2. Build Pipeline with ColumnTransformer (OneHotEncoder for nominal categories) + Classifier
        preprocessor = get_feature_preprocessor()
        base_clf = HistGradientBoostingClassifier(
            max_iter=100,
            learning_rate=0.05,
            min_samples_leaf=15,
            max_leaf_nodes=15,
            random_state=seed,
        )

        pipeline = Pipeline(
            steps=[
                ("preprocessor", preprocessor),
                ("classifier", base_clf),
            ]
        )
        pipeline.fit(X_train, y_train)

        # 3. Predict on Test Split
        y_pred_proba = pipeline.predict_proba(X_test)[:, 1]
        y_pred = (y_pred_proba >= 0.50).astype(int)

        # 4. Calibration Baselines & Evaluation
        pos_prevalence = round(float(np.mean(y_test)), 4)
        pr_baseline = pos_prevalence
        brier_baseline = round(float(np.mean((pos_prevalence - y_test) ** 2)), 4)
        brier_model = round(float(brier_score_loss(y_test, y_pred_proba)), 4)

        # Evaluate 3-fold cross-validated probability calibration on training set (NO test leakage)
        cal_clf = CalibratedClassifierCV(estimator=base_clf, method="sigmoid", cv=3)
        cal_pipeline = Pipeline(
            steps=[
                ("preprocessor", preprocessor),
                ("classifier", cal_clf),
            ]
        )
        cal_pipeline.fit(X_train, y_train)
        y_prob_cal = cal_pipeline.predict_proba(X_test)[:, 1]
        brier_cal = round(float(brier_score_loss(y_test, y_prob_cal)), 4)

        # Standard Performance Metrics
        roc_auc = round(float(roc_auc_score(y_test, y_pred_proba)), 4) if len(np.unique(y_test)) > 1 else 0.0
        pr_auc = round(float(average_precision_score(y_test, y_pred_proba)), 4) if len(np.unique(y_test)) > 1 else 0.0
        precision = round(float(precision_score(y_test, y_pred, zero_division=0)), 4)
        recall = round(float(recall_score(y_test, y_pred, zero_division=0)), 4)
        f1 = round(float(f1_score(y_test, y_pred, zero_division=0)), 4)
        cm = confusion_matrix(y_test, y_pred).tolist()

        # 5. Permutation Feature Importance on Validation Split
        perm = permutation_importance(pipeline, X_val, y_val, random_state=seed, n_repeats=5)
        top_indices = np.argsort(perm.importances_mean)[::-1]
        top_features = [
            {
                "feature": RAW_FEATURE_NAMES[idx],
                "importance_mean": round(float(perm.importances_mean[idx]), 4),
                "importance_std": round(float(perm.importances_std[idx]), 4),
            }
            for idx in top_indices[:8]
        ]

        # 6. Save Artifacts
        joblib.dump(pipeline, self.model_path)
        secondary_model_path = "backend/app/ml/recovery_model.joblib"
        os.makedirs(os.path.dirname(secondary_model_path), exist_ok=True)
        joblib.dump(pipeline, secondary_model_path)

        metadata = {
            "model_version": MODEL_VERSION,
            "dataset_version": DATASET_VERSION,
            "feature_version": FEATURE_VERSION,
            "algorithm": "Pipeline(ColumnTransformer(OneHotEncoder) + HistGradientBoostingClassifier)",
            "random_seed": seed,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "training_rows": len(X_train),
            "validation_rows": len(X_val),
            "test_rows": len(X_test),
            "positive_count": int(sum(y)),
            "negative_count": int(len(y) - sum(y)),
            "raw_feature_names": list(RAW_FEATURE_NAMES),
            "encoded_feature_names": get_encoded_feature_names(),
            "split_info": split["split_counts"],
            "metrics": {
                "positive_prevalence": pos_prevalence,
                "pr_baseline_noskill": pr_baseline,
                "brier_baseline_constant": brier_baseline,
                "brier_score": brier_model,
                "brier_calibrated_cv3": brier_cal,
                "roc_auc": roc_auc,
                "pr_auc": pr_auc,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "confusion_matrix": cm,
                "calibration_behavior": "Calibration is limited by the small synthetic holdout and class prevalence.",
            },
            "top_features": top_features,
            "hyperparameters": {
                "max_iter": 100,
                "learning_rate": 0.05,
                "min_samples_leaf": 15,
                "max_leaf_nodes": 15,
                "random_state": seed,
                "categorical_encoding": "OneHotEncoder(handle_unknown='ignore')",
            },
        }

        with open(self.metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        secondary_metadata_path = "backend/app/ml/model_metadata.json"
        with open(secondary_metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        return metadata

model_trainer = ModelTrainer()

