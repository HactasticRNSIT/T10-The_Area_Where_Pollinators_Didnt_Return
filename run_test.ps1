$ErrorActionPreference = "Stop"
Set-Location -Path "c:\Users\sridh\OneDrive\Desktop\all projects\poly_nexus\backend"
& .\venv\Scripts\Activate.ps1

$env:POLYNEXUS_MOCK_EXTERNAL = "1"
$env:ENABLE_EFFICACY_ENDPOINT = "1"
$env:POLYNEXUS_API_KEY = "test_key"
$env:ANALYSE_RATE_LIMIT = "200/minute"
$env:COMPARE_RATE_LIMIT = "60/minute"

$uvicornProcess = Start-Process -NoNewWindow -PassThru `
    -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "api:app", "--port", "8000" `
    -RedirectStandardOutput "server_log.txt" `
    -RedirectStandardError "server_log_err.txt"

Start-Sleep -Seconds 5
python -m locust -f loadtest\locustfile.py --host=http://localhost:8000 --headless -u 10 -r 2 -t 30s > locust_output_final.txt 2>&1
Stop-Process -Id $uvicornProcess.Id -Force
