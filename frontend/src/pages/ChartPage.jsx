import { useEffect, useRef, useState } from 'react';
import { Chart, LineController, LineElement, PointElement, CategoryScale, LinearScale, TimeScale, Legend, Tooltip, Title } from 'chart.js';
import 'chartjs-adapter-date-fns';
import Layout from '../components/Layout.jsx';

Chart.register(LineController, LineElement, PointElement, CategoryScale, LinearScale, TimeScale, Legend, Tooltip, Title);

function SymbolChart({ symbol, minutes }) {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);
  const [error, setError] = useState(null);
  const [signals, setSignals] = useState([]);

  useEffect(() => {
    let mounted = true;
    const run = async () => {
      setError(null);
      try {
        const res = await fetch(`/api/chart/${symbol}?interval=1m&minutes=${minutes}`);
        const data = await res.json();
        if (!mounted) return;
        if (!data.success) {
          setError(data.error || '加载失败');
          return;
        }
        setSignals(data.signals || []);
        const labels = data.klines.map((k) => new Date(k.timestamp));
        const price = data.klines.map((k) => k.close);
        const ema9 = data.klines.map((k) => k.ema9);
        const ema21 = data.klines.map((k) => k.ema21);
        const ema55 = data.klines.map((k) => k.ema55);

        if (chartRef.current) chartRef.current.destroy();
        chartRef.current = new Chart(canvasRef.current, {
          type: 'line',
          data: {
            labels,
            datasets: [
              { label: '价格', data: price, borderColor: '#00d4ff', borderWidth: 2, pointRadius: 0 },
              { label: 'EMA9', data: ema9, borderColor: '#00ff9f', borderWidth: 2, pointRadius: 0 },
              { label: 'EMA21', data: ema21, borderColor: '#bf00ff', borderWidth: 2, pointRadius: 0 },
              { label: 'EMA55', data: ema55, borderColor: '#ff0080', borderWidth: 2, borderDash: [5, 5], pointRadius: 0 }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { labels: { color: '#8b949e' } },
              title: { display: true, text: `${symbol}/USD 1分钟K线 + EMA`, color: '#e6edf3' }
            },
            scales: {
              x: { type: 'time', ticks: { color: '#8b949e' }, grid: { color: '#30363d' } },
              y: { ticks: { color: '#8b949e' }, grid: { color: '#30363d' } }
            }
          }
        });
      } catch (e) {
        if (mounted) setError('加载失败');
      }
    };

    run();
    return () => {
      mounted = false;
      if (chartRef.current) chartRef.current.destroy();
    };
  }, [minutes, symbol]);

  return (
    <div>
      <h3>{symbol}</h3>
      <div className="chart-container">{error ? <div className="error">{error}</div> : <canvas ref={canvasRef} />}</div>
      <div className="signals">
        {signals.slice(-5).reverse().map((s) => (
          <div className="signal-item" key={`${s.timestamp}-${s.type}`}>
            <span>{s.label}</span>
            <span>${s.price.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ChartPage() {
  const [minutes, setMinutes] = useState(60);

  return (
    <Layout>
      <div className="range-buttons">
        <button onClick={() => setMinutes(10)} className={minutes === 10 ? 'active' : ''}>10分钟</button>
        <button onClick={() => setMinutes(30)} className={minutes === 30 ? 'active' : ''}>30分钟</button>
        <button onClick={() => setMinutes(60)} className={minutes === 60 ? 'active' : ''}>1小时</button>
        <button onClick={() => setMinutes(1440)} className={minutes === 1440 ? 'active' : ''}>24小时</button>
      </div>

      <div className="chart-grid">
        <SymbolChart symbol="BTC" minutes={minutes} />
        <SymbolChart symbol="ETH" minutes={minutes} />
      </div>
    </Layout>
  );
}
