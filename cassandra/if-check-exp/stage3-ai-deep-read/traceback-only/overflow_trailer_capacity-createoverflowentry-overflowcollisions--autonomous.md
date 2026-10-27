# overflow_trailer_capacity — trace-back only  <!-- file: traceback-only/overflow_trailer_capacity-createoverflowentry-overflowcollisions--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sasi/disk/AbstractTokenTreeBuilder.java:323` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** OVERFLOW_TRAILER_CAPACITY is a compile-time constant (not a configuration entry or JVM property), checked at AbstractTokenTreeBuilder.java:323 (`overflowCollisions.size() == OVERFLOW_TRAILER_CAPACITY` inside createOverflowEntry, which throws an AssertionError at line 324) and first declared in the interface TokenTreeBuilder.java:35 as `OVERFLOW_TRAILER_BYTES / OVERFLOW_ENTRY_BYTES`. Its unit is a count of 8-byte offset entries per SASI token-tree leaf block, and it caps the on-disk size of the overflow-collision trailer. The default is derived as 64 / 8 = 8 entries, from OVERFLOW_TRAILER_BYTES = 64 (TokenTreeBuilder.java:33) and OVERFLOW_ENTRY_BYTES = Long.BYTES = 8 (TokenTreeBuilder.java:34). The same trailer size is subtracted from the 4096-byte BLOCK_BYTES (TokenTreeBuilder.java:29) when computing TOKENS_PER_BLOCK (TokenTreeBuilder.java:36). It is hard-coded, so it cannot be set through yaml, a -D property or JMX, and changing it would require editing the source and rebuilding. It would also alter the on-disk SASI index format.
