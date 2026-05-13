"""Recreate the aoi table from the latest pass — works around a DuckDB
index-sync bug that fails DELETE on the existing rows."""
import sys
import duckdb

conn = duckdb.connect("data/damocles.duckdb")
before = conn.execute("SELECT count(*) FROM aoi").fetchone()[0]
sys.stdout.write(f"before: {before} total AoIs\n"); sys.stdout.flush()

# Snapshot the rows we want to KEEP (latest AI pass + all user AoIs)
conn.execute("""
    CREATE OR REPLACE TABLE _aoi_keep AS
    SELECT * FROM aoi
     WHERE source = 'user' OR scan_id = 'scan-w1-quality-pass'
""")
keep = conn.execute("SELECT count(*) FROM _aoi_keep").fetchone()[0]
sys.stdout.write(f"keep:   {keep} rows\n"); sys.stdout.flush()

# Rebuild
conn.execute("DROP TABLE aoi")
conn.execute("ALTER TABLE _aoi_keep RENAME TO aoi")
# Restore indices (CREATE INDEX IF NOT EXISTS is idempotent)
conn.execute("CREATE INDEX IF NOT EXISTS idx_aoi_source ON aoi (source)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_aoi_scan   ON aoi (scan_id)")
conn.commit()

after = conn.execute("SELECT count(*) FROM aoi").fetchone()[0]
sys.stdout.write(f"after:  {after} total AoIs\n"); sys.stdout.flush()
sys.stdout.write(f"deleted: {before - after}\n"); sys.stdout.flush()
conn.close()
