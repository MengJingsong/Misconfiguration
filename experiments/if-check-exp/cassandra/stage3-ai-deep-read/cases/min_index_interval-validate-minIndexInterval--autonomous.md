# min_index_interval / max_index_interval (table parameters) — verification solution  <!-- file: cases/min_index_interval-validate-minIndexInterval--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`TableParams.java:185`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L185) (also covers `TableParams.java:188#1`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code at Meta (no version number printed), 2026-10-26 |
| Estimate | **185#1 `positive`.** `min_index_interval` m is the densest sampling the BIG index summary ever uses. A summary holds at most `ceil(keys/m)` entries of `4 + keyLen + 8` off-heap bytes (`IndexSummaryBuilder.java:100-127,273`; `IndexSummary.java:259-262`), so the summary's off-heap bytes per key are capped by 1/m. The check at :185 keeps m ≥ 1. **188#1 `undetermined`.** `max_index_interval` M is the sparsest sampling that `index_summary_capacity` redistribution may reach (`IndexSummaryBuilder.java:299-311`). It puts a floor of about `keys/M` entries under summary memory, which can sit above the capacity. Whether that counts as a cap, or as a floor that defeats one, is what the B3 phase 2 readings decide. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- `min_index_interval` (m) and `max_index_interval` (M) are per-table schema parameters. Declared as `TableParams.Option.MIN_INDEX_INTERVAL` / `MAX_INDEX_INTERVAL`, fields at [`TableParams.java:107-108`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L107-L108). Builder defaults are m = 128 and M = 2048 ([`TableParams.java:364-365`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L364-L365)).
- Unit: partitions per summary entry.
- Set with `CREATE/ALTER TABLE ... WITH min_index_interval = m AND max_index_interval = M` (`TableAttributes.java:137,143`). No restart is needed.
- A changed m or M is applied to existing sstables at the next index-summary redistribution, as a forced resample or upsample ([`IndexSummaryRedistribution.java:192-231`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryRedistribution.java#L192-L231)), or when a summary is loaded or rebuilt ([`IndexSummary.java:423-441`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummary.java#L423-L441), [`BigTableReader.java:591-609`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java#L591-L609)).
- Checks under test (`TableParams.validate()`):
  - `:185` `minIndexInterval < 1` → fail;
  - `:188` `maxIndexInterval < minIndexInterval` → fail.
- Related global settings (`conf/cassandra.yaml:939-947`): `index_summary_capacity` defaults to 5% of heap ([`DatabaseDescriptor.java:867-872`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L867-L872)), and `index_summary_resize_interval` defaults to 60m.
- This only applies to the BIG format, which is the 5.0.9 default ([`Config.java:373`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L373)). BTI has no summary.


**Limit type (2026-10-29).** not-a-case: the entry-pointer `if` validates the option against a literal lower bound (`< 1`), not usage against a capacity ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)). The verification solution and the stage-4 results are kept as filed.
**A2. What it caps.** Off-heap memory of BIG index summaries (`IndexSummaryOffHeapMemoryUsed`, `IndexSummaryMetrics.java:40`). The compared quantity is the sampling interval: m sets the full-sampling entry count `ceil(keys/m)`, and M sets the lowest sampling level `ceil(128·m/M)` out of 128.

**A3. Mechanism.**
1. DDL → `validate()`: m < 1 or M < m is refused with `ConfigurationException`.
2. Write, BIG: [`BigTableWriter.java:255`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java#L255) creates `new IndexSummaryBuilder(keyCount, m, BASE_SAMPLING_LEVEL=128)`.
   - The builder pre-sizes off-heap writers for `keys/m` entries (`IndexSummaryBuilder.java:106,125-127`) and samples every m-th key (`:235`).
   - `sizeAtFullSampling = ceil(keysWritten/m)` (`:273`).
   - Overshoot guard: if `keys/m × entrySize > Integer.MAX_VALUE`, m is raised automatically and a warning is logged (`:108-117`), so a single summary stays ≤ 2 GiB whatever m is.
3. Off-heap bytes = `offsetCount × 4 + entriesLength` ([`IndexSummary.java:259-262`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummary.java#L259-L262)). Entry = key bytes + 8 ([`IndexSummaryBuilder.java:146-149`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L146-L149)).
4. Redistribution (every `index_summary_resize_interval`, [`IndexSummaryManager.java:103-109`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryManager.java#L103-L109)): `adjustSamplingLevels` ([`IndexSummaryRedistribution.java:159-260`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryRedistribution.java#L159-L260)) hands out `index_summary_capacity` in proportion to 15-minute read rates. Each sstable gets `newSamplingLevel = clamp(target, ceil(128·m/M), 128)` ([`IndexSummaryBuilder.java:299-311`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L299-L311)).
   - The upper clamp (128, i.e. interval m) means summary memory never exceeds full sampling at m.
   - The lower clamp means it never drops below `ceil(128·m/M)/128` of full sampling, even when capacity is exceeded. The yaml comment says capacity is "best-effort" (`cassandra.yaml:931-936`).
   - With zero reads, `idealSpace = round(remaining × 0/0) = 0`, so `targetNumEntries = 1` and every cold sstable is downsampled to the M floor ([`IndexSummaryRedistribution.java:181-186`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryRedistribution.java#L181-L186)).
- Bypasses:
  - BTI tables.
  - The automatic interval raise at step 2.
  - Sstables under compaction are not redistributed (`nonRedistributingOffHeapSize`, `IndexSummaryRedistribution.java:111-113,138`).

**A4. Other consumers.** Off-heap bloom filters (`bloom_filter_fp_chance`), compression metadata, memtables, chunk cache, and the key cache (heap/off-heap). For disk, `Summary.db` is written with the same content.

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:931-947`, the comments on `index_summary_capacity` and the resize interval.
- CASSANDRA-5519 introduced min/max index interval and summary downsampling (https://issues.apache.org/jira/browse/CASSANDRA-5519).
- Existing tests `test/unit/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryTest.java` and `IndexSummaryManagerTest.java` were noted, not relied on for numbers.

## B. Verification solution

**B1. Claim under test.**
- (a) For fixed N keys, BIG index summary off-heap bytes at full sampling equal `Σ ceil(keys_i/m) × (keyLen + 12)`. They fall as m rises, and m < 1 is refused.
- (b) Under redistribution with no reads, summary bytes settle at `≈ (ceil(128·m/M)/128) × full`. They follow M, not `index_summary_capacity`, and M < m is refused.

### B2. Unit tier

**B2a. Environment and build.**
- Local clone: `git clone --branch cassandra-5.0.9 --depth 1 <clone> /local/c509 && cd /local/c509 && ant build-test`.
- New test `test/unit/org/apache/cassandra/io/sstable/indexsummary/IndexIntervalCapTest.java` (local clone only), run with `ant testsome -Dtest.name=org.apache.cassandra.io.sstable.indexsummary.IndexIntervalCapTest`.
- In `@BeforeClass`, call `DatabaseDescriptor.daemonInitialization()` and use `Murmur3Partitioner.instance`.

**Amendment 2026-10-26 (step-0 audit) — B2a, this host.** Run clone `$W/cassandra-run43` (`W=~/Library/Caches/stage4`; `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run43`, then `ant -Dlocal.repository=$W/m2 build-test`), macOS arm64, JDK 11.0.32.1, Ant 1.10.18; no `/local` paths and no `--depth 1`. The harness script `harness/min_index_interval-validate-minIndexInterval--autonomous/unit-run.sh` copies `IndexIntervalCapTest.java` into the clone, runs `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.io.sstable.indexsummary.IndexIntervalCapTest` once, and removes the file (the clone's git status stays clean). Every reading is one `System.out.println` line with prefix `MII `, read from `build/test/logs/**/TEST-<class>.log`. Reason: paths of another machine; the output location was open.

**B2b. Knobs.**
- m ∈ {1, 16, 128, 512} with M = 2048.
- Downsampling: (m, M) = (128, 2048) and (128, 512).
- Validation: `TableParams.builder().minIndexInterval(0)`, `.minIndexInterval(-5)`, `.minIndexInterval(128).maxIndexInterval(127)`, `.minIndexInterval(128).maxIndexInterval(128)`. The last one should pass.

**B2c. Workload.**
- N = 1,000,000 keys, `ByteBufferUtil.bytes((long) i)` (8-byte keys), decorated and sorted by token.
- Feed them to `new IndexSummaryBuilder(N, m, 128)` via `maybeAddEntry(key, i * 100L)`, then `build(partitioner)`.
- For downsampling, call `IndexSummaryBuilder.downsample(summary, ceil(128·m/M), m, partitioner)`.
- Arithmetic at m = 1: 1M × 20 B = 20 MB off-heap, enough to measure and small enough for a test JVM.

**Amendment 2026-10-26 (step-0 audit) — B2c, write-path trim, order.** `builder.prepareToCommit()` is called before `build(partitioner)`, as the write path does (`BigTableWriter.java:320-321`); it trims the builder's memory, pre-sized for 64-byte keys (`IndexSummaryBuilder.java:42,105-128`), to the bytes written (`SafeMemoryWriter.java:69-72`, `IndexSummaryBuilder.java:246-252`). Keys are built once and sorted by token; the same array is used for every m. Order: m = 1, 16, 128, 512 (the m = 128 summary kept open for step 2, the others closed after their line); step 2 downsamples the m = 128 summary to level `ceil(128·m/M)` for M = 2048 then 512. Reason: without the trim the summary holds the builder's untrimmed capacity, which no sstable on a node holds after a flush; the order was open.

**B2d. Observables and instruments.** `summary.size()`, `summary.getOffHeapSize()`, `getSamplingLevel()`, `getEffectiveIndexInterval()`. For validation, whether `ConfigurationException` is thrown. Not observable at this tier: redistribution scheduling and read-rate meters.

**Amendment 2026-10-26 (step-0 audit) — B2d, output lines and the real resource.** Lines: `MII build m=<m> size=<entries> offHeap=<getOffHeapSize()> alloc=<native bytes> level=<getSamplingLevel()> interval=<getEffectiveIndexInterval()> maxEntries=<getMaxNumberOfEntries()>`; `MII down m=128 M=<M> target=<level> size=… offHeap=… alloc=… level=… interval=…`; `MII validate case=<min>/<max or default> result=<ok | threw:<class>:<message>>`; `MII calc M=<M> level=<calculateSamplingLevel(128, size128, 1, 128, M)>`; `MII done` last. `alloc` = `getOffsets().size() + getEntries().size()` (package-private, `IndexSummary.java:244-257`): the bytes of the two `Memory` blocks the summary holds, the real off-heap resource; `offHeap` is the counter every metric reads (`IndexSummary.java:259-262`). Gap: no process-level native-memory reading. Reason: output format open; group A asks for the real resource.

**B2e. Procedure.**
1. For each m, build the summary, record the four values, then close it.
2. For each (m, M), downsample the m = 128 summary and record the values.
3. Run the four validate cases and record pass or fail.
4. Run `IndexSummaryBuilder.calculateSamplingLevel(128, size, 1, m, M)` (package-private; the test is in the same package) and record the result.

**Amendment 2026-10-26 (step-0 audit) — B2e, stop condition.** Each step is caught and printed, so the test runs to `MII done`; a missing `MII done`, a missing line, or a JUnit error is an invalid run. Reason: the stop condition was open.

**B2f. Predictions.** At 20 B/entry:

| m | entries | off-heap bytes |
|---|---|---|
| 1 | 1,000,000 | 20,000,000 |
| 16 | 62,500 | 1,250,000 |
| 128 | 7,813 | 156,260 |
| 512 | 1,954 | 39,080 |

- Downsample (128, 2048) → level 8, ≈ 489 entries, ≈ 9.8 KB. (128, 512) → level 32, ≈ 1,954 entries, ≈ 39 KB.
- `calculateSamplingLevel` returns 8 and 32 respectively.
- Validation: the first three cases throw, (128, 128) passes.

**Amendment 2026-10-26 (step-0 audit) — B2f, exact values from the source.** (i) Each built summary: `size = ceil(N/m)` (sample at keys 0, m, 2m, …, `IndexSummaryBuilder.java:200-244`), `offHeap = 20 × size` exactly (4 B offset + 8 B key + 8 B position), `alloc = offHeap` exactly (trimmed), level 128, interval = m, maxEntries = size; values as in the table above. (ii) Downsampling the m = 128 summary (7,813 entries): the entries removed are those whose index is ≡ s (mod 128) for each start point s of `Downsampling.getStartPoints(128, L)` (`IndexSummaryBuilder.java:324-380`, `Downsampling.java:125-148`): M = 2048 → L = 8, **489 entries, 9,780 B**, interval 2,048; M = 512 → L = 32, **1,954 entries, 39,080 B**, interval 512; `alloc = offHeap` (the new `Memory` blocks are allocated at the exact sizes, `:352-353`); maxEntries 7,813. (iii) `calculateSamplingLevel` returns exactly 8 and 32 (`IndexSummaryBuilder.java:299-314`). (iv) Messages (`TableParams.java:185-194,206-209`): `min_index_interval must be greater than or equal to 1 (got 0)`, `… (got -5)`, `max_index_interval must be greater than or equal to min_index_interval (128) (got 127)`; 128/128 → ok. (v) No warning `min_index_interval of 1 is too low` (72 B × 10^6 < 2^31, `:106-117`). Reason: B2f used ≈ for values the source fixes exactly.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Entries = ceil(N/m) and bytes = 20 × entries | Claim (a) holds at the unit level |
| Bytes do not fall with m | Claim (a) refuted |
| Downsampled level = ceil(128·m/M) and bytes scale with it | Claim (b) mechanism as traced |
| Downsample goes below the M floor | (b) refuted: M is not a floor |
| m = 0 or M < m passes validate | The :185/:188 check refuted |

**Amendment 2026-10-26 (step-0 audit) — B2g, verdicts and added rows.** Row 1 together with row 3 and all four validation results as in B2f (iv) → **Confirmed**, Effect `caps` (m bounds the summary at `ceil(N/m)` entries; M bounds how far it can be downsampled, a floor, recorded with the verdict). Row 2 → **Refuted**, Effect `does not cap`. Row 4 → **Refuted** for (b). Row 5 → **Refuted** for the check. Added: (a) `alloc ≠ offHeap` at any point → **Not confirmed for the real resource**, Effect `undetermined`; (b) entries or bytes off the B2f exact values while still falling with m → **Not confirmed** (the trace is wrong in detail), Effect `caps`; (c) `calculateSamplingLevel` ≠ 8 / 32 → **Refuted** for (b); (d) 128/128 refused → **Refuted** for the check (`≤` not `<`); (e) a missing line, missing `MII done`, a JUnit error, or the too-low-interval warning → **Invalid**, Effect `undetermined`. Reason: rows had meanings without verdicts and lacked the real-resource and invalid outcomes.

**B2h. Controls.**
- Same keys for all m.
- (128, 128) passing shows the M check is `<`, not `≤`.
- The m = 1 row shows the densest allowed case. The automatic raise (`:108-117`) is not triggered at 1M keys (20 MB < 2 GiB), so it does not confound.

**Amendment 2026-10-26 (step-0 audit) — B2h, control evidence.** Same keys: one sorted array (B2c amendment). (128, 128) passing: its `MII validate` line. No auto-raise: no warning in the test log and `interval = 1` for m = 1. Reason: each control names its evidence.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node, JDK 11, `ant jar` in `/local/c509`, run with `bin/cassandra -f -R`.
- Yaml: data/commitlog/hints/saved_caches under `/local/cass`, `concurrent_compactors: 1`.
- Phase 1: `index_summary_resize_interval:` (empty → disabled) and `index_summary_capacity:` (default).
- Phase 2: `index_summary_resize_interval: 1m`.
- `MAX_HEAP_SIZE=4G`, `HEAP_NEWSIZE=800M`, so the default capacity is ≈ 204.8 MiB.

**Amendment 2026-10-26 (step-0 audit) — B3a, this host and phase 2's capacity.** One node on 127.0.0.1 from `$W/cassandra-run43` (no `ant` run in the clone while the node runs); node directory `$W/node-mii43` (data, commit log, hints, saved caches, cdc), conf generated by the harness's `make-node-conf.sh` from the clone's shipped yaml plus this node's lines; started as a tracked background `bin/cassandra -f` (no `-R`: not root; no `setsid` on this host) with `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M`; `concurrent_compactors: 1`. Phase 1: `index_summary_resize_interval:` (null), `index_summary_capacity:` (shipped, empty). Phase 2: `index_summary_resize_interval: 1m`; **phase 2a** keeps the default capacity (`int(totalMemory × 0.05 / 2^20)`, ≈ 204 MiB, `DatabaseDescriptor.java:867-869`; read back from the log line `Initializing index summary manager with a memory pool size of N MB`); **phase 2b** sets the capacity to **0 MiB** at run time through the writable MBean attribute `org.apache.cassandra.db:type=IndexSummaries` `MemoryPoolCapacityInMB` (`IndexSummaryManagerMBean.java:25-26`, `IndexSummaryManager.java:184-187`), read back. Reason, from the source: with no reads every sstable's `idealSpace` is 0 and its target 1 entry (`IndexSummaryRedistribution.java:183,188`), so it is put on the downsample list at its floor and `remainingSpace` falls by the floor size only (`:241-246`); while `remainingSpace > 0` (`:258`), `distributeRemainingSpace` (`:327-355`) takes every sstable back off the list whose regained bytes still fit. At ≈ 204 MiB against ≈ 95 MB of full summaries (B3f) every sstable fits, so at the default capacity nothing is downsampled and B3f's phase-2 floors are not reachable. With capacity 0, `remainingSpace` starts at 0, `distributeRemainingSpace` is not called, and every zero-read sstable goes to its floor `max(1, ceil(128·m/M))`. Phase 2a records the default-capacity behaviour as a control; phase 2b tests B1 (b) as B3f predicts it.

**B3b. Knobs.**
- Phase 1: keyspace `ii` (RF 1) with tables `t1`, `t16`, `t128`, `t512` and `min_index_interval` = 1, 16, 128, 512 (all `max_index_interval = 2048`).
- Phase 2: tables `t128` (M = 2048) and `m512` (m = 128, M = 512).
- Boundary DDL: `ALTER TABLE ii.t128 WITH min_index_interval = 0` and `WITH max_index_interval = 64`. Both should be refused.

**Amendment 2026-10-26 (step-0 audit) — B3b, keyspaces.** B3b's keyspace `ii` with tables `t1…` and B3c's keyspaces `ii_X` disagree; B3c's form is used: five keyspaces (SimpleStrategy RF 1), each with one table `standard1`: `ii_1` (m 1, M 2048), `ii_16` (16, 2048), `ii_128` (128, 2048), `ii_512` (512, 2048), `ii_m512` (128, 512). All five are written in phase 1 and observed in phase 2. The boundary ALTERs run on `ii_128.standard1`. Reason: inconsistency; B3c, B3e and B3f use the `ii_X` names.

**B3c. Workload.**
- Create each table as `(key blob PRIMARY KEY, "C0" blob) WITH compression = {} AND min_index_interval = m AND max_index_interval = M`, then run `nodetool disableautocompaction ii`.
- Per table: `tools/bin/cassandra-stress write n=4000000 cl=ONE -pop seq=1..4000000 -col n=FIXED(1) size=FIXED(16) -schema keyspace=ii -rate threads=64`. Write each table in turn by pre-creating only that table name as `standard1` in its own keyspace (`ii_1`, `ii_16`, `ii_128`, `ii_512`, `ii_m512`). Stress writes to `<keyspace>.standard1`, and `CREATE TABLE IF NOT EXISTS` keeps the pre-created table.
- Then `nodetool flush`.
- Stress keys are 10 bytes, so an entry is 22 B.
- Data per keyspace is ≈ 4M × ~40 B ≈ 160 MB, ≈ 1 GB total.
- Duration: about 3-5 minutes per keyspace for phase 1, plus 5 minutes for phase 2.

**Amendment 2026-10-26 (step-0 audit) — B3c, commands and the limit-reached check.** Each table: `CREATE TABLE ii_X.standard1 (key blob PRIMARY KEY, "C0" blob) WITH compression = {} AND compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'} AND min_index_interval = m AND max_index_interval = M` (the table option replaces `nodetool disableautocompaction`, which does not survive the restart at B3e step 4). Stress per keyspace, in the order ii_1, ii_16, ii_128, ii_512, ii_m512: `tools/bin/cassandra-stress write n=4000000 cl=ONE -pop seq=1..4000000 -col n=FIXED(1) size=FIXED(16) -schema keyspace=ii_X -rate threads=64 -node 127.0.0.1`, then `nodetool flush ii_X standard1`. Limit reached: the `totalRows` sum over the keyspace's sstables (sstablemetadata) is 4,000,000 and stress reports `Total errors: 0`. Reason: the commands were not exact; the restart would re-enable compaction.

**B3d. Observables and instruments.**
- `nodetool tablestats ii_X.standard1`, field "Index summary off heap memory used", and JMX `org.apache.cassandra.metrics:type=Table,keyspace=ii_X,scope=standard1,name=IndexSummaryOffHeapMemoryUsed`.
- Total summary use and capacity: JMX `org.apache.cassandra.db:type=IndexSummaries` attributes `MemoryPoolSizeInMB`, `MemoryPoolCapacityInMB`, `AverageIndexInterval` (read with `tools/bin/jmxtool` or `jconsole`).
- Disk: `du -cb .../*-Summary.db`.
- Log lines "Redistributing index summaries" / "Completed resizing" in `logs/system.log`.
- Sampling: once after flush (phase 1), and once every minute for 5 minutes (phase 2).
- Not directly observable: the per-sstable sampling level, except via `AverageIndexInterval` and the bytes.

**Amendment 2026-10-26 (step-0 audit) — B3d, instruments on this host.** (i) A harness JMX client `MiiProbe.java` (no jmxterm here; `jmxtool` does not read attributes): `snap` prints the IndexSummaries attributes `MemoryPoolSizeInMB` (× 2^20), `MemoryPoolCapacityInMB`, `AverageIndexInterval`, `ResizeIntervalInMinutes`, the five tables' `IndexSummaryOffHeapMemoryUsed`, and the `IndexIntervals` map (per sstable, `round(128/L × m)`, `IndexSummaryManager.java:165-173`), from which each sstable's level L is read; `setcap <MB>` sets and reads back `MemoryPoolCapacityInMB`. (ii) `nodetool tablestats ii_X.standard1` ("Index summary off heap memory used"). (iii) Disk: `stat -f %z` of every `*-Summary.db` (BSD; no `du -cb`). (iv) `sstablemetadata` of every Data.db (rows per sstable). (v) `system.log` lines `Redistributing index summaries`, `index summaries: downsample: …`, `Completed resizing`. Real resource: the gauge is the counted bytes of the summaries' memory; Summary.db holds the same bytes plus 52 B per sstable (B3f amendment) and is the independent byte reading; process RSS is recorded as context only (gap: no per-allocation native reading on the node). Sampling: a snapshot per record point, and every 60 s in phases 2a and 2b. Reason: tools named in B3d are not on this host; group A.

**B3e. Procedure.**
1. Phase 1 yaml. Start the node and create the keyspaces and tables. Disable autocompaction.
2. Run stress and flush per keyspace, then record the gauges and `du`.
3. Run the boundary ALTERs and record the errors.
4. `nodetool drain`, stop the node. Set `index_summary_resize_interval: 1m`, restart, and run `nodetool disableautocompaction` on all keyspaces again.
5. Issue no reads. Sample the gauges and `AverageIndexInterval` each minute for 5 minutes.
6. Positive control for (b): `ALTER TABLE ii_m512.standard1 WITH max_index_interval = 2048`, wait 2 minutes, record (expect it to drop to the t128 level). Then `ALTER ... max_index_interval = 256`, wait, record (expect a forced upsample, `IndexSummaryRedistribution.java:222-230`).
7. Drain, stop, and check no Cassandra JVM is left.

**Amendment 2026-10-26 (step-0 audit) — B3e, procedure as run.** One script (`cluster-run.sh`), shakedown first with n = 100,000 (not judged). 1. Phase-1 conf; start; wait for `UN` and `statusbinary running`; create the five keyspaces and tables (B3c amendment). 2. Per keyspace: stress, flush, record P1 (snapshot, tablestats, Summary.db sizes, sstablemetadata, RSS). 3. Boundary ALTERs `ALTER TABLE ii_128.standard1 WITH min_index_interval = 0` and `… WITH max_index_interval = 64`, cqlsh exit code and output; read back both columns from `system_schema.tables`. `nodetool compactionhistory`. 4. Drain, stop; conf with `index_summary_resize_interval: 1m`; restart (same data). 5a. Phase 2a, default capacity, no reads: snapshot every 60 s until at least two `Completed resizing` lines exist after the restart (at most 240 s); record P2a. 5b. `setcap 0`, read back; snapshot every 60 s for 5 minutes (5 snapshots); record P2b at the end; at least two `Completed resizing` lines must lie after the setcap. 6. `ALTER TABLE ii_m512.standard1 WITH max_index_interval = 2048`; wait until two `Completed resizing` lines lie after the ALTER (at most 200 s); record S6a. Then `… max_index_interval = 256`, the same wait, record S6b. 7. `compactionhistory`, ERROR count, drain, stop, check no daemon, stress or cqlsh process is left, wipe `$W/node-mii43`. Reason: phase 2a/2b and the waits follow from the B3a amendment; the waits were open.

**B3f. Predictions.**
- Phase 1, with Σ over flush sstables (+ ≤ 22 B per sstable):

  | table | off-heap |
  |---|---|
  | ii_1 | ≈ 88.0 MB |
  | ii_16 | ≈ 5.50 MB |
  | ii_128 | ≈ 0.69 MB |
  | ii_512 | ≈ 0.17 MB |

  Summary.db is of the same order plus the first/last key. Both boundary ALTERs are refused.
- Phase 2, no reads, so target = 1 entry and each sstable drops to its floor:
  - ii_128 (M = 2048): level 8 → ≈ 43 KB.
  - ii_m512 (M = 512): level 32 → ≈ 172 KB.
  - ii_1 (m = 1, M = 2048): level 1 → ≈ 0.69 MB.
  - ii_16: level 1 → ≈ 43 KB.
  - ii_512: level 32 → ≈ 43 KB.
  - Total ≈ 1 MB, far under the ~205 MiB capacity. The values are set by M, not by capacity.
- Step 6: ii_m512 → ≈ 43 KB at M = 2048, and ≈ 344 KB (level 64) at M = 256.

**Amendment 2026-10-26 (step-0 audit) — B3f, exact relations and bands from the source.** Stress keys are 10 B (`SettingsCommandPreDefined.java:82,108`), so an entry is 22 B. **P1:** per keyspace, gauge = Σ_i ceil(rows_i/m) × 22 over its sstables (recorded exact check from sstablemetadata rows); band ±1 % of 4,000,000 × 22 / m: ii_1 88,000,000; ii_16 5,500,000; ii_128 687,500; ii_512 171,875; ii_m512 687,500 B; every ii sstable's interval = m (level 128). Σ Summary.db = gauge + 52 B × sstables (24-B header `IndexSummary.java:401-405`, plus first and last key with 4-B lengths, `IndexSummaryComponent.java:125-127`). Boundary ALTERs: cqlsh exit ≠ 0 with `min_index_interval must be greater than or equal to 1 (got 0)` and `max_index_interval must be greater than or equal to min_index_interval (128) (got 64)` (the CQL validate builds from the builder defaults plus the given option, `TableAttributes.java:59-66`); read-back 128 / 2048. **P2a** (≈ 204 MiB): every ii gauge equal to its P1 value, every interval still m, every redistribution logs `index summaries: downsample: 0, force resample: 0, upsample: 0, force upsample: 0` (B3a amendment). **P2b** (capacity 0): every ii sstable at its floor L = max(1, ceil(128·m/M)): ii_1 L 1 (interval 128), ii_16 1 (2048), ii_128 8 (2048), ii_512 32 (2048), ii_m512 32 (512); gauge = Σ_i down(ceil(rows_i/m), L) × 22 with `down` the start-point removal of B2f (ii) (recorded exact check); band ±2 % of 4,000,000/m × L/128 × 22: ii_1 687,500; ii_16 42,969; ii_128 42,969; ii_512 42,969; ii_m512 171,875 B (the per-sstable start-point remainder gives at most 0.61 % over 300 simulated splits of 4–20 sstables). The five sum to ≈ 1.03 MB, above the capacity of 0. Σ Summary.db = gauge + 52 × sstables. **S6a** (ii_m512 M = 2048): its sstables at L 8 (interval 2048), gauge ±2 % of 42,969 B (exact: the start points of 32 → 8 applied to the P2b summaries); the other four unchanged from P2b. **S6b** (M = 256): a log line `force upsample: n` with n ≥ the ii_m512 sstable count after the ALTER (`IndexSummaryRedistribution.java:224-231`); its sstables at L 64 (interval 256), gauge ±2 % of 343,750 B (exact: a builder at level 64 over rows_i, `BigTableReader.java:631-640`); the other four unchanged. Reason: B3f used ≈ throughout and predicted floors at a capacity where they are not reached (B3a amendment).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Phase 1 bytes ∝ 1/m within a few % | (a) confirmed: m caps summary memory |
| Phase 1 bytes equal across m | (a) refuted |
| Phase 2 bytes settle at the M floors, and step 6 moves them with M | (b) confirmed: M floors summary memory; the 188 target bounds downsampling, not usage from above |
| Phase 2 bytes go below the M floor | (b) refuted |
| Phase 2 does not run (no "Redistributing" log line) | Not confirmed: re-run with the resize interval set and check the logs |
| A boundary ALTER accepted | The :185/:188 check refuted |

**Amendment 2026-10-26 (step-0 audit) — B3g, verdicts and added rows.** (a) **Confirmed**, Effect `caps`, when row 1 holds as amended (all five P1 gauges in band, intervals = m, Σ Summary.db = gauge + 52 × sstables) and row 6's ALTERs are refused with the B3f messages and read back unchanged. (b) **Confirmed** (M sets a floor; Effect for :188 `does not cap`) when row 3 holds as amended: P2b all floors and gauges in band, S6a and S6b as in B3f, and P2a unchanged. Row 2 → **Refuted** for (a), Effect `does not cap`. Row 4 → **Refuted** for (b). Row 5 → **Not confirmed** for (b) (no re-run in this tier without a new amendment). Row 6 (an ALTER accepted) → **Refuted** for the check. Added: (c) P2a not unchanged (some ii summary downsampled at ≈ 204 MiB) → **Not confirmed** for (b): the B3a derivation is wrong; (d) P2b neither at the floors nor below them (e.g. some sstables kept above the floor at capacity 0) → **Not confirmed** for (b); (e) S6a or S6b off → **Not confirmed** for (b); (f) Σ Summary.db ≠ gauge + 52 × sstables → **Not confirmed for the real resource**; (g) stress errors, a `totalRows` sum ≠ 4,000,000, an ii compaction (an `ii_` line in `compactionhistory` or a changed sstable count), or the node dying → **Invalid**, Effect `undetermined`. The tier's verdict states (a) and (b) separately; the Effect field is that of (a), with (b)'s result named next to it. Reason: rows had meanings without verdicts; the outcomes of phase 2a/2b and invalid runs were missing.

**B3h. Controls.**
- Identical data in each keyspace.
- Compaction is disabled.
- Redistribution is disabled in phase 1, so phase 1 shows m only.
- Phase 2 has no reads, so read rates cannot confound.
- Step 6 moves usage with M on the same sstables.

**Amendment 2026-10-26 (step-0 audit) — B3h, control evidence.** Identical data: `totalRows` 4,000,000 and the same `-pop seq` per keyspace. Compaction disabled: table option, no `ii_` line in `compactionhistory`, constant sstable counts per keyspace through every record point. Phase 1 without redistribution: `ResizeIntervalInMinutes` −1 in the P1 snapshots and no `Redistributing` line before the restart. No reads: none issued (the script reads only JMX, nodetool tablestats and offline sstablemetadata). Step 6 moves the same sstables with M. Reason: each control names its evidence.

**B4. Risks and cleanup.** Data is ≈ 1-2 GB under `/local/cass` only. Afterwards: `rm -rf /local/cass`, `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` should both be empty, and remove `/local/c509` when done. The unit tier allocates ≤ 20 MB off-heap and closes every summary.

**Amendment 2026-10-26 (step-0 audit) — B4, this host.** Data under `$W/node-mii43` only, wiped before and after each cluster run; check `ps -eo command | grep '[C]assandraDaemon'` empty, no stress or cqlsh process; the run clone `$W/cassandra-run43` stays with a clean git status. Reason: paths of another machine.

## C. Sources read

- src/java/org/apache/cassandra/schema/TableParams.java
- src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java
- src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummary.java
- src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryRedistribution.java
- src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryManager.java
- src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryManagerMBean.java
- src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryMetrics.java
- src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java
- src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java
- src/java/org/apache/cassandra/io/sstable/Downsampling.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- conf/cassandra.yaml
- tools/stress/src/org/apache/cassandra/stress/settings/SettingsSchema.java
- https://issues.apache.org/jira/browse/CASSANDRA-5519

## D. Stage-4 feedback

**2026-10-26, stage 4 run 1 on the advisor's machine** (results: [`../../stage4-runtime-verification/results/min_index_interval-validate-minIndexInterval--autonomous.md`](../../stage4-runtime-verification/results/min_index_interval-validate-minIndexInterval--autonomous.md); frozen at sha256 `5446447a…823e` after sixteen dated step-0 amendments; uncommitted).
- **Unit: Confirmed — caps (m); M a floor** (B2g rows 1 and 3). 1M keys gave 20,000,000 / 1,250,000 / 156,260 / 39,080 B at m = 1 / 16 / 128 / 512 (20 B per sampled key; the two `Memory` blocks hold exactly the counted bytes). Downsampling the m = 128 summary stopped at levels 8 (M 2048, 489 entries) and 32 (M 512, 1,954 entries). m = 0, −5 and 128/127 were refused with the exact messages; 128/128 was accepted.
- **Cluster: Confirmed — caps (m); M a floor, does not cap** (B3g rows 1 and 3). 4M keys gave 88,000,000 / 5,500,044 / 687,566 / 171,952 B at m = 1 / 16 / 128 / 512, each equal to Σ ceil(rows_i/m)·22, with Summary.db + 52 B per sstable; both boundary ALTERs were refused. With no reads and the pool at 0 MiB, every sstable went to its floor (0.99 MB in all, above the pool), and ALTERing M on `ii_m512` moved it to 43,054 B (2048) and, by a forced upsample, 343,794 B (256).
- **Note for stage 3 (not applied):** at the default pool (204 MiB) the zero-read redistribution downsampled nothing (`downsample: 0` in both runs), because `distributeRemainingSpace` (`IndexSummaryRedistribution.java:258-264, 327-355`) hands back every listed summary that still fits. A3 step 4 and B1 (b) should say that the M floor appears only when the pool is below the full total; above it the summaries stay at full sampling, so they follow neither M nor the pool. The audit split phase 2 for this reason (2a default pool, 2b pool 0). Also untested: the CQL validate checks a lone `max_index_interval` against the default m 128 (`TableAttributes.java:59-66`), not the table's own m; and summaries rebuilt by a forced upsample (`BigTableReader.java:625-640`) are not trimmed, so their allocation may exceed the counted bytes.
