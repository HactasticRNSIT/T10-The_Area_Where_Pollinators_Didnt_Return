@echo off
cd /d "c:\Users\sridh\OneDrive\Desktop\all projects\poly_nexus\backend"
call venv\Scripts\activate.bat
set POLYNEXUS_MOCK_EXTERNAL=1
set ENABLE_EFFICACY_ENDPOINT=1
set POLYNEXUS_API_KEY=test_key
set ANALYSE_RATE_LIMIT=200/minute
set COMPARE_RATE_LIMIT=60/minute

echo Starting Uvicorn...
start /B "" python -m uvicorn api:app --port 8000 > server_log.txt 2> server_log_err.txt
timeout /t 5 /nobreak > nul

echo Running Locust...
python -m locust -f loadtest\locustfile.py --host=http://127.0.0.1:8000 --headless -u 10 -r 2 -t 30s > locust_output_final.txt 2>&1

echo Killing Uvicorn...
for /f "tokens=5" %%a in ('netstat -aon ^| find "8000" ^| find "LISTENING"') do taskkill /f /pid %%a
