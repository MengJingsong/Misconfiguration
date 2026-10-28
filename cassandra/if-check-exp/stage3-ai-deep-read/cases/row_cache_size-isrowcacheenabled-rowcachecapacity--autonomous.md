# row-cache-enabled gate (rows_per_partition > 0 and row cache capacity > 0) — verification solution  <!-- file: cases/row_cache_size-isrowcacheenabled-rowcachecapacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`ColumnFamilyStore.java:3262`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3262) (helper `ColumnFamilyStore.isRowCacheEnabled()`, defined at line 3259) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code agent, 2026-10-27 |
| Estimate | `positive`: the gate keeps the off-heap row cache empty unless both a per-table row quota is set and a nonzero cache capacity exists, and the capacity is the cache's size cap. |
| Ground | — |

**Type:** non-config (per-table/per-index option + hard-coded constant). The check is `caching.cacheRows() && rowCache.getCapacity() > 0`. The first operand is the per-table option `caching = {'rows_per_partition': N}`, tested as `rowsPerPartitionToCache > 0` (numeric literal 0). The second reads the yaml entry `row_cache_size` (via the runtime cache capacity) against the literal `0`. The constant rule applies: the literal `0` takes part in both comparisons, and the yaml entry is also read.

## A. Constraint trace

**A1. The constraint.** Two operands, both compared against the literal `0`.
(a) Per-table option `caching.rows_per_partition`, stored as `CachingParams.rowsPerPartitionToCache`, declared at [`CachingParams.java:61`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/CachingParams.java#L61); the test is `rowsPerPartitionToCache > 0` at [`CachingParams.java:76`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/CachingParams.java#L76). Unit: rows per partition (`NONE` = 0, `ALL` = `Integer.MAX_VALUE`). Default 0 when the option is absent (`CachingParams.java:97-99`). Set per table with CQL `CREATE/ALTER TABLE ... WITH caching = {'keys':..., 'rows_per_partition': '...'}`; no restart.
(b) Row cache capacity, from yaml `row_cache_size`, declared at [`Config.java:474`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L474) (default `0MiB`; `conf/cassandra.yaml:564` also `0MiB`). Unit: MiB in config, bytes in the cache. At startup it selects the provider: `NopCacheProvider` if size is 0, otherwise `row_cache_class_name` (default `OHCProvider`) ([`CacheService.java:146-147`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/CacheService.java#L146)). It can be changed at runtime through JMX `CacheService.setRowCacheCapacityInMB` (`CacheService.java:327-332`, `nodetool setcachecapacity`). Runtime read: `InstrumentingCache.getCapacity()` returns `map.capacity()` (`InstrumentingCache.java:77-80`).
Literal: `0` in `> 0` (both comparisons); no named constant declaration.

**A2. What it caps.** Off-heap memory (OHC, `OHCProvider`) used by the row cache. The helper compares (a) rows per partition to cache and (b) the cache's byte capacity against 0. It does not itself bound bytes. It decides whether the row cache is used for a table at all. The size bound is the capacity value enforced by OHC eviction.

**A3. Mechanism.** [`ColumnFamilyStore.java:3262`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3262): `retval = caching.cacheRows() && rowCache.getCapacity() > 0`; line 3263 asserts the table is not an index. True: reads go through `getThroughCache` and may populate the cache. False: reads skip the cache. A path that bypasses the gate: none found for populating. Callers read (list): `SinglePartitionReadCommand.java:491` (read path, picks `getThroughCache` vs `queryMemtableAndDisk`) and `:509` (assert); `ColumnFamilyStore.java:2430, 2493` (invalidate/clear row cache early-return); `CassandraStreamReceiver.java:263, 269` (invalidate cached rows after streaming); `SSTableImporter.java:233`; `CacheService.java:409` (skip tables without row cache when loading saved cache). Once enabled, the number of rows cached per partition is limited by `rowsToCache = rowsPerPartitionToCache()` (`SinglePartitionReadCommand.java:565-587`) and total size by OHC capacity. Overshoot: runtime capacity change to a nonzero value from a provider chosen as `Nop` at startup (size 0 at boot) flips this gate true while the cache is a Nop cache, so nothing is stored, with capacity possibly reported as nonzero. Unconfirmed in code; see B3 control.

**A4. Other consumers.** Key cache (`isKeyCacheEnabled`, `ColumnFamilyStore.java:3273`) and counter cache have separate caps; memtables and OHC off-heap allocations from other users compete for the same direct memory.

**A5. Evidence beyond the source.** none. (Source comments in `getThroughCache`, `SinglePartitionReadCommand.java:549-557`, explain partial caching.)

## B. Verification solution

**B1. Claim under test.** Row-cache memory is zero (no off-heap row-cache allocation) whenever `row_cache_size` is 0 or a table has `rows_per_partition = NONE`, and once both are positive the row cache's off-heap size grows with reads of that table and stops at about `row_cache_size`; the per-table row count never exceeds `rows_per_partition`.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. In a private copy of the tag: `ant jar`, plus a small JUnit test (e.g. `test/unit/org/apache/cassandra/db/RowCacheGateTest.java`, in the private copy) using `SchemaLoader` like `RowCacheTest`. JVM options: defaults of `ant test`, `-Dcassandra.config=` pointing to a test yaml with `row_cache_size: 16MiB`.
**B2b. Knobs.** Table option `rows_per_partition` in {`NONE`, `1`, `ALL`}; `CacheService.instance.setRowCacheCapacityInMB` in {0, 16}. Four-cell cross of (option>0) x (capacity>0) shows each operand matters.
**B2c. Workload.** Create a table with 100 rows in one partition, 1000 partitions; read each partition's head with `SELECT ... LIMIT 1`.
**B2d. Observables and instruments.** Return value of `cfs.isRowCacheEnabled()`; `CacheService.instance.rowCache.size()` and `weightedSize()`; `cfs.metric.rowCacheHit/Miss`; `getCapacity()`.
**B2e. Procedure.** For each of the four cells: set capacity, `ALTER TABLE` caching, assert `isRowCacheEnabled()`, run the reads twice, record `rowCache.size()` and hit/miss counters.
**B2f. Predictions.** Enabled only when option>0 and capacity>0. In the other three cells `rowCache.size() == 0` and miss/hit counters stay 0. In the enabled cell with `rows_per_partition=1`, each cached entry holds at most 1 row; the second pass shows hits.
**B2g. Readings.** Enabled only for the (>0, >0) cell: claim confirmed. Entries or size nonzero in a disabled cell: claim refuted. Cached rows per partition above N: refuted. Enabled cell with zero hits and zero entries: not confirmed (workload did not reach the cache).
**B2h. Controls.** Repeat the (>0, >0) cell with the same workload to show the cache does fill; table not an index.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from a local copy of the tag; heap 2 GiB (`MAX_HEAP_SIZE=2G`). Data dir on local disk under a private directory.
**B3b. Knobs.** yaml `row_cache_size` in {`0MiB`, `64MiB`}; table `rows_per_partition` in {`NONE`, `ALL`}. Runtime check via `nodetool setcachecapacity 0 64 0` (key, row, counter) switching from 0 to 64 without restart.
**B3c. Workload.** `cassandra-stress` or CQL script: 20000 partitions of about 10 KiB each (about 200 MB total, exceeds 64 MiB capacity), then read all partitions twice, plus 3 passes over a hot set of 2000 partitions.
**B3d. Observables and instruments.** `nodetool info` (row cache entries, size, capacity, hit rate); JMX `org.apache.cassandra.metrics:type=Cache,scope=RowCache,name=Size/Entries/Capacity`; `pmap`/`/proc/<pid>/smaps` for off-heap growth of the process (sampled every 5 s); NMT not needed because OHC memory is native.
**B3e. Procedure.** Start the node per arm, create the schema, load data, restart once so reads hit sstables, run the reads, sample metrics before, during, after; stop the node and confirm no process remains (`pgrep -f CassandraDaemon`).
**B3f. Predictions.** Arm A (`row_cache_size 0`, option ALL): Size/Entries 0, RSS flat. Arm B (`64MiB`, `NONE`): same. Arm C (`64MiB`, `ALL`): Size rises with reads and plateaus at or below 64 MiB (67108864 bytes); hit rate on the hot set above the cold pass; RSS rises by roughly the cache size. Arm D: start at 0MiB, run `nodetool setcachecapacity 0 64 0`, repeat reads; prediction: either cache stays empty (Nop provider) or fills, whichever is observed settles the A3 overshoot question.
**B3g. Readings.** Arms A and B empty, C plateaus at the cap: claim confirmed. Any nonzero size in A or B, or size above the cap in C by more than a few percent: refuted. C empty: not confirmed (reads not through the cache; check the CQL option applied).
**B3h. Controls.** Same data and reads across arms; arm C is the positive control that the workload fills the cache; page cache and key cache left unchanged.

**B4. Risks and cleanup.** Disk: about 200 MB of data in a private directory; delete it after the run. Stop the node, check no `CassandraDaemon` is left, remove the private source copy and logs. No change to shared source or storage.

## C. Sources read

- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (3250-3275)
- src/java/org/apache/cassandra/schema/CachingParams.java
- src/java/org/apache/cassandra/service/CacheService.java (140-170, 320-335)
- src/java/org/apache/cassandra/cache/InstrumentingCache.java (74-80)
- src/java/org/apache/cassandra/cache/OHCProvider.java (62-65)
- src/java/org/apache/cassandra/config/Config.java (472-474)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (3913-3924)
- conf/cassandra.yaml (553-564)
- src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java (485-600)

## D. Stage-4 feedback

`none yet`
