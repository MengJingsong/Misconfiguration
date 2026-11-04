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

### B2 amendment: design audit, 2026-10-29 (stage 4; applies `stage4-runtime-verification/none-type-design.md` sections 3 and 4)

The estimate (`negative`) is unchanged. This block supersedes B2a-B2h where they differ; the filed text stays as the record. This case covers line 117; its float twin is the case `none-readfully-dest_length--autonomous` (line 69), run separately with its own results file.

**U0. Kind and the meaning of "caps" here.** Kind 3 (requested length, none-type-design.md section 2): the operand is the caller's requested element count (`count`); the other side is the elements left in the current mmap region, a data-layout value. The callers are in jvector 1.0.2 (`build/lib/jars/jvector-1.0.2.jar`, read with `javap -c`): `OnDiskGraphIndex$OnDiskView` calls `RandomAccessReader.readFully([F)V` (vector fetch) and `RandomAccessReader.read([III)V` (neighbour list); the case file left this unverified. "Usage follows the operand" is expected (the operand is the data size) and is not a finding; the finding is the difference the branch causes at equal operand. Here "caps" is used only if the true branch reduces or refuses the guarded allocation, or bounds retained bytes; a true branch that adds a transient copy and retains nothing is path selection, which is "does not cap" (this reads design section 4 row 2 for a branch that adds an allocation instead of skipping one).

**U1. Launcher.** Not `ant testsome` (the filed `-XX:+UseSerialGC` is dropped: it aborts the test JVM there). The probe is compiled by `javac` into a separate directory against the copy's `build/classes/main`, `build/test/classes` and `build/lib/jars/*`, and run with plain `java -Xmx512m` (G1, the default collector), `-Dcassandra.config=` the copy's `test/conf/cassandra.yaml`, and the JDK 11 `--add-exports/--add-opens` flags of `conf/jvm11-server.options`. The probe sits in package `org.apache.cassandra.index.sai.disk.v1.vector` (package-private constructor) and is never copied into a source tree. Build: `copy-source.sh ~/s4-none` then `ant build-test`, on `pc41` only.

**U2. Audit corrections to the filed B2.** (a) A first read before any `seek` throws `UnsupportedOperationException`: the reader starts with `Rebufferer.EMPTY` (RandomAccessReader.java:40) whose `floatBuffer()`/`intBuffer()` are the interface defaults that throw (Rebufferer.java:52-60, EMPTY at 74-97). jvector seeks before each read, so the probe calls `seek(start)` before every call (outside the measured window). (b) The filed dimensions (128..8192, two orders) are widened to six values over four orders. (c) The filed loop of 100000 calls gives an average that hides the branch; the instrument is a window around one call, K calls per repetition. (d) The filed 1 MiB file has to hold a 4 MiB read at the largest N, so the file is 16 MiB. (e) Citations re-read in `cassandra/cassandra-5.0.9/`: RandomAccessReaderAdapter.java:46, 69, 72-75, 77-78 and 91, 117, 120-123, 125-126; MmappedRegions.java:44, 186; FileHandle.java:415-416; IndexDescriptor.java:296; RandomAccessReader.java:34, 40, 67; DiskAnn.java:60, 63; all hold.

**U3. Sweep, arms, instruments.** Operand N in {32, 128, 1536, 16384, 131072, 1048576} elements (128 B to 4 MiB). The file is 16 MiB, element i holds the value i (exact below 2^24). Start offset `s = 65536 - min(2N, 32768)` bytes (a multiple of 4), the same in both arms and always inside region 0 (offset 0, aligned: the same code path, lines 52-58 / 100-107). Arm F (check false): default `MAX_SEGMENT_SIZE`, one region. Arm T (check true): `MmappedRegions.MAX_SEGMENT_SIZE = 65536` assigned before the `FileHandle` is built (256 regions, MmappedRegions.java:186) and restored after; the read of `4N` bytes from `s` crosses the end of region 0 for every N. Per call: `seek(s)` (outside the window), then the window `getThreadAllocatedBytes` before and after the single read call (`com.sun.management.ThreadMXBean`, as in `harness/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided/Alloc.java`). Arm order in one JVM per N: EMPTY (two readings with nothing between), F1, T1, F2, T2 (F2 and T2 repeat F1 and T1 on identical input: the noise floor). K calls per repetition: 2000 (N <= 1536), 500 (16384), 100 (131072), 20 (1048576); 5 repetitions; 2K warm-up calls per arm; the repetition medians and the min and max per-call values are reported. Every repetition's first call checks the returned array against the file's values and the file pointer against `s + 4N`.
Two passes per N, each in a fresh JVM: pass A (no agent) gives allocation, retained size and controls; pass B (`-javaagent` Byteman, one rule `AT LINE` on line 120, action `stage4.Count.hit()` on a static counter) gives the branch counters. Pass B's allocation is printed but not used for the bands, because a rule's own allocation is not assumed to be zero.
Retained: after the arms, M calls of F and then M calls of T on the same reader, M = clamp(2^30 / (4N), 200, 20000); used heap after three `System.gc()` calls before and after each block.
Controls, in pass A: C1 `new int[N]` through the same window; C2 100 MiB of such arrays kept alive (at most 250000 arrays), post-GC used heap before and after; C3 the EMPTY window. **Honest limit (design section 3.5):** no closed capping setting binds on this transient allocation; C1 and C2 show that the instrument sees an allocation and retention, and T minus F equal to the copy shows that it resolves a branch difference.


**B2f (amended). Frozen predictions.** T minus F means the median of arm T1 minus the median of arm F1 at the same N, pass A. All figures are bytes.
- P1 (pass B counters at line 120): arm F counts 0 hits at every N; arm T counts exactly its number of calls (warm-up plus 5 x K) at every N.
- P2 (arm F): median at most 512 at every N, and the largest minus the smallest F median across the six N at most 64 (F does not follow N).
- P3 (the branch): T minus F lies in [4N + 16, 4N + 640] at every N (the copy buffer `byte[4N]` is 4N + 16; the heap buffer object, the second `Buffer` view and the region switch add a few hundred bytes).
- P4 (noise floor): |F1 - F2| at most 32 and |T1 - T2| at most 64; the EMPTY window reads at most 16; for N >= 16384 T minus F is at least 10 times the larger of the two spreads.
- P5 (data): every content and file-pointer check passes in both arms.
- P6 (retained): the post-GC used-heap change over the M-call blocks is within 2 MiB (plus or minus) for F and for T at every N.
- P7 (controls): C1 reads in [4N + 16, 4N + 32]; C2 raises the post-GC used heap by at least 90 MiB.

**B2g (amended). Conclusions table.** The first matching row, in this order.

| Reading | Meaning | Verdict | Effect on the constraint |
|---|---|---|---|
| Pass B: F has 0 hits or T's hits differ from its calls at some N; or a content check fails | the branch was not the one designed, or the read is wrong | Invalid | undetermined |
| C1 or C2 outside P7, or the EMPTY window above 16 | the instrument could not show an effect | Not confirmed | undetermined |
| P1 to P7 all hold | the check selects the read path; the true branch adds one transient copy of 4N bytes that nothing retains; it bounds nothing | Confirmed | does not cap |
| T minus F below 4N + 16 at some N although P1 holds | the copy is not visible to the instrument or not made as traced | Not confirmed | undetermined |
| F grows with N (P2 fails), or T minus F above 4N + 640 growing faster than 4N, or retained change above 2 MiB | the check or the code near it costs more than the traced copy | Refuted | undetermined (it is `caps` only if T allocates less than F, which the traced code cannot do) |

**B2h (amended). Controls.** C1, C2 and C3 above, the same file read by arm F as the negative control (no crossing, no copy), and the identical re-runs F2 and T2 as the noise floor.

**U4. Unit-tier limit.** The sweep reaches 4 MiB per call and retains nothing, so the unit tier measures the allocation of one call exactly; a heap-level effect is below the G1 noise of about 16 MiB, so the cluster tier cannot resolve it (see B3).

### B3. Cluster tier

**B3 amendment, 2026-10-29: `n/a: the cluster tier cannot resolve the effect.`** The default region is about 2 GiB (MmappedRegions.java:44 and 186), so a node's graph file below 2 GiB is one region and the true branch is never taken; reaching it needs a patched `MAX_SEGMENT_SIZE` (a code change, as B3b says) and a data file above 2 GiB. The transient copy is `4 x dimension` bytes per call (6 KiB at 1536), far below the heap noise of about 16 MiB with G1, and a patched build adds no information that the unit tier does not give exactly. The filed B3a-B3h below are not run; they stay as the record. The unit tier alone settles this case; the outcome class is taken from it.


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

`done 2026-10-29` (unit tier only; B3 amended `n/a`). Results: [`results/none-read-count--autonomous.md`](../../stage4-runtime-verification/results/none-read-count--autonomous.md). **Verdict: Confirmed - does not cap; outcome class true negative** (estimate `negative`, effect `does not cap`). Same harness as its float twin (`none-readfully-dest_length`), int variant, run and filed separately: line 120 hit 0 times in the one-region arm and once per call in the lowered-segment arm at every N = 32 .. 1048576; F = 56 bytes at every N; T - F = 4N + 208 up to N = 16384 (4N + 824 at 131072, 4N + 5752 at 1048576); noise floor 0; retained change under 140 kB; C1 and C2 as designed. Frozen sub-predictions missed, not edited: the T - F band at N = 131072 and 1048576 (the per-region `reBuffer()` cost of the lowered segment) and C2 at N = 32 (array count capped at 250000).

Audit feedback for stage 3 (2026-10-29): (1) a read before any `seek` throws (`Rebufferer.EMPTY.intBuffer()` is the throwing default), so the probe seeks first; (2) jvector 1.0.2 `OnDiskGraphIndex$OnDiskView` calls `read([III)V` (`javap -c`), which the case file left unverified; (3) the filed counts 1..1024 and segment sizes 4096/16384 are replaced by six counts over four orders and a single lowered size so both arms share the start offset; (4) the true branch needs a lowered `MAX_SEGMENT_SIZE` or a graph file above 2 GiB, so B3 is `n/a`; (5) no capping setting binds this transient allocation. Citations held.
