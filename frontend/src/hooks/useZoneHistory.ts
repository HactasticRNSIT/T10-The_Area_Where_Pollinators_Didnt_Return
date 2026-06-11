import { useMemo } from 'react';
import { useCachedFetch } from './useCachedFetch';
import type { HistoryPoint } from '../types/api';

const API_HEADERS = { 'X-API-Key': 'test-api-key-123' };

export function useZoneHistory(zoneId?: string) {
  const key = zoneId ? `history:${zoneId}` : null;
  const state = useCachedFetch<{ zone_id: string; history: HistoryPoint[] }>(
    key,
    zoneId ? `/zones/${encodeURIComponent(zoneId)}/history?weeks=52` : null,
    { headers: API_HEADERS },
  );

  const points = useMemo(() => (
    [...(state.data?.history ?? [])]
      .filter((p) => typeof p.activity_score === 'number')
      .sort((a, b) => Date.parse(a.analysed_at) - Date.parse(b.analysed_at))
  ), [state.data]);

  return { ...state, points };
}

