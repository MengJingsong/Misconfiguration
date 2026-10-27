# max_unsigned_short — trace-back only  <!-- file: traceback-only/max_unsigned_short-validateindexedvalue-value_remaining--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/internal/CassandraIndex.java:618` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `FBUtilities.MAX_UNSIGNED_SHORT`; kind: hard-coded constant (not a configuration entry, JVM property or runtime-queried limit); first declared at `src/java/org/apache/cassandra/utils/FBUtilities.java:158` as `public static final int MAX_UNSIGNED_SHORT = 0xFFFF`; unit: bytes (the maximum size of a value whose length is serialized as an unsigned 16-bit short); default/value: 65535, a literal with no derivation from other settings; it is not settable via yaml, -D property or JMX, and changing it would require editing the source and rebuilding. The target check is `CassandraIndex.validateIndexedValue` (`CassandraIndex.java:618`), which rejects an indexed cell value when `value.remaining() >= FBUtilities.MAX_UNSIGNED_SHORT` (note `>=`, so the effective limit is 65534 bytes) by throwing an InvalidRequestException ("Cannot index value of size %d ... maximum allowed size=%d", `CassandraIndex.java:620-626`). The same constant caps other key/clustering/marker sizes (e.g. `QueryProcessor.java:259`, `Validation.java:51`, `ClusteringPrefix.java:278`), so this is a serialization-format size limit on a single indexed value, which bounds the size of the index row key (the indexed value becomes the index table's partition key) rather than a tunable memory/disk budget.
