# none — trace-back only  <!-- file: traceback-only/none-read-count--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sai/disk/v1/vector/RandomAccessReaderAdapter.java:117` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** None; the check is not a resource constraint. The target line, `if (count > intBuffer.remaining())` at RandomAccessReaderAdapter.java:117, sits in `read(int[] dest, int offset, int count)` (declared at line 91). It is pure bookkeeping. `count` is the caller-supplied number of ints to read (line 91), and `intBuffer.remaining()` is the number of ints left in the current rebuffered region. That region comes from `bufferHolder` (RandomAccessReader.java:40, refilled at RandomAccessReader.java:67 via `rebufferer.rebuffer(position)`), either as `bh.intBuffer()` (line 105) or `bb.asIntBuffer()` (line 114). The branch only detects that the requested slice crosses a region boundary. In that case the slow path at lines 119-123 allocates a heap buffer of `Integer.BYTES * count` bytes and reads via `readFully`. It does not compare against any configuration entry, JVM property, or limit, and it neither caps nor enforces memory or disk use. The region size is set elsewhere by the rebufferer/chunk layout of the FileHandle (line 42 uses `fileHandle.instantiateRebufferer(null)`). I did not trace that size further, so whether it derives from a configurable value is not verified.
