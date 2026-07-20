import subprocess
p = subprocess.run([r"c:\Users\sridh\OneDrive\Desktop\all projects\poly_nexus\backend\venv\Scripts\pytest.exe", "-v"], capture_output=True, text=True)
print("STDOUT:", p.stdout)
print("STDERR:", p.stderr)
print("CODE:", p.returncode)
