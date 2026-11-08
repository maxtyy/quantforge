from concurrent.futures import ThreadPoolExecutor

import pytest

from quantforge.paper import PaperBroker


def place(broker, order_id="buy-1", **kwargs):
    return broker.submit(
        **{
            "client_order_id": order_id,
            "symbol": "DEMO",
            "side": "buy",
            "quantity": 10,
            "reference_price": 100,
            "price_date": "2025-12-31",
            **kwargs,
        }
    )


def test_round_trip_and_persistence(tmp_path):
    path = tmp_path / "account.sqlite3"
    broker = PaperBroker(path)
    buy = place(broker)
    reopened = PaperBroker(path)
    assert reopened.account()["positions"][0]["quantity"] == 10
    sell = place(reopened, "sell-1", side="sell", reference_price=110)
    account = reopened.account()
    assert account["positions"] == []
    expected_pnl = 10 * (sell["price"] - buy["price"]) - buy["fee"] - sell["fee"]
    assert sell["realized_pnl"] == pytest.approx(expected_pnl)
    assert account["cash"] == pytest.approx(100_000 + expected_pnl)


def test_duplicate_order_is_idempotent_even_if_quote_changes(tmp_path):
    broker = PaperBroker(tmp_path / "paper.sqlite3")
    first = place(broker)
    assert place(broker, reference_price=120) == first
    assert len(broker.account()["orders"]) == 1
    with pytest.raises(ValueError, match="different orders"):
        place(broker, quantity=11)


def test_concurrent_retries_fill_once(tmp_path):
    broker = PaperBroker(tmp_path / "paper.sqlite3")
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: place(broker), range(12)))
    assert all(result == results[0] for result in results)
    assert broker.account()["positions"][0]["quantity"] == 10


@pytest.mark.parametrize(
    "kwargs",
    [
        {"side": "sell"},
        {"quantity": -1},
        {"quantity": float("nan")},
        {"quantity": 300},
        {"reference_price": float("inf")},
        {"symbol": "../secret"},
    ],
)
def test_invalid_orders_do_not_mutate_account(tmp_path, kwargs):
    broker = PaperBroker(tmp_path / "paper.sqlite3")
    before = broker.account()
    with pytest.raises(ValueError):
        place(broker, **kwargs)
    assert broker.account() == before


def test_insufficient_cash_and_position_cap(tmp_path):
    broker = PaperBroker(tmp_path / "paper.sqlite3", initial_cash=1000)
    with pytest.raises(ValueError, match="Insufficient available cash"):
        place(broker, quantity=20)
    with pytest.raises(ValueError, match="95%"):
        place(broker, quantity=9.6)
    assert broker.account()["cash"] == 1000
