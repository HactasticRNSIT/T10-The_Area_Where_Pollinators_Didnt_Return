import os

frontend_dir = os.path.join(os.getcwd(), 'frontend')
app_file = os.path.join(frontend_dir, 'app.js')

with open(app_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Update renderFactors for compact view
target_factors_old = """    card.innerHTML = `
      <div class="factor-head">
        <h3>${meta.label}</h3>
        <div class="weight">${meta.weight}% model weight</div>
      </div>
      <span>Estimated stress level</span>
      <div class="meter"><div class="meter-fill" style="width:${percent}%;background:${meta.color}"></div></div>
      <div class="factor-score">${escapeHtml(stressBand(stress))}</div>
      <div class="factor-range">${stressRange(percent)}</div>
    `;"""

target_factors_replacement = """    card.innerHTML = `
      <h3>${meta.label}</h3>
      <div class="factor-score">${escapeHtml(stressBand(stress))}</div>
      <div class="meter"><div class="meter-fill" style="width:${percent}%;background:${meta.color}"></div></div>
      <div class="factor-range">${stressRange(percent)}</div>
    `;"""

content = content.replace(target_factors_old, target_factors_replacement)

# Update trendSparkline height for decluttered view (64 -> 40)
content = content.replace('viewBox="0 0 220 64"', 'viewBox="0 0 220 40"')
content = content.replace('const y = 58 -', 'const y = 36 -')
content = content.replace('((value - min) / span) * 46;', '((value - min) / span) * 32;')
content = content.replace('220,64 0,64', '220,40 0,40')

# Update pollinationBar height (118 -> 50)
content = content.replace('viewBox="0 0 24 118"', 'viewBox="0 0 24 50"')
content = content.replace('y1="108" x2="12" y2="${108 - height}"', 'y1="46" x2="12" y2="${46 - height}"')
content = content.replace('108 - height', '46 - height') # and other similar lines

with open(app_file, 'w', encoding='utf-8') as f:
    f.write(content)

print("app.js decluttered")
