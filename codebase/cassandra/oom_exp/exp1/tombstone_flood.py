# tombstone_flood.py — fixed for Cassandra 5.x, 192MiB heap
# Usage: python tombstone_flood.py <NODE_IP>
#   e.g. python tombstone_flood.py 128.110.216.213

import argparse
import os
import subprocess
import time
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement, ConsistencyLevel
from cassandra.policies import RoundRobinPolicy

# ── Argument parsing ──────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(
    description="Tombstone flood experiment — triggers OOM on a Cassandra node."
)
parser.add_argument(
    "node_ip",
    metavar="NODE_IP",
    help="IP address of the Cassandra node (e.g. 128.110.216.213)",
)
args = parser.parse_args()
NODE_IP = args.node_ip

# ── Constants ─────────────────────────────────────────────────────────────────

SERVER_USER    = "jason92"
CASSANDRA_HOME = "/mydata/apache-cassandra-5.0.7"

# KEY: tiny blob so Phase 1 writes never OOM the node.
# Tombstones are ~200B in heap regardless of the original value size.
ROW_COUNT   = 800_000   # needs to exceed ~712K to OOM a 192MiB heap
BLOB_SIZE   = 8         # small — live data must not fill the heap
BATCH_PRINT = 10_000
TIMEOUT_MS  = 3_600_000
TIMEOUT_S   = 7_200

# ── SSH nodetool helper ───────────────────────────────────────────────────────

def ssh_nodetool(cmd, silent=False):
    full = f"{CASSANDRA_HOME}/bin/nodetool {cmd}"
    result = subprocess.run(
        ["ssh", f"{SERVER_USER}@{NODE_IP}", full],
        capture_output=True, text=True
    )
    if not silent and result.stdout.strip():
        print(f"  {result.stdout.strip()}")
    if result.returncode != 0 and not silent:
        print(f"  [WARN] {result.stderr.strip()}")
    return result.stdout.strip()

# ── Pre-flight ────────────────────────────────────────────────────────────────

print(f"[Pre-flight] Target node: {NODE_IP}")
print("[Pre-flight] Configuring timeouts and disabling compaction ...")

# NOTE: In Cassandra 5.x, tombstone/replica-row thresholds are set in cassandra.yaml.
# The nodetool commands settombstonethresholds / setcachedreplicarowsthresholds
# do NOT exist in C* 5. They are already set to 2147483647 in cassandra.yaml.

for kind in ["read", "range", "write", "misc"]:
    ssh_nodetool(f"settimeout {kind} {TIMEOUT_MS}", silent=True)

ssh_nodetool("disableautocompaction oomtest wide")

read_to   = ssh_nodetool("gettimeout read", silent=True)
heap_info = ssh_nodetool("info", silent=True)
heap_line = next((l for l in heap_info.split("\n") if "Heap" in l), "unknown")

print(f"  Live read timeout    : {read_to}")
print(f"  Heap                 : {heap_line.strip()}")
print(f"  Auto-compaction      : disabled on oomtest.wide")
print(f"  Tombstone thresholds : set to MAX in cassandra.yaml (C*5 — no nodetool command)")

import re
m = re.search(r'[\d.]+\s*/\s*([\d.]+)', heap_line)
heap_max_mb = float(m.group(1)) if m else 192.0
metaspace_mb = 56
available_mb = heap_max_mb - metaspace_mb
tombstone_mb = ROW_COUNT * 200 / (1024 * 1024)
write_pressure_mb = ROW_COUNT * BLOB_SIZE / (1024 * 1024)

print(f"\n  Heap max:              {heap_max_mb:.0f} MiB")
print(f"  Metaspace overhead:    {metaspace_mb} MiB")
print(f"  Available for scan:    {available_mb:.0f} MiB")
print(f"  Write pressure (live): {write_pressure_mb:.1f} MiB  ({ROW_COUNT:,} × {BLOB_SIZE}B) — safe")
print(f"  Tombstones in heap:    {tombstone_mb:.0f} MiB  ({ROW_COUNT:,} × 200B)")

if tombstone_mb > available_mb:
    print(f"  [OK] Tombstones ({tombstone_mb:.0f}MiB) > available ({available_mb:.0f}MiB) → OOM expected during scan")
else:
    needed = int((available_mb + 50) * 1024 * 1024 / 200)
    print(f"  [WARN] Tombstones ({tombstone_mb:.0f}MiB) < available ({available_mb:.0f}MiB)")
    print(f"         Increase ROW_COUNT to at least {needed:,}")
print()

# ── Connect ───────────────────────────────────────────────────────────────────

cluster = Cluster(
    [NODE_IP],
    load_balancing_policy=RoundRobinPolicy(),
    protocol_version=5,
    connect_timeout=60,
)
session = cluster.connect('oomtest')
session.default_timeout    = TIMEOUT_S
session.default_fetch_size = None   # disable paging — force all tombstones into heap at once

insert_stmt = session.prepare("INSERT INTO wide (pk, ck, val) VALUES (?, ?, ?)")
delete_stmt = session.prepare("DELETE FROM wide WHERE pk = ? AND ck = ?")
blob = os.urandom(BLOB_SIZE)

# ── Phase 1: Write rows ───────────────────────────────────────────────────────

print(f"[Phase 1] Writing {ROW_COUNT:,} rows (pk=1, {BLOB_SIZE}B blob each) ...")
print(f"          Write pressure: {write_pressure_mb:.1f} MiB — well within memtable limits")
t0 = time.time()
for i in range(ROW_COUNT):
    session.execute(insert_stmt, (1, i, blob))
    if i % BATCH_PRINT == 0:
        print(f"  wrote {i:,} / {ROW_COUNT:,}", end="\r")
print(f"\n  Done in {time.time()-t0:.1f}s")

# ── Phase 2: Flush live data ──────────────────────────────────────────────────

print("\n[Phase 2] Flushing live rows to SSTables ...")
ssh_nodetool("flush oomtest wide")

print("[Phase 2b] Confirming auto-compaction is disabled ...")
ssh_nodetool("disableautocompaction oomtest wide")

# ── Phase 3: Delete every row ─────────────────────────────────────────────────

print(f"\n[Phase 3] Writing {ROW_COUNT:,} tombstones ...")
t0 = time.time()
for i in range(ROW_COUNT):
    session.execute(delete_stmt, (1, i))
    if i % BATCH_PRINT == 0:
        print(f"  deleted {i:,} / {ROW_COUNT:,}", end="\r")
print(f"\n  Done in {time.time()-t0:.1f}s")

# ── Phase 4: Flush tombstones ─────────────────────────────────────────────────

print("\n[Phase 4] Flushing tombstones to SSTables ...")
ssh_nodetool("flush oomtest wide")

print("\n[Info] SSTable count before scan:")
ssh_nodetool("cfstats oomtest.wide")

# ── Phase 5: Trigger OOM ──────────────────────────────────────────────────────

print(f"""
[Phase 5] Full partition scan — loading {ROW_COUNT:,} tombstones into coordinator heap.
  Expected heap pressure: ~{int(tombstone_mb)}MiB against ~{int(available_mb)}MiB available → OOM

  Open these on the SERVER in separate terminals before proceeding:

  Terminal 1 — watch heap climb:
    watch -n1 "{CASSANDRA_HOME}/bin/nodetool info | grep Heap"

  Terminal 2 — GC thrashing:
    tail -f {CASSANDRA_HOME}/logs/gc.log

  Terminal 3 — OOM events:
    tail -f {CASSANDRA_HOME}/logs/system.log | grep -iE "OutOfMemory|GC overhead|tombstone|heap"

  Terminal 4 — OS process memory:
    PID=$(pgrep -f CassandraDaemon); watch -n1 "ps -p $PID -o pid,rss,%mem --no-header"
""")

scan_stmt = SimpleStatement(
    "SELECT * FROM wide WHERE pk = 1",
    consistency_level=ConsistencyLevel.ONE,
    fetch_size=None,
)

t0 = time.time()
try:
    rows = list(session.execute(scan_stmt))
    elapsed = time.time() - t0
    print(f"\n  Scan complete in {elapsed:.1f}s — {len(rows):,} rows returned")
    print("  No OOM — try increasing ROW_COUNT by 100K increments.")

except Exception as e:
    elapsed = time.time() - t0
    print(f"\n  Exception after {elapsed:.1f}s: {type(e).__name__}: {e}")

    print("\n  Checking server logs for OOM evidence ...")
    result = subprocess.run(
        ["ssh", f"{SERVER_USER}@{NODE_IP}",
         f"grep -iE 'OutOfMemory|GC overhead|heap space' "
         f"{CASSANDRA_HOME}/logs/system.log | tail -10"],
        capture_output=True, text=True
    )
    if result.stdout.strip():
        print(f"\n  [system.log OOM lines]:\n{result.stdout}")
    else:
        dmesg = subprocess.run(
            ["ssh", f"{SERVER_USER}@{NODE_IP}",
             "sudo dmesg | grep -iE 'oom|killed process' | tail -5"],
            capture_output=True, text=True
        )
        if dmesg.stdout.strip():
            print(f"  [dmesg OOM]:\n{dmesg.stdout}")
        else:
            print("  Nothing in logs yet — check gc.log and system.log manually.")

finally:
    cluster.shutdown()
