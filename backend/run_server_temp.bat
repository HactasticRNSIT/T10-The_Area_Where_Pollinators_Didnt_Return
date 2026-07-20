@echo on
cd /d "c:\Users\sridh\OneDrive\Desktop\all projects\poly_nexus\backend"
call venv\Scripts\activate.bat
set POLYNEXUS_API_KEY=test-api-key-123
python -u -m uvicorn api:app --host 127.0.0.1 --port 8000 > "c:\Users\sridh\OneDrive\Desktop\all projects\poly_nexus\backend\my_server_out.log" 2>&1
