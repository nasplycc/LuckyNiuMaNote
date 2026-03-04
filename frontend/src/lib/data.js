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
        // 首先尝试实时数据
        let res = await fetch('/realtime-data.json?t=' + Date.now());
        if (!res.ok) {
          // 回退到静态数据
          res = await fetch('/generated-data.json');
        }
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const json = await res.json();
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
