from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd

from config import settings


def load_artifact(path: Path | None = None) -> dict:
    source = path or settings.model.artifact_path
    if not source.exists():
        raise FileNotFoundError(
            f"Model artifact not found at {source}. Run model/train.py first."
        )
    return joblib.load(source)


def score_frame(dataframe: pd.DataFrame, artifact: dict | None = None) -> pd.DataFrame:
    loaded = artifact or load_artifact()
    frame = dataframe.copy()
    features = loaded["feature_columns"]
    transformed = loaded["scaler"].transform(frame[features])
    scores = -loaded["model"].score_samples(transformed)
    frame["anomaly_score"] = scores
    frame["is_anomaly"] = frame["anomaly_score"] >= loaded["threshold"]
    return frame
