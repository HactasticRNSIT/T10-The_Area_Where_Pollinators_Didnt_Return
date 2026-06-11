import { useState, useEffect } from 'react';
import type { AnalysisResponse, ZoneSummary } from '../types/api';

export const FACTOR_META: Record<string, { label: string, weight: number, color: string }> = {
  pesticide_exposure: { label: 'Pesticides', weight: 32, color: '#f43f5e' },
  soil_fertility: { label: 'Soil', weight: 23, color: '#f59e0b' },
  floral_diversity: { label: 'Floral Diversity', weight: 17, color: '#10b981' },
  climate_variability: { label: 'Climate', weight: 12, color: '#3b82f6' },
  nesting_availability: { label: 'Nesting', weight: 8, color: '#84cc16' },
  pollination_factor: { label: 'Pollination', weight: 8, color: '#14b8a6' },
};

export function usePolyNexus() {
  const [zones, setZones] = useState<ZoneSummary[]>([]);
  const [activeZoneId, setActiveZoneId] = useState<string>('');
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [apiHealth, setApiHealth] = useState<boolean>(false);

  useEffect(() => {
    checkHealth();
    loadZones();
  }, []);

  const checkHealth = async () => {
    try {
      const res = await fetch('/health');
      setApiHealth(res.ok);
    } catch {
      setApiHealth(false);
    }
  };

  const loadZones = async () => {
    try {
      const res = await fetch('/zones');
      if (res.ok) {
        const data = await res.json();
        setZones(data.zones as ZoneSummary[]);
      }
    } catch (e) {
      console.error('Failed to load zones', e);
    }
  };

  const runAnalysis = async (zoneId: string, lat: number, lon: number, name: string) => {
    setLoading(true);
    setActiveZoneId(zoneId);
    try {
      const params = new URLSearchParams({ zone_id: zoneId, lat: String(lat), lon: String(lon) });
      const res = await fetch(`/analyse?${params.toString()}`, {
        headers: {
          'X-API-Key': 'test-api-key-123'
        }
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setAnalysis({ ...(data as AnalysisResponse), displayName: name });
      checkHealth();
    } catch (error: any) {
      console.error(error);
      alert(`Analysis failed: ${error?.message || 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  return {
    zones,
    activeZoneId,
    analysis,
    loading,
    apiHealth,
    runAnalysis,
    setAnalysis,
  };
}
