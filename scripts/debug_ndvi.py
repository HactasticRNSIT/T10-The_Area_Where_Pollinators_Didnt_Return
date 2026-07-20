import sys
import os
import json
import datetime
import requests
from dotenv import load_dotenv

backend_dir = os.path.join(os.path.dirname(__file__), '../backend')
sys.path.append(backend_dir)
load_dotenv(os.path.join(backend_dir, '.env'))

from data_fetcher import _get_copernicus_token

def test_copernicus():
    token = _get_copernicus_token()
    if not token:
        print("Failed to acquire token. Check COPERNICUS_CLIENT_ID and COPERNICUS_CLIENT_SECRET in .env.")
        return
    print("Token acquired successfully.")

    lat = 31.1048
    lon = 77.1734
    d = 0.005
    bbox = [lon-d, lat-d, lon+d, lat+d]

    # The code in data_fetcher.py currently uses datetime.datetime.now(datetime.UTC)
    # The system clock is currently set to 2026. So the fetch range is:
    start = '2026-05-11T00:00:00Z'
    end = '2026-06-10T23:59:59Z'

    payload = {
        'input': {
            'bounds': {'bbox': bbox, 'properties': {'crs': 'http://www.opengis.net/def/crs/EPSG/0/4326'}},
            'data': [{'type': 'sentinel-2-l2a', 'dataFilter': {'timeRange': {'from': start, 'to': end}, 'maxCloudCoverage': 20}}]
        },
        'aggregation': {
            'timeRange': {'from': start, 'to': end},
            'aggregationInterval': {'of': 'P1D'},
            'evalscript': '''//VERSION=3
                function setup() { return { input: ['B04', 'B08', 'SCL', 'dataMask'], output: [{ id: 'ndvi', bands: 1 }, { id: 'cloud', bands: 1 }, { id: 'dataMask', bands: 1 }] }; }
                function evaluatePixel(samples) {
                    let ndvi = (samples.B08 - samples.B04) / (samples.B08 + samples.B04);
                    let isCloud = (samples.SCL === 3 || samples.SCL === 8 || samples.SCL === 9 || samples.SCL === 10) ? 1.0 : 0.0;
                    return { ndvi: [ndvi], cloud: [isCloud], dataMask: [samples.dataMask] };
                }
            '''
        }
    }

    print("\n--- STATISTICAL API PAYLOAD ---")
    print(json.dumps(payload, indent=2))

    try:
        r = requests.post('https://sh.dataspace.copernicus.eu/api/v1/statistics', headers={'Authorization': f'Bearer {token}'}, json=payload, timeout=20)
        print("\n--- STATISTICAL API RESPONSE STATUS ---:", r.status_code)
        print("\n--- STATISTICAL API RESPONSE BODY ---")
        with open('stat_response.json', 'w') as f:
            json.dump(r.json(), f, indent=2)
        print(json.dumps(r.json(), indent=2))
    except Exception as e:
        print("Error:", e)

    # Real time catalog API query
    print("\n--- CATALOG API QUERY ---")
    # Let's check catalog from 2024 to 2026-06-10
    cat_payload = {
        "bbox": bbox,
        "datetime": "2024-01-01T00:00:00Z/2026-06-10T23:59:59Z",
        "collections": ["sentinel-2-l2a"],
        "limit": 10
    }
    print("\n--- CATALOG API PAYLOAD ---")
    print(json.dumps(cat_payload, indent=2))

    try:
        r2 = requests.post('https://sh.dataspace.copernicus.eu/api/v1/catalog/1.0.0/search', headers={'Authorization': f'Bearer {token}'}, json=cat_payload, timeout=20)
        print("\n--- CATALOG API RESPONSE STATUS ---:", r2.status_code)
        features = r2.json().get('features', [])
        print(f"Found {len(features)} features")
        for f in features:
            print(f"- ID: {f.get('id')}, Date: {f.get('properties', {}).get('datetime')}, Cloud: {f.get('properties', {}).get('eo:cloud_cover')}")
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    test_copernicus()
