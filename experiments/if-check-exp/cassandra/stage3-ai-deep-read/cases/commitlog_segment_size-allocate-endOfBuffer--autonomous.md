# commitlog_segment_size — verification solution  <!-- file: cases/commitlog_segment_size-allocate-endOfBuffer--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java:246` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (`claude-sonnet-5-5`), Claude Code CLI (version not exposed to the session), 2026-10-23 |
| Estimate | `positive`, scoped to a single segment: the bytes a segment can hold, and so the size of its file or buffer, are capped by `commitlog_segment_size`. The commit log's total disk footprint is capped by a different, soft limit (`commitlog_total_space`), so the segment size bounds each file but not the sum. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- Name: `commitlog_segment_size` (yaml), field `Config.commitlog_segment_size`. Kind: configuration entry. Old name `commitlog_segment_size_in_mb` is accepted through `@Replaces` (`Config.java:396`).
- First declared at `src/java/org/apache/cassandra/config/Config.java:397` as `DataStorageSpec.IntMebibytesBound`, default `"32MiB"`. The default is a literal in the field initializer. `conf/cassandra.yaml:660` repeats `32MiB`.
- Unit: MiB in the yaml; `DatabaseDescriptor.getCommitLogSegmentSize()` (`DatabaseDescriptor.java:2875-2877`) returns bytes as `int`.
- Validation at startup (`DatabaseDescriptor.java:891-901`):
  - must be non-zero and `< 2048` MiB;
  - `max_mutation_size` defaults to half the segment size (`:899`);
  - an explicit `max_mutation_size` must satisfy `segment >= 2 * max_mutation_size` (`:900-901`).
- Settable only in `cassandra.yaml` (or by an `-Dcassandra.config` alternate yaml). A restart is required. The only runtime setter is the test hook `setCommitLogSegmentSize` (`DatabaseDescriptor.java:2887`). `CommitLogSegmentManagerCDC.java:402-404` states that it is "only loaded from yaml".
- Related limits that interact with it:
  - `commitlog_total_space`, `Config.java:390`. Its default is computed at `DatabaseDescriptor.java:664-675`: 8192 MiB, or 1/4 of the commitlog volume if that is smaller, through `calculateDefaultSpaceInMiB`.
  - `max_mutation_size`, `Config.java:407`.

**A2. What it caps.**
- Resource: **disk** for every access mode. It also caps **memory** for the modes that stage a segment in a heap or direct buffer: the compressed and encrypted segments, and direct I/O.
- Quantity compared against the limit at the target line: `next = allocatePosition + size` against `endOfBuffer`. `endOfBuffer` is set to `buffer.capacity()` in `writeLogHeader()` (`CommitLogSegment.java:177`), and the buffer's capacity is the configured segment size:
  - mmap: `channel.map(READ_WRITE, 0, getCommitLogSegmentSize())`, `MemoryMappedSegment.java:62`.
  - compressed / encrypted / direct: the `SimpleCachedBufferPool` buffers are sized by `getCommitLogSegmentSize()` (`CompressedSegment.java:113-117`, `EncryptedSegment.java:176`, `DirectIOSegment.java:201-206`, with block padding).
- So the operand is the in-segment write offset, counted in bytes of the uncompressed log stream.

**A3. Mechanism.**
1. `CommitLog.add` calls `mutation.validateSize(current_version, ENTRY_OVERHEAD_SIZE)` (`CommitLog.java:304`). This rejects a mutation whose serialized size plus 12 bytes overhead exceeds `MAX_MUTATION_SIZE` (`Mutation.java:169-176`; constant from `IMutation.java:31`). It throws `MutationExceededMaxSizeException` and marks `oversizedMutations`. This is the front-door cap that keeps a single entry below half a segment.
2. `segmentManager.allocate(mutation, size + 12)` (`CommitLog.java:311`) is `CommitLogSegmentManagerStandard.allocate` (`:47-60`). It calls `segment.allocate(mutation, size)` in a loop. When that returns `null` it calls `advanceAllocatingFrom(segment)` and retries on the next segment.
3. `CommitLogSegment.allocate(Mutation,int)` (`CommitLogSegment.java:201-223`) calls the private `allocate(int)`. The private method (`:240-255`) is the target: a CAS loop on `allocatePosition`.
   - **Line 245-246:** `next = prev + size; if (next >= endOfBuffer) return -1;`
   - **Outcome at the limit:** `-1`. The public `allocate` closes the `OpOrder` group and returns `null`; the manager moves to a new segment. Nothing is written past `endOfBuffer`.
   - The `>=` leaves the last byte unused, so the largest reachable `allocatePosition` is `endOfBuffer - 1`.
4. `sync()` (`:303-372`) also uses `allocate(SYNC_MARKER_SIZE)` (`:327`). A failure there means "segment is full": `discardUnusedTail()` (`:258-287`) sets `allocatePosition = endOfBuffer + 1`, then the segment is closed (`internalClose`, `:520-531`).
5. Whole-commit-log accounting: `AbstractCommitLogSegmentManager.size` (`:103`) is incremented per segment (mmap: `MemoryMappedSegment.java:63`; compressed: `CompressedSegment.java:81`; header: `FileDirectSegment.java:49`). `unusedCapacity()` (`AbstractCommitLogSegmentManager.java:445-451`) subtracts it from `commitlog_total_space`. `maybeFlushToReclaim()` (`:246-264`) forces flushes of the oldest segments when `unused < 0`.

**Bypasses and overshoots.**
- Overshoot of the per-segment cap: none in the allocation path, because the CAS only succeeds when `next < endOfBuffer`.
- Disk size can be *less* than the cap for compressed/encrypted segments (`onDiskSize()` is `lastWrittenPos`, `CompressedSegment.java:93-96`). The plaintext offset is still capped, but the file size is not equal to it.
- The cap bounds each segment, not the directory. Total disk is `segments × segment size`, limited only by `commitlog_total_space`. That limit is enforced asynchronously by the flush path (`maybeFlushToReclaim`), and the allocator thread keeps one segment pre-built in `availableSegment`. In practice, directory size can exceed `commitlog_total_space` by at least the pre-allocated segment plus whatever is not yet reclaimable. It also grows past it if flushes are slow or blocked. This is a different constraint; it is noted here because it bounds how far a per-segment cap implies a disk cap.
- Segments for which a table is still dirty cannot be freed until flush completes (`getDirtyTableIds`, `isUnused`, `CommitLogSegment.java:591-620`).
- CDC mode adds its own accounting (`CommitLogSegmentManagerCDC.java:201-207`) and is out of scope.

**A4. Other consumers.**
- Memtables / flush writers / SSTables share the same disk if the commit log directory is not separate.
- `cdc_raw` hard links, archived (`commitlog_archiving.properties`) segments, and not-yet-replayed files from previous runs (`CommitLog.java:170-214`) occupy the commitlog directory without being counted in `size`.
- The compression buffer pool (`commitlog_max_compression_buffers_in_pool`, default 3, `Config.java:400`) caps pooled buffer count, so memory is `buffers × segment size` for non-mmap modes.
- Hints and system files use `getMaxMutationSize()` (`HintsService.java:110`) which derives from the same value.

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:644-660` (comments on segment size, max mutation size, 2048 limit).
- Test files for patterns to copy (existence only; contents not relied on): `test/unit/org/apache/cassandra/db/commitlog/CommitLogTest.java`, `CommitLogSegmentBackpressureTest.java`, `CommitLogChainedMarkersTest.java`.
- No external documentation or tracker issue was consulted.

## B. Verification solution

**B1. Claim under test.** With `commitlog_segment_size = S`, no commit log segment accepts an entry that would place its end at or beyond `S` bytes: the in-segment write offset never reaches `S`, a new segment is started instead, and the segment file's size on disk never exceeds `S` (plus nothing, for mmap and direct, where the file is pre-sized to `S`). The claim is per segment; it does **not** claim that the commit log directory stays below `S`, or below any multiple of it.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11, Ant. Copy the tag to local disk, e.g. `rsync -a ~/cassandra-5.0.9/ /local/work/c509/`. Never build in the shared tree.
- `cd /local/work/c509 && ant jar` then `ant build-test`.
- Put the test at `/local/work/c509/test/unit/org/apache/cassandra/db/commitlog/SegmentSizeCapTest.java`. It must be in package `org.apache.cassandra.db.commitlog` to reach the package-private `CommitLogSegment.allocate(Mutation,int)` and `lastSyncedOffset`.
- Run: `ant testsome -Dtest.name=SegmentSizeCapTest -Dtest.classlist.file=` or `ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.SegmentSizeCapTest`.
- JVM options: the stock test settings from `build.xml`. Heap: `-Xmx1g` is enough. Use a scratch directory on a local disk of known size for `commitlog_directory`, with at least 2 GiB free.
- Start from the structure of `CommitLogTest` (config via `DatabaseDescriptor.daemonInitialization()`, a `CommitLog.instance.start()`-style setup).

**B2b. Knobs.**
- `S` = `commitlog_segment_size` in MiB, set with `DatabaseDescriptor.setCommitLogSegmentSize(S)` *before* `CommitLog` starts, or through a test yaml (`-Dcassandra.config=file:///.../test.yaml` with `commitlog_segment_size: <S>MiB`). Values: 1, 2, 8, 32. 1 MiB is the smallest legal value (zero is rejected at `DatabaseDescriptor.java:891`); 32 is the default; the spread shows linear scaling.
- Access mode: `commitlog_disk_access_mode`: `mmap` (default path for uncompressed) and, as a second run, `commitlog_compression: LZ4Compressor` with `standard`. Both are supported by the builders in `AbstractCommitLogSegmentManager.createSegmentBuilder` (`:121-143`).
- `max_mutation_size` is left unset so it is `S/2` (`DatabaseDescriptor.java:899`).

**B2c. Workload.**
- Drive `CommitLog.instance.add(mutation)` directly, with a single table of one `blob` column and mutations whose payload is chosen so that serialized size plus 12 bytes is a known value `E`.
- Fixed `E = 64 KiB` (well under `S/2` for every `S` ≥ 1 MiB). Number of adds: `ceil(3 × S / E) + 10`. For `S = 8 MiB` that is 384 + 10 = 394 adds, producing at least 3 segment rollovers.
- Then a boundary probe: reach the tail exactly by adding entries until `getCurrentCommitLogPosition().position` is within `E` of `S`, and add one more entry of size `E`. Allocation must fail on this segment and roll over.
- Oversize probe: one mutation with serialized size `S/2 + 1` KiB. Expect `MutationExceededMaxSizeException` (`CommitLog.java:304`).
- Arithmetic: each segment holds at most `floor((S - header - 8 - 1) / E)` entries (header size from `CommitLogDescriptor.writeHeader`; initial sync marker 8 bytes, `CommitLogSegment.java:96,180`; the `>=` at `:246` costs one more byte). The number of rollovers after `n` adds is therefore at least `floor(n / that)`.

**B2d. Observables and instruments.**
- Per-segment write offset: `segment.getCurrentCommitLogPosition().position` (`CommitLogSegment.java:441-444`) just before each `add`, taken from `CommitLog.instance.segmentManager.getActiveSegments()`; record the maximum per segment id. Note the post-close value is `endOfBuffer + 1` (`:271-282`); take the maximum observed *before* `discardUnusedTail` runs, and separately record `allocatePosition - 1` after close as the `buffer.capacity()` marker.
- `segment.buffer.capacity()` while open (package-private field `buffer`, `:136`).
- `segment.onDiskSize()` and, for each file in the commit log directory, `File.length()`.
- `CommitLog.instance.metrics.oversizedMutations` count.
- Not observable directly: `endOfBuffer` (private); derive it from `buffer.capacity()` as `writeLogHeader` does (`:177`).
- Sampling: after every `add` for positions; file sizes once at the end and after `CommitLog.instance.sync(true)`.

**B2e. Procedure.**
1. Copy and build as in B2a.
2. For each `S` in {1, 2, 8, 32} and each mode in {mmap, LZ4+standard}: start a fresh JVM (fresh test method with `CommitLog.instance.stopUnsafe(true)` then restart, or a separate `ant testsome` per value).
3. Set `S`, start the commit log, record `buffer.capacity()` of the first segment.
4. Run the workload of B2c, recording per-segment maximum observed position and the final file sizes.
5. Run the boundary probe and the oversize probe.
6. Write results as a CSV: `S, mode, segmentId, maxPosition, bufferCapacity, fileLength, onDiskSize`.
7. `ant clean`-free cleanup: delete the scratch commit log directory.

**B2f. Predictions (stated before any run).** *(Amended 2026-10-23, stage-4 audit: see B2i items 2 and 3 for the compressed-mode file length and the retired-segment positions.)*
- `buffer.capacity() == S × 1048576` for every `S`, in both modes (compressed mode: pool buffer sized by `getCommitLogSegmentSize()`, with no direct-I/O padding).
- For every segment, `maxPosition < S × 1048576`. The gap is below `E + 12` bytes, since the next entry is the one that failed.
- mmap: `fileLength == S × 1048576` for every segment, including the last, partially filled one.
- Compressed: `fileLength <= S × 1048576`. For incompressible payloads it is slightly below `S` because of the 8-byte markers; for compressible payloads it is far smaller.
- Number of segments after `n` adds is at least `ceil(n × E / S)`.
- Boundary probe: the final entry rolls to a new segment and the old segment's position stays `< S`.
- Oversize probe: throws; `oversizedMutations` increases by 1; no bytes are added to any segment.
- What would show the claim wrong: any `maxPosition >= S × 1048576`, any `fileLength > S × 1048576`, or `buffer.capacity() != S × 1048576`.

**B2g. Readings.** *(Amended 2026-10-23: the compressed-mode `fileLength` rows are replaced by B2i item 3.)*

| Observation | Meaning |
|---|---|
| All `maxPosition < S·2^20`, `capacity == S·2^20`, mmap `fileLength == S·2^20` | Claim supported: segment size caps the segment. |
| Any `maxPosition >= S·2^20`, or `fileLength > S·2^20` | Claim refuted: the allocation guard at `:246` or the buffer size is bypassed. |
| `capacity != S·2^20` for some mode | The knob is not the buffer size in that mode; the cap is then governed by something else. Trace that mode again. |
| Compressed `fileLength` far below `S` | Expected; cap holds on plaintext, disk usage is lower. Not a refutation. |
| Rollover count does not grow as `S` shrinks | The workload did not reach the limit (check `E` and `n`); not confirmed. |
| Oversize mutation accepted | `max_mutation_size` guard is not in effect; separate finding. |

(No negative-estimate rows are needed because the estimate is positive.)

**B2h. Controls.**
- Same workload at two values of `S` to show the effect is the knob, not the workload: the per-segment maximum must scale with `S`.
- Run the in-segment test with `E` varied (16 KiB and 64 KiB) to check the gap below `S` tracks `E`.
- Repeat one configuration twice to show the result is deterministic.

**B2i. Stage-4 audit amendments, 2026-10-23.** Each is derived from the pinned source alone, before any run or reading; none changes B1.

1. **Knob and JVMs (B2a, B2b).** `S` is set through a per-arm yaml (a copy of `test/conf/cassandra.yaml` with `commitlog_segment_size: <S>MiB`, `max_mutation_size` unset, `commitlog_compression` set for the LZ4 arms), passed as `-Dcassandra.config=file://<yaml>` in `-Dtest.jvm.args`, one fresh JVM per (`S`, mode, `E`) arm. It is not `setCommitLogSegmentSize`: the test yaml has 5 MiB, so after the setter `max_mutation_size` stays 2.5 MiB (`DatabaseDescriptor.java:898-899` runs only at config load), and `IMutation.MAX_MUTATION_SIZE` is a static final read once (`IMutation.java:31`), so the oversize probe and the `S/2` entry ceiling would not be `S/2`. Mode `mmap` is `commitlog_disk_access_mode: legacy` without compression; the LZ4 arm sets `commitlog_compression: - class_name: LZ4Compressor`.
2. **Observables (B2d).** A closed segment's `buffer` is nulled (`CommitLogSegment.java:524-528`), so `buffer.capacity()` is recorded the first time a segment appears in `getActiveSegments()`. `endOfBuffer` (private) is read by reflection. After a segment retires, `discardUnusedTail()` has set `endOfBuffer` to the last `allocatePosition` that was reached (`:271-282`), so for a retired segment the exact maximum reserved offset is `endOfBuffer` and `allocatePosition == capacity + 1`. The end offset of every add is also taken from the returned `CommitLogPosition.position`, which is `buffer.limit()` = `prev + size` (`CommitLogSegment.java:748-751`), the very `next` compared at `:246`. Prediction: every returned end offset and every retired `endOfBuffer` is `< capacity`.
3. **Compressed-mode file length (B2f, B2g, B3f, B3h).** A compressed segment's file is the header plus, per sync, a 12-byte marker and one LZ4 block (`CompressedSegment.java:44-92`), and an LZ4 block of incompressible bytes is larger than its input (about `len/255 + 16`). So the file can exceed the plaintext offset: the cap holds on the plaintext offset (`capacity`, `endOfBuffer`, `maxPosition`), **not** on the compressed file length, and "compressed `fileLength <= S`" in B2f / B2g / B3f is withdrawn for incompressible payloads. Replacement prediction for the compressed arms: `capacity == S·2^20`, every `maxPosition < S·2^20`, and `fileLength <= S·2^20 + ceil(S·2^20/255) + 32·(syncs in that segment) + 64`; for compressible payloads (repeated byte) `fileLength` is far below `S·2^20`. Replacement rows for B2g: compressed `fileLength` above `S·2^20` but within that bound is **expected expansion, not a refutation** of the plaintext cap; `fileLength` above that bound, or any `maxPosition >= capacity`, is **Refuted**. mmap rows are unchanged (`fileLength == S·2^20`).
4. **Exact-edge probe (B2c, added).** B2c's boundary probe only gets "within `E`". Because the target is `next >= endOfBuffer` (`:246`), add two probes, each in a fresh segment, after `sync(true)` so that no marker moves `allocatePosition` (`commitlog_sync_period` is raised to 1h in the arm yaml; the extra sync at a rollover is waited out by a final `sync(true)`): fill with `E`-sized entries until `remaining = capacity - allocatePosition <= S/2`, then (a) add one entry whose total size (serialized + 12) is `remaining - 1`: prediction, it stays in this segment and `allocatePosition == capacity - 1`; (b) in a further fresh segment, with its own `remaining = R` read the same way, add one entry with total size `R`: prediction, it is refused (`next == capacity`), the add returns a position in a new segment, and the old segment, once retired, has `endOfBuffer == capacity - R` (its last reserved offset) and never reached `capacity`. A (a) that rolls or a (b) that stays in the segment contradicts the `>=` reading.
5. **Cluster tier (B3c, B3d, B3f).** Stress generates incompressible values, so the LZ4 cluster arm falls under item 3 (bound, not `S`); the compressible control (repeated byte) is run with a small Python loader on the bundled driver at the same row count. A live file's size is read with `stat -c %s`; a file just created and not yet mapped can read 0, so "every file is exactly `S`" in B3f is read as "no file is larger than `S`, and the largest observed is `S`". Peak file counts are reported and, as B3g already says, are not a refutation. Off-heap is read from `/proc/<pid>/maps` (size of the `CommitLog-*.log` mappings) in addition to the files.
6. **Positive control (B2h, B3h).** B2h's two-`S` comparison is the control for the unit tier; the cluster tier's control is B3h's `commitlog_total_space: 64MiB` arm.

### B3. Cluster tier

**B3a. Environment and build.**
- One node suffices; a second node is optional. Linux, JDK 11, Ant. Build a local copy: `rsync -a ~/cassandra-5.0.9/ /local/work/c509-node/ && cd /local/work/c509-node && ant jar`.
- Directories on local disk of known size (≥ 20 GiB free): `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` under `/local/work/node1/`. Put `commitlog_directory` on its own filesystem or directory whose usage you can measure with `du -sb`.
- `cassandra.yaml` changes: `commitlog_segment_size: <S>MiB`; `commitlog_total_space: 4096MiB` (large, so the total limit does not fire and only the segment size is under test); `commitlog_sync: periodic`; `commitlog_sync_period: 100ms`; `commitlog_disk_access_mode: mmap`; `memtable_heap_space`/`memtable_offheap_space` left as default but `memtable_flush_writers: 1`. To keep the commit log from being reclaimed during the run, use a large memtable: `memtable_heap_space: 2048MiB` with `-Xmx4g`.
- JVM options: `-Xms4g -Xmx4g`.
- Disable auto-snapshot irrelevance: no snapshots are needed.

**B3b. Knobs.**
- `S` in {8, 32, 128} MiB, each in a fresh data directory, restarting the node between values. Reason: three values a factor of four apart, so a 4× change in segment file size is unmistakable.
- Positive control: a second knob, `commitlog_total_space`, set to 64 MiB with `S = 8` MiB, a limit known to cause flush-driven reclaim of old segments.

**B3c. Workload.**
- `cassandra-stress` from the same build (`tools/bin/cassandra-stress`), or a CQL script, on a table `ks.t (k int primary key, v blob)` with `durable_writes = true`.
- Write 1 KiB blobs through the native protocol at CL ONE: `n = 600000` rows → about 600 MiB of commit log payload, which exceeds `S = 128` MiB by about 4.7× and `S = 8` by about 75×. So even the largest value produces several segment rollovers.
- Memtable is kept from flushing early by the large memtable settings above; otherwise old segments would be deleted before they are measured. Duration: a few minutes.

**B3d. Observables and instruments.**
- `ls -l --time-style=full-iso <commitlog_directory>` and `stat -c %s` for each `CommitLog-*.log` every 2 s during the run. Per-file maximum, and file count.
- `du -sb <commitlog_directory>` (total bytes).
- `nodetool` JMX metrics: `org.apache.cassandra.metrics:type=CommitLog,name=TotalCommitLogSize`, `name=CompletedTasks`, `name=OversizedMutations`; read through `nodetool sjk mx` or any JMX client.
- Not observable: `endOfBuffer` and per-segment `allocatePosition`; only file sizes are available. For mmap, file length is pre-set to `S`, so it shows the cap but not fill level; use `TotalCommitLogSize` and segment count for fill.

**B3e. Procedure.**
1. Build the local copy; prepare `/local/work/node1` and the yaml for `S = 8`.
2. Start the node: `bin/cassandra -f -p /local/work/node1/pid` (background it), wait for "Starting listening for CQL clients".
3. Create the keyspace and table. Start the sampler loop on the commit log directory.
4. Run the workload; stop when stress finishes.
5. `nodetool drain` is not used until sampling ends; stop the sampler; record the maximum single-file size and the file count.
6. Stop the node (`kill $(cat pid)`), wait for exit; check `pgrep -f CassandraDaemon` is empty.
7. Wipe `/local/work/node1`, repeat for `S = 32` and `S = 128`.
8. Run the positive control (`S = 8`, `commitlog_total_space: 64MiB`, small memtable so flushes happen) and record `du -sb` over time.

**B3f. Predictions.**
- Every `CommitLog-*.log` has size exactly `S × 1048576` bytes while it is live (mmap pre-sizes the file, `MemoryMappedSegment.java:62`), and none is larger, for each `S`.
- The count of files grows roughly as workload bytes divided by `S`: at least `ceil(600 MiB / S)` rollovers if nothing is reclaimed (about 75, 19 and 5 for 8, 32 and 128). Files may be fewer if flushes reclaim some.
- The largest observed single file is 8, 32, 128 MiB respectively: ratio 1 : 4 : 16.
- Total directory size is **not** predicted to equal `S`. It is expected to be a multiple of `S` (roughly the count of un-reclaimed segments plus one pre-allocated spare).
- Positive control: with `commitlog_total_space = 64MiB` and `S = 8`, directory size is expected to stay near 64 MiB plus about two segments (up to ~80 MiB), while the uncontrolled `S = 8` run grows well beyond 64 MiB. This shows the total is governed by the other knob and the workload is capable of moving usage.
- What would show the claim wrong: any file larger than `S` MiB, or a max file size that does not scale 1 : 4 : 16.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Max file = `S` MiB in all three runs | Claim supported at the real resource: per-file disk is capped by the knob. |
| Any file > `S` MiB | Claim refuted. |
| Max file same across `S` | The knob is not applied (config not loaded, or wrong yaml); check the startup log line with the value, rerun. |
| Directory total > `S` | Expected; shows the segment size does not cap the directory. Not a refutation. |
| Control directory total ≈ 64 MiB + spare, uncontrolled run larger | The workload reaches limits; control valid. |
| Control directory total unchanged vs uncontrolled run | Workload too small or memtable flushes not happening; not confirmed, redo with a larger workload. |

**B3h. Controls.**
- Positive control above (`commitlog_total_space`).
- A run with `commitlog_compression: LZ4Compressor` (with `commitlog_disk_access_mode: standard`) at `S = 32` to show the plaintext cap does not become a file-size cap in that mode: file sizes should be ≤ `S` and, for compressible values (e.g. a repeated byte), much smaller.
- Idle baseline: node started without the workload, to see the files that exist at rest (one pre-built segment plus the active one).

**B4. Risks and cleanup.**
- Disk: worst case about `ceil(600 MiB / S)` segments × `S`, i.e. ~600 MiB to ~1 GiB per run; the 4096 MiB total-space setting is a ceiling. Keep everything under `/local/work/` on local disk with at least 20 GiB free; check with `df -h /local/work` before each run.
- Never build in or write to the shared source tree.
- Processes: after each run, `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` must return nothing; kill and re-check if not.
- Remove `/local/work/node1`, `/local/work/c509*` and the scratch commit log directories when done. The unit-tier test leaves its commit log files in the scratch directory; delete it.

## C. Sources read

- `/users/jason92/writeup-A/playbook-autonomous.md`
- `/users/jason92/writeup-A/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java`
- `src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java`
- `src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerStandard.java`
- `src/java/org/apache/cassandra/db/commitlog/MemoryMappedSegment.java`
- `src/java/org/apache/cassandra/db/commitlog/CompressedSegment.java`
- `src/java/org/apache/cassandra/db/commitlog/FileDirectSegment.java`
- `src/java/org/apache/cassandra/db/commitlog/CommitLog.java`
- `src/java/org/apache/cassandra/config/Config.java`
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java`
- `src/java/org/apache/cassandra/db/Mutation.java`
- `conf/cassandra.yaml`
- Grep results (line references only) over `src/java` and a file listing of `test/unit/org/apache/cassandra/db/commitlog/`

## D. Stage-4 feedback

**2026-10-23, stage 4 (pc12, one run per tier, no run 2).** Results: [`results/commitlog_segment_size-allocate-endOfBuffer--autonomous.md`](../../stage4-runtime-verification/results/commitlog_segment_size-allocate-endOfBuffer--autonomous.md). Case-file version: sha256 `90bef1e6a2eb1ed36cc8773149cffff99c211f59b150897dfba7ef395216d071` (after the audit's B2i amendments; the file is untracked, so no commit holds it).

- **Verdict:** unit **Confirmed — caps**; cluster **Confirmed — caps**. **Outcome class: true positive** (estimate `positive`, effect `caps`). The estimate stands: no segment reserved a byte at or beyond `commitlog_segment_size` in 88 unit segments and every cluster sample; the largest live file was exactly S (8, 32, 128 MiB, ratio 1 : 4 : 16); the exact-edge probe confirmed the `>=` at `CommitLogSegment.java:246` (an entry ending at `capacity - 1` is accepted, one ending at `capacity` is refused).
- **Amended before run 1 (B2i, 2026-10-23):** the knob is set by yaml, not the test setter (max_mutation_size and `IMutation.MAX_MUTATION_SIZE`); a retired segment's maximum offset is its `endOfBuffer`; the compressed-mode file length is **not** capped by S (LZ4 expansion: observed up to 1.0039 × S in the unit tier, 6 of 8 segments at S = 32), so the A2/A3 wording "the segment size bounds the file" holds for mmap and direct, and for compressed modes holds for the plaintext offset only; an exact-edge probe was added.
- **Wording to fix in stage 3:** (1) B2g's "Rollover count does not grow as S shrinks → not confirmed" contradicts B2c, which scales the adds with S (about 3 rollovers at every S); the limit-reached evidence should be the retired-segment states, not a growing count. (2) B3f's control prediction "up to about 80 MiB" was too tight: with S = 8 and `commitlog_total_space` 64 MiB the live directory peaked at 128 MiB (88 MiB by the JMX gauge), a 2 × overshoot of the soft total by a 40 MB/s writer. This is the already-known soft nature of `commitlog_total_space`, not a defect of the per-segment cap. (3) The `OversizedMutations` MBean name in B3d was not found on the node.
- **Bypass/Target-3 note:** none for the per-segment cap. The directory-level footprint is bounded only by `commitlog_total_space` (reactive, overshoots) and was 672 to 896 MiB at 8 to 128 MiB segments with the total set to 4096 MiB.
