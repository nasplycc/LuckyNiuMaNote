import Layout from '../components/Layout.jsx';

function FallbackList({ items, empty = '暂无内容' }) {
  if (!items || !items.length) return <div className="empty-state">{empty}</div>;
  return <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>;
}

export default function StrategyPage({ data }) {
  const strategyData = data?.STRATEGY || {};
  const strat = strategyData.strategy || {};
  const markets = strategyData.markets || {};
  const indicators = strategyData.indicators || [];
  const entryRules = strategyData.entryRules || {};
  const exitRules = strategyData.exitRules || {};
  const risk = strategyData.riskManagement || {};
  const perf = strategyData.performance || {};
  const diagnostics = data?.SIGNAL_DIAGNOSTICS?.diagnostics || [];
  const btcDiag = diagnostics.find((item) => item.symbol === 'BTC');
  const ethDiag = diagnostics.find((item) => item.symbol === 'ETH');
  const currentShortRule = btcDiag && ethDiag
    ? `RSI(4/14) 进入超买区（BTC 当前 ${btcDiag.thresholds.short.rsi_fast_min}/${btcDiag.thresholds.short.rsi_main_min}，ETH 当前 ${ethDiag.thresholds.short.rsi_fast_min}/${ethDiag.thresholds.short.rsi_main_min}）`
    : null;
  const shortRules = (entryRules.short || []).map((item) => item.includes('RSI(4/14)') && currentShortRule ? currentShortRule : item);

  return (
    <Layout>
      <div className="wallet-card">
        <h3>📋 策略概述</h3>
        <div className="dashboard-status-list">
          <div><span>策略名称</span><strong>{strat.name || 'NFI / LuckyNiuMa'}</strong></div>
          <div><span>版本</span><strong>{strat.version || '—'}</strong></div>
          <div><span>状态</span><strong>{strat.status || 'active'}</strong></div>
          <div><span>交易所</span><strong>{markets.exchange || 'Hyperliquid'}</strong></div>
          <div><span>主市场</span><strong>{(markets.primary || []).join(' / ') || 'BTC / ETH'}</strong></div>
          <div><span>周期</span><strong>{markets.timeframe || '1h'}</strong></div>
        </div>
        <p className="text-secondary">{strat.description || '当前使用 LuckyNiuMa / NFI 方向的多指标趋势 + 反转过滤策略，优先做风控和等待高质量 setup。'}</p>
        {currentShortRule ? <p className="text-secondary">当前实盘做空阈值：{currentShortRule.replace('RSI(4/14) 进入超买区（', '').replace('）', '')}</p> : null}
      </div>

      <div className="position-card">
        <div className="position-header"><h3>📊 核心指标</h3></div>
        {indicators.length ? indicators.map((ind) => (
          <div className="position-item" key={`${ind.name}-${ind.period}`}>
            <div className="position-row">
              <span className="coin">{ind.name}</span>
              <span className="tag">周期: {ind.period}</span>
            </div>
            <div className="text-secondary">{ind.description}</div>
          </div>
        )) : <div className="empty-state">暂无指标说明</div>}
      </div>

      <div className="grid-two">
        <div className="wallet-card">
          <h3>📈 做多条件</h3>
          <FallbackList items={entryRules.long} empty="当前没有单独展示的做多规则" />
        </div>
        <div className="wallet-card">
          <h3>📉 做空条件</h3>
          <FallbackList items={shortRules} empty="当前没有单独展示的做空规则" />
        </div>
      </div>

      <div className="wallet-card">
        <h3>🚪 出场规则</h3>
        <div className="stats">
          <div className="stat-card"><div className="stat-label">止损</div><div className="stat-value pink">{exitRules.stopLoss || '-'}</div></div>
          <div className="stat-card"><div className="stat-label">止盈</div><div className="stat-value green">{exitRules.takeProfit || '-'}</div></div>
          <div className="stat-card"><div className="stat-label">移动止损</div><div className="stat-value blue">{exitRules.trailingStop || '-'}</div></div>
        </div>
      </div>

      <div className="position-card">
        <div className="position-header"><h3>🛡️ 风险管理</h3></div>
        <div className="stats">
          <div className="stat-card"><div className="stat-label">日最大回撤</div><div className="stat-value pink">{risk.maxDailyDrawdown || '-'}</div></div>
          <div className="stat-card"><div className="stat-label">单笔止损</div><div className="stat-value pink">{risk.stopLossPerTrade || '-'}</div></div>
          <div className="stat-card"><div className="stat-label">冷静期</div><div className="stat-value">{risk.cooldownAfterLoss || '-'}</div></div>
          <div className="stat-card"><div className="stat-label">最大并发仓位</div><div className="stat-value">{risk.maxConcurrentPositions || '-'}</div></div>
        </div>
      </div>

      <div className="wallet-card">
        <h3>🎯 策略目标</h3>
        <div className="dashboard-status-list">
          <div><span>初始资金参考</span><strong>{perf.initialCapital || '-'}</strong></div>
          <div><span>目标</span><strong>{perf.targetReturn || '稳健复利优先'}</strong></div>
          <div><span>最大可接受损失</span><strong>{perf.maxAcceptableLoss || '-'}</strong></div>
        </div>
        <FallbackList items={perf.notes} empty="暂无补充说明" />
      </div>
    </Layout>
  );
}
