from __future__ import annotations

import json
import time
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd

from backend.detector import load_detector
from config import settings
from model.features import build_processed_dataset


def iter_events(delay_seconds: float | None = None) -> None:
    delay = delay_seconds if delay_seconds is not None else settings.api.simulator_delay_seconds
    if not settings.data.simulation_processed_data_path.exists():
        raw_source = (
            settings.data.simulation_raw_data_path
            if settings.data.simulation_raw_data_path.exists()
            else settings.data.raw_data_path
        )
        dataframe = build_processed_dataset(
            raw_path=raw_source,
            processed_path=settings.data.simulation_processed_data_path,
        )
    else:
        dataframe = pd.read_csv(
            settings.data.simulation_processed_data_path,
            parse_dates=[settings.data.timestamp_column],
        )

    detector = load_detector()
    for _, row in dataframe.iterrows():
        result = detector.score_row(row)
        print(json.dumps(result.to_dict()))
        time.sleep(delay)


if __name__ == "__main__":
    iter_events()
