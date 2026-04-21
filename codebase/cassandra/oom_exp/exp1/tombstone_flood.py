# 01_tombstone_flood.py
import os
import subprocess
import time
from cassandra.cluster import Cluster
from cassandra.policies import RoundRobinPolicy
from cassandra.query import SimpleStatement, ConsistencyLevel

NODE_IP = "128.110.216.213"
ROW_COUNT = 500_000       # increase if OOM doesn't happen fast enough
BATCH_SIZE = 1000         # rows per execute loop print
BLOB_SIZE  = 512          # bytes per row (small — we want quantity, not size)

cluster = Cluster([NODE_IP], load_balancing_policy=RoundRobinPolicy(), protocol_version=5)
session = cluster.connect('oomtest')

# Prepare statements (faster than string queries in a loop)
insert_stmt = session.prepare("INSERT INTO wide (pk, ck, val) VALUES (?, ?, ?)")
delete_stmt = session.prepare("DELETE FROM wide WHERE pk = ? AND ck = ?")

blob = os.urandom(BLOB_SIZE)

# ── Phase 1: Write rows ──────────────────────────────────────────────────────
print(f"[Phase 1] Writing {ROW_COUNT:,} rows to pk=1 ...")
t0 = time.time()
for i in range(ROW_COUNT):
    session.execute(insert_stmt, (1, i, blob))
    if i % BATCH_SIZE == 0:
        print(f"  wrote {i:,} / {ROW_COUNT:,}", end="\r")
print(f"\n  Done in {time.time()-t0:.1f}s")

# ── Phase 2: Flush live data to SSTables ────────────────────────────────────
print("[Phase 2] Flushing live rows to disk (nodetool flush) ...")
subprocess.run(["nodetool", "-h", NODE_IP, "flush", "oomtest", "wide"], check=True)
print("  Flush complete.")

# ── Phase 3: Delete every row (creates one tombstone per row) ────────────────
print(f"[Phase 3] Deleting {ROW_COUNT:,} rows to create tombstones ...")
t0 = time.time()
for i in range(ROW_COUNT):
    session.execute(delete_stmt, (1, i))
    if i % BATCH_SIZE == 0:
        print(f"  deleted {i:,} / {ROW_COUNT:,}", end="\r")
print(f"\n  Done in {time.time()-t0:.1f}s")

# ── Phase 4: Flush tombstones to SSTables ────────────────────────────────────
print("[Phase 4] Flushing tombstones to disk ...")
subprocess.run(["nodetool", "-h", NODE_IP, "flush", "oomtest", "wide"], check=True)
print("  Flush complete.")

# ── Phase 5: Full partition scan — the OOM trigger ───────────────────────────
# The coordinator must hold ALL tombstones in heap simultaneously.
# With tombstone_failure_threshold set to max, this will NOT be aborted.
# Watch heap on the Cassandra node climb to 100%.
print("[Phase 5] Triggering full partition scan (pk=1) ...")
print("          >> Watch heap on the Cassandra node NOW <<")
t0 = time.time()

scan_stmt = SimpleStatement(
    "SELECT * FROM wide WHERE pk = 1",
    consistency_level=ConsistencyLevel.ONE,
    fetch_size=None       # None = disable paging, force full result into memory at once
)

rows = list(session.execute(scan_stmt))
print(f"  Scan complete in {time.time()-t0:.1f}s — returned {len(rows):,} rows")

cluster.shutdown()
