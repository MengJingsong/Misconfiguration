# chunk_length_in_kb — verification solution  <!-- file: cases/chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/streaming/CompressedInputStream.java:144` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code agent, 2026-10-25 |
| Estimate | `negative`: the receive-side direct buffer `compressedChunk` is sized by the chunk lengths the sender puts on the wire, not by a receiver-side limit. It starts at `chunk_length_in_kb` but is regrown at line 150 to `max(1.5 x capacity, wireLength)`. |
| Ground | The grow guard at line 144 compares against `capacity()`, not against any configured ceiling. The operand `chunkLength` comes from `Chunk.deserialize` (`CompressionMetadata.java:562-565`, a bare `in.readInt()`), and `CompressionInfoSerializer.deserialize` (`CompressionInfo.java:185-198`) applies no upper bound. Natural overshoot is 1.5x the table's chunk size for incompressible data. The only hard stop is the JVM's `-XX:MaxDirectMemorySize`, which is not the constraint under test. |

## A. Constraint trace

**A1. The constraint.** `chunk_length_in_kb`, a per-table compression sub-option (`compression = {'class': ..., 'chunk_length_in_kb': N}`).
- Kind: schema/table option, not a yaml entry.
- First declared at `schema/CompressionParams.java:55` (`CHUNK_LENGTH_IN_KB`). It is parsed by `parseChunkLength` (`CompressionParams.java:343-359`), which converts KiB to bytes and rejects values over `Integer.MAX_VALUE/1024` (about 2 GiB).
- Unit: KiB in CQL, bytes in `chunkLength()` (`CompressionParams.java:241`).
- Default: `DEFAULT_CHUNK_LENGTH = 1024*16` = 16 KiB (`CompressionParams.java:48`, applied at `:375`).
- Must be a power of 2 (`CompressionParams.java:441-451`).
- Set with `CREATE/ALTER TABLE ... WITH compression`. No restart is needed. It affects only SSTables written afterwards, and the value travels in the stream header (`CompressionParams.Serializer`, `:519-541`).
- The companion `min_compress_ratio` (`:57`, default 0.0) sets `maxCompressedLength` (`calcMaxCompressedLength`, `:187-190`). With ratio 0 it is `Integer.MAX_VALUE`.

**A2. What it caps.** Off-heap (direct) memory held by one inbound compressed-SSTable stream.
- `CompressedInputStream` allocates two direct buffers: `buffer` (the uncompressed chunk) at line 78 and `compressedChunk` at line 87. Both start at `chunkLength()`.
- The quantity compared at line 144 is `compressedChunk.capacity()` against the wire chunk length (`compressedChunks.next().length`, line 135).

**A3. Mechanism.**
1. `CassandraCompressedStreamReader.read` creates one `CompressedInputStream` per streamed file (`CassandraCompressedStreamReader.java:74`).
2. `loadNextChunk` takes the next chunk length from the sender-supplied `CompressionInfo` (line 135).
3. If `chunkLength < maxCompressedLength()` (line 142), the chunk is compressed. With the default ratio 0 this is always true.
4. If `compressedChunk.capacity() < chunkLength` (line 144), the old buffer is freed (line 149) and a new direct buffer is allocated at `max((int)(cap*1.5), chunkLength)` (line 150). There is no upper bound.
5. The chunk is read into the buffer (line 154) and the CRC is checked (line 157). It is then decompressed into `buffer` (line 160). `buffer` is fixed at `chunkLength()`, so a larger decompressed size would fail rather than grow it.
6. Otherwise (ratio > 0 and the chunk is not smaller than `maxCompressedLength`), the raw chunk is read directly into `buffer` (lines 165-169). `buffer` is not resized, so the chunk must fit it. `CompressedSequentialWriter` guarantees this (`:160-175`, `maxCompressedLength <= buffer.capacity()`).
7. The writer side emits compressed chunks larger than `chunkLength` when `maxCompressedLength == Integer.MAX_VALUE`. For incompressible data, LZ4 output is at most n + n/255 + 16, plus the 4-byte length prefix (`LZ4Compressor.java:113-116`, `CompressedSequentialWriter.java:156-165`), so the wire length is about chunk + 84 bytes.
8. That value is just above the initial capacity, so the first such chunk triggers the regrow to 1.5 x chunk. This overshoot is therefore the normal case for incompressible data with default settings.
- Bypass: with `stream_entire_sstables: true` (default, `Config.java:699`) eligible SSTables are streamed as whole files and this class is not used. Only compressed, non-entire-file streams reach line 144.
- `close()` frees both buffers (lines 210-224). `position()` skips chunks without allocating.

**A4. Other consumers.**
- Concurrent streams: each has its own pair of buffers (`streaming_connections_per_host`, and several peers).
- Direct memory used by the networking buffer pools, `BufferPool` (chunk cache), the commitlog, and `ChunkCache`.
- All of these share `-XX:MaxDirectMemorySize` (`conf/cassandra-env.sh:93,158`; `conf/jvm-server.options:174` leaves it commented, so the JVM default applies).

**A5. Evidence beyond the source.**
- CASSANDRA-10520 (compression min ratio), cited in the source comment at lines 139-141.
- Test `test/unit/org/apache/cassandra/streaming/compression/CompressedInputStreamTest.java:58,190` shows how to build a `CompressionInfo` and stream by hand.

## B. Verification solution

**B1. Claim under test.** The direct memory held by a `CompressedInputStream` is not bounded by the table's `chunk_length_in_kb`. `compressedChunk` grows beyond `chunkLength()`: to about 1.5x for naturally incompressible data, and to whatever length the stream header declares (here tens of MiB) in a hand-built stream. Usage follows the wire-declared chunk length, not the configured option.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11, Ant. Copy the tree to local disk first: `rsync -a /users/jason92/cassandra-5.0.9/ /tmp/c509-unit/`. Work only in the copy.
- Add the test class `test/unit/org/apache/cassandra/streaming/compression/CompressedInputStreamOversizeTest.java` to the copy, modelled on `CompressedInputStreamTest.java`.
- Build: `cd /tmp/c509-unit && ant build-test`.
- Run: `ant testsome -Dtest.name=org.apache.cassandra.streaming.compression.CompressedInputStreamOversizeTest`.
- JVM options: `-XX:MaxDirectMemorySize=512m`. Set it through `test.jvm.args` or the test target's jvmargs.

**B2b. Knobs.**
- `chunkLength` in the `CompressionParams`: 4096, 16384 (default), 65536, built with `new CompressionParams("LZ4Compressor", Collections.emptyMap(), chunkLength, 0.0)`. This is the public constructor at `CompressionParams.java:182`, so `maxCompressedLength` is `Integer.MAX_VALUE`.
- Declared wire length `L` of the single chunk, set through `new CompressionMetadata.Chunk(0, L)`: `L` = chunkLength - 1 (control), chunkLength + 84 (natural LZ4 worst case), 1.5 x chunkLength + 1, and 32 MiB (hand-built).
- Why: the first value should not regrow, the second is the real overshoot, the third is just past the 1.5x step, and the last tests the unbounded claim.

**B2c. Workload.**
- Build a `byte[]` of `L + 4` bytes (payload plus 4-byte CRC) filled with random bytes. Use `CompressionInfo.newInstance(new Chunk[]{chunk}, params)`.
- Feed it via `new DataInputBuffer(bytes)`, which takes the `readChunkSlow` path (line 183). Pass `() -> 0.0` as the checksum chance so the CRC is not verified.
- Call `cis.position(0)` (which calls `loadNextChunk`) inside a try/catch.
- Decompression of random bytes will throw an `IOException` or a buffer exception. That is expected, because the capacity at line 150 is set before the failure. The test must not treat it as a failure.
- Arithmetic: for chunkLength = 16384 and L = 16468, 16384 < 16468 is true, so line 150 allocates `max(24576, 16468)` = 24576. For L = 32 MiB it allocates exactly 33554432.

**B2d. Observables and instruments.**
- `compressedChunk.capacity()` read by reflection (`Field f = CompressedInputStream.class.getDeclaredField("compressedChunk"); f.setAccessible(true)`). This is the check's own operand.
- `buffer.capacity()` of the uncompressed buffer (the superclass field `buffer`), read by reflection.
- `java.lang.management.ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)`, pool "direct": `getMemoryUsed()` before construction, after the failed `position()`, and after `close()`.
- Not observable here: real node memory, or interaction with other consumers.

**B2e. Procedure.**
1. Copy the tree and add the test (B2a).
2. For each (chunkLength, L) pair, construct the stream and record `buffer.capacity()`, `compressedChunk.capacity()` and the direct pool used.
3. Call `position(0)` inside try/catch, then record the same values again.
4. Call `close()` and record the pool again.
5. Run the L = 32 MiB case under `-XX:MaxDirectMemorySize=512m`, then again under `-XX:MaxDirectMemorySize=16m` (expect `OutOfMemoryError: Direct buffer memory`, the positive control).
6. Delete `/tmp/c509-unit` when finished.

**B2f. Predictions.** Stated before any run.

| chunkLength | L | `buffer.capacity()` | `compressedChunk.capacity()` after |
|---|---|---|---|
| 16384 | 16383 | 16384 | 16384 |
| 16384 | 16468 | 16384 | 24576 |
| 16384 | 24577 | 16384 | 24577 |
| 16384 | 32 MiB | 16384 | 33554432 |
| 4096 | 4180 | 4096 | 6144 |
| 65536 | 65620 | 65536 | 98304 |

- The pool-used delta after the failed `position()` is about `chunkLength + compressedChunk.capacity()` (plus the allocator's page rounding).
- It returns to the baseline after `close()`.
- If the claim were wrong, `compressedChunk.capacity()` would stay at or below `chunkLength` (or a configured ceiling) for every L.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `compressedChunk.capacity() > chunkLength` for L = chunkLength + 84, and 32 MiB for L = 32 MiB | Claim confirmed: usage follows the wire length, not the option. |
| Capacity stays <= chunkLength for all L, or an exception is thrown before the allocation | Claim refuted: some ceiling exists that the trace missed. |
| L = chunkLength - 1 shows no growth and `buffer.capacity()` is constant at chunkLength | Control is sound: line 144 only fires on overshoot, and the uncompressed side is bounded by the option. |
| With `-XX:MaxDirectMemorySize=16m` and L = 32 MiB, `OutOfMemoryError: Direct buffer memory` | Positive control: a cap that does bind (the JVM limit) stops the allocation, so the instrument can see a cap. |
| L = 32 MiB succeeds but the pool delta is below L | The instrument is not seeing the allocation; not confirmed. |
| Failure before line 150 (e.g. `NoSuchElementException`) | The limit was not reached; not confirmed. Fix the test input. |

**B2h. Controls.**
- The L = chunkLength - 1 case isolates the regrow from the initial allocation.
- Running the same L under two chunk lengths shows the 1.5x scaling is tied to the option.
- The `MaxDirectMemorySize` run supplies the positive control.
- Running each case in a fresh stream avoids carry-over of `compressedChunk` between cases.

**B2i. Audit amendments to the unit tier (2026-10-25, stage-4 step 0, before any reading).** These supply values the filed text left open and add rows; B2f's table above is unchanged except where a row here says it is added.
1. *Paths and run.* The tree is a `copy-source.sh` copy (`~/s4-ci/cassandra` on the run node), not `/users/jason92/cassandra-5.0.9` or `/tmp/c509-unit`. The test JVM option is passed as `ant testsome -Dtest.name=... -Dtest.jvm.args="-XX:MaxDirectMemorySize=<size>"` (`build.xml:94,1192`). Three invocations: (U-main) `512m`, all arms; (U-cap) `16m`, the arms `cap_wire32MiB` and `cap_natural16MiB_init`; (U-cap38) `38m`, the arms `cap38_natural16MiB` and `cap38_ratio11_16MiB`.
2. *Real-path arm added ("natural").* Hand-declared lengths do not prove that the real sender produces an overshoot. For n in {4096, 16384, 65536, 1 MiB, 16 MiB} the test fills n random bytes, compresses them with the real `LZ4Compressor` (`LZ4Compressor.java`, 4-byte length prefix plus an LZ4 block), writes the real CRC32 of the compressed bytes, declares `Chunk(0, W)` with W the real compressed length, and runs `position(0)` with `() -> 1.0`, so the chunk is decompressed and its bytes compared with the input. The expectation for LZ4 on random data is a literal-only block, W = n + 4 + 2 + floor((n-15)/255) (about n + 70 at 16 KiB). Prediction (numeric): W is in [n + 5, n + 4 + n/255 + 16]; `compressedChunk.capacity()` after = (int)(1.5 x n) exactly (4096 -> 6144, 16384 -> 24576, 65536 -> 98304, 1 MiB -> 1572864, 16 MiB -> 25165824); `buffer.capacity()` = n; the decompressed bytes equal the input (no exception).
3. *Boundary arms added.* L = n (16384, 4096, 65536): no regrow (`capacity() < chunkLength` is false at equality), capacity stays n. L = n + 1: regrow to 1.5 x n. The filed L = chunkLength - 1 control stays.
4. *Wire-declared arms.* `wire32MiB` (n = 16384, L = 32 MiB, the filed arm) and `wire128MiB` (n = 16384, L = 128 MiB) both with random bytes and no checksum validation: capacity after = L exactly (L >= 1.5 n); decompression is expected to throw (random bytes), caught; the capacity is read after the exception. The 128 MiB arm shows a direct buffer 8192 times the option. `buffer.capacity()` stays 16384.
5. *Ratio 1.1 arm added (unit control for the raw path).* `new CompressionParams("LZ4Compressor", n, (int) Math.ceil(n / 1.1), emptyMap())` (the four-argument constructor, `CompressionParams.java:195`) with a raw chunk of exactly n bytes (L = n >= maxCompressedLength, so `loadNextChunk` takes lines 165-169): `compressedChunk.capacity()` stays n, `buffer` receives the n bytes. Run at n = 16 MiB (arm `ratio11_16MiB`) and 1 MiB. Prediction: capacity n, pool delta after the call = 2 n.
6. *Pool-delta prediction (numeric).* Single thread, test JVM: `delta_after_position` = `buffer.capacity()` + `compressedChunk.capacity()` within 1 MiB (the JVM counts reserved capacity; other direct users in a unit JVM are a few KiB); `delta_after_close` = 0 within 1 MiB.
7. *Positive controls (known-binding cap on the same resource: the JVM direct-memory limit).* (a) `cap_wire32MiB` under 16m: expected `OutOfMemoryError` with message containing "Direct buffer memory", thrown inside `loadNextChunk`; the capacity read afterwards is 16384 (the old buffer was cleaned, the field still refers to it). (b) `cap_natural16MiB_init` under 16m: the constructor itself (two 16 MiB buffers = 32 MiB) throws the same error; this shows the limit sees the option-sized allocation. (c) The sharp pair under 38m with n = 16 MiB: the constructor holds 32 MiB, which fits; `cap38_natural16MiB` needs 16 MiB + 24 MiB = 40 MiB at the regrow and must throw "Direct buffer memory" at line 150; `cap38_ratio11_16MiB` (the raw path, no regrow, 32 MiB total) must succeed. If the constructor of either arm throws under 38m, that arm is invalid (limit too tight for the JVM's other direct users) and the control is recorded as not established, not as a result.
8. *Which row each outcome is.* Everything in B2g stays. Added rows: (i) natural arm capacity equals n (no regrow) or the decompressed bytes differ from the input: the real sender path is not what B1 says: Refuted for the natural-overshoot half of B1; (ii) `wire128MiB` capacity < L: the unbounded half of B1 refuted; (iii) the 38m pair behaves the same (both succeed or both fail): the control cannot tell the 1.0x from the 1.5x footprint; Not confirmed. Effect on the constraint: **does not cap** if capacity > chunkLength for the natural arm and capacity = L for the wire arms; **caps** only if capacity never exceeds the option.
9. *Citations.* Re-read in `cassandra-5.0.9` at repository commit 25b4a70: `CompressedInputStream.java:78,87,135-160,165-170,210-224` correct; `GROWTH_FACTOR = 1.5` at `:54`; `CompressionInfo.java:185-198` and `CompressionMetadata.java:562-565` (bare `readInt`) correct; `CompressionParams.java:182` (public constructor with ratio) correct, `:195` is the constructor with an explicit `maxCompressedLength`; `calcMaxCompressedLength` is `:187-190` and gives `Integer.MAX_VALUE` for ratio 0. A3.7: the extra length for incompressible data is about 70 bytes at 16 KiB, not 84 (the 84 is the bound n + n/255 + 16 plus 4); both are above the initial capacity, so the regrow conclusion stands.

### B3. Cluster tier

**B3a. Environment and build.**
- Two nodes (A is the sender, B is the receiver) on one Linux host, or two hosts.
- JDK 11, Ant. Build in a local copy: `rsync -a /users/jason92/cassandra-5.0.9/ /tmp/c509-cluster/ && cd /tmp/c509-cluster && ant jar`.
- Use separate local data, commitlog, hints and saved-caches directories under `/tmp/c509-A` and `/tmp/c509-B` on local disk.
- Two loopback addresses, e.g. 127.0.0.1 and 127.0.0.2.
- Both nodes: `stream_entire_sstables: false` in `cassandra.yaml` (without it, this class is bypassed), `num_tokens: 1`, `-Xmx1G`, `-XX:NativeMemoryTracking=summary`.
- Node B gets `-XX:MaxDirectMemorySize=256m` in `jvm-server.options` for the second run.

**B3b. Knobs.**
- Table `chunk_length_in_kb`: 4, 64, 1024 (powers of two; 1024 is large enough to see an overshoot above the noise of other direct memory).
- `min_compress_ratio`: 0 (default; takes the regrow path), and 1.1 (the control: with `maxCompressedLength` below the chunk length, incompressible chunks go through the raw path of lines 165-169, so there is no regrow).
- Set with `ALTER TABLE ks.t WITH compression = {'class':'LZ4Compressor','chunk_length_in_kb':'64'}` (and `'min_compress_ratio':'1.1'` for the control).
- B's `-XX:MaxDirectMemorySize`: unset, then 256m, as the positive control.

**B3c. Workload.**
- Table `ks.t (id int PRIMARY KEY, v blob)`, RF=1.
- Load with a Python driver script that inserts 200 MiB of `os.urandom(...)` blobs at 64 KiB per row, which gives incompressible data and about 3200 rows. Do this on node A only (node B not yet bootstrapped), then run `nodetool flush`.
- Trigger streaming by bootstrapping node B (`auto_bootstrap: true`), or with `nodetool rebuild` if B joins empty.
- Arithmetic: 200 MiB / 64 KiB chunks = 3200 chunks, so every chunk exceeds its initial capacity by about 84 bytes at ratio 0.
- Duration: a few minutes (the stream finishes when the 200 MiB has moved).

**B3d. Observables and instruments.**
- `jcmd <pidB> VM.native_memory summary`. The category "Other" includes direct ByteBuffers; take a baseline (idle, before the stream) and then one every 2 seconds during the stream: `while sleep 2; do jcmd <pidB> VM.native_memory summary | grep -A1 'Other'; done`.
- JMX `java.nio:type=BufferPool,name=direct` (attributes `MemoryUsed`, `Count`) through `jconsole` or `nodetool` where available.
- Logs: B's `system.log` for "Direct buffer memory" errors, and the `[Stream #...] Finished receiving file` lines (`CassandraCompressedStreamReader.java:96`).
- Not observable: the individual buffer sizes (the JVM only reports totals), and other direct consumers' usage, which is the noise floor.

**B3e. Procedure.**
1. Build as in B3a and start node A with the yaml set up above.
2. Create the keyspace and table with `chunk_length_in_kb=64`, `min_compress_ratio=0`.
3. Load 200 MiB of random blobs, then `nodetool flush` and `nodetool compact` so the data sits in a few large SSTables.
4. Record the baseline "Other" and `BufferPool direct` for B (start B with auto_bootstrap off long enough to take the baseline, or use a second idle sample from a node with the same settings).
5. Start the bootstrap of B (`auto_bootstrap: true`) and sample as in B3d until it finishes.
6. Record the peak "Other" and pool-used values.
7. Repeat steps 2-6 for 4 and 1024 KiB, then for `min_compress_ratio=1.1`, then for B with `MaxDirectMemorySize=256m`.
8. Stop both nodes (`nodetool drain`, then `kill`), run `pgrep -f CassandraDaemon` to check none remain, and delete `/tmp/c509-*`.

**B3f. Predictions.** Stated before any run. N is the number of simultaneous inbound compressed streams on B (set by `streaming_connections_per_host` and the number of SSTable files streaming at once). The prediction is a relation, because totals include other direct users.

| Setting | Peak direct delta on B (above baseline) |
|---|---|
| chunk 4 KiB, ratio 0 | about N x (4 + 6) KiB, with the regrow |
| chunk 64 KiB, ratio 0 | about N x (64 + 96) KiB |
| chunk 1024 KiB, ratio 0 | about N x (1024 + 1536) KiB = 2.5 x chunk per stream; the delta scales roughly linearly with the option |
| chunk 64 KiB, ratio 1.1 | about N x (64 + 64) KiB, no regrow (compressedChunk is only the initial size) |

- The ratio 0 vs ratio 1.1 difference at equal chunk size is the 1.5x vs 1.0x of `compressedChunk`: a 25% difference on the two-buffer total (2.5 vs 2.0).
- With `MaxDirectMemorySize=256m` the 1024 KiB case still completes (the footprint is far below the limit); the cap only shows if the table forces a footprint near it.
- At these sizes the effect is a few MiB, so it can be hidden by the other direct consumers. If the readings are inside the noise, the cluster tier cannot confirm the claim and the unit tier must carry it.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Peak delta at ratio 0 is about 2.5 x chunk x N and larger than at ratio 1.1 (about 2.0 x chunk x N) at the same chunk size | Claim confirmed: the receiving buffer exceeds the configured chunk size by the regrow step. |
| Delta at ratio 0 equals the delta at ratio 1.1 | Claim refuted at this scale: no regrow happened (check the data really was incompressible). |
| Delta scales with chunk_length_in_kb (4 -> 64 -> 1024) | Usage follows the option in magnitude (the initial allocation), but the overshoot above it is still not capped by it. This is consistent with the claim and does not refute it. |
| Delta flat across 4/64/1024 KiB | The direct memory is not coming from this class (or the measurement is dominated by other consumers); not confirmed. |
| Failure with `Direct buffer memory` only when `MaxDirectMemorySize` is lowered below the footprint | Positive control: the JVM cap binds, the option does not. |
| Stream finishes with no change in direct memory and no regrow in the unit tier | Limit never reached; not confirmed. |

**B3h. Controls.**
- Ratio 1.1 (same data, same chunk size, no regrow path) isolates the line 144-150 behaviour.
- A run with `stream_entire_sstables: true` should show no such delta, which shows the class is the source.
- Taking the idle baseline just before the stream removes the steady-state direct memory.
- Using random data in every case rules out compressibility as the explanation.

**B3i. Audit amendments to the cluster tier (2026-10-25, stage-4 step 0, before any reading).** The filed B3f is a relation in units of N streams and is too small to resolve at 64 KiB chunks (see 4). The amendments below fix the node set-up, enlarge the chunk so the effect is resolvable, and give numbers. B3f/B3g as filed remain, with these rows added.
1. *Set-up.* Both nodes run on one host (`pc12`), from the built tree `~/s4-ci/node-tree` (a copy; `ant` is never run in it), with separate conf directories, data on tmpfs (`/dev/shm/s4-ci`), loopback addresses 127.0.12.1 (A, seed) and 127.0.12.2 (B), storage port 7012, native 9112, JMX 7212 (A) and 7213 (B) (the default 7199 is hard-coded in `conf/cassandra-env.sh:235`, so each node has its own copy of the conf with that line edited), `-Dcassandra.ring_delay_ms=5000`, `-Xmx2G`/`-Xms2G`, `ulimit -n 100000`. A: `initial_token: -4611686018427387904`, B: `initial_token: 4611686018427387904` (B owns (A, B], half the ring; with `num_tokens: 1`). B has `auto_bootstrap: true` and joins A; the stream is the bootstrap stream. `NativeMemoryTracking` is not used (replaced by 3). `stream_entire_sstables: false` on both, except the control in 6.
2. *Chunk values and tables.* One table per run, `ks.t (id int PRIMARY KEY, v blob) WITH compression = {'class':'LZ4Compressor','chunk_length_in_kb':'<n>'[, 'min_compress_ratio':'1.1']}`, RF 1 (`SimpleStrategy`), every run starting from fresh data directories. Chunk values: 4, 16 (default), 64, 1024 and 16384 KiB (16 MiB). 16384 KiB is allowed (the parse limit is about 2 GiB). Data: 256 rows of 1 MiB of `os.urandom` (256 MiB, incompressible), written with the bundled Python driver at native protocol 4 on A only, then `nodetool flush` and `nodetool compact` so A holds one SSTable. About half of it is streamed to B.
3. *Instrument.* A harness Java class `PoolSampler` reads `java.nio:type=BufferPool,name=direct` (`MemoryUsed`, `Count`) through JMX on B every 20 ms and writes `epoch_ms,used,count`. This is the JVM's count of reserved direct buffer capacity, the real resource for `allocateDirect` buffers; Netty's own pooled arenas are not in it (gap named; the entire-sstable control in 6 shows what is left when this class and the compressed writer are not used). It replaces the `jcmd VM.native_memory` sampling for the peak (NMT is not enabled: it adds its own overhead). B's `system.log` gives the window: from the line containing "Executing streaming plan for Bootstrap" to the line containing "All sessions completed" (read from B's log at run time; if the text differs, the harness window is fixed in the instrument check, which is not a reading). Baseline = median of the samples in the 5 s before the window; **P = max of samples in the window minus baseline**. Per-run files are kept on the node.
4. *Resolution.* Two direct buffers of the reader (`buffer`, `compressedChunk`) and the receiver's `CompressedSequentialWriter` buffers (`buffer` and `compressed`, about 2 x chunk, the same in both ratios) are all proportional to the option, so P grows with the option. The part this claim is about is the regrow: `compressedChunk` 1.5 x n (ratio 0) against n (ratio 1.1). At 64 KiB that is 32 KiB, far below the noise; at 1 MiB it is 0.5 MiB, probably below it; at 16 MiB it is 8 MiB, above it. The filed "few MiB" therefore needs the 16 MiB chunk to be resolved. Streams in parallel are not added (one peer; N = 1), so the cluster arm resolves the effect only through the larger chunk and says so.
5. *Predictions (numeric), n in MiB, N = 1.* Reader pair: 2.5 n (ratio 0), 2.0 n (ratio 1.1). Writer: about 2 n. So P(ratio 0) is about 4.5 n and P(ratio 1.1) about 4.0 n, and **D = P(ratio 0) - P(ratio 1.1) is about 0.5 n**. Graded points: n = 16 MiB: P(ratio 0) in [50, 95] MiB; D in [5, 11] MiB in each of two repeats; |P(rep a) - P(rep b)| <= 2 MiB for the same setting (the noise estimate). n = 1 MiB: reported, graded only for the ordering P(1024 KiB) < P(16384 KiB); D at 1 MiB (0.5 MiB expected) and all values at 4, 16 and 64 KiB are reported as unresolved if |D| < 2 MiB. Dose response: P(16384 KiB) > P(1024 KiB) > P(64 KiB) (ratio 0).
6. *Controls.* (a) Ratio 1.1 at 1024 and 16384 KiB (the unit tier's raw path): D as above. (b) Entire-sstable control: A's token -9223372036854775000 and B's 9223372036854775000 (B owns nearly the whole ring, so the SSTable is contained in the requested ranges, `CassandraOutgoingFile.java:181-202`), `stream_entire_sstables: true` on both. Confirmation that the entire-file path was used: B's log at DEBUG for `org.apache.cassandra.db.streaming` must contain "Incoming stream entireSSTable=true" (`CassandraIncomingFile.java:71`); if it cannot be confirmed the control is reported as unconfirmed. Prediction: P <= 10 MiB at 16384 KiB (neither the reader nor the compressed writer is used). (c) Cap control: B started with `MAX_DIRECT_MEMORY_SIZE=48m` at 16384 KiB, ratio 0 (cap below the reader pair plus writer, 64 MiB or more): B's log shows `OutOfMemoryError` with "Direct buffer memory" (or the stream fails with it) and the stream does not complete; if B fails before the stream starts (baseline direct use above 48 MiB, start-up failure), the control is invalid and is not a result. (d) Stream data are random in every run, which rules out compressibility.
7. *Rows added to B3g.* (i) D in [5, 11] MiB at 16384 KiB in both repeats, repeat noise <= 2 MiB, ratio-1.1 and ratio-0 both completed, and the cap control stopped the stream with "Direct buffer memory": **Confirmed (does not cap)**: the receiver's direct memory exceeds the option by the regrow step and only the JVM limit stops it. (ii) |D| < 2 MiB at 16384 KiB in both repeats with P(ratio 0) in range: the regrow is not visible at the largest chunk: **Not confirmed** (the unit tier carries the claim); not Refuted, because the unit tier's natural arm decides whether the regrow exists. (iii) P(ratio 0) outside [50, 95] MiB: the instrument sees a different set of allocations than assumed: Not confirmed. (iv) cap control inconclusive: positive control not established, so the tier cannot be Confirmed.
8. *Workload arithmetic.* 256 MiB x 2 copies plus compaction headroom on tmpfs under 2 GiB per run, 126 GiB tmpfs available; time per run: load about 1 min, compaction seconds, join and stream under 1 min at the default 24 MiB/s outbound throttle for the 128 MiB moved (about 5 s). Runs: chunk {4, 16, 64, 1024, 16384} ratio 0; 1024 and 16384 ratio 1.1; 16384 ratio 0 and ratio 1.1 repeated (rep b); cap control; entire-sstable control: 12 runs.
9. *Second amendment to the cluster tier (2026-10-25, found at the instrument check, before run 1 and before any reading of a run; supersedes the cap value in 6c, the run count in 8 and nothing else).* The instrument check (a shakedown that is not a reading) showed that an idle Cassandra node already holds about 54.7 MiB of direct buffers after start-up (the JMX `BufferPool` baseline), so `MAX_DIRECT_MEMORY_SIZE=48m` in 6c kills B before the stream starts: the control would be invalid. The cap is changed to **100m**: above the start-up baseline (54.7 MiB), below the smallest footprint of the 16 MiB-chunk stream (baseline + two reader buffers of 16 MiB + the writer's two buffers of about 16 MiB each, at least 118 MiB). Prediction: B starts, a stream window opens ("Executing streaming plan for Bootstrap"), B's log shows `OutOfMemoryError: Direct buffer memory` and "All sessions completed" never appears. B3i.7(iv) applies if B dies before the stream window opens. The list in 8 has 11 runs (chunk 4, 16, 64, 1024, 16384 at ratio 0; 1024 and 16384 at ratio 1.1; repeats of the two 16384 runs; cap; entire), not 12.

**B4. Risks and cleanup.**
- Disk: 200 MiB of data per node, plus compaction headroom of about 3x. Use local `/tmp` directories on a volume with at least 5 GiB free, and check with `df -h /tmp` first.
- Do not put data, commitlog or hints on shared storage. Do not build in the shared source tree.
- Unit tier: the 32 MiB case and the 16m OOM case run in a JVM that exits afterwards.
- Cleanup: `nodetool drain`, kill both nodes, `pgrep -f CassandraDaemon` and `pgrep -f ant` must return nothing, then `rm -rf /tmp/c509-unit /tmp/c509-cluster /tmp/c509-A /tmp/c509-B`.

## C. Sources read

- `/users/jason92/writeup-A/playbook-autonomous.md`
- `/users/jason92/writeup-A/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/db/streaming/CompressedInputStream.java`
- `src/java/org/apache/cassandra/schema/CompressionParams.java`
- `src/java/org/apache/cassandra/db/streaming/CompressionInfo.java`
- `src/java/org/apache/cassandra/db/streaming/CassandraCompressedStreamReader.java`
- `src/java/org/apache/cassandra/io/compress/CompressionMetadata.java`
- `src/java/org/apache/cassandra/io/compress/CompressedSequentialWriter.java`
- `src/java/org/apache/cassandra/io/compress/LZ4Compressor.java`
- `src/java/org/apache/cassandra/config/Config.java` (grep)
- `conf/cassandra.yaml`, `conf/cassandra-env.sh` (grep)
- `test/unit/org/apache/cassandra/streaming/compression/CompressedInputStreamTest.java`

## D. Stage-4 feedback

**Verdict (2026-10-25, run 1 at both tiers, self-checked, no run 2): Confirmed - does not cap** (unit and cluster); outcome class **true negative** (estimate `negative`). Results: [`results/chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous.md`](../../stage4-runtime-verification/results/chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous.md). Frozen version for the runs: sha256 `4075fd9139c6108e258e3d50d3d545a2852d100256376eb9b53296ac4679955f` (after amendments B2i, B3i and B3i.9, all dated 2026-10-25; the file was untracked, no commit).
- **Unit (B2):** the real LZ4 chunk of incompressible data is n + 22 to n + 65,798 bytes on the wire (n = 4 KiB to 16 MiB) and `compressedChunk` regrows to exactly int(1.5 n) (24,576 at the default 16 KiB), bytes decoded correctly; L = n does not regrow, L = n + 1 does; a hand-declared 32 MiB and 128 MiB chunk under a 16 KiB option gives a 32 MiB and 128 MiB direct buffer (8,192 x the option). Pool delta = `buffer` + `compressedChunk` exactly; freed on `close()`. Positive control: `-XX:MaxDirectMemorySize=16m` stops the 32 MiB chunk; at 38m the regrow (16 + 24 MiB) throws `Direct buffer memory` and the raw-path chunk (ratio 1.1, 32 MiB) succeeds.
- **Cluster (B3):** bootstrap of a half ring (256 MiB of random blobs, one SSTable, N = 1 stream), direct-pool peak above the idle baseline (52.13 MiB): 1.0 to 1.3 MiB at 4, 16, 64 KiB, 5.5 MiB at 1 MiB, **73.07 MiB at 16 MiB** (ratio 0) against 65.07 MiB (ratio 1.1): the regrow is **+0.5 n = 8.00 MiB**, repeated to the byte; entire-file streaming (control) 0.00 MiB; B capped at 100m stops the stream with `OutOfMemoryError: Direct buffer memory` (inside the receiving writer's buffer, so the cap control shows a JVM cap binds, not that it binds the regrow; the unit 38m pair does that).
- **What the original text got wrong or left open:** (1) the effect at the filed chunk sizes (4 to 1024 KiB) is far below the noise of the idle node's own 52 MiB of direct buffers; 16 MiB chunks are needed, and at 1 MiB the difference was still resolvable because the JMX pool counter is quiet (B3i.5 had expected otherwise). (2) The overshoot of an honest sender is 1.5x on one of the two reader buffers (about 70 bytes over the option at 16 KiB, not 84; 84 is the upper bound): a constant factor, and the writer on the same stream adds about 2 n. The unbounded half of B1 (any declared length) is shown only by a hand-built header at the unit tier. (3) A1 says `stream_entire_sstables: true` bypasses the class; it does so only for an SSTable wholly inside the requested ranges (`CassandraOutgoingFile.java:194-202`); a partial-range bootstrap uses `CompressedInputStream` at the default. (4) The idle node already holds about 52 MiB of direct buffers, so any `MaxDirectMemorySize` below it (the 48m first chosen) makes the node fail before the stream. (5) After a failed regrow the old buffer is already freed (`FileUtils.clean` at line 149 precedes the allocation), so the footprint at the regrow is `buffer` + the new buffer, not `buffer` + old + new.
- Not amended: the estimate stays `negative` (confirmed). Parallel streams (N > 1) were not run.

