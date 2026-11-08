# QuantForge

一个可本地运行的 Python 量化研究项目：从行情导入、策略信号、含成本回测，到风控、报告导出和持久化模拟交易。配有中文网页研究台和 REST API，无需 API 密钥即可运行完整演示。

**当前范围：股票 / ETF 日线、单标的、只做多、无杠杆、本地模拟成交。** 不连接实盘券商。DEMO 使用明确标注的合成行情，不代表任何真实证券收益。

![QuantForge 中文研究台](docs/dashboard.png)

## 快速开始

需要 Python 3.11+。在项目根目录运行：

```bash
python3 -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
quantforge demo
quantforge serve
```

打开 **http://127.0.0.1:8000**。API 文档位于 **http://127.0.0.1:8000/docs**。网页首次打开会自动执行演示回测。

如果系统的软件源未配置，可显式使用 `python -m pip install --index-url https://pypi.org/simple -e '.[dev]'`。

## 已实现功能

| 模块 | 能力 |
| --- | --- |
| 行情 | 固定随机种子的合成日线、标准 CSV 导入、Yahoo 复权日线下载 |
| 校验 | 拒绝重复日期、缺失字段、NaN、无穷值、负价格及非法 OHLC |
| 策略 | 双均线趋势、时间序列动量、带持仓状态的均值回归 |
| 回测 | 当日收盘信号 → 下一交易日开盘成交，手续费、滑点、零杠杆资金约束 |
| 风控 | 单标的仓位上限、历史波动率缩放、收盘回撤触发后下一开盘清仓 |
| 绩效 | 收益、年化收益、年化波动率、夏普、最大回撤、卖出成交胜率、成本 |
| 报告 | 权益曲线 CSV、成交 CSV、包含参数及逐日记录的 JSON |
| 模拟交易 | SQLite 持久化、事务内风控、幂等订单、现金与持仓成本记账 |
| 网页 | 中文研究台、参数编辑、资金曲线、交易记录、导入、导出、模拟下单 |
| 工程 | Python 包、CLI、自动化测试、Ruff、GitHub Actions、MIT 许可 |

## 命令行工作流

```bash
# 离线演示，报告包含对应的合成行情 CSV
quantforge demo --output reports/demo

# 下载行情：结束日期不包含当天；网络/数据服务可用性由 Yahoo 决定
quantforge download SPY --start 2020-01-01 --end 2025-12-31

# 回测下载的行情
quantforge backtest data/datasets/SPY.csv --strategy trend --cash 100000
quantforge backtest data/datasets/SPY.csv --strategy momentum --output reports/momentum
quantforge backtest data/datasets/SPY.csv --strategy mean_reversion --output reports/reversion

# 使用不同端口运行研究台
quantforge serve --port 8080
```

CSV 格式：日期应为 `YYYY-MM-DD`，价格应处于一致的复权口径，不要混用未复权 OHLC 和复权收盘价。

```csv
date,open,high,low,close,volume
2025-01-02,100,102,99,101,1000000
2025-01-03,101,104,100,103,1200000
```

项目不自动转换币种。初始资金、价格和收益金额必须采用同一种货币；不同币种标的不应放进同一模拟账户。

## Python 研究接口

```python
from quantforge.data import demo_bars
from quantforge.engine import BacktestConfig, run_backtest
from quantforge.strategies import StrategyConfig

result = run_backtest(
    demo_bars(),
    StrategyConfig(name="trend", fast=20, slow=60),
    BacktestConfig(
        initial_cash=100_000,
        commission_bps=5,
        slippage_bps=5,
        max_position=0.95,
        target_volatility=0.15,
        max_drawdown=0.20,
    ),
)
print(result.metrics)
result.export("reports/custom")
```

策略参数含义与成交模型见 [研究与执行假设](docs/METHODOLOGY.md)。项目结构和扩展方式见 [架构说明](docs/ARCHITECTURE.md)。

## 模拟交易规则

网页模拟订单以对应数据集的**最后一个收盘价**为参考，买入加 5 bps 滑点、卖出减 5 bps 滑点，另收 5 bps 手续费。它是本地成交模拟器，不是实时撮合系统，也不会向券商发送订单。

- 初始资金 100,000；单笔成交金额上限 25,000；单标的持仓上限 95%。
- 不允许透支、卖空或提交非正数数量；支持小数份额。
- `client_order_id` 提供幂等性；同一 ID 重试不会重复成交，不同参数复用同一 ID 会被拒绝。
- 账户权益使用各持仓最近一次模拟成交的参考价格，接口返回其日期；不是自动刷新行情后的市值。
- 数据位于 `data/paper.sqlite3`，行情位于 `data/datasets/`。可通过环境变量 `QUANTFORGE_DATA_DIR` 更换目录；`.env` 文件不会自动加载。
- 本地账户可跨会话保留。需要独立研究账户时，使用不同的数据目录。

```bash
QUANTFORGE_DATA_DIR=./data/experiment-2 quantforge serve --port 8001
```

## API

| 方法与路径 | 用途 |
| --- | --- |
| `GET /api/health` | 健康状态 |
| `GET /api/datasets` | 已导入标的 |
| `POST /api/data` | 导入演示数据或 Yahoo 行情 |
| `POST /api/data/csv` | 导入 CSV 字符串 |
| `POST /api/backtests` | 回测，返回参数、权益、成交及指标 |
| `GET /api/paper/account` | 账户、持仓、最近 100 笔订单 |
| `POST /api/paper/orders` | 提交本地模拟订单 |

```bash
curl http://127.0.0.1:8000/api/backtests \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"DEMO","strategy":{"name":"trend","fast":20,"slow":60}}'
```

服务默认只绑定 `127.0.0.1`，没有用户认证，面向单用户本机使用。部署到多人或公网环境前需要实现身份认证、访问控制、TLS 和请求资源限制。

## 开发与验证

```bash
ruff check .
ruff format --check .
pytest -q
python -m build
```

测试覆盖信号与成交时序、未来数据扰动不改变过去结果、成本与资产恒等式、回撤清仓、无交易场景、输入校验、持仓与现金约束、重试及并发幂等性、API 数据导入到模拟成交的完整链路。CI 配置为 Python 3.11 / 3.12 / 3.13，并导出演示报告作为构建附件。

`requirements.lock.txt` 记录已验证开发环境的精确依赖；通常按 `pyproject.toml` 安装即可。

## 创建 GitHub 远程仓库

本项目可以直接作为独立 GitHub 仓库。安装 [GitHub CLI](https://cli.github.com/) 后，在项目根目录执行：

```bash
gh auth login --hostname github.com --git-protocol https --web
gh repo create quantforge --private --source=. --remote=origin --push \
  --description 'Python quantitative research, cost-aware backtesting and local paper trading'
```

默认使用私有仓库；需要公开源码时可自行将 `--private` 替换为 `--public`。不要提交本地账户数据库、真实密钥或受许可限制的行情数据；项目已将 `data/`、`reports/` 和 `.env` 加入忽略规则。

## 使用边界

目前没有多标的组合优化、滚动样本外评估、交易日历校验、涨跌停/停牌处理、A 股整手与 T+1 约束、真实券商适配或生产级运维。CSV 可导入不同市场，但实际成交规则需要按市场补充。历史回测和合成演示均不能证明未来盈利。

MIT License。欢迎通过 Issue 和 Pull Request 改进。
