# AI HFT Manipulation Detector

Production-style HFT anomaly detection project with:

- real baseline training data from the internet
- a faster real simulation tape for the dashboard
- a separate real anomaly holdout dataset for testing
- live Coinbase market streaming
- second Coinbase live market streaming
- FastAPI backend
- React frontend
- Docker and CI support

## Dataset Strategy

This repo now uses real Coinbase public trade data instead of the old synthetic CSV for the main workflow.

Generated real datasets:

- `data/real/coinbase_baseline_training.csv`
  A calmer real BTC-USD trade window selected for baseline model training.
- `data/real/coinbase_fast_simulation.csv`
  A faster-moving real BTC-USD trade window used for simulation mode and a more active chart.
- `data/real/coinbase_anomaly_holdout.csv`
  A separate real high-stress holdout window kept aside for anomaly testing.

Processed versions:

- `data/processed/training_processed.csv`
- `data/processed/simulation_processed.csv`
- `data/processed/anomaly_holdout_processed.csv`

Dataset metadata:

- `data/real/dataset_manifest.json`

## Main Modes

### Simulation mode

Uses the real fast-simulation dataset so the graph moves quickly and looks more like a trading tape.

### Live mode

Uses live public market data for:

- Coinbase `BTC-USD`
- Coinbase `ETH-USD`

Each live source is analyzed separately.

### Holdout testing

Uses the separate anomaly holdout dataset so you can test the detector later without overwriting the main training data.

## Core Files

- [config.py](/C:/Users/rehan/OneDrive/Desktop/HFT DETECT/config.py)
- [scripts/fetch_coinbase_datasets.py](/C:/Users/rehan/OneDrive/Desktop/HFT DETECT/scripts/fetch_coinbase_datasets.py)
- [scripts/score_holdout.py](/C:/Users/rehan/OneDrive/Desktop/HFT DETECT/scripts/score_holdout.py)
- [model/features.py](/C:/Users/rehan/OneDrive/Desktop/HFT DETECT/model/features.py)
- [model/train.py](/C:/Users/rehan/OneDrive/Desktop/HFT DETECT/model/train.py)
- [model/train_live.py](/C:/Users/rehan/OneDrive/Desktop/HFT DETECT/model/train_live.py)
- [backend/live_market.py](/C:/Users/rehan/OneDrive/Desktop/HFT DETECT/backend/live_market.py)
- [backend/api.py](/C:/Users/rehan/OneDrive/Desktop/HFT DETECT/backend/api.py)
- [frontend/src/App.jsx](/C:/Users/rehan/OneDrive/Desktop/HFT DETECT/frontend/src/App.jsx)

## How Real Data Is Prepared

Run:

```bash
python scripts/fetch_coinbase_datasets.py
```

What it does:

- fetches recent public BTC-USD trades from Coinbase
- selects a low-volatility baseline window
- selects a faster real simulation window
- selects a higher-stress anomaly holdout window
- saves raw and processed CSV files

The training and holdout split is derived from real public market data, not fabricated rows.

## Training

Train the baseline model:

```bash
python model/train.py
```

Train the live Coinbase bootstrap model:

```bash
python model/train_live.py
```

## Holdout Scoring

Score the baseline, simulation, and anomaly holdout datasets:

```bash
python scripts/score_holdout.py
```

## Run Locally

Start the full app from the terminal with one command:

```powershell
.\.venv\Scripts\python.exe -m backend
```

The backend serves the built frontend too, so use:

- `http://127.0.0.1:8000`

## API Endpoints

- `GET /health`
- `GET /stream`
- `GET /status`
- `POST /reset`
- `GET /live/health`
- `GET /live/status`
- `GET /live/coinbase/health`
- `GET /live/coinbase/status`
- `GET /live/secondary/health`
- `GET /live/secondary/status`

## Docker

```bash
docker compose up --build
```

## CI

GitHub Actions workflow:

- [ci.yml](/C:/Users/rehan/OneDrive/Desktop/HFT DETECT/.github/workflows/ci.yml)

## Notes On Market Data Sources

The real historical and live datasets are built from Coinbase Exchange public market data:

- public historical trades from the Coinbase Exchange REST trade endpoint
- public live ticks from the Coinbase Exchange WebSocket ticker channel

Reference docs:

- [Coinbase Exchange Get product trades](https://docs.cdp.coinbase.com/exchange/reference/exchangerestapi_getproducttrades)
- [Coinbase Exchange WebSocket ticker channel](https://docs.cdp.coinbase.com/exchange/websocket-feed/channels)

## Current Intent

This setup now gives you:

- a real normal dataset for training
- a real faster dataset for simulation output
- a separate real stress dataset kept aside for testing

That matches the split you asked for without mixing the anomaly holdout into the default training flow.
