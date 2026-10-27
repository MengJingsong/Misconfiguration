# cassandra.virtual.logs.max.rows — trace-back only  <!-- file: traceback-only/cassandra.virtual.logs.max.rows-boundedlinkedlist.add-maxsize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/virtual/LogMessagesTable.java:193` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** The in-memory row capacity of the `system_logs` virtual table (`LogMessagesTable`), a JVM system property `cassandra.virtual.logs.max.rows`, declared as the enum entry `LOGS_VIRTUAL_TABLE_MAX_ROWS` in `CassandraRelevantProperties.java:338`. The checked operand is `BoundedLinkedList.maxSize` (`LogMessagesTable.java:178`, compared at `:193` as `size() == maxSize`, evicting the oldest entry via `removeLast()` at `:194`). It is set in the constructor (`:185-188`), receives the `size` passed from `BoundedLinkedList.create(size)` (`:91`, `:180-182`), which comes from `resolveBufferSize()` (`:74`, `:147-152`). The unit is log rows (LogMessage entries held on heap), not bytes. The default is 50,000 (`LOGS_VIRTUAL_TABLE_DEFAULT_ROWS`, constant at `LogMessagesTable.java:58`, passed as the property default via `convertToString` at `CassandraRelevantProperties.java:338`). The value is read with `getInt()` (`:149`) and validated against hard-coded constants, minimum 1,000 (`:57`) and maximum 100,000 (`:59`); a value outside that range silently falls back to 50,000 (`:150-151`). It can be set only by the `-Dcassandra.virtual.logs.max.rows=<n>` JVM property (no yaml key, no JMX); it is read once when the table is constructed (`:72-75`), so changing it requires a restart.
