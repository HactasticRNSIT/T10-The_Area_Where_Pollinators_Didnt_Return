'use strict';

const FACTOR_META = {
  pesticide_exposure: { label: 'Pesticides', weight: 32, color: '#ef5b64' },
  soil_fertility: { label: 'Soil', weight: 23, color: '#f2b84b' },
  floral_diversity: { label: 'Floral Diversity', weight: 17, color: '#48d597' },
  climate_variability: { label: 'Climate', weight: 12, color: '#6aa8ff' },
  nesting_availability: { label: 'Nesting', weight: 8, color: '#a890ff' },
  pollination_factor: { label: 'Pollination', weight: 8, color: '#4dd6d0' },
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
    data.zones.forEach((zone) => {
      const button = document.createElement('button');
      button.className = 'zone-item';
      button.type = 'button';
      button.textContent = `${zone.zone_id} - ${zone.name}`;
      button.title = `${zone.lat}, ${zone.lon}`;
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
    item.classList.toggle('active', item.textContent.startsWith(`${zoneId} `));
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
  renderSources(data._meta?.data_sources || {}, data._meta?.data_quality || {});
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
    <h4>Biodiversity Insight</h4>
    <p>${escapeHtml(data.biodiversity_insight || 'No insight returned.')}</p>
    <h4>Top Intervention</h4>
    <p>${escapeHtml(data.top_intervention || 'No intervention returned.')}</p>
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
  const values = [
    ['Average visits/hour', summary.avg_visitations_per_hour],
    ['Expected visits/hour', summary.expected_visitations_per_hour],
    ['Visitation ratio', formatRatio(summary.visitation_ratio)],
    ['12-week decline', formatRatio(summary.decline_rate_12w)],
    ['Timing disruption', formatRatio(summary.pollination_timing_disruption)],
    ['Flowering success', formatRatio(summary.flowering_success_rate)],
    ['12-week visits/hour', Array.isArray(summary.twelve_week_visits_per_hour) ? summary.twelve_week_visits_per_hour.join(', ') : null],
  ];
  detail.innerHTML = values.map(([label, value]) => `
    <div class="detail-item">
      <span>${label}</span>
      <strong>${value == null ? '--' : escapeHtml(String(value))}</strong>
    </div>
  `).join('');
}

function renderSources(sources, quality) {
  const strip = document.getElementById('source-strip');
  strip.innerHTML = Object.entries(sources).map(([key, source]) => (
    `<span class="source-chip">${escapeHtml(titleCase(key))}: ${escapeHtml(formatSource(source, quality[key]))}</span>`
  )).join('');
}

function formatSource(source, quality) {
  const shortName = String(source || 'unknown')
    .replaceAll('_', ' ')
    .replace('modelled visitation', 'visitation model');
  return `${shortName} / ${quality || 'unknown'}`;
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
