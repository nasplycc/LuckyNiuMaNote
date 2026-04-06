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

function formatDurationMs(value) {
  const ms = Number(value);
  if (!Number.isFinite(ms) || ms <= 0) return '—';
  const totalMin = Math.round(ms / 60000);
  if (totalMin < 60) return `${totalMin} 分钟`;
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return m ? `${h}小时 ${m}分钟` : `${h}小时`;
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
  const rawAction = String(trade?.action || trade?.type || trade?.event_type || '');
  if (rawAction === '开仓' || rawAction === '平仓') return rawAction;

  const action = rawAction.toLowerCase();
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

  const latestTrade = filteredTrades[0] || null;
  const topWinningTrade = [...filteredTrades]
    .filter((trade) => Number.isFinite(Number(trade.pnl)))
    .sort((a, b) => (Number(b.pnl) || 0) - (Number(a.pnl) || 0))[0] || null;
  const topFeeTrade = [...filteredTrades]
    .filter((trade) => Number.isFinite(Number(trade.fee)))
    .sort((a, b) => (Number(b.fee) || 0) - (Number(a.fee) || 0))[0] || null;

  const closedTrades = useMemo(
    () => filteredTrades.filter((trade) => trade.action === '平仓' && Number.isFinite(Number(trade.pnl))),
    [filteredTrades]
  );
  const winCount = closedTrades.filter((trade) => Number(trade.pnl) > 0).length;
  const lossCount = closedTrades.filter((trade) => Number(trade.pnl) < 0).length;
  const winRate = closedTrades.length ? (winCount / closedTrades.length) * 100 : 0;
  const avgWin = winCount
    ? closedTrades.filter((trade) => Number(trade.pnl) > 0).reduce((sum, trade) => sum + Number(trade.pnl), 0) / winCount
    : 0;
  const avgLossAbs = lossCount
    ? Math.abs(closedTrades.filter((trade) => Number(trade.pnl) < 0).reduce((sum, trade) => sum + Number(trade.pnl), 0) / lossCount)
    : 0;
  const payoffRatio = avgLossAbs > 0 ? avgWin / avgLossAbs : null;

  const replayGroups = useMemo(() => {
    const openQueues = new Map();
    const groups = [];

    filteredTrades
      .slice()
      .sort((a, b) => new Date(a.ts || 0).getTime() - new Date(b.ts || 0).getTime())
      .forEach((trade) => {
        const queueKey = `${trade.symbol}::${trade.positionSide}`;
        if (trade.action === '开仓') {
          const queue = openQueues.get(queueKey) || [];
          queue.push(trade);
          openQueues.set(queueKey, queue);
          return;
        }
        if (trade.action === '平仓') {
          const queue = openQueues.get(queueKey) || [];
          const openTrade = queue.shift();
          if (openTrade) {
            groups.push({
              key: `${openTrade.key}=>${trade.key}`,
              symbol: trade.symbol,
              positionSide: trade.positionSide,
              openTrade,
              closeTrade: trade,
              durationMs: new Date(trade.ts || 0).getTime() - new Date(openTrade.ts || 0).getTime(),
              pnl: Number(trade.pnl) || 0,
              fee: (Number(openTrade.fee) || 0) + (Number(trade.fee) || 0),
            });
          }
          openQueues.set(queueKey, queue);
        }
      });

    return groups.sort((a, b) => new Date(b.closeTrade.ts || 0).getTime() - new Date(a.closeTrade.ts || 0).getTime());
  }, [filteredTrades]);

  const symbolPerformance = useMemo(() => {
    const map = new Map();
    closedTrades.forEach((trade) => {
      const current = map.get(trade.symbol) || {
        symbol: trade.symbol,
        trades: 0,
        wins: 0,
        pnl: 0,
        fee: 0,
      };
      current.trades += 1;
      if (Number(trade.pnl) > 0) current.wins += 1;
      current.pnl += Number(trade.pnl) || 0;
      current.fee += Number(trade.fee) || 0;
      map.set(trade.symbol, current);
    });
    return Array.from(map.values())
      .map((item) => ({
        ...item,
        winRate: item.trades ? (item.wins / item.trades) * 100 : 0,
      }))
      .sort((a, b) => b.pnl - a.pnl);
  }, [closedTrades]);

  const periodPerformance = useMemo(() => {
    const periods = [
      { key: '24H', label: '近 24 小时', range: '1D' },
      { key: '7D', label: '近 7 天', range: '7D' },
      { key: '30D', label: '近 30 天', range: '30D' },
    ];
    return periods.map((period) => {
      const subset = closedTrades.filter((trade) => isWithinRange(trade.ts, period.range));
      const pnl = subset.reduce((sum, trade) => sum + (Number(trade.pnl) || 0), 0);
      const fee = subset.reduce((sum, trade) => sum + (Number(trade.fee) || 0), 0);
      const wins = subset.filter((trade) => Number(trade.pnl) > 0).length;
      return {
        ...period,
        trades: subset.length,
        wins,
        pnl,
        fee,
        winRate: subset.length ? (wins / subset.length) * 100 : 0,
      };
    });
  }, [closedTrades]);

  const behaviorInsights = useMemo(() => {
    const bestSymbol = symbolPerformance[0] || null;
    const worstSymbol = [...symbolPerformance].sort((a, b) => a.pnl - b.pnl)[0] || null;
    const feeHeavySymbol = [...symbolPerformance].sort((a, b) => b.fee - a.fee)[0] || null;
    const lowQualityReplay = [...replayGroups]
      .filter((group) => group.pnl <= 0 || group.fee >= Math.abs(group.pnl || 0))
      .sort((a, b) => (b.fee - Math.abs(b.pnl || 0)) - (a.fee - Math.abs(a.pnl || 0)))[0] || null;
    return {
      bestSymbol,
      worstSymbol,
      feeHeavySymbol,
      lowQualityReplay,
    };
  }, [symbolPerformance, replayGroups]);

  const actionSuggestions = useMemo(() => {
    const items = [];
    const perf24h = periodPerformance.find((item) => item.key === '24H');
    const perf7d = periodPerformance.find((item) => item.key === '7D');

    if (perf24h && perf7d && perf24h.trades > 0 && perf7d.trades > 0 && perf24h.pnl < perf7d.pnl / Math.max(perf7d.trades, 1)) {
      items.push({
        tone: 'warning',
        title: '最近 24 小时表现弱于近 7 天均值',
        body: `近 24 小时净盈亏 ${formatMoney(perf24h.pnl, 2)}，建议优先观察近期入场质量是否下降。`,
      });
    }

    if (behaviorInsights.feeHeavySymbol && Number(behaviorInsights.feeHeavySymbol.fee) > Math.max(Math.abs(Number(behaviorInsights.feeHeavySymbol.pnl)), 1)) {
      items.push({
        tone: 'warning',
        title: `${behaviorInsights.feeHeavySymbol.symbol} 手续费侵蚀偏高`,
        body: `该标的累计手续费 ${formatMoney(behaviorInsights.feeHeavySymbol.fee, 4)}，已接近或超过其净收益，建议关注交易频率与持仓质量。`,
      });
    }

    if (behaviorInsights.worstSymbol && Number(behaviorInsights.worstSymbol.pnl) < 0) {
      items.push({
        tone: 'danger',
        title: `${behaviorInsights.worstSymbol.symbol} 当前是主要拖累项`,
        body: `该标的当前净盈亏 ${formatMoney(behaviorInsights.worstSymbol.pnl, 2)}，胜率 ${behaviorInsights.worstSymbol.winRate.toFixed(1)}%，建议优先复盘其最近闭环。`,
      });
    }

    if (behaviorInsights.bestSymbol && Number(behaviorInsights.bestSymbol.pnl) > 0) {
      items.push({
        tone: 'positive',
        title: `${behaviorInsights.bestSymbol.symbol} 目前是优势来源`,
        body: `该标的当前净盈亏 ${formatMoney(behaviorInsights.bestSymbol.pnl, 2)}，胜率 ${behaviorInsights.bestSymbol.winRate.toFixed(1)}%，可作为策略稳定性参考样本。`,
      });
    }

    if (!items.length) {
      items.push({
        tone: 'neutral',
        title: '当前样本偏少，暂未发现明显动作建议',
        body: '建议继续积累更多闭环交易，再判断哪些标的和时间窗口存在稳定偏差。',
      });
    }

    return items.slice(0, 4);
  }, [periodPerformance, behaviorInsights]);

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

      <section className="trades-hero-strip">
        <div className="trade-spotlight-card emphasis">
          <span className="trade-spotlight-label">最近成交</span>
          <strong>{latestTrade ? `${latestTrade.symbol} · ${latestTrade.action}` : '暂无'}</strong>
          <small>{latestTrade ? `${formatTs(latestTrade.ts)} · ${formatMoney(latestTrade.price, 4)}` : '等待新成交'}</small>
        </div>
        <div className="trade-spotlight-card">
          <span className="trade-spotlight-label">最佳已实现盈亏</span>
          <strong className={Number(topWinningTrade?.pnl) >= 0 ? 'profit' : 'loss'}>{topWinningTrade ? formatMoney(topWinningTrade.pnl, 2) : '—'}</strong>
          <small>{topWinningTrade ? `${topWinningTrade.symbol} · ${topWinningTrade.action}` : '暂无可比较记录'}</small>
        </div>
        <div className="trade-spotlight-card">
          <span className="trade-spotlight-label">最高手续费</span>
          <strong>{topFeeTrade ? formatMoney(topFeeTrade.fee, 4) : '—'}</strong>
          <small>{topFeeTrade ? `${topFeeTrade.symbol} · ${formatTs(topFeeTrade.ts)}` : '暂无可比较记录'}</small>
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
          <h3>已平仓绩效</h3>
          <span className="panel-badge">{closedTrades.length} 笔已闭环</span>
        </div>
        <div className="performance-grid">
          <div className="performance-card">
            <span>胜率</span>
            <strong>{closedTrades.length ? `${winRate.toFixed(1)}%` : '—'}</strong>
            <small>{winCount} 胜 / {lossCount} 负</small>
          </div>
          <div className="performance-card">
            <span>平均盈利</span>
            <strong className="profit">{closedTrades.length ? formatMoney(avgWin, 2) : '—'}</strong>
            <small>仅统计盈利平仓</small>
          </div>
          <div className="performance-card">
            <span>平均亏损</span>
            <strong className="loss">{closedTrades.length ? formatMoney(avgLossAbs, 2) : '—'}</strong>
            <small>仅统计亏损平仓</small>
          </div>
          <div className="performance-card">
            <span>盈亏比</span>
            <strong>{payoffRatio != null ? payoffRatio.toFixed(2) : '—'}</strong>
            <small>平均盈利 / 平均亏损</small>
          </div>
        </div>
      </section>

      <section className="dashboard-panel trades-panel">
        <div className="panel-header">
          <h3>闭环交易回放</h3>
          <span className="panel-badge">{replayGroups.length} 组</span>
        </div>
        {replayGroups.length ? (
          <div className="replay-grid">
            {replayGroups.map((group) => (
              <article className="replay-card" key={group.key}>
                <div className="replay-card-top">
                  <div className="trade-timeline-title-row">
                    <span className="coin">{group.symbol}</span>
                    <span className={`position-chip ${group.positionSide === 'LONG' ? 'long' : group.positionSide === 'SHORT' ? 'short' : ''}`}>{group.positionSide}</span>
                  </div>
                  <strong className={group.pnl >= 0 ? 'profit' : 'loss'}>{formatMoney(group.pnl, 2)}</strong>
                </div>
                <div className="replay-card-body">
                  <div><span>开仓</span><strong>{formatTs(group.openTrade.ts)}</strong></div>
                  <div><span>平仓</span><strong>{formatTs(group.closeTrade.ts)}</strong></div>
                  <div><span>持有时长</span><strong>{formatDurationMs(group.durationMs)}</strong></div>
                  <div><span>开仓价</span><strong>{formatMoney(group.openTrade.price, 4)}</strong></div>
                  <div><span>平仓价</span><strong>{formatMoney(group.closeTrade.price, 4)}</strong></div>
                  <div><span>合计手续费</span><strong>{formatMoney(group.fee, 4)}</strong></div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state">当前筛选条件下暂时无法组成完整开平仓闭环</div>
        )}
      </section>

      <section className="dashboard-panel trades-panel">
        <div className="panel-header">
          <h3>交易行为诊断</h3>
          <span className="panel-badge">结果归因</span>
        </div>
        <div className="insight-grid">
          <div className="insight-card">
            <span>最赚钱标的</span>
            <strong>{behaviorInsights.bestSymbol?.symbol || '—'}</strong>
            <small className={Number(behaviorInsights.bestSymbol?.pnl) >= 0 ? 'profit' : 'loss'}>
              {behaviorInsights.bestSymbol ? `净盈亏 ${formatMoney(behaviorInsights.bestSymbol.pnl, 2)} · 胜率 ${behaviorInsights.bestSymbol.winRate.toFixed(1)}%` : '暂无足够数据'}
            </small>
          </div>
          <div className="insight-card">
            <span>最伤收益标的</span>
            <strong>{behaviorInsights.worstSymbol?.symbol || '—'}</strong>
            <small className={Number(behaviorInsights.worstSymbol?.pnl) >= 0 ? 'profit' : 'loss'}>
              {behaviorInsights.worstSymbol ? `净盈亏 ${formatMoney(behaviorInsights.worstSymbol.pnl, 2)} · 胜率 ${behaviorInsights.worstSymbol.winRate.toFixed(1)}%` : '暂无足够数据'}
            </small>
          </div>
          <div className="insight-card">
            <span>手续费吞噬最大</span>
            <strong>{behaviorInsights.feeHeavySymbol?.symbol || '—'}</strong>
            <small>
              {behaviorInsights.feeHeavySymbol ? `累计手续费 ${formatMoney(behaviorInsights.feeHeavySymbol.fee, 4)}` : '暂无足够数据'}
            </small>
          </div>
          <div className="insight-card warning">
            <span>低质量闭环提示</span>
            <strong>{behaviorInsights.lowQualityReplay?.symbol || '—'}</strong>
            <small>
              {behaviorInsights.lowQualityReplay
                ? `盈亏 ${formatMoney(behaviorInsights.lowQualityReplay.pnl, 2)} / 手续费 ${formatMoney(behaviorInsights.lowQualityReplay.fee, 4)} / 持有 ${formatDurationMs(behaviorInsights.lowQualityReplay.durationMs)}`
                : '暂无明显低质量闭环'}
            </small>
          </div>
        </div>
      </section>

      <section className="dashboard-panel trades-panel">
        <div className="panel-header">
          <h3>按标的绩效</h3>
          <span className="panel-badge">{symbolPerformance.length} 个标的</span>
        </div>
        {symbolPerformance.length ? (
          <div className="performance-symbol-grid">
            {symbolPerformance.map((item) => (
              <div className="performance-symbol-card" key={`perf-${item.symbol}`}>
                <div className="symbol-summary-top">
                  <strong>{item.symbol}</strong>
                  <span>{item.trades} 笔平仓</span>
                </div>
                <div className="symbol-summary-metrics">
                  <div><span>胜率</span><strong>{item.winRate.toFixed(1)}%</strong></div>
                  <div><span>净盈亏</span><strong className={item.pnl >= 0 ? 'profit' : 'loss'}>{formatMoney(item.pnl, 2)}</strong></div>
                  <div><span>手续费</span><strong>{formatMoney(item.fee, 4)}</strong></div>
                  <div><span>胜场</span><strong>{item.wins}</strong></div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">暂无可用于按标的绩效分析的已平仓记录</div>
        )}
      </section>

      <section className="dashboard-panel trades-panel">
        <div className="panel-header">
          <h3>时间维度表现</h3>
          <span className="panel-badge">最近表现切片</span>
        </div>
        <div className="period-performance-grid">
          {periodPerformance.map((item) => (
            <div className="period-performance-card" key={item.key}>
              <span>{item.label}</span>
              <strong className={item.pnl >= 0 ? 'profit' : 'loss'}>{formatMoney(item.pnl, 2)}</strong>
              <small>{item.trades} 笔平仓 · 胜率 {item.winRate.toFixed(1)}%</small>
              <div className="period-performance-sub">手续费 {formatMoney(item.fee, 4)}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="dashboard-panel trades-panel">
        <div className="panel-header">
          <h3>行动建议</h3>
          <span className="panel-badge">最近恶化 / 优势提示</span>
        </div>
        <div className="recommendation-list">
          {actionSuggestions.map((item, idx) => (
            <article className={`recommendation-card ${item.tone}`} key={`${item.title}-${idx}`}>
              <div className="recommendation-title">{item.title}</div>
              <div className="recommendation-body">{item.body}</div>
            </article>
          ))}
        </div>
      </section>

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
          <h3>交易时间线</h3>
          <span className="panel-badge">{filteredTrades.length} 条</span>
        </div>

        {filteredTrades.length ? (
          <div className="trade-timeline">
            {filteredTrades.map((trade) => {
              const expanded = expandedTradeKey === trade.key;
              return (
                <article className={`trade-timeline-card ${expanded ? 'expanded' : ''}`} key={`card-${trade.key}`} onClick={() => setExpandedTradeKey(expanded ? null : trade.key)}>
                  <div className="trade-timeline-top">
                    <div>
                      <div className="trade-timeline-title-row">
                        <span className="coin">{trade.symbol}</span>
                        <span className={`trade-chip ${trade.action === '开仓' ? 'open' : 'close'}`}>{trade.action}</span>
                        <span className={`position-chip ${trade.positionSide === 'LONG' ? 'long' : trade.positionSide === 'SHORT' ? 'short' : ''}`}>{trade.positionSide}</span>
                      </div>
                      <div className="trade-timeline-time">{formatTs(trade.ts)}</div>
                    </div>
                    <div className={`trade-timeline-pnl ${Number(trade.pnl) >= 0 ? 'profit' : 'loss'}`}>
                      {trade.pnl == null ? '—' : formatMoney(trade.pnl, 2)}
                    </div>
                  </div>

                  <div className="trade-timeline-metrics">
                    <div><span>方向</span><strong>{trade.side}</strong></div>
                    <div><span>数量</span><strong>{formatNum(trade.size, 6)}</strong></div>
                    <div><span>价格</span><strong>{formatMoney(trade.price, 4)}</strong></div>
                    <div><span>成交额</span><strong>{formatMoney(trade.notional, 2)}</strong></div>
                    <div><span>手续费</span><strong>{formatMoney(trade.fee, 4)}</strong></div>
                  </div>

                  {expanded ? (
                    <div className="trade-timeline-detail-grid">
                      <div><span>Trade ID</span><strong>{trade.raw?.trade_id || '—'}</strong></div>
                      <div><span>Hash</span><strong className="hash-text">{trade.raw?.hash || '—'}</strong></div>
                      <div><span>原始方向</span><strong>{trade.raw?.raw_direction || '—'}</strong></div>
                      <div><span>起始仓位</span><strong>{trade.raw?.start_position ?? '—'}</strong></div>
                      <div><span>来源</span><strong>{trade.raw?.source || '—'}</strong></div>
                      <div><span>策略标签</span><strong>{trade.raw?.strategy_tag || '—'}</strong></div>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        ) : (
          <div className="empty-state">当前筛选条件下没有可展示的交易记录</div>
        )}
      </section>

      <section className="dashboard-panel trades-panel">
        <div className="panel-header">
          <h3>表格明细</h3>
          <span className="panel-badge">用于精确核对</span>
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
