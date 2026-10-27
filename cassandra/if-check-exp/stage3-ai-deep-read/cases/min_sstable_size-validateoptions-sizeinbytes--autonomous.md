# min_sstable_size — verification solution  <!-- file: cases/min_sstable_size-validateoptions-sizeinbytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`Controller.java:613`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/unified/Controller.java#L613) (`if (sizeInBytes >= limit)` in `Controller.validateOptions`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the line is a schema-time sanity check on the relation between two options; it bounds neither heap, off-heap nor disk. The option it validates only changes how many shards (and so how many SSTables) UCS cuts, which shifts per-SSTable overhead indirectly. |
| Ground | The check runs once, in `validateOptions`, and throws or passes; it does not look at any usage quantity. At runtime `min_sstable_size` is only a divisor used to pick a shard count (`Controller.java:268-270`), so total bytes on disk are unchanged by it; it can alter SSTable count, and thereby per-SSTable memory structures, but nothing compares that memory or disk to a limit. |

> **Link rule.** Declaration and if statement are linked below.

## A. Constraint trace

**A1. The constraint.** UCS compaction sub-option `min_sstable_size` (a per-table configuration entry in the `compaction` map; cluster default via a JVM property). Declared at [`Controller.java:59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/unified/Controller.java#L59) (`MIN_SSTABLE_SIZE_OPTION = "min_sstable_size"`). The default string is read at `Controller.java:61` from `CassandraRelevantProperties.UCS_MIN_SSTABLE_SIZE` (`unified_compaction.min_sstable_size`, built-in `"100MiB"`, `CassandraRelevantProperties.java:610`). The limit being checked at line 613 is derived from a second option, `target_sstable_size` (`Controller.java:80`; default `UCS_TARGET_SSTABLE_SIZE.getSizeInBytes()` at `Controller.java:81-82`, property `unified_compaction.target_sstable_size`, built-in `"1GiB"`, `CassandraRelevantProperties.java:615`; `getSizeInBytes` at `CassandraRelevantProperties.java:856-862` uses the system property if set, else the default). Floor for the target is `MIN_TARGET_SSTABLE_SIZE = 1L << 20` (`Controller.java:83`). The factor is `INVERSE_SQRT_2 = Math.sqrt(0.5)` (`Controller.java:169`).
Unit: bytes, written as a human-readable string (parsed by `FBUtilities.parseHumanReadableBytes`, `utils/FBUtilities.java:1089-1092`). `0` disables the feature (comment at `Controller.java:608`). Default limit with the default target: ceil(1073741824 x sqrt(0.5)) = 759250125 bytes (about 724 MiB; recompute in JShell before use). The default min (100MiB) is below it.
Setting: per table through `CREATE/ALTER TABLE ... WITH compaction = {'class': 'UnifiedCompactionStrategy', 'min_sstable_size': '...'}` (no node restart; the strategy is rebuilt with new options, `Controller.fromOptions`, `Controller.java:436-438`); the JVM-property defaults are read in static initializers (`Controller.java:61`, `81-82`), so changing them needs a restart. JMX settability: not verified.

**A2. What it caps.** Nothing in memory or disk directly. The compared operand is `sizeInBytes`, the parsed option value (`Controller.java:607`), against `limit = ceil(targetSSTableSize * INVERSE_SQRT_2)` (`Controller.java:612`). Both are configuration values, not measured usage. The option's runtime role is a lower bound on target SSTable size in the shard-count decision (A3 step 5), which affects SSTable count and size, not total data volume.

**A3. Mechanism.**
1. `UnifiedCompactionStrategy.validateOptions` calls `Controller.validateOptions` (`UnifiedCompactionStrategy.java:103`); this is the only caller found by grep in `src/java` (the `Controller.fromOptions` path at `Controller.java:436-438` re-parses the values without re-checking them).
2. `Controller.validateOptions` (`Controller.java:463`) starts `targetSSTableSize` at `DEFAULT_TARGET_SSTABLE_SIZE` (`Controller.java:492`; the earlier trace said 491, which is the preceding comment line), then overrides it from the `target_sstable_size` option (`Controller.java:493`), rejecting values below `MIN_TARGET_SSTABLE_SIZE` (`Controller.java:504-510`) or at/above Long.MAX_VALUE (`Controller.java:499-503`).
3. Line 602 removes `min_sstable_size` from the option map; if absent (`s == null`) nothing is checked, so the JVM-property default is never validated against the target.
4. Line 607 parses `sizeInBytes`; line 609 throws if negative (comment at 608: zero disables). Line 612 computes `limit`. **The check is line [613](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/unified/Controller.java#L613): `if (sizeInBytes >= limit)`**, which throws `ConfigurationException` ("should be less than 70% of the targetSSTableSize", lines 614-617). A `NumberFormatException` is rewrapped at lines 619-625 (`Controller.java:619-625`).
5. Runtime use of the stored value: `Controller.getNumShards` (`Controller.java:264`): if `minSSTableSize > 0` (268), `count = localDensity / minSSTableSize` (270); if `!(count >= baseShardCount)` (274) the shard count becomes `min(highestOneBit((int) count | 1), baseShardCount & -baseShardCount)` (279) and returns (287), otherwise the target-size based logic applies. Callers: flush path `UnifiedCompactionStrategy.java:274` and compaction path `UnifiedCompactionTask.java:58`.
Outcomes: at or above the limit, the ALTER/CREATE is rejected and the old options remain; below it, accepted. Bypasses: absent option plus a `-Dunified_compaction.min_sstable_size` default that is above the limit for a small per-table target is not validated (step 3); a `-D` target and default min are evaluated independently. Overshoot is not a meaningful notion because the check compares two configured numbers.


The check itself is the if statement at [`Controller.java:613`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/unified/Controller.java#L613).

**A4. Other consumers.** Total disk use is set by ingested data, compaction space amplification, snapshots, and hints/commitlog; heap and off-heap by memtables (`memtable_heap_space`/`memtable_offheap_space`), bloom filters, index summaries, key/chunk caches, and per-SSTable reader objects. `min_sstable_size` influences only the number and size of SSTables UCS writes and therefore per-SSTable overhead; none of those are governed by it. (`UnifiedCompactionStrategy.md` lines 424-440 describe the intent: SSTable count versus on-heap per-sstable structures.)

**A5. Evidence beyond the source.** In-tree doc `src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.md` (`min_sstable_size` entry at line 440; `base_shard_count` text at line 424). Unit test `test/unit/org/apache/cassandra/db/compaction/unified/ControllerTest.java` lines 622-648 exercises zero, negative and over-limit values. No external issue cited.

## B. Verification solution

**B1. Claim under test.** `min_sstable_size` does not cap memory or disk: (a) the validation at `Controller.java:613` only rejects a configuration where min >= ceil(target x sqrt(0.5)) and measures no usage; (b) varying `min_sstable_size` below the limit changes shard/SSTable count but leaves total on-disk bytes for the same data essentially unchanged, and no heap or disk limit is enforced as a result. The claim would be wrong if total disk or a memory region tracked `min_sstable_size` proportionally for the same dataset, or if a value below the limit were rejected / above it accepted.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/cass/`), `cd $WORK/cass && ant jar` (and `ant build-test` for the test classes). Write a JUnit class in package `org.apache.cassandra.db.compaction.unified` (so package-private `Controller.MIN_SSTABLE_SIZE_OPTION`, `TARGET_SSTABLE_SIZE_OPTION`, `INVERSE_SQRT_2` are visible), placed in the local copy only, modelled on `ControllerTest.java:622-648`. Run: `ant testsome -Dtest.name=<Class> -Dtest.methods=<m>`. JVM options: default test options.

**B2b. Knobs.** `min_sstable_size` option value `m` and `target_sstable_size` option value `T` passed in the options map to `Controller.validateOptions`. T in {1MiB (floor), 2MiB, 256MiB, 1GiB (default)}. For each, m at limit-1, limit, limit+1, 0, -1, and a non-numeric string, where limit = ceil(T x sqrt(0.5)) (T=1GiB: 759250125; 256MiB: 189812532; 2MiB: 1482911; 1MiB: 741456, computed offline, recheck in JShell). Second knob for the runtime half: `-Dunified_compaction.min_sstable_size` / `target_sstable_size` set before class load, in separate JVM runs.

**B2c. Workload.** No data. For validation: call `Controller.validateOptions(map)` with each combination. For the shard-count half: construct a `Controller` as `ControllerTest` does (via `Controller.fromOptions`) with `base_shard_count=4`, `m` in {0, 10MiB, 100MiB, 700MiB}, T=1GiB, and call `getNumShards(d)` for densities d in {50MiB, 400MiB, 3GiB, 100GiB}. Arithmetic: with m=100MiB, d=400MiB gives count=4, not below baseShardCount so the target logic applies; d=150MiB gives count=1.5, below 4, so shards = min(highestOneBit(1|1)=1, 4&-4=4) = 1.

**B2d. Observables and instruments.** Exception thrown or not (with message); returned shard count from `getNumShards`. Implied SSTable size = d / shards. Total bytes d is an input, so unit tier cannot observe real disk or heap; that is for the cluster tier. Also observe heap via `Runtime` before/after only as a sanity control (it should not move, since nothing is allocated proportional to m).

**B2e. Procedure.** 1) Build. 2) Run the validation matrix and record accept/reject per (T, m). 3) Run the shard-count matrix per (m, d). 4) Repeat step 2 with no `min_sstable_size` in the map while `-Dunified_compaction.min_sstable_size=2GiB` is set and `target_sstable_size=1MiB` in the map: expect acceptance (bypass, A3 step 3), then call `getNumShards` to see the unvalidated min in effect. 5) Positive control: same harness, `Controller.validateOptions` with `target_sstable_size=512KiB`, expecting rejection at `Controller.java:504-510`, showing the harness detects an enforced bound.

**B2f. Predictions.** m = limit-1 accepted; m = limit and limit+1 rejected with the "70%" message; m = 0 accepted; m = -1 rejected with the "greater than or equal to 0" message; non-numeric rejected. Shard counts non-increasing as m grows for fixed d; for m=0 the target-size logic alone decides. Bypass case (step 4) accepted. Heap sanity shows no m-proportional change.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Matrix matches B2f | Mechanism is as traced: a configured-values check, no usage quantity involved. |
| A value at or above limit accepted, or below limit rejected | Trace of line 612-613 wrong (limit formula, rounding, or ordering); amend A3. |
| Shard count or sstable size derived from m changes total input bytes (the harness input d) | Impossible by construction; indicates harness error. |
| Bypass case rejected | A3 step 3 wrong (default is validated somewhere else). |
| Positive control (target below floor) not rejected | Harness does not exercise `validateOptions`; discard run. |
| Limit never reached because options never parsed | Not confirmed. |

**B2h. Controls.** Positive control: target floor rejection (B2e step 5). Negative control: m=0 (feature disabled) versus m=10MiB, to separate the option's effect from base logic. Fresh JVM per `-D` setting.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from a local copy of the tag (`ant jar`), run from a local-disk directory with its own `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` (all under `$WORK/node1`, on a disk with at least 40 GiB free). JVM: `-Xms4G -Xmx4G` (MAX_HEAP_SIZE 4G, fixed so heap lines are comparable), `memtable_allocation_type: heap_buffers`, `memtable_heap_space: 512MiB`, `memtable_offheap_space: 512MiB`, `concurrent_compactors: 2`. Client: cqlsh and `tools/bin/cassandra-stress` from the same build.

**B3b. Knobs.** Per-table compaction map on three identical tables: `{'class':'UnifiedCompactionStrategy','target_sstable_size':'64MiB','base_shard_count':'4','min_sstable_size':M}` with M in {0, 8MiB, 40MiB (just under the 64MiB target's limit ceil(67108864 x sqrt(0.5)) = 47453133 bytes), 47453134B (expected to be rejected by ALTER)}. Set with `ALTER TABLE`. Second experiment (positive control): `memtable_heap_space` 128MiB versus 512MiB in `cassandra.yaml` (restart).

**B3c. Workload.** `cassandra-stress write n=20000000 -col size=FIXED(200) n=FIXED(5) -schema keyspace=ks compaction(strategy=UnifiedCompactionStrategy) -rate threads=32` equivalent per table, so roughly 20 M x ~1 KB = about 20 GB raw before compression; reduce n to keep each table under about 6 GB on disk. Same keyset and seed for each M. After writing, `nodetool flush` and `nodetool compact` or wait until `nodetool compactionstats` is idle (about 30 min cap). Arithmetic: with 64MiB target and base shards 4, L0 flushes of a few hundred MiB reach the `count < baseShardCount` branch for M=40MiB only when density per shard is below 160MiB, so M=40MiB and M=0 should yield different SSTable counts for small flushes; this is the only effect expected.

**B3d. Observables and instruments.** Disk: `du -sb` of the table data directory and `nodetool tablestats ks.t` (Space used (live), SSTable count, Bloom filter off heap memory, Index summary off heap, Compression metadata off heap, Memtable data size). Heap: `jcmd <pid> GC.heap_info` and `nodetool info` (heap used) sampled every 10 s during load and after compaction. Off-heap: `nodetool tablestats` off-heap fields. Log: `grep "Shard count" debug.log` with `logger.debug` enabled for `org.apache.cassandra.db.compaction.unified.Controller` (log lines from `Controller.java:280-285`). Not directly observable: JVM-internal per-SSTable reader object sizes (inferred from SSTable count).

**B3e. Procedure.** 1) Copy source, build, configure. 2) Start node, create the three tables (M=0, 8MiB, 40MiB). 3) Try `ALTER TABLE ... 'min_sstable_size':'47453134B'` and expect `ConfigurationException`; note old options remain (`DESCRIBE`). 4) For each table run the same stress write with identical seed, flush, let compaction settle, record B3d. 5) Record SSTable count and live space per table. 6) Positive control: restart with `memtable_heap_space` 128MiB, repeat one table's write, record Memtable heap in `tablestats`/`jcmd`. 7) Stop node (`nodetool drain`, kill), remove `$WORK/node1`, confirm no java process left.

**B3f. Predictions.** Step 3 rejected. Live space per table within a small percentage of each other across M (same data), because M does not change data volume. SSTable count may differ by M (M=0 or 8MiB produce the same or more shards at low densities; M=40MiB fewer), so bloom-filter and index-summary off-heap totals scale roughly with SSTable count but with no bound at any value tied to M. Heap used stays under the 4G ceiling for all M and does not track M. Positive control: peak memtable heap at 128MiB limit is clearly lower than at 512MiB for the same workload.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Live disk and heap/off-heap indistinguishable across M beyond SSTable-count effects; control moves | Claim confirmed (usage does not follow the constraint). |
| Disk or a memory region scales with M or is capped at a value derived from M | Claim refuted. |
| 47453134B accepted, or 40MiB rejected | Limit arithmetic or ordering in A3 wrong. |
| Positive control (memtable heap) does not move between 128MiB and 512MiB | Workload too small or instruments wrong; not confirmed. |
| SSTable counts identical for all M | Min size branch never reached at these densities; not confirmed, increase flush size or lower base_shard_count differences. |

**B3h. Controls.** Positive control: memtable heap space cap (known to bind). Same seed, same hardware, one table at a time to avoid compaction interference; compression and caches the same; warm-up identical; repeat each M twice.

**B4. Risks and cleanup.** Unit tier: runs in local copy only; delete `$WORK/cass` after. Cluster tier: keep all directories under `$WORK/node1` on local disk of known size (>= 40 GiB free; abort if free space < 10 GiB); never write to the shared source tree; no hints or commit log on shared storage. After each run `nodetool drain`, kill the process, `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` must return nothing, then delete the data directories.

## C. Sources read

- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/INSTRUCTIONS.md
- .../agent-docs/playbook-autonomous.md
- .../agent-docs/_TEMPLATE-autonomous.md
- .../agent-in/137.md
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/unified/Controller.java (lines 55-64, 78-90, 165-172, 236-330, 428-456, 463-470, 488-515, 595-625)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (grep, lines 610, 615, 856-874)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java (lines 103, 262-280)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/unified/UnifiedCompactionTask.java (lines 50-64)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.md (lines 420-450)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/FBUtilities.java (lines 1089-1092)
- /users/jason92/cassandra-5.0.9/test/unit/org/apache/cassandra/db/compaction/unified/ControllerTest.java (grep, lines 622-648)

## D. Stage-4 feedback

`none yet`
