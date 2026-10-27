# block_packed_max_block_size — trace-back only  <!-- file: traceback-only/block_packed_max_block_size-checkblocksize-blocksize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sai/disk/v1/SAICodecUtils.java:129` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `AbstractBlockPackedWriter.MAX_BLOCK_SIZE` (with its lower bound `MIN_BLOCK_SIZE`), a hard-coded constant (not a configuration entry, JVM property or runtime-queried limit), first declared at `src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/AbstractBlockPackedWriter.java:35` (`1 << (30 - 3)`, i.e. 134,217,728; `MIN_BLOCK_SIZE = 64` is at line 34). The unit is the number of long values per block (the writer allocates `new long[blockSize]` at line 51). The target line `SAICodecUtils.java:129` is in `checkBlockSize(int blockSize, int minBlockSize, int maxBlockSize)` (declared at line 127) and tests `blockSize >= minBlockSize && blockSize <= maxBlockSize`. Otherwise it throws `IllegalArgumentException` (line 142), and a non-power-of-two also throws (line 133). The constants are passed in by the writer constructor (`AbstractBlockPackedWriter.java:49`) and by the readers (`BlockPackedReader.java:55`, `MonotonicBlockPackedReader.java:53`), where the checked value is `meta.blockSize`, read from the file at `NumericValuesMeta.java:34`. The actual block sizes written are fixed constants, `NumericValuesWriter.BLOCK_SIZE = 128` (line 35) and `MONOTONIC_BLOCK_SIZE = 16384` (line 34), chosen at line 49. The check is therefore a format-sanity bound (it guards against a corrupt or absurd block size before allocating) rather than a tunable cap. Default: not derived, it is the literal values above. It cannot be set through a yaml key, -D property or JMX (no such reference found in the files read), and changing it requires a code change and rebuild/restart.
