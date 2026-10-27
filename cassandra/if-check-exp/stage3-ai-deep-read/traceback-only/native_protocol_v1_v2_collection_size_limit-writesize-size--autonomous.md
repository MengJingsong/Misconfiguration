# native_protocol_v1_v2_collection_size_limit — trace-back only  <!-- file: traceback-only/native_protocol_v1_v2_collection_size_limit-writesize-size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/cql3/functions/types/CodecUtils.java:101` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** There is no memory or disk constraint at this line. The check at `src/java/org/apache/cassandra/cql3/functions/types/CodecUtils.java:101` (`if (size > 65535)` inside `private static void writeSize(ByteBuffer output, int size, ProtocolVersion version)`, switch cases `V1`/`V2` at lines 99-100) is a hard-coded literal constant, declared inline at that line and nowhere else. It is the wire-format limit of native protocol v1/v2, which encodes a collection element count as an unsigned 16-bit short (`output.putShort((short) size)` immediately follows the check). The unit is elements in a collection, the value is 65535 (2^16-1), and it is not derived from anything. It is not a configuration entry, JVM property or runtime-queried limit, so it cannot be set through yaml, -D or JMX, and changing it would require a source change and rebuild. For V3 through V6 the same method writes a 4-byte int with `output.putInt(size)` and applies no such cap, so the check says nothing about heap or disk use.
