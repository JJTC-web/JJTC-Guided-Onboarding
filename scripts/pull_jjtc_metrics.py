"""
Pull live numbers for the "Metrics That Matter" deck from the JJTC app's
Railway Postgres database.

WHERE TO RUN THIS
------------------
This can't be run from inside Claude's sandbox - Claude's environment can't
reach your Railway database over the network. Run it yourself:
  1. On your own machine (with `pip install psycopg2-binary` first), or
  2. Via `railway run python pull_jjtc_metrics.py` from the JJTC Railway
     project directory (this automatically injects DATABASE_URL for you).

SETUP
-----
Set your database connection string as an environment variable before running:
    export DATABASE_URL="postgresql://user:pass@host:port/dbname"
(Railway shows this under your Postgres service -> Variables -> DATABASE_URL.)

If the NPS/survey app uses a *separate* Postgres database from the main JJTC
app, you'll need to run this twice - once per DATABASE_URL - or add a second
connection below.

FIRST RUN: use --inspect
-------------------------
    python pull_jjtc_metrics.py --inspect
This lists every table and its columns so we can see your real schema and
fill in the correct table/column names below (the QUERIES dict currently has
placeholders based on what's been described in conversation, not confirmed
column names).
"""

import argparse
import os
import sys

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.exit("Missing dependency. Run: pip install psycopg2-binary")


def connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Set DATABASE_URL first (see instructions at top of this file).")
    return psycopg2.connect(url)


def inspect_schema(conn):
    """List all tables and columns in the connected database."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position;
        """)
        rows = cur.fetchall()

    current_table = None
    for table, column, dtype in rows:
        if table != current_table:
            print(f"\n{table}")
            current_table = table
        print(f"  - {column} ({dtype})")


# ---------------------------------------------------------------------------
# EDIT THIS: once --inspect shows the real schema, update table/column names
# below to match. These are placeholders based on what's been mentioned in
# conversation (a `subscribers` table exists; NPS table name unconfirmed).
# ---------------------------------------------------------------------------
QUERIES = {
    "Total subscribers/leads captured": "SELECT COUNT(*) FROM subscribers;",
    "Welcome emails sent": "SELECT COUNT(*) FROM subscribers WHERE welcome_email_sent_at IS NOT NULL;",
    "Workbook emails sent": "SELECT COUNT(*) FROM subscribers WHERE workbook_email_sent_at IS NOT NULL;",
    # "NPS responses total": "SELECT COUNT(*) FROM nps_responses;",
    # "NPS promoters": "SELECT COUNT(*) FROM nps_responses WHERE category = 'promoter';",
    # "NPS passives": "SELECT COUNT(*) FROM nps_responses WHERE category = 'passive';",
    # "NPS detractors": "SELECT COUNT(*) FROM nps_responses WHERE category = 'detractor';",
}


def run_metrics(conn):
    with conn.cursor() as cur:
        for label, query in QUERIES.items():
            try:
                cur.execute(query)
                result = cur.fetchone()[0]
                print(f"{label}: {result}")
            except Exception as e:
                conn.rollback()
                print(f"{label}: FAILED ({e})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect", action="store_true", help="List tables/columns instead of running metrics")
    args = parser.parse_args()

    conn = connect()
    if args.inspect:
        inspect_schema(conn)
    else:
        run_metrics(conn)
    conn.close()
