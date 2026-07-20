"""
Gate check for Task 7: Count intervention rows in the SQLite database.
Run with: <venv_python> count_interventions.py
Writes result to stdout; exit 0 if >=30, exit 1 if <30.
"""
import sqlite3
import os
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = os.environ.get(
    "HISTORY_DB_PATH",
    str(DATA_DIR / "polynexus_history.db")
)

OUTFILE = r"C:\Users\sridh\.gemini\antigravity-ide\brain\244abb44-c025-4ffd-bbfa-9f652fb46938\scratch\intervention_count.txt"

if not Path(DB_PATH).exists():
    msg = f"DB not found at {DB_PATH} — 0 intervention rows\n"
    with open(OUTFILE, "w") as f:
        f.write(msg)
    print(msg)
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
try:
    row = conn.execute("SELECT COUNT(*) FROM interventions").fetchone()
    count = row[0]
except Exception as e:
    count = 0
    msg_extra = f" (error: {e})"
else:
    msg_extra = ""

conn.close()

msg = f"intervention row count = {count}{msg_extra}\n"
with open(OUTFILE, "w") as f:
    f.write(msg)
print(msg)
sys.exit(0 if count >= 30 else 1)
