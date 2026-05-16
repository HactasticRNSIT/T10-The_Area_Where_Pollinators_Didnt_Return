import os
import re

frontend_dir = os.path.join(os.getcwd(), 'frontend')
app_file = os.path.join(frontend_dir, 'app.js')

with open(app_file, 'r', encoding='utf-8') as f:
    content = f.read()

target = """function renderDashboard(data, displayName) {
  document.getElementById('zone-title').textContent = `${data.zone_id} - ${displayName || 'Custom zone'}`;
  document.getElementById('zone-meta').textContent =
    `Lat ${Number(data.latitude).toFixed(4)} | Lon ${Number(data.longitude).toFixed(4)} | ${formatDate(data.analysed_at)}`;
  document.getElementById('activity-score').textContent = Number(data.activity_score).toFixed(1);
  document.getElementById('activity-label').textContent = data.activity_label;
  document.getElementById('stress-index').textContent = data._meta?.overall_stress == null
    ? data.pollination_stress_index
    : `${Math.round(Number(data._meta.overall_stress) * 100)}%`;
  document.getElementById('stress-label').textContent = data.pollination_stress_index || 'index';
  document.getElementById('habitat-score').textContent = Number(data.habitat_suitability_score).toFixed(1);

  renderFactors(data._meta?.raw_factor_stress || {});
  renderCropTable(data.crop_risk || {}, data.crop_dependency || {});
  renderInsights(data);
  renderAnomalies(data.anomalies || []);
  renderPollinationDetail(data._meta?.visitation_summary || {});
  renderMethodNote(data._meta || {});
}"""

replacement = """function renderDashboard(data, displayName) {
  // Re-trigger animation
  document.body.classList.remove('animate-on-load');
  void document.body.offsetWidth; // trigger reflow
  document.body.classList.add('animate-on-load');

  document.getElementById('zone-title').textContent = `${data.zone_id} - ${displayName || 'Custom zone'}`;
  document.getElementById('zone-meta').textContent =
    `Lat ${Number(data.latitude).toFixed(4)} | Lon ${Number(data.longitude).toFixed(4)} | ${formatDate(data.analysed_at)}`;
  
  animateValue(document.getElementById('activity-score'), 0, Number(data.activity_score), 1000);
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
  renderAnomalies(data.anomalies || []);
  renderPollinationDetail(data._meta?.visitation_summary || {});
  renderMethodNote(data._meta || {});
}

function animateValue(obj, start, end, duration, suffix = '') {
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
}"""

# Handle Windows/Unix line endings
target = target.replace('\\n', '\\r?\\n')
content = re.sub(target, replacement, content, flags=re.MULTILINE)

with open(app_file, 'w', encoding='utf-8') as f:
    f.write(content)

print("app.js updated")
