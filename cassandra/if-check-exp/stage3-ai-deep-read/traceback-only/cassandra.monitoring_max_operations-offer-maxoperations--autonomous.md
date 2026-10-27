# cassandra.monitoring_max_operations — trace-back only  <!-- file: traceback-only/cassandra.monitoring_max_operations-offer-maxoperations--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/monitoring/MonitoringTask.java:221` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `cassandra.monitoring_max_operations` (enum `MONITORING_MAX_OPERATIONS`); kind: JVM system property; first declared at `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java:361` as `MONITORING_MAX_OPERATIONS("cassandra.monitoring_max_operations", "50")`; unit: a count of distinct timed-out/slow operations (aggregated by name) held in memory between log reports; default is the literal string "50" at that line, with no derivation from heap or disk. It is read once at class load into `private static final int MAX_OPERATIONS = MONITORING_MAX_OPERATIONS.getInt()` (`MonitoringTask.java:65`), passed through `make(...)` (`MonitoringTask.java:68`, `:77-85`) and the constructor (`MonitoringTask.java:88-91`) to each `OperationsQueue` as `maxOperations` (`MonitoringTask.java:207-209`). The target line `MonitoringTask.java:221` is inside `OperationsQueue.offer(Operation)` (declared at `:219`): `maxOperations == 0` means logging is disabled and the operation is not queued; otherwise a positive value makes the queue a bounded `newBlockingQueue(maxOperations)` and a failed `queue.offer` only increments `numDroppedOperations` (`:210`, `:224-225`), while a negative value gives an unbounded queue (`:191-193`, `:65` comment at `:61-64`), so the memory cap only applies when the value is positive. It is settable only via `-Dcassandra.monitoring_max_operations=<n>` at JVM startup (not a cassandra.yaml key, and no JMX setter found in `MonitoringTask`); because it is a static final read at class initialization, a change requires a restart.
