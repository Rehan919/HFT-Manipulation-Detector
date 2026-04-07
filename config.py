from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class DataConfig:
    raw_data_path: Path = BASE_DIR / "data" / "real" / "coinbase_baseline_training.csv"
    processed_data_path: Path = BASE_DIR / "data" / "processed" / "training_processed.csv"
    simulation_raw_data_path: Path = BASE_DIR / "data" / "real" / "coinbase_fast_simulation.csv"
    simulation_processed_data_path: Path = BASE_DIR / "data" / "processed" / "simulation_processed.csv"
    anomaly_holdout_path: Path = BASE_DIR / "data" / "real" / "coinbase_anomaly_holdout.csv"
    anomaly_holdout_processed_path: Path = BASE_DIR / "data" / "processed" / "anomaly_holdout_processed.csv"
    legacy_sample_data_path: Path = BASE_DIR / "data" / "raw" / "trades.csv"
    timestamp_column: str = "timestamp"
    price_column: str = "price"
    volume_column: str = "volume"


@dataclass(frozen=True)
class FeatureConfig:
    short_window: int = 5
    long_window: int = 20
    epsilon: float = 1e-9
    feature_columns: tuple[str, ...] = (
        "price_change",
        "volume_change",
        "rolling_mean_price",
        "rolling_mean_volume",
        "rolling_std_price",
        "price_zscore",
        "volume_spike_ratio",
    )


@dataclass(frozen=True)
class ModelConfig:
    artifact_path: Path = BASE_DIR / "model" / "model.pkl"
    live_artifact_path: Path = BASE_DIR / "model" / "live_model.pkl"
    metrics_path: Path = BASE_DIR / "model" / "metrics.json"
    live_metrics_path: Path = BASE_DIR / "model" / "live_metrics.json"
    n_estimators: int = 100
    contamination: float = 0.005
    random_state: int = 42
    validation_fraction: float = 0.2


@dataclass(frozen=True)
class DetectionConfig:
    suspicious_price_zscore: float = 3.25
    suspicious_volume_ratio: float = 6.0
    high_risk_price_zscore: float = 5.0
    high_risk_volume_ratio: float = 10.0


@dataclass(frozen=True)
class ApiConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    simulator_delay_seconds: float = 0.15
    frontend_live_poll_ms: int = 1000
    frontend_simulation_poll_ms: int = 200


@dataclass(frozen=True)
class LiveMarketConfig:
    enabled: bool = env_bool("ENABLE_LIVE_MARKET", True)
    provider: str = os.getenv("LIVE_MARKET_PROVIDER", "coinbase_exchange")
    product_id: str = os.getenv("COINBASE_PRODUCT_ID", "BTC-USD")
    rest_base_url: str = os.getenv("COINBASE_REST_BASE_URL", "https://api.exchange.coinbase.com")
    websocket_url: str = os.getenv("COINBASE_WS_URL", "wss://ws-feed.exchange.coinbase.com")
    bootstrap_trade_limit: int = int(os.getenv("LIVE_BOOTSTRAP_TRADE_LIMIT", "1200"))
    history_size: int = int(os.getenv("LIVE_HISTORY_SIZE", "1500"))
    reconnect_delay_seconds: float = float(os.getenv("LIVE_RECONNECT_DELAY_SECONDS", "5"))
    raw_capture_path: Path = BASE_DIR / "data" / "live" / "coinbase_bootstrap.csv"
    processed_capture_path: Path = BASE_DIR / "data" / "live" / "coinbase_processed.csv"


@dataclass(frozen=True)
class SecondaryLiveConfig:
    enabled: bool = env_bool("ENABLE_SECONDARY_LIVE", True)
    provider: str = os.getenv("SECONDARY_LIVE_PROVIDER", "coinbase_exchange")
    product_id: str = os.getenv("SECONDARY_COINBASE_PRODUCT_ID", "ETH-USD")
    rest_base_url: str = os.getenv("SECONDARY_COINBASE_REST_BASE_URL", "https://api.exchange.coinbase.com")
    websocket_url: str = os.getenv("SECONDARY_COINBASE_WS_URL", "wss://ws-feed.exchange.coinbase.com")
    bootstrap_trade_limit: int = int(os.getenv("SECONDARY_BOOTSTRAP_TRADE_LIMIT", "1200"))
    history_size: int = int(os.getenv("SECONDARY_HISTORY_SIZE", "1500"))
    reconnect_delay_seconds: float = float(os.getenv("SECONDARY_RECONNECT_DELAY_SECONDS", "5"))
    raw_capture_path: Path = BASE_DIR / "data" / "live" / "secondary_coinbase_bootstrap.csv"
    processed_capture_path: Path = BASE_DIR / "data" / "live" / "secondary_coinbase_processed.csv"
    artifact_path: Path = BASE_DIR / "model" / "secondary_live_model.pkl"
    metrics_path: Path = BASE_DIR / "model" / "secondary_live_metrics.json"


@dataclass(frozen=True)
class Settings:
    data: DataConfig = field(default_factory=DataConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    live: LiveMarketConfig = field(default_factory=LiveMarketConfig)
    secondary_live: SecondaryLiveConfig = field(default_factory=SecondaryLiveConfig)


settings = Settings()
