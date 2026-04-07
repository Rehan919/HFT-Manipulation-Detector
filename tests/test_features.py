from __future__ import annotations

import pandas as pd

from model.features import clean_dataset, engineer_features


def test_engineer_features_creates_expected_columns() -> None:
    rows = [
        {
            "timestamp": f"2026-04-07 09:{minute:02d}:00",
            "price": 100 + minute,
            "volume": 1000 + minute * 10,
        }
        for minute in range(30)
    ]
    dataframe = pd.DataFrame(rows)

    cleaned = clean_dataset(dataframe)
    engineered = engineer_features(cleaned)

    assert not engineered.empty
    assert {
        "price_change",
        "volume_change",
        "rolling_mean_price",
        "rolling_mean_volume",
        "rolling_std_price",
        "price_zscore",
        "volume_spike_ratio",
    }.issubset(engineered.columns)
    assert engineered.isna().sum().sum() == 0
