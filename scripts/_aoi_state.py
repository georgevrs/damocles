"""Tiny one-shot for inspecting AoI store state."""
import duckdb
conn = duckdb.connect("data/damocles.duckdb")

print("=== aoi.source ===")
for row in conn.execute("SELECT source, count(*) FROM aoi GROUP BY source").fetchall():
    print(f"  {row[0]}: {row[1]}")

print()
print("=== aoi.threat_grade (AI only) ===")
for row in conn.execute(
    "SELECT threat_grade, count(*) FROM aoi WHERE source='ai' GROUP BY threat_grade ORDER BY 1"
).fetchall():
    print(f"  {row[0]}: {row[1]}")

print()
print("=== distinct scans ===")
for row in conn.execute(
    "SELECT scan_id, count(*) FROM aoi WHERE source='ai' GROUP BY scan_id ORDER BY 2 DESC"
).fetchall():
    print(f"  {row[0]}: {row[1]}")

print()
print("=== composite source-type x is_water (raw_ais) ===")
total = conn.execute("SELECT count(*) FROM raw_ais").fetchone()[0]
water = conn.execute("SELECT count(*) FROM raw_ais WHERE is_water").fetchone()[0]
land  = conn.execute("SELECT count(*) FROM raw_ais WHERE is_water = false").fetchone()[0]
null  = conn.execute("SELECT count(*) FROM raw_ais WHERE is_water IS NULL").fetchone()[0]
print(f"  raw_ais: total={total}, water={water}, land={land}, null={null}")

total = conn.execute("SELECT count(*) FROM raw_sar").fetchone()[0]
water = conn.execute("SELECT count(*) FROM raw_sar WHERE is_water").fetchone()[0]
land  = conn.execute("SELECT count(*) FROM raw_sar WHERE is_water = false").fetchone()[0]
null  = conn.execute("SELECT count(*) FROM raw_sar WHERE is_water IS NULL").fetchone()[0]
print(f"  raw_sar: total={total}, water={water}, land={land}, null={null}")

conn.close()
