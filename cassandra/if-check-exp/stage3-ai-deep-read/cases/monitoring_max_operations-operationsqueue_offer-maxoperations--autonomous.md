# monitoring_max_operations — verification solution  <!-- file: cases/monitoring_max_operations-operationsqueue_offer-maxoperations--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`MonitoringTask.java:221`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/monitoring/MonitoringTask.java#L221) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `positive`: with maxOperations = N > 0 the queue holds at most N Operation objects per queue (each pins its Monitorable, i.e. the ReadCommand), and with 0 nothing is retained. |
| Ground | — |

**Type:** non-config (hard-coded constant: the numeric literal `0` in `maxOperations == 0`; the check also reads the JVM property `cassandra.monitoring_max_operations` via `MONITORING_MAX_OPERATIONS`)

## A. Constraint trace

**A1. The constraint.** `maxOperations` (field of `OperationsQueue`, [`MonitoringTask.java:194`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/monitoring/MonitoringTask.java#L194)), set from the constructor argument (line 209), which comes from `MAX_OPERATIONS` ([`MonitoringTask.java:65`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/monitoring/MonitoringTask.java#L65)) = `MONITORING_MAX_OPERATIONS.getInt()`, declared at [`CassandraRelevantProperties.java:361`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L361) (`cassandra.monitoring_max_operations`, default `"50"`). Unit: count of unique-or-not queued operations per queue (two queues: failed and slow). Settable only with `-Dcassandra.monitoring_max_operations=N` at JVM start (restart needed); not in cassandra.yaml, not JMX. Negative = unbounded, 0 = disabled (javadoc lines 61-65, 191-193). Constant involved in the check: the literal `0` at line 221 (constant rule); the compared value `maxOperations` itself comes only from the JVM property.

**A2. What it caps.** Heap. The number of `Operation` wrappers (`FailedOperation`/`SlowOperation`) waiting in the `LinkedBlockingQueue` between report runs (default every 5000 ms, `MONITORING_REPORT_INTERVAL_MS`, line 59). Each Operation strongly references its `Monitorable` (field `operation`, line ~320), which in practice is a `ReadCommand`/range command, so the retained size is roughly N x (command size plus query text built lazily by `name()`). The quantity compared at line 221 is whether the limit is zero (queue disabled).

**A3. Mechanism.** Callers: `MonitorableImpl.abort()` ([MonitorableImpl.java:101](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/monitoring/MonitorableImpl.java#L101)) and `complete()` (line 115) call `MonitoringTask.addFailedOperation/addSlowOperation` (lines 107, 112) -> `OperationsQueue.offer` (line 219). Enclosing method `offer`: [`if (maxOperations == 0)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/monitoring/MonitoringTask.java#L221) returns immediately: the Operation (already allocated by the caller at 109/114) is dropped at once and never queued, so nothing is retained and no drop counter is bumped. Otherwise line 224 `queue.offer(...)`: for N > 0 the queue was built with `newBlockingQueue(N)` (line 210, `LinkedBlockingQueue(N)`, BlockingQueues.java:43-46) so a full queue rejects and `numDroppedOperations` is incremented (line 225). For N < 0 the queue is unbounded `LinkedBlockingQueue()` and `offer` always succeeds: the cap does not apply and retention grows with timeouts until the next drain. Drain: `popOperations()` (line 235) empties the queue every report interval (constructor, lines 96-99), aggregating by `name()` into a HashMap (so after a drain the transient map is at most the queue's content). Bypass/overshoot: the transient AggregatedOperations map plus log string (`getLogMessage`) exist outside the queue bound but only hold what was already in the queue; `Operation` allocated by the caller before `offer` is garbage when dropped.

**A4. Other consumers.** The Monitorables themselves are also held by in-flight read stages, and the log message StringBuilder at debug level (lines 153-158) holds a string proportional to queued ops. Heap is shared with memtables, caches, etc.

**A5. Evidence beyond the source.** None beyond source (javadoc at MonitoringTask.java:61-65, 191-193). Unit tests exist under `test/unit/org/apache/cassandra/db/monitoring/MonitoringTaskTest.java` (to be checked by the engineer; not relied on).

## B. Verification solution

**B1. Claim under test.** With `cassandra.monitoring_max_operations = N >= 0` the heap retained by queued failed/slow Operations between reports never exceeds about 2 x N Operation objects plus their Monitorables, and N = 0 retains none (the check at line 221 short-circuits); with N < 0 retention is unbounded.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant, a private copy of the tag (`ant jar` in the copy, not the shared tree). Test source: a new JUnit class beside `MonitoringTaskTest` in the private copy; `MonitoringTask.make(int, int)` (line 77, `@VisibleForTesting`) and package-private `addFailedOperation` let the test pick N directly without the JVM property. Use a very long report interval (e.g. 3600000 ms) so the task does not drain during the run.

**B2b. Knobs.** `maxTimedoutOperations` passed to `make`: 0, 1, 50 (default), 1000, -1. Chosen as disabled, minimal, default, large, unbounded.

**B2c. Workload.** For each N, call `addFailedOperation(new FakeMonitorable(...), now)` M = 10000 times with distinct names (a stub `Monitorable` returning a unique short name), with a stub holding a fixed 1 KiB byte[] so retained size is measurable. Limit reached when M > N.

**B2d. Observables and instruments.** (1) `popOperations` result via `getFailedOperations()` (line 118): number of log lines plus the "... (k were dropped)" tail. (2) Retained heap: force `System.gc()` then `Runtime.totalMemory()-freeMemory()` before and after the loop, or a JOL/heap-histogram count of `MonitoringTask$FailedOperation` instances (`jcmd <pid> GC.class_histogram`). Not observable: allocation churn of the discarded Operations (use GC logs if needed).

**B2e. Procedure.** For each N: `MonitoringTask.make(3600000, N)`; record baseline heap; loop M adds; GC; record heap and histogram count of FailedOperation; call `getFailedOperations()` and parse the dropped count; repeat 3 times.

**B2f. Predictions.** N=0: 0 FailedOperation instances retained, 0 lines, no dropped tail, heap delta about 0. N=1: 1 instance, dropped = M-1. N=50: 50 instances (heap delta about 50 KiB + overhead), dropped = M-50. N=1000: 1000 instances, dropped M-1000. N=-1: M instances (about 10 MiB), dropped 0.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Instances = N (N>0) / 0 (N=0), heap delta scales with N | claim confirmed (positive) |
| Instances > N or heap delta unchanged across N | claim wrong |
| N=0 retains instances | line 221 not effective; claim wrong |
| N=-1 retains M instances | positive control for the claim that only the cap bounds usage |
| Instances never reach N (M too small) | limit not reached; not confirmed |

**B2h. Controls.** Same stub payload for every N; GC forced before each reading; reporting task cannot fire (long interval); N=-1 as the uncapped control.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from a private copy of the tag (`ant jar`), 1 GiB heap (`-Xmx1g`), small `cassandra.yaml` data dirs under private scratch. JVM options per run: `-Dcassandra.monitoring_max_operations=N` and `-Dcassandra.monitoring_report_interval_ms=600000` (so queues are not drained during the observation window).

**B3b. Knobs.** N = 0, 50, 5000, -1 via the JVM property; restart per value. Also lower `read_request_timeout` (e.g. 1 ms via yaml `read_request_timeout: 1ms`) so reads time out.

**B3c. Workload.** Table with 1 KiB-wide partitions loaded (100k rows). Drive 200k point reads with distinct, long CQL text (e.g. unique 2 KiB IN-lists via the driver, or cassandra-stress with a user profile) at concurrency 64 so most reads abort/time out under a 1 ms timeout; also set `slow_query_log_timeout` low (1 ms) to feed the slow queue. Total timeouts far exceed 5000.

**B3d. Observables and instruments.** `jcmd <pid> GC.class_histogram` instance counts and bytes for `MonitoringTask$FailedOperation`/`SlowOperation` and `ReadCommand` subclasses, heap used via `jstat -gc` after `jcmd GC.run`; debug.log "were dropped" tail after a forced drain is not triggered, so rely on histogram. Not observable: which command each Operation pins without a heap dump.

**B3e. Procedure.** Start node with the knob; wait for startup; baseline histogram; run workload for 60 s; histogram + `GC.run` + heap reading; stop workload; stop node (`kill`, confirm with `pgrep -f CassandraDaemon`); wipe private data dirs; next N.

**B3f. Predictions.** N=0: zero Failed/SlowOperation instances, heap flat. N=50: at most 50 of each class, pinned command bytes bounded by 100 x command size (about 100s of KiB). N=5000: at most 5000 each, tens of MiB at 2 KiB per command. N=-1: instances grow with the number of timeouts (about 10^5 scale), heap growth in the hundreds of MiB, possibly GC pressure.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Instances capped at N, retained bytes scale with N | claim confirmed |
| Instances exceed N for N >= 0 | claim wrong |
| N=0 shows retained operations | claim wrong |
| N=-1 grows unbounded while N>0 is flat | positive control satisfied |
| Fewer than N timeouts occurred | limit not reached; not confirmed |

**B3h. Controls.** Same data, workload and heap per run; fresh data dir; confirm timeouts occurred via `nodetool tpstats`/`clientrequest` timeout metrics; report interval long in every run.

**B4. Risks and cleanup.** N=-1 can raise heap to OOM on a 1 GiB heap: cap the workload duration. Use private scratch dirs only; delete data dirs after each run; kill the node and the load generator and check `pgrep -f "CassandraDaemon|cassandra-stress"` is empty.

## C. Sources read

- src/java/org/apache/cassandra/db/monitoring/MonitoringTask.java
- src/java/org/apache/cassandra/db/monitoring/MonitorableImpl.java (lines 85-120)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (lines 361, 363)
- src/java/org/apache/cassandra/utils/concurrent/BlockingQueues.java

## D. Stage-4 feedback

`none yet`
