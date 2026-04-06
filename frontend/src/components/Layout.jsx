import { NavLink } from 'react-router-dom';

export default function Layout({ children }) {
  return (
    <div className="container app-shell">
      <header className="site-header">
        <div className="site-header-top">
          <div className="brand-wrap">
            <img src="/logo_256.png" alt="赛博牛马" className="logo" />
            <div className="brand-copy">
              <div className="brand-kicker">LuckyNiuMa Dashboard</div>
              <h1>🤖🐴 赛博牛马的交易日志</h1>
              <p className="subtitle">把账户、风险、执行、诊断、告警收进一个更清晰的驾驶舱里。</p>
            </div>
          </div>
          <div className="header-status-card">
            <span className="header-status-label">Workspace</span>
            <strong>Hyperliquid Live</strong>
            <span className="header-status-sub">AI Trading Experiment</span>
          </div>
        </div>
        <nav className="nav-links nav-links-refined">
          <NavLink to="/" end>🏠 首页</NavLink>
          <NavLink to="/trades">🧾 交易记录</NavLink>
          <NavLink to="/strategy">🎯 交易策略</NavLink>
          <NavLink to="/chart">📊 实时图表</NavLink>
        </nav>
      </header>
      <main className="page-content">{children}</main>
      <footer>
        <p>🤖🐴 赛博牛马 × AI Trading Experiment</p>
        <p className="footer-sub">Powered by OpenClaw</p>
      </footer>
    </div>
  );
}
