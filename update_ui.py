import os
import re

frontend_dir = os.path.join(os.getcwd(), 'frontend')
index_file = os.path.join(frontend_dir, 'index.html')

with open(index_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Add fonts
fonts = """  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/style.css?v=readable-3" />"""
content = re.sub(r'  <link rel="stylesheet" href="/static/style\.css[^"]*" />', fonts, content)

# Update body class
content = content.replace('<body>', '<body class="animate-on-load">')

with open(index_file, 'w', encoding='utf-8') as f:
    f.write(content)

print("index.html updated")
