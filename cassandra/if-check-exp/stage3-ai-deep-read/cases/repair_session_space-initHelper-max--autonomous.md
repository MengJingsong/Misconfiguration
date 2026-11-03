# repair_session_space — verification solution  <!-- file: cases/repair_session_space-initHelper-max--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`MerkleTree.java:151`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L151) (`if (depth == max)` in `initHelper`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5[1m]), Claude Code CLI, 2026-10-26; Band D triage batch (MergeIterator / MerkleTree / MerkleTrees / MonotonicClock) |
| Estimate | `positive`. `max` at :151 is `min(log2(maxsize), hashdepth)`, and `maxsize` is `2^depth`, where `depth` comes from `repair_session_space / RF` in `ValidationManager.createMerkleTrees`. So the number of on-heap leaf/inner nodes built for each validation tree is capped at about `repair_session_space / RF` bytes. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `repair_session_space`: a configuration entry, declared at [`Config.java:207-208`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L207-L208) (`DataStorageSpec.IntMebibytesBound`, old name `repair_session_space_in_mb`). Unit: MiB. Default: `null`, which `DatabaseDescriptor.applySimpleConfig` replaces with `max(1, maxHeap / 16 MiB)` MiB, i.e. 1/16 of the heap ([`DatabaseDescriptor.java:609-610`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L609-L610)). Values below 1 MiB are rejected (`:612-613`). A warning is logged above heap/4 (`:614-615`). It is set with the yaml key `repair_session_space` (commented out in `conf/cassandra.yaml:840`), which needs a restart. At runtime it can be changed through JMX `org.apache.cassandra.db:type=RepairService` `RepairSessionSpaceInMiB` ([`ActiveRepairService.java:334-338`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L334-L338) -> `DatabaseDescriptor.setRepairSessionSpaceInMiB`, `:4091-4100`). The setting is read fresh for every validation ([`ValidationManager.java:62`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L62)), so a change applies to the next repair. There is no nodetool command for it in `src/java/org/apache/cassandra/tools`. A companion cap is `repair_session_max_tree_depth` (deprecated, default 20, [`DatabaseDescriptor.java:596-607`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L596-L607)).


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** It caps heap memory: the on-heap Merkle trees (`MerkleTree$OnHeapLeaf` / `$OnHeapInner` plus their 32-byte hash arrays and tokens) that one replica builds when it validates one table over the requested ranges. The usage-side quantity at the entry line is the recursion `depth` in `initHelper`, compared with `max`. Equivalently it is the tree's leaf count `size = 2^max` (`MerkleTree.java:140`). The budget is applied as bytes per range: `rangeAvailableBytes = ratio * repair_session_space*2^20 / RF`.

**A3. Mechanism.**
1. `ValidationManager.doValidation` -> `createMerkleTrees` ([`ValidationManager.java:135`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L135), `:54-91`). It sets `availableBytes = repair_session_space MiB * 1048576 / RF(allReplicas)` (`:62-63`, with the comment that the coordinator holds RF trees).
2. For each range: `rangeAvailableBytes = max(1, (int)(ratio * availableBytes))`, where `ratio` is the range's share of the estimated partitions (`:67-71`). `estimatedMaxDepth = MerkleTree.estimatedMaxDepthForBytes(partitioner, rangeAvailableBytes, 32)` (`:74`). That function measures one leaf plus one inner with `ObjectSizes.measureDeep` and returns `max(1, floor(log2((bytes+inner)/(leaf+inner))))` ([`MerkleTree.java:1520-1541`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L1520-L1541)). Then `maxDepth = min(estimatedMaxDepth, repair_session_max_tree_depth)` (`:75-77`) and `depth = min(ceil(log2(numPartitions)), maxDepth)` (`:79`). Finally `trees.addMerkleTree((int) 2^depth, range)` (`:80`), and `MerkleTrees.addMerkleTree` builds a tree with `hashdepth = RECOMMENDED_DEPTH = 126` ([`MerkleTrees.java:108-116`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTrees.java#L108-L116), [`MerkleTree.java:89`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L89)).
3. `Validator.prepare`: for a non-order-preserving partitioner (Murmur3, the default) it calls `trees.init()` ([`Validator.java:122-125`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/Validator.java#L122-L125)). `MerkleTree.init()` computes `sizedepth = floor(log10(maxsize)/log10(2))` and `depth = min(sizedepth, hashdepth)` ([`MerkleTree.java:136-137`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L136-L137)), then calls `initHelper(..., 0, depth)`.
4. **Entry line** [`MerkleTree.java:151`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L151): when the recursion `depth == max`, it returns a leaf. Otherwise it creates an `OnHeapInner` with two children (`:154-160`). Result: a full binary tree with `2^max` leaves and `2^max - 1` inners, all on heap. A recursion can also stop early with a leaf when the midpoint equals an end (`:155-156`), which only makes the tree smaller.
5. Order-preserving partitioners use `split()` instead, where the cap is `size >= maxsize` ([`MerkleTree.java:409-410`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L409-L410)).
6. When validation completes, the tree is sent to the coordinator. A local initiator moves it off-heap ([`Validator.java:296-301`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/Validator.java#L296-L301), [`MerkleTree.java:769-783`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L769-L783)), and remote trees are deserialized off-heap when `use_offheap_merkle_trees` is true ([`Config.java:212`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L212), [`MerkleTree.java:707`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L707)).

Overshoots and bypasses:
- The budget applies per validation (one table x one request's ranges), not per node. Repairing several tables, keyspaces or vnode ranges at once multiplies it, unless `concurrent_merkle_tree_requests` (default 0 = unlimited, [`Config.java:210`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L210)) is set. `conf/cassandra.yaml` says this explicitly ("can exceed this limit").
- The byte estimate is approximate: it uses `measureDeep` on a sample, and leaves gain `sizeOfRange`/`partitionsInRange` but no extra objects.
- The floor in `estimatedMaxDepthForBytes` is 1. `ratio` uses estimated partition counts, so the per-range shares can add up to more than 1 if the estimates are skewed.

**A4. Other consumers.** Other repair heap usage is outside this cap: the validation compaction's own read path (`CassandraValidationIterator`), row hashing buffers, `TopPartitionTracker`, streaming after the diff, and the coordinator's off-heap copies of the RF trees (direct memory, sized by the same `size`). Everything else on the node (memtables, caches, reads) shares the heap.

**A5. Evidence beyond the source.** `conf/cassandra.yaml:827-861` (comments for `repair_session_space` and `concurrent_merkle_tree_requests`). CASSANDRA-14096 (https://issues.apache.org/jira/browse/CASSANDRA-14096), CASSANDRA-11390 and CASSANDRA-19336 (`CHANGES.txt:2111`, `:3030`). `test/unit/org/apache/cassandra/repair/ValidatorTest.java:235-283` (`testSizeLimiting`: at 1 MiB and 2^14 rows the tree has 2^12 leaves) and `:294-` (`testRangeSplittingTreeSizeLimit`).

## B. Verification solution

**B1. Claim under test.** For a Murmur3 table validated in one repair session, the Merkle tree a replica builds has exactly `2^d` leaves, where `d = min(floor(log2(S*2^20/RF / c)), 20, ceil(log2 partitions))`, `S = repair_session_space` in MiB, and `c` = bytes per leaf+inner pair (about 200 B). Its heap footprint is at most `S/RF` MiB. Doubling `S` doubles the tree, until the partition cap or the depth-20 cap takes over.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Clone the repo to local disk: `git clone --branch cassandra-5.0.9 --depth 1 file:///<shared>/cassandra-src /local/c509 && cd /local/c509 && ant jar build-test`. Add the test source `test/unit/org/apache/cassandra/repair/RepairSessionSpaceProbeTest.java` in the local clone only. Use the default unit-test JVM options from `build.xml`; the test heap is enough at 2^18 rows.

> **Amendment U1 (2026-10-27, stage-4 audit; host paths only).** On the advisor's Mac (no `/local`, no `mkdir` in `$HOME`): clone
> `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run60` (`W=~/Library/Caches/stage4`), build with
> `ant -Dlocal.repository=$W/m2 build-test`. The test source is `harness/repair_session_space-initHelper-max--autonomous/RepairSessionSpaceProbeTest.java`,
> copied into the clone's `test/unit/org/apache/cassandra/repair/` by `unit-run.sh`. The forked test JVM has `-Xmx1024m`
> (`build.xml:1153`, `maxmemory="1024m"`) and `-XX:ActiveProcessorCount=2`; the test timeout is raised with `-Dtest.timeout=1800000`.

**B2b. Knobs.** Set `S` in {1, 2, 4, 8, 16} MiB with `DatabaseDescriptor.setRepairSessionSpaceInMiB(S)` before each validation. These values put `d` below both other caps (partitions 2^18 -> 18, max depth 20), so `S` is the binding term. Control: `S = 64` (the estimate is about 18, where the partition cap of 18 also binds).

**B2c. Workload.** Copy the `ValidatorTest.testSizeLimiting` structure (`ValidatorTest.java:235-283`): keyspace `KeyspaceParams.simple(1)` (RF=1), `CompactionsTest.populate(ks, cf, 0, 1<<18, 0)`, flush, then one `RepairJobDesc` over `(first token, last token]` of the single sstable. Use a `Validator(..., evenTreeDistribution=true, ...)` with remote initiator `127.0.0.2`, `ValidationManager.instance.submitValidation`, and capture the `ValidationResponse` through the outbound sink (`registerOutgoingMessageSink` as in that test). Arithmetic: `S*2^20/200` = 5243 (S=1, d=12), 10486 (13), 20972 (14), 41943 (15), 83886 (16). All are well below 2^18 partitions.

> **Amendment U2 (2026-10-27, stage-4 audit; exact workload).** `CompactionsTest.populate(ks, cf, 0, 1<<18, 0)` writes keys
> 0..2^18 **inclusive** (`CompactionsTest.java:120`, `i <= endRowKey`), 10 rows each, so 2^18 + 1 partitions; the range
> `(first token, last token]` excludes the first partition, so exactly 2^18 are hashed (`rowCount`). The data are populated
> **once**, flushed with autocompaction disabled, and every S (and the control) validates the same SSTables (B2h: same data and
> range for all S; B2e's repopulate option is not used). If the 1 GiB test heap flushes the memtable more than once, the range is
> taken over all live SSTables (smallest `first`, largest `last`); the SSTable count is printed. The test also prints the
> partition estimate the validation uses, `estKeys` = sum of `estimatedKeysForRanges` over the live SSTables
> (`CassandraValidationIterator.java:228-236`), and its depth `pc = ceil(log2 estKeys)`; with RF = 1 and one range the space
> budget is exactly `S*2^20` (`ValidationManager.java:62-71`, ratio 1), so `d_est = estimatedMaxDepthForBytes(p, S*2^20, 32)` and
> the expected tree is `2^min(d_est, 20, pc)` (`:74-80`). Order: S = 1, 2, 4, 8, 16, then the control S = 64.

> **Runbook-defect fix D1 (2026-10-27, stage 4, found by the harness shakedown before unit run 1; B2f/B2g unchanged).** Copying
> the `ValidatorTest` structure (`SchemaLoader.prepareServer()` with the unit yaml) creates the table under the unit yaml's
> partitioner, `ByteOrderedPartitioner` (`test/conf/cassandra.yaml:18`), not Murmur3, which B1 and B2f assume (B2f's `c` ≈ 200 B
> uses Murmur3's fixed-size `LongToken`; a byte-ordered token has a variable size, and `estimatedMaxDepthForBytes` sizes it from the
> empty minimum token). The test therefore calls `DatabaseDescriptor.setPartitionerUnsafe(Murmur3Partitioner.instance)`
> (`DatabaseDescriptor.java:2002-2007`) after `prepareServer()` and before the keyspace is created, as
> `RepairMessageVerbHandlerOutOfRangeTest.java:84` does, and prints the table's partitioner in its `config` line; a line that does
> not show `Murmur3Partitioner` makes the run Invalid. The validator keeps `evenTreeDistribution=true`; with Murmur3 the
> `trees.init()` branch is taken anyway (`Validator.java:122-125`).

**B2d. Observables and instruments.**
- (1) `tree.size()`: the leaf count, `2^max` at :151.
- (2) The log line `MerkleTree.estimatedMaxDepthForBytes(partitioner, S*2^20, 32)` printed by the test, to get the exact `d` for this JVM.
- (3) `ObjectSizes.measureDeep(tree) - ObjectSizes.measureDeep(partitioner)` (`ObjectSizes.java:230`): the tree's heap bytes.
- (4) `trees.rowCount()`, to confirm all 2^18 partitions were hashed.

The tree's lifetime peak inside a running validation cannot be observed directly; (3) measures it after completion, which is the same object.

**B2e. Procedure.**
1. Write the test with one `@Test` per S (or a loop with `cfs.clearUnsafe()` and repopulate between iterations). Print `S, d_est, size, bytes, rowCount`.
2. `ant testsome -Dtest.name=org.apache.cassandra.repair.RepairSessionSpaceProbeTest`.
3. Run the init-only control in the same class: `new MerkleTree(Murmur3Partitioner.instance, fullRange, 126, 1L<<k).init()` for k in {8, 12, 16} checks `size()==2^k`. With `hashdepth=5` and `maxsize=2^12` it should give `size()==32`.
4. Collect the output from `build/test/logs` / `build/test/output`.

> **Amendment U3 (2026-10-27, stage-4 audit; exact output and one more observable).** One `@Test` runs the sweep and the control
> (U2), then the init-only controls. Per validation it prints one line
> `STAGE4 reading sweep|control s=<S> readback=<S read back> sstables=<n> estKeys=<n> pc=<n> d_est=<n> expected=<2^min(d_est,20,pc)>
> size=<tree.size()> leaves=<leaf count> rowCount=<n> bytes=<measureDeep(tree) - measureDeep(partitioner)> limit=<S*2^20>`.
> `leaves` counts the tree's leaves by walking `MerkleTrees.rangeIterator()` (`MerkleTrees.java:263`), because `size()` is a field
> set by `init()` (`MerkleTree.java:146`), not a count of the nodes built at :151. `bytes` is measured before `rowCount`
> (`rowCount` only walks leaves, `MerkleTree.java:490-500`). The response is captured by the outbound sink and not serialized, so
> the inner nodes keep the shared empty hash (`MerkleTree.java:1256`, hashes are filled only by `fillInnerHashes`): `bytes` is the
> tree as built and hashed by the validation. Init-only controls print
> `STAGE4 reading init k=<k> hashdepth=<h> size=<n> leaves=<n>` for (126, 2^8), (126, 2^12), (126, 2^16) and (5, 2^12), with
> `fullRange = (min token, min token]` of Murmur3. Value lines (not readings) `STAGE4 value cluster_d s=<S> budget=<S*2^20/3> d=<n>`
> give, for B3f, the exact `estimatedMaxDepthForBytes` of the cluster budgets in this JDK (S = 1, 4, 16, 64, 127, 128, 1024).
> Output goes to stdout and to the file named by `-Dstage4.out` (passed with `-Dtest.jvm.args`).

**B2f. Predictions.** `size == 2^d_est` exactly, for every S. `d_est` = 12, 13, 14, 15, 16 for S = 1, 2, 4, 8, 16 (± 1 if the measured `c` differs from about 200 B; the test's own `d_est` is authoritative). `bytes <= S*2^20` and `bytes >= 0.5*S*2^20` (floor of log2). Each step doubles `size` and roughly doubles `bytes`. S=64 gives `size == 2^18` (partition cap). `rowCount == 2^18` everywhere. Controls: `2^k`, and 32.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `size == 2^d_est`, doubling with S, `bytes <= S MiB` | Claim confirmed at the unit level |
| `size` the same for all S | Claim wrong: S does not reach :151 (look for another cap) |
| `bytes > S MiB` for some S | The cap is approximate: the `c` estimate is too low, so usage overshoots |
| S=64 gives `2^18`, not more | Partition cap binds as traced (positive control for the mechanism) |
| init-only control gives a size other than `2^k` / 32 | :151 / :136-137 does not behave as traced |

> **Amendment U4 (2026-10-27, stage-4 audit; verdict words and missing rows; no prediction changed).** Checked in this order:
> **Invalid** — the test does not print six validation lines and four `init` lines; a `readback` differs from the S set; `rowCount`
> differs from 2^18 in a line; or `pc` ≤ `d_est` for some S in 1..16 (then S is not the binding term, B2b).
> **Refuted** (rows 2 and 5) — `size` is the same for S = 1..16; or an init-only control gives a size or leaf count other than
> 2^k / 32. **Refuted, Effect caps** (row 3) — `size` follows `2^d_est` but `bytes > limit` for some S (B1's "at most S/RF MiB"
> fails; the setting still sets the tree size).
> **Confirmed** (rows 1 and 4) — for S = 1..16: `size == expected == 2^d_est`, `leaves == size`, `size` doubles at each step,
> `0.5*limit <= bytes <= limit`; the control S = 64 gives `size == leaves == 2^18`; the four init controls give 2^8, 2^12, 2^16 and 32.
> Direct evidence that the :151 branch stopped the recursion: `leaves == 2^d_est < rowCount` (fewer leaves than hashed partitions)
> and the init controls. Which cap binds at S = 64 is reported from `d_est` and `pc` (B2b expects both near 18); it does not change
> the verdict.
> **Not confirmed** — anything else, listed: `size` moves with S but differs from `2^d_est` for some S; `leaves != size`;
> `bytes < 0.5*limit`; or the S = 64 tree is not 2^18. A `d_est` outside B2f's 12..16 (±1) is recorded but does not change the
> verdict (B2f: the test's own `d_est` is authoritative).

**B2h. Controls.** The same data and range for all S, so only S changes. `rowCount` is constant. The init-only control isolates :151 from `createMerkleTrees`. RF=1 removes the RF divisor.

### B3. Cluster tier

**B3a. Environment and build.** Three Linux nodes, or one host with three loopback addresses through ccm (`ccm create rss --install-dir=/local/c509 -n 3`). Build with `ant jar` in the local clone. Each node: `MAX_HEAP_SIZE=2G`, `HEAP_NEWSIZE=400M`, `num_tokens: 1` (one primary range per node), `use_offheap_merkle_trees: true` (default). Data, commitlog and hints go on local disk with at least 10 GB free per node.

> **Amendment C1 (2026-10-27, stage-4 audit; host ring, no ccm).** ccm is not installed on this host. Three nodes on one host,
> `127.0.0.1`, `127.0.0.2`, `127.0.0.3` (loopback aliases on `lo0`), all run from the unit tier's clone `$W/cassandra-run60` after the
> unit tier has finished (no `ant` runs while a node is up), each with its own generated `conf/` and its data, commit log, hints,
> saved caches and cdc_raw under `$W/node-rssih/n<i>/` (internal SSD, APFS). Per node the yaml is the tag's `conf/cassandra.yaml`
> plus `cluster_name: rssih`, `num_tokens: 1`, `initial_token` -9223372036854775808 / -3074457345618258603 / 3074457345618258602
> (evenly spaced, so each primary range is one third of the ring), `auto_bootstrap: false` (bootstrap streaming fails on this host;
> the ring is empty when it forms), `listen_address` = `rpc_address` = the node's address, seed `127.0.0.1:7000`; JMX ports 7199 /
> 7299 / 7399 (`cassandra-env.sh`). `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`; `use_offheap_merkle_trees` stays at its default (true).
> Nodes start one after another as tracked background processes (`bin/cassandra -f`), each waited for until `nodetool status`
> shows it `UN` and `statusbinary` prints `running`. Scripted in `harness/repair_session_space-initHelper-max--autonomous/cluster-run.sh`
> (with `make-node-conf.sh`).

**B3b. Knobs.** `repair_session_space` in {1, 4, 16, 64} MiB, set in each node's `cassandra.yaml` with a rolling restart before each step (or through JMX `RepairSessionSpaceInMiB` on all three nodes). Positive control: `1024MiB` (above heap/4, which only warns). With that value the depth-20 / partition cap binds. Default for reference: 2048/16 = 128 MiB.

> **Amendment C2 (2026-10-27, stage-4 audit; how the knob is set, and the default added as a value).** No rolling restart: S is set
> through JMX, attribute `RepairSessionSpaceInMiB` of `org.apache.cassandra.db:type=RepairService` (`ActiveRepairServiceMBean.java:50-51`,
> a setter/getter pair, so an attribute, not an operation), on all three nodes, with the harness's JMX client `JmxAttr`, and read back
> on all three before each repair (`DatabaseDescriptor.java:4091-4100` accepts any S ≥ 1 and only warns above heap/4). Group A needs
> the default among the values: the node's own default (`max(1, maxMemory/16 MiB)`, `DatabaseDescriptor.java:609-610`; 127 or 128
> with `-Xmx2G`, depending on how the collector reports `maxMemory`) is read back at the start and run first, before any set, as
> label `default`. Order: `default`, 1, 4, 16, 64, then the control 1024; three repairs per value.

**B3c. Workload.** `tools/bin/cassandra-stress write n=3000000 cl=ALL -schema "replication(factor=3)" keyspace=rss -col "size=FIXED(64)" "n=FIXED(1)" -rate threads=50 -node 127.0.0.1`, then `nodetool flush` on all nodes. Each node then holds about 3M partitions, about 1M per primary range, so the partition cap is `ceil(log2 1e6) = 20`. Per range the budget is `S/3`: at c ≈ 200 B, `d` = 10, 12, 14, 16 for S = 1, 4, 16, 64, and 20 for the control. Repair: `nodetool -h node1 repair -full -pr rss standard1`, which gives one range and three replicas validating. Each repair takes seconds to a minute. Repeat each S three times.

> **Amendment C3 (2026-10-27, stage-4 audit; exact load and repair commands).** Load: `tools/bin/cassandra-stress write n=3000000
> cl=ALL -schema "replication(factor=3)" keyspace=rss -col "size=FIXED(64)" "n=FIXED(1)" -rate threads=50 -node 127.0.0.1` (as filed;
> stress's warm-up is kept). Then `nodetool flush rss standard1` on each node; wait until no compaction is active and the SSTable
> count is unchanged for 30 s (with a 600 s limit); then `nodetool disableautocompaction rss standard1` on each node (no node restarts
> during the tier), so every repair validates the same SSTables. Recorded per node: SSTable count and `Number of partitions (estimate)`
> from `nodetool tablestats rss.standard1`. Stress keys can collide (legacy keys), so the stored count may be slightly below 3M; the
> partition cap is checked per repair from the `P partitions` field of the `ValidationManager.java:85` line instead: it must be above
> 2^19 = 524,288 so that `ceil(log2 P)` ≥ 20 and only S (or depth 20) binds. Repair: `nodetool -h 127.0.0.1 -p 7199 repair -full -pr rss
> standard1`, one at a time, each with a 900 s limit.

**B3d. Observables and instruments.**
- (1) The `DEBUG` lines from `ValidationManager.java:85` ("Created 1 merkle trees with merkle trees size N, P partitions, B bytes") and `Validator.java:158` ("Prepared AEService trees of size N"), enabled with `nodetool setlogginglevel org.apache.cassandra.repair DEBUG`, on all nodes.
- (2) Actual heap: during the repair, poll `jcmd <pid> GC.class_histogram | egrep 'MerkleTree\$OnHeap(Leaf|Inner)'` every 0.5 s on node2. Record the peak `#instances` and `#bytes` (shallow), and add `48 B * instances` for the hash arrays and `24 B * inners` for `LongToken`.
- (3) Context only: heap after GC from `nodetool gcstats` / `jstat -gc 1000`.

The validation window is short, so it may fall between samples. If no sample shows the classes, raise `n` to 10M; per-range depth is unchanged because S binds.

> **Amendment C4 (2026-10-27, stage-4 audit; observables made exact).** (1) N is read from the `Validator.java:158` line ("Prepared
> AEService trees of size N"), one per replica per repair. The `ValidationManager.java:85` line is logged **before** `init()`, when
> each tree's `size` is still the constructor's 1 (`MerkleTree.java:110`; `init()` sets it at `:146`), so its "size" field is not N;
> that line is used only for `P partitions`. Both are read from each node's `debug.log` (the shipped `logback.xml:132` already logs
> `org.apache.cassandra` at DEBUG; `setlogginglevel` is run as well), only from bytes written after the repair started.
> (2) `jstat` cannot attach on this host and is dropped from (3); (3) is not recorded. The histogram poller runs on node2 as filed
> (`jcmd <pid> GC.class_histogram`, a live-object histogram, then `sleep 0.5`; each sample is time-stamped, so the real interval is
> recorded). An idle histogram of node2 is taken just before each repair. A sample's tree counts are its `MerkleTree$OnHeapLeaf` and
> `MerkleTree$OnHeapInner` instances minus the idle histogram's; its derived heap is
> `leaf #bytes + inner #bytes (shallow, minus idle) + 48 B x (leaf + inner instances) + 24 B x inner instances`, as filed. The
> repair's reading is the sample with the most leaf instances over its samples; per value, the largest over the three repairs.
> "Caught" means a sample with leaf instances in [N, N+2] and inner instances in [N-1, N] (the +2/+1 allow the transient two
> leaves and one inner of a concurrent `estimatedMaxDepthForBytes`, `MerkleTree.java:1522-1527`).

**B3e. Procedure.**
1. Create, configure and start the cluster, then run stress and flush.
2. For each S (ascending), then the control: set S, rolling restart, set DEBUG logging, start the histogram poller on node2 (`while true; do date +%s.%N; jcmd $PID GC.class_histogram | egrep 'OnHeap(Leaf|Inner)'; sleep 0.5; done > hist_S.txt &`), run the repair, stop the poller, and grep the debug lines from `logs/debug.log`.
3. Tabulate N (tree size), the peak leaf/inner instances, and the derived bytes per S.

> **Amendment C5 (2026-10-27, stage-4 audit; exact sequence and stop conditions).** `cluster-run.sh`: pre-checks (no Cassandra
> process, ports 7000/7199/7299/7399/9042 free, `lo0` has .2 and .3); build the three confs; start the ring (C1; abort if a node
> is not up in 360 s or its process dies); load (C3); for each label in the C2 order: set S on all nodes (not for `default`), read
> back on all nodes, idle histogram of node2, start the node2 poller, run the repair, stop the poller, cut each node's `debug.log`
> after the start offset and grep the two lines, tabulate; three repairs per label. A repair with exit ≠ 0 or without three
> `Validator.java:158` lines is recorded and the run goes on. Fallback (B3d): if for some label no repair catches the tree (C4),
> after the last label the script loads 10M keys on the same ring (`n=10000000`, same command; keys 1..3M are overwritten),
> flushes and waits as in C3, and repeats only the uncaught labels (three repairs each); those readings are reported next to the
> first ones. Then all nodes are drained and stopped, no Cassandra process may remain, and `$W/node-rssih` is removed.

**B3f. Predictions.**
- N = 2^d on all three replicas: about 1024, 4096, 16384, 65536 for S = 1, 4, 16, 64 (exact `d` from the formula with the node's measured `c`), and 2^20 = 1048576 for S = 1024.
- Peak `OnHeapLeaf` instances ≈ N and `OnHeapInner` ≈ N-1 (plus the one sampled tree).
- Derived heap ≤ S/3 MiB for S ≤ 64: 0.33, 1.33, 5.3, 21 MiB.
- The control gives about 200 MiB (≈ 2^20 x 200 B), which is less than 1024/3 MiB, because the depth-20 cap binds.

> **Amendment C6 (2026-10-27, stage-4 audit; exact d, the default value, bands; no filed prediction changed).** The exact `d` for
> S = 1, 4, 16, 64, 1024 is `min(estimatedMaxDepthForBytes(Murmur3, S*2^20/3, 32), 20)` as printed by the unit tier's
> `STAGE4 value cluster_d` lines (same JDK and object layout), with `ratio = 1` because a `-pr` repair requests one range
> (`ValidationManager.java:67-71`). Added value `default`: N = 2^d with d from the `cluster_d` line of the read-back default (127 or
> 128; B3f's formula at c ≈ 200 B gives 17 for both), derived heap ≤ default/3 MiB. "Double per S step" in B3g row 1 means "follows
> 2^d": the filed S steps are x4, so N grows x4 per step (d + 2), as B3f's numbers already say. "About 200 MiB" for the control
> means within ±10% of 2^20 x 200 B = 200 MiB, and below 1024/3 MiB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| N and peak instances double per S step, heap ≤ S/3 MiB | Claim confirmed: the setting governs actual tree heap |
| N the same for all S | Claim wrong: another term binds (check partition count, `repair_session_max_tree_depth`) |
| Heap > S/3 MiB with one table/range | The estimate undershoots: an approximate cap |
| Control shows 2^20 / ~200 MiB | Instrument and workload can show large trees (positive control); the low-S values were bound by S |
| Histogram never catches the classes | Not confirmed by heap; rely on (1) and repeat with a larger n |

> **Amendment C7 (2026-10-27, stage-4 audit; verdict words and missing rows).** Checked in this order:
> **Invalid** — the ring is not three `UN` nodes; stress reports errors; a read-back S differs from the value set on some node; for
> some label no repair gives three `Validator.java:158` lines; or `P` ≤ 2^19 in a repair (C3: the partition cap could bind).
> **Refuted** (row 2) — N is the same for every label. **Refuted, Effect caps** (row 3) — N follows 2^d but the caught derived heap
> exceeds S/3 MiB for some S ≤ 64 or the default.
> **Confirmed** (rows 1 and 4) — in every repair N = 2^d (C6) on all three replicas for `default`, 1, 4, 16, 64, and N = 2^20 for
> 1024; for every label the tree is caught (C4) in at least one repair (first run or fallback), with derived heap ≤ S/3 MiB for
> S ≤ 64 and the default, and the control's derived heap within the C6 band. Direct evidence that the :151 branch fired: N < P
> (fewer leaves than partitions in the range) with inner instances = N - 1.
> **Not confirmed** — anything else, listed: N moves with S but differs from 2^d (C6) in some repair or replica; a label whose tree
> is not caught even after the fallback (row 5); peak instances outside the C4 window for every sample of a label although a tree
> was seen (counter or log not matched by the objects); the control outside its band.

**B3h. Controls.** The same data for all S, `-full -pr` on the same node, and one table per repair, so the `concurrent_merkle_tree_requests` multiplication (A3) is excluded. Optional extra: repair two tables at once with S=16 and show that the total instances are about twice one tree's. That demonstrates the per-validation scope.

**B4. Risks and cleanup.** Never build in the shared clone. Stress data is about 3M x ~100 B x 3 replicas, under 2 GB per node, on local disk. Afterwards: `ccm stop && ccm remove rss` (or `nodetool stopdaemon` on each node), `pkill -f cassandra-stress`, check that `pgrep -f CassandraDaemon` is empty, and remove `/local/c509/build/test` output if space is needed. The unit test runs in a forked JUnit JVM that exits; check for none left with `pgrep -f junit`.

> **Amendment C8 (2026-10-27, stage-4 audit; host cleanup).** No ccm: cleanup is C5's last step (drain and stop each node, check
> `ps -eo command | grep '[C]assandraDaemon'` and `pgrep -f cassandra-stress` are empty, remove `$W/node-rssih`); the copied test file
> is removed from `$W/cassandra-run60` afterwards and `git status` there must be clean.

## C. Sources read

- src/java/org/apache/cassandra/utils/MerkleTree.java
- src/java/org/apache/cassandra/utils/MerkleTrees.java
- src/java/org/apache/cassandra/repair/ValidationManager.java
- src/java/org/apache/cassandra/repair/Validator.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/service/ActiveRepairService.java
- src/java/org/apache/cassandra/utils/ObjectSizes.java
- conf/cassandra.yaml
- test/unit/org/apache/cassandra/repair/ValidatorTest.java
- CHANGES.txt
- https://issues.apache.org/jira/browse/CASSANDRA-14096 (cited, as referenced in the yaml)

## D. Stage-4 feedback

2026-10-27, stage 4 run 1 on the advisor's Mac (Claude Opus 5.5, claude-opus-5-5[1m]); results:
[`../../stage4-runtime-verification/results/repair_session_space-initHelper-max--autonomous.md`](../../stage4-runtime-verification/results/repair_session_space-initHelper-max--autonomous.md).
Audit: Ready after amendments U1–U4, C1–C8 (frozen `8aa77acf…`); runbook defect D1 (the unit yaml's partitioner is ByteOrderedPartitioner;
the test now sets Murmur3), fixed before any run-1 reading (`d14bc66c…`); both tiers ran at `d14bc66c…`. Not committed yet.
**Unit: Confirmed — caps.** Leaves = `size` = 2^d_est = 4,096 … 65,536 for S = 1 … 16 MiB (doubling), with 2^18 partitions hashed;
`measureDeep` of the tree 0.59 × S MiB; S = 64 gives 2^18 (bound by d_est = 18; the partition cap is 19 because the estimate is 262,784
keys, not 18 as B2b expected); init controls exact. **Cluster: Confirmed — caps.** Three loopback nodes, RF 3, 3M partitions, `-full -pr`:
N = 2^d on all three replicas in all 18 repairs (default 128 MiB → 2^17; 1 / 4 / 16 / 64 MiB → 2^10 / 2^12 / 2^14 / 2^16; 1024 MiB → 2^20),
node2's live histogram shows exactly N leaves and N − 1 inners, derived heap 0.586 × S/3 MiB, control 200.0 MiB. Notes for stage 3:
A3 step 3's `MerkleTree.java:136-137` is `:142-143`; the `ValidationManager.java:85` debug line logs the tree size before `init()` (always 1),
so N must be read from `Validator.java:158`; the heap/4 warning of `setRepairSessionSpaceInMiB` prints the previous value
(`DatabaseDescriptor.java:4097`).
