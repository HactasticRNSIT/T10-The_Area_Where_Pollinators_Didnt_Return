"""Fix duplicate polygon 422 handling in data_fetcher.py."""
import re as stdlib_re

path = r'c:\Users\sridh\OneDrive\Desktop\poly_nexus\backend\data_fetcher.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add import re if missing
if 'import re\n' not in content:
    content = content.replace('import logging\n', 'import logging\nimport re\n', 1)
    print('Added import re')

# Replace the POST polygon block to handle 422 duplicate response
OLD = (
    '    # Create a new polygon\n'
    '    try:\n'
    '        body = _build_polygon_geojson(lat, lon)\n'
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
    '    # Create a new polygon (handle 422 duplicate gracefully)\n'
    '    try:\n'
    '        body = _build_polygon_geojson(lat, lon)\n'
    '        r = requests.post(API_ENDPOINTS["agromonitoring_polygons"], params=params,\n'
    '                          json=body, timeout=REQUEST_TIMEOUT)\n'
    '        if r.status_code == 422:\n'
    "            # Agromonitoring returns 422 when an identical polygon already exists.\n"
    "            # Extract the existing polygon ID from the error message.\n"
    '            msg = r.json().get("message", "")\n'
    "            m = re.search(r\"polygon '([0-9a-f]+)'\", msg)\n"
    '            if m:\n'
    '                pid = m.group(1)\n'
    '                _poly_id_cache[key] = pid\n'
    '                log.info("[agro] reusing existing polygon %s (from duplicate 422)", pid)\n'
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
    print('OK: duplicate 422 handling added')
else:
    print('WARN: target block not found - trying to locate it')
    idx = content.find('# Create a new polygon')
    if idx != -1:
        print(repr(content[idx:idx+400]))

# Also fix polygon name: replace colons with hyphens (safer for API)
content = content.replace(
    'poly_name = f"polynexus:{key}"',
    'poly_name = f"polynexus-{key}"',
    1
)
# Also fix _build_polygon_geojson to use hyphens
content = content.replace(
    '"name": f"polynexus:{lat:.4f}:{lon:.4f}"',
    '"name": f"polynexus-{lat:.4f}-{lon:.4f}"',
    1
)
# Fix counterclockwise winding order (right-hand rule for exterior ring)
OLD_RING = (
    '    ring = [[lon-d,lat+d],[lon+d,lat+d],[lon+d,lat-d],[lon-d,lat-d],[lon-d,lat+d]]'
)
NEW_RING = (
    '    # GeoJSON exterior ring: counterclockwise (right-hand rule)\n'
    '    ring = [[lon-d,lat-d],[lon+d,lat-d],[lon+d,lat+d],[lon-d,lat+d],[lon-d,lat-d]]'
)
if OLD_RING in content:
    content = content.replace(OLD_RING, NEW_RING, 1)
    print('OK: fixed ring winding order (CCW)')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
