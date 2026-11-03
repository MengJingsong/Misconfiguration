# repair_session_space (startup validation in applySimpleConfig) — verification solution  <!-- file: cases/repair_session_space-applySimpleConfig-repair_session_space--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:612`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L612) (`612#1`) and `:614` (`614#1`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5), Claude Code (CLI version not obtainable: `claude --version` failed inside the sandbox), 2026-10-24, band D triage |
| Estimate | `positive`: the entry sets the Merkle-tree memory budget per validation (`availableBytes = space / RF`, split by range ownership) from which the maximum tree depth is derived, so tree heap per validation is capped by it. Line 612 rejects < 1 MiB; line 614 only warns above heap/4 (no upper cap). |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `repair_session_space`, configuration entry ([`Config.java:207-208`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L207-L208), `IntMebibytesBound`, legacy `repair_session_space_in_mb`), unit MiB. Default when unset: `max(1, maxMemory/16)` MiB ([`DatabaseDescriptor.java:609-610`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L609-L610)). `< 1` throws (`:612-613`); `> maxMemory/4` warns of heap pressure (`:614-615`). Runtime-settable: `ActiveRepairServiceMBean.setRepairSessionSpaceInMiB` → `DatabaseDescriptor.setRepairSessionSpaceInMiB` ([`DatabaseDescriptor.java:4091-4101`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4091-L4101), same rules); read at each validation.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Heap of Merkle trees built by one validation (budget for RF trees held at the coordinator). Operand: `availableBytes` → `rangeAvailableBytes` → `estimatedMaxDepthForBytes`.

**A3. Mechanism.** `ValidationManager.createMerkleTrees`: `availableBytes = space*2^20 / RF` ([`ValidationManager.java:62-63`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L62-L63)); per range `rangeAvailableBytes = max(1, ratio*availableBytes)` (`:71`); `estimatedMaxDepth = MerkleTree.estimatedMaxDepthForBytes(partitioner, rangeAvailableBytes, 32)` (`:74`), which divides bytes by `measureDeep` of a leaf+inner pair and takes floor(log2) ([`MerkleTree.java:1520-1541`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L1520-L1541)); `maxDepth = min(estimatedMaxDepth, repair_session_max_tree_depth)` (`:75-77`); tree of `2^depth` leaves (`:79-80`). Overshoot: `estimatedMaxDepthForBytes` returns ≥ 1, so a tiny budget still yields 2 leaves; the estimate is from `ObjectSizes`, not measured heap; concurrent validations (`concurrent_merkle_tree_requests`) and multiple sessions each get the full budget.

**A4. Other consumers.** `repair_session_max_tree_depth` (other term), all other heap users; Merkle trees received from replicas at the coordinator.

**A5. Evidence beyond the source.** `NEWS.txt:497`, `:819-820`; CASSANDRA-14096/11390 (`ValidationManager.java:70-71`); `ValidatorTest.java:235-283` (1 MiB → 2^12 leaves for 2^14 rows).

## B. Verification solution

**B1. Claim under test.** With `repair_session_max_tree_depth` = 20, the leaves per single-range validation tree equal `2^min(ceil(log2 partitions), floor(log2(space·2^20/RF / (leaf+inner bytes))))`, so tree heap is ≤ the budget and halves when the budget halves; a value of 0 is rejected.

### B2. Unit tier

**B2a. Environment and build.** Local clone `/local/c509`, JDK 11, `ant jar build-test`. New test `test/unit/org/apache/cassandra/repair/ValidatorSpaceCapTest.java` copied from `ValidatorTest` setup. `ant testsome -Dtest.name=org.apache.cassandra.repair.ValidatorSpaceCapTest`.

**B2b. Knobs.** `setRepairSessionSpaceInMiB(s)` for s ∈ {1, 2, 4, 8, 16}; `setRepairSessionMaxTreeDepth(20)`; also s = 0 for rejection.

**B2c. Workload.** `CompactionsTest.populate(ks, cf, 0, 1 << 18, 0)` (262,144 partitions; depth ≤ 18 from data), flush, single range, `submitValidation` (as `ValidatorTest.java:241-272`). Test keyspace RF = 1.

**Amendment 2026-10-24 (step-0 audit) — B2c, exact workload.** `populate(ks, cf, 0, 1 << 18, 0)` writes keys 0..2^18 **inclusive** (262,145 keys, 10 rows each, `CompactionsTest.java:116-128`), in a keyspace `ValidatorSpaceCapTest` with `KeyspaceParams.simple(1)` and one standard table; autocompaction is disabled before each populate. "Clear" is `cfs.clearUnsafe()` (as `ValidatorTest.java:239`). 2.6 M rows can exceed one memtable, so the flush may leave several sstables: the single range is `(min first token, max last token]` over the live sstables (as `ValidatorTest.java:257-258` for one sstable). The initiator is `127.0.0.2` (not this node), so the response goes to the outbound sink with the trees still on heap (`Validator.java:280-286`; a local initiator moves them off heap first, `:288-305`). Reason: B2c's count, keyspace and range were not exact.

**B2d. Observables and instruments.** `tree.size()`, `ObjectSizes.measureDeep(trees)`, and the expected depth computed in the test by calling `MerkleTree.estimatedMaxDepthForBytes(partitioner, s<<20, 32)`.

**Amendment 2026-10-24 (step-0 audit) — B2d, where each observable is read.** The trees are the `MerkleTrees` of the `ValidationResponse` captured by the outbound sink (hashes filled): number of trees, `tree.size()` (leaves), `ObjectSizes.measureDeep(trees)`, and `trees.rowCount()` (partitions hashed). Expected depth d(s) = `estimatedMaxDepthForBytes(partitioner, (s·2^20)/RF, 32)` with RF read from the keyspace (1); with one range the owning ratio is exactly 1 (`CassandraValidationIterator.java:227-236`, `ValidationManager.java:68-71`), so d(s) is the budget term before the data and depth-cap terms. Data term: `ceil(log2 rowCount)` must exceed d(s) for a reading to test the budget. The harness also prints, as value lines for B3f (not unit-tier readings), d for `Murmur3Partitioner` at the cluster per-range budgets ⌊⌊s·2^20/3⌋/3⌋ for s = 4, 16, 64, and at 0.95× and 1.05× of each. Reason: B2d did not say which object is measured, and the data term needs a reading.

**B2e. Procedure.** For each s: clear, set, populate, flush, submit, record; finally `setRepairSessionSpaceInMiB(0)` and record exception.

**Amendment 2026-10-24 (step-0 audit) — B2e, order and stop conditions.** One JVM (the knob is read at each validation, so setting it at run time suffices): `setRepairSessionMaxTreeDepth(20)`; for s = 1, 2, 4, 8, 16: clear, `setRepairSessionSpaceInMiB(s)` and read it back, populate, flush, register a parent session and submit one validation, wait up to 60 s for the response, record. Then the B2h control (clear, s = 16, `setRepairSessionMaxTreeDepth(12)`, populate, flush, submit), and depth restored to 20. Last, `setRepairSessionSpaceInMiB(0)`: record the exception class and message and `getRepairSessionSpaceInMiB()` afterwards. Reason: B2e left the control's place, the timeout and the read-backs open.

**B2f. Predictions.** Leaves double per doubling of s (until 2^18); `measureDeep(trees)` ≤ s MiB for each s; leaves = 2^estimatedMaxDepthForBytes(s MiB) exactly; s = 0 → `ConfigurationException` "Cannot set repair_session_space to 0 < 1 mebibyte".

**Amendment 2026-10-24 (step-0 audit) — B2f, exact form.** For each s: one tree; leaves = 2^d(s) exactly (d(s) as amended in B2d), hence leaves(2s) = 2 × leaves(s); `measureDeep(trees)` ≤ s × 1,048,576 B; read-back = s. Control: leaves = 2^12 = 4,096. s = 0: `ConfigurationException` with the message `Cannot set repair_session_space to 0 < 1 mebibyte` (`DatabaseDescriptor.java:4093-4095`), and `getRepairSessionSpaceInMiB()` still 16 afterwards. "Until 2^18" does not arise (every d(s) is below the data term). Reason: the relations were stated without the control's value or the value after the rejection.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| leaves double with s, `measureDeep` ≤ s MiB | claim confirmed |
| `measureDeep` > s MiB | estimate under-counts; cap is not exact (partial refutation) |
| leaves constant across s | budget not used (claim wrong) |
| s = 0 accepted | validation ineffective |

**Amendment 2026-10-24 (step-0 audit) — B2g, rows added; the four rows above are unchanged.** Row 1 ("claim confirmed") needs every amended B2f item: leaves = 2^d(s) exactly and doubling, `measureDeep` ≤ s MiB at every s, and the s = 0 rejection with the value unchanged (the direct evidence that the disallow branch fires). Added rows:

| Observation | Meaning |
|---|---|
| leaves double with s but differ from 2^d(s) at some s | the budget governs, not by the traced formula: not confirmed |
| leaves move with s but not ×2 per doubling (and not constant) | not confirmed |
| s = 0 throws but `getRepairSessionSpaceInMiB()` changed | rejection ineffective: refuted for the rejection |
| `2^ceil(log2 rowCount)` ≤ 2^d(s) at some s (data term binds) | invalid for that s |
| control leaves ≠ 4,096 | the observable does not respond to a known cap: invalid |
| no response within 60 s, or not exactly one tree, or a read-back ≠ s | invalid for that s |

**B2h. Controls.** s = 16 with `setRepairSessionMaxTreeDepth(12)` → leaves 2^12 (other term binds), showing the observable responds to a known cap.

### B3. Cluster tier

**B3a. Environment and build.** Three local nodes (127.0.0.1-3) from `/local/c509`, `MAX_HEAP_SIZE=1G` (default space 64 MiB), `num_tokens: 1`, data under `/local/c509-nodeN`; debug logger for `org.apache.cassandra.repair.ValidationManager` in `conf/logback.xml`.

**Amendment 2026-10-24 (step-0 audit) — B3a, this host's ring.** One clone per node: n1 `127.0.0.1` from `$W/cassandra-run4` (built `build-test`), n2 `127.0.0.2` from `$W/cassandra-run4-n2`, n3 `127.0.0.3` from `$W/cassandra-run4-n3` (`ant jar`), `W=~/Library/Caches/stage4`. Each node's yaml: `cluster_name: stage4-rss4`, `num_tokens: 1`, `initial_token` −9223372036854775808 / −3074457345618258603 / 3074457345618258602 (equal thirds of the Murmur3 ring, so each node replicates three ranges of ≈ 1/3 of the data), `auto_bootstrap: false` (empty ring), its own `listen_address`/`rpc_address`, seed `127.0.0.1`, data, commit log, hints, saved caches and CDC under `$W/node-rss/nN/`; JMX ports 7199 / 7299 / 7399; `MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M`. Everything else as shipped: `use_offheap_merkle_trees: true` (`Config.java:212`), `concurrent_merkle_tree_requests: 0`, `repair_session_max_tree_depth` unset (→ 20, `DatabaseDescriptor.java:605-607`). `conf/logback.xml` is not changed: `:132` already logs `org.apache.cassandra` at DEBUG to `debug.log`. Nodes start one at a time; each must show `UN` and `statusbinary` `running` within 360 s. Reason: three nodes on one host need distinct addresses, ports and directories; random tokens would make the per-range depths unpredictable.

**B3b. Knobs.** `repair_session_space` ∈ {`4MiB`, `16MiB`, `64MiB`} set by JMX on all nodes: `nodetool sjk mx -b org.apache.cassandra.db:type=RepairService -mc -op setRepairSessionSpaceInMiB -a <s>` (MBean name from `ActiveRepairServiceMBean.java:27`, operation at `:50`); startup with `repair_session_space: 0MiB` and `300MiB` (> heap/4 → warning only).

**Amendment 2026-10-24 (step-0 audit) — B3b, order and read-backs.** First a repair at the **default** (unset; read back over JMX, expected 64 at a 1 GiB heap), then 4, 16, 64 MiB set on each node with `nodetool -p <port> sjk mx -b org.apache.cassandra.db:type=RepairService -mc -op setRepairSessionSpaceInMiB -a <s>` and read back with `-mg -f RepairSessionSpaceInMiB` (must equal s on all three). Control (B3h) at s = 4, 16, 64 with `-b org.apache.cassandra.db:type=StorageService -mc -op setRepairSessionMaxTreeDepth -a 10` (`StorageServiceMBean.java:484`), read back `RepairSessionMaxTreeDepth`, restored to 20 afterwards. The startup values `0MiB` and `300MiB` are set in n1's yaml after the control. Reason: the default was implicit, and a set without a read-back cannot show the knob took.

**Runbook fix 2026-10-24 (stage 4, defect 1, found by the harness shakedown before cluster run 1) — B3b, the JMX command.** `setRepairSessionSpaceInMiB` and `setRepairSessionMaxTreeDepth` are the setters of JMX **attributes** (`RepairSessionSpaceInMiB`, `ActiveRepairServiceMBean.java:50-51`; `RepairSessionMaxTreeDepth`, `StorageServiceMBean.java:484`, `:490`), not operations, so `sjk mx … -mc -op setRepairSessionSpaceInMiB -a <s>` fails with `Operation setRepairSessionSpaceInMiB/1 not found` (and `nodetool` still exits 0). The knob is set with `nodetool -p <port> sjk mx -b org.apache.cassandra.db:type=RepairService -ms -f RepairSessionSpaceInMiB -v <s>` and the control's depth with `-b org.apache.cassandra.db:type=StorageService -ms -f RepairSessionMaxTreeDepth -v 10`; the read-backs are unchanged. B3f and B3g are unchanged.

**B3c. Workload.** `cassandra-stress write n=3000000 cl=ALL -col n=FIXED(1) size=FIXED(32) -schema "replication(factor=3)"`; `nodetool flush`; then `nodetool repair -full keyspace1 standard1` per s. ≈1M partitions per range (> 2^19), so the data term does not bind.

**Amendment 2026-10-24 (step-0 audit) — B3c, exact commands and stability.** Stress from n1's clone: `tools/bin/cassandra-stress write n=3000000 cl=ALL -col 'n=FIXED(1)' 'size=FIXED(32)' -schema 'replication(factor=3)' -node 127.0.0.1` (200 threads, the default for a write with `n`, `SettingsRate.java:117-125`); valid if `Total errors` is 0 and 3,000,000 partitions were written. Then `nodetool flush keyspace1 standard1` on each node, wait until `nodetool compactionstats` shows 0 pending tasks on each (bound 600 s), and `nodetool disableautocompaction keyspace1 standard1` on each, so the partition estimates do not change between repairs. Each repair is `nodetool -p 7199 repair -full keyspace1 standard1` run against n1, bound 900 s, valid if it exits 0; without `-pr` the three ranges share their endpoints and form one session (`RepairCoordinator.java:490-506`), so each node runs one validation over three ranges. Reason: B3c left stress validity, compaction between repairs and the repair's coordinator open.

**B3d. Observables and instruments.** Debug line at `ValidationManager.java:85` (tree size S, serialized bytes B); `jcmd <pid> GC.class_histogram` sampled 1 s during validation for `MerkleTree$OnHeap*` bytes; `jstat -gc` old-gen.

**Amendment 2026-10-24 (step-0 audit) — B3d, exact observables; `jstat` replaced.** S is the second field of the debug line at `ValidationManager.java:85`, `Created {R} merkle trees with merkle trees size {S}, {P} partitions, {B} bytes`: S is the sum of leaves over the R ranges (`MerkleTrees.java:197-206`); each node logs one line per repair, read from the part of its `debug.log` written after the repair started (byte offset). Histogram: `jcmd <pid> GC.class_histogram` on each node every 1 s from just before the repair until it returns, plus one idle histogram before each repair; H = per node, the maximum over samples of the bytes of `org.apache.cassandra.utils.MerkleTree$OnHeapLeaf` plus `$OnHeapInner`. `jstat` cannot attach to a node on this host (`-XX:+PerfDisableSharedMem`, `conf/jvm-server.options:137`); the old-gen reading is replaced by the histogram's `Total` bytes (live heap after the forced full GC), support only. Gaps named: the class histogram counts the node objects' shallow size, not their hash `byte[]`s or inner tokens (the unit tier's `measureDeep` covers the full tree); the coordinator's received trees are off heap by default (`Config.java:212`, `Validator.java:288-305`) and not in H. Reason: S over several ranges, H and the sampling window were undefined; `jstat` cannot run here.

**Runbook fix 2026-10-24 (stage 4, defect 2, found by the harness shakedown before cluster run 1) — B3d, where S is read.** The line at `ValidationManager.java:85` is logged right after `addMerkleTree` (`:80`), before the trees are initialised: each tree is still a single root leaf, so its "size" field is always R (3) and its "bytes" field is the size of R one-leaf trees, whatever the knob (shakedown: `size 3, … 268 bytes` at every value). The trees reach `maxsize` leaves in `Validator.prepare` (`trees.init()`, `Validator.java:120-124`, on Murmur3, which does not preserve order), which then logs `Prepared AEService trees of size {S} for {desc}` (`Validator.java:158`). S is read from that line (one per node per repair); R and P are still read from the `:85` line, and its B field is not used. B3f and B3g are unchanged.

**B3e. Procedure.** Start, load, flush; per s: set via JMX on all nodes, repair, collect S/B/histogram max. Restart node 1 with `0MiB` (expect failure) and `300MiB` (expect start + warning).

**Amendment 2026-10-24 (step-0 audit) — B3e, full sequence and stop conditions.** Start n1, n2, n3 (B3a); stress; flush, compaction wait, disable autocompaction (B3c). Per value (default, 4, 16, 64; then control 4, 16, 64): set and read back on all nodes, idle histograms, samplers on, repair, samplers off, extract each node's `Created` line after the start offset. Then stop n1 (`nodetool drain` bounded 60 s, then kill), set `repair_session_space: 0MiB`, start: **fails** = the process exits within 120 s and `system.log` contains `repair_session_space must be > 0, but was 0MiB` (`DatabaseDescriptor.java:612-613`); then `300MiB`: **starts** = `UN` and `statusbinary` `running` within 360 s and `system.log` contains `A repair_session_space of 300MiB mebibytes is likely to cause heap pressure` (`:614-615`). Stop every node the same way; `ps -eo command | grep '[C]assandraDaemon'` and `pgrep -f cassandra-stress` empty; `$W/node-rss` wiped. Reason: B3e had no bounds, no order for the control and no test for "fails" and "starts".

**B3f. Predictions.** S scales ×4 from 4→16 MiB and ×4 from 16→64 MiB (depth +2 each); histogram bytes of `MerkleTree$OnHeap*` per validation ≤ s/RF·(number of concurrent trees ≤ RF at coordinator) ≈ ≤ s; startup with 0 fails with "repair_session_space must be > 0"; 300 MiB logs "likely to cause heap pressure".

**Amendment 2026-10-24 (step-0 audit) — B3f, exact form.** On every node: R = 3; S(16)/S(4) = 4 and S(64)/S(16) = 4 exactly; S(default) = S(64) when the default reads back 64. With the equal tokens each range owns ≈ 1/3 of the partitions, so each tree has 2^d leaves with d = `estimatedMaxDepthForBytes(Murmur3Partitioner, ⌊⌊s·2^20/3⌋/3⌋, 32)` (printed by the unit-tier harness, B2d amendment; if d is the same at 0.95× and 1.05× of the budget, an owning ratio within ±5 % of 1/3 cannot change it) and S = 3 × 2^d. Data term: P/3 ≈ 1,000,000 per range, ceil(log2) = 20 > d. H ≤ s × 1,048,576 B on every node at every s. Control: S = 3 × 2^10 = 3,072 at each s. Startup: as above, with the exact texts of the B3e amendment. Reason: the ratio, the absolute value and the control's S (three ranges, not one) were not stated.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| S ∝ s, histogram ≤ s | claim confirmed |
| S constant | budget not governing (claim wrong) |
| histogram bytes ≫ s | cap not bounding real heap (claim wrong for heap) |

**Amendment 2026-10-24 (step-0 audit) — B3g, definitions and rows added; the three rows above are unchanged.** "≫ s" means H > s MiB at any s on any node. Row 1 ("claim confirmed") needs on every node: S ×4 and ×4 exactly, S = 3 × 2^d at each s (the depth set by the budget, below the data term and the depth cap — the direct evidence that the budget, not the data, sized the trees), H ≤ s MiB, and the startup checks as predicted (0 rejected, 300 started with the warning). Added rows:

| Observation | Meaning |
|---|---|
| S moves with s but not ×4 exactly, or S ≠ 3 × 2^d at some s | the budget governs, not by the traced formula: not confirmed |
| startup with `0MiB` completes | the check at `:612` is ineffective: refuted for the rejection |
| startup with `300MiB` is refused | refuted for "warns only" (`:614`) |
| a read-back ≠ s, R ≠ 3, a `Created` line missing, a repair not exiting 0, or stress errors | invalid for that value |
| P/3 ≤ 2^d (data term binds) | invalid for that value |
| control S ≠ 3,072 | the observable does not respond to a known cap: invalid |
| no histogram sample during a repair shows `MerkleTree$OnHeap*` objects | H not measured: invalid for the histogram part |

**B3h. Controls.** Same repair with `repair_session_max_tree_depth` set to 10 → S = 2^10 regardless of s, showing the observable is sensitive to a known binding cap; GC noise excluded by using class histogram (live objects with `GC.class_histogram`, which forces full GC).

**B4. Risks and cleanup.** ≈1-2 GB per node on local disk; stop nodes, check `pgrep -f CassandraDaemon`, remove `/local/c509-node*`.

## C. Sources read

src/java/org/apache/cassandra/config/DatabaseDescriptor.java (596-616, 4086-4101)
src/java/org/apache/cassandra/config/Config.java (206-208)
src/java/org/apache/cassandra/repair/ValidationManager.java (50-90)
src/java/org/apache/cassandra/utils/MerkleTree.java (1520-1541)
src/java/org/apache/cassandra/service/ActiveRepairService.java (312-355)
test/unit/org/apache/cassandra/repair/ValidatorTest.java (230-295)
NEWS.txt (497, 819-820)

## D. Stage-4 feedback

**Stage 4 closed 2026-10-24** ([results](../../stage4-runtime-verification/results/repair_session_space-applySimpleConfig-repair_session_space--autonomous.md)); Claude Opus 5.5 (claude-opus-5-5), advisor's machine; estimate `positive` held. **Unit tier: Confirmed — caps** (one tree of exactly 2^d(s) leaves, 4,096 · 8,192 · 16,384 · 32,768 · 65,536 at 1 · 2 · 4 · 8 · 16 MiB, d from `estimatedMaxDepthForBytes`; `measureDeep(trees)` 0.47 × the limit at every s; control depth 12 → 4,096; `setRepairSessionSpaceInMiB(0)` → `ConfigurationException` "Cannot set repair_session_space to 0 < 1 mebibyte", value unchanged). **Cluster tier: Confirmed — caps** (three nodes, RF 3, 3 M partitions, three equal ranges per validation: S = 6,144 · 24,576 · 98,304 = 3 × 2^11 · 2^13 · 2^15 at 4 · 16 · 64 MiB and the unset default (64), identical on all nodes, ×4 per ×4; `MerkleTree$OnHeap*` histogram bytes ≤ 0.12 × s; control depth 10 → 3,072 at every s; `0MiB` refused at startup with "repair_session_space must be > 0, but was 0MiB", `300MiB` starts with the heap-pressure warning). Runbook defects (fixed before cluster run 1, dated above): B3b's `sjk … -mc -op setRepairSessionSpaceInMiB` cannot run (the knob is a JMX attribute: `-ms -f RepairSessionSpaceInMiB -v <s>`); B3d's S at `ValidationManager.java:85` is logged before `init()` and always equals the number of ranges (S read from `Validator.java:158`). Notes for stage 3, not applied: B1's formula omits the `+ inner` term (`MerkleTree.java:1539`) and the range-owning ratio (`ValidationManager.java:71`); the coordinator's off-heap received trees, the budget's own rationale, were not measured. The twelve amendments of 2026-10-24 (B2c, B2d, B2e, B2f, B2g, B3a, B3b, B3c, B3d, B3e, B3f, B3g) were made at the step-0 audit and the two runbook fixes after the harness shakedown; both hashes are in `_INDEX-advisor.md` §2, and this section was added after them.
