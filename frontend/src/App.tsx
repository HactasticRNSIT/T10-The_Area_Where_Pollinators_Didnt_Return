import { useState, useEffect } from 'react';
import { motion, AnimatePresence, useSpring, useTransform, useMotionValue } from 'framer-motion';
import type { Variants } from 'framer-motion';
import { 
  Search, Hexagon, Leaf, Bug, Menu, X, 
  AlertTriangle, TrendingUp, 
  FileText, Printer, Zap, Shield, Info 
} from 'lucide-react';
import { usePolyNexus, FACTOR_META } from './hooks/usePolyNexus';
import { Chatbot } from './components/Chatbot';
import {
  ComparisonBar,
  CropRiskCards,
  HivePlacementCard,
  HistoryDrawer,
  InterventionPlan,
  LoggedActionsBadge,
  PhenologyCalendar,
  ScoreDisplay,
  StressInsights,
  WindStressIndicator,
  ZoneHistorySummary,
  isInCriticalWindow,
  ActionsTakenLog,
} from './components/RoadmapWidgets';
import type { AnalysisResponse, ZoneSummary, PhenologyCrop } from './types/api';
import { useCachedFetch } from './hooks/useCachedFetch';
import './App.css';

// ──────────────────────────────────────────────────────────────────────────────
// Indian States Mapping (from legacy app.js)
// ──────────────────────────────────────────────────────────────────────────────
const STATE_MAP: Record<string, string> = {
  'Andaman and Nicobar Islands': 'IN_AN',
  'Andhra Pradesh': 'IN_AP',
  'Arunachal Pradesh': 'IN_AR',
  'Assam': 'IN_AS',
  'Bihar': 'IN_BR',
  'Chandigarh': 'IN_CH',
  'Chhattisgarh': 'IN_CT',
  'Dadra and Nagar Haveli and Daman and Diu': 'IN_DN',
  'Delhi': 'IN_DL',
  'Goa': 'IN_GA',
  'Gujarat': 'IN_GJ',
  'Haryana': 'IN_HR',
  'Himachal Pradesh': 'IN_HP',
  'Jammu and Kashmir': 'IN_JK',
  'Jharkhand': 'IN_JH',
  'Karnataka': 'IN_KA',
  'Kerala': 'IN_KL',
  'Ladakh': 'IN_LA',
  'Lakshadweep': 'IN_LD',
  'Madhya Pradesh': 'IN_MP',
  'Maharashtra': 'IN_MH',
  'Manipur': 'IN_MN',
  'Meghalaya': 'IN_ML',
  'Mizoram': 'IN_MZ',
  'Nagaland': 'IN_NL',
  'Odisha': 'IN_OR',
  'Puducherry': 'IN_PY',
  'Punjab': 'IN_PB',
  'Rajasthan': 'IN_RJ',
  'Sikkim': 'IN_SK',
  'Tamil Nadu': 'IN_TN',
  'Telangana': 'IN_TG',
  'Tripura': 'IN_TR',
  'Uttar Pradesh': 'IN_UP',
  'Uttarakhand': 'IN_UT',
  'West Bengal': 'IN_WB'
};

// ──────────────────────────────────────────────────────────────────────────────
// Intervention Scenarios (from legacy app.js)
// ──────────────────────────────────────────────────────────────────────────────
const INTERVENTION_SCENARIOS = [
  {
    id: 'spray_ipm',
    label: 'Switch to IPM spray timing',
    cost: 'Low',
    time: '7 days',
    effects: { pesticide_exposure: 0.32, pollination_factor: 0.08 },
  },
  {
    id: 'flower_strips',
    label: 'Add flowering border strips',
    cost: 'Medium',
    time: '3-6 weeks',
    effects: { floral_diversity: 0.26, pollination_factor: 0.18, nesting_availability: 0.08 },
  },
  {
    id: 'soil_recovery',
    label: 'Compost and soil moisture recovery',
    cost: 'Medium',
    time: '6-10 weeks',
    effects: { soil_fertility: 0.24, climate_variability: 0.08, floral_diversity: 0.08 },
  },
  {
    id: 'nesting_refugia',
    label: 'Create no-till nesting refuges',
    cost: 'Low',
    time: '2 weeks',
    effects: { nesting_availability: 0.30, pollination_factor: 0.08 },
  },
  {
    id: 'drought_buffer',
    label: 'Install water and drought buffers',
    cost: 'Medium',
    time: '10 days',
    effects: { climate_variability: 0.22, floral_diversity: 0.10, pollination_factor: 0.10 },
  },
];

// ── Animation Variants ─────────────────────────────────────────────────────
const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.1, delayChildren: 0.05 }
  }
};

const itemVariants: Variants = {
  hidden: { y: 36, opacity: 0, scale: 0.95 },
  visible: {
    y: 0, opacity: 1, scale: 1,
    transition: { type: 'spring', stiffness: 220, damping: 26 }
  }
};

// ── Animated Number Counter ─────────────────────────────────────────────────
function AnimatedCounter({
  value, suffix = '', decimals = 0
}: { value: number; suffix?: string; decimals?: number }) {
  const mv = useMotionValue(0);
  const spring = useSpring(mv, { stiffness: 55, damping: 24 });
  const display = useTransform(spring, v => v.toFixed(decimals) + suffix);
  useEffect(() => { mv.set(value); }, [value, mv]);
  return <motion.span>{display}</motion.span>;
}

// ── Floating Ambient Orbs ───────────────────────────────────────────────────
function FloatingOrbs() {
  const orbs = [
    { left: '5%',  top: '12%', size: 500, color: 'rgba(16,185,129,0.05)',  dur: 22, delay: 0   },
    { left: '70%', top: '5%',  size: 380, color: 'rgba(20,184,166,0.04)',  dur: 28, delay: 3   },
    { left: '50%', top: '68%', size: 420, color: 'rgba(59,130,246,0.035)', dur: 24, delay: 6   },
    { left: '15%', top: '72%', size: 310, color: 'rgba(245,158,11,0.03)',  dur: 19, delay: 1.5 },
    { left: '86%', top: '52%', size: 260, color: 'rgba(244,63,94,0.025)',  dur: 32, delay: 8   },
  ];
  return (
    <div className="floating-orbs-layer" aria-hidden="true">
      {orbs.map((orb, i) => (
        <motion.div
          key={i}
          className="floating-orb"
          style={{
            left: orb.left, top: orb.top,
            width: orb.size, height: orb.size,
            background: `radial-gradient(circle, ${orb.color} 0%, transparent 68%)`,
          }}
          animate={{ y: [0, -32, 14, -22, 0], x: [0, 24, -14, 18, 0], scale: [1, 1.07, 0.96, 1.04, 1] }}
          transition={{ duration: orb.dur, repeat: Infinity, ease: 'easeInOut', delay: orb.delay }}
        />
      ))}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Custom SVG Charts & Sub-components
// ──────────────────────────────────────────────────────────────────────────────

interface FactorRadarProps {
  factors: Record<string, number>;
}

function FactorRadar({ factors }: FactorRadarProps) {
  const cx = 58, cy = 58, rMax = 54;
  const keys = Object.keys(FACTOR_META);

  const getPoints = (values: number[], radius: number) =>
    values.map((val, index) => {
      const angle = -Math.PI / 2 + (index / values.length) * Math.PI * 2;
      const distance = Math.max(0.08, val) * radius;
      return `${(cx + Math.cos(angle) * distance).toFixed(1)},${(cy + Math.sin(angle) * distance).toFixed(1)}`;
    }).join(' ');

  const rows = keys.map(key => ({
    key,
    stress: Math.max(0, Math.min(1, Number(factors[key] || 0)))
  }));

  const rings = [20, 38, 54].map((radius, rIdx) => (
    <polygon key={rIdx} points={getPoints(rows.map(() => radius / rMax), radius)}
      fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="1" />
  ));

  const spokes = rows.map((_, index) => {
    const angle = -Math.PI / 2 + (index / rows.length) * Math.PI * 2;
    return (
      <motion.line key={index} x1={cx} y1={cy}
        x2={cx + Math.cos(angle) * rMax} y2={cy + Math.sin(angle) * rMax}
        stroke="rgba(255,255,255,0.08)" strokeWidth="1"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }}
        transition={{ delay: 0.2 + index * 0.06 }}
      />
    );
  });

  const stressValues = rows.map(row => row.stress);
  const stressPointsStr = getPoints(stressValues, rMax);
  const dotPoints = stressPointsStr.split(' ');

  return (
    <div className="radar-chart-container">
      <motion.svg
        className="factor-radar" viewBox="0 0 116 116" width="130" height="130"
        initial={{ scale: 0.2, opacity: 0, rotate: -45 }}
        animate={{ scale: 1, opacity: 1, rotate: 0 }}
        transition={{ type: 'spring', stiffness: 130, damping: 22, delay: 0.3 }}
      >
        <g className="radar-grid">{rings}{spokes}</g>
        <motion.polygon
          points={stressPointsStr}
          fill="rgba(20,184,166,0.18)" stroke="var(--accent-teal)" strokeWidth="2"
          initial={{ opacity: 0, scale: 0 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 1.1, delay: 0.55, ease: [0.34, 1.56, 0.64, 1] }}
          style={{ transformOrigin: `${cx}px ${cy}px` }}
        />
        {dotPoints.map((point, idx) => {
          const [px, py] = point.split(',');
          return (
            <motion.circle key={idx} cx={px} cy={py} r="3.5"
              fill="var(--accent-teal)"
              style={{ filter: 'drop-shadow(0 0 5px var(--accent-teal))' }}
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: [0, 1.4, 1], opacity: 1 }}
              transition={{ type: 'spring', stiffness: 300, damping: 18, delay: 0.9 + idx * 0.09 }}
            />
          );
        })}
      </motion.svg>
    </div>
  );
}

interface TrendSparklineProps {
  values: number[];
}

function TrendSparkline({ values }: TrendSparklineProps) {
  if (!values || values.length < 2) {
    return <p className="empty-text">Trend data not available</p>;
  }
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = Math.max(max - min, 0.01);
  const isFlat = max === min;

  const points = values.map((value, index) => ({
    x: (index / (values.length - 1)) * 220,
    y: isFlat ? 25 : 42 - ((value - min) / span) * 34,
  }));

  // Smooth cubic-bezier path
  const pathD = points.reduce((d, p, i) => {
    if (i === 0) return `M ${p.x.toFixed(1)},${p.y.toFixed(1)}`;
    const prev = points[i - 1];
    const cpx = (prev.x + p.x) / 2;
    return `${d} C ${cpx.toFixed(1)},${prev.y.toFixed(1)} ${cpx.toFixed(1)},${p.y.toFixed(1)} ${p.x.toFixed(1)},${p.y.toFixed(1)}`;
  }, '');
  const areaD = `${pathD} L 220,48 L 0,48 Z`;

  const latest = values[values.length - 1];
  const isUp = latest >= values[values.length - 2];
  const accentColor = isUp ? 'var(--accent-emerald)' : 'var(--accent-rose)';

  return (
    <div className="sparkline-container">
      <svg className={`trend-sparkline ${isUp ? 'up' : 'down'}`} viewBox="0 0 220 56" width="100%">
        <defs>
          <linearGradient id="trendFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={accentColor} stopOpacity="0.28" />
            <stop offset="100%" stopColor={accentColor} stopOpacity="0" />
          </linearGradient>
        </defs>
        <line x1="0" y1="43" x2="220" y2="43" stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
        {/* Animated area fill fades in after path draws */}
        <motion.path d={areaD} fill="url(#trendFill)"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          transition={{ delay: 1.4, duration: 0.7 }}
        />
        {/* Path draws itself left-to-right */}
        <motion.path
          d={pathD} fill="none" stroke={accentColor}
          strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{ duration: 1.6, ease: 'easeInOut', opacity: { duration: 0.01 } }}
        />
        {/* Dots pop in sequentially */}
        {points.map((p, idx) => (
          <motion.circle key={idx} cx={p.x} cy={p.y}
            r={idx === points.length - 1 ? 4 : 2.5}
            fill={idx === points.length - 1 ? accentColor : 'rgba(255,255,255,0.55)'}
            stroke={idx === points.length - 1 ? 'rgba(255,255,255,0.45)' : 'none'}
            strokeWidth="1.5"
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 1.5 + idx * 0.07, type: 'spring', stiffness: 280, damping: 18 }}
          />
        ))}
        <text x="0" y="54" fontSize="7" fill="var(--text-muted)">12w ago</text>
        <text x="220" y="54" fontSize="7" fill="var(--text-muted)" textAnchor="end">now</text>
      </svg>
    </div>
  );
}

interface PollinationMetricsProps {
  summary: any;
}

function PollinationMetrics({ summary }: PollinationMetricsProps) {
  const formatRatio = (val: number | null | undefined) =>
    val == null ? '--' : `${Math.round(Number(val) * 100)}%`;
  const formatNumber = (val: number | null | undefined) =>
    val == null || !Number.isFinite(Number(val)) ? '--' : Number(val).toFixed(1);

  const avgVisits = Number(summary.avg_visitations_per_hour || 0);
  const expectedVisits = Number(summary.expected_visitations_per_hour || 0);
  const maxVisits = Math.max(avgVisits, expectedVisits, 1);

  const metrics = [
    { label: 'Avg visits', value: avgVisits, display: formatNumber(summary.avg_visitations_per_hour), max: maxVisits },
    { label: 'Expected', value: expectedVisits, display: formatNumber(summary.expected_visitations_per_hour), max: maxVisits },
    { label: 'Visit ratio', value: Number(summary.visitation_ratio || 0), display: formatRatio(summary.visitation_ratio), max: 1 },
    { label: 'Decline', value: Number(summary.decline_rate_12w || 0), display: formatRatio(summary.decline_rate_12w), max: 1 },
    { label: 'Timing', value: Number(summary.pollination_timing_disruption || 0), display: formatRatio(summary.pollination_timing_disruption), max: 1 },
    { label: 'Flowering', value: Number(summary.flowering_success_rate || 0), display: formatRatio(summary.flowering_success_rate), max: 1 },
  ];

  return (
    <div className="pollination-bars-grid">
      {metrics.map((item, idx) => {
        const height = Math.max(8, Math.min(100, (item.value / item.max) * 100));
        const y2Full = 46 - (height / 100) * 38;
        return (
          <motion.div key={idx} className="bar-metric-item"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.09, type: 'spring', stiffness: 220, damping: 24 }}
          >
            <svg viewBox="0 0 24 50" width="22" height="42" className="metric-bar-svg" style={{ overflow: 'visible' }}>
              {/* Track line */}
              <line x1="12" y1="46" x2="12" y2="8" stroke="rgba(255,255,255,0.05)" strokeWidth="3.5" strokeLinecap="round" />
              {/* Animated fill bar */}
              <motion.line
                x1="12" y1="46" x2="12" y2="46"
                stroke="var(--accent-teal)" strokeWidth="3.5" strokeLinecap="round"
                style={{ filter: 'drop-shadow(0 0 5px rgba(20,184,166,0.55))' }}
                animate={{ x2: 12, y2: y2Full }}
                transition={{ duration: 1, ease: 'easeOut', delay: 0.35 + idx * 0.09 }}
              />
            </svg>
            <strong className="bar-val-text">{item.display}</strong>
            <span className="bar-label-text">{item.label}</span>
          </motion.div>
        );
      })}
    </div>
  );
}

// Helper formatting utilities
const formatDate = (val: string) => {
  try {
    return new Date(val).toLocaleString();
  } catch {
    return val || '';
  }
};

// ──────────────────────────────────────────────────────────────────────────────
// Report HTML Generation Builder (Legacy matched)
// ──────────────────────────────────────────────────────────────────────────────
function buildFarmerReportHtml(data: any, displayName: string) {
  const brief = data.decision_brief || {};
  const drivers = brief.top_risk_drivers || [];
  const plan = brief.intervention_plan || [];
  const crops = brief.crop_exposure || [];
  const sources = brief.source_scorecard || [];
  const summary = data._meta?.visitation_summary || {};
  const caveats = Array.isArray(data._meta?.data_caveats) ? data._meta.data_caveats : [];
  
  const titleCase = (val: string) => val.replace(/\w\S*/g, (w) => w.charAt(0).toUpperCase() + w.slice(1));
  const escapeHtml = (val: string) => String(val).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>PolyNexus Farmer Report - ${escapeHtml(data.zone_id)}</title>
  <style>
    body{font-family:Arial,sans-serif;color:#17201a;margin:32px;line-height:1.45}
    h1{font-size:28px;margin:0 0 4px} h2{font-size:16px;margin:24px 0 8px}
    .muted{color:#5d6b62}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}
    .card{border:1px solid #d7ded9;border-radius:8px;padding:12px}.card strong{display:block;font-size:24px}
    table{width:100%;border-collapse:collapse;margin:8px 0 18px}td,th{border-bottom:1px solid #e1e6e2;padding:8px;text-align:left;font-size:13px}
    .action{border-left:4px solid #159957;background:#f3fbf6;padding:10px 12px;margin:8px 0}
    .boost{border-left:4px solid #e6a817;background:#fffbf0;padding:10px 12px;margin:8px 0}
    ol.boost-ol{margin:4px 0 0 16px;padding:0} ol.boost-ol li{margin:6px 0;font-size:13px}
    @media print{body{margin:18mm}.no-print{display:none}}
  </style>
</head>
<body>
  <h1>PolyNexus Farmer Report</h1>
  <p class="muted">${escapeHtml(data.zone_id)} - ${escapeHtml(displayName || 'Selected zone')} - ${escapeHtml(formatDate(data.analysed_at))}</p>
  <div class="grid">
    <div class="card"><span>Activity</span><strong>${escapeHtml(data.activity_score)}</strong><small>${escapeHtml(data.activity_label)}</small></div>
    <div class="card"><span>Stress</span><strong>${Math.round(Number(data._meta?.overall_stress || 0) * 100)}%</strong><small>${escapeHtml(data.pollination_stress_index)}</small></div>
    <div class="card"><span>Confidence</span><strong>${Math.round(Number(brief.data_confidence_score || 0))}%</strong><small>${escapeHtml(brief.data_confidence_label || '--')}</small></div>
    <div class="card"><span>Resilience</span><strong>${Math.round(Number(brief.resilience_score || 0))}%</strong><small>recovery capacity</small></div>
  </div>
  <h2>How to Increase Pollination &amp; Crop Fertility</h2>
  <p>${escapeHtml(data.biodiversity_insight || '')}</p>
  <h2>Top Action to Boost Fertility This Season</h2>
  <div class="action">${escapeHtml(data.top_intervention || '')}</div>
  ${Array.isArray(data.pollination_boost_actions) && data.pollination_boost_actions.length ? `
  <h2>3 More Steps to Increase Pollination</h2>
  <div class="boost">
    <ol class="boost-ol">
      ${data.pollination_boost_actions.map((a: string) => `<li>${escapeHtml(a)}</li>`).join('')}
    </ol>
  </div>` : ''}
  ${caveats.length ? `<h2>Data Caveats</h2>${caveats.map((item: string) => `<div class="action">${escapeHtml(item)}</div>`).join('')}` : ''}
  <h2>Priority Action Plan</h2>
  ${plan.slice(0, 5).map((item: any) => `<div class="action"><strong>${escapeHtml(item.severity)} - ${escapeHtml(item.label)}</strong><br>${escapeHtml(item.action)}${item.pollination_uplift ? `<br><em style="color:#159957">&#x2191; ${escapeHtml(item.pollination_uplift)}</em>` : ''}</div>`).join('') || '<p>No urgent actions returned.</p>'}
  <h2>Top Risk Drivers</h2>
  <table><thead><tr><th>Driver</th><th>Impact</th><th>Evidence</th></tr></thead><tbody>
    ${drivers.map((driver: any) => `<tr><td>${escapeHtml(driver.label)}</td><td>${Math.round(Number(driver.weighted_impact || 0) * 100)}%</td><td>${escapeHtml(driver.evidence_quality)}</td></tr>`).join('')}
  </tbody></table>
  <h2>Crop Exposure</h2>
  <table><thead><tr><th>Crop</th><th>Dependency</th><th>Exposure</th></tr></thead><tbody>
    ${crops.map((crop: any) => `<tr><td>${escapeHtml(titleCase(crop.crop))}</td><td>${Math.round(Number(crop.dependency || 0) * 100)}%</td><td>${escapeHtml(crop.level)}</td></tr>`).join('')}
  </tbody></table>
  <h2>Pollination Signal</h2>
  <p>Average visits: ${escapeHtml(summary.avg_visitations_per_hour == null ? '--' : Number(summary.avg_visitations_per_hour).toFixed(1))}; expected: ${escapeHtml(summary.expected_visitations_per_hour == null ? '--' : Number(summary.expected_visitations_per_hour).toFixed(1))}; 12-week decline: ${escapeHtml(summary.decline_rate_12w == null ? '--' : Math.round(Number(summary.decline_rate_12w) * 100) + '%')}.</p>
  <h2>Data Sources</h2>
  <table><thead><tr><th>Signal</th><th>Source</th><th>Quality</th></tr></thead><tbody>
    ${sources.map((source: any) => `<tr><td>${escapeHtml(source.signal)}</td><td>${escapeHtml(source.source || '--')}</td><td>${escapeHtml(source.quality || '--')}</td></tr>`).join('')}
  </tbody></table>
  <p class="muted">Decision-support estimate. Validate with field scouting before major operational changes.</p>
</body>
</html>`;
}

// ──────────────────────────────────────────────────────────────────────────────
// Main Dashboard Component
// ──────────────────────────────────────────────────────────────────────────────
function App() {
  const { zones, activeZoneId, analysis, loading, apiHealth, runAnalysis, setAnalysis } = usePolyNexus();
  
  // Search Autocomplete state
  const [searchQuery, setSearchQuery] = useState('');
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedCompareZones, setSelectedCompareZones] = useState<string[]>([]);
  const [historyZone, setHistoryZone] = useState<ZoneSummary | null>(null);

  const phenologyState = useCachedFetch<{ zone_id?: string; phenology?: PhenologyCrop[]; crops?: PhenologyCrop[] }>(
    analysis ? `phenology:${analysis.zone_id}` : null,
    analysis ? `/zones/${encodeURIComponent(analysis.zone_id)}/phenology` : null,
    { headers: { 'X-API-Key': 'test-api-key-123' } }
  );
  const phenologyCrops = phenologyState.data?.phenology ?? phenologyState.data?.crops ?? [];
  const floweringActive = phenologyCrops.some(isInCriticalWindow);

  const displayAnomalies = [...(analysis?.anomalies || [])];
  if (analysis?.climate?.wind_stress_level === 'Critical' && !displayAnomalies.some((a) => a.variable === 'wind_stress_level')) {
    displayAnomalies.push({
      severity: 'HIGH',
      factor: 'wind_stress',
      variable: 'wind_stress_level',
      description: 'Wind conditions suppressing bee flight',
      observation: `${analysis.climate.wind_speed_kmh} km/h`,
      recommended_action: 'Monitor wind conditions before applying interventions.',
    });
  }

  // Intervention Simulator state
  const [selectedScenarios, setSelectedScenarios] = useState<string[]>([]);

  // Auto-select recommended simulator scenarios when analysis updates
  useEffect(() => {
    if (analysis) {
      const drivers = analysis.decision_brief?.top_risk_drivers || [];
      const ids = new Set<string>();
      drivers.slice(0, 2).forEach((driver: any) => {
        if (driver.factor === 'pesticide_exposure') ids.add('spray_ipm');
        if (driver.factor === 'floral_diversity') ids.add('flower_strips');
        if (driver.factor === 'soil_fertility') ids.add('soil_recovery');
        if (driver.factor === 'nesting_availability') ids.add('nesting_refugia');
        if (driver.factor === 'climate_variability') ids.add('drought_buffer');
        if (driver.factor === 'pollination_factor') ids.add('flower_strips');
      });
      if (ids.size === 0) ids.add('flower_strips');
      setSelectedScenarios(Array.from(ids));
    }
  }, [analysis]);

  // Debounced Search suggestion loader (Nominatim API)
  useEffect(() => {
    if (searchQuery.trim().length < 3) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(searchQuery)}&countrycodes=in&limit=5&addressdetails=1`);
        if (res.ok) {
          const data = await res.json();
          setSuggestions(data);
          setShowSuggestions(data.length > 0);
        }
      } catch (e) {
        console.error('Failed to fetch Nominatim suggestions', e);
      }
    }, 400);

    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Handle outside click to close search suggestions
  useEffect(() => {
    const handleGlobalClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('.search-container')) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('click', handleGlobalClick);
    return () => document.removeEventListener('click', handleGlobalClick);
  }, []);

  const regionLabel = (name: string) => {
    return String(name).replace(/\u2014|\u00e2\u20ac\u201d/g, '-').split('-').pop()?.trim() || '';
  };

  const handleSelectSuggestion = (item: any) => {
    const lat = parseFloat(item.lat);
    const lon = parseFloat(item.lon);
    const name = item.display_name;
    const state = item.address.state || '';
    const stateCode = STATE_MAP[state] || 'IN';
    const zoneId = `${stateCode}_SEARCH_${Date.now()}`;
    runAnalysis(zoneId, lat, lon, name);
    setShowSuggestions(false);
    setSearchQuery('');
  };

  // Run Simulator Calculations
  const simResults = analysis ? runSimulation(analysis, selectedScenarios) : null;

  // Report download & print trigger actions
  const triggerDownload = () => {
    if (!analysis) return;
    const html = buildFarmerReportHtml(analysis, analysis.displayName || '');
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `polynexus_report_${analysis.zone_id.replace(/[^a-z0-9_-]+/gi, '_').toLowerCase()}.html`;
    document.body.appendChild(link);
    link.click();
    URL.revokeObjectURL(url);
    link.remove();
  };

  const triggerPrint = () => {
    if (!analysis) return;
    const win = window.open('', '_blank');
    if (!win) {
      alert('Allow popups to print the report.');
      return;
    }
    win.document.write(buildFarmerReportHtml(analysis, analysis.displayName || ''));
    win.document.close();
    win.focus();
    win.print();
  };

  function runSimulation(data: any, selectedIds: string[]) {
    const factorStress = data._meta?.raw_factor_stress || {};
    const weights = data._meta?.factor_weights || Object.fromEntries(
      Object.entries(FACTOR_META).map(([key, meta]) => [key, meta.weight / 100])
    );
    const selected = INTERVENTION_SCENARIOS.filter(s => selectedIds.includes(s.id));
    const combinedEffects: Record<string, number> = {};
    selected.forEach((scenario) => {
      Object.entries(scenario.effects).forEach(([factor, effect]) => {
        combinedEffects[factor] = 1 - ((1 - (combinedEffects[factor] || 0)) * (1 - effect));
      });
    });

    const projected: Record<string, number> = {};
    const keys = Object.keys(FACTOR_META);
    keys.forEach((factor) => {
      const current = Math.max(0, Math.min(1, Number(factorStress[factor] || 0)));
      const effect = combinedEffects[factor] || 0;
      projected[factor] = Math.max(0, current * (1 - effect));
    });

    const currentStress = keys.reduce((sum, factor) => (
      sum + Math.max(0, Math.min(1, Number(factorStress[factor] || 0))) * Number(weights[factor] || 0)
    ), 0);
    const projectedStress = keys.reduce((sum, factor) => (
      sum + projected[factor] * Number(weights[factor] || 0)
    ), 0);
    const currentActivity = Math.round(Math.max(0, Math.min(100, (1 - currentStress) * 100)));
    const projectedActivity = Math.round(Math.max(0, Math.min(100, (1 - projectedStress) * 100)));
    
    const factorChanges = Object.keys(combinedEffects).map(factor => ({
      factor,
      before: Math.round(Number(factorStress[factor] || 0) * 100),
      after: Math.round(projected[factor] * 100),
    })).sort((a, b) => (b.before - b.after) - (a.before - a.after));

    return {
      currentActivity,
      projectedActivity,
      activityGain: Math.max(0, projectedActivity - currentActivity),
      stressDrop: currentStress <= 0 ? 0 : Math.round(((currentStress - projectedStress) / currentStress) * 100),
      factorChanges,
      note: selected.length
        ? 'Projection uses conservative factor reductions, not a guaranteed field outcome. Use it to compare intervention priority.'
        : 'Select one or more interventions to estimate likely recovery direction.',
    };
  }

  const stressVal = analysis ? (analysis._meta?.overall_stress == null ? 0 : Math.round(Number(analysis._meta.overall_stress) * 100)) : 0;
  const activeZone = zones.find((zone) => zone.zone_id === activeZoneId) || null;
  const toggleCompareZone = (zoneId: string) => {
    setSelectedCompareZones((current) => {
      if (current.includes(zoneId)) return current.filter((id) => id !== zoneId);
      if (current.length >= 5) return current;
      return [...current, zoneId];
    });
  };

  return (
    <div className="app-layout">
      {/* Floating ambient colour orbs */}
      <FloatingOrbs />

      {/* Background ambient hex layer */}
      <div className="ambient-hex-layer" aria-hidden="true">
        <svg className="hex-grid" viewBox="0 0 900 520" preserveAspectRatio="none">
          <defs>
            <pattern id="hexPattern" width="54" height="47" patternUnits="userSpaceOnUse">
              <path d="M27 1 L53 15 L53 32 L27 46 L1 32 L1 15 Z" fill="none" stroke="rgba(255,255,255,0.013)" strokeWidth="1" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#hexPattern)" />
        </svg>
      </div>

      {/* Navbar */}
      <nav className="navbar glass-panel">
        <div className="nav-left">
          <button className="hamburger-btn icon-button" aria-label="Open zone selection" onClick={() => setDrawerOpen(true)}>
            <Menu size={20} />
          </button>
          <div className="brand">
            <div className="brand-icon">PX</div>
            <div className="brand-text">
              <h1>PolyNexus</h1>
              <p>Pollinator Intelligence</p>
            </div>
          </div>
        </div>
        
        <div className="search-container">
          <Search size={16} className="search-icon" />
          <input 
            type="text" 
            className="search-input glass-panel" 
            placeholder="Search Indian regions, cities, state..." 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => setShowSuggestions(suggestions.length > 0)}
          />
          {showSuggestions && suggestions.length > 0 && (
            <div className="search-suggestions-dropdown glass-panel">
              {suggestions.map((item, idx) => (
                <div 
                  key={idx} 
                  className="suggestion-item"
                  onClick={() => handleSelectSuggestion(item)}
                >
                  <strong className="suggestion-title">{item.display_name.split(',')[0]}</strong>
                  <small className="suggestion-subtitle">{item.display_name.split(',').slice(1).join(',')}</small>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="nav-actions">
          <motion.div className="api-status glass-panel"
            animate={apiHealth ? { boxShadow: ['0 0 0px rgba(16,185,129,0)', '0 0 12px rgba(16,185,129,0.35)', '0 0 0px rgba(16,185,129,0)'] } : {}}
            transition={{ duration: 2.5, repeat: Infinity, ease: 'easeInOut' }}
          >
            <span className={`status-dot ${apiHealth ? 'online' : 'offline'}`}></span>
            {apiHealth ? 'API Online' : 'API Offline'}
          </motion.div>
        </div>
      </nav>

      {/* Collapsible Sidebar Drawer overlay */}
      <AnimatePresence>
        {drawerOpen && (
          <>
            <motion.div 
              className="drawer-overlay"
              initial={{ opacity: 0 }}
              aria-hidden="true"
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setDrawerOpen(false)}
            />
            <motion.aside 
              className="drawer glass-panel"
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 220 }}
            >
              <div className="drawer-header">
                <div>
                  <span className="eyebrow">Analysis Controls</span>
                  <h2>Choose a Zone</h2>
                </div>
                <button className="drawer-close-btn" onClick={() => setDrawerOpen(false)} aria-label="Close drawer">
                  <X size={20} />
                </button>
              </div>
              
              <div className="drawer-scrollable">
                {/* Preset List */}
                <div className="drawer-section">
                  <h3>Preset Zones</h3>
                  <div className="preset-list">
                    {zones.map((zone: ZoneSummary) => (
                      <div key={zone.zone_id} className={`preset-item zone-card-upgraded ${activeZoneId === zone.zone_id ? 'active' : ''}`}>
                        <label className="compare-check" onClick={(event) => event.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={selectedCompareZones.includes(zone.zone_id)}
                            onChange={() => toggleCompareZone(zone.zone_id)}
                            disabled={!selectedCompareZones.includes(zone.zone_id) && selectedCompareZones.length >= 5}
                          />
                          Compare
                        </label>
                        <button
                          type="button"
                          className="preset-main-button"
                          onClick={() => {
                            runAnalysis(zone.zone_id, zone.lat, zone.lon, zone.name);
                            setDrawerOpen(false);
                          }}
                        >
                          <strong>{zone.zone_id}</strong>
                          <small>{regionLabel(zone.name)}</small>
                        </button>
                        <ZoneHistorySummary zoneId={zone.zone_id} onOpen={() => setHistoryZone(zone)} />
                        <LoggedActionsBadge zoneId={zone.zone_id} />
                      </div>
                    ))}
                  </div>
                </div>

                {/* Custom Form */}
                <div className="drawer-section">
                  <h3>Custom Zone</h3>
                  <form className="custom-zone-form" onSubmit={(e) => {
                    e.preventDefault();
                    const form = e.currentTarget;
                    const zId = (form.elements.namedItem('customZoneId') as HTMLInputElement).value.trim() || 'CUSTOM_ZONE';
                    const lat = parseFloat((form.elements.namedItem('customLat') as HTMLInputElement).value);
                    const lon = parseFloat((form.elements.namedItem('customLon') as HTMLInputElement).value);
                    
                    if (isNaN(lat) || lat < -90 || lat > 90 || isNaN(lon) || lon < -180 || lon > 180) {
                      alert('Enter valid latitude (-90 to 90) and longitude (-180 to 180) values.');
                      return;
                    }
                    runAnalysis(zId, lat, lon, `${lat.toFixed(4)}, ${lon.toFixed(4)}`);
                    setDrawerOpen(false);
                  }}>
                    <div className="form-group">
                      <label htmlFor="customZoneId">Zone ID</label>
                      <input id="customZoneId" name="customZoneId" type="text" placeholder="MY_FARM" required />
                    </div>
                    <div className="form-row">
                      <div className="form-group">
                        <label htmlFor="customLat">Latitude</label>
                        <input id="customLat" name="customLat" type="number" step="0.0001" min="-90" max="90" placeholder="15.4589" required />
                      </div>
                      <div className="form-group">
                        <label htmlFor="customLon">Longitude</label>
                        <input id="customLon" name="customLon" type="number" step="0.0001" min="-180" max="180" placeholder="75.0078" required />
                      </div>
                    </div>
                    <button type="submit" className="submit-btn text-gradient">
                      Analyse Zone
                    </button>
                  </form>
                </div>
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <HistoryDrawer zone={historyZone} open={Boolean(historyZone)} onClose={() => setHistoryZone(null)} />
      <ComparisonBar
        selectedZones={selectedCompareZones}
        zones={zones}
        onClear={() => setSelectedCompareZones([])}
        onSelectResult={(nextAnalysis: AnalysisResponse) => setAnalysis(nextAnalysis)}
      />

      <main className="main-content-fluid">
        <AnimatePresence mode="wait">
          {loading ? (
            <motion.div
              key="loading"
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.94, filter: 'blur(8px)' }}
              transition={{ duration: 0.4 }}
              className="loading-panel glass-panel"
            >
              {/* Orbital rings loader */}
              <div className="orbital-loader">
                <motion.div className="orbital-ring ring-1"
                  animate={{ rotate: 360 }}
                  transition={{ duration: 2.2, repeat: Infinity, ease: 'linear' }}
                />
                <motion.div className="orbital-ring ring-2"
                  animate={{ rotate: -360 }}
                  transition={{ duration: 3.4, repeat: Infinity, ease: 'linear' }}
                />
                <motion.div className="orbital-ring ring-3"
                  animate={{ rotate: 360 }}
                  transition={{ duration: 5, repeat: Infinity, ease: 'linear' }}
                />
                <motion.div className="orbital-core"
                  animate={{ scale: [1, 1.12, 1] }}
                  transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
                >
                  <Hexagon size={26} className="text-teal" />
                </motion.div>
              </div>
              <motion.div
                className="loader-text text-gradient"
                animate={{ opacity: [0.6, 1, 0.6] }}
                transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
              >
                Analysing Ecosystem...
              </motion.div>
              <div className="loader-subtext">Fetching live satellite and climate signals</div>
            </motion.div>
          ) : analysis ? (
            <motion.div
              key="dashboard"
              variants={containerVariants}
              initial="hidden"
              animate="visible"
              exit={{ opacity: 0, scale: 0.97, filter: 'blur(6px)' }}
              className="dashboard-bento-layout"
            >
              {/* Header/Hero KPI Card */}
              <motion.div variants={itemVariants} className="hero-card glass-panel">
                <div className="hero-info">
                  <span className="eyebrow">Selected Zone</span>
                  <h2 className="text-gradient">
                    {analysis.zone_id} — {analysis.displayName ? regionLabel(analysis.displayName) : 'Custom Zone'}
                  </h2>
                  <p className="hero-meta">
                    Lat {Number(analysis.latitude).toFixed(4)} | Lon {Number(analysis.longitude).toFixed(4)} | {formatDate(analysis.analysed_at)}
                  </p>
                  
                  <div className="hero-kpis">
                    <div className="kpi-item">
                      <span className="kpi-label">Stress</span>
                      <strong className="kpi-value">
                        <AnimatedCounter value={stressVal} suffix="%" />
                      </strong>
                      <span className="kpi-sublabel">index</span>
                    </div>
                    <div className="kpi-item">
                      <span className="kpi-label">Habitat</span>
                      <strong className="kpi-value highlight-teal">
                        <AnimatedCounter value={Number(analysis.habitat_suitability_score) || 0} decimals={1} />
                      </strong>
                      <span className="kpi-sublabel">suitability</span>
                    </div>
                    <div className="kpi-item">
                      <span className="kpi-label">Simulator</span>
                      <strong className="kpi-value highlight-amber">
                        {simResults ? <><span>+</span><AnimatedCounter value={simResults.activityGain} /></> : '--'}
                      </strong>
                      <span className="kpi-sublabel">projected gain</span>
                    </div>
                  </div>

                  <div className="report-actions">
                    <motion.button className="btn-action primary" onClick={triggerDownload}
                      whileHover={{ scale: 1.04, boxShadow: '0 0 18px rgba(255,255,255,0.2)' }}
                      whileTap={{ scale: 0.97 }}
                    >
                      <FileText size={16} />
                      <span>Download Report</span>
                    </motion.button>
                    <motion.button className="btn-action secondary" onClick={triggerPrint}
                      whileHover={{ scale: 1.04, borderColor: 'var(--border-light)' }}
                      whileTap={{ scale: 0.97 }}
                    >
                      <Printer size={16} />
                      <span>Print Report</span>
                    </motion.button>
                  </div>
                </div>

                <motion.div className="hero-ring-card"
                  initial={{ scale: 0.7, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ type: 'spring', stiffness: 160, damping: 22, delay: 0.2 }}
                >
                  <div className="ring-svg-wrapper">
                    <svg viewBox="0 0 160 160" className="metric-ring">
                      <circle className="ring-track" cx="80" cy="80" r="64" fill="none" />
                      <motion.circle
                        className="ring-progress"
                        cx="80" cy="80" r="64" fill="none"
                        strokeDasharray="402.1"
                        initial={{ strokeDashoffset: 402.1, opacity: 0 }}
                        animate={{ strokeDashoffset: 402.1 - (402.1 * (Number(analysis.activity_score) / 100)), opacity: 1 }}
                        transition={{ duration: 1.6, ease: [0.4, 0, 0.2, 1], delay: 0.3 }}
                        strokeLinecap="round"
                        style={{
                          stroke: Number(analysis.activity_score) >= 75 ? 'var(--accent-emerald)' : Number(analysis.activity_score) >= 55 ? 'var(--accent-amber)' : 'var(--accent-rose)',
                          filter: `drop-shadow(0 0 10px ${Number(analysis.activity_score) >= 75 ? 'rgba(16,185,129,0.6)' : Number(analysis.activity_score) >= 55 ? 'rgba(245,158,11,0.6)' : 'rgba(244,63,94,0.6)'})`
                        }}
                      />
                    </svg>
                    <div className="ring-value-content">
                      <ScoreDisplay analysis={analysis} />
                    </div>
                  </div>
                </motion.div>
              </motion.div>

              <motion.div variants={itemVariants} className="bento-card glass-panel span-3">
                <PhenologyCalendar zoneId={analysis.zone_id} anomalies={analysis.anomalies || []} />
              </motion.div>

              {/* Stress Drivers Breakdown */}
              <motion.div variants={itemVariants} className="bento-card glass-panel span-2 span-2-desktop"
                whileHover={{ y: -5, boxShadow: '0 20px 48px rgba(0,0,0,0.45), 0 0 0 1px rgba(20,184,166,0.12)' }}
                transition={{ type: 'spring', stiffness: 280, damping: 22 }}
              >
                <div className="bento-header">
                  <div>
                    <span className="eyebrow">Drivers</span>
                    <h3>Factor Stress Breakdown</h3>
                  </div>
                  <WindStressIndicator analysis={analysis} />
                </div>
                <StressInsights analysis={analysis} />
                <div className="stress-breakdown-content">
                  <div className="factor-list">
                    {Object.entries(FACTOR_META).map(([key, meta], fIdx) => {
                      const val = analysis._meta?.raw_factor_stress?.[key] || 0;
                      const pct = Math.round(Number(val) * 100);
                      return (
                        <motion.div key={key} className="factor-item-row"
                          initial={{ x: -24, opacity: 0 }}
                          animate={{ x: 0, opacity: 1 }}
                          transition={{ delay: fIdx * 0.08, type: 'spring', stiffness: 240, damping: 26 }}
                        >
                          <div className="factor-label-info">
                            <strong>{meta.label}</strong>
                            <small>{meta.weight}% model weight</small>
                          </div>
                          <div className="factor-bar-bg">
                            <motion.div
                              className="factor-bar-fill"
                              style={{ background: meta.color, boxShadow: `0 0 8px ${meta.color}55` }}
                              initial={{ width: 0 }}
                              animate={{ width: `${pct}%` }}
                              transition={{ duration: 1.1, ease: [0.4, 0, 0.2, 1], delay: 0.2 + fIdx * 0.08 }}
                            />
                          </div>
                          <motion.strong className="factor-pct-value"
                            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                            transition={{ delay: 0.4 + fIdx * 0.08 }}
                          >
                            {pct}%
                          </motion.strong>
                        </motion.div>
                      );
                    })}
                  </div>
                  <div className="radar-chart-section">
                    <FactorRadar factors={analysis._meta?.raw_factor_stress || {}} />
                    <div className="radar-chart-caption">
                      <Shield size={12} className="text-teal" />
                      <span>Stress Contribution Overlay</span>
                    </div>
                  </div>
                </div>
              </motion.div>

              {/* Recommendations (AI Fertility Insights) */}
              <motion.div variants={itemVariants} className="bento-card glass-panel"
                whileHover={{ y: -5, boxShadow: '0 20px 48px rgba(0,0,0,0.4), 0 0 0 1px rgba(16,185,129,0.1)' }}
                transition={{ type: 'spring', stiffness: 280, damping: 22 }}
              >
                <div className="bento-header">
                  <div>
                    <span className="eyebrow">Recommendations & Execution</span>
                    <h3>Interventions Plan</h3>
                  </div>
                  <span className="tag">GenAI Source</span>
                </div>
                <div className="roadmap-interventions">
                  <div className="insight-callout-card positive">
                    <div className="callout-icon text-green"><Leaf size={18} /></div>
                    <div className="callout-body">
                      <h4>How to Increase Pollination</h4>
                      <p>{analysis.biodiversity_insight || 'No insight returned.'}</p>
                    </div>
                  </div>
                  <div className="insight-callout-card warning">
                    <div className="callout-icon text-amber"><Zap size={18} /></div>
                    <div className="callout-body">
                      <h4>Top Action to Boost Fertility</h4>
                      <p>{analysis.top_intervention || 'No action returned.'}</p>
                    </div>
                  </div>
                  {Array.isArray(analysis.pollination_boost_actions) && analysis.pollination_boost_actions.length > 0 && (
                    <div className="insight-callout-card info">
                      <div className="callout-icon text-blue"><Bug size={18} /></div>
                      <div className="callout-body">
                        <h4>3 More Steps to Support Pollination</h4>
                        <ol className="boost-ol-list">
                          {analysis.pollination_boost_actions.map((act: string, aIdx: number) => (
                            <motion.li key={aIdx}
                              initial={{ x: -12, opacity: 0 }}
                              animate={{ x: 0, opacity: 1 }}
                              transition={{ delay: 0.1 + aIdx * 0.12, type: 'spring', stiffness: 240, damping: 24 }}
                            >{act}</motion.li>
                          ))}
                        </ol>
                      </div>
                    </div>
                  )}
                  <InterventionPlan analysis={analysis} />
                </div>
              </motion.div>

              {/* Managed Hive Placement */}
              <motion.div variants={itemVariants} className="bento-card glass-panel"
                 whileHover={{ y: -5, boxShadow: '0 20px 48px rgba(0,0,0,0.4), 0 0 0 1px rgba(245,158,11,0.1)' }}
                 transition={{ type: 'spring', stiffness: 280, damping: 22 }}>
                 <div className="bento-header">
                   <div>
                     <span className="eyebrow">Action</span>
                     <h3>Managed Hive Placement</h3>
                   </div>
                 </div>
                 <HivePlacementCard advice={analysis.decision_brief?.hive_placement} />
              </motion.div>

              {/* Actions Taken */}
              <motion.div variants={itemVariants} className="bento-card glass-panel"
                 whileHover={{ y: -5, boxShadow: '0 20px 48px rgba(0,0,0,0.4), 0 0 0 1px rgba(59,130,246,0.1)' }}
                 transition={{ type: 'spring', stiffness: 280, damping: 22 }}>
                 <div className="bento-header">
                   <div>
                     <span className="eyebrow">Log</span>
                     <h3>Actions Taken</h3>
                   </div>
                 </div>
                 <ActionsTakenLog zoneId={analysis.zone_id} />
              </motion.div>

              {/* Intervention Simulator */}
              <motion.div variants={itemVariants} className="bento-card glass-panel span-2"
                whileHover={{ y: -5, boxShadow: '0 20px 48px rgba(0,0,0,0.4), 0 0 0 1px rgba(245,158,11,0.1)' }}
                transition={{ type: 'spring', stiffness: 280, damping: 22 }}
              >
                <div className="bento-header">
                  <div>
                    <span className="eyebrow">Modelling</span>
                    <h3>Intervention Simulator</h3>
                  </div>
                  <span className="tag highlight-amber">{selectedScenarios.length} Scenario Selected</span>
                </div>
                <div className="simulator-body-layout">
                  <div className="simulator-controls">
                    <p className="simulator-desc">Toggle scenarios below to evaluate ecosystem recovery projection:</p>
                    <div className="scenarios-checkbox-list">
                      {INTERVENTION_SCENARIOS.map((scenario, sIdx) => (
                        <motion.label key={scenario.id} className="scenario-checkbox-item glass-panel"
                          initial={{ opacity: 0, x: -16 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: sIdx * 0.07, type: 'spring', stiffness: 220, damping: 24 }}
                          whileHover={{ scale: 1.02, borderColor: 'rgba(245,158,11,0.3)' }}
                          whileTap={{ scale: 0.98 }}
                        >
                          <input
                            type="checkbox"
                            value={scenario.id}
                            checked={selectedScenarios.includes(scenario.id)}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedScenarios([...selectedScenarios, scenario.id]);
                              } else {
                                setSelectedScenarios(selectedScenarios.filter(id => id !== scenario.id));
                              }
                            }}
                          />
                          <div className="checkbox-info">
                            <span className="checkbox-label">{scenario.label}</span>
                            <span className="checkbox-meta">{scenario.cost} cost • {scenario.time} window</span>
                          </div>
                        </motion.label>
                      ))}
                    </div>
                  </div>

                  <div className="simulator-output-card glass-panel">
                    <div className="sim-meters-row">
                      <div className="sim-val-box">
                        <span>Current</span>
                        <strong>{simResults?.currentActivity}</strong>
                        <em>activity</em>
                      </div>
                      <div className="sim-val-box">
                        <span>Projected</span>
                        <strong className="text-green">{simResults?.projectedActivity}</strong>
                        <em>activity</em>
                      </div>
                      <div className="sim-val-box">
                        <span>Stress Cut</span>
                        <strong className="text-amber">-{simResults?.stressDrop}%</strong>
                        <em>relative</em>
                      </div>
                    </div>

                    <div className="sim-dual-meter">
                      <div className="meter-track">
                        <motion.div className="meter-fill current"
                          initial={{ width: 0 }}
                          animate={{ width: `${simResults?.currentActivity || 0}%` }}
                          transition={{ duration: 0.9, ease: 'easeOut' }}
                        />
                        <motion.div className="meter-fill projected"
                          initial={{ width: 0 }}
                          animate={{ width: `${simResults?.projectedActivity || 0}%` }}
                          transition={{ duration: 1.2, ease: 'easeOut', delay: 0.15 }}
                        />
                      </div>
                    </div>

                    <div className="sim-factor-changes scrollable-area">
                      {simResults?.factorChanges && simResults.factorChanges.length > 0 ? (
                        simResults.factorChanges.map((item: any, fIdx: number) => {
                          const meta = FACTOR_META[item.factor];
                          return (
                            <div key={fIdx} className="sim-factor-change-row">
                              <span>{meta ? meta.label : item.factor}</span>
                              <strong>{item.before}% → {item.after}%</strong>
                            </div>
                          );
                        })
                      ) : (
                        <div className="empty-sim-state">Select interventions to model stress reduction</div>
                      )}
                    </div>
                    <p className="sim-disclaimer-note">{simResults?.note}</p>
                  </div>
                </div>
              </motion.div>

              {/* Pollination Trends */}
              <motion.div variants={itemVariants} className="bento-card glass-panel"
                whileHover={{ y: -5, boxShadow: '0 20px 48px rgba(0,0,0,0.4), 0 0 0 1px rgba(16,185,129,0.1)' }}
                transition={{ type: 'spring', stiffness: 280, damping: 22 }}
              >
                <div className="bento-header">
                  <div>
                    <span className="eyebrow">Trends</span>
                    <h3>Pollination Signals</h3>
                  </div>
                  <span className="tag">12-Week Visitation</span>
                </div>
                <div className="pollination-trend-content">
                  <div className="visitation-sparkline-card glass-panel">
                    <div className="sparkline-header">
                      <span>12-week visitation trend</span>
                      <TrendingUp size={14} className="text-green" />
                    </div>
                    <TrendSparkline values={analysis._meta?.visitation_summary?.twelve_week_visits_per_hour || []} />
                  </div>
                  <PollinationMetrics summary={analysis._meta?.visitation_summary || {}} />
                </div>
              </motion.div>

              {/* Crop Risk Assessment */}
              <motion.div variants={itemVariants} className="bento-card glass-panel span-2"
                whileHover={{ y: -5, boxShadow: '0 20px 48px rgba(0,0,0,0.4), 0 0 0 1px rgba(59,130,246,0.1)' }}
                transition={{ type: 'spring', stiffness: 280, damping: 22 }}
              >
                <div className="bento-header">
                  <div>
                    <span className="eyebrow">Exposure</span>
                    <h3>Crop Risk Assessment</h3>
                  </div>
                  <span className="tag">
                    {analysis.crop_risk ? Object.keys(analysis.crop_risk).length : 0} Crops
                  </span>
                </div>
                <CropRiskCards analysis={analysis} />
              </motion.div>

              {/* Anomaly Feed alerts */}
              <motion.div variants={itemVariants} className="bento-card glass-panel"
                whileHover={{ y: -5, boxShadow: '0 20px 48px rgba(0,0,0,0.4), 0 0 0 1px rgba(244,63,94,0.12)' }}
                transition={{ type: 'spring', stiffness: 280, damping: 22 }}
              >
                <div className="bento-header">
                  <div>
                    <span className="eyebrow">Alerts</span>
                    <h3>Anomaly Feed</h3>
                  </div>
                  <span className="tag highlight-rose">
                    {displayAnomalies.length} Alerts
                  </span>
                </div>
                <div className="anomaly-feed-list scrollable-area">
                  {displayAnomalies && displayAnomalies.length > 0 ? (
                    displayAnomalies.map((anomaly: any, aIdx: number) => (
                      <motion.div key={aIdx} className="anomaly-alert-item glass-panel"
                        initial={{ opacity: 0, y: 16, scale: 0.97 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        transition={{ delay: aIdx * 0.1, type: 'spring', stiffness: 220, damping: 24 }}
                        whileHover={{ scale: 1.015, borderColor: 'rgba(244,63,94,0.25)' }}
                      >
                        {anomaly.factor === 'pesticide_exposure' && floweringActive && (
                          <div className="flowering-alert-pill" style={{ marginBottom: '8px' }}>⚠ Active flowering window</div>
                        )}
                        <div className="anomaly-alert-header">
                          <motion.span className={`severity-badge ${anomaly.severity.toLowerCase()}`}
                            animate={{ opacity: [1, 0.65, 1] }}
                            transition={{ duration: 2.5, repeat: Infinity, ease: 'easeInOut', delay: aIdx * 0.4 }}
                          >
                            {anomaly.severity}
                          </motion.span>
                          <strong className="anomaly-title-factor">
                            {anomaly.factor.replace('_', ' ')} — {anomaly.variable}
                          </strong>
                        </div>
                        <p className="anomaly-desc">{anomaly.description}</p>
                        <div className="anomaly-action-box">
                          <strong>Action:</strong> {anomaly.recommended_action}
                        </div>
                      </motion.div>
                    ))
                  ) : (
                    <div className="empty-anomalies-state">
                      <AlertTriangle size={32} className="text-muted" style={{ marginBottom: '12px' }} />
                      <p>No anomalies detected in the current zone.</p>
                    </div>
                  )}
                </div>
              </motion.div>

              {/* Model Note / Disclaimer */}
              <motion.div variants={itemVariants} className="bento-card glass-panel span-3 model-limitations-footer">
                <div className="limitation-info">
                  <Info size={14} className="text-muted" />
                  <p>
                    <strong>Model note:</strong> {analysis._meta?.model_limitations || 'Scores are estimated decision-support bands.'}
                  </p>
                </div>
                {Array.isArray(analysis._meta?.data_caveats) && analysis._meta.data_caveats.filter(Boolean).length > 0 && (
                  <div className="caveat-box-footer">
                    <span><strong>Caveat:</strong> {analysis._meta.data_caveats.filter(Boolean)[0]}</span>
                  </div>
                )}
              </motion.div>

            </motion.div>
          ) : (
            <motion.div
              key="empty"
              initial={{ opacity: 0, scale: 0.92, y: 24 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96 }}
              transition={{ type: 'spring', stiffness: 180, damping: 24 }}
              className="dashboard-empty-panel glass-panel"
            >
              <motion.div
                animate={{ y: [0, -12, 0], rotate: [0, 8, -8, 0] }}
                transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
              >
                <Hexagon size={90} className="empty-brand-icon text-gradient" />
              </motion.div>
              <h2>Select an ecological zone to begin</h2>
              <p>Search for a location using the bar above, or open the side drawer controls to select a preset zone.</p>
              <motion.button className="select-zone-button text-gradient" onClick={() => setDrawerOpen(true)}
                whileHover={{ scale: 1.06, boxShadow: '0 0 28px rgba(16,185,129,0.4)' }}
                whileTap={{ scale: 0.97 }}
              >
                Open Zone Selection
              </motion.button>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
      
      {/* Agricultural Chatbot Overlay */}
      <Chatbot />
    </div>
  );
}

export default App;
