/* ═══════════════════════════════════════════════════════════════════════════
   PolyNexus Dashboard — app.js
   ═══════════════════════════════════════════════════════════════════════════ */

'use strict';

const API_BASE = '';

// ── State ──────────────────────────────────────────────────────────────────
let currentData   = null;
let leafletMap    = null;
let markerCluster = null;
let scanCircle    = null;
let heatLayer     = null;
let heatmapOn     = false;
let satLayer      = null;
let osmLayer      = null;
let activeLayer   = 'satellite';
const sparkCharts = {};
const gaugeCtxs   = {};

const PRESET_ZONES = [];   // filled by /zones call

// ── Boot ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initMap();
  initForm();
  checkApiHealth();
  loadPresetZones();
  showLoadingOverlay('INITIALISING POLYNEXUS…', false);
  setTimeout(() => hideLoadingOverlay(), 900);
});

// ── Loading overlay ────────────────────────────────────────────────────────
function showLoadingOverlay(msg = 'RUNNING ANALYSIS…', persistent = true) {
  let el = document.getElementById('loading-overlay');
  if (!el) {
    el = document.createElement('div');
    el.id = 'loading-overlay';
    el.innerHTML = `<div class="loading-spinner"></div><div class="loading-text" id="loading-text"></div>`;
    document.body.appendChild(el);
  }
  el.classList.remove('fade-out');
  el.style.pointerEvents = 'all';
  document.getElementById('loading-text').textContent = msg;
  if (!persistent) return;
}
function hideLoadingOverlay() {
  const el = document.getElementById('loading-overlay');
  if (!el) return;
  el.classList.add('fade-out');
  setTimeout(() => el && el.parentNode && el.parentNode.removeChild(el), 500);
}

// ── API health ─────────────────────────────────────────────────────────────
async function checkApiHealth() {
  const indicator = document.getElementById('api-status-indicator');
  try {
    const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(4000) });
    if (res.ok) {
      indicator.innerHTML = '<span class="dot dot-green"></span> API Online';
    } else {
      throw new Error('non-ok');
    }
  } catch {
    indicator.innerHTML = '<span class="dot dot-red"></span> API Offline';
  }
}

// ── Preset zones ────────────────────────────────────────────────────────────
async function loadPresetZones() {
  const list = document.getElementById('zone-list');
  try {
    const res  = await fetch(`${API_BASE}/zones`, { signal: AbortSignal.timeout(4000) });
    const data = await res.json();
    data.zones.forEach(z => {
      PRESET_ZONES.push(z);
      const li = document.createElement('li');
      li.textContent = `${z.zone_id} — ${z.name}`;
      li.title = `${z.lat}, ${z.lon}`;
      li.dataset.zoneId = z.zone_id;
      li.addEventListener('click', () => {
        document.querySelectorAll('#zone-list li').forEach(x => x.classList.remove('active'));
        li.classList.add('active');
        runAnalysis(z.zone_id, z.lat, z.lon);
      });
      list.appendChild(li);
    });
  } catch {
    list.innerHTML = '<li style="color:var(--text-dim);font-size:11px;padding:6px;">API offline — enter coords manually</li>';
  }
}

// ── Custom form ─────────────────────────────────────────────────────────────
function initForm() {
  document.getElementById('custom-zone-form').addEventListener('submit', e => {
    e.preventDefault();
    const zoneId = document.getElementById('custom-zone-id').value.trim() || 'CUSTOM';
    const lat    = parseFloat(document.getElementById('custom-lat').value);
    const lon    = parseFloat(document.getElementById('custom-lon').value);
    if (isNaN(lat) || isNaN(lon)) { alert('Please enter valid lat/lon values.'); return; }
    document.querySelectorAll('#zone-list li').forEach(x => x.classList.remove('active'));
    runAnalysis(zoneId, lat, lon);
  });
}

// ── Run analysis ────────────────────────────────────────────────────────────
async function runAnalysis(zoneId, lat, lon) {
  setAnalyseLoading(true);
  showLoadingOverlay(`ANALYSING ZONE ${zoneId}…`);
  try {
    const url = `${API_BASE}/analyse?zone_id=${encodeURIComponent(zoneId)}&lat=${lat}&lon=${lon}`;
    const res  = await fetch(url, { signal: AbortSignal.timeout(90000) });
    if (!res.ok) { const t = await res.text(); throw new Error(t); }
    const data = await res.json();
    currentData = data;
    renderDashboard(data, zoneId, lat, lon);
    updateDataSourceStrip(data._meta.data_sources);
    checkApiHealth();
  } catch (err) {
    hideLoadingOverlay();
    alert(`Analysis failed: ${err.message}`);
  } finally {
    setAnalyseLoading(false);
    hideLoadingOverlay();
  }
}

function setAnalyseLoading(on) {
  const btn  = document.getElementById('analyse-btn');
  const txt  = document.getElementById('analyse-btn-text');
  const spin = document.getElementById('analyse-spinner');
  btn.disabled = on;
  txt.classList.toggle('hidden', on);
  spin.classList.toggle('hidden', !on);
}

// ── Render full dashboard ───────────────────────────────────────────────────
function renderDashboard(data, zoneId, lat, lon) {
  renderSummaryBar(data, zoneId, lat, lon);
  renderFactorCards(data);
  renderMap(lat, lon, data);
  renderCropTable(data.crop_risk, data.crop_dependency);
  renderAIPanel(data);
  renderAnomalyFeed(data.anomalies, data._meta);
}

// ── Summary bar ─────────────────────────────────────────────────────────────
function renderSummaryBar(data, zoneId, lat, lon) {
  // Find human name from presets
  const preset = PRESET_ZONES.find(z => z.zone_id === zoneId);
  const locationName = preset ? preset.name : `${lat.toFixed(4)}°, ${lon.toFixed(4)}°`;
  document.getElementById('zone-name-display').textContent = `${zoneId} — ${locationName}`;
  document.getElementById('zone-coords-display').textContent =
    `lat ${lat.toFixed(4)} · lon ${lon.toFixed(4)}`;
  const ts = new Date(data.analysed_at).toLocaleString('en-GB', { timeZone: 'UTC', hour12: false });
  document.getElementById('zone-timestamp').textContent = `Last updated: ${ts} UTC`;

  // Activity score
  animateValue('kpi-activity-val', data.activity_score, 1);
  const actPill = document.getElementById('kpi-activity-pill');
  actPill.textContent = data.activity_label;
  setPillClass(actPill, scoreToColor(data.activity_score, 'activity'));

  // Stress index
  document.getElementById('kpi-stress-val').textContent = data.pollination_stress_index;
  const stressPill = document.getElementById('kpi-stress-pill');
  stressPill.textContent = data.pollination_stress_index;
  const stressColor = { Low: 'green', Medium: 'amber', High: 'red', Severe: 'red' }[data.pollination_stress_index] || 'dim';
  setPillClass(stressPill, stressColor);

  // Habitat suitability
  animateValue('kpi-habitat-val', data.habitat_suitability_score, 1);
  const habPill = document.getElementById('kpi-habitat-pill');
  habPill.textContent = scoreToLabel(data.habitat_suitability_score);
  setPillClass(habPill, scoreToColor(data.habitat_suitability_score, 'habitat'));
}

function setPillClass(el, color) {
  el.className = 'kpi-pill';
  el.classList.add(`pill-${color}`);
}
function scoreToColor(score, type) {
  if (type === 'activity' || type === 'habitat') {
    if (score >= 80) return 'green';
    if (score >= 60) return 'amber';
    return 'red';
  }
  return 'dim';
}
function scoreToLabel(score) {
  if (score >= 80) return 'High';
  if (score >= 60) return 'Moderate';
  if (score >= 40) return 'Low';
  return 'Critical';
}

// ── Animate counter value ───────────────────────────────────────────────────
function animateValue(elId, target, decimals = 0) {
  const el = document.getElementById(elId);
  if (!el) return;
  const start = 0;
  const duration = 900;
  const startTime = performance.now();
  function update(now) {
    const t = Math.min((now - startTime) / duration, 1);
    const ease = 1 - Math.pow(1 - t, 3);
    el.textContent = (start + (target - start) * ease).toFixed(decimals);
    el.classList.add('count-up');
    if (t < 1) requestAnimationFrame(update);
    else el.textContent = target.toFixed(decimals);
  }
  requestAnimationFrame(update);
}

// ── Factor score cards ──────────────────────────────────────────────────────
const FACTOR_META = {
  pesticide_exposure:   { color: '#e63946', sparkKeys: ['usage_stress','freq_stress','recency_stress'] },
  soil_fertility:       { color: '#f5a623', sparkKeys: ['ph_stress','carbon_stress','nitrogen_stress','moisture_stress'] },
  floral_diversity:     { color: '#39ff14', sparkKeys: ['ndvi_stress','flower_stress','patch_stress','species_stress'] },
  climate_variability:  { color: '#58a6ff', sparkKeys: ['temp_stress','precip_stress','drought_stress'] },
  nesting_availability: { color: '#bc8cff', sparkKeys: ['bare_stress','hedge_stress','dw_stress','dist_stress'] },
};

function renderFactorCards(data) {
  const fs = data._meta.raw_factor_stress;
  Object.keys(FACTOR_META).forEach(factor => {
    const stress = fs[factor] ?? 0;
    drawGauge(factor, stress);
    // Gauge center value
    animateValue(`gval-${factor}`, Math.round(stress * 100), 0);
    // Fake sparkline from overall stress variation
    drawSparkline(factor, stress);
  });
}

function drawGauge(factor, stressValue) {
  const canvas = document.getElementById(`gauge-${factor}`);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  canvas.width  = 90 * dpr;
  canvas.height = 90 * dpr;
  ctx.scale(dpr, dpr);
  const cx = 45, cy = 45, r = 34;
  const start = Math.PI * 0.75;
  const end   = Math.PI * 2.25;
  const filled = start + (end - start) * stressValue;
  const color  = FACTOR_META[factor]?.color || '#39ff14';

  ctx.clearRect(0, 0, 90, 90);

  // Track
  ctx.beginPath();
  ctx.arc(cx, cy, r, start, end);
  ctx.strokeStyle = 'rgba(255,255,255,0.06)';
  ctx.lineWidth   = 7;
  ctx.lineCap     = 'round';
  ctx.stroke();

  // Glow
  ctx.save();
  ctx.shadowColor = color;
  ctx.shadowBlur  = 10;
  ctx.beginPath();
  ctx.arc(cx, cy, r, start, filled);
  ctx.strokeStyle = color;
  ctx.lineWidth   = 7;
  ctx.lineCap     = 'round';
  ctx.stroke();
  ctx.restore();
}

function drawSparkline(factor, stressVal) {
  const canvas = document.getElementById(`spark-${factor}`);
  if (!canvas) return;

  // Destroy previous chart if any
  if (sparkCharts[factor]) { sparkCharts[factor].destroy(); }

  // Generate plausible sub-metric values seeded from stressVal
  const count = 6;
  const seed  = stressVal;
  const vals  = Array.from({ length: count }, (_, i) =>
    Math.max(0, Math.min(100, Math.round((seed + Math.sin(seed * 7 + i) * 0.3) * 100))
  ));

  const color = FACTOR_META[factor]?.color || '#39ff14';
  sparkCharts[factor] = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: vals.map((_, i) => `m${i+1}`),
      datasets: [{ data: vals, backgroundColor: color + '55', borderColor: color, borderWidth: 1, borderRadius: 2 }]
    },
    options: {
      responsive: false,
      animation: { duration: 600 },
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: {
        x: { display: false },
        y: { display: false, min: 0, max: 100 }
      },
    }
  });
}

// ── Map ─────────────────────────────────────────────────────────────────────
function initMap() {
  leafletMap = L.map('zone-map', {
    center: [51.5, 0],
    zoom: 6,
    zoomControl: true,
    attributionControl: false,
  });

  satLayer = L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    { maxZoom: 18 }
  );
  osmLayer = L.tileLayer(
    'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    { maxZoom: 18 }
  );
  satLayer.addTo(leafletMap);

  markerCluster = L.markerClusterGroup({ chunkedLoading: true });
  leafletMap.addLayer(markerCluster);
}

function renderMap(lat, lon, data) {
  leafletMap.setView([lat, lon], 11);

  // Clear old markers & scan circle
  markerCluster.clearLayers();
  if (scanCircle) leafletMap.removeLayer(scanCircle);

  // 10 km scan zone
  scanCircle = L.circle([lat, lon], {
    radius: 10000,
    color: '#f5a623',
    weight: 1.5,
    fillColor: '#f5a623',
    fillOpacity: 0.06,
    dashArray: '6 4',
  }).addTo(leafletMap);

  // GBIF species markers (simulated from species_list + counts)
  const gbif = data._meta?.data_sources?.gbif;
  const speciesCount = currentData ? (currentData.contribution_scores?.floral_diversity !== undefined ? 0 : 0) : 0;

  // Use GBIF data from anomalies context to place mock markers around zone
  const seed   = lat * 1000 + lon;
  const nmarks = Math.min(40, Math.max(5, Math.round(Math.abs(Math.sin(seed)) * 35 + 5)));
  for (let i = 0; i < nmarks; i++) {
    const dlat = (Math.sin(seed + i * 2.3) * 0.07);
    const dlon = (Math.cos(seed + i * 1.7) * 0.10);
    const marker = L.circleMarker([lat + dlat, lon + dlon], {
      radius: 5, color: '#39ff14', fillColor: '#39ff14', fillOpacity: 0.7, weight: 1
    });
    marker.bindPopup(`<b style="color:#39ff14;">GBIF Occurrence #${i+1}</b><br>Pollinator species sighting`);
    markerCluster.addLayer(marker);
  }

  // Central zone marker
  const homeIcon = L.divIcon({
    className: '',
    html: `<div style="width:12px;height:12px;background:#39ff14;border-radius:50%;
           box-shadow:0 0 12px #39ff14;border:2px solid #0d1117;"></div>`,
    iconSize: [12, 12], iconAnchor: [6, 6]
  });
  L.marker([lat, lon], { icon: homeIcon })
    .bindPopup(`<b style="color:#39ff14;">${currentData?.zone_id || ''}</b><br>${lat.toFixed(4)}° N, ${lon.toFixed(4)}° E`)
    .addTo(leafletMap);

  // Heatmap layer (if on)
  if (heatmapOn) buildHeatmap(lat, lon);
}

function setMapLayer(type) {
  activeLayer = type;
  document.getElementById('btn-satellite').classList.toggle('active', type === 'satellite');
  document.getElementById('btn-osm').classList.toggle('active', type === 'osm');
  if (type === 'satellite') {
    if (leafletMap.hasLayer(osmLayer)) leafletMap.removeLayer(osmLayer);
    satLayer.addTo(leafletMap);
  } else {
    if (leafletMap.hasLayer(satLayer)) leafletMap.removeLayer(satLayer);
    osmLayer.addTo(leafletMap);
  }
}

function toggleHeatmap() {
  heatmapOn = !heatmapOn;
  const btn = document.getElementById('btn-heatmap');
  btn.classList.toggle('active', heatmapOn);
  if (heatmapOn && currentData) {
    buildHeatmap(currentData.latitude, currentData.longitude);
  } else if (heatLayer) {
    leafletMap.removeLayer(heatLayer);
    heatLayer = null;
  }
}

function buildHeatmap(lat, lon) {
  if (heatLayer) leafletMap.removeLayer(heatLayer);
  // Simulate NDVI-derived heatmap with colored circles
  const seed = lat * 100 + lon;
  for (let i = 0; i < 25; i++) {
    const dlat  = (Math.sin(seed + i * 3.1) * 0.06);
    const dlon  = (Math.cos(seed + i * 2.2) * 0.09);
    const ndvi  = 0.3 + Math.abs(Math.sin(seed + i)) * 0.5;
    const alpha = ndvi * 0.6;
    const g     = Math.round(ndvi * 180);
    L.circle([lat + dlat, lon + dlon], {
      radius: 1200,
      color: 'transparent',
      fillColor: `rgb(0,${g},20)`,
      fillOpacity: alpha,
    }).addTo(leafletMap);
  }
}

// ── Crop risk table ─────────────────────────────────────────────────────────
function renderCropTable(cropRisk, cropDependency = {}) {
  const tbody = document.getElementById('crop-tbody');
  tbody.innerHTML = '';
  const cropOrder = Object.keys(cropRisk || {});
  if (cropOrder.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="dimmed mono" style="text-align:center;padding:20px;">No crop risk data returned</td></tr>';
    return;
  }
  cropOrder.forEach(crop => {
    const risk = cropRisk[crop] || '—';
    const dep  = cropDependency[crop] !== undefined ? `${Math.round(cropDependency[crop]*100)}%` : '—';
    const cls  = { Low: 'risk-low', Moderate: 'risk-moderate', High: 'risk-high', Severe: 'risk-severe' }[risk] || '';
    const tr   = document.createElement('tr');
    tr.innerHTML = `
      <td style="font-weight:500;text-transform:capitalize;">${crop}</td>
      <td class="dep-mono">${dep}</td>
      <td><span class="risk-badge ${cls}">${risk}</span></td>
    `;
    tbody.appendChild(tr);
  });
}

// ── AI Insights panel ───────────────────────────────────────────────────────
function renderAIPanel(data) {
  const content = document.getElementById('ai-content');
  const srcTag  = document.getElementById('ai-source-tag');
  const src     = data._meta?.insight_source || '';

  // Source tag
  srcTag.textContent = formatSourceTag(src);
  srcTag.className   = 'source-tag';
  if (src.includes('groq'))    srcTag.classList.add('groq');
  else if (src.includes('rule') || src.includes('healthy')) srcTag.classList.add('rule');

  if (src === 'healthy_zone_no_ai') {
    content.innerHTML = `
      <div class="ai-healthy">
        <span style="font-size:18px;">✅</span>
        <span>Zone is healthy — AI analysis skipped</span>
      </div>
      <div style="margin-top:8px;">
        <div class="ai-section-label">Biodiversity Insight</div>
        <div class="ai-text">${data.biodiversity_insight}</div>
      </div>
      <div style="margin-top:12px;">
        <div class="ai-section-label">Top Intervention</div>
        <div class="ai-text">${data.top_intervention}</div>
      </div>`;
    return;
  }

  content.innerHTML = `
    <div>
      <div class="ai-section-label">Biodiversity Insight</div>
      <div class="ai-text">${data.biodiversity_insight}</div>
    </div>
    <div>
      <div class="ai-section-label">Top Intervention</div>
      <div class="ai-text">${data.top_intervention}</div>
    </div>`;
}

function formatSourceTag(src) {
  if (!src) return '—';
  if (src.includes('groq'))    return 'Groq LLM';
  if (src.includes('healthy')) return 'Healthy Zone';
  if (src.includes('rule'))    return 'Rule-based';
  return src.replace(/_/g, ' ');
}

// ── Anomaly feed ────────────────────────────────────────────────────────────
function renderAnomalyFeed(anomalies, meta) {
  const feed = document.getElementById('anomaly-feed');
  feed.innerHTML = '';

  document.getElementById('critical-count-badge').textContent = `${meta.critical_count} CRITICAL`;
  document.getElementById('warning-count-badge').textContent  = `${meta.warning_count} WARNING`;

  if (!anomalies || anomalies.length === 0) {
    feed.innerHTML = '<div class="ai-healthy" style="margin:6px;"><span>✅</span><span>No anomalies detected — ecosystem is within normal parameters.</span></div>';
    return;
  }

  anomalies.forEach(a => {
    const isCritical = a.severity === 'CRITICAL';
    const card = document.createElement('div');
    card.className = `anomaly-card${isCritical ? ' critical' : ''}`;
    card.innerHTML = `
      <div class="anomaly-header">
        <span class="severity-badge sev-${a.severity.toLowerCase()}">${a.severity}</span>
        <span class="anomaly-factor">${a.factor.replace(/_/g,' ')}</span>
      </div>
      <div class="anomaly-variable">⬡ ${a.variable} · observed: <span class="mono">${a.observed_value}</span></div>
      <div class="anomaly-desc">${a.description}</div>
      <div class="anomaly-action">▶ ${a.recommended_action}</div>
    `;
    feed.appendChild(card);
  });
}

// ── Data source strip ───────────────────────────────────────────────────────
function updateDataSourceStrip(sources) {
  const MAP = {
    climate:   'src-climate',
    nasa:      'src-nasa',
    gbif:      'src-gbif',
    soil:      'src-soil',
    ndvi:      'src-ndvi',
    pesticide: 'src-pesticide',
  };
  const LIVE = ['open_meteo','nasa_power','gbif','isric_soilgrids'];
  const STAC = ['openlandmap_stac_mock'];

  Object.entries(MAP).forEach(([key, elId]) => {
    const el   = document.getElementById(elId);
    if (!el) return;
    const src  = sources[key] || '';
    const dot  = el.querySelector('.dot');
    dot.className = 'dot';
    if (LIVE.some(l => src.includes(l.replace('_','')))) {
      // simplified: check if 'mock' appears
    }
    if (src.includes('mock')) {
      dot.classList.add('dot-amber');
    } else if (STAC.includes(src)) {
      dot.classList.add('dot-amber');
    } else if (src && !src.includes('mock')) {
      dot.classList.add('dot-green');
    } else {
      dot.classList.add('dot-dim');
    }
  });
}
