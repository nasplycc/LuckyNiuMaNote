import { Navigate, Route, Routes } from 'react-router-dom';
import HomePage from './pages/HomePage.jsx';
import EntryPage from './pages/EntryPage.jsx';
import LearnPage from './pages/LearnPage.jsx';
import StrategyPage from './pages/StrategyPage.jsx';
import ChartPage from './pages/ChartPage.jsx';
import DashboardPage from './pages/DashboardPage.jsx';
import TradesPage from './pages/TradesPage.jsx';
import { useSiteData } from './lib/data.js';

function App() {
  const { data, loading, error } = useSiteData();

  if (loading) {
    return <div className="loading-screen">加载中...</div>;
  }

  if (error || !data) {
    return <div className="loading-screen error">加载站点数据失败</div>;
  }

  return (
    <Routes>
      <Route path="/" element={<DashboardPage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/trades" element={<TradesPage />} />
      <Route path="/entry/:slug" element={<EntryPage data={data} />} />
      <Route path="/strategy" element={<StrategyPage data={data} />} />
      <Route path="/learn" element={<LearnPage data={data} />} />
      <Route path="/learn/:slug" element={<LearnPage data={data} />} />
      <Route path="/chart" element={<ChartPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
