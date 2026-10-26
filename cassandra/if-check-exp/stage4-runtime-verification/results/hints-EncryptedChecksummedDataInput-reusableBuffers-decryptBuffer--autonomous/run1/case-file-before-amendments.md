# Hints encrypted-reader thread-local decrypt buffer (reusableBuffers) vs hint write-buffer / max_mutation_size — verification solution  <!-- file: cases/hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/hints/EncryptedChecksummedDataInput.java:126` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code agent, 2026-10-25 |
| Estimate | `negative`. Line 126 is a grow-only high-water mark of a per-thread buffer. Nothing on the read path compares a block length to any limit, so retained memory follows the largest block written in the file, not a configured cap. |
| Ground | (1) No limit is consulted: the block size comes from an 8-byte header read from the file (`EncryptionUtils.java:144-148`) and goes straight to `ensureCapacity` (`ByteBufferUtil.java:813-829`). (2) The only bounds are indirect and write-side: the 256 KiB aggregation buffer (`HintsWriteExecutor.java:50`) and `HintsBuffer.allocate`'s limit of slab/2 (`HintsBuffer.java:152`), where slab = max(2 x max_mutation_size, 32 MiB) (`HintsService.java:110`). A block can exceed the 256 KiB constant (`HintsWriter.java:220`). (3) The buffer is never shrunk and lives as long as its thread (`:126-127`). (4) In 5.0.9 a stock node never writes encrypted hints (`HintsService.java:130-148` only emits compression), so this path runs only on a hints file that was produced elsewhere. |

## A. Constraint trace

**A1. The constraint.** The target line is not a limit. It is the grow step of a per-thread cache:

- `reusableBuffers` is a `FastThreadLocal<ByteBuffer>` whose initial value is `ByteBuffer.allocate(0)` (`EncryptedChecksummedDataInput.java:35-41`, allocation at `:39`).
- `readBuffer()` fetches it (`:122`), has `EncryptionUtils.decrypt` fill it (`:123`), and replaces the thread-local if the returned buffer is larger (`:126-127`).

The candidate "constraints" that could cap this buffer, traced back:

1. `HintsWriteExecutor.WRITE_BUFFER_SIZE = 256 << 10` (`HintsWriteExecutor.java:50`). It is a constant, not settable, and sizes the direct aggregation buffer at `:60`. Each encrypted block on disk is one flush of this buffer, so it is the nominal block size. Unit: bytes; 262144.
2. `max_mutation_size` (`Config.java:406-407`). Unit: KiB (`IntKibibytesBound`). Default: unset in Config, then `commitlog_segment_size / 2` (`DatabaseDescriptor.java:898-899`). `commitlog_segment_size` defaults to 32 MiB (`Config.java:397`), so the default is 16 MiB. It sets the hints slab as `max(2 * max_mutation_size, 32 MiB)` (`HintsService.java:79,110`), and the slab bounds one hint to slab/2 (`HintsBuffer.java:152-157`). It is set in yaml and needs a restart.
3. `hints_compression` / `transparent_data_encryption_options.chunk_length_kb` (default 64, `conf/cassandra.yaml:1776`) are NOT used for hint block sizing. `chunkLength` is read at `EncryptionContext.java:67`, but the hints writer sizes blocks from the 256 KiB buffer, not from it.

The solution tests the claim against (1) and (2): the retained decrypt buffer is not capped by either.

**A2. What it caps.** Nothing is actually capped here. The resource is on-heap: `ByteBuffer.allocate` (on-heap) is used for `reusableBuffers`, and `BufferType.typeOf(buf)` preserves that type on regrowth (`ByteBufferUtil.java:799`), so the retained thread-local is a `byte[]` on the Java heap. A second, related buffer is the reader's own `buffer`. It is allocated OFF_HEAP at `RandomAccessReader.DEFAULT_BUFFER_SIZE` = 4096 (`ChecksummedDataInput.java:56,70`; `RandomAccessReader.java:34`) and regrown by `EncryptionUtils.uncompress` (`:184`) to the plaintext block length. That is direct memory, per open reader. The quantity to observe is `decrypted.capacity()` / `byteBuffer.capacity()`, i.e. the high-water mark of block length.

**A3. Mechanism (step by step).**

1. `HintsReader.open` upgrades to the encrypted reader when the descriptor is encrypted (`HintsReader.java:75-88`).
2. Each `reBuffer()` (`ChecksummedDataInput.java:204-213`) calls `readBuffer()` (`EncryptedChecksummedDataInput.java:114`).
3. `EncryptionUtils.decrypt` reads an 8-byte header (`EncryptionUtils.java:140-146`: `encryptedLength`, then the compressed length labelled `plainTextLength`). It calls `ensureCapacity(outputBuffer, max(plainTextLength, encryptedLength), true)` (`:148`). That allocates a new buffer when `capacity < required` (`ByteBufferUtil.java:817-822`; `allowBufferResize` is always `true` at `EncryptedChecksummedDataInput.java:123`, so the `IllegalStateException` at `:820` is unreachable), then reads and decrypts in place (`:149-157`). It returns `dupe`, a duplicate sharing the capacity (`:152-153,165`).
4. `uncompress` takes the leading int as `outputLength` and regrows the reader's off-heap `buffer` to it (`EncryptionUtils.java:183-186`; call at `EncryptedChecksummedDataInput.java:124`).
5. Line 126 compares capacities; if `decrypt` had to regrow, the bigger buffer replaces the thread-local (`:127`). The buffer never shrinks and is not tied to the reader's lifetime, so it persists while the thread lives.

Outcomes:

- Block length <= current capacity: reuse, no allocation, no check.
- Block length > current capacity: allocate a new, larger on-heap array, with no upper limit. A corrupt or hostile header gives up to `Integer.MAX_VALUE` bytes (`ensureCapacity` only rejects negatives, `ByteBufferUtil.java:815-816`).

Writer side, which determines block length:

- `HintsWriteExecutor.flushInternal` opens `writer.newSession(writeBuffer)` with the 256 KiB buffer (`HintsWriteExecutor.java:241`) and appends each hint (`:245`), stopping at `max_hints_file_size` (`:239,247`).
- `Session.append` flushes the aggregate when a hint does not fit (`HintsWriter.java:205-209`); a hint that still does not fit is written directly as its own block (`:218-221`). For `EncryptedHintsWriter`, every `writeBuffer` call is one compressed-then-encrypted block (`EncryptedHintsWriter.java:47-52`; `EncryptionUtils.compress` `:66-77`; `encryptAndWrite` `:88-116`, header at `:98-99`).
- Normal block: up to 256 KiB plaintext. Compressed size is LZ4 worst-case bound `n + n/255 + 16` (`LZ4Compressor.java:113-116`); AES/CBC/PKCS5 adds at most 16 bytes. Oversized block: one hint up to slab/2 (default 16 MiB) arrives via `HintsBuffer.allocate` (`HintsBuffer.java:148-157`, `HintsBufferPool.java:59-65`, `HintsService.java:161-169`).
- The test-only `Session.append(Hint)` (`HintsWriter.java:232-262`) has no such limit.

Bypass and overshoot:

- The retained buffer can exceed 256 KiB by up to about 64x (16 MiB / 256 KiB) in legitimate files, and can exceed `max_mutation_size` if the file was not produced by this node's limits (corrupt, hostile, or written by a node with a larger `max_mutation_size`).
- Per thread, not per reader: `HintsDispatcher` pool threads (`HintsDispatchExecutor.java:68-72`, `max_hints_delivery_threads` default 2, `Config.java:443`) each hold one. Any other thread that opens an encrypted reader also gets one, e.g. a test or tool thread.

Reachability: `HintsService.createDescriptorParams` only ever adds `COMPRESSION` (`HintsService.java:130-148`). `HintsDescriptor.ENCRYPTION` (`HintsDescriptor.java:75`) is set only by a test (`HintsEncryptionTest.java:78`). Compression and encryption are mutually exclusive in a descriptor (`HintsDescriptor.java:109-110`). So in 5.0.9 a node reads encrypted hints only from a pre-existing or externally produced file whose header names `encryption`. Evidence beyond the source (A5) shows the feature came from CASSANDRA-11040.

**A4. Other consumers.**

- Heap: the memtables, caches, and so on, are outside this constraint.
- Direct memory: the hints write buffer (256 KiB, one per node, `HintsWriteExecutor.java:60`), the hints slab(s) (`HintsBuffer.java:75-77`; at most `MAX_HINT_BUFFERS` = 3, `HintsBufferPool.java:41`, `CassandraRelevantProperties.java:351`, each `max(2 x max_mutation_size, 32 MiB)`), and the reader's off-heap `buffer`.
- All of these are far larger than the typical 256 KiB decrypt buffer, so the target line is a minor consumer unless an oversized block exists.

**A5. Evidence beyond the source.**

- `CHANGES.txt:3076` ("Encrypted hints (CASSANDRA-11040)") for the feature's origin.
- `test/unit/org/apache/cassandra/hints/HintsEncryptionTest.java` (reader/writer round trip).
- Netty `FastThreadLocal` semantics: the value lives per thread until `removeAll` or thread death.
- Nothing else relied on. No external URLs were fetched.

## B. Verification solution

**B1. Claim under test.** The on-heap `reusableBuffers` array retained after reading encrypted hints has capacity equal to the largest block header seen by that thread (about 256 KiB + 1 KiB overhead for incompressible 256 KiB blocks; about the oversized hint's size for an oversized block). It is independent of `max_mutation_size` and of the 256 KiB `WRITE_BUFFER_SIZE`. It does not shrink after the read ends, and a forged header larger than every configured limit is allocated without any check. Falsified if the retained capacity is always <= 256 KiB + a few KiB regardless of block header, or if it tracks `max_mutation_size` when that is lowered.

### B2. Unit tier

**B2a. Environment and build.**

- JDK 11, Ant. Copy the tree: `rsync -a ~/cassandra-5.0.9/ /local/scratch/c509/`, then `cd /local/scratch/c509 && ant jar` (and `ant build-test` if using the JUnit scaffolding).
- Put the new test class in the copy at `/local/scratch/c509/test/unit/org/apache/cassandra/hints/EncReusableBufProbe.java`, in package `org.apache.cassandra.hints` so package-private classes are visible. Model it on `HintsEncryptionTest.java` (`EncryptionContextGenerator.createContext(true)`, `DatabaseDescriptor.setEncryptionContext`, `HintsDescriptor` with an `ENCRYPTION` param map as at `HintsEncryptionTest.java:78`).
- Run: `ant testsome -Dtest.name=org.apache.cassandra.hints.EncReusableBufProbe -Dtest.runners=1`, with `-Xmx2g` via `-Dtest.jvm.args` (or `JAVA_TOOL_OPTIONS`) so the forged-header case is allowed to attempt a ~512 MiB allocation.
- Read the private static `reusableBuffers` by reflection (`Field f = EncryptedChecksummedDataInput.class.getDeclaredField("reusableBuffers"); f.setAccessible(true); FastThreadLocal<ByteBuffer> t = ...; t.get().capacity()`), on the same thread as the reader. Spawn a fresh thread per scenario so each starts from capacity 0.

**B2b. Knobs.**

- K1, hint payload shape per scenario. S1: 2,000 hints of 1 KiB random bytes (about 2 MiB, about 8 aggregate blocks of 256 KiB). S2: one hint of 1 MiB. S3: one hint of 8 MiB. S4: one hint of 15 MiB. Use random bytes so LZ4 does not shrink them. These are written with the test-only `Session.append(Hint)` (`HintsWriter.java:232-262`), which has no size limit, or with `Session.append(ByteBuffer)` (`:200-222`) for the exact framing.
- K2, `DatabaseDescriptor.setMaxMutationSize`-equivalent. The reader never reads it, so vary it in the probe only to show indifference: default (16 MiB) vs 1 MiB (also set `commitlog_segment_size` to 2 MiB to satisfy the check at `DatabaseDescriptor.java:900-901`). The reader's behaviour should not change.
- K3, forged header (S5): after writing a valid descriptor, append raw bytes `[int encryptedLength = 512 MiB][int plainTextLength = 512 MiB]` and a few junk bytes. Run the reader in a fresh thread under `-Xmx2g`.
- K4, compressibility control (S6): 256 KiB of zeros per block, so the compressed and encrypted block is very small.

**B2c. Workload.** Write each scenario to a fresh file with an `EncryptedHintsWriter` (`HintsWriter.create`, which picks it when `descriptor.isEncrypted()`, `HintsWriter.java:86-87`), then read it fully with `HintsReader.open(file)` (`HintsReader.java:75-88`) and iterate `hints()`/`buffers()` until EOF. Arithmetic:

- S1: 2,000 x (1 KiB + 12 bytes of entry overhead, `HintsBuffer.java:58`) is about 2.0 MiB, so about 8 flushes of at most 256 KiB. The block count is not needed, only that the maximum is about 256 KiB.
- S2-S4: a single hint larger than the 256 KiB aggregate, written as its own block (`HintsWriter.java:218-221`), so block ~= hint size.
- S5: a forged length of 512 MiB is far above every limit.

**B2d. Observables and instruments.**

- Primary: `reusableBuffers.get().capacity()` after the read finishes, via reflection, on the reading thread. Also capture it after each `BuffersIterator` page to see the high-water mark.
- Secondary: `buffer.capacity()` of the reader (reflection on `RandomAccessReader`/`ChecksummedDataInput.buffer`, via `getDeclaredField("buffer")` on the superclass) to see the off-heap regrowth.
- Cross-check with `Runtime.totalMemory()-freeMemory()` after `System.gc()` twice, before and after, per scenario in a fresh thread. This is approximate and is for corroboration only.
- Not directly observable: the exact LZ4 worst-case bound per block. Derive it from `LZ4Compressor.initialCompressedBufferLength`.

**B2e. Procedure.**

1. Build the copy (B2a). Write the probe with one JUnit test per scenario S1-S6 plus the control C1 below.
2. For each scenario: new thread; confirm `capacity()==0`; write file; read file to EOF; record `reusableBuffers.get().capacity()`, reader `buffer.capacity()`; then run the read a second time on the same thread with a smaller file (S1) and record again (checks no shrink).
3. Repeat S3 with K2 = 1 MiB `max_mutation_size`.
4. Run S5 with `-Xmx2g`. Expect an `IOException`/`EOFException`/`FSReadError` from the read after the allocation, which is acceptable; record the capacity after catching it.
5. Run control C1 (B2h) and record.

**B2f. Predictions (stated before any run).**

- S1: capacity in [256 KiB, 256 KiB + ~2 KiB] (the compressed bound `n + n/255 + 16` plus LZ4 header plus <=16 bytes of padding). Reader `buffer.capacity()` is about 256 KiB.
- S2 (1 MiB hint): capacity about 1 MiB + ~5 KiB. S3 (8 MiB): about 8 MiB + ~33 KiB. S4 (15 MiB): about 15 MiB + ~60 KiB. Each is larger than 256 KiB.
- K2 = 1 MiB: S3 gives the same capacity as with the default. No change from the knob.
- No shrink: after the S1 second read, capacity equals the first read's.
- S5: after the failed read, capacity >= 512 MiB (the allocation happens before any bytes are read, `EncryptionUtils.java:148-150`).
- S6 (zeros): capacity is much smaller than 256 KiB (a few KiB), since the buffer size is the encrypted compressed length. This shows it is not the plaintext constant.
- What would show the claim wrong: S3 or S4 retained capacity <= 256 KiB + a few KiB; or K2 changes the result; or capacity falls after a smaller second read; or S5 throws before allocating.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Capacity ~ block size (S1 ~256 KiB; S2-S4 ~ hint size; S5 >= 512 MiB), unchanged by K2 | Claim confirmed: buffer follows the largest block on disk, not 256 KiB or `max_mutation_size`. |
| S3/S4 capacity > 256 KiB and > 1 MiB while K2 = 1 MiB | Confirms no link to `max_mutation_size`. |
| Usage (capacity) rises with K2 in step with the knob | Claim refuted: some path reads the limit. Re-trace. |
| Capacity stays <= ~258 KiB for S2-S5 | Claim refuted: a cap exists on the read side that this trace missed. |
| Capacity shrinks after a smaller second read | Claim refuted (not grow-only). |
| Positive control C1 shows the write-side cap rejecting an oversized hint while the reader accepts the oversized block | Cap known to bind exists on the write path; read path has none. |
| C1 does not throw, or S1-S6 do not produce blocks of the intended sizes (file size check, B2h) | Not confirmed: workload did not reach the limit. |

**B2h. Controls.**

- C1, positive control: `HintsBuffer.create(1 << 20)` then `allocate(600 * 1024)` must throw `IllegalArgumentException` "Hint of ... bytes is too large" (`HintsBuffer.java:152-157`): this is a cap known to bind, on the write path. Then show that a 600 KiB block already on disk (S2-style) is read fine and grows the reader buffer.
- File-size check per scenario: the file length must be about the sum of block sizes + header (verify the block sizes by parsing the 8-byte headers with a small loop), so the workload provably produced the intended blocks.
- Fresh thread per scenario (the `FastThreadLocal` is per thread). The cipher is the same in all scenarios. Random vs zero payload isolates compressibility (S1 vs S6).
- Repeat each scenario 3 times; capacity is deterministic, so any difference means a harness bug.

### B3. Cluster tier

A stock 5.0.9 node never writes encrypted hints (`HintsService.java:130-148`), so the cluster tier must inject an encrypted hints file. It cannot be driven through the normal client path. The design is therefore a two-node cluster where one node reads an injected encrypted hints file addressed to the other.

**B3a. Environment and build.**

- Two nodes, A (reader) and B (target), JDK 11, built from a local copy (`ant jar` in `/local/scratch/c509`). Use local disk with at least 5 GiB free for data, commitlog, hints and heap dumps. Use loopback aliases (127.0.0.1/127.0.0.2) or two hosts.
- Node A yaml: `transparent_data_encryption_options: {enabled: true, chunk_length_kb: 64, cipher: AES/CBC/PKCS5Padding, key_alias: testing:1, key_provider: JKSKeyProvider with a JCEKS keystore holding an AES key under alias testing:1}` (format as `conf/cassandra.yaml:1774-1786`). Create the keystore with `keytool -genseckey -alias testing:1 -keyalg AES -keysize 128 -storetype JCEKS -keystore conf/.keystore -storepass cassandra -keypass cassandra`. Also `max_hints_delivery_threads: 1` (so exactly one dispatcher thread can hold a buffer), `max_mutation_size` per B3b, `hints_directory` on local disk.
- JVM on A: `MAX_HEAP_SIZE=2G`, `HEAP_NEWSIZE` unset (G1), `-XX:NativeMemoryTracking=summary`, JMX local enabled.
- Producer tool: a small main class in the same package as the B2 probe, built against the same jar, that writes the encrypted hints file with the same keystore and `EncryptionContext`. Using the unit-tier writer keeps descriptor, IV and cipher consistent. Name the file `<hostIdOfB>-<timestamp>-<messagingVersion>.hints` as in `HintsDescriptor.java:97-98`. Place it in A's `hints_directory` before A starts (or while A runs, then `nodetool` hints trigger as in B3e).

**B3b. Knobs.**

- K1, block shape in the injected file (as B2b): F1 = many 1 KiB hints (about 256 KiB blocks, total 64 MiB); F2 = one 8 MiB hint then small ones; F3 = one 15 MiB hint.
- K2, `max_mutation_size` on A: default (16 MiB) vs `1024` (KiB) with `commitlog_segment_size: 2MiB`. Applied in yaml; restart A.
- K3, `max_hints_file_size`: default 128 MiB vs `4MiB` (`Config.java:446-447`), used in the positive control only (it caps hints disk per file on the write path, `HintsWriteExecutor.java:237-247`).

**B3c. Workload.** Start B, start A, let A see B as UP. Put the injected file for B's host ID in A's hints directory and let A's dispatcher deliver it. Delivery is triggered when A schedules dispatch for the store (hints dispatch runs periodically and on gossip UP; if it is not triggered, restart A with the file already in place, since startup scans the hints directory via `HintsCatalog.load`, `HintsService.java:107`). The file must cover: F1 total 64 MiB (about 256 blocks of 256 KiB each); F2/F3 with the oversized hint first so the high-water mark is set early. Duration: until dispatch completes (file deleted), then 5 minutes idle for observation.

**B3d. Observables and instruments.**

- On A: `jcmd <pid> GC.class_histogram | head -5` before dispatch, immediately after dispatch finishes, and after `jcmd <pid> GC.run` plus 60 s idle. Track the `[B` row (byte[]) bytes: the retained decrypt buffer shows as one large `byte[]` (identify by `jcmd <pid> GC.heap_dump /local/scratch/h.hprof` and checking the retaining GC root: the `HintsDispatcher` thread's thread-local map; analyse with `jhat`-class tooling such as Eclipse MAT if available, otherwise compare `[B` totals only).
- Direct memory: JMX `java.nio:type=BufferPool,name=direct` `MemoryUsed`, polled every 2 s with `jcmd`/a JMX client, for the reader's off-heap `buffer` growth. `jcmd <pid> VM.native_memory summary` for corroboration.
- `nodetool tpstats`-style check that dispatch ran: `ls hints_directory` empties; log lines from `HintsDispatcher`.
- Not observable directly: the per-thread capacity (no JMX for it); inferred from heap-dump root analysis or from `[B` deltas.

**B3e. Procedure.**

1. Build and configure both nodes (B3a). Start B, then A with an empty hints directory. Record the baseline histogram `[B` bytes and `BufferPool direct`.
2. Stop A. Generate F1 with the producer tool and place it in A's `hints_directory`. Start A. Wait for dispatch to finish (file gone). Record histograms/direct memory (after-dispatch, after `GC.run`, +60 s).
3. Repeat from step 1 with a fresh A data directory for F2 and F3. Repeat F2 with K2 = 1024 KiB.
4. Positive control run: with a client (`cqlsh`/`cassandra-stress`), stop B, write 200 MiB of data at CL=ONE through A so A hints for B (normal client path), with `max_hints_file_size: 4MiB` vs default. Record `du -sh hints_directory` and file count.
5. Stop all nodes (`nodetool drain`; `kill` the PIDs), `pgrep -f CassandraDaemon` must return nothing; delete `/local/scratch` data.

**B3f. Predictions (stated before any run).**

- F1: after dispatch and after `GC.run`, A holds one large retained `byte[]` of about 256 KiB + ~1 KiB (random payload) in the dispatcher thread's thread-local; `[B` after-GC exceeds the baseline by roughly that plus the usual churn. No growth over the 5 idle minutes (not released, unless the pool thread times out and is reclaimed, `HintsDispatchExecutor.java:68-72`; if so the buffer is freed with the thread, which is itself informative).
- F2: retained `byte[]` about 8 MiB + ~33 KiB; F3: about 15 MiB + ~60 KiB, greater than 256 KiB and, with K2 = 1024 KiB, greater than `max_mutation_size` too. K2 does not change F2/F3 results.
- Direct memory: peak above baseline by about the oversized plaintext block (8 MiB or 15 MiB) during the read, for the reader's off-heap buffer, released when the reader closes.
- Positive control: with `max_hints_file_size` 4 MiB, hints for 200 MiB are split into files of about 4 MiB (file count about 50x higher than at default; no file much larger than 4 MiB + one hint); disk follows the cap's relation.
- What would show the claim wrong: F3 retained `byte[]` stays near 256 KiB; the retained size follows K2; or the buffer is not retained after dispatch on a live thread.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Retained `byte[]` ~ file's largest block (F1 ~256 KiB, F2 ~8 MiB, F3 ~15 MiB), unchanged by K2 | Claim confirmed: node memory held by this path follows the on-disk block, not 256 KiB or `max_mutation_size`. |
| F2/F3 retained > K2 limit (1 MiB) | Confirms the limit does not govern the reader. |
| Retained size tracks K2 (smaller K2, smaller buffer) | Claim refuted. |
| Retained size is always <= ~260 KiB for F2/F3 | Claim refuted; a read-side cap exists. |
| Positive control: hints disk / file sizes follow `max_hints_file_size` | A known cap does bind usage on the write side, so a flat reader buffer is a real absence of cap, not a harness blind spot. |
| Dispatch never ran (file still present), or control files did not rotate | Not confirmed: workload or control did not engage. |

**B3h. Controls.**

- Same file and workload with K2 only varied (single-variable).
- Baseline histogram before dispatch, and a run with an unencrypted (`hints_compression`-only or plain) hints file of the same payload, to show the extra retained `byte[]` is specific to the encrypted reader (the plain reader uses only the 4 KiB off-heap `buffer`, `ChecksummedDataInput.java:56`).
- Force `GC.run` before every after-reading histogram so garbage buffers (replaced smaller ones) are excluded.
- Verify the injected file really decodes as encrypted (A logs no "ignoring encryption" warning from `HintsDescriptor.java:185`) and that the keystore alias matches.

**B4. Risks and cleanup.**

- Disk: F1 is 64 MiB, F2/F3 are under 32 MiB, the positive control writes up to about 200 MiB of hints plus data and commitlog (give each node a local volume with at least 5 GiB free; never use shared storage). Heap dumps are about 2 GiB each: write them only to local scratch, and delete them after analysis.
- Memory: the B2 forged-header case (S5) allocates 512 MiB: use `-Xmx2g` and run it in an isolated JVM. Do not use a forged length above 1 GiB.
- Never build in or write to `~/cassandra-5.0.9` or any shared tree; work only in `/local/scratch/c509`.
- Cleanup: `nodetool drain` then stop both nodes, `pgrep -f 'CassandraDaemon|ant'` must be empty, remove the data, commitlog, hints and heap dump directories and the keystore.

## C. Sources read

- /tmp/wprompt.txt
- ~/writeup-A/playbook-autonomous.md
- ~/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/hints/EncryptedChecksummedDataInput.java
- src/java/org/apache/cassandra/security/EncryptionUtils.java
- src/java/org/apache/cassandra/security/EncryptionContext.java
- src/java/org/apache/cassandra/utils/ByteBufferUtil.java (ensureCapacity)
- src/java/org/apache/cassandra/hints/EncryptedHintsWriter.java
- src/java/org/apache/cassandra/hints/HintsWriter.java
- src/java/org/apache/cassandra/hints/HintsWriteExecutor.java
- src/java/org/apache/cassandra/hints/HintsBuffer.java
- src/java/org/apache/cassandra/hints/HintsBufferPool.java
- src/java/org/apache/cassandra/hints/HintsService.java
- src/java/org/apache/cassandra/hints/HintsDescriptor.java
- src/java/org/apache/cassandra/hints/HintsReader.java
- src/java/org/apache/cassandra/hints/ChecksummedDataInput.java
- src/java/org/apache/cassandra/hints/HintsDispatchExecutor.java
- src/java/org/apache/cassandra/io/util/RandomAccessReader.java
- src/java/org/apache/cassandra/io/compress/LZ4Compressor.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
- conf/cassandra.yaml
- CHANGES.txt
- test/unit/org/apache/cassandra/hints/HintsEncryptionTest.java

## D. Stage-4 feedback

none yet
