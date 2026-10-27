# LOGS_VIRTUAL_TABLE_DEFAULT_ROWS — verification solution  <!-- file: cases/logs_virtual_table_default_rows-addtobuffer-messagebuffer_size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/utils/logging/VirtualTableAppender.java:125` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the constant does bound the pre-registration buffer by event count, but that buffer is a short-lived startup list that exists only when the (default-commented-out) CQLLOG appender is enabled, and the cap is a count, not bytes, so it does not bound a memory-significant object. |
| Ground | The cap applies only to `messageBuffer` (`VirtualTableAppender.java:54`), which is used only until `setupVirtualKeyspaces()` (`CassandraDaemon.java:291`, `:534-544`) flushes and clears it (`VirtualTableAppender.java:86-92`). The appender is disabled in the shipped `conf/logback.xml:114-128` (commented out). The limit counts events, not bytes (each `LoggingEvent` retains its message and arguments), and is a compile-time constant that no runtime knob moves. The steady-state bound on log memory is a different object (`LogMessagesTable.buffer`) governed by a different knob. So usage is not expected to "follow" this constraint as a tunable cap. |

## A. Constraint trace

**A1. The constraint.** `LOGS_VIRTUAL_TABLE_DEFAULT_ROWS` is a hard-coded constant, `public static final int LOGS_VIRTUAL_TABLE_DEFAULT_ROWS = 50_000` (`src/java/org/apache/cassandra/db/virtual/LogMessagesTable.java:58`), next to `LOGS_VIRTUAL_TABLE_MIN_ROWS = 1000` (`:57`) and `LOGS_VIRTUAL_TABLE_MAX_ROWS = 100_000` (`:59`). Unit: log events (rows). It is not a yaml key, `-D` property or JMX value; changing it needs a recompile and restart. It is statically imported at `VirtualTableAppender.java:34` and used at `:125`. The earlier trace holds, with these checks and additions:
- The same constant also supplies the default of the *separate* JVM property `cassandra.virtual.logs.max.rows` (`CassandraRelevantProperties.java:338`, `convertToString(LogMessagesTable.LOGS_VIRTUAL_TABLE_DEFAULT_ROWS)`), and is the fallback in `LogMessagesTable.resolveBufferSize()` (`LogMessagesTable.java:146-152`) when the property is outside 1000..100000. That property sizes the table's `BoundedLinkedList` (`LogMessagesTable.java:91`, class at `:176-197`), not the appender buffer.
- The appender is not active by default: the `CQLLOG` appender and its `appender-ref` are commented out in `conf/logback.xml:112-120` and `:127-129`. It is enabled by uncommenting them (restart needed); test configs enable it (`test/conf/logback-dtest_with_vtable_appender.xml:54-58,64`). Only one such appender is allowed (`LogbackLoggingSupport.java:151-172`).
- The buffer is a plain unsynchronised `LinkedList<LoggingEvent>` (`VirtualTableAppender.java:54`).

**A2. What it caps.** Heap: the number of `LoggingEvent` objects (with their formatted-message strings and argument arrays) held in `messageBuffer` while `system_views.system_logs` does not yet exist. The code compares `messageBuffer.size()` (an element count) with 50,000 (`:125`). It does not measure bytes, so the heap bound is 50,000 times the per-event size, which is unbounded in principle (event messages and arguments are arbitrary).

**A3. Mechanism.**
1. `append()` (`:57-72`) drops events from the logger named in `forbiddenLoggers` (`FileAuditLogger`, `:47`); for others, while `logs == null` it calls `getVirtualTable()` (`:63`).
2. `getVirtualTable()` (`:94-119`) returns null while `VirtualKeyspaceRegistry` has no `system_views` keyspace or no `system_logs` table (`:96-107`).
3. Null leads to `addToBuffer()` (`:65`, `:121-127`): `if (messageBuffer.size() < 50_000) messageBuffer.add(event)`. At the limit the new event is silently dropped (newest dropped, oldest kept); there is no log, counter or exception.
4. `CassandraDaemon.setup()` calls `setupVirtualKeyspaces()` (`CassandraDaemon.java:291`) after `Schema.instance.loadFromDisk()` (`:283`), which registers `SystemViewsKeyspace` (`:537`; it contains `new LogMessagesTable(VIRTUAL_VIEWS)` at `SystemViewsKeyspace.java:53`) and then calls `flushBuffer()` (`:541-543`).
5. `flushBuffer()` (`VirtualTableAppender.java:86-92`) feeds every buffered event to `LogMessagesTable.add()` (`LogMessagesTable.java:129-132`) and clears the list. The table keeps only the newest `size` rows (`BoundedLinkedList.add`, `:190-197`, `size` from `resolveBufferSize()`), so if the property is set below the buffered count, the excess is discarded at flush.
6. `stop()` (`:74-79`) also clears the buffer.
Bypasses and overshoot: (a) the cap is on count not bytes; (b) `LinkedList` is not thread-safe and `append` can run on any logging thread while `flushBuffer()` iterates and clears, so the size check at `:125` is racy and a concurrent add can throw `ConcurrentModificationException` or lose events (this is a hypothesis from reading; not verified); (c) if the `system_logs` table is never registered (e.g. the appender used in a tool/client JVM that never runs `setupVirtualKeyspaces`), the buffer stays at the cap for the life of the JVM; (d) after registration the appender no longer touches `messageBuffer`; its cap no longer matters.

**A4. Other consumers.** The post-registration store `LogMessagesTable.buffer` (`LogMessagesTable.java:70,91`), capped at 1000..100000 rows by `-Dcassandra.virtual.logs.max.rows`, with each row holding logger, level and the formatted message strings (`:162-165`); `system.log`/`debug.log` file appenders (disk); and every other heap user during startup (schema, caches, memtables). The buffered `LoggingEvent` also keeps the argument array and any throwable until flushed; the table copies only strings (`:164`).

**A5. Evidence beyond the source.** CASSANDRA-18238 (introduction of the virtual logs table; referenced at `LogMessagesTable.java:50`): https://issues.apache.org/jira/browse/CASSANDRA-18238. Tests in the tree: `test/unit/org/apache/cassandra/db/virtual/LogMessagesTableTest.java` (property validation, `:125-140`) and `test/distributed/org/apache/cassandra/distributed/test/VirtualTableLogsTest.java`. Logback `LoggingEvent` API: https://logback.qos.ch/apidocs/ch/qos/logback/classic/spi/LoggingEvent.html. Cassandra docs for the table: https://cassandra.apache.org/doc/latest/cassandra/new/virtualtables.html (system_logs section).

## B. Verification solution

**B1. Claim under test.** Memory held by the logging subsystem does not follow `LOGS_VIRTUAL_TABLE_DEFAULT_ROWS` as a usage cap: (i) `messageBuffer` is bounded only in event count and only during startup, and (ii) after the table is registered the retained log memory is governed by the table's own bound (`cassandra.virtual.logs.max.rows`), unaffected by this constant. It would be refuted if heap held by the logging path grows with, or plateaus at, a level tied to the constant in steady state after startup, or if the buffer outlives the flush.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Copy the tree to local disk (`cp -r /users/jason92/cassandra-5.0.9 /local/tmp/c509`), `cd /local/tmp/c509 && ant jar` (and `ant build-test` for classpath). Write the test class `VtableBufferProbe` in package `org.apache.cassandra.db.virtual` (so the package-private `LogMessagesTable(String,int)` constructor at `LogMessagesTable.java:78` is reachable) in a separate directory, compile it against `build/classes/main` plus `lib/*.jar` and `build/lib/jars/*.jar`. Do not call `DatabaseDescriptor.daemonInitialization()` and do not start Cassandra. Run with `java -Xmx2g -XX:+UseSerialGC -cp ...`. Reflection is needed to read private fields `messageBuffer` (`VirtualTableAppender.java:54`) and `LogMessagesTable.buffer` (`:70`).

**B2b. Knobs.** (1) Number of events pushed through `doAppend`: N in {1,000, 49,999, 50,000, 50,001, 120,000}. (2) Event payload size: message 100 B vs 10 KB (to test count-not-bytes). (3) `-Dcassandra.virtual.logs.max.rows` in {1000 (the minimum), default 50000, 100000} for the positive control only. The constant itself cannot be varied at run time; a second build with it changed is B3's job.

**B2c. Workload.** Construct `ch.qos.logback.classic.spi.LoggingEvent` objects (set logger name to something not `FileAuditLogger`, level WARN, a formatted message of the chosen size). Create `new VirtualTableAppender()`, call `start()`, and push N events with `doAppend(event)`. With `VirtualKeyspaceRegistry.instance` empty, `getVirtualTable()` returns null (`:96-98`) so every event goes to `addToBuffer`. Arithmetic: reaching the limit needs N >= 50,000; N = 120,000 exceeds it by 70,000, all of which must be dropped. At 10 KB per message, 50,000 events retain roughly 50,000 x (10 KB x 2 bytes/char for UTF-16, or about 10 KB with compact strings for Latin-1) which is of the order of 0.5 GB, so the 2 GB heap is sufficient and the byte volume plainly depends on payload, not on the constant.

**B2d. Observables and instruments.** (1) `messageBuffer.size()` via reflection after each batch. (2) Number of live `LoggingEvent` instances: `jcmd <pid> GC.class_histogram` after `System.gc()` (or `jmap -histo:live`). (3) Retained heap: `MemoryMXBean.getHeapMemoryUsage().getUsed()` after three `System.gc()` calls, sampled before and after each batch. (4) For the control, `LogMessagesTable.buffer.size()` by reflection. Not observable directly: per-event retained size (derived from the histogram bytes divided by the instance count).

**B2e. Procedure.**
1. Build as in B2a; confirm `git -C /local/tmp/c509 status` shows no change besides `build/`.
2. For each (N, payload): fresh JVM; start appender; baseline heap after GC; push N events; record `messageBuffer.size()`, histogram count of `ch.qos.logback.classic.spi.LoggingEvent`, heap after GC.
3. Flush check: register nothing, so instead call `stop()` (`:77`) and re-measure: size 0 and instance count falls (events not retained by the buffer after clear).
4. Positive control: in a fresh JVM, for each `max.rows` value m in {1000, 50000, 100000}, run `-Dcassandra.virtual.logs.max.rows=m`, construct `new LogMessagesTable("system_views", LogMessagesTable.resolveBufferSize())` (static, package-visible at `:147`), call `add(event)` 120,000 times with the same events, record `buffer.size()` and heap after GC.
5. Repeat step 2 once with payload 10 KB, N = 50,000 and 120,000.

**B2f. Predictions.** (stated before any run)
- Appender: `messageBuffer.size() == min(N, 50,000)` for every N; at N = 50,001 and 120,000 exactly 50,000 retained and the first 50,000 events (oldest) are the ones kept. Live `LoggingEvent` count equals the size (plus a few unrelated).
- Retained heap grows roughly linearly with payload at equal N (10 KB payload gives a much larger heap delta than 100 B at N = 50,000), showing the count cap does not bound bytes.
- After `stop()`, size 0 and heap returns near baseline.
- Positive control: `LogMessagesTable.buffer.size() == m` for m in {1000, 50000, 100000} (at 120,000 adds); heap delta increases with m. The appender buffer size is identical across all m (the property has no effect on it, since `:125` compares with the constant).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Appender size = min(N, 50,000), unchanged by `max.rows`; table size = m, moves with `max.rows` | Claim confirmed: the constant bounds only the count in the startup buffer; the knob that moves table size is a different one |
| Appender size exceeds 50,000 | Claim and A3 wrong: the check at `:125` is not effective (e.g. a race or another add path) |
| Appender size follows `max.rows` | A1 wrong: the appender would then not be using the constant |
| Heap delta at N = 50,000 is the same for 100 B and 10 KB payloads | Count cap bounds bytes in effect; the count-not-bytes ground would be refuted |
| Table size does not move with m (positive control fails) | Control invalid; reading is not confirmed |
| N never reached 50,000 (e.g. events filtered or dropped earlier) | Limit never reached; not confirmed |

**B2h. Controls.** Same JVM flags and heap for every run; `-XX:+UseSerialGC` so the post-GC heap is deterministic; GC three times before each reading; warm-up of 1,000 events discarded; the same event objects (or equal-size copies) in appender and table runs; a run with N = 0 gives the baseline; `forbiddenLoggers` logger name avoided so events are not skipped (`:47,59`).

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, Ant, built from a local copy (`/local/tmp/c509-A`, and a second copy `/local/tmp/c509-B`). Build A is unmodified. Build B differs only in `LogMessagesTable.java:58`, changed from `50_000` to `1_000` (a recompile is the only way to change this constant; the property default `CassandraRelevantProperties.java:338` then also changes, so pin `-Dcassandra.virtual.logs.max.rows=100000` on every run to keep the table capacity fixed and independent). Node data, commit log, hints, saved caches, and logs all under a local directory of known size (for example 20 GB free), set with `-Dcassandra.storagedir=/local/tmp/node1` or yaml directories. Edit that copy's `conf/logback.xml`: uncomment the CQLLOG appender (`:114-118`) and `<appender-ref ref="CQLLOG"/>` (`:127-129`), set its ThresholdFilter level to `TRACE` and the `org.apache.cassandra` logger to `TRACE` so many events occur before `setupVirtualKeyspaces()`. JVM: `-Xms1g -Xmx1g`, `-XX:+UseSerialGC`. Seed the node beforehand with many keyspaces/tables (for example 40 keyspaces x 25 tables) so that schema load emits many startup events; this is workload for the pre-registration window.

**B3b. Knobs.** (1) The constant: 50,000 (build A) vs 1,000 (build B). (2) Presence of the appender: enabled (above) vs disabled (stock logback.xml) as the no-appender control. (3) `-Dcassandra.virtual.logs.max.rows` fixed at 100000 in A and B (and a third run of A with 1000 as the positive control for the table cap). Applied by build, logback edit and `JVM_EXTRA_OPTS`/`conf/jvm11-server.options`.

**B3c. Workload.** The drive is the node's own startup: restarting a node with the seeded schema makes `Schema.instance.loadFromDisk()` and earlier startup code log before `CassandraDaemon.java:291`. Whether this reaches 50,000 events is not guaranteed from the source alone, so build B with 1,000 is the boundary case (the pre-registration events should far exceed 1,000 at TRACE), and build A tests whether the stock value is reachable: if the pre-registration event count (from the log file) is below 50,000, the buffer never fills in A, which itself is evidence that the stock cap is not what bounds usage. After startup, a second workload drives post-registration logging: run `cassandra-stress write n=2000000` plus repeated `nodetool setlogginglevel org.apache.cassandra TRACE` and a flush/compaction loop for 10 minutes to emit steady-state events.

**B3d. Observables and instruments.** (1) `SELECT count(*) FROM system_views.system_logs WHERE ...` is not allowed to filter implicitly (`LogMessagesTable.java:140-144`); instead `SELECT timestamp, message FROM system_views.system_logs` via `cqlsh` with a large `--request-timeout`, counted client-side, with the rows split at the timestamp of the first log line following the flush point (the `opening keyspace {}` DEBUG message at `CassandraDaemon.java:305-306`, found in `debug.log`). (2) Number of pre-flush lines in `debug.log` before that marker (ground truth of events logged). (3) Heap: `jcmd <pid> GC.class_histogram` for `ch.qos.logback.classic.spi.LoggingEvent` and `org.apache.cassandra.db.virtual.LogMessagesTable$LogMessage` instance counts, and `jcmd <pid> GC.heap_info` after `GC.run`, sampled at 5 s during startup up to flush, then every 30 s. (4) Node RSS (`ps -o rss`) as the real resource. Not observable: the exact instant of `flushBuffer()`; use the sampled histogram and the debug.log marker.

**B3e. Procedure.**
1. Build A and B (`ant jar` in each copy); create the data directory and seed the schema using a script of CQL run against build A.
2. Run 1 (A, appender off): start the node, sample heap/histogram through startup and 5 minutes of steady state; stop with `nodetool drain` then kill; verify with `pgrep -f CassandraDaemon` that nothing remains.
3. Run 2 (A, appender on, max.rows=100000): same sampling; at the end read system_logs rows, count pre-flush vs post-flush.
4. Run 3 (B, appender on, max.rows=100000): same.
5. Run 4 (A, appender on, max.rows=1000): positive control for the table cap; same sampling and the post-startup stress phase.
6. After each run, wipe or reuse the data directory as appropriate (restart on the same seeded data for identical schema); keep `debug.log`.

**B3f. Predictions.** (stated before any run)
- Run 1: no `LoggingEvent` instances accumulate; no `system_logs` table content.
- Run 2: peak `LoggingEvent` count before the flush equals the lesser of (pre-flush events logged) and 50,000, then drops to near zero after the flush (the histogram sample after `opening keyspace`); `LogMessage` instances then equal min(total events, 100,000), growing during the stress phase until they plateau at 100,000.
- Run 3: peak `LoggingEvent` count is capped at 1,000 while the debug.log shows far more pre-flush events; the pre-flush portion of system_logs has at most 1,000 rows. The post-startup plateau is unchanged (100,000), so the constant does not influence steady state.
- Run 4: `LogMessage` plateau at 1,000, regardless of the constant.
- Steady-state RSS/heap difference between runs 2 and 3 is within noise once startup is over.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Pre-flush `LoggingEvent` peak = 1,000 in B, steady-state `LogMessage` plateau identical in A and B, plateau follows `max.rows` in run 4 | Claim confirmed: the constant caps only a transient startup buffer in count; steady-state log memory follows a different knob |
| Steady-state `LogMessage` plateau differs between A and B | Claim refuted: the constant influences retained log memory after startup |
| `LoggingEvent` instances persist long after the flush marker | Buffer not cleared; A3 step 5 wrong; usage may follow the constant |
| Pre-flush event count in A below 50,000 so the buffer never fills | The stock limit is not reached in practice (supports negative); B still tests the boundary |
| Run 4 plateau does not move to 1,000 (positive control fails) | Control invalid; reading not confirmed |
| No `LoggingEvent` instances in run 2 at any sample | Appender not active or the startup window was missed; not confirmed |

**B3h. Controls.** Run 1 (no appender) shows the baseline heap without the buffer; run 4 is the positive control where a cap known to bind (`BoundedLinkedList`, `LogMessagesTable.java:176-197`) moves usage. Same seeded schema, same JVM options and same heap for all runs; the only difference between runs 2 and 3 is the constant; samples at identical time offsets from the process start; at least three repetitions per run to see variance.

**B4. Risks and cleanup.** Unit tier: heap up to about 1 GB with the 10 KB payload; no disk beyond the `build/` directory in the local copy. Cluster tier: TRACE logging of a seeded schema can produce large `system.log`/`debug.log` files; keep the node's logs and data on the local 20 GB directory (set the logs directory via `-Dcassandra.logdir`), rotate/limit by the existing logback policy and check `df` before and after each run. Never build in or write to `/users/jason92/cassandra-5.0.9`. Stop every process started (`nodetool drain`, kill the JVM, `pgrep -f CassandraDaemon` and `pgrep -f VtableBufferProbe` must be empty), then delete `/local/tmp/c509*` and `/local/tmp/node1`.

## C. Sources read

- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/logging/VirtualTableAppender.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/virtual/LogMessagesTable.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java` (line 338 and the import at 28)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/service/CassandraDaemon.java` (lines 280-330, 530-546, 602-610)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/virtual/SystemViewsKeyspace.java` (lines 45-60)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/logging/LogbackLoggingSupport.java` (lines 150-175)
- `/users/jason92/cassandra-5.0.9/conf/logback.xml` (lines 105-135)
- `/users/jason92/cassandra-5.0.9/test/conf/logback-dtest_with_vtable_appender.xml` (lines 50-66)
- `/users/jason92/cassandra-5.0.9/test/unit/org/apache/cassandra/db/virtual/LogMessagesTableTest.java` (outline and lines 125-140)
- `/users/jason92/cassandra-5.0.9/test/distributed/org/apache/cassandra/distributed/test/VirtualTableLogsTest.java` (outline)
- https://issues.apache.org/jira/browse/CASSANDRA-18238 (cited from the source comment; not fetched)

## D. Stage-4 feedback

`none yet`
