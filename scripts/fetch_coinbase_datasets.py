from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

import httpx
import pandas as pd

from config import settings
from model.features import build_processed_dataset


TOTAL_TRADES = 24000
WINDOW_SIZE = 5000
STEP = 250


@dataclass(frozen=True)
class WindowSelection:
    name: str
    start: int
    end: int
    volatility: float
    max_abs_return: float

    @property
    def score(self) -> float:
        return self.volatility + self.max_abs_return


def fetch_recent_trades(total: int = TOTAL_TRADES, page_limit: int = 1000) -> pd.DataFrame:
    headers = {"User-Agent": "hft-ai-detector/1.0"}
    endpoint = f"{settings.live.rest_base_url}/products/{settings.live.product_id}/trades"
    after: str | None = None
    collected: list[dict] = []

    with httpx.Client(timeout=20.0, headers=headers) as client:
        while len(collected) < total:
            params: dict[str, str | int] = {"limit": min(page_limit, total - len(collected))}
            if after:
                params["after"] = after
            response = client.get(endpoint, params=params)
            response.raise_for_status()
            payload = response.json()
            if not payload:
                break
            collected.extend(payload)
            next_after = response.headers.get("cb-after")
            if not next_after or next_after == after:
                break
            after = next_after

    if not collected:
        raise ValueError("No trades were fetched from Coinbase.")

    frame = pd.DataFrame(collected)
    frame = frame.rename(columns={"time": "timestamp", "size": "volume"})
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "price", "volume"])
    frame = frame.drop_duplicates(subset=["trade_id"])
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    return frame


def build_candidates(frame: pd.DataFrame, window_size: int = WINDOW_SIZE, step: int = STEP) -> tuple[list[WindowSelection], pd.Series]:
    returns = frame["price"].pct_change().fillna(0.0)
    candidates: list[WindowSelection] = []

    for start in range(0, len(frame) - window_size + 1, step):
        end = start + window_size
        window_returns = returns.iloc[start:end]
        candidates.append(
            WindowSelection(
                name="candidate",
                start=start,
                end=end,
                volatility=float(window_returns.std()),
                max_abs_return=float(window_returns.abs().max()),
            )
        )
    if not candidates:
        raise ValueError(
            f"Need at least {window_size} fetched trades to build datasets, found {len(frame)}."
        )
    return candidates, returns


def overlaps(left: WindowSelection, right: WindowSelection) -> bool:
    return not (left.end <= right.start or right.end <= left.start)


def pick_windows(
    candidates: list[WindowSelection],
    returns: pd.Series,
) -> tuple[WindowSelection, WindowSelection, WindowSelection]:
    baseline = min(candidates, key=lambda item: (item.score, item.max_abs_return))

    baseline_returns = returns.iloc[baseline.start : baseline.end].abs()
    jump_threshold = float(baseline_returns.quantile(0.995))

    def anomaly_score(item: WindowSelection) -> tuple[float, float, float]:
        window_returns = returns.iloc[item.start : item.end].abs()
        exceedances = float((window_returns > jump_threshold).sum())
        return (exceedances, item.max_abs_return, item.volatility)

    anomaly_options = [item for item in candidates if not overlaps(item, baseline)]
    anomaly = max(anomaly_options, key=anomaly_score)

    remaining = [item for item in candidates if not overlaps(item, baseline) and not overlaps(item, anomaly)]
    moderate_remaining = [item for item in remaining if item.max_abs_return < anomaly.max_abs_return * 0.9]
    pool = moderate_remaining or remaining or [item for item in candidates if not overlaps(item, baseline)]
    simulation = max(pool, key=lambda item: (item.volatility, item.max_abs_return))

    return (
        WindowSelection("baseline_training", baseline.start, baseline.end, baseline.volatility, baseline.max_abs_return),
        WindowSelection("fast_simulation", simulation.start, simulation.end, simulation.volatility, simulation.max_abs_return),
        WindowSelection("anomaly_holdout", anomaly.start, anomaly.end, anomaly.volatility, anomaly.max_abs_return),
    )


def save_window(frame: pd.DataFrame, selection: WindowSelection, path: Path) -> pd.DataFrame:
    path.parent.mkdir(parents=True, exist_ok=True)
    sliced = frame.iloc[selection.start : selection.end].copy().reset_index(drop=True)
    sliced["timestamp"] = sliced["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S.%f%z")
    sliced.to_csv(path, index=False)
    return sliced


def main() -> None:
    frame = fetch_recent_trades()
    candidates, returns = build_candidates(frame)
    baseline, simulation, anomaly = pick_windows(candidates, returns)

    baseline_frame = save_window(frame, baseline, settings.data.raw_data_path)
    simulation_frame = save_window(frame, simulation, settings.data.simulation_raw_data_path)
    anomaly_frame = save_window(frame, anomaly, settings.data.anomaly_holdout_path)
    build_processed_dataset(
        raw_path=settings.data.raw_data_path,
        processed_path=settings.data.processed_data_path,
    )
    build_processed_dataset(
        raw_path=settings.data.simulation_raw_data_path,
        processed_path=settings.data.simulation_processed_data_path,
    )
    build_processed_dataset(
        raw_path=settings.data.anomaly_holdout_path,
        processed_path=settings.data.anomaly_holdout_processed_path,
    )

    manifest = {
        "provider": settings.live.provider,
        "product_id": settings.live.product_id,
        "fetched_trade_count": int(len(frame)),
        "window_size": WINDOW_SIZE,
        "baseline_training": {
            "path": str(settings.data.raw_data_path),
            "processed_path": str(settings.data.processed_data_path),
            "rows": int(len(baseline_frame)),
            "volatility": baseline.volatility,
            "max_abs_return": baseline.max_abs_return,
        },
        "fast_simulation": {
            "path": str(settings.data.simulation_raw_data_path),
            "processed_path": str(settings.data.simulation_processed_data_path),
            "rows": int(len(simulation_frame)),
            "volatility": simulation.volatility,
            "max_abs_return": simulation.max_abs_return,
        },
        "anomaly_holdout": {
            "path": str(settings.data.anomaly_holdout_path),
            "processed_path": str(settings.data.anomaly_holdout_processed_path),
            "rows": int(len(anomaly_frame)),
            "volatility": anomaly.volatility,
            "max_abs_return": anomaly.max_abs_return,
        },
    }

    manifest_path = settings.data.raw_data_path.parent / "dataset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
