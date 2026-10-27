# write_buffer_size — trace-back only  <!-- file: traceback-only/write_buffer_size-append-hint--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/hints/HintsWriter.java:214` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** HintsWriteExecutor.WRITE_BUFFER_SIZE is a compile-time constant (not a yaml key, JVM property or runtime-queried value), first declared at `src/java/org/apache/cassandra/hints/HintsWriteExecutor.java:50` as `static final int WRITE_BUFFER_SIZE = 256 << 10`, i.e. 262144 bytes (256 KiB); the default is the literal shift expression and is not derived from anything else. It sizes the single direct (off-heap) aggregation buffer allocated once in the HintsWriteExecutor constructor (`HintsWriteExecutor.java:60`, `ByteBuffer.allocateDirect(WRITE_BUFFER_SIZE)`), which is passed to `HintsWriter.newSession(buffer)` (`HintsWriteExecutor.java:241`, `HintsWriter.java:136`) and stored as the Session's `buffer` (`HintsWriter.java:179`). The check at `HintsWriter.java:214` (`hint.remaining() <= buffer.remaining()`) compares the serialized hint size to the remaining capacity of that buffer: if the hint fits it is copied into the buffer, otherwise it is written straight to the channel (`HintsWriter.java:220`). It therefore caps per-write buffering memory and is not a limit on hint size or total disk use. It is not settable by yaml, -D property or JMX; changing it requires editing the source and rebuilding/restarting.
