import os

frontend_dir = os.path.join(os.getcwd(), 'frontend')
app_file = os.path.join(frontend_dir, 'app.js')

with open(app_file, 'r', encoding='utf-8') as f:
    content = f.read()

target1 = "  document.getElementById('activity-score').textContent = Number(data.activity_score).toFixed(1);"
target2 = "  document.getElementById('stress-index').textContent = data._meta?.overall_stress == null\n    ? data.pollination_stress_index\n    : `${Math.round(Number(data._meta.overall_stress) * 100)}%`;"
target3 = "  document.getElementById('habitat-score').textContent = Number(data.habitat_suitability_score).toFixed(1);"
target4 = "function renderDashboard(data, displayName) {"

replacement1 = "  animateValue(document.getElementById('activity-score'), 0, Number(data.activity_score), 1000);"
replacement2 = """  const stressVal = data._meta?.overall_stress == null ? 0 : Math.round(Number(data._meta.overall_stress) * 100);
  if (data._meta?.overall_stress == null) {
    document.getElementById('stress-index').textContent = data.pollination_stress_index;
  } else {
    animateValue(document.getElementById('stress-index'), 0, stressVal, 1000, '%');
  }"""
replacement3 = "  animateValue(document.getElementById('habitat-score'), 0, Number(data.habitat_suitability_score), 1000);"
replacement4 = """function renderDashboard(data, displayName) {
  // Re-trigger animation
  document.body.classList.remove('animate-on-load');
  void document.body.offsetWidth; // trigger reflow
  document.body.classList.add('animate-on-load');"""

content = content.replace(target4, replacement4)
content = content.replace(target1, replacement1)
content = content.replace(target2, replacement2)
# CRLF fallback
content = content.replace(target2.replace('\\n', '\\r\\n'), replacement2)
content = content.replace(target3, replacement3)

new_func = """
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
}
"""

content += new_func

with open(app_file, 'w', encoding='utf-8') as f:
    f.write(content)

print("app.js updated string replace")
