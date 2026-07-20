import sys
import io
import pytest
from contextlib import redirect_stdout, redirect_stderr
    
out = io.StringIO()
err = io.StringIO()
    
with redirect_stdout(out), redirect_stderr(err):
    exit_code = pytest.main(["c:/Users/sridh/OneDrive/Desktop/all projects/poly_nexus/backend/tests/test_anomaly_golden.py", "-v"])
        
with open("c:/Users/sridh/OneDrive/Desktop/all projects/poly_nexus/backend/pytest_output.txt", "w") as f:
    f.write(f"EXIT CODE: {exit_code}\n")
    f.write("--- STDOUT ---\n")
    f.write(out.getvalue())
    f.write("--- STDERR ---\n")
    f.write(err.getvalue())
