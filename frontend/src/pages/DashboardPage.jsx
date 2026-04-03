import Layout from '../components/Layout.jsx';
import { useDashboardData } from '../lib/data.js';

function formatMoney(value, digits = 2) {
  const num = Number(value || 0);
  return `$${num.toFixed(digits)}`;
}

function formatPct(value, digits = 2) {
  const num = Number(value || 0);
  return `${num >= 0 ? '+' : ''}${num.toFixed(digits)}%`;
}

function formatTs(value) {
  if (!value) return '暂无';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('zh-CN', { hour12: false });
}

function formatDistance(value, digits = 2) {
  const num = Number(value || 0);
  return `${num >= 0 ? '+' : ''}${num.toFixed(digits)}`;
}

function statusText(botStatus) {
  if (!botStatus) return '未知';
  if (botStatus.safe_mode) return 'SAFE_MODE';
  if (botStatus.process_healthy) return 'RUNNING';
  return String(botStatus.service_status || 'unknown').toUpperCase();
}

function MetricCard({ label, value, tone = '' }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${tone}`}>{value}</div>
    </div>
  );
}

function DiagnosticCard({ item }) {
  const longMissing = item?.long_setup?.missing || [];
  const shortMissing = item?.short_setup?.missing || [];

  return (
    <article className="diagnostic-card">
      <div className="diagnostic-top">
        <div>
          <div className="coin">{item.symbol}</div>
          <div className="diagnostic-sub">{item.timeframe} 策略诊断</div>
        </div>
        <div className="diagnostic-price">{formatMoney(item.price, 2)}</div>
      </div>

      <div className="diagnostic-metrics">
        <div><span>RSI Fast</span><strong>{item.rsi_fast}</strong></div>
        <div><span>RSI Main</span><strong>{item.rsi_main}</strong></div>
        <div><span>当前量能</span><strong>{Number(item.volume_now || 0).toFixed(2)}</strong></div>
        <div><span>量能阈值</span><strong>{Number(item.volume_threshold || 0).toFixed(2)}</strong></div>
        <div><span>量能/均量</span><strong>{item.volume_ratio_to_sma != null ? `${(Number(item.volume_ratio_to_sma) * 100).toFixed(2)}%` : '暂无'}</strong></div>
        <div><span>距量能阈值</span><strong className={Number(item.distance_to_volume_threshold || 0) > 0 ? 'loss' : 'profit'}>{formatDistance(item.distance_to_volume_threshold, 2)}</strong></div>
      </div>

      <div className="diagnostic-grid">
        <div className="diagnostic-side-card">
          <div className="diagnostic-side-title">实盘做空诊断</div>
          <div className={`diagnostic-ready ${item?.short_setup?.ready ? 'ok' : 'bad'}`}>
            {item?.short_setup?.ready ? '已满足' : '未满足'}
          </div>
          <div className="diagnostic-thresholds">
            <div><span>RSI Fast ≥</span><strong>{item?.thresholds?.short?.rsi_fast_min}</strong></div>
            <div><span>RSI Main ≥</span><strong>{item?.thresholds?.short?.rsi_main_min}</strong></div>
            <div><span>当前差值</span><strong className={Number(item?.distance_to_short_rsi?.rsi_fast || 0) > 0 || Number(item?.distance_to_short_rsi?.rsi_main || 0) > 0 ? 'loss' : 'profit'}>{formatDistance(item?.distance_to_short_rsi?.rsi_fast, 2)} / {formatDistance(item?.distance_to_short_rsi?.rsi_main, 2)}</strong></div>
          </div>
          <div className="diagnostic-tags">
            {shortMissing.length ? shortMissing.map((tag) => <span className="diagnostic-tag" key={`short-${item.symbol}-${tag}`}>{tag}</span>) : <span className="diagnostic-tag ok">ready</span>}
          </div>
        </div>
      </div>

      <div className="diagnostic-summary">{item.human_summary || '暂无诊断说明'}</div>
    </article>
  );
}

export default function DashboardPage() {
  const { data, loading, error } = useDashboardData();

  if (loading) {
    return <div className="loading-screen">Dashboard 加载中...</div>;
  }

  if (error || !data) {
    return <div className="loading-screen error">Dashboard 数据加载失败</div>;
  }

  const { meta, overview, positions, botStatus, alerts, signalDiagnostics } = data;
  const latestAlerts = (alerts?.alerts || []).slice(0, 5);
  const diagnostics = signalDiagnostics?.diagnostics || [];

  return (
    <Layout>
      <section className="dashboard-hero">
        <div>
          <div className="dashboard-kicker">LuckyNiuMa Live</div>
          <h2 className="dashboard-title">交易运行面板</h2>
          <p className="dashboard-subtitle">
            这是你自己的 LuckyNiuMa Live，总览 Spot / Perp 状态、机器人运行状态与未进场原因。
          </p>
        </div>
        <div className="dashboard-hero-meta">
          <div><span>环境</span><strong>{meta?.env || 'production'}</strong></div>
          <div><span>交易所</span><strong>{meta?.exchange || 'Hyperliquid'}</strong></div>
          <div><span>版本</span><strong>{botStatus?.version || meta?.git_version || 'unknown'}</strong></div>
          <div><span>更新时间</span><strong>{formatTs(meta?.generated_at || overview?.updated_at)}</strong></div>
        </div>
      </section>

      <div className="stats">
        <MetricCard label="Spot USDC" value={formatMoney(overview?.spot_usdc)} tone="green" />
        <MetricCard label="Perp 权益" value={formatMoney(overview?.perp_equity ?? overview?.equity)} tone="blue" />
        <MetricCard label="当前模式" value={overview?.bot_mode || 'LIVE'} tone={overview?.bot_mode === 'SAFE_MODE' ? 'red' : 'green'} />
        <MetricCard label="持仓数" value={String(overview?.open_positions_count ?? 0)} />
        <MetricCard label="挂单数" value={String(overview?.open_orders_count ?? 0)} />
        <MetricCard label="Perp 可用" value={formatMoney(overview?.perp_available_balance ?? overview?.available_balance)} />
        <MetricCard label="Perp 保证金" value={formatMoney(overview?.perp_margin_used ?? overview?.margin_used)} />
        <MetricCard
          label="Perp 浮动盈亏"
          value={`${overview?.unrealized_pnl >= 0 ? '+' : ''}${formatMoney(overview?.unrealized_pnl)}`}
          tone={overview?.unrealized_pnl >= 0 ? 'green' : 'red'}
        />
      </div>

      <div className="dashboard-grid">
        <section className="dashboard-panel dashboard-panel-lg">
          <div className="panel-header">
            <h3>当前持仓</h3>
            <span className="panel-badge">{positions?.positions?.length || 0} 个仓位</span>
          </div>
          {positions?.positions?.length ? (
            <div className="dashboard-position-list">
              {positions.positions.map((pos) => (
                <article className="dashboard-position-card" key={`${pos.symbol}-${pos.side}`}>
                  <div className="dashboard-position-top">
                    <div>
                      <div className="coin">{pos.symbol}</div>
                      <div className="dashboard-position-meta">{pos.margin_mode} · {pos.leverage || 0}x</div>
                    </div>
                    <span className={`side ${pos.side === 'LONG' ? 'long' : 'short'}`}>{pos.side}</span>
                  </div>
                  <div className="dashboard-position-body">
                    <div><span>仓位</span><strong>{pos.size}</strong></div>
                    <div><span>开仓价</span><strong>{formatMoney(pos.entry_price, 2)}</strong></div>
                    <div><span>标记价</span><strong>{formatMoney(pos.mark_price, 2)}</strong></div>
                    <div><span>浮盈亏</span><strong className={pos.unrealized_pnl >= 0 ? 'profit' : 'loss'}>{formatMoney(pos.unrealized_pnl, 2)}</strong></div>
                    <div><span>盈亏率</span><strong className={pos.unrealized_pnl_pct >= 0 ? 'profit' : 'loss'}>{formatPct(pos.unrealized_pnl_pct, 2)}</strong></div>
                    <div><span>开仓时间</span><strong>{formatTs(pos.opened_at)}</strong></div>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty-state">当前无持仓</div>
          )}
        </section>

        <section className="dashboard-panel dashboard-panel-full dashboard-glossary-panel">
          <div className="panel-header">
            <h3>诊断提示</h3>
            <span className="panel-badge">快速说明</span>
          </div>
          <div className="dashboard-status-list">
            <div><span>regime</span><strong>趋势环境是否匹配</strong></div>
            <div><span>rsi</span><strong>RSI 强弱条件是否达标</strong></div>
            <div><span>volume</span><strong>成交量是否达到触发阈值</strong></div>
            <div><span>stabilizing</span><strong>价格是否出现企稳 / 反转确认</strong></div>
          </div>
          <div className="glossary-note">当前实盘为 short_only，因此这里只展示实盘做空诊断。缺失项越多，代表离做空入场条件越远；这不是报错，而是策略还没等到入场 setup。</div>
        </section>

        <section className="dashboard-panel dashboard-panel-full diagnostic-panel">
          <div className="panel-header">
            <h3>信号诊断</h3>
            <span className="panel-badge">{diagnostics.length} 个标的</span>
          </div>
          {diagnostics.length ? (
            <div className="diagnostic-list">
              {diagnostics.map((item) => (
                <DiagnosticCard item={item} key={item.symbol} />
              ))}
            </div>
          ) : (
            <div className="empty-state">暂无诊断数据</div>
          )}
        </section>

        <section className="dashboard-panel">
          <div className="panel-header">
            <h3>最近告警</h3>
            <span className="panel-badge">{latestAlerts.length} 条</span>
          </div>
          {latestAlerts.length ? (
            <div className="dashboard-alert-list">
              {latestAlerts.map((alert) => (
                <article className={`dashboard-alert-item level-${alert.level || 'info'}`} key={alert.id}>
                  <div className="dashboard-alert-top">
                    <strong>{alert.title}</strong>
                    <span>{formatTs(alert.created_at)}</span>
                  </div>
                  <p>{alert.message || '—'}</p>
                  {alert.symbol && <div className="dashboard-alert-symbol">标的：{alert.symbol}</div>}
                </article>
              ))}
            </div>
          ) : (
            <div className="empty-state">暂无告警</div>
          )}
        </section>

        <section className="dashboard-panel">
          <div className="panel-header">
            <h3>机器人状态</h3>
            <span className={`panel-badge ${botStatus?.process_healthy ? 'ok' : 'bad'}`}>{statusText(botStatus)}</span>
          </div>
          <div className="dashboard-status-list">
            <div><span>服务名</span><strong>{botStatus?.service_name || 'luckyniuma-trader.service'}</strong></div>
            <div><span>systemd</span><strong>{botStatus?.service_status || 'unknown'}</strong></div>
            <div><span>SAFE_MODE</span><strong>{botStatus?.safe_mode ? 'ON' : 'OFF'}</strong></div>
            <div><span>Monitor Only</span><strong>{botStatus?.monitor_only ? 'YES' : 'NO'}</strong></div>
            <div><span>SQLite</span><strong>{botStatus?.sqlite_ok ? 'OK' : 'FAIL'}</strong></div>
            <div><span>最近心跳</span><strong>{formatTs(botStatus?.last_heartbeat_at)}</strong></div>
            <div><span>最近交易</span><strong>{formatTs(botStatus?.last_trade_at)}</strong></div>
            <div><span>最近对账/事件</span><strong>{formatTs(botStatus?.last_reconcile_at)}</strong></div>
            <div><span>日志文件</span><strong className="path-text">{botStatus?.latest_log_file || '暂无'}</strong></div>
          </div>
        </section>
      </div>
    </Layout>
  );
}
