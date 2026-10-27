<!-- file: cases/rows-per-partition-hasEnoughLiveData-rowLimit--autonomous.md -->
# rows_per_partition (row-cache rows per partition) — verification solution  <!-- file: cases/rows-per-partition-hasEnoughLiveData-rowLimit--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/filter/DataLimits.java:417` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 via Claude Code (Agent SDK), 2026-10-27 |
| Estimate | `positive` for the real constraint behind this site (table option `caching.rows_per_partition`, bounded globally by `row_cache_size`): the number of live rows stored per cached partition follows it, so off-heap row-cache usage is bounded. The entry line itself is not a cap. |
| Ground | `—` (the entry line is a read-side shortcut, see A3; the cap is enforced where the cache is populated and by OHC capacity) |

## A. Constraint trace

**A1. The constraint.**
- Entry operand: `rowLimit` of `CQLLimits` (`DataLimits.java:349`), the CQL `LIMIT` / page size of the query. This is not a resource constraint; it is only compared with the cached partition's row count at `DataLimits.java:417` (`if (cached.rowCount() < rowLimit) return false;`).
- The resource constraints on this path are:
  - **`caching = {'rows_per_partition': N|'ALL'|'NONE'}`**, a table option. Declared in `schema/CachingParams.java:61` (`rowsPerPartitionToCache`), parsed at `CachingParams.java:97-109`, `ALL` = `Integer.MAX_VALUE` (`:55`, `:143`; `cacheAllRows()` at `:81`), `NONE` = 0 (`cacheRows()` is `> 0`, `:76`). Unit: live rows per partition. Default `NONE`. Set by `CREATE/ALTER TABLE ... WITH caching = {...}`; no restart.
  - **`row_cache_size`** (`config/Config.java:474`, `LongMebibytesBound`, default `0MiB`, which disables the row cache; `isRowCacheEnabled` requires capacity > 0, `ColumnFamilyStore.java:3262`). Settable in cassandra.yaml (restart) and at runtime via `CacheService.setRowCacheCapacityInMB` (`CacheService.java:327`, JMX / `nodetool setcachecapacity`). Off-heap, applied as OHC capacity (`cache/OHCProvider.java:40`).

**A2. What it caps.** Off-heap memory (OHC) used by the row cache. `rows_per_partition` caps rows per cached partition; `row_cache_size` caps total bytes. The quantity compared in the check at line 417 is `CachedPartition.rowCount()` vs query `rowLimit`.

**A3. Mechanism.**
1. Read path: `SinglePartitionReadCommand.java:491` uses the row cache only if `cfs.isRowCacheEnabled()`.
2. On a miss, `SinglePartitionReadCommand.java:546-558` decides whether to populate: full partitions if `cacheAllRows()` (clustered tables) or any positive value (no clustering), otherwise only for head-of-partition filters.
3. Population (`:566-617`): a wrapping iterator stops once `rowsCounted < rowsToCache` fails, where `rowsToCache = caching.rowsPerPartitionToCache()` and only live rows increment `rowsCounted` (`:586`, `:594-598`). The result is built by `CachedBTreePartition.create` (`db/partitions/CachedBTreePartition.java:~82-115`) and stored by `rowCache.replace` (`:612`). This is where the per-partition cap is enforced.
4. On a hit, `ColumnFamilyStore.isFilterFullyCoveredBy` (`ColumnFamilyStore.java:1920-1941`) decides whether the cached data suffices: first `cachedLiveRows < rowsPerPartitionToCache` means the whole partition is cached; otherwise `limits.hasEnoughLiveData(...)` is called for head filters (`:1938`).
5. `CQLLimits.hasEnoughLiveData` (`DataLimits.java:407-431`): `rowsWithNonExpiringCells >= rowLimit` returns true (`:414`); `rowCount() < rowLimit` returns false (`:417`, the entry line); otherwise re-count with a `CQLCounter`. A false result sends the read to memtable/sstables; nothing is stored or evicted here. So line 417 only affects read latency/cache-hit rate, not memory.
6. Global bound: OHC is built with `capacity(rowCacheSizeMiB*1MiB)` and `throwOOME(true)` (`OHCProvider.java:40-43`); OHC evicts to stay within capacity.
- Overshoot/bypass: the cap counts live rows only, so tombstones, range-tombstone markers and expired rows read before the N-th live row are also cached (`CachedBTreePartition.create` caches whatever the wrapper iterator yielded). The static row is extra. Row width (large cells) is not bounded by the row count, only by `row_cache_size`. OHC overhead per entry (hash table, key) may make real native usage slightly exceed the `weightedSize` figure (to be measured).

**A4. Other consumers.** Key cache and counter cache (heap/Caffeine, `CacheService.java:121,174`), memtables (off-heap if configured), chunk cache, OS page cache, bloom filters/index summaries; all outside `row_cache_size`. Row-cache sentinels (`RowCacheSentinel`) are tiny.

**A5. Evidence beyond the source.** Cassandra docs, "Caching" and `CREATE TABLE` `caching` option: https://cassandra.apache.org/doc/5.0/cassandra/developing/cql/ddl.html#caching-options ; OHC project: https://github.com/snazy/ohc . Source comments at `SinglePartitionReadCommand.java:546-558` and `ColumnFamilyStore.java:1922-1930`.

## B. Verification solution

**B1. Claim under test.** (i) Line 417 is a read-side shortcut: changing the query `LIMIT` changes cache-served vs disk-served reads but never the number of rows held in the row cache. (ii) The number of live rows held per cached partition is at most `rows_per_partition` (plus non-live rows read before the cutoff), and total row-cache bytes never exceed `row_cache_size`.

### B2. Unit tier

*(B2a-B2h rewritten at the 2026-10-27 audit, before any reading; see section D. The claim, the knob and the per-row meaning of each reading are unchanged.)*

**B2a. Environment and build.** JDK 11, Ant. Make a working tree with `stage4-runtime-verification/copy-source.sh <dir>` (never build in the repository's `cassandra/cassandra-5.0.9/`), `ant build-test` there, then copy the test class `RowCachePartitionLimitTest.java` (from `harness/<stem>/`) into `test/unit/org/apache/cassandra/db/` of that tree only and run `ant testsome -Dtest.name=org.apache.cassandra.db.RowCachePartitionLimitTest`. The unit yaml already enables the row cache (`test/conf/cassandra.yaml:44-45`: OHC, `row_cache_size: 16MiB`), so the test sets nothing (a later `setRowCacheSizeInMiB` would not create a cache after `CacheService` initialised).

**B2b. Knobs.** Table option `rows_per_partition` N in {5, 50, ALL}, plus `NONE` (the default) as the negative control; query `LIMIT` L in {1, 4, 5, 6, 49, 50, 51, 1000}. One partition of 200 live rows on a clustered table `(pk int, ck int, v text, PRIMARY KEY (pk, ck))`, v = 100 characters. Set with `CREATE TABLE ... WITH caching = {'keys':'ALL','rows_per_partition':'N'}`. Variants (all N=5): `TTL` (the 200 rows inserted `USING TTL 3600`, so no cell is non-expiring); `TOMB` (row deletions of ck 0-49 flushed before the first read); `NOCK` (table without clustering columns, N=5, one row). `ROWS` (200) may be lowered by the env var `STAGE4_ROWS` for shakedowns only.

**B2c. Workload.** Insert the rows into pk=1, flush. First read `SELECT * FROM t WHERE pk=1 LIMIT 1` (miss; populates the cache). Then, for each L in order, one read `SELECT * FROM t WHERE pk=1 LIMIT L`.

**B2d. Observables and instruments.** (1) The cached entry of pk=1 from `CacheService.instance.rowCache.get(RowCacheKey)`: `rowCount()`, `cachedLiveRows()`, `rowsWithNonExpiringCells()`, `CachedPartition.cacheSerializer.serializedSize`; (2) for each L, called directly on that entry: `DataLimits.cqlLimits(L).hasEnoughLiveData(cached, now, false, true)` and `cfs.isFilterFullyCoveredBy(new ClusteringIndexSliceFilter(Slices.ALL, false), DataLimits.cqlLimits(L), cached, now, strict)`; (3) `rowCache.size()` and `rowCache.weightedSize()` (the OHC `memUsed`); (4) the deltas of `cfs.metric.rowCacheHit / rowCacheMiss / rowCacheHitOutOfRange` caused by the read with LIMIT L. Native bytes cannot be seen in the unit tier; the serialized size and `weightedSize` are the proxies (gap named).

**B2e. Procedure.** For each arm: create the table, record the table's `rowsPerPartitionToCache`, insert, flush, `invalidateRowCacheForCf`, read with LIMIT 1, record the entry shape, `size()`, `weightedSize()` and the counters ("populate"). Then for each L: record the counters, read with LIMIT L, record the counter deltas and the two direct calls. After the last L record the entry shape, `size()` and `weightedSize()` again ("after"). First trigger: arm N=5 must leave a real entry (not a sentinel) after the populating read; if not, stop.

**B2f. Predictions (before any run).** Written as exact values.
- **N=5.** Populate leaves `rowCount` = `cachedLiveRows` = `rowsWithNonExpiringCells` = 5. `hasEnoughLiveData(L)` is true for L in {1, 4, 5} (line 414) and false for L in {6, 49, 50, 51, 1000} (line 417, since 5 < L). `isFilterFullyCoveredBy` equals `hasEnoughLiveData` for every L (the first test in it is `5 < 5`, false). The read with LIMIT L adds one `rowCacheHit` for L <= 5 and one `rowCacheHitOutOfRange` for L >= 6, never a miss.
- **N=50.** Same with 50 rows and the threshold 50: true for L in {1, 4, 5, 6, 49, 50}; false for {51, 1000}; hit for L <= 50, out of range for L >= 51.
- **N=ALL.** `rowCount` = `cachedLiveRows` = 200. `isFilterFullyCoveredBy` is true for every L (first test `200 < 2147483647`) and every read is a hit. `hasEnoughLiveData` is true for L <= 200 and false for L = 1000 (direct call only).
- **For all three:** the entry shape (`rowCount`, `cachedLiveRows`, `serializedSize`) and `size()` and `weightedSize()` after the L reads equal those after the populate read (the LIMIT changed neither); `serializedSize(5) < serializedSize(50) < serializedSize(ALL)` and `serializedSize(50)/serializedSize(5)` within 7..10.5; `weightedSize` strictly increases with N (5 < 50 < ALL).
- **NONE.** No entry; hit = miss = outOfRange = 0 after all reads; `isRowCacheEnabled` false.
- **TTL (N=5).** `rowCount` 5, `cachedLiveRows` 5, `rowsWithNonExpiringCells` 0; `hasEnoughLiveData(L)` true for L in {1, 5} (via the re-count branch) and false for L = 6.
- **TOMB (N=5).** `cachedLiveRows` 5, `rowCount` 55 (the 50 deleted rows before the live ones are stored), `rowsWithNonExpiringCells` 5; `hasEnoughLiveData` true for L in {1, 5}, false for L = 6 (re-count finds 5 live rows).
- **NOCK (N=5).** `cachedLiveRows` = `rowCount` = 1.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| entry shape, `size()` and `weightedSize()` after the L reads equal those after the populate read, for every N; `rowCount` == N (5, 50) and 200 for ALL | claim (i) and the per-partition cap (ii) hold in the unit tier; line 417 only decides hit or out of range |
| `rowCount` > N by many live rows (without tombstones) | cap does not bind; claim (ii) refuted |
| `rowCount` > N only by the number of dead rows (TOMB: 55) | known overshoot: non-live rows are not capped (record the magnitude) |
| the entry, `size()` or `weightedSize()` differs after the L reads | LIMIT influences memory; claim (i) refuted |
| `weightedSize` and `serializedSize` flat across N (5, 50, ALL) | N does not move usage: control failed, Not confirmed |
| the hit / out-of-range pattern or the direct-call results differ from B2f for any L | the read-side trace is wrong (record which L); claim (i) as worded is not supported by this tier: Not confirmed (no matching row) unless the entry and sizes are still unchanged, in which case the memory claim holds and the pattern defect is recorded |
| no entry after the populate read of N=5 | setup error; not a refutation |

**B2h. Controls.** `NONE`: cache stays empty. N=5 vs N=50 vs N=ALL is the control that N moves usage while L does not. The `NOCK` variant: with no clustering columns any positive N stores the whole (one-row) partition (`SinglePartitionReadCommand.java:547-549`).

### B3. Cluster tier

*(B3a-B3h rewritten at the 2026-10-27 audit, before any reading; see section D.)*

**B3a. Environment and build.** One node on loopback address 127.0.5.1 (port slot 5: storage 7000, native 9042, JMX 7150), JDK 11, `ant jar` in a tree made with `copy-source.sh`; heap `MAX_HEAP_SIZE=2G`, `HEAP_NEWSIZE=512M`, `-XX:+AlwaysPreTouch`; data, commit log, hints and saved caches on a tmpfs (`/dev/shm/...`; the data is about 0.7 GB). cassandra.yaml: `row_cache_size: 256MiB`, `row_cache_save_period: 0s`, `row_cache_class_name: org.apache.cassandra.cache.OHCProvider`, `key_cache_size: 0MiB`, `counter_cache_size: 0MiB`, `memtable_allocation_type: heap_buffers`, `file_cache_size: 64MiB`. (256 MiB replaces the filed 64 MiB: at N=50 the 20,000 entries are about 156 MB, so 64 MiB would bind at N=50 and make "Size flat across LIMIT" untestable there.)

**B3b. Knobs.** `rows_per_partition` in {5, 50, ALL} and `NONE` (default, the control), one node lifetime each, cold row cache; query LIMIT 1 and 100 (and 1 again). Informational: a runtime `nodetool setcachecapacity 0 8 0` on the N=50 arm after its passes.

**B3c. Workload.** Table `ks.t (pk int, ck int, v text, PRIMARY KEY (pk, ck))`, 20,000 partitions x 200 rows x 100-character `v` (about 0.6 GB on disk, flushed). Reads are unprepared single-partition `SELECT * FROM ks.t WHERE pk=<pk> LIMIT <L>` over pk 0..19,999 in order. Passes: **P1** LIMIT 1 (populates), **P2** LIMIT 100, **P3** LIMIT 1. A tombstone arm `t5` uses `ks.t2` (2,000 partitions x 200 rows, ck 0-99 deleted as 100 row deletions per partition, flushed), N=5, pass P1 only. Each pass takes seconds to a few minutes; the run is a count of passes, not a duration.

**B3d. Observables and instruments.** JMX gauges `org.apache.cassandra.metrics:type=Cache,scope=RowCache,name=Size|Capacity|Entries` (polled every 5 s and read at each checkpoint) and the table counters `RowCacheHit|RowCacheMiss|RowCacheHitOutOfRange` of the table under test; `RssAnon` from `/proc/<pid>/status` (RSS minus heap is not used: the heap is pre-touched, and memtable and OHC memory are native `malloc`, which NMT does not see) at the checkpoints `baseline` (after 20 s idle, a warm-up of whole-partition reads on the table not under test, and 10 s), `pass1`, `pass2`, `pass3`; `nodetool info` row-cache line. The per-entry row count is not visible in the cluster; it is inferred from Size / Entries.

**B3e. Procedure.**
1. Load once: create `ks.t` and `ks.t2` with `rows_per_partition NONE`, load, delete in `ks.t2`, flush, drain; known-answer reads (pk=17: 200 rows in `ks.t`, 100 live rows in `ks.t2`).
2. For each arm: start a node on a clean row cache with the arm's yaml; `ALTER TABLE ks.<table> WITH caching = {'keys':'NONE','rows_per_partition':'<N>'}` and read it back from `system_schema.tables`; row cache of the other table off; `nodetool invalidaterowcache`; take `baseline`; run P1 and take `pass1` (**first trigger**: the cache holds entries, for NONE it holds none; otherwise stop); run P2, `pass2`; run P3, `pass3`; stop the node (`nodetool drain`, SIGTERM) and confirm no daemon is left.
3. On the N=50 arm only, after `pass3`: `nodetool setcachecapacity 0 8 0`, checkpoints at +5 s and +60 s, then one more LIMIT 1 pass (informational, not a B3f prediction).
4. Delete the node directory afterwards.

**B3f. Predictions (before any run).** Capacity = 268,435,456 B. e(N) = Size / Entries after P1, in bytes.
- Size <= Capacity at every poll of every arm (the gauge is the check's counter; the real-memory reading is the last bullet).
- **n5:** Entries = 20,000 after P1, e(5) between 600 and 1,200 B (about 5 rows x 150 B plus about 150 B of entry overhead), so Size between 12 and 24 MB.
- **n50:** Entries = 20,000 after P1 (no eviction: 20,000 x about 7.8 KB = about 156 MB, below 256 MiB); e(50)/e(5) within 7..10.5.
- **nall:** e(ALL)/e(50) within 3.3..4.1 (taken from a partially filled cache's average); Size after P1 at least 0.85 x Capacity and Entries between 5,000 and 12,000 (fewer than 20,000: the byte cap binds).
- **LIMIT does not move the cache (claim i), n5 and n50:** Size and Entries after P2 and after P3 are equal to those after P1 (exact equality; no eviction happens in these arms).
- **Line 417 fires (n5 and n50, exact):** counters from `baseline`: P1 miss +20,000; P2 `RowCacheHitOutOfRange` +20,000 and hit +0 (LIMIT 100 > N); P3 hit +20,000 (LIMIT 1 <= N).
- **NONE:** Entries 0, Size 0, hit = miss = outOfRange = 0 after P3.
- **t5:** Entries = 2,000; e(t5) > e(5) + 500 B (the 100 deleted rows before the live ones are stored).
- **Real memory (informational prediction, B3g row):** with `d(arm)` = `RssAnon` at `pass3` minus `baseline`, `d(arm)` minus `d(none)` <= 1.5 x Size(pass3) + 16 MiB for n5, n50 and nall.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Size <= Capacity at every poll; n5/n50 Size and Entries unchanged by P2 and P3; counters as in B3f (P2 out of range 20,000, P3 hit 20,000); e(N) rises with N (ratios in B3f) | claim (i) and (ii) hold at the cluster tier: the LIMIT decides hit or out of range only; N moves usage; the byte cap binds in nall |
| Size or Entries of n5 or n50 differs after P2 or P3 | LIMIT influences the cache; claim (i) refuted |
| Size > Capacity at any poll | the byte cap does not hold; claim (ii) refuted |
| e(N) flat across N | per-partition cap does not move usage (control failed): Not confirmed |
| `d(arm) - d(none)` > 1.5 x Capacity (= 384 MiB) for an arm | native memory far beyond the cache; claim (ii)'s real-memory part refuted for that arm |
| `d(arm) - d(none)` above the B3f bound but not above 1.5 x Capacity | memory outside the cache accompanying the reads; reported as an overshoot, the Size-based rows still decide |
| n5 or n50 counters differ from B3f but Size and Entries are unchanged | memory claim holds; the read-side trace needs correction (recorded); Not confirmed for the counter row |
| nall Size < 0.85 x Capacity, or t5 e(t5) <= e(5) + 500 B | cap-binding or overshoot prediction not met: recorded as unmatched; the other rows still decide |
| the first trigger fails (no entries after P1 where N > 0) | setup error; not a refutation |

**B3h. Controls.** `NONE` arm (cache empty, counters 0, `RssAnon` delta of the same passes: subtracted above); N=5/50/ALL are the controls that N moves usage while LIMIT does not; the tombstone arm `t5` measures the non-live overshoot; the informational `setcachecapacity 0 8 0` shows the capacity knob moving Size.

**B4. Risks and cleanup.** (amended 2026-10-27) Data about 0.7 GB on a tmpfs (`/dev/shm`) of the run node only; no shared storage and no files in the shared source tree (work trees are `copy-source.sh` copies); stop every Cassandra process of the run by PID and verify with `ps -eo pid,args | grep "[C]assandraDaemon"`; delete the node directory and the trees afterwards or list them as leftovers.

## C. Sources read

- ~/writeup-A/playbook-autonomous.md
- ~/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/filter/DataLimits.java
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java
- src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java
- src/java/org/apache/cassandra/schema/CachingParams.java
- src/java/org/apache/cassandra/db/partitions/CachedBTreePartition.java
- src/java/org/apache/cassandra/cache/OHCProvider.java
- src/java/org/apache/cassandra/service/CacheService.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/metrics/CacheMetrics.java

## D. Stage-4 feedback

**Stage-4 run 1, 2026-10-27 (pc12, port slot 5): both tiers Confirmed; effect on the constraint: caps. Outcome class: true positive.** Results: [`../../stage4-runtime-verification/results/rows-per-partition-hasEnoughLiveData-rowLimit--autonomous.md`](../../stage4-runtime-verification/results/rows-per-partition-hasEnoughLiveData-rowLimit--autonomous.md). No section of the traced path (A) was refuted; the only edits to this file are the audit amendments D1 below (made before run 1) and this field.

- **Claim (i), line 417 moves no memory:** unit: for N = 5, 50, ALL and eight LIMITs, `hasEnoughLiveData` and `isFilterFullyCoveredBy` are true exactly for L <= N (ALL: always covered), a covered read is a `rowCacheHit`, an uncovered one a `rowCacheHitOutOfRange` (never a miss), and the cached entry, its serialized size and the cache's `size()` / `weightedSize()` are identical before and after the reads. Cluster: Size and Entries are identical after the LIMIT 1, LIMIT 100 and LIMIT 1 passes (n5: 14,099,113 B, n50: 114,891,148 B, 20,000 entries each), and the out-of-range counter rises by exactly 20,000 at LIMIT 100 > N.
- **Claim (ii), per-partition and byte caps:** `rowCount` = N (5, 50), 200 for ALL; bytes per entry 705, 5,745, 22,545 B for N = 5, 50, ALL; Size peaked at 268,370,382 B under the 256 MiB capacity (268,435,456 B) with 11,904 of 20,000 entries in nall.
- **Overshoots as A3 says:** dead rows before the live ones are stored (TOMB: 5 live, 55 stored; cluster t5 entries 1,204 B larger than n5's); the `ALL` entry is the whole partition.
- **Not in the traced path, noted by the run:** (a) `RssAnon` rose 0.2 to 0.4 GB with the reads (net of the cache-off arm 355.6, 225.5, 198.3 MB for n5, n50, nall), mostly in the populating pass, and not tied to the cache bytes (cause not isolated); (b) after `nodetool setcachecapacity 0 8 0` the gauge `Capacity` read 8 MiB while Size stayed 114.9 MB (20,000 entries) for 60 s and across a hit-only pass: the runtime shrink of the OHC row cache does not release memory without new inserts (not retested with a put pass).
- **A3 wording:** add that a read with LIMIT above `rows_per_partition` is a `rowCacheHitOutOfRange` and never re-populates (`SinglePartitionReadCommand.java:537-539`).

### D1. Step-0 audit amendments (2026-10-27, stage-4 agent p75; made before any reading)

Applied to the text above; the claim B1, the knob and the meaning of each reading are unchanged. Reasons do not depend on any run.

1. **B2a** - dropped the `setRowCacheSizeInMiB(16)` instruction (a no-op after `CacheService` initialised; the unit yaml already enables OHC at 16 MiB, `test/conf/cassandra.yaml:44-45`); added the work-tree method (`copy-source.sh`).
2. **B2b/B2c/B2e** - the LIMIT list, the single populating read (LIMIT 1) and "one read per L, counters as deltas" made exact; the entry is read before and after the L reads so that claim (i) (the LIMIT does not change what is cached) is observed directly; the re-count branch of `hasEnoughLiveData` (`DataLimits.java:421-430`), unreachable on plain data, gets two variants (`TTL`: `rowsWithNonExpiringCells` = 0; `TOMB`: dead rows inflate `rowCount`); `NOCK` kept as in B2h. The first trigger is stated.
3. **B2f** - made exact for every N and L (the filed text covered N=5 only in words). Derived from `ColumnFamilyStore.isFilterFullyCoveredBy` (`:1931`: `cachedLiveRows < N` first, then the head-filter `hasEnoughLiveData`) and `getThroughCache` (`SinglePartitionReadCommand.java:528-539`: covered is a hit, otherwise `rowCacheHitOutOfRange` and a disk read with no cache write). The filed "ALL: line 417 is not called" is kept; it is checked through the covered flag for every L, not by observing the call.
4. **B2g** - rows added for "entry changes after the L reads", "N does not move usage", "pattern differs but memory unchanged" and the setup error, so each outcome has a row.
5. **B3a/B3b** - `row_cache_size` 256 MiB instead of 64 MiB: the filed arithmetic put N=50 at 20,000 x about 7.8 KB = about 156 MB, which would exceed 64 MiB and make a flat Size across LIMIT untestable there (the cache would churn). 64 MiB / 8 MiB runtime change kept only as the informational `setcachecapacity 0 8 0`. Data on a tmpfs, not "/local/node1" (the local disk is 63 GB shared with other cases).
6. **B3c/B3e** - passes made exact (P1 LIMIT 1, P2 LIMIT 100, P3 LIMIT 1); the filed "about 10 minutes per configuration" removed (the work is three passes of 20,000 reads); unprepared statements (a prepared SELECT keeps the table's old caching options after `ALTER TABLE`, seen in an earlier case); one node lifetime per N (glibc keeps freed native memory, so one arm's `RssAnon` would carry into the next); the tombstone phase gets its own table `ks.t2` (100 row deletions per partition).
7. **B3f** - numbers fixed: entry sizes, ratios, exact counters (the P2 out-of-range count of 20,000 is the direct evidence that line 417 fired), exact Size/Entries equality across passes for n5 and n50, the NONE and tombstone predictions, and the RSS rule.
8. **B3g** - the filed row "RSS delta far above Size (> 1.5x Capacity) -> refuted" is made decidable: RSS delta is `RssAnon` at `pass3` minus `baseline`, net of the NONE arm's delta (the same passes without a cache), compared with 1.5 x Capacity; the smaller overshoot is "reported, Size decides" (an earlier row-cache case saw `RssAnon` rise by several hundred MB in arms whose cache held far less, from the read path).
9. **B3h/B4** - controls restated as arms; `pgrep -fl` replaced by the `ps | grep '[C]assandraDaemon'` form; paths updated.
10. **Citations** - `CachingParams.java`: ALL = `Integer.MAX_VALUE` is at `:55` and `:143`, `:81` is `cacheAllRows()` (A1 corrected). All other citations in A1-A3 were checked against `cassandra-5.0.9` and hold (`DataLimits.java:349,407-431`; `ColumnFamilyStore.java:1920-1941,3259-3262`; `SinglePartitionReadCommand.java:491,546-558,575-598`; `CachedBTreePartition.java:86-115`; `OHCProvider.java:40-43`; `CacheService.java:327`; `Config.java:473-474`).

Recommendations left for stage 3 (not applied): the Estimate line says "`positive` for the real constraint behind this site" while the entry line (417) is not itself a cap; a note in A3 that a read with LIMIT above N is a `RowCacheHitOutOfRange` (and never re-populates) would help the next reader.
