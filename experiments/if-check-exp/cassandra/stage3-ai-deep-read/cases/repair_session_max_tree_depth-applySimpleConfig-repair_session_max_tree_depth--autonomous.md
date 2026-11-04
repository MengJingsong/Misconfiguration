# repair_session_max_tree_depth (startup validation in applySimpleConfig) — verification solution  <!-- file: cases/repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:599`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L599) (`599#1`) and `:601` (`601#1`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5), Claude Code (CLI version not obtainable: `claude --version` failed inside the sandbox), 2026-10-24, band D triage |
| Estimate | `positive`: although deprecated, the entry is still read by `ValidationManager.createMerkleTrees`, where each range's tree depth is `min(estimatedMaxDepth(repair_session_space), repair_session_max_tree_depth)`, so a tree has at most 2^depth leaves and its heap is capped by it. Line 599 rejects values below 10 (floor of 2^10 leaves); line 601 only warns above 20 (no upper cap enforced). |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `repair_session_max_tree_depth`, configuration entry ([`Config.java:206`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L206), `Integer`, default `null`). Unit: tree depth (leaves = 2^depth). When unset it becomes 20 ([`DatabaseDescriptor.java:604-607`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L604-L607)); when set a deprecation warning is logged (`:598`), < 10 throws (`:599-600`), > 20 warns (`:601-602`). Runtime-settable through JMX `StorageServiceMBean.setRepairSessionMaxTreeDepth` ([`StorageService.java:4979-4982`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L4979-L4982) → [`DatabaseDescriptor.java:4075-4084`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4075-L4084), same < 10 / > 20 rules); read at each validation, so no restart needed.


**Limit type (2026-10-29).** not-a-case: the entry-pointer `if` validates the setting against a literal minimum (`< 10`), not usage against a capacity ([README §6](../README.md#6-rules-that-hold-for-both-agents)). The verification solution and the stage-4 results are kept as filed.
**A2. What it caps.** Heap held by Merkle trees built during repair validation (one tree per range; the coordinator holds RF trees per range). Operand: per-range `maxDepth`, then `depth = min(ceil(log2(numPartitions)), maxDepth)`.

**A3. Mechanism.**
1. `availableBytes = repair_session_space MiB * 2^20 / RF` ([`ValidationManager.java:62-63`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L62-L63)).
2. Per range: `rangeAvailableBytes = max(1, ownershipRatio * availableBytes)` (`:71`); `estimatedMaxDepth = MerkleTree.estimatedMaxDepthForBytes(...)` (`:74`, [`MerkleTree.java:1520-1541`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L1520-L1541)).
3. `maxDepth = min(estimatedMaxDepth, getRepairSessionMaxTreeDepth())` ([`ValidationManager.java:75-77`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L75-L77)).
4. `depth = min(ceil(log2(numPartitions)), maxDepth)`; `trees.addMerkleTree(2^depth, range)` (`:79-80`). Size is logged at debug (`:85`).
- The entry binds only when it is below the space-derived depth; with defaults (20) and typical heaps the space term usually binds. No bypass found; total memory also scales with number of ranges, concurrent validations (`concurrent_merkle_tree_requests`) and RF at the coordinator, which this entry does not bound.

**A4. Other consumers.** `repair_session_space` (the other term), streaming buffers, validation compaction read buffers, all other heap users.

**A5. Evidence beyond the source.** `NEWS.txt:934` (setting introduced to let operators reduce Merkle tree size), `NEWS.txt:819-820` (superseded by `repair_session_space_in_mb`); CASSANDRA-14096, CASSANDRA-11390 cited at `ValidationManager.java:70-71`. Existing test pattern `test/unit/org/apache/cassandra/repair/ValidatorTest.java:235-283` (`testSizeLimiting`).

## B. Verification solution

**B1. Claim under test.** With `repair_session_space` large enough not to bind, the number of leaves per validation tree equals `2^min(ceil(log2(partitions)), repair_session_max_tree_depth)`, and the trees' heap size halves for each unit decrease of the entry; values < 10 are rejected.

### B2. Unit tier

**B2a. Environment and build.** Local clone `/local/c509` (`git clone --branch cassandra-5.0.9 /path/to/shared/cassandra-src /local/c509`), JDK 11, `ant jar build-test`. New test `test/unit/org/apache/cassandra/repair/ValidatorDepthCapTest.java`, copied from `ValidatorTest` (same `@BeforeClass` schema setup, `registerOutgoingMessageSink`). Run `ant testsome -Dtest.name=org.apache.cassandra.repair.ValidatorDepthCapTest`.

**Amendment 2026-10-24 (step-0 audit) — B2a, this host.** Run clone `$W/cassandra-run7` (`W=~/Library/Caches/stage4`; `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run7`, `ant -Dlocal.repository=$W/m2 build-test`), JDK 11; the test class is kept under `stage4-runtime-verification/harness/<stem>/` and copied into the clone's `test/unit/org/apache/cassandra/repair/` by the harness, which runs `ant testsome -Dtest.name=org.apache.cassandra.repair.ValidatorDepthCapTest`. Instrument check before run 1: the class compiles (`ant build-test`) and upstream `ValidatorTest` passes (known answer: `testSizeLimiting`, 2^12 leaves at 1 MiB). Reason: B2a named a CloudLab path.

**B2b. Knobs.** `DatabaseDescriptor.setRepairSessionSpaceInMiB(256)` (so the space term allows depth > 16 for one range), then `DatabaseDescriptor.setRepairSessionMaxTreeDepth(d)` for d ∈ {10, 12, 14, 16, 20}; plus d = 9 to test rejection.

**B2c. Workload.** As in `testSizeLimiting`: `CompactionsTest.populate(keyspace, cf, 0, 1 << 16, 0)` (65,536 partitions, so `ceil(log2) = 16`), flush, one range from first to last token, `ValidationManager.instance.submitValidation(cfs, validator)`.

**Amendment 2026-10-24 (step-0 audit) — B2c, exact workload.** `populate(ks, cf, 0, 1 << 16, 0)` writes keys 0..2^16 **inclusive** (65,537 keys, 10 rows each, `CompactionsTest.java:116-128`) into keyspace `ValidatorDepthCapTest` (`KeyspaceParams.simple(1)`, one standard table, the test yaml's `ByteOrderedPartitioner`); autocompaction is disabled before each populate; "clear" is `cfs.clearUnsafe()`. The flush may leave several sstables, so the single range is `(min first token, max last token]` over the live sstables; it is left-open, so the key with the smallest token is excluded and `rowCount` is 65,536 (as `ValidatorTest.java:257-258`, `:283`). The validator is built as in `ValidatorTest.java:268` (`evenTreeDistribution = true`, so `trees.init()` builds an even tree of exactly `2^depth` leaves, `Validator.java:121-124`), with initiator `127.0.0.2`, so the response goes to the outbound sink with the trees on heap; wait up to 60 s for it. Reason: B2c's key count, range and tree construction were not exact.

**B2d. Observables and instruments.** From the `ValidationResponse`: `tree.size()` (leaves) per range, `trees.rowCount()`, `ObjectSizes.measureDeep(trees)` for heap bytes, `MerkleTrees.serializer.serializedSize(trees, 0)`.

**Amendment 2026-10-24 (step-0 audit) — B2d, the data term and the space term.** The depth's data term uses the validation's **estimated** partition count, not the exact one: `numPartitions` = Σ over the live sstables of `estimatedKeysForRanges(range)` (`CassandraValidationIterator.java:227-236`, read at `ValidationManager.java:67`, used at `:79`). The test computes the same sum (estKeys) and D = `ceil(log2 estKeys)` for each scenario and prints them. The space term is printed as a value line: d_space(s) = `estimatedMaxDepthForBytes(partitioner, s·2^20 / RF, 32)` (one range, owning ratio 1); computed at the audit on the run clone: d_space(256 MiB, ByteOrdered) = **20**, d_space(1 MiB, ByteOrdered) = **12**. Read-backs of both knobs are recorded with each scenario. Reason: B2f's "2^16 at d = 20" assumed the exact count (65,536, D = 16); an estimate above 65,536 gives D = 17.

**B2e. Procedure.** For each d: clear cfs, set knobs, populate, flush, submit, read response, record observables. Then call `setRepairSessionMaxTreeDepth(9)` and record the exception.

**Amendment 2026-10-24 (step-0 audit) — B2e, order and stop conditions.** One JVM (both knobs are read at each validation, `ValidationManager.java:62`, `:76`): `setRepairSessionSpaceInMiB(256)`, read back. For d = 10, 12, 14, 16, 20 in that order: clear, `setRepairSessionMaxTreeDepth(d)` and read back, populate, flush, register a parent session, submit one validation, wait ≤ 60 s, record. Control (B2h): clear, d = 20, `setRepairSessionSpaceInMiB(1)`, populate, flush, submit, record; then `setRepairSessionSpaceInMiB(256)`. Last, `setRepairSessionMaxTreeDepth(9)`: record the exception class and message and `getRepairSessionMaxTreeDepth()` afterwards. Reason: B2e left the control's place, the timeout and the read-backs open.

**B2f. Predictions.** Leaves = 2^10, 2^12, 2^14, 2^16, 2^16 for d = 10, 12, 14, 16, 20; `measureDeep` grows ≈4× per step of 2 up to d = 16, flat between 16 and 20; `rowCount` = 65,536 always. d = 9 → `ConfigurationException` "Cannot set repair_session_max_tree_depth to 9 which is < 10".

**Amendment 2026-10-24 (step-0 audit) — B2f, exact form (the data term is an estimate).** For each d: one tree; `rowCount` = 65,536; leaves = 2^min(D, d) exactly, with D from B2d (≥ 16 whenever estKeys > 32,768) and d_space(256) = 20 not binding: **1,024 · 4,096 · 16,384 · 65,536** at d = 10 · 12 · 14 · 16, and **2^D** at d = 20 (65,536 if D = 16, 131,072 if D = 17; "flat between 16 and 20" holds only if D = 16). `measureDeep(trees)`: ratio between consecutive values d = 10 → 12 → 14 → 16 in [3.8, 4.2] ("≈ 4×", the tree's size being linear in its node count); `measureDeep(20) / measureDeep(16)` within ±5 % of 2^(D − 16). Control: leaves = 2^12 = **4,096**. d = 9: `ConfigurationException` with message `Cannot set repair_session_max_tree_depth to 9 which is < 10, doing nothing` (`DatabaseDescriptor.java:4077-4079`) and `getRepairSessionMaxTreeDepth()` = 20 afterwards. Reason: the source shows the data term is an estimate (B2d amendment); the control's value and the value after the rejection were not stated. This changes the d = 20 prediction for a reason read from the source, before any reading.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| leaves follow 2^min(16, d) | cap works as traced |
| leaves = 2^16 for d = 10 | entry not consulted (claim wrong) |
| leaves < 2^min(16,d) | space term bound instead (raise `repair_session_space`; not a refutation) |
| d = 9 accepted | lower-bound check ineffective |

**Amendment 2026-10-24 (step-0 audit) — B2g, rows added; the four rows above are unchanged.** "Follow 2^min(16, d)" is read as 2^min(D, d) (B2f amendment). Row 1 ("cap works as traced") needs every amended B2f item: leaves = 2^min(D, d) exactly at all five d, the `measureDeep` ratios in band, and the d = 9 rejection with the value unchanged (the direct evidence that the disallow branch fires). Row 3 ("space term bound") is invalid for that d, not a confirmation. Added rows:

| Observation | Meaning |
|---|---|
| leaves move with d but differ from 2^min(D, d) at some d (and not below it because of the space term) | the entry governs, not by the traced formula: not confirmed |
| leaves follow 2^min(D, d) but a `measureDeep` ratio is outside its band | the leaf count is capped but heap does not follow it: not confirmed for heap |
| d = 9 throws but `getRepairSessionMaxTreeDepth()` changed | rejection ineffective: refuted for the rejection |
| D < d for some d ≤ 16 (data term binds) | invalid for that d |
| control leaves ≠ 4,096 | the observable does not respond to a known cap: invalid |
| no response within 60 s, not exactly one tree, `rowCount` ≠ 65,536, or a read-back ≠ the set value | invalid for that d |

**B2h. Controls.** Same data with d = 20 and `repair_session_space` = 1 MiB reproduces the existing test's space-limited depth (2^12 for 2^14 rows per `ValidatorTest.java:245`), separating the two terms.

**Amendment 2026-10-24 (step-0 audit) — B2h, expected value.** With the same data (D ≥ 16), d = 20 and 1 MiB, the space term binds: d_space(1 MiB, ByteOrdered, RF 1) = 12 (computed at the audit; the known answer of `ValidatorTest.java:246`, `:278`), so leaves = **4,096**. Reason: the control's expectation must be derived before the run.

### B3. Cluster tier

**B3a. Environment and build.** Three nodes (or three loopback addresses 127.0.0.1-3 on one host with separate dirs) built from `/local/c509`, `MAX_HEAP_SIZE=2G`, data dirs under `/local/c509-nodeN`, `num_tokens: 1` (one range per node, simple arithmetic), `repair_session_space: 256MiB`. Add to `conf/logback.xml`: `<logger name="org.apache.cassandra.repair.ValidationManager" level="DEBUG"/>`.

**Amendment 2026-10-24 (step-0 audit) — B3a, this host's ring and the space value.** One clone per node: n1 `127.0.0.1` from `$W/cassandra-run7` (built `build-test`), n2 `127.0.0.2` from `$W/cassandra-run7-n2`, n3 `127.0.0.3` from `$W/cassandra-run7-n3` (`ant jar`). Each node's yaml: `cluster_name: stage4-rsmtd7`, `num_tokens: 1`, `initial_token` −9223372036854775808 / −3074457345618258603 / 3074457345618258602 (equal thirds of the Murmur3 ring), `auto_bootstrap: false`, its own `listen_address`/`rpc_address`, seed `127.0.0.1`, data, commit log, hints, saved caches and CDC under `$W/node-rsmtd/nN/`, and **`repair_session_space: 1024MiB`** (not 256MiB); JMX 7199 / 7299 / 7399; `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`. Everything else as shipped (`use_offheap_merkle_trees: true`, `concurrent_merkle_tree_requests: 0`, `repair_session_max_tree_depth` unset → 20). `conf/logback.xml` is not changed: `:132` already logs `org.apache.cassandra` at DEBUG to `debug.log`. Nodes start one at a time; each must show `UN` and `statusbinary` `running` within 360 s. Why 1024MiB: each node validates three ranges of ≈ 1/3 of the data, so the per-range budget is ⌊⌊s·2^20/3⌋/3⌋, and `estimatedMaxDepthForBytes(Murmur3Partitioner, ·, 32)` computed at the audit on the run clone gives d_space = **17** at 256 MiB (so d = 18 could not bind, B3f's own assumption fails), 18 at 512 MiB and **19** at 1024 MiB, each unchanged at 0.95× and 1.05× of the budget. 1024 MiB is above heap/4 (512 MiB), so a startup warning `… is likely to cause heap pressure` is expected (`DatabaseDescriptor.java:614-615`); it is only a warning. Reason: the original space value makes the d = 18 arm space-limited (B3g row 3) before any run; three nodes on one host need distinct addresses, ports and directories.

**B3b. Knobs.** `repair_session_max_tree_depth` via JMX between repairs: `nodetool sjk mx -b org.apache.cassandra.db:type=StorageService -mc -op setRepairSessionMaxTreeDepth -a <d>` on all nodes, d ∈ {10, 14, 18}; also yaml value `9` at startup.

**Amendment 2026-10-24 (step-0 audit) — B3b, the JMX command, the default and read-backs.** `getRepairSessionMaxTreeDepth`/`setRepairSessionMaxTreeDepth` (`StorageServiceMBean.java:484`, `:490`) form the JMX **attribute** `RepairSessionMaxTreeDepth`, not an operation, so `-mc -op setRepairSessionMaxTreeDepth` cannot run. Set with `nodetool -p <port> sjk mx -b org.apache.cassandra.db:type=StorageService -ms -f RepairSessionMaxTreeDepth -v <d>` and read back with `-mg -f RepairSessionMaxTreeDepth` on all three (`nodetool` exits 0 when the call fails, so the read-back decides). Order: first a repair at the **default** (unset; read back, expected 20), then d = 10, 14, 18, then the control (B3h), then the yaml value `9` on n1. Reason: the command as written cannot run; the default was not among the values; a set without a read-back cannot show the knob took.

**B3c. Workload.** `cassandra-stress write n=2000000 cl=ALL -col n=FIXED(1) size=FIXED(32) -schema "replication(factor=3)"` → ≈667k partitions per primary range (> 2^19), so depth would be ≥ 19 without the cap; then `nodetool repair -full keyspace1 standard1` per knob value.

**Amendment 2026-10-24 (step-0 audit) — B3c, exact commands and stability.** Stress from n1's clone: `tools/bin/cassandra-stress write n=2000000 cl=ALL -col 'n=FIXED(1)' 'size=FIXED(32)' -schema 'replication(factor=3)' -node 127.0.0.1`; valid if `Total errors` is 0 and 2,000,000 partitions were written. Then `nodetool flush keyspace1 standard1` on each node, wait until `nodetool compactionstats` shows 0 pending tasks (bound 600 s), and `nodetool disableautocompaction keyspace1 standard1` on each, so the estimates do not change between repairs. Each repair is `nodetool -p 7199 repair -full keyspace1 standard1` against n1, bound 900 s, valid if it exits 0; without `-pr` the three ranges form one session, so each node runs one validation over three ranges. Data term: P ≈ 2,000,000 per node, P/3 ≈ 666,667 per range, ceil(log2) = 20 for any estimate in (524,288, 1,048,576]. Reason: stress validity, compaction between repairs and the coordinator were open.

**B3d. Observables and instruments.** Debug line "Created N merkle trees with merkle trees size S, P partitions, B bytes" (`ValidationManager.java:85`) in `logs/debug.log`; `jcmd <pid> GC.class_histogram | grep -i 'MerkleTree'` taken while validation runs (poll every 1 s, keep the max instance count of `MerkleTree$OnHeapLeaf`/`OnHeapInner`).

**Amendment 2026-10-24 (step-0 audit) — B3d, where S is read; B replaced.** The line at `ValidationManager.java:85` is logged right after `addMerkleTree` (`:80`), before `Validator.prepare` initialises the trees (`trees.init()`, `Validator.java:120-124`): its size field is R (one root leaf per range) and its bytes field is the size of R one-leaf trees, whatever the knob. S (the sum of leaves over the R ranges, `MerkleTrees.java:197-206`) is read from `Prepared AEService trees of size {S} for {desc}` (`Validator.java:158`), one line per node per repair, from the part of `debug.log` written after the repair started (byte offset); R and P are read from the `:85` line; its B field is not used. The serialized-size observable is replaced by the heap of the trees' node objects: `jcmd <pid> GC.class_histogram` on each node every 1 s from just before the repair until it returns, plus one idle histogram before it; H = per node, the maximum over samples of the bytes of `org.apache.cassandra.utils.MerkleTree$OnHeapLeaf` + `$OnHeapInner`, and Lmax = the maximum `OnHeapLeaf` instance count. (`jstat` cannot attach on this host, `-XX:+PerfDisableSharedMem`, `conf/jvm-server.options:137`.) Gaps named: shallow sizes only (the unit tier's `measureDeep` covers the full tree); the coordinator's received trees are off heap by default (`Config.java:212`) and not in H. Reason: S as written cannot move with the knob; B is read before `init()`.

**B3e. Procedure.** Start 3 nodes, wait all UN, load data, `nodetool flush` on all. For each d: set via JMX on all nodes, run repair, grep the debug lines for that session, record S and B and histogram max. Separately restart one node with `repair_session_max_tree_depth: 9` and record whether it starts.

**Amendment 2026-10-24 (step-0 audit) — B3e, full sequence and stop conditions.** Start n1, n2, n3 (B3a); stress; flush, compaction wait, disable autocompaction (B3c). Per label (default; d = 10, 14, 18; control): set and read back on all nodes, idle histograms, samplers on, repair, samplers off, extract each node's `Prepared` and `Created` lines after the start offset. Then restore `RepairSessionSpaceInMiB` = 1024 (read back), stop n1 (`nodetool drain` bounded 60 s, then kill), add `repair_session_max_tree_depth: 9` to its yaml and start it: **fails** = the process exits within 120 s, `system.log` or the console contains `repair_session_max_tree_depth should not be < 10, but was 9` (`DatabaseDescriptor.java:599-600`) and there is no `Startup complete`; **starts** = otherwise. Stop every node; `ps -eo command | grep '[C]assandraDaemon'` and `pgrep -f cassandra-stress` empty; `$W/node-rsmtd` wiped. Reason: B3e had no bounds, no place for the control and no test for "starts".

**B3f. Predictions.** Tree size S per range = 2^10, 2^14, 2^18 for d = 10, 14, 18 (assuming the space term at 256 MiB/3 allows ≥ 18); serialized B scales ≈ by 16× per step; leaf instance count max ∝ 2^d. Startup with 9 fails with "repair_session_max_tree_depth should not be < 10".

**Amendment 2026-10-24 (step-0 audit) — B3f, exact form.** On every node: R = 3; with the per-range data term 20 and d_space(1024 MiB) = 19 (B3a amendment), S = 3 × 2^min(d, 19): **3,072 · 49,152 · 786,432** at d = 10 · 14 · 18, so S(14)/S(10) = S(18)/S(14) = 16 exactly, and at the **default** (20, read back) **S = 3 × 2^19 = 1,572,864** (the space term binds there). Lmax = S on each node (one validation per node; the coordinator's received trees are off heap); H(14)/H(10) and H(18)/H(14) in [15, 17] (H is linear in the node count 2S − R; this replaces "serialized B ≈ 16×", B3d amendment). Control: S = 3 × 2^11 = **6,144** (B3h amendment). Startup with 9: fails with the B3e text. Reason: the absolute values, the three ranges and the default were not stated; B is unusable.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| S = 2^d per range | claim confirmed |
| S constant across d | entry not governing (claim wrong) |
| S below 2^d for d = 18 | space term binding; raise `repair_session_space` and retry |
| node starts with 9 | validation not effective |

**Amendment 2026-10-24 (step-0 audit) — B3g, definitions and rows added; the four rows above are unchanged.** "S = 2^d per range" is read as S = 3 × 2^d over the three ranges. Row 1 ("claim confirmed") needs on every node: S = 3 × 2^d at d = 10, 14, 18 (the depth set by the entry, below the space and data terms — the direct evidence that the entry, not the data or the budget, sized the trees), the ×16 ratios, the H ratios in band, Lmax = S, S(default) = 1,572,864, and the startup with 9 refused. Row 3 ("space term binding") is invalid for that value. Added rows:

| Observation | Meaning |
|---|---|
| S moves with d but S ≠ 3 × 2^d at some d | the entry governs, not by the traced formula: not confirmed |
| S = 3 × 2^d, but an H ratio outside [15, 17] or Lmax ≠ S | the leaf count follows the entry but the heap reading does not: not confirmed for heap |
| S(default) ≠ 1,572,864 (with S = 3 × 2^d at the set values) | the space term is not as computed: recorded; does not change row 1's other parts, but row 1 is then not met |
| a read-back ≠ d, R ≠ 3, a `Prepared` line missing, a repair not exiting 0, or stress errors | invalid for that value |
| P/3 ≤ 2^18 (data term binds) | invalid for that value |
| control S ≠ 6,144 | the observable does not respond to a known cap: invalid |
| no histogram sample during a repair shows `MerkleTree$OnHeapLeaf` objects | H not measured: invalid for the heap part |

**B3h. Controls.** Repeat d = 18 with `repair_session_space` set to 4 MiB through JMX (`org.apache.cassandra.db:type=RepairService`, `setRepairSessionSpaceInMiB`, `ActiveRepairServiceMBean.java:27,50`), expecting smaller S: shows the same workload moves tree size when the other known cap binds.

**Amendment 2026-10-24 (step-0 audit) — B3h, command and value.** `RepairSessionSpaceInMiB` is a JMX attribute (`ActiveRepairServiceMBean.java:50-51`): set with `nodetool -p <port> sjk mx -b org.apache.cassandra.db:type=RepairService -ms -f RepairSessionSpaceInMiB -v 4` on all three, read back with `-mg -f RepairSessionSpaceInMiB`, with d = 18 read back. The per-range budget ⌊⌊4·2^20/3⌋/3⌋ = 466,033 B gives d_space = 11 (computed at the audit on the run clone; also at 0.95× and 1.05×), so S = 3 × 2^11 = 6,144. Afterwards 1024 is restored and read back. Reason: the command as written cannot run; the expected S was not stated.

**B4. Risks and cleanup.** ≈1-2 GB per node under `/local/c509-nodeN`. Stop all nodes (`pkill -f CassandraDaemon`, check `pgrep`), `rm -rf /local/c509-node*`. Debug logging only in the local clone's `conf/`.

## C. Sources read

src/java/org/apache/cassandra/config/DatabaseDescriptor.java (596-607, 4070-4100)
src/java/org/apache/cassandra/config/Config.java (206-208)
src/java/org/apache/cassandra/repair/ValidationManager.java (50-90)
src/java/org/apache/cassandra/utils/MerkleTree.java (1520-1541)
src/java/org/apache/cassandra/service/StorageService.java (4979-4990), StorageServiceMBean.java (484-490)
test/unit/org/apache/cassandra/repair/ValidatorTest.java (230-295)
NEWS.txt (819-820, 934)

## D. Stage-4 feedback

**Stage 4 closed 2026-10-24** ([results](../../stage4-runtime-verification/results/repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous.md)); Claude Opus 5.5 (claude-opus-5-5), advisor's machine; estimate `positive` held. **Unit tier: Confirmed — caps** (one tree of exactly 2^min(D, d) leaves, 1,024 · 4,096 · 16,384 · 65,536 · 65,536 at d = 10 · 12 · 14 · 16 · 20 with D = 16; `measureDeep(trees)` ×3.96–3.99 per +2; control at 1 MiB → 4,096; `setRepairSessionMaxTreeDepth(9)` → `ConfigurationException` "Cannot set repair_session_max_tree_depth to 9 which is < 10, doing nothing", value unchanged). **Cluster tier: Confirmed — caps** (three nodes, RF 3, 2 M partitions, three equal ranges per validation, `repair_session_space: 1024MiB`: S = 3,072 · 49,152 · 786,432 = 3 × 2^10 · 2^14 · 2^18 at d = 10 · 14 · 18, identical on all nodes, ×16 per +4; `MerkleTree$OnHeap*` histogram bytes ×16.0, leaf instances = S; at the default 20 the budget binds, S = 3 × 2^19; control 4 MiB at d = 18 → 6,144; startup with `repair_session_max_tree_depth: 9` refused with "should not be < 10, but was 9"). No runbook defect: the problems known from case 3 (the JMX attribute, and S at `ValidationManager.java:85` logged before `init()`) were found at the audit and fixed by amendments. Audit findings for stage 3: as filed, B3's `repair_session_space: 256MiB` gives a per-range space depth of 17 (three ranges, RF 3), so the d = 18 arm could not have bound (raised to 1024MiB); B2's data term is the validation's partition estimate (`CassandraValidationIterator.java:227-236`), not the exact count, so "flat between 16 and 20" holds only when the estimate is ≤ 65,536 (it was 65,536 here); `ValidatorTest.java:245` is a blank line (`:246`, `:278`). Notes not applied: B1 could state that the entry binds only below the per-range budget depth; line 601 (> 20 only warns) is untested. The fifteen amendments of 2026-10-24 (B2a, B2c, B2d, B2e, B2f, B2g, B2h, B3a, B3b, B3c, B3d, B3e, B3f, B3g, B3h) were made at the step-0 audit; the frozen hash is in `_INDEX.md` §4, and this section was added after it.
