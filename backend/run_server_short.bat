@echo off
cd /d "c:\Users\sridh\OneDrive\Desktop\ALLPRO~1\poly_nexus\backend"
call venv\Scripts\activate.bat
set POLYNEXUS_API_KEY=test-api-key-123
python -u -m uvicorn api:app --host 127.0.0.1 --port 8000 --reload
