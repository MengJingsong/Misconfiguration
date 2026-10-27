# none — trace-back only  <!-- file: traceback-only/none-readfully-dest_length--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sai/disk/v1/vector/RandomAccessReaderAdapter.java:69` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** None: the check at RandomAccessReaderAdapter.java:69 (`if (dest.length > floatBuffer.remaining())`) inside `readFully(float[] dest)` (declared at line 46) is pure bookkeeping, not a memory or disk cap. It compares the number of floats the caller asked for (`dest.length`, set by the caller's array size) with the floats left in the current buffer region (`floatBuffer.remaining()`, built at lines 57-58 or 64-66 from the `BufferHolder` returned by the rebufferer). If the request spills past the region, the code takes the "slow path" at lines 71-74: it allocates a temporary `ByteBuffer` of `Float.BYTES * dest.length` (line 72) and calls `readFully(bb)` (line 73). So the check only picks between a zero-copy read and a copying read, and it enforces no limit. The region size comes from the file's rebufferer (`fileHandle.instantiateRebufferer(null)`, line 42). I did not trace how that chunk or region size is configured, so that part is not verified. No yaml key, -D property, JMX setting or restart requirement applies to this line.
