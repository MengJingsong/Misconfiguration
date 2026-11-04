<!-- file: cases/max-unsigned-short-prepare-boundTerms--autonomous.md -->
# FBUtilities.MAX_UNSIGNED_SHORT (bind-marker limit in prepare) — verification solution  <!-- file: cases/max-unsigned-short-prepare-boundTerms--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/cql3/QueryProcessor.java:758` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-26 |
| Estimate | `negative`: the constant is a wire-format bound on the number of `?` markers (a 2-byte count in the protocol), not a memory or disk budget; the memory a prepared statement holds is governed by the prepared-statement cache weight limit, not by this count. |
| Ground | The constant limits a count to what fits in an unsigned 16-bit field. Per-marker cost is small and fixed (one `ColumnSpecification` plus a few refs), so the worst case is a few MiB per statement. Total prepared-statement memory is capped separately by `prepared_statements_cache_size` (Caffeine `maximumWeight`, `QueryProcessor.java:113-116`). The constant is shared by unrelated checks (key length, clustering length, warnings count), so it is not a resource cap. |

## A. Constraint trace

**A1. The constraint.** `FBUtilities.MAX_UNSIGNED_SHORT` = `0xFFFF` = 65535, a `public static final int` constant, declared at `src/java/org/apache/cassandra/utils/FBUtilities.java:158`. Unit: count (markers) here, bytes or elements in other uses. Default is the literal; not derived. Not settable (no yaml key, `-D`, or JMX); changing it needs a source edit and rebuild.

**A2. What it caps.** Not a memory or disk resource directly. At the target it caps the number of bind variables (`statement.getBindVariables().size()`, `QueryProcessor.java:757`) of a statement being prepared. The reason is protocol framing: the prepared-result metadata and EXECUTE values count are 2-byte unsigned shorts (see `CBUtil.java` `readUnsignedShort` uses). Indirect effect: it bounds the size of one `Prepared` entry that goes into the prepared cache.

**A3. Mechanism.**
1. `prepare(String, ClientState)` (`QueryProcessor.java:728`) checks the cache by MD5 id (`:731-734`), returns the cached entry if both variants are present (`:738-753`).
2. Otherwise `parseAndPrepare` (`:754`) parses and builds the statement.
3. `boundTerms = statement.getBindVariables().size()` (`:757`); if `> 0xFFFF`, throws `InvalidRequestException("Too many markers(?)...")` (`:758-759`). The statement is rejected before it is stored.
4. Otherwise `storePreparedStatement` (`:763-778`) puts it in `preparedStatements`, a Caffeine cache with `maximumWeight(PREPARED_STATEMENT_CACHE_SIZE_BYTES)` and weigher `getSizeOfPreparedStatementForCache` = `ObjectSizes.measureDeep` (`:113-116`, `:949`). Eviction happens by weight, logged by a warning task (`:120-125`).
Bypass/overshoot: the check runs after parsing, so the parse of a very large query string has already allocated memory; the query-string size is bounded by the native transport frame/message limits, not by this constant. Statements built internally (`prepareInternal`, `:170-190`) skip this check.

**A4. Other consumers.** The prepared cache weight limit (`prepared_statements_cache_size`, `Config.java:584-585`, default derived in `DatabaseDescriptor.java:795-804`, max(1/256 heap, 10 MiB) per the comment) is the real memory cap for this object. Parser/AST garbage during prepare, client-request in-flight bytes (native transport limits), and other uses of the constant (`ClusteringPrefix.java:278-287`, `CacheService.java:504`, `ClientWarn.java:79-86`, `ByteBufferUtil.java:365`, `CassandraIndex.java:225,618`) are unrelated to this check.

**A5. Evidence beyond the source.** none.

## B. Verification solution

**B1. Claim under test.** Usage does not follow this constant: the memory held by prepared statements with many markers is bounded by the prepared-statement cache weight limit (`prepared_statements_cache_size`), not by the 65535 marker cap, and a statement just under the cap costs a small bounded amount (per-marker linear, a few MiB) regardless of node resources.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tag to local disk (e.g. `/local/work/cassandra-5.0.9`), `ant jar` there; write a JUnit test under `test/unit/org/apache/cassandra/cql3/` in the copy (never the shared tree). Run `ant testsome -Dtest.name=PrepareMarkerLimitTest`. JVM opts: `-Xmx1g`.

**B2b. Knobs.** (1) Marker count N in {1000, 65535, 65536}. (2) `prepared_statements_cache_size` in {1 MiB, 10 MiB, 100 MiB} via `DatabaseDescriptor` setup/yaml in the test (needs fresh JVM per value since the cache size is read in a static initializer, `QueryProcessor.java:113`).

**B2c. Workload.** Create table `t(k int primary key, v int)`; build `SELECT * FROM t WHERE k IN (?, ?, ..., ?)` with N markers (query string about 3N bytes, ~200 KB at N=65535). Call `QueryProcessor.prepare(query, ClientState.forInternalCalls())`. For the cache test, prepare many distinct statements (vary a literal in the string) with N=65535 until total exceeds the cache size.

**B2d. Observables and instruments.** Whether `InvalidRequestException` is thrown; `QueryProcessor.preparedStatementsCount()` (`:149`); `ObjectSizes.measureDeep(prepared)` per entry; `QueryProcessor.getPreparedStatementsMemoryUsage` style metrics if available (else the weigher); heap used after `System.gc()` via `Runtime`. Cannot observe the transient parse garbage exactly.

**B2e. Procedure.** 1. Build. 2. Prepare N=1000, 65535: record success and measureDeep. 3. Prepare N=65536: record exception text. 4. Fix N=65535, set cache 10 MiB, prepare 200 distinct statements; record count and total weight. 5. Repeat with 1 and 100 MiB. 6. Positive control: same loop with N=10 statements, many of them; count follows cache size.

**B2f. Predictions.** N=65535 succeeds; N=65536 throws "Too many markers(?)". measureDeep scales roughly linearly in N (order of 100 bytes to a few hundred bytes per marker, so single-digit MiB at 65535). With a fixed N, the number of retained statements and total weight scale with cache size (about size/weight), independent of the 0xFFFF constant. *[Amended 2026-10-26, see B2i: the per-marker figure and the "single-digit MiB" are a source estimate, 100 B to 1 KB per marker (6.5 to 65 MB at 65535), and are not a pass/fail criterion. The prediction is the relation: for every cache size, retained weight (sum of `key.size() + pstmntSize`) <= the cap; at a cap below the weight of one 65535-marker statement the statement is rejected by the size gate at `QueryProcessor.java:824-829` and nothing is retained; retained weight and count at M = 1000 and M = 10 follow the cap ratios 1 : 10 : 100.]*

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Retained weight tracks `prepared_statements_cache_size` and stays below it; per-statement weight is bounded by N*c | Claim confirmed (usage governed by cache cap, constant only bounds a count) |
| Retained weight grows past the cache size, or tracks 65535 irrespective of cache size | Claim refuted |
| N=65536 accepted | Source trace wrong |
| Control (small statements) does not move with cache size, or cache never fills | Not confirmed |
| *(added 2026-10-26)* At a cap below the weight of one 65535-marker statement, the prepare throws "Prepared statement of size ... larger than allowed maximum" (`QueryProcessor.java:824-829`) and the count is unchanged | The cache cap binds on a single statement; counts toward Claim confirmed together with the other conditions of row 1 |
| *(added 2026-10-26)* N=65536 rejected with exactly "Too many markers(?). 65536 markers exceed the allowed maximum of 65535" and the count unchanged, N=65535 accepted or size-gate rejected | Disallow evidence for the constant itself; required for Claim confirmed |
| *(added 2026-10-26)* Retained weight at M = 1000 and M = 10 is <= cap at all three caps but does not rise with the cap (ratio of retained weights across caps < 2 while the caps differ by 10x), or no eviction occurs at a cap | Not confirmed (cache not binding, or workload too small) |

**B2h. Controls.** Same statements with the cache at three sizes; a statement with few markers but a long string of equal weight to show weight, not marker count, drives eviction; warm up and GC before readings.

**B2i. Stage-4 audit amendments, 2026-10-26** (made before any reading; none depends on a reading; the added rows and the restated prediction are marked in B2f and B2g).
1. *Citations corrected (A3, B2d).* `storePreparedStatement` is `QueryProcessor.java:818-836`, not `:763-778`; the cache builder is `:112-118` (the byte limit `PREPARED_STATEMENT_CACHE_SIZE_BYTES` is a static initialiser at `:107`, read once per JVM); `prepareInternal` is `:425`; the weigher is `getSizeOfPreparedStatementForCache` at `:952-958` = `key.size() + pstmntSize`, and `pstmntSize = ObjectSizes.measureDeep(Prepared)` is computed at parse time (`:469`, `:949-950`). `QueryProcessor.getPreparedStatementsMemoryUsage` does not exist; the observables are `QueryProcessor.instance.getPreparedStatements()` (sum of `key.size() + pstmntSize`, as the closed `prepared_statements_cache_size` harness did), `preparedStatementsCount()`, and the CQL metrics `PreparedStatementsCount`, `PreparedStatementsEvicted`, `PreparedStatementsExecuted`, `PreparedStatementsRatio` (`CQLMetrics.java:32-63`). Checked and holding: `:728` (`prepare`), `:757-759` (the check and its message), `FBUtilities.java:158`, `DatabaseDescriptor.java:795-804`, `Config.java:584-585`, the warning task `:120-125`.
2. *A second gate added to A3 step 4.* `storePreparedStatement` first rejects a statement whose weight exceeds the cap (`:824-829`, `InvalidRequestException "Prepared statement of size %d bytes is larger than allowed maximum of %d MB"`), then stores it, then persists the query text to `system.prepared_statements` (`:832-833`, a memtable write outside the cache; an eviction deletes the row, `:132-139`, but the memtable keeps the written text and a tombstone until it flushes). So a 65535-marker statement is either retained or rejected by this gate, depending on its weight against the cap. Rows were added to B2g for it (marked). The claim B1 is unchanged: both outcomes show the cache cap, not the marker constant, as the binding limit.
3. *Knobs and arms (B2b, B2c).* Cache size in {1, 10, 100} MiB (10 MiB is also the `auto` value at `-Xmx1g`: `max(10, 1024/256)`), one fresh JVM per value. Marker count M in {10, 1000, 65535} for the load loops, and 65536 for the boundary prepare; M = 10 is the positive control (a small statement on the same cache, the knob of a closed Confirmed case). Statements are `SELECT * FROM ks.t WHERE k IN (?, ..., ?)` with M markers, fully qualified and prepared with `ClientState.forInternalCalls()` (no keyspace, so one cache entry per prepare), made distinct by a trailing `/* c<i> */`. Per JVM and per M: prepare one statement, record its weight w(M) and bind-variable count; then prepare distinct statements until the offered weight is 4 x cap or the count reaches 200,000 (M = 10), 20,000 (M = 1000) or 400 (M = 65535), whichever comes first (a time bound; if w(65535) > cap the loop stops after 5 consecutive size-gate rejections). Per arm record count, evicted, sum of weights, `measureDeep` of the cache map, live heap after two `System.gc()`, and the rows in `system.prepared_statements`.
4. *Boundary rows (B2e.2, B2e.3).* In every JVM: M = 65535 (success, or size-gate rejection recorded as such), M = 65536 (exact message "Too many markers(?). 65536 markers exceed the allowed maximum of 65535", count unchanged), and M = 1 as the lower anchor.
5. *Confirmation conditions (B2g row 1).* All of: (a) retained sum <= cap in every arm and JVM; (b) at M = 10 and M = 1000 evictions occurred at every cap and the retained sums rise with the cap (the ratio between the 100 MiB and the 1 MiB JVM above 20, for caps differing by 100x); (c) the 65536 rejection text; (d) at M = 65535 retained <= cap, or the size-gate rejection. Refuted if any retained sum exceeds its cap.
6. *Gaps named (B2d).* The transient parse garbage of a 200 KB query cannot be observed; the live-heap delta after GC includes the memtable copy of the persisted query text (outside the cache), so it is reported but is not a pass/fail value; the decisive reading is the sum of weights the weigher uses, plus the evicted counter.
7. *Build, paths (B2a).* The tree is a `copy-source.sh` copy at `~/s4-b9-bt/u`, built with `ant build-test`; the test class (`harness/max-unsigned-short-prepare-boundTerms--autonomous/PrepareMarkerLimitTest.java`) is copied into that tree only. `ant testsome` forks a 1 GiB JVM (`maxmemory` overrides `-Xmx`); each cache size is passed as a yaml copy with `-Dcassandra.config=file://...`. Leftover check by PID (other sessions run JVMs on the host).

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from a local copy; `-Xms2g -Xmx2g`; data, commitlog on local disk (e.g. 5 GiB reserved). `prepared_statements_cache_size: 10MiB` in `cassandra.yaml` for the baseline.

**B3b. Knobs.** `prepared_statements_cache_size` in {10MiB, 50MiB}; markers per statement in {10, 65535}; restart between values.

**B3c. Workload.** Python driver (or cqlsh-independent script) issuing PREPARE of distinct statements with 65535 markers, e.g. 500 distinct queries (each ~ few MiB, so well above 10 MiB total); repeat with 10-marker statements, 100000 distinct. Duration a few minutes. Also send one 65536-marker prepare to see the rejection.

**B3d. Observables and instruments.** JMX `org.apache.cassandra.metrics:type=CQL,name=PreparedStatementsCount` and `PreparedStatementsEvicted` (and `PreparedStatementsExecuted`); `jcmd <pid> GC.class_histogram` and heap after forced GC (`jcmd GC.run`) at intervals of 10 s; `system.log` warning "prepared statements discarded in the last minute". Cannot separate prepared-cache heap from other heap in a histogram exactly.

**B3e. Procedure.** 1. Build and start the node with 10MiB. 2. Baseline heap after GC. 3. Run the 65535-marker workload; sample heap and metrics. 4. Run the 65536 prepare; expect rejection. 5. Stop, set 50MiB, restart, repeat. 6. Repeat with 10-marker control. 7. Stop node, delete data.

**B3f. Predictions.** Retained prepared-statement heap stays near the configured cache size (10 MiB, then 50 MiB) with evictions and the warning log once exceeded; it does not grow with the number of prepares. Heap delta scales about 5x between the two settings. 65536 markers is rejected. *[Amended 2026-10-26, see B3i: cache sizes 10, 50 and 200 MiB; markers 10 (control), 1000, 65535, one node lifetime per pair. The prediction is the relation: retained weight (JMX `PreparedStatementsCount` times the per-statement weight, and the live `QueryHandler$Prepared` instance count in the post-GC histogram) is bounded by the cap and rises with it, at M = 10 and M = 1000 by the cap ratios 1 : 5 : 20; at M = 65535 either the same relation (count x weight <= cap) or, at a cap below one statement's weight, every prepare is rejected by the size gate and the count stays 0. The live heap delta is reported, not predicted to scale exactly (the persisted copies in `system.prepared_statements` are outside the cache, B3i.3). 65536 markers is rejected with "Too many markers(?)" and the count is unchanged.]*

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Post-GC heap delta plateaus near cache size and moves with it; evictions appear | Claim confirmed |
| Heap delta keeps growing with prepares, ignoring cache size | Claim refuted |
| Delta equal at both cache sizes (cache not binding) | Not confirmed; raise workload |
| 10-marker control also plateaus at cache size | Positive control: cap binds as expected |
| *(added 2026-10-26)* At a cap below the weight of one 65535-marker statement every prepare of that arm fails with "Prepared statement of size ... larger than allowed maximum" and `PreparedStatementsCount` stays 0 | The cache cap binds on a single statement; counts toward Claim confirmed together with the M = 10 and M = 1000 arms |
| *(added 2026-10-26)* 65536-marker prepare rejected with "Too many markers(?). 65536 markers exceed the allowed maximum of 65535", count unchanged | Disallow evidence for the constant itself; required for Claim confirmed |
| *(added 2026-10-26)* Count of live `QueryHandler$Prepared` objects keeps rising with the number offered after evictions began, or retained weight exceeds the cap | Claim refuted |

**B3h. Controls.** Fresh JVM per setting; same GC settings; repeat each run twice; confirm via metrics that evictions occurred.

**B3i. Stage-4 audit amendments, 2026-10-26** (made before any reading; none depends on a reading; the added rows and the restated prediction are marked in B3f and B3g).
1. *Values (B3a, B3b).* Cache size in {10, 50, 200} MiB (10 MiB is the `auto` value at `-Xmx2g`: `max(10, 2048/256)`; a third value was added because the file had two). Markers M in {10, 1000, 65535}. One node lifetime (wipe, start, load, stop) per (cache size, M) pair: 9 lifetimes, so that an arm's cache holds only its own statements. The 10-marker arms are the positive control. `-Xms2g -Xmx2g` (`MAX_HEAP_SIZE=2G`), data, commit log and hints on tmpfs (`/dev/shm/s4-b9-bt/node`), port slot 3: node on 127.0.3.1, JMX 7130, native 9042 on 127.0.3.1.
2. *Workload (B3c).* The bundled Python driver, native protocol 4 (a large request on v5 leaves unreturned direct buffers; the reading is heap, so v4), no keyspace on the session, 8 threads, paced at 800 prepares/s for M = 10 and 1000 and unpaced-by-threads for M = 65535 (each query is about 200 KB, so the server, not the pacing, limits). Statement `SELECT v FROM ks.t WHERE k IN (?, ..., ?)` on `ks.t (k int PRIMARY KEY, v int)`, distinct by a trailing comment. Stop rule per arm: evicted >= 3 x count with count > 0 and the last 10 samples (every 30 s) of count within 1 %, or 5 consecutive size-gate rejections with count 0, or offered reaches 150,000 (M = 10), 20,000 (M = 1000) or 400 (M = 65535). Then one 65536-marker prepare (arms with M = 65535 only) and one 100-repeat prepare of a single text (adds at most one entry).
3. *Observables (B3d).* JMX `PreparedStatementsCount`, `PreparedStatementsEvicted`, and `AllMemtablesHeapSize` of `system.prepared_statements` (every distinct prepare is persisted there, B2i.2, outside the cache); `jmap -histo:live <pid>` (forces a full GC) at the baseline and at the end, giving the total live bytes and the instance count of `org.apache.cassandra.cql3.QueryHandler$Prepared`; `jcmd <pid> GC.heap_info`; `system.log` for "Initialized prepared statement caches with N MiB" (knob read-back) and, after a 70 s wait past the end of the load, "prepared statements discarded in the last minute". Live heap delta and delta minus the memtable heap are reported; the gap (parse garbage, other consumers) is named, not hidden.
4. *Repeats (B3h).* Each value is run once in run 1; "repeat each run twice" is replaced by the 9 independent lifetimes (a repeat is run 2 if the conclusion needs it).
5. *Citations and cleanup (B3a, B4).* As B2i.1. Cleanup is by PID (`nodetool stopdaemon`, then `kill` of the recorded PID); `pgrep -f` is not used because other sessions run daemons on the host; the tmpfs directory is removed at the end.

**B4. Risks and cleanup.** Unit tier writes only to the local copy; cluster tier uses local disk with a known quota. Kill the Cassandra and test JVMs (`pgrep -f CassandraDaemon`, `pgrep -f junit`), remove the local copy and data dirs.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/cql3/QueryProcessor.java (lines 108-125, 700-800, grep hits)
- src/java/org/apache/cassandra/utils/FBUtilities.java (150-160)
- grep of MAX_UNSIGNED_SHORT across src/java; config/Config.java and config/DatabaseDescriptor.java grep hits for prepared_statements_cache_size

## D. Stage-4 feedback

**2026-10-26, stage 4 run 1 (node pc07, no run 2): unit tier Confirmed - does not cap; cluster tier Confirmed - does not cap. Outcome class: true negative.** Results: `stage4-runtime-verification/results/max-unsigned-short-prepare-boundTerms--autonomous.md`; harness: `stage4-runtime-verification/harness/max-unsigned-short-prepare-boundTerms--autonomous/`. The estimate stands as filed.
- Unit (caches of 1, 10, 100 MiB): the weight of one statement is 2,452 / 2,836 / 46,348 / 2,842,844 B at 1 / 10 / 1000 / 65535 markers (43 B per marker); 65536 markers rejected with the exact "Too many markers(?)" text in all JVMs; at a 1 MiB cache a 65535-marker statement is rejected by the cache's own size gate (`QueryProcessor.java:824-829`), 5 of 5, nothing retained; retained weight never exceeded the cap (0.97 to 1.00 of it where evicting), 100x between 1 and 100 MiB for 10- and 1000-marker statements.
- Cluster (10, 50, 200 MiB; 10, 1000, 65535 markers; nine node lifetimes): retained counts 1 : 5 : 20 with the cap (3,749 / 18,697 / 74,791 at 10 markers; 226 / 1,132 / 4,528 at 1000; 3 / 19 / 74 at 65535), evictions and the "discarded in the last minute" warning in every arm, the 65536 prepare rejected through the driver.
- Notes for stage 3: the size gate (`:824-829`) is a second cache limit on a single statement and a row `system.prepared_statements` is deleted on eviction (`:132-139`); a 65535-marker statement weighs 2.84 MB, so the minimum 10 MiB cache holds three; `QueryProcessor.getPreparedStatementsMemoryUsage` does not exist (B2d). Open points: the cluster per-entry weight was not measured (inferred from the unit tier, up to 3 % lower); the cache's entry count was seen a few entries above its settled value during a multi-threaded load (Caffeine eviction lag). Amendments: B2i, B3i (2026-10-26).

Stage-4 audit amendments of 2026-10-26 are B2i and B3i above. Citation checks (pinned `cassandra-5.0.9`): lines 728, 757-759 of `QueryProcessor.java`, 158 of `FBUtilities.java`, 795-804 of `DatabaseDescriptor.java`, 584-585 of `Config.java` hold; corrected: `storePreparedStatement` is `:818-836` (not 763-778), `prepareInternal` `:425` (not 170-190), the weigher `:952-958` (not 949).
