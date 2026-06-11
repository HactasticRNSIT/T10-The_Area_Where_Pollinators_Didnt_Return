import { useCallback, useEffect, useState } from 'react';

const cache = new Map<string, unknown>();

interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<T | null>;
}

export function useCachedFetch<T>(
  key: string | null,
  url: string | null,
  options?: RequestInit,
): FetchState<T> {
  const [data, setData] = useState<T | null>(() => {
    if (!key || !cache.has(key)) return null;
    return cache.get(key) as T;
  });
  const [loading, setLoading] = useState(Boolean(key && !cache.has(key)));
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    if (!key || !url) return null;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(url, options);
      if (!res.ok) throw new Error(await res.text());
      const json = (await res.json()) as T;
      cache.set(key, json);
      setData(json);
      return json;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Request failed';
      setError(message);
      return null;
    } finally {
      setLoading(false);
    }
  }, [key, url]);

  useEffect(() => {
    if (!key || !url) return;
    if (cache.has(key)) {
      setData(cache.get(key) as T);
      setLoading(false);
      void refetch();
    } else {
      void refetch();
    }
  }, [key, url, refetch]);

  return { data, loading, error, refetch };
}
