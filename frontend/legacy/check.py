import re
content = open('app.js', 'r', encoding='utf-8').read()
def strip_js(text):
    text = re.sub(r'/\*[\s\S]*?\*/', '', text)
    text = re.sub(r'//.*', '', text)
    text = re.sub(r'"(?:[^\\"]|\\.)*"', '', text)
    text = re.sub(r"'(?:[^\\']|\\.)*'", '', text)
    text = re.sub(r'`(?:[^\\`]|\\.)*`', '', text)
    return text
lines = content.split('\n')
b = 0
for line in lines:
    clean = strip_js(line)
    b += clean.count('{') - clean.count('}')
print(b)
