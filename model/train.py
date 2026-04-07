from __future__ import annotations

import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from config import settings
from model.features import build_processed_dataset, prepare_processed_frame


def time_split(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    split_index = max(1, int(len(dataframe) * (1 - settings.model.validation_fraction)))
    train_frame = dataframe.iloc[:split_index].copy()
    validation_frame = dataframe.iloc[split_index:].copy()
    if validation_frame.empty:
        validation_frame = train_frame.tail(1).copy()
    return train_frame, validation_frame


def train_model_from_processed_dataframe(
    dataframe: pd.DataFrame,
    artifact_path: Path | None = None,
    metrics_path: Path | None = None,
) -> dict:
    artifact_target = artifact_path or settings.model.artifact_path
    metrics_target = metrics_path or settings.model.metrics_path
    if len(dataframe) < settings.features.long_window:
        raise ValueError(
            "Not enough processed rows to train the model. Add more data or reduce the "
            "rolling window sizes in config.py."
        )

    feature_columns = list(settings.features.feature_columns)
    train_frame, validation_frame = time_split(dataframe)

    scaler = StandardScaler()
    x_train = scaler.fit_transform(train_frame[feature_columns])
    x_validation = scaler.transform(validation_frame[feature_columns])

    model = IsolationForest(
        n_estimators=settings.model.n_estimators,
        contamination=settings.model.contamination,
        random_state=settings.model.random_state,
    )
    model.fit(x_train)

    train_scores = -model.score_samples(x_train)
    validation_scores = -model.score_samples(x_validation)
    threshold = float(np.quantile(train_scores, 1 - settings.model.contamination))

    metrics = {
        "training_rows": int(len(train_frame)),
        "validation_rows": int(len(validation_frame)),
        "threshold": threshold,
        "train_score_mean": float(np.mean(train_scores)),
        "validation_score_mean": float(np.mean(validation_scores)),
        "feature_columns": feature_columns,
    }

    artifact = {
        "model": model,
        "scaler": scaler,
        "feature_columns": feature_columns,
        "threshold": threshold,
        "metrics": metrics,
    }

    artifact_target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, artifact_target)
    metrics_target.parent.mkdir(parents=True, exist_ok=True)
    metrics_target.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return artifact


def train_model(processed_path: Path | None = None, artifact_path: Path | None = None) -> dict:
    processed_source = processed_path or settings.data.processed_data_path
    artifact_target = artifact_path or settings.model.artifact_path

    if not processed_source.exists():
        dataframe = build_processed_dataset()
    else:
        dataframe = pd.read_csv(processed_source, parse_dates=[settings.data.timestamp_column])

    return train_model_from_processed_dataframe(
        dataframe,
        artifact_path=artifact_target,
        metrics_path=settings.model.metrics_path,
    )


def train_model_from_raw_dataframe(
    dataframe: pd.DataFrame,
    artifact_path: Path | None = None,
    metrics_path: Path | None = None,
    processed_output_path: Path | None = None,
) -> dict:
    processed = prepare_processed_frame(dataframe)
    if processed_output_path is not None:
        processed_output_path.parent.mkdir(parents=True, exist_ok=True)
        processed.to_csv(processed_output_path, index=False)
    return train_model_from_processed_dataframe(
        processed,
        artifact_path=artifact_path,
        metrics_path=metrics_path,
    )


def ensure_model_artifact() -> dict:
    if settings.model.artifact_path.exists():
        return joblib.load(settings.model.artifact_path)
    return train_model()


if __name__ == "__main__":
    artifact = train_model()
    print("Model trained successfully")
    print(json.dumps(artifact["metrics"], indent=2))
