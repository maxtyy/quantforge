"""Local API and static research dashboard. Bind only to loopback by default."""

import io
import os
from pathlib import Path
from typing import Literal
from uuid import uuid4

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .data import SYMBOL_PATTERN, demo_bars, read_csv, validate_symbol, yahoo_bars
from .engine import BacktestConfig, run_backtest
from .paper import PaperBroker
from .strategies import StrategyConfig


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class DataRequest(StrictModel):
    source: Literal["demo", "yahoo"] = "demo"
    symbol: str = Field(default="DEMO", pattern=SYMBOL_PATTERN, max_length=20)
    start: str = "2020-01-01"
    end: str = "2025-12-31"


class CsvRequest(StrictModel):
    symbol: str = Field(pattern=SYMBOL_PATTERN, max_length=20)
    csv: str = Field(max_length=10_000_000)


class BacktestRequest(StrictModel):
    symbol: str = "DEMO"
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    execution: BacktestConfig = Field(default_factory=BacktestConfig)


class OrderRequest(StrictModel):
    client_order_id: str = Field(min_length=1, max_length=80)
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0, le=1_000_000)


def create_app(data_dir: str | Path | None = None) -> FastAPI:
    root = Path(data_dir or os.environ.get("QUANTFORGE_DATA_DIR", "data"))
    root.mkdir(parents=True, exist_ok=True)
    datasets = root / "datasets"
    datasets.mkdir(exist_ok=True)
    broker = PaperBroker(root / "paper.sqlite3")
    app = FastAPI(
        title="QuantForge",
        version="0.1.0",
        description="Local quantitative research and paper trading",
    )
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"]
    )

    @app.exception_handler(ValueError)
    async def invalid_value(request, exc):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    def load(symbol: str):
        symbol = validate_symbol(symbol)
        path = datasets / f"{symbol}.csv"
        if not path.exists():
            if symbol == "DEMO":
                return demo_bars()
            raise HTTPException(404, "Import market data for this symbol first")
        return read_csv(path)

    def save(symbol: str, bars: pd.DataFrame):
        symbol = validate_symbol(symbol)
        # Atomic rename ensures readers never see partial CSV content.
        temporary = datasets / f".{uuid4().hex}.tmp"
        try:
            bars.to_csv(temporary)
            temporary.replace(datasets / f"{symbol}.csv")
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "symbol": symbol,
            "rows": len(bars),
            "start": str(bars.index[0].date()),
            "end": str(bars.index[-1].date()),
            "last_close": float(bars.close.iloc[-1]),
        }

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": "research_and_local_simulation", "version": "0.1.0"}

    @app.get("/api/datasets")
    def list_datasets():
        return {"symbols": sorted({"DEMO"} | {p.stem for p in datasets.glob("*.csv")})}

    @app.post("/api/data")
    def import_data(body: DataRequest):
        if body.source == "demo":
            return save("DEMO", demo_bars())
        if validate_symbol(body.symbol) == "DEMO":
            raise ValueError("DEMO is reserved for synthetic data; use a real security symbol")
        return save(body.symbol, yahoo_bars(body.symbol, body.start, body.end))

    @app.post("/api/data/csv")
    def import_csv(body: CsvRequest):
        if validate_symbol(body.symbol) == "DEMO":
            raise ValueError("DEMO is reserved for synthetic data")
        return save(body.symbol, read_csv(io.StringIO(body.csv)))

    @app.post("/api/backtests")
    def backtest(body: BacktestRequest):
        result = run_backtest(load(body.symbol), body.strategy, body.execution).payload()
        result["symbol"] = validate_symbol(body.symbol)
        result["data_kind"] = "synthetic" if body.symbol.upper() == "DEMO" else "imported"
        return result

    @app.get("/api/paper/account")
    def account():
        return broker.account()

    @app.post("/api/paper/orders")
    def order(body: OrderRequest):
        bars = load(body.symbol)
        return broker.submit(
            **body.model_dump(),
            reference_price=float(bars.close.iloc[-1]),
            price_date=str(bars.index[-1].date()),
        )

    web = Path(__file__).parent / "web"
    app.mount("/static", StaticFiles(directory=web), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(web / "index.html")

    return app
