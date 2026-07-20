import { useMemo, useState } from 'react';
import { AlertTriangle, CalendarPlus, CheckCircle, Hexagon, Info, TrendingDown, Wind, X, Layers } from 'lucide-react';
import { motion } from 'framer-motion';
import { useCachedFetch } from '../hooks/useCachedFetch';
import { useInterventions } from '../hooks/useInterventions';
import { useZoneHistory } from '../hooks/useZoneHistory';
import type {
  AnalysisResponse,
  Anomaly,
  CompareResponse,
  HistoryPoint,
  HivePlacementAdvice,
  PhenologyCrop,
  ZoneSummary,
} from '../types/api';
import { formatInr } from '../utils/currency';
import { API_KEY } from '../api/client';

const API_HEADERS = { 'X-API-Key': API_KEY };

function titleCase(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function priorityRank(priority?: string): number {
  return priority === 'High' ? 0 : priority === 'Medium' ? 1 : 2;
}

function costRank(cost?: string): number {
  return cost === 'Low' ? 0 : cost === 'Medium' ? 1 : 2;
}

function getHistorySlope(points: HistoryPoint[]): 'up' | 'flat' | 'down' {
  if (points.length < 2) return 'flat';
  const last = points.slice(-4);
  const delta = last[last.length - 1].activity_score - last[0].activity_score;
  if (delta > 2) return 'up';
  if (delta < -2) return 'down';
  return 'flat';
}

export function MiniSparkline({ points, compact = false }: { points: HistoryPoint[]; compact?: boolean }) {
  const values = points.slice(-12).map((p) => p.activity_score);
  if (values.length < 2) return <span className="roadmap-muted">No trend</span>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(1, max - min);
  const slope = getHistorySlope(points);
  const color = slope === 'up' ? '#10b981' : slope === 'down' ? '#f43f5e' : '#f59e0b';
  const coords = values.map((value, index) => {
    const x = values.length === 1 ? 0 : (index / (values.length - 1)) * 120;
    const y = 34 - ((value - min) / span) * 28;
    return { x, y, value, date: points.slice(-12)[index]?.analysed_at };
  });
  const d = coords.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
  return (
    <svg className={compact ? 'mini-sparkline compact' : 'mini-sparkline'} viewBox="0 0 120 40" role="img"
      aria-label={`Activity score trend: ${values.join(', ')}`}>
      <path d={d} fill="none" stroke={color} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      {coords.map((p, index) => (
        <circle key={`${p.x}-${p.y}`} cx={p.x} cy={p.y} r={index === coords.length - 1 ? 3.2 : 2}
          fill={index === coords.length - 1 ? color : 'rgba(255,255,255,0.55)'}>
          <title>{`${Math.round(p.value)} on ${new Date(p.date).toLocaleDateString()}`}</title>
        </circle>
      ))}
    </svg>
  );
}

export function ZoneHistorySummary({
  zoneId,
  onOpen,
}: {
  zoneId: string;
  onOpen: () => void;
}) {
  const { points, loading, error } = useZoneHistory(zoneId);
  const latest = points[points.length - 1];
  const previous = points[points.length - 2];
  const drop = latest && previous ? previous.activity_score - latest.activity_score : 0;
  const [dismissed, setDismissed] = useState(false);
  return (
    <div className="zone-history-summary">
      {!dismissed && drop > 8 && (
        <div className="score-drop-banner">
          <TrendingDown size={13} />
          <span>Activity dropped {Math.round(drop)} points since last analysis.</span>
          <button type="button" onClick={(event) => { event.stopPropagation(); setDismissed(true); }} aria-label="Dismiss alert">
            <X size={12} />
          </button>
        </div>
      )}
      <div className="zone-spark-row">
        {loading ? <span className="roadmap-skeleton" /> : error ? <span className="roadmap-muted">History unavailable</span> : <MiniSparkline points={points} compact />}
        <strong>{latest ? Math.round(latest.activity_score) : '--'}</strong>
      </div>
      <button type="button" className="roadmap-link-button" onClick={(event) => { event.stopPropagation(); onOpen(); }}>
        History
      </button>
    </div>
  );
}

export function HistoryDrawer({
  zone,
  open,
  onClose,
}: {
  zone: ZoneSummary | null;
  open: boolean;
  onClose: () => void;
}) {
  const { points, loading, error } = useZoneHistory(zone?.zone_id);
  const [showResilience, setShowResilience] = useState(true);
  const [seasonView, setSeasonView] = useState(false);
  const baseline = useMemo(() => computeSeasonalBaseline(points), [points]);
  if (!open || !zone) return null;
  return (
    <div className="history-panel-backdrop" onClick={onClose}>
      <aside className="history-panel glass-panel" onClick={(event) => event.stopPropagation()}>
        <div className="history-panel-header">
          <div>
            <span className="eyebrow">Zone History</span>
            <h3>{zone.zone_id}</h3>
          </div>
          <button className="drawer-close-btn" onClick={onClose} aria-label="Close history panel"><X size={18} /></button>
        </div>
        {loading ? <div className="roadmap-loading-block" /> : error ? (
          <div className="roadmap-empty">Unable to load history right now.</div>
        ) : points.length < 3 ? (
          <div className="roadmap-empty">Not enough history yet - run analysis a few more times to see trends.</div>
        ) : (
          <>
            <div className="history-controls">
              <label><input type="checkbox" checked={showResilience} onChange={(e) => setShowResilience(e.target.checked)} /> Resilience score</label>
              <label><input type="checkbox" checked={seasonView} onChange={(e) => setSeasonView(e.target.checked)} /> Season-over-season</label>
            </div>
            <HistoryChart points={points} showResilience={showResilience} seasonView={seasonView} baseline={baseline} />
          </>
        )}
      </aside>
    </div>
  );
}

function computeSeasonalBaseline(points: HistoryPoint[]) {
  if (points.length < 3) return null;
  const latest = points[points.length - 1];
  const latestMonth = new Date(latest.analysed_at).getMonth();
  const monthPoints = points.filter((p) => new Date(p.analysed_at).getMonth() === latestMonth);
  if (monthPoints.length < 2) return null;
  const mean = monthPoints.reduce((sum, p) => sum + p.activity_score, 0) / monthPoints.length;
  const variance = monthPoints.reduce((sum, p) => sum + (p.activity_score - mean) ** 2, 0) / monthPoints.length;
  return {
    monthName: new Date(latest.analysed_at).toLocaleString(undefined, { month: 'long' }),
    mean,
    low: mean - Math.sqrt(variance),
    high: mean + Math.sqrt(variance),
  };
}

function HistoryChart({
  points,
  showResilience,
  seasonView,
  baseline,
}: {
  points: HistoryPoint[];
  showResilience: boolean;
  seasonView: boolean;
  baseline: ReturnType<typeof computeSeasonalBaseline>;
}) {
  const width = 460;
  const height = 220;
  const plot = (value: number, index: number, total: number) => {
    const x = seasonView
      ? ((weekOfYear(new Date(points[index].analysed_at)) - 1) / 51) * width
      : (index / Math.max(total - 1, 1)) * width;
    const y = height - (clamp(value, 0, 100) / 100) * height;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  };
  const activityPath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${plot(p.activity_score, i, points.length)}`).join(' ');
  const resilience = points.filter((p) => typeof p.resilience_score === 'number');
  const resiliencePath = resilience.map((p, i) => `${i === 0 ? 'M' : 'L'} ${plot(Number(p.resilience_score), i, resilience.length)}`).join(' ');
  const latest = points[points.length - 1];
  const belowBaseline = Boolean(baseline && latest.activity_score < baseline.low);
  return (
    <div className="history-chart-wrap">
      <svg viewBox={`0 0 ${width} ${height + 34}`} role="img" aria-label="Activity score history chart">
        {[0, 25, 50, 75, 100].map((tick) => (
          <g key={tick}>
            <line x1="0" x2={width} y1={height - (tick / 100) * height} y2={height - (tick / 100) * height} stroke="rgba(255,255,255,0.07)" />
            <text x="0" y={height - (tick / 100) * height - 4} fontSize="9" fill="rgba(255,255,255,0.45)">{tick}</text>
          </g>
        ))}
        {baseline && (
          <>
            <rect x="0" width={width} y={height - (baseline.high / 100) * height}
              height={Math.max(4, ((baseline.high - baseline.low) / 100) * height)}
              fill="rgba(245,158,11,0.12)" />
            <text x="8" y={height - (baseline.high / 100) * height + 14} fontSize="10" fill="#f59e0b">
              Typical for {baseline.monthName}
            </text>
          </>
        )}
        <path d={activityPath} fill="none" stroke="#10b981" strokeWidth="3" strokeLinecap="round" />
        {showResilience && resiliencePath && <path d={resiliencePath} fill="none" stroke="#3b82f6" strokeWidth="2" strokeDasharray="5 5" />}
        {belowBaseline && (
          <g transform={`translate(${plot(latest.activity_score, points.length - 1, points.length)})`}>
            <circle r="8" fill="#f43f5e" />
            <text x="-3" y="4" fontSize="10" fill="#fff">!</text>
            <title>Below typical range for this time of year.</title>
          </g>
        )}
      </svg>
    </div>
  );
}

function weekOfYear(date: Date): number {
  const start = new Date(date.getFullYear(), 0, 1);
  return Math.ceil((((date.getTime() - start.getTime()) / 86400000) + start.getDay() + 1) / 7);
}

export function ScoreDisplay({ analysis }: { analysis: AnalysisResponse }) {
  const score = Number(analysis.activity_score || 0);
  const margin = Number(analysis.activity_score_margin ?? analysis.decision_brief?.activity_score_margin ?? 0);
  const confidence = Number(analysis.decision_brief?.data_confidence_score ?? 0);
  const label = confidence >= 82 ? 'live' : confidence >= 62 ? 'mixed' : 'modelled';
  return (
    <div className="score-uncertainty">
      <strong className="ring-val-number" title="This range reflects data quality.">
        {Math.round(score)}{margin ? ` ± ${Math.round(margin)}` : ''}
      </strong>
      <span className="ring-val-label">{label} data</span>
    </div>
  );
}

export function StressInsights({ analysis }: { analysis: AnalysisResponse }) {
  const overall = Number(analysis._meta?.overall_stress ?? 0);
  const cropWeighted = analysis.crop_weighted_stress == null ? null : Number(analysis.crop_weighted_stress);
  const interaction = Number(analysis._meta?.raw_factor_stress?.interaction_penalty ?? 0);
  const factorEntries = Object.entries(analysis._meta?.raw_factor_stress ?? {})
    .filter(([key]) => key !== 'interaction_penalty')
    .sort((a, b) => b[1] - a[1]);
  const primary = factorEntries[0]?.[0];
  const delta = cropWeighted == null ? 0 : (cropWeighted - overall) * 100;
  return (
    <div className="stress-insights">
      {interaction > 0 && (
        <div className="compound-banner">
          <AlertTriangle size={15} />
          <span>Compound stress detected: co-occurring factors add {Math.round(interaction * 100)}% combined stress penalty.</span>
          <Info size={14}><title>Co-occurring stressors are harder for pollinator populations to recover from than each factor in isolation.</title></Info>
        </div>
      )}
      <div className="dual-stress-grid">
        <div><span>Overall stress</span><strong>{Math.round(overall * 100)}%</strong></div>
        <div className="primary"><span>Crop-weighted stress</span><strong>{cropWeighted == null ? '--' : `${Math.round(cropWeighted * 100)}%`}</strong><small>adjusted for crop dependency</small></div>
      </div>
      {Math.abs(delta) > 10 && <p className="roadmap-note">Your crops are {delta > 0 ? 'more' : 'less'} vulnerable to stress than the zone average.</p>}
      {primary && <p className="roadmap-note">Primary driver: {titleCase(primary)}</p>}
    </div>
  );
}

export function CropRiskCards({ analysis }: { analysis: AnalysisResponse }) {
  const cropNames = Object.keys(analysis.crop_risk ?? {});
  const total = cropNames.reduce((sum, crop) => sum + Number(analysis.crop_risk_details?.[crop]?.value_at_risk_inr ?? 0), 0);
  if (cropNames.length === 0) return <div className="roadmap-empty">No crop risk data returned.</div>;
  return (
    <div className="crop-risk-cards">
      {total > 0 && <div className="crop-risk-total">Total across all crops: <strong>{formatInr(total)}</strong></div>}
      <div className="crop-risk-card-grid">
        {cropNames.map((crop) => {
          const risk = analysis.crop_risk_details?.[crop]?.risk_label ?? analysis.crop_risk?.[crop] ?? '--';
          const value = Number(analysis.crop_risk_details?.[crop]?.value_at_risk_inr ?? 0);
          const dependency = analysis.crop_dependency?.[crop];
          return (
            <div key={crop} className="crop-risk-card">
              <div className="crop-risk-top"><strong>{titleCase(crop)}</strong><span className={`risk-badge ${String(risk).toLowerCase()}`}>{risk}</span></div>
              {value > 0 ? (
                <>
                  <div className="money-risk">{formatInr(value)} at risk</div>
                  <small>estimated yield value at risk this season</small>
                </>
              ) : (
                <small>{dependency == null ? 'dependency unknown' : `${Math.round(dependency * 100)}% pollinator dependency`}</small>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function WindStressIndicator({ analysis }: { analysis: AnalysisResponse }) {
  const speed = analysis.climate?.wind_speed_kmh;
  const severity = analysis.climate?.wind_stress_level || 'None';
  return (
    <div className={`wind-stress-badge ${severity.toLowerCase()}`} title="Wind speeds above 25 km/h suppress bee flight. Pollination activity may be reduced.">
      <Wind size={15} />
      <span>{speed ? `${speed} km/h` : 'Wind normal'}</span>
      <strong>{severity}</strong>
    </div>
  );
}

export function PhenologyCalendar({ zoneId, anomalies }: { zoneId: string; anomalies: Anomaly[] }) {
  const state = useCachedFetch<{ zone_id?: string; phenology?: PhenologyCrop[]; crops?: PhenologyCrop[] }>(
    zoneId ? `phenology:${zoneId}` : null,
    zoneId ? `/zones/${encodeURIComponent(zoneId)}/phenology` : null,
    { headers: API_HEADERS },
  );
  const crops = state.data?.phenology ?? state.data?.crops ?? [];
  const floweringActive = crops.some(isInCriticalWindow);
  const pesticideAnomaly = anomalies.some((a) => a.factor === 'pesticide_exposure');
  return (
    <div className="phenology-widget glass-panel">
      <div className="mini-section-header"><span className="eyebrow">Phenology</span><strong>Crop Calendar</strong></div>
      {state.loading ? <div className="roadmap-loading-line" /> : state.error ? (
        <div className="roadmap-muted">Phenology calendar unavailable.</div>
      ) : crops.length === 0 ? (
        <div className="roadmap-muted">No crop flowering windows returned.</div>
      ) : (
        <>
          {pesticideAnomaly && floweringActive && <div className="flowering-alert-pill">Active flowering window</div>}
          <div className="calendar-strip">
            <span className="today-marker" style={{ left: `${(new Date().getMonth() / 11) * 100}%` }} title="Today" />
            {crops.map((crop) => <PhenologyBand key={`${crop.crop}-${crop.flowering_start}`} crop={crop} />)}
          </div>
          <div className="month-row">{['Jan', 'Mar', 'May', 'Jul', 'Sep', 'Nov'].map((m) => <span key={m}>{m}</span>)}</div>
        </>
      )}
    </div>
  );
}

export function isInCriticalWindow(crop: PhenologyCrop): boolean {
  const today = new Date();
  const start = parseMonthDay(crop.flowering_start);
  start.setDate(start.getDate() - crop.critical_window_days);
  const end = parseMonthDay(crop.flowering_end);
  return today >= start && today <= end;
}

export function parseMonthDay(value: string): Date {
  const year = new Date().getFullYear();
  const parsed = new Date(`${year}-${value}`);
  return Number.isNaN(parsed.getTime()) ? new Date(value) : parsed;
}

function PhenologyBand({ crop }: { crop: PhenologyCrop }) {
  const start = parseMonthDay(crop.flowering_start);
  const end = parseMonthDay(crop.flowering_end);
  const startPct = (start.getMonth() / 12) * 100;
  const endPct = ((end.getMonth() + 1) / 12) * 100;
  const criticalStart = Math.max(0, startPct - (crop.critical_window_days / 365) * 100);
  return (
    <>
      <span className="phenology-band normal" style={{ left: `${startPct}%`, width: `${Math.max(4, endPct - startPct)}%` }} title={`${crop.crop}: normal flowering season`} />
      <span className="phenology-band critical" style={{ left: `${criticalStart}%`, width: `${Math.max(3, endPct - criticalStart)}%` }}
        title={`${titleCase(crop.crop)}: Flowering ${crop.flowering_start} - ${crop.flowering_end}. Avoid pesticide application within ${crop.critical_window_days} days.`}>
        {titleCase(crop.crop)}
      </span>
    </>
  );
}

export function InterventionPlan({
  analysis,
}: {
  analysis: AnalysisResponse;
}) {
  const zoneId = analysis.zone_id;
  const { recordIntervention } = useInterventions(zoneId);
  const [quickWins, setQuickWins] = useState(false);
  const [selectedAction, setSelectedAction] = useState<string | null>(null);
  const [notes, setNotes] = useState('');
  const [appliedAt, setAppliedAt] = useState(() => new Date().toISOString().slice(0, 10));
  const plan = [...(analysis.decision_brief?.intervention_plan ?? [])].sort((a, b) => (
    priorityRank(a.priority) - priorityRank(b.priority) || costRank(a.cost_tier) - costRank(b.cost_tier)
  ));
  const visiblePlan = quickWins ? plan.filter((item) => item.priority === 'High' && item.cost_tier === 'Low') : plan;
  const confirm = async () => {
    if (!selectedAction) return;
    await recordIntervention(selectedAction, appliedAt, notes);
    setSelectedAction(null);
    setNotes('');
  };
  return (
    <div className="roadmap-interventions">
      <div className="intervention-toolbar">
        <button type="button" className={quickWins ? 'toggle-chip active' : 'toggle-chip'} onClick={() => setQuickWins((v) => !v)}>Show quick wins only</button>
        <CalendarExportButton analysis={analysis} />
      </div>
      <div className="roadmap-interventions-grid">
        {visiblePlan.length === 0 ? <div className="roadmap-empty">No matching interventions.</div> : visiblePlan.map((item, index) => {
          const action = item.action ?? item.recommended_action ?? item.rationale ?? 'Recommended action';
          return (
            <details key={`${action}-${index}`} className="intervention-plan-item">
              <summary>
                <span>{action}</span>
                <em className={`priority-chip ${String(item.priority ?? 'Low').toLowerCase()}`}>{item.priority ?? 'Low'}</em>
                <em className="cost-chip">{'₹'.repeat(costRank(item.cost_tier) + 1)} {item.cost_tier ?? 'Low'}</em>
              </summary>
              <p>{item.rationale ?? 'Recommended from the current risk profile.'}</p>
              {item.uplift_range && <strong className="uplift-stat">+{item.uplift_range} pollination uplift expected</strong>}
              <button type="button" className="mark-done-btn" onClick={() => setSelectedAction(action)}><CheckCircle size={15} /> Mark as done</button>
            </details>
          );
        })}
      </div>

      {selectedAction && (
        <div className="roadmap-modal-backdrop">
          <div className="roadmap-modal glass-panel">
            <h3>Mark Action as Done</h3>
            <p>{selectedAction}</p>
            <label>Date applied<input type="date" value={appliedAt} onChange={(e) => setAppliedAt(e.target.value)} /></label>
            <label>Notes<textarea value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
            <div className="modal-actions">
              <button type="button" onClick={() => setSelectedAction(null)}>Cancel</button>
              <button type="button" onClick={confirm}>Confirm</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CalendarExportButton({ analysis }: { analysis: AnalysisResponse }) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const download = async () => {
    const res = await fetch(`/zones/${encodeURIComponent(analysis.zone_id)}/calendar.ics?lat=${analysis.latitude}&lon=${analysis.longitude}`, { headers: API_HEADERS });
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${analysis.zone_id}_advisory.ics`;
    document.body.appendChild(link);
    link.click();
    URL.revokeObjectURL(url);
    link.remove();
    setConfirmOpen(false);
  };
  const count = analysis.decision_brief?.intervention_plan?.length ?? 0;
  return (
    <>
      <button type="button" className="toggle-chip" onClick={() => setConfirmOpen(true)}><CalendarPlus size={14} /> Export to calendar</button>
      {confirmOpen && (
        <div className="roadmap-modal-backdrop">
          <div className="roadmap-modal glass-panel">
            <h3>Export Advisory Calendar</h3>
            <p>{count} calendar events will be created for the current intervention plan.</p>
            <p>Events will be timed to the optimal window for your crops based on the flowering calendar.</p>
            <div className="modal-actions"><button type="button" onClick={() => setConfirmOpen(false)}>Cancel</button><button type="button" onClick={download}>Download .ics</button></div>
          </div>
        </div>
      )}
    </>
  );
}

export function HivePlacementCard({ advice }: { advice?: HivePlacementAdvice[] }) {
  const item = advice?.[0];
  const [hectares, setHectares] = useState(1);
  if (!item) return null;
  const hives = Number(item.hives_per_hectare ?? String(item.hives_per_ha ?? '').match(/[0-9]+/)?.[0] ?? 0);
  const radius = item.placement_radius_m ?? item.max_forage_m ?? '—';
  const species = item.species_recommendation ?? item.species ?? 'Local guidance';
  const timing = item.timing ?? item.timing_note ?? 'Before peak flowering';
  return (
    <div className="hive-card">
      <div className="hive-card-head"><Hexagon size={16} /><strong>Managed Hive Placement</strong></div>
      <dl className="hive-stat-grid">
        <dt>Hives / ha</dt><dd>{hives || item.hives_per_ha}</dd>
        <dt>Forage radius</dt><dd>{radius} m</dd>
        <dt>Species</dt><dd>{species}</dd>
        <dt>Timing</dt><dd>{timing}</dd>
      </dl>
      {hives > 0 && (
        <div className="hive-calc-row">
          <label className="hive-calc-label">
            Farm size (ha)
            <input type="number" min="0" step="0.1" value={hectares}
              onChange={(e) => setHectares(Number(e.target.value))} />
          </label>
          <span className="hive-calc-result">≈ <strong>{Math.ceil(hives * hectares)}</strong> hives needed</span>
        </div>
      )}
    </div>
  );
}

export function ComparisonBar({
  selectedZones,
  zones,
  onClear,
  onSelectResult,
}: {
  selectedZones: string[];
  zones: ZoneSummary[];
  onClear: () => void;
  onSelectResult: (analysis: AnalysisResponse) => void;
}) {
  const [open, setOpen] = useState(false);
  if (selectedZones.length < 2) return null;
  return (
    <>
      <div className="comparison-sticky-bar">
        <span>Comparing {selectedZones.length} zones</span>
        <button type="button" onClick={() => setOpen(true)}>View comparison</button>
        <button type="button" onClick={onClear}>Clear</button>
      </div>
      {open && <ComparisonView selectedZones={selectedZones} zones={zones} onClose={() => setOpen(false)} onSelectResult={onSelectResult} />}
    </>
  );
}

function ComparisonView({
  selectedZones,
  zones,
  onClose,
  onSelectResult,
}: {
  selectedZones: string[];
  zones: ZoneSummary[];
  onClose: () => void;
  onSelectResult: (analysis: AnalysisResponse) => void;
}) {
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const selected = zones.filter((zone) => selectedZones.includes(zone.zone_id));
  const runCompare = async () => {
    setLoading(true);
    const res = await fetch('/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...API_HEADERS },
      body: JSON.stringify({ zone_ids: selectedZones }),
    });
    if (res.ok) setResult((await res.json()) as CompareResponse);
    setLoading(false);
  };
  const runAll = async () => {
    setLoading(true);
    const analyses = await Promise.all(selected.map(async (zone) => {
      const params = new URLSearchParams({ zone_id: zone.zone_id, lat: String(zone.lat), lon: String(zone.lon) });
      const res = await fetch(`/analyse?${params}`, { headers: API_HEADERS });
      return (await res.json()) as AnalysisResponse;
    }));
    setResult({ zones: analyses.sort((a, b) => a.activity_score - b.activity_score), completed: analyses.length, total: analyses.length, wall_clock_ms: 0 });
    if (analyses[0]) onSelectResult({ ...analyses[0], displayName: selected.find((z) => z.zone_id === analyses[0].zone_id)?.name });
    setLoading(false);
  };
  const rows = result?.zones ?? [];
  return (
    <div className="comparison-modal-backdrop">
      <div className="comparison-modal glass-panel">
        <div className="history-panel-header"><h3>Multi-Zone Comparison</h3><button className="drawer-close-btn" onClick={onClose}><X size={18} /></button></div>
        <div className="intervention-toolbar"><button type="button" onClick={runCompare}>Load comparison</button><button type="button" onClick={runAll}>Run analysis for all</button></div>
        {loading ? (
          <div className="roadmap-loading-block" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '16px', color: 'var(--text-secondary)' }}>
            <motion.div animate={{ rotate: 360 }} transition={{ duration: 3, repeat: Infinity, ease: 'linear' }}>
              <Hexagon size={48} className="text-teal" style={{ opacity: 0.6 }} />
            </motion.div>
            <span>Running comparative ecosystem analysis...</span>
          </div>
        ) : rows.length === 0 ? (
          <div className="roadmap-empty" style={{ padding: '64px 20px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
            <Layers size={40} className="text-muted" style={{ opacity: 0.3 }} />
            <p style={{ margin: 0 }}>Select multiple zones and click <strong>Load comparison</strong> to benchmark their resilience scores.</p>
          </div>
        ) : (
          <>
            <div className="comparison-table-wrap">
              <table className="comparison-table">
                <thead><tr><th>Metric</th>{rows.map((row) => <th key={row.zone_id}>{row.zone_id}</th>)}</tr></thead>
                <tbody>
                  <tr><td>Activity score</td>{rows.map((row) => <td key={row.zone_id}>{Math.round(row.activity_score)}</td>)}</tr>
                  <tr><td>Resilience</td>{rows.map((row) => <td key={row.zone_id}>{Math.round(Number(row.decision_brief?.resilience_score ?? 0))}</td>)}</tr>
                  <tr><td>Overall stress</td>{rows.map((row) => <td key={row.zone_id}>{Math.round(Number(row._meta?.overall_stress ?? 0) * 100)}%</td>)}</tr>
                  <tr><td>Top drivers</td>{rows.map((row) => <td key={row.zone_id}>{row.anomalies?.slice(0, 2).map((a) => titleCase(a.factor)).join(', ') || '--'}</td>)}</tr>
                  <tr><td>Confidence</td>{rows.map((row) => <td key={row.zone_id}>{Math.round(Number(row.decision_brief?.data_confidence_score ?? 0))}%</td>)}</tr>
                </tbody>
              </table>
            </div>
            <div className="ranked-bars">{rows.map((row) => <div key={row.zone_id}><span>{row.zone_id}</span><strong style={{ width: `${row.activity_score}%` }}>{Math.round(row.activity_score)}</strong></div>)}</div>
          </>
        )}
      </div>
    </div>
  );
}

export function LoggedActionsBadge({ zoneId }: { zoneId: string }) {
  const { interventions } = useInterventions(zoneId);
  if (interventions.length === 0) return null;
  return <span className="actions-count-badge">{interventions.length} actions logged</span>;
}

export function ActionsTakenLog({ zoneId }: { zoneId: string }) {
  const { interventions, loading } = useInterventions(zoneId);
  return (
    <div className="actions-log">
      {loading ? <span className="roadmap-muted">Loading actions...</span> : interventions.length === 0 ? (
        <span className="roadmap-muted">No actions logged yet.</span>
      ) : interventions.map((item) => (
        <div key={item.id} className="action-log-item">
          <span>{item.applied_at ?? 'Date not set'} - {item.intervention}</span>
          {item.after_score == null ? <small>Awaiting next analysis to measure outcome.</small> : <small className={Number(item.delta ?? 0) >= 0 ? 'positive-delta' : 'negative-delta'}>Score before: {item.before_score} {'→'} {item.after_score}</small>}
        </div>
      ))}
    </div>
  );
}

