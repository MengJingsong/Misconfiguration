# denylist_max_keys_total — verification solution  <!-- file: cases/denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`PartitionDenylist.java:484`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/PartitionDenylist.java#L484) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5[1m]`), Claude Code CLI, 2026-10-26 (Band D triage, advisor-run) |
| Estimate | `positive`, scoped: a full `load()` (node startup or JMX `loadPartitionDenylist`) keeps at most `denylist_max_keys_total` denylisted keys in the on-heap cache, so heap held by the cache follows the knob. The cap does not hold after a single table is refreshed: the timer reload, a cache-miss load and a key add/remove all reload that table with only the per-table limit (`PartitionDenylist.java:194,205,388-391,551`), and the class javadoc says so (`:74-82`). Steady-state usage can therefore climb back to `tables x denylist_max_keys_per_table`. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `denylist_max_keys_total`. A configuration entry, declared at
[`Config.java:780`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L780) as
`public volatile int denylist_max_keys_total = 10000;`. The javadoc at `:776-779` says it exists "to keep things from growing unbounded".
Unit: a count of partition keys, not bytes. The default is the literal 10000. Ways to set it:
- the yaml key `denylist_max_keys_total` (it is commented out in `conf/cassandra.yaml:1462`);
- JMX `StorageProxyMBean.setDenylistMaxKeysTotal(int)` ([`StorageProxyMBean.java:83`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxyMBean.java#L83), [`StorageProxy.java:3116-3119`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L3116-L3119)), which goes to `DatabaseDescriptor.setDenylistMaxKeysTotal`. That setter rejects values `<= 0` ([`DatabaseDescriptor.java:4825-4830`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4825-L4830)).

A JMX change needs no restart, but it only takes effect at the next full `load()`.
The sibling knob `denylist_max_keys_per_table` (default 1000) is declared at [`Config.java:774`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L774).
Everything is gated by `partition_denylist_enabled` (default false, [`Config.java:759`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L759)).


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Heap. The capped object is the Caffeine `LoadingCache<TableId, DenylistEntry>` at
`PartitionDenylist.java:92`. Each `DenylistEntry` holds an `ImmutableSet<ByteBuffer>` of raw
partition keys and an `ImmutableSortedSet<Token>` (`:95-111`). The check compares
`getDenylistMaxKeysTotal() - totalProcessed`, where `totalProcessed` is the running sum of
`keys.size()` over the tables loaded so far (`:477, :484, :499`). Keys are `blob` clustering values in
`system_distributed.partition_denylist` (`SystemDistributedKeyspace.java:175-183`). Each can be up to
about 64 KiB, so the cache is memory-significant only when keys are large. For example, 10000 keys of 60 KiB is about 600 MiB. With ordinary keys of tens of bytes it is under 1 MiB.

**A3. Mechanism.**
1. [`StorageService.java:1349`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L1349) calls `StorageProxy.initialLoadPartitionDenylist()`. That reaches `PartitionDenylist.initialLoad()` (`:132-164`), which calls `load()` (`:219-234`). JMX `loadPartitionDenylist` reaches `load()` directly ([`StorageProxy.java:3068-3071`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L3068-L3071)).
2. `load()` calls `getDenylistForAllTablesFromCQL()` (`:464-524`). That function runs `SELECT DISTINCT ks_name, table_name` (`:469-473`) and iterates over the tables.
3. For each table, the check at `:484` runs:
   - If the total budget is used up, it logs an error and stores an empty `DenylistEntry` (`:486-492`).
   - Otherwise it computes `allowedTableRecords = min(per_table, total - totalProcessed)` (`:496`) and calls `getDenylistForTableFromCQL(tid, allowedTableRecords)` (`:396-450`). That function runs `SELECT ... LIMIT allowed+1` (`:403-408`) and keeps at most `allowed` keys (`:436-445`). Then `totalProcessed += keys.size()` (`:499`).
4. A new cache is built and filled with the result, then swapped in (`:224-232`). The old cache becomes garbage.

Paths that bypass the total cap (each one uses only the per-table limit, via `:388-391`):
- (a) The `refreshAfterWrite(denylist_refresh)` async reload (`:183-212`, reload at `:203-211`). It fires on the first access to an entry after the refresh interval (default 600 s, [`Config.java:767`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L767)). Access happens through `isKeyPermitted` (`:333-349`) on every read or write of a table, and through `getDeniedKeysInRangeCount`.
- (b) The `CacheLoader.load` for a table that is absent from the loaded map (`:189-198`).
- (c) `addKeyToDenylist` / `removeKeyFromDenylist` → `refreshTableDenylist` (`:250-299, :541-553`).

After any of these, a table that got 0 or a partial budget at load time can hold up to `per_table` keys.
The query result itself (up to `allowed+1` rows, unpaged: [`QueryProcessor.java:377-392`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L377-L392),
[`QueryOptions.java:62-65`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryOptions.java#L62-L65)) is transient and bounded by the same limit.

**A4. Other consumers.** Other heap users that are not under this knob:
- the `system_distributed` memtable holding freshly inserted denylist rows;
- transient read buffers during the load query;
- the old cache, until it is collected.

The chunk cache is off-heap. Disk use of `system_distributed.partition_denylist` is not capped at all. Only the loaded count is capped, and inserts beyond the limit are accepted (`conf/cassandra.yaml:1454-1456`).

**A5. Evidence beyond the source.**
- `test/unit/org/apache/cassandra/service/PartitionDenylistTest.java`: `testShrinkAndGrow` at `:353` and `testTableLimitRespected` at `:405ff`. The latter shows table3 gets only 2 keys when total is 12 and per-table is 5.
- `NEWS.txt:462-463`.
- `doc/modules/cassandra/pages/managing/operating/denylisting_partitions.adoc`.
- CASSANDRA-12106 (partition denylisting): https://issues.apache.org/jira/browse/CASSANDRA-12106

## B. Verification solution

**B1. Claim under test.**
- Right after a full `load()`, the number of denylisted keys in the cache equals `min(denylist_max_keys_total, sum over tables of min(per_table, rows))`. Heap retained by the cache grows linearly with that count, times the key size.
- Secondary (bypass) claim: once each table entry has been refreshed after `denylist_refresh`, the count rises to `sum over tables of min(per_table, rows)`, whatever the total is.

### B2. Unit tier

**B2a. Environment and build.**
1. Clone to local disk: `git clone --branch cassandra-5.0.9 --depth 1 /Users/yangwang/cassandra-src /tmp/c509-dl` (on Linux, use a local-disk path such as `/local/$USER/c509-dl`).
2. Build with JDK 11 and Ant: `cd /tmp/c509-dl && ant -Duse.jdk11=true build build-test`.
3. Add the test source `test/unit/org/apache/cassandra/schema/DenylistTotalCapProbeTest.java` in the scratch clone only.
4. JVM options: the test defaults from `build.xml` (`-Xmx` is unchanged and not relevant to the counts).

**Amendment 2026-10-26 (step-0 audit) — B2a, this host.** Run clone `$W/cassandra-run41` (`W=~/Library/Caches/stage4`; full `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run41`, then `ant -Dlocal.repository=$W/m2 build-test`; `-Duse.jdk11=true` is not read by `build.xml` at the tag and is dropped), macOS arm64, JDK 11.0.32.1, Ant 1.10.18. The test class is kept as `stage4-runtime-verification/harness/<stem>/DenylistTotalCapProbeTest.java` and copied into the clone's `test/unit/org/apache/cassandra/schema/` by `harness/<stem>/unit-run.sh`, which runs `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.schema.DenylistTotalCapProbeTest` once per run label and copies the JUnit XML and the test log `build/test/logs/**/TEST-org.apache.cassandra.schema.DenylistTotalCapProbeTest.log` to `$W/logs/<stem>/unit-<label>/`. Test JVM heap 1024 MiB (`build.xml:1153`). Instrument check: the class compiles in the run clone. Reason: B2a named `/tmp` and Linux paths.

**B2b. Knobs.** `per_table` is fixed at 200. `DatabaseDescriptor.setDenylistMaxKeysTotal(T)` is set before each `load()`, with T in {1, 150, 450, 799, 800, 10000}:
- 150 is less than one table's budget;
- 450 ends partway through the third table;
- 799 and 800 sit at the boundary;
- 10000 is non-binding (positive control: everything loads).

Fixed settings: `setDenylistRefreshSeconds(3600)` for phase 1 and `setDenylistRefreshSeconds(1)` for phase 2, set **before** `load()`, because the refresh interval is captured in `buildEmptyCache` (`:183-186`). Also `setPartitionDenylistEnabled(true)`, `setDenylistConsistencyLevel(ONE)`, and `setDenylistMaxKeysPerTable(200)`.

**B2c. Workload.** Copy the `@BeforeClass` from `PartitionDenylistTest.java:45-80`: `ServerTestUtils.daemonInitialization()`, `CQLTester.prepareServer()`, and `StorageService.instance.initServer(0)`.
1. Create keyspace `dlprobe` (`KeyspaceParams.simple(1)`) with tables `t1..t4 (k blob PRIMARY KEY, v int)`.
2. Insert 200 rows per table directly with `QueryProcessor.process("INSERT INTO system_distributed.partition_denylist (ks_name, table_name, key) VALUES ('dlprobe','tN',0x<hex>)", ONE)`. Do not use `denylistKey`, to avoid 800 per-table refreshes.
3. Each key is 1024 bytes: a 4-byte big-endian index followed by 1020 bytes of `0xAB`.

Arithmetic: 4 x 200 = 800 rows and 819,200 key bytes. Every T below 800 binds; T = 10000 does not.

**Amendment 2026-10-26 (step-0 audit) — B2c, partitioner, order, read thresholds, no early access.** (i) The unit JVM's partitioner is ByteOrderedPartitioner (`test/conf/cassandra.yaml:18`), so `SELECT DISTINCT ks_name, table_name` returns the partitions `(dlprobe, tN)` in byte order t1 < t2 < t3 < t4 (same keyspace prefix; the names differ only in their last byte), which decides the per-table counts (B2f amendment). (ii) Read thresholds stay as the unit yaml sets them (`test/conf/cassandra.yaml:63-67`, coordinator warn 1024 KiB, fail 4096 KiB): the largest denylist read returns at most 200 rows of 1 KiB keys (about 200 KiB), below the warn threshold, so no load is aborted. (iii) Nothing in the test reads a `dlprobe` table, and writes to `system_distributed` return from `isKeyPermitted` before `denylist.get` (`canDenylistKeyspace`, `PartitionDenylist.java:292-300`, checked at `:312`), so no cache-miss load (`:189-198`) adds an entry before the first `load()`. (iv) The schema is created as in the copied `@BeforeClass`: `CreateTableStatement.parse("CREATE TABLE tN (k blob PRIMARY KEY, v int)", "dlprobe")`, `KeyspaceMetadata.create("dlprobe", KeyspaceParams.simple(1), Tables.of(...))`, `SchemaTestUtil.addOrUpdateKeyspace(..., false)`, then `setPartitionDenylistEnabled(true)`, `setDenylistConsistencyLevel(ONE)` and `initServer(0)`. Key i (0..199) is the 4-byte big-endian i followed by 1020 bytes of `0xAB`, inserted as a 2048-hex-digit literal with `QueryProcessor.process(..., ONE)` as written. Reason: decides B2f's per-table values and removes two known confounders.

**B2d. Observables and instruments.** Read the cache by reflection:
1. Get `StorageProxy.partitionDenylist` (private static, `StorageProxy.java:213`).
2. From it get the field `denylist` (`PartitionDenylist.java:92`) and call `.asMap()`, which does not trigger loads.
3. For each value, read the fields `keys` and `tokens`.

Record:
- `K` = Σ keys.size();
- `B` = Σ key.remaining();
- `R` = Σ capacity of distinct backing arrays, using an identity set over `key.array()` when `hasArray()`. This detects slices that retain a larger buffer.
- the per-table key count;
- the count of `"Hit limit on allowable denylisted keys in total"` log lines (use a logback `ListAppender`, or grep `build/test/logs`).

What cannot be observed here is the exact retained heap. That is left to B3.

**Amendment 2026-10-26 (step-0 audit) — B2d, output and refresh evidence.** (i) Every printed line is one `System.out.println` of one string with prefix `DLP `, read from the test log (above). Before the control, before each phase-1 `load()` and before the phase-2 load and poll loop, a marker `DLP MARK <label>` is printed; each ERROR line is attributed to the segment between consecutive markers. (ii) Per table and in total: K (`keys.size()`), `tokens.size()`, B (Σ `remaining()`), R (Σ `array().length` over an identity set of the keys' backing arrays; keys without `hasArray()` are counted as `noArray=`), and `cacheEntries` (`asMap().size()`). (iii) Phase 2 also prints each poll (`poll <i> <ms> K=<k>`), `replaced=<n>` (tables whose `DenylistEntry` object differs by identity from the one right after the phase-2 load; every load or reload builds a new entry, `PartitionDenylist.java:448`) and `reloadReads=<n>` (increase of `ColumnFamilyStore.getIfExists("system_distributed","partition_denylist").metric.readLatency.latency.getCount()` across the poll loop). (iv) ERROR lines matched by text: `Hit limit on allowable denylisted keys in total. Processed <n> total entries. Not adding all entries to denylist for <ks>/<t>` (`:486`), `Partition denylist for <ks>/<t> has exceeded the <global|per-table> allowance of (<n>)` (`:425`), `Error reading partition_denylist table` (`:452`) and `Error reading full partition denylist` (`:508`); `Loaded partition denylist cache in` (`:237`) counts loads. Reason: the output location and per-T attribution were open, and the bypass part needs evidence that a refresh ran.

**B2e. Procedure.**
1. Insert the workload once, in `@BeforeClass`.
2. Phase 1, for each T: set the knobs, call `StorageProxy.instance.loadPartitionDenylist()`, then read K, B, R and the per-table counts. Do not call `isKeyPermitted` between the load and the read.
3. Phase 2: set refresh to 1 s and T = 150, then call `load()`. Read K (expected 150). `Thread.sleep(2000)`. Call `partitionDenylist.isKeyPermitted("dlprobe","tN", anyKey)` (reflected instance) for N = 1..4. Poll K every 500 ms for up to 15 s, repeating the access calls on each poll, since reload is async.
4. Run `ant testsome -Dtest.name=org.apache.cassandra.schema.DenylistTotalCapProbeTest`. The test prints a table `T, K, B, R, perTable[]`.

**Amendment 2026-10-26 (step-0 audit) — B2e, the control's step and the poll loop.** (a) **Control first** (B2h's last bullet): after the inserts and before phase 1, `DatabaseDescriptor.setPartitionDenylistEnabled(false)`, `StorageProxy.instance.initialLoadPartitionDenylist()`, read K and `cacheEntries`, then `setPartitionDenylistEnabled(true)`. `initialLoad()` returns at `PartitionDenylist.java:134-135` when the flag is false, but `load()`, and so `loadPartitionDenylist()`, does **not** read the flag (`:222-238`, `StorageProxy.java:3068-3071`); the control is therefore run on the startup path, the only path the flag gates. (b) Phase 1 runs T = 1, 150, 450, 799, 800, 10000 in this order; before each load `setDenylistRefreshSeconds(3600)`, `setDenylistMaxKeysPerTable(200)`, `setDenylistMaxKeysTotal(T)`, and the three getters are printed. (c) Phase 2 poll loop: after `Thread.sleep(2000)`, exactly 30 polls 500 ms apart (15 s), each calling `isKeyPermitted("dlprobe", "tN", 0x00)` for N = 1..4 on the reflected instance and then reading K; every poll is printed, then the full snapshot, `replaced` and `reloadReads`. (d) After the inserts, `rows tN=<n>` (`QueryProcessor.executeInternal("SELECT key FROM system_distributed.partition_denylist WHERE ks_name='dlprobe' AND table_name='tN'")`) and the partitioner's class name are printed. The test method is `probe()`. Reason: B2h's control had no step and, as named, would not test the flag on `load()`; the poll loop's stop condition was open.

**B2f. Predictions.** Tables load in `SELECT DISTINCT` token order, so which table is partial is order-dependent. Only the sums are predicted.

| T | Expected K | Expected B | Tables at a partial count | Expected "Hit limit" log lines |
|---|---|---|---|---|
| 1 | 1 | 1,024 | one table holds 1 key, three are empty | 3 |
| 150 | 150 | 153,600 | — | 3 |
| 450 | 450 | 460,800 | counts are 200 / 200 / 50 / 0 | 1 |
| 799 | 799 | — | one table holds 199 | 0 |
| 800 | 800 | — | — | 0 |
| 10000 | 800 | 819,200 | — | 0 |

In every phase-1 case R ≤ B + 1 x (largest result buffer per table). Phase 2: K goes from 150 to 800 within 15 s.

**Amendment 2026-10-26 (step-0 audit) — B2f, exact values from the source.** (i) **Control:** K = 0, `cacheEntries` = 0, no `Loaded` line in its segment. (ii) **Phase 1** per-table counts t1/t2/t3/t4: T = 1: 1/0/0/0; 150: 150/0/0/0; 450: 200/200/50/0; 799: 200/200/200/199; 800 and 10000: 200/200/200/200. K = min(T, 800); B = 1024 × K exactly (799: 818,176; 800 and 10000: 819,200); `tokens.size()` = `keys.size()` per table; **R = B exactly**: each key wraps its own exact-size array (the clustering value is read into a new `byte[length]`, `ByteArrayAccessor.java:100-105` via `ClusteringPrefix.java:517`; `bufferAt` wraps it, `ByteArrayAccessor.java:132-136`, `SelectStatement.java:1143`; `UntypedResultSet.Row.getBlob` returns that buffer, `UntypedResultSet.java:363-366`), so the filed bound "R ≤ B + 1 x (largest result buffer per table)" holds with R − B = 0. One `Loaded` line per load. (iii) **ERROR lines per segment:** `Hit limit …`: T = 1: 3 (`Processed 1`, t2, t3, t4); 150: 3 (`Processed 150`); 450: 1 (`Processed 450`, t4); 799, 800, 10000: 0. `has exceeded the global allowance of (T)`: T = 1: 1 (t1); 150: 1 (t1); 450: 1 (t3); 799: 1 (t4); 800: 0 (t4 is read with limit 200 = P against 200 rows); 10000: 0. No `per-table` line and no `Error reading` line anywhere. (iv) **Phase 2:** right after the load (refresh 1 s, T = 150) K = 150 (150/0/0/0), with 3 `Hit limit … Processed 150` lines and 1 global line (t1) in the load segment; by the last poll K = 800 (200/200/200/200), `replaced=4`, `reloadReads ≥ 4`, and no ERROR line in the poll segment (each reload reads with limit = P = 200 against 200 rows). Reason: the per-table split, the ERROR lines and R follow from the source and were open or unbounded; changed before any reading.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| K = min(T, 800) for every T, and B = 1024·K | Mechanism works as traced; claim confirmed at the unit level |
| K > T for some T < 800 right after `load()` | Total cap does not bind on full load; claim wrong |
| K = 800 at T = 10000 but K stays at 800 at T = 150 | Knob not read / load path differs from trace; claim wrong |
| K at T = 10000 < 800 | Workload never reached the limit (inserts lost, or the per-table cap was not 200); not confirmed, fix the setup |
| R ≫ B (for example, each key retains a whole response buffer) | Count is capped, but retained bytes per key exceed the key size. The heap still follows T, with a larger slope, and B3 must use measured bytes |
| Phase 2: K rises to 800 | Bypass confirmed: the cap holds only until a per-table refresh |
| Phase 2: K stays at 150 | Refresh honours the total, contrary to `:203-211`; the bypass claim is wrong |

**Amendment 2026-10-26 (step-0 audit) — B2g, the verdict of each row and added rows.** The filed rows are kept with these verdicts. Row 1 ("K = min(T, 800) for every T, and B = 1024·K") requires (i)–(iii) of the B2f amendment; with the phase-2 row "K rises to 800" (and `replaced=4`): **Confirmed** (both parts of B1), Effect *caps only on some paths (bypass)*. Row 1 with "Phase 2: K stays at 150" and `replaced=4` (the reload ran): **Refuted** (bypass part), Effect *caps*. Row 1 with K staying at 150 and `replaced` < 4: **Not confirmed** (refresh not triggered), Effect *undetermined*. "K > T for some T < 800": **Refuted**, Effect *does not cap*. "K = 800 at T = 10000 but K stays at 800 at T = 150": **Refuted**, Effect *does not cap*. "K at T = 10000 < 800": **Not confirmed** (setup), Effect *undetermined*. "R ≫ B" is read as R > 1.10 × B at some T: the count part stands and heap follows T with slope R/K, recorded; the verdict then follows the other rows. Added rows: (a) R ≠ B but R ≤ 1.10 × B: recorded as a deviation from (ii), verdict unchanged. (b) Phase 2 ends with 150 < K < 800: **Not confirmed** (partial refresh), Effect *caps only on some paths (bypass)* (K above T after a refresh). (c) Phase 2 K > 800: **Not confirmed** (per-table cap exceeded; outside this claim). (d) Counts as in row 1 but ERROR lines differ from (iii)/(iv): **Not confirmed** (disallow evidence missing), Effect from the counts. (e) Control K ≠ 0: **Not confirmed** (control failed). (f) Any `Error reading` line: **Not confirmed** (a failed read leaves an empty entry that looks like the cap). (g) Compile failure or a test error before the readings: **Invalid run** (runbook defect). Reason: the rows had meanings without verdicts and several outcomes had no row.

**B2h. Controls.**
- T = 10000 is the non-binding control: the same workload with nothing capped.
- Per-table counts check the order-independent sum.
- Not touching tables between `load()` and the read rules out refresh contamination in phase 1.
- `asMap()` rules out observer-triggered loads.
- A run with `partition_denylist_enabled=false` must give K = 0.

**Amendment 2026-10-26 (step-0 audit) — B2h, controls' evidence.** "T = 10000 non-binding": K = 800 there. "Per-table counts": printed per table. "No access between load and read": no `isKeyPermitted` call in phase 1 (test code) and `cacheEntries` = 4 after each load. "`asMap()`": used for every read. "Disabled → K = 0": B2e amendment (a), on `initialLoad`. "Same rows": `rows tN=200` for each table; no write follows. Reason: the controls' evidence was not named.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node, JDK 11. Build with `ant -Duse.jdk11=true jar` in the local clone `/local/$USER/c509-dl`, then copy `build/` and `conf/` to `/local/$USER/dlnode`.
- In `conf/cassandra.yaml`:
  - `data_file_directories`, `commitlog_directory`, `hints_directory` and `saved_caches_directory` under `/local/$USER/dlnode/data`;
  - `partition_denylist_enabled: true`;
  - `denylist_consistency_level: ONE` (one node; `system_distributed` has RF 3, so QUORUM would be unavailable);
  - `denylist_max_keys_per_table: 1000`;
  - `denylist_refresh: 86400s` for phase 1;
  - `file_cache_size: 32MiB`;
  - `MAX_HEAP_SIZE=2G` and `HEAP_NEWSIZE=400M` in `conf/cassandra-env.sh`, or set them in the environment.
- Ports stay at their defaults, on a machine with no other Cassandra.

**Amendment 2026-10-26 (step-0 audit) — B3a, this host.** One node on 127.0.0.1 from the run clone `$W/cassandra-run41` (its `build/` and `bin/` used in place; `build-test` includes `jar`); nothing is copied into or written in the clone. `harness/<stem>/make-node-conf.sh` (the sister case's, with the clone and node paths changed) writes `$W/node-dl41/conf` from the tag's `conf/` with `cluster_name: dl41`, listen and rpc 127.0.0.1, data, commit log, hints, saved caches and cdc directories under `$W/node-dl41/`, and B3a's lines: `partition_denylist_enabled` (true; false for the baseline and the setup start), `denylist_consistency_level: ONE`, `denylist_max_keys_per_table: 1000`, `denylist_refresh: 86400s` (20s in phase 2), `file_cache_size: 32MiB`, `denylist_max_keys_total: <T>`, and **`memtable_allocation_type: offheap_buffers`**. The tag's yaml has `heap_buffers` (`conf/cassandra.yaml:825`), under which every memtable that takes a write allocates on-heap 1 MiB `[B` regions (`SlabAllocator.java:51`, `:139`); the system-table writes of each start would move the `[B` reading in 1 MiB steps between restarts, the size of the T = 1 band. With `offheap_buffers` those regions are direct buffers; the denylist keys are read from sstables into heap arrays either way (B2f amendment (ii)). Heap `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`, G1. Start: `CASSANDRA_CONF=$W/node-dl41/conf CASSANDRA_LOG_DIR=<config dir>/node nohup bin/cassandra -f > node.out 2>&1 < /dev/null &`, pid from `$!` (no `setsid` on this host; `bin/cassandra -p` daemonizes, which this host cannot track). Stop: `nodetool drain`, `kill <pid>`, wait for the exit. Each start has its own log directory, so its `system.log` holds one startup. Reason: B3a named Linux paths; the `[B` instrument needs the memtable slabs off heap.

**B3b. Knobs.** `denylist_max_keys_total` ∈ {1, 1000, 2500, 10000}, set in the yaml with a restart per value, so the startup `initialLoad` → `load()` path is the one measured.
- 1000 equals one table's budget.
- 2500 binds partway through the third table.
- 10000 is non-binding: the positive control, where the per-table cap of 1000 is known to bind and all 4000 keys load.
- Baseline: `partition_denylist_enabled: false`, with the same data.
- Phase 2: `denylist_max_keys_total: 1000`, `denylist_refresh: 20s`.

**B3c. Workload.**
1. Run `bin/cqlsh -e "CREATE KEYSPACE dl WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE dl.t1 (k blob PRIMARY KEY, v int);"` and repeat the table for `t2..t4`.
2. Insert 1000 keys per table into `system_distributed.partition_denylist`, each 32,768 bytes (4-byte index plus a filler of `0xAB`). Use a Python 3 script that imports the driver bundled with cqlsh: `sys.path.insert(0, glob('lib/cassandra-driver-internal-only-*.zip')[0])`. Run it with `python3 -I insert_dl.py /local/$USER/dlnode` and use a prepared `INSERT ... VALUES ('dl', ?, ?)` at CL ONE.
3. Then run `bin/nodetool flush system_distributed` and `bin/nodetool drain`, and stop the node. This keeps the rows out of the memtable and commit log on restart.

Arithmetic: 4000 x 32 KiB = 125 MiB of key bytes, which fits a 2 GiB heap.
- T = 1000 → about 31 MiB.
- T = 2500 → about 78 MiB.
- T = 10000 → about 125 MiB.

The disk used is about 130 MiB, plus about 125 MiB of commit log before the drain.

**Amendment 2026-10-26 (step-0 audit) — B3c, setup start, insert script and row check.** The setup start uses the baseline yaml (`partition_denylist_enabled: false`), so no cache is built while the data is written. `harness/<stem>/insert_dl.py`, run as `python3 -I insert_dl.py <driver zip> 1000 <out>`, imports the driver bundled in the clone (`lib/cassandra-driver-internal-only-*.zip`; the `cassandra` package is under its `cassandra-driver-<ver>/` folder), connects with protocol 5, `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`, and executes the prepared `INSERT INTO system_distributed.partition_denylist (ks_name, table_name, key) VALUES ('dl', ?, ?)` at CL ONE for t1..t4 and i = 0..999 (key = 4-byte big-endian i, then 32,764 bytes of `0xAB`); a failed insert is retried up to 5 times with a reconnect; it prints the inserted and failed counts. Then `SELECT count(*) FROM system_distributed.partition_denylist WHERE ks_name='dl' AND table_name='tN'` must return 1000 for each table (it reads the denylist table, not a `dl` table), then `nodetool flush system_distributed`, drain and stop. Reason: paths; the row check makes "workload never reached the limit" observable.

**B3d. Observables and instruments.**
- `jcmd <pid> GC.class_histogram`, which forces a full GC and so counts live objects only. Read the bytes of `[B` and the instance counts of `org.apache.cassandra.dht.Murmur3Partitioner$LongToken` and `java.nio.HeapByteBuffer`. Take 3 samples, 10 s apart, starting 60 s after the log line `Loaded partition denylist cache`, and use the median.
- Optional cross-check: `jcmd <pid> GC.heap_dump /local/$USER/dlnode/h.hprof`, then the retained size of `PartitionDenylist` in Eclipse MAT.
- Also record the count of `Hit limit on allowable denylisted keys` lines in `logs/system.log`.

What cannot be observed is the cache size in isolation. It is estimated as the `[B` delta against the baseline.

**Amendment 2026-10-26 (step-0 audit) — B3d, how each reading is taken.** (i) From `jcmd <pid> GC.class_histogram` (live objects after a full GC): the bytes of the row whose class column (4th field) is exactly `[B`; the instances of `org.apache.cassandra.dht.Murmur3Partitioner$LongToken`, `java.nio.HeapByteBuffer` and `org.apache.cassandra.schema.PartitionDenylist$DenylistEntry` (recorded); and `Total`. (ii) Sampling: with the denylist enabled, 3 samples 10 s apart starting 60 s after that start's `Loaded partition denylist cache` line; baseline, 3 samples 10 s apart starting 120 s after that start's `Startup complete` line (`CassandraDaemon.java:744`). Each reading is the median of its 3 samples. Phase 2's H0 and H1 are such medians too. (iii) Δ = median(config) − median(B0a); **B0b**, the baseline repeated at the end, is the cross-restart drift control. (iv) Phase-2 refresh evidence: the READS sampler `nodetool profileload -a READS -k 20 system_distributed partition_denylist 95000`, started right after H0 and covering both read rounds; it samples only non-empty partitions (`SinglePartitionReadCommand.java:911-917`, `:1052-1055`), so it counts the `dl:t1`..`dl:t4` reads and not the empty `system_schema` partitions that each cqlsh connection adds to the cache (sister case `denylist_max_keys_total-setDenylistMaxKeysTotal-value`, defect 1); `Local read count` of the table before and after is recorded. (v) Log lines in each start's `system.log` (phase 2 also split at H0 by byte offset): `Hit limit …` (with `Processed <n>` and the table), `has exceeded the <type> allowance of (<n>)`, `Error reading …`, `Loaded partition denylist cache`. (vi) Settings read back from `system_views.settings` after the histograms of each start (cqlsh reads no `dl` table). (vii) The MAT cross-check is not run: MAT is not installed on this host (the file marks it optional). Reason: the column match on this JDK, the baseline's and phase 2's sampling, the drift control and the refresh evidence were open.

**B3e. Procedure.**
1. Do the setup, workload, flush, drain and stop described in B3c.
2. For each configuration (baseline, then T = 1, 1000, 2500, 10000):
   1. Edit the yaml.
   2. Start with `bin/cassandra -p /local/$USER/dlnode/pid`.
   3. Wait for `Loaded partition denylist cache` (or, for the baseline, wait 120 s after startup).
   4. Do **not** issue any client request to `dl.*`.
   5. Take the histograms.
   6. Stop with `bin/nodetool drain; kill $(cat pid)`, and wait for the process to exit.
3. Phase 2:
   1. Set T = 1000 and `denylist_refresh: 20s`, then start and take a histogram (H0).
   2. Wait 30 s.
   3. Run `bin/cqlsh -e "SELECT * FROM dl.tN WHERE k=0x00"` for N = 1..4. Each read calls `isKeyPermitted`, which triggers the async refresh.
   4. Wait 30 s, repeat the four reads, wait 30 s, then take a histogram (H1).
   5. Stop.

**Amendment 2026-10-26 (step-0 audit) — B3e, order and scripts.** Script `harness/<stem>/cluster-run.sh` (logs `$W/logs/<stem>/cluster-<run>/`). Order, each a restart on the same data: setup (B3c) → **B0a** (enabled false) → T = 1 → 1000 → 2500 → 10000 → phase 2 (T = 1000, refresh 20 s) → **B0b** (enabled false, drift control). No client request to `dl.*` except phase 2's reads. Phase 2: H0, start the sampler, wait 30 s, four reads (one `bin/cqlsh -e` per read), wait 30 s, four reads, wait 30 s and until the sampler has ended, H1. A shakedown with 100 keys per table (P = 100) runs every step before run 1; its readings are not judged. The node directory is wiped at the start and the end. Reason: B3e named `-p pid` and Linux paths; the drift control and refresh evidence need a place in the order.

**B3f. Predictions.** Δ[B] is measured against the baseline.

| T | Expected Δ[B] | Expected LongToken count | Expected log lines |
|---|---|---|---|
| 1 | about 0 (< 2 MiB) | — | 3 "Hit limit" |
| 1000 | 31–36 MiB | about 1000 | 3 |
| 2500 | 78–90 MiB | about 2500 | 1 |
| 10000 | 125–145 MiB | about 4000 | 0 |

The ranges allow up to +15% for object headers and any shared slice buffers.

Phase 2: H0 shows about 31–36 MiB. H1 shows 125–145 MiB, i.e. the cap is bypassed after refresh.

**Amendment 2026-10-26 (step-0 audit) — B3f, values derived and bands.** Each loaded key holds one 32,768-byte array (32,784 B in the histogram with the 16-byte header) and one `HeapByteBuffer`; Murmur3 tokens are `LongToken` objects without arrays. So Δ[B] per key = 32,784 B: T = 1: 32,784 B; 1000: 31.27 MiB; 2500: 78.16 MiB; 4000 keys: 125.06 MiB. The filed ranges are kept and widened by the baseline allowance the file itself uses for T = 1 (2 MiB): **T = 1: |Δ[B]| < 2 MiB; T = 1000 and H0: [29, 38] MiB; T = 2500: [76, 92] MiB; T = 10000 and H1: [123, 147] MiB.** ΔLongToken within ±max(100, 10 % of K) of K: T = 1: 1 ± 100; 1000 and H0: [900, 1100]; 2500: [2250, 2750]; 10000 and H1: [3600, 4400]. ΔHeapByteBuffer recorded. **Log lines per start:** T = 1: 3 `Hit limit` (`Processed 1`), 1 `global allowance of (1)`; T = 1000: 3 `Hit limit` (`Processed 1000`), no `exceeded` line (the first table is read with limit 1000 = P against 1000 rows); T = 2500: 1 `Hit limit` (`Processed 2500`), 1 `global allowance of (2500)`; T = 10000: none; phase-2 load: 3 `Hit limit` (`Processed 1000`) and no line after H0; no `per-table` line and no `Error reading` line; exactly one `Loaded` line per enabled start, none in B0a or B0b. Settings read back equal the yaml. Rows 1000 per table. **Drift control:** |[B(B0b) − [B(B0a)| ≤ 2 MiB. **Phase-2 sampler:** ≥ 4 `dl` reads (one per table per refresh; 8 expected for two rounds 35 s apart). Reason: values derived; the filed lower bounds left no room for baseline noise, which the file's T = 1 band allows; "about" made numeric; disallow and refresh evidence made exact. Changed before any reading.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Δ[B] tracks min(T, 4000) x 32 KiB within the ranges, and is flat between 10000 and larger T | Heap follows the knob on full load; claim confirmed |
| Δ[B] at T = 1000 about equal to Δ[B] at T = 10000 | Total does not cap the heap on load; claim wrong |
| Δ[B] at T = 10000 is about 0 | Positive control did not move: the load failed (CL unavailable, or the `dl` tables missing so `tid` was null) or the data was lost. Not confirmed; check the log |
| Δ[B] scales with T but with a slope ≫ 32 KiB/key | Count is capped, but each key retains more (slices of response buffers). Claim holds with a different constant; record the slope |
| Phase 2: H1 ≫ H0, about the 10000 level | Bypass confirmed: steady-state heap follows per_table x tables, not total |
| Phase 2: H1 about equal to H0 | Refresh honours the total, or the refresh never fired. Check for `DenylistCache` thread activity, and repeat with more reads |

**Amendment 2026-10-26 (step-0 audit) — B3g, the verdict of each row and added rows.** Row 1 ("Δ[B] tracks min(T, 4000) x 32 KiB within the ranges, and is flat between 10000 and larger T"; no T above 10000 is run, so "flat" is read as T = 10000 at the 4000-key level set by the per-table cap) requires the B3f amendment's bands, ΔLongToken, log lines, row counts, settings and drift control. With the phase-2 row "H1 ≫ H0, about the 10000 level" (H1 in [123, 147] MiB and sampler ≥ 4): **Confirmed** (both parts of B1), Effect *caps only on some paths (bypass)*. Row 1 with "H1 about equal to H0" (H1 in H0's band) and sampler ≥ 4: **Refuted** (bypass part), Effect *caps*; with sampler < 4: **Not confirmed** (refresh not seen), Effect *undetermined*. Row 2 ("Δ[B] at T = 1000 about equal to Δ[B] at T = 10000", i.e. Δ1000 in the 10000 band): **Refuted**, Effect *does not cap*. Row 3 ("Δ[B] at T = 10000 is about 0", below 2 MiB): **Not confirmed** (positive control did not move). Row 4 (slope ≫ 32 KiB/key: every Δ[B] above its band with Δ[B]/K > 1.5 × 32,784 B and ΔLongToken in band): **Confirmed** with a different constant (slope recorded), Effect from phase 2 as for row 1. Added rows: (a) drift control > 2 MiB: **Not confirmed** (instrument noise), Effect *undetermined*; (b) a row count ≠ 1000 or a settings mismatch: **Not confirmed** (setup); (c) bands hold but log lines differ: **Not confirmed** (disallow evidence missing), Effect from the heap; (d) any `Error reading` line: **Not confirmed** (load failure); (e) a reading outside its band that matches no other row: **Not confirmed**, Effect *undetermined*; (f) H1 between the H0 and H1 bands: **Not confirmed**, Effect *caps only on some paths (bypass)* if H1 is above H0's band; (g) a node that does not start or load: runbook defect. Reason: the rows had meanings without verdicts and several outcomes had no row.

**Runbook fix 2026-10-26 (stage 4, defect 1; found by the cluster shakedown before cluster run 1) — B3f and B3g amendments, ΔLongToken.** In the shakedown (100 keys per table, readings not judged), the instance count of `Murmur3Partitioner$LongToken` with the denylist off was 156 at B0a and 276 at B0b, and with each start's K subtracted it ranged from 156 to 266 over the seven starts: the background of `LongToken` objects (decorated keys of system-table partitions that each start writes or reads) moves across restarts by about the width of the ±100 band the audit added for T = 1 and T = 1000, so that band cannot separate K from the background. Fix: ΔLongToken is still recorded and compared with its band, but it is no longer a condition of any B3g row (row 1 and row 4 drop it). The `[B` bands, which the file names as its observable, the log lines, row counts, settings, drift control and every other condition are unchanged; so are the claim, the values and the rows. The unit tier (run at sha256 `61bab981…28f9`) is unaffected. Reason: a criterion added at the audit was narrower than its instrument's background; found before cluster run 1.

**B3h. Controls.**
- The baseline with the denylist disabled and identical on-disk data cancels the memtable, chunk cache and schema footprint.
- Flushing and draining before each restart keeps the 125 MiB out of the memtable.
- Sending no client traffic to `dl.*` in phase 1 rules out refresh-driven reloads.
- The T = 10000 positive control shows the workload is large enough to be seen.
- 3-sample medians reduce GC noise.

**Amendment 2026-10-26 (step-0 audit) — B3h, controls' evidence.** Baseline: B0a with the same data and the denylist off; B0b repeats it after all other starts (drift control). Flush and drain: `nodetool flush system_distributed` then drain before every stop, so no commit-log replay brings the 125 MiB into a memtable; with `offheap_buffers` a memtable's cell bytes would not be in `[B` anyway. No `dl` traffic in phase 1: the script sends none (cqlsh only reads `system_views.settings` after the histograms). Positive control: T = 10000 at the 4000-key level. Medians of 3. Reason: the controls' evidence was not named.

**B4. Risks and cleanup.**
- Disk:
  - unit tier, about 50 MiB under `build/test`;
  - cluster tier, about 300 MiB peak under `/local/$USER/dlnode`;
  - a heap dump, if taken, about 2 GiB. Delete it after use.
- Never write into `/Users/yangwang/cassandra-src` or shared storage.
- After each run, check with `pgrep -f CassandraDaemon` and `pgrep -f DenylistTotalCapProbeTest` that no process is left.
- Finally, `rm -rf /local/$USER/dlnode /local/$USER/c509-dl`.

**Amendment 2026-10-26 (step-0 audit) — B4, this host.** Node directory `$W/node-dl41` (data, commit log, hints) on the internal SSD, wiped at the start and end of each cluster run; no heap dump is taken; nothing is written to `~/cassandra-src` or under `/local`. After each run, `ps -eo command | grep '[C]assandraDaemon'` must be empty and the run clone's `git status` clean (the unit-run script removes the copied test class). Reason: B4 named Linux paths.

## C. Sources read

- src/java/org/apache/cassandra/schema/PartitionDenylist.java
- src/java/org/apache/cassandra/config/Config.java (759-786)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (4808-4830)
- src/java/org/apache/cassandra/service/StorageProxy.java (213, 3060-3160)
- src/java/org/apache/cassandra/service/StorageService.java (1340-1352)
- src/java/org/apache/cassandra/schema/SystemDistributedKeyspace.java (96-183)
- src/java/org/apache/cassandra/cql3/QueryProcessor.java (377-392)
- src/java/org/apache/cassandra/cql3/QueryOptions.java (62-65)
- src/java/org/apache/cassandra/cql3/UntypedResultSet.java (363-366)
- conf/cassandra.yaml (1438-1467)
- test/unit/org/apache/cassandra/service/PartitionDenylistTest.java
- NEWS.txt (462-463)
- https://issues.apache.org/jira/browse/CASSANDRA-12106

## D. Stage-4 feedback

**2026-10-26 — stage 4, run 1 (advisor's machine), Claude Opus 5.5 (claude-opus-5-5).** Results: [`stage4-runtime-verification/results/denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous.md`](../../stage4-runtime-verification/results/denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous.md). Frozen after fifteen step-0 amendments at sha256 `61bab981…28f9` (unit tier) and, after runbook fix 1, `a7f6dec7…cc2b` (cluster tier); uncommitted.
- **Unit: Confirmed — caps only on some paths (bypass).** B2g row 1: K = 1, 150, 450, 799, 800, 800 for T = 1, 150, 450, 799, 800, 10000, per-table split first-come in token order (t1..t4), B = R = 1024·K, the exact `Hit limit` and `global allowance` lines per T, control K = 0; phase 2 (refresh 1 s, T = 150): K 150 → 800 with all four entries replaced and 56 reload reads.
- **Cluster: Confirmed — caps only on some paths (bypass).** B3g row 1: live `[B` above the denylist-off baseline 0.06 / 31.31 / 78.18 / 125.09 MiB for T = 1 / 1000 / 2500 / 10000 at the startup load (32.8 KB per 32 KiB key), exact log lines, baseline drift 9 KB; phase 2 (T = 1000, refresh 20 s): 31.30 → 125.20 MiB after two read rounds (8 sampled refresh reads).
- **Runbook defect 1** (cluster shakedown): the background `LongToken` count moves across restarts by about the ±100 band added at the audit; ΔLongToken is recorded only (all its run-1 readings fell inside the band).
- **For stage 3:** `partition_denylist_enabled` gates `initialLoad` and the access paths but not `load()` itself (`PartitionDenylist.java:222-238`; JMX `loadPartitionDenylist` loads with the flag off), so B2h's control as filed would not have given K = 0 on `load()`; the add/remove and cache-miss paths are derived as bypasses (A3) but were not run. The Estimate stands as filed.
