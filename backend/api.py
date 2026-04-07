from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.detector import Detector, load_detector
from backend.live_market import (
    LiveMarketService,
    create_primary_live_market_service,
    create_secondary_live_market_service,
)
from config import settings
from model.features import build_processed_dataset


FRONTEND_DIST_DIR = Path(__file__).resolve().parents[1] / "frontend" / "dist"


def load_processed_frame() -> pd.DataFrame:
    if not settings.data.simulation_processed_data_path.exists():
        raw_source = (
            settings.data.simulation_raw_data_path
            if settings.data.simulation_raw_data_path.exists()
            else settings.data.raw_data_path
        )
        return build_processed_dataset(
            raw_path=raw_source,
            processed_path=settings.data.simulation_processed_data_path,
        )
    return pd.read_csv(
        settings.data.simulation_processed_data_path,
        parse_dates=[settings.data.timestamp_column],
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.dataset = load_processed_frame()
    app.state.detector = load_detector()
    app.state.live_market = create_primary_live_market_service()
    app.state.secondary_live_market = create_secondary_live_market_service()
    app.state.cursor = 0
    app.state.latest_event = None
    await app.state.live_market.start()
    await app.state.secondary_live_market.start()
    yield
    await app.state.live_market.stop()
    await app.state.secondary_live_market.stop()


app = FastAPI(title="HFT Manipulation Detector API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def next_event(dataset: pd.DataFrame, detector: Detector, cursor: int) -> tuple[dict[str, Any], int]:
    if dataset.empty:
        raise HTTPException(status_code=404, detail="Processed dataset is empty.")
    row = dataset.iloc[cursor % len(dataset)]
    result = detector.score_row(row).to_dict()
    for field in ("scenario_label", "alert_message", "manipulation_tag", "confirmed_simulation_case"):
        if field in row.index:
            value = row[field]
            if pd.notna(value):
                if field == "confirmed_simulation_case":
                    result[field] = str(value).strip().lower() in {"true", "1", "yes"}
                else:
                    result[field] = str(value)
    if result.get("confirmed_simulation_case"):
        result["signal"] = "HIGH_RISK"
        result["is_anomaly"] = True
        result["simulation_override"] = True
    result["cursor"] = cursor % len(dataset)
    result["completed_cycle"] = (cursor + 1) % len(dataset) == 0
    return result, cursor + 1


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "model_ready": settings.model.artifact_path.exists(),
        "processed_ready": settings.data.processed_data_path.exists(),
        "simulation_processed_ready": settings.data.simulation_processed_data_path.exists(),
        "live_market_enabled": settings.live.enabled,
    }


@app.get("/stream")
def stream() -> dict[str, Any]:
    event, cursor = next_event(app.state.dataset, app.state.detector, app.state.cursor)
    app.state.cursor = cursor
    app.state.latest_event = event
    return event


@app.get("/status")
def status() -> dict[str, Any]:
    if app.state.latest_event is None:
        return {"message": "Simulation has not started yet. Call /stream first."}
    return app.state.latest_event


@app.post("/reset")
def reset() -> dict[str, Any]:
    app.state.cursor = 0
    app.state.latest_event = None
    return {"message": "Simulation cursor reset."}


@app.get("/live/health")
def live_health() -> dict[str, Any]:
    return app.state.live_market.health()


@app.get("/live/status")
def live_status() -> dict[str, Any]:
    return app.state.live_market.snapshot()


@app.get("/live/coinbase/health")
def live_coinbase_health() -> dict[str, Any]:
    return app.state.live_market.health()


@app.get("/live/coinbase/status")
def live_coinbase_status() -> dict[str, Any]:
    return app.state.live_market.snapshot()


@app.get("/live/secondary/health")
def live_secondary_health() -> dict[str, Any]:
    return app.state.secondary_live_market.health()


@app.get("/live/secondary/status")
def live_secondary_status() -> dict[str, Any]:
    return app.state.secondary_live_market.snapshot()


if FRONTEND_DIST_DIR.exists():
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/")
    def frontend_index() -> FileResponse:
        return FileResponse(FRONTEND_DIST_DIR / "index.html")


    @app.get("/{full_path:path}")
    def frontend_catch_all(full_path: str) -> FileResponse:
        requested = FRONTEND_DIST_DIR / full_path
        if requested.exists() and requested.is_file():
            return FileResponse(requested)
        return FileResponse(FRONTEND_DIST_DIR / "index.html")
