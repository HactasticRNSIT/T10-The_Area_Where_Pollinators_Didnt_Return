'use strict';

const FACTOR_META = {
  pesticide_exposure: { label: 'Pesticides', weight: 32, color: '#d96c58' },
  soil_fertility: { label: 'Soil', weight: 23, color: '#caa65a' },
  floral_diversity: { label: 'Floral Diversity', weight: 17, color: '#74c98d' },
  climate_variability: { label: 'Climate', weight: 12, color: '#88aac9' },
  nesting_availability: { label: 'Nesting', weight: 8, color: '#a6bf77' },
  pollination_factor: { label: 'Pollination', weight: 8, color: '#6fc6ad' },
};

let activeZoneId = '';
let latestAnalysis = null;
let latestDisplayName = '';
let loadingMessageTimer = null;

const LOADING_MESSAGES = [
  'Fetching live satellite and climate signals',
  'Checking species and visitation records',
  'Scoring ecosystem stress drivers',
  'Preparing decision support outputs',
];

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

document.addEventListener('DOMContentLoaded', () => {
  setupDrawer();
  loadZones();
  checkHealth();
  document.getElementById('custom-zone-form').addEventListener('submit', handleCustomSubmit);
  setupLocationSearch();
  document.getElementById('download-report-btn').addEventListener('click', downloadFarmerReport);
  document.getElementById('print-report-btn').addEventListener('click', printFarmerReport);
  setupPanelAnimations();
});

const STATE_MAP = {
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

function setupDrawer() {
  const toggle = document.getElementById('drawer-toggle');
  const closeButton = document.getElementById('drawer-close');
  const overlay = document.getElementById('drawer-overlay');
  const open = () => {
    document.body.classList.add('drawer-open');
    toggle.setAttribute('aria-expanded', 'true');
  };
  const close = () => {
    document.body.classList.remove('drawer-open');
    toggle.setAttribute('aria-expanded', 'false');
  };
  toggle.addEventListener('click', () => {
    if (document.body.classList.contains('drawer-open')) close();
    else open();
  });
  closeButton.addEventListener('click', close);
  overlay.addEventListener('click', close);
  window.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') close();
  });
}

function setupPanelAnimations() {
  const revealTargets = () => document.querySelectorAll('.panel, .factor-section');
  if (!('IntersectionObserver' in window)) {
    revealTargets().forEach((panel) => panel.classList.add('is-visible'));
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });
  revealTargets().forEach((panel, index) => {
    panel.style.transitionDelay = `${index * 45}ms`;
    observer.observe(panel);
  });
}

function refreshPanelAnimations() {
  const panels = [...document.querySelectorAll('.panel, .factor-section')];
  panels.forEach((panel, index) => {
    panel.classList.remove('is-visible');
    panel.style.transitionDelay = `${index * 45}ms`;
  });
  requestAnimationFrame(() => {
    panels.forEach((panel) => panel.classList.add('is-visible'));
  });
}

function setupLocationSearch() {
  const input = document.getElementById('location-search');
  const results = document.getElementById('search-results');
  let debounceTimer;

  input.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    const query = input.value.trim();
    if (query.length < 3) {
      results.classList.add('hidden');
      return;
    }
    debounceTimer = setTimeout(() => fetchSuggestions(query), 400);
  });

  document.addEventListener('click', (e) => {
    if (!input.contains(e.target) && !results.contains(e.target)) {
      results.classList.add('hidden');
    }
  });
}

async function fetchSuggestions(query) {
  const results = document.getElementById('search-results');
  try {
    const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&countrycodes=in&limit=5&addressdetails=1`);
    if (!res.ok) throw new Error('Search failed');
    const data = await res.json();
    if (data.length === 0) {
      results.innerHTML = '<p class="empty">No results found.</p>';
    } else {
      results.innerHTML = data.map(item => `
        <div class="search-item" data-lat="${item.lat}" data-lon="${item.lon}" data-name="${item.display_name}" data-state="${item.address.state || ''}">
          <strong>${escapeHtml(item.display_name.split(',')[0])}</strong>
          <small>${escapeHtml(item.display_name.split(',').slice(1).join(','))}</small>
        </div>
      `).join('');
      
      results.querySelectorAll('.search-item').forEach(el => {
        el.addEventListener('click', () => {
          const lat = parseFloat(el.dataset.lat);
          const lon = parseFloat(el.dataset.lon);
          const name = el.dataset.name;
          const state = el.dataset.state;
          const stateCode = STATE_MAP[state] || 'IN';
          const zoneId = `${stateCode}_SEARCH_${Date.now()}`;
          runAnalysis(zoneId, lat, lon, name);
          results.classList.add('hidden');
          document.getElementById('location-search').value = '';
        });
      });
    }
    results.classList.remove('hidden');
  } catch (err) {
    console.error(err);
  }
}

async function checkHealth() {
  const status = document.getElementById('api-status');
  try {
    const res = await fetch('/health');
    if (!res.ok) throw new Error('API health failed');
    status.textContent = 'API online';
    status.className = 'status-pill status-online';
  } catch {
    status.textContent = 'API offline';
    status.className = 'status-pill status-offline';
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
      button.style.setProperty('--zone-delay', `${Math.min(index * 24, 260)}ms`);
      button.innerHTML = `
        <span class="zone-card-top">
          <strong>${escapeHtml(zone.zone_id)}</strong>
          <small>${escapeHtml(regionLabel(zone.name))}</small>
        </span>
      `;
      button.addEventListener('click', () => {
        runAnalysis(zone.zone_id, zone.lat, zone.lon, zone.name);
        document.body.classList.remove('drawer-open');
      });
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
  document.body.classList.remove('drawer-open');
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
    latestAnalysis = data;
    latestDisplayName = name || '';
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
  const subtext = document.querySelector('.loading-subtext');
  button.disabled = isLoading;
  button.textContent = isLoading ? 'Analysing...' : 'Analyse Zone';
  if (isLoading) {
    let messageIndex = 0;
    if (subtext) subtext.textContent = LOADING_MESSAGES[messageIndex];
    clearInterval(loadingMessageTimer);
    loadingMessageTimer = setInterval(() => {
      messageIndex = (messageIndex + 1) % LOADING_MESSAGES.length;
      if (subtext) subtext.textContent = LOADING_MESSAGES[messageIndex];
    }, 1350);
    document.body.classList.add('is-loading');
  } else {
    clearInterval(loadingMessageTimer);
    loadingMessageTimer = null;
    document.body.classList.remove('is-loading');
  }
}

function markActiveZone(zoneId) {
  document.querySelectorAll('.zone-item').forEach((item) => {
    item.classList.toggle('active', item.dataset.zoneId === zoneId);
  });
}

function renderDashboard(data, displayName) {
  // Re-trigger animation
  document.body.classList.remove('animate-on-load');
  void document.body.offsetWidth; // trigger reflow
  document.body.classList.add('animate-on-load');
  let titleStr = `${data.zone_id} - ${displayName || 'Custom zone'}`;
  if (data.zone_id.includes('_SEARCH_')) {
    titleStr = displayName || 'Search Result';
  }
  document.getElementById('zone-title').textContent = titleStr;
  document.getElementById('zone-meta').textContent =
    `Lat ${Number(data.latitude).toFixed(4)} | Lon ${Number(data.longitude).toFixed(4)} | ${formatDate(data.analysed_at)}`;
  animateValue(document.getElementById('activity-score'), 0, Number(data.activity_score), 1000);
  animateRing(Number(data.activity_score));
  document.getElementById('activity-label').textContent = data.activity_label;
  const stressVal = data._meta?.overall_stress == null ? 0 : Math.round(Number(data._meta.overall_stress) * 100);
  if (data._meta?.overall_stress == null) {
    document.getElementById('stress-index').textContent = data.pollination_stress_index;
  } else {
    animateValue(document.getElementById('stress-index'), 0, stressVal, 1000, '%');
  }
  document.getElementById('stress-label').textContent = data.pollination_stress_index || 'index';
  animateValue(document.getElementById('habitat-score'), 0, Number(data.habitat_suitability_score), 1000);

  renderFactors(data._meta?.raw_factor_stress || {});
  renderCropTable(data.crop_risk || {}, data.crop_dependency || {});
  renderInsights(data);
  renderDecisionBrief(data.decision_brief || {});
  renderAnomalies(data.anomalies || []);
  renderPollinationDetail(data._meta?.visitation_summary || {}, data._meta?.realtime_status || {});
  renderInterventionSimulator(data);
  renderMethodNote(data._meta || {});
  setReportButtons(true);
  refreshPanelAnimations();
}

function setReportButtons(enabled) {
  document.getElementById('download-report-btn').disabled = !enabled;
  document.getElementById('print-report-btn').disabled = !enabled;
}

function renderFactors(factors) {
  const grid = document.getElementById('factor-grid');
  grid.classList.remove('rows-ready');
  grid.innerHTML = '';
  Object.entries(FACTOR_META).forEach(([key, meta]) => {
    const stress = Number(factors[key] || 0);
    const percent = Math.round(stress * 100);
    const row = document.createElement('article');
    row.className = 'factor-bar-row';
    row.style.setProperty('--factor-color', meta.color);
    row.style.setProperty('--row-delay', `${grid.children.length * 70}ms`);
    row.innerHTML = `
      <div class="factor-label">
        <strong>${escapeHtml(meta.label)}</strong>
        <span>${meta.weight}% model weight</span>
      </div>
      <div class="factor-track"><div class="factor-fill" style="width:${percent}%"></div></div>
      <strong class="factor-percent">${percent}%</strong>
      <span class="factor-band">${escapeHtml(stressBand(stress))}</span>
    `;
    grid.appendChild(row);
  });
  requestAnimationFrame(() => grid.classList.add('rows-ready'));
}

function buildFactorOverview(factors) {
  const rows = Object.entries(FACTOR_META).map(([key, meta]) => {
    const stress = Math.max(0, Math.min(1, Number(factors[key] || 0)));
    return { key, ...meta, stress, impact: stress * (meta.weight / 100) };
  }).sort((a, b) => b.impact - a.impact);
  const article = document.createElement('article');
  article.className = 'factor-overview';
  article.innerHTML = `
    <div>
      <h3>Stress Contribution</h3>
      <p>${escapeHtml(rows[0]?.label || 'Factor')} is currently the strongest weighted pressure.</p>
    </div>
    ${factorRadar(rows)}
    <div class="factor-impact-list">
      ${rows.map(row => `
        <div class="impact-row">
          <span>${escapeHtml(row.label)}</span>
          <div class="impact-track"><i style="width:${Math.round(row.impact * 100)}%;background:${row.color}"></i></div>
          <strong>${Math.round(row.impact * 100)}%</strong>
        </div>
      `).join('')}
    </div>
  `;
  return article;
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
  const caveats = Array.isArray(meta.data_caveats) ? meta.data_caveats.filter(Boolean) : [];
  note.innerHTML = `
    <strong>Model note</strong>
    <span>${escapeHtml(text)}</span>
    ${caveats.length ? `<span class="caveat-line">${escapeHtml(caveats[0])}</span>` : ''}
  `;
}

function renderInsights(data) {
  document.getElementById('insight-source').textContent = data._meta?.insight_source || '--';
  const boostActions = Array.isArray(data.pollination_boost_actions) ? data.pollination_boost_actions : [];
  document.getElementById('ai-content').innerHTML = `
    <article class="insight-callout biodiversity" style="animation-delay:0ms">
      <div class="insight-icon" aria-hidden="true">&#x1F33C;</div>
      <div>
        <h4>How to Increase Pollination</h4>
        <p>${escapeHtml(data.biodiversity_insight || 'No insight returned.')}</p>
      </div>
    </article>
    <article class="insight-callout intervention" style="animation-delay:80ms">
      <div class="arrow-mark" aria-hidden="true"></div>
      <div>
        <h4>Top Action to Boost Fertility This Season</h4>
        <p>${escapeHtml(data.top_intervention || 'No intervention returned.')}</p>
      </div>
    </article>
    ${boostActions.length ? `
    <article class="insight-callout boost-actions" style="animation-delay:160ms">
      <div class="insight-icon boost-icon" aria-hidden="true">&#x1F41D;</div>
      <div>
        <h4>3 More Steps to Increase Pollination</h4>
        <ol class="boost-list">
          ${boostActions.map(action => `<li>${escapeHtml(action)}</li>`).join('')}
        </ol>
      </div>
    </article>` : ''}
  `;
}

function renderAnomalies(anomalies) {
  const feed = document.getElementById('anomaly-feed');
  document.getElementById('anomaly-count').textContent = `${anomalies.length} alerts`;
  if (anomalies.length === 0) {
    feed.innerHTML = '<p class="empty">No anomalies detected.</p>';
    return;
  }
  feed.innerHTML = anomalies.map((item, index) => `
    <article class="alert" style="animation-delay:${Math.min(index * 55, 260)}ms">
      <span class="severity ${item.severity.toLowerCase()}">${escapeHtml(item.severity)}</span>
      <h4>${escapeHtml(titleCase(item.factor.replaceAll('_', ' ')))} - ${escapeHtml(item.variable)}</h4>
      <p>${escapeHtml(item.description)}</p>
      <p><strong>Action:</strong> ${escapeHtml(item.recommended_action)}</p>
    </article>
  `).join('');
}

function renderPollinationDetail(summary, realtimeStatus = {}) {
  const detail = document.getElementById('pollination-detail');
  const sourceHealth = realtimeStatus.source_health?.visitation || {};
  const sourceLabel = sourceHealth.source || 'unknown';
  const sourceTag = document.getElementById('pollination-source');
  sourceTag.textContent = `${sourceHealth.quality || 'pending'} - ${sourceLabel.replaceAll('_', ' ')}`;
  sourceTag.className = `tag source-${sourceHealth.quality || 'unknown'}`;
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
  return String(name).replace(/\u2014|\u00e2\u20ac\u201d/g, '-').split('-').pop().trim();
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
    const y = 42 - ((value - min) / span) * 34;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const area = `${points.join(' ')} 220,48 0,48`;
  const latest = values.at(-1);
  const previous = values.at(-2);
  const direction = latest >= previous ? 'up' : 'down';
  return `
    <svg class="trend-spark ${direction}" viewBox="0 0 220 56" role="img" aria-label="12-week visitation trend">
      <defs>
        <linearGradient id="trendFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="currentColor" stop-opacity="0.26"></stop>
          <stop offset="100%" stop-color="currentColor" stop-opacity="0"></stop>
        </linearGradient>
      </defs>
      <line x1="0" y1="43" x2="220" y2="43" class="spark-axis"></line>
      <polygon points="${area}" fill="url(#trendFill)"></polygon>
      <polyline points="${points.join(' ')}" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline>
      ${points.map((point, index) => `<circle cx="${point.split(',')[0]}" cy="${point.split(',')[1]}" r="${index === points.length - 1 ? 3.6 : 2.2}"></circle>`).join('')}
      <text x="0" y="54">12w ago</text>
      <text x="220" y="54" text-anchor="end">now</text>
    </svg>
  `;
}

function renderDecisionBrief(brief) {
  const container = document.getElementById('decision-brief');
  const grade = brief.decision_grade || '--';
  const gradeTag = document.getElementById('decision-grade');
  gradeTag.textContent = `Grade ${grade}`;
  gradeTag.className = `tag grade-${String(grade).toLowerCase()}`;

  const drivers = Array.isArray(brief.top_risk_drivers) ? brief.top_risk_drivers : [];
  const plan = Array.isArray(brief.intervention_plan) ? brief.intervention_plan : [];
  const crops = Array.isArray(brief.crop_exposure) ? brief.crop_exposure : [];
  const sourceScorecard = Array.isArray(brief.source_scorecard) ? brief.source_scorecard : [];

  if (!drivers.length && !plan.length) {
    container.innerHTML = '<p class="empty">Decision support will appear after analysis.</p>';
    return;
  }

  container.innerHTML = `
    <div class="decision-summary">
      <div>
        <span>Confidence</span>
        <strong>${Math.round(Number(brief.data_confidence_score || 0))}%</strong>
        <em>${escapeHtml(brief.data_confidence_label || 'Limited')}</em>
      </div>
      <div>
        <span>Resilience</span>
        <strong>${Math.round(Number(brief.resilience_score || 0))}%</strong>
        <em>recovery capacity</em>
      </div>
    </div>
    <p class="judge-summary">${escapeHtml(brief.judge_summary || '')}</p>
    <section class="driver-list">
      ${drivers.map(driver => `
        <article>
          <span>${escapeHtml(driver.label)}</span>
          <strong>${Math.round(Number(driver.weighted_impact || 0) * 100)}%</strong>
          <div class="impact-track"><i style="width:${Math.round(Number(driver.weighted_impact || 0) * 100)}%"></i></div>
          <em>${escapeHtml(driver.evidence_quality)} evidence</em>
        </article>
      `).join('')}
    </section>
    <section class="action-plan">
      ${plan.slice(0, 3).map(item => `
        <article>
          <b>${Math.round(Number(item.priority_score || 0))}</b>
          <div>
            <span>${escapeHtml(item.severity)} - ${escapeHtml(item.label)}</span>
            <p>${escapeHtml(item.action)}</p>
            ${item.pollination_uplift ? `<em class="uplift-hint">&#x2191; ${escapeHtml(item.pollination_uplift)}</em>` : ''}
          </div>
        </article>
      `).join('')}
    </section>
    <section class="evidence-row">
      <span>${sourceScorecard.filter(item => item.quality === 'live').length}/${sourceScorecard.length || 0} live signals</span>
      <span>Top crop: ${escapeHtml(titleCase(crops[0]?.crop || '--'))}</span>
      <span>Exposure: ${escapeHtml(crops[0]?.level || '--')}</span>
    </section>
  `;
}

function renderInterventionSimulator(data) {
  const container = document.getElementById('intervention-simulator');
  const selected = recommendedScenarioIds(data);
  container.innerHTML = `
    <div class="sim-selector">
      ${INTERVENTION_SCENARIOS.map(scenario => `
        <label>
          <input type="checkbox" value="${scenario.id}" ${selected.includes(scenario.id) ? 'checked' : ''} />
          <span>${escapeHtml(scenario.label)}</span>
          <em>${escapeHtml(scenario.cost)} cost - ${escapeHtml(scenario.time)}</em>
        </label>
      `).join('')}
    </div>
    <div id="simulation-output" class="simulation-output"></div>
  `;
  container.querySelectorAll('input[type="checkbox"]').forEach((input) => {
    input.addEventListener('change', () => updateSimulation(data));
  });
  updateSimulation(data);
}

function recommendedScenarioIds(data) {
  const drivers = data.decision_brief?.top_risk_drivers || [];
  const ids = new Set();
  drivers.slice(0, 2).forEach((driver) => {
    if (driver.factor === 'pesticide_exposure') ids.add('spray_ipm');
    if (driver.factor === 'floral_diversity') ids.add('flower_strips');
    if (driver.factor === 'soil_fertility') ids.add('soil_recovery');
    if (driver.factor === 'nesting_availability') ids.add('nesting_refugia');
    if (driver.factor === 'climate_variability') ids.add('drought_buffer');
    if (driver.factor === 'pollination_factor') ids.add('flower_strips');
  });
  if (ids.size === 0) ids.add('flower_strips');
  return [...ids];
}

function updateSimulation(data) {
  const container = document.getElementById('intervention-simulator');
  const selectedIds = [...container.querySelectorAll('input[type="checkbox"]:checked')].map(input => input.value);
  const result = simulateInterventions(data, selectedIds);
  const selectedLabels = INTERVENTION_SCENARIOS
    .filter(scenario => selectedIds.includes(scenario.id))
    .map(scenario => scenario.label);
  document.getElementById('simulation-gain').textContent = `+${result.activityGain}`;
  document.getElementById('sim-status').textContent = selectedIds.length
    ? `${selectedIds.length} selected`
    : 'no scenario';
  const output = document.getElementById('simulation-output');
  output.classList.remove('updated');
  void output.offsetWidth;
  output.classList.add('updated');
  output.innerHTML = `
    <div class="sim-selected">
      ${selectedLabels.length
        ? selectedLabels.map(label => `<span>${escapeHtml(label)}</span>`).join('')
        : '<span>Select an intervention to model recovery</span>'}
    </div>
    <div class="sim-score-row">
      <div><span>Current</span><strong>${result.currentActivity}</strong><em>activity</em></div>
      <div><span>Projected</span><strong>${result.projectedActivity}</strong><em>activity</em></div>
      <div><span>Stress Cut</span><strong>${result.stressDrop}%</strong><em>relative</em></div>
    </div>
    <div class="sim-meter">
      <i style="width:${result.currentActivity}%"></i>
      <b style="width:${result.projectedActivity}%"></b>
    </div>
    <section class="sim-impact-list">
      ${result.factorChanges.length ? result.factorChanges.map(item => `
        <article>
          <span>${escapeHtml(FACTOR_META[item.factor]?.label || item.factor)}</span>
          <strong>${item.before}% to ${item.after}%</strong>
        </article>
      `).join('') : '<article><span>No scenario selected</span><strong>0% change</strong></article>'}
    </section>
    <p class="sim-note">${escapeHtml(result.note)}</p>
  `;
}

function simulateInterventions(data, selectedIds) {
  const factorStress = data._meta?.raw_factor_stress || {};
  const weights = data._meta?.factor_weights || Object.fromEntries(
    Object.entries(FACTOR_META).map(([key, meta]) => [key, meta.weight / 100])
  );
  const selected = INTERVENTION_SCENARIOS.filter(scenario => selectedIds.includes(scenario.id));
  const combinedEffects = {};
  selected.forEach((scenario) => {
    Object.entries(scenario.effects).forEach(([factor, effect]) => {
      combinedEffects[factor] = 1 - ((1 - (combinedEffects[factor] || 0)) * (1 - effect));
    });
  });

  const projected = {};
  Object.keys(FACTOR_META).forEach((factor) => {
    const current = Math.max(0, Math.min(1, Number(factorStress[factor] || 0)));
    const effect = combinedEffects[factor] || 0;
    projected[factor] = Math.max(0, current * (1 - effect));
  });

  const currentStress = Object.keys(FACTOR_META).reduce((sum, factor) => (
    sum + Math.max(0, Math.min(1, Number(factorStress[factor] || 0))) * Number(weights[factor] || 0)
  ), 0);
  const projectedStress = Object.keys(FACTOR_META).reduce((sum, factor) => (
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

function downloadFarmerReport() {
  if (!latestAnalysis) return;
  const html = buildFarmerReportHtml(latestAnalysis, latestDisplayName);
  const blob = new Blob([html], { type: 'text/html' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `polynexus_report_${safeFileName(latestAnalysis.zone_id || 'zone')}.html`;
  document.body.appendChild(link);
  link.click();
  URL.revokeObjectURL(link.href);
  link.remove();
}

function printFarmerReport() {
  if (!latestAnalysis) return;
  const reportWindow = window.open('', '_blank');
  if (!reportWindow) {
    alert('Allow popups to print the farmer report.');
    return;
  }
  reportWindow.document.write(buildFarmerReportHtml(latestAnalysis, latestDisplayName));
  reportWindow.document.close();
  reportWindow.focus();
  reportWindow.print();
}

function buildFarmerReportHtml(data, displayName) {
  const brief = data.decision_brief || {};
  const drivers = brief.top_risk_drivers || [];
  const plan = brief.intervention_plan || [];
  const crops = brief.crop_exposure || [];
  const sources = brief.source_scorecard || [];
  const summary = data._meta?.visitation_summary || {};
  const caveats = Array.isArray(data._meta?.data_caveats) ? data._meta.data_caveats : [];
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
      ${data.pollination_boost_actions.map(a => `<li>${escapeHtml(a)}</li>`).join('')}
    </ol>
  </div>` : ''}
  ${caveats.length ? `<h2>Data Caveats</h2>${caveats.map(item => `<div class="action">${escapeHtml(item)}</div>`).join('')}` : ''}
  <h2>Priority Action Plan</h2>
  ${plan.slice(0, 5).map(item => `<div class="action"><strong>${escapeHtml(item.severity)} - ${escapeHtml(item.label)}</strong><br>${escapeHtml(item.action)}${item.pollination_uplift ? `<br><em style="color:#159957">&#x2191; ${escapeHtml(item.pollination_uplift)}</em>` : ''}</div>`).join('') || '<p>No urgent actions returned.</p>'}
  <h2>Top Risk Drivers</h2>
  <table><thead><tr><th>Driver</th><th>Impact</th><th>Evidence</th></tr></thead><tbody>
    ${drivers.map(driver => `<tr><td>${escapeHtml(driver.label)}</td><td>${Math.round(Number(driver.weighted_impact || 0) * 100)}%</td><td>${escapeHtml(driver.evidence_quality)}</td></tr>`).join('')}
  </tbody></table>
  <h2>Crop Exposure</h2>
  <table><thead><tr><th>Crop</th><th>Dependency</th><th>Exposure</th></tr></thead><tbody>
    ${crops.map(crop => `<tr><td>${escapeHtml(titleCase(crop.crop))}</td><td>${Math.round(Number(crop.dependency || 0) * 100)}%</td><td>${escapeHtml(crop.level)}</td></tr>`).join('')}
  </tbody></table>
  <h2>Pollination Signal</h2>
  <p>Average visits: ${escapeHtml(formatNumber(summary.avg_visitations_per_hour))}; expected: ${escapeHtml(formatNumber(summary.expected_visitations_per_hour))}; 12-week decline: ${escapeHtml(formatRatio(summary.decline_rate_12w))}.</p>
  <h2>Data Sources</h2>
  <table><thead><tr><th>Signal</th><th>Source</th><th>Quality</th></tr></thead><tbody>
    ${sources.map(source => `<tr><td>${escapeHtml(source.signal)}</td><td>${escapeHtml(source.source || '--')}</td><td>${escapeHtml(source.quality || '--')}</td></tr>`).join('')}
  </tbody></table>
  <p class="muted">Decision-support estimate. Validate with field scouting before major operational changes.</p>
</body>
</html>`;
}

function safeFileName(value) {
  return String(value).replace(/[^a-z0-9_-]+/gi, '_').toLowerCase();
}

function factorRadar(rows) {
  const cx = 58;
  const cy = 58;
  const rings = [20, 38, 54].map(radius =>
    `<polygon points="${radarPoints(rows.map(() => radius / 54), cx, cy, radius)}"></polygon>`
  ).join('');
  const stressPoints = radarPoints(rows.map(row => row.stress), cx, cy, 54);
  const spokes = rows.map((_, index) => {
    const angle = -Math.PI / 2 + (index / rows.length) * Math.PI * 2;
    return `<line x1="${cx}" y1="${cy}" x2="${cx + Math.cos(angle) * 54}" y2="${cy + Math.sin(angle) * 54}"></line>`;
  }).join('');
  return `
    <svg class="factor-radar" viewBox="0 0 116 116" role="img" aria-label="Factor stress radar">
      <g class="radar-grid">${rings}${spokes}</g>
      <polygon class="radar-shape" points="${stressPoints}"></polygon>
      ${stressPoints.split(' ').map(point => `<circle cx="${point.split(',')[0]}" cy="${point.split(',')[1]}" r="3"></circle>`).join('')}
    </svg>
  `;
}

function radarPoints(values, cx, cy, radius) {
  return values.map((value, index) => {
    const angle = -Math.PI / 2 + (index / values.length) * Math.PI * 2;
    const distance = Math.max(0.08, value) * radius;
    return `${(cx + Math.cos(angle) * distance).toFixed(1)},${(cy + Math.sin(angle) * distance).toFixed(1)}`;
  }).join(' ');
}

function miniDonut(percent, color) {
  const radius = 18;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - Math.max(0, Math.min(100, percent)) / 100);
  return `
    <svg class="mini-donut" viewBox="0 0 44 44" aria-hidden="true">
      <circle cx="22" cy="22" r="${radius}"></circle>
      <circle cx="22" cy="22" r="${radius}" style="stroke:${color};stroke-dasharray:${circumference.toFixed(2)};stroke-dashoffset:${offset.toFixed(2)}"></circle>
    </svg>
  `;
}

function pollinationBar(item, index) {
  const value = Number.isFinite(item.value) ? Math.max(0, item.value) : 0;
  const max = Number.isFinite(item.max) && item.max > 0 ? item.max : 1;
  const height = Math.max(8, Math.min(100, (value / max) * 100));
  const y2 = 46 - (height / 100) * 38;
  return `
    <div class="bar-metric" style="--bar-offset:${100 - height};--delay:${index * 90}ms">
      <svg viewBox="0 0 24 50" aria-hidden="true">
        <line x1="12" y1="46" x2="12" y2="${y2.toFixed(1)}" pathLength="100"></line>
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

function animateRing(score) {
  const ring = document.getElementById('activity-ring');
  if (!ring) return;
  const radius = Number(ring.getAttribute('r')) || 64;
  const circumference = 2 * Math.PI * radius;
  const value = Math.max(0, Math.min(100, Number(score) || 0));
  ring.style.strokeDasharray = String(circumference);
  ring.style.strokeDashoffset = String(circumference * (1 - value / 100));
  if (value >= 75) ring.style.stroke = 'var(--green)';
  else if (value >= 55) ring.style.stroke = 'var(--amber)';
  else ring.style.stroke = 'var(--red)';
}

function animateValue(obj, start, end, duration, suffix = '') {
  if (!obj) return;
  if (!Number.isFinite(end)) {
    obj.textContent = '--';
    return;
  }
  let startTimestamp = null;
  const isFloat = end % 1 !== 0;
  const step = (timestamp) => {
    if (!startTimestamp) startTimestamp = timestamp;
    const progress = Math.min((timestamp - startTimestamp) / duration, 1);
    const easeOut = 1 - Math.pow(1 - progress, 3);
    const current = start + easeOut * (end - start);
    obj.innerHTML = (isFloat ? current.toFixed(1) : Math.round(current)) + suffix;
    if (progress < 1) {
      window.requestAnimationFrame(step);
    } else {
      obj.innerHTML = (isFloat ? end.toFixed(1) : end) + suffix;
    }
  };
  window.requestAnimationFrame(step);
}
