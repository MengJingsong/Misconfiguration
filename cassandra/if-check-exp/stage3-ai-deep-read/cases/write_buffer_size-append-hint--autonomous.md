# WRITE_BUFFER_SIZE — verification solution  <!-- file: cases/write_buffer_size-append-hint--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`src/java/org/apache/cassandra/hints/HintsWriter.java:214`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriter.java#L214) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the 256 KiB constant sizes one fixed direct buffer that is allocated once, so it is not a cap on any quantity that grows with load; hint bytes larger than the remaining space bypass it, and the hint-memory and hint-disk quantities that do grow are bounded elsewhere. |
| Ground | `WRITE_BUFFER_SIZE` fixes the capacity of one buffer (`HintsWriteExecutor.java:60`). Total direct memory it accounts for is constant (256 KiB) regardless of hint volume, so node memory usage cannot "follow" it as a limit. Line 214 only chooses between copying into the buffer and writing straight to the channel (`HintsWriter.java:214-221`); both paths write every byte, so disk usage is unaffected. The memory-significant hint object is the `HintsBuffer` slab (min 32 MiB), sized by `max_mutation_size` (`HintsService.java:79,110`), and the disk-significant limits are `max_hints_file_size` and `max_hints_size_per_host`. |

## A. Constraint trace

**A1. The constraint.** `HintsWriteExecutor.WRITE_BUFFER_SIZE`; kind: compile-time constant (not a yaml key, `-D` property, JMX attribute or runtime-queried value). First declared at [`src/java/org/apache/cassandra/hints/HintsWriteExecutor.java:50`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriteExecutor.java#L50) as `static final int WRITE_BUFFER_SIZE = 256 << 10;`. Unit: bytes. Default (and only) value 262144 B = 256 KiB, the literal shift expression, derived from nothing else. Not settable at runtime or by configuration; changing it needs a source edit and a rebuild/restart. A grep of the `hints` package finds only two uses: the declaration (line 50) and the allocation (line 60). The earlier trace's claims were re-checked against these lines and hold, with one correction: the earlier trace cites `HintsWriter.java:136` and `:179` correctly, but its description of line 214 as "the check" omits that line 205 (`hint.remaining() > buffer.remaining()`) is the flush-first check and line 214 is the second, "fits" check.

**A2. What it caps.** Off-heap (direct) memory, and only the size of one reused aggregation buffer: `ByteBuffer.allocateDirect(WRITE_BUFFER_SIZE)` at `HintsWriteExecutor.java:60`, held in the final field `writeBuffer` (line 54) for the life of the `HintsWriteExecutor`. The quantity compared at line 214 is `hint.remaining()` (serialized hint plus 12 bytes of entry overhead, `HintsBuffer.java:58`) against `buffer.remaining()` (free space in the aggregation buffer, at most 262144). It does not cap total hint memory, hint bytes on disk or hint size.

**A3. Mechanism.**
1. `HintsService` builds `HintsWriteExecutor` (`HintsService.java:107`), whose constructor allocates the single direct buffer (`HintsWriteExecutor.java:60`).
2. For each flush, `flushInternal` opens `writer.newSession(writeBuffer)` (`HintsWriteExecutor.java:241`); `HintsWriter.newSession` (`HintsWriter.java:136`) builds a `Session` whose constructor calls `buffer.clear()` and stores the buffer (`HintsWriter.java:176-180`). The same buffer is therefore shared by every host's writer in turn (class comment, `HintsWriter.java:163-166`).
3. `Session.append(ByteBuffer hint)` (`HintsWriter.java:200`) adds `hint.remaining()` to `bytesWritten` first (line 202), so position accounting is independent of which path is taken.
4. Line 205: if the hint does not fit in the free space, the buffer is flipped, written to the channel (`writeBuffer`, line 157) and cleared (lines 207-209).
5. Line 214 (target): if the hint now fits (`hint.remaining() <= buffer.remaining()`), it is copied into the buffer (line 216). Otherwise (hint larger than the whole 256 KiB buffer) it is written straight to the channel (line 220), with no copy and no extra allocation.
6. `Session.close()` flushes any remaining buffered bytes (`flushBuffer`, `HintsWriter.java:277-286`, then `maybeFsync`).
Outcomes: fits means a memory copy, later one channel write; does not fit means a direct channel write. No outcome rejects, drops or errors a hint. Bypass: any hint with serialized size above 262144 B takes the direct write path. Overshoot: none possible for the buffer itself, as it is fixed-size.
Hint size is limited elsewhere: `HintsBuffer` rejects an entry whose total size exceeds half its slab (`HintsBuffer.java:152`), and the slab size is `max(2 * max_mutation_size, 32 MiB)` (`HintsService.java:79,110`), where `max_mutation_size` defaults to `commitlog_segment_size / 2` (`DatabaseDescriptor.java:898-899`). A hint can therefore be up to about 16 MiB by default, i.e. far above 256 KiB, so the bypass at line 220 is reachable on defaults.
Hint file size is limited by `max_hints_file_size` (default 128 MiB, `Config.java:447`), checked after each append (`HintsWriteExecutor.java:239,247`), so a file can overshoot it by up to one hint plus nothing from this buffer's size. Per-host disk is limited by `max_hints_size_per_host` (`Config.java:448`, enforced when deciding to hint, `StorageProxy.java:2488-2496`).


The check itself is the if statement at [`src/java/org/apache/cassandra/hints/HintsWriter.java:214`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriter.java#L214).

**A4. Other consumers.** Off-heap: the `HintsBuffer` slab(s) from `ByteBuffer.allocateDirect(slabSize)` (`HintsBuffer.java:77`) of at least 32 MiB each, with a pool that can hold more than one while a flush is in progress (`HintsBufferPool.java`); hint dispatch reads (`ChecksummedDataInput`, `ChecksummedDataInput.java:56`, using `RandomAccessReader.DEFAULT_BUFFER_SIZE`); the chunk cache, memtable off-heap (if configured), commit log, networking buffers, NIO direct-memory limit shared by all of these. Heap: the hint-serialization objects, `Hint`/`Mutation` copies created by `HintsService.write`. Disk: hint files themselves (every byte of every hint, whichever path line 214 takes), commit log, sstables.

**A5. Evidence beyond the source.** Cassandra docs, hints configuration (`max_hints_file_size`, `max_hints_size_per_host`, `hints_flush_period`): https://cassandra.apache.org/doc/5.0/cassandra/managing/configuration/cass_yaml_file.html (relied on only for the existence and meaning of these keys). `conf/cassandra.yaml:106,111` in the pinned tree documents the same keys. JDK `BufferPoolMXBean` / `java.nio:type=BufferPool,name=direct` and NMT (`-XX:NativeMemoryTracking`) documentation for the instruments. Otherwise none.

## B. Verification solution

**B1. Claim under test.** Node memory and disk usage do not follow `WRITE_BUFFER_SIZE`: with the same hint workload, changing the constant (e.g. 64 KiB, 256 KiB, 1 MiB) changes the aggregation buffer's own capacity by exactly that amount and nothing else that grows with load, and hint bytes on disk are identical in every case, including for hints larger than the buffer, which are written straight to the channel. The positive control is `max_mutation_size`/`commitlog_segment_size`, which does move hint off-heap memory (the `HintsBuffer` slab).

**Audit amendments (stage 4 step 0, 2026-10-28).** Made before any run or reading; each leaves B1, the predictions and the other readings rows as filed except where it says it corrects a number or adds a row (results file §1.1 gives the reason for each).
- R1 (B2c, B2e): the count per cell is min(20000, ceil(256 MiB / (hint size + 12))): the filed formula gives 2 GiB for the 2 MiB and 300 KiB cells (against the "few hundred MiB" it names), 36 cells of it. Entries are opaque direct `ByteBuffer`s of hint size + 12 bytes (the production shape: `flushInternal` passes direct slices of the slab). Channel writes are counted through a counting subclass of `HintsWriter` (it overrides the protected `writeBuffer`, `HintsWriter.java:157`), not a Mockito spy. The file's bytes are checked by CRC against the expected header + count copies. The direct pool is read at three points per cell (entry and writer present; aggregation buffer allocated; after the appends and close).
- R2 (B3f): the 400 KiB sentence corrected: a 400 KiB hint is above the 64 KiB and 256 KiB buffers but fits the 1 MiB one (400 KiB + 12 < 1 MiB). Source arithmetic, independent of readings.
- R3 (B3e step 4): volume instead of wall-clock, see B3e step 4. Each build x payload arm is run twice (B3h), the order shuffled with a fixed seed, A restarted before every arm (the previous case's lesson: `truncatehints` does not delete the open file). The controls run once each on the 256 KiB build with the 1 KiB workload, `commitlog_segment_size` 128MiB (its default `max_mutation_size` is 64 MiB, so the slab is 128 MiB: `DatabaseDescriptor.java:898-899`, `HintsService.java:110`) and `max_hints_size_per_host` 64MiB (set in the yaml). B3d: the heap is read by JMX every second instead of `jstat -gc` (same quantity); NMT before and after each arm.
- R4 (B3g): a row is added for a pool total that moves by whole slabs (the previous closed case, `WRITE_BUFFER_SIZE-append-remaining`, saw 1 to 3 slabs of 32 MiB under natural load, 72 to 153 MiB); derived from that case's source reading, not from any reading of this file. The existing "not distinguishable" row now says when it applies.
- R5 (B3b): `commitlog_segment_size` 128MiB makes up to three slabs of 128 MiB (384 MiB) against `MaxDirectMemorySize=1G`; B4 already notes this.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /local/work/c509/`; never build in the shared tree). `cd /local/work/c509 && ant jar` (or `ant build-test`). Put a small JUnit test (e.g. `test/unit/org/apache/cassandra/hints/WriteBufferProbeTest.java`, in package `org.apache.cassandra.hints` so package-private `HintsWriter`, `HintsWriteExecutor` and `Session` are visible) in the copy. Run with `ant testsome -Dtest.name=org.apache.cassandra.hints.WriteBufferProbeTest` or a plain `java -cp build/classes/main:build/test/classes:lib/*` run. JVM options: `-Xmx512m -XX:MaxDirectMemorySize=1g`.

**B2b. Knobs.** (1) Size of the aggregation `ByteBuffer` passed to `newSession`: the test allocates its own direct buffer of 64 KiB, 256 KiB (the real `HintsWriteExecutor.WRITE_BUFFER_SIZE`) and 1 MiB, standing in for the constant, because it cannot be set otherwise (the test also asserts `HintsWriteExecutor.WRITE_BUFFER_SIZE == 262144`). (2) Hint size: 1 KiB, 100 KiB, 300 KiB (above 256 KiB, below 1 MiB) and 2 MiB (above all buffers). (3) Positive control knob: slab size passed to `HintsBuffer.create(slabSize)`: 32 MiB vs 64 MiB.

**B2c. Workload.** Create a `HintsWriter` in a temp directory on local disk (`HintsDescriptor` + `HintsWriter.create`, as in existing hints tests). For each (buffer size, hint size) pair, build N serialized hint `ByteBuffer`s (hint body plus 12 bytes overhead; bodies need not be valid hints because `append(ByteBuffer)` at `HintsWriter.java:200` treats them as opaque bytes) and call `session.append(...)` for each, N = min(20000, ceil(256 MiB / (hint size + 12))) so the total is at most 256 MiB per cell (amended 2026-10-28, R1; was "2 GiB / hint size capped at 20000"). Arithmetic: with buffer B and hint size h <= B, a channel write happens about every floor(B/h) hints; with h > B, every append writes straight to the channel (line 220) and also triggers a flush of any buffered bytes first (line 205).

**B2d. Observables and instruments.** (a) Wrap the `FileChannel` or count calls to `writeBuffer` with a subclass/spy (`HintsWriter.writeBuffer` is `protected`, `HintsWriter.java:157`, so a test subclass or Mockito spy can count calls and bytes per call). (b) `buffer.position()`/`capacity()` of the passed buffer after each append. (c) `session.getBytesWritten()` (`HintsWriter.java:182-185`) and file length after `close()`. (d) `BufferPoolMXBean` "direct" `getMemoryUsed()` before and after the run, and `Runtime` heap used after `System.gc()`. Not observable directly: kernel page cache.

**B2e. Procedure.**
1. Build as in B2a.
2. Baseline: read the direct-pool `getMemoryUsed()`, heap used.
3. For each buffer size and hint size: allocate the direct buffer, open writer, open session on it, append N hints, close session, record (b)-(d) and the file length, delete the file, release the buffer (null it, `System.gc()`).
4. Control run: allocate `HintsBuffer.create(32 MiB)` and `create(64 MiB)`, record the direct-pool delta, release.
5. Repeat each cell three times (3 repetitions, each in the same JVM, files deleted between cells).

**B2f. Predictions.** (stated before running)
- File length after close equals the sum of appended hint bytes (including 12-byte overhead) for every cell; identical across the three buffer sizes.
- Direct-pool delta during a cell equals the buffer's capacity (65536, 262144, 1048576) and does not grow with N or hint size, including for 2 MiB hints (no allocation on the bypass path).
- Number of channel writes: for h = 1 KiB about total/B; for h = 300 KiB and B = 256 KiB, one write per hint; for h = 2 MiB, one write per hint for every B. Buffer position after any append is <= B.
- Control: direct-pool delta of `HintsBuffer.create(32 MiB)` is 33554432 and of 64 MiB is 67108864.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| File length identical across buffer sizes; direct delta = buffer capacity only; flat as N and h grow | Claim confirmed: the constant sizes one fixed buffer and does not bound usage that grows with load |
| Direct delta grows with N or with h above B (e.g. an allocation for oversized hints) | Claim refuted: the buffer or a hint-sized allocation scales with workload |
| File length differs by buffer size (bytes lost or added) | Claim refuted on disk, and a bug in the append path to be reported |
| Control slab delta moves by 32 MiB between settings while the aggregation buffer delta is flat | Positive control works; the comparison is valid |
| Control slab delta does not move, or the 2 MiB hints never occurred (spy shows no direct writes) | Not confirmed: limit not reached or control failed; redo |

**B2h. Controls.** Positive control: `HintsBuffer` slab size (step 4). Hint sizes both below and above B show both branches of line 214. Run with the direct-memory counter read before any other allocation, with GC forced, so a leftover buffer is not attributed to a later cell. Same JVM, same temp directory, files deleted between cells.

### B3. Cluster tier

**B3a. Environment and build.** One node is enough (hints are stored for a down peer), but use two nodes so a real peer can go down: node1 (under test) and node2 (to be stopped), each on local disk of known size (>= 20 GiB free), JDK 11. Copy the tag to local disk and build three variants from copies of the tree, each with a one-line edit of `HintsWriteExecutor.java:50`: `64 << 10`, `256 << 10` (unmodified) and `1024 << 10`; `ant jar` in each. Node1 JVM options (`conf/jvm11-server.options` or `JVM_EXTRA_OPTS`): `-Xms2G -Xmx2G -XX:MaxDirectMemorySize=1G -XX:NativeMemoryTracking=summary`. Config on node1: `hints_directory` and `data_file_directories` on separate local directories, `max_hints_file_size: 128MiB`, `max_hints_size_per_host: 0MiB` (disabled), `max_hint_window: 3h`, `hints_flush_period: 1000ms`, `trickle_fsync: false`, JMX on localhost.

**B3b. Knobs.** (1) The constant: three builds (64 KiB, 256 KiB, 1 MiB). (2) Mutation (hint) value size: 1 KiB and 400 KiB (above 256 KiB, below default `max_mutation_size` of 16 MiB). (3) Positive control, memory: `commitlog_segment_size` 32MiB (default) vs 128MiB on the 256 KiB build (raises the default `max_mutation_size` to 64 MiB through `DatabaseDescriptor.java:899`, so the hint slab becomes `2 * 64 MiB` = 128 MiB, `HintsService.java:110`). (4) Positive control, disk: `max_hints_size_per_host: 64MiB` on the 256 KiB build, which stops new hints after the stored size passes it (`StorageProxy.java:2488-2496`).

**B3c. Workload.** Keyspace with RF=2 on both nodes, table with one blob column. Stop node2 (`nodetool drain; kill` then confirm `nodetool status` shows DN) so every write from node1 at CL ONE creates a hint. Use `cassandra-stress` (or a CQL loop) to write 1 GiB of payload to node1: 1,000,000 rows of 1 KiB, or 2,500 rows of 400 KiB. Hints are written with every mutation, so about 1 GiB of hint bytes is generated (plus 12 bytes per hint). Hold the volume, not the wall-clock length, the same on each run (amended 2026-10-28, R3: a fixed time would give builds a different hint volume), then wait for at least two flush periods. Duration about 10 minutes per run.

**B3d. Observables and instruments.** (a) Direct memory: JMX `java.nio:type=BufferPool,name=direct` `MemoryUsed` and `Count`, sampled every 5 s with `jcmd`/`jmxterm`; `jcmd <pid> VM.native_memory summary` (NMT categories "Other"/"Internal" hold direct buffers) at start and end. (b) Heap: `jstat -gc <pid> 5000`. (c) Disk: `du -sb <hints_directory>` every 10 s, and file count; `nodetool` hints metrics (`org.apache.cassandra.metrics:type=Hints`). (d) RSS from `/proc/<pid>/status` (VmRSS). Not observable: the aggregation buffer alone (it is one of several direct buffers); the difference between builds is the signal, a 192 KiB or 768 KiB step against slabs of tens of MiB, so use the pool `Count`/`MemoryUsed` after the first flush and compare with the unmodified build.

**B3e. Procedure.**
1. Build the three variants and the config for B3a; start node2 and node1, create schema, check `nodetool status` shows UN UN.
2. Record baseline direct pool, RSS, NMT summary on node1 after 2 minutes idle.
3. Stop node2; confirm DN.
4. Run the 1 KiB workload for the fixed duration; sample all instruments throughout; after it, wait 3 flush periods and sample again; stop the writes.
5. Stop node1; record `du -sb` of the hints directory and the NMT summary taken before stopping; delete the data and hints directories.
6. Repeat 2-5 with the 400 KiB workload.
7. Repeat for each of the three builds (same config, fresh directories).
8. Positive control runs: 256 KiB build with `commitlog_segment_size: 128MiB` (memory control), and with `max_hints_size_per_host: 64MiB` (disk control), using the 1 KiB workload.
9. Stop every process (`jps`, `pgrep -f CassandraDaemon`) and confirm none remain.

**B3f. Predictions.** (before any run)
- Across the 64 KiB, 256 KiB and 1 MiB builds, with the same workload: hints directory size (`du -sb`) is the same within the noise of one `max_hints_file_size` file boundary, and equals about total hint bytes written; direct pool `MemoryUsed` after the first flush differs by roughly the difference in constants (192 KiB and 768 KiB) and no more; it does not grow during the run after the slabs exist; heap series show no trend related to the build.
- For the 400 KiB workload the same holds: hints larger than the build's buffer (the 64 KiB and 256 KiB builds; amended 2026-10-28, R2: at the 1 MiB build a 400 KiB hint fits in the buffer) go straight to the channel, with no growth in the direct pool.
- Memory control: with `commitlog_segment_size: 128MiB` the direct pool `MemoryUsed` rises by about 96 MiB or more over the default (slab 128 MiB against 32 MiB), an effect hundreds of times larger than any build difference.
- Disk control: hints directory size plateaus near 64 MiB (plus overshoot of in-flight buffers) instead of reaching about 1 GiB, and hints metrics show new hints refused.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Hints directory size and heap equal across builds; direct pool differs by only the constant's difference (<= 768 KiB) and is flat in time; controls move by tens of MiB or plateau | Claim confirmed: usage does not follow `WRITE_BUFFER_SIZE` |
| Hints directory size or direct pool grows with the constant by more than its own capacity difference, or grows in time with load | Claim refuted: usage follows the constant |
| Memory control does not raise the direct pool, or disk control does not plateau | Control failed; result not confirmed |
| Hint sizes never reach the bypass (no 400 KiB hints accepted, e.g. write rejected for size) or no hints are created (node2 not DN) | Limit not reached; not confirmed |
| Build differences are below sampler noise, and the Byteman create trace and the traced buffer capacity cannot explain the pool total | Not distinguishable: only the unit tier's exact byte accounting supports the claim |
| Direct pool peaks differ across builds by more than the constants' difference, but the excess equals the difference in the number of slabs created (Byteman create trace) times the slab size, to within 2 MiB, and each build's traced buffer capacity is its constant; hint disk equal across builds (added 2026-10-28, R4) | Claim confirmed on attributable memory: the pool total cannot resolve a 192 KiB or 768 KiB step against whole-slab steps, and the slab count, not the constant, explains it |

**B3h. Controls.** Positive controls: `commitlog_segment_size` (memory) and `max_hints_size_per_host` (disk), which are caps known to bind. Unmodified 256 KiB build as the reference; identical config, schema, payload, duration and fresh directories for each run; node2 down for the whole run so hint generation is constant; run order randomized; repeat each build twice to estimate noise; confirm each build's constant by `javap -constants -p -cp build/classes/main org.apache.cassandra.hints.HintsWriteExecutor`.

**B4. Risks and cleanup.** Disk: about 1 GiB of hints plus data per run on local disk; the disk control caps itself; keep `hints_directory` and data on a local volume with at least 20 GiB free, never on shared storage; delete directories after each run. Processes: stop node1 and node2, check with `jps` and `pgrep -f CassandraDaemon`; kill any `cassandra-stress` or `jmxterm` left. Memory: `-Xmx2G` and `MaxDirectMemorySize=1G` per node; the 128 MiB commit-log control needs about 128 MiB slab plus a second during flush, still below the 1 GiB limit. Source: only edit copies; the shared tree and `~/cassandra-5.0.9` are never modified. Unit tier: temp files under local disk, deleted after each cell; no processes left.

## C. Sources read

- `/tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/INSTRUCTIONS.md`
- `.../agent-docs/playbook-autonomous.md`
- `.../agent-docs/_TEMPLATE-autonomous.md`
- `.../agent-in/89.md`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriter.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriteExecutor.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java` (lines 79, 100-125)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBuffer.java` (lines 40-80, grep for 141-190)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java` (grep)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java` (grep, lines 443-458)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (lines 898-901, 2827, 3718)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java` (lines 2480-2500)
- `/users/jason92/cassandra-5.0.9/conf/cassandra.yaml` (grep)
- https://cassandra.apache.org/doc/5.0/cassandra/managing/configuration/cass_yaml_file.html (cited, not fetched)

## D. Stage-4 feedback

**2026-10-28 — closed, unit Confirmed, cluster Confirmed, does not cap; outcome class true negative** ([results](../../stage4-runtime-verification/results/write_buffer_size-append-hint--autonomous.md)). Audit amendments R1-R5 made before run 1 (block at the head of section B; frozen sha256 recorded in the results file). Unit (36 cells, 333 checks, 0 mismatches): file length identical across the 64 KiB / 256 KiB / 1 MiB buffers for each hint size, direct-pool delta exactly N and zero growth over up to 256 MiB of appends including 2 MiB hints written through, `HintsBuffer.create` 32 vs 64 MiB moves the pool by exactly 33,554,432 vs 67,108,864 B. Cluster (1 GiB per arm, builds 64 KiB / 256 KiB / 1 MiB x 1 KiB / 400 KiB x 2 reps): hint disk byte-identical across builds (1,146,093,946 B and 1,073,745,406 B), the idle baseline and NMT differ by exactly the constants' difference (-196,608 / +786,432 B), pool peaks at 1 KiB within 0.07 MiB of it and at 400 KiB within 2 MiB (slab counts equal), the 1 MiB build does not bypass at 400 KiB (as amended); `commitlog_segment_size` 128MiB made 128 MiB slabs and the pool +192 MiB, `max_hints_size_per_host` 64MiB held disk at 68.6 MiB against 1,093 MiB. Notes for stage 3: B2c's count formula and B3e step 4's wall-clock were inconsistent (amended); `Session.append` calls `writeBuffer` on an empty buffer before every oversized entry; the pool total moves by whole slabs and rises with payload at every build, so only the baseline, NMT and the unit tier resolve a sub-MiB step.
