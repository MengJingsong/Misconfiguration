# sai_vector_search_max_top_k — trace-back only  <!-- file: traceback-only/sai_vector_search_max_top_k-validate-command.limits.count--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java:503` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `MAX_TOP_K`, backed by the JVM system property `cassandra.sai.vector_search.max_top_k` (enum `SAI_VECTOR_SEARCH_MAX_TOP_K`); kind: JVM property (read into a constant). The property is first declared at `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java:479` with default string "1000". The constant is declared at `src/java/org/apache/cassandra/index/sai/disk/v1/IndexWriterConfig.java:57` as `public static final int MAX_TOP_K = SAI_VECTOR_SEARCH_MAX_TOP_K.getInt()`, and it is imported into `StorageAttachedIndex.java:118`. The check is in `StorageAttachedIndex.validate(ReadCommand)` (`StorageAttachedIndex.java:497`). At line 503 a vector-index query is rejected with InvalidRequestException (message `ANN_LIMIT_ERROR`, line 141) if `command.limits().count() > MAX_TOP_K`. The code comment at line 502 says the purpose is to avoid overflow of the vector graph internal data structure and OOM when filtering top-k. Unit: number of rows (the CQL LIMIT on an ANN OF ordering query). The default is the literal 1000, not derived from any resource. `getInt()` (`CassandraRelevantProperties.java:794-800`) reads `System.getProperty(key)` and falls back to the default. It is set with `-Dcassandra.sai.vector_search.max_top_k=<n>` at JVM startup. Because it is stored in a static final field, a change needs a restart; I found no yaml key or JMX setter for it (the only references to `MAX_TOP_K` in the source tree under `org/apache/cassandra` were the ones cited above).
