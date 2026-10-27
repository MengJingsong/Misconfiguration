# hints_write_buffer_size — verification solution  <!-- file: cases/hints_write_buffer_size-append-hint_remaining--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`src/java/org/apache/cassandra/hints/HintsWriter.java:205`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriter.java#L205) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`. The constant `HintsWriteExecutor.WRITE_BUFFER_SIZE` does fix the size of the one shared write-aggregation buffer, but that buffer is a small fixed object that does not grow with hint volume and does not limit what is hinted. The memory- and disk-significant hint objects are bounded by other settings. |
| Ground | The check at `HintsWriter.java:205` only decides when to flush a batch to the file channel, and an oversized hint is written straight through (`HintsWriter.java:220`). Hint memory comes from the `HintsBuffer` slabs sized by `max_mutation_size` (`HintsService.java:110`), and hint disk from `max_hints_file_size` / `max_hints_size_per_host` (`HintsWriteExecutor.java:239,247`, `StorageProxy.java:2488-2491`). None of these read `WRITE_BUFFER_SIZE`. Total usage should not follow it beyond its own 256 KiB. |

## A. Constraint trace

**A1. The constraint.** `HintsWriteExecutor.WRITE_BUFFER_SIZE`, a hard-coded constant, declared `static final int WRITE_BUFFER_SIZE = 256 << 10;` at [`hints/HintsWriteExecutor.java:50`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriteExecutor.java#L50) (package-private, not a config entry, JVM property or runtime-queried value). Unit: bytes, value 262144 (256 KiB), the literal itself with nothing derived. Its only use in the tree is `ByteBuffer.allocateDirect(WRITE_BUFFER_SIZE)` in the constructor (`HintsWriteExecutor.java:60`; a repo-wide grep finds no other reference). It cannot be set by yaml, `-D` or JMX; changing it means editing the source and rebuilding. The earlier trace's claims were re-checked and hold, including the line numbers 50, 60, 241, 136-140, 205, and the neighbours `max_hints_file_size` (`config/Config.java:446-447`, 128MiB) and `max_hints_size_per_host` (`Config.java:448`, default 0B = disabled). Correction: the Session constructor is at `HintsWriter.java:174` and the oversized-hint branch is `HintsWriter.java:214-221`, as claimed; `Session` itself is declared at line 167.

**A2. What it caps.** Off-heap (direct) memory, one 256 KiB buffer for the whole node: the aggregation buffer that batches serialized hints before a channel write. The quantity compared at line 205 is `hint.remaining()` (serialized hint length plus the 12-byte entry overhead, `HintsBuffer.java:58,141`) against `buffer.remaining()` (free space left in the 256 KiB buffer). It does not cap total hint memory, hint count, or hint disk.

**A3. Mechanism.**
1. `HintsService` builds one `HintsWriteExecutor` (`HintsService.java:107`), which allocates the single direct buffer once (`HintsWriteExecutor.java:60`).
2. A flush (`flush`, `HintsWriteExecutor.java:217-230`) drains a `HintsBuffer` slab host by host and calls `flushInternal`, which opens `writer.newSession(writeBuffer)` (`HintsWriteExecutor.java:241`) and passes every serialized hint to `session.append` (`:245`).
3. `HintsWriter.newSession` (`HintsWriter.java:136-140`) creates `Session`, whose constructor clears the buffer (`:174-181`); all hosts' sessions reuse the same buffer, one at a time because the executor is single-threaded (`HintsWriteExecutor.java:61`).
4. `Session.append(ByteBuffer)` (`HintsWriter.java:200-222`): `bytesWritten += hint.remaining()` first (`:202`). If `hint.remaining() > buffer.remaining()` ([`:205`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriter.java#L205)), the buffer is flipped, written with `writeBuffer`, and cleared (`:207-209`). Then if the hint now fits it is copied in (`:213-216`); otherwise (hint larger than 256 KiB) it is written to the channel directly (`:218-220`) with no copy and no new allocation in the plain writer.
5. Outcomes at the limit: the buffer is flushed, never rejects or drops a hint. `close()` flushes the remainder (`HintsWriter.java:269-275`; `flushBuffer` at `:277-286`).
6. Bypass/overshoot: hints above 256 KiB bypass the buffer. For `CompressedHintsWriter`, `writeBuffer` allocates a per-writer `compressionBuffer` sized from the input (`CompressedHintsWriter.java:48-54`), and `EncryptedHintsWriter.writeBuffer` (`:47`) also allocates scratch from input size, so large hints can create allocations unrelated to the 256 KiB. The file size limit is separate: `flushInternal` ends the session when `session.position() >= maxHintsFileSize` (`HintsWriteExecutor.java:239,247`).

**A4. Other consumers.** Hint ingest memory: `HintsBuffer` slabs are `ByteBuffer.allocateDirect(slabSize)` (`HintsBuffer.java:77`) with `slabSize = max(max_mutation_size*2, 32 MiB)` (`HintsService.java:79,110-111`; `HintsBufferPool.java:133`); a single hint may be up to half the slab (`HintsBuffer.java:150-157`). Default `max_mutation_size` is half of `commitlog_segment_size` (`DatabaseDescriptor.java:898-899`). Also the compression/encryption scratch buffers (A3 item 6), the page cache for hint files, and hint disk (`max_hints_file_size`, `max_hints_size_per_host` enforced in `StorageProxy.shouldHint`, `StorageProxy.java:2488-2491`). All outside this constant.

**A5. Evidence beyond the source.** None relied on beyond source. (The class comment at `HintsWriteExecutor.java:39-44` says the buffer is shared by all writers.)

## B. Verification solution

**B1. Claim under test.** Total off-heap memory and disk used by hint writing do not follow `WRITE_BUFFER_SIZE`: changing the constant changes only the one aggregation buffer by exactly the difference, independent of hint volume, host count or hint size, while the settings that actually bound hint memory/disk (`max_mutation_size`, `max_hints_file_size`, `max_hints_size_per_host`) move usage. It would be refuted if hint-related memory scaled with the constant or with hint load through it, or if hints were rejected/dropped when they exceed it.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $LOCAL/c509/`), `cd $LOCAL/c509 && ant jar` (and `ant build-test` for the test classpath). Put a new JUnit test `org.apache.cassandra.hints.WriteBufferProbeTest` under `test/unit/org/apache/cassandra/hints/` of the copy (package-private access to `HintsWriter.Session`). Run with `ant testsome -Dtest.name=org.apache.cassandra.hints.WriteBufferProbeTest`. Use `DatabaseDescriptor.daemonInitialization()`, a temp hints dir on local disk, and an uncompressed `HintsDescriptor` (as in the existing `HintsWriterTest` setup).

**B2b. Knobs.** Aggregation buffer capacity passed to `writer.newSession(ByteBuffer.allocateDirect(N))`, N in {64 KiB, 256 KiB (the constant), 1 MiB}; the test supplies N directly because the constant is not settable. Hint size H: {1 KiB, 100 KiB, 255 KiB, 300 KiB, 2 MiB}. Positive control knob: `DatabaseDescriptor.setMaxHintsSizePerHostInMiB` is not on this path, so the control is the file-size stop in `HintsWriteExecutor.flushInternal` (B2h).

**B2c. Workload.** For each (N, H): build serialized entries as `ByteBuffer` of length H+12 filled with a pattern (the `append(ByteBuffer)` overload does not parse content, `HintsWriter.java:200-222`), append K entries with K = ceil(2.5*N/(H+12)) (at least 3) so the buffer overflows at least twice; for H > N use K = 3.

**B2d. Observables and instruments.** After each `append`: `session.getBytesWritten()` (`HintsWriter.java:184`), `writer.getFile().length()` (grows only when `channel.write` runs, so it shows each flush or write-through), the buffer's `position()/remaining()` read from the test's own handle, and the count of heap allocations is not measured directly. Cannot be observed: the JVM's total direct memory is not what this tier measures (cluster tier does).

**B2e. Procedure.** 1) Build. 2) For each N, create a writer and session. 3) For each H append K entries, recording the tuple (bytesWritten, file length, buffer position) after each. 4) Close the session and confirm final file length equals total bytes appended. 5) Delete temp dir.

**B2f. Predictions (before any run).** For H+12 <= N: file length stays 0 until cumulative bytes first exceed N, then jumps to the amount buffered before the overflowing entry, never exceeding N-ish per jump; buffer position never exceeds N. For H+12 > N: each append leaves the file length growing by exactly H+12 and the buffer position unchanged (write-through at `HintsWriter.java:218-220`), with no exception and no loss. At close, file length equals the sum of all entries for every N and H. The flush threshold scales with N exactly; the amount of data lost or refused is 0.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Flush points move with N exactly as predicted; oversized hints pass through; every byte arrives | Mechanism as traced: N bounds only the batching buffer (claim confirmed at unit level) |
| Appends throw or bytes are dropped when H+12 > N | Buffer acts as a hint size limit: claim refuted |
| Buffer position exceeds N | Source misread, claim not confirmed |
| File length grows on every append for small H | Buffer not batching; trace wrong |
| Positive control (B2h) file-size stop does not trigger | Control failed, run not confirmed |

**B2h. Controls.** Positive control: call `Session.append` in a loop mimicking `flushInternal` (`HintsWriteExecutor.java:245-248`) with `maxHintsFileSize` set to 1 MiB; the loop must stop when `session.position() >= 1 MiB` for every N, showing a cap that does bind and does not depend on N. Also run an identical sequence with an N-sized heap `ByteBuffer` to show the result does not depend on direct vs heap.

### B3. Cluster tier

**B3a. Environment and build.** Two nodes on local disk of a Linux host (node1 receives writes and writes hints; node2 is stopped to force hints), JDK 11, Ant, built from local copies. Three builds of node1: A = stock (256 KiB), B = `WRITE_BUFFER_SIZE = 64 << 10`, C = `WRITE_BUFFER_SIZE = 4 << 20` (edit `HintsWriteExecutor.java:50` in a copy, `ant jar`). node1 JVM: `-Xms2G -Xmx2G -XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=1G`, `commitlog_directory`, `data_file_directories` and `hints_directory` on local disk with at least 20 GiB free. Defaults otherwise (`hints_flush_period: 10000ms`, `conf/cassandra.yaml:102`; hints enabled; `hints_compression` unset; `max_hints_file_size: 128MiB`).

**B3b. Knobs.** (1) `WRITE_BUFFER_SIZE` via builds A/B/C. (2) Positive controls on build A: `max_hints_file_size` {128MiB, 8MiB} (yaml `:106`, restart), `max_hints_size_per_host` {0, 64MiB} (yaml `:111`, or JMX `StorageProxy.setMaxHintsSizePerHostInMiB`), `max_mutation_size` {default 16384KiB, 4096KiB} (restart; changes slab size per `HintsService.java:110`). (3) Load: hint payload size {1 KiB, 200 KiB, 2 MiB}.

**B3c. Workload.** Keyspace with RF=2 on 2 nodes, CL=ONE, `cassandra-stress` or CQL writes to node1 only with node2 down. Rows with blob values of the payload size; volume 6 GiB of hints for the 1 KiB and 200 KiB runs (about 6 million and 30 thousand mutations) and 2 GiB for 2 MiB; set `max_hint_window` to a value longer than the run (default 3h, `conf/cassandra.yaml`, assumed). This is far above 256 KiB, so the aggregation buffer is cycled many thousands of times; duration roughly 10-30 minutes per run.

**B3d. Observables and instruments.** (a) JMX `java.nio:type=BufferPool,name=direct` (Count, MemoryUsed, TotalCapacity) every 5 s; (b) `jcmd <pid> VM.native_memory summary` (Internal/Other categories) before, during, at peak and after; (c) process RSS from `/proc/<pid>/status`; (d) hints directory size (`du -sb`) and file count/size via `ls -l` (hint file sizes); (e) JMX `org.apache.cassandra.metrics:type=Storage,name=TotalHints` and HintsService metrics. Cannot be observed: the identity of which direct buffers belong to the writer; this is inferred by differences between builds A/B/C.

**B3e. Procedure.** 1) Build A, B, C into separate directories. 2) Start both nodes, create keyspace, stop node2. 3) Start sampling. 4) Run the workload for the chosen payload against node1. 5) Record peak direct `MemoryUsed`, NMT, RSS and hints-directory size, then stop the load. 6) Restart node2 and confirm hints are delivered. 7) Stop all processes, wipe data/commitlog/hints, repeat for next build/payload/control. 8) `ps` check that none remain.

**B3f. Predictions (before any run).** Across builds A/B/C at equal workload: peak direct `MemoryUsed` differs by about the constants' difference (-192 KiB for B, +3.75 MiB for C) and is otherwise flat in payload size and hint volume; it is dominated by `HintsBuffer` slabs of max(2*16 MiB, 32 MiB) = 32 MiB each (default), so the build difference is under about 12% of the hint direct total and does not grow over time. Hint disk size and file sizes are identical across A/B/C (file rolls at 128 MiB). 2 MiB hints (larger than every candidate buffer except C) are all stored without error. Positive controls: `max_hints_file_size 8MiB` makes hint files roll at about 8 MiB; `max_hints_size_per_host 64MiB` stops hinting once the directory passes about 64 MiB (so hints dir stays near 64 MiB while the workload continues); `max_mutation_size 32768KiB` with `commitlog_segment_size 64MiB` raises each slab to max(2 x 32 MiB, 32 MiB) = 64 MiB (`HintsService.java:79`, `:110`), so direct memory rises by about 32 MiB per slab; `max_mutation_size 4096KiB` leaves the slab at the 32 MiB floor (2 x 4 MiB is below it) and shows no change.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Direct memory and RSS differ across A/B/C only by about the constants' difference, flat in time and payload; controls move disk/memory as predicted | Claim confirmed: usage does not follow the constant beyond its own buffer |
| Direct memory or RSS grows with the hint volume or payload and scales with the constant (more than its difference) | Claim refuted |
| Hints rejected, dropped or errors when hint exceeds the constant (build B with 200 KiB or 2 MiB hints) | Buffer acts as a limit: refuted |
| Hint disk differs across builds | Refuted (disk follows the constant) |
| Controls (file size, per-host cap, slab size) do not change disk/memory as predicted | Control failed: not confirmed |
| Hints not produced (node2 considered up, window expired) so the writer never ran | Limit never reached: not confirmed |

**B3h. Controls.** Positive control: same workload on build A with the three real caps above, showing usage moves where a cap binds. Baseline: node1 idle with no hints (direct memory without any hint writing). Repeat each build twice for noise. Keep the heap, GC and concurrent compaction constant; disable unrelated load.

**B4. Risks and cleanup.** Unit tier: temp directory under local disk, delete after. Cluster tier: hints can reach several GiB per run, so keep all directories on local disk of known size (20 GiB free minimum) and never on shared storage; use `max_hints_size_per_host` or a short load duration as a stop. Stop both Cassandra processes (`nodetool drain`, then kill), confirm with `ps -u $USER | grep -i cassandra`, delete data, commitlog, hints and build copies. Never build in the shared source tree.

## C. Sources read

- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriteExecutor.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriter.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/hints/CompressedHintsWriter.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/hints/EncryptedHintsWriter.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBuffer.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java` (grep)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java` (grep)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java`
- `/users/jason92/cassandra-5.0.9/conf/cassandra.yaml` (grep)
- `/users/jason92/cassandra-5.0.9/conf/jvm*-server.options` (grep)

## D. Stage-4 feedback

`none yet`
