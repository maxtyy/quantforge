# Validation record

Local environment: Python 3.12.3 on Linux. Exact dependencies are recorded in `requirements.lock.txt`.

- `pytest -q`: 35 tests passed. The third-party Starlette test client emits a deprecation notice about moving to httpx2; current tests work.
- `ruff check .` and `ruff format --check .`: passed.
- `quantforge demo`: completed a backtest on 756 synthetic daily bars and exported equity, fills, a JSON report, and input data.
- `python -m build`: source distribution and wheel built successfully, including dashboard assets.
- Chromium: default backtest, strategy switching, JSON download, paper buys and sells, CSV upload, and backtesting passed without JavaScript errors.
- Desktop at 1440 pixels and mobile at 390 pixels passed layout checks. A table overflow issue on narrow screens was fixed.
- A live Yahoo download attempt returned `YFRateLimitError` from the upstream service, so successful real-data downloading was not verified in this environment. The CLI returned a clear error; CSV and offline demo workflows were verified.

The dashboard, runtime messages, CLI help, API descriptions, and repository documentation are in English. The README screenshot is captured from the English dashboard.

GitHub Actions runs on Python 3.11, 3.12, and 3.13. The private repository is https://github.com/maxtyy/quantforge. Pushes trigger cloud validation; see the repository's Actions page for current results.
