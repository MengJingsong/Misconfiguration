# none — verification solution  <!-- file: cases/none-readfully-dest_length--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`RandomAccessReaderAdapter.java:69`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/RandomAccessReaderAdapter.java#L69) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the check at line 69 is not a limit on memory or disk; it only chooses between a zero-copy read and a copying read of one vector. |
| Ground | The operand (`dest.length`) is the vector dimension times one, and the other side (`floatBuffer.remaining()`) is the remaining part of an mmap region, not a configured limit. The only allocation the check can trigger is a transient heap buffer of `Float.BYTES * dest.length` bytes (line 72), freed right after the call; nothing is retained or bounded by a knob. |

## A. Constraint trace

**A1. The constraint.** There is no resource constraint at this line. The if statement is [`RandomAccessReaderAdapter.java:69`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/RandomAccessReaderAdapter.java#L69), `if (dest.length > floatBuffer.remaining())`, inside `readFully(float[] dest)` (declared at [`RandomAccessReaderAdapter.java:46`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/RandomAccessReaderAdapter.java#L46)). Kind: none (a buffer-boundary test). The earlier trace's claim is confirmed for lines 46-79. It left the region size unverified; verified here: the handle for the graph file is built with `new FileHandle.Builder(file).mmapped(true).complete()` (IndexDescriptor.java:296), which with no compression metadata uses `MmappedRegions.map(channel, length, bufferSize)` and a `MmapRebufferer` (FileHandle.java:413-417). Each region is at most `max(chunkSize, (MAX_SEGMENT_SIZE / chunkSize) * chunkSize)` bytes (MmappedRegions.java:186), where `MAX_SEGMENT_SIZE = Integer.MAX_VALUE` (MmappedRegions.java:44, a public non-final static, so a test can lower it). `bufferSize` defaults to `RandomAccessReader.DEFAULT_BUFFER_SIZE` = 4096 (RandomAccessReader.java:34, FileHandle.java:273). So the region is about 2 GiB and the "limit" on line 69 is the end of that region; it is a property of the file layout, not a configurable cap. Unit: floats. Default: not applicable. Settable: no yaml key, `-D` property or JMX controls it; only the test-only `MAX_SEGMENT_SIZE` field changes the region length. No restart question arises. The nearest memory/disk-significant objects are (a) the graph file's mmap (off-heap, page cache, not capped by Cassandra) and (b) the per-vector temporary of line 72 (heap, `4 * dimension` bytes).

**A2. What it caps.** Nothing. The quantity compared is the caller's requested float count (`dest.length`, the array allocated by the caller; the caller is the jvector `OnDiskGraphIndex` view in a jar outside this tree, not verified) against the floats left in the current region's `FloatBuffer` (lines 57-58 or 64-66).

**A3. Mechanism.**
1. Constructor: `super(fileHandle.instantiateRebufferer(null))` (RandomAccessReaderAdapter.java:42), creating the reader over the shared `MmapRebufferer` (FileHandle.java:197-209, MmapRebufferer.java instantiateRebufferer returns itself).
2. `readFully(float[])` reads `bufferHolder` and `getPosition()` (lines 48-49; `bufferHolder` is set in RandomAccessReader.java:67, `getPosition()` is `bufferHolder.offset() + buffer.position()` at RandomAccessReader.java:84).
3. Builds a `FloatBuffer` over the region: fast aligned path `bh.floatBuffer()` (lines 52-58; `MmappedRegions.Region.floatBuffer()` is `buffer.asFloatBuffer()`, MmappedRegions.java:274-277) or the unaligned path (lines 60-67).
4. Check: [`RandomAccessReaderAdapter.java:69`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/RandomAccessReaderAdapter.java#L69). True only if the vector straddles the end of the region.
5. True: line 72 allocates a heap `ByteBuffer` of `Float.BYTES * dest.length`; line 73 `readFully(ByteBuffer)` (RebufferingInputStream.java:108) copies across the region boundary via `reBuffer()` (line 121); line 74 wraps it. False: no allocation beyond the small view objects.
6. Both outcomes: `floatBuffer.get(dest)` (line 77) and `seek` (line 78). Nothing is refused, no error, no eviction. Overshoot or bypass: not applicable, because no limit exists. The twin check for ints is at line 117 (same logic, `read(int[],...)`).

**A4. Other consumers.** The mmapped graph file occupies page cache/virtual memory outside the Java heap and is not governed by this check. `DiskAnn` also keeps a `CachingGraphIndex` over the graph (DiskAnn.java:60) and reads compressed vectors through a second adapter that is closed in the try block (DiskAnn.java:63-71). The size policy of `CachingGraphIndex` lives in the jvector jar (not in this tree; not verified). The heap array `dest` is allocated by the caller regardless of this check.

**A5. Evidence beyond the source.** none. (No external document was relied on.)

## B. Verification solution

**B1. Claim under test.** Usage does not follow the line-69 check: the check only selects the read path, the extra heap allocation on the slow path is exactly one transient `4 * dest.length` bytes per call and is independent of any configuration entry, and no retained memory or disk grows because a vector crosses a region boundary.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant, on a local copy of the tag (`cp -r` of the tree to local disk; never build in the shared tree). `ant jar` then compile a small JUnit test placed in the copy at `test/unit/org/apache/cassandra/index/sai/disk/v1/vector/RandomAccessReaderAdapterProbeTest.java` (the constructor is package-private, so the test sits in that package). Run with `ant testsome -Dtest.name=RandomAccessReaderAdapterProbeTest`. JVM options: `-Xmx512m -XX:+UseSerialGC` (so allocation counts are not noisy); `DatabaseDescriptor.daemonInitialization()` at test start.

**B2b. Knobs.** (1) `dest.length` (dimension): 128, 1536, 8192 floats (512 B, 6 KiB, 32 KiB). (2) Starting position relative to the region end: far from the boundary (fast path) versus start such that the vector straddles the boundary (slow path). (3) `MmappedRegions.MAX_SEGMENT_SIZE`: set by assignment before building the `FileHandle` to 65536 so a 1 MiB file has 16 regions and boundaries are cheap to hit (MmappedRegions.java:44, 186). Restore the value after the test. (4) Positive control knob: `-Xmx` and an explicit large `new float[n]` loop (see B2h).

**B2c. Workload.** Write a 1 MiB file of known float values into a temp dir on local disk. Build `new FileHandle.Builder(file).mmapped(true).complete()` (as IndexDescriptor.java:296). Create `new RandomAccessReaderAdapter(handle)`. For each dimension, call `readFully(float[])` 100000 times: (a) from position 0 stepping by `4*dim` within a region, (b) from `regionEnd - 4*dim/2` (aligned to 4) every time, via `seek`. Arithmetic: with segment 65536 B and dim 1536 (6144 B) a straddling start exists at `65536 - 3072`; the check at line 69 is true there since `remaining()` is 768 floats < 1536.

**B2d. Observables and instruments.** Per-thread allocated bytes via `com.sun.management.ThreadMXBean.getThreadAllocatedBytes(Thread.currentThread().getId())` before and after the loop (the check's own cost: line 72 allocation); `floatBuffer.remaining()` and `dest.length` cannot be read from outside, so the test infers the path from the allocation delta and from a spy by reflection-free means: compare with a `ByteBuffer.allocate` of the same size taken as baseline. Also check returned data equals the file's floats. Not observable directly: which branch ran (no hook); inferred from allocation.

**B2e. Procedure.** 1. Copy tree, `ant jar`. 2. Write the test described above. 3. Run for each dimension in the fast configuration, record bytes per call. 4. Set `MAX_SEGMENT_SIZE=65536`, rebuild the handle, run the straddling configuration, record bytes per call. 5. Run the control. 6. Delete the temp dir and the copy of the tree.

**B2f. Predictions.** Fast path: per-call allocation is a small constant (a few view objects, independent of `dim`). Straddling path: per-call allocation is at least `4 * dim` bytes more than the fast path (`ByteBuffer.allocate`, line 72) and grows linearly with `dim`. Data returned is identical in both. No exception, no change in any configured limit. Allocation per call never exceeds `4*dim` plus the constant, so total heap use stays flat across 100000 calls (garbage collected). The claim is wrong if the allocation stays above the straddling figure on the fast path, or retained heap grows across iterations.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Fast path allocation constant across `dim`; straddle allocation = fast + about `4*dim` | Check only selects the path (claim confirmed). |
| Post-GC heap flat across the loop while the control grows | Usage does not follow the constraint (claim confirmed). |
| Allocation on the fast path scales with `dim`, or heap retained grows with the number of calls | Claim refuted: the check or something near it retains memory. |
| Straddling path never taken (allocation delta equals the fast path) | Boundary not reached; not confirmed (check `MAX_SEGMENT_SIZE` was set before the handle was built). |
| Control (B2h) does not move heap | Instrument invalid; not confirmed. |

**B2h. Controls.** Positive control: a loop that keeps `n` allocated `float[dim]` arrays (retained in a list) under `-Xmx512m`, shown to raise the post-GC heap in proportion to `n` and to hit OOM at the heap cap; this shows the instrument sees retained memory. Negative control: read the same file with plain `RandomAccessReader.readFully(byte[])` of equal byte size and compare, to rule out file-read cost being attributed to line 72.

### B2 amendment: design audit, 2026-10-29 (stage 4; applies `stage4-runtime-verification/none-type-design.md` sections 3 and 4)

The estimate (`negative`) is unchanged. This block supersedes B2a-B2h where they differ; the filed text stays as the record. This case covers line 69; its int twin is the case `none-read-count--autonomous` (line 117), run separately with its own results file.

**U0. Kind and the meaning of "caps" here.** Kind 3 (requested length, none-type-design.md section 2): the operand is the caller's requested element count (`dest.length`); the other side is the elements left in the current mmap region, a data-layout value. The callers are in jvector 1.0.2 (`build/lib/jars/jvector-1.0.2.jar`, read with `javap -c`): `OnDiskGraphIndex$OnDiskView` calls `RandomAccessReader.readFully([F)V` (vector fetch) and `RandomAccessReader.read([III)V` (neighbour list); the case file left this unverified. "Usage follows the operand" is expected (the operand is the data size) and is not a finding; the finding is the difference the branch causes at equal operand. Here "caps" is used only if the true branch reduces or refuses the guarded allocation, or bounds retained bytes; a true branch that adds a transient copy and retains nothing is path selection, which is "does not cap" (this reads design section 4 row 2 for a branch that adds an allocation instead of skipping one).

**U1. Launcher.** Not `ant testsome` (the filed `-XX:+UseSerialGC` is dropped: it aborts the test JVM there). The probe is compiled by `javac` into a separate directory against the copy's `build/classes/main`, `build/test/classes` and `build/lib/jars/*`, and run with plain `java -Xmx512m` (G1, the default collector), `-Dcassandra.config=` the copy's `test/conf/cassandra.yaml`, and the JDK 11 `--add-exports/--add-opens` flags of `conf/jvm11-server.options`. The probe sits in package `org.apache.cassandra.index.sai.disk.v1.vector` (package-private constructor) and is never copied into a source tree. Build: `copy-source.sh ~/s4-none` then `ant build-test`, on `pc41` only.

**U2. Audit corrections to the filed B2.** (a) A first read before any `seek` throws `UnsupportedOperationException`: the reader starts with `Rebufferer.EMPTY` (RandomAccessReader.java:40) whose `floatBuffer()`/`intBuffer()` are the interface defaults that throw (Rebufferer.java:52-60, EMPTY at 74-97). jvector seeks before each read, so the probe calls `seek(start)` before every call (outside the measured window). (b) The filed dimensions (128..8192, two orders) are widened to six values over four orders. (c) The filed loop of 100000 calls gives an average that hides the branch; the instrument is a window around one call, K calls per repetition. (d) The filed 1 MiB file has to hold a 4 MiB read at the largest N, so the file is 16 MiB. (e) Citations re-read in `cassandra/cassandra-5.0.9/`: RandomAccessReaderAdapter.java:46, 69, 72-75, 77-78 and 91, 117, 120-123, 125-126; MmappedRegions.java:44, 186; FileHandle.java:415-416; IndexDescriptor.java:296; RandomAccessReader.java:34, 40, 67; DiskAnn.java:60, 63; all hold.

**U3. Sweep, arms, instruments.** Operand N in {32, 128, 1536, 16384, 131072, 1048576} elements (128 B to 4 MiB). The file is 16 MiB, element i holds the value i (exact below 2^24). Start offset `s = 65536 - min(2N, 32768)` bytes (a multiple of 4), the same in both arms and always inside region 0 (offset 0, aligned: the same code path, lines 52-58 / 100-107). Arm F (check false): default `MAX_SEGMENT_SIZE`, one region. Arm T (check true): `MmappedRegions.MAX_SEGMENT_SIZE = 65536` assigned before the `FileHandle` is built (256 regions, MmappedRegions.java:186) and restored after; the read of `4N` bytes from `s` crosses the end of region 0 for every N. Per call: `seek(s)` (outside the window), then the window `getThreadAllocatedBytes` before and after the single read call (`com.sun.management.ThreadMXBean`, as in `harness/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided/Alloc.java`). Arm order in one JVM per N: EMPTY (two readings with nothing between), F1, T1, F2, T2 (F2 and T2 repeat F1 and T1 on identical input: the noise floor). K calls per repetition: 2000 (N <= 1536), 500 (16384), 100 (131072), 20 (1048576); 5 repetitions; 2K warm-up calls per arm; the repetition medians and the min and max per-call values are reported. Every repetition's first call checks the returned array against the file's values and the file pointer against `s + 4N`.
Two passes per N, each in a fresh JVM: pass A (no agent) gives allocation, retained size and controls; pass B (`-javaagent` Byteman, one rule `AT LINE` on line 72, action `stage4.Count.hit()` on a static counter) gives the branch counters. Pass B's allocation is printed but not used for the bands, because a rule's own allocation is not assumed to be zero.
Retained: after the arms, M calls of F and then M calls of T on the same reader, M = clamp(2^30 / (4N), 200, 20000); used heap after three `System.gc()` calls before and after each block.
Controls, in pass A: C1 `new float[N]` through the same window; C2 100 MiB of such arrays kept alive (at most 250000 arrays), post-GC used heap before and after; C3 the EMPTY window. **Honest limit (design section 3.5):** no closed capping setting binds on this transient allocation; C1 and C2 show that the instrument sees an allocation and retention, and T minus F equal to the copy shows that it resolves a branch difference.


**B2f (amended). Frozen predictions.** T minus F means the median of arm T1 minus the median of arm F1 at the same N, pass A. All figures are bytes.
- P1 (pass B counters at line 72): arm F counts 0 hits at every N; arm T counts exactly its number of calls (warm-up plus 5 x K) at every N.
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


**B3a. Environment and build.** One node, JDK 11, built by `ant jar` from a local copy of the tag. Data, commit log, hints and saved caches under one local directory of known size (at least 20 GiB free). `cassandra.yaml`: `file_cache_size: 512MiB` (cassandra.yaml:753; this is a commented default in the shipped file, uncomment it), `heap`: `-Xms2g -Xmx2g` via `MAX_HEAP_SIZE=2g HEAP_NEWSIZE=512m`. Storage-attached indexes enabled by default in 5.0.

**B3b. Knobs.** Vector dimension: 128 and 1536 (`vector<float, N>`). Row count: 200000. The line-69 check has no knob; to force the slow path on a real node, the test cannot lower `MAX_SEGMENT_SIZE` without code change, so use a local patched copy that sets `MmappedRegions.MAX_SEGMENT_SIZE = 1 << 20` in a static initialiser (documented as a test-only patch, not applied to the shared tree). Variants: unpatched (regions about 2 GiB; boundary effectively never hit) and patched (1 MiB regions; many vectors straddle). Positive control knob: `file_cache_size` 64MiB vs 512MiB on a table with `disk_access_mode` not mmap (chunk cache bound at ChunkCache.java:50,152).

**B3c. Workload.** `CREATE TABLE ks.t (id int PRIMARY KEY, v vector<float, 1536>); CREATE CUSTOM INDEX ON ks.t(v) USING 'StorageAttachedIndex'`. Insert 200000 random vectors (raw size about 1.2 GB at dim 1536), flush, then run 20000 `SELECT id FROM ks.t ORDER BY v ANN OF [..] LIMIT 10` queries from 8 client threads, repeated for dim 128. Graph file reads go through `readFully(float[])` when `CompressedVectors` is null (DiskAnn.java:105-110 uses `view.getVector`; the call chain into the adapter is in jvector, not verified).

**B3d. Observables and instruments.** JVM heap used after full GC (`jcmd <pid> GC.heap_info`, or `jstat -gc` every 5 s); allocation rate per query (`jcmd <pid> JFR.start` with the `jdk.ObjectAllocationSample` event, filter on `RandomAccessReaderAdapter.readFully` stack frames); resident memory and mapped size of the graph file (`pmap -x <pid>` and `/proc/<pid>/smaps` for the `*_TermsData.db`-named component, the file name suffix not verified); disk usage of the data directory (`du -sb`). Cannot observe directly: which branch of line 69 each call took, except through JFR allocation stacks at line 72.

**B3e. Procedure.** 1. Copy tree, build unpatched and patched jars. 2. Start node on local disk. 3. Create schema, load, flush, compact. 4. Start JFR and `jstat`; run the query workload for 10 minutes. 5. Record heap after GC, allocation samples touching line 72, `pmap` of the graph file. 6. Stop node, wipe data, repeat with the patched build. 7. Repeat once with dim 128. 8. Control run (B3h). 9. `jps` to confirm no leftover process; delete the data directory.

**B3f. Predictions.** Unpatched: no allocation samples at line 72 (boundary not reached for a graph file below about 2 GiB; if larger, only a rare few). Patched: samples at line 72 appear, sized `4*dim` bytes, in proportion to queries. Heap after GC and disk usage are the same in both builds within run-to-run noise, and do not change with `file_cache_size` for this mmapped file. Mapped size of the graph file equals its length in both builds. Heap after GC stays well under `-Xmx2g` and does not grow over the 10 minutes.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Patched build shows line-72 allocations, heap after GC and mapped size same as unpatched | Check is path selection only (claim confirmed). |
| Heap after GC or off-heap mapping differs between builds by more than noise, growing with query count | Claim refuted: boundary crossing changes retained usage. |
| Heap/mapping flat while the positive control (changing `file_cache_size` on a non-mmap table) moves chunk-cache memory | Usage does not follow the constraint, instrument works (claim confirmed). |
| No line-72 samples even in the patched build | Slow path never reached or JFR did not capture; not confirmed. |
| Control does not move | Instrument invalid; not confirmed. |

**B3h. Controls.** Positive control: a second table with `compression = {'enabled': 'false'}` read through a non-mmapped `FileHandle` (`mmapped` false path, FileHandle.java:421-433) with `file_cache_size: 64MiB` then `512MiB`; chunk-cache resident memory is capped at `cacheSize` (ChunkCache.java:50, 152), so reading data beyond 64 MiB should plateau near the cap, which shows a cap that binds. Baseline: the same workload with queries disabled (idle) to rule out background compaction or flush as the source of heap change.

**B4. Risks and cleanup.** Disk: unit tier uses 1 MiB; cluster tier raw data about 1.2 GB plus index and commit log, kept to a local directory of known size, never shared storage. Processes: stop the node (`nodetool drain` then kill the PID), confirm with `jps` and `pgrep -f CassandraDaemon`; JFR files under the local scratch dir deleted. The patched jar and the tree copy are deleted after the run. The shared source tree is never built in or modified.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/RandomAccessReaderAdapter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/DiskAnn.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/PerColumnIndexFiles.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/format/IndexDescriptor.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/RandomAccessReader.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/RebufferingInputStream.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/FileHandle.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/MmappedRegions.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/MmapRebufferer.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/Rebufferer.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml (grep for file_cache_size only)

## D. Stage-4 feedback

`done 2026-10-29` (unit tier only; B3 amended `n/a`). Results: [`results/none-readfully-dest_length--autonomous.md`](../../stage4-runtime-verification/results/none-readfully-dest_length--autonomous.md). **Verdict: Confirmed - does not cap; outcome class true negative** (estimate `negative`, effect `does not cap`). Sweep N = 32 .. 1048576 floats, pass B counters: line 72 hit 0 times in the one-region arm and once per call in the lowered-segment arm; arm F allocates 56 bytes at every N; arm T allocates 4N + 208 bytes more (4N + 824 at N = 131072, 4N + 5752 at N = 1048576, one `reBuffer()` of about 90 bytes per 64 KiB region crossed); noise floor 0; retained change under 140 kB after up to 20000 calls; controls C1 (4N + 16) and C2 (retention seen). Two frozen sub-predictions missed and were not edited: the T - F band at N = 131072 and 1048576 (priced the region switch as a constant), and the C2 array count at N = 32 (35 MiB, not 100).

Audit feedback for stage 3 (2026-10-29): (1) a first read before any `seek` throws `UnsupportedOperationException` (`Rebufferer.EMPTY`'s `floatBuffer()` is the throwing default; Rebufferer.java:52-60, 74-97), so the filed workload had to seek first; jvector's `OnDiskGraphIndex$OnDiskView` seeks before reading. (2) The caller is verified: jvector 1.0.2 `OnDiskGraphIndex$OnDiskView` calls `readFully([F)V` and `read([III)V` (`javap -c`). (3) The filed dimension sweep covered two orders and a 100000-call average; replaced by a one-call allocation window over six values. (4) The true branch exists only with `MmappedRegions.MAX_SEGMENT_SIZE` lowered, or a graph file above 2 GiB; B3 is `n/a`. (5) The honest limit: no capping setting binds this transient allocation. All A1 and A3 citations held.
