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

export default function TradesPage() {
  const { data, loading, error } = useTradesData();

  if (loading) {
    return <div className="loading-screen">交易记录加载中...</div>;
  }

  if (error || !data) {
    return <div className="loading-screen error">交易记录加载失败</div>;
  }

  const trades = data?.trades || [];

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
          <div><span>记录数</span><strong>{trades.length}</strong></div>
          <div><span>更新时间</span><strong>{formatTs(data?.updated_at)}</strong></div>
        </div>
      </section>

      <section className="dashboard-panel trades-panel">
        <div className="panel-header">
          <h3>开仓 / 平仓明细</h3>
          <span className="panel-badge">{trades.length} 条</span>
        </div>

        {trades.length ? (
          <div className="trades-table-wrap">
            <table className="trades-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>标的</th>
                  <th>动作</th>
                  <th>方向</th>
                  <th>数量</th>
                  <th>价格</th>
                  <th>成交额</th>
                  <th>盈亏</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((trade, idx) => {
                  const action = inferAction(trade);
                  const side = inferSide(trade);
                  const symbol = trade?.symbol || trade?.coin || '—';
                  const size = trade?.size ?? trade?.sz ?? trade?.qty;
                  const price = trade?.price ?? trade?.avg_px ?? trade?.avgPx ?? trade?.entry_price ?? trade?.exit_price;
                  const notional = trade?.notional ?? trade?.value ?? (Number(size) && Number(price) ? Number(size) * Number(price) : null);
                  const pnl = trade?.realized_pnl ?? trade?.pnl ?? trade?.closed_pnl;
                  const ts = trade?.timestamp || trade?.created_at || trade?.time || trade?.closed_at || trade?.opened_at;
                  return (
                    <tr key={`${symbol}-${ts || idx}-${idx}`}>
                      <td>{formatTs(ts)}</td>
                      <td className="coin">{symbol}</td>
                      <td>
                        <span className={`trade-chip ${action === '开仓' ? 'open' : 'close'}`}>{action}</span>
                      </td>
                      <td>{side}</td>
                      <td>{formatNum(size, 6)}</td>
                      <td>{formatMoney(price, 4)}</td>
                      <td>{formatMoney(notional, 2)}</td>
                      <td className={Number(pnl) >= 0 ? 'profit' : 'loss'}>{pnl == null ? '—' : formatMoney(pnl, 2)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">当前还没有可展示的开仓 / 平仓记录</div>
        )}
      </section>
    </Layout>
  );
}
