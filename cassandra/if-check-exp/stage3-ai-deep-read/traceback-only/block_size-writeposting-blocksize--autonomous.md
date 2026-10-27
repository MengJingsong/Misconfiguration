# block_size — trace-back only  <!-- file: traceback-only/block_size-writeposting-blocksize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sai/disk/v1/postings/PostingsWriter.java:222` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** There is no memory or disk cap here. The check at `PostingsWriter.java:222` (`bufferUpto == blockSize` in `writePosting`) compares the count of deltas buffered so far against `blockSize`, an instance field set at `PostingsWriter.java:126` from the constructor argument. The only non-test callers pass the hard-coded constant `BLOCK_SIZE`, declared at `PostingsWriter.java:89` as `private final static int BLOCK_SIZE = 128` (callers at `:110` and `:115`). The comment at `:88` says it mirrors Lucene50PostingsFormat.BLOCK_SIZE, and the class javadoc (`:49-50`) calls the size fixed. The fourth constructor (`:119-122`) takes an arbitrary `blockSize` but is `@VisibleForTesting`, so only tests use it. The unit is the number of postings (longs) per FoR-compressed block. The value 128 is a compile-time constant. It has no yaml key, no -D property and no JMX setter, and changing it needs a code change and a rebuild. It also sizes the `deltaBuffer = new long[blockSize]` allocation at `:129`, which is about 1 KB per writer. That is a fixed on-disk format and buffering parameter, not a configurable resource limit. The line is block-boundary bookkeeping: when the buffer is full it adds a skip-table entry, writes the block and resets the counters (`:224-226`).
