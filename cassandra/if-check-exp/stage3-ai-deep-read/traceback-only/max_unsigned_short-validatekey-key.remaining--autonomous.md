# max_unsigned_short — trace-back only  <!-- file: traceback-only/max_unsigned_short-validatekey-key.remaining--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/cql3/QueryProcessor.java:251` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** FBUtilities.MAX_UNSIGNED_SHORT is a compile-time constant (not a configuration entry, JVM property or runtime-queried value), first declared at src/java/org/apache/cassandra/utils/FBUtilities.java:158 as `public static final int MAX_UNSIGNED_SHORT = 0xFFFF`. The unit is bytes when compared against the partition key's `key.remaining()` in QueryProcessor.validateKey (src/java/org/apache/cassandra/cql3/QueryProcessor.java:245-256; the comparison is at line 251, with the rejecting InvalidRequestException raised in that if-block). Its value is 65535 and is hard-coded, so there is no derivation from memory or disk. It is not settable through a yaml key, a -D property or JMX, and changing it requires editing the source and rebuilding. It exists because the key is serialized with a 2-byte unsigned length prefix (the comment at QueryProcessor.java:248 names ByteArrayUtil.writeWithShortLength and ByteBufferUtil.writeWithShortLength), so it caps the size of a single partition key to fit the format rather than being a configurable memory or disk budget.
