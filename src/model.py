"""Compare interpretable models on later arrivals without leaking final status."""

import argparse
import logging
from datetime import date
from importlib.metadata import version
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
import psycopg
from numpy.typing import NDArray
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, f1_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

from src.artifacts import new_output_bundle
from src.config import PROJECT_ROOT
from src.csv_source import source_sha256
from src.database import connect_database, snapshot_transaction, write_json

LOGGER = logging.getLogger(__name__)
NUMERIC_FEATURES = (
    "lead_time", "is_repeated_guest", "total_of_special_requests",
    "adults", "children", "babies",
)
CATEGORICAL_FEATURES = (
    "hotel", "market_segment", "distribution_channel", "deposit_type", "customer_type",
)
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
LEAKAGE_COLUMNS = ("reservation_status", "reservation_status_date")
THRESHOLDS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
PREDICTION_COLUMNS = (
    "source_record_number", "arrival_date", "actual", "risk", "model",
)
LIMITATIONS = [
    "Two hotels in one country; data from 2015-2017.",
    "The model is not validated on other markets.",
    "Arrival-date split is a later-arrival holdout, not a booking-time backtest.",
    "Final-extract feature timing and historical label availability are unverified.",
    "Predictive associations do not demonstrate an intervention's causal effect.",
]


def split_chronologically(
    frame: pd.DataFrame, validation_start: date, test_start: date
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if validation_start >= test_start:
        raise ValueError("validation-start must be earlier than test-start.")
    if not frame["source_record_number"].is_unique:
        raise ValueError("Source record numbers must be unique.")
    if frame["arrival_date"].isna().any():
        raise ValueError("Missing arrival dates cannot enter the chronological split.")
    if not frame["is_canceled"].isin([0, 1]).all():
        raise ValueError("Cancellation labels must be nonmissing and binary.")
    dates = pd.to_datetime(frame["arrival_date"], errors="raise")
    partitions = (
        frame.loc[dates < pd.Timestamp(validation_start)].copy(),
        frame.loc[
            (dates >= pd.Timestamp(validation_start)) & (dates < pd.Timestamp(test_start))
        ].copy(),
        frame.loc[dates >= pd.Timestamp(test_start)].copy(),
    )
    for name, partition in zip(("training", "validation", "test"), partitions):
        if partition.empty or partition["is_canceled"].nunique() != 2:
            raise ValueError(
                f"The {name} period must be nonempty and contain both outcomes. "
                "Choose dates from coverage/class counts before evaluating models."
            )
    return partitions


def feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    # Final reservation status and its date reveal future/outcome information.
    # Remove them explicitly, then select only audited candidate features.
    without_leakage = frame.drop(columns=list(LEAKAGE_COLUMNS))
    result = without_leakage.loc[:, list(FEATURES)].copy()
    for column in CATEGORICAL_FEATURES:
        result[column] = result[column].map(
            lambda value: np.nan if value is None else value
        )
    return result


def build_pipeline(tree: bool = False) -> Pipeline:
    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("scale", StandardScaler()),
    ])
    categories = Pipeline([
        ("impute", SimpleImputer(
            strategy="constant", fill_value="Unknown", keep_empty_features=True,
        )),
        ("encode", OneHotEncoder(handle_unknown="ignore")),
    ])
    preprocess = ColumnTransformer([
        ("numeric", numeric, list(NUMERIC_FEATURES)),
        ("categorical", categories, list(CATEGORICAL_FEATURES)),
    ])
    classifier = (
        DecisionTreeClassifier(max_depth=4, min_samples_leaf=10, random_state=42)
        if tree else LogisticRegression(max_iter=2000)
    )
    return Pipeline([("preprocess", preprocess), ("classifier", classifier)])


def validated_arrays(
    labels: Sequence[int] | NDArray, risks: Sequence[float] | NDArray
) -> tuple[NDArray, NDArray[np.float64]]:
    target = np.asarray(labels)
    probabilities = np.asarray(risks, dtype=float)
    if target.ndim != 1 or probabilities.ndim != 1 or target.size != probabilities.size:
        raise ValueError("Labels and probabilities must be equal-length vectors.")
    if target.size == 0 or not np.isin(target, [0, 1]).all():
        raise ValueError("Labels must be a nonempty binary vector.")
    if not np.isfinite(probabilities).all() or (
        (probabilities < 0) | (probabilities > 1)
    ).any():
        raise ValueError("Risks must be finite probabilities between 0 and 1.")
    return target, probabilities


def choose_threshold(labels: NDArray, risks: NDArray) -> float:
    target, probabilities = validated_arrays(labels, risks)
    return max(THRESHOLDS, key=lambda threshold: (
        f1_score(target, probabilities >= threshold, zero_division=0),
        -abs(threshold - 0.5),
        threshold,
    ))


def evaluate_test(
    labels: Sequence[int] | NDArray,
    risks: Sequence[float] | NDArray,
    threshold: float,
) -> dict[str, object]:
    target, probabilities = validated_arrays(labels, risks)
    if np.unique(target).size != 2:
        raise ValueError("Test ROC-AUC requires both outcome classes.")
    if not 0 <= threshold <= 1:
        raise ValueError("Threshold must be between 0 and 1.")
    flagged = probabilities >= threshold
    tp = int(((target == 1) & flagged).sum())
    fp = int(((target == 0) & flagged).sum())
    fn = int(((target == 1) & ~flagged).sum())
    tn = int(((target == 0) & ~flagged).sum())
    notes = []
    if tp + fp == 0:
        notes.append("Precision is undefined: no bookings were flagged.")
        LOGGER.warning(notes[-1])
    return {
        "population": "final_test_later_arrivals",
        "bookings": int(target.size),
        "threshold": threshold,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn),
        "roc_auc": float(roc_auc_score(target, probabilities)),
        "brier_score": float(brier_score_loss(target, probabilities)),
        "true_positives": tp, "false_positives": fp,
        "false_negatives": fn, "true_negatives": tn,
        "notes": notes,
    }


def calibration_rows(
    labels: Sequence[int] | NDArray, risks: Sequence[float] | NDArray, model: str
) -> list[dict[str, object]]:
    target, probabilities = validated_arrays(labels, risks)
    bins = np.minimum((probabilities * 10).astype(int), 9)
    rows = []
    for index in range(10):
        mask = bins == index
        count = int(mask.sum())
        rows.append({
            "model": model,
            "lower_bound": index / 10,
            "upper_bound": (index + 1) / 10,
            "upper_inclusive": index == 9,
            "bookings": count,
            "mean_predicted_risk": float(probabilities[mask].mean()) if count else None,
            "observed_cancellation_rate": float(target[mask].mean()) if count else None,
            "population": "final_test_later_arrivals",
        })
    return rows


def train_models(
    connection: psycopg.Connection,
    output: Path,
    validation_start: date,
    test_start: date,
    *,
    acknowledge_snapshot_limitations: bool = False,
) -> None:
    if not acknowledge_snapshot_limitations:
        raise ValueError(
            "Read the feature/label timing limitations in README.md, then explicitly "
            "pass --acknowledge-snapshot-limitations for an exploratory arrival holdout."
        )
    with new_output_bundle(output) as staging:
        with snapshot_transaction(connection) as snapshot:
            with connection.cursor() as cursor:
                cursor.execute(
                    (PROJECT_ROOT / "sql" / "phase4" / "01_model_input.sql")
                    .read_text(encoding="utf-8")
                )
                frame = pd.DataFrame.from_records(
                    cursor.fetchall(), columns=[column.name for column in cursor.description]
                )
        train, validation, test = split_chronologically(
            frame, validation_start, test_start
        )
        x_train, x_validation, x_test = (
            feature_frame(partition) for partition in (train, validation, test)
        )
        entirely_missing = [
            column for column in NUMERIC_FEATURES if x_train[column].isna().all()
        ]
        if entirely_missing:
            raise ValueError(
                "Numeric training inputs are entirely missing: "
                + ", ".join(entirely_missing)
                + ". Review the feature set; a training median cannot be learned."
            )
        y_train, y_validation, y_test = (
            partition["is_canceled"].to_numpy()
            for partition in (train, validation, test)
        )
        # Model designs and primary model are fixed before accessing test scores.
        candidates = {
            "logistic_regression": build_pipeline(),
            "decision_tree": build_pipeline(tree=True),
        }
        frozen_thresholds = {}
        for name, pipeline in candidates.items():
            pipeline.fit(x_train, y_train)
            frozen_thresholds[name] = choose_threshold(
                y_validation, pipeline.predict_proba(x_validation)[:, 1]
            )

        metrics = {}
        calibration = []
        test_risks = {}
        for name, pipeline in candidates.items():
            risks = pipeline.predict_proba(x_test)[:, 1]
            test_risks[name] = risks
            metrics[name] = evaluate_test(y_test, risks, frozen_thresholds[name])
            calibration.extend(calibration_rows(y_test, risks, name))
            names = pipeline["preprocess"].get_feature_names_out()
            weights = (
                pipeline["classifier"].coef_[0] if name == "logistic_regression"
                else pipeline["classifier"].feature_importances_
            )
            pd.DataFrame({
                "feature": names,
                "coefficient" if name == "logistic_regression" else "importance": weights,
            }).to_csv(staging / f"{name}_features.csv", index=False)
        baseline = np.full(y_test.size, y_train.mean(), dtype=float)
        metrics["training_rate_baseline"] = evaluate_test(y_test, baseline, 0.5)
        calibration.extend(calibration_rows(y_test, baseline, "training_rate_baseline"))

        # Logistic regression is the prespecified primary, not a test-selected winner.
        predictions = pd.DataFrame({
            "source_record_number": test["source_record_number"].to_numpy(),
            "arrival_date": test["arrival_date"].to_numpy(),
            "actual": y_test,
            "risk": test_risks["logistic_regression"],
            "model": "logistic_regression",
        })
        prediction_path = staging / "test_predictions.csv"
        predictions.to_csv(prediction_path, index=False, columns=list(PREDICTION_COLUMNS))
        pd.DataFrame(calibration).to_csv(staging / "test_calibration.csv", index=False)
        write_json(staging / "test_metrics.json", metrics)
        write_json(staging / "manifest.json", {
            "artifact_type": "hotel_booking_model_v1",
            "source_snapshot": snapshot.as_dict(),
            "primary_model": "logistic_regression",
            "validation_start": validation_start.isoformat(),
            "test_start": test_start.isoformat(),
            "split_basis": "scheduled_arrival_date",
            "partition_counts": {
                "training": len(train), "validation": len(validation), "test": len(test),
            },
            "features": list(FEATURES),
            "excluded_leakage_columns": list(LEAKAGE_COLUMNS),
            "threshold_selection": "Earlier validation F1 on a fixed grid; not cost-optimal.",
            "prediction_sha256": source_sha256(prediction_path),
            "limitations": LIMITATIONS,
            "versions": {
                package: version(package)
                for package in ("numpy", "pandas", "scikit-learn", "psycopg")
            },
        })


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-start", type=date.fromisoformat, required=True)
    parser.add_argument("--test-start", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--acknowledge-snapshot-limitations", action="store_true",
        help="Acknowledge this is exploratory, not a verified booking-time backtest.",
    )
    parser.add_argument(
        "--output", type=Path, default=PROJECT_ROOT / "data" / "processed" / "phase4",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        with connect_database() as connection:
            train_models(
                connection, args.output, args.validation_start, args.test_start,
                acknowledge_snapshot_limitations=args.acknowledge_snapshot_limitations,
            )
    except (OSError, ValueError, RuntimeError, psycopg.Error) as exc:
        LOGGER.error("Phase 4 failed: %s", exc)
        return 1
    LOGGER.info("Phase 4 saved to %s. Review test outputs and limitations.", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
