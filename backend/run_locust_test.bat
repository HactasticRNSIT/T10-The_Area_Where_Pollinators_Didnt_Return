@echo off
cd /d "c:\Users\sridh\OneDrive\Desktop\all projects\poly_nexus\backend"
call venv\Scripts\activate.bat

:: Start uvicorn in the background with mock mode enabled
set POLYNEXUS_MOCK_EXTERNAL=1
set ENABLE_EFFICACY_ENDPOINT=1
start /B uvicorn api:app --port 8000 > uvicorn_log.txt 2>&1

:: Wait a moment for server to start
timeout /t 5 /nobreak > nul

:: Run a curl command to verify /v1/analyse
echo "--- CURL TEST ---"
curl -s "http://127.0.0.1:8000/v1/analyse?zone_id=IN_RJ_01&lat=0.0&lon=0.0" > curl_output.txt

:: Run locust headless for 30s
echo "--- LOCUST LOAD TEST ---"
locust -f loadtest\locustfile.py --host=http://127.0.0.1:8000 --headless -u 10 -r 2 -t 30s > locust_output.txt 2>&1

:: Kill the background uvicorn process
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8000" ^| find "LISTENING"') do taskkill /f /pid %%a
