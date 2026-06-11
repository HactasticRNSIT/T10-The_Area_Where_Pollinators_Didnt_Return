import requests, os, datetime

client_id = os.environ.get('COPERNICUS_CLIENT_ID', '')
client_secret = os.environ.get('COPERNICUS_CLIENT_SECRET', '')

def get_copernicus_ndvi(lat, lon):
    r_auth = requests.post('https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token', 
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data={'client_id': client_id, 'client_secret': client_secret, 'grant_type': 'client_credentials'})
    token = r_auth.json().get('access_token')

    d = 0.005
    bbox = [lon-d, lat-d, lon+d, lat+d]

    now = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=730)
    start = (now - datetime.timedelta(days=30)).strftime('%Y-%m-%dT00:00:00Z')
    end = now.strftime('%Y-%m-%dT23:59:59Z')

    # Catalog API
    cat_payload = {
        'collections': ['sentinel-2-l2a'],
        'bbox': bbox,
        'datetime': f'{start}/{end}',
        'limit': 20
    }
    r_cat = requests.post('https://sh.dataspace.copernicus.eu/api/v1/catalog/1.0.0/search', headers={'Authorization': f'Bearer {token}'}, json=cat_payload)
    features = r_cat.json().get('features', [])
    
    best_scene = None
    for f in features:
        if f['properties'].get('eo:cloud_cover', 100) <= 20:
            best_scene = f
            break
            
    if not best_scene:
        return {"error": "No cloud-free scene found"}

    scene_date = best_scene['properties']['datetime']
    cloud_cov = best_scene['properties']['eo:cloud_cover']
    
    # Statistical API for exactly this scene
    dt_scene = datetime.datetime.fromisoformat(scene_date.replace('Z', '+00:00'))
    start_scene = dt_scene.strftime('%Y-%m-%dT00:00:00Z')
    end_scene = dt_scene.strftime('%Y-%m-%dT23:59:59Z')

    stat_payload = {
        'input': {
            'bounds': {'bbox': bbox, 'properties': {'crs': 'http://www.opengis.net/def/crs/EPSG/0/4326'}},
            'data': [{'type': 'sentinel-2-l2a', 'dataFilter': {'timeRange': {'from': start_scene, 'to': end_scene}}}]
        },
        'aggregation': {
            'timeRange': {'from': start_scene, 'to': end_scene},
            'aggregationInterval': {'of': 'P1D'},
            'evalscript': '''//VERSION=3
                function setup() { return { input: ['B04', 'B08', 'dataMask'], output: [{ id: 'ndvi', bands: 1 }, { id: 'dataMask', bands: 1 }] }; }
                function evaluatePixel(samples) {
                    let ndvi = (samples.B08 - samples.B04) / (samples.B08 + samples.B04);
                    return { ndvi: [ndvi], dataMask: [samples.dataMask] };
                }
            '''
        }
    }
    r_stat = requests.post('https://sh.dataspace.copernicus.eu/api/v1/statistics', headers={'Authorization': f'Bearer {token}'}, json=stat_payload)
    stats = r_stat.json()
    try:
        ndvi_mean = stats['data'][0]['outputs']['ndvi']['bands']['B0']['stats']['mean']
    except Exception as e:
        return {"error": f"Stats parsing failed: {e}", "resp": stats}

    return {
        "ndvi": ndvi_mean,
        "scene_date": scene_date,
        "cloud_pct": cloud_cov
    }

print(get_copernicus_ndvi(12.9, 77.5))
