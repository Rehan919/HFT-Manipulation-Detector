from backend.live_market import normalize_trade_message


def test_normalize_rest_trade_message() -> None:
    payload = {
        "time": "2026-04-07T10:00:00Z",
        "price": "81234.12",
        "size": "0.015",
        "trade_id": 123,
        "side": "buy",
    }

    normalized = normalize_trade_message(payload, "BTC-USD", source="rest")

    assert normalized is not None
    assert normalized["price"] == 81234.12
    assert normalized["volume"] == 0.015
    assert normalized["trade_id"] == 123


def test_normalize_websocket_ticker_message() -> None:
    payload = {
        "type": "ticker",
        "product_id": "BTC-USD",
        "time": "2026-04-07T10:00:01Z",
        "price": "81240.00",
        "last_size": "0.005",
        "trade_id": 124,
        "best_bid": "81239.99",
        "best_ask": "81240.01",
        "volume_24h": "1234.56",
    }

    normalized = normalize_trade_message(payload, "BTC-USD", source="websocket")

    assert normalized is not None
    assert normalized["best_bid"] == 81239.99
    assert normalized["best_ask"] == 81240.01
    assert normalized["volume_24h"] == 1234.56
