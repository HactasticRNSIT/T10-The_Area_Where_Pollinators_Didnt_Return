import { useCallback } from 'react';
import { useCachedFetch } from './useCachedFetch';
import type { LoggedIntervention } from '../types/api';

const API_HEADERS = { 'Content-Type': 'application/json', 'X-API-Key': 'test-api-key-123' };

export function useInterventions(zoneId?: string) {
  const key = zoneId ? `interventions:${zoneId}` : null;
  const state = useCachedFetch<{ zone_id: string; interventions: LoggedIntervention[] }>(
    key,
    zoneId ? `/zones/${encodeURIComponent(zoneId)}/interventions` : null,
    { headers: API_HEADERS },
  );

  const recordIntervention = useCallback(async (intervention: string, appliedAt: string, notes?: string) => {
    if (!zoneId) return false;
    const res = await fetch(`/zones/${encodeURIComponent(zoneId)}/interventions`, {
      method: 'POST',
      headers: API_HEADERS,
      body: JSON.stringify({ intervention, action_key: intervention, applied_at: appliedAt, notes }),
    });
    if (!res.ok) throw new Error(await res.text());
    await state.refetch();
    return true;
  }, [zoneId, state]);

  return {
    ...state,
    interventions: state.data?.interventions ?? [],
    recordIntervention,
  };
}

