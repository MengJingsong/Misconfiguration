# hints compression buffer (no dedicated limit; indirectly max_mutation_size) — verification solution  <!-- file: cases/hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/hints/CompressedHintsWriter.java:53` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-25 |
| Estimate | `negative`: the per-writer `compressionBuffer` is sized by the largest buffer ever compressed (plus compressor overhead), and none of the hints disk/size knobs (`max_hints_file_size`, `max_hints_size_per_host`) bounds it. |
| Ground | The check at line 53 is a grow-only capacity test, not a limit: `compressionBuffer` is never shrunk and one is held per open writer (per peer with pending hints). Its only ceiling is the structural maximum hint size (half the HintsBuffer slab, `max(2*max_mutation_size, 32MiB)/2`), which is a size cap on a single hint and is not a cap on total off-heap use (that scales with the number of peers). |

## A. Constraint trace

**A1. The constraint.** There is no constraint declared for this buffer. Line 53 (`compressionBuffer == null || compressionBuffer.capacity() < estimatedSize`) is a grow-only capacity check. The nearest governing quantities are:
- `max_mutation_size` (kind: configuration entry, yaml, restart needed). Declared `Config.java:406-407` (`DataStorageSpec.IntKibibytesBound`), default derived in `DatabaseDescriptor.java:898-899` as `commitlog_segment_size / 2` (32MiB / 2 = 16MiB). Read via `DatabaseDescriptor.getMaxMutationSize()` (`DatabaseDescriptor.java:2827-2830`).
- `HintsService.java:79,110`: `MIN_BUFFER_SIZE = 32<<20`; `bufferSize = max(getMaxMutationSize()*2, 32MiB)` = 32MiB by default; this sizes each `HintsBuffer` slab (`HintsBuffer.java:75-77`, direct).
- `HintsBuffer.java:150-152`: a hint with `totalSize > slab.capacity()/2` is rejected. So the largest hint is about 16MiB by default.
- `max_hints_file_size` (`Config.java:446-447`, default 128MiB) and `max_hints_size_per_host` (`Config.java:448`, default 0 = disabled) limit disk, not this buffer.
- `hints_compression` (`Config.java:450`, `DatabaseDescriptor.java:3723-3731`) is what turns this class on; default unset (yaml line 125 is commented out).

**A2. What it caps.** Nothing directly. The resource is off-heap (direct) memory: `compressor.preferredBufferType().allocate(estimatedSize)` (line 55); LZ4's `preferredBufferType()` is `OFF_HEAP` (`LZ4Compressor.java:240-243`). The compared quantity is `compressionBuffer.capacity()` against `estimatedSize = compressor.initialCompressedBufferLength(originalSize) + 8` (line 51), where `originalSize = bb.remaining()`.

**A3. Mechanism.**
1. `HintsWriter.create` returns a `CompressedHintsWriter` when the descriptor is compressed (`HintsWriter.java:86-89`). `HintsStore.getOrOpenWriter` (`HintsStore.java:295-300`) keeps one writer per peer, held open until `max_hints_file_size` is reached (`HintsWriteExecutor.java:239-248` returns false, then `closeWriter`, `HintsStore.java:325-333`) or until dispatch/shutdown closes it.
2. `HintsWriteExecutor` is a single thread with one shared 256KiB direct `writeBuffer` (`HintsWriteExecutor.java:50,60`). Its class comment (lines 40-45) says a compression buffer would be shared, but in 5.0.9 `compressionBuffer` is a per-instance field (`CompressedHintsWriter.java:39`), so it is per writer.
3. `Session.append(ByteBuffer)` (`HintsWriter.java:200-222`) calls `writeBuffer(buffer)` with the aggregation buffer (at most 256KiB). For a single hint larger than the aggregation buffer, it calls `writeBuffer(hint)` directly (line 220), so `bb.remaining()` can be as large as a hint (up to about 16MiB by default).
4. Line 51 computes `estimatedSize` (LZ4: `4 + maxCompressedLength(n)`, `LZ4Compressor.java:113-116`, about `n + n/255 + 16`, +4 +8). Lines 53-56 allocate only if null or too small, so the capacity is the high-water mark; the old buffer becomes garbage to be freed by direct-buffer cleaner on GC.
5. Compress (line 60), write metadata, hand to `HintsWriter.writeBuffer` (line 68, `HintsWriter.java:157-161`).
- Outcome at the check: true, so allocate a new larger buffer (transient peak = old + new); false, reuse. There is no limit-reached branch, no failure, no shrink.
- Overshoot: the buffer retains the size of the largest hint ever written to that peer's writer, while the file is open (a long time for a down peer with a trickle of hints). Total = sum over peers with open compressed writers.

[Amended 2026-10-25, stage-4 audit (dated, independent of any reading)] Cite and arithmetic audit against `cassandra/cassandra-5.0.9/`: all line cites above hold except `HintsWriter.java:86-89` (the `isCompressed()` branch is lines 88-89; `create` starts at 68) and `HintsStore.java:325-333` (`closeWriter` is 322-330). The per-hint cap is exact and slightly different from "about 16 MiB": `HintsBuffer.allocate` (150-152) tests `hintSize + ENTRY_OVERHEAD_SIZE(12) > slab.capacity()/2`, and the slab is `max(2*max_mutation_size, 32 MiB)` (`HintsService.java:110`), so the cap is `max(max_mutation_size, 16 MiB)` = 16,777,216 B for a whole record (what the writer sees as `bb.remaining()`), i.e. a hint payload of at most 16,777,204 B; it does not fall when `max_mutation_size` is lowered below 16 MiB. Largest possible compression buffer (LZ4, lz4-java `maxCompressedLength(n) = n + n/255 + 16`): n = 16,777,216, n/255 = 65,793, so 4 + (16,777,216 + 65,793 + 16) + 8 = 16,843,037 B = 16.063 MiB (the "about 16,843,000 B, 16.06 MiB" above holds). For 4 MiB: 4,210,780 B; 8 MiB: 8,421,532 B (8.031 MiB); 256 KiB: 263,200 B (0.251 MiB); 1 MiB: 1,052,716 B. When the first hint of a session is larger than the 256 KiB aggregation buffer, `Session.append` first flushes the empty buffer (`HintsWriter.java:205-209`), so `writeBuffer` runs once with `bb.remaining() == 0` and allocates a 28 B buffer (4 + 16 + 8) before the hint-sized one.

**A4. Other consumers.** Hint HintsBuffer slabs (up to `MAX_HINT_BUFFERS`=3, `CassandraRelevantProperties.java:351`, `HintsBufferPool.java:41`) of 32MiB direct each; the shared 256KiB write buffer; the dispatch-side `CompressedChecksummedDataInput` using `BufferPools.forChunkCache()` (`CompressedChecksummedDataInput.java:35,120-138`); chunk cache, memtables, netty direct buffers; the page cache holding the hint files.

**A5. Evidence beyond the source.** `java.nio` direct buffer accounting: JMX `java.nio:type=BufferPool,name=direct` (JDK 11 `BufferPoolMXBean` docs). CASSANDRA-9428 (hints compression) is referenced by the executor comment. Otherwise none.

## B. Verification solution

**B1. Claim under test.** The off-heap compression buffer of a `CompressedHintsWriter` has capacity equal to the largest compressor bound seen (about 1.0x the largest written buffer plus a few tens of bytes, LZ4) and is unaffected by `max_hints_file_size` and `max_hints_size_per_host`; it is capped only by the per-hint size cap, and grows with the number of peers holding open writers.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk: `rsync -a ~/cassandra-5.0.9/ /local/scratch/c509/`; `cd /local/scratch/c509 && ant jar` (or `ant build-test`). Put a JUnit class `CompressedHintsWriterCapTest` in package `org.apache.cassandra.hints` under `test/unit/org/apache/cassandra/hints/` (to reach package-private `HintsWriter.create`, `newSession`). Run with `ant testsome -Dtest.name=org.apache.cassandra.hints.CompressedHintsWriterCapTest`. JVM: default test options plus `-Dcassandra.config=file:///local/scratch/c509/test/conf/cassandra.yaml`. Temp directory under `/local/scratch/hintsut` (local disk).

**B2b. Knobs.** (1) Hint/buffer size S written through one session: 100 B, 200KiB, 256KiB (the aggregation buffer), 1MiB, 4MiB, 16MiB (the cap). (2) `DatabaseDescriptor.setMaxHintsFileSize`-equivalent: set `conf.max_hints_file_size` via reflection/yaml to 1MiB vs 128MiB (not consulted by the writer itself, only by `HintsWriteExecutor`). (3) Compressor: LZ4 (`ParameterizedClass("LZ4Compressor", emptyMap)`) and Deflate (heap vs LZ4 off-heap) to show buffer type. (4) Number of writers N = 1, 4, 16.

**B2c. Workload.** Create `HintsDescriptor(hostId, ts, ImmutableMap.of(HintsDescriptor.COMPRESSION, Map.of("class_name","LZ4Compressor","parameters",Map.of())))`; `HintsWriter.create(dir, desc)`; `try (Session s = w.newSession(ByteBuffer.allocateDirect(256<<10))) { s.append(randomBytes(S)) }`. Random (incompressible) bytes so the compressed size is near the bound. Sequences: S ascending 100B, 1MiB, 16MiB; then descending, to show grow-only. Arithmetic: for S=16MiB, LZ4 bound = 4 + (16777216 + 16777216/255 + 16) + 8 = about 16,843,000 B (about 16.06MiB). For N=16 writers: about 257MiB.

**B2d. Observables and instruments.** `compressionBuffer.capacity()` of each writer by reflection on the private field `CompressedHintsWriter.compressionBuffer`; `BufferPoolMXBean` "direct" `getMemoryUsed()` via `ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)`, before/after, with `System.gc()` after replaced buffers; `compressor.initialCompressedBufferLength(S)` as the expected value. Cannot observe: native allocator overhead.

**B2e. Procedure.**
1. Build as B2a. 2. For each S ascending: new writer, append one S-byte hint, close the session, record `capacity()` and direct-pool used. 3. On the same writer, append the descending S values and record capacity after each (must not shrink). 4. Repeat with `max_hints_file_size`=1MiB and 128MiB. 5. Create N writers each with a 4MiB hint; record the direct-pool delta. 6. Repeat step 2 with uncompressed `HintsWriter` (no compression) as the positive-control/reference: no `compressionBuffer` field, direct delta about 0.

**B2f. Predictions.** Capacity = `4 + S + S/255 + 16 + 8` rounded as `LZ4 maxCompressedLength` (within +/-64 B) when S > 256KiB; for S <= 256KiB the capacity corresponds to the aggregation-buffer size at flush (the writer flushes the 256KiB buffer or the partially filled buffer at close, so about the flushed byte count); non-decreasing across the descending sequence; identical for the two `max_hints_file_size` values; direct delta for N writers is about N x capacity (within 10%); uncompressed writer: delta about 0.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Capacity tracks the compressor bound of the largest S, equal across file-size settings, never shrinks, N-fold sum | Claim confirmed: no cap tied to hint-size knobs |
| Capacity differs with `max_hints_file_size` (1MiB gives smaller) | Claim refuted: file-size knob bounds the buffer |
| Capacity shrinks on descending S | Claim wrong (it is not grow-only) |
| Capacity constant at 256KiB+ regardless of S | Claim wrong: there is an internal cap or chunking |
| S=16MiB works but 17MiB hint is rejected at HintsBuffer (`HintsBuffer.java:152`), not at the writer | Confirms the only ceiling is the per-hint cap |
| Direct pool delta does not move for compressed writers (reading error) | Not confirmed; check reflection/GC and that compression was actually on |
| Positive control: `HintsBuffer.create(32MiB)` vs `max_mutation_size` changed (64MiB gives slab 128MiB) moves direct use by exactly the slab size | Instrument works where a cap binds |

**B2h. Controls.** Uncompressed writer (no buffer); incompressible vs compressible data (capacity unchanged because it is sized by the bound, not the result); GC before reading; same JVM-heap `-Xmx` throughout; one writer at a time except for step 5.

[Amended 2026-10-25, stage-4 audit (dated, independent of any reading)] B2: (1) `S` is the record size seen by `writeBuffer` (the cap is 16,777,216 for a record, 16,777,204 for a hint payload); the 17 MiB row of B2g is tested as `HintsBuffer.create(32 MiB).allocate(16,777,204)` accepted and `allocate(16,777,205)` and `allocate(17 MiB)` throwing `IllegalArgumentException`. (2) The expected capacity is the exact formula 4 + (S + S/255 + 16) + 8 (integer division); the +/-64 B of B2f is kept as the tolerance, and the unit test also checks the exact value and `maxCompressedLength` itself against `n + n/255 + 16`. (3) `max_hints_file_size` is set through `DatabaseDescriptor.getRawConfig()`; the writer does not consult it, so the unit check is a negative-control (identical capacity). (4) Extra checks that do not change B2f/B2g: Deflate's buffer is on-heap (`DeflateCompressor.java:228-231`, `isDirect() == false`), LZ4's is direct (`LZ4Compressor.java:240-243`). (5) Pool deltas use `System.gc()` and a 300 ms wait before each reading, the harness's usual rule.

### B3. Cluster tier

**B3a. Environment and build.** Two nodes on one Linux machine (127.0.0.1 and 127.0.0.2 loopback aliases) or two hosts; JDK 11; build from the local copy (`ant jar`). Node A (observed) `-Xmx2G`, `-XX:MaxDirectMemorySize=2G` left at default behaviour (or set explicitly to avoid conflating); `hinted_handoff_enabled: true`, `hints_compression: [{class_name: LZ4Compressor, parameters: [{}]}]`, `max_hints_window: 3h`, `commitlog_segment_size: 32MiB`, `max_mutation_size` default; `hints_directory`, data and commit log on local disk dirs of at least 20GB (`/local/scratch/nodeA/...`). Enable JMX locally. Node B is the hint target.

**B3b. Knobs.** (1) `hints_compression` LZ4 vs absent (control). (2) `max_hints_file_size`: 1MiB vs 128MiB (default). (3) `max_hints_size_per_host`: 0 vs 1MiB (note: it only stops new hints from being stored, `StorageProxy.java:2488`). (4) Value size V of the blob written: 1KiB, 1MiB, 8MiB (below the 16MiB cap, with rows well under max_mutation_size). (5) Number of down peers: 1 vs 2 (add node C if three nodes are used). Each by yaml, restart node.

**B3c. Workload.** `CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':2}; CREATE TABLE ks.t(k int PRIMARY KEY, v blob);` Stop node B (`nodetool drain` then kill). On node A (coordinator) issue writes at CL ONE: for V=8MiB, `cassandra-stress` user profile or a Python driver loop of 200 inserts of random 8MiB blobs (about 1.6GB of hints; with max_hints_size_per_host=0 all stored) so many hints, each of which has to be written as one oversize record that goes through line 53 directly. Small-V arm: 200000 inserts of 1KiB (about 200MB). Wait 60 s for the periodic flush (`HintsService.java:118`, 10 s) so the writer is open.

**B3d. Observables and instruments.** JMX `java.nio:type=BufferPool,name=direct` MemoryUsed/Count (via `jmxterm` or `jcmd <pid> VM.native_tracking summary` with `-XX:NativeMemoryTracking=summary`, category "Other"); `jcmd <pid> GC.run` before reading; `ps -o rss` of node A; `ls -l` of hints dir (disk size, to confirm the load reached the file size limit); `nodetool statushandoff` / hint metrics `Hints_created`. Cannot observe the capacity of one specific buffer directly in the cluster (only pool totals).

**B3e. Procedure.**
1. Build and start A and B; create schema; record baseline direct pool and RSS (after 2 min idle). 2. Stop B. 3. Run the small-V arm with compression on; sample direct pool every 5 s for 2 min after `GC.run`. 4. Run the V=8MiB arm; sample likewise. 5. Repeat 3-4 with `max_hints_file_size`=1MiB and `max_hints_size_per_host`=1MiB (restart A, new hint dir). 6. Repeat 4 with compression absent (control). 7. Repeat 4 with two peers down (needs C). 8. Positive control: raise `max_mutation_size` (and `commitlog_segment_size` to 128MiB) and see the HintsBuffer slab direct memory (about 3 x 128MiB when all buffers are allocated) move. 9. Stop all processes (`pkill -f CassandraDaemon`, `pgrep -fl Cassandra` shows none) and delete data directories.

**B3f. Predictions.** Compressed, V=8MiB: direct-pool increase over the uncompressed arm of about 8.0-8.1MiB per down peer (one compression buffer, 1x the largest hint plus LZ4 slack), 2 peers about 16MiB; V=1KiB: increase no more than about 0.3MiB. Setting `max_hints_file_size`=1MiB or `max_hints_size_per_host`=1MiB: same compression-buffer increment (it may close/reopen writers, so a new buffer per file, but live total stays about 1 per peer). Uncompressed arm: no increment. Slab positive control: direct pool changes by about 2 x the changed slab size. [Amended 2026-10-25: replaced by item 5 of the B3 amendment below: the pool follows the slab size, `dPool(M128) - dPool(D1)` = `Corr(M128) - Corr(D1)` +/- 8 MiB and that difference >= 64 MiB.]

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Increment about 1 x largest hint x peers, same for both file-size/host-size settings, none uncompressed | Claim confirmed: usage tracks hint size and peers, not the hint-size knobs |
| Increment shrinks when `max_hints_file_size` or `max_hints_size_per_host` is lowered | Claim refuted: those knobs bound it |
| Increment is bounded below 8MiB (e.g. flat at 256KiB) at V=8MiB | Claim wrong: chunking/other cap |
| Increment moves with `max_mutation_size`/slab only | Only the per-hint cap bounds it |
| Increment not seen in compressed vs uncompressed arm, positive control moves | Not confirmed (GC freed, or writer not open); repeat before GC |
| Positive control (slab size via `max_mutation_size`) does not move | Instrument/knob invalid, nothing concluded |
| [Amended 2026-10-25] Positive control moves as item 5 says (difference of pools tracks the difference of slabs created x slab size, >= 64 MiB) | The instrument can show a cap that binds; the flat/following readings of the L lifetimes are meaningful |

**B3h. Controls.** Uncompressed arm; same workload, same JVM options; `GC.run` before every sample; idle baseline; compare to `hints_directory` byte counts to show the workload actually produced hints; a repeat run for noise.

[Amended 2026-10-25, stage-4 audit (dated, independent of any reading)] B3 (audit; all of this is settled before any reading):
1. **Lifetimes.** The compression buffer is grow-only, so the small-V and the 8 MiB workloads cannot share a node lifetime (the first reading after the second would still show the first's high-water mark). One workload per lifetime, node data wiped between: `S` (LZ4, 200,000 x 1 KiB), `US` (same, `hints_compression` absent, the control of `S`), `D1` and `D2` (LZ4, 8 MiB hints; the repeat measures noise), `F1` (`max_hints_file_size: 1MiB`), `H1` (`max_hints_size_per_host: 1MiB`), `U` (8 MiB, compression absent: the control of the L lifetimes), `P2` (8 MiB, two peers down, a third node, RF 3), `M128` (the slab positive control, below). In `H1` the knob stops hints after the first flush has put the host's files above 1 MiB, so only the hints that reached the writer before that count; the buffer still reaches the 8 MiB bound if one 8 MiB hint was flushed, and the trace shows what was written.
2. **Workload sizes.** `L` is 200 inserts of 8 MiB (1.6 GB of mutations; the hints directory reaches about 1.6 GB, `df` checked first), one at a time with 4 in flight, protocol 4 (large native-v5 requests leave direct frame buffers). `write_request_timeout: 30000ms` and `native_transport_timeout: 60000ms` are set in every lifetime so that a slow 8 MiB local apply is not a client timeout; hints are submitted for a down replica before the response either way. Heap stays 2 GiB, `-XX:MaxDirectMemorySize=2g`. The ring: A = 127.0.14.1, B = 127.0.14.2, C = 127.0.14.3 (P2 only); native 9146, storage 7014, A's JMX 7814 (B and C use JMX 7815 and 7816; the assigned 7214 is also used by another agent's node on the host, whose `nodetool drain` reached this harness's A during a shakedown, so these three were changed on 2026-10-25 before any run-1 reading), Byteman listener on A only, port 9114.
3. **Extra instrument (observation only).** A Byteman rule at the exit of `CompressedHintsWriter.writeBuffer` writes the writer's identity, `bb.remaining()` and `compressionBuffer.capacity()`, and one at `HintsWriter.close` writes the closing writer's identity, so the buffer of each writer is read exactly (B3d said it could not be). The pool totals of B3d remain the real-resource reading.
4. **Reading rules (fixed here).** Marks: baseline (after B is seen DN, `GC.run` twice, 10 s), then end of workload + 15 s with `GC.run` twice. Slab correction: `Corr = (sum of `created` sizes in the trace after the baseline)`; the hint-attributable change of an arm is `X = (dPool_arm - Corr_arm) - (dPool_control - Corr_control)`, `dPool` the change of A's java.nio direct `MemoryUsed` from the baseline mark. Band for every "about" in B3f: 2 MiB (an increment of one 8.03 MiB buffer is read as X in [6.03, 10.03] MiB per peer; the S lifetimes read as X <= 0.3 + 2 MiB). "Same increment" between two arms = X within 2 MiB. `F1` also expects, from the trace, more than one writer identity (the knob closes writers) with at most one live at the end.
5. **Positive control (replaces the last sentence of B3f, the last row of B3g and step 8 of B3e, which disagreed: "2 x" against "3 x 128 MiB").** `M128`: `commitlog_segment_size: 128MiB` (so `max_mutation_size` defaults to 64 MiB, slab 128 MiB, the per-hint cap 64 MiB). Reading: `dPool(M128) - dPool(D1)` equals `Corr(M128) - Corr(D1)` within 8 MiB (the pool follows the knob through the slab size), with `Corr(M128) - Corr(D1) >= 64 MiB`. If that fails, nothing is concluded for the L lifetimes (the row "positive control does not move").
6. **Stopping.** Not `pkill -f CassandraDaemon` (shared node): each node is stopped by `nodetool stopdaemon` then by its PID; leftovers are listed. B3e step 9 otherwise stands.

**B4. Risks and cleanup.** Unit tier: temp dir under `/local/scratch/hintsut`, delete after; up to about 260MiB direct memory for N=16 (use `-XX:MaxDirectMemorySize=1G`). Cluster tier: about 1.6GB of hints plus data (local disk, at least 20GB free, check `df`); never use shared storage; don't build in the shared tree; stop all JVMs and confirm with `pgrep -fl CassandraDaemon`; `rm -rf /local/scratch/nodeA /local/scratch/nodeB`; remove loopback aliases.

## C. Sources read

- ~/writeup-A/playbook-autonomous.md
- ~/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/hints/CompressedHintsWriter.java
- src/java/org/apache/cassandra/hints/HintsWriter.java
- src/java/org/apache/cassandra/hints/HintsWriteExecutor.java
- src/java/org/apache/cassandra/hints/HintsStore.java
- src/java/org/apache/cassandra/hints/HintsService.java
- src/java/org/apache/cassandra/hints/HintsBuffer.java (grep)
- src/java/org/apache/cassandra/hints/HintsBufferPool.java (grep)
- src/java/org/apache/cassandra/hints/CompressedChecksummedDataInput.java (grep)
- src/java/org/apache/cassandra/io/compress/LZ4Compressor.java, SnappyCompressor.java, DeflateCompressor.java, ZstdCompressor.java (grep)
- src/java/org/apache/cassandra/config/Config.java, DatabaseDescriptor.java, CassandraRelevantProperties.java (grep)
- src/java/org/apache/cassandra/service/StorageProxy.java (grep)
- conf/cassandra.yaml (grep)

## D. Stage-4 feedback

2026-10-25, stage 4 (results: `stage4-runtime-verification/results/hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous.md`; commits not yet made). Outcome class **true negative**. Unit tier: **Confirmed** (B2g row 1): the compression buffer is exactly `4 + (S + S/255 + 16) + 8` B for S = 100 B ... 16 MiB, never shrinks, N writers hold N times it, identical for `max_hints_file_size` 1 MiB and 128 MiB; the `HintsBuffer` refuses a hint above 16,777,204 B (record 16,777,216 B = half the 32 MiB slab). Cluster tier: the Byteman trace shows 8,421,599 B per writer for 8 MiB hints in every arm (`D1`, `D2`, `F1`, `H1`, `P2`, `M128`), 16.07 MiB for two peers, 0.12 MiB for 1 KiB hints; the slab positive control moved the pool by 192 MiB as predicted. **One sub-prediction missed:** B3f said that with `max_hints_file_size` 1 MiB "live total stays about 1 per peer"; `HintsWriteExecutor.flushInternal` returns false after each 8 MiB hint and `closeWriter()` runs at once (`HintsWriteExecutor.java:228-229,247-248`), so 200 writers each allocated an 8.03 MiB buffer, none was live at the end (post-GC increment 0.01 MiB against 8.04 MiB) and the peak direct delta was 362 MiB (13 writers and 105-136 MiB in the default arms). B3g row 2 as worded ("Increment shrinks ... Claim refuted") matches that reading; the case's substance (no hints size knob bounds the buffer's size) is not affected. Estimate left as filed. Audit corrections to the write-up: `HintsWriter.java:86-89` is 88-89, `HintsStore.java:325-333` is 322-330; the per-hint cap is `max(max_mutation_size, 16 MiB)`; the first flush of an empty aggregation buffer allocates a 28 B buffer before the hint-sized one.
