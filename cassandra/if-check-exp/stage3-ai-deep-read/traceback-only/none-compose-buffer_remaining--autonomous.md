# none — trace-back only  <!-- file: traceback-only/none-compose-buffer_remaining--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/cql3/functions/UDFDataType.java:177` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** None; the check at UDFDataType.java:177 (inside `UDFDataType.compose(ProtocolVersion, ByteBuffer)`, declared at UDFDataType.java:175) is pure null/empty-value bookkeeping, not a memory or disk cap. It tests `buffer == null || (buffer.remaining() == 0 && abstractType.isEmptyValueMeaningless())` and returns null for a null or zero-length serialized value, otherwise deserializing via `typeCodec.deserialize` (UDFDataType.java:180). The compared value `buffer.remaining()` is compared against the literal 0, not a limit; `isEmptyValueMeaningless()` is a per-type boolean declared at AbstractType.java:458-461 (default `false`, overridden by some types). There is no configuration entry, JVM property, constant, or runtime-queried limit involved, so there is no default, no settable key, and no restart question.
