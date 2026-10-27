# native_protocol_v1_v2_max_element_size — trace-back only  <!-- file: traceback-only/native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/cql3/functions/types/CodecUtils.java:250` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** There is no memory or disk constraint here. Line 250 sits in `CodecUtils.sizeOfValue(ByteBuffer, ProtocolVersion)`, in the `if (elemSize > 65535)` check (line 250) under `case V1`/`case V2` (`CodecUtils.java:246-251`). That check compares `elemSize = value.remaining()` (line 249) with the literal `65535`, which is a hard-coded constant declared inline at line 250 and nowhere else. It is the CQL native protocol v1/v2 wire-format limit: collection elements are encoded with a 2-byte unsigned length prefix (`sizeOfCollectionSize` returns 2 for V1/V2, lines 229-231), so an element cannot exceed 65535 bytes. The unit is bytes. It has no default, because it is not derived from anything. It cannot be set through a yaml key, a -D property or JMX, and it cannot be changed without recompiling. It is not a limit meant to cap memory or disk use. It only keeps the value representable in the protocol's 16-bit length field, and for V3 and later (lines 252-256) the length is 4 bytes and no such check applies.
