# tokens_per_block — trace-back only  <!-- file: traceback-only/tokens_per_block-add-pos--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sasi/disk/AbstractTokenTreeBuilder.java:520` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `TOKENS_PER_BLOCK` is a compile-time constant (not a configuration entry, JVM property or runtime-queried limit), first declared as an `int` field of the `TokenTreeBuilder` interface at `src/java/org/apache/cassandra/index/sasi/disk/TokenTreeBuilder.java:36`. The check is `if (pos == TOKENS_PER_BLOCK)` in `InteriorNode.add` at `AbstractTokenTreeBuilder.java:520`, where `pos = tokens.size()` (line 519); when the node is full it calls `split()` (line 522) instead of adding another token. The unit is tokens per on-disk tree block. The value is derived as `(BLOCK_BYTES - BLOCK_HEADER_BYTES - OVERFLOW_TRAILER_BYTES) / BLOCK_ENTRY_BYTES` = (4096 - 64 - 64) / 16 = 248, from `BLOCK_BYTES = 4096` (line 30), `BLOCK_HEADER_BYTES = 64` (line 31), `BLOCK_ENTRY_BYTES = 2 * Long.BYTES` (line 32) and `OVERFLOW_TRAILER_BYTES = 64` (line 33), all in the same file. It is not settable by yaml, -D property or JMX; changing it requires recompiling and would change the SASI on-disk format. It is a fixed node-capacity (fan-out) limit that keeps each node within one 4096-byte block, so it is structural bookkeeping for the SASI token tree layout rather than a tunable memory or disk cap. The only related size limit is `MAX_OFFSET = (1L << 47) - 1` (line 38), checked at `AbstractTokenTreeBuilder.java:297`, which is also a hard-coded constant.
