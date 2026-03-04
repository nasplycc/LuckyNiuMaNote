import Layout from '../components/Layout.jsx';

export default function StrategyPage({ data }) {
  const strat = data.STRATEGY?.strategy || {};
  const indicators = data.STRATEGY?.indicators || [];
  const entryRules = data.STRATEGY?.entryRules || {};
  const exitRules = data.STRATEGY?.exitRules || {};
  const risk = data.STRATEGY?.riskManagement || {};

  return (
    <Layout>
      <div className="wallet-card">
        <h3>📋 策略概述</h3>
        <p className="text-secondary">{strat.description}</p>
      </div>

      <div className="position-card">
        <div className="position-header"><h3>📊 技术指标</h3></div>
        {indicators.map((ind) => (
          <div className="position-item" key={`${ind.name}-${ind.period}`}>
            <div className="position-row">
              <span className="coin">{ind.name}</span>
              <span className="tag">周期: {ind.period}</span>
            </div>
            <div className="text-secondary">{ind.description}</div>
          </div>
        ))}
      </div>

      <div className="grid-two">
        <div className="wallet-card">
          <h3>📈 做多条件</h3>
          <ul>{(entryRules.long || []).map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
        <div className="wallet-card">
          <h3>📉 做空条件</h3>
          <ul>{(entryRules.short || []).map((item) => <li key={item}>{item}</li>)}</ul>
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
        </div>
      </div>
    </Layout>
  );
}
