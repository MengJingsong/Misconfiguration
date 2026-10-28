# cassandra.virtual.logs.max.rows (system_logs row cap) — verification solution  <!-- file: cases/virtual_logs_max_rows-boundedlinkedlist_add-size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`LogMessagesTable.java:193`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/virtual/LogMessagesTable.java#L193) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `positive`: the buffer never holds more than `maxSize` messages, and `maxSize` is clamped to [1000, 100000] rows, so heap held by the table is bounded by rows times message size. |
| Ground | — |

**Type:** non-config (hard-coded constant; also reads JVM property `cassandra.virtual.logs.max.rows`). The constant rule applies: the value compared at line 193 is the property value filtered through the constants `LOGS_VIRTUAL_TABLE_MIN_ROWS` (1000), `LOGS_VIRTUAL_TABLE_MAX_ROWS` (100_000) and `LOGS_VIRTUAL_TABLE_DEFAULT_ROWS` (50_000).

## A. Constraint trace

**A1. The constraint.** `maxSize` field of `BoundedLinkedList` ([`LogMessagesTable.java:178`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/virtual/LogMessagesTable.java#L178)), set from the constructor argument at line 185-188, passed from `LogMessagesTable(String keyspace, int size)` (line 78, 91), whose production caller is `LogMessagesTable(String keyspace)` -> `resolveBufferSize()` (line 74, 147-152). Kind: constant bounds plus a JVM property. Constants declared at [`LogMessagesTable.java:57-59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/virtual/LogMessagesTable.java#L57-L59) (MIN 1000, DEFAULT 50_000, MAX 100_000). JVM property `LOGS_VIRTUAL_TABLE_MAX_ROWS` = `cassandra.virtual.logs.max.rows`, declared at `CassandraRelevantProperties.java:338`, default `convertToString(LOGS_VIRTUAL_TABLE_DEFAULT_ROWS)` = "50000". Unit: rows (log messages). Resolution: property value if within [1000, 100000], otherwise 50000 (line 150-151). Set with `-Dcassandra.virtual.logs.max.rows=N` (restart needed; read once at table construction). The bounds are not settable. A second constructor (`@VisibleForTesting`, line 78) lets tests pass any size.

**A2. What it caps.** Heap: the number of `LogMessage` objects (timestamp, logger, level, message strings; lines 155-174) retained in the in-memory `buffer` list. Compared quantity: `size()` of the linked list vs `maxSize`.

**A3. Mechanism.** `LogMessagesTable.add(LoggingEvent)` (line 129-132) calls `buffer.add(new LogMessage(event))`; `buffer` is `Collections.synchronizedList(new BoundedLinkedList<>(size))` (line 182). [`if (size() == maxSize)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/virtual/LogMessagesTable.java#L193) in `BoundedLinkedList.add` (line 191-198): true -> `removeLast()` (drop oldest, since new entries go to the front) then `addFirst(t)`; false -> just `addFirst(t)`. Size therefore stays at most `maxSize`. Callers: `VirtualTableAppender` (utils/logging/VirtualTableAppender.java) feeds events, and line 125 there buffers pre-startup events against `LOGS_VIRTUAL_TABLE_DEFAULT_ROWS` separately. Bypass/overshoot: `==` rather than `>=` is safe because only `add(T)` is overridden and the list starts empty; other `LinkedList` mutators (add(int,..), addAll, push) are not used by this class. Each entry's bytes are unbounded per message (message length is not capped), so heap = rows x message size, not rows alone. `truncate()` (line 135-138) clears the buffer. `data()` (line 95-127) builds a full `SimpleDataSet` copy of every row per query, a transient extra heap use of the same order, outside this cap.

**A4. Other consumers.** The log appender's own pre-startup buffer (`VirtualTableAppender`, capped by DEFAULT_ROWS), logback file/console appenders, and the per-query `SimpleDataSet` copy from `data()` (up to rows x message size on the heap per concurrent query).

**A5. Evidence beyond the source.** Class javadoc line 40-52 ("bounded in its size ... oldest one is removed"); [CASSANDRA-18238](https://issues.apache.org/jira/browse/CASSANDRA-18238). Tests in the tree, if any, were not read.

## B. Verification solution

**B1. Claim under test.** With `cassandra.virtual.logs.max.rows=N` (N in [1000, 100000]), the `system_logs` buffer holds at most N messages and its heap use grows with N and stops growing once N messages are held; out-of-range values (for example 500 or 200000) fall back to 50000.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant, a local copy of the tag (not the shared tree): `ant jar`. Test source in a scratch copy, for example a JUnit class in package `org.apache.cassandra.db.virtual` (the `LogMessagesTable(String,int)` and `resolveBufferSize()` members are package-private/`@VisibleForTesting`). Use `-Xmx1g`.

**B2b. Knobs.** Constructor `size` in {1000, 5000, 100000}; for `resolveBufferSize()` set the system property to {999, 1000, 100000, 100001, unset}. Chosen to hit both clamp edges and one value off each side.

**B2c. Workload.** Create `new LogMessagesTable("system_views", size)`; call `add(new LoggingEvent(...))` (or build one with `LogMessage` via a logback `LoggingEvent`) `size + 5000` times with a 200-character message each.

**B2d. Observables and instruments.** Row count from `table.data()` row iteration (or reflection on `buffer.size()`); heap after `System.gc()` via `Runtime.totalMemory()-freeMemory()`, or `jcmd <pid> GC.class_histogram` counting `LogMessage` instances. The actual heap per entry is only estimated.

**B2e. Procedure.** 1. Build. 2. Run the test for each size, recording row count and `LogMessage` instance count after the workload. 3. Run `resolveBufferSize()` for each property value and record the result. 4. Repeat the 100000 case with a 2000-character message to see heap scale with message size.

**B2f. Predictions.** Row count = min(adds, size) exactly, so size for each knob value; newest entries retained, oldest evicted. `resolveBufferSize()`: 50000 for 999, 100001 and unset; 1000 for 1000; 100000 for 100000. `LogMessage` instance count equals row count; heap grows roughly linearly with size, and 10x message length raises per-entry heap several-fold.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Row count == size after size+5000 adds, instance count equal | claim confirmed |
| Row count exceeds size | claim refuted (bypass of line 193) |
| Resolved size outside [1000, 100000] | clamp broken |
| Heap flat across sizes with same adds | measurement invalid (adds never reached the limit) |

**B2h. Controls.** Same message length across sizes; GC before each reading; one run with adds < size (row count == adds) shows the cap is not reached.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from a local copy of the tag; start with `-Xmx2g`, `-Dcassandra.virtual.logs.max.rows=<N>` added to `conf/jvm-server.options` copy in a private conf dir. Logging config must include the `VirtualTableAppender` (default `logback.xml`).

**B3b. Knobs.** N in {1000, 20000, 100000, 200000 (out of range, expect 50000)}; set via the property, one restart per value.

**B3c. Workload.** Generate log volume well above N: run `nodetool setlogginglevel org.apache.cassandra DEBUG` and a loop of schema changes / `nodetool flush` / `nodetool repair` plus `cassandra-stress write n=200000` to produce more than 2xN INFO/DEBUG lines (check via `debug.log` line count). Use messages of ordinary size.

**B3d. Observables and instruments.** `SELECT count(*) FROM system_views.system_logs;` (virtual table; count scans all rows); heap via `jcmd <pid> GC.class_histogram` (count of `LogMessagesTable$LogMessage` instances) and `jcmd <pid> GC.heap_info`. Direct per-table heap is not exposed.

**B3e. Procedure.** 1. Start node with N. 2. Confirm `debug.log` line count after workload exceeds N. 3. Query `count(*)` and take histogram. 4. Stop node (`nodetool drain`; kill the process), verify no `java` process remains with `pgrep -f CassandraDaemon`. 5. Next N.

**B3f. Predictions.** count = N for N in {1000, 20000, 100000}; 50000 for N=200000; histogram `LogMessage` instance count tracks the count; heap used by those instances rises with N.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| count == N (or 50000 for out of range), instances match | confirmed |
| count > N | refuted |
| count < N and log lines in the workload < N | limit not reached; raise workload |

**B3h. Controls.** Fresh data dir per run; same workload; baseline run with no workload shows count small.

**B4. Risks and cleanup.** Disk: debug.log growth; use a private data/log directory and remove it afterward. Memory: keep `-Xmx` small. Stop all processes and verify none remain.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/virtual/LogMessagesTable.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (grep, line 338)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/logging/VirtualTableAppender.java (grep only, line 125)

## D. Stage-4 feedback

`none yet`
