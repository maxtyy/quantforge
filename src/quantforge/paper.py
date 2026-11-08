"""SQLite local simulator: atomic fills, cash accounting, and retry-safe orders."""

import json
import math
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .data import validate_symbol


class PaperBroker:
    def __init__(self, database: str | Path, initial_cash: float = 100_000):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        if not math.isfinite(initial_cash) or initial_cash <= 0:
            raise ValueError("Initial cash must be positive")
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS account (
                    id INTEGER PRIMARY KEY CHECK(id=1), cash REAL NOT NULL,
                    initial_cash REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY, quantity REAL NOT NULL,
                    average_cost REAL NOT NULL, mark REAL NOT NULL, mark_date TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS orders (
                    client_order_id TEXT PRIMARY KEY, request TEXT NOT NULL,
                    result TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            """)
            db.execute(
                "INSERT OR IGNORE INTO account VALUES (1, ?, ?)", (initial_cash, initial_cash)
            )

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def account(self) -> dict:
        with self.connection() as db:
            db.execute("BEGIN")
            account = dict(db.execute("SELECT * FROM account WHERE id=1").fetchone())
            positions = [dict(row) for row in db.execute("SELECT * FROM positions ORDER BY symbol")]
            orders = [
                json.loads(row[0])
                for row in db.execute("SELECT result FROM orders ORDER BY rowid DESC LIMIT 100")
            ]
        equity = account["cash"] + sum(p["quantity"] * p["mark"] for p in positions)
        return {
            "cash": account["cash"],
            "initial_cash": account["initial_cash"],
            "equity": equity,
            "positions": positions,
            "orders": orders,
            "valuation": "Valued at each position's most recent simulated fill reference price, not live market prices",
        }

    def submit(
        self,
        *,
        client_order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        reference_price: float,
        price_date: str,
    ) -> dict:
        symbol = validate_symbol(symbol)
        if not client_order_id or len(client_order_id) > 80:
            raise ValueError("An idempotent order ID of at most 80 characters is required")
        if side not in {"buy", "sell"}:
            raise ValueError("Side must be buy or sell")
        if (
            not math.isfinite(quantity)
            or not math.isfinite(reference_price)
            or quantity <= 0
            or reference_price <= 0
        ):
            raise ValueError("Quantity and reference price must be finite positive numbers")
        request = json.dumps({"symbol": symbol, "side": side, "quantity": quantity}, sort_keys=True)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT request, result FROM orders WHERE client_order_id=?", (client_order_id,)
            ).fetchone()
            if previous:
                if previous["request"] != request:
                    raise ValueError("The same order ID cannot be used for different orders")
                return json.loads(previous["result"])
            account = db.execute("SELECT cash FROM account WHERE id=1").fetchone()
            position = db.execute("SELECT * FROM positions WHERE symbol=?", (symbol,)).fetchone()
            held = position["quantity"] if position else 0.0
            basis = position["average_cost"] if position else 0.0
            price = reference_price * (1.0005 if side == "buy" else 0.9995)
            notional = price * quantity
            if not math.isfinite(notional) or notional > 25_000:
                raise ValueError("The maximum simulated order notional is 25000")
            fee = notional * 0.0005
            realized_pnl = None
            if side == "buy":
                if notional + fee > account["cash"]:
                    raise ValueError("Insufficient available cash")
                cash = account["cash"] - notional - fee
                new_quantity = held + quantity
                average_cost = (basis * held + notional + fee) / new_quantity
                other_value = db.execute(
                    "SELECT COALESCE(SUM(quantity * mark), 0) FROM positions WHERE symbol != ?",
                    (symbol,),
                ).fetchone()[0]
                equity = cash + other_value + new_quantity * reference_price
                if new_quantity * reference_price > equity * 0.95:
                    raise ValueError(
                        "A single position cannot exceed 95% of simulated account equity"
                    )
            else:
                if quantity > held:
                    raise ValueError(
                        "Insufficient holdings to sell; the simulated account does not support short selling"
                    )
                cash = account["cash"] + notional - fee
                new_quantity, average_cost = held - quantity, basis
                realized_pnl = notional - fee - basis * quantity
            db.execute("UPDATE account SET cash=? WHERE id=1", (cash,))
            if new_quantity > 1e-10:
                db.execute(
                    "INSERT OR REPLACE INTO positions VALUES (?, ?, ?, ?, ?)",
                    (symbol, new_quantity, average_cost, reference_price, price_date),
                )
            else:
                db.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
            result = {
                "client_order_id": client_order_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "fee": fee,
                "status": "filled",
                "mode": "local_simulation",
                "price_date": price_date,
                "realized_pnl": realized_pnl,
            }
            db.execute(
                "INSERT INTO orders (client_order_id, request, result) VALUES (?, ?, ?)",
                (client_order_id, request, json.dumps(result, allow_nan=False)),
            )
            return result
