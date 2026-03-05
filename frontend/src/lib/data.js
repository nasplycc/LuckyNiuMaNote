import { useEffect, useState } from 'react';

export function useSiteData() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;
    
    // 尝试获取实时数据，如果不存在则回退到静态数据
    const fetchData = async () => {
      try {
        let json = null;
        const res1 = await fetch('/realtime-data.json?t=' + Date.now());
        if (res1.ok) {
          const ct = res1.headers.get('content-type') || '';
          if (ct.includes('application/json')) {
            try {
              json = await res1.json();
            } catch (_) {}
          }
        }
        if (!json) {
          const res2 = await fetch('/generated-data.json');
          if (!res2.ok) throw new Error(`HTTP ${res2.status}`);
          json = await res2.json();
        }
        if (mounted) {
          setData(json);
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
    
    // 每10秒刷新一次实时数据
    const interval = setInterval(fetchData, 10000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return { data, loading, error };
}
