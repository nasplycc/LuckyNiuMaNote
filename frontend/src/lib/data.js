import { useEffect, useState } from 'react';

async function fetchJson(path) {
  const res = await fetch(`${path}?t=${Date.now()}`);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
}

export function useSiteData() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;

    const fetchData = async () => {
      try {
        let realtime = null;
        let base = null;
        let signalDiagnostics = null;

        const res1 = await fetch('/realtime-data.json?t=' + Date.now());
        if (res1.ok) {
          const ct = res1.headers.get('content-type') || '';
          if (ct.includes('application/json')) {
            try {
              realtime = await res1.json();
            } catch (_) {}
          }
        }

        const res2 = await fetch('/generated-data.json?t=' + Date.now());
        if (res2.ok) {
          base = await res2.json();
        }

        const res3 = await fetch('/data-export/signal_diagnostics.json?t=' + Date.now());
        if (res3.ok) {
          try {
            signalDiagnostics = await res3.json();
          } catch (_) {}
        }

        const json = base && realtime ? { ...base, ...realtime, SITE_CONFIG: { ...(base.SITE_CONFIG || {}), ...(realtime.SITE_CONFIG || {}) }, VERIFICATION: { ...(base.VERIFICATION || {}), ...(realtime.VERIFICATION || {}) }, STRATEGY: realtime.STRATEGY || base.STRATEGY, ENTRIES: realtime.ENTRIES || base.ENTRIES } : (realtime || base);
        if (json && signalDiagnostics) json.SIGNAL_DIAGNOSTICS = signalDiagnostics;
        if (!json) throw new Error('No site data available');

        if (mounted) {
          setData(json);
          setError(null);
        }
      } catch (err) {
        if (mounted) {
          setError(err);
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    fetchData();

    const interval = setInterval(fetchData, 10000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return { data, loading, error };
}

export function useDashboardData() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;

    const fetchAll = async () => {
      try {
        const [meta, overview, positions, botStatus, alerts, signalDiagnostics] = await Promise.all([
          fetchJson('/data-export/meta.json'),
          fetchJson('/data-export/overview.json'),
          fetchJson('/data-export/positions.json'),
          fetchJson('/data-export/bot_status.json'),
          fetchJson('/data-export/alerts.json'),
          fetchJson('/data-export/signal_diagnostics.json'),
        ]);

        if (!mounted) return;
        setData({ meta, overview, positions, botStatus, alerts, signalDiagnostics });
        setError(null);
      } catch (err) {
        if (mounted) {
          setError(err);
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    fetchAll();
    const interval = setInterval(fetchAll, 60000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return { data, loading, error };
}

export function useTradesData() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;

    const fetchTrades = async () => {
      try {
        const trades = await fetchJson('/data-export/trades.json');
        if (!mounted) return;
        setData(trades);
        setError(null);
      } catch (err) {
        if (mounted) {
          setError(err);
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    fetchTrades();
    const interval = setInterval(fetchTrades, 60000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return { data, loading, error };
}
