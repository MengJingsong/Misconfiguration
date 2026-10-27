# block_size — trace-back only  <!-- file: traceback-only/block_size-add-blockindex--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/AbstractBlockPackedWriter.java:62` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** No configurable memory/disk constraint is checked at the target; line 62 (`if (blockIndex == blockValues.length)` in `AbstractBlockPackedWriter.add`, AbstractBlockPackedWriter.java:62) is pure buffer-full bookkeeping that flushes the in-memory `long[]` block to disk (`flush()` at :64, :111-115) when `blockIndex` (declared :44) reaches the array length. The array length is the constructor argument `blockSize` (`blockValues = new long[blockSize]`, AbstractBlockPackedWriter.java:52), which is validated by `checkBlockSize(blockSize, MIN_BLOCK_SIZE, MAX_BLOCK_SIZE)` (:49; SAICodecUtils.java:127-139, requires a power of two within range) against the hard-coded constants `MIN_BLOCK_SIZE = 64` (:34) and `MAX_BLOCK_SIZE = 1 << (30 - 3)` (:35), i.e. 134,217,728 elements. The actual values come from compile-time constants in NumericValuesWriter.java: `BLOCK_SIZE = 128` (:35, non-monotonic) and `MONOTONIC_BLOCK_SIZE = 16384` (:34, monotonic), chosen at :49 (`monotonic ? MONOTONIC_BLOCK_SIZE : BLOCK_SIZE`) and passed to `BlockPackedWriter`/`MonotonicBlockPackedWriter` at :61-62; the only constructions (SSTableComponentsWriter.java:58-72) use the 4-argument form, so no caller overrides the size. These are unit-less element counts (longs, so 1 KiB and 128 KiB of heap per writer by default), derived from nothing (fixed literals), and are not settable via cassandra.yaml, a -D property, or JMX; changing them requires a source change and rebuild/restart. The block-size limits only bound a small per-writer buffer and are not a tunable memory or disk cap.
