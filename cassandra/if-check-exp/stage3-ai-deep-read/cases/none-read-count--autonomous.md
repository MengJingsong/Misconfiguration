# none — read(int[]) region-boundary check — verification solution  <!-- file: cases/none-read-count--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`RandomAccessReaderAdapter.java:117`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/RandomAccessReaderAdapter.java#L117) (`if (count > intBuffer.remaining())`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`. The line compares a caller-supplied int count with the ints left in the current mmap region; it is not a configuration entry, property or limit, and the only allocation on its true branch is `4 * count` bytes of transient heap. |
| Ground | The condition is a data-layout test (does the slice cross a region boundary), not a cap. Its operand `count` comes from the caller (jvector), not from any setting. The regions come from a hard-coded mmap of the SAI file with a fixed 2 GiB segment size, so neither yaml knobs nor index size set a bound on memory or disk through this line. |

> **Link rule.** Applied below: the nearest declarations and the if statement are permalinks at tag `cassandra-5.0.9`.

## A. Constraint trace

**A1. The constraint.** There is none. The target is the `if` at [`RandomAccessReaderAdapter.java:117`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/RandomAccessReaderAdapter.java#L117) in `read(int[] dest, int offset, int count)` (declared at RandomAccessReaderAdapter.java:91). I checked the earlier trace against the source and it holds, with these corrections and additions:
- `count` is the method parameter (line 91); `intBuffer.remaining()` is the number of ints left in the current region, where `intBuffer` is built at line 105 (`bh.intBuffer()`) or line 114 (`bb.asIntBuffer()`) from `bufferHolder` (RandomAccessReader.java:40), which is refilled at RandomAccessReader.java:67.
- The earlier trace left the region size untraced. It is traced here. The reader is made from `fileHandle.instantiateRebufferer(null)` (RandomAccessReaderAdapter.java:42). The only constructors of the adapter are in DiskAnn.java:60 (graph file, via `createSupplier`) and DiskAnn.java:63 (compressed-vectors file). Both handles come from `createPerIndexFileHandle`, which builds `new FileHandle.Builder(file).mmapped(true).complete()` ([`IndexDescriptor.java:296`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/format/IndexDescriptor.java#L296)). The mmap is therefore hard-coded; `disk_access_mode` (Config.java:122) is not consulted for these files.
- With `mmapped` true and no compression, `FileHandle.complete()` calls `MmappedRegions.map(channel, length, bufferSize)` (FileHandle.java:415-416) and uses `MmapRebufferer`, which returns `regions.floor(position)` (MmapRebufferer.java:38-41). No chunk cache is involved on this path (`maybeCached` is only used in the non-mmap and compressed branches, FileHandle.java:411, 429).
- Region (segment) size: `maxSize = max(chunkSize, (MAX_SEGMENT_SIZE / chunkSize) * chunkSize)` (MmappedRegions.java:186), and `MAX_SEGMENT_SIZE` is declared [`public static int MAX_SEGMENT_SIZE = Integer.MAX_VALUE`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/MmappedRegions.java#L44) with a comment that it is non-final for tests. This is the only size constant behind the line. It is a constant, not settable by yaml, `-D` or JMX; it changes only by code (tests set it). Unit: bytes. Default about 2 GiB (rounded down to a multiple of the 4096-byte `bufferSize`, `RandomAccessReader.DEFAULT_BUFFER_SIZE`, RandomAccessReader.java:34).
- The slow path (lines 119-123) allocates `ByteBuffer.allocate(Integer.BYTES * count)` on the heap and fills it with `readFully(bb)` (RebufferingInputStream.java:108-135), which crosses regions by calling `reBuffer()`.

**A2. What it caps.** Nothing. The quantity compared is `count` (ints requested) against ints remaining in the current mmap region. Resources touched: off-heap/page-cache (the mmap regions, sized by the file length) and a short-lived heap array of `4 * count` bytes on the slow path only.

**A3. Mechanism.** Steps for [`read(int[], int, int)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/RandomAccessReaderAdapter.java#L117):
1. `count == 0` returns (line 93-94).
2. Take `bufferHolder` and `getPosition()` (lines 96-97).
3. If the region starts at file offset 0 and the position is int-aligned, use `bh.intBuffer()` (an `asIntBuffer()` of the region, MmappedRegions.java:281-285) and set its position (lines 100-107). Otherwise take `bh.buffer()`, set the position relative to the region offset and call `asIntBuffer()` (lines 108-115).
4. The check, [`if (count > intBuffer.remaining())`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/RandomAccessReaderAdapter.java#L117).
   - True: slice crosses the region end. Allocate `4 * count` heap bytes, `readFully` into it, wrap as `IntBuffer` (lines 119-122).
   - False: the slice lies inside the region; no allocation beyond the view object.
5. `intBuffer.get(dest, offset, count)`, then `seek(position + 4 * count)` (lines 125-126).

Bypass or overshoot: none relevant, because nothing is limited. A sibling check for floats is at line 69 (same pattern, `readFully(float[])`). Because regions are about 2 GiB, the true branch can only fire for a slice straddling a multiple-of-segment-size offset in a file longer than one segment (reasoning from MmappedRegions.java:183-195; not run). In a file under one segment the whole file is one region and the check is always false.


The check itself is the if statement at [`RandomAccessReaderAdapter.java:117`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/RandomAccessReaderAdapter.java#L117).

**A4. Other consumers.** The mmapped SAI component files share the OS page cache and virtual address space with SSTable data (default `mmap_index_only`, Config.java:122), the memtable, the chunk cache (only when `file_cache_enabled`, Config.java:499) and the heap. Callers of `read(int[]...)` live in the jvector library (`OnDiskGraphIndex`, constructed at DiskAnn.java:60); which jvector code passes which `count` is not verified.

**A5. Evidence beyond the source.** none (the jvector call sites were not read).

## B. Verification solution

**B1. Claim under test.** Usage does not follow this line: (a) neither heap nor off-heap/disk use of a node serving a vector index changes with any setting that could plausibly be tied to it (`disk_access_mode`, `file_cache_size`/`file_cache_enabled`), and (b) taking the true branch costs only a transient heap allocation of `4 * count` bytes, with no retained or growing usage. Wrong if either rises with those settings, or if the true-branch allocation exceeds `4 * count` bytes per call or is retained.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/cassandra-5.0.9/`), `cd $WORK/cassandra-5.0.9 && ant jar`. Put a JUnit test in package `org.apache.cassandra.index.sai.disk.v1.vector` (the adapter constructor at RandomAccessReaderAdapter.java:40 is package-private), e.g. `test/unit/org/apache/cassandra/index/sai/disk/v1/vector/RandomAccessReaderAdapterBoundaryTest.java`, in the local copy only. Run with `ant testsome -Dtest.name=RandomAccessReaderAdapterBoundaryTest -Dtest.methods=...`. JVM options: default test options plus `-Xmx256m`. Initialise `DatabaseDescriptor` via the usual test base (`DatabaseDescriptor.daemonInitialization()`).

**B2b. Knobs.** `MmappedRegions.MAX_SEGMENT_SIZE` (public static, MmappedRegions.java:44): 4096 (many tiny regions), 16384, and `Integer.MAX_VALUE` (default; one region). Restore the default in a `finally`/`@After`. Also `count`: 1, 4, 256, 1024. Values are chosen so that a crossing can be forced with a tiny file.

**B2c. Workload.** Write a 64 KiB file of consecutive big-endian ints 0..16383 on local disk (a temp dir). Open it with `new FileHandle.Builder(file).mmapped(true).complete()` (the same call as IndexDescriptor.java:296) after setting `MAX_SEGMENT_SIZE`, then `new RandomAccessReaderAdapter(handle)`. Seek to `regionEnd - 8` (for segment 4096: byte offset 4088) and call `read(dest, 0, 4)`: the slice is 16 bytes, 8 in the region, so `count (4) > remaining (2)` and the slow path runs. Contrast with a read at offset 0 of the same count (check false), and with each `count` above.

**B2d. Observables and instruments.** (1) Content: `dest` equals the expected consecutive ints and `getFilePointer()` advances by `4 * count`. (2) Branch taken: not directly observable (private local); infer from thread-allocated bytes, `((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId())` before and after the call, repeated 1000 times and averaged after 2000 warm-up calls. (3) Heap after `System.gc()` via `Runtime.totalMemory()-freeMemory()` before and after 100000 slow-path calls, to show nothing is retained. Cannot observe: native mmap residency inside the JVM (use `/proc/self/status` VmRSS only as a coarse check).

**B2e. Procedure.**
1. Build, write the file, set `MAX_SEGMENT_SIZE=4096`.
2. For each `count`, run the boundary read and the in-region read; record content check, allocated-bytes delta, per-call.
3. Repeat for 16384 and `Integer.MAX_VALUE`; with the default, the same offsets (4088 etc.) lie in one region.
4. Run 100000 slow-path calls; record post-GC heap before and after.
5. Positive control: run the same driver against a reader whose heap allocation is known to scale, namely the explicit `ByteBuffer.allocate(4 * count)` loop in the test body, to prove the allocation counter moves with `count`.
6. Delete the temp file; confirm no leftover JVM (`pgrep -u $USER java`).

**B2f. Predictions.** Slow path (segment 4096, offset 4088, count 4): allocated bytes per call at least 16 (`4*count`) plus the small view objects, and growing linearly with `count`; for `count` = 1024 at a boundary the delta is at least 4096 bytes. In-region reads and the default `Integer.MAX_VALUE` setting: the delta is only the `IntBuffer` view (a few tens of bytes, independent of `count`). Content correct in all cases. Post-GC heap after 100000 slow-path calls equals the before value within noise (no retention).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Delta at boundary grows by about `4 * count` per call, in-region delta flat | Mechanism as traced (claim confirmed: only a transient `4*count` allocation) |
| Post-GC heap flat across 100000 slow-path calls | No retained usage (claim confirmed) |
| Delta in-region also grows with `count` | Claim wrong: the fast path copies too (re-read lines 99-126) |
| Delta at boundary far exceeds `4 * count` or heap grows after GC | Claim wrong: a hidden retained or larger allocation |
| Allocation counter moves in the control loop but not in either read path | Instrument works; no growth is observed (confirmed) |
| Counter does not move in the control loop | Instrument invalid; not confirmed |
| Boundary read never takes the slow path (delta never rises at the 4096 setting) | Limit not reached; not confirmed (check offsets and that `MAX_SEGMENT_SIZE` was set before the handle was created) |

**B2h. Controls.** Content check ensures the crossing is real; the default-size setting (one region) is the negative control for the same read; the explicit-allocation loop is the positive control; warm-up and averaging remove JIT noise; setting `MAX_SEGMENT_SIZE` before opening the handle (regions are fixed at map time, MmappedRegions.java:183-195).

### B3. Cluster tier

**B3a. Environment and build.** One node (JDK 11, Ant) built from a local copy (`ant jar`), data, commit log, hints and saved caches on a local disk of known size (at least 3x the expected SAI file size, see B3c). Heap `-Xms2g -Xmx2g` in `conf/jvm11-server.options` (or via `JVM_EXTRA_OPTS`). Config in `cassandra.yaml`: `file_cache_enabled: true`, `file_cache_size: 64MiB`, `disk_access_mode: mmap_index_only` (baseline); no other change. Vector indexes need the 5.0 SAI vector type (`vector<float, 1536>`).

**B3b. Knobs.** (1) `disk_access_mode`: `mmap_index_only` vs `standard`. (2) `file_cache_size`: 16MiB vs 256MiB, with `file_cache_enabled: true`. Reason: these are the only settings that look related to how index files are read; the claim is that the SAI graph/pq files ignore them (IndexDescriptor.java:296 forces mmap, no chunk cache on the mmap path, FileHandle.java:415-417). Set in `cassandra.yaml`, restart between values.

**B3c. Workload.** Table `ks.t (id int primary key, v vector<float, 1536>)` with `CREATE CUSTOM INDEX ON ks.t(v) USING 'StorageAttachedIndex'`. Insert N random vectors; N is chosen so that the index terms data file of one sstable exceeds 2^31 bytes (so a second mmap region exists and a slice can straddle the 2 GiB boundary): full-precision vectors are 6144 bytes each, so N of about 400000 gives roughly 2.4 GB of raw vectors; whether they are stored inline in the graph file is not verified, so after flush check `ls -l` of the `*TermsData*` (graph) component and grow N until it exceeds 2147483647 bytes. Flush and compact to a single sstable (`nodetool flush`, `nodetool compact ks t`). Then run 20000 ANN queries `SELECT id FROM ks.t ORDER BY v ANN OF [..] LIMIT 10` with random query vectors, from 8 concurrent clients, for 10 minutes. Whether queries hit a neighbor list that straddles the boundary is not controllable; a node file that has a second region is the precondition for the true branch to be possible at all.

**B3d. Observables and instruments.** Heap: `jcmd <pid> GC.heap_info` and JMX `java.lang:type=Memory` each 5 s. Off-heap/resident: `/proc/<pid>/status` (VmRSS, RssFile) and `/proc/<pid>/smaps_rollup` each 5 s, plus the count and size of the mapped SAI files from `/proc/<pid>/maps`. Chunk cache: JMX `org.apache.cassandra.metrics:type=ChunkCache,name=Size` (metric name not verified; check with `nodetool sjk mx` or jconsole). Disk: `du -sk` of the data directory. Allocation inside `read`: not directly observable on a node; use JFR (`-XX:StartFlightRecording`) allocation profiling and look for `ByteBuffer.allocate` frames under `RandomAccessReaderAdapter.read` (this shows whether the slow path was ever taken). Cannot observe: the branch itself.

**B3e. Procedure.**
1. Build, configure baseline, start with JFR on, create schema and index, load N rows, flush, compact, confirm the graph file size.
2. Run the 10-minute query load; sample as in B3d; stop the load.
3. Stop the node, change a knob (`disk_access_mode: standard`, then `file_cache_size` values), restart, rerun steps 2.
4. Positive control: same node, `disk_access_mode: standard`, `file_cache_enabled: true`, `file_cache_size: 16MiB` then `256MiB`, and a read-heavy workload on a plain table (no SAI) of at least 1 GiB, e.g. `cassandra-stress` read of 1 GiB of data; the chunk-cache size should bind at the configured size (ChunkCache.java:50, 152).
5. Stop the node, `pgrep -u $USER -f CassandraDaemon` empty, delete the data directories.

**B3f. Predictions.** Across `disk_access_mode` and `file_cache_size` values, with the same SAI workload: steady-state heap within the same range (no relation to knob), SAI file mappings in `/proc/<pid>/maps` identical in count and size (the files are always mmapped), chunk-cache size near zero for the SAI files, and RssFile grows to about the working set of touched pages irrespective of the knob. If the slow path is seen in JFR, `ByteBuffer.allocate` allocations are small (on the order of `4 * count` bytes, tens to hundreds of bytes) and short-lived. In the positive control, chunk-cache size tracks and stays at or below `file_cache_size` (16 MiB run lower than the 256 MiB run).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| SAI-run heap, RSS and mappings flat across knob values; control chunk cache moves with `file_cache_size` | Claim confirmed |
| Heap or RssFile of the SAI run scales with `file_cache_size` or changes with `disk_access_mode` | Claim refuted (usage follows a knob) |
| SAI files not in `/proc/<pid>/maps` under `standard` | Claim refuted (re-read IndexDescriptor.java:296) |
| Control chunk cache does not move with `file_cache_size` | Control invalid; not confirmed |
| Graph file stays below 2^31 bytes, so no second region | True branch unreachable; the heap-allocation half of B1 is not confirmed here (rely on the unit tier) |
| JFR shows `read` allocations large or growing | Claim refuted for B1(b) |
| JFR shows no `read` slow-path allocations | Branch not exercised; flat usage is still consistent but the branch itself is not confirmed |

**B3h. Controls.** The positive control (chunk cache bound), a run with file-cache off for the SAI table, identical data/queries across knob values (same sstable copied or regenerated with a fixed seed), JIT/GC warm-up of 2 minutes excluded from readings, page cache dropped with `sync; echo 3 > /proc/sys/vm/drop_caches` only if permitted (otherwise use a fresh machine boot or compare RssFile deltas).

**B4. Risks and cleanup.** Unit tier: a small temp file only; no processes remain. Cluster tier: about 2.4 GB or more of vectors plus index (3x headroom on local disk), the node uses 2 GiB heap plus mappings; run only on a local disk of known size, not shared storage. Stop Cassandra and JFR, confirm with `pgrep`, remove data, commitlog, hints and saved_caches directories and the local source copy; never build in `/users/jason92/cassandra-5.0.9`.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/RandomAccessReaderAdapter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/RandomAccessReader.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/DiskAnn.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/PerColumnIndexFiles.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/format/IndexDescriptor.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/FileHandle.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/MmappedRegions.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/MmapRebufferer.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/Rebufferer.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/RebufferingInputStream.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java (grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/ChunkCache.java (grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (grep)
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml (grep)
- the input file agent-in/152.md (earlier trace)

## D. Stage-4 feedback

`none yet`
