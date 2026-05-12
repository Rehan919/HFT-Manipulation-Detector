from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from config import settings
from model.predict import load_artifact
from model.train import ensure_model_artifact


@dataclass
class DetectionResult:
    timestamp: str
    price: float
    volume: float
    anomaly_score: float
    is_anomaly: bool
    signal: str
    price_zscore: float
    volume_spike_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_signal(is_anomaly: bool, price_zscore: float, volume_spike_ratio: float) -> str:
    strong_spike = (
        price_zscore >= settings.detection.high_risk_price_zscore
        or volume_spike_ratio >= settings.detection.high_risk_volume_ratio
    )
    suspicious_spike = (
        price_zscore >= settings.detection.suspicious_price_zscore
        or volume_spike_ratio >= settings.detection.suspicious_volume_ratio
    )

    if is_anomaly and strong_spike:
        return "HIGH_RISK"
    if is_anomaly and suspicious_spike:
        return "SUSPICIOUS"
    return "NORMAL"


class Detector:
    def __init__(self, artifact: dict | None = None) -> None:
        self.artifact = artifact or ensure_model_artifact()

    def score_row(self, row: pd.Series | dict[str, Any]) -> DetectionResult:
        series = pd.Series(row)
        frame = pd.DataFrame([series])
        features = self.artifact["feature_columns"]
        transformed = self.artifact["scaler"].transform(frame[features])
        anomaly_score = float(-self.artifact["model"].score_samples(transformed)[0])
        is_anomaly = anomaly_score >= float(self.artifact["threshold"])
        price_zscore = float(series.get("price_zscore", 0.0))
        volume_spike_ratio = float(series.get("volume_spike_ratio", 0.0))
        signal = resolve_signal(is_anomaly, price_zscore, volume_spike_ratio)

        return DetectionResult(
            timestamp=str(series[settings.data.timestamp_column]),
            price=float(series[settings.data.price_column]),
            volume=float(series[settings.data.volume_column]),
            anomaly_score=anomaly_score,
            is_anomaly=is_anomaly,
            signal=signal,
            price_zscore=price_zscore,
            volume_spike_ratio=volume_spike_ratio,
        )


def load_detector() -> Detector:
    artifact = load_artifact() if settings.model.artifact_path.exists() else ensure_model_artifact()
    return Detector(artifact=artifact)
