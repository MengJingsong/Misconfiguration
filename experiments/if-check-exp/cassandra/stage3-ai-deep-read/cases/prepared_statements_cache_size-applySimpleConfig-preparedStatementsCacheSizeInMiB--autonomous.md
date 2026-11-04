# prepared_statements_cache_size (startup validation in applySimpleConfig) — verification solution  <!-- file: cases/prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:800`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L800) (`800#1`, `preparedStatementsCacheSizeInMiB == 0`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5), Claude Code at Meta (version string not available in the sandbox), 2026-10-25, band D triage |
| Estimate | `positive`: the value checked at line 800 becomes the `maximumWeight` (bytes) of the Caffeine cache holding prepared statements on heap (`QueryProcessor.java:107,112-118`), and a single statement larger than it is refused (`QueryProcessor.java:825-829`), so heap held by cached statements is capped by it. Line 800 itself only rejects an explicit `0MiB` (the auto default is `max(10, heap/256)` MiB, never 0). |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `prepared_statements_cache_size`, configuration entry ([`Config.java:584-585`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L584-L585), `DataStorageSpec.LongMebibytesBound`, default `null` = auto; legacy key `prepared_statements_cache_size_mb`), yaml at `conf/cassandra.yaml:508`. Unit MiB. Auto value: `max(10, Runtime.maxMemory()/1MiB/256)` ([`DatabaseDescriptor.java:795-798`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L795-L798)). Explicit `0MiB` is rejected through the `NumberFormatException` path (`:800-801`, `:806-810`); negatives are already refused by the parser ([`DataStorageSpec.java:42`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DataStorageSpec.java#L42), `:72`, `:107-108`); units below MiB are refused ([`DataStorageSpec.java:86`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DataStorageSpec.java#L86)). The resolved value is written back for the settings virtual table (`:804`) and served by `getPreparedStatementsCacheSizeMiB()` (`:4178-4181`). Read into a static at `QueryProcessor` class init ([`QueryProcessor.java:107`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L107)), so a change needs a restart; no JMX setter.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Heap held by the prepared-statement cache. Operand at line 800: the resolved size in MiB. Runtime operand: the Caffeine weighted size, i.e. sum over entries of `key.size() + Prepared.pstmntSize` (`QueryProcessor.java:952-958`), where `pstmntSize` is `ObjectSizes.measureDeep(prepared)` (`:947-950`).

**A3. Mechanism.**
1. Startup: resolve size ([`DatabaseDescriptor.java:796-798`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L796-L798)); if 0 → `ConfigurationException` "prepared_statements_cache_size option was set incorrectly…", node does not start (`:800-810`).
2. `PREPARED_STATEMENT_CACHE_SIZE_BYTES = size * 1024 * 1024` ([`QueryProcessor.java:107`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L107), `:142-145`); the cache is built with `maximumWeight(PREPARED_STATEMENT_CACHE_SIZE_BYTES)` and the weigher above (`:112-118`). Caffeine evicts when the weighted size exceeds the maximum; evictions increment `PreparedStatementsEvicted` (`:132-137`, [`CQLMetrics.java:44`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/CQLMetrics.java#L44)) and a per-minute warning is logged ([`QueryProcessor.java:120-126`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L120-L126)).
3. `storePreparedStatement` refuses a single statement whose weight exceeds the cap with `InvalidRequestException` ([`QueryProcessor.java:825-829`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L825-L829)).
- Overshoot: Caffeine eviction is amortised (the weighted size can briefly exceed the maximum between insertion and maintenance); the weight is `measureDeep` of the `Prepared` object, which may share objects (schema metadata) with the rest of the heap, so actual retained heap can differ from the weight. Prepared statements are also persisted to `system.prepared_statements` ([`QueryProcessor.java:831-833`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L831-L833)), on disk, outside this cap.

**A4. Other consumers.** Other caches (key/counter/paxos), memtables, the driver-side statement cache (client heap, not node), the `system.prepared_statements` table on disk (`SystemKeyspace.writePreparedStatement`, `QueryProcessor.java:833`).

**A5. Evidence beyond the source.** CASSANDRA-17734 (settings virtual table, cited at `DatabaseDescriptor.java:803`). See also the existing case `prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous.md` for the runtime check at `QueryProcessor.java:825`.

## B. Verification solution

**B1. Claim under test.** (a) `prepared_statements_cache_size: 0MiB` prevents startup with the message at `DatabaseDescriptor.java:808`; any value ≥ 1 MiB is accepted. (b) With a value C MiB, the summed weight of cached prepared statements never exceeds C MiB (beyond one entry of transient slack), and the retained heap of `QueryHandler$Prepared` instances scales with C rather than with the number of distinct statements prepared.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant ≥ 1.10. `git clone --depth 1 --branch cassandra-5.0.9 https://github.com/apache/cassandra.git /local/c509 && cd /local/c509 && ant jar` (never in the shared clone). Probe sources in `/local/probe` (outside the clone). `CP="/local/c509/build/classes/main:/local/c509/build/lib/jars/*"`. Base yaml: `cp /local/c509/conf/cassandra.yaml /local/probe/base.yaml` and set `data_file_directories: [/local/probe/data/data]`, `commitlog_directory: /local/probe/data/commitlog`, `saved_caches_directory: /local/probe/data/saved_caches`, `hints_directory: /local/probe/data/hints`, `cdc_raw_directory: /local/probe/data/cdc_raw`.

Program 1 (`/local/probe/src/ConfigProbe.java`), the startup check:
```java
import org.apache.cassandra.config.DatabaseDescriptor;
public class ConfigProbe {
  public static void main(String[] a) throws Exception {
    try { DatabaseDescriptor.daemonInitialization();
          System.out.println("OK " + a[0] + "=" + DatabaseDescriptor.class.getMethod(a[0]).invoke(null)); }
    catch (Throwable t) { Throwable c = t; while (c.getCause() != null) c = c.getCause();
          System.out.println("REJECT " + t.getClass().getSimpleName() + ": " + t.getMessage() + " / root: " + c); }
  }
}
```
Compile: `javac -cp "$CP" -d /local/probe/classes /local/probe/src/ConfigProbe.java`. Run: `java -Xms1G -Xmx1G -cp "$CP:/local/probe/classes" -Dcassandra.config=file:///local/probe/<v>.yaml -Dcassandra.storagedir=/local/probe/data -Dlogback.configurationFile=/local/c509/test/conf/logback-test.xml ConfigProbe getPreparedStatementsCacheSizeMiB`.

Program 2, the mechanism: JUnit class `/local/c509/test/unit/org/apache/cassandra/probe/PreparedCacheCapProbeTest.java` extending `org.apache.cassandra.cql3.CQLTester` (local clone only). Knob value set by editing `prepared_statements_cache_size:` in `/local/c509/test/conf/cassandra.yaml` (currently `1MiB`, `test/conf/cassandra.yaml:48`). Run with `cd /local/c509 && ant testsome -Dtest.name=org.apache.cassandra.probe.PreparedCacheCapProbeTest`; stdout lands in `build/test/output/TEST-org.apache.cassandra.probe.PreparedCacheCapProbeTest.xml`.

**Amendment 2026-10-25 (step-0 audit) — B2a, this host's paths and the run recipe.** Clone `C=$W/cassandra-run10` (`W=~/Library/Caches/stage4`; `git clone --branch cassandra-5.0.9 ~/cassandra-src $C`, HEAD `b5f2a54210`), built with `source $W/env.sh; ant -Dlocal.repository=$W/m2 build-test` (a superset of `ant jar`; `testsome` needs the test classes). `/local/c509` reads `$C`; `/local/probe` reads `P=$W/probe-psca` (outside the clone). Program 1's source is kept at `harness/prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous/ConfigProbe.java` (text exactly as above) and compiled to `$P/classes`; `base.yaml` is `$C/conf/cassandra.yaml` with the five directory keys removed and re-added under `$P/data/`; the three variants differ from it only in the `prepared_statements_cache_size:` line (`0MiB`, `1MiB`, or the line left as shipped, empty = auto). Program 2's source is kept in the same harness folder and copied to `$C/test/unit/org/apache/cassandra/probe/`; it writes its `STAGE4` lines also to the file named by `-Dstage4.out` (passed with `-Dtest.jvm.args`). Each knob value is its own `ant testsome` (own forked JVM), because `daemonInitialization()` runs once per JVM (`DatabaseDescriptor.java:245-260`) and `QueryProcessor` reads the size into a static at class init (`QueryProcessor.java:107`). The knob is set by `sed` on the one line of `$C/test/conf/cassandra.yaml` (`:48`), removed for auto, and restored with `git checkout` after the last value. Reason: B2a's paths and network clone do not exist on this host, and the JVM split was left open.

**Amendment 2026-10-25 (stage 4 run 1, runbook fix; B2f/B2g unchanged) — B2a, Program 1's `java` command.** As written, all three variants print `REJECT ExceptionInInitializerError: null / root: java.lang.IllegalAccessException: access to public member failed: jdk.internal.ref.Cleaner.clean…, from org.apache.cassandra.io.util.FileUtils` on JDK 11: `FileUtils`' static initialiser needs `jdk.internal.ref` exported, which the plain `java` command does not do (the node gets it from `conf/jvm11-server.options`, tests from `build.xml:244-261`). Program 1 runs with the seventeen `--add-exports`/`--add-opens` flags of `build.xml:244-261` added before `-cp`; nothing else changes. The unit tier restarts from Program 1.

**B2b. Knobs.** Program 1: `prepared_statements_cache_size` ∈ {`0MiB` (boundary, must reject), `1MiB` (smallest accepted), unset (auto: expect `max(10, 1024/256)=10`)}. Program 2: C ∈ {1MiB, 4MiB, 16MiB} (spans 16×, all small enough that the workload exceeds them).

**Amendment 2026-10-25 (step-0 audit) — B2b, the default added to Program 2.** Program 2 also runs with the line removed (auto). Its expected value is `max(10, ⌊maxMemory/2^20/256⌋)` read inside the JVM (`DatabaseDescriptor.java:796-797`); for the 1 GiB `testsome` JVM that is 10 MiB. Values: {1, 4, 16 MiB, auto}. Reason: group A asks for at least three values including the default.

**B2c. Workload.** In the test: `createTable("CREATE TABLE %s (k int PRIMARY KEY, " + 50 text columns c0..c49 + ")")`; then for i in 0..N-1 prepare the distinct string `"SELECT c0,…,c49 FROM ks.tbl WHERE k = ? AND c0 = '" + i + "' ALLOW FILTERING"` via `QueryProcessor.instance.prepare(q, ClientState.forInternalCalls())`. Record the per-statement weight `w = id.size() + QueryProcessor.instance.getPrepared(id).pstmntSize` for the first statement (expected order of tens of KiB for 50 columns). Choose N = ceil(4 × 16 MiB / w) (for w ≈ 20 KiB, N ≈ 3300) so that even C = 16 MiB is exceeded 4×.

**Amendment 2026-10-25 (step-0 audit) — B2c, exact workload.** Table `CREATE TABLE %s (k int PRIMARY KEY, c0 text, c1 text, …, c49 text)`; statement i is `SELECT c0, c1, …, c49 FROM <KEYSPACE>.<currentTable()> WHERE k = ? AND c0 = '<i>' ALLOW FILTERING`, fully qualified, prepared with `ClientState.forInternalCalls()` (no keyspace), so each prepare stores exactly one cache entry (`QueryProcessor.java:760-767`). Statement i = 0 is the calibration: `w = id.size() + pstmntSize` of that entry (`QueryProcessor.java:952-958`), and the test checks that the cache holds exactly 1 entry after it. `N = ceil(4 × 16 × 2^20 / w)` in every JVM (the same rule at every value), i = 0 … N−1. Reason: "ks.tbl" and the column type were placeholders; the keyspace rule is the HANDOFF §10 lesson.

**B2d. Observables and instruments.** After every 100 prepares: `QueryProcessor.preparedStatementsCount()` (count), and the estimated weight `count × w` (the weigher is not exposed; the preparedStatements field is private, so optionally read it by reflection and call `policy().eviction().get().weightedSize()`). `QueryProcessor.metrics.preparedStatementsEvicted.getCount()`. At the end, `System.gc()` then `Runtime.totalMemory()-freeMemory()` as a coarse heap reading. Cannot observe directly: exact retained heap of shared metadata.

**Amendment 2026-10-25 (step-0 audit) — B2d, instruments.** weightedSize is read exactly, by reflection on the private `QueryProcessor.preparedStatements` (`QueryProcessor.java:93`): `policy().eviction().get().weightedSize().getAsLong()`; the sum of `key.size() + pstmntSize` over `getPreparedStatements()` (`:239-242`) is logged beside it as a cross-check. Samples after every 100 prepares and after the last; evictions are the delta of `QueryProcessor.metrics.preparedStatementsEvicted` since the start of the loop. The coarse heap reading (B2d) is logged without a prediction. Reason: the file left the weight reading optional; B2f's prediction is about it.

**B2e. Procedure.**
1. Program 1 with the three yaml variants; record output line.
2. For each C: set the test yaml, run Program 2, extract the series (prepares, count, weightedSize, evictions).
3. `git -C /local/c509 checkout test/conf/cassandra.yaml`.

**Amendment 2026-10-25 (step-0 audit) — B2e, order.** Per Program 2 JVM: calibration → main series (N) → B2h control (a) → B2h control (b). Program 1's three variants run first, each its own `java` process.

**B2f. Predictions.** Program 1: `0MiB` → `REJECT ConfigurationException: prepared_statements_cache_size option was set incorrectly to '0MiB'…`; `1MiB` → `OK …=1`; unset with `-Xmx1G` → `OK …=10`. Program 2: weightedSize ≤ C×2^20 + w at every sample; count plateaus at ≈ C×2^20 / w (±10%), i.e. roughly 4× more cached statements at 4 MiB than at 1 MiB and 16× at 16 MiB; evictions ≈ N − plateau count.

**Amendment 2026-10-25 (step-0 audit) — B2f, exact values (prediction unchanged in substance).** Program 1, `0MiB`: the line starts `REJECT ConfigurationException: prepared_statements_cache_size option was set incorrectly to '0MiB', supported values are <integer> >= 0.` (`DatabaseDescriptor.java:806-809`; `DataStorageSpec.toString()` gives `0MiB`, `DataStorageSpec.java:160-163`); `1MiB` → `OK getPreparedStatementsCacheSizeMiB=1`; unset → `OK getPreparedStatementsCacheSizeMiB=10`. Program 2, at each C ∈ {1, 4, 16 MiB, auto}: (i) weightedSize ≤ C·2^20 + w at every sample; (ii) final count within ±10 % of C·2^20/w; (iii) evicted = N − final count (±1 %; each distinct prepare inserts once and every size eviction increments the counter, `QueryProcessor.java:132-137`), and > 0; (iv) count(C)/count(1 MiB) within ±10 % of C/1 MiB (4, 16, and 10 for auto). Reason: "≈" had no tolerance for (iii) and (iv).

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| 0MiB rejected, 1MiB accepted, auto = 10 | startup check behaves as traced |
| weightedSize plateaus at ≈ C and scales with C; evictions > 0 | claim holds (cap governs the operand) |
| weightedSize grows past C + w and keeps growing with N | claim wrong |
| count plateaus but not proportional to C | weigher not the binding factor (e.g., size-based eviction elsewhere); investigate |
| N reached without evictions | workload too small; recompute N from measured w |

**Amendment 2026-10-25 (step-0 audit) — B2g, rows added (the rows above are unchanged).** Row 2 ("claim holds") needs B2f (i)–(iv) at every C, Program 1 as predicted (row 1) and both B2h controls as predicted. Added rows:
| Observation | Meaning |
|---|---|
| `0MiB` accepted (OK line) | claim (a) refuted (B1 (a)) |
| `1MiB` rejected, or auto ≠ the expected value | claim (a) not confirmed as traced (record the line) |
| Program 1 fails for a reason other than the knob (another configuration error, class-path failure) | Program 1 invalid; runbook defect |
| weightedSize ≤ C·2^20 + w at every sample but evicted ≠ N − count beyond 1 % | the counter does not follow the cache; Not confirmed |
| a B2h control misses its frozen expectation | tier Invalid |

**B2h. Controls.** Same workload with C unchanged but N = plateau/2: no evictions (shows evictions are cap-driven). Prepare the same string N times: count stays 1 (shows distinct statements drive growth).

**Amendment 2026-10-25 (step-0 audit) — B2h, exact controls.** Both run in each Program 2 JVM after the main series. (a) `QueryProcessor.clearPreparedStatementsCache()` (an explicit removal: the listener increments the eviction counter only for `cause.wasEvicted()`, `QueryProcessor.java:132-137`, `:970-973`), then prepare statements i = 0 … ⌊count_end/2⌋ − 1 again: expected evicted delta 0 and count exactly ⌊count_end/2⌋ (their weight is about C/2). (b) clear again, then prepare statement 0's text N times: expected count exactly 1 and evicted delta 0 (with no keyspace the two ids coincide and the cached entry is returned, `QueryProcessor.java:731-751`). Reason: "C unchanged" and "count stays 1" did not say whether the cache starts empty.

### B3. Cluster tier

**B3a. Environment and build.** Single node on the same Linux host, from `/local/c509` after `ant jar`. `mkdir -p /local/run && cp -r /local/c509/conf /local/run/conf`; in `/local/run/conf/cassandra.yaml` point the directories to `/local/run/data/{data,commitlog,saved_caches,hints,cdc_raw}`. `export CASSANDRA_CONF=/local/run/conf CASSANDRA_LOG_DIR=/local/run/logs MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`. Start `/local/c509/bin/cassandra -p /local/run/cassandra.pid`, wait for `UN` in `/local/c509/bin/nodetool status`.

**Amendment 2026-10-25 (step-0 audit) — B3a, this host.** Clone `$W/cassandra-run10` (B2a amendment; no `ant` while a node runs from it). Node directory `N=$W/node-psca`: `conf/` copied from the clone, `cassandra.yaml` = the shipped file with the directory keys and `prepared_statements_cache_size` removed and re-added at the end (`data_file_directories: [$N/data]`, `commitlog_directory`, `saved_caches_directory`, `hints_directory`, `cdc_raw_directory` under `$N/`). `CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`, started as a tracked background `bin/cassandra -f` (macOS has no `setsid`); ready when `nodetool status` shows `UN 127.0.0.1` **and** `nodetool statusbinary` prints `running`; the script fails at once if the daemon dies. Before each lifetime `pgrep -f CassandraDaemon` is empty and ports 7000/7199/9042/9091 are free; `$N` is wiped before and after. Reason: B3a's paths do not exist here.

**B3b. Knobs.** `prepared_statements_cache_size` ∈ {`0MiB` (expect start failure), `2MiB`, `32MiB`}; restart per value with a wiped data dir.

**Amendment 2026-10-25 (step-0 audit) — B3b, default added and read-back.** Values {`0MiB`, `2MiB`, auto (line left empty), `32MiB`}; auto = `max(10, ⌊maxMemory/2^20/256⌋)` = 10 MiB at `-Xmx2G` (2048/256 = 8 < 10). Every started value is read back from the `Initialized prepared statement caches with <n> MiB` line written by this start (`QueryProcessor.java:128-129`; read from the log's byte offset at start); a mismatch stops the run. Reason: group A asks for the default; restart-only knob (A1) needs a read-back.

**B3c. Workload.** Python driver (`pip install cassandra-driver` in a venv in `/local/venv`) script `/local/probe/prep.py`: create `ks` (RF 1) and the 50-column table from B2c; prepare N = 20000 distinct statements of the B2c form through `session.prepare()` (normal client path, `PREPARE` message). With w ≈ 20 KiB, 20000 × 20 KiB ≈ 390 MiB of would-be weight, far above 32 MiB, and within the 2 GiB heap if the cap did not hold. Duration a few minutes.

**Amendment 2026-10-25 (step-0 audit) — B3c, client.** Instead of `pip install`, the driver bundled in `$C/lib/cassandra-driver-internal-only-*.zip` (protocol 5), `DCAwareRoundRobinPolicy(local_dc='datacenter1')`, `token_metadata_enabled=False`, **no session keyspace**, statements fully qualified `ks.tbl`, so one cache entry per PREPARE (HANDOFF §10). Table `ks.tbl (k int PRIMARY KEY, c0 text … c49 text)`, keyspace `SimpleStrategy` RF 1. Statement i = the B2c text with `ks.tbl`, i = 0 … 19,999, prepared sequentially by one session; the driver's own logger is set to ERROR. Reason: no network installs on this host; the keyspace rule.

**B3d. Observables and instruments.** `nodetool sjk mx -mg -b org.apache.cassandra.metrics:type=CQL,name=PreparedStatementsCount -f Value` and `…name=PreparedStatementsEvicted -f Count` every 1000 prepares; at the end `jmap -histo:live $(cat /local/run/cassandra.pid) | grep -E 'QueryHandler\$Prepared|SelectStatement'` (instance count, shallow bytes) and `jcmd <pid> GC.heap_info`. `system.log` for "prepared statements discarded in the last minute because cache limit reached". Retained (deep) size is not directly measurable without a heap dump; optional `jmap -dump:live,format=b,file=/local/run/h.hprof` and Eclipse MAT retained size of the `preparedStatements` cache.

**Amendment 2026-10-25 (step-0 audit) — B3d, sampling and heap reading.** The client pauses after every 1,000 prepares while the harness runs the two `sjk mx -mg` reads of B3d (and once before the load). Heap: `jmap -histo:live <pid>` (forces a full GC) once after schema creation (baseline) and once at the end; the reading is the histogram's `Total` live bytes and the `QueryHandler$Prepared` instance count (`jstat` cannot attach on this host); `jcmd <pid> GC.heap_info` right after each histogram. The B3f old-gen bullet is read as `D = live(32 MiB) − live(2 MiB)` at the end (both runs offer the same 20,000 statements, so heap that depends on the number offered cancels). Reason: a heap dump and MAT are not available; HANDOFF §10 names the live histogram.

**B3e. Procedure.** Per value: wipe `/local/run/data`, set yaml, start; for `0MiB`, confirm the process exits and `system.log` contains the ConfigurationException; otherwise run `prep.py`, sample, histo, stop with `kill $(cat /local/run/cassandra.pid)`, confirm `pgrep -f CassandraDaemon` is empty.

**Amendment 2026-10-25 (step-0 audit) — B3e, order and waits.** Per started value: wipe, yaml, start, read-back, schema, baseline histogram, load with samples, **wait 65 s** (the discard warning is logged by a task at a fixed 1-minute rate, `QueryProcessor.java:120-126`), final sjk reads, histogram, heap info, `grep` of `system.log` from the start offset for `prepared statements discarded in the last minute`, stop (`nodetool drain`, then `kill`), check `pgrep -f CassandraDaemon` empty, wipe. `0MiB`: wait up to 120 s for the daemon to exit; read `system.log` and the console. Order: `0MiB`, `2MiB`, auto, `32MiB`, then the B3h lifetime. Reason: the warning B3g row 1 requires cannot appear if the node stops within the minute.

**B3f. Predictions.** `0MiB`: startup aborts. `2MiB`: `PreparedStatementsCount` plateaus at ≈ 2 MiB / w (≈ 100), `Prepared` instances in histo ≈ same; `32MiB`: plateau ≈ 16× higher (≈ 1600); evictions ≈ 20000 − plateau; old-gen after full GC differs between the two runs by roughly 30 MiB × (retained/weight ratio).

**Amendment 2026-10-25 (step-0 audit) — B3f, exact relations (prediction unchanged in substance).** `0MiB`: the daemon exits within 120 s and `system.log` holds `Exception encountered during startup: prepared_statements_cache_size option was set incorrectly to '0MiB', supported values are <integer> >= 0.` (`CassandraDaemon.java:751-767`, `:887`). For each capped run: (i) **plateau** = `PreparedStatementsCount` constant (±1 %) over the last five samples; (ii) count(32)/count(2) within ±10 % of 16 and count(auto)/count(2) within ±10 % of 5; (iii) evicted = 20,000 − final count (±1 %), > 0; (iv) `QueryHandler$Prepared` instances − final count is between 0 and 200 in every run, and differs by at most 20 between runs (the other instances belong to `internalStatements`, `QueryProcessor.java:97`, which the knob does not touch); (v) the discard warning logged at least once; (vi) `D > 0` and `D / (30 × 2^20)` between 0.5 and 2 ("roughly 30 MiB × the retained/weight ratio", with the ratio taken as within 2× of 1). Reason: "≈" and "roughly" had no tolerance.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| plateau proportional to C, evictions > 0, warning logged | cap governs actual heap use |
| Prepared instance count ≈ 20000 regardless of C | cap not enforced; claim wrong |
| plateau equal for both C | some other limit binds; inspect weigher |
| 0MiB starts | startup check not reached; claim (a) wrong |

**Amendment 2026-10-25 (step-0 audit) — B3g, rows added (the rows above are unchanged).** Row 1 ("cap governs actual heap use") needs B3f (i)–(vi) and both B3h controls. Added rows:
| Observation | Meaning |
|---|---|
| (i)–(v) hold but (vi) fails (D ≤ 0, or outside 0.5–2 × 30 MiB) | the cap bounds the weight estimate, not the real heap in proportion: Not confirmed for B1 (b)'s heap part |
| (i)–(vi) hold, and the whole-JVM live heap also grows with the 20,000 offered statements by an amount that does not depend on C | the cache is capped; the other growth is a consumer outside the cap: caps only on some paths (bypass), consumer named if observable |
| evicted = 0 at 2 MiB | limit never reached: Invalid (recompute N) |
| a B3h control misses its frozen expectation, or a read-back mismatches | tier Invalid |

**B3h. Controls.** Repeat the 32MiB run with only 500 distinct statements: no evictions and count 500 (workload below cap). Same driver against a node whose cap is 32MiB with re-preparation of the same 500 strings 40× (identity reuse): count stays 500.

**Amendment 2026-10-25 (step-0 audit) — B3h, exact controls.** One lifetime at `32MiB`: prepare statements i = 0 … 499 (fully qualified, no keyspace): expected count exactly 500 and evicted 0; then re-prepare the same 500 texts 40 times (20,000 PREPARE messages): expected count still 500 and evicted 0 (a cached id is returned without a new entry, `QueryProcessor.java:731-751`). Both expectations assume 500 × w ≤ 32 MiB, i.e. w ≤ 67,108 B, w taken from the unit tier's calibration of the same statement form; if w is larger the control cannot be read and is recorded as a design defect. Reason: the two controls fit one lifetime; their expected values derived from the source.

**B4. Risks and cleanup.** Disk: `/local/run` and `/local/probe/data` under 1 GiB; check `df -h /local` first. Processes: stop the node, `pgrep -f CassandraDaemon` and `pgrep -f ConfigProbe` empty. Restore `test/conf/cassandra.yaml` and delete `test/unit/org/apache/cassandra/probe/` in the local clone; `rm -rf /local/run /local/probe/data /local/venv` at the end.

## C. Sources read

src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 790-880, 4175-4183)
src/java/org/apache/cassandra/config/Config.java (584-585)
src/java/org/apache/cassandra/config/DataStorageSpec.java (42-108, 341-380)
src/java/org/apache/cassandra/cql3/QueryProcessor.java (93-150, 682-730, 815-840, 947-958)
src/java/org/apache/cassandra/metrics/CQLMetrics.java (33-49)
src/java/org/apache/cassandra/cql3/QueryHandler.java (63)
conf/cassandra.yaml (508), test/conf/cassandra.yaml (48)

## D. Stage-4 feedback

**2026-10-25, run 1 (Claude Opus 5.5, claude-opus-5-5), advisor's machine** — results: [`../../stage4-runtime-verification/results/prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous.md`](../../stage4-runtime-verification/results/prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous.md). Frozen version sha256 `ea4b8f5f…222e` (sixteen step-0 amendments of 2026-10-25 above), then `f325aef5…4dbc` after one runbook fix (B2a: Program 1's `java` command needs the JDK 11 `--add-exports`/`--add-opens` flags; as filed it fails in `FileUtils`' class init before the knob is read); both tiers ran at the second version; uncommitted. Estimate left as filed (`positive`).

- **Unit: Confirmed — caps** (B2g rows 1 and 2). `0MiB` refused with the traced message, `1MiB` → 1, auto → 10 at `-Xmx1G`; w = 21,812 B; weightedSize ≤ C at every sample; count ⌊C/w⌋ = 48 · 192 · 769 · 480 at 1 · 4 · 16 · 10 MiB; evicted = N − count; both B2h controls as frozen.
- **Cluster: Confirmed — caps only on some paths (bypass)** (B3g row 1 and the added bypass row). `0MiB` start aborted (`CassandraDaemon.java:887` line); plateau 96 · 482 · 1,542 at 2 · 10 · 32 MiB (1 : 5.02 : 16.06); evicted = 20,000 − count; `Prepared` instances = count + 31; discard warning logged; live-heap difference 32 vs 2 MiB = 0.857 × 30 MiB; B3h controls 500/0 and 500/0. Bypass: the `system.prepared_statements` memtable gains one partition per distinct PREPARE (+20,001 at every value, ≈ 21.7 MB of live heap independent of the knob).
- For stage 3 (not applied): A4 lists the system table as an on-disk consumer only; before a flush it is the largest on-heap consumer of a PREPARE flood.
