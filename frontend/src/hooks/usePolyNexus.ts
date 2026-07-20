import { useState, useEffect, useCallback } from 'react';
import type { AnalysisResponse, ZoneSummary } from '../types/api';
import { API_KEY } from '../api/client';

const STORAGE_KEY = 'selectedZone';

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

  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch('/health');
      setApiHealth(res.ok);
    } catch {
      setApiHealth(false);
    }
  }, []);

  const runAnalysis = useCallback(async (zoneId: string, lat: number, lon: number, name: string) => {
    setLoading(true);
    setActiveZoneId(zoneId);
    localStorage.setItem(STORAGE_KEY, zoneId);
    try {
      const params = new URLSearchParams({ zone_id: zoneId, lat: String(lat), lon: String(lon) });
      const res = await fetch(`/analyse?${params.toString()}`, {
        headers: {
          'X-API-Key': API_KEY
        }
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setAnalysis({ ...(data as AnalysisResponse), displayName: name });
      checkHealth();
    } catch (error: any) {
      console.error(error);
      alert('Analysis failed to load. Please try again later.');
    } finally {
      setLoading(false);
    }
  }, [checkHealth]);

  const loadZones = useCallback(async () => {
    try {
      const res = await fetch('/zones');
      if (res.ok) {
        const data = await res.json();
        const loadedZones = data.zones as ZoneSummary[];
        setZones(loadedZones);

        const storedId = localStorage.getItem(STORAGE_KEY);
        const match = loadedZones.find(z => z.zone_id === storedId);
        if (match) {
          runAnalysis(match.zone_id, match.lat, match.lon, match.name);
        } else if (loadedZones.length > 0) {
          const first = loadedZones[0];
          runAnalysis(first.zone_id, first.lat, first.lon, first.name);
        }
      }
    } catch (e) {
      console.error('Failed to load zones', e);
    }
  }, [runAnalysis]);

  useEffect(() => {
    checkHealth();
    loadZones();
  }, [checkHealth, loadZones]);

  const addCustomZone = useCallback((newZone: ZoneSummary) => {
    setZones(prev => {
      // Avoid duplicate custom zone additions
      if (prev.some(z => z.zone_id === newZone.zone_id)) return prev;
      return [newZone, ...prev];
    });
    runAnalysis(newZone.zone_id, newZone.lat, newZone.lon, newZone.name);
  }, [runAnalysis]);

  return {
    zones,
    activeZoneId,
    analysis,
    loading,
    apiHealth,
    runAnalysis,
    setAnalysis,
    addCustomZone,
  };
}
