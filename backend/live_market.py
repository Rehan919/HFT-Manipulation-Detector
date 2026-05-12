from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any

import httpx
import numpy as np
import pandas as pd
import websockets

from backend.detector import Detector
from config import settings
from model.predict import load_artifact
from model.train import train_model_from_raw_dataframe


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_builtin(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


@dataclass
class CoinbaseExchangeClient:
    product_id: str
    rest_base_url: str
    websocket_url: str

    async def fetch_recent_trades(self, limit: int) -> list[dict[str, Any]]:
        headers = {"User-Agent": "hft-ai-detector/1.0"}
        collected: list[dict[str, Any]] = []
        after: str | None = None

        async with httpx.AsyncClient(base_url=self.rest_base_url, timeout=20.0, headers=headers) as client:
            while len(collected) < limit:
                params: dict[str, str | int] = {"limit": min(1000, limit - len(collected))}
                if after:
                    params["after"] = after
                response = await client.get(f"/products/{self.product_id}/trades", params=params)
                response.raise_for_status()
                payload = response.json()
                if not payload:
                    break
                collected.extend(payload)
                next_after = response.headers.get("cb-after")
                if not next_after or next_after == after:
                    break
                after = next_after

        normalized = [normalize_trade_message(item, self.product_id, source="rest") for item in collected]
        normalized = [item for item in normalized if item is not None]
        normalized.sort(key=lambda item: item["timestamp"])
        return normalized

    async def stream_ticker(self):
        subscribe_message = {
            "type": "subscribe",
            "product_ids": [self.product_id],
            "channels": ["ticker"],
        }
        async with websockets.connect(self.websocket_url, ping_interval=20, ping_timeout=20) as websocket:
            await websocket.send(json.dumps(subscribe_message))
            async for message in websocket:
                payload = json.loads(message)
                trade = normalize_trade_message(payload, self.product_id, source="websocket")
                if trade is not None:
                    yield trade


def normalize_trade_message(
    payload: dict[str, Any],
    product_id: str,
    source: str,
) -> dict[str, Any] | None:
    message_type = payload.get("type")
    incoming_product_id = payload.get("product_id", product_id)
    if incoming_product_id != product_id:
        return None

    if source == "rest":
        timestamp = payload.get("time")
        price = payload.get("price")
        size = payload.get("size")
    else:
        if message_type != "ticker":
            return None
        timestamp = payload.get("time")
        price = payload.get("price")
        size = payload.get("last_size") or payload.get("size")

    if timestamp is None or price is None or size is None:
        return None

    return {
        "timestamp": timestamp,
        "price": float(price),
        "volume": float(size),
        "trade_id": payload.get("trade_id"),
        "product_id": incoming_product_id,
        "side": payload.get("side"),
        "best_bid": float(payload["best_bid"]) if payload.get("best_bid") else None,
        "best_ask": float(payload["best_ask"]) if payload.get("best_ask") else None,
        "volume_24h": float(payload["volume_24h"]) if payload.get("volume_24h") else None,
    }


class LiveMarketService:
    def __init__(
        self,
        *,
        provider_name: str,
        product_id: str,
        rest_base_url: str,
        websocket_url: str,
        bootstrap_trade_limit: int,
        history_size: int,
        reconnect_delay_seconds: float,
        raw_capture_path,
        processed_capture_path,
        artifact_path,
        metrics_path,
        min_score_interval_seconds: float,
        enabled: bool = True,
    ) -> None:
        self.provider_name = provider_name
        self.product_id = product_id
        self.bootstrap_trade_limit = bootstrap_trade_limit
        self.reconnect_delay_seconds = reconnect_delay_seconds
        self.min_score_interval_seconds = min_score_interval_seconds
        self.raw_capture_path = raw_capture_path
        self.processed_capture_path = processed_capture_path
        self.artifact_path = artifact_path
        self.metrics_path = metrics_path
        self.enabled = enabled
        self.client = CoinbaseExchangeClient(
            product_id=product_id,
            rest_base_url=rest_base_url,
            websocket_url=websocket_url,
        )
        self.history: deque[dict[str, Any]] = deque(maxlen=history_size)
        self.detector: Detector | None = None
        self.task: asyncio.Task | None = None
        self.connection_status = "idle"
        self.last_error: str | None = None
        self.latest_event: dict[str, Any] | None = None
        self.last_update_at: str | None = None
        self.bootstrap_rows = 0
        self.score_task: asyncio.Task | None = None
        self.score_requested = False
        self.last_score_monotonic = 0.0

    async def start(self) -> None:
        if not self.enabled:
            self.connection_status = "disabled"
            return
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.run_forever())

    async def stop(self) -> None:
        await self._cancel_task(self.task)
        await self._cancel_task(self.score_task)
        self.task = None
        self.score_task = None
        self.score_requested = False

    async def _cancel_task(self, task: asyncio.Task | None) -> None:
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def health(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider_name,
            "product_id": self.product_id,
            "connection_status": self.connection_status,
            "bootstrap_rows": self.bootstrap_rows,
            "model_ready": self.detector is not None,
            "last_error": self.last_error,
            "last_update_at": self.last_update_at,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            **self.health(),
            "latest_event": self.latest_event,
        }

    async def run_forever(self) -> None:
        while True:
            try:
                await self.bootstrap()
                self.connection_status = "streaming"
                async for trade in self.client.stream_ticker():
                    self.last_error = None
                    await self.ingest_trade(trade)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.connection_status = "reconnecting"
                self.last_error = str(exc)
                await asyncio.sleep(self.reconnect_delay_seconds)

    async def bootstrap(self) -> None:
        self.connection_status = "bootstrapping"
        trades = await self.client.fetch_recent_trades(self.bootstrap_trade_limit)
        bootstrap_frame = pd.DataFrame(trades)
        if bootstrap_frame.empty:
            raise ValueError("Coinbase bootstrap returned no trade rows.")

        artifact = await asyncio.to_thread(self._train_bootstrap_artifact, bootstrap_frame)
        self.detector = Detector(artifact=artifact)
        self.history.clear()
        for trade in trades:
            self.history.append(trade)
        self.bootstrap_rows = len(self.history)
        self.last_update_at = utc_now_iso()
        self.connection_status = "connecting"
        self.latest_event = None
        self.score_requested = False
        self.last_score_monotonic = 0.0
        await self.request_score_refresh(force=True)

    def _train_bootstrap_artifact(self, bootstrap_frame: pd.DataFrame) -> dict:
        self.raw_capture_path.parent.mkdir(parents=True, exist_ok=True)
        bootstrap_frame.to_csv(self.raw_capture_path, index=False)
        return train_model_from_raw_dataframe(
            bootstrap_frame,
            artifact_path=self.artifact_path,
            metrics_path=self.metrics_path,
            processed_output_path=self.processed_capture_path,
        )

    async def ingest_trade(self, trade: dict[str, Any]) -> None:
        self.history.append(trade)
        self.last_update_at = utc_now_iso()
        await self.request_score_refresh()

    async def request_score_refresh(self, force: bool = False) -> None:
        if self.detector is None or not self.history:
            return
        if force:
            self.last_score_monotonic = 0.0
        self.score_requested = True
        if self.score_task is None or self.score_task.done():
            self.score_task = asyncio.create_task(self._run_score_loop())

    async def _run_score_loop(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            while self.score_requested:
                self.score_requested = False
                remaining = self.min_score_interval_seconds - (
                    loop.time() - self.last_score_monotonic
                )
                if remaining > 0:
                    await asyncio.sleep(remaining)

                history_snapshot = list(self.history)
                event = await asyncio.to_thread(
                    self._score_history_snapshot,
                    history_snapshot,
                )
                self.last_score_monotonic = loop.time()
                if event is not None:
                    self.latest_event = event
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error = str(exc)

    def _score_history_snapshot(self, history_snapshot: list[dict[str, Any]]) -> dict[str, Any] | None:
        if self.detector is None or not history_snapshot:
            return None

        history_frame = pd.DataFrame(history_snapshot)
        from model.features import prepare_processed_frame

        processed = prepare_processed_frame(history_frame)
        latest_row = processed.iloc[-1]
        result = self.detector.score_row(latest_row).to_dict()
        result.update(
            {
                "source": "live",
                "provider": self.provider_name,
                "product_id": to_builtin(latest_row.get("product_id", self.product_id)),
                "trade_id": to_builtin(latest_row.get("trade_id")),
                "side": to_builtin(latest_row.get("side")),
                "best_bid": to_builtin(latest_row.get("best_bid")),
                "best_ask": to_builtin(latest_row.get("best_ask")),
                "volume_24h": to_builtin(latest_row.get("volume_24h")),
                "model_ready": True,
            }
        )
        return result


def create_primary_live_market_service() -> LiveMarketService:
    return LiveMarketService(
        provider_name=settings.live.provider,
        product_id=settings.live.product_id,
        rest_base_url=settings.live.rest_base_url,
        websocket_url=settings.live.websocket_url,
        bootstrap_trade_limit=settings.live.bootstrap_trade_limit,
        history_size=settings.live.history_size,
        reconnect_delay_seconds=settings.live.reconnect_delay_seconds,
        min_score_interval_seconds=settings.live.min_score_interval_seconds,
        raw_capture_path=settings.live.raw_capture_path,
        processed_capture_path=settings.live.processed_capture_path,
        artifact_path=settings.model.live_artifact_path,
        metrics_path=settings.model.live_metrics_path,
        enabled=settings.live.enabled,
    )


def create_secondary_live_market_service() -> LiveMarketService:
    return LiveMarketService(
        provider_name=settings.secondary_live.provider,
        product_id=settings.secondary_live.product_id,
        rest_base_url=settings.secondary_live.rest_base_url,
        websocket_url=settings.secondary_live.websocket_url,
        bootstrap_trade_limit=settings.secondary_live.bootstrap_trade_limit,
        history_size=settings.secondary_live.history_size,
        reconnect_delay_seconds=settings.secondary_live.reconnect_delay_seconds,
        min_score_interval_seconds=settings.secondary_live.min_score_interval_seconds,
        raw_capture_path=settings.secondary_live.raw_capture_path,
        processed_capture_path=settings.secondary_live.processed_capture_path,
        artifact_path=settings.secondary_live.artifact_path,
        metrics_path=settings.secondary_live.metrics_path,
        enabled=settings.secondary_live.enabled,
    )
