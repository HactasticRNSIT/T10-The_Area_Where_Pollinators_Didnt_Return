@echo off
cd /d "c:\Users\sridh\OneDrive\Desktop\all projects\poly_nexus\backend"
call venv\Scripts\activate.bat
pytest tests/test_anomaly_golden.py -v
