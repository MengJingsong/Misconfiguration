# tombstone_flood_optimized.py — fixed for Phase 1 connection deaths + OOM detection
# Usage: python tombstone_flood_optimized.py <NODE_IP>

import argparse
import os
import subprocess
import time
import warnings
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
warnings.filterwarnings("ignore", category=DeprecationWarning)

from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement, ConsistencyLevel
from cassandra.policies import RoundRobinPolicy
from cassandra.concurrent import execute_concurrent_with_args
from cassandra import OperationTimedOut, NoHostAvailable, ConnectionShutdown

# ── Argument parsing ──────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(
    description="Tombstone flood experiment with Phase 1 OOM detection"
)
parser.add_argument("node_ip", help="IP address of the Cassandra node")
parser.add_argument("--rows", type=int, default=800_000,
    help="Number of rows to write (default: 800,000)")
parser.add_argument("--blob-size", type=int, default=8,
    help="Blob size in bytes (default: 8)")
parser.add_argument("--concurrency", type=int, default=256,
    help="Async write concurrency (default: 256)")
parser.add_argument("--auto-adjust", action="store_true",
    help="Auto-reduce row count if Phase 1 fails")
parser.add_argument("--skip-phase-5", action="store_true",
    help="Skip the tombstone scan (test Phase 1 only)")
args = parser.parse_args()

NODE_IP = args.node_ip
ROW_COUNT = args.rows
BLOB_SIZE = args.blob_size
CONCURRENCY = args.concurrency

# ── Constants ─────────────────────────────────────────────────────────────────

SERVER_USER = "jason92"
CASSANDRA_HOME = "/mydata/apache-cassandra-5.0.7"

# ── Global monitoring state ───────────────────────────────────────────────────

monitoring_active = False
heap_samples = []
gc_pause_count = 0

# ── SSH nodetool helper ───────────────────────────────────────────────────────

def ssh_nodetool(cmd, silent=False):
    full = f"{CASSANDRA_HOME}/bin/nodetool {cmd}"
    result = subprocess.run(
        ["ssh", f"{SERVER_USER}@{NODE_IP}", full],
        capture_output=True, text=True, timeout=30
    )
    if not silent and result.stdout.strip():
        print(f"  {result.stdout.strip()}")
    if result.returncode != 0 and not silent:
        print(f"  [WARN] {result.stderr.strip()}")
    return result.stdout.strip() if result.returncode == 0 else None

# ── Heap monitoring ───────────────────────────────────────────────────────────

def get_heap_info():
    """Get current heap usage via nodetool info"""
    try:
        info = ssh_nodetool("info", silent=True)
        if not info:
            return None

        # Parse heap line: "Heap Memory (MB): 156.78 / 192.00"
        for line in info.split('\n'):
            if 'Heap Memory' in line:
                parts = line.split(':')[1].strip().split('/')
                used_mb = float(parts[0].strip())
                max_mb = float(parts[1].strip())
                return {'used': used_mb, 'max': max_mb, 'percent': (used_mb / max_mb) * 100}
        return None
    except Exception:
        return None

def get_gc_stats():
    """Get GC statistics"""
    try:
        gc_info = ssh_nodetool("gcstats", silent=True)
        if gc_info and "Full GC" in gc_info:
            # Count lines with GC info
            lines = [l for l in gc_info.split('\n') if 'ms' in l and ('G1' in l or 'Full' in l)]
            return len(lines)
        return 0
    except Exception:
        return 0

def heap_monitor_thread():
    """Background thread to monitor heap and GC during writes"""
    global monitoring_active, heap_samples, gc_pause_count

    initial_gc_count = get_gc_stats()
    start_time = time.time()

    while monitoring_active:
        try:
            heap = get_heap_info()
            if heap:
                heap['timestamp'] = time.time() - start_time
                heap_samples.append(heap)

                # Check for danger zone
                if heap['percent'] > 90:
                    print(f"  [HEAP WARNING] {heap['percent']:.1f}% used ({heap['used']:.1f}/{heap['max']:.1f} MB)")
                elif heap['percent'] > 95:
                    print(f"  [HEAP CRITICAL] {heap['percent']:.1f}% used - OOM imminent!")

                # Update GC count
                current_gc = get_gc_stats()
                if current_gc > initial_gc_count:
                    gc_pause_count = current_gc - initial_gc_count

        except Exception:
            pass

        time.sleep(2)  # Sample every 2 seconds

# ── Phase 1 with async writes and monitoring ──────────────────────────────────

def execute_phase_1_with_monitoring(session, insert_stmt, blob):
    """Execute Phase 1 with heap monitoring and async writes"""
    global monitoring_active, heap_samples, gc_pause_count

    # Start heap monitoring
    monitoring_active = True
    heap_samples = []
    gc_pause_count = 0

    monitor_thread = threading.Thread(target=heap_monitor_thread, daemon=True)
    monitor_thread.start()

    print(f"[Phase 1] Writing {ROW_COUNT:,} rows asynchronously (concurrency: {CONCURRENCY}) ...")

    # Calculate expected heap pressure
    row_overhead = 200  # BTreeRow + BufferCell + LivenessInfo overhead
    expected_heap_mb = (ROW_COUNT * (BLOB_SIZE + row_overhead)) / (1024 * 1024)
    print(f"          Expected heap pressure: ~{expected_heap_mb:.1f} MB (live rows in memtable)")

    t0 = time.time()
    try:
        # Prepare parameters for concurrent execution
        params = [(1, i, blob) for i in range(ROW_COUNT)]

        # Execute with progress tracking
        batch_size = 50_000  # Process in batches for progress reporting
        total_processed = 0

        for i in range(0, len(params), batch_size):
            batch_params = params[i:i + batch_size]
            batch_start = time.time()

            try:
                results = execute_concurrent_with_args(
                    session, insert_stmt, batch_params,
                    concurrency=CONCURRENCY,
                    raise_on_first_error=False
                )

                # Check for failures in this batch
                failures = [r for r in results if not r.success]
                if failures:
                    print(f"  [WARN] {len(failures)} failures in batch {i // batch_size + 1}")
                    for fail in failures[:3]:  # Show first 3
                        print(f"    {type(fail.result).__name__}: {fail.result}")

                total_processed += len(batch_params)
                batch_time = time.time() - batch_start
                rate = len(batch_params) / batch_time if batch_time > 0 else 0

                print(f"  Wrote {total_processed:,} / {ROW_COUNT:,} ({rate:.0f} rows/s)")

            except Exception as e:
                print(f"  [ERROR] Batch {i // batch_size + 1} failed: {e}")
                raise

        elapsed = time.time() - t0
        rate = ROW_COUNT / elapsed if elapsed > 0 else 0
        print(f"  Done in {elapsed:.1f}s ({rate:.0f} rows/s avg)")

        return True, None

    except (NoHostAvailable, ConnectionShutdown) as e:
        elapsed = time.time() - t0
        return False, f"Connection lost after {elapsed:.1f}s: {e}"
    except OperationTimedOut as e:
        elapsed = time.time() - t0
        return False, f"Write timeout after {elapsed:.1f}s: {e}"
    except Exception as e:
        elapsed = time.time() - t0
        return False, f"Unexpected error after {elapsed:.1f}s: {e}"
    finally:
        # Stop monitoring
        monitoring_active = False
        time.sleep(1)  # Let monitor thread finish

def analyze_phase_1_failure():
    """Analyze why Phase 1 failed and provide recommendations"""
    print("\n[Phase 1 Analysis] Diagnosing failure...")

    # Check if we got heap samples
    if not heap_samples:
        print("  No heap data collected - likely immediate connection failure")
        print("  Recommendations:")
        print("    1. Check if Cassandra is running and accessible")
        print("    2. Verify SSH access and nodetool permissions")
        print("    3. Try smaller row count (--rows 100000)")
        return

    max_heap = max(s['percent'] for s in heap_samples) if heap_samples else 0
    avg_heap = sum(s['percent'] for s in heap_samples) / len(heap_samples) if heap_samples else 0

    print(f"  Heap usage: max {max_heap:.1f}%, avg {avg_heap:.1f}%")
    print(f"  GC pauses during write: {gc_pause_count}")

    # Classify failure type
    if max_heap > 95:
        print("  DIAGNOSIS: Phase 1 OOM - heap exhausted during writes")
        print("  The node ran out of memory before completing the write phase.")
        print("  This is DIFFERENT from the intended tombstone-scan OOM.")
        print("  Recommendations:")
        print("    1. Increase JVM heap size (-Xmx512m or higher)")
        print("    2. Reduce memtable_heap_space in cassandra.yaml")
        print("    3. Or reduce row count with --rows 400000")

    elif gc_pause_count > 20:
        print("  DIAGNOSIS: GC thrashing - too many long pauses")
        print("  The JVM spent too much time in garbage collection.")
        print("  Recommendations:")
        print("    1. Increase heap size to reduce GC pressure")
        print("    2. Use async writes (already enabled)")
        print("    3. Reduce write rate with lower --concurrency")

    elif avg_heap < 50:
        print("  DIAGNOSIS: Network/timeout issue - not heap related")
        print("  The server had plenty of heap space but connection failed.")
        print("  Recommendations:")
        print("    1. Check network connectivity")
        print("    2. Increase driver timeouts")
        print("    3. Check server logs for other errors")
    else:
        print("  DIAGNOSIS: Mixed pressure - heap + GC pauses")
        print("  Recommendations:")
        print("    1. Increase heap size moderately")
        print("    2. Check if other processes are using memory")
        print("    3. Try smaller batches")

# ── Pre-flight checks ─────────────────────────────────────────────────────────

def preflight_checks():
    """Pre-flight configuration and heap estimation"""
    print(f"[Pre-flight] Target node: {NODE_IP}")
    print("[Pre-flight] Configuring timeouts and checking heap...")

    # Get current heap info
    heap_info = get_heap_info()
    if not heap_info:
        print("  [WARN] Could not get heap info - SSH/nodetool issues?")
        heap_max_mb = 192  # Assume default from your config
    else:
        heap_max_mb = heap_info['max']
        heap_used_mb = heap_info['used']
        print(f"  Current heap: {heap_used_mb:.1f} / {heap_max_mb:.1f} MB ({heap_info['percent']:.1f}%)")

    # Disable auto-compaction
    try:
        ssh_nodetool("disableautocompaction oomtest wide")
        print("  Auto-compaction: disabled on oomtest.wide")
    except Exception:
        print("  [WARN] Could not disable auto-compaction")

    # Estimate heap requirements
    metaspace_mb = 56
    available_mb = heap_max_mb - metaspace_mb

    # Phase 1 estimate: row overhead + blob
    row_overhead = 200  # BTreeRow + BufferCell + LivenessInfo + clustering key
    phase1_pressure_mb = ROW_COUNT * (BLOB_SIZE + row_overhead) / (1024 * 1024)

    # Phase 5 estimate: tombstone objects only
    tombstone_mb = ROW_COUNT * 200 / (1024 * 1024)

    print(f"\n  Heap analysis:")
    print(f"    Max heap:              {heap_max_mb:.0f} MB")
    print(f"    Available for data:    {available_mb:.0f} MB")
    print(f"    Phase 1 pressure:      {phase1_pressure_mb:.1f} MB ({ROW_COUNT:,} live rows)")
    print(f"    Phase 5 pressure:      {tombstone_mb:.1f} MB ({ROW_COUNT:,} tombstones)")

    # Recommendations
    if phase1_pressure_mb > available_mb * 0.8:
        print(f"  [WARNING] Phase 1 may fail - writes need {phase1_pressure_mb:.1f}MB, only {available_mb:.1f}MB available")
        if args.auto_adjust:
            new_count = int(ROW_COUNT * (available_mb * 0.6) / phase1_pressure_mb)
            print(f"  [AUTO-ADJUST] Reducing row count to {new_count:,}")
            return new_count
        else:
            print("  Recommendation: use --auto-adjust or --rows <smaller_number>")

    if tombstone_mb <= available_mb:
        print(f"  [INFO] Phase 5 may NOT OOM - tombstones need {tombstone_mb:.1f}MB, {available_mb:.1f}MB available")
        print(f"         Consider shrinking heap to ~{tombstone_mb + 50:.0f}MB to guarantee Phase 5 OOM")

    return ROW_COUNT

# ── Main execution ────────────────────────────────────────────────────────────

def main():
    global ROW_COUNT, monitoring_active, heap_samples

    # Pre-flight checks and potential row count adjustment
    ROW_COUNT = preflight_checks()

    # Connect with robust timeouts
    print(f"\n[Connect] Establishing connection with extended timeouts...")
    cluster = Cluster(
        [NODE_IP],
        load_balancing_policy=RoundRobinPolicy(),
        protocol_version=5,
        connect_timeout=120,         # Extended from default 5s
        idle_heartbeat_interval=120, # Extended from default 30s
        idle_heartbeat_timeout=120,  # Extended from default 30s
        control_connection_timeout=120,
    )

    try:
        session = cluster.connect('oomtest')
        session.default_timeout = 7200  # 2 hour timeout
        session.default_fetch_size = None

        insert_stmt = session.prepare("INSERT INTO wide (pk, ck, val) VALUES (?, ?, ?)")
        delete_stmt = session.prepare("DELETE FROM wide WHERE pk = ? AND ck = ?")
        blob = os.urandom(BLOB_SIZE)

        print("  Connection established successfully")

        # ── Phase 1: Write with monitoring ──────────────────────────────────────

        success, error = execute_phase_1_with_monitoring(session, insert_stmt, blob)

        if not success:
            print(f"\n[Phase 1 FAILED] {error}")
            analyze_phase_1_failure()

            if args.auto_adjust and "Connection lost" in str(error) and ROW_COUNT > 100_000:
                print(f"\n[Auto-retry] Trying with 50% fewer rows...")
                ROW_COUNT = ROW_COUNT // 2
                success, error = execute_phase_1_with_monitoring(session, insert_stmt, blob)
                if not success:
                    print(f"\n[Auto-retry FAILED] {error}")
                    return
            else:
                return

        print(f"[Phase 1 SUCCESS] All {ROW_COUNT:,} rows written")

        if args.skip_phase_5:
            print("[Skipping Phase 5] Use --skip-phase-5 to test Phase 1 only")
            return

        # ── Phase 2: Flush ──────────────────────────────────────────────────────

        print("\n[Phase 2] Flushing live rows to SSTables...")
        ssh_nodetool("flush oomtest wide")

        # ── Phase 3: Delete rows ────────────────────────────────────────────────

        print(f"\n[Phase 3] Writing {ROW_COUNT:,} tombstones...")
        t0 = time.time()

        # Use batch deletes for speed
        delete_params = [(1, i) for i in range(ROW_COUNT)]

        for i in range(0, len(delete_params), 50_000):
            batch_params = delete_params[i:i + 50_000]
            execute_concurrent_with_args(
                session, delete_stmt, batch_params,
                concurrency=CONCURRENCY, raise_on_first_error=False
            )
            print(f"  deleted {min(i + 50_000, ROW_COUNT):,} / {ROW_COUNT:,}", end="\r")

        print(f"\n  Done in {time.time() - t0:.1f}s")

        # ── Phase 4: Flush tombstones ───────────────────────────────────────────

        print("\n[Phase 4] Flushing tombstones to SSTables...")
        ssh_nodetool("flush oomtest wide")

        # ── Phase 5: Trigger OOM ────────────────────────────────────────────────

        print(f"\n[Phase 5] Full partition scan - attempting to load {ROW_COUNT:,} tombstones into heap...")

        scan_stmt = SimpleStatement(
            "SELECT * FROM wide WHERE pk = 1",
            consistency_level=ConsistencyLevel.ONE,
            fetch_size=None,  # Disable paging - critical for OOM
        )

        # Start heap monitoring for Phase 5
        monitoring_active = True
        heap_samples = []
        monitor_thread = threading.Thread(target=heap_monitor_thread, daemon=True)
        monitor_thread.start()

        t0 = time.time()
        try:
            print("  Executing scan... (watch heap in another terminal)")
            rows = list(session.execute(scan_stmt))
            elapsed = time.time() - t0

            print(f"\n[Phase 5 UNEXPECTED] Scan completed in {elapsed:.1f}s - {len(rows):,} rows returned")
            print("  No OOM occurred - the scan succeeded. This means:")
            print("    1. Heap was larger than expected, OR")
            print("    2. Tombstones were compacted away, OR")
            print("    3. Row count was insufficient for OOM")

            max_heap = max(s['percent'] for s in heap_samples) if heap_samples else 0
            print(f"  Peak heap during scan: {max_heap:.1f}%")

        except Exception as e:
            elapsed = time.time() - t0
            print(f"\n[Phase 5 RESULT] Exception after {elapsed:.1f}s: {type(e).__name__}: {e}")

            # Check what type of failure
            if "OutOfMemory" in str(e) or "heap" in str(e).lower():
                print("  SUCCESS! This is the intended tombstone-flood OOM.")
                print("  The coordinator ran out of heap materializing tombstones.")
            elif "timeout" in str(e).lower():
                print("  Timeout during scan - server may be under extreme GC pressure.")
                print("  This could indicate the OOM attack is working.")
            else:
                print("  Unexpected error type - check server logs.")

        finally:
            monitoring_active = False

    except Exception as e:
        print(f"[FATAL] {e}")

    finally:
        cluster.shutdown()

if __name__ == "__main__":
    main()
