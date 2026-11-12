<!-- file: cases/data_output_stream_plus_temp_buffer_size-retrievetemporarybuffer-bytes.length--autonomous.md -->
# cassandra.data_output_stream_plus_temp_buffer_size — verification solution

| Field | Value |
|---|---|
| Entry pointer | [`DataOutputStreamPlus.java:51`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputStreamPlus.java#L51) (`MAX_BUFFER_SIZE = DATA_OUTPUT_STREAM_PLUS_TEMP_BUFFER_SIZE.getInt()`: where the capacity gets its value; the enforcing check is at line 59, see A3) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code autonomous subagent, 2026-11-11 |
| Estimate | `positive`: the per-thread scratch `byte[]` kept in a `FastThreadLocal` is only ever replaced by an array of length `min(MAX_BUFFER_SIZE, 2*highestOneBit(request))` (line 62), so its length, and the heap it retains on every thread that writes through this path, never exceeds the property; raising the property lets the same workload retain proportionally more heap per thread (up to the rounded request size). Caveat: at the default (8 KiB) the bounded object is small (8 KiB per thread). |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `cassandra.data_output_stream_plus_temp_buffer_size`, a JVM system
property (an entry of the `CassandraRelevantProperties` enum), first declared at
[`CassandraRelevantProperties.java:184`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L184)
as `DATA_OUTPUT_STREAM_PLUS_TEMP_BUFFER_SIZE("cassandra.data_output_stream_plus_temp_buffer_size", "8192")`.
Unit: bytes (length of a `byte[]`). Default `8192`, a literal string default, parsed by
`getInt()` (`CassandraRelevantProperties.java:794-800`: `System.getProperty(key)`, else the default,
through `INTEGER_CONVERTER`). It is read once into the `private static final int MAX_BUFFER_SIZE` at
[`DataOutputStreamPlus.java:51`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputStreamPlus.java#L51)
when the class is initialised. Settable only as `-Dcassandra.data_output_stream_plus_temp_buffer_size=<int>`
on the JVM command line (e.g. `JVM_EXTRA_OPTS` / `conf/jvm-server.options`); not in `cassandra.yaml`,
not via JMX; a change needs a JVM restart. Not mentioned in `conf/` or `NEWS.txt`.

**A2. What it caps.** Heap: the length of the per-thread temporary `byte[]` held by the
`FastThreadLocal<byte[]> tempBuffer` (`DataOutputStreamPlus.java:68-75`, initial value
`new byte[16]`). The array is retained for the life of the thread (the thread-local is never
cleared or shrunk), so the retained heap is `Σ over threads that used it of bytes.length`. The
quantity compared against the limit is `minSize`, the number of bytes the caller wants to stage
(`Math.min(minSize, MAX_BUFFER_SIZE)` at line 59); the resulting `bytes.length` is the operand
this case measures.

**A3. Mechanism.**
1. `retrieveTemporaryBuffer(int minSize)` (`DataOutputStreamPlus.java:56`) reads the thread's
   current array (line 58).
2. The check:
   [`DataOutputStreamPlus.java:59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputStreamPlus.java#L59)
   `if (bytes.length < Math.min(minSize, MAX_BUFFER_SIZE))`.
   - True: allocate
     [`DataOutputStreamPlus.java:62`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputStreamPlus.java#L62)
     `new byte[Math.min(MAX_BUFFER_SIZE, 2 * Integer.highestOneBit(minSize))]` and store it in the
     thread-local (line 63). The new length is capped by `MAX_BUFFER_SIZE`.
   - False: the existing array is returned, even if smaller than `minSize` (once at the cap). It never shrinks.
3. Callers then process data in chunks of `bytes.length`, so a request larger than the cap is
   served by looping, not by a larger array:
   - the default `WritableByteChannel` of `DataOutputStreamPlus` (`DataOutputStreamPlus.java:95-131`):
     for a non-array (direct) `ByteBuffer` of ≥16 bytes it calls `retrieveTemporaryBuffer(toWrite)`
     (line 115) and copies in chunks of `buf.length` (line 120). Reached from
     `UnbufferedDataOutputStreamPlus.write(ByteBuffer)` for direct buffers
     (`UnbufferedDataOutputStreamPlus.java:357-369`, `channel.write(hollowBufferD)` at 368) whenever the
     subclass did not supply a channel, e.g. `WrappedDataOutputStreamPlus(OutputStream)`
     (`WrappedDataOutputStreamPlus.java:33-37`).
   - `UnbufferedDataOutputStreamPlus.writeUTF(String, DataOutput)` (`UnbufferedDataOutputStreamPlus.java:252-339`):
     `retrieveTemporaryBuffer(utfCount + 2)` at line 277 after rejecting `utfCount > 65535` (line 274), so
     this path never requests more than 65537 bytes (array ≤ 131072). Also used by
     `BufferedDataOutputStreamPlus.writeUTF` (`BufferedDataOutputStreamPlus.java:255-258`).
4. A node path that reaches the large direct-buffer case: the serializing row cache.
   `SerializingCache.serialize` (`SerializingCache.java:91-117`) serializes the cached partition with
   `new WrappedDataOutputStreamPlus(new MemoryOutputStream(freeableMemory))` (line 109, default channel);
   cell values go through `ByteBufferAccessor.write` → `out.write(ByteBuffer)`
   (`ByteBufferAccessor.java:61-64`). With `memtable_allocation_type: offheap_buffers`, values larger than
   128 KiB are held in their own direct `ByteBuffer` (`SlabAllocator.java:92-99`, `MAX_CLONED_SIZE` at line 52),
   and a row-cache miss caches what it reads from memtable + disk without copying
   (`SinglePartitionReadCommand.java:561`, `:604`, `:608` → `SerializingCache.replace` at
   `SerializingCache.java:210`). So a read of a large memtable-resident blob with
   `SerializingCacheProvider` calls `retrieveTemporaryBuffer(valueSize)` on the reading thread.

Overshoot / bypass:
- Power-of-two rounding: below the cap, the array is up to 2× the request (request 4096 → 8192,
  request 4 MiB → 8 MiB); never above the cap.
- The initial array is 16 bytes regardless of the property, so a property `< 16` does not shrink it.
- Overflow (only if the property is raised above 2^30): `2 * Integer.highestOneBit(minSize)` is
  `Integer.MIN_VALUE` for `minSize ≥ 2^30`, giving `NegativeArraySizeException` (not a bypass).
- The cap is per thread; the total retained is `threads × cap`, unbounded by this property in thread
  count (SEP worker threads, Netty event loops, compaction threads, etc.).
- Subclasses that override `newDefaultChannel` (`DataOutputBuffer.java:191`, `AsyncChannelOutputPlus.java:263`)
  or the buffered `write(ByteBuffer)` (`BufferedDataOutputStreamPlus.java:124`) do not use this buffer for
  ByteBuffer writes.

**A4. Other consumers.** Everything else on the heap; in the cluster workload notably: memtable
on-heap metadata, the transient client request/response buffers (4 MiB blobs; collected by the full GC
before each histogram), the key cache, Netty buffers (mostly direct). Off-heap: memtable direct buffers
and row-cache `RefCountedMemory` (not `byte[]`, so not in the `byte[]` histogram line).

**A5. Evidence beyond the source.** `CHANGES.txt:3539` (CASSANDRA-10203, "Fix broken
UnbufferedDataOutputStreamPlus.writeUTF"), https://issues.apache.org/jira/browse/CASSANDRA-10203 — history
of the writeUTF chunking that relies on this buffer. JDK `Integer.highestOneBit`:
https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Integer.html#highestOneBit(int).
JFR `jdk.ObjectAllocationOutsideTLAB` and `jfr print`: https://docs.oracle.com/en/java/javase/11/tools/jfr.html.
No test in the tree sets this property (`grep -rn data_output_stream_plus_temp_buffer_size test/` finds nothing).

## B. Verification solution

**B1. Claim under test.** For every thread, the length of the `DataOutputStreamPlus` temporary
buffer (and hence the heap it retains) is at most `cassandra.data_output_stream_plus_temp_buffer_size`;
for a request `r ≥ 16` it equals `min(P, 2*highestOneBit(r))` once grown, so retained heap
follows the property up to the rounded request size. The claim is wrong if any observed array is
longer than `P` (for `P ≥ 16`), or if, under the same workload, retained heap does not change with `P`.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk and build there:
```
export WORK=/mydata/o43-s4            # local disk, not shared storage
mkdir -p $WORK && rsync -a ~/cassandra-5.0.9/ $WORK/src/
cd $WORK/src && ant jar               # produces build/classes/main and build/lib/jars
```
Probe source outside the tree: `$WORK/probe/org/apache/cassandra/io/util/TempBufferProbe.java`
(same package so the `protected static retrieveTemporaryBuffer` is accessible). JVM options:
`-Xms1g -Xmx1g` plus the `--add-exports`/`--add-opens` lines of `conf/jvm11-server.options` (99-115).

> *Amendment A1 (stage-4 audit, 2026-11-12; runbook only, B2f/B2g/B3f/B3g unchanged by it):* on the shared stage-4
> node `WORK=/mydata/jingsong-cass-s4/o43`; the tree is made with
> `cassandra/stage4-runtime-verification/copy-source.sh $WORK/src` (5.0.9 from this repository) and built with
> `ant build-test` (a superset of `ant jar`). The probe source and the run/analysis scripts are kept in
> `cassandra/stage4-runtime-verification/harness/data_output_stream_plus_temp_buffer_size-retrievetemporarybuffer-bytes.length--autonomous/`
> and copied to `$WORK/probe/...` before compiling; the B2f/B2g comparison is done by a Python analyzer there,
> not by eye.

```java
package org.apache.cassandra.io.util;

import java.io.*;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.CountDownLatch;

public class TempBufferProbe
{
    static int cur() { return DataOutputStreamPlus.retrieveTemporaryBuffer(1).length; } // 1 <= len: never reallocates
    static final OutputStream SINK = new OutputStream() {
        public void write(int b) {}
        public void write(byte[] b, int o, int l) {}
    };
    static long heapUsed() { System.gc(); System.gc(); return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed(); }

    public static void main(String[] args) throws Exception
    {
        System.out.println("P=" + System.getProperty("cassandra.data_output_stream_plus_temp_buffer_size", "default"));
        // 1. direct calls, one thread, increasing requests
        System.out.println("initial len=" + cur());
        for (int r : new int[]{ 100, 5000, 8193, 65537, 1 << 20, 4 << 20, 20 << 20 })
            System.out.println("request=" + r + " len=" + DataOutputStreamPlus.retrieveTemporaryBuffer(r).length);
        // 2. real paths, each on a fresh thread
        Thread t1 = new Thread(() -> { try {
            new WrappedDataOutputStreamPlus(SINK).write(ByteBuffer.allocateDirect(4 << 20));
            System.out.println("directWrite 4MiB len=" + cur()); } catch (IOException e) { throw new UncheckedIOException(e); } });
        t1.start(); t1.join();
        Thread t2 = new Thread(() -> { try {
            char[] c = new char[60000]; Arrays.fill(c, 'x');
            new WrappedDataOutputStreamPlus(SINK).writeUTF(new String(c));
            System.out.println("writeUTF 60000 len=" + cur()); } catch (IOException e) { throw new UncheckedIOException(e); } });
        t2.start(); t2.join();
        // 3. 32 live threads, each writes a 4 MiB direct buffer, then waits
        int n = 32; CountDownLatch done = new CountDownLatch(n), release = new CountDownLatch(1);
        int[] lens = new int[n];
        ByteBuffer src = ByteBuffer.allocateDirect(4 << 20);
        long before = heapUsed();
        for (int i = 0; i < n; i++) { final int id = i; new Thread(() -> { try {
            new WrappedDataOutputStreamPlus(SINK).write(src.duplicate()); lens[id] = cur(); done.countDown(); release.await();
        } catch (Exception e) { throw new RuntimeException(e); } }).start(); }
        done.await();
        long after = heapUsed();
        System.out.println("threads=" + n + " sumLen=" + Arrays.stream(lens).asLongStream().sum()
                           + " maxLen=" + Arrays.stream(lens).max().getAsInt() + " heapDelta=" + (after - before));
        release.countDown();
    }
}
```

**B2b. Knobs.** `P` = `-Dcassandra.data_output_stream_plus_temp_buffer_size=`: `4096` (below default),
unset (default 8192), `1048576`, `16777216`. One JVM per value, because `MAX_BUFFER_SIZE` is a static
final read at class load. The values put the cap below, at, and between/above the 4 MiB and 20 MiB requests.

**B2c. Workload.** Requests 100 B … 20 MiB (part 1), a 4 MiB direct write and a 60000-char ASCII
`writeUTF` (part 2), 32 threads × 4 MiB direct writes (part 3). Every request ≥ 5000 exceeds
`P=4096`; 4 MiB and 20 MiB exceed `P=1 MiB`; 20 MiB exceeds `P=16 MiB`; so each cap is reached and
exceeded. Part 3 at `P=16 MiB`: 32 × 8 MiB = 256 MiB < 1 GiB heap.

**B2d. Observables and instruments.** `bytes.length` of the thread-local array via
`retrieveTemporaryBuffer(1)` (does not reallocate since length ≥ 16 > 1), printed per step; sum of
lengths over 32 live threads; heap-used delta from `MemoryMXBean` after `System.gc()` (approximate).
Not observable directly: which code holds the array (inferred from the probe design).

**B2e. Procedure.**
```
cd $WORK/src
CP="build/classes/main:build/lib/jars/*:lib/*"
mkdir -p $WORK/probe-out
javac -cp "$CP" -d $WORK/probe-out $WORK/probe/org/apache/cassandra/io/util/TempBufferProbe.java
OPENS=$(grep -E '^--add-(exports|opens)' conf/jvm11-server.options | tr '\n' ' ')
for P in 4096 default 1048576 16777216; do
  D=""; [ "$P" != default ] && D="-Dcassandra.data_output_stream_plus_temp_buffer_size=$P"
  java -Xms1g -Xmx1g $OPENS $D -cp "$WORK/probe-out:$CP" org.apache.cassandra.io.util.TempBufferProbe \
     | tee $WORK/unit-$P.log
done
```

**B2f. Predictions.** (lengths in bytes; initial len = 16 for all)

| step | P=4096 | P=8192 (default) | P=1048576 | P=16777216 |
|---|---|---|---|---|
| request=100 | 128 | 128 | 128 | 128 |
| request=5000 | 4096 | 8192 | 8192 | 8192 |
| request=8193 | 4096 | 8192 | 16384 | 16384 |
| request=65537 | 4096 | 8192 | 131072 | 131072 |
| request=1 MiB | 4096 | 8192 | 1048576 | 2097152 |
| request=4 MiB | 4096 | 8192 | 1048576 | 8388608 |
| request=20 MiB | 4096 | 8192 | 1048576 | 16777216 |
| directWrite 4 MiB | 4096 | 8192 | 1048576 | 8388608 |
| writeUTF 60000 | 4096 | 8192 | 65536 | 65536 |
| part 3 sumLen (32 thr) | 131072 | 262144 | 33554432 | 268435456 |
| part 3 heapDelta | ≈ 0.1 MiB (noise) | ≈ 0.25 MiB (noise) | ≈ 32 MiB | ≈ 256 MiB (± a few MiB) |

In every row `len ≤ P`.

> *Amendment A3 (stage-4 audit, 2026-11-12, before any reading):* "within a few MiB" / "± a few MiB" for `heapDelta`
> means `|heapDelta − sumLen| ≤ max(4 MiB, 10 % of sumLen)`; at `P=4096` and the default, `heapDelta` within ±4 MiB
> of 0 is "noise". Row added to B2g below (marked A3) for `heapDelta` well below `sumLen`.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| All lengths match B2f; `len ≤ P` everywhere | Claim confirmed at the operand level. |
| Any `len > P` (P ≥ 16) | Claim wrong: the cap is bypassed. |
| Lengths identical across P values for requests > 8192 | Property not applied (not read or wrong name); claim refuted for the knob. |
| `heapDelta` tracks `sumLen` (within a few MiB) | Retained heap follows the operand. |
| `heapDelta` ≫ `sumLen` at the same P | Something else allocates; inspect before concluding. |
| (A3, 2026-11-12) `heapDelta` below `sumLen` by more than the A3 tolerance at `P ≥ 1 MiB`, lengths as in B2f | Arrays not retained (or instrument fault): the operand-level result stands, the retained-heap part of B1 is not confirmed. |
| writeUTF len > 131072 at any P | `utfCount` limit (line 274) misread. |

**B2h. Controls.** Part 1 at `P=16777216` is the positive control (the same request sequence
grows the array to 16 MiB when the cap is high). `P=4096` vs default shows the cap acts below the
default too. `retrieveTemporaryBuffer(1)` as the reader cannot itself grow the array. Fresh threads in
parts 2 and 3 exclude carry-over from part 1.

### B3. Cluster tier

**B3a. Environment and build.** One node on the stage-4 machine (16 cores, ~14 GiB free), built as
in B2a in `$WORK/src`. Run data on local disk:
```
mkdir -p $WORK/node/{data,commitlog,hints,saved_caches,cdc,logs}
```
Edit `$WORK/src/conf/cassandra.yaml` (copy, not the shared tree):
```
data_file_directories: [ $WORK/node/data ]       # write the expanded absolute path
commitlog_directory: $WORK/node/commitlog
hints_directory: $WORK/node/hints
saved_caches_directory: $WORK/node/saved_caches
cdc_raw_directory: $WORK/node/cdc
memtable_allocation_type: offheap_buffers        # >128 KiB values become direct ByteBuffers (SlabAllocator.java:92-99)
memtable_heap_space: 1024MiB
memtable_offheap_space: 2048MiB                  # keep the 256 MiB of blobs in the memtable (no flush)
row_cache_class_name: org.apache.cassandra.cache.SerializingCacheProvider
row_cache_size: 1024MiB
row_cache_save_period: 0s
```
Heap: `export MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M`. Check ports 7000/7199/9042 are free
(`ss -ltn | grep -E ':(7000|7199|9042) '`); if not, change `storage_port`, `native_transport_port`
and `JMX_PORT` in `conf/cassandra-env.sh`. Memory budget: 4 GiB heap + ≤ 256 MiB memtable direct
+ ≤ 300 MiB row cache off-heap + JVM overhead < 6 GiB.

> *Amendment A2 (stage-4 audit, 2026-11-12; runbook only, B3f/B3g unchanged):* on the shared node the ports are
> fixed, not "change if busy": `storage_port: 7300`, `ssl_storage_port: 7301`, `native_transport_port: 9342`,
> `JMX_PORT="7499"` in `conf/cassandra-env.sh` (so every `nodetool` call takes `-p 7499`), `listen_address` and
> `rpc_address` `127.0.0.1`, seeds `"127.0.0.1:7300"`; the driver connects to port 9342. `MAX_DIRECT_MEMORY_SIZE=2G`
> is set with `MAX_HEAP_SIZE` (5.0.9's `cassandra-env.sh` sets `-XX:MaxDirectMemorySize` itself, and the 256 MiB of
> memtable values are `allocateDirect` buffers). `JVM_EXTRA_OPTS` is passed only on the `bin/cassandra` command line,
> never exported (environment.md §6). The JFR count of B3e is done by the harness's Python parser of
> `jfr print` output (same events, same "stack contains `retrieveTemporaryBuffer`" criterion, sizes in bytes).

**B3b. Knobs.** `P` via `export JVM_EXTRA_OPTS="-Dcassandra.data_output_stream_plus_temp_buffer_size=$P"`:
default (unset, 8192), `1048576`, `16777216`. Fresh node (data wiped) per value. Plus the control run
(B3h) at `P=16777216` with `memtable_allocation_type: heap_buffers`.

**B3c. Workload.** Table `o43.t (k int PRIMARY KEY, v blob)` with
`caching = {'keys':'ALL','rows_per_partition':'ALL'}`. Write 64 partitions × 4 MiB random blob
(256 MiB, all in the memtable: below `memtable_offheap_space` × cleanup threshold ≈ 2048 × 0.33 ≈ 680 MiB;
4 MiB mutation < `max_mutation_size` = 16 MiB; 4 MiB frame < 16 MiB native frame). Then read each
partition once with 32 concurrent requests: each read is a row-cache miss that serializes the 4 MiB
direct value through `retrieveTemporaryBuffer(4194304)`, so each executing thread grows its array to
`A(P) = min(P, 8388608)` = 8 KiB / 1 MiB / 8 MiB. The 64 misses run on `T` distinct threads,
`1 ≤ T ≤ 64`. Duration: < 2 min per value.

> *Audit note A4 (stage-4 audit, 2026-11-12, from source only, before any run; workload, B3f and B3g not changed):*
> the spot-check of A3 step 4 found that a read from a SkipList memtable goes through
> `AtomicBTreePartition.unfilteredIterator` → `allocator.ensureOnHeap().applyToPartition(...)`
> (`AtomicBTreePartition.java:220-223`), and for `offheap_buffers` the allocator's `ensureOnHeap` is
> `EnsureOnHeap.CloneToHeap` (`SlabAllocator.java:70`), which clones every row with `HeapCloner`
> (`EnsureOnHeap.java:60-65`, `HeapCloner.java:33-35`: `ByteBuffer.allocate`). The partition handed to
> `CachedBTreePartition.create` therefore holds heap values, and `UnbufferedDataOutputStreamPlus.write(ByteBuffer)`
> takes the array branch (line 359-361) as in the B3h control. SSTable reads also produce heap values
> (`ByteBufferUtil.read`, `ByteBufferUtil.java:444-452`). The audit therefore expects the B3g row "No
> `retrieveTemporaryBuffer` allocations at any `P`, 64 row-cache misses seen" (not confirmed). The tier is run as
> written, because it is executable and its conclusions table already names this outcome; a substitute workload would no
> longer test the traced path (stage-4 README). Recommendation to stage 3 in section D.

Workload script `$WORK/o43.py` (bundled driver):
```python
import os, sys
from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent_with_args
mode, n, size, conc = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
s = Cluster(['127.0.0.1'], port=9042).connect()
s.default_timeout = 60
if mode == 'write':
    s.execute("CREATE KEYSPACE IF NOT EXISTS o43 WITH replication={'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE IF NOT EXISTS o43.t (k int PRIMARY KEY, v blob) WITH caching={'keys':'ALL','rows_per_partition':'ALL'}")
    ins = s.prepare("INSERT INTO o43.t (k, v) VALUES (?, ?)")
    for k in range(n): s.execute(ins, (k, os.urandom(size)))
else:
    sel = s.prepare("SELECT k, v FROM o43.t WHERE k = ?")
    res = execute_concurrent_with_args(s, sel, [(k,) for k in range(n)], concurrency=conc)
    print("ok", sum(1 for ok, _ in res if ok))
```

**B3d. Observables and instruments.**
- Live `byte[]` heap: `jcmd $PID GC.class_histogram` (forces a full GC) → the `[B` line's bytes;
  taken after the writes (baseline `H0`) and after the reads (`H1`); `ΔH = H1 − H0`.
- Number and size of temp-buffer allocations: JFR started before the reads
  (`jcmd $PID JFR.start name=o43 settings=profile filename=$WORK/o43-$P.jfr`), dumped after; count
  `jdk.ObjectAllocationOutsideTLAB` / `jdk.ObjectAllocationInNewTLAB` events whose stack contains
  `retrieveTemporaryBuffer`, with their `allocationSize`. This gives `T` (one allocation per thread,
  since every request has the same size) and confirms the path is exercised.
- Row-cache misses: `nodetool info | grep 'Row Cache'` (requests/hits) — expect 64 misses on the read pass.
- Memtable not flushed: `nodetool tablestats o43.t` shows `SSTable count: 0`.
Not observable directly: which thread-local owns a given `byte[]` (inferred from ΔH ≈ T × A).

**B3e. Procedure.** For each `P` in `default 1048576 16777216`:
```
cd $WORK/src
rm -rf $WORK/node/{data,commitlog,hints,saved_caches,cdc}/* ; mkdir -p $WORK/node/logs
export MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M CASSANDRA_LOG_DIR=$WORK/node/logs
export JVM_EXTRA_OPTS=""; [ "$P" != default ] && export JVM_EXTRA_OPTS="-Dcassandra.data_output_stream_plus_temp_buffer_size=$P"
bin/cassandra -p $WORK/node/pid
until bin/nodetool status 2>/dev/null | grep -q '^UN'; do sleep 5; done
PID=$(cat $WORK/node/pid)
jinfo -sysprops $PID | grep data_output_stream_plus || echo "P unset (default 8192)"
export PYTHONPATH=$(ls $WORK/src/lib/cassandra-driver-internal-only-*.zip)
python3 $WORK/o43.py write 64 4194304 1
bin/nodetool tablestats o43.t | grep 'SSTable count'          # expect 0
jcmd $PID GC.class_histogram | grep -E ' \[B$' | tee $WORK/h0-$P.txt
jcmd $PID JFR.start name=o43 settings=profile filename=$WORK/o43-$P.jfr
python3 $WORK/o43.py read 64 0 32                               # expect "ok 64"
jcmd $PID JFR.dump name=o43 ; jcmd $PID JFR.stop name=o43
bin/nodetool info | grep 'Row Cache'
jcmd $PID GC.class_histogram | grep -E ' \[B$' | tee $WORK/h1-$P.txt
jfr print --events 'jdk.ObjectAllocationOutsideTLAB,jdk.ObjectAllocationInNewTLAB' --stack-depth 20 $WORK/o43-$P.jfr \
  | awk '/^jdk.ObjectAllocation/{if(hit)print sz; hit=0; sz=""} /allocationSize/{sz=$3$4} /retrieveTemporaryBuffer/{hit=1} END{if(hit)print sz}' \
  | sort | uniq -c | tee $WORK/jfr-$P.txt
bin/nodetool stopdaemon; sleep 5; kill $PID 2>/dev/null; pgrep -f CassandraDaemon && echo "LEFTOVER"
```
(If `jdk.ObjectAllocationInNewTLAB` is not sampled for small sizes at the default `P`, only the 1 MiB and
16 MiB runs need the JFR count.) Then the control run (B3h).

> *Amendment A5 (stage-4 run 1, runbook defect D1, 2026-11-12; B3f/B3g unchanged):* the bundled driver zip holds the
> package under a top-level `cassandra-driver-<ver>/` directory, so `PYTHONPATH=<zip>` fails with
> `ModuleNotFoundError: No module named 'cassandra'`. Use
> `export PYTHONPATH=$(ls $WORK/src/lib/cassandra-driver-internal-only-*.zip)/cassandra-driver-3.29.0` (as
> `bin/cqlsh.py:56` does). The cluster tier restarted from its beginning.

**B3f. Predictions.**
- Default `P`: `A = 8192`; `ΔH ≤ 64 × 8 KiB = 512 KiB`, i.e. within histogram noise (|ΔH| < 16 MiB).
- `P = 1048576`: `A = 1 MiB`; JFR shows `T` allocations of 1 MiB (`1 ≤ T ≤ 64`), none larger;
  `ΔH ≈ T × 1 MiB` (±16 MiB noise).
- `P = 16777216`: `A = 8 MiB`; JFR shows `T'` allocations of 8 MiB, none larger than 16 MiB;
  `ΔH ≈ T' × 8 MiB`; with `T' ≈ T`, `ΔH(16 MiB) ≈ 8 × ΔH(1 MiB)`, tens to a few hundred MiB
  (≤ 512 MiB).
- In all runs no JFR temp-buffer allocation exceeds `P`.
- Claim wrong if: any temp-buffer allocation > `P`; or `ΔH` at `P=16 MiB` ≈ `ΔH` at default while JFR
  shows the 8 MiB allocations (they would not be retained).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| JFR sizes = `A(P)`, never > `P`; ΔH ≈ T×A(P); ΔH grows ~8× from 1 MiB to 16 MiB | Claim confirmed: retained heap follows the property. |
| A temp-buffer allocation > `P` | Claim wrong (cap bypassed). |
| JFR shows 8 MiB allocations but ΔH ≈ 0 at `P=16 MiB` | Arrays not retained; claim (retained heap follows P) wrong. |
| No `retrieveTemporaryBuffer` allocations at any `P`, 64 row-cache misses seen | Path not exercised (values not direct, or different serialization); not confirmed; check `memtable_allocation_type` and SSTable count. |
| Row-cache misses < 64 or SSTable count > 0 | Workload did not reach the path; re-run. |
| ΔH large at default `P` | Another `byte[]` consumer (A4); compare with the control run. |

**B3h. Controls.**
- Control run at `P=16777216` with `memtable_allocation_type: heap_buffers` (everything else equal):
  values are heap buffers, `UnbufferedDataOutputStreamPlus.write(ByteBuffer)` takes the array branch
  (line 359-361) and never calls the temp buffer → predicted no 8 MiB temp-buffer allocations in JFR
  and ΔH within noise. This separates "the knob" from "the workload".
- Positive control: the `P=16777216` offheap run itself — the same workload that stays flat at the
  default moves heap by `T × 8 MiB` when the cap is high.
- `jinfo -sysprops` confirms the property reached the JVM; `GC.class_histogram` forces full GC so
  transient client buffers are excluded.

**B4. Risks and cleanup.** Disk: ≤ 300 MiB commit log + no SSTables per run, all under
`$WORK/node` on local disk; logs under `$WORK/node/logs`. Memory: ≤ 6 GiB per node run, ≤ 1.3 GiB
per unit JVM; run one at a time. After each cluster run `nodetool stopdaemon`, then
`pgrep -f CassandraDaemon` must print nothing (kill the PID otherwise); the unit JVMs exit by
themselves (`pgrep -f TempBufferProbe` empty). At the end: `rm -rf $WORK/node $WORK/*.jfr` (keep the
`.txt`/`.log` readings), and leave `~/cassandra-5.0.9` untouched (all builds in `$WORK/src`).

## C. Sources read

src/java/org/apache/cassandra/io/util/DataOutputStreamPlus.java
src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (184, 794-800)
src/java/org/apache/cassandra/io/util/UnbufferedDataOutputStreamPlus.java
src/java/org/apache/cassandra/io/util/WrappedDataOutputStreamPlus.java
src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java (grep)
src/java/org/apache/cassandra/io/util/DataOutputBuffer.java (grep)
src/java/org/apache/cassandra/net/AsyncChannelOutputPlus.java (grep)
src/java/org/apache/cassandra/cache/SerializingCache.java
src/java/org/apache/cassandra/cache/SerializingCacheProvider.java
src/java/org/apache/cassandra/cache/AutoSavingCache.java (360-380)
src/java/org/apache/cassandra/db/marshal/ByteBufferAccessor.java
src/java/org/apache/cassandra/db/marshal/AbstractType.java (529-547)
src/java/org/apache/cassandra/utils/ByteBufferUtil.java (350-368)
src/java/org/apache/cassandra/utils/memory/SlabAllocator.java (51-105)
src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java (506-625)
src/java/org/apache/cassandra/db/partitions/CachedBTreePartition.java (65-107)
src/java/org/apache/cassandra/concurrent/SEPExecutor.java (218-230)
src/java/org/apache/cassandra/config/Config.java (472, 524, 1207-1213)
conf/cassandra.yaml; conf/jvm11-server.options; CHANGES.txt; lib/ (listing)
grep of `.writeUTF(` callers under src/java
https://issues.apache.org/jira/browse/CASSANDRA-10203
https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Integer.html#highestOneBit(int)
https://docs.oracle.com/en/java/javase/11/tools/jfr.html

## D. Stage-4 feedback

**2026-11-12, run 1** ([results](../../stage4-runtime-verification/results/data_output_stream_plus_temp_buffer_size-retrievetemporarybuffer-bytes.length--autonomous.md);
case file and results not yet committed at repository HEAD `f74aade6`). Outcome class: **weak true positive**.
- **Unit (B2): Confirmed — caps** (B2g row 1). All 44 predicted lengths matched B2f exactly at P = 4096, default,
  1 MiB and 16 MiB; no array was longer than P; every request above P left the array at exactly P; the P = 16 MiB
  positive control grew to 16 MiB. The B2f `heapDelta` magnitudes were not met at P ≥ 1 MiB (64.06 MiB against
  32 MiB, 288.06 MiB against 256 MiB): G1 (1 MiB regions in the 1 GiB probe JVM) counts each 1 MiB or 8 MiB array as
  2 or 9 whole humongous regions; `heapDelta − 32 × regions × 1 MiB` is the same 58,696 B at both values. Retained heap
  follows P, in region units. The prediction should have included the region rounding.
- **Cluster (B3): Not confirmed** (B3g row "No `retrieveTemporaryBuffer` allocations at any P, 64 row-cache misses
  seen"). As the audit found from the source (note A4), a read from an `offheap_buffers` memtable clones each row to
  heap (`EnsureOnHeap.CloneToHeap`). JFR shows the 4 MiB values allocated by `HeapCloner` ← `AbstractCell.clone` on
  every offheap read pass, and none in the `heap_buffers` control. So `SerializingCache.serialize` writes heap
  buffers, and no run made a temp-buffer allocation. ΔH was 0.30 MiB at every P, with 64 misses and 0 SSTables each time.
  A3 step 4 (the "node path that reaches the large direct-buffer case") is wrong for 5.0.9.
- **Recommendation for stage 3:** the audit found no node path that requests more than 65,537 B (`writeUTF`). Either
  redesign the cluster tier around `writeUTF` (array ≤ min(P, 131072) per thread, measured with JFR allocation events
  or a Byteman count) or mark the tier `n/a` with that reason. The Estimate's caveat should say that on a node the
  bounded object grows only through `writeUTF` (≤ 128 KiB) unless a direct value reaches a channel-less
  `UnbufferedDataOutputStreamPlus`.
- Runbook defects (fixed in A5 / in the harness): D1, the driver zip path; D2, `grep ' \[B$'` matches nothing on JDK 11
  (the line ends `[B (java.base@11.0.33)`).
