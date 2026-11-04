# repair_session_space heap-pressure warning threshold (maxMemory / 4 MiB) — verification solution  <!-- file: cases/repair_session_space-setrepairsessionspaceinmib-sizeinmib-2--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:4096`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4096) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: the check only logs a warning when the requested `repair_session_space` exceeds a quarter of max heap; it rejects or clamps nothing, so the value stored (and the Merkle-tree memory budget derived from it) is not bounded by this check. |
| Ground | The `else if` branch has no effect other than `logger.warn`; the value is stored unconditionally at line 4100. The only hard bound in the method is the `< 1` rejection (line 4093), a different branch. Memory use is shaped by `ValidationManager.createMerkleTrees`, which uses the stored value with no heap-fraction ceiling. |

**Type:** non-config (runtime-queried + hard-coded constant). The compared bound is `Runtime.getRuntime().maxMemory() / (4 * 1048576)`: a runtime-queried heap size and the numeric literals `4` and `1048576`. The compared operand `sizeInMiB` is the argument of a JMX setter (value of the yaml entry `repair_session_space` once set at runtime). Constant rule applies: literals take part, so not a skip.

## A. Constraint trace

**A1. The constraint.** Name: heap-pressure warning threshold for `repair_session_space`, `maxMemory/(4*1048576)` MiB (25% of max heap in MiB). Kind: runtime-queried (`Runtime.maxMemory()`) with hard-coded literals `4` and `1048576` (no named constant). Declared inline at [`DatabaseDescriptor.java:4096`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4096). Unit: MiB. Default: derived from the JVM max heap (-Xmx); not independently settable. The value it checks, `repair_session_space`, is a yaml entry ([`Config.java:208`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L208), commented out in `conf/cassandra.yaml:840`), default `max(1, maxMemory/(16*1048576))` MiB (1/16 of heap) computed at `DatabaseDescriptor.java:609-610`; changeable at runtime through the `ActiveRepairService` MBean `setRepairSessionSpaceInMiB` (`ActiveRepairService.java:334-345`), no restart. The same 25% test also exists at startup (`DatabaseDescriptor.java:614-615`, warn only) and in the setter at 4096 (this target).

**A2. What it caps.** Nothing itself. The guarded quantity is heap used by Merkle trees during validation compaction (on-heap), whose budget is `repair_session_space`. The check compares the requested budget (MiB) with 25% of max heap (MiB) to warn that the budget "is likely to cause heap pressure".

**A3. Mechanism.** Enclosing method `setRepairSessionSpaceInMiB(int)` (`DatabaseDescriptor.java:4091-4101`).
- Line 4093: `if (sizeInMiB < 1)` throws `ConfigurationException` (hard reject; literal `1`).
- [`DatabaseDescriptor.java:4096`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4096): `else if (sizeInMiB > (int)(maxMemory/(4*1048576)))`: true => `logger.warn(...)` only (4097-4098); false => nothing.
- Line 4100: `conf.repair_session_space = new IntMebibytesBound(sizeInMiB)` executes in both outcomes. No clamp: the limit is advisory, any int up to Integer.MAX_VALUE MiB is accepted.
- Callers: `ActiveRepairService.setRepairSessionSpaceInMegabytes` (:305-307), `setRepairSessionSpaceInMebibytes` (:320-322), `setRepairSessionSpaceInMiB` (:334-340; wraps ConfigurationException into IllegalArgumentException). All are JMX only; no internal caller.
- Consumer of the stored value: `ValidationManager.createMerkleTrees` (`ValidationManager.java:62`): `availableBytes = repairSessionSpaceMiB*1048576 / RF`; `rangeAvailableBytes` (:72); `MerkleTree.estimatedMaxDepthForBytes` (:75, `MerkleTree.java:1520`) gives max depth; `maxDepth = min(estimated, repair_session_max_tree_depth)` (:76-78); depth also capped by log2(numPartitions) (:80). Note `(int) ... * 1048576` at :62 is int*int before widening to long, so values >= 2048 MiB overflow (int multiply of `getRepairSessionSpaceInMiB() * 1048576`); this is a bypass/oddity beyond the warning threshold.
Bypass: the warning is the only effect past the threshold; usage can exceed 25% of heap with no error.

**A4. Other consumers.** Heap is shared with memtables, key/chunk caches, compaction, and (on the repair coordinator) the RF Merkle trees held concurrently (comment `ValidationManager.java:60-61`); `concurrent_merkle_tree_requests` multiplies the count of simultaneous trees. None of these is governed by the 4096 check.

**A5. Evidence beyond the source.** `conf/cassandra.yaml:830-840` comment on `repair_session_space` and CASSANDRA-14096 (https://issues.apache.org/jira/browse/CASSANDRA-14096). No test searched/relied on beyond that; not run.

## B. Verification solution

**B1. Claim under test.** Crossing the 25%-of-heap threshold in `setRepairSessionSpaceInMiB` does not change what the node does (no rejection, no clamp), and Merkle-tree memory follows `repair_session_space` smoothly across the threshold, not capped at it.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant; copy of tag built in a private dir (`ant jar`); a small Java main or JUnit test in a scratch dir on the built classpath; `-Xmx512m` (threshold = 512/4 = 128 MiB, `Runtime.maxMemory()` slightly below Xmx so read it at run time and use it).

**B2b. Knobs.** `T = (int)(Runtime.maxMemory()/(4*1048576))`. Call `DatabaseDescriptor.setRepairSessionSpaceInMiB(v)` for v in {T-1, T, T+1, 2T}. Needs `DatabaseDescriptor.daemonInitialization()`/`clientInitialization` so `conf` exists.

**B2c. Workload.** No data. For each v, call the setter, then read back `getRepairSessionSpaceInMiB()`. Separately call `MerkleTree.estimatedMaxDepthForBytes(Murmur3Partitioner.instance, v*1048576L, 32)` and build a `MerkleTrees` of that depth (`2^depth` leaves, `addMerkleTree`) for the same v, measuring deep size.

**B2d. Observables and instruments.** Log output captured via logback appender (warn present or not); stored value; `ObjectSizes.measureDeep(trees)` or `MerkleTrees.size()`; max depth. Cannot observe actual validation-compaction heap here.

**B2e. Procedure.** 1) init DatabaseDescriptor; 2) attach list appender to `DatabaseDescriptor` logger; 3) for each v: call setter, record warn flag, stored value; 4) compute depth and measured tree size; 5) print table.

**B2f. Predictions.** Warn flag false for v <= T, true for v > T; stored value == v in all cases (no clamp, no exception); estimated depth non-decreasing in v with no break at T; tree size grows roughly proportional to v (up to the depth step, each +1 depth roughly doubles size).

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| Stored value == v for v > T, depth keeps rising across T | claim confirmed (check bounds nothing) |
| Stored value clamped to T or exception for v > T | claim refuted |
| Warn absent for v > T | check not reached or logic differs; not confirmed |
| Control (positive): v < 1 throws ConfigurationException | the method does have one real bound, at 4093, not 4096 |

**B2h. Controls.** Positive control above (v=0 rejected); repeat at two `-Xmx` values (256m, 1g) to confirm T tracks heap; fix partitioner (Murmur3).

### B3. Cluster tier

**B3a. Environment and build.** One node (optionally 3 with RF=3, `ccm`-free: local copies, distinct loopback IPs), JDK 11, tag built in a private dir, `-Xmx1g` (T about 256 MiB), `concurrent_merkle_tree_requests` unset, `repair_session_max_tree_depth` unset (null; uses space budget). Data in a private dir.

**B3b. Knobs.** Runtime JMX `setRepairSessionSpaceInMiB`: V1 = 16 (default-ish), V2 = T (just under threshold), V3 = T+200 (above, warns). Chosen to straddle the threshold with the same workload.

**B3c. Workload.** One keyspace RF=1 (or 3), table with at least 4 million small partitions (e.g. `cassandra-stress write n=4000000`, ~1 GB disk or less; check free space first) so max depth is limited by the space budget, not by partition count: with 32-byte hashes the tree needs on the order of 2^depth leaves; at 256 MiB budget roughly 2^21 leaves fit (about 100 B per node), so 4M partitions (depth 22) saturates V2/V3 and not V1. Flush, then run `nodetool repair -full <ks> <table>` once per knob value.

**B3d. Observables and instruments.** During validation compaction: heap used via `jcmd <pid> GC.class_histogram` (MerkleTree$OnHeapInner/OnHeapLeaf instance counts and bytes) sampled every 2 s, `jstat -gc` for old gen, `debug.log` line "Created N merkle trees with merkle trees size..." (needs DEBUG for ValidationManager) giving tree size; `system.log` for the WARN. Cannot observe per-range split directly.

**B3e. Procedure.** Start node; load data; for each of V1, V2, V3: set via `jconsole`/`jmxterm` call on `org.apache.cassandra.db:type=RepairService`; grep WARN; start sampler; run repair; stop sampler; record peak MerkleTree bytes and leaf count; stop node; delete data dir.

**B3f. Predictions.** WARN only at V3. Peak MerkleTree bytes: V1 about 16 MiB class (below its budget), V2 and V3 larger by about 16x and 28x only up to the 4M-partition depth cap (about 2^22 leaves), so V2 and V3 may be equal if the data saturates; hence use more partitions or smaller T-sized heap to keep V3 unsaturated. Peak never jumps down at V3 (no cap at T).

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| V3 tree bytes >= V2 (or saturated at data limit) and WARN only at V3 | claim confirmed: usage follows the knob, not the threshold |
| V3 tree bytes capped at about T MiB with data unsaturated | claim refuted |
| Tree bytes at V1 << V2 | positive control: the knob does move usage where it binds |
| Peak equal for all three | workload too small/saturated; not confirmed |

**B3h. Controls.** Same data and heap for all arms; run repair twice, discard first (warmup); GC forced (`jcmd GC.run`) before sampling; a baseline run with no repair.

**B4. Risks and cleanup.** Disk: about 1-2 GB in private dir; V3 may approach 25% of heap during validation (OOM risk at -Xmx1g with RF=3, use RF=1); stop all Cassandra, jcmd, and sampler processes (`pgrep -u $USER -f CassandraDaemon` must be empty); remove data and log dirs; no files in shared source tree.

## C. Sources read

- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 590-620, 4065-4110)
- src/java/org/apache/cassandra/config/Config.java (:206-210)
- src/java/org/apache/cassandra/repair/ValidationManager.java (:50-110)
- src/java/org/apache/cassandra/service/ActiveRepairService.java (:300-360)
- src/java/org/apache/cassandra/utils/MerkleTree.java (:1520-1532)
- conf/cassandra.yaml (:825-860)

## D. Stage-4 feedback

`none yet`
