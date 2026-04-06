import { useMemo, useState } from 'react';
import Layout from '../components/Layout.jsx';
import { useTradesData } from '../lib/data.js';

function formatTs(value) {
  if (!value) return '暂无';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('zh-CN', { hour12: false });
}

function formatNum(value, digits = 4) {
  const num = Number(value);
  if (!Number.isFinite(num)) return '—';
  return num.toFixed(digits);
}

function formatMoney(value, digits = 2) {
  const num = Number(value);
  if (!Number.isFinite(num)) return '—';
  return `$${num.toFixed(digits)}`;
}

function inferSide(trade) {
  const side = String(trade?.side || trade?.direction || '').toUpperCase();
  if (side) return side;
  const isBuy = trade?.is_buy;
  if (isBuy === true) return 'BUY';
  if (isBuy === false) return 'SELL';
  return '—';
}

function inferAction(trade) {
  const action = String(trade?.action || trade?.type || trade?.event_type || '').toLowerCase();
  if (action.includes('open') || action.includes('entry')) return '开仓';
  if (action.includes('close') || action.includes('exit')) return '平仓';
  return trade?.reduce_only ? '平仓' : '开仓';
}

function inferPositionSide(trade) {
  const value = String(trade?.position_side || trade?.raw?.position_side || '').toUpperCase();
  if (value.includes('LONG')) return 'LONG';
  if (value.includes('SHORT')) return 'SHORT';
  return '—';
}

function isWithinRange(ts, range) {
  if (range === 'ALL') return true;
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return true;
  const now = Date.now();
  const diff = now - d.getTime();
  const dayMs = 24 * 60 * 60 * 1000;
  if (range === '1D') return diff <= dayMs;
  if (range === '7D') return diff <= 7 * dayMs;
  if (range === '30D') return diff <= 30 * dayMs;
  return true;
}

export default function TradesPage() {
  const { data, loading, error } = useTradesData();
  const [symbolFilter, setSymbolFilter] = useState('ALL');
  const [actionFilter, setActionFilter] = useState('ALL');
  const [rangeFilter, setRangeFilter] = useState('ALL');
  const [expandedTradeKey, setExpandedTradeKey] = useState(null);

  const trades = data?.trades || [];
  const symbolOptions = useMemo(
    () => ['ALL', ...Array.from(new Set(trades.map((trade) => trade?.symbol || trade?.coin).filter(Boolean)))],
    [trades]
  );

  const normalizedTrades = useMemo(() => trades.map((trade, idx) => {
    const action = inferAction(trade);
    const side = inferSide(trade);
    const positionSide = inferPositionSide(trade);
    const symbol = trade?.symbol || trade?.coin || '—';
    const size = trade?.size ?? trade?.sz ?? trade?.qty;
    const price = trade?.price ?? trade?.avg_px ?? trade?.avgPx ?? trade?.entry_price ?? trade?.exit_price;
    const fee = trade?.fee;
    const notional = trade?.notional ?? trade?.value ?? (Number(size) && Number(price) ? Number(size) * Number(price) : null);
    const pnl = trade?.realized_pnl ?? trade?.pnl ?? trade?.closed_pnl;
    const ts = trade?.timestamp || trade?.executed_at || trade?.created_at || trade?.time || trade?.closed_at || trade?.opened_at;
    const key = `${symbol}-${trade?.trade_id || trade?.hash || ts || idx}-${idx}`;
    return {
      raw: trade,
      key,
      idx,
      action,
      side,
      positionSide,
      symbol,
      size,
      price,
      fee,
      notional,
      pnl,
      ts,
    };
  }), [trades]);

  const filteredTrades = useMemo(() => normalizedTrades.filter((trade) => {
    if (symbolFilter !== 'ALL' && trade.symbol !== symbolFilter) return false;
    if (actionFilter !== 'ALL' && trade.action !== actionFilter) return false;
    if (!isWithinRange(trade.ts, rangeFilter)) return false;
    return true;
  }), [normalizedTrades, symbolFilter, actionFilter, rangeFilter]);

  const totalNotional = filteredTrades.reduce((sum, trade) => sum + (Number(trade.notional) || 0), 0);
  const totalPnl = filteredTrades.reduce((sum, trade) => sum + (Number(trade.pnl) || 0), 0);
  const totalFee = filteredTrades.reduce((sum, trade) => sum + (Number(trade.fee) || 0), 0);
  const openCount = filteredTrades.filter((trade) => trade.action === '开仓').length;
  const closeCount = filteredTrades.filter((trade) => trade.action === '平仓').length;

  const symbolSummaries = useMemo(() => {
    const map = new Map();
    filteredTrades.forEach((trade) => {
      const current = map.get(trade.symbol) || {
        symbol: trade.symbol,
        count: 0,
        openCount: 0,
        closeCount: 0,
        notional: 0,
        fee: 0,
        pnl: 0,
      };
      current.count += 1;
      if (trade.action === '开仓') current.openCount += 1;
      if (trade.action === '平仓') current.closeCount += 1;
      current.notional += Number(trade.notional) || 0;
      current.fee += Number(trade.fee) || 0;
      current.pnl += Number(trade.pnl) || 0;
      map.set(trade.symbol, current);
    });
    return Array.from(map.values()).sort((a, b) => b.notional - a.notional);
  }, [filteredTrades]);

  if (loading) {
    return <div className="loading-screen">交易记录加载中...</div>;
  }

  if (error || !data) {
    return <div className="loading-screen error">交易记录加载失败</div>;
  }

  return (
    <Layout>
      <section className="dashboard-hero">
        <div>
          <div className="dashboard-kicker">LuckyNiuMa Trades</div>
          <h2 className="dashboard-title">交易记录</h2>
          <p className="dashboard-subtitle">
            查看机器人历史开仓、平仓记录。页面数据来自 <code>/data-export/trades.json</code>。
          </p>
        </div>
        <div className="dashboard-hero-meta">
          <div><span>记录数</span><strong>{filteredTrades.length}</strong></div>
          <div><span>更新时间</span><strong>{formatTs(data?.updated_at)}</strong></div>
        </div>
      </section>

      <div className="stats">
        <div className="stat-card"><div className="stat-label">总记录</div><div className="stat-value">{filteredTrades.length}</div></div>
        <div className="stat-card"><div className="stat-label">开仓次数</div><div className="stat-value blue">{openCount}</div></div>
        <div className="stat-card"><div className="stat-label">平仓次数</div><div className="stat-value green">{closeCount}</div></div>
        <div className="stat-card"><div className="stat-label">累计成交额</div><div className="stat-value">{formatMoney(totalNotional, 2)}</div></div>
        <div className="stat-card"><div className="stat-label">累计手续费</div><div className="stat-value">{formatMoney(totalFee, 4)}</div></div>
        <div className="stat-card"><div className="stat-label">累计已实现盈亏</div><div className={`stat-value ${totalPnl >= 0 ? 'green' : 'red'}`}>{formatMoney(totalPnl, 2)}</div></div>
      </div>

      <section className="dashboard-panel trades-panel">
        <div className="panel-header">
          <h3>按标的汇总</h3>
          <span className="panel-badge">{symbolSummaries.length} 个标的</span>
        </div>
        {symbolSummaries.length ? (
          <div className="symbol-summary-grid">
            {symbolSummaries.map((item) => (
              <div className="symbol-summary-card" key={item.symbol}>
                <div className="symbol-summary-top">
                  <strong>{item.symbol}</strong>
                  <span>{item.count} 笔</span>
                </div>
                <div className="symbol-summary-metrics">
                  <div><span>开仓</span><strong>{item.openCount}</strong></div>
                  <div><span>平仓</span><strong>{item.closeCount}</strong></div>
                  <div><span>成交额</span><strong>{formatMoney(item.notional, 2)}</strong></div>
                  <div><span>手续费</span><strong>{formatMoney(item.fee, 4)}</strong></div>
                  <div><span>已实现盈亏</span><strong className={item.pnl >= 0 ? 'profit' : 'loss'}>{formatMoney(item.pnl, 2)}</strong></div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">当前筛选条件下没有可展示的标的汇总</div>
        )}
      </section>

      <section className="dashboard-panel trades-panel">
        <div className="panel-header">
          <h3>开仓 / 平仓明细</h3>
          <span className="panel-badge">{filteredTrades.length} 条</span>
        </div>

        <div className="trades-filters">
          <label>
            <span>标的</span>
            <select value={symbolFilter} onChange={(e) => setSymbolFilter(e.target.value)}>
              {symbolOptions.map((symbol) => <option value={symbol} key={symbol}>{symbol === 'ALL' ? '全部' : symbol}</option>)}
            </select>
          </label>
          <label>
            <span>动作</span>
            <select value={actionFilter} onChange={(e) => setActionFilter(e.target.value)}>
              <option value="ALL">全部</option>
              <option value="开仓">开仓</option>
              <option value="平仓">平仓</option>
            </select>
          </label>
          <label>
            <span>时间范围</span>
            <select value={rangeFilter} onChange={(e) => setRangeFilter(e.target.value)}>
              <option value="ALL">全部</option>
              <option value="1D">近 24 小时</option>
              <option value="7D">近 7 天</option>
              <option value="30D">近 30 天</option>
            </select>
          </label>
        </div>

        {filteredTrades.length ? (
          <div className="trades-table-wrap">
            <table className="trades-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>标的</th>
                  <th>动作</th>
                  <th>仓位方向</th>
                  <th>成交方向</th>
                  <th>数量</th>
                  <th>价格</th>
                  <th>成交额</th>
                  <th>手续费</th>
                  <th>盈亏</th>
                </tr>
              </thead>
              <tbody>
                {filteredTrades.map((trade) => {
                  const expanded = expandedTradeKey === trade.key;
                  return (
                    <>
                      <tr key={trade.key} className="trade-row" onClick={() => setExpandedTradeKey(expanded ? null : trade.key)}>
                        <td>{formatTs(trade.ts)}</td>
                        <td className="coin">{trade.symbol}</td>
                        <td>
                          <span className={`trade-chip ${trade.action === '开仓' ? 'open' : 'close'}`}>{trade.action}</span>
                        </td>
                        <td>
                          <span className={`position-chip ${trade.positionSide === 'LONG' ? 'long' : trade.positionSide === 'SHORT' ? 'short' : ''}`}>{trade.positionSide}</span>
                        </td>
                        <td>{trade.side}</td>
                        <td>{formatNum(trade.size, 6)}</td>
                        <td>{formatMoney(trade.price, 4)}</td>
                        <td>{formatMoney(trade.notional, 2)}</td>
                        <td>{formatMoney(trade.fee, 4)}</td>
                        <td className={Number(trade.pnl) >= 0 ? 'profit' : 'loss'}>{trade.pnl == null ? '—' : formatMoney(trade.pnl, 2)}</td>
                      </tr>
                      {expanded ? (
                        <tr className="trade-detail-row">
                          <td colSpan="10">
                            <div className="trade-detail-grid">
                              <div><span>Trade ID</span><strong>{trade.raw?.trade_id || '—'}</strong></div>
                              <div><span>Hash</span><strong className="hash-text">{trade.raw?.hash || '—'}</strong></div>
                              <div><span>原始方向</span><strong>{trade.raw?.raw_direction || '—'}</strong></div>
                              <div><span>起始仓位</span><strong>{trade.raw?.start_position ?? '—'}</strong></div>
                              <div><span>来源</span><strong>{trade.raw?.source || '—'}</strong></div>
                              <div><span>策略标签</span><strong>{trade.raw?.strategy_tag || '—'}</strong></div>
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">当前筛选条件下没有可展示的交易记录</div>
        )}
      </section>
    </Layout>
  );
}
