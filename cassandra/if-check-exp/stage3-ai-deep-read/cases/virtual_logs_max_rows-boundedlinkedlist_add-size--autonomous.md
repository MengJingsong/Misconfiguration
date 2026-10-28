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

> **Amendments to B2 (stage-4 audit, 2026-10-27, before the unit tier ran).**
> - **U1 (B2a, B2c, B2e: how it runs).** The test class is `VirtualLogsMaxRowsProbeTest` in `org.apache.cassandra.db.virtual` (harness folder), run with the plain `java` launcher and JUnitCore on the run copy's classpath plus the JDK 11 module flags of `conf/jvm11-server.options` (a `ant testsome` JVM would append its own heap setting; the class touches `FileUtils`, which needs the flags), `-Xmx1g`, one JVM per run, `DatabaseDescriptor.daemonInitialization()` first. Events are real logback `LoggingEvent`s passed to `add(LoggingEvent)`, each with a message `m<seq>-xxx...` of exactly `len` characters, so the retained set can be identified by sequence number.
> - **U2 (B2b, B2e: the runs).** Sizes {1000, 5000, 50000, 100000} with 200-character messages and `size + 5000` adds (B2c); `size` 100000 with 2000-character messages (B2e step 4); the B2h control `size` 100000 with 600 adds (adds < size); `size` 1000 with 50 x size adds; an 8-thread run (`size` 1000, 8 x 200000 adds; the production appender is called by every logging thread); `resolveBufferSize()` in-process for the property values {unset, 999, 1000, 1001, 50000, 50001, 100000, 100001, 0, -1} and through `-D` on the JVM command line for {unset, 999, 1000, 100000, 100001} (the case says the knob is set with `-D`).
> - **U3 (B2d: observables).** Row count is read three ways: `buffer.size()` by reflection, the rows a full `select(DataRange.allData, ColumnFilter.all)` returns, and the live-instance count of `LogMessagesTable$LogMessage` in a collecting class histogram (`DiagnosticCommand.gcClassHistogram`, after 3 x `System.gc()`). Retained heap per entry is the histogram byte delta, after minus before the adds, of `LogMessage` + `java.util.LinkedList$Node` + `java.lang.String` + `[B`, divided by the row count. The histogram text itself adds under 0.5 MB of `String`/`[B` noise, so the per-entry byte reading is only used for sizes of 50000 and above.
> - **U4 (B2f: numeric prediction for the heap, written before any reading).** Per entry, the live heap is `LogMessage` 32 B + `LinkedList$Node` 24 B + `String` 24 B + `byte[]` 16 B header plus the message bytes (Latin-1, rounded up to 8): `L + 96 B` for a message of `L` characters, so `sumBytes / rows` lies in `[L + 80, L + 112]`: [280, 312] for L = 200 and [2080, 2112] for L = 2000, and the total for `size` 100000 is 28-31 MB (L = 200) and 208-211 MB (L = 2000). Row counts are exact: `bufferSize == dataRows == LogMessage instances == min(adds, size)` in the single-thread runs; newest id = adds, oldest id = adds - size + 1 once adds >= size; the 8-thread run ends at exactly `size` with a sampled maximum of `size`.
> - **U5 (B2g: added rows).** `dataRows` < `bufferSize` in a single-thread run would mean the table's read path collapsed same-key rows (`data()` keys rows by (timestamp, running index), lines 111-119), not a cap effect; `LogMessage` instance count > `bufferSize` would mean another holder of `LogMessage` objects (then the instance count is not the row count). Both are recorded, neither changes the claim row unless `bufferSize` itself exceeds `size`.

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

> **Amendments to B3 (stage-4 audit, 2026-10-27; C1-C3 were found by a shakedown arm whose readings were discarded, before any reading used in the verdict).**
> - **C1 (B3a: the logging configuration; the filed text is wrong).** The shipped `conf/logback.xml` does **not** include the appender: the `CQLLOG` appender is commented out (lines 112-118), its `<appender-ref ref="CQLLOG"/>` is commented out (lines 127-129), and its `ThresholdFilter` is `WARN`. With the shipped file the table is never fed. The node therefore runs with a private copy (`make-node.sh`) in which the appender and its reference are uncommented and the threshold is `TRACE` (so that the workload's log lines reach the table); the DEBUGLOG rolling size is raised so `debug.log` stays one file. The heap is `-Xmx2g` as filed.
> - **C2 (B3c: the log volume).** Ordinary INFO/DEBUG activity does not reach 2 x N lines in reasonable time. The workload is `nodetool setlogginglevel org.apache.cassandra TRACE` plus `cassandra-stress write n=<step> -rate threads=32` in cumulative steps of 2000, 10000, 20000, 40000 and 100000 operations (the level is put back to DEBUG and the node left idle 10 s before each reading), against N in {1000, 20000, 100000}: the last step is more than 5 x N lines for N = 100000 (the debug.log event count of each step is recorded). The messages are ordinary-sized log lines.
> - **C3 (B3d: observables; `count(*)` is not usable).** `SELECT count(*)` over the virtual table returned about 105 where the live buffer held 726 messages (shakedown); a paging-off `SELECT timestamp, order_in_millisecond` returned 723 rows. The primary row reading is therefore the live `LogMessagesTable$LogMessage` instance count of `jcmd <pid> GC.class_histogram` (a collecting histogram), which is the buffer size at a quiescent moment (exact; a message being added at that instant adds at most one per logging thread). Secondary readings: the number of rows a paging-off listing returns (a lower bound: bursts from many threads share milliseconds and rows with the same (timestamp, index) key collapse), and the timestamp of its oldest row against `debug.log` (every event reaches both appenders at the same threshold, so the number of `debug.log` events at or after the oldest listed timestamp is of the order of N if old events were dropped and about the whole run if the buffer kept growing; the tolerance is `<= 2 x N + 1000`, set after the shakedown showed 1.28 x N at N = 1000, because an event gets its timestamp when it is created and is appended to the buffer slightly later under 32 writer threads). Direct heap: the class-histogram byte totals of `LogMessage` + `LinkedList$Node` + `String` + `[B` and the post-GC heap of `GC.heap_info`, **ON minus OFF** at the same step (the OFF arm runs the same workload with the appender left commented out as shipped, so the table stays empty; the memtable, caches and the logging queue cancel in the difference).
> - **C4 (B3b: arms).** N = 1000, 20000, 100000, 200000 (out of range), unset (the default), the OFF arm (no appender), and a control arm `w1000` with the appender on at the shipped `WARN` threshold and N = 1000 (only WARN/ERROR lines reach the table, so the cap is intentionally not reached).
> - **C5 (B3f: numeric predictions, written before any cluster reading).** Let `b0`/`e0` be the base reading's instance count and `debug.log` event count (before the workload) and `E` the event count of a step. Instances = `min(N_eff, b0 + (E - e0))` within 1 percent while E is below the cap and exactly `N_eff` (tolerance +5 for in-flight objects) once past it, with `N_eff` = N for 1000 / 20000 / 100000, 50000 for N = 200000 and for the unset arm, 0 for the OFF arm; the `-D` value is on the process command line and the capacity DEBUG line (`LogMessagesTable.java:90`, "capacity of virtual table ... at most <N_eff> rows") shows `N_eff` in `debug.log`. The paging-off row count is at most the instance count (a lower bound). Heap: for the arms with N >= 20000, (ON minus OFF byte total) / instances is the same within +-25 percent across the arms, and the byte delta for N = 100000 is between 60 and 140 times the delta for N = 1000 (instances differ 100-fold); per entry 60-600 B. Arm `w1000`: instances = the number of WARN/ERROR events since registration (counted in `debug.log`) within 5, below 1000.
> - **C6 (B3e step 4).** The "no process remains" check is `ps -eo pid,comm,args | awk '$2=="java" && /CassandraDaemon/'` run on the node (a `pgrep -f` inside the script matches its own shell).
> - **C7 (B3g: added rows).** "paging-off rows < instances while instances == N" is the read path losing same-key rows (C3), not a cap effect. "Instances == N for N = 200000 or unset is 50000" is the clamp. "OFF arm instances == 0 and `w1000` instances < 1000" are the controls.

**B4. Risks and cleanup.** Disk: debug.log growth; use a private data/log directory and remove it afterward. Memory: keep `-Xmx` small. Stop all processes and verify none remain.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/virtual/LogMessagesTable.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (grep, line 338)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/logging/VirtualTableAppender.java (grep only, line 125)

## D. Stage-4 feedback

**2026-10-27, node pc41, results [`results/virtual_logs_max_rows-boundedlinkedlist_add-size--autonomous.md`](../../stage4-runtime-verification/results/virtual_logs_max_rows-boundedlinkedlist_add-size--autonomous.md) (not committed by the session that ran it; frozen version = the file before this section, sha256 `ac361a2e3182237d0b0cd4b8de3eb35b7743803f6b85511a8a137aa57c2b7e71`).**

- **Verdict:** unit **Confirmed, caps**; cluster **Confirmed, caps** (row count). Outcome class **true positive** (estimate `positive`, effect `caps`). The buffer held exactly `min(adds, N)` messages in 11 unit JVMs (sizes 1000 / 5000 / 50000 / 100000, 8 writer threads, 50 x size adds) and exactly N_eff live `LogMessage` objects in every cluster step past the cap, for `-Dcassandra.virtual.logs.max.rows` = 1000 / 20000 / 100000 / 200000 (resolved to 50000) / unset (50000), with 0.03 to 1.6 million log events behind each reading; the unit tier measured the retained heap at `message length + 96` bytes per entry (299 B at 200 characters, 2099 B at 2000), so the table's heap is rows x message size as A3 says. `resolveBufferSize()` clamps as traced for all 15 values tried (in-process and `-D`).
- **Wrong in B3a (amended, C1):** the shipped `conf/logback.xml` does not include the `VirtualTableAppender`; the appender and its reference are commented out and its filter is `WARN`. A default node's `system_logs` is empty (arm `off`: 0 rows after 1.6 million events), and with the appender enabled at the shipped threshold it held 6 messages (arm `w1000`). The cap binds, but only for events that reach the appender, which the default configuration does not do.
- **Not usable as filed (amended, C3):** `SELECT count(*)` over the table returned about 105 where the buffer held 726 messages, and a paging-off listing shows fewer rows than the buffer after a multi-threaded burst (467 of 1000, 74136 of 100000), because `data()` (lines 111-119) assigns the running index only to consecutive equal timestamps and rows with the same (timestamp, index) key collapse. The reading that matches the buffer is the live-instance count of a class histogram.
- **Missed (recorded, not tuned):** in the cluster tier the ON-minus-OFF byte totals per retained entry were not constant within 25 percent across arms (90 to 510 B) and the N = 1000 arm gave a non-positive difference; the stress workload's memtable and GC state moved the heap by about 10 MB between arms, more than 1000 messages occupy. The unit tier's per-entry bytes are exact. A log source that stores nothing (for example a read-only workload) would make the cluster byte reading precise.
- **For stage 3:** (1) A4 is right that `data()` makes a transient per-query copy; nothing was measured on it. (2) The constant-rule point of A1 (bounds 1000 and 100000 are not settable) held: values 999, 100001, 0, -1 and 200000 all resolve to 50000.

