import pytest
from fastapi.testclient import TestClient

from quantforge.api import create_app
from quantforge.data import demo_bars


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        yield client


def test_dashboard_and_demo_backtest(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/health").json()["status"] == "ok"
    response = client.post("/api/backtests", json={})
    assert response.status_code == 200
    result = response.json()
    assert result["data_kind"] == "synthetic"
    assert result["metrics"]["bars"] == 756
    assert len(result["equity"]) == 756


def test_csv_import_backtest_and_paper_order(client):
    csv = demo_bars(100).to_csv()
    response = client.post("/api/data/csv", json={"symbol": "TEST", "csv": csv})
    assert response.status_code == 200
    assert "TEST" in client.get("/api/datasets").json()["symbols"]
    assert client.post("/api/backtests", json={"symbol": "TEST"}).status_code == 200
    order = {"client_order_id": "api-1", "symbol": "TEST", "side": "buy", "quantity": 1}
    first = client.post("/api/paper/orders", json=order)
    assert first.status_code == 200
    assert client.post("/api/paper/orders", json=order).json() == first.json()
    assert len(client.get("/api/paper/account").json()["orders"]) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"symbol": "../bad"},
        {"strategy": {"fast": 80, "slow": 20}},
        {"execution": {"max_position": 1.5}},
        {"execution": {"commission_bps": -1}},
        {"unknown": True},
    ],
)
def test_invalid_requests_return_client_error(client, body):
    assert client.post("/api/backtests", json=body).status_code in {400, 422}


def test_missing_symbol_and_reserved_demo(client):
    assert client.post("/api/backtests", json={"symbol": "MISSING"}).status_code == 404
    assert (
        client.post(
            "/api/data/csv", json={"symbol": "DEMO", "csv": demo_bars(5).to_csv()}
        ).status_code
        == 400
    )


def test_untrusted_host_is_rejected(client):
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400
