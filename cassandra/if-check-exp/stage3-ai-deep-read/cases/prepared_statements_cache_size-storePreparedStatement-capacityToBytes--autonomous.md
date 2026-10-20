# prepared_statements_cache_size — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/cql3/QueryProcessor.java:825` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code agent, 2026-10-19 |
| Estimate | `positive`: the entry bounds the total weighted size of the on-heap prepared-statement cache (Caffeine `maximumWeight`), and line 825 is a secondary per-statement guard that rejects any single statement heavier than the whole cache. Caveat: the weight is an estimate (`ObjectSizes.measureDeep`), so the cap is on estimated, not exact, heap. |

## A. Constraint trace

**A1. The constraint.** `prepared_statements_cache_size` (configuration entry; legacy name `prepared_statements_cache_size_mb`).
- Declared at `config/Config.java:584-585` (`DataStorageSpec.LongMebibytesBound`, default `null`, `@Replaces` the old `_mb` name). Template in `conf/cassandra.yaml:508` (blank = auto).
- Unit: MiB. Resolved at `config/DatabaseDescriptor.java:795-798`: null gives `max(10, maxMemory/1024/1024/256)` MiB (about 1/256 of max heap, floor 10 MiB); otherwise the configured MiB. `0` throws a `ConfigurationException` (lines 800-801, 808).
- The resolved value is written back to `conf` (line 804) and exposed by `getPreparedStatementsCacheSizeMiB()` (`DatabaseDescriptor.java:4178`).
- Set via yaml only, read once at startup (`DatabaseDescriptor` applyConfig); a change needs a restart. `QueryProcessor.PREPARED_STATEMENT_CACHE_SIZE_BYTES` (`QueryProcessor.java:107`) is fixed in the static initializer. I found no setter or JMX operation for it.
- Note: line 825 re-reads `DatabaseDescriptor.getPreparedStatementsCacheSizeMiB()` on each call, while the Caffeine bound (line 115) uses the value frozen at class init. In production they are the same.

**A2. What it caps.** On-heap memory held by `QueryProcessor.preparedStatements` (`Cache<MD5Digest, Prepared>`, line 93). The compared quantity is the sum of weights, where weight = `key.size() + Prepared.pstmntSize` (`QueryProcessor.java:952-957`). `pstmntSize` = `ObjectSizes.measureDeep(prepared)` (line 947-949, set at line 469).
- Line 825 compares one entry's weight to `capacityToBytes(MiB) = MiB*1024*1024` (lines 142-145).

**A3. Mechanism.**
1. Cache built at `QueryProcessor.java:113-118` with `maximumWeight(PREPARED_STATEMENT_CACHE_SIZE_BYTES)`, `weigher(getSizeOfPreparedStatementForCache)`, `executor(ImmediateExecutor.INSTANCE)` (eviction work runs on the caller thread), and a removal listener.
2. `storePreparedStatement` (818-838): computes id (823), then line 825 rejects with `InvalidRequestException` if one statement's weight exceeds the whole cache. The message prints `prepared.pstmntSize` and the MiB limit.
3. Otherwise `preparedStatements.get(id, k -> prepared)` (831) inserts. Caffeine then evicts entries (W-TinyLFU policy) until total weight is at or below the max. Evicted entries trigger `evictPreparedStatement` (lines 130-137): metric `preparedStatementsEvicted++`, a counter for a once-a-minute WARN (lines 119-126), and `SystemKeyspace.removePreparedStatement(key)`, which removes the row from the `system.prepared_statements` table.
4. On a new insert (`previous == prepared`) the statement is also persisted to `system.prepared_statements` (833).
5. Preload at startup (`preloadPreparedStatements`, 166-196) uses `preparedStatements.put` (182, 186), subject to the same weight bound. `SystemKeyspace.java:1927` logs when stored statements exceed the cache size.
6. Bypasses and overshoot:
   - Weight is an estimate. `measureDeep` walks the whole `Prepared` object graph and may over-count shared objects (schema/`TableMetadata`, selectors, etc.) or under-count other things. The real retained heap can differ from the weight.
   - Caffeine's bound is approximate under concurrency (eviction is maintenance-driven), so brief overshoot is possible.
   - A single entry of weight W <= cap is admitted. Caffeine may evict it immediately if W > its internal per-window/main region limits. This is not checked here.
   - Internal statements (`prepareInternal`, `isInternal`) use a separate path with `measure=false`; they are not in this cache and are uncapped by it (`parseAndPrepare`, 441-471). Verify at stage 4 which map `prepareInternal` uses.
   - The guard at 825 can throw `StringIndexOutOfBoundsException` from `queryString.substring(0, 200)` when the query is under 200 chars, which only matters for tiny caps. The guard cannot trigger with the 10 MiB floor on a short query.

**A4. Other consumers.** Everything else on the heap (memtables on heap, key/row/counter/chunk caches, index summaries, compaction, native-transport buffers). Parsed-but-uncached statements in flight, the `system.prepared_statements` table (memtable and sstables on disk, shrunk by eviction removals but with tombstones until compaction), and per-connection state in `ClientState`.

**A5. Evidence beyond the source.** `conf/cassandra.yaml:495-508` comments (heap fraction, "discarded in last minute" warning). Test: `test/unit/org/apache/cassandra/cql3/PreparedStatementsTest.java`. Caffeine docs (maximumWeight/weigher): https://github.com/ben-manes/caffeine/wiki/Eviction. CASSANDRA-17734 is cited in the code (Settings virtual table). Not otherwise researched.

## B. Verification solution

**B1. Claim under test.** The total estimated weight of `QueryProcessor.preparedStatements` never stays above `prepared_statements_cache_size` (MiB*2^20) after insertions settle, and the real retained on-heap bytes of the cache grow roughly in proportion to that value until it is reached and stay flat beyond. A single statement weighing more than the cap is rejected at line 825 and is never cached.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. `git clone` the pinned tag to local disk (for example `/local/scratch/c509`); never build in the shared tree. `ant jar` then `ant build-test`. Add a JUnit class `PreparedCacheCapTest extends CQLTester` under `test/unit/org/apache/cassandra/cql3/` in the local clone (the pattern of `PreparedStatementsTest.java`). Run `ant testsome -Dtest.name=org.apache.cassandra.cql3.PreparedCacheCapTest`. JVM: `-Xmx1g`. Set the knob before DatabaseDescriptor init: `-Dcassandra.config=file:///.../cassandra-capN.yaml` with `prepared_statements_cache_size: N`.

**Amendment 2026-10-19 (step-0 audit) — B2a.** `test/conf/cassandra.yaml:48` already sets `prepared_statements_cache_size: 1MiB`, so the per-value yaml is a copy of `test/conf/cassandra.yaml` with that one line changed (`<N>MiB`), passed through `-Dtest.jvm.args=-Dcassandra.config=file://<copy>`. The default-run copy has the line removed (auto, `max(10, 1024/256)` = 10 MiB at `-Xmx1g`). Reason: the case's text implied a bare yaml; nothing else may differ from the test yaml.

**B2b. Knobs.** `prepared_statements_cache_size` of 1, 2, 4 and 8 MiB (one JVM per value, since it is frozen at class init). The 10 MiB auto default is a separate run (leave unset, `-Xmx1g` gives max(10,4)=10 MiB).

**B2c. Workload.** (Amended 2026-10-19: every statement is fully qualified (`ks.t`) and the `ClientState` has no keyspace, so `QueryProcessor.prepare` stores exactly one cache entry per statement. With a session keyspace set, `prepare` (`QueryProcessor.java:760-779`) stores a second entry for the same `Prepared` under the keyspace-salted id, which would double the entries and break `n = 4 * cap_bytes / w`; the audit found this by reading `prepare()`.) One table. Prepare distinct statements via `QueryProcessor.prepare(query, ClientState.forInternalCalls())`, using unique text such as `SELECT v FROM ks.t WHERE k = ? /* unique-i */` so each statement has a different id. Per-statement weight w is read from `Prepared.pstmntSize` (expected a few KiB to tens of KiB). Prepare n = 4 * (cap_bytes / w) statements, so total offered weight is four times the cap. For the 825 guard: build one statement with an IN list or a huge column list whose measured weight exceeds cap (for 1 MiB cap, roughly several thousand selected columns or a very long literal-free query; calibrate by iterating until `pstmntSize > cap`).

**B2d. Observables and instruments.**
- Sum of weights: `QueryProcessor.getPreparedStatements()` (line 241) values, summing `key.size()+pstmntSize` through reflection or the `@VisibleForTesting` surface; also `preparedStatementsCount()` (148).
- `QueryProcessor.metrics.preparedStatementsEvicted`.
- Count of rows in `system.prepared_statements`.
- Return of `storePreparedStatement` or the `InvalidRequestException` text.
- Cannot be observed directly: true retained heap (weight is an estimate). Cross-check with `ObjectSizes.measureDeep` on the whole map as an independent view, and with a heap histogram in B2e step 6.
- **Amendment 2026-10-19 — instrument for the real-heap reading.** No heap analyser (MAT) is installed on the node, and none is installed for this case; the unit-tier real-heap reading is the in-JVM live-heap delta: `used = Runtime.totalMemory() - freeMemory()` after two `System.gc()` calls, with the cache full minus the same reading with the cache empty (`clearPreparedStatementsCache()`, then the same two GCs), together with `ObjectSizes.measureDeep(map)` and `jmap -histo:live` totals for `Prepared`-reachable classes. Reason: B2e step 6 named `jcmd`/`jmap` only; the delta needs a defined formula.

**B2e. Procedure.**
1. Write the yaml with the knob; start the test JVM with `-Dcassandra.config`.
2. Create keyspace and table; clear the cache with `QueryProcessor.clearPreparedStatementsCache()` (970).
3. Prepare n unique statements one at a time; after each 50, record sum-of-weights, count, evictions, system-table row count.
4. Prepare the oversize statement; record exception and whether the id is in the cache.
5. Repeat for each knob value.
6. After step 3 (settled, `System.gc()` twice), record `jcmd <pid> GC.class_histogram` or `jmap -histo:live` totals, and compute retained delta versus the same JVM with an empty cache.

**B2f. Predictions.**
- After settle, sum-of-weights <= cap_bytes (small transient overshoot not persisting beyond one more insert). For 1/2/4/8 MiB: <= 1048576 / 2097152 / 4194304 / 8388608.
- Count is about cap_bytes / w for each value (linear in cap); evictions about n - count; system-table rows about equal to count.
- The oversize statement is rejected with "larger than allowed maximum of N MB" and not present in the cache.
- Live-heap delta of the cache objects is within about 2x of sum-of-weights and scales linearly with the knob.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Sum-of-weights plateaus at <= cap and count scales linearly with cap | Mechanism works as traced; claim supported at the operand level |
| Sum-of-weights exceeds cap persistently | Claim wrong (weigher or bound not enforced) |
| Oversize statement is cached or no exception | Line 825 guard not effective; claim wrong |
| Sum-of-weights plateaus but live-heap delta is much larger than weight (more than 2x) or flat vs knob | Weight is not a faithful proxy; cap exists on the estimate but not on real heap (refines claim, report as partial) |
| Cap never reached (n too small), or no evictions | Not confirmed; raise n |
| Sum-of-weights plateaus at <= cap but live-heap delta is less than half of sum-of-weights (**added 2026-10-19, before run 1, from A3's note that `measureDeep` walks the shared `Prepared` graph and may over-count**) | The weight over-counts shared objects; the cap holds real heap at or below the estimate, with a conservative ratio. Report the ratio; the case is Confirmed on the mechanism and the cap bounds real usage from above, but the "proportional to the knob" half is read from the delta, not the weight |

**B2h. Controls.** (a) Same workload with a very large cap (for example 64 MiB): no evictions, count = n, which shows the limit, not workload, causes eviction. (b) Re-preparing the same text does not add entries (rules out duplicates). (c) Same JVM flags and heap in every run. (d) The weight-vs-heap check in step 6 rules out reading only the estimate.

### B3. Cluster tier

**B3a. Environment and build.** One node (second optional), Linux, JDK 11, built from a local clone: `ant jar`. Node data, commitlog, hints on local disk of known size (at least 20 GiB free), `-Xms2g -Xmx2g` (jvm11-server.options), `-XX:+UseG1GC`. Python `cassandra-driver` (or `cassandra-stress` from the same build) as client. Disable the `auto` value by setting the knob explicitly in `cassandra.yaml`.

**B3b. Knobs.** `prepared_statements_cache_size`: 1, 4, 16, 64 MiB (restart between values; wipe `data/`, `commitlog/`, `saved_caches/` between runs so the `system.prepared_statements` preload does not carry over). Heap fixed at 2 GiB so the auto value (10 MiB) is not confounded.

**B3c. Workload.** (Amended 2026-10-19: the session has **no keyspace** (no `USE`, `Cluster.connect()` with none) and every statement is fully qualified, so each PREPARE adds one cache entry; stop condition: the run for a value ends when `PreparedStatementsEvicted` >= 5 x `PreparedStatementsCount` and Count has been constant over 10 consecutive 30 s samples, or at 200,000 statements; reaching 200,000 with the counters not met is Not confirmed for that value, never Confirmed. Client: the driver bundled in the clone's `lib/` (`cassandra-driver-internal-only-*.zip`), as the other cluster tiers do.) A client opens a native-protocol session and sends PREPARE requests with unique query strings (bind markers kept, unique trailing comment), 200,000 distinct statements at about 2-5 KB weight each (about 400 MB-1 GB offered, above even the 64 MiB cap by an order of magnitude; confirm by checking the `preparedStatementsEvicted` counter rises). Several threads (8) via the driver. Also execute a small set of the prepared ids (hot set) to make sure eviction does not break correctness. Duration until the count is stable, about 10 minutes per value. Oversize case: one PREPARE with a very large statement above the cap (for 1 MiB: tens of thousands of columns in a SELECT, or equivalent).

**B3d. Observables and instruments.**
- JMX/`nodetool`: `org.apache.cassandra.metrics:type=CQL,name=PreparedStatementsCount`, `PreparedStatementsEvicted`, `PreparedStatementsExecuted` (via `nodetool sjk mx` or jmxterm); also `nodetool info` heap.
- Real heap: `jcmd <pid> GC.class_histogram` (live) before and after, with focus on `Caffeine` node classes, `Prepared`, `SelectStatement`, parse trees; and a heap dump (`jcmd GC.heap_dump`) on local disk, opened with Eclipse MAT to read retained size of the `preparedStatements` Cache. Dump size about 2 GiB, so check disk first.
- **Amendment 2026-10-19 — real-heap reading on the node.** No MAT is installed, and none is installed for this case. The real-heap reading is the live used heap after `jcmd <pid> GC.run` twice (`jcmd <pid> GC.heap_info`, and the `jmap -histo:live` total), at each knob value, minus the baseline taken at the same point after startup with no PREPARE (same start state, same JVM flags), together with the live instance count and shallow bytes of the `Prepared` class and of the statement classes in the histogram. This replaces the heap-dump-and-MAT retained-size reading of B3e step 4 and B3f's third bullet; the prediction (about the cap within about 2x, linear across 1:4:16:64) is unchanged. Reason: the instrument was not available.
- Disk: `du` of `data/system/prepared_statements-*` and row count via `SELECT count(*) FROM system.prepared_statements`.
- Cannot observe directly: per-entry weight (use unit tier).

**B3e. Procedure.**
1. Clone, `ant jar`, create `conf/cassandra.yaml` with the knob and local directories; start the node and wait for `Initialized prepared statement caches with N MiB` in `system.log`.
2. Record baseline: `GC.class_histogram`, JMX counters.
3. Run the PREPARE workload; sample JMX every 30 s.
4. When counters stabilize, force `jcmd GC.run` twice, take a class histogram and, for 1 and 64 MiB, a heap dump; read the retained size of the cache.
5. Send the oversize PREPARE; record the error message.
6. Stop the node, wipe data dirs, restart with the next value; repeat.
7. Restart check: restart without wiping at 1 MiB and confirm the preload log (`Preloaded N prepared statements`) and `SystemKeyspace.java:1927` warning appear.

**B3f. Predictions.**
- `PreparedStatementsCount` plateaus at about cap_bytes / w_avg (about 200-500 for 1 MiB; about 13k-32k for 64 MiB); it does not rise toward 200,000.
- `PreparedStatementsEvicted` is about 200,000 - count.
- Retained size of the cache from the heap dump is about the cap, within about 2x, and scales linearly with the four values (1:4:16:64).
- `system.prepared_statements` row count tracks count (eviction deletes rows) while disk size may exceed it until compaction.
- The oversize PREPARE gets an error "Prepared statement of size ... larger than allowed maximum of N MB".
- Total heap used does not grow with the offered workload beyond the plateau.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Count and retained heap plateau, scale with the knob | Claim supported on the actual resource |
| Count grows with offered statements regardless of knob, or heap keeps growing | Claim wrong |
| Count plateaus but retained heap per entry far larger than weight (more than 2x), or flat across knob values | Cap bounds the estimate, not real heap; partial, report ratio |
| Oversize PREPARE accepted | Guard at 825 fails; claim wrong |
| Evicted counter stays 0 | Cap not reached; increase offered load, not confirmed |
| Heap difference swamped by GC noise | Repeat with forced GC and the heap dump method (not available; repeat three times and take the median) |
| Count plateaus, evictions match, but live-heap delta is less than half of the cap (**added 2026-10-19, before run 1**) | The weight over-counts shared objects; the cap is conservative on real heap. Report the ratio; the knob still bounds usage from above |

**B3h. Controls.** (a) Repeated PREPARE of the same text (no growth) separates caching from load. (b) The 64 MiB run is a control with minimal eviction. (c) Fixed heap size and G1 settings. (d) Comparing before/after the same workload with a trivial no-PREPARE load (plain unprepared queries) shows other heap consumers are flat.

**B4. Risks and cleanup.** Heap dumps are about the heap size (2 GiB each): write them only to a local disk with room, delete afterward. The system table grows with 200k rows before eviction; keep data dirs on a local disk of known size (20 GiB) and wipe between runs. Build only in the local clone. After each run stop the node (`nodetool drain`, then kill the process), and verify with `pgrep -f CassandraDaemon` and `jps` that nothing remains; remove the clone, data dirs and dumps.

## C. Sources read

- `src/java/org/apache/cassandra/cql3/QueryProcessor.java` (lines 90-200, 441-472, 680-840, 935-1000)
- `src/java/org/apache/cassandra/config/Config.java:584-585`
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:788-812, 4178`
- `conf/cassandra.yaml:495-508`, `conf/cassandra_latest.yaml:515`
- `src/java/org/apache/cassandra/db/SystemKeyspace.java:1927` (grep only)
- `test/unit/org/apache/cassandra/cql3/PreparedStatementsTest.java` (listing only)
- https://github.com/ben-manes/caffeine/wiki/Eviction (from knowledge, not fetched)

## D. Stage-4 feedback

**Stage 4 closed 2026-10-19** ([results](../../stage4-runtime-verification/results/prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous.md)); estimate `positive` held. **Unit tier: Confirmed** (weights 0.9998 × cap at 1 · 2 · 4 · 8 · 10 MiB, count ⌊cap/w⌋, oversize refused, 64 MiB control no evictions). **Cluster tier: Confirmed for the cache** (count 395 · 1,581 · 6,326 · 25,305 at 1 · 4 · 16 · 64 MiB, rows equal count, knob-dependent heap 0.80 × weights, restart preloads 395), **with a bypass:** the same PREPARE load grows live heap by about 93 MB at 151,819 statements (≈ 614 B each) independent of the knob, through the memtable of `system.prepared_statements` (one row per PREPARE); B3f's last bullet ("total heap does not grow beyond the plateau") is refuted. Notes for stage 3, not applied: A4 should name that table as the dominant other consumer; the oversize PREPARE reaches the guard only at caps below the 16 MiB transport limit (16 and 64 MiB were refused by the transport); the cache's own retained size needs a heap analyser. Amendments of 2026-10-19 (B2a, B2c, B2d, B2g, B3c, B3d, B3g) were made at the step-0 audit; the frozen hash is the one in `_INDEX.md` §4 and this section was added after it.
