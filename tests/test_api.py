from fastapi.testclient import TestClient

from backend.api import app


def test_health_endpoint_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"


def test_head_endpoints_return_success() -> None:
    with TestClient(app) as client:
        root_response = client.head("/")
        health_response = client.head("/health")
    assert root_response.status_code == 200
    assert health_response.status_code == 200
