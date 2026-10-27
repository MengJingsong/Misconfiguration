# none — trace-back only  <!-- file: traceback-only/none-validatekey-key_remaining--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/cql3/Validation.java:47` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** None for the target line. Validation.java:47 sits in `validateKey(TableMetadata, ByteBuffer)` (Validation.java:45) and is `if (key == null || key.remaining() == 0)`, which is a null/empty-key sanity check that throws "Key may not be empty" (Validation.java:48). It compares against the literal 0 and no configuration entry, JVM property or runtime-queried limit, and it caps no memory or disk use. The only size check in the method is the adjacent line 51, `key.remaining() > FBUtilities.MAX_UNSIGNED_SHORT`. That constant is declared at FBUtilities.java:158 as `public static final int MAX_UNSIGNED_SHORT = 0xFFFF`. It is a hard-coded constant in bytes (65535), the largest length that `writeWithShortLength` can serialize (Validation.java:50 comment). It has no default derivation and cannot be set by yaml, -D property or JMX, so changing it requires a code change and rebuild. It is a wire/serialization-format limit rather than a memory or disk cap.
