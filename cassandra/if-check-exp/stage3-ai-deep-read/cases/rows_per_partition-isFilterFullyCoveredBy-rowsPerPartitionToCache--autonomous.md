<!-- file: cases/rows_per_partition-isFilterFullyCoveredBy-rowsPerPartitionToCache--autonomous.md -->
# caching `rows_per_partition` (CachingParams.rowsPerPartitionToCache) — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/ColumnFamilyStore.java:1931` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code agent, 2026-10-26 (design only, nothing built or run) |
| Estimate | `positive` with caveats. The comparison at line 1931 is only a coverage test. The real cap is applied where the entry is built (`SinglePartitionReadCommand.java:586`, `CacheService.java:411-424`), and it bounds live rows per cached partition. Total row-cache memory is bounded separately by `row_cache_size`. |
| Ground | — (the caveats are listed in A3: tombstones/non-live rows, `ALL`, tables without clustering columns, the on-heap copy of an entry) |

## A. Constraint trace

**A1. The constraint.** `rows_per_partition` is a table-level caching option (CQL `WITH caching = {'keys':'ALL','rows_per_partition':'N'|'ALL'|'NONE'}`), held as `CachingParams.rowsPerPartitionToCache`.
- Kind: schema/table parameter (per-table runtime metadata).
- Declared: field `schema/CachingParams.java:61`, constructor `:63`, accessor `:84`, parsing `rowsPerPartitionFromString` `:140` [citation corrected 2026-10-26 from `:~125`] (`ALL` -> `Integer.MAX_VALUE`, `NONE` -> 0, numeric -> `Integer.parseInt`). The default is `DEFAULT_ROWS_PER_PARTITION_TO_CACHE = 0` (`:51`, corrected 2026-10-26 from `:55`), so row caching is off per table by default.
- Unit: live rows per partition.
- Set with `CREATE/ALTER TABLE ... WITH caching = {...}`. It is a schema change and needs no restart.
- It only takes effect if the global row cache is on. `row_cache_size` defaults to 0MiB (`config/Config.java:474`, `conf/cassandra.yaml:564`). `ColumnFamilyStore.isRowCacheEnabled()` is `cacheRows() && rowCache.getCapacity() > 0` (`ColumnFamilyStore.java:3259-3265`). `cacheRows()` is `rowsPerPartitionToCache > 0` (`CachingParams.java:74-77`).
- The global byte cap, `row_cache_size` (MiB, `Config.java:474`), is a separate constraint. It sets the OHC capacity (`cache/OHCProvider.java:40`) and can be changed through JMX, `DatabaseDescriptor.java:3918-3924`. It is not the target here.

**A2. What it caps.** It caps the number of live rows kept in the row cache for each partition. The row cache is off-heap OHC memory. The unit-level operand is `CachedPartition.cachedLiveRows()`, compared with `rowsPerPartitionToCache` at line 1931 (the quantity the code compares). The resource affected is the off-heap serialized size of a row-cache entry (`serializedSize`, `CachedBTreePartition.java:199-211`). While an entry is built, and again when it is read back, it also sits on the Java heap as a `CachedBTreePartition`.

**A3. Mechanism.**
1. Read path. `SinglePartitionReadCommand.getThroughCache` (`:506`) looks up the `RowCacheKey` (`:515`). On a hit it calls `cfs.isFilterFullyCoveredBy(...)` (`:528`). That function (`ColumnFamilyStore.java:1916-1943`) at `:1931` returns true when `cachedLiveRows < rowsPerPartitionToCache`. The logic is: if the cached entry holds fewer live rows than the cap, the entry must be the whole partition, since it was not truncated. If so, the entry is served as complete.
2. Otherwise it needs a head filter with enough live data (`:1938`), or `filter.isFullyCoveredBy(cached)` (`:1942`). If none holds, the query ignores the cache (`rowCacheHitOutOfRange`, `:535`).
3. The line-1931 check therefore does not limit anything. It relies on the cap having been applied at population time. When `cachedLiveRows == rowsPerPartitionToCache` the entry may be truncated and the cheap "whole partition" shortcut is not taken. When the cap is lowered by ALTER after caching, an old entry with more rows than the new cap still passes the second-stage test (it is not trimmed until evicted or invalidated).
4. Population (the actual cap). On a miss the code decides `cacheFullPartitions` (`:547-549`): with clustering columns only `ALL` (`cacheAllRows()`), otherwise any positive value (a partition with no clustering has one row). It caches only when `cacheFullPartitions || filter.isHeadFilter()` (`:558`). It takes a sentinel (`:561`), reads the full partition (`:569`) and wraps the iterator. `hasNext()` returns `rowsCounted < rowsToCache && iter.hasNext()` (`:586`), and `rowsCounted` increments only for rows with live data (`:594-598`). `CachedBTreePartition.create` (`:604`) consumes that wrapper, so at most `rowsToCache` live rows are stored. The entry replaces the sentinel (`:608`).
5. Saved-cache reload: `CacheService.RowCacheSerializer.deserialize` (`:411-424`) rebuilds with `DataLimits.cqlLimits(rowsToCache)`, the same cap.
6. Overshoots/bypasses:
   - Only live rows are counted (`:594-598`). Non-live rows (tombstones, range tombstone markers, rows of expired data) read before the cap is reached are stored but not counted, so entries can exceed N rows when the head of the partition is full of tombstones.
   - `rows_per_partition = ALL` (`Integer.MAX_VALUE`) caches the whole partition. Its size is bounded only by `row_cache_size` and by what OHC accepts (`throwOOME(true)`, `OHCProvider.java:43`), and the whole partition is materialised on heap first.
   - A partition without clustering columns is one row. A positive N caches that whole row regardless of cell size.
   - A single row can be arbitrarily wide in cells or bytes. The cap is in rows, not bytes.
   - On the non-cached branch the remaining iterator is concatenated lazily (`:~625`), so the query still reads past N rows from disk, but those are not stored.
   - Hits deserialize the entry into a heap `CachedBTreePartition` (`OHCProvider.java:ValueSerializer.deserialize`).

**A4. Other consumers.** Off-heap OHC capacity is shared by all tables' row-cache entries and by sentinels (`RowCacheSentinel`, small). Other off-heap users: key cache, counter cache, chunk cache, memtables (if off-heap), bloom filters, index summaries. Heap users: memtables, the transient on-heap `CachedBTreePartition` for each miss and each hit, and read buffers.

**A5. Evidence beyond the source.** None used. Cassandra docs for `caching` table options (cassandra.apache.org, "Table options") were not consulted for this design. CASSANDRA-3862 is referenced in the code comment at `SinglePartitionReadCommand.java:~512` (sentinel handling).

## B. Verification solution

**B1. Claim under test.** For a table with clustering columns, the number of live rows stored in a row-cache entry never exceeds `rows_per_partition` (N), so the entry's off-heap size grows with N until the partition has fewer than N live rows, and total row-cache bytes stay under `row_cache_size`. The cap is on live rows only: a partition whose head is dead rows can exceed N stored rows, and `ALL` and no-clustering tables store the whole partition.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tag to local disk (`rsync -a cassandra-5.0.9/ /local/work/c509/`) and never build in the shared tree. `ant jar` then `ant build-test`. The test is a JUnit class added to the copy under `test/unit/org/apache/cassandra/db/RowCacheRowsPerPartitionTest.java`, extending `CQLTester` (needs `row_cache_size` > 0). **[Amended 2026-10-26, step-0 audit: `test/conf/cassandra.yaml:44-45` already sets `row_cache_class_name: OHCProvider` and `row_cache_size: 16MiB`, so `CacheService.rowCache` is an OHC cache of 16 MiB when the test starts; the test needs no row-cache setup (a 1000-row entry of about 110 KB fits). `DatabaseDescriptor.setRowCacheSizeInMiB` after `CacheService` has initialised would not create a cache.]** Run with `ant testsome -Dtest.name=RowCacheRowsPerPartitionTest`. JVM options: the default test options, `-Xmx1g`.

**B2b. Knobs.** `rows_per_partition` N in {1, 10, 100, ALL} via `ALTER TABLE ... WITH caching`, on a table `(pk int, ck int, v text, PRIMARY KEY (pk, ck))`. Also a second table with no clustering columns for the caveat. The partition holds 1000 live rows, so N=1, 10 and 100 are below the partition size; ALL and a control with N=2000 are above it.

**B2c. Workload.** Insert 1000 rows into one partition (`v` = 100 bytes), then run `SELECT * FROM t WHERE pk=1 LIMIT 5` (head filter, miss, populates), then again (hit). Arithmetic: 1000 > N for N in {1,10,100}, so the cap binds; for N=2000, `cachedLiveRows`=1000 < 2000, so line 1931 returns true. Variant: delete the first 50 rows with row deletions (range tombstone or row tombstones) before the read with N=10.

**B2d. Observables and instruments.** `CacheService.instance.rowCache.get(new RowCacheKey(metadata, key))` returns the `CachedPartition`; read `cachedLiveRows()`, `rowCount()`, and `CachedPartition.cacheSerializer.serializedSize(p)`. Also `cfs.isFilterFullyCoveredBy(...)` called directly with a head filter, and table metrics `RowCacheHit`, `RowCacheMiss`, `RowCacheHitOutOfRange`. Heap is not measured in this tier. Entry bytes are computed from the serializer, not the OHC allocator.

**B2e. Procedure.**
1. Create keyspace/table with `caching = {'keys':'ALL','rows_per_partition':'<N>'}`.
2. Insert 1000 rows into pk=1; flush.
3. Run the LIMIT 5 query once; read the cache entry; record `cachedLiveRows`, `rowCount`, serialized size.
4. Run it again; record hit metrics. Call `isFilterFullyCoveredBy` with a full-slice filter and with a head filter LIMIT 5.
5. Repeat for each N; drop the table between runs (`cfs.invalidateRowCache()` is also enough).
6. Do the tombstone variant and the no-clustering variant.

**B2f. Predictions.**
- N=1: `cachedLiveRows`=1; N=10: 10; N=100: 100; N=ALL: 1000; N=2000: 1000. Serialized size is about proportional to rows (roughly 10x from N=10 to N=100, within about 20% for header overhead).
- Full-slice filter: `isFilterFullyCoveredBy` is false for N in {1,10,100} (line 1931 false, `cachedLiveRows == N`, not fully covered), true for N=ALL and N=2000 (1000 < N).
- LIMIT 5 head filter: true for N >= 5 (enough live data), false for N=1.
- Tombstone variant (N=10, first 50 rows deleted with row deletions, `DELETE FROM t WHERE pk=1 AND ck=<i>`, flushed): `cachedLiveRows`=10 and `rowCount`=60 (50 dead rows read before the live ones, plus 10 live). **[Amended 2026-10-26, step-0 audit: the original text said a single range tombstone gives 10 rows plus 2 markers. Range-tombstone markers are not rows: `AbstractBTreePartition.build` (`:312-320`) puts them into `deletionInfo`, so `rowCount` counts rows only. A range-tombstone variant (`DELETE ... WHERE pk=1 AND ck < 50`) is an extra arm that predicts `cachedLiveRows`=10, `rowCount`=10 and a non-empty range-tombstone list in `deletionInfo()`.]**
- No-clustering table, N=1: the single row is cached whole; size grows with cell size, not N.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `cachedLiveRows` = N for N below 1000, 1000 for ALL/2000 | Claim holds: population honours the cap |
| `cachedLiveRows` > N for any N below 1000 | Claim wrong: the cap does not bind |
| size grows about linearly with N | per-entry bytes follow N |
| size flat across N while `cachedLiveRows` rises | rows counted but bytes not following (investigate the serializer) |
| `rowCount` > N only in tombstone variant | known overshoot (live rows only counted) |
| `isFilterFullyCoveredBy` true for the full slice at N below 1000 | the line-1931 logic is wrong or the entry was not truncated |
| entry is absent after the first read | cache was not enabled (`row_cache_size`=0, N=0) or the query was not a head filter: setup error, not a refutation |

**B2h. Controls.** N=2000 (above the partition size) shows the entry is not truncated and line 1931 returns true. A table with `rows_per_partition='NONE'` must give no entry. Same data and query across all N, and a fresh JVM state (`invalidateRowCache`) per run.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, build the copy with `ant jar`. **[Amended 2026-10-26, step-0 audit: node data, commit log, hints and saved caches go on tmpfs `/dev/shm` (the local disk has 29 GB free and is shared with other cases); loopback address 127.0.2.1, JMX 7120, native 9042. The JVM is started with `-XX:+AlwaysPreTouch` as well as `-Xms2G -Xmx2G`, so the heap is resident before the baseline and an `RssAnon` difference measures off-heap memory. Original text: "200 GB free".]** `cassandra.yaml` changes: `row_cache_size: 256MiB`, `row_cache_save_period: 0s`, `commitlog_directory`, `data_file_directories` and `hints_directory` on the local disk. JVM options: `-Xms2G -Xmx2G`, G1 (the default). The row cache class stays `OHCProvider`. Client: `cqlsh` and `cassandra-stress` from the built copy.

**B3b. Knobs.** Table `ks.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))`. Vary `rows_per_partition` N in {1, 10, 100, ALL}, set with `ALTER TABLE` between runs (no restart, but call `nodetool invalidaterowcache` after each). Fixed: `row_cache_size` 256MiB (kept far above the expected usage to isolate N). Row payload `v` = 1 KiB. Dataset: 20,000 partitions x 1,000 rows (about 20 GB raw, so ALL would need about 20 GB and be limited by `row_cache_size`).
Arithmetic: per partition N=10 -> about 10 KiB, 20,000 partitions -> about 200 MB (close to but under 256 MiB, hence reduce to 10,000 partitions touched, about 100 MB); N=100 -> about 100 KiB per partition, 256 MiB / 100 KiB = about 2,500 partitions, so the byte cap binds; N=1 -> about 20 MB.
**[Amended 2026-10-26, step-0 audit: dataset is 10,000 partitions (pk 0-9999) x 300 rows (ck 0-299) x 1 KiB `v` = 3.1 GB raw, compression off, on tmpfs. The 20 GB original would take far longer to load than the question needs and fills the shared tmpfs; 300 rows is three times the largest finite N (100) and the only thing the experiment needs from the partition size. Consequence: a `rows_per_partition='ALL'` entry is a whole partition of 300 rows, about 315 KiB, not 1 MiB (B3f amended). A second table `ks.t2` (same schema) holds 2,000 partitions x 300 rows with `DELETE FROM ks.t2 WHERE pk=? AND ck=?` for ck 0-199 of every partition, for the tombstone phase.]**

**B3c. Workload.** Load with `cassandra-stress` user profile or a script. Then read the head of each partition: `SELECT * FROM ks.t WHERE pk=? LIMIT 5`, over 10,000 distinct partitions, twice (pass 1 populates, pass 2 hits). Duration about 10 minutes per N. Second phase: the same reads on a table whose first 200 rows per partition are deleted (tombstone variant, N=10). **[Amended 2026-10-26, step-0 audit: no fixed duration; each pass reads pk 0-9999 once in order, with 128 requests in flight from 4 client processes. The tombstone phase reads `ks.t2` pk 0-1999 in one pass (pass 1 only) at N=10. Each N is its own node lifetime (B3e).]**

**B3d. Observables and instruments.** JMX/`nodetool`: `nodetool info` (row cache entries, size, hit rate), `nodetool tablestats ks.t`, `nodetool proxyhistograms`. Metrics `org.apache.cassandra.metrics:type=Cache,scope=RowCache,name=Size|Entries|Capacity|Hits|Requests`, and the table's `RowCacheHit/Miss/HitOutOfRange`. Process memory: `ps -o rss`, `jcmd <pid> GC.heap_info`, `jcmd <pid> VM.native_memory summary` (needs `-XX:NativeMemoryTracking=summary`; note OHC memory is `Unsafe`-allocated, so NMT does not see it, RSS delta and the `Cache` `Size` metric are used instead). Sample every 10 s. Cannot be observed directly: per-entry bytes (derived as `Size/Entries`).

**B3e. Procedure.**
1. Build, set the yaml, start one node, check `nodetool info` shows row cache capacity 256 MiB.
2. Create the table, load the data, `nodetool flush`.
3. For N in {1, 10, 100, ALL}: `ALTER TABLE ks.t WITH caching = {'keys':'ALL','rows_per_partition':'<N>'}`; `nodetool invalidaterowcache`; record baseline RSS and cache Size; run pass 1 and pass 2; record Size, Entries, hits, RSS, heap used after each pass. **[Amended 2026-10-26, step-0 audit: each N runs in its own node lifetime (stop the node, start it again with a cold JVM and cache, then the ALTER), because glibc keeps memory the cache freed and `RssAnon` would carry the previous N into the next one (seen in the `row_cache_size` case, 2026-10-25). The data stays on tmpfs between lifetimes. Table-level hit counters (`RowCacheHit`, `RowCacheHitOutOfRange`, `RowCacheMiss`) are read over JMX (`org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=<counter>`) after each pass.]**
4. Tombstone phase for N=10.
5. Positive control (below).
6. Shut down the node, delete the data directories.

**B3f. Predictions.** **[Amended 2026-10-26, step-0 audit, before any reading: numbers recomputed for the amended dataset (300 rows per partition, 1 KiB `v`, B3b) and tolerances fixed; the original text is kept in git history. Let `e(N)` = cache `Size` / `Entries` after pass 1, in bytes, and `r` = 1.05 KiB (1 KiB value plus about 16 B of row encoding).]**
- Bytes per entry follow N: `0.75 <= e(N) / (N x r) <= 1.4` for N = 1, 10 and 100 (the per-entry fixed part, about 0.2 KiB for the key, OHC header and partition header, is the reason for a ratio above 1 at N=1). Expected `e` is about 1.2 KiB (N=1), about 10.6 KiB (N=10), about 105 KiB (N=100). N=ALL stores whole partitions: `e(ALL)` between 250 KiB and 400 KiB (300 rows x r = 315 KiB), which is far above `e(100)` (ratio 2.4 to 3.8).
- Total: `Size` after pass 1 is about 12 MB for N=1 (10,000 entries), about 106 MB for N=10 (10,000 entries). For N=100 and N=ALL the byte cap binds: `Size <= 256 MiB` (268,435,456 B), `Entries` below 10,000 (about 2,500 for N=100, at most about 800 for N=ALL) and evictions occur (`Entries` less than the 10,000 partitions read).
- Resident memory: `RssAnon` after pass 1 minus `RssAnon` at the arm's baseline (heap pre-touched) equals `Size` within 20% or 16 MiB, whichever is larger (the 16 MiB allows for direct buffers and metaspace moving during the pass).
- Hits: N=10 pass 2 has `RowCacheHit` about 100% of the 10,000 reads (at least 95%) and no `RowCacheHitOutOfRange`; N=1 has no hit in either pass and `RowCacheHitOutOfRange` about 10,000 in pass 2 (5 live rows wanted, 1 cached). No hit-rate claim for N=100 and N=ALL (the cache is smaller than the sequential scan).
- Tombstone phase (`ks.t2`, N=10, one pass over 2,000 partitions): `e` is at least 2 KiB above the live-row estimate `10 x r` + fixed part (210 rows are stored for 10 live ones, 200 of them dead), and exceeds `e(10)` measured on `ks.t`.
- Negative control (`rows_per_partition='NONE'`): `Entries` = 0 and `Size` = 0 after both passes, and `RowCacheMiss`, `RowCacheHit` stay 0.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| bytes/entry about proportional to N below the byte cap; Size <= 256 MiB | Claim holds |
| bytes/entry independent of N | Claim wrong: the rows cap does not shape usage |
| Size exceeds `row_cache_size` | the byte cap is not binding (a different constraint is broken) |
| N=ALL entries about whole partitions (about 315 KiB, amended 2026-10-26 from 1 MiB) | expected overshoot of the per-partition cap |
| tombstone phase bytes/entry above N x row size | known overshoot, live-only counting |
| `RssAnon` delta above Size by more than 20% and 16 MiB | memory outside the cache (transient copies, allocator): report as overshoot |
| Cache `Size` and RSS both flat across N while the positive control moves | (for a negative claim, if this occurs) cap not followed |
| Size flat but control also flat, or limit never reached | not confirmed; the setup did not exercise the cap |

**B3h. Controls.** Positive control: the same workload with `row_cache_size` at 32 MiB for N=100. Size must stop at or below 32 MiB (33,554,432 B) with `Entries` of about 300 or fewer and evictions, showing a cap that is known to bind moves the same readings. **[Amended 2026-10-26, step-0 audit: set in the yaml of its own node lifetime (arm `c32`) instead of lowering it by JMX on a running node, for the allocator reason given in B3e step 3.]** Negative control: `rows_per_partition='NONE'` gives Entries=0 and no RSS growth. Same data, same node, same queries for each N, `invalidaterowcache` between runs, no other tables read.

**B4. Risks and cleanup.** Disk: about 20 GB of data plus commit log on a local disk of known size, not on shared storage. Memory: the node uses 2 GiB heap plus up to 256 MiB off-heap; the N=ALL phase is the heaviest (whole 1 MiB partitions materialised on heap). Leftover processes: stop the Cassandra JVM and the stress client (`nodetool drain`, then kill the pid), check with `pgrep -f CassandraDaemon`. Cleanup: delete the data, commitlog, hints, saved_caches directories, remove the copied tree and the added test class. Unit tier: the CQLTester writes to a temp directory under the copy; delete it.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (1890-1969, 2430-2500, 3259-3265)
- src/java/org/apache/cassandra/schema/CachingParams.java
- src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java (500-640)
- src/java/org/apache/cassandra/db/PartitionRangeReadCommand.java (405-430)
- src/java/org/apache/cassandra/service/CacheService.java (100-175, 395-430)
- src/java/org/apache/cassandra/db/partitions/CachedBTreePartition.java (75-215)
- src/java/org/apache/cassandra/cache/OHCProvider.java
- src/java/org/apache/cassandra/config/Config.java (grep, 472-477), DatabaseDescriptor.java (grep)
- conf/cassandra.yaml (grep, lines 553-579)

## D. Stage-4 feedback

**Step-0 design audit amendments, 2026-10-26 (stage 4, tag `rp`; made before any reading; the text they change is marked `[Amended 2026-10-26 ...]` above):**
1. B2a: no row-cache setup needed in the unit test (`test/conf/cassandra.yaml:44-45`).
2. B2f: range-tombstone markers are not rows (`AbstractBTreePartition.java:312-320`); the row-deletion variant predicts `rowCount`=60, a range-tombstone arm predicts `rowCount`=10.
3. B3a/B3b/B3c: data on tmpfs, 10,000 partitions x 300 rows (not 20,000 x 1,000), second table `ks.t2` for the tombstone phase, heap pre-touched.
4. B3e: one node lifetime per N (allocator keeps freed memory).
5. B3f: recomputed for the amended dataset, tolerances fixed (ratio 0.75-1.4 of N x 1.05 KiB; `RssAnon` within 20% or 16 MiB; hit-rate claims limited to N=1 and N=10); B3g: two rows updated to match.
6. B3h: the positive control is its own arm with `row_cache_size` 32 MiB.
7. Citations corrected: `CachingParams.java:51` and `:140`.

**Stage-4 feedback (2026-10-26, run 1 only, results file `stage4-runtime-verification/results/rows_per_partition-isFilterFullyCoveredBy-rowsPerPartitionToCache--autonomous.md`):** unit tier **Confirmed**, cluster tier **Confirmed**; effect **caps** (soft: live rows only). Outcome class: true positive (estimate positive, effect caps). Nothing in A or B was refuted; the section A caveats were all observed.
- Unit (1000-row partition): `cachedLiveRows` = 1, 10, 100, 1000, 1000 for N = 1, 10, 100, ALL, 2000; serialized size 157, 1147, 11047, 110811 B; `isFilterFullyCoveredBy` false at `cachedLiveRows` == N for the full slice, true for ALL and 2000; row-deletion variant stored 60 rows for 10 live; a range tombstone adds no row (it sits in `deletionInfo`); `NONE` leaves no entry.
- Cluster (10,000 partitions x 300 rows x 1 KiB, 256 MiB): bytes/entry 1182, 10,515, 103,844 B for N = 1, 10, 100 (0.97 to 1.10 of N x 1.05 KiB); N=100 and ALL fill the cache (265.8 MB of 268.4 MB; 2,560 and 768 entries); ALL entries are 304 KiB; the 32 MiB control stops at 26.6 MB (256 entries).
- Open point: `RssAnon` rose 0.3 to 0.7 GB in the n10, n100 and c32 arms, far more than the cache Size (cause not isolated; read buffers kept by the allocator are the likely one).
- Finding for stage 3 / upstream (instrument check, not a run-1 reading): a prepared `SELECT` keeps the table's `rows_per_partition` from the time it was prepared (seen after a node restart, probably through the persisted prepared statements; not isolated), so after `ALTER TABLE ... caching` the row cache kept populating with the old N until the statement was re-prepared; unprepared statements follow the new value at once. Not checked against JIRA.
- Citation corrections made at the audit: `CachingParams.java:51`, `:140`. The case file is unchanged since the audit apart from this field.
