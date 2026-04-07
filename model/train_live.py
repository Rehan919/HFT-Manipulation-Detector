from __future__ import annotations

import asyncio
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd

from backend.live_market import CoinbaseExchangeClient
from config import settings
from model.train import train_model_from_raw_dataframe


async def main() -> None:
    client = CoinbaseExchangeClient()
    trades = await client.fetch_recent_trades(settings.live.bootstrap_trade_limit)
    frame = pd.DataFrame(trades)
    train_model_from_raw_dataframe(
        frame,
        artifact_path=settings.model.live_artifact_path,
        metrics_path=settings.model.live_metrics_path,
        processed_output_path=settings.live.processed_capture_path,
    )
    settings.live.raw_capture_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(settings.live.raw_capture_path, index=False)
    print(f"Live model trained for {settings.live.product_id} using {len(frame)} Coinbase trades.")


if __name__ == "__main__":
    asyncio.run(main())
