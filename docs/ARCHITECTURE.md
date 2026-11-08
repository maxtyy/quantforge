# Architecture and extensions

```text
CSV / Yahoo / Synthetic
          |
     data.py (validation)
          |
  strategies.py (closing targets)
          |
    engine.py (next-open fills + risk controls)
          |
     Metrics / Equity / Trades / Reports
          |
       CLI / API / Web

Last closing reference price -> paper.py -> SQLite accounts and orders
```

```text
src/quantforge/
  data.py          Data sources, symbol checks, and OHLCV validation
  strategies.py    Strategy configuration and target signals
  engine.py        Backtesting, risk controls, performance, and reports
  paper.py         Local fill simulation and transactional accounting
  api.py           FastAPI application factory
  cli.py           Command-line entry points
  web/             Dashboard with no frontend build or external CDN dependency
tests/             Core and integration tests
docs/              Methodology, architecture, and validation
.github/workflows/ GitHub CI
```

## Adding strategies

Extend strategy-name validation in `StrategyConfig` and implement the new strategy in `target_weights()`. Return a Series aligned with the input index, with values in [0, 1]. Calculations must use only current and past data. Do not shift signals inside the strategy: the execution engine applies `shift(1)`. Update CLI and dashboard options and add a future-data perturbation test.

## Adding data sources

New sources must return a DataFrame accepted by `validate_bars()`. OHLC prices must use consistent adjustments. Do not silently repair duplicate dates, invalid prices, or missing values. Exchange calendars, corporate actions, and trading halts belong in an explicit market adapter.

## Paper accounts and concurrency

Each request uses a separate SQLite connection. Order submission runs inside a `BEGIN IMMEDIATE` transaction: check idempotency, read account and position state, validate risk constraints, then write atomically. Account reads also use a transaction for a consistent snapshot. Concurrent submissions with the same order ID produce only one fill.

Historical CSV files use a temporary file followed by atomic replacement, so backtests never read a partial write. Importing a CSV replaces any dataset with the same symbol; previously generated reports are not updated. Account fill records retain the actual reference date and execution price.

The single-account design is intended for local research. Multiuser deployments need account isolation, database migrations, authentication, background jobs, and observability. The local API is not ready for direct public exposure.

## Research and paper trading boundaries

Backtests maintain their own daily equity. The paper account independently persists manually submitted orders. They do not synchronize automatically, and no scheduler converts strategy signals into paper orders. Paper valuations use the most recent simulated fill reference prices and cannot replace live portfolio valuation.

A live broker integration requires order lifecycle management, fill events, cancellations, retries, trading-session rules, reconciliation, and broker-side risk controls. No such adapter is included.
