'use strict';

const FACTOR_META = {
  pesticide_exposure: { label: 'Pesticides', weight: 32, color: '#ff6a5f' },
  soil_fertility: { label: 'Soil', weight: 23, color: '#e0b44f' },
  floral_diversity: { label: 'Floral Diversity', weight: 17, color: '#79ff9f' },
  climate_variability: { label: 'Climate', weight: 12, color: '#8ec7ff' },
  nesting_availability: { label: 'Nesting', weight: 8, color: '#c7ff7a' },
  pollination_factor: { label: 'Pollination', weight: 8, color: '#48f5c7' },
};

let activeZoneId = '';

document.addEventListener('DOMContentLoaded', () => {
  loadZones();
  checkHealth();
  document.getElementById('custom-zone-form').addEventListener('submit', handleCustomSubmit);
});

async function checkHealth() {
  const status = document.getElementById('api-status');
  try {
    const res = await fetch('/health');
    if (!res.ok) throw new Error('API health failed');
    status.textContent = 'API online';
    status.style.color = 'var(--green)';
  } catch {
    status.textContent = 'API offline';
    status.style.color = 'var(--red)';
  }
}

async function loadZones() {
  const list = document.getElementById('zone-list');
  list.innerHTML = '<p class="empty">Loading zones...</p>';
  try {
    const res = await fetch('/zones');
    if (!res.ok) throw new Error('Could not load zones');
    const data = await res.json();
    list.innerHTML = '';
    data.zones.forEach((zone, index) => {
      const button = document.createElement('button');
      button.className = 'zone-item';
      button.type = 'button';
      button.title = `${zone.lat}, ${zone.lon}`;
      button.dataset.zoneId = zone.zone_id;
      button.innerHTML = `
        <span class="zone-card-top">
          <strong>${escapeHtml(zone.zone_id)}</strong>
          <small>${escapeHtml(regionLabel(zone.name))}</small>
        </span>
        <span class="zone-card-name">${escapeHtml(zone.name)}</span>
        ${zoneSparkline(index)}
      `;
      button.addEventListener('click', () => runAnalysis(zone.zone_id, zone.lat, zone.lon, zone.name));
      list.appendChild(button);
    });
  } catch (error) {
    list.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`;
  }
}

function handleCustomSubmit(event) {
  event.preventDefault();
  const zoneId = document.getElementById('custom-zone-id').value.trim() || 'CUSTOM_ZONE';
  const lat = Number(document.getElementById('custom-lat').value);
  const lon = Number(document.getElementById('custom-lon').value);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    alert('Enter valid latitude and longitude values.');
    return;
  }
  runAnalysis(zoneId, lat, lon, `${lat.toFixed(4)}, ${lon.toFixed(4)}`);
}

async function runAnalysis(zoneId, lat, lon, name) {
  activeZoneId = zoneId;
  setLoading(true);
  markActiveZone(zoneId);
  try {
    const params = new URLSearchParams({ zone_id: zoneId, lat: String(lat), lon: String(lon) });
    const res = await fetch(`/analyse?${params.toString()}`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    renderDashboard(data, name);
    checkHealth();
  } catch (error) {
    alert(`Analysis failed: ${error.message}`);
  } finally {
    setLoading(false);
  }
}

function setLoading(isLoading) {
  const button = document.getElementById('analyse-btn');
  button.disabled = isLoading;
  button.textContent = isLoading ? 'Analysing...' : 'Analyse Zone';
}

function markActiveZone(zoneId) {
  document.querySelectorAll('.zone-item').forEach((item) => {
    item.classList.toggle('active', item.dataset.zoneId === zoneId);
  });
}

function renderDashboard(data, displayName) {
  document.getElementById('zone-title').textContent = `${data.zone_id} - ${displayName || 'Custom zone'}`;
  document.getElementById('zone-meta').textContent =
    `Lat ${Number(data.latitude).toFixed(4)} | Lon ${Number(data.longitude).toFixed(4)} | ${formatDate(data.analysed_at)}`;
  document.getElementById('activity-score').textContent = Number(data.activity_score).toFixed(1);
  document.getElementById('activity-label').textContent = data.activity_label;
  document.getElementById('stress-index').textContent = data.pollination_stress_index;
  document.getElementById('habitat-score').textContent = Number(data.habitat_suitability_score).toFixed(1);

  renderFactors(data._meta?.raw_factor_stress || {});
  renderCropTable(data.crop_risk || {}, data.crop_dependency || {});
  renderInsights(data);
  renderAnomalies(data.anomalies || []);
  renderPollinationDetail(data._meta?.visitation_summary || {});
  renderMethodNote(data._meta || {});
}

function renderFactors(factors) {
  const grid = document.getElementById('factor-grid');
  grid.innerHTML = '';
  Object.entries(FACTOR_META).forEach(([key, meta]) => {
    const stress = Number(factors[key] || 0);
    const percent = Math.round(stress * 100);
    const card = document.createElement('article');
    card.className = 'factor-card';
    card.innerHTML = `
      <div class="factor-head">
        <h3>${meta.label}</h3>
        <div class="weight">${meta.weight}% model weight</div>
      </div>
      <span>Estimated stress level</span>
      <div class="meter"><div class="meter-fill" style="width:${percent}%;background:${meta.color}"></div></div>
      <div class="factor-score">${escapeHtml(stressBand(stress))}</div>
      <div class="factor-range">${stressRange(percent)}</div>
    `;
    grid.appendChild(card);
  });
}

function renderCropTable(cropRisk, cropDependency) {
  const tbody = document.getElementById('crop-tbody');
  const crops = Object.keys(cropRisk);
  document.getElementById('crop-count').textContent = `${crops.length} crops`;
  if (crops.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="empty">No crop risk data returned.</td></tr>';
    return;
  }
  tbody.innerHTML = crops.map((crop) => {
    const risk = cropRisk[crop] || '--';
    const dependency = cropDependency[crop] == null ? '--' : `est. ${Math.round(cropDependency[crop] * 100)}%`;
    return `
      <tr>
        <td>${escapeHtml(titleCase(crop))}</td>
        <td>${dependency}</td>
        <td><span class="risk-badge ${risk.toLowerCase()}">${escapeHtml(risk)}</span></td>
      </tr>
    `;
  }).join('');
}

function renderMethodNote(meta) {
  const note = document.getElementById('method-note');
  const text = meta.model_limitations ||
    'Scores are estimated decision-support bands from mixed live, modelled, and surrogate inputs; they are not calibrated farm-level sensor measurements.';
  note.innerHTML = `
    <strong>Model note</strong>
    <span>${escapeHtml(text)}</span>
  `;
}

function renderInsights(data) {
  document.getElementById('insight-source').textContent = data._meta?.insight_source || '--';
  document.getElementById('ai-content').innerHTML = `
    <article class="insight-callout biodiversity">
      <div class="insight-icon" aria-hidden="true">BI</div>
      <div>
        <h4>Biodiversity Insight</h4>
        <p>${escapeHtml(data.biodiversity_insight || 'No insight returned.')}</p>
      </div>
    </article>
    <article class="insight-callout intervention">
      <div class="arrow-mark" aria-hidden="true"></div>
      <div>
        <h4>Top Intervention</h4>
        <p>${escapeHtml(data.top_intervention || 'No intervention returned.')}</p>
      </div>
    </article>
  `;
}

function renderAnomalies(anomalies) {
  const feed = document.getElementById('anomaly-feed');
  document.getElementById('anomaly-count').textContent = `${anomalies.length} alerts`;
  if (anomalies.length === 0) {
    feed.innerHTML = '<p class="empty">No anomalies detected.</p>';
    return;
  }
  feed.innerHTML = anomalies.map((item) => `
    <article class="alert">
      <span class="severity ${item.severity.toLowerCase()}">${escapeHtml(item.severity)}</span>
      <h4>${escapeHtml(titleCase(item.factor.replaceAll('_', ' ')))} - ${escapeHtml(item.variable)}</h4>
      <p>${escapeHtml(item.description)}</p>
      <p><strong>Action:</strong> ${escapeHtml(item.recommended_action)}</p>
    </article>
  `).join('');
}

function renderPollinationDetail(summary) {
  const detail = document.getElementById('pollination-detail');
  const trend = Array.isArray(summary.twelve_week_visits_per_hour)
    ? summary.twelve_week_visits_per_hour.map(Number).filter(Number.isFinite)
    : [];
  const values = [
    { label: 'Avg visits', value: Number(summary.avg_visitations_per_hour), display: formatNumber(summary.avg_visitations_per_hour), max: Math.max(Number(summary.expected_visitations_per_hour || 0), Number(summary.avg_visitations_per_hour || 0), 1) },
    { label: 'Expected', value: Number(summary.expected_visitations_per_hour), display: formatNumber(summary.expected_visitations_per_hour), max: Math.max(Number(summary.expected_visitations_per_hour || 0), Number(summary.avg_visitations_per_hour || 0), 1) },
    { label: 'Visit ratio', value: Number(summary.visitation_ratio), display: formatRatio(summary.visitation_ratio), max: 1 },
    { label: 'Decline', value: Number(summary.decline_rate_12w), display: formatRatio(summary.decline_rate_12w), max: 1 },
    { label: 'Timing', value: Number(summary.pollination_timing_disruption), display: formatRatio(summary.pollination_timing_disruption), max: 1 },
    { label: 'Flowering', value: Number(summary.flowering_success_rate), display: formatRatio(summary.flowering_success_rate), max: 1 },
  ];
  detail.innerHTML = `
    <div class="trend-card">
      <span>12-week visitation signal</span>
      ${trendSparkline(trend)}
    </div>
    <div class="pollination-bars">
      ${values.map((item, index) => pollinationBar(item, index)).join('')}
    </div>
  `;
}

function formatDate(value) {
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value || '';
  }
}

function formatRatio(value) {
  return value == null ? null : `${Math.round(Number(value) * 100)}%`;
}

function formatNumber(value) {
  return value == null || !Number.isFinite(Number(value)) ? '--' : Number(value).toFixed(1);
}

function stressBand(value) {
  if (value >= 0.75) return 'Severe';
  if (value >= 0.50) return 'High';
  if (value >= 0.25) return 'Moderate';
  return 'Low';
}

function stressRange(percent) {
  const low = Math.max(0, Math.floor(percent / 10) * 10);
  const high = Math.min(100, low + 10);
  return `${low}-${high}% score band`;
}

function regionLabel(name) {
  return String(name).split('—').pop().trim();
}

function zoneSparkline(index) {
  const points = Array.from({ length: 10 }, (_, step) => {
    const wave = Math.sin((step + index) * 0.9) * 8;
    const lift = ((index + step * 7) % 11) * 1.5;
    return 26 - Math.max(4, Math.min(24, 10 + wave + lift));
  });
  const d = points.map((y, x) => `${x * 10},${y.toFixed(1)}`).join(' ');
  return `
    <svg class="zone-spark" viewBox="0 0 90 28" aria-hidden="true">
      <polyline points="${d}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></polyline>
    </svg>
  `;
}

function trendSparkline(values) {
  if (values.length < 2) {
    return '<p class="empty">Trend appears after analysis.</p>';
  }
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = Math.max(max - min, 0.01);
  const points = values.map((value, index) => {
    const x = (index / (values.length - 1)) * 220;
    const y = 58 - ((value - min) / span) * 46;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return `
    <svg class="trend-spark" viewBox="0 0 220 64" role="img" aria-label="12-week visitation trend">
      <polyline points="${points}" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline>
      <polyline points="${points} 220,64 0,64" fill="currentColor" opacity="0.08"></polyline>
    </svg>
  `;
}

function pollinationBar(item, index) {
  const value = Number.isFinite(item.value) ? Math.max(0, item.value) : 0;
  const max = Number.isFinite(item.max) && item.max > 0 ? item.max : 1;
  const height = Math.max(8, Math.min(100, (value / max) * 100));
  return `
    <div class="bar-metric" style="--bar-height:${height}%;--delay:${index * 90}ms">
      <svg viewBox="0 0 24 118" aria-hidden="true">
        <line x1="12" y1="108" x2="12" y2="${108 - height}" pathLength="100"></line>
      </svg>
      <strong>${escapeHtml(item.display || '--')}</strong>
      <span>${escapeHtml(item.label)}</span>
    </div>
  `;
}

function titleCase(value) {
  return String(value).replace(/\w\S*/g, (word) => word.charAt(0).toUpperCase() + word.slice(1));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}
