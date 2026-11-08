'use strict';
const $ = (id) => document.getElementById(id);
const money = (v) => Number(v).toLocaleString('en-US', {maximumFractionDigits: 2, minimumFractionDigits: 2});
const percent = (v) => `${(v * 100).toFixed(2)}%`;
let latestReport = null;
let pendingOrder = null;
function notify(message, error = false) {
  $('notice').textContent = message;
  $('notice').classList.toggle('error', error);
}
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail));
  return result;
}
async function busy(form, operation) {
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  try { await operation(); } catch (error) { notify(error.message, true); }
  finally { button.disabled = false; }
}
function dataLabel() {
  $('data-label').textContent = $('symbol').value === 'DEMO'
    ? 'DEMO uses synthetic daily bars, not actual security returns.' : 'Imported historical data. Verify price adjustments and data completeness.';
}
async function refreshSymbols(selected) {
  const {symbols} = await api('/api/datasets');
  for (const id of ['symbol', 'order-symbol']) {
    const previous = selected || $(id).value;
    $(id).replaceChildren(...symbols.map((symbol) => new Option(symbol, symbol)));
    if (symbols.includes(previous)) $(id).value = previous;
  }
  dataLabel();
}
const svgNS = 'http://www.w3.org/2000/svg';
function svgNode(name, attributes, text) {
  const node = document.createElementNS(svgNS, name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}
function chart(rows) {
  const width = 850, height = 310, left = 70, right = 15, top = 20, bottom = 35;
  let minimum = Infinity, maximum = -Infinity;
  for (const row of rows) {
    minimum = Math.min(minimum, row.equity, row.benchmark);
    maximum = Math.max(maximum, row.equity, row.benchmark);
  }
  const padding = (maximum - minimum || maximum * 0.01 || 1) * 0.12;
  minimum -= padding; maximum += padding;
  const x = (i) => left + i / Math.max(rows.length - 1, 1) * (width - left - right);
  const y = (v) => top + (maximum - v) / (maximum - minimum) * (height - top - bottom);
  const svg = svgNode('svg', {viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': 'Strategy and buy-and-hold benchmark equity curves'});
  for (let i = 0; i <= 4; i++) {
    const value = minimum + (maximum - minimum) * i / 4;
    svg.append(svgNode('line', {x1: left, x2: width - right, y1: y(value), y2: y(value), stroke: '#25313a', 'stroke-dasharray': '3 5'}));
    svg.append(svgNode('text', {x: left - 10, y: y(value) + 4, fill: '#82939f', 'font-size': 10, 'text-anchor': 'end'}, money(value)));
  }
  for (const [key, color] of [['benchmark', '#7e8e9c'], ['equity', '#9ee8bd']]) {
    const d = rows.map((row, i) => `${i ? 'L' : 'M'}${x(i).toFixed(2)},${y(row[key]).toFixed(2)}`).join(' ');
    svg.append(svgNode('path', {d, fill: 'none', stroke: color, 'stroke-width': key === 'equity' ? 2.3 : 1.5}));
  }
  for (const [i, anchor] of [[0, 'start'], [Math.floor((rows.length - 1) / 2), 'middle'], [rows.length - 1, 'end']]) {
    svg.append(svgNode('text', {x: x(i), y: height - 9, fill: '#82939f', 'font-size': 10, 'text-anchor': anchor}, rows[i].date));
  }
  $('chart').replaceChildren(svg);
}
function render(report) {
  latestReport = report;
  const m = report.metrics;
  $('total-return').textContent = percent(m.total_return);
  $('annual-return').textContent = percent(m.annualized_return);
  $('max-dd').textContent = percent(m.max_drawdown);
  $('sharpe').textContent = m.sharpe_ratio.toFixed(2);
  $('period').textContent = `${report.symbol} · ${m.bars} trading days`;
  $('trade-summary').textContent = `${m.trade_count} fills · Fees ${money(m.total_fees)} · Slippage ${money(m.total_slippage)}`;
  $('risk-summary').textContent = m.halt_date ? `Drawdown stop triggered on ${m.halt_date}` : `Average exposure ${percent(m.average_exposure)} · No drawdown stop`;
  chart(report.equity);
  const rows = report.trades.slice(-30).reverse().map((trade) => {
    const row = document.createElement('tr');
    const values = [trade.date, trade.side === 'buy' ? 'Buy' : 'Sell', trade.quantity.toFixed(4), money(trade.price), money(trade.fee), trade.realized_pnl === null ? '—' : money(trade.realized_pnl)];
    values.forEach((value, index) => {
      const cell = document.createElement('td'); cell.textContent = value;
      if (index === 1) cell.className = trade.side;
      row.append(cell);
    });
    return row;
  });
  if (!rows.length) {
    const row = document.createElement('tr'), cell = document.createElement('td');
    cell.colSpan = 6; cell.className = 'empty'; cell.textContent = 'No trades generated during this period'; row.append(cell); rows.push(row);
  }
  $('trades').replaceChildren(...rows);
  $('export').disabled = false;
  notify(`Backtest complete: ${report.symbol} · ${report.equity[0].date} to ${report.equity.at(-1).date}${report.data_kind === 'synthetic' ? ' · Synthetic data demo' : ''}`);
}
$('symbol').addEventListener('change', dataLabel);
$('backtest-form').addEventListener('submit', (event) => {
  event.preventDefault();
  busy(event.currentTarget, async () => {
    notify('Calculating signals, execution costs, and risk metrics…');
    const value = (id) => Number($(id).value);
    render(await api('/api/backtests', {
      symbol: $('symbol').value,
      strategy: {name: $('strategy').value, fast: value('fast'), slow: value('slow'), lookback: value('lookback'), entry_z: value('entry-z')},
      execution: {initial_cash: value('cash'), max_position: value('position') / 100,
        max_drawdown: value('drawdown') / 100, commission_bps: value('commission'),
        slippage_bps: value('slippage'), target_volatility: value('volatility') / 100},
    }));
  });
});
$('download-form').addEventListener('submit', (event) => {
  event.preventDefault();
  busy(event.currentTarget, async () => {
    notify('Downloading Yahoo market data. Please wait…');
    const result = await api('/api/data', {source: 'yahoo', symbol: $('download-symbol').value.trim(), start: $('start-date').value, end: $('end-date').value});
    await refreshSymbols(result.symbol);
    notify(`Imported ${result.symbol}: ${result.rows} rows, ${result.start} to ${result.end}`);
  });
});
$('csv-form').addEventListener('submit', (event) => {
  event.preventDefault();
  busy(event.currentTarget, async () => {
    const file = $('csv-file').files[0];
    if (file.size > 10_000_000) throw new Error('CSV files must not exceed 10 MB');
    const result = await api('/api/data/csv', {symbol: $('csv-symbol').value.trim(), csv: await file.text()});
    await refreshSymbols(result.symbol); notify(`Imported ${result.symbol}: ${result.rows} rows`);
  });
});
async function refreshAccount() {
  const account = await api('/api/paper/account');
  $('paper-equity').textContent = money(account.equity);
  $('paper-cash').textContent = money(account.cash);
  $('positions').textContent = account.positions.length
    ? account.positions.map((p) => `${p.symbol} · ${p.quantity.toFixed(4)} shares · Average cost ${money(p.average_cost)} · Valuation date ${p.mark_date}`).join('\n') : 'No open positions';
}
$('order-form').addEventListener('submit', (event) => {
  event.preventDefault();
  busy(event.currentTarget, async () => {
    const order = {symbol: $('order-symbol').value, side: $('side').value, quantity: Number($('quantity').value)};
    const fingerprint = JSON.stringify(order);
    // Reuse the ID after an uncertain network response to avoid duplicate fills.
    if (!pendingOrder || pendingOrder.fingerprint !== fingerprint) pendingOrder = {fingerprint, id: crypto.randomUUID()};
    const result = await api('/api/paper/orders', {...order, client_order_id: pendingOrder.id});
    pendingOrder = null;
    $('order-result').textContent = `${result.symbol} ${result.side === 'buy' ? 'Buy' : 'Sell'} ${result.quantity} shares at a simulated fill price of ${money(result.price)}. Reference date: ${result.price_date}.`;
    await refreshAccount(); notify('Local paper order filled and saved.');
  });
});
$('export').addEventListener('click', () => {
  if (!latestReport) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(latestReport, null, 2)], {type: 'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = `quantforge-${latestReport.symbol}.json`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
(async () => {
  try {
    await Promise.all([refreshSymbols(), refreshAccount()]);
    $('backtest-form').requestSubmit();
  } catch (error) { notify(error.message, true); }
})();
