# bloom_filter_fp_chance — verification solution  <!-- file: cases/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`FilterFactory.java:63`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/FilterFactory.java#L63) (`if (maxFalsePosProbability == 1.0)`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5[1m]), Claude Code CLI, 2026-10-26 (Band D triage batch) |
| Estimate | `positive`: the table option `bloom_filter_fp_chance` sets the bits per partition key of each SSTable's off-heap Bloom filter bitset (and its `Filter.db` file); `1.0` removes the filter entirely (0 bytes). Usage follows the knob per key, but it is a per-key sizing knob, not an absolute cap: total grows with partition count. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `bloom_filter_fp_chance`, a per-table schema option (CQL
`CREATE/ALTER TABLE ... WITH bloom_filter_fp_chance = x`).
- Declared: `TableParams.bloomFilterFpChance` field, [`TableParams.java:76`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L76); builder default `-1` at [`TableParams.java:358`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L358), resolved at [`TableParams.java:99-101`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L99-L101) to `CompactionParams.defaultBloomFilterFbChance()` = `0.1` for LCS, `0.01` otherwise ([`CompactionParams.java:261-264`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/CompactionParams.java#L261-L264)).
- Parsed from CQL: [`TableAttributes.java:110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/schema/TableAttributes.java#L110); persisted in `system_schema.tables` ([`SchemaKeyspace.java:579`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/SchemaKeyspace.java#L579), read back `:1065`).
- Unit: probability (dimensionless). Valid range `(minSupportedBloomFilterFpChance(), 1.0]` ([`TableParams.java:160-166`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L160-L166); min = `probs[20][14]` = 6.71e-05, [`BloomCalculations.java:195-200`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/BloomCalculations.java#L195-L200), table at `:44-67`).
- Settable online by `ALTER TABLE`; no restart. Takes effect only for SSTables written (flush, compaction, `upgradesstables -a`, `scrub`) after the change, except the `1.0` case, which also takes effect when an existing SSTable is reopened (A3 step 5).


**Limit type (2026-10-29).** non-config: per-table/per-index option. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Off-heap memory (native, `Memory.allocate`) of every SSTable's
Bloom filter, and the disk size of the `Filter.db` component. The quantity it
determines is `bucketsPerElement` (bits per key); bitset size =
`ceil((numElements * bucketsPerElement + 20) / 64) * 8` bytes
(`FilterFactory.java:70-75`, `utils/obs/OffHeapBitSet.java:39-48`).

**A3. Mechanism.**
1. A writer opens its index writer and calls `FilterFactory.getFilter(keyCount, params.bloomFilterFpChance)` (`io/sstable/format/SortedTableWriter.java:445`). `keyCount` is the memtable partition count at flush (`db/memtable/Flushing.java:117,207-210`) or the compaction writer's estimate (`db/compaction/writers/CompactionAwareWriter.java:235`).
2. Target line [`FilterFactory.java:63`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/FilterFactory.java#L63): if the fp chance is exactly `1.0`, return the singleton `AlwaysPresent` filter (no allocation; `offHeapSize()` and `serializedSize()` are 0, [`FilterFactory.java:77-120`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/FilterFactory.java#L77-L120)). Otherwise:
3. `maxBucketsPerElement(numElements)` = min(20, (Long.MAX_VALUE-20)/n) ([`BloomCalculations.java:180-189`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/BloomCalculations.java#L180-L189)), so 20 for any realistic n; `computeBloomSpec(20, fp)` ([`BloomCalculations.java:140-173`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/BloomCalculations.java#L140-L173)) picks the smallest bucket count whose optimal-K probability is <= fp. Worked from the table: fp 0.001 -> 15 bits (K=7); 0.01 -> 10 bits (K=6); 0.1 -> 5 bits (K=3). Trivial branch [`BloomCalculations.java:147-150`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/BloomCalculations.java#L147-L150): for fp >= 0.393 it returns `new BloomSpecification(2, optKPerBuckets[2])`, i.e. K=2 and bucketsPerElement = `optKPerBuckets[2]` = 1 (arguments appear swapped; constructor is `(k, bucketsPerElement)`, `:114`). So any fp in [0.393, 1.0) gives 1 bit per key.
4. `createFilter` allocates `OffHeapBitSet(numBits)` ([`FilterFactory.java:70-75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/FilterFactory.java#L70-L75)), i.e. native memory via `Memory.allocate` ([`OffHeapBitSet.java:47-48`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/obs/OffHeapBitSet.java#L47-L48)). The filter is serialized to `Filter.db` only when the FILTER component was added, which happens iff `shouldUseBloomFilter(fp)` i.e. fp != 1.0 (tolerance 0) (`SortedTableWriter.java:448-461,496-507`; `FilterComponent.java:43-44,141-144`).
5. On SSTable open, `FilterComponent.maybeLoadBloomFilter` returns `AlwaysPresent` if the current table fp is 1.0, without loading `Filter.db` ([`FilterComponent.java:99-111`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/FilterComponent.java#L99-L111)); a changed non-1.0 fp does not trigger a rebuild (`rebuildFilterOnFPChanceChange = false`, `:43,119`). Missing filters are rebuilt with the current fp (`big/BigSSTableReaderLoadingBuilder.java:207`, `bti/BtiTableReaderLoadingBuilder.java:156`).
- Overshoot/bypass: total off-heap is the sum over SSTables, so it is unbounded in partition count; compaction-time `keyCount` is an estimate, so the bitset can be over- or under-sized relative to actual keys; during compaction both input and output filters coexist.
- Note: `FilterFactory.getFilter(long,int)` (line 41-51) has no production callers.

**A4. Other consumers.** Other off-heap users outside this knob: index summaries
(`index_summary_capacity`), compression metadata, memtable off-heap allocators,
chunk/network buffer pools, SAI/ trie indexes, direct buffers. Disk: `Data.db`,
indexes, commit log, hints, snapshots.

**A5. Evidence beyond the source.** `doc/modules/cassandra/pages/managing/operating/bloom_filters.adoc`
(states RAM grows as fp falls, and that 0.01 needs "about three times" the memory of 0.1;
the code gives 10 vs 5 bits, i.e. 2x, a claim this solution can check). Tests:
`test/unit/org/apache/cassandra/utils/BloomFilterTest.java` (e.g. `getFilter(10, 1)` at line 166 uses the int overload).
Metrics: `BloomFilterOffHeapMemoryUsed` / `BloomFilterDiskSpaceUsed`
(`io/sstable/filter/BloomFilterMetrics.java:60-72`), printed by `nodetool tablestats`
(`tools/nodetool/stats/TableStatsPrinter.java:131-134`).

## B. Verification solution

**B1. Claim under test.** For a fixed number of partition keys N in an SSTable, the
Bloom filter's off-heap bytes (and `Filter.db` size) equal
`ceil((N*b(fp)+20)/64)*8` with b(0.001)=15, b(0.01)=10, b(0.1)=5, b(0.5)=1, and are 0
when fp = 1.0; so off-heap usage follows `bloom_filter_fp_chance`. The claim is wrong
if usage does not change with fp at fixed N, or the ratios differ materially from 15:10:5:1:0.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. `git clone --branch cassandra-5.0.9 <shared clone> /local/c509 && cd /local/c509 && ant jar build-test`. Test source: `/local/c509/test/unit/org/apache/cassandra/utils/BloomFpChanceSizeTest.java` (local clone only). JVM default test options from `build.xml`; add `-XX:NativeMemoryTracking=summary` via `-Dtest.jvm.args` is not needed for the primary reading.

> **Amendment U1 (2026-10-27, stage-4 audit; host paths only).** On the advisor's Mac (no `/local`): clone
> `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run59` (`W=~/Library/Caches/stage4`, `source $W/env.sh`), build
> `ant -Dlocal.repository=$W/m2 build-test` (this also builds `build/apache-cassandra-5.0.9-SNAPSHOT.jar`, so `ant jar` is not run
> separately). The test source is kept in `harness/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous/BloomFpChanceSizeTest.java`,
> copied into `$W/cassandra-run59/test/unit/org/apache/cassandra/utils/` for the run and removed afterwards (step 4).

**B2b. Knobs.** `maxFalsePosProbability` passed to `FilterFactory.getFilter(N, fp)`: 0.001, 0.01, 0.1, 0.39, 0.5, 0.9999, 1.0. 0.39 vs 0.5 straddles the trivial-branch threshold 0.393; 0.9999 vs 1.0 straddles the target check. Second axis (positive control): N = 1,000,000 and 2,000,000.

**B2c. Workload.** For each (N, fp): build the filter, add N distinct keys (`Util.dk(String.valueOf(i))` or `FilterTestHelper`-style keys via `BloomFilter.add(FilterKey)`), record sizes, close. Sizes need no "limit reached": the operand is computed at construction.

> **Amendment U2 (2026-10-27, stage-4 audit; exact workload and output).** Keys are `Util.dk(String.valueOf(i))`, i = 0..N-1
> (`test/unit/org/apache/cassandra/Util.java`, the configured partitioner after `DatabaseDescriptor.daemonInitialization()`). The grid
> is N in (1,000,000, 2,000,000) x fp in (0.001, 0.01, 0.1, 0.39, 0.5, 0.9999, 1.0), in that order, run twice (rep 1, rep 2; the
> determinism control of B2h): 28 cells. For each cell the test prints `BFMARK begin <cell>` before `getFilter`, `BFMARK end <cell>`
> after it, adds the N keys, then one line
> `BFP rep=<r> N=<n> fp=<fp> class=<simple class name> K=<hashCount or -> offheap=<offHeapSize()> serialized=<serializedSize(false)>`
> and closes the filter; at the end `END cells=28`. The test makes no assertions; `selfcheck.py` judges the lines.

**B2d. Observables and instruments.** `IFilter.offHeapSize()`, `IFilter.serializedSize(false)`, class of returned filter (`AlwaysPresentFilter` vs `BloomFilter`), and `BloomFilter.hashCount` (via `toString()` / reflection) for K. Optionally, for N = 100,000,000 at fp 0.01 (125 MB), run in a standalone `main` with `-XX:NativeMemoryTracking=summary` and read `jcmd <pid> VM.native_memory summary` category "Other" before/after allocation, to confirm native memory (not just the reported number) moves.

> **Amendment U3 (2026-10-27, stage-4 audit; the real-memory instrument).** The optional NMT step is not run: the bit set is allocated
> by `MemoryUtil.allocate`, which calls JNA `Native.malloc` (`utils/memory/MemoryUtil.java:81-84`), i.e. libc `malloc` outside the
> JVM's own allocator, which NMT does not track; NMT "Other" could not move whatever the filter size. It is replaced by observe-only
> Byteman rules (`harness/.../bf-unit.btm`) loaded into the forked test JVM with
> `-Dtest.jvm.args=-javaagent:build/lib/jars/byteman-4.0.20.jar=script:<bf-unit.btm>`: `BMBF A <size> <thread>` at the exit of every
> `MemoryUtil.allocate(long)` and `BMBF BA <bytes> <thread>` at the exit of every `OffHeapBitSet(long)` constructor. Real-memory
> reading of a cell: the sum of `BMBF A` sizes printed on the test's thread between that cell's `BFMARK begin` and `BFMARK end`
> lines (the malloc request the filter makes; whether the OS commits the pages is not observed, a gap named here).

**B2e. Procedure.**
1. Write a JUnit test (call `DatabaseDescriptor.daemonInitialization()` in `@BeforeClass`) looping over the knob grid, printing `N fp class K offHeapSize serializedSize`.
2. `ant testsome -Dtest.name=org.apache.cassandra.utils.BloomFpChanceSizeTest`.
3. Optional NMT step: `java -XX:NativeMemoryTracking=summary -cp build/classes/main:build/lib/jars/* <Main> 100000000 0.01`, pausing before and after allocation; `jcmd <pid> VM.native_memory summary` at each pause.
4. Remove the test file from the local clone afterwards.

**B2f. Predictions.** N = 1,000,000 (bytes = ceil((N*b+20)/64)*8):

| fp | b | K | offHeapSize |
|---|---|---|---|
| 0.001 | 15 | 7 | 1,875,008 |
| 0.01 | 10 | 6 | 1,250,008 |
| 0.1 | 5 | 3 | 625,008 |
| 0.39 | 3 | 1 | 375,008 |
| 0.5 | 1 | 2 | 125,008 |
| 0.9999 | 1 | 2 | 125,008 |
| 1.0 | — | AlwaysPresent | 0 |

N = 2,000,000 values are 2x (minus the 8-byte rounding term). `serializedSize` = offHeapSize + a small fixed header (<= 16 bytes). fp 0.39: below the 0.393 trivial threshold, smallest b with optimal probability <= 0.39 is b=3 (0.237 at K=2); K is then relaxed to K=1 (0.283 <= 0.39, `BloomCalculations.java:167-170`). NMT "Other" rises by ~125 MB for the 100M/0.01 case.

> **Amendment U4 (2026-10-27, stage-4 audit; a derivation error fixed before any reading, sizes unchanged).** The K column for
> fp 0.01 is **5**, not 6 as filed: after b = 10 is reached (`probs[10][7]` = 0.00819 <= 0.01, `BloomCalculations.java:54`), the
> relax loop (`:167-170`) lowers K while `probs[10][K-1]` <= 0.01: `probs[10][6]` = 0.00844 and `probs[10][5]` = 0.00943 pass,
> `probs[10][4]` = 0.0118 stops it, so K = 5. The other K values (7, 3, 1, 2, 2) re-derive as filed. K is informational: no B2g row
> uses it. Exact values for N = 2,000,000 (`OffHeapBitSet.java:41-46`, words = ceil(numBits/64)): b 15 -> 3,750,008; b 10 ->
> 2,500,008; b 5 -> 1,250,008; b 3 -> 750,008; b 1 -> 250,008; 1.0 -> 0. `serializedSize` = offHeapSize + 8 exactly (4-byte hash
> count, `BloomFilterSerializer.java:65-69`, plus 4-byte length, `OffHeapBitSet.java:139-142`), and 0 for `AlwaysPresent`. The
> NMT sentence above is withdrawn with U3; the U3 reading is predicted to equal `offheap` in every `BloomFilter` cell (one
> `MemoryUtil.allocate` of the bit set's bytes, `Memory.java:80-88`) and to show no allocation in the 1.0 cells.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| sizes match the table, 0 at 1.0 | claim confirmed at the mechanism level |
| sizes identical across fp at fixed N | claim refuted |
| 0.9999 gives non-zero, 1.0 gives 0 | target check `FilterFactory.java:63` is the switch |
| 0.01/0.1 ratio = 2.0, not ~3 | doc statement in A5 is inaccurate for this code |
| N=2M doubles size but fp changes nothing | instrument works, knob ineffective: refuted |
| NMT "Other" does not move although offHeapSize does | reported number not backed by native allocation; investigate |

> **Amendment U5 (2026-10-27, stage-4 audit; matching rules and verdict words).** "Match" means exact equality of `offheap`,
> `serialized` (= offheap + 8, or 0) and class with B2f/U4 in all 28 cells, and both reps equal. Verdicts:
> **Confirmed** (row 1; row 3 holds within it) — every cell matches and the U3 reading equals `offheap` in every `BloomFilter`
> cell, with no `MemoryUtil.allocate` on the test thread inside a 1.0 cell.
> **Refuted** (rows 2 and 5) — at fixed N, `offheap` is the same for every fp below 1.0.
> **Not confirmed** — sizes move with fp but some cell differs from B2f/U4 (the cells are listed), or the U3 reading differs from
> `offheap` (this replaces the NMT row: the reported number is not backed by the allocation).
> **Invalid** — the test does not print 28 `BFP` lines and `END cells=28`, the N axis does not scale `offheap` (B2h), or the U3
> rules print no `BMBF` line (instrument not live).
> Row 4 (ratio 0.01/0.1) is a note on the doc in A5, not a verdict row.

**B2h. Controls.** N axis (size must scale with N at fixed fp) shows the instrument is live; repeating a cell gives identical bytes (determinism); `AlwaysPresent` class check separates "small filter" from "no filter".

### B3. Cluster tier

**B3a. Environment and build.** One Linux node, JDK 11, built from `/local/c509` (`ant jar`). `conf/cassandra.yaml`: `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` all under `/local/c509-node/` on a local disk with >= 10 GB free. `conf/jvm-server.options` / env: `MAX_HEAP_SIZE=2G`, `HEAP_NEWSIZE=400M`, add `-XX:NativeMemoryTracking=summary`. Record `sstable: selected_format` from `cassandra.yaml` (big or bti) in the results.

> **Amendment C1 (2026-10-27, stage-4 audit; host paths and instruments).** Node built from `$W/cassandra-run59` (U1). Node
> directory `$W/node-bfgf` (internal SSD, APFS; data, commit log, hints, saved caches, cdc_raw and a generated `conf/` under it) in
> place of `/local/c509-node`; the conf is the clone's `conf/` with the tag's `cassandra.yaml` plus `cluster_name: bfgf`,
> listen/rpc `127.0.0.1` and those directories (`harness/.../make-node-conf.sh`); nothing else in the yaml changes (`sstable:` is
> commented out in the tag's yaml, so the format is the default `big`; recorded from the `nb-` prefix of `Data.db`). The node starts
> as a tracked background process (`bin/cassandra -f > node.out 2>&1 < /dev/null`; no tmux on this host) with `MAX_HEAP_SIZE=2G
> HEAP_NEWSIZE=400M` and `JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -javaagent:<byteman-4.0.20.jar>=script:<bf-node.btm>"`;
> the `STDOUT` appender is removed from the node's copy of `logback.xml` so `node.out` carries only Byteman lines. `bf-node.btm` is
> observe-only and prints: `BMBF GF <numElements> <fp> <result class>` at the exit of `FilterFactory.getFilter(long, double)`;
> `BMBF BA <bytes>` / `BMBF BC <bytes>` at the exit of `OffHeapBitSet(long)` and the entry of `OffHeapBitSet.close()`; `BMBF A
> <size> <addr>` / `BMBF F <addr>` at every `MemoryUtil.allocate` / `MemoryUtil.free`.

**B3b. Knobs.** `bloom_filter_fp_chance` on `keyspace1.standard1`: 0.01 (default for STCS, baseline), 0.001, 0.1, 0.5, 1.0, then back to 0.01. Set with `ALTER TABLE keyspace1.standard1 WITH bloom_filter_fp_chance = <x>;` followed by `nodetool upgradesstables -a keyspace1 standard1` to rewrite every SSTable with the new value.

**B3c. Workload.** `tools/bin/cassandra-stress write n=2000000 cl=ONE -rate threads=32 -node 127.0.0.1` (one row per partition, N = 2,000,000 keys; data ~0.5 GB). Then `nodetool flush keyspace1` and `nodetool compact keyspace1 standard1` so a single SSTable holds all keys (compaction keyCount is an estimate; see tolerance). Positive control: a second load `n=4000000` into a fresh keyspace (`-schema keyspace=ks_ctl`) at fp 0.01.

**B3d. Observables and instruments.** Per step: `nodetool tablestats keyspace1.standard1` lines "Bloom filter off heap memory used" and "Bloom filter space used" and "SSTable count"; `du -b /local/c509-node/data/keyspace1/standard1-*/*Filter.db` (sum); presence of `*Filter.db`; `jcmd <pid> VM.native_memory summary` category "Other" (coarse, also includes other Unsafe allocations). Cannot isolate Bloom native memory from other native users with NMT alone; the gauge is the primary reading.

> **Amendment C2 (2026-10-27, stage-4 audit; observables made exact).** `du -b` (GNU) is replaced by BSD `stat -f %z` per
> `*-Filter.db` file under `$W/node-bfgf/data/<ks>/standard1-*/`, summed. NMT is kept for information only: the bit set is JNA
> `Native.malloc` memory (U3), which NMT does not see. The real-memory reading is **live Bloom bit-set bytes** from `bf-node.btm`:
> at each sample, the byte offset of `node.out` is recorded and live = sum of `BA` minus sum of `BC` over lines before it, counting
> only bit sets of at least 65,536 bytes (system-keyspace tables also flush filters, all far smaller; the smallest keyspace1 filter
> predicted below is ~250,000 bytes). Direct evidence of the target branch: the `GF` lines of each rewrite (fp 1.0 returns
> `AlwaysPresentFilter` with no `BA` line in that window). Also recorded per sample: `sstablemetadata` of the `Data.db`
> (`totalRows`, `Bloom Filter FP chance`), tablestats "Number of partitions (estimate)", RSS.

**B3e. Procedure.**
1. Start node (`bin/cassandra -f` in a tmux pane), wait for `nodetool status` UN.
2. Run the stress write; `nodetool flush keyspace1`; `nodetool disableautocompaction keyspace1`; `nodetool compact keyspace1 standard1`.
3. Reading R0 (fp 0.01): tablestats, `du`, NMT.
4. For fp in 0.001, 0.1, 0.5, 1.0, 0.01: ALTER, `nodetool upgradesstables -a keyspace1 standard1`, wait for `nodetool compactionstats` empty, take readings.
5. Restart-only check: ALTER to 1.0 without rewrite, read tablestats (expect unchanged), restart node, read again (expect 0 off-heap; `Filter.db` files still on disk).
6. Positive control load into `ks_ctl` (N = 4M, fp 0.01), compact, read.
7. `nodetool drain`, stop the node, `pgrep -f CassandraDaemon` empty, `rm -rf /local/c509-node`.

> **Amendment C3 (2026-10-27, stage-4 audit; exact sequence and stop conditions).** Scripted in `harness/.../cluster-run.sh`:
> (1) start (C1); "up" = `nodetool status` shows `UN 127.0.0.1` and `nodetool statusbinary` prints `running`; abort if the process
> dies or is not up in 360 s. (2) `tools/bin/cassandra-stress write n=2000000 cl=ONE -rate threads=32 -node 127.0.0.1` exactly as
> B3c; `nodetool flush keyspace1`; `nodetool disableautocompaction keyspace1`; `nodetool compact keyspace1 standard1`. "Idle" (the
> wait used after every compaction, rewrite and load) = `nodetool compactionstats` shows `pending tasks 0` and the table's SSTable
> count is 1, then 5 s; abort after 1800 s. (3) sample `R0`. (4) for fp in 0.001, 0.1, 0.5, 1.0, 0.01: `ALTER TABLE ... WITH
> bloom_filter_fp_chance = <fp>` through `bin/cqlsh`, read back `system_schema.tables`, `nodetool upgradesstables -a keyspace1
> standard1`, idle, sample `F<fp>`. (5) ALTER to 1.0 (read back), sample `S5a`; drain, stop and start the node with the same conf
> (Byteman lines go to a second file `node2.out`), up, sample `S5b`; autocompaction is enabled again after the restart, which does
> not matter for a table with one SSTable. (6) `cassandra-stress write n=4000000 cl=ONE -rate threads=32 -node 127.0.0.1
> -schema keyspace=ks_ctl`; `nodetool flush ks_ctl`; `nodetool compact ks_ctl standard1`; idle on `ks_ctl.standard1`; sample `CTRL`
> (tablestats `ks_ctl.standard1`, read back its fp). (7) drain, stop, check no daemon / stress / cqlsh process is left, `rm -rf
> $W/node-bfgf`. A failed step aborts the run (logged), stops the node and cleans up.

> **Runbook-defect fix D1 (2026-10-27, stage 4 run 1, cluster tier; §B3f/B3g unchanged).** The C3 "idle" condition cannot be met
> after `nodetool disableautocompaction`: with compaction disabled, `CompactionStrategyManager.getNextBackgroundTask` returns at
> `CompactionStrategyManager.java:203` before STCS recomputes `estimatedRemainingTasks` (`SizeTieredCompactionStrategy.java:89`),
> so `pending tasks` stays at the value computed while the flushed SSTables existed (1 in the aborted attempt, with one SSTable
> left). "Idle" is redefined as: the table's SSTable count is 1 **and** `nodetool compactionstats` lists no active task (no
> `compaction type` header row), then 5 s; abort after 1800 s. The cluster tier restarts from its beginning.

**B3f. Predictions.** With N = 2,000,000 in one SSTable, allowing +-10% for the compaction key estimate: fp 0.01 -> ~2.5 MB off-heap; 0.001 -> ~3.75 MB; 0.1 -> ~1.25 MB; 0.5 -> ~0.25 MB; 1.0 -> 0 and no `Filter.db`; back to 0.01 -> ~2.5 MB. Ratios to the 0.01 reading: 1.5 / 0.5 / 0.1 / 0. "Bloom filter space used" ~= off-heap + header per SSTable. Step 5: unchanged before restart, 0 after. Control `ks_ctl`: ~5.0 MB (2x R0). NMT "Other" changes are within noise at these sizes (MBs); do not use it as the decision reading.

> **Amendment C4 (2026-10-27, stage-4 audit; bands stated, no predicted value changed).** "MB" above is 10^6 bytes (the values
> come from ceil((N*b+20)/64)*8 with N = 2,000,000: 2,500,008 / 3,750,008 / 1,250,008 / 250,008; control 5,000,008). Bands: each
> off-heap reading within +-10% of its value (the filed allowance); each ratio to `R0` within +-10% of 1.5 / 0.5 / 0.1; `F1.0`
> off-heap 0, "space used" 0 and no `Filter.db`; `F0.01` within +-10% of 2.5 MB; "space used" = off-heap + 8 per SSTable (exact,
> U4); step 5: `S5a` off-heap equal to `F0.01` and `S5b` 0 with the `Filter.db` file still present; `CTRL` within +-10% of 5.0 MB.
> Real memory (C2): live bit-set bytes equal the off-heap gauge at every sample. Why the ratios should be tight: every rewrite
> sizes its filter from `SSTableReader.getApproximateKeyCount` of the single input (`CompactionAwareWriter.java:84`,
> `DefaultCompactionWriter.java:62-65`), the same cardinality estimate of the same keys each time; the +-10% band stays the
> decision band.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| off-heap tracks the predicted ratios, 0 at 1.0 | claim confirmed: usage follows the knob |
| off-heap roughly constant across fp while `ks_ctl` doubles | claim refuted (knob ineffective, instrument live) |
| off-heap constant and `ks_ctl` also unchanged | not confirmed: instrument/workload problem |
| 0.5 reading equals 0.1 reading | trivial-branch analysis (1 bit/key) wrong |
| step 5 off-heap drops only after restart | confirms load-time `AlwaysPresent` path (`FilterComponent.java:105-111`) |
| 0.01/0.1 ratio ~3 | contradicts code trace (expects 2), recheck `BloomCalculations` |

> **Amendment C5 (2026-10-27, stage-4 audit; verdict words and missing rows).**
> **Invalid** — first, if any holds: `totalRows` of keyspace1 outside +-10% of 2,000,000 or of `ks_ctl` outside +-10% of 4,000,000
> (limit not reached); SSTable count not 1 at a sample; a read-back fp differs from the value set; a step aborts; the C2 rules print
> no `BMBF` line.
> **Confirmed** (row 1) — all C4 bands hold for `R0`, `F0.001`, `F0.1`, `F0.5`, `F1.0`, `F0.01` and `CTRL`, the live bit-set bytes
> equal the gauge, and the `GF` lines of the `F1.0` rewrite show `AlwaysPresentFilter`.
> **Refuted** (row 2, and row 4 for b(0.5)) — the non-1.0 readings all lie within +-10% of `R0` while `CTRL` is at least 1.8 x `R0`;
> or `F0.5` equals `F0.1` within +-10%; or `F1.0` is not 0.
> **Not confirmed** (row 3, row 6, and a new row) — `CTRL` below 1.8 x `R0` (instrument or workload problem); a 0.01/0.1 ratio of
> about 3; off-heap moves with fp but some reading is outside its band (listed); or the live bit-set bytes differ from the gauge by
> more than 1% (counter not backed by allocation).
> Step 5 (row 5) is reported separately and does not change the B1 verdict: `S5a` unchanged and `S5b` 0 confirms the load-time
> `AlwaysPresent` path; any other result is recorded as a finding against A3 step 5.

**B3h. Controls.** Same data set for every fp (rewrite, not reload); SSTable count recorded each step (sum over SSTables otherwise confounds); return to 0.01 shows reversibility; `ks_ctl` shows the gauge moves with N; autocompaction disabled so no background rewrites.

**B4. Risks and cleanup.** Unit: test file only in the local clone; delete it. Cluster: all node directories on local disk (<1 GB used), never on shared storage; stop the node with `nodetool drain` then kill, verify no `CassandraDaemon` or `cassandra-stress` Java process remains; remove `/local/c509-node`.

> **Amendment C6 (2026-10-27, stage-4 audit; host paths).** Cluster cleanup removes `$W/node-bfgf` (not `/local/c509-node`); the
> unit test file is removed from `$W/cassandra-run59` by `unit-run.sh`, and `git -C $W/cassandra-run59 status --porcelain` must be
> empty at the end. Full logs stay in `$W/logs/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous/`.

## C. Sources read

src/java/org/apache/cassandra/utils/FilterFactory.java
src/java/org/apache/cassandra/utils/BloomCalculations.java
src/java/org/apache/cassandra/utils/obs/OffHeapBitSet.java
src/java/org/apache/cassandra/utils/BloomFilter.java (grep)
src/java/org/apache/cassandra/io/sstable/format/FilterComponent.java
src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java
src/java/org/apache/cassandra/io/sstable/format/SSTableReaderWithFilter.java
src/java/org/apache/cassandra/io/sstable/format/big/BigSSTableReaderLoadingBuilder.java
src/java/org/apache/cassandra/io/sstable/format/bti/BtiTableReaderLoadingBuilder.java
src/java/org/apache/cassandra/io/sstable/filter/BloomFilterMetrics.java
src/java/org/apache/cassandra/schema/TableParams.java
src/java/org/apache/cassandra/schema/CompactionParams.java
src/java/org/apache/cassandra/db/memtable/Flushing.java (grep)
src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java (grep)
src/java/org/apache/cassandra/tools/nodetool/stats/TableStatsPrinter.java (grep)
test/unit/org/apache/cassandra/utils/BloomFilterTest.java (grep)
doc/modules/cassandra/pages/managing/operating/bloom_filters.adoc

## D. Stage-4 feedback

**2026-10-27, stage 4 run 1 (advisor's Mac, clone `cassandra-run59`)** — [results](../../stage4-runtime-verification/results/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous.md).
Audit: Ready after amendments U1–U5, C1–C6 (frozen `7a71bbb7…`); runbook defect D1 (stale `pending tasks` under
`disableautocompaction`) fixed in C3, cluster tier restarted (`d9feb24d…`). **Unit: Confirmed — caps** (B2g rows 1 and 3: 28/28 cells
exact, e.g. N = 1M → 1,875,008 / 1,250,008 / 625,008 / 375,008 / 125,008 / 125,008 / 0 bytes; the Byteman malloc equals `offHeapSize`;
`AlwaysPresentFilter` allocates nothing at 1.0). **Cluster: Confirmed — caps** (B3g row 1: 2,465,352 / 3,698,024 / 1,232,680 /
246,544 / 0 / 2,465,352 bytes for fp 0.01 / 0.001 / 0.1 / 0.5 / 1.0 / 0.01, ratios 1.5 / 0.5 / 0.1 exact; the filter is sized from the
HLL key estimate 1,972,278, hence 0.986 of the B3f values; live bit-set bytes equal the gauge; `getFilter(…, 1.0)` returned
`AlwaysPresentFilter`; `ks_ctl` 2.01×). Step 5 confirmed (unchanged before restart, 0 after, `Filter.db` still on disk). The filed K
for fp 0.01 was wrong (5, not 6; U4); the A5 doc claim "about three times" is 2.0× in this code.
