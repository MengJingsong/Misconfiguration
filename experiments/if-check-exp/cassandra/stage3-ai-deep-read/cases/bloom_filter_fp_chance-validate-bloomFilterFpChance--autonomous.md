# bloom_filter_fp_chance (table parameter) — verification solution  <!-- file: cases/bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`TableParams.java:161`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L161) (also covers `TableParams.java:161#2`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code at Meta (no version number printed), 2026-10-26 |
| Estimate | `positive`. The table's `bloom_filter_fp_chance` sets the bits per partition key of every bloom filter written for the table (2 to 20 bits, `BloomCalculations.java:140-172`), and each filter is one off-heap bitset of `keys × bitsPerKey + 20` bits (`FilterFactory.java:70-75`), plus a `Filter.db` file of the same size. The check at :161 bounds the setting to (6.71e-05, 1.0], so it caps bits per key at 20; at 1.0 no filter is built at all. Bloom filter off-heap bytes and `Filter.db` bytes therefore scale with the setting, per key. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `bloom_filter_fp_chance`, a per-table schema parameter (CQL `WITH bloom_filter_fp_chance = x`).
- Declared as `TableParams.Option.BLOOM_FILTER_FP_CHANCE` ([`TableParams.java:47`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L47)) and held in the field `bloomFilterFpChance` ([`TableParams.java:76`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L76)). The builder's sentinel is `-1` ([`TableParams.java:358`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L358)).
- Default when unset: `CompactionParams.defaultBloomFilterFbChance()` returns 0.1 for LCS and 0.01 otherwise ([`CompactionParams.java:261-264`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/CompactionParams.java#L261-L264), applied at [`TableParams.java:99-101`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L99-L101)).
- Unit: a probability (dimensionless).
- How to set it: `CREATE TABLE`/`ALTER TABLE ... WITH bloom_filter_fp_chance = x` ([`TableAttributes.java:109-110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/schema/TableAttributes.java#L109-L110)). It is stored in `system_schema.tables.bloom_filter_fp_chance` (`SchemaKeyspace.java:579,1065`). No restart is needed. However, existing sstables keep their old filter, because `rebuildFilterOnFPChanceChange = false` (`FilterComponent.java:43,119`). Only new sstables (flush, compaction, `nodetool upgradesstables -a`) get the new size. The one exception is a change to exactly 1.0: on the next load, `maybeLoadBloomFilter` returns `AlwaysPresent` ([`FilterComponent.java:105-111`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/FilterComponent.java#L105-L111)).
- The range check under test is `TableParams.validate()`, [`TableParams.java:160-167`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L160-L167). It rejects `fp <= BloomCalculations.minSupportedBloomFilterFpChance()` (that is `probs[20][14] = 6.71e-05`, `BloomCalculations.java:65,195-200`) as occurrence #1, and `fp > 1` as occurrence #2.


**Limit type (2026-10-29).** not-a-case: the entry-pointer `if` validates the option against a literal range, not usage against a capacity ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)). The verification solution and the stage-4 results are kept as filed.
**A2. What it caps.** Off-heap native memory and disk taken by sstable bloom filters.
- The governed quantity is bits per partition key. The check bounds the setting itself: it caps bits/key at 20 (the lower bound on fp) and rejects nonsense values above 1.
- Per sstable: `numBits = numElements × bucketsPerElement + 20` (`FilterFactory.java:72`), allocated as `Memory.allocate(ceil(numBits/64) × 8)` (`OffHeapBitSet.java:39-53`).

**A3. Mechanism.**
1. Schema change → `TableParams.validate()` at `:161`. An out-of-range value throws `ConfigurationException` through `fail(...)` and the DDL is refused, so the table can never carry fp ≤ 6.71e-05 or > 1.
2. Writer: `SortedTableWriter.AbstractIndexWriter` calls `FilterFactory.getFilter(b.getKeyCount(), params.bloomFilterFpChance)` ([`SortedTableWriter.java:445`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java#L445)). The `Filter.db` component is added only if `shouldUseBloomFilter(fp)`, i.e. fp ≠ 1.0 ([`SortedTableWriter.java:501-504`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java#L501-L504), [`FilterComponent.java:141-144`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/FilterComponent.java#L141-L144)).
3. `FilterFactory.getFilter(n, fp)` ([`FilterFactory.java:60-68`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/FilterFactory.java#L60-L68)):
   - fp == 1.0 → `AlwaysPresent`, 0 bytes;
   - otherwise `maxBucketsPerElement(n)` is 20 for any realistic n ([`BloomCalculations.java:180-189`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/BloomCalculations.java#L180-L189)), and `computeBloomSpec(20, fp)` picks the smallest bucket count whose best K reaches fp ([`BloomCalculations.java:140-172`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/BloomCalculations.java#L140-L172)).
   - Worked from the `probs` table: fp 0.1 → 5 bits/key, 0.01 → 10, 0.001 → 15, 0.0001 → 20, 0.00007 → 20.
   - `computeBloomSpec` throws if fp < `probs[20][14]` (`:151-155`). The validate check moves that failure to DDL time.
4. Reader load, BIG format ([`BigSSTableReaderLoadingBuilder.java:207`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigSSTableReaderLoadingBuilder.java#L207)) or BTI ([`BtiTableReaderLoadingBuilder.java:156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/bti/BtiTableReaderLoadingBuilder.java#L156)): the serialized filter is loaded or rebuilt with the same sizing.
5. Accounting: the `BloomFilterOffHeapMemoryUsed` and `BloomFilterDiskSpaceUsed` gauges ([`BloomFilterMetrics.java:60-72`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/filter/BloomFilterMetrics.java#L60-L72)) sum `getFilterOffHeapSize` and `getFilterSerializedSize` over live sstables. `nodetool tablestats` prints them ([`TableStatsPrinter.java:134`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/tools/nodetool/stats/TableStatsPrinter.java#L134)).
- Overshoots and bypasses:
  - The setting is per key, so total memory grows with partition count with no absolute ceiling. The only hard stop is the 16 GB per-filter wordCount guard ([`OffHeapBitSet.java:43-44`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/obs/OffHeapBitSet.java#L43-L44)).
  - The compaction writer's `getKeyCount()` is a cardinality estimate, so a filter can be sized for more keys than it holds.
  - Old sstables keep their old size after an `ALTER` (A1).

**A4. Other consumers.** These use the same off-heap and disk resources outside this setting:
- index summaries (BIG; `min_index_interval`, `index_summary_capacity`);
- compression metadata offsets;
- the chunk cache and key cache;
- memtables (`memtable_offheap_space`);
- data, index and other sstable components on disk.

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml` has no global key for this setting; it is per table.
- `test/unit/org/apache/cassandra/utils/BloomFilterTest.java` exists in the tree. It was not relied on for numbers.
- Cassandra docs, "Bloom Filters" (https://cassandra.apache.org/doc/5.0/cassandra/managing/operating/bloom_filters.html): lowering fp increases memory, 1.0 disables the filter, and an ALTER needs upgradesstables to take effect on existing files.

## B. Verification solution

**B1. Claim under test.** For a fixed set of N partition keys written to fresh sstables:
- bloom filter off-heap bytes equal `Σ_sstables ceil((keys_i × b(fp) + 20)/64) × 8`, with b(fp) ∈ {0, 5, 10, 15, 20} for fp ∈ {1.0, 0.1, 0.01, 0.001, 0.00007};
- `Filter.db` bytes track the same;
- any fp ≤ 6.71e-05 or > 1 is refused, so no table can exceed 20 bits per key.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11 and Ant on a Linux box. Clone the tag to local disk: `git clone --branch cassandra-5.0.9 --depth 1 <clone-url-or-path> /local/c509 && cd /local/c509 && ant build-test`.
- Test source: `/local/c509/test/unit/org/apache/cassandra/utils/BloomFpChanceCapTest.java` (new file in the local clone only).
- Run: `ant testsome -Dtest.name=org.apache.cassandra.utils.BloomFpChanceCapTest`.
- Default test JVM options from `build.xml`.

**Amendment 2026-10-26 (step-0 audit) — B2a, this host.** Run clone `$W/cassandra-run42` (`W=~/Library/Caches/stage4`; `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run42`, then `ant -Dlocal.repository=$W/m2 build-test`), macOS arm64, JDK 11.0.32.1, Ant 1.10.18; no `/local` paths. The test class is kept as `cassandra/stage4-runtime-verification/harness/<stem>/BloomFpChanceCapTest.java` and copied into the clone's `test/unit/org/apache/cassandra/utils/` by `harness/<stem>/unit-run.sh`, which runs `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.utils.BloomFpChanceCapTest` once per run label, copies the JUnit XML and the test log `build/test/logs/**/TEST-org.apache.cassandra.utils.BloomFpChanceCapTest.log` to `$W/logs/<stem>/unit-<label>/`, and removes the copied file. `@BeforeClass` calls `DatabaseDescriptor.daemonInitialization()` (unit test yaml). Test JVM heap 1024 MiB (`build.xml:1153`); the bitsets are native (`Memory.allocate`), at most 10,000,008 B each, one open at a time. Reason: B2a named `/local` and Linux paths.

**B2b. Knobs.** fp ∈ {1.0, 0.1, 0.01, 0.001, 0.0001, 0.00007} (accepted), plus boundary values {6.71e-05, 6.0e-05, 1.0000001, 0, -0.1} (should be rejected). The accepted values cover every bits-per-key step and the extreme just inside the bound. The rejected values sit exactly on and just past each bound. Each is set with `TableParams.builder().bloomFilterFpChance(fp).build()`.

**B2c. Workload.** N ∈ {1,000,000; 4,000,000} elements. For each accepted fp, call `FilterFactory.getFilter(N, fp)` and insert N keys (`Murmur3Partitioner.instance.decorateKey(ByteBufferUtil.bytes((long) i))` passed through `filter.add(...)`). Allocation happens in the constructor, so inserting only checks that the filter works. Arithmetic: at 20 bits/key and N = 4M, the bitset is 80,000,020 bits, ≈ 10.0 MB off-heap. That is well within a test JVM's native limits.

**Amendment 2026-10-26 (step-0 audit) — B2c/B2e, absent keys and order.** B2d says the FP rate is measured on 1M absent keys and B2e step 2 says keys N..2N-1; the B2d figure is kept: the absent keys are `i = N .. N + 999,999` for both N. Order: N = 1,000,000 then 4,000,000; within each N the accepted fp in the B2b order (1.0, 0.1, 0.01, 0.001, 0.0001, 0.00007); then the boundary values; then step 4 for N = 1,000,000 and 4,000,000. Reason: internal inconsistency; the order makes the output deterministic.

**B2d. Observables and instruments.**
- `((BloomFilter) filter).offHeapSize()` (`BloomFilter.java:151-154`), and `serializedSize(false)` (`:59-62`).
- For the rejection rows: whether `TableParams.validate()` throws `ConfigurationException`.
- The FP rate is measured on 1M absent keys as a sanity check of the spec, not of memory.
- Not observable here: per-sstable key-count estimation and process RSS.

**Amendment 2026-10-26 (step-0 audit) — B2d, output lines.** Every reading is one `System.out.println` with prefix `BFP `, read from the test log (B2a amendment): `BFP filter N=<N> fp=<fp> class=<simple class name> hashCount=<K or -> offHeap=<bytes> serialized=<bytes> fpCount=<false positives of 1,000,000> validate=<ok|threw>`; `BFP reject fp=<value> threw=<exception class or none> msg=<message>`; `BFP direct N=<N> fp=6.0E-5 threw=<exception class or none> msg=<message>`; `BFP done`. `validate` is `TableParams.builder().bloomFilterFpChance(fp).build().validate()` for the accepted value (B1 says these are accepted). Reason: the readings' format and location were open.

**B2e. Procedure.**
1. Write the test with one `@Test` per table below.
2. For each accepted fp and each N: build the filter, record `offHeapSize()` and `serializedSize(false)`, add N keys, measure the FP rate on keys N..2N-1, then `filter.close()`.
3. For each boundary value: assert that `build().validate()` throws, and record the message.
4. As a direct contrast, call `FilterFactory.getFilter(N, 6.0e-05)` without validation and record the `UnsupportedOperationException` (`BloomCalculations.java:151-155`).
5. Run with `ant testsome ...`. The readings are printed via `System.out`, collected from `build/test/output/TEST-*.xml`.

**Amendment 2026-10-26 (step-0 audit) — B2e, stop condition.** Each measurement is caught and printed, so the test runs to `BFP done`; the JUnit result is pass unless the test cannot run. A missing `BFP done` line is an invalid run. Reason: the stop condition was open.

**B2f. Predictions.** `offHeapSize = ceil((N·b + 20)/64)·8` bytes.

| fp | b | N = 1M | N = 4M |
|---|---|---|---|
| 1.0 | 0 | 0 (AlwaysPresent) | 0 |
| 0.1 | 5 | 625,008 | 2,500,008 |
| 0.01 | 10 | 1,250,008 | 5,000,008 |
| 0.001 | 15 | 1,875,008 | 7,500,008 |
| 0.0001 | 20 | 2,500,008 | 10,000,008 |
| 0.00007 | 20 | 2,500,008 | 10,000,008 |

- `serializedSize` = offHeapSize + a small fixed header.
- Every boundary value throws at validate.
- The measured FP rate is ≤ the fp asked for, within sampling error.

**Amendment 2026-10-26 (step-0 audit) — B2f, exact values from the source.** (i) `serializedSize(false)` = offHeapSize + 8 exactly: 4 B hash count plus a 4 B word count before the words (`BloomFilterSerializer.java:65-70`, `OffHeapBitSet.java:139-142`); for `AlwaysPresent` both are 0 (`FilterFactory.java:108`, `:117-120`) and the class is `AlwaysPresentFilter`. (ii) Hash counts from `computeBloomSpec(20, fp)` over the `probs` table (`BloomCalculations.java:140-172`): fp 0.1 → b 5, K 3; 0.01 → 10, 5; 0.001 → 15, 7; 0.0001 → 20, 10; 0.00007 → 20, 13 (recorded; not a row condition). (iii) "within sampling error" = fpCount ≤ 10^6·fp + 3·sqrt(10^6·fp) (Poisson, three standard deviations): 0.1 → 100,949; 0.01 → 10,300; 0.001 → 1,094; 0.0001 → 130; 0.00007 → 95 (for fp = 1.0, fpCount = 1,000,000). (iv) Every accepted fp prints `validate=ok`. (v) Rejections throw `ConfigurationException` with the message `bloom_filter_fp_chance must be larger than 6.71E-5 and less than or equal to 1.0 (got <value>)` (`TableParams.java:161-167`, `:206-209`), the value printed by `Double.toString`: 6.71E-5, 6.0E-5, 1.0000001, 0.0, -0.1. (vi) Step 4 throws `UnsupportedOperationException` with `Unable to satisfy 6.0E-5 with 20 buckets per element` (`BloomCalculations.java:151-155`) for both N. Reason: "a small fixed header", "within sampling error" and the rejection evidence were open; derived before any reading.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Sizes match the table exactly and grow 4× with N | Mechanism as traced; claim holds at the unit level |
| Sizes differ from the table but are still monotone in fp | Bits-per-key mapping is mis-traced; the claim is still positive in direction, so re-derive b(fp) |
| offHeapSize is the same for all fp ≠ 1.0 | Claim wrong: fp does not set the size |
| A value ≤ 6.71e-05 or > 1 passes validate | The cap at :161 does not hold; claim wrong for that bound |
| fp = 1.0 gives a non-zero filter | Claim wrong for the disable path |

**Amendment 2026-10-26 (step-0 audit) — B2g, verdict words and added rows.** Row 1 (all twelve sizes exactly as the B2f table, serialized = offHeap + 8, `validate=ok` for the six accepted values, all five boundary values rejected with the (v) message, step 4 throws as in (vi), fp = 1.0 gives `AlwaysPresentFilter` with 0 B) → **Confirmed — caps**. Row 2 (monotone, not exact) → **Not confirmed** — Effect caps (direction), b(fp) mis-traced. Row 3 (equal for all fp ≠ 1.0) → **Refuted — does not cap**. Row 4 (a boundary value passes validate) → **Refuted** for that bound — does not cap (no table-level bound). Row 5 (fp = 1.0 non-zero) → **Refuted** for the disable path — Effect from rows 1-3 otherwise. Added: (a) an accepted value fails validate → **Refuted** for B1's accepted range. (b) serialized ≠ offHeap + 8 → **Not confirmed** (the disk form does not track the memory form as traced). (c) Step 4 does not throw → **Not confirmed** (the control that shows validate is what keeps fp in range did not work). (d) An fpCount above its (iii) bound → recorded and fed back to stage 3 as a spec note; it does not change the memory verdict (FP rate is a sanity check, B2d). (e) No `BFP done`, a compile or test failure → **Invalid run**. Reason: B2g gave meanings without verdicts and left these outcomes open.

**B2h. Controls.**
- The N=1M and N=4M rows separate the per-key effect from fixed overhead.
- The 0.0001 and 0.00007 rows (same b) show the 20-bit ceiling.
- The direct-call row in step 4 shows that the validate check, not luck, keeps fp in range.

**Amendment 2026-10-26 (step-0 audit) — B2h, control evidence.** The 0.0001 / 0.00007 equality (both b = 20) is read from the two N rows; the step-4 control is the (vi) line of the B2f amendment. Reason: names which line evidences each control.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node, JDK 11, built from the local clone (`ant jar`). Run with `bin/cassandra -f -R` from `/local/c509`.
- `conf/cassandra.yaml` changes: `data_file_directories: [/local/cass/data]`, `commitlog_directory: /local/cass/commitlog`, `hints_directory: /local/cass/hints`, `saved_caches_directory: /local/cass/caches`. Leave `sstable.selected_format` at its default (big). Set `concurrent_compactors: 1`.
- `conf/jvm-server.options` / env: `MAX_HEAP_SIZE=4G`, `HEAP_NEWSIZE=800M`.
- Needs ≥ 20 GB free local disk.

**Amendment 2026-10-26 (step-0 audit) — B3a, this host.** Clone `$W/cassandra-run42` (built by `ant -Dlocal.repository=$W/m2 build-test`, which builds the jar and `tools/bin/cassandra-stress`; no separate `ant jar`). Node directory `$W/node-bf42` (data, commitlog, hints, saved_caches, cdc_raw), conf `$W/node-bf42/conf` built by `harness/<stem>/make-node-conf.sh` from the tag's `conf/` with the node lines (cluster `bf42`, `127.0.0.1`, the directories) and `concurrent_compactors: 1`. Started as a tracked background process `CASSANDRA_CONF=$W/node-bf42/conf MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M nohup bin/cassandra -f &` (no `-R`: not root; no `setsid` on this host). The sstable format is the default `big` (the yaml's `sstable:` block is commented out at the tag, `conf/cassandra.yaml:1172`); read back from the `-big-` in the Data.db file names. Free disk on this host 129 GiB. Reason: `/local` paths; this host's start method.

**B3b. Knobs.** Five keyspaces `bf_1`, `bf_01`, `bf_001`, `bf_0001`, `bf_00007` (RF 1, SimpleStrategy), each holding a table `standard1` created with fp = 1.0, 0.1, 0.01, 0.001 and 0.00007 respectively. Boundary DDL: `ALTER TABLE bf_01.standard1 WITH bloom_filter_fp_chance = 0.0000671` and `= 1.01` (both expected to be refused).

**Amendment 2026-10-26 (step-0 audit) — B3b, a sixth keyspace `bf_00001`.** A keyspace `bf_00001` with fp = 0.0001 (b = 20, as `bf_00007`) is added, written between `bf_0001` and `bf_00007`, so the cluster tier shows the 20-bit ceiling the same way B2h does (two accepted values with b = 20 give the same bytes) and drives the setting past the point where bits per key stop growing (README group A). The boundary ALTERs are unchanged. Reason: the filed cluster values had a single b = 20 value, so "flat at the ceiling" was not observable on the node; chosen before any reading.

**B3c. Workload.**
- Pre-create each table with cqlsh: `CREATE TABLE bf_X.standard1 (key blob PRIMARY KEY, "C0" blob, "C1" blob, "C2" blob, "C3" blob, "C4" blob) WITH bloom_filter_fp_chance = <fp> AND compression = {}`.
- Disable compaction: `nodetool disableautocompaction bf_X`.
- Write N = 4,000,000 partitions to each keyspace with `tools/bin/cassandra-stress write n=4000000 cl=ONE -pop seq=1..4000000 -schema keyspace=bf_X -rate threads=64 -node 127.0.0.1`. Stress uses `CREATE TABLE IF NOT EXISTS` (`SettingsSchema.java:127`), so the pre-created table is kept.
- Then `nodetool flush bf_X`.
- Data volume: about 4M × (5 × 34 B + overhead), ≈ 1 GB per keyspace, ≈ 5 GB total.
- Arithmetic: at 20 bits/key the expected total filter size is 10 MB per keyspace. That is easily measured against a gauge resolution of bytes.
- Duration: about 5-10 minutes per keyspace.
- Phase 2, key-count control: write a further `-pop seq=4000001..8000000` to `bf_001` and flush. The prediction doubles.

**Amendment 2026-10-26 (step-0 audit) — B3c, exact commands and the limit-reached check.** cqlsh runs as `HOME=$W/home bin/cqlsh 127.0.0.1`. `CREATE KEYSPACE bf_X WITH replication = {'class':'SimpleStrategy','replication_factor':1}`, the table as filed, then `nodetool disableautocompaction bf_X standard1` (the node is not restarted in this tier, so the nodetool switch holds). Stress: `tools/bin/cassandra-stress write n=4000000 cl=ONE -pop seq=1..4000000 -schema keyspace=bf_X -rate threads=64 -node 127.0.0.1`, its output kept whole in the log directory; then `nodetool flush bf_X standard1`. **Limit-reached check:** the sum of `totalRows` over the keyspace's sstables (`tools/bin/sstablemetadata`; one row per partition in this schema, so it counts partitions exactly) must be 4,000,000 (8,000,000 for `bf_001` after phase 2); stress's `Total errors` is recorded. Reason: commands and the check that the workload reached N were open.

**B3d. Observables and instruments.**
- `nodetool tablestats bf_X.standard1`, fields "Bloom filter off heap memory used" and "Bloom filter space used".
- JMX `org.apache.cassandra.metrics:type=Table,keyspace=bf_X,scope=standard1,name=BloomFilterOffHeapMemoryUsed`.
- Independent disk check: `du -cb /local/cass/data/bf_X/standard1-*/*-Filter.db | tail -1`.
- Partition count from `nodetool tablestats` "Number of partitions (estimate)" and `sstablemetadata` key counts.
- Sampling: once, after flush with compaction disabled.
- Not observable directly: the share of process RSS due to filters. A whole-process `pmap`/NMT delta is noisy, so it is recorded as context only.

**Amendment 2026-10-26 (step-0 audit) — B3d, this host's instruments.** (i) Filter.db bytes: the sum of `stat -f %z` over `$W/node-bf42/data/bf_X/standard1-*/*-Filter.db` (BSD: no `du -cb`), with the file count. (ii) Per sstable from `tools/bin/sstablemetadata`: `totalRows`, `Bloom Filter FP chance`, `Estimated cardinality`. (iii) `nodetool tablestats bf_X.standard1`: `SSTable count`, `Bloom filter space used`, `Bloom filter off heap memory used`, `Number of partitions (estimate)`; the off-heap line is the `BloomFilterOffHeapMemoryUsed` gauge, which sums `bitset.offHeapSize()` = the byte count passed to `Memory.allocate` for each live filter (`BloomFilterMetrics.java:68-72`, `SSTableReaderWithFilter.java:116-124`, `OffHeapBitSet.java:39-53`) — the native allocation itself, not a separate counter; the disk sum (i) is the independent real-resource reading. (iv) `nodetool compactionhistory` lines for `bf_` keyspaces (none expected before step 6). (v) Process RSS (`ps -o rss= -p <pid>`) at each record point, context only (B3d's last bullet). (vi) Exact recorded checks (not row conditions): gauge = Σ_i ceil((totalRows_i·b + 20)/64)·8 for flush sstables (`Flushing.java:117` sizes each flush filter with the exact partition count); Filter.db = gauge + 8 × sstables (B2f amendment (i)). Sampling: after each keyspace's flush, and once more for all keyspaces before step 4 (stability). Reason: `du -cb` does not exist on macOS; the instrument's relation to the real resource was not named.

**B3e. Procedure.**
1. Start the node and wait until `nodetool status` shows UN.
2. Create the five keyspaces and tables, then disable autocompaction for each.
3. For each keyspace: run stress, flush, and record the gauges and `du` of Filter.db.
4. Run the boundary ALTERs in cqlsh and record the errors.
5. Phase 2 on `bf_001`: write, flush, record.
6. Positive-control step: `ALTER TABLE bf_001.standard1 WITH bloom_filter_fp_chance = 0.1`, record (expect no change), then `nodetool upgradesstables -a bf_001 standard1`, record (expect the 0.1 prediction).
7. `nodetool drain`, stop the node, check `pgrep -f CassandraDaemon` is empty.

**Amendment 2026-10-26 (step-0 audit) — B3e, order.** One script, `harness/<stem>/cluster-run.sh`: wipe `$W/node-bf42`, conf, start, wait for `UN` and `statusbinary running`; create the six keyspaces; for `bf_1`, `bf_01`, `bf_001`, `bf_0001`, `bf_00001`, `bf_00007` in this order: stress, flush, record (B3d amendment); record all six again; step 4 (two ALTERs, then `SELECT bloom_filter_fp_chance FROM system_schema.tables WHERE keyspace_name='bf_01'`, expected 0.1); step 5 (phase 2 on `bf_001`, flush, record); step 6 (ALTER `bf_001` to 0.1, record; `nodetool upgradesstables -a bf_001 standard1`, record); drain, stop, check no daemon is left, wipe. A cluster shakedown with n = 100,000 per keyspace runs first and is not judged. Reason: places the added keyspace and the readbacks; one scripted path.

**B3f. Predictions.** Total off-heap per keyspace ≈ `4,000,000 × b / 8` bytes plus ≤ 8 bytes per sstable:

| keyspace | fp | prediction |
|---|---|---|
| bf_1 | 1.0 | 0, and no Filter.db files |
| bf_01 | 0.1 | ≈ 2.50 MB |
| bf_001 | 0.01 | ≈ 5.00 MB |
| bf_0001 | 0.001 | ≈ 7.50 MB |
| bf_00007 | 0.00007 | ≈ 10.0 MB |

- Flush key counts are exact per sstable, so the expected match is within 1%.
- Filter.db bytes are within a few hundred bytes per sstable of the off-heap number.
- Phase 2: `bf_001` goes to ≈ 10.0 MB.
- Step 6: the size is unchanged after the ALTER, and ≈ 5.0 MB (the 0.1 value for 8M keys) after upgradesstables.
- Both boundary ALTERs are refused with the `must be larger than 6.71E-5 ...` message.

**Amendment 2026-10-26 (step-0 audit) — B3f, exact bounds.** (i) Per keyspace, "within 1%" of 4,000,000·b/8: `bf_01` 2,500,000 B, `bf_001` 5,000,000, `bf_0001` 7,500,000, `bf_00001` 10,000,000, `bf_00007` 10,000,000 (each ±1%); `bf_1` 0 B with no Filter.db file. (ii) "Filter.db within a few hundred bytes per sstable": |Filter.db − gauge| ≤ 300 B × sstable count (derived exact value: + 8 B per sstable). (iii) Phase 2: `bf_001` 10,000,000 B ± 1%. (iv) Step 6: right after the ALTER the gauge equals the pre-ALTER reading exactly (filters are not rebuilt, `FilterComponent.java:43,119`; nothing reloads them); after `upgradesstables -a`, every sstable reports `Bloom Filter FP chance` 0.1 and the gauge is 5,000,000 B ± 4%: the rewrite sizes each filter with the source sstable's HyperLogLog++ estimate (`CompactionAwareWriter.java:84,235`, `DefaultCompactionWriter.java:62-64`, `SSTableReader.java:302-342`) with p = 13 (`MetadataCollector.java:147`), standard error 1.04/sqrt(8192) = 1.15%, so 3σ ≈ 3.5% (recorded exact check: Σ ceil((card_i·5 + 20)/64)·8 over the pre-upgrade `Estimated cardinality` values). (v) The ALTER message contains `bloom_filter_fp_chance must be larger than 6.71E-5 and less than or equal to 1.0` (`TableParams.java:163-166`), with `(got 6.71E-5)` and `(got 1.01)`. Reason: "≈" and "a few hundred bytes" needed numbers; the step-6 tolerance was missing; derived before any reading.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Per-keyspace bytes follow b(fp) × N/8 within 1-2% | Claim confirmed: the setting governs filter memory and disk |
| Bytes monotone in fp but off by a constant factor | Key-count estimation differs from the trace; still positive, so investigate `getKeyCount()` |
| Bytes equal across fp ≠ 1.0 | Claim refuted |
| bf_1 has filters or non-zero bytes | Disable path refuted |
| A boundary ALTER succeeds | The :161 cap is refuted |
| Phase 2 does not double | Per-key scaling refuted |

**Amendment 2026-10-26 (step-0 audit) — B3g, verdict words and added rows.** Row 1 (every (i) band, (ii), `bf_00001` and `bf_00007` within 1% of each other, both ALTERs refused with the (v) message and the read-back 0.1, phase 2 within (iii)) → **Confirmed — caps**. Row 2 (monotone but off by a constant factor) → **Not confirmed** — Effect caps (direction), key-count estimate differs. Row 3 (equal across fp ≠ 1.0) → **Refuted — does not cap**. Row 4 (`bf_1` has filters or bytes) → **Refuted** for the disable path. Row 5 (a boundary ALTER succeeds) → **Refuted — does not cap** (the :161 bound). Row 6 (phase 2 does not double) → **Refuted** for per-key scaling. Added: (a) Filter.db and the gauge disagree beyond (ii) → **Not confirmed** (counter and real resource differ). (b) A keyspace's `totalRows` sum ≠ 4,000,000 (8,000,000 after phase 2), a `bf_` compaction before step 6, a node failure or a missing reading → **Invalid run** for that tier. (c) Step 6 off its (iv) prediction (changed by the ALTER alone, or not within ±4% after the rewrite) → recorded and fed back; the B1 verdict is unchanged (step 6 is a control on the ALTER path, not part of B1). Reason: B3g gave meanings without verdicts and left these outcomes open.

**B3h. Controls.**
- Compaction is disabled, so the sstable set is only the flush output.
- Five tables with identical data isolate fp as the only variable.
- `du` on Filter.db cross-checks the gauge.
- Phase 2 shows the workload moves usage where the cap binds per key.
- Step 6 shows the setting acts at sstable creation time.

**Amendment 2026-10-26 (step-0 audit) — B3h, control evidence.** "Compaction is disabled": `compactionhistory` has no `bf_` line before step 6 and the sstable count does not fall; "`du` cross-checks the gauge": the `stat` sum of the B3d amendment; "six tables" with the added `bf_00001`. Reason: names the evidence of each control.

**B4. Risks and cleanup.**
- Unit tier: native memory ≤ 10 MB per filter, closed after each case.
- Cluster tier: ≈ 6 GB on `/local/cass` only, never on shared storage.
- After the run: `rm -rf /local/cass`, check that no `CassandraDaemon` or stress JVM is left (`pgrep -f cassandra`), and delete `/local/c509` when done.

**Amendment 2026-10-26 (step-0 audit) — B4, this host.** Paths are `$W/node-bf42` and `$W/cassandra-run42`; after the run `$W/node-bf42` is wiped, `ps -eo command | grep '[C]assandraDaemon'` and the stress JVM are checked empty, and the clone's `git status` is clean. The clone is kept (the workspace keeps earlier run clones). Reason: `/local` paths.

## C. Sources read

- src/java/org/apache/cassandra/schema/TableParams.java
- src/java/org/apache/cassandra/schema/CompactionParams.java
- src/java/org/apache/cassandra/utils/BloomCalculations.java
- src/java/org/apache/cassandra/utils/FilterFactory.java
- src/java/org/apache/cassandra/utils/obs/OffHeapBitSet.java
- src/java/org/apache/cassandra/utils/BloomFilter.java
- src/java/org/apache/cassandra/io/sstable/format/FilterComponent.java
- src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java
- src/java/org/apache/cassandra/io/sstable/filter/BloomFilterMetrics.java
- src/java/org/apache/cassandra/cql3/statements/schema/TableAttributes.java
- src/java/org/apache/cassandra/tools/nodetool/stats/TableStatsPrinter.java
- tools/stress/src/org/apache/cassandra/stress/settings/SettingsSchema.java
- https://cassandra.apache.org/doc/5.0/cassandra/managing/operating/bloom_filters.html

## D. Stage-4 feedback

**2026-10-26, stage 4 run 1 on the advisor's machine** (results: [`../../stage4-runtime-verification/results/bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous.md`](../../stage4-runtime-verification/results/bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous.md); frozen at sha256 `56ee6b8e…6688` after sixteen dated step-0 amendments; uncommitted).
- **Unit: Confirmed — caps** (B2g row 1). offHeap exactly `ceil((N·b + 20)/64)·8` at all twelve points (b = 0/5/10/15/20/20; 2,500,008 B and 10,000,008 B at 20 bits for 1M and 4M keys), serialized = offHeap + 8, the five boundary values refused with the exact message, and the direct `getFilter(N, 6.0E-5)` throws.
- **Cluster: Confirmed — caps** (B3g row 1). 4M keys gave 0 / 2,500,072 / 5,000,072 / 7,500,072 / 10,000,080 / 10,000,072 B off heap for fp 1.0 / 0.1 / 0.01 / 0.001 / 0.0001 / 0.00007 (each equal to the per-sstable formula), with Filter.db + 8 B per sstable. Both boundary ALTERs were refused, and phase 2 doubled `bf_001` to 10,000,144 B. Step 6 went as predicted: the ALTER alone changed nothing, and `upgradesstables -a` gave 4,993,696 B.
- **Note for stage 3 (not applied):** the rewrite path sizes each filter from the source sstable's HyperLogLog++ estimate (`CompactionAwareWriter.java:84,235`). Step 6's bytes equal the formula over those estimates exactly (−0.13% from `keys × 5/8`), which is consistent with A3's overshoot note. An ALTER to exactly 1.0 on a loaded table (A1) was not tested.
