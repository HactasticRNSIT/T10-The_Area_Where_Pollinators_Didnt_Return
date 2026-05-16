"""Fix POST polygon block to handle 422 duplicate."""
import re

path = r'c:\Users\sridh\OneDrive\Desktop\poly_nexus\backend\data_fetcher.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

OLD = (
    '    try:\n'
    '        r = requests.post(API_ENDPOINTS["agromonitoring_polygons"], params=params,\n'
    '                          json=body, timeout=REQUEST_TIMEOUT)\n'
    '        r.raise_for_status()\n'
    '        pid = r.json()["id"]\n'
    '        _poly_id_cache[key] = pid\n'
    '        log.info("[agro] created polygon %s", pid)\n'
    '        return pid\n'
    '    except Exception as exc:\n'
    '        log.warning("[agro] POST polygon: %s", exc)\n'
    '        return None\n'
)
NEW = (
    '    try:\n'
    '        r = requests.post(API_ENDPOINTS["agromonitoring_polygons"], params=params,\n'
    '                          json=body, timeout=REQUEST_TIMEOUT)\n'
    '        if r.status_code == 422:\n'
    '            # Duplicate polygon: Agromonitoring returns the existing ID in the message\n'
    '            msg = r.json().get("message", "")\n'
    "            m = re.search(r\"polygon '([0-9a-f]+)'\", msg)\n"
    '            if m:\n'
    '                pid = m.group(1)\n'
    '                _poly_id_cache[key] = pid\n'
    '                log.info("[agro] reusing polygon %s (duplicate 422)", pid)\n'
    '                return pid\n'
    '        r.raise_for_status()\n'
    '        pid = r.json()["id"]\n'
    '        _poly_id_cache[key] = pid\n'
    '        log.info("[agro] created polygon %s", pid)\n'
    '        return pid\n'
    '    except Exception as exc:\n'
    '        log.warning("[agro] POST polygon: %s", exc)\n'
    '        return None\n'
)

if OLD in content:
    content = content.replace(OLD, NEW, 1)
    print('OK: 422 duplicate handling patched')
else:
    print('ERROR: block still not matched')
    idx = content.find('requests.post')
    print(repr(content[max(0,idx-50):idx+350]))

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
