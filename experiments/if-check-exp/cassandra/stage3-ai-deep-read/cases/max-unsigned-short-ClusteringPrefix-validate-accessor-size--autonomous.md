<!-- file: cases/max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous.md -->
# FBUtilities.MAX_UNSIGNED_SHORT (clustering key length limit) — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/ClusteringPrefix.java:278` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code, 2026-10-26 |
| Estimate | `negative`. The constant is a fixed 65535-byte format limit on one clustering key, not a memory or disk budget. It bounds each key's size but not how many keys a node holds, so total usage does not follow it. |
| Ground | The limit is a hard-coded serialization constraint (lengths are written as unsigned shorts). It is not tied to any budget, and it is not configurable. Total usage is the sum over rows, which is unbounded by it. The per-key bound (<= 65535 B) is real, but it is far below a memory- or disk-significant object. |

## A. Constraint trace

**A1. The constraint.** `FBUtilities.MAX_UNSIGNED_SHORT = 0xFFFF` (65535), a `public static final int` constant, declared at `src/java/org/apache/cassandra/utils/FBUtilities.java:158`. Unit: bytes (as used here). The default is the largest value of a 16-bit unsigned length. It cannot be set through yaml, `-D` or JMX, and changing it needs a source edit and a rebuild.

**A2. What it caps.** It is a per-value and per-key size cap. It is a limit on the serialized length of a clustering value and of the clustering key sum, not a resource budget. At `ClusteringPrefix.java:278` the compared quantity is `accessor.size(v)`, the byte size of one clustering component. At `:284` it is `sum`, the total bytes of all components. The resource touched is heap or off-heap memtable space and disk, but only through the size of each key.

**A3. Mechanism.**
- `ClusteringPrefix.validate()` (`db/ClusteringPrefix.java:272-288`) loops over `getRawValues()` (declared at `:395`).
- If any non-null component is larger than 65535 bytes, it throws `InvalidRequestException` (`:278-281`).
- It then sums component sizes (`:282`), and throws the same exception if the sum exceeds 65535 (`:284-287`).
- The caller is `ModificationStatement` (`cql3/statements/ModificationStatement.java:815`, `clustering.validate()` before `addUpdateForKey`). So an INSERT/UPDATE/DELETE with an oversize clustering key is rejected with an InvalidRequestException before any memtable allocation.
- Downstream, `NativeClustering` asserts `dataSize <= MAX_UNSIGNED_SHORT` (`db/NativeClustering.java:50`) and stores the size in a short (`:55`), which is the reason for the limit.
- Related checks of the same constant: partition keys at `cql3/Validation.java:51`, `SortedTableWriter.java:169` and `QueryProcessor.java:259`.
- Bypass and overshoot: reads and other paths (for example commit log replay, streamed sstables, or batches that do not go through `ModificationStatement`) do not call this check. The message formats `dataSize()` rather than the offending size at `:280`, which is cosmetic. Nothing limits the number of clusterings per partition or rows per table.

**A4. Other consumers.** Memtable space (`memtable_heap_space`, `memtable_offheap_space`), row and cell data, indexes, key and row caches, commit log, and sstables all use the same memory and disk. They are governed by their own limits and are not controlled by this constant.

**A5. Evidence beyond the source.** none (code only).

## B. Verification solution

**B1. Claim under test.** The 65535-byte clustering limit does not bound total memory or disk usage: a node's usage grows with the number of rows written (many keys each under the limit), and the limit only rejects single keys that are too large.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tag to local disk (`rsync -a ~/cassandra-5.0.9/ /local/c/`), run `ant jar` there, and write a small `main` class (kept outside the tree) compiled against `build/classes/main` and `lib/*`. JVM options: `-Dcassandra.config=file:///local/c/conf/cassandra.yaml -Xmx1g`. Call `DatabaseDescriptor.daemonInitialization()` first.

**B2b. Knobs.** Clustering component size S in {1000, 65535, 65536, 70000} bytes; number of components N in {1, 2, 3}. These straddle the boundary at 65535 for a single value and for the sum. Set in code.

**B2c. Workload.** Build `BufferClustering` instances from `ByteBuffer.allocate(S)` repeated N times and call `validate()`. Arithmetic: S=65535, N=1 gives sum 65535 (not over); S=65535, N=2 gives sum 131070 (over, via `:284`); S=65536, N=1 trips the check at `:278`. Then a loop creating M=100000 distinct clusterings of S=1000 bytes (100 MB in total) and retaining them in a list, all of which pass `validate()`.

**B2d. Observables and instruments.** Whether `validate()` throws; heap used after `System.gc()` (`Runtime.totalMemory()-freeMemory()`, or `jcmd <pid> GC.heap_info`) at M = 10k, 50k, 100k. Direct observation of the memtable is not possible in this tier.

**B2e. Procedure.** 1) Build. 2) Run the S/N grid and record throw / no throw. 3) Run the M loop, sampling heap after each 10k. 4) Positive control: run the same loop with a hard cap that does bind, for example a `ByteBuffer`-backed list that stops at a configured count, and show the heap flat after the cap.

**B2f. Predictions.** Throws for (65536, any N) and for (65535, N>=2) and (>=32768, N=2); no throw for (1000, N<=65) and (65535, N=1). The retained heap grows linearly with M (about 1 KB per key plus overhead), and `validate()` never throws for any M.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Per-key throw only at the predicted S/N cells, heap grows linearly with M with no throw | Claim confirmed: the limit bounds one key, not the aggregate |
| Heap flat while M grows (and the control grows) | Claim refuted |
| Heap flat in the control | Control failed: not confirmed |
| `validate()` never throws in the grid | Limit not reached: not confirmed |
| Throws at S < 65535 with N=1 | Trace wrong (claim refuted) |

**B2h. Controls.** Same JVM and heap settings for all runs; `System.gc()` before each sample; the positive control above; repeat three times.

**B2i. Stage-4 audit amendments, 2026-10-26** (made before any reading; none depends on a reading; B2g is unchanged).
1. *Paths and build (B2a).* The tree is a `copy-source.sh` copy at `~/s4-b9-cp`, built once with `ant jar`; the driver (`harness/max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous/ClusterKeyDriver.java`) is compiled outside the tree against `build/classes/main`, `build/lib/jars/*` and `conf`, with `-Xmx1g` and `-Dcassandra.config=file://<tree>/conf/cassandra.yaml`. `validate()` needs no `TableMetadata` or comparator: `new BufferClustering(ByteBuffer...)` and `new ArrayClustering(byte[]...)` are enough.
2. *Boundary grid made exact (B2b, B2f).* Cells: S in {1, 1000, 32767, 32768, 65534, 65535, 65536, 70000} x N in {1, 2, 3}, plus S = 1000 with N = 65 and N = 66, plus mixed cells (65536 and 1; 65535 and 1; 65535 and 0 bytes; a null component with 65535; the empty clustering `Clustering.EMPTY` and `STATIC_CLUSTERING`). Rule from `ClusteringPrefix.java:272-288`: reject if any non-null component is larger than 65535 (message reports `dataSize()`, which is the **sum of all components**, not the offending component's size, `:280`, `:317-326`); otherwise reject if the sum is larger than 65535 (message reports the sum). Both messages read exactly `Key length of <n> is longer than maximum of 65535`. So (S=65535, N=2) is rejected through the sum branch with n = 131070, (65536, 1) through the first branch with n = 65537, and (32768, 2), (1000, 66) and (65535, 1 plus 1 byte) are rejected; (32767, 2), (1000, 65), (65535, 0 bytes) and a null component are accepted. The check is also made for `ArrayClustering` (byte[] accessor) at (65535, 1) and (65536, 1): same results.
3. *Heap numbers made explicit (B2f).* "About 1 KB per key plus overhead" is restated as a relation: with M clusterings of S bytes held in a list (a `BufferClustering`, its one-element `ByteBuffer[]`, a heap `ByteBuffer` and its `byte[]`), the heap after a full GC grows by S + overhead per key with overhead between 40 and 200 B; for S = 1000 that is 1.04 to 1.20 KB per key (104 to 120 MB at M = 100,000). The series is sampled after each 10,000 clusterings (10k to 100k), growth per step must stay within 10 percent of the mean step, and `validate()` never throws. Three JVMs repeat the series (B2h); their slopes agree within 5 percent.
4. *Aggregate part (B2c).* Besides the held list, stream M = 100,000 freshly allocated distinct clusterings of one 65535-byte component (6.55 x 10^9 bytes, 100,000 times the per-key cap) through `validate()` without holding them: prediction, all accepted, heap after a final GC below 100 MB. This shows that the check itself retains nothing and bounds nothing in aggregate.
5. *Controls (B2e.4, B2h) specified.* (a) Small-key control: the same held loop with S = 1: slope below 250 B per key, ratio of the S = 1000 slope over the S = 1 slope above 5. (b) Capped control: the same S = 1000 loop in which the list keeps only the newest 10,000 entries (a known cap): heap at M = 100k within 5 MB of heap at M = 10k, while the uncapped loop grows by more than 80 MB. Together they show the instrument tells a capped from an uncapped retention.
6. *Gap named (B2d).* The heap readings measure the driver's own list; `validate()` itself retains nothing. They show what holding that many accepted keys costs, not the memtable accounting, which only the cluster tier sees.
7. *Leftover check (B2e).* The driver's own PID is checked, not `ps | grep java` (other sessions run JVMs on the same host).

### B3. Cluster tier

**B3a. Environment and build.** One node, from the local copy built with `ant jar`. Local disk of known size (at least 20 GB free) for data, commit log and hints. `cassandra.yaml`: `memtable_allocation_type: offheap_objects`, `memtable_heap_space: 256MiB`, `memtable_offheap_space: 256MiB`, `-Xmx1g`.

**B3b. Knobs.** The clustering key size K in {100, 1000, 65535, 65536} bytes (a cql blob in a `PRIMARY KEY (pk, ck)` table); the number of rows R. The constant itself cannot be varied. Both are set from the client.

**B3c. Workload.** Table `t(pk int, ck blob, v int, PRIMARY KEY(pk, ck))`. 1) Insert one row with ck of 65536 bytes and one of 65535 bytes (driver, prepared statement, bound blob). 2) Insert R rows with K=1000 under 65535: R=1e5 (about 100 MB of keys), then 1e6 (about 1 GB). Use cassandra-stress or a driver loop. The row count and key size make the product exceed 65535 many times over, so total bytes far exceed the limit. Duration: until the inserts finish plus a flush.

**B3d. Observables and instruments.** Client errors (InvalidRequestException on K=65536). `nodetool tablestats` (memtable data size, off-heap memory used, space used live), `du -sb` on the data directory, `jcmd <pid> GC.heap_info`, sampled every 10 s during the load and after `nodetool flush`.

**B3e. Procedure.** 1) Start the node and create the keyspace and table. 2) Do the two boundary inserts and record the results. 3) Insert 1e5 rows, sample, flush, sample. 4) Insert up to 1e6 rows, repeat. 5) Positive control: set `memtable_offheap_space` small (64MiB) and show flushes triggered when that cap binds. 6) Stop the node (`nodetool drain`, kill) and check with `ps` that nothing is left.

**B3f. Predictions.** The K=65536 insert fails with "Key length of ... is longer than maximum of 65535"; K=65535 succeeds. Memtable and disk usage rise roughly in proportion to R x K (about 100 MB at 1e5, about 1 GB at 1e6 for disk before compression), far above 65535 bytes, with no error from this check.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Boundary behaviour as predicted, and usage keeps growing with R beyond 65535 bytes | Claim confirmed |
| Usage plateaus near 65535 bytes total | Claim refuted |
| Memtable usage flat at the memtable cap in the control while disk keeps growing | Positive control bound (the memtable cap does bound memtable usage) |
| Control does not flush at the small cap, or load never exceeds the limit | Not confirmed |

**B3h. Controls.** Same data and JVM settings across runs; compare with the control run; clear the data directory between runs; repeat the K=65535 insert with the same payload.

**B3i. Stage-4 audit amendments, 2026-10-26** (made before any reading; none depends on a reading; B3g is unchanged).
1. *Paths and node set-up (B3a).* No `/local` path exists here: the tree is `~/s4-b9-cp` (`copy-source.sh` + `ant jar`), a copy of its `conf/` lives on tmpfs `/dev/shm/s4-b9-cp/node` with data, commitlog, hints and saved_caches there (tmpfs bytes stand for disk bytes; 126 GB free). Port slot 6: node address 127.0.6.1, JMX 7160, native 9042 on that address. Extra yaml lines beyond B3a: `memtable_cleanup_threshold: 0.99` (otherwise the pool limit is never reached), `auto_snapshot: false` (drop must not snapshot), `commitlog_total_space: 1GiB`, `native_transport_timeout: 30s`, `write_request_timeout: 20000ms`, `num_tokens: 16`. Heap `MAX_HEAP_SIZE=1G` (B3a), `ulimit -n 100000`. Pools: `memtable_heap_space` = `memtable_offheap_space` = 256 MiB in life 1; the control restarts the node with both at 64 MiB (life 2).
2. *Schema and keys (B3c).* `ks.t_<arm>(pk int, ck blob, v int, PRIMARY KEY (pk, ck))`, a fresh table per arm. Rows are spread over 100 partitions (pk = i mod 100) so that no partition is a single giant one; ck = an 8-byte big-endian counter plus seeded random bytes up to K bytes (distinct and incompressible), 32 requests in flight, protocol 4, consistency ONE, prepared statement.
3. *Arms (B3b, B3c).* Life 1: boundary precheck (below), then K = 100 with R = 100,000 (10 MB of key bytes), K = 1000 with R = 100,000 (100 MB), K = 1000 with R = 1,000,000 (1 GB, above the 256 MiB pool), K = 65535 with R = 10,000 (655 MB) and K = 65536 with R = 10,000 (every write rejected). Life 2 (the known-binding control, B3e.5): the K = 65535, R = 10,000 workload again at 64 MiB pools. "Roughly proportional" is bounded in item 6.
4. *First-trigger precheck (B3e.2).* Before any arm, on single-ck table: 5 inserts at K = 65535 must succeed and 5 at K = 65536 must fail with exactly `Key length of 65536 is longer than maximum of 65535`; on a two-column table `(pk, c1, c2)`: 3 inserts (32768, 32767) succeed, 3 inserts (32768, 32768) fail with the same text (sum branch, `:284`), 3 inserts (70000, 10) fail with `Key length of 70010 is longer than maximum of 65535` (first branch, `dataSize()` = the sum). If any of these differs, the run stops (B3g row 3: the traced boundary is wrong).
5. *Control (B3e.5, B3h) restated.* The pool control uses the same workload as the K = 65535 arm, so only the pool changes. The key bytes of `offheap_objects` rows sit in the off-heap pool, hence both pools are lowered together.
6. *Numbers for B3f.* Data+Index bytes after the flush (Data.db plus Index.db; Index.db repeats the keys) for K = 65535 and for K = 1000 with R = 1,000,000 are between 1.0 and 3.0 times R x K; Data+Index grows in the order (K=100, R=1e5) < (K=1000, R=1e5) < (K=1000, R=1e6) and (K=65535) > (K=1000, R=1e5). Plateau: at 256 MiB the arms with 1 GB and 655 MB of key bytes each log at least one `MEMTABLE_LIMIT` flush, the logged off-heap usage at most 320 MiB; the 100 MB arm logs none; at 64 MiB the K = 65535 arm logs at least one with usage at most 80 MiB; the ratio of the first `MEMTABLE_LIMIT` off-heap usage at 256 MiB over that at 64 MiB is between 2.5 and 6. K = 65536: 10,000 of 10,000 rejected, the table directory unchanged, the memtable empty.
7. *Observables (B3d).* Real resources: sstable bytes on tmpfs, `RssAnon` of the node (`/proc/<pid>/status`, not `VmRSS`), the node's own flush log lines (`Enqueuing flush of ..., Reason: MEMTABLE_LIMIT, Usage: ...`); `nodetool tablestats` (its "Memtable data size" may omit key bytes) is context only. `jcmd GC.heap_info` is replaced by the log lines, because the key bytes are off-heap malloc. Sampling every 2 s.
8. *Probe outside B3g (informational; it does not change any conclusion row).* The text of A3 says other paths skip the check. In the source, `ModificationStatement.java:815` is reached only through `addUpdates` (plain statements, batches and range deletes by slice: the slice branch `:762-787` has no `validate()` at all), and the conditional path (`buildCasRequest`, `:573`) takes the clustering from `createClustering` without calling `validate()`. So "batches" are not a bypass (they use `addUpdates`), and the conditional write is a candidate. After the main arms (life 2), on a fresh table: (a) a plain insert with a 65536-byte ck, expected rejected with the exact text; (b) `INSERT ... IF NOT EXISTS` with a 65536-byte ck, expected **not** rejected with that text at statement level (it may fail later, for example on `NativeClustering.java:50`'s `assert dataSize <= MAX_UNSIGNED_SHORT`, which would be a failed write in the log; whichever happens is recorded); (c) `DELETE ... WHERE pk = ? AND ck > <70000-byte value>`, expected not rejected with that text. Recorded as a side finding, outside the verdict. Also: `PartitionKeySingleRestrictionSet.java:67` calls the same `validate()` for components of a composite partition key, so `ClusteringPrefix.validate` is not clustering-only.
9. *Leftover check (B3e.6).* The node is stopped by its PID file/`stopdaemon` and checked by PID; no `pkill`.

**B4. Risks and cleanup.** The disk is limited to the 20 GB local volume (largest run about 1 GB x replication 1). Keep data, commit log and hints on local disk, never on shared storage. Stop the node, kill any cassandra-stress or driver processes, check with `ps -ef | grep -i cassandra`, and delete the data directories and the copied tree.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/ClusteringPrefix.java (lines 230-330)
- src/java/org/apache/cassandra/db/NativeClustering.java (lines 40-60)
- src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java (lines 800-822)
- src/java/org/apache/cassandra/cql3/Validation.java (lines 45-58)
- src/java/org/apache/cassandra/utils/FBUtilities.java (lines 150-160)
- grep results for MAX_UNSIGNED_SHORT across src/java

## D. Stage-4 feedback

Stage-4 run 1, 2026-10-26/27 (pc07), results: `stage4-runtime-verification/results/max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous.md`. Both tiers **Confirmed - does not cap** (unit B2g row 1; cluster B3g row 1, row 4 for the control). Outcome class: true negative.

- Unit: the grid throws exactly where a component or the sum exceeds 65535, with the message reporting the sum of all components; held clusterings cost S + 116.7 B each (no bound below `-Xmx`); 6.55 x 10^9 bytes validated without a rejection; controls (S = 1, capped list) moved as predicted.
- Cluster: K = 65536 rejected 10,000 of 10,000 with the exact text; K = 65535 and the two-component cases as predicted; 1 GB of 1000-byte keys and 655 MB of 65535-byte keys accepted, the logged off-heap memtable plateau followed the pool (254.0 MiB at 256 MiB pools, 64.0 MiB at 64 MiB, ratio 3.97). Data+Index at K = 65535 was 3.005 x R x K (Index.db repeats the clustering, 2.00 x), 0.17 percent above the audit bracket of B3i.6.
- Notes for stage 3: (1) A3's "batches" are not a bypass (`addUpdates` validates); the real skips are `INSERT ... IF NOT EXISTS` (`ModificationStatement.java:573`; with `offheap_objects` it fails at `NativeClustering.java:50` in the mutation stage and the client times out after 20 s) and range deletes by slice (`:762-787`; a 70000-byte bound is accepted and the later flush fails in `StatsMetadata` serialization, `ByteBufferUtil.java:366`). (2) The first-branch message reports `dataSize()`, the sum, not the oversize component. (3) `PartitionKeySingleRestrictionSet.java:67` also calls `validate()` (composite partition keys). Amendments: B2i, B3i (2026-10-26).

Citation checks (pinned `cassandra-5.0.9`): `ClusteringPrefix.java:272-288` and `:317-326`, `NativeClustering.java:50`, `ModificationStatement.java:573, 753-787, 815`, `FBUtilities.java:158`, `PartitionKeySingleRestrictionSet.java:67`, `ByteBufferUtil.java:366` hold.
