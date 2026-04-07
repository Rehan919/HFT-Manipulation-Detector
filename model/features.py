from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config import settings


def load_raw_dataset(path: Path | None = None) -> pd.DataFrame:
    source = path or settings.data.raw_data_path
    dataframe = pd.read_csv(source)
    required = {
        settings.data.timestamp_column,
        settings.data.price_column,
        settings.data.volume_column,
    }
    missing = required.difference(dataframe.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    return dataframe


def clean_dataset(dataframe: pd.DataFrame) -> pd.DataFrame:
    cleaned = dataframe.copy()
    cleaned[settings.data.timestamp_column] = pd.to_datetime(
        cleaned[settings.data.timestamp_column], errors="coerce"
    )
    cleaned[settings.data.price_column] = pd.to_numeric(
        cleaned[settings.data.price_column], errors="coerce"
    )
    cleaned[settings.data.volume_column] = pd.to_numeric(
        cleaned[settings.data.volume_column], errors="coerce"
    )

    cleaned = cleaned.dropna(
        subset=[
            settings.data.timestamp_column,
            settings.data.price_column,
            settings.data.volume_column,
        ]
    )
    if "trade_id" in cleaned.columns:
        cleaned = cleaned.drop_duplicates(subset=["trade_id"])
    else:
        cleaned = cleaned.drop_duplicates(
            subset=[
                settings.data.timestamp_column,
                settings.data.price_column,
                settings.data.volume_column,
            ]
        )
    cleaned = cleaned.sort_values(settings.data.timestamp_column).reset_index(drop=True)
    return cleaned


def engineer_features(dataframe: pd.DataFrame) -> pd.DataFrame:
    feature_frame = dataframe.copy()
    price_col = settings.data.price_column
    volume_col = settings.data.volume_column
    short_window = settings.features.short_window
    long_window = settings.features.long_window
    epsilon = settings.features.epsilon

    feature_frame["price_change"] = feature_frame[price_col].diff()
    feature_frame["volume_change"] = (
        feature_frame[volume_col].pct_change().replace([np.inf, -np.inf], np.nan)
    )
    feature_frame["rolling_mean_price"] = (
        feature_frame[price_col].rolling(window=short_window, min_periods=short_window).mean()
    )
    feature_frame["rolling_mean_volume"] = (
        feature_frame[volume_col].rolling(window=short_window, min_periods=short_window).mean()
    )
    feature_frame["rolling_std_price"] = (
        feature_frame[price_col].rolling(window=long_window, min_periods=long_window).std()
    )
    feature_frame["price_zscore"] = (
        (feature_frame[price_col] - feature_frame["rolling_mean_price"]).abs()
        / (feature_frame["rolling_std_price"] + epsilon)
    )
    feature_frame["volume_spike_ratio"] = (
        feature_frame[volume_col] / (feature_frame["rolling_mean_volume"] + epsilon)
    )

    feature_frame = feature_frame.dropna(
        subset=[
            settings.data.timestamp_column,
            settings.data.price_column,
            settings.data.volume_column,
            "price_change",
            "volume_change",
            "rolling_mean_price",
            "rolling_mean_volume",
            "rolling_std_price",
            "price_zscore",
            "volume_spike_ratio",
        ]
    ).reset_index(drop=True)
    return feature_frame


def prepare_processed_frame(dataframe: pd.DataFrame) -> pd.DataFrame:
    engineered = engineer_features(clean_dataset(dataframe))
    if engineered.empty:
        raise ValueError(
            "Feature engineering produced no rows. Check that the input dataset has "
            "enough records for the configured rolling windows."
        )
    return engineered


def build_processed_dataset(
    raw_path: Path | None = None, processed_path: Path | None = None
) -> pd.DataFrame:
    raw_source = raw_path or settings.data.raw_data_path
    processed_target = processed_path or settings.data.processed_data_path
    processed_target.parent.mkdir(parents=True, exist_ok=True)

    engineered = prepare_processed_frame(load_raw_dataset(raw_source))
    engineered.to_csv(processed_target, index=False)
    return engineered
