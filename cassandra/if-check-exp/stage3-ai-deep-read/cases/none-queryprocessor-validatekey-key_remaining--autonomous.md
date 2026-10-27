<!-- file: cases/none-queryprocessor-validatekey-key_remaining--autonomous.md -->
# none (empty partition-key test) — verification solution

| Field | Value |
|---|---|
| Entry pointer | [`QueryProcessor.java:251`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L251) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the line is a validity test (key is non-null and non-empty), not a limit; it bounds no memory- or disk-significant quantity. |
| Ground | The test rejects only zero-length (or null) keys, so it can only reduce usage by a zero-byte object; there is no threshold that scales with resource use. The nearest real limit (the 65535-byte key length check two statements below) caps one key's size, not total heap or disk. |

## A. Constraint trace

**A1. The constraint.** There is no resource constraint at the entry point. [`QueryProcessor.java:251`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L251) is `if (key == null || key.remaining() == 0)`, which throws `InvalidRequestException("Key may not be empty")` (QueryProcessor.java:253). The constant 0 is a literal, not a configuration entry, JVM property or runtime-queried value; nothing is declared, derived or settable. (The earlier trace followed the adjacent size check; that was a different line, see below.) Nearest real limit, for reference only: `FBUtilities.MAX_UNSIGNED_SHORT`, a compile-time constant, declared at [`FBUtilities.java:158`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/FBUtilities.java#L158) (`0xFFFF`, unit bytes, not settable without a rebuild), compared at QueryProcessor.java:259 and rejected at lines 261-262. The comment at QueryProcessor.java:258 gives its reason: the key must fit `writeWithShortLength`'s 2-byte unsigned length prefix. It is a format limit on one key, not a memory or disk budget.

**A2. What it caps.** Nothing in memory or disk. The quantity compared is `key.remaining()` (bytes in the serialized partition key) against the literal 0, to reject a key that cannot identify a partition. Same-named check for the other write path exists at cql3/Validation.java:47-48 (not verified beyond reading those lines).

**A3. Mechanism.** [`if (key == null || key.remaining() == 0)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L251) in `validateKey` (QueryProcessor.java:249). True: throws "Key may not be empty" (253) and the statement fails with an invalid-request error before any mutation or read is built. False: continues to the UNSET check (255-256), then the size check (259-263), then returns. Callers verified: SelectStatement.java:732 (per key, before `decorateKey`), ModificationStatement.java:374 (`buildPartitionKeyNames`) and TriggerExecutor.java:209 (per mutation key from triggers). Bypass: ModificationStatement.java:781 and 802 call `Validation.validateKey(metadata(), key)` instead, which has its own equivalent empty test (Validation.java:47-48), so that path does not pass through line 251. Overshoot: not applicable, there is no quantity to overshoot. Note a clustering column or non-key value may be empty; this test concerns only the partition key.


The check itself is the if statement at [`QueryProcessor.java:251`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L251).

**A4. Other consumers.** Heap and disk for partition keys are consumed by every accepted key (memtable, key cache, index summary, SSTable index/data), governed by memtable and cache settings, not by this test. The only per-key size cap is the 65535-byte check at line 259; individual values are separately governed by `max_value_size` (Config.java:310, default "256MiB").

**A5. Evidence beyond the source.** none.

## B. Verification solution

**B1. Claim under test.** The empty-key check at QueryProcessor.java:251 does not bound memory or disk: it rejects only zero-length keys and leaves node usage unchanged, while usage grows with the number and size of accepted non-empty keys and is capped (per key) only by the 65535-byte check. It is falsified if rejecting or accepting empty keys measurably changes heap, off-heap or disk, or if any resource-scaled threshold is found on that line.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant; copy the tree to local disk (never build in the shared tree), `ant jar` (or `ant build-test`), then a JUnit test under a local copy of `test/unit/org/apache/cassandra/cql3/` run with `ant testsome -Dtest.name=<Class> -Dtest.methods=<m>`. JVM options: defaults from build.xml; add `-Xmx512m` for a stable heap baseline.

**B2b. Knobs.** Key length in bytes passed to `QueryProcessor.validateKey`: null, 0, 1, 65535, 65536. These bracket the empty test (0 vs 1) and the neighbouring size limit (65535 vs 65536, the positive control). Set in the test code; no configuration involved.

**B2c. Workload.** Call `validateKey` with `ByteBuffer.allocate(n)` for each n above; then a loop of 1,000,000 calls with an empty buffer and with a 1-byte buffer, to see whether repeated rejection/acceptance retains anything. Control: 1000 calls with 65535-byte and 65536-byte buffers.

**B2d. Observables and instruments.** Outcome per call (returns or throws, exception message); used heap after `System.gc()` before and after each loop via `Runtime.totalMemory()-freeMemory()` or a JMX `MemoryMXBean` read; optionally JFR allocation profile. The check's operand (`remaining()`) is read directly. Cannot be observed: disk, because no node runs.

**B2e. Procedure.** 1) Build. 2) Run the five-length matrix and record outcomes. 3) Run each 1,000,000-call loop with GC before/after readings, three repetitions. 4) Run the 65535/65536 control. 5) Clean the local copy.

**B2f. Predictions.** null and 0: throw "Key may not be empty". 1 and 65535: return. 65536: throw "Key length of 65536 is longer than maximum of 65535". Retained heap after the loops is flat (within GC noise) for both empty and 1-byte keys; empty-key rejection retains no allocation beyond transient exception objects.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Outcomes match B2f and retained heap flat for empty and 1-byte loops while the 65535/65536 flip is the only size-dependent change | Claim confirmed: line 251 is a validity test; the only bound is the key-length format limit |
| Retained heap grows with the number of empty-key calls, or empty vs 1-byte differ in retention | Claim refuted: the check affects usage |
| Empty key accepted, or 0-length not rejected | Trace wrong (line is not the empty test) |
| 65536 is accepted, or 65535 rejected | Positive control failed; matrix not trustworthy, not confirmed |
| Loops too short to see any heap signal and the control did not move | Not confirmed; lengthen or enlarge |

**B2h. Controls.** The 65535/65536 pair shows the harness can detect a cap that binds; the 1-byte key shows the non-empty path under identical call overhead; GC before every reading; the same JVM and warm-up for all cases.

### B3. Cluster tier

**B3a. Environment and build.** One node (second optional), JDK 11, built from a local copy with `ant jar`. Data, commit log and hints directories on a local disk of known size (for example 5 GiB free); `-Xms1g -Xmx1g`. Default `cassandra.yaml` otherwise; `cqlsh` as client.

**B3b. Knobs.** Key size and emptiness in the client workload: empty blob key, 1-byte, 65535-byte, 65536-byte. Fixed configuration (nothing at a boundary, since the line has no config); the contrast knob is `memtable_heap_space` (e.g. 64MiB vs 256MiB) as a positive control for a cap known to bind heap, set in `cassandra.yaml` with a restart.

**B3c. Workload.** Table `ks.t (k blob PRIMARY KEY, v blob)`. (1) `INSERT INTO ks.t (k, v) VALUES (0x, 0x01)` and `SELECT ... WHERE k = 0x` repeated 100,000 times by a driver script; expect rejection each time. (2) 100,000 inserts with 1-byte distinct keys. (3) A smaller run with 65535-byte then 65536-byte keys (about 1000 each; 1000 x 65535 B is roughly 62 MiB of key data). (4) Control run: 200,000 inserts of 1 KiB values with distinct 8-byte keys under each `memtable_heap_space` value. Duration: minutes per step.

**B3d. Observables and instruments.** Heap used and memtable data size via `nodetool info` and `nodetool tablestats ks.t` (Memtable data size, off-heap, SSTable space used); `jstat -gc <pid>` every 5 s; `du -sb` on the data and commitlog directories; client error counts and messages. Cannot be observed: per-request transient allocation, except via JFR.

**B3e. Procedure.** 1) Start node, create schema, record baseline heap/disk. 2) Run workload step 1; read instruments after, flush with `nodetool flush`, read again. 3) Step 2, then step 3. 4) Step 4 at both `memtable_heap_space` values (restart between). 5) `nodetool drain`, stop the node, verify no Cassandra process remains (`pgrep -f CassandraDaemon`), delete data directories.

**B3f. Predictions.** Step 1: 100,000 rejections ("Key may not be empty"), no new rows, memtable data size and disk unchanged from baseline within noise. Step 2: memtable and disk grow in proportion to row count. Step 3: 65535-byte keys accepted and grow memtable and disk by about key bytes times count; 65536-byte keys rejected with the "longer than maximum of 65535" message and add nothing. Step 4: memtable heap use plateaus near the configured `memtable_heap_space` (flushes occur) and differs between the two values; this is the contrasting cap.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Empty-key step leaves heap, memtable size and disk flat while step 4 moves with `memtable_heap_space` | Claim confirmed: empty-key test does not govern usage; the control cap does |
| Usage moves with the empty-key workload (growth or shrink) | Claim refuted |
| Any empty key accepted | Trace wrong |
| Step 4 shows no change between the two `memtable_heap_space` values | Positive control failed: not confirmed |
| Step 3 shows 65536-byte keys accepted | Neighbouring limit not as traced; report separately |
| Empty-key step too short to see the baseline noise | Not confirmed; lengthen |

**B3h. Controls.** Baseline reading before each step; an identical workload with 1-byte keys (proves the driver and instruments register growth); the `memtable_heap_space` contrast; restart and flush before each reading to remove memtable carry-over; same JVM flags throughout.

**B4. Risks and cleanup.** Disk: step 3 and step 4 write at most a few hundred MiB, to local directories of known size; never place data on shared storage. Heap pressure from 65535-byte keys is bounded by the small count. Leftover processes: stop the node and any driver, then check `pgrep -f CassandraDaemon` and `pgrep -f cqlsh` return nothing. Remove the local source copy, data, commitlog and hints directories, and the JUnit output.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java (lines 235-269)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/FBUtilities.java (line 158, via grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Validation.java (lines 40-60)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java (lines 725-735)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java (lines 368-377; callers at 781 and 802 via grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/triggers/TriggerExecutor.java (lines 205-211)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (line 309-310)

## D. Stage-4 feedback

`none yet`
