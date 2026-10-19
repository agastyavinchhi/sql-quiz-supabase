import os
import sys
from decimal import Decimal

import psycopg2
from psycopg2 import errors
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    dbname=os.getenv("POSTGRES_DB", "postgres"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT", "5432"),
    sslmode=os.getenv("DB_SSLMODE", "require"),
)
cur = conn.cursor()
failed = False

cur.execute("SELECT current_user")
print("Connected as", cur.fetchone()[0])

# Quiz answers still match the hints
checks = [
    ("Q1 rock tracks",
     "SELECT COUNT(*) FROM track t JOIN genre g ON g.genre_id = t.genre_id WHERE g.name = %s",
     ("Rock",), 1297),
    ("Q4 total sales", "SELECT SUM(total) FROM invoice", None, Decimal("2328.60")),
]
for name, sql, params, expected in checks:
    cur.execute(sql, params)
    got = cur.fetchone()[0]
    ok = got == expected
    failed |= not ok
    print(f"{'OK  ' if ok else 'FAIL'} {name}: got {got}, expected {expected}")

# Integrity: the taker role must not be able to edit the audit log
try:
    cur.execute("UPDATE audit_log SET action = 'save'")
    print("FAIL quiz_reader was able to UPDATE audit_log")
    failed = True
except errors.InsufficientPrivilege:
    print("OK   quiz_reader cannot UPDATE audit_log")
conn.rollback()

cur.close()
conn.close()
sys.exit(1 if failed else 0)