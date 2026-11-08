# Research and execution assumptions

## Data and event ordering

1. Validate daily OHLCV and sort by date, with one record per day. Missing trading days are not filled automatically.
2. After the close on day t, calculate strategy signals and volatility using data available through t.
3. Shift target weights by one row and execute at the day t+1 open, adjusted for slippage.
4. Mark equity, exposure, and drawdown at the t+1 close, then determine whether to halt trading permanently.

The account holds cash until indicator windows are complete. Signals on the final day cannot execute without a subsequent bar. Positions are not forcibly closed at the end of a backtest: remaining holdings are marked at the final close, without hypothetical liquidation fees.

## Strategies

- `trend`: the target signal is 1 when the fast simple moving average exceeds the slow average, otherwise 0.
- `momentum`: the signal is 1 when the closing price return over `lookback` bars is positive, otherwise 0.
- `mean_reversion`: enter when the closing price's rolling Z-score is below `-entry_z`; exit when it reaches 0 or above. Rolling standard deviation uses the sample definition. A zero standard deviation produces no position.

All strategies are long only and return signals in [0, 1]. The configuration always requires `fast < slow`; strategies other than moving average trend do not use these two windows.

## Position sizing and costs

When target volatility is positive, annualized historical volatility is the sample standard deviation of the last `volatility_window` daily returns multiplied by `sqrt(252)`. The scaling factor is `min(target volatility / historical volatility, 1)`. Incomplete windows hold cash; a complete window with zero volatility uses a factor of 1. A target volatility of zero disables scaling.

Target weight = strategy signal × scaling factor × maximum position. This is a target at execution time, not a guarantee that exposure will stay within the same bound after prices move.

By default, rebalance when target weight and current opening exposure differ by at least 2 percentage points. A target of zero always permits an exit. Fill quantities account for trading costs to approximate the desired allocation after execution, with an explicit available-cash constraint. Fractional shares and full fills are assumed. There is no volume participation limit, minimum commission, or market-impact function.

Buy fill price = opening price × (1 + slippage bps / 10000). Sell fill price = opening price × (1 - slippage bps / 10000). Commission = quantity × fill price × commission bps / 10000.

Cost basis uses a moving weighted average. Buy commissions are included in cost basis; realized sell P&L also deducts sell commissions.

## Drawdown halt

Peak equity starts at initial cash. When closing equity / historical peak - 1 reaches the negative drawdown threshold, the account enters a halted state. It liquidates at the next available open and never reenters. If the trigger occurs on the final bar, the report retains the position that could not yet be liquidated.

The threshold is a trigger, **not a maximum-loss guarantee**. Overnight gaps, trading costs, and daily monitoring can produce a realized drawdown beyond the threshold.

## Performance metrics

- Total return: final equity / initial cash - 1.
- Annualized return: (final equity / initial cash)^(252 / return observations) - 1.
- Daily returns: changes between consecutive daily closing equity values; the first day is excluded.
- Annualized volatility: population standard deviation of daily returns × sqrt(252).
- Sharpe ratio: mean daily return × 252 / annualized volatility. The risk-free rate is zero; near-zero volatility returns a ratio of 0.
- Maximum drawdown: the largest decline from the running equity peak, reported as a positive number.
- Sell-fill win rate: profitable sell fills / all sell fills. This is not a round-trip trade win rate; it is null if there are no sells.
- Buy-and-hold benchmark: buy at the first closing price, then mark at subsequent closes without costs. This is a price reference, not a competing strategy under identical execution conditions.

The default annualization assumes 252 observations per year, appropriate for daily stock research. Annualized results over short periods can be unstable. No parameter optimization or out-of-sample validation is included, so repeated tuning on the same data is not independent evidence.

## Reproducibility

Demo data uses random seed 42, a fixed end date of 2025-12-31, and 756 business days. A business-day index is not an exchange calendar. Reports retain strategy and execution parameters; the CLI demo also saves its synthetic input data. For real research, archive the input CSV, dependency versions, and Git commit separately.
