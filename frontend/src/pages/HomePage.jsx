import { useEffect, useState } from 'react';
import Layout from '../components/Layout.jsx';

const ACTION_LABEL = { LONG: '做多 ↑', SHORT: '做空 ↓', HOLD: '观望 —' };

function formatLastActive(ts) {
  if (!ts) return '暂无记录';
  const diff = Math.floor((Date.now() - ts) / 1000);
  if (diff < 60) return `${diff}秒前`;
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  return `${Math.floor(diff / 86400)}天前`;
}

function SignalBadge({ coin, signal }) {
  if (!signal) {
    return (
      <div className="bot-signal-item">
        <span className="bot-coin">{coin}</span>
        <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>—</span>
      </div>
    );
  }
  const isHold = signal.action === 'HOLD';
  return (
    <div className="bot-signal-item">
      <span className="bot-coin">{coin}</span>
      <span
        className={isHold ? '' : `side ${signal.action === 'LONG' ? 'long' : 'short'}`}
        style={isHold ? { color: 'var(--text-muted)', border: '1px solid var(--border)', borderRadius: '20px', padding: '4px 10px', fontSize: '0.75rem' } : {}}
      >
        {ACTION_LABEL[signal.action] || signal.action}
      </span>
      <span className="bot-signal-reason">{signal.reason}</span>
      {signal.time && <span className="bot-signal-time">{signal.time.slice(11, 16)}</span>}
    </div>
  );
}

function BotCard({ bot }) {
  const isOnline = bot.status === 'running';
  return (
    <div className="bot-card" style={{ borderColor: isOnline ? 'var(--accent)' : 'var(--border)' }}>
      <div className="bot-card-header">
        <div>
          <span className="bot-name">{bot.name}</span>
          <p className="bot-description">{bot.description}</p>
        </div>
        <div className="bot-status-badge" style={{ color: isOnline ? 'var(--accent)' : 'var(--cyber-pink)' }}>
          <span className={`bot-status-dot ${isOnline ? 'online' : 'offline'}`} />
          {isOnline ? '运行中' : '已停止'}
        </div>
      </div>
      <div className="bot-signals">
        <SignalBadge coin="BTC" signal={bot.lastSignal?.BTC} />
        <SignalBadge coin="ETH" signal={bot.lastSignal?.ETH} />
      </div>
      <div className="bot-footer">
        <span className="bot-last-active">最后活跃：{formatLastActive(bot.lastActive)}</span>
        {bot.recentLogs?.length > 0 && (
          <details className="bot-logs">
            <summary>查看日志</summary>
            {bot.recentLogs.map((line, i) => (
              <div key={i} className="bot-log-line">{line}</div>
            ))}
          </details>
        )}
      </div>
    </div>
  );
}

function LiveStats({ staticStats, account }) {
  if (!account) {
    return (
      <div className="stats">
        <div className="stat-card"><div className="stat-label">📅 启动资金</div><div className="stat-value green">$98</div></div>
        <div className="stat-card"><div className="stat-label">💰 当前余额</div><div className="stat-value blue">${staticStats.balance.toFixed(2)}</div></div>
        <div className="stat-card"><div className="stat-label">📈 总收益</div><div className="stat-value pink">{staticStats.returnPct >= 0 ? '+' : ''}{staticStats.returnPct.toFixed(1)}%</div></div>
        <div className="stat-card"><div className="stat-label">🎯 完成交易</div><div className="stat-value green">{staticStats.trades}</div></div>
      </div>
    );
  }

  const pnlClass = account.totalPnl >= 0 ? 'green' : 'red';
  const pnlSign = account.totalPnl >= 0 ? '+' : '';
  const urPnl = account.unrealizedPnl || 0;
  const urClass = urPnl >= 0 ? 'green' : 'red';
  const urSign = urPnl >= 0 ? '+' : '';

  return (
    <div className="stats">
      <div className="stat-card"><div className="stat-label">📅 启动资金</div><div className="stat-value green">${account.initialCapital}</div></div>
      <div className="stat-card"><div className="stat-label">💰 总资产</div><div className="stat-value blue">${account.totalValue.toFixed(2)}</div></div>
      <div className="stat-card"><div className="stat-label">📈 总收益</div><div className={`stat-value ${pnlClass}`}>{pnlSign}{account.totalPnlPct.toFixed(2)}%</div></div>
      <div className="stat-card"><div className="stat-label">💰 总盈亏</div><div className={`stat-value ${pnlClass}`}>{pnlSign}${account.totalPnl.toFixed(2)}</div></div>
      <div className="stat-card"><div className="stat-label">💵 未实现盈亏</div><div className={`stat-value ${urClass}`}>{urSign}${urPnl.toFixed(2)}</div></div>
    </div>
  );
}

export default function HomePage({ data }) {
  const [positionData, setPositionData] = useState(null);
  const [tradersData, setTradersData] = useState(null);
  const wallet = data.VERIFICATION;

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      const tasks = [
        fetch('/api/position').then((r) => r.json()).catch(() => null),
        fetch('/api/traders-status').then((r) => r.json()).catch(() => null)
      ];
      const [position, traders] = await Promise.all(tasks);
      if (!alive) return;
      if (position?.success) setPositionData(position);
      if (traders?.success) setTradersData(traders);
    };

    poll();
    const timer = setInterval(poll, 30000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  return (
    <Layout>
      <LiveStats staticStats={data.STATS} account={positionData?.account} />

      {positionData && (
        <div className="position-card">
          <div className="position-header">
            <h3>📊 实时持仓</h3>
            <span className="live-badge" style={{ color: positionData?.botStatus?.monitor_only ? 'var(--warning)' : 'var(--accent)' }}>
              ● {positionData?.botStatus?.monitor_only ? 'MONITOR' : 'LIVE'}
            </span>
          </div>
          {positionData.positions?.length ? (
            positionData.positions.map((pos) => (
              <div className="position-item" key={`${pos.coin}-${pos.side}`}>
                <div className="position-row">
                  <span className="coin">{pos.coin} {pos.leverage && `${pos.leverage}x`}</span>
                  <span className={`side ${pos.side === 'LONG' ? 'long' : 'short'}`}>{pos.side}</span>
                  <span className="size">{pos.size} {pos.coin}</span>
                </div>
                <div className="position-row"><span className="label">仓位价值</span><span className="value">{pos.positionValue.toFixed(2)} USDC</span></div>
                <div className="position-row"><span className="label">开仓价格</span><span className="value">${pos.entryPx.toLocaleString()}</span></div>
                <div className="position-row"><span className="label">标记价格</span><span className="value price-live">${pos.currentPx.toLocaleString()}</span></div>
                <div className="position-row pnl-row"><span className="label">盈亏(ROE)</span><span className={`value ${pos.pnl >= 0 ? 'profit' : 'loss'}`}>{pos.pnl >= 0 ? '+' : ''}{pos.pnl.toFixed(2)}  ({(pos.roe * 100) >= 0 ? '+' : ''}{(pos.roe * 100).toFixed(1)}%)</span></div>
                <div className="position-row"><span className="label">保证金</span><span className="value">{pos.marginUsed.toFixed(2)} ({pos.leverageType})</span></div>
                <div className="position-row"><span className="label">资金费</span><span className="value">{pos.cumFunding >= 0 ? '+' : ''}{pos.cumFunding.toFixed(2)}</span></div>
              </div>
            ))
          ) : (
            <div className="no-position">当前无持仓</div>
          )}
        </div>
      )}

      {tradersData && (
        <div>
          <div className="position-header" style={{ margin: '20px 0 12px' }}>
            <h3 style={{ margin: 0 }}>🤖🐮 量化机器人军团</h3>
            <span className="live-badge" style={{ color: tradersData?.botStatus?.monitor_only ? 'var(--warning)' : 'var(--accent)' }}>
              ● {tradersData?.botStatus?.monitor_only ? 'MONITOR' : 'LIVE'}
            </span>
          </div>
          <div className="bots-grid">
            {tradersData.traders.map((bot) => <BotCard key={bot.id} bot={bot} />)}
          </div>
        </div>
      )}

      {wallet && (
        <div className="wallet-card">
          <h3>💰 交易钱包</h3>
          <div>
            <span className="muted-label">WALLET ADDRESS</span>
            <code>{wallet.tradingAccount}</code>
          </div>
          <div className="wallet-info">
            <strong>充值说明:</strong><br />
            • 网络: <strong>{wallet.depositChain}</strong><br />
            • 币种: <strong>{wallet.depositToken}</strong><br />
            • 备注: {wallet.depositNote}
          </div>
        </div>
      )}
    </Layout>
  );
}
