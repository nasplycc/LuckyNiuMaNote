import { useState } from 'react';
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

function statusTone(botStatus) {
  if (!botStatus) return 'neutral';
  if (botStatus.safe_mode) return 'danger';
  if (botStatus.process_healthy) return 'success';
  return 'warning';
}

function MetricCard({ label, value, tone = '', hint = '', featured = false }) {
  return (
    <div className={`stat-card stat-card-refined ${featured ? 'stat-card-featured' : ''}`}>
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${tone}`}>{value}</div>
      {hint ? <div className="stat-hint">{hint}</div> : null}
    </div>
  );
}

function InfoCard({ title, badge, children, tone = '' }) {
  return (
    <section className={`dashboard-panel info-card ${tone}`}>
      <div className="panel-header">
        <h3>{title}</h3>
        {badge ? <span className="panel-badge">{badge}</span> : null}
      </div>
      {children}
    </section>
  );
}

function PositionCard({ pos }) {
  const pnl = Number(pos?.unrealized_pnl || 0);
  const pnlPct = Number(pos?.unrealized_pnl_pct || 0);
  const progress = Math.max(0, Math.min(100, Math.abs(pnlPct) * 4));
  const profitable = pnl >= 0;

  return (
    <article className="dashboard-position-card dashboard-position-card-refined" key={`${pos.symbol}-${pos.side}`}>
      <div className="dashboard-position-top">
        <div>
          <div className="coin">{pos.symbol}</div>
          <div className="dashboard-position-meta">{pos.margin_mode} · {pos.leverage || 0}x</div>
        </div>
        <span className={`side ${pos.side === 'LONG' ? 'long' : 'short'}`}>{pos.side}</span>
      </div>

      <div className="position-pnl-hero">
        <div>
          <div className="position-pnl-label">浮动盈亏</div>
          <div className={`position-pnl-value ${profitable ? 'profit' : 'loss'}`}>{formatMoney(pnl, 2)}</div>
        </div>
        <div className={`position-pnl-rate ${profitable ? 'profit' : 'loss'}`}>{formatPct(pnlPct, 2)}</div>
      </div>

      <div className="position-progress-track">
        <div
          className={`position-progress-fill ${profitable ? 'profit' : 'loss'}`}
          style={{ width: `${progress}%` }}
        />
      </div>

      <div className="position-price-compare">
        <div className="price-box">
          <span>开仓价</span>
          <strong>{formatMoney(pos.entry_price, 2)}</strong>
        </div>
        <div className="price-box">
          <span>标记价</span>
          <strong>{formatMoney(pos.mark_price, 2)}</strong>
        </div>
      </div>

      <div className="dashboard-position-body position-detail-grid">
        <div><span>仓位</span><strong>{pos.size}</strong></div>
        <div><span>开仓时间</span><strong>{formatTs(pos.opened_at)}</strong></div>
      </div>
    </article>
  );
}

function DiagnosticCard({ item }) {
  const shortMissing = item?.short_setup?.missing || [];
  const ready = Boolean(item?.short_setup?.ready);
  const distanceFast = Number(item?.distance_to_short_rsi?.rsi_fast || 0);
  const distanceMain = Number(item?.distance_to_short_rsi?.rsi_main || 0);
  const volumeDistance = Number(item?.distance_to_volume_threshold || 0);

  return (
    <article className="diagnostic-card diagnostic-card-refined">
      <div className="diagnostic-card-header">
        <div>
          <div className="coin">{item.symbol}</div>
          <div className="diagnostic-sub">{item.timeframe} 策略诊断</div>
        </div>
        <div className="diagnostic-header-right">
          <div className="diagnostic-price">{formatMoney(item.price, 2)}</div>
          <div className={`diagnostic-ready-pill ${ready ? 'ok' : 'bad'}`}>{ready ? '可入场' : '未满足'}</div>
        </div>
      </div>

      <div className="diagnostic-summary-box">
        <div className="diagnostic-summary-title">结论</div>
        <div className="diagnostic-summary">{item.human_summary || '暂无诊断说明'}</div>
      </div>

      <div className="diagnostic-focus-grid">
        <div className="diagnostic-focus-card">
          <span>RSI Fast 差值</span>
          <strong className={distanceFast > 0 ? 'loss' : 'profit'}>{formatDistance(distanceFast, 2)}</strong>
        </div>
        <div className="diagnostic-focus-card">
          <span>RSI Main 差值</span>
          <strong className={distanceMain > 0 ? 'loss' : 'profit'}>{formatDistance(distanceMain, 2)}</strong>
        </div>
        <div className="diagnostic-focus-card">
          <span>量能差值</span>
          <strong className={volumeDistance > 0 ? 'loss' : 'profit'}>{formatDistance(volumeDistance, 2)}</strong>
        </div>
      </div>

      <div className="diagnostic-tags diagnostic-tags-refined">
        {shortMissing.length ? shortMissing.map((tag) => <span className="diagnostic-tag" key={`short-${item.symbol}-${tag}`}>{tag}</span>) : <span className="diagnostic-tag ok">ready</span>}
      </div>

      <details className="diagnostic-details">
        <summary>查看详细指标</summary>
        <div className="diagnostic-details-grid">
          <div className="diagnostic-side-card">
            <div className="diagnostic-side-title">核心指标</div>
            <div className="diagnostic-metrics">
              <div><span>RSI Fast</span><strong>{item.rsi_fast}</strong></div>
              <div><span>RSI Main</span><strong>{item.rsi_main}</strong></div>
              <div><span>当前量能</span><strong>{Number(item.volume_now || 0).toFixed(2)}</strong></div>
              <div><span>量能阈值</span><strong>{Number(item.volume_threshold || 0).toFixed(2)}</strong></div>
              <div><span>量能/均量</span><strong>{item.volume_ratio_to_sma != null ? `${(Number(item.volume_ratio_to_sma) * 100).toFixed(2)}%` : '暂无'}</strong></div>
            </div>
          </div>
          <div className="diagnostic-side-card">
            <div className="diagnostic-side-title">做空阈值</div>
            <div className="diagnostic-thresholds">
              <div><span>RSI Fast ≥</span><strong>{item?.thresholds?.short?.rsi_fast_min}</strong></div>
              <div><span>RSI Main ≥</span><strong>{item?.thresholds?.short?.rsi_main_min}</strong></div>
              <div><span>当前差值</span><strong className={distanceFast > 0 || distanceMain > 0 ? 'loss' : 'profit'}>{formatDistance(distanceFast, 2)} / {formatDistance(distanceMain, 2)}</strong></div>
            </div>
          </div>
        </div>
      </details>
    </article>
  );
}

function CockpitSummary({ overview, runtimeStatus, runtimeTone, positionsCount, alertsCount }) {
  return (
    <section className="cockpit-summary-grid">
      <div className="cockpit-summary-card emphasis">
        <span className="cockpit-summary-label">账户总览</span>
        <strong>{formatMoney(overview?.perp_equity ?? overview?.equity)}</strong>
        <small>Perp 权益</small>
      </div>
      <div className="cockpit-summary-card">
        <span className="cockpit-summary-label">运行状态</span>
        <strong className={runtimeTone === 'success' ? 'profit' : runtimeTone === 'danger' ? 'loss' : ''}>{runtimeStatus}</strong>
        <small>服务 / 交易引擎</small>
      </div>
      <div className="cockpit-summary-card">
        <span className="cockpit-summary-label">持仓</span>
        <strong>{positionsCount}</strong>
        <small>当前打开仓位</small>
      </div>
      <div className="cockpit-summary-card">
        <span className="cockpit-summary-label">告警</span>
        <strong>{alertsCount}</strong>
        <small>最近事件数量</small>
      </div>
    </section>
  );
}

function ExecutiveSummary({ overview, botStatus, runtimeStatus, positionsCount, latestAlerts, recoveryAlert }) {
  const hasRisk = Boolean(botStatus?.safe_mode || botStatus?.monitor_only || !botStatus?.sqlite_ok);
  const topAlert = latestAlerts.find((item) => item?.title !== 'safe_mode_exit') || latestAlerts[0];

  return (
    <section className={`executive-summary ${hasRisk ? 'risk' : 'healthy'}`}>
      <div className="executive-summary-main">
        <div className="executive-summary-kicker">老板驾驶舱</div>
        <div className="executive-summary-headline">
          {hasRisk
            ? '当前需优先关注系统/风控状态'
            : positionsCount > 0
              ? `系统运行正常，当前有 ${positionsCount} 个持仓在执行`
              : '系统运行正常，当前无持仓，处于等待机会状态'}
        </div>
        <div className="executive-summary-subline">
          模式 {overview?.bot_mode || 'LIVE'} · 服务 {runtimeStatus} · 挂单 {overview?.open_orders_count ?? 0} · 持仓 {positionsCount}
        </div>
      </div>

      <div className="executive-summary-side">
        <div className="executive-summary-item">
          <span>异常优先级</span>
          <strong className={hasRisk ? 'loss' : 'profit'}>{hasRisk ? '需要关注' : '正常'}</strong>
        </div>
        <div className="executive-summary-item">
          <span>最新事件</span>
          <strong>{topAlert?.title || (recoveryAlert ? 'safe_mode_exit' : '暂无异常')}</strong>
        </div>
      </div>
    </section>
  );
}

function CollapsibleSection({ title, badge, defaultOpen = true, children, className = '' }) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className={`dashboard-panel dashboard-panel-full collapsible-panel ${className} ${open ? 'open' : 'collapsed'}`}>
      <div className="panel-header panel-header-clickable" onClick={() => setOpen((v) => !v)}>
        <div className="panel-header-main">
          <h3>{title}</h3>
          {badge ? <span className="panel-badge">{badge}</span> : null}
        </div>
        <button type="button" className="collapse-btn" aria-expanded={open}>
          {open ? '收起' : '展开'}
        </button>
      </div>
      {open ? <div className="collapsible-body">{children}</div> : null}
    </section>
  );
}

function AlertBanner({ botStatus, latestAlerts, recoveryAlert }) {
  const blockingAlert = latestAlerts.find((item) => item?.title !== 'safe_mode_exit');
  const hasCritical = Boolean(botStatus?.safe_mode || botStatus?.monitor_only || !botStatus?.sqlite_ok || blockingAlert);

  if (!hasCritical && !recoveryAlert) {
    return (
      <section className="alert-banner healthy">
        <div className="alert-banner-kicker">状态横幅</div>
        <div className="alert-banner-title">当前无高优先级异常，系统处于相对安静状态</div>
        <div className="alert-banner-text">首页默认以执行与风险概览为主，详细诊断与事件放在下层按需查看。</div>
      </section>
    );
  }

  return (
    <section className={`alert-banner ${hasCritical ? 'danger' : 'healthy'}`}>
      <div>
        <div className="alert-banner-kicker">异常优先</div>
        <div className="alert-banner-title">
          {botStatus?.safe_mode
            ? 'SAFE_MODE 正在生效，需要优先处理'
            : botStatus?.monitor_only
              ? '当前为 MONITOR_ONLY，尚未进入正常实盘执行'
              : !botStatus?.sqlite_ok
                ? 'SQLITE 状态异常，需优先核查运行链路'
                : `${blockingAlert?.title || '存在需关注事件'} 需要优先查看`}
        </div>
        <div className="alert-banner-text">
          {blockingAlert?.message || recoveryAlert?.message || '请先查看首页第一视图中的系统状态与风控信息。'}
        </div>
      </div>
      <div className="alert-banner-side">
        <div className="alert-banner-chip">{botStatus?.safe_mode ? 'SAFE_MODE' : botStatus?.monitor_only ? 'MONITOR_ONLY' : !botStatus?.sqlite_ok ? 'SQLITE_FAIL' : (blockingAlert?.level || 'ALERT').toUpperCase()}</div>
        <div className="alert-banner-time">{blockingAlert?.created_at || recoveryAlert?.created_at ? formatTs(blockingAlert?.created_at || recoveryAlert?.created_at) : '实时'}</div>
      </div>
    </section>
  );
}

function CompactHero({ meta, overview, botStatus, runtimeStatus, runtimeTone, positionsCount }) {
  return (
    <section className="compact-hero">
      <div className="compact-hero-main">
        <div className="dashboard-kicker">LuckyNiuMa Live</div>
        <h2 className="dashboard-title compact-hero-title">交易总控台</h2>
        <div className="dashboard-hero-status-row compact-hero-status-row">
          <span className={`hero-status-pill ${runtimeTone}`}>服务 {runtimeStatus}</span>
          <span className={`hero-status-pill ${overview?.bot_mode === 'SAFE_MODE' ? 'danger' : 'success'}`}>模式 {overview?.bot_mode || 'LIVE'}</span>
          <span className="hero-status-pill neutral">持仓 {positionsCount} 个</span>
          <span className={`hero-status-pill ${botStatus?.monitor_only ? 'warning' : 'success'}`}>{botStatus?.monitor_only ? 'MONITOR_ONLY' : 'LIVE_EXECUTION'}</span>
        </div>
      </div>
      <div className="compact-hero-meta">
        <div><span>环境</span><strong>{meta?.env || 'production'}</strong></div>
        <div><span>交易所</span><strong>{meta?.exchange || 'Hyperliquid'}</strong></div>
        <div><span>版本</span><strong>{botStatus?.version || meta?.git_version || 'unknown'}</strong></div>
        <div><span>更新时间</span><strong>{formatTs(meta?.generated_at || overview?.updated_at)}</strong></div>
      </div>
    </section>
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
  const recoveryAlert = (alerts?.alerts || []).find((item) => item?.title === 'safe_mode_exit');
  const runtimeStatus = statusText(botStatus);
  const runtimeTone = statusTone(botStatus);
  const modeTone = overview?.bot_mode === 'SAFE_MODE' ? 'red' : 'green';

  return (
    <Layout>
      <AlertBanner
        botStatus={botStatus}
        latestAlerts={latestAlerts}
        recoveryAlert={recoveryAlert}
      />

      <ExecutiveSummary
        overview={overview}
        botStatus={botStatus}
        runtimeStatus={runtimeStatus}
        positionsCount={positions?.positions?.length || 0}
        latestAlerts={latestAlerts}
        recoveryAlert={recoveryAlert}
      />

      <CockpitSummary
        overview={overview}
        runtimeStatus={runtimeStatus}
        runtimeTone={runtimeTone}
        positionsCount={positions?.positions?.length || 0}
        alertsCount={latestAlerts.length}
      />

      <CompactHero
        meta={meta}
        overview={overview}
        botStatus={botStatus}
        runtimeStatus={runtimeStatus}
        runtimeTone={runtimeTone}
        positionsCount={positions?.positions?.length || 0}
      />

      <section className="dashboard-section dashboard-section-cockpit dashboard-section-cockpit-compact">
        <div className="section-heading section-heading-compact">
          <div>
            <div className="section-kicker">总览</div>
            <h3>驾驶舱总览</h3>
          </div>
        </div>
        <div className="dashboard-kpi-shell">
          <div className="dashboard-kpi-main">
            <MetricCard label="Perp 权益" value={formatMoney(overview?.perp_equity ?? overview?.equity)} tone="blue" hint="合约账户总权益" featured />
            <MetricCard label="浮动盈亏" value={`${overview?.unrealized_pnl >= 0 ? '+' : ''}${formatMoney(overview?.unrealized_pnl)}`} tone={overview?.unrealized_pnl >= 0 ? 'green' : 'red'} hint="未实现收益" featured />
            <MetricCard label="当前模式" value={overview?.bot_mode || 'LIVE'} tone={modeTone} hint="当前交易状态" featured />
          </div>
          <div className="stats stats-refined stats-secondary">
            <MetricCard label="Spot USDC" value={formatMoney(overview?.spot_usdc)} tone="green" hint="现货钱包" />
            <MetricCard label="持仓数" value={String(overview?.open_positions_count ?? 0)} hint="当前打开仓位" />
            <MetricCard label="挂单数" value={String(overview?.open_orders_count ?? 0)} hint="当前待成交订单" />
          </div>
        </div>
      </section>

      {recoveryAlert && !botStatus?.safe_mode ? (
        <section className="dashboard-recovery-banner">
          <div className="dashboard-recovery-title">✅ 系统已恢复</div>
          <div className="dashboard-recovery-body">
            {recoveryAlert.message || '机器人已自动退出 SAFE_MODE，当前处于正常交易检查状态。'}
          </div>
          <div className="dashboard-recovery-meta">
            恢复时间：{formatTs(recoveryAlert.created_at)}
          </div>
        </section>
      ) : null}

      <section className="dashboard-section dashboard-section-priority">
        <div className="section-heading">
          <div>
            <div className="section-kicker">第一视图</div>
            <h3>风险与执行</h3>
          </div>
        </div>
        <div className="dashboard-two-col dashboard-two-col-tight dashboard-two-col-priority">
          <InfoCard title="机器人状态" badge={runtimeStatus} tone="card-priority">
            <div className="status-board">
              <div className={`status-board-pill ${runtimeTone}`}>
                <span className="status-board-label">运行</span>
                <strong>{runtimeStatus}</strong>
              </div>
              <div className={`status-board-pill ${botStatus?.safe_mode ? 'danger' : 'success'}`}>
                <span className="status-board-label">SAFE_MODE</span>
                <strong>{botStatus?.safe_mode ? 'ON' : 'OFF'}</strong>
              </div>
              <div className={`status-board-pill ${botStatus?.monitor_only ? 'warning' : 'success'}`}>
                <span className="status-board-label">MONITOR</span>
                <strong>{botStatus?.monitor_only ? 'ONLY' : 'LIVE'}</strong>
              </div>
              <div className={`status-board-pill ${botStatus?.sqlite_ok ? 'success' : 'danger'}`}>
                <span className="status-board-label">SQLITE</span>
                <strong>{botStatus?.sqlite_ok ? 'OK' : 'FAIL'}</strong>
              </div>
            </div>
            <div className="dashboard-status-list dashboard-status-list-refined">
              <div><span>服务名</span><strong>{botStatus?.service_name || 'luckyniuma-trader.service'}</strong></div>
              <div><span>systemd</span><strong>{botStatus?.service_status || 'unknown'}</strong></div>
              <div><span>最近心跳</span><strong>{formatTs(botStatus?.last_heartbeat_at)}</strong></div>
              <div><span>最近交易</span><strong>{formatTs(botStatus?.last_trade_at)}</strong></div>
              <div><span>最近对账/事件</span><strong>{formatTs(botStatus?.last_reconcile_at)}</strong></div>
              <div><span>日志文件</span><strong className="path-text">{botStatus?.latest_log_file || '暂无'}</strong></div>
            </div>
          </InfoCard>

          <InfoCard title="风险资金占用" badge="Risk" tone="card-secondary">
            <div className="risk-metrics-grid">
              <div className="risk-metric-card">
                <span>Perp 可用</span>
                <strong>{formatMoney(overview?.perp_available_balance ?? overview?.available_balance)}</strong>
              </div>
              <div className="risk-metric-card">
                <span>Perp 保证金</span>
                <strong>{formatMoney(overview?.perp_margin_used ?? overview?.margin_used)}</strong>
              </div>
              <div className="risk-metric-card">
                <span>挂单数</span>
                <strong>{String(overview?.open_orders_count ?? 0)}</strong>
              </div>
              <div className="risk-metric-card">
                <span>持仓数</span>
                <strong>{String(overview?.open_positions_count ?? 0)}</strong>
              </div>
            </div>
          </InfoCard>
          <InfoCard title="当前持仓" badge={`${positions?.positions?.length || 0} 个仓位`} tone="card-secondary">
            {positions?.positions?.length ? (
              <div className="dashboard-position-list dashboard-position-list-refined">
                {positions.positions.map((pos) => (
                  <PositionCard pos={pos} key={`${pos.symbol}-${pos.side}`} />
                ))}
              </div>
            ) : (
              <div className="empty-state">当前无持仓</div>
            )}
          </InfoCard>
        </div>
      </section>

      <section className="dashboard-section dashboard-section-secondary">
        <div className="section-heading">
          <div>
            <div className="section-kicker">二级信息</div>
            <h3>摘要与诊断</h3>
          </div>
        </div>

        <CollapsibleSection title="诊断提示" badge="快速说明" defaultOpen={false} className="dashboard-glossary-panel">
          <div className="dashboard-status-list dashboard-status-list-refined">
            <div><span>regime</span><strong>趋势环境是否匹配</strong></div>
            <div><span>rsi</span><strong>RSI 强弱条件是否达标</strong></div>
            <div><span>volume</span><strong>成交量是否达到触发阈值</strong></div>
            <div><span>stabilizing</span><strong>价格是否出现企稳 / 反转确认</strong></div>
          </div>
          <div className="glossary-note">当前实盘为 short_only，因此这里只展示实盘做空诊断。缺失项越多，代表离做空入场条件越远；这不是报错，而是策略还没等到入场 setup。</div>
        </CollapsibleSection>

        <CollapsibleSection title="信号诊断" badge={`${diagnostics.length} 个标的`} defaultOpen={true} className="diagnostic-panel">
          {diagnostics.length ? (
            <div className="diagnostic-list">
              {diagnostics.map((item) => (
                <DiagnosticCard item={item} key={item.symbol} />
              ))}
            </div>
          ) : (
            <div className="empty-state">暂无诊断数据</div>
          )}
        </CollapsibleSection>
      </section>

      <section className="dashboard-section">
        <div className="section-heading">
          <div>
            <div className="section-kicker">事件层</div>
            <h3>最近告警</h3>
          </div>
        </div>
        <CollapsibleSection title="最近告警" badge={`${latestAlerts.length} 条`} defaultOpen={false}>
          {latestAlerts.length ? (
            <div className="dashboard-alert-list dashboard-alert-list-refined">
              {latestAlerts.map((alert) => {
                const isRecovery = alert?.title === 'safe_mode_exit';
                return (
                  <article className={`dashboard-alert-item level-${alert.level || 'info'} ${isRecovery ? 'alert-recovery' : ''}`} key={alert.id}>
                    <div className="dashboard-alert-top">
                      <strong>{isRecovery ? 'safe_mode_exit · 已恢复' : alert.title}</strong>
                      <span>{formatTs(alert.created_at)}</span>
                    </div>
                    <p>{alert.message || '—'}</p>
                    <div className="dashboard-alert-footer">
                      {alert.symbol && <div className="dashboard-alert-symbol">标的：{alert.symbol}</div>}
                      <span className={`alert-level-badge level-${alert.level || 'info'} ${isRecovery ? 'level-recovery' : ''}`}>{isRecovery ? 'RECOVERY' : (alert.level || 'info').toUpperCase()}</span>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="empty-state">暂无告警</div>
          )}
        </CollapsibleSection>
      </section>
    </Layout>
  );
}
