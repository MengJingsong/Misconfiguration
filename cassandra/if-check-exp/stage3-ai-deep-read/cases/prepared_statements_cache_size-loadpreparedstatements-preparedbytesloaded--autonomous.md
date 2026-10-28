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

> **Amendment 2026-10-27 (stage-4 audit, before any run; node pc29; none of it depends on a reading).**
> (1) *What "resident prepared-statement heap" means here:* the cache component, i.e. the sum over the cache of `key.size() + pstmntSize` (exactly the Caffeine weight, read from `QueryProcessor.instance.getPreparedStatements()`), and `ObjectSizes.measureDeep` of that map. The post-GC live heap and the memtable of `system.prepared_statements` are reported beside it and read as stated in B2g/B3g.
> (2) *Why the filed workload cannot reach the check (runbook defect, fixed below):* every cache eviction deletes the row from `system.prepared_statements` (`QueryProcessor.evictPreparedStatement`, lines 132-139), so PREPARE-only loading never leaves more than about 1 x cap on disk and the preload loop can never pass 1.1 x cap. The rows must be written without going through the cache (B2c, B3c below).
> (3) *Positive control* (negative-claim rule): the same preload workload and the same readings in arm B (check inert) at caps 1, 4 and 10 MiB; the cache component must move with the cap (about 1 : 4 : 10). That is the closed `Confirmed` case on this knob (`prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous`) re-used as the control on the preload path.

**B1. Claim under test.** The threshold check does not bound resident prepared-statement heap: with the check effectively disabled, heap held by prepared statements after startup stays at or below the Caffeine cache cap (`prepared_statements_cache_size`), the same as with the check enabled; the check changes only the number of statements loaded and startup time. Also (sanity): `pstmntSize` is >= 0 at the check.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant, local copy of the tag outside the shared tree (`cp -r` to a work dir, `ant jar`). Write a JUnit test modelled on `PstmtPersistenceTest` (test/unit/org/apache/cassandra/cql3/PstmtPersistenceTest.java), run with `ant testsome -Dtest.name=PstmtPersistenceThresholdTest`. JVM `-Xmx512m`.

> **Amendment 2026-10-27 (B2a-B2h, replaces the text it sits beside where they differ).**
> *B2a:* two copies of the tag are built on the node, `~/s4-base` (arm A, unmodified) and `~/s4-psc-b` (arm B, `* 1.1)` at `SystemKeyspace.java:1907` changed to `* 1000.0)`; `git diff` of the copy is kept). Test class `PstmtPreloadThresholdTest` (harness folder), copied into both.
> *B2b:* caps 1, 4 and 10 MiB (10 MiB is the auto default at the unit-test heap, `max(10, 1 GiB/256 MiB)`; 4 replaces 2 so the control spans 1 : 4 : 10); arm A and arm B at every cap; one JVM per cell, because the cap is read at class init.
> *B2c:* statement text `SELECT v FROM <ks>.<table> WHERE k = ? /* u<i> */` (fully qualified, unique comment; one size s for all; the same text in all arms). s = `pstmntSize` of one statement as the preload callback computes it (`parseAndPrepare(query, cs, false)`, `measure` true). Rows are written with `SystemKeyspace.writePreparedStatement(null, MD5Digest.compute(query), query, ts+i)` for i < n, n = ceil(f x cap / s), then the table's memtable is flushed, the cache is empty, and `preloadPreparedStatements(100)` runs once. Factor f = 3 (as filed) at every cap; factor f = 30 at caps 1 and 10 (new: a leak-sized backlog, the situation CASSANDRA-19703 describes). Offered/cap is printed.
> *B2d:* per cell the test prints: `loaded` (return value), WARN seen (logback appender on `SystemKeyspace`), cache `count`, `evicted`, `sumWeights`, `sumPstmntSize`, `measureDeep`, rows left in `system.prepared_statements`, memtable on-heap data size of that table before/after (`allMemtablesOnHeapDataSize`), post-GC live heap before/after (3 x `System.gc()`), and thread-allocated bytes during the preload (work done). Resolution note: the post-GC live heap moves by about 1 to 2 MiB between identical runs, so at a 1 MiB cap it cannot by itself show a difference of one cap; the cache component is the exact reading.
> *B2e step 8 (repetitions):* f = 3 cells are run 3 times (reps), f = 30 cells once.
> *B2f additions (stated before the run):* arm A loads `floor(1.1 x cap / s) + 1` statements (that is 428 at cap 1 MiB for s = 2696, but the run uses the s it measures) at every cap and every f, WARN logged; arm B loads n, WARN not logged, `count + evicted = n`; `sumWeights <= cap` and `sumWeights > cap - 2 x (s + 16)` in every cell once n x s > cap (the cache fills); the cache component of A and B differs by less than one cap (both are at the cap). Control: in arm B `sumWeights` at 1 : 4 : 10 MiB is about 1 : 4 : 10. Arm A at f = 30 has the same `loaded` as at f = 3 (the check bounds the work, not the backlog). Arm B's evictions delete rows, so arm B ends with about count rows on disk and a memtable holding about `n - count` tombstones, arm A with about `n - loaded + count` rows and a memtable holding about `loaded - count` tombstones; I expect the memtable difference B - A to be below one cap at f = 3 and to be of the order of one cap or more at cap 1 MiB, f = 30 (about 11,000 tombstones; the per-tombstone size is unknown to me, so no number is claimed).
> *B2g rows added (these refine the first row; the filed rows stay):*
>
> | Observation | Meaning |
> |---|---|
> | `sumWeights` of either arm exceeds its cap, or arm B's exceeds arm A's by one cap or more | Claim refuted: the check bounds the cache |
> | `sumWeights` of both arms at the cap (arm B within one statement of arm A), `loaded` A < B, positive control moves 1 : 4 : 10, and the post-GC live-heap difference B - A (cache + memtable) below one cap | Claim confirmed (the check bounds work only) |
> | Cache component equal, but the live-heap difference B - A is one cap or more and is explained by the memtable difference (memtable difference B - A within 25 % of the live-heap difference) | Claim holds for the cache and fails for total heap: the check indirectly limits heap through the tombstones of evictions. Verdict Not confirmed, Effect `caps only on some paths (bypass)` |
> | WARN absent in arm A, or `loaded` equal in A and B | Check not reached (n too small) or `pstmntSize` unpopulated: Not confirmed |

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

> **Amendment 2026-10-27 (B3a-B3h).**
> *B3a:* arm A runs from `~/s4-base`, arm B from `~/s4-psc-b` (both built, `bin/cassandra` from the copy), one node on loopback, `MAX_HEAP_SIZE=1G`, own `CASSANDRA_CONF`, data on local disk under `~/s4-pthr`, never under `/proj`.
> *B3b:* caps 1, 4 and 10 MiB x arms A and B (6 node starts, plus one seeding start); the 1 MiB pair is repeated once more for a repeat reading.
> *B3c (replaces the PREPARE-then-restart wording):* seed once, with the cap raised to 64 MiB so nothing is evicted: start arm A at 64 MiB, PREPARE M = 20,000 distinct fully qualified statements (`SELECT v FROM ks.t WHERE k = ? /* c<i> */`, 8 threads, protocol v5, no session keyspace), confirm `system.prepared_statements` holds M rows and the cache count is M, stop the node, and take a copy of the data directory. Each measured start restores a fresh copy of that data directory, so every start sees the same M rows (about 54 MiB of `pstmntSize` if s is near 2.7 KB, i.e. 54 x the 1 MiB cap and 5.4 x the 10 MiB cap). Writing the table through CQL is not possible (system keyspaces reject client writes).
> *B3d:* after each start: the `Preloaded N prepared statements in X ms` line and any `Detected prepared statement cache filling up` line from this start's part of `system.log`; JMX `PreparedStatementsCount`, `PreparedStatementsEvicted`, the memtable bean of `system.prepared_statements`; `jmap -histo:live` total live bytes and the instance count and shallow bytes of `QueryHandler$Prepared` (a full GC) 60 s after the listener is up; `GC.heap_info`; rows left in `system.prepared_statements` (cqlsh count).
> *B3f additions:* arm A preloads about `floor(1.1 x cap / s) + 1` statements (428 at 1 MiB if s = 2696) and logs the WARN; arm B preloads all M; in both, the count of `Prepared` instances after the full GC is about `cap / (s + 16)` (386 at 1 MiB) and equal across arms within a few statements; arm B at 1 : 4 : 10 MiB shows `Prepared` instances at about 1 : 4 : 10 (positive control); as in B2f, the memtable of arm B holds the tombstones of about `M - count` evictions and arm A far fewer, so the total live-heap difference B - A may be one cap or more at 1 MiB (same reading rules as the B2g rows added above).
> *B3g:* the B2g rows added above apply with "cache component" = `Prepared` instances x per-instance weight (and `PreparedStatementsCount`), "live-heap difference" = the `jmap -histo:live` total, "memtable" = the JMX bean.

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

**2026-10-27, stage 4 (results: `stage4-runtime-verification/results/prepared_statements_cache_size-loadpreparedstatements-preparedbytesloaded--autonomous.md`).** Amended before the runs (frozen sha256 `892c8eb3…beea`): rows must be written directly because evictions delete their rows (the check is unreachable with PREPARE-only loading); a leak-sized backlog (f = 30), a positive control on the preload path and rows for the memtable outcome were added.

- **Unit and cluster: Not confirmed, Effect `caps only on some paths (bypass)`; outcome class false negative (estimate `negative`).** The stage-3 reasoning about the cache holds: the Caffeine cache weight is identical with the check on or off (`sumWeights` equal in 11 unit pairs, `Prepared` instance counts equal in 4 cluster pairs) and follows `prepared_statements_cache_size` 1 : 4 : 10. What the stage-3 text missed: every cache eviction writes a delete into the memtable of `system.prepared_statements`, so with the check inert (arm B) a backlog of 54 x the cap (cluster, 20,000 rows) left 4.3 to 5.4 MB more live heap than with the check on, and 30 x at 10 MiB (unit, 116,682 rows) 32 MB more (3.07 caps); the difference tracks the memtable gauge within 11 to 15 % (35 % at 1 MiB, f = 30). The check, by stopping the loop at about 1.1 x cap, avoids those tombstones. At the filed workload (3 x cap) the difference is below one cap.
- Not measured: whether the memtable is flushed (and the heap freed) before it matters on a real node; attribution is by the memtable gauge, not by a heap dump.
- For stage 3: the "Ground" line is right for the cache but "only saves startup time and transient garbage" omits the system-table tombstones. Estimate left as filed.

