import sys
import pytest

if __name__ == "__main__":
    with open(r"C:\Users\sridh\.gemini\antigravity-ide\brain\244abb44-c025-4ffd-bbfa-9f652fb46938\scratch\pytest_api_output.txt", "w") as f:
        # We need to capture pytest output. There are plugins for this or we can redirect stdout.
        # simpler: just use pytest's built-in file logging or standard python redirection
        pass

    # A better way is to redirect sys.stdout inside python
    import io
    from contextlib import redirect_stdout, redirect_stderr
    
    out = io.StringIO()
    err = io.StringIO()
    
    with redirect_stdout(out), redirect_stderr(err):
        exit_code = pytest.main(["c:/Users/sridh/OneDrive/Desktop/all projects/poly_nexus/backend/tests/test_anomaly_golden.py", "-v"])
        
    with open(r"C:\Users\sridh\.gemini\antigravity-ide\brain\244abb44-c025-4ffd-bbfa-9f652fb46938\scratch\pytest_api_output.txt", "w") as f:
        f.write(f"EXIT CODE: {exit_code}\n")
        f.write("--- STDOUT ---\n")
        f.write(out.getvalue())
        f.write("--- STDERR ---\n")
        f.write(err.getvalue())
