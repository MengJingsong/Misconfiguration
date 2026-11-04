# indexing_target_page_size (32 MiB target for 2i build pages) — verification solution  <!-- file: cases/indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`SecondaryIndexManager.java:1156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/SecondaryIndexManager.java#L1156), `:1160#1`, `:1164#1` (three guards in one function, one constraint, one case file) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5[1m]), Claude Code CLI (version not readable in session), 2026-10-26, Band D triage mode |
| Estimate | `positive`, but with a bypass. When the base table has sstable statistics and at least one regular column, the hard-coded 32 MiB byte target sets the page size, so the heap held by one materialized build page is about 32 MiB of row data. The three target guards are the fallbacks to a flat 10000 rows with no byte limit. `:1156` and `:1160` fire only when no canonical sstable statistics exist, which in practice means no data to page. `:1164` fires for any table with zero regular columns, and there the page is bounded only by row count. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** It is a hard-coded constant, `double targetPageSizeInBytes = 32 * 1024 * 1024` ([`SecondaryIndexManager.java:1153`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/SecondaryIndexManager.java#L1153)), a local in `calculateIndexingPageSize()` (`:1149`). It is paired with the row-count ceiling and fallback `DEFAULT_PAGE_SIZE = 10000` ([`SecondaryIndexManager.java:142`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/SecondaryIndexManager.java#L142)). Unit: bytes for the target, rows for the page size. The target cannot be changed (no yaml key, no `-D`, no JMX). The only switch is the JVM property `cassandra.force_default_indexing_page_size` ([`CassandraRelevantProperties.java:240`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L240), read at [`SecondaryIndexManager.java:1151`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/SecondaryIndexManager.java#L1151) on every call). If it is true, the byte target is skipped and the page is always 10000 rows. Setting it on a node takes a restart (`-D`). A test JVM can call `System.setProperty`, because the value is read on each call.


**Limit type (2026-10-29).** non-config: hard-coded constant. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Heap. The page size in rows is computed so that `pageSize × meanRowSize ≈ 32 MiB`, capped at 10000 and floored at 1 (`:1170`). The heap object it bounds is the page that `indexPartition` materializes as an `ImmutableBTreePartition` (`SecondaryIndexManager.java:1059-1066`) before handing its rows to the indexers. The code compares statistics, not usage. The inputs are `getMeanPartitionSize()` (`ColumnFamilyStore.java:3123-3134`, from each sstable's estimated partition-size histogram), `getMeanEstimatedCellPerPartitionCount()` (`ColumnFamilyStore.java:3110-3121`), and the regular column count (`:1163`).

**A3. Mechanism.**
1. A legacy 2i build (`CassandraIndex.buildBlocking`, `internal/CassandraIndex.java:690-713`), a rebuild (`rebuildIndexesBlocking`, [`SecondaryIndexManager.java:391`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/SecondaryIndexManager.java#L391), flush at `:420`), or any custom index using the default `Index.INDEX_BUILDER_SUPPORT` (`Index.java:200,208`) creates a `CollatedViewIndexBuilder`. Its `build()` calls `calculateIndexingPageSize()` once per build (`internal/CollatedViewIndexBuilder.java:74`) and then `indexPartition(key, indexers, pageSize, columns)` per partition (`:82`).
2. `calculateIndexingPageSize()`:
   - `:1151` property true → 10000.
   - `:1156` (target) `meanPartitionSize <= 0` → 10000. This is 0 only when no canonical sstable has partitions ([`ColumnFamilyStore.java:3133`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3133)).
   - `:1160` (target) `meanCellsPerPartition <= 0` → 10000. `EstimatedHistogram.mean()` returns at least the first bucket offset of 1 once anything was added (`utils/EstimatedHistogram.java:235-260`), so this is 0 only with no sstable partitions, the same condition as `:1156`.
   - `:1164` (target) `columnsPerRow <= 0` → 10000. `regularColumns()` excludes clustering and static columns, so this fires for every table whose only non-key columns are static, or that has none.
   - Otherwise `meanRowsPerPartition = meanCells / columnsPerRow` (`:1167`, integer division), `meanRowSize = meanPartitionSize / meanRowsPerPartition` (`:1168`), and `pageSize = max(1, min(10000, 32 MiB / meanRowSize))` (`:1170`).
3. `indexPartition` pages one partition with a `SinglePartitionPager` (`:1053-1059`). `fetchPageUnfiltered` limits each page to `min(pageSize, remaining)` rows (`service/pager/AbstractQueryPager.java:95-101`). The whole page is copied into an `ImmutableBTreePartition` (`:1066`), and after that rows are fed to the indexers between `begin()` and `finish()` (`:1090-1132`). One page is live at a time.

Overshoots and bypasses:
- (a) All three fallbacks drop the byte target. `:1164` is reachable with real data, so 10000 rows of any size can be held.
- (b) The estimate uses a mean, so partitions or rows larger than the mean overshoot proportionally.
- (c) Histogram means use bucket offsets with about a 1.2 ratio between buckets, so the estimate is off by up to about ±20% either way.
- (d) The size is the serialized size of all columns. The build reads only the indexed columns when the index depends on specific columns ([`CollatedViewIndexBuilder.java:90-113`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/internal/CollatedViewIndexBuilder.java#L90-L113)), so real page heap is usually below the target, not above it.
- (e) `meanCells < columnsPerRow` (sparse rows) makes `meanRowsPerPartition = 0` and `meanRowSize = ∞`, which gives a page of 1 row. That is harmless for memory.
- (f) On-heap size per row exceeds serialized size by object overhead.

**A4. Other consumers.** The index table's memtable receives the index writes during the build (`CassandraIndex` indexer → `indexCfs` writes), and memtable heap is governed by `memtable_heap_space`. Compaction and other reads run concurrently. The chunk cache and buffer pool hold off-heap buffers for sstable reads. SAI uses `StorageAttachedIndexBuildingSupport` (`sai/StorageAttachedIndex.java:150,581-584`) and SASI uses its own support (`sasi/SASIIndex.java:119`). Neither goes through this function.

**A5. Evidence beyond the source.** `test/unit/org/apache/cassandra/index/CustomIndexTest.java:758-797,834-867` (`indexPartition` paging with explicit page sizes) and `test/unit/org/apache/cassandra/index/StubIndex.java`. No test exercises `calculateIndexingPageSize`. The git history in the clone is shallow and gives no introduction commit. No external source was relied on.

## B. Verification solution

**B1. Claim under test.**
- (i) With the property unset and a table that has at least one regular column, the rows held per build page are `≈ 32 MiB / meanRowSize`, so the heap per page stays near 32 MiB whatever the row size.
- (ii) With `cassandra.force_default_indexing_page_size=true`, or with a table that has zero regular columns (target guard `:1164`), the page is `min(10000, partition rows)` rows and its heap grows linearly with row size, with no byte bound.

### B2. Unit tier

**B2a. Environment and build.** JDK 11 and Ant. Clone the tag to local disk: `git clone --branch cassandra-5.0.9 --depth 1 file:///Users/yangwang/cassandra-src /local/c509 && cd /local/c509 && ant jar build-test`. Add the probe as `test/unit/org/apache/cassandra/index/IndexingPageSizeProbeTest.java`, extending `CQLTester`, in the local clone only. Run it with `ant testsome -Dtest.name=org.apache.cassandra.index.IndexingPageSizeProbeTest` (the testsome JVM gets `-Xmx4G`, `build.xml:1245-1255`).

> **Amendment B2a (2026-10-26, stage-4 audit, before any run-1 reading).** On the advisor's machine (macOS 27, arm64, JDK 11.0.32.1, Ant 1.10.18; `environment-advisor.md`) the clone is
> `$W/cassandra-run38` (`W=~/Library/Caches/stage4`), a fresh full `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run38` (no `/local`, no `--depth`),
> built with `ant -Dlocal.repository=$W/m2 build-test` (it builds the jar classes too). The probe is `stage4-runtime-verification/harness/indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous/IndexingPageSizeProbeTest.java`;
> `unit-run.sh` in the same folder copies it into `test/unit/org/apache/cassandra/index/`, runs `ant testsome`, and removes it, so the clone's `git status` stays clean.
> **Heap correction:** the testsome JVM gets `-Xmx1024m` from the junit task's `maxmemory="1024m"` (`build.xml:1153`); `build.xml:1245-1255` belongs to the
> `testlist` macro, which testsome does not use, and `-Dtest.jvm.args=-Xmx4G` does not override it (checked: the probe prints the JVM's max heap). 1 GiB holds the largest
> page (≈ 131 MB); default test JVM options are kept.

**B2b. Knobs.**
- K1: the property `cassandra.force_default_indexing_page_size`, `false`/`true`, set with `System.setProperty` before each call.
- K2: schema, with regular column count 1 versus 0 (exercises `:1164`).
- K3: data presence, sstables flushed versus memtable only (exercises `:1156`/`:1160`).
- Row size is fixed at about 64 KB so that the computed page (about 500 rows) is well below 10000.

**B2c. Workload.**
- T1: `CREATE TABLE %s (k int, c int, v blob, PRIMARY KEY (k,c))`. Insert 2000 rows into `k=0`, each with `v` set to a 65536-byte blob filled with `(byte) c`. Then `flush()`. The partition is about 131 MB serialized. At 32 MiB / about 65.6 KB that gives about 511 rows per page, about 4 pages. Forced: `min(10000, 2000)` = one page of all 2000 rows, about 131 MB.
- T2: `CREATE TABLE %s (k int, c text, s int static, PRIMARY KEY (k,c))`. Insert 2000 rows into `k=0`, with `c` set to a 60000-char string (`String.format("%05d", i)` followed by 59995 `'a'`), plus `s=1`. Then `flush()`. This has zero regular columns, so `:1164` applies.
- T2b: the same as T2 plus a regular column `v int` set to 1 in every row (control for T2).
- T3: a T1 schema with 10 rows inserted and no flush (no sstables).

**B2d. Observables and instruments.**
- The return value of `cfs.indexManager.calculateIndexingPageSize()`, together with `cfs.getMeanPartitionSize()` and `cfs.getMeanEstimatedCellPerPartitionCount()`.
- A probe index, `PageProbeIndex extends StubIndex` (created with `CREATE CUSTOM INDEX ON %s(v) USING '<class>'`, or on `c` for T2). Its indexer resets counters in `begin()`, adds 1 and `row.dataSize()` (`db/rows/Row.java:314`) in `insertRow`, and in `finish()` records the page row count and byte sum into lists. `StubIndex.dependsOn` returns false (`StubIndex.java:80-83`), so all columns are read.
- Drive it with `cfs.indexManager.indexPartition(cfs.decorateKey(bytes(0)), Set.of(index), pageSize)`, the same call the builder makes (`CollatedViewIndexBuilder.java:82`).
- Optional: `ObjectSizes.measureDeep` over the rows of the largest page, for on-heap bytes.
- Real heap is not observed in this tier.

> **Amendment B2d (2026-10-26, stage-4 audit, before any run-1 reading).** Exact instrument. `PageProbeIndex extends StubIndex` overrides `indexerFor` (it does not retain rows): per page
> (one `begin()`..`finish()`), it counts **non-static** rows, the sum and the maximum of their `row.dataSize()`, and separately the static rows (the static row is fed on the first
> page only, `SecondaryIndexManager.java:1094-1100`, and is not one of the rows the pager limits). The index is created with `createIndexAsync` (a `StubIndex` has no
> initialization task), on `v` for T1/T3 and on `c` for T2/T2b. `indexPartition` is called with three arguments, which reads `regularAndStaticColumns()`
> (`SecondaryIndexManager.java:1023-1026`), the columns the builder reads for an index that depends on no column (`CollatedViewIndexBuilder.java:91-113`).
> `@BeforeClass` turns read thresholds off (`test/conf/cassandra.yaml:63-69` enables them). `ObjectSizes.measureDeep` (optional) is not done. One stdout line per
> measurement, in `build/test/logs/**/TEST-org.apache.cassandra.index.IndexingPageSizeProbeTest*.log`:
> `ITP CASE case=<T1|T2|T2b|T3> k1=<bool> rep=<1..3> prop=<value read back> sstables=<n> meanPartitionSize=<d> meanCells=<n> regularCols=<n> ps=<n> pages=<n> totalRows=<n>
> staticRows=<n> maxRows=<n> maxBytes=<n> maxRowDataSize=<n> ms=<n> rowsPerPage=[..] bytesPerPage=[..]`. "Max bytes per page" in B2f/B2g is `maxBytes` (Σ `Row.dataSize()`).

**B2e. Procedure.**
1. For T1, with K1=false: read the statistics and `ps`, run `indexPartition` with `ps`, and record the pages, max rows per page and max bytes per page.
2. For T1, with K1=true: same as step 1.
3. For T2 and T2b, with K1=false: same as step 1.
4. For T3: record `getMeanPartitionSize()` and `ps`.
5. Print everything with `logger.info`/`System.out`, and assert nothing beyond completion, so a refutation still prints.
6. Delete the test file from the local clone afterwards.

> **Amendment B2e (2026-10-26, stage-4 audit, before any run-1 reading).** Runner: `source ~/Library/Caches/stage4/env.sh; stage4-runtime-verification/harness/indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous/unit-run.sh`. One `@Test` per table (`t1`: T1 with K1=false then
> K1=true on the same data; `t2`; `t2b`; `t3`), each on a fresh CQLTester table with autocompaction disabled. "Repeat each case 3 times" (B2h) = steps 1–4 are each
> measured 3 times on the same data (statistics, `ps`, a full `indexPartition`), with the property set before each repeat and cleared after the case.
> Raw files: `ant.log`, `TEST.log`, `TEST.xml`, `itp.txt`, `summary.txt`, `commands.log` under `$W/logs/<stem>/unit/`.

**B2f. Predictions.**

| Case | `ps` | Rows per page | Max bytes per page |
|---|---|---|---|
| T1, K1=false | in [420, 620] (bucket error ±20%) | `ps` (last page fewer) | in [0.8, 1.25] × 33,554,432, i.e. 27–42 MB |
| T1, K1=true | exactly 10000 | one page of 2000 | ≈ 131 MB (≥ 3× the K1=false maximum) |
| T2 | exactly 10000 | one page of 2000 | ≈ 120 MB |
| T2b | in [450, 700] | `ps` | 27–42 MB |
| T3 | 10000 | — | — (`meanPartitionSize = 0.0`) |

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| T1 K1=false max page bytes ≈ 32 MiB (within ±25%) and K1=true is one 131 MB page | Claim (i) confirmed. The byte target governs the page operand. |
| T1 K1=false `ps` = 10000, or max page ≈ 131 MB | Claim wrong. The target does not bound the page. |
| T1 K1=false page bytes far below 32 MiB (for example < 10 MB) | The estimate is badly off. Report the statistics and the `:1168` arithmetic. Claim (i) is not confirmed in its "≈" form. |
| T2 `ps` = 10000 while T2b `ps` ≈ 500 | `:1164` bypass confirmed (claim ii). |
| T2 `ps` ≈ T2b `ps` | Bypass not present. Claim (ii) wrong for `:1164`. |
| T3 `ps` = 10000 with `meanPartitionSize` = 0 | `:1156` fallback reached only with no sstables, as traced. |
| T1 K1=true `ps` ≠ 10000 | The property was not read. Fix the setup and rerun (not confirmed). |

> **Amendment B2g (2026-10-26, stage-4 audit, before any run-1 reading).** Verdict words and Effect (stage-4 README). All three repeats of a case must give the same `ps` and pages, or the tier is
> **Not confirmed**. "Max bytes" is `maxBytes` (B2d). Mapping:
> - **Confirmed — caps only on some paths (bypass):** row 1 (T1 K1=false `maxBytes` in [0.8, 1.25] × 33,554,432 with `ps` in B2f's band, and K1=true one page of 2000 rows,
>   ≥ 3× the K1=false maximum) **and** row 4 (T2 `ps` = 10000, one page of 2000 rows, while T2b `ps` is in [450, 700]) **and** row 6 (T3) all hold. Direct disallow evidence: every
>   non-last page of T1 K1=false and T2b holds exactly `ps` rows.
> - **Refuted — does not cap:** row 2.
> - **Refuted in part (ii) — caps:** row 5 (T2 `ps` ≈ T2b `ps`) with row 1 holding.
> - **Not confirmed:** row 3; or any reading outside B2f's bands that is not row 2 or row 5 (Effect then follows the readings: `caps only on some paths (bypass)` if T1 K1=false
>   `maxBytes` ≤ T1 K1=true `maxBytes` / 3 and T2 `ps` = 10000, otherwise `undetermined`).
> - **Invalid run:** row 7 (property not read), the test did not complete, or a case printed no line.

**B2h. Controls.**
- K1=true on the same data is the positive control. It shows that the same workload moves the operand where no byte cap binds.
- T2b differs from T2 only in one tiny regular column.
- Byte sums use `Row.dataSize()`, which is independent of GC.
- Repeat each case 3 times. `ps` must be identical across repeats.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node with JDK 11. Build in the local clone: `ant clean jar` in `/local/c509`.
- Data, commitlog, hints and saved caches go under `/local/c509-node/` on a local disk with at least 5 GB free.
- `conf/cassandra.yaml`: point `data_file_directories`, `commitlog_directory`, `hints_directory` and `saved_caches_directory` at that directory. Keep the defaults otherwise.
- Heap: `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`.
- GC log: add to `conf/jvm11-server.options` the line `-Xlog:gc*:file=/local/c509-node/gc.log:time,uptime`.
- Start with `bin/cassandra -p /local/c509-node/pid`.

> **Amendment B3a (2026-10-26, stage-4 audit, before any run-1 reading).** On this machine: one node from `$W/cassandra-run38` (already built by `build-test`; no `ant clean jar`, and no `ant` while the
> node runs). Node files under `$W/node-itp/` on the internal SSD (`conf/` = a copy of the clone's `conf/`, used through `CASSANDRA_CONF`; `data`, `commitlog`, `hints`,
> `saved_caches`, `cdc_raw`, `logs` through `CASSANDRA_LOG_DIR`; 131 GiB free). The yaml changes only the five directories (`yaml-diff.txt`). The gc line is
> `-Xlog:gc*:file=$W/node-itp/gc.log:time,uptime` in that copy's `jvm11-server.options`. `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` as filed; under G1 (the 5.0 default,
> `jvm11-server.options`) `HEAP_NEWSIZE` is ignored with a warning (`cassandra-env.sh:125-128`), recorded, not changed. No `setsid`/`-p` pid file: the node is started as a
> tracked background process `bin/cassandra -f > node.out 2>&1 < /dev/null` and stopped with `nodetool drain` + `kill <pid>`. `JVM_EXTRA_OPTS` carries the Byteman agent
> (`-javaagent:build/lib/jars/byteman-4.0.20.jar=script:stage4-runtime-verification/harness/indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous/itp.btm`, no listener) and, for K1=true, the property. The rules are type-checked with Byteman's
> `TestScript` before every start (`btm-check.txt`).

**B3b. Knobs.**
- K1: `-Dcassandra.force_default_indexing_page_size=true` (appended through `JVM_EXTRA_OPTS`, needs a restart) versus unset.
- K2: table B (one regular column) versus table A (no regular column, so `:1164` applies).

**B3c. Workload.**
1. `CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':1}`.
2. Table A: `CREATE TABLE ks.a (pk int, ck text, s int, PRIMARY KEY (pk, ck))` with `s` declared `static`.
3. Table B: the same plus `v int`.
4. `nodetool disableautocompaction ks`.
5. Generate a CSV on local disk with python3: 12000 lines `0,<ck>,1[,1]`, where `ck` = 5-digit row number followed by 39995 `'a'` (about 40 KB, compressible on disk). Load each table with `cqlsh -e "COPY ks.b (pk,ck,s,v) FROM '/local/c509-node/b.csv' WITH MAXBATCHSIZE=1 AND CHUNKSIZE=50"`, and similarly for `ks.a`.
6. `nodetool flush ks`.
7. `CREATE INDEX a_s ON ks.a (s); CREATE INDEX b_s ON ks.b (s);`. The index on the static column writes one entry per partition, so the index memtable stays negligible.
8. Measure with `nodetool rebuild_index ks b b_s` and `nodetool rebuild_index ks a a_s`, each run 3 times.

Arithmetic: rows are about 40 KB. In table B the computed page is about 33.5 MB / 40 KB ≈ 820 rows, about 33 MB live. In table A, or with K1=true, the page is `min(10000, 12000)` = 10000 rows, ≈ 400 MB live. Each rebuild takes seconds to a minute.

> **Amendment B3c (2026-10-26, stage-4 audit, before any run-1 reading).** `cqlsh` runs with `HOME=$W/home` (no writes in `$HOME`). The CSVs are written to `$W/node-itp/{a,b}.csv` and deleted after the
> load. After step 6 the script reads `count(*)` of each table and `nodetool tablestats ks`. `CREATE INDEX` starts an initial build of each index; the script waits until both
> have finished (two `ITP END` lines, B3d) before step 8.

> **Runbook-defect fix D1 (2026-10-26, stage 4, after run-1 cluster attempt 1; B3f and B3g unchanged).** `nodetool disableautocompaction ks` (step 4) does not survive the
> B3e step-5 restart. In attempt 1 the restarted node began compacting the four sstables of `ks.a` and of `ks.b` 0 s after `Startup complete` and died with
> `OutOfMemoryError: Java heap space` (G1 humongous allocations) 3 s later, before the first K1=true rebuild, so step 5 could not run. Fix: step 4 also sets the
> table option, which is stored in the schema and survives a restart: `ALTER TABLE ks.a WITH compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'}`
> and the same for `ks.b` (`CompactionParams.java:123-125`, `CompactionStrategyManager.java:187,271-273`). The script reads it back after the restart
> (`system_schema.tables`). The cluster tier restarts from its beginning.

**B3d. Observables and instruments.**
- Operand: `nodetool setlogginglevel org.apache.cassandra.index.SecondaryIndexManager TRACE`, then grep `logs/debug.log`/`system.log` for `Calculated page size` (`SecondaryIndexManager.java:1172`). It is logged only on the computed path, so its absence means a fallback.
- Actual heap: post-GC heap occupancy from `gc.log` (`Pause Young ... X M->Y M(2048M)`, take Y). Baseline is the max Y over 60 s idle before the rebuild. Peak is the max Y during the rebuild, with the window taken from `nodetool compactionstats` showing "Secondary index build".
- Also sample `jcmd $(cat pid) GC.heap_info` every 0.5 s.
- Not directly observable: which objects make up the live set (optionally take `jcmd <pid> GC.class_histogram` mid-build and look at the `HeapByteBuffer`/`byte[]` totals).

> **Amendment B3d (2026-10-26, stage-4 audit, before any run-1 reading).** Instruments made exact, and the heap observable redefined so it can see the page.
> - **Why:** a young pause's after-value Y includes dead objects promoted earlier (it is not live heap); an idle window can hold no GC at all, so "max Y over 60 s idle" can be
>   empty; and a full page lives only from its materialization (`SecondaryIndexManager.java:1066`) to the end of the indexing loop (`:1090-1132`), so a 0.5 s sampler or the
>   young pauses can miss it.
> - **Primary heap observable:** four observe-only Byteman rules (`itp.btm`; no return value or control flow is changed). `ITP START`: at `CollatedViewIndexBuilder.build()`
>   entry, `System.gc()` (a full collection under G1; no `ExplicitGCInvokesConcurrent`/`DisableExplicitGC` in `jvm*-server.options`) and the heap's used bytes
>   (`Runtime.totalMemory() − freeMemory()`, printed as `heapUsedPostGC`) = the build's **baseline**. (The `MemoryMXBean` value is printed too, as `mxUsed`, but not used: under
>   G1 it counts eden by whole 16 MiB regions and read one region high in cluster shakedown 1.) Each `System.gc()` also leaves a `Pause Full (System.gc()) X->Y M` line in
>   gc.log; the count of those lines (1 + pages) and their after-values cross-check each build's delta (within 8 MiB). `ITP PAGE`: in `indexPartition(DecoratedKey, Set, int, RegularAndStaticColumns)` after `ImmutableBTreePartition.create` returns, `System.gc()` and the used bytes,
>   with the page's `rowCount()` and the page size passed in. `ITP PS`: the value `calculateIndexingPageSize()` returns on every path, with the property, the statistics, the regular
>   column count and the sstable count. `ITP END`: at `build()` exit.
>   "Peak − baseline post-GC heap" in B3f/B3g = max over the build's `ITP PAGE` `heapUsedPostGC` − its `ITP START` `heapUsedPostGC` (MB = 10^6 B).
> - **Window:** a build = the blocking `nodetool rebuild_index` call (`ColumnFamilyStore.java:936-942` → `rebuildIndexesBlocking`), marked with epoch ms and the byte offsets
>   of `node.out` and `logs/debug.log` before and after (`MARK` lines in `summary.txt`); this replaces the `compactionstats` window.
> - **Logged page size:** after `setlogginglevel ... TRACE` the `Calculated page size` line reaches `debug.log` (its appender has no threshold, `conf/logback.xml:41-62`);
>   the level is set again after the restart. A line is attributed to a build by the debug.log offsets.
> - **Secondary, as filed:** gc.log `Pause` after-values in the window (max Y, all pauses) and `jcmd <pid> GC.heap_info` every 0.5 s (`heapinfo-<phase>-<table>-<rep>.txt`)
>   are recorded but not used for B3g. Class histograms are not taken.
> - **Disallow evidence:** in each build every non-last `ITP PAGE` has `rows` = the returned `ps`, and the rows sum to 12,000.

**B3e. Procedure.**
1. Start the node with K1 unset and load the data (steps 1-7 of B3c).
2. Record the idle baseline.
3. Rebuild table B 3 times, then table A 3 times, recording the peaks and log lines.
4. `nodetool drain`, then kill the process using the pid file.
5. Restart with K1=true and repeat the table B rebuild 3 times.
6. Stop the node.

> **Amendment B3e (2026-10-26, stage-4 audit, before any run-1 reading).** One script: `source ~/Library/Caches/stage4/env.sh; stage4-runtime-verification/harness/indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous/cluster-run.sh` (B3c steps 1–8, then B3e steps 2–6;
> step 2's idle baseline is the `ITP START` reading of each build, B3d). Between builds 5 s. Raw files under `$W/logs/<stem>/cluster/`: `summary.txt`, `commands.log`, `node.out`,
> `itp.txt`, `system-<phase>.log`, `debug-k1true.log` (debug.log is appended across the restart, so it holds both phases), `gc-<phase>.log`, `heapinfo-*.txt`, `copy-*.log`,
> `tablestats-before-index.txt`, `btm-check.txt`.

**B3f. Predictions.**

| Run | Logged page size | Peak − baseline post-GC heap |
|---|---|---|
| Table B, K1 unset | 680–980 | ≤ 100 MB |
| Table B, K1=true | no log line | ≥ 350 MB |
| Table A, K1 unset | no log line (`:1164` fallback) | ≥ 350 MB |

The B-forced and A deltas should be at least 3× the B-default delta.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| B-default delta ≤ 100 MB, while B-forced and A deltas are ≥ 350 MB | Claim confirmed. The 32 MiB target governs real heap, and `:1164` bypasses it. |
| B-default delta ≈ B-forced delta (both large) | Claim wrong. The page size does not govern heap, or something else dominates. |
| All deltas small (< 100 MB) | Positive control did not move. Not confirmed. Check that the rebuild actually read the rows (compactionstats bytes), and the young-gen sizing. |
| A delta small while B-forced is large | `:1164` bypass refuted in practice. |
| OOM in a forced or A run | Strong support for (ii). Record it and lower the row count if a measurable figure is needed. |

> **Amendment B3g (2026-10-26, stage-4 audit, before any run-1 reading).** Verdict words and Effect. All three repeats of a run must agree with the row, or the tier is **Not confirmed**.
> "Delta" is B3d's peak − baseline. Mapping:
> - **Confirmed — caps only on some paths (bypass):** row 1, with B3f's logged page sizes (table B K1 unset: a line with 680–980 in each build; table B K1=true and table A: no line,
>   and `ITP PS` = 10000), B-forced and A deltas ≥ 3× the B-default delta, and the disallow evidence of B3d.
> - **Refuted — does not cap:** row 2.
> - **Refuted in part (ii) — caps:** row 4 (A delta small while B-forced is large).
> - **Not confirmed — undetermined:** row 3, or a row-1 pattern whose logged page size is outside 680–980 or whose deltas miss B3f's numbers (Effect then `caps only on some paths
>   (bypass)` if the B-default delta is ≤ 1/3 of both other deltas, otherwise `undetermined`).
> - Row 5 (OOM) is recorded with the run's other readings; it supports (ii) but the tier is **Not confirmed** unless the remaining rows give row 1.
> - **Invalid run:** the property read back in `ITP PS` does not match the phase, a `rebuild_index` fails, a table holds fewer than 12,000 rows, or no `ITP PAGE` line appears.

**B3h. Controls.**
- Autocompaction is disabled, so no concurrent compaction.
- The index memtable is negligible (static-column index).
- K1 on the same data and node is the positive control.
- A and B differ only by one int column.
- Run 3 repeats. A heap that remains large after a full GC (`jcmd <pid> GC.run`) after the rebuild would indicate a leak rather than the page.

**B4. Risks and cleanup.**
- Disk use is about 1.2 GB of CSV plus compressed sstables (well under 1 GB) under `/local/c509-node`. Never use the shared clone or shared storage.
- After the runs: `nodetool drain`, kill the pid, check `pgrep -f CassandraDaemon` returns nothing, and `rm -rf /local/c509-node /local/c509`.
- Unit tier: delete the probe test. CQLTester data lives under the clone's `build/test`, which is removed together with the clone.

> **Amendment B4 (2026-10-26, stage-4 audit, before any run-1 reading).** Paths on this machine: `$W/node-itp` (removed by the script, also on abnormal exit) and the clone `$W/cassandra-run38` (kept; its `git status` must be clean).
> Full logs stay under `$W/logs/indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous/`. The check for a leftover node is
> `ps -eo command | grep '[C]assandraDaemon'`.

## C. Sources read

```
src/java/org/apache/cassandra/index/SecondaryIndexManager.java
src/java/org/apache/cassandra/index/internal/CollatedViewIndexBuilder.java
src/java/org/apache/cassandra/index/internal/CassandraIndex.java
src/java/org/apache/cassandra/index/Index.java
src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java
src/java/org/apache/cassandra/index/sasi/SASIIndex.java
src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
src/java/org/apache/cassandra/db/ColumnFamilyStore.java
src/java/org/apache/cassandra/io/sstable/metadata/MetadataCollector.java
src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java
src/java/org/apache/cassandra/utils/EstimatedHistogram.java
src/java/org/apache/cassandra/service/pager/AbstractQueryPager.java
src/java/org/apache/cassandra/tools/nodetool/RebuildIndex.java
test/unit/org/apache/cassandra/index/CustomIndexTest.java
test/unit/org/apache/cassandra/index/StubIndex.java
build.xml
conf/cassandra.yaml
```

## D. Stage-4 feedback

**2026-10-26, stage 4 run 1 on the advisor's machine** ([results](../../stage4-runtime-verification/results/indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous.md); uncommitted, no commit asked for).
Frozen at sha256 `cae4285e…08b5` after ten audit amendments (unit tier). The runbook-defect fix D1 (B3c step 4) gives `e20ec09a…cae9` (cluster tier).
- **Unit: Confirmed — caps only on some paths (bypass)** (B2g rows 1, 4, 6). T1 `ps` = 563, pages of ≤ 36.9 MB (1.10 × 32 MiB). The same data with K1 = true gives one page of
  2,000 rows, 131.2 MB. T2 (zero regular columns) gives `ps` = 10000, one page of 120.0 MB; T2b gives `ps` = 595, ≤ 35.7 MB. T3 gives `ps` = 10000 with `meanPartitionSize` = 0.
- **Cluster: Confirmed — caps only on some paths (bypass)** (B3g row 1). Table B logged `Calculated page size 857`; the post-GC live heap of a page was 35.2–35.8 MB. With K1 = true,
  or for table A (`:1164`), there was no log line, pages of 10,000 rows, and 397.6–409.1 MB.
- **Defect D1:** `nodetool disableautocompaction` does not survive B3e's restart. The restarted node compacted the 480 MB partitions and died of OOM. Fixed with the table option
  `'enabled':'false'`.
- **For stage 3:** the testsome heap is 1 GiB (`build.xml:1153`), not 4G. The filed post-young-GC heap observable cannot see a page that lives only through the indexing
  loop; the run used the live heap after a forced full GC at build start and at each page.
- The estimate stands as filed.
