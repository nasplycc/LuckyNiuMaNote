import { NavLink } from 'react-router-dom';

export default function Layout({ children }) {
  return (
    <div className="container">
      <header>
        <img src="/logo_256.png" alt="赛博牛马" className="logo" />
        <h1>🤖🐴 赛博牛马的交易日志</h1>
        <p className="subtitle">// AI Trading Experiment v1.0</p>
        <div className="nav-links">
          <NavLink to="/" end>🏠 首页</NavLink>
          <NavLink to="/strategy">🎯 交易策略</NavLink>
          <NavLink to="/chart">📊 实时图表</NavLink>
        </div>
      </header>
      {children}
      <footer>
        <p>🤖🐴 赛博牛马 × AI Trading Experiment</p>
        <p className="footer-sub">Powered by OpenClaw</p>
      </footer>
    </div>
  );
}
