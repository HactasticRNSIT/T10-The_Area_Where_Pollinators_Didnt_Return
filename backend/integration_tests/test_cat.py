import requests, os, json, datetime

client_id = os.environ.get('COPERNICUS_CLIENT_ID', '')
client_secret = os.environ.get('COPERNICUS_CLIENT_SECRET', '')
r_auth = requests.post('https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token', 
    headers={'Content-Type': 'application/x-www-form-urlencoded'},
    data={'client_id': client_id, 'client_secret': client_secret, 'grant_type': 'client_credentials'})
token = r_auth.json().get('access_token')

url = 'https://sh.dataspace.copernicus.eu/api/v1/catalog/1.0.0/search'
lat, lon = 12.9, 77.5
d = 0.005
now = datetime.datetime.now(datetime.UTC)
start = (now - datetime.timedelta(days=30)).strftime('%Y-%m-%dT00:00:00Z')
end = now.strftime('%Y-%m-%dT23:59:59Z')

payload = {
    'collections': ['sentinel-2-l2a'],
    'bbox': [lon-d, lat-d, lon+d, lat+d],
    'datetime': f'{start}/{end}',
    'limit': 10
}

r_cat = requests.post(url, headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}, json=payload)
print('Catalog Status:', r_cat.status_code, r_cat.text)
