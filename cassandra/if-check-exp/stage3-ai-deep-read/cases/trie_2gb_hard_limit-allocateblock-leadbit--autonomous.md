# trie_2gb_hard_limit — verification solution  <!-- file: cases/trie_2gb_hard_limit-allocateblock-leadbit--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`InMemoryTrie.java:148`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryTrie.java#L148) (`if (leadBit + BUF_START_SHIFT == 31)` in `allocateBlock()`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `positive` for the object it bounds: one `InMemoryTrie`'s buffer space can never exceed 2^31 - 256 bytes, because the buffer array has a fixed length and positions are `int`. Caveat: the limit is per trie, it is a backstop that the memtable flush path is designed never to reach, and it does not bound the node total or the heap objects the trie points to. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** Name: the hard 2 GB size limit of one `InMemoryTrie` (the check throws `SpaceExhaustedException`, message "The hard 2GB limit on trie size has been exceeded", [`InMemoryTrie.java:110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryTrie.java#L110)). Kind: constant, compiled in. It is declared structurally in two places: the `buffers` array has `31 - BUF_START_SHIFT` slots ([`InMemoryTrie.java:90`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryTrie.java#L90), comment "last one is 1G for a total of ~2G bytes"), with `BUF_START_SHIFT = 8` and `BUF_START_SIZE = 1 << BUF_START_SHIFT` ([`InMemoryReadTrie.java:207-208`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryReadTrie.java#L207-L208)); and it is enforced by the check at [`InMemoryTrie.java:148`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryTrie.java#L148). Reason: 32-bit pointers in byte buffers (class comment `InMemoryTrie.java:46`, `:52-55`, `:98-100`). Unit: bytes of buffer space (`allocatedPos`, an `int`, `InMemoryTrie.java:70`). Value: buffer `i` has size `256 << i` (`InMemoryTrie.java:151`), slots 0..22 exist, so the total is 256 * (2^23 - 1) = 2^31 - 256 bytes; the javadoc says the same ("2G - 256 bytes", `InMemoryTrie.java:949`). Setting: not settable by yaml, `-D` or JMX; a change needs a source change and rebuild. Nearest configurable limit (mentioned only for context, covered by other work): the soft `ALLOCATED_SIZE_THRESHOLD` ([`InMemoryTrie.java:58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryTrie.java#L58)), default `2048 * 10 / 11` MB (`:63`), key `cassandra.memtable.row_overhead_size` (`CassandraRelevantProperties.java:356`), accepted range 1..2047 MB else `AssertionError` (`:64-66`), read once in a static initializer so a restart is needed. The earlier trace's A1 was checked: its line numbers are right, except that its quote of `InMemoryReadTrie.java:127` is correct (`BLOCK_SIZE = 32`) and the `getChunkIdx` body is at `InMemoryReadTrie.java:231-234`. Its "2048 * 10 / 11 = 1861 MB" is arithmetic from line 63 (not measured).

**A2. What it caps.** Resource: the byte buffers of one trie, on heap (`ByteBuffer.allocate`) or off heap (`ByteBuffer.allocateDirect`) depending on `BufferType` ([`BufferType.java:28`, `:35`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/compress/BufferType.java#L28), path `src/java/org/apache/cassandra/io/compress/BufferType.java`). Operand compared: `leadBit + BUF_START_SHIFT` against 31, where `leadBit = getChunkIdx(allocatedPos, 8, 256)` is the index of the buffer that the next block falls in (`InMemoryReadTrie.java:231-234`; `InMemoryTrie.java:147`). The sum reaches 31 exactly when `allocatedPos == 2^31 - 256` (then `pos + 256` overflows to `Integer.MIN_VALUE`, `numberOfLeadingZeros` is 0, `leadBit` is 23). Not capped: the content objects (`contentArrays`, `InMemoryTrie.java:91`, `:162-175`) and the objects they reference (for the memtable, `BTreePartitionData`) live on heap and are bounded separately (content array limit `29 - CONTENTS_START_SHIFT`, `:91`).

**A3. Mechanism.** Every node creation goes through `allocateBlock()` ([`InMemoryTrie.java:140`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryTrie.java#L140), callers `:433`, `:451`, `:476`, `:497`, and `advanceAllocatedPos` `:961-965`).
1. `v = allocatedPos` (`:144`). The check only runs when `v` is at the start of a buffer (`inChunkPointer(v) == 0`, `:145`).
2. `leadBit` computed (`:147`); the if statement: [`if (leadBit + BUF_START_SHIFT == 31)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryTrie.java#L148) throws `SpaceExhaustedException` (`:149`).
3. Otherwise the new buffer of `BUF_START_SIZE << leadBit` bytes is allocated and stored (`:151-152`) and `allocatedPos += BLOCK_SIZE` (32, `:158`).
Outcomes at the limit: the exception propagates out of every `putRecursive`/`apply`/`putSingleton` (declared `throws`, e.g. `:822`, `:895`); `allocatedPos` is unchanged, existing content stays readable (the unit test at `test/unit/.../InMemoryTriePutTest.java:98-103` asserts reads still work after the failure). Callers: `TrieMemtable.put` converts it to `IllegalStateException` (`TrieMemtable.java:200-205`, comment: "should never happen"); SAI wraps it in `RuntimeException` (`TrieMemoryIndex.java:237-240`, `SegmentTrieBuffer.java:71-74`). Bypass/overshoot: none for the buffers (the array and the `int` position make it structural). Before the limit, the soft threshold is polled after each memtable put (`TrieMemtable.java:192`, log "Scheduling flush due to trie size limit reached." at `:194`, `signalFlushRequired` at `:195`), and the trie "expects up to 10% growth above this threshold" (`InMemoryTrie.java:947-948`); that signal is asynchronous, so writes between the signal and the memtable switch can keep growing the trie. Only `TrieMemtable` calls `reachedAllocatedSizeThreshold` (grep of `src/java`); the SAI tries (`TrieMemoryIndex.java:81`, `SegmentTrieBuffer.java:48`, `RowMapping.java:75`) have no soft guard of this kind (their own limits were not traced: not verified).


The check itself is the if statement at [`InMemoryTrie.java:148`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryTrie.java#L148).

**A4. Other consumers.** Same resource outside this limit: (a) each `TrieMemtable` has one trie per shard (`TrieMemtable.java:127`, `:451`), shard count from `cassandra.memtable.shard.count` or CPU count (`AbstractShardedMemtable.java:46`), so the node total is shards x tables x live memtables x up to ~2 GB, bounded only by `memtable_heap_space` / `memtable_offheap_space` (`conf/cassandra.yaml:797-799`); (b) heap objects referenced by trie content; (c) SAI memory index tries and `RowMapping` (off heap, `RowMapping.java:75`); (d) the JIT/GC overhead of allocating a 1 GiB single buffer (for on-heap, a contiguous heap region; not verified for the collector in use).

**A5. Evidence beyond the source.** In-tree test `test/unit/org/apache/cassandra/db/tries/InMemoryTriePutTest.java:62-111` (`testOver1GSize`, `@Ignore`d because it needs about 8 GB heap, per its own comment at `:64-66`); it drives `advanceAllocatedPos` (`InMemoryTrie.java:961`) past the soft threshold and expects `SpaceExhaustedException` at the hard limit. No external sources relied on.

## B. Verification solution

**B1. Claim under test.** (1) One `InMemoryTrie` never holds more than 2^31 - 256 bytes of buffer space: `allocatedPos` stops growing at that value and the next allocation throws `SpaceExhaustedException`, with the allocated buffer memory growing in step with `allocatedPos`. (2) In a running node with the default configuration the trie memtable is switched (flushed) at the soft threshold, so the actual per-trie buffer memory stays below the hard limit and `SpaceExhaustedException` is not reached on the normal write path.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/cassandra-5.0.9/`, never build in the shared tree). `cd $WORK/cassandra-5.0.9 && ant jar build-test`. Put a new test class `Trie2GbLimitProbe` in `test/unit/org/apache/cassandra/db/tries/` (same package, because `advanceAllocatedPos` and `ALLOCATED_SIZE_THRESHOLD` are package-private, `InMemoryTrie.java:58`, `:961`). Run: `ant testsome -Dtest.name=org.apache.cassandra.db.tries.Trie2GbLimitProbe -Dtest.jvm.args="-Xmx10g -XX:MaxDirectMemorySize=6g -XX:NativeMemoryTracking=summary -Dcassandra.memtable.row_overhead_size=<MB>"` (`test.jvm.args` property, `build.xml:94`). Use a machine with at least 12 GB free RAM.

**B2b. Knobs.** (i) `BufferType`: `OFF_HEAP` (direct buffers; the main variant) and `ON_HEAP` (needs the large heap above). (ii) `-Dcassandra.memtable.row_overhead_size`: unset (default), `512`, `2047`; and the invalid values `0` and `2048` (expect `AssertionError` at class load, `InMemoryTrie.java:64-66`). Values chosen to show the soft threshold moves while the hard limit does not.

**B2c. Workload.** `new InMemoryTrie<String>(type)`, then `advanceAllocatedPos(target)` (allocates blocks of 32 bytes until `allocatedPos >= target`, `:961-965`). Targets: `ALLOCATED_SIZE_THRESHOLD`, `ALLOCATED_SIZE_THRESHOLD + 0x1000`, `0x7FFFFEE0` (2^31 - 288), then `Integer.MAX_VALUE`. Arithmetic: buffers 0..22 sum to 2^31 - 256; the last block starts at 2^31 - 288; the block after that starts at 2^31 - 256 which is the start of buffer 23, so `leadBit + 8 == 31` and the throw happens. A real `putRecursive` of a short key near the edge should throw as well (as in `InMemoryTriePutTest.java:93-98`).

**B2d. Observables and instruments.** In the probe: `trie.sizeOffHeap()` (`:969-972`, returns `allocatedPos` for off heap) and `trie.sizeOnHeap()` (`:974-981`); `trie.reachedAllocatedSizeThreshold()`; whether and where `SpaceExhaustedException` is thrown (record `sizeOffHeap()` before and after the failing call); `BufferPoolMXBean` "direct" `getMemoryUsed()` and `getCount()` via `ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)`; `MemoryMXBean` heap used; `jcmd <pid> VM.native_memory summary` at each target for an independent off-heap reading. Not directly observable: `allocatedPos` itself (private; use `sizeOffHeap()` for OFF_HEAP) and `leadBit`.

**B2e. Procedure.**
1. Build as in B2a. 2. Write the probe: for each target, call `advanceAllocatedPos`, then record the readings of B2d. 3. Run with `OFF_HEAP`, property unset. 4. Repeat with `row_overhead_size` = 512 and 2047. 5. Repeat once with `ON_HEAP`. 6. Run with `0` and `2048` and record the `ExceptionInInitializerError`/`AssertionError`. 7. As a positive control run the existing `testOver1GSize` with `@Ignore` removed in the local copy (the shared tree is not touched). 8. Stop all JVMs (`pgrep -f Trie2GbLimitProbe` empty), delete `$WORK`.

**B2f. Predictions (stated before any run).** `reachedAllocatedSizeThreshold()` flips to true at the first target at or above the threshold: after about 1861 MB for the default, about 512 MB for `512`, about 2047 MB for `2047`; it is false below. `advanceAllocatedPos(0x7FFFFEE0)` succeeds. The next block allocation throws `SpaceExhaustedException`, and `sizeOffHeap()` after the failure equals its value before it, and never exceeds 2^31 - 256 for any knob value. `advanceAllocatedPos(Integer.MAX_VALUE)` throws at the same point. Direct buffer total (`BufferPoolMXBean`) is at least `sizeOffHeap()` and at most 2^31 - 256 plus the part of the next buffer being allocated (nothing, because the throw happens before `allocate`, `:148-151`). The soft knob changes only when `reachedAllocatedSizeThreshold()` flips, never the point of the throw.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Throw occurs at `allocatedPos` = 2^31 - 256 for every knob value; reading does not grow after | claim (1) confirmed |
| Throw point moves with `row_overhead_size`, or `sizeOffHeap()` exceeds 2^31 - 256 | claim wrong |
| Direct buffer total keeps growing in step with `sizeOffHeap()` up to the last buffer | allocation follows the counter (supports that the counter measures real memory) |
| Direct buffer total much larger or smaller than `sizeOffHeap()` | counter does not match actual memory; investigate (e.g. buffers allocated but not counted) |
| Run ends with `OutOfMemoryError` before the limit | not confirmed (heap or direct limit too small); raise `-Xmx` / `MaxDirectMemorySize` |
| `0` / `2048` do not raise `AssertionError` | A1 range claim wrong |

**B2h. Controls.** The `ON_HEAP` run against `OFF_HEAP` shows the limit does not depend on where the buffer lives. The three soft-knob values show the soft guard is independent of the hard limit. Reading `sizeOffHeap()` and the MXBean/NMT figures together rules out a counter that diverges from real allocation.

### B3. Cluster tier

**B3a. Environment and build.** One node on Linux, JDK 11, built from a local copy (`ant jar`). Local disk of known size (at least 20 GB free) for data, commit log and hints; set `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` under `$WORK/node`. `cassandra.yaml` changes: keep the yaml `memtable.configurations.trie` entry (`conf/cassandra.yaml:785-789`) and create the table with `memtable = 'trie'`; set shard count by `-Dcassandra.memtable.shard.count=1` (`CassandraRelevantProperties.java:357`, read at `AbstractShardedMemtable.java:46`) so one trie receives all writes. `memtable_allocation_type: offheap_buffers` (so the trie buffers are direct, `Config.java:1223-1225`) with `memtable_offheap_space: 6144MiB` and `memtable_heap_space: 4096MiB` so the memtable-wide limits do not flush before the trie threshold. JVM: `MAX_HEAP_SIZE=8G`, `-XX:MaxDirectMemorySize=6g` (note `cassandra-env.sh:93` only adds its own value when none is given), `-XX:NativeMemoryTracking=summary`, `-Dcassandra.memtable.shard.count=1`. Table created with `durable_writes = false` to avoid commit log volume.

**B3b. Knobs.** `-Dcassandra.memtable.row_overhead_size`: unset (default threshold), `512`, `2047`. Reason: the soft threshold decides when the trie is switched; if the node's actual trie memory follows it and stays under the hard limit, claim (2) holds. The hard limit itself has no knob. Optionally `memtable_allocation_type: heap_buffers` (heap run, needs `MAX_HEAP_SIZE` of 12G or more).

**B3c. Workload.** Table `t(k blob PRIMARY KEY, v blob)` on the trie memtable. Insert partitions with a random 2000-byte key and a 1-byte value, from one client (e.g. a small Python/Java driver script or `cassandra-stress` with a user profile, `-rate threads=16`). Arithmetic: a chain node block holds at most 27 transition bytes plus a pointer in 32 bytes (`LAST_POINTER_OFFSET = BLOCK_SIZE - 4`, `InMemoryReadTrie.java`; chain behaviour not re-verified in detail), so a random 2000-byte key costs about 2000 / 27 * 32 = about 2.4 KB of buffer space; about 0.8 million such keys reach a 1861 MB threshold, about 0.2 million reach 512 MB. Heap objects per partition are small relative to the 8 GB heap. Keep writing, with the same workload, for at least 20% of keys beyond the first flush log line, to observe behaviour past the signal. Duration: minutes per run.

**B3d. Observables and instruments.** (a) Node log lines "Scheduling flush due to trie size limit reached." (`TrieMemtable.java:194`) and the flush start/complete lines; absence of `IllegalStateException` with cause `SpaceExhaustedException` (`TrieMemtable.java:205`). (b) JMX `java.nio:type=BufferPool,name=direct` `MemoryUsed` sampled every second (`jconsole`-less: `jmxterm` or `nodetool sjk mxdump`); `jcmd <pid> VM.native_memory summary` before, at, and after the first flush signal. (c) `nodetool tablestats <ks>.t`: "Memtable off heap memory used", "Memtable data size", "Memtable cell count" (fields exist in tablestats; exact names not verified). (d) `nodetool gcstats`/`jstat -gc` for heap. Not directly observable: `allocatedPos` of the single shard (private); the direct-buffer total is the proxy.

**B3e. Procedure.**
1. Copy the tree, `ant jar`, set yaml and options as in B3a, start with `bin/cassandra -f` under a log file. 2. Create keyspace (RF 1) and the table with `memtable = 'trie'`, `durable_writes = false`. 3. Start sampling (B3d b) at 1 Hz to a CSV. 4. Run the workload of B3c. 5. Note the time of the "Scheduling flush" line and the sample at that moment, the peak direct total, and the sample after the flush completes. 6. `nodetool drain` and stop the node; confirm no `CassandraDaemon` process remains (`pgrep -f CassandraDaemon`). 7. Delete `$WORK/node`; repeat for each knob value, with a fresh data directory each time. 8. Positive control: run the identical workload with `memtable_offheap_space: 512MiB` (the memtable-wide cap, a known binding cap) and show flushes occur much earlier at a direct total near that value (see B3g).

**B3f. Predictions (stated before any run).** With each knob value, the "Scheduling flush due to trie size limit reached" line appears once the single trie's buffer reaches the threshold (about 1861 / 512 / 2047 MB of `allocatedPos`), and the direct buffer total at that moment is at least the threshold and below 2^31 - 256 bytes plus other direct users (other direct usage on the node is small but not zero: not verified). After the flush completes the direct total drops. No `SpaceExhaustedException` appears in any run. Doubling the written keys beyond the threshold changes the number of flushes, not the peak per-trie buffer.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Flush signal at the threshold, peak direct total below the hard limit, no exception | claim (2) confirmed |
| Peak direct total (trie buffers) above 2^31 - 256 bytes at any time | claim wrong (would need a second trie, see controls) |
| `IllegalStateException` caused by `SpaceExhaustedException` in the log | soft guard failed to switch in time; the hard limit was reached; claim (2) refuted, claim (1) confirmed in a real node |
| No flush signal and the workload finished below the threshold | not confirmed; increase the key count |
| Direct total does not rise with the writes | the trie is not off heap in this setup; check `memtable_allocation_type` and the table's memtable class |
| In the positive control (`memtable_offheap_space: 512MiB`) flushes come early and the trie-size line is absent | memtable-wide cap binds as known; the setup measures real memory |

**B3h. Controls.** Shard count 1 so one trie takes all keys (with more shards each trie is smaller and the limit would not be approached). Same workload, different knob values, fresh data directory. The `memtable_offheap_space` control shows the harness can detect a cap that binds. A run with durable writes on is not needed. A second-trie check: SAI is not enabled on the table, so no other large trie exists.

**B4. Risks and cleanup.** Unit tier: needs up to about 2 GB direct memory (about 2 GB heap for ON_HEAP, plus headroom), on a machine with 12 GB or more free; no disk beyond the build. Cluster tier: data and logs on local disk under `$WORK/node` (at most a few GB after flush; `durable_writes = false` avoids commit log growth); one JVM of 8 GB heap and up to 6 GB direct; run on a machine with at least 16 GB free. Never build in the shared source tree. After each run stop the JVM, verify with `pgrep -f "Trie2GbLimitProbe|CassandraDaemon"` that nothing is left, and delete `$WORK`.

## C. Sources read

- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryTrie.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryReadTrie.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/TrieMemtable.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractShardedMemtable.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (memtable space defaults, lines 583-588)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/compress/BufferType.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentTrieBuffer.java`
- `/users/jason92/cassandra-5.0.9/test/unit/org/apache/cassandra/db/tries/InMemoryTriePutTest.java`
- `/users/jason92/cassandra-5.0.9/conf/cassandra.yaml`, `/users/jason92/cassandra-5.0.9/conf/cassandra-env.sh`, `/users/jason92/cassandra-5.0.9/build.xml` (grep only)

## D. Stage-4 feedback

`none yet`
