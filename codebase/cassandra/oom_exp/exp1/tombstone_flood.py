# tombstone_flood.py — tuned for 192MiB heap
import os
import subprocess
import time
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement, ConsistencyLevel
from cassandra.policies import RoundRobinPolicy

NODE_IP        = "128.110.216.213"
SERVER_USER    = "jason92"
CASSANDRA_HOME = "/mydata/apache-cassandra-5.0.7"

ROW_COUNT   = 800_000   # 800k × 200 bytes = 160MiB > 136MiB available → OOM
BLOB_SIZE   = 512
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
    if result.returncode != 0:
        print(f"  [WARN] {result.stderr.strip()}")
    return result.stdout.strip()

# ── Pre-flight ────────────────────────────────────────────────────────────────

print("[Pre-flight] Setting live thresholds, timeouts, disabling compaction ...")
ssh_nodetool("settombstonethresholds 2147483647 2147483647")
ssh_nodetool("setcachedreplicarowsthresholds 2147483647 2147483647")
for kind in ["read", "range", "write", "misc"]:
    ssh_nodetool(f"settimeout {kind} {TIMEOUT_MS}", silent=True)
ssh_nodetool("disableautocompaction oomtest wide")  # prevent compaction from purging tombstones

tombstone_conf = ssh_nodetool("gettombstonethresholds", silent=True)
read_to        = ssh_nodetool("gettimeout read", silent=True)
heap_info      = ssh_nodetool("info", silent=True)
heap_line      = next((l for l in heap_info.split("\n") if "Heap" in l), "unknown")
print(f"  Tombstone thresholds : {tombstone_conf}")
print(f"  Live read timeout    : {read_to} ms")
print(f"  Heap                 : {heap_line.strip()}")
print(f"  Auto-compaction      : disabled on oomtest.wide")

# Sanity check: estimate whether ROW_COUNT is sufficient for OOM
import re
m = re.search(r'[\d.]+\s*/\s*([\d.]+)', heap_line)
if m:
    heap_max_mb = float(m.group(1))
    metaspace_mb = 56          # observed from your gc.log
    available_mb = heap_max_mb - metaspace_mb
    tombstone_mb = ROW_COUNT * 200 / (1024 * 1024)
    print(f"\n  Heap max:            {heap_max_mb:.0f} MiB")
    print(f"  Metaspace overhead:  {metaspace_mb} MiB")
    print(f"  Available for scan:  {available_mb:.0f} MiB")
    print(f"  Tombstones needed:   {tombstone_mb:.0f} MiB ({ROW_COUNT:,} × 200B)")
    if tombstone_mb > available_mb:
        print(f"  [OK] Tombstones ({tombstone_mb:.0f}MiB) > available ({available_mb:.0f}MiB) → OOM expected")
    else:
        shortfall = available_mb - tombstone_mb
        needed = int((available_mb + 50) * 1024 * 1024 / 200)
        print(f"  [WARN] Tombstones ({tombstone_mb:.0f}MiB) < available ({available_mb:.0f}MiB) by {shortfall:.0f}MiB")
        print(f"         Increase ROW_COUNT to at least {needed:,} or reduce heap further")
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
session.default_fetch_size = None   # disable paging — force all into heap at once

insert_stmt = session.prepare("INSERT INTO wide (pk, ck, val) VALUES (?, ?, ?)")
delete_stmt = session.prepare("DELETE FROM wide WHERE pk = ? AND ck = ?")
blob = os.urandom(BLOB_SIZE)

# ── Phase 1: Write rows ───────────────────────────────────────────────────────

print(f"[Phase 1] Writing {ROW_COUNT:,} rows (pk=1, {BLOB_SIZE}B each) ...")
t0 = time.time()
for i in range(ROW_COUNT):
    session.execute(insert_stmt, (1, i, blob))
    if i % BATCH_PRINT == 0:
        print(f"  wrote {i:,} / {ROW_COUNT:,}", end="\r")
print(f"\n  Done in {time.time()-t0:.1f}s")

# ── Phase 2: Flush live data ──────────────────────────────────────────────────

print("\n[Phase 2] Flushing live rows to SSTables ...")
ssh_nodetool("flush oomtest wide")

# Disable compaction NOW — before Phase 3 writes tombstones — so they
# cannot be merged with live data and purged before Phase 5 scan.
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

# Confirm SSTable count — both live-data SSTables and tombstone SSTables
# should be present and NOT yet compacted together.
print("\n[Info] SSTable count before scan (should be multiple uncompacted files):")
ssh_nodetool("cfstats oomtest.wide")

# ── Phase 5: Trigger OOM ──────────────────────────────────────────────────────

print(f"""
[Phase 5] Full partition scan of pk=1
  Loading {ROW_COUNT:,} tombstones into coordinator heap simultaneously.
  Expected: ~{ROW_COUNT * 200 // (1024*1024)}MiB tombstone heap pressure
            against ~{int(heap_max_mb) - metaspace_mb}MiB available
            → OOM expected

  >> Watch these on the SERVER NODE in separate terminals:

  Terminal 1 — heap climbing to 100%:
    watch -n1 "{CASSANDRA_HOME}/bin/nodetool info | grep Heap"

  Terminal 2 — GC thrashing and OOM event:
    tail -f {CASSANDRA_HOME}/logs/gc.log

  Terminal 3 — OOM in system log:
    tail -f {CASSANDRA_HOME}/logs/system.log | grep -iE "OutOfMemory|GC overhead|tombstone|heap"

  Terminal 4 — OS-level process memory:
    PID=$(pgrep -f CassandraDaemon)
    watch -n1 "ps -p $PID -o pid,rss,%mem --no-header"
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
    print("  No OOM — tombstones still fit in heap.")
    print("  → Reduce heap further (try 160MiB) or increase ROW_COUNT.")

except Exception as e:
    elapsed = time.time() - t0
    print(f"\n  Exception after {elapsed:.1f}s: {e}")

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
        print("  Nothing in system.log yet — checking dmesg ...")
        dmesg = subprocess.run(
            ["ssh", f"{SERVER_USER}@{NODE_IP}",
             "sudo dmesg | grep -iE 'oom|killed process' | tail -5"],
            capture_output=True, text=True
        )
        if dmesg.stdout.strip():
            print(f"  [dmesg]:\n{dmesg.stdout}")

finally:
    cluster.shutdown()
