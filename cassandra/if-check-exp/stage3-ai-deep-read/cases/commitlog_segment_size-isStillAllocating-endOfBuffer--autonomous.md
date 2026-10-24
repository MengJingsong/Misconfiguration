# commitlog_segment_size — verification solution  <!-- file: cases/commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java:423` (`allocatePosition.get() < endOfBuffer` in `isStillAllocating()`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (`claude-sonnet-5-5`), Claude Code CLI (version not exposed to the agent), 2026-10-23 |
| Estimate | `positive` for the per-segment cap: `endOfBuffer` is initialised from the buffer capacity, which is `commitlog_segment_size` (mmap, direct) or a pool buffer of that size (compressed, encrypted), and `allocate()` refuses to hand out bytes past it. The aggregate commit log footprint is only softly bounded by `commitlog_total_space` (see A3), so the claim is scoped to one segment and the total is a stated overshoot case. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `commitlog_segment_size`: configuration entry. First declared at `src/java/org/apache/cassandra/config/Config.java:396-397` as `DataStorageSpec.IntMebibytesBound commitlog_segment_size = new DataStorageSpec.IntMebibytesBound("32MiB")` (old name `commitlog_segment_size_in_mb`, converted by `@Replaces`). Unit: MiB in the yaml, bytes through `DatabaseDescriptor.getCommitLogSegmentSize()` (`DatabaseDescriptor.java:2875-2877`). The default is a hard-coded 32 MiB, repeated in `conf/cassandra.yaml:660`. It is set through the yaml key and needs a restart; the only runtime setter is the test-only `DatabaseDescriptor.java:2881-2889`. Validation (`DatabaseDescriptor.java:891-901`): 0 MiB is rejected, 2048 MiB or more is rejected, and `max_mutation_size` defaults to half of it. If `max_mutation_size` is set explicitly, the segment size must be at least twice that.

The operand in the target line, `endOfBuffer`, is a derived field (`CommitLogSegment.java:118`). `writeLogHeader()` sets `endOfBuffer = buffer.capacity()` (`:177`). `buffer` comes from `createBuffer()` (`:168`, `:192-195`):
- mmap: `channel.map(READ_WRITE, 0, getCommitLogSegmentSize())`, `MemoryMappedSegment.java:62`.
- compressed and encrypted: `manager.getBufferPool().createBuffer()`. The pool is built with `bufferSize = getCommitLogSegmentSize()` (`CompressedSegment.java:113-117`, `EncryptedSegment.java:176`), and the buffer is allocated at `SimpleCachedBufferPool.java:68-78`.
- direct I/O: the pool is built with `getCommitLogSegmentSize() + fsBlockSize - 1` (`DirectIOSegment.java:201`), then aligned. The exact capacity after alignment needs a runtime check (B2).

**A2. What it caps.** Disk (segment file size) and off-heap memory (the mapped region, or the per-segment `ByteBuffer` for the compressed, encrypted and direct modes). The quantity compared is `allocatePosition` (bytes reserved in the segment, starting at the header length plus `SYNC_MARKER_SIZE`, `:180`) against `endOfBuffer`, which is at most the segment size.

**A3. Mechanism.**
1. `allocate(int size)` (`CommitLogSegment.java:240-255`) computes `next = prev + size`. If `next >= endOfBuffer` it returns -1; otherwise it advances `allocatePosition` by CAS. A mutation can therefore never reserve bytes at or beyond `endOfBuffer`, and the usable maximum is `capacity - 1`.
2. `Allocation allocate(Mutation, int)` (`:201-223`) returns null on -1. `CommitLogSegmentManagerStandard.allocate` (loop on null) calls `advanceAllocatingFrom(segment)` to move to the next prepared segment. `AbstractCommitLogSegmentManager.java:296-335` then calls `old.discardUnusedTail()`.
3. `discardUnusedTail()` (`:258-287`) CAS-sets `allocatePosition = endOfBuffer + 1` and writes `endOfBuffer = prev`, so the final `endOfBuffer` is the last real allocation point. Afterwards `isStillAllocating()` is false (`allocatePosition > endOfBuffer`).
4. `sync()` (`:303-372`) allocates the next sync marker the same way. If that fails it closes the segment (`discardUnusedTail`, `internalClose`).
5. Consumers of `isStillAllocating()` (`:421-424`): `removeCleanFromDirty()` (`:570`) and `isUnused()` (`:615`) refuse to clean or recycle a segment that is still being allocated from. The compressed and encrypted `write()` assert on it (`CompressedSegment.java:63`, `EncryptedSegment.java:104`). So the target line gates segment retirement and does not itself enforce a size. The size cap is the `next >= endOfBuffer` test in step 1.
6. Segment count (an indirect disk bound) is governed separately: `commitlog_total_space` (`Config.java:389-390`; default `min(8192 MiB, 1/4 of the volume)`, `DatabaseDescriptor.java:664-675`). It is checked in `unusedCapacity()` (`AbstractCommitLogSegmentManager.java:445-451`) from `size`. `maybeFlushToReclaim()` (`:246-264`) flushes older segments when `unused < 0`. This is reactive: the allocator thread keeps creating the next segment (`createSegment` at `:189`), so the total can overshoot by roughly one prepared segment plus the time flushes take.

Overshoots and bypasses:
- Direct I/O may allocate a buffer a little larger than the segment size (alignment). `allocate()` still tests `endOfBuffer`, so the question is whether `endOfBuffer` is `segmentSize` or `segmentSize + up to fsBlockSize - 1`.
- Compressed segments are smaller on disk than their buffer: `onDiskSize()` returns `lastWrittenPos` (`CompressedSegment.java:93-96`). mmap segments always report the full segment size (`MemoryMappedSegment.java:103-106`).
- A single mutation larger than `max_mutation_size` (default half the segment) is rejected earlier in `CommitLog.add`. This was not read in full here and is treated as an assumption.

**A4. Other consumers.**
- Off-heap and disk: compressed and encrypted modes hold a thread-local reusable compression buffer (`getThreadLocalReusableBuffer`, `CompressedSegment.java:67`) sized to `initialCompressedBufferLength(length) + COMPRESSED_MARKER_SIZE`, and a pool of up to `commitlog_max_compression_buffers_in_pool` (default 3, `Config.java:400`) segment-size buffers. `atSegmentBufferLimit()` (`AbstractCommitLogSegmentManager.java:241-244`) throttles segment creation when the pool is exhausted.
- CDC (`CommitLogSegmentManagerCDC.java:201-207`) counts whole segments against `cdc_total_space`.
- Hints, sstables and memtables use the same disk and heap but are outside this constraint.

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:640-660` (segment size description).
- `test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentBackpressureTest.java`: sets `setCommitLogSegmentSize(1)` and `setCommitLogMaxCompressionBuffersPerPool(3)`, and asserts 3 active segments when sync is blocked. This shows the pool limit throttles segment creation.
- `CommitLogTest.java` lines 374, 410, 737 size mutations as fractions of `getCommitLogSegmentSize()`.
- No external links were used.

## B. Verification solution

**B1. Claim under test.** For every commit log segment, the highest byte offset reserved by any mutation stays below `commitlog_segment_size` (so segment files, and the segment buffers where one exists, never exceed that size), whatever the mutation sizes and rates. Writes that do not fit move to a new segment and do not enlarge the old one.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree: `rsync -a /users/jason92/cassandra-5.0.9/ /tmp/cass-ut/`; build there with `cd /tmp/cass-ut && ant jar` (never in the shared tree). Put the test in `/tmp/cass-ut/test/unit/org/apache/cassandra/db/commitlog/SegmentCapProbeTest.java` (package-private access to `CommitLogSegment` needs this package), modelled on `CommitLogSegmentBackpressureTest`. Run: `ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.SegmentCapProbeTest`. JVM options: the defaults from `build.xml`, plus `-Dcassandra.commitlog...` none needed. All commit log, data and hints directories go to a local `/tmp/cass-ut/data` (test config does this; check free space with `df -h /tmp`).

**B2b. Knobs.** `DatabaseDescriptor.setCommitLogSegmentSize(n)` (`:2881-2889`) with n = 1, 4, 32 (MiB), to confirm the bound scales and is not a constant. Each of three modes: mmap (no compression), `LZ4Compressor` compression (`setCommitLogCompression`), and, if the filesystem supports it, `commitlog_disk_access_mode: direct`. Call `initializeCommitLogDiskAccessMode()` after changing them.

**B2c. Workload.** Append mutations through `CommitLog.instance.add(m)` with a payload of `size/16` bytes (random bytes so LZ4 cannot shrink them), 64 times per configuration, so at least 4 segments are filled (for n = 1 MiB: 64 KiB payloads give 16 per segment, 64 gives about 4 segments; the arithmetic is 64 × 64 KiB = 4 MiB over a 1 MiB cap). Also append one mutation of exactly `max_mutation_size - overhead` (half the segment) and one that is deliberately too large, to cover the boundary and the rejection path.

**B2d. Observables and instruments.** For each segment in `CommitLog.instance.segmentManager.getActiveSegments()` read, via reflection or a test-package accessor: `buffer.capacity()`, the private fields `endOfBuffer` and `allocatePosition`, `isStillAllocating()`, `onDiskSize()`. Also `Allocation` positions (`position + size`) from the returned allocations, and file lengths of `*.log` in the commit log directory (`File.length()`). Sample after each add and after `CommitLog.instance.sync(true)`. Not observable directly: CAS retries and the transient `allocatePosition = endOfBuffer + 1` state, except by sampling after `discardUnusedTail`.

**B2e. Procedure.**
1. Build (B2a).
2. For each mode × n: set the knobs, start the commit log (`CommitLog.instance.start()` through `SchemaLoader.prepareServer()` as in the backpressure test), record `buffer.capacity()` and `endOfBuffer` of the first segment.
3. Run the workload, recording the maximum `position + size` over all allocations, per segment.
4. Force `sync(true)`, then record file lengths and `onDiskSize()` for every segment, and `isStillAllocating()` for the retired ones.
5. Shut down (`CommitLog.instance.shutdownBlocking()`), delete `/tmp/cass-ut/data`.

**B2f. Predictions.** Stated before any run. *(Amended 2026-10-23, stage-4 audit: see B2i items 2 to 4 for the retired-segment positions, the compressed file length and the direct-mode capacity.)*
- Every allocation satisfies `position + size < endOfBuffer ≤ buffer.capacity()`.
- mmap: `buffer.capacity() == n MiB` exactly; every file length equals `n MiB`; `onDiskSize() == n MiB`.
- compressed: `buffer.capacity() == n MiB`; file lengths are at most `n MiB` and, for random payloads, close to the filled size; the per-segment maximum offset stays below `n MiB`.
- direct: `buffer.capacity()` is `n MiB` or up to `fsBlockSize - 1` bytes more (alignment); file length still a multiple of the block size and at most `n MiB` plus one block.
- Retired segments report `isStillAllocating() == false`, and `allocatePosition == endOfBuffer + 1` (equal to `capacity + 1`, assertion `:275`/`:282`). The active segment reports true.
- More than `n MiB` of total payload yields more than one segment, never one larger segment.
- Scaling n from 1 to 4 to 32 scales the capacity linearly.

**B2g. Readings.** *(Amended 2026-10-23: rows on compressed file length and direct-mode capacity are replaced by B2i items 3 and 4.)*

| Observation | Meaning |
|---|---|
| All offsets < `n MiB` and file lengths ≤ `n MiB` (or ≤ aligned bound for direct) in every mode | Claim holds in the unit tier |
| Any allocation with `position + size >= buffer.capacity()` | Claim refuted: `allocate()` check is not effective |
| A file longer than `n MiB` (mmap or compressed) | Claim refuted for that mode |
| Direct-mode capacity larger than `n MiB` by up to `fsBlockSize - 1` | Not a refutation; the cap is `n MiB` plus alignment slack, record it |
| Only one segment is ever created although payload exceeds `n MiB` | Workload or throttling problem (pool limit, sync blocked); the limit was not reached, claim not confirmed |
| Capacity does not change with n | `setCommitLogSegmentSize` did not take effect; rerun |

**B2h. Controls.** Vary only n between runs. Use the same payload seed. Compare mmap against compressed to separate buffer size from file size. Positive control for sensitivity: a deliberately failing assertion variant that expects the cap `n + 1` MiB must fail. Use a fresh JVM per mode so the pool and `DatabaseDescriptor` state do not carry over.

**B2i. Stage-4 audit amendments, 2026-10-23.** Each is derived from the pinned source alone, before any run or reading; none changes B1.

1. **Knob and JVMs (B2a, B2b).** `n` is set through a per-arm yaml (a copy of `test/conf/cassandra.yaml` with `commitlog_segment_size: <n>MiB`, `max_mutation_size` unset, `commitlog_compression` or `commitlog_disk_access_mode: direct` set per mode), passed as `-Dcassandra.config=file://<yaml>` in `-Dtest.jvm.args`, one fresh JVM per (mode, `n`) arm, instead of `setCommitLogSegmentSize`. Reason: the test yaml has 5 MiB, so after the setter `max_mutation_size` stays 2.5 MiB (`DatabaseDescriptor.java:898-899` runs only at config load) and `IMutation.MAX_MUTATION_SIZE` is a static final read once (`IMutation.java:31`); then B2c's "exactly `max_mutation_size`" mutation would be larger than a 1 MiB segment and `CommitLogSegmentManagerStandard.allocate` (`:52-57`) would loop forever on it. `commitlog_sync_period` stays at the yaml's 10 s; every observation is followed by an explicit `sync(true)` where B2e asks for one.
2. **Retired-segment positions (B2f, last-but-two bullet).** "`allocatePosition == endOfBuffer + 1`" contradicts A3.3 and the source. `discardUnusedTail()` sets `allocatePosition = endOfBuffer + 1` **with the old `endOfBuffer`, which equals `capacity`**, then overwrites `endOfBuffer` with the last reserved offset (`CommitLogSegment.java:271-282`). Replacement prediction: for a retired segment `allocatePosition == capacity + 1`, `endOfBuffer < capacity` (it is the last reserved offset), `isStillAllocating() == false`; for the allocating segment `allocatePosition < endOfBuffer == capacity` and `isStillAllocating() == true`. A closed segment's `buffer` is null (`:524-528`), so `capacity` is recorded when the segment first appears in `getActiveSegments()`.
3. **Compressed file length (B2f, B2g).** A compressed segment's file is the header plus, per sync, a 12-byte marker and one LZ4 block (`CompressedSegment.java:44-92`), and an LZ4 block of the random payload B2c prescribes is larger than its input (about `len/255 + 16`). So "compressed file lengths are at most `n MiB`" (B2f) and "a file longer than `n MiB` (mmap or compressed): refuted" (B2g) are withdrawn for compressed arms. Replacement prediction for compressed arms: `capacity == n·2^20`, every `position + size < capacity`, every retired `endOfBuffer < capacity`, and `fileLength <= n·2^20 + ceil(n·2^20/255) + 32·(syncs in that segment) + 64`. Replacement B2g rows: a compressed file above `n·2^20` but within that bound is expected expansion of the plaintext-capped segment, not a refutation; above the bound, or any offset `>= capacity`, is Refuted. mmap rows are unchanged.
4. **Direct-mode capacity (B2f, B2g).** B2f's "`n MiB` or up to `fsBlockSize - 1` bytes more" is not what the code does: the direct pool oversizes its raw buffer, then `alignedSlice` is asserted to have `limit == capacity == segmentSize` (`DirectIOSegment.java:217-219`). Replacement prediction: direct `capacity == n·2^20` exactly, file length a multiple of the block size and `<= n·2^20`. If the volume does not support direct I/O (`DatabaseDescriptor.java:1533-1540`), the arm is `n/a: direct I/O unsupported on this volume`, recorded with the startup error, not a failure of the claim.
5. **Payload (B2c).** "A payload of `size/16` bytes" means `n·2^20/16` bytes of random data per mutation (64 KiB at `n = 1`, 256 KiB at 4, 2 MiB at 32), 64 adds per arm; the boundary mutation is one with serialized size + 12 equal to `max_mutation_size` (`n·2^19`, accepted) and the too-large one is `n·2^19 + 1` (rejected with `MutationExceededMaxSizeException`, `oversizedMutations` +1). Sizes are found by probing `Mutation.serializedSize` so the totals are exact.
6. **Control (B2h).** The "deliberately failing assertion variant" is the analysis script asserting `capacity == (n+1) MiB`; it must report false for every arm. The scaling control is the three values of `n` run on the same payload seed.
7. **Cluster tier.** Stress values are random (incompressible), so the LZ4 series falls under item 3: the bound is the plaintext cap, not `n`. Off-heap is read from `/proc/<pid>/maps` (the `CommitLog-*.log` mappings, mmap series) and `jcmd VM.native_memory summary` (compressed series, node started with `-XX:NativeMemoryTracking=summary`). Live file sizes by `stat -c %s` (a file not yet mapped can read 0). Peak file counts are reported and, as B3g says, are not a refutation. "Segment rolls" in B3g are counted as distinct `CommitLog-*.log` names created during the stress run.

### B3. Cluster tier

**B3a. Environment and build.** One node (a second node is optional and unnecessary), Linux, JDK 11, Ant. `rsync -a /users/jason92/cassandra-5.0.9/ /tmp/cass-node/ && cd /tmp/cass-node && ant jar`. In the copy's `conf/cassandra.yaml` set data, commit log, hints, saved_caches and cdc_raw directories under `/tmp/cass-node/data/` (local disk, check `df -h /tmp` shows at least 20 GiB free). `commitlog_sync: periodic`, `commitlog_sync_period: 10s`. Heap `-Xms2G -Xmx2G` (`conf/jvm11-server.options`) so the off-heap numbers are separable from heap.

**B3b. Knobs.** `commitlog_segment_size`: 8MiB, 32MiB (default), 64MiB; set in the yaml, one node restart each. Keep `commitlog_total_space: 1024MiB` fixed so the total bound is the same in all runs. Run a second series with `commitlog_compression: [{class_name: LZ4Compressor}]` at 32MiB. Leave `memtable_flush_period` and table flushing defaults, and disable memtable-driven flushes for the run by setting a large `memtable_heap_space`/`memtable_offheap_space` (e.g. 1GiB each), so commit log segments are not recycled early.

**B3c. Workload.** `tools/bin/cassandra-stress write n=2000000 -col size=FIXED(1024) n=FIXED(1) -rate threads=64 -schema keyspace=ks1 replication(factor=1)` (about 2 GiB of payload, well over the 1 GiB total space and many times any segment size, so segments roll about 64 times at 32 MiB). Duration: until the stress run finishes (minutes). Arithmetic: 2,000,000 × ~1.1 KiB ≈ 2.1 GiB of commit log writes versus 8, 32, 64 MiB segments gives about 270, 68 and 34 segment rolls.

**B3d. Observables and instruments.**
- Disk: `stat -c %s` on every file in the commit log directory every 5 s (`watch`/loop writing a CSV), plus `du -sb` of the directory.
- Metrics via JMX (`nodetool sjk mx` or `jconsole`): `org.apache.cassandra.metrics:type=CommitLog,name=TotalCommitLogSize`, `PendingTasks`, `WaitingOnSegmentAllocation`, `CompletedTasks`.
- Off-heap: `nodetool info` and `jcmd <pid> VM.native_memory summary` (start the node with `-XX:NativeMemoryTracking=summary`), plus `pmap -x <pid>` to see mapped `.log` regions.
- Heap: `jcmd <pid> GC.heap_info`.
- Not observable directly: `allocatePosition` and `endOfBuffer` (use the unit tier).

**B3e. Procedure.**
1. Build; record `df -h /tmp`.
2. For each knob value: write the yaml, start the node (`bin/cassandra -f` in the background with output to a log, `-Dcassandra.logdir=/tmp/cass-node/logs`), wait for "Starting listening for CQL clients".
3. Start the sampler loop (B3d).
4. Run the stress command (B3c).
5. After it ends, wait 60 s, run `nodetool flush`, wait 60 s, stop sampling.
6. `nodetool drain`, stop the node, confirm with `pgrep -f CassandraDaemon` that nothing is left, then `rm -rf /tmp/cass-node/data` before the next value.

**B3f. Predictions.** Stated before any run.
- Every `*.log` file seen during the run has length ≤ `commitlog_segment_size` for the mmap series, and the observed file length is exactly the configured size (mmap preallocates the full length) for 8, 32 and 64 MiB.
- The count of files at the peak is about `1024 MiB / segment size` plus 1 to 2 (the allocator's prepared segment and the not-yet-reclaimed overshoot), i.e. about 129-130, 33-34 and 17-18.
- For compressed segments file lengths are at most the configured size and typically smaller; `TotalCommitLogSize` is below the uncompressed volume written.
- Resident off-heap growth from the commit log is about one segment size per active/prepared segment for the compressed series (pool of up to 3 buffers), and the mapped regions in `pmap` for the mmap series are one segment size each.
- The per-segment bound does not become a total bound: `TotalCommitLogSize` may exceed `commitlog_total_space` momentarily by roughly one to two segments.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| All files ≤ configured size at all three values; file size tracks the knob | Claim holds in the cluster tier |
| Any file larger than the configured size | Claim refuted |
| File size identical across the three knob values | The knob is not governing size (or the setting did not load); check the startup log, claim not confirmed |
| Peak file count ≫ `1024/size + 2` | Segment recycling or flushing is lagging; the total bound is weaker than predicted, but the per-segment claim is unaffected |
| Peak `TotalCommitLogSize` far over 1024 MiB | Overshoot of the soft total bound (A3.6), reported as a finding, not a refutation |
| Fewer than about 30 segment rolls | Workload too small or the memtable flushes recycled segments early; limit not reached, claim not confirmed |

**B3h. Controls.** Same stress command, schema and heap for each value; only `commitlog_segment_size` differs. Positive control for the contrast between a per-segment cap and a soft total cap: also run `commitlog_total_space: 256MiB` at the 32 MiB segment size; the file count at peak should drop to about 8-10, showing a cap that does bind on the number of segments. The compressed series separates buffer size from file size.

**B4. Risks and cleanup.** Peak disk use is below about 2.5 GiB per run (1024 MiB commit log plus sstables from the stress data), all in `/tmp/cass-node/data` or `/tmp/cass-ut/data`, never the shared tree. Check `df -h /tmp` before each run. After each run stop the node (`nodetool drain`, then kill), confirm with `pgrep -fl "CassandraDaemon|ant|java"` that no process of this run is left, kill the sampling loop, then delete the data directories and the `/tmp/cass-node`, `/tmp/cass-ut` copies at the end. Do not run on a node holding real data.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java
- src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java
- src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerStandard.java
- src/java/org/apache/cassandra/db/commitlog/MemoryMappedSegment.java
- src/java/org/apache/cassandra/db/commitlog/CompressedSegment.java
- src/java/org/apache/cassandra/db/commitlog/DirectIOSegment.java (lines 40-110, 190-206)
- src/java/org/apache/cassandra/db/commitlog/CommitLog.java (lines 595-625)
- src/java/org/apache/cassandra/io/util/SimpleCachedBufferPool.java
- src/java/org/apache/cassandra/config/Config.java (grep hits)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 640-690, 2875-2913, grep hits)
- src/java/org/apache/cassandra/metrics/CommitLogMetrics.java (grep hits)
- conf/cassandra.yaml (lines 640-680, 870-885)
- test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentBackpressureTest.java (lines 40-120)
- test/unit/org/apache/cassandra/db/commitlog/CommitLogTest.java (grep hits)

## D. Stage-4 feedback

**2026-10-23, stage 4 (pc12, one run per tier, no run 2).** Results: [`results/commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous.md`](../../stage4-runtime-verification/results/commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous.md). Case-file version: sha256 `df551bcd9ea44616670d3a9bb14016f8fa1d51c8edf7b7a18f726c48e48276fc` (after the audit's B2i amendments; the file is untracked, so no commit holds it).

- **Verdict:** unit **Confirmed — caps**; cluster **Confirmed — caps**. **Outcome class: true positive** (estimate `positive`, effect `caps`). The estimate stands: capacity was exactly n MiB in mmap, LZ4 and direct modes (50 segments), every end offset was below capacity, mmap files were exactly n, direct files were block multiples at most n, and the largest live file in the cluster scaled 1 : 4 : 8 with the knob (8, 32, 64 MiB). The entry line itself, `isStillAllocating()` (`:423`), is observed to be false for exactly the 40 retired segments and true for the 10 open ones; it gates retirement and does not enforce the size (A3.5), which the offsets and file lengths show.
- **Amended before run 1 (B2i, 2026-10-23):** the knob is set by yaml, not the test setter (`max_mutation_size` and the static `IMutation.MAX_MUTATION_SIZE`); B2f's "`allocatePosition == endOfBuffer + 1`" for a retired segment was wrong (`allocatePosition == capacity + 1`, `endOfBuffer` is the last reserved offset); the compressed file length is not capped by n (LZ4 expansion; not exercised here, payloads of n/16 leave a tail, max 0.9436 × n; seen in the sibling case at 1.0039 × S); direct-mode capacity is exactly n (asserted at `DirectIOSegment.java:217-219`), not "up to `fsBlockSize - 1` more".
- **Misses of soft predictions (not the claim):** (1) peak live files were 95 / 26 / 15 at n = 8 / 32 / 64, below B3f's "about 129–130 / 33–34 / 17–18", because 8 `MEMTABLE_LIMIT` flushes reclaimed segments before the 1024 MiB total space was reached (peaks 760 to 960 MiB); B3g has no row for "below". With a 1 GiB memtable heap the memtable limit, not `commitlog_total_space`, set the retention. (2) The control (`commitlog_total_space` 256 MiB at n = 32) peaked at 24 files / 768 MiB against B3f's "8–10" and the uncontrolled 26 files / 832 MiB: the 90 MB/s writer outran the reactive reclaim (`maybeFlushToReclaim` runs at segment allocation), so the control did not bind within its prediction. (3) The off-heap prediction for compressed segments was not testable: NMT "Other" (1.4 to 1.5 GiB) mixes the pool with other direct buffers.
- **Wording to fix in stage 3:** B2c's "payload of `size/16` bytes" needed the clarification now in B2i.5; B3a's heap and memtable pair (2 GiB heap, 1 GiB memtable heap) makes the memtable limit the retention bound, so the file-count predictions need either a larger memtable limit or the control at a lower write rate. The `OversizedMutations` MBean name in B3d was not found.
- **Bypass/Target-3 note:** none for the per-segment cap; the directory-level footprint is only softly bounded by `commitlog_total_space` (768 MiB at 256 MiB total space under a fast writer).
