"""Diagnose the AoI table state."""
import duckdb
conn = duckdb.connect("data/damocles.duckdb")

print("=== distinct (source, scan_id) ===")
rows = conn.execute(
    "SELECT source, scan_id, count(*) FROM aoi GROUP BY source, scan_id ORDER BY 3 DESC"
).fetchall()
for r in rows:
    print(f"  source={r[0]!r:18s}  scan={r[1]!r:30s}  count={r[2]}")

print()
print(f"=== TOTAL: {conn.execute('SELECT count(*) FROM aoi').fetchone()[0]} ===")
conn.close()
