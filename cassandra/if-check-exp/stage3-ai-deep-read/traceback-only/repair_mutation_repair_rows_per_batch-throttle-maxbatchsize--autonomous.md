# repair_mutation_repair_rows_per_batch — trace-back only  <!-- file: traceback-only/repair_mutation_repair_rows_per_batch-throttle-maxbatchsize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/rows/ThrottledUnfilteredIterator.java:234` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** The target (ThrottledUnfilteredIterator.java:234, `if (maxBatchSize == 0) // opt out` inside the static method `throttle(UnfilteredPartitionIterator, int maxBatchSize)`, declared at line 232) is only the opt-out test; the javadoc at lines 225-231 says maxBatchSize is the max number of unfiltereds per UnfilteredRowIterator and 0 means no throttle. The only caller found is CassandraStreamReceiver.java:212, which passes `MAX_ROWS_PER_BATCH`, declared at CassandraStreamReceiver.java:63 as `REPAIR_MUTATION_REPAIR_ROWS_PER_BATCH.getInt()`; the comment at lines 209-210 says the split is "to avoid OOMing and generating heap pressure". The constraint is therefore the JVM system property `cassandra.repair.mutation_repair_rows_per_batch` (CassandraRelevantProperties enum entry REPAIR_MUTATION_REPAIR_ROWS_PER_BATCH), first declared at config/CassandraRelevantProperties.java:410. Unit: rows/unfiltereds per batch (a count, not bytes). Default: the hard-coded string "100" at CassandraRelevantProperties.java:410, used when System.getProperty returns null (getInt, lines 794-800); it is not derived from any other value. It is set with -Dcassandra.repair.mutation_repair_rows_per_batch=N at JVM start; MAX_ROWS_PER_BATCH is a `private static final` read once at class load (CassandraStreamReceiver.java:63), so a change needs a restart. A value of 0 disables throttling (line 234). No yaml key or JMX setter was found (only the grep for MAX_ROWS_PER_BATCH and the property name was done; other setters not verified).
