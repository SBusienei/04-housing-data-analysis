"""Use fictional outcomes to verify leakage controls, split boundaries, and metrics."""

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.artifacts import new_output_bundle
from src.model import (
    FEATURES, LEAKAGE_COLUMNS, build_pipeline, calibration_rows,
    choose_threshold, evaluate_test, feature_frame, split_chronologically,
)


def temporal_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "source_record_number": list(range(6)),
        "arrival_date": [
            date(2016, 12, 1), date(2016, 12, 2),
            date(2017, 4, 1), date(2017, 6, 30),
            date(2017, 7, 1), date(2017, 8, 1),
        ],
        "is_canceled": [0, 1, 0, 1, 0, 1],
    })


def test_split_boundaries_and_disjointness() -> None:
    partitions = split_chronologically(
        temporal_frame(), date(2017, 4, 1), date(2017, 7, 1)
    )
    assert [list(part.source_record_number) for part in partitions] == [
        [0, 1], [2, 3], [4, 5],
    ]


def test_single_class_or_empty_period_rejected() -> None:
    frame = temporal_frame()
    frame.loc[frame.index < 2, "is_canceled"] = 0
    with pytest.raises(ValueError, match="training period"):
        split_chronologically(frame, date(2017, 4, 1), date(2017, 7, 1))
    with pytest.raises(ValueError, match="earlier"):
        split_chronologically(frame, date(2017, 7, 1), date(2017, 4, 1))


def test_missing_dates_duplicate_ids_and_invalid_labels_rejected() -> None:
    for column, value, message in (
        ("arrival_date", None, "Missing arrival"),
        ("source_record_number", 1, "unique"),
        ("is_canceled", 0.5, "binary"),
    ):
        frame = temporal_frame().astype({"is_canceled": float})
        frame.loc[0, column] = value
        with pytest.raises(ValueError, match=message):
            split_chronologically(frame, date(2017, 4, 1), date(2017, 7, 1))


def test_status_is_removed_and_training_imputation_is_not_refitted() -> None:
    frame = pd.DataFrame({
        feature: ["Direct", "TA/TO"] if feature in (
            "hotel", "market_segment", "distribution_channel", "deposit_type", "customer_type"
        ) else [10.0, 30.0]
        for feature in FEATURES
    })
    for column in LEAKAGE_COLUMNS:
        frame[column] = ["outcome-revealing", "outcome-revealing"]
    inputs = feature_frame(frame)
    assert list(inputs.columns) == list(FEATURES)
    assert not set(LEAKAGE_COLUMNS).intersection(inputs.columns)
    pipeline = build_pipeline()
    pipeline.fit(inputs, [0, 1])
    imputer = pipeline["preprocess"].named_transformers_["numeric"]["impute"]
    before = imputer.statistics_.copy()
    later = inputs.copy()
    later["lead_time"] = [np.nan, 99999]
    pipeline.predict_proba(later)
    np.testing.assert_array_equal(imputer.statistics_, before)
    assert before[0] == 20


def test_precision_recall_auc_and_calibration_have_known_fictional_values() -> None:
    result = evaluate_test([1, 1, 0, 0], [0.9, 0.6, 0.7, 0.2], 0.65)
    assert result["precision"] == pytest.approx(0.5)
    assert result["recall"] == pytest.approx(0.5)
    assert result["roc_auc"] == pytest.approx(0.75)
    rows = calibration_rows([1, 0], [0.0, 1.0], "fictional")
    assert len(rows) == 10
    assert sum(row["bookings"] for row in rows) == 2
    assert rows[0]["mean_predicted_risk"] == 0
    assert rows[-1]["mean_predicted_risk"] == 1
    assert rows[1]["observed_cancellation_rate"] is None


def test_no_alerts_has_explicit_undefined_precision(caplog: pytest.LogCaptureFixture) -> None:
    result = evaluate_test([0, 1], [0.1, 0.2], 0.5)
    assert result["precision"] is None
    assert result["recall"] == 0
    assert "undefined" in caplog.text


@pytest.mark.parametrize("risks", [[float("nan"), 0.2], [1.1, 0.2], [-0.1, 0.2]])
def test_invalid_probabilities_rejected(risks: list[float]) -> None:
    with pytest.raises(ValueError, match="finite probabilities"):
        evaluate_test([0, 1], risks, 0.5)


def test_threshold_selection_is_deterministic() -> None:
    assert choose_threshold(np.array([0, 1]), np.array([0.1, 0.9])) == 0.5


def test_bundle_never_replaces_or_publishes_partial_results(tmp_path: Path) -> None:
    destination = tmp_path / "run"
    with pytest.raises(ValueError, match="fictional failure"):
        with new_output_bundle(destination) as staging:
            (staging / "partial.txt").write_text("fictional", encoding="utf-8")
            raise ValueError("fictional failure")
    assert not destination.exists()
    with new_output_bundle(destination) as staging:
        (staging / "complete.txt").write_text("fictional", encoding="utf-8")
    with pytest.raises(FileExistsError):
        with new_output_bundle(destination):
            pytest.fail("An existing run must never be replaced.")

