from __future__ import annotations

import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd

from config import settings
from model.predict import load_artifact, score_frame


def summarize(path: Path) -> dict:
    frame = pd.read_csv(path, parse_dates=[settings.data.timestamp_column])
    scored = score_frame(frame, artifact=load_artifact())
    suspicious = int((scored["anomaly_score"] >= scored["anomaly_score"].quantile(0.95)).sum())
    return {
        "path": str(path),
        "rows": int(len(scored)),
        "anomaly_flags": int(scored["is_anomaly"].sum()),
        "top_5pct_scores": suspicious,
        "max_score": float(scored["anomaly_score"].max()),
        "mean_score": float(scored["anomaly_score"].mean()),
    }


def main() -> None:
    payload = {
        "baseline_training": summarize(settings.data.processed_data_path),
        "fast_simulation": summarize(settings.data.simulation_processed_data_path),
        "anomaly_holdout": summarize(settings.data.anomaly_holdout_processed_path),
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
