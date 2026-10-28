# Prepared-statement preload byte threshold (1.1 x prepared_statements_cache_size) — verification solution  <!-- file: cases/prepared_statements_cache_size-loadpreparedstatements-preparedbytesloaded--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`SystemKeyspace.java:1919`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/SystemKeyspace.java#L1919) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: the check is a startup early-exit that limits how many saved statements are paged and re-prepared, but the heap held by prepared statements is already capped by the Caffeine cache weigher, so the check does not bound resident memory. |
| Ground | Resident prepared-statement memory is bounded by `maximumWeight(PREPARED_STATEMENT_CACHE_SIZE_BYTES)` (QueryProcessor.java:113-117) whether or not this check fires; statements loaded past the threshold would only be evicted. Breaking out only saves startup time and transient garbage. The 1.1 factor is a hard-coded literal, and the count is of `pstmntSize` that the same cache already evicts. |

**Type:** non-config (hard-coded constant). The constant rule applied: the literal `1.1` (and the literal `0` in `Math.max(0, ...)`) take part in the check, together with the yaml entry `prepared_statements_cache_size` (no JVM property involved).

> Link rule: declarations and the if statement are linked below.

## A. Constraint trace

**A1. The constraint.** `preparedBytesLoadThreshold = (long) (PREPARED_STATEMENT_CACHE_SIZE_BYTES * 1.1)` ([`SystemKeyspace.java:1907`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/SystemKeyspace.java#L1907)). Compared operands:
- `preparedBytesLoaded`: local `long` accumulated at SystemKeyspace.java:1908 and :1917 (`+= Math.max(0, prepared.pstmntSize)`); unit bytes.
- `preparedBytesLoadThreshold`: bytes. Hard-coded literal `1.1` (headroom, comment at :1905-1906) times `PREPARED_STATEMENT_CACHE_SIZE_BYTES`, declared at [`QueryProcessor.java:107`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L107) as `capacityToBytes(DatabaseDescriptor.getPreparedStatementsCacheSizeMiB())` (MiB x 1024 x 1024, QueryProcessor.java:142-145). It is a non-final static, fixed at class init.
- The MiB value comes from yaml `prepared_statements_cache_size` ([`Config.java:585`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L585), `conf/cassandra.yaml:508`). Default null means "auto": `max(10, maxMemory/1024/1024/256)` MiB, i.e. max(1/256 of heap, 10 MiB) (DatabaseDescriptor.java:795-798). Value 0 is rejected (:800-801). Setting it needs a restart; no JMX setter was found for this path.
- Literals: `1.1` (headroom, not settable), `0` (clamps a negative `pstmntSize`, which defaults to -1 at QueryHandler.java:63, to zero).

**A2. What it caps.** Nominally heap used by prepared statements: the sum of `ObjectSizes.measureDeep(Prepared)` (QueryProcessor.java:947-950, set at :469) for statements re-created at startup. In fact it bounds only the amount of work done in the preload loop (startup time and short-lived garbage), not what stays resident.

**A3. Mechanism.** Enclosing method `SystemKeyspace.loadPreparedStatements(TriFunction, int pageSize)` ([`SystemKeyspace.java:1899`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/SystemKeyspace.java#L1899)). It pages `system.prepared_statements` (:1901-1902); for each row the callback `onLoaded` parses and prepares the statement and `preparedStatements.put(id, prepared)` (QueryProcessor.java:174-182). Non-null results increment `counter` and add size (:1915-1918). The if statement ([`SystemKeyspace.java:1919`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/SystemKeyspace.java#L1919)):
- true: logs a warning (CASSANDRA-19703 leak symptom) and `break`s; remaining rows are not loaded; the method returns `counter`.
- false: continue the loop.
Callers: `loadPreparedStatements(onLoaded)` at :1894-1897 (page size 5000, QueryProcessor.java:104); `QueryProcessor.preloadPreparedStatements(int)` (QueryProcessor.java:171); `CassandraDaemon.java:377` at startup; `PstmtPersistenceTest.java:126,310`. Bypass/overshoot: the break happens only after the byte total has already exceeded 110%, so up to one statement over the threshold is loaded; statements with null result (parse error) add 0; `pstmntSize` defaults to -1 (QueryHandler.java:63) but the preload callback calls `parseAndPrepare(query, clientState, false)` (QueryProcessor.java:179), which delegates with `measure=true` (:436-439, :468-469), so the size is set before the check; the `Math.max(0, ...)` is only a guard.

**A4. Other consumers.** Heap for the same cache is also consumed by user `PREPARE` calls (QueryProcessor.java:825-833) which check each statement against the same cap, and by the Caffeine eviction path (:113-117). The rest of the heap (memtables, caches, buffers) is independent.

**A5. Evidence beyond the source.** In-code comment citing CASSANDRA-19703 (prepared statement cache leak). Test `PstmtPersistenceTest.testPreloadPreparedStatements` (test/unit/.../PstmtPersistenceTest.java:310) covers paging, not the threshold. The third argument of `parseAndPrepare` at :179 is `isInternal`, and `measure` is true (QueryProcessor.java:436-441), so `pstmntSize` is populated at the check.

## B. Verification solution

**B1. Claim under test.** The threshold check does not bound resident prepared-statement heap: with the check effectively disabled, heap held by prepared statements after startup stays at or below the Caffeine cache cap (`prepared_statements_cache_size`), the same as with the check enabled; the check changes only the number of statements loaded and startup time. Also (sanity): `pstmntSize` is >= 0 at the check.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant, local copy of the tag outside the shared tree (`cp -r` to a work dir, `ant jar`). Write a JUnit test modelled on `PstmtPersistenceTest` (test/unit/org/apache/cassandra/cql3/PstmtPersistenceTest.java), run with `ant testsome -Dtest.name=PstmtPersistenceThresholdTest`. JVM `-Xmx512m`.

**B2b. Knobs.** `prepared_statements_cache_size` in test yaml: 1 MiB (ensure min allowed; note the floor of 1 since 0 is rejected), 2 MiB, 10 MiB. Arm B: the work copy with `1.1` patched to `1000.0` (literal patch, effectively disabling the check). Set the knob via a test yaml/`DatabaseDescriptor` before `QueryProcessor` class init (static field).

**B2c. Workload.** Prepare N distinct statements (`INSERT ... USING TIMESTAMP i`, as the existing test does) so that on-disk total exceeds 1.1 x cache: with a per-statement size s (printed by the test from `prepared.pstmntSize`), N = ceil(3 x cap / s). Clear the cache only (`QueryProcessor.clearPreparedStatements(true)`), then call `preloadPreparedStatements(pageSize=100)`.

**B2d. Observables and instruments.** Return value `counter`; `QueryProcessor.preparedStatementsCount()`; Caffeine `preparedStatements.policy().eviction()` weighted size; `pstmntSize` of each loaded statement (log it inside a test hook or via a Byteman rule on `SystemKeyspace.loadPreparedStatements`); the WARN log line "Detected prepared statement cache filling up"; heap after `System.gc()` via `Runtime` used memory or a heap histogram (`jcmd GC.class_histogram`).

**B2e. Procedure.** 1) Set knob; 2) prepare N statements; 3) record on-disk count; 4) clear cache only; 5) preload; 6) record counter, cache count, weighted size, WARN presence, used heap after GC; 7) repeat for each knob and for arm B (patched literal); 8) positive control below.

**B2f. Predictions.** Arm A (unpatched), N s = 3 x cap: WARN logged (if `pstmntSize` is populated), `counter` approximately 1.1 x cap / s + 1 and well below N; cache weighted size <= cap. Arm B (patched): no WARN, `counter` = N; cache weighted size still <= cap and used heap after GC within noise of arm A (difference below one cap). If `pstmntSize` is -1 at the check, arm A also shows no WARN and `counter` = N, identical to arm B (check dead on this path).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Arm B weighted cache size / post-GC heap grows beyond cap, or exceeds arm A by about 1 cap or more | Claim refuted: the check bounds resident memory |
| Cache size <= cap and post-GC heap equal in both arms while `counter` differs (arm A < arm B) | Claim confirmed (check bounds work only) |
| Positive control (below) moves heap with its knob while arms A/B stay flat | Confirms the instrument can see change |
| `counter` equal in both arms and no WARN | Check dead on this path (pstmntSize unpopulated) or threshold not reached: not confirmed for the "bounds work" part; negative-for-memory still holds, confirmed by flat heap |
| Cache size unchanged when knob changes in the positive control | Instrument failed; not confirmed |

**B2h. Controls.** Positive control: a cache knob that does bind memory, `prepared_statements_cache_size` itself: 1 vs 10 MiB with same N; resident weighted size and post-GC heap should scale with it (about 1 vs 10 MiB). Repeat each run 3 times; GC before each reading; same statements text in all arms.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, `ant jar` of a local copy; arm B uses a second copy patched `1.1` -> `1000.0`. `-Xms1g -Xmx1g`, own `cassandra.yaml` copy, separate data dirs under a private work directory, loopback IP.

**B3b. Knobs.** `prepared_statements_cache_size`: 1 and 10 (MiB, restart required); build arm (unpatched/patched).

**B3c. Workload.** With the node up, use a CQL driver (or Python script over cqlsh native protocol) to prepare M distinct statements (varied `USING TIMESTAMP`) with 10 MiB cache so that the persisted table `system.prepared_statements` holds more than 3 x 1 MiB of statements (M = 3 MiB / s using measured s; cache itself evicts, persisted rows are removed on eviction via `evictPreparedStatement`, so check `SELECT count(*) FROM system.prepared_statements`; if eviction removes the rows, instead write rows directly with `INSERT INTO system.prepared_statements` after stopping client load, using the same query strings). Stop node, change knob to 1 MiB, restart for the measurement.

**B3d. Observables and instruments.** `system.log` (WARN line and "Preloaded N prepared statements in X ms"); `nodetool info`/`jcmd <pid> GC.heap_info` after `jcmd GC.run`; `jcmd GC.class_histogram` totals for `Prepared`, `CQLStatement` classes; `nodetool tablestats` not needed. Sample heap at startup end and 60 s later.

**B3e. Procedure.** Start node (arm A, 1 MiB) -> record log and post-GC heap -> stop -> start arm B build on a copy of the same data dir -> record -> compare; repeat at 10 MiB as positive control.

**B3f. Predictions.** Arm A at 1 MiB: WARN present (if size populated) and fewer statements loaded; arm B: all loaded then evicted; both post-GC heap used by prepared statements <= about 1 MiB + overhead, difference below 1 MiB; 10 MiB runs show about 10 MiB scale class-histogram bytes of `Prepared` objects when enough statements exist.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Arm B post-GC prepared bytes exceed arm A by >= cap | Claim refuted |
| Equal within one cap while startup log counts differ | Claim confirmed |
| 10 MiB control does not scale class-histogram bytes | Control failed; not confirmed |
| No WARN in arm A | Threshold not reached or size unpopulated; resolve with B2 |

**B3h. Controls.** Same data dir copy for both arms; same heap flags; same JDK; force GC before each reading; no other client load.

**B4. Risks and cleanup.** Disk: a few MiB of statements and a private data dir; delete the work dir after. Stop every started JVM (`pgrep -f CassandraDaemon`) and the ant test JVM; never build in the shared source tree.

## C. Sources read

- src/java/org/apache/cassandra/db/SystemKeyspace.java (1890-1950)
- src/java/org/apache/cassandra/cql3/QueryProcessor.java (100-200, 455-475, 825-835, 945-958)
- src/java/org/apache/cassandra/cql3/QueryHandler.java (pstmntSize, grep)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (790-812)
- src/java/org/apache/cassandra/config/Config.java (584-585)
- conf/cassandra.yaml (500-515)
- src/java/org/apache/cassandra/service/CassandraDaemon.java (370-380)
- test/unit/org/apache/cassandra/cql3/PstmtPersistenceTest.java (300-340)

## D. Stage-4 feedback

`none yet`
