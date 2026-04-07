from __future__ import annotations

from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd

from config import settings
from model.features import build_processed_dataset


BASE_REPEAT_COUNT = 3
ALERT_SPACING_ROWS = 420


def make_base_frame() -> pd.DataFrame:
    source = pd.read_csv(settings.data.anomaly_holdout_path)
    source["timestamp"] = pd.to_datetime(source["timestamp"], utc=True)
    for column in ("scenario_label", "alert_message", "manipulation_tag", "confirmed_simulation_case"):
        if column in source.columns:
            source = source.drop(columns=[column])
    source = source.sort_values("timestamp").reset_index(drop=True)
    step = source["timestamp"].diff().median()
    if pd.isna(step) or step <= pd.Timedelta(0):
        step = pd.Timedelta(milliseconds=250)

    frames: list[pd.DataFrame] = []
    for repeat_index in range(BASE_REPEAT_COUNT):
        frame = source.copy()
        frame["timestamp"] = frame["timestamp"] + step * len(source) * repeat_index
        drift = 1 + repeat_index * 0.00035
        frame["price"] = frame["price"] * drift
        frame["volume"] = frame["volume"] * (1 + repeat_index * 0.08)
        if "trade_id" in frame.columns:
            frame["trade_id"] = frame["trade_id"].astype("int64") + repeat_index * 10_000_000
        frame["scenario_label"] = ""
        frame["alert_message"] = ""
        frame["manipulation_tag"] = ""
        frame["confirmed_simulation_case"] = False
        frames.append(frame)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("timestamp").reset_index(drop=True)
    return combined


def inject_window(
    frame: pd.DataFrame,
    *,
    start: int,
    length: int,
    price_multiplier: float,
    volume_multiplier: float,
    label: str,
    tag: str,
    message: str,
) -> None:
    end = min(len(frame), start + length)
    if start >= end:
        return

    target = frame.loc[start : end - 1].copy()
    ramp = pd.Series(range(len(target)), dtype="float64") / max(len(target) - 1, 1)
    frame.loc[start : end - 1, "price"] = target["price"].to_numpy() * (
        1 + (price_multiplier - 1) * ramp.to_numpy()
    )
    frame.loc[start : end - 1, "volume"] = target["volume"].to_numpy() * (
        1 + (volume_multiplier - 1) * ramp.to_numpy()
    )
    frame.loc[start : end - 1, "scenario_label"] = label
    frame.loc[start : end - 1, "alert_message"] = message
    frame.loc[start : end - 1, "manipulation_tag"] = tag
    frame.loc[start : end - 1, "confirmed_simulation_case"] = True


def inject_dramatic_cases(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    size = len(working)
    scenarios = [
        {
            "label": "Open Pump",
            "tag": "opening_pump",
            "message": "Injected simulation case: aggressive coordinated buying burst right after replay start.",
            "price_multiplier": 1.024,
            "volume_multiplier": 28.0,
            "length": 110,
        },
        {
            "label": "Flash Dump",
            "tag": "flash_dump",
            "message": "Injected simulation case: abrupt sell collapse with abnormal trade intensity.",
            "price_multiplier": 0.976,
            "volume_multiplier": 32.0,
            "length": 120,
        },
        {
            "label": "Pump Burst",
            "tag": "pump_and_dump",
            "message": "Injected simulation case: coordinated buying surge with extreme volume acceleration.",
            "price_multiplier": 1.018,
            "volume_multiplier": 18.0,
            "length": 130,
        },
        {
            "label": "Liquidity Vacuum",
            "tag": "liquidity_sweep",
            "message": "Injected simulation case: abrupt sell sweep with heavy tape pressure and violent displacement.",
            "price_multiplier": 0.982,
            "volume_multiplier": 24.0,
            "length": 120,
        },
        {
            "label": "Wash Burst",
            "tag": "wash_trade_cluster",
            "message": "Injected simulation case: repeated abnormal prints designed to resemble artificial activity.",
            "price_multiplier": 1.026,
            "volume_multiplier": 30.0,
            "length": 150,
        },
        {
            "label": "Closing Frenzy",
            "tag": "closing_manipulation_wave",
            "message": "Injected simulation case: late-session manipulation wave with exaggerated price lift and heavy volume.",
            "price_multiplier": 1.03,
            "volume_multiplier": 40.0,
            "length": 180,
        },
    ]

    start_points = range(180, size - 200, ALERT_SPACING_ROWS)
    for scenario_index, start in enumerate(start_points):
        scenario = scenarios[scenario_index % len(scenarios)]
        inject_window(
            working,
            start=start,
            length=scenario["length"],
            price_multiplier=scenario["price_multiplier"],
            volume_multiplier=scenario["volume_multiplier"],
            label=scenario["label"],
            tag=scenario["tag"],
            message=scenario["message"],
        )

    working["timestamp"] = working["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S.%f%z")
    return working


def main() -> None:
    dramatic = inject_dramatic_cases(make_base_frame())
    settings.data.simulation_raw_data_path.parent.mkdir(parents=True, exist_ok=True)
    dramatic.to_csv(settings.data.simulation_raw_data_path, index=False)
    processed = build_processed_dataset(
        raw_path=settings.data.simulation_raw_data_path,
        processed_path=settings.data.simulation_processed_data_path,
    )
    print(
        {
            "raw_rows": int(len(dramatic)),
            "processed_rows": int(len(processed)),
            "path": str(settings.data.simulation_raw_data_path),
        }
    )


if __name__ == "__main__":
    main()
