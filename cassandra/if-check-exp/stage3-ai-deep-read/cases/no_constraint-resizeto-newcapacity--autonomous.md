# no-op resize guard in SafeMemoryWriter.resizeTo — verification solution  <!-- file: cases/no_constraint-resizeto-newcapacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`SafeMemoryWriter.java:52`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SafeMemoryWriter.java#L52) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code, 2026-10-27 |
| Estimate | `negative`: no constraint. The check `newCapacity != capacity()` only skips a reallocation when the size is unchanged; it caps nothing. |
| Ground | The check compares two sizes of the same buffer for equality. It is not a limit, and whichever branch runs, the resulting size is set by the caller (`calculateNewSize` or `length()`), not by this check. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands of the compared pair:
- `newCapacity`: the parameter of `resizeTo(long)` ([`SafeMemoryWriter.java:50`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SafeMemoryWriter.java#L50)). It comes from `calculateNewSize(count)` (SafeMemoryWriter.java:47) or `length()` (SafeMemoryWriter.java:71).
- `capacity()`: `memory.size()` (SafeMemoryWriter.java:89-92), the byte size of the current off-heap `SafeMemory`.
No declared constant, numeric literal, yaml entry or JVM property is in the comparison itself. Constants and a JVM property appear only upstream in `calculateNewSize` (DataOutputBuffer.java:158-172: `1024L*1024L*DOUBLING_THRESHOLD`, with `DOUBLING_THRESHOLD = DOB_DOUBLING_THRESHOLD_MB.getLong()` at DataOutputBuffer.java:48) and in `validateReallocation` (SafeMemoryWriter.java:101-107, `Integer.MAX_VALUE`). They shape the growth size, and the check at line 52 does not test against them.

**A2. What it caps.** Nothing. The object involved is an off-heap `SafeMemory` region. The check could only bound the number of reallocations (skip the copy when the size is equal), not the size held. The size is fixed by the value passed in. `validateReallocation` (not the target) clamps growth to `length() + Integer.MAX_VALUE`.

**A3. Mechanism.** Enclosing method: `resizeTo(long newCapacity)`, [`SafeMemoryWriter.java:52`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SafeMemoryWriter.java#L52).
- True (size differs): records position and byte order (54-55), `memory.copy(newCapacity)` allocates a new `SafeMemory` and copies `min(size,newSize)` bytes (SafeMemory.java:70-75), rebuilds the tail buffer (59-63), then frees the old buffer (65).
- False (size equal): does nothing; the existing memory is kept.
- Callers: `expandToFit(long)` (47), reached from `DataOutputBuffer` write paths when the buffer is full; and `trim()` (71, `resizeTo(length())`), which is a no-op when the writer is already exactly full.
- Users of the class: only `IndexSummaryBuilder` (`offsets`, `entries`, IndexSummaryBuilder.java:45-46, 126-127), which calls `trim()` at 250-251 and guards `entries.length() + entrySize <= Integer.MAX_VALUE` at 204 (a separate check, not this target).
- Bypass or overshoot: not applicable, since there is no limit here.

**A4. Other consumers.** The same off-heap memory is also used by `IndexSummary` through `currentBuffer().sharedCopy()` (IndexSummaryBuilder.java:275-276). None of it is controlled by this check.

**A5. Evidence beyond the source.** Searched in the tree for: callers of `resizeTo`, `trim`, `SafeMemoryWriter` (the results above); config keys naming the writer (none; only `DOB_DOUBLING_THRESHOLD_MB`, which acts in `calculateNewSize`); no tests or docs were relied on. No issue-tracker or history reading; the claim rests on the code alone.

## B. Verification solution

**B1. Claim under test.** The guard `newCapacity != capacity()` does not cap memory or disk usage: it only skips a same-size reallocation, and the writer's size is set by the written data and the growth policy, not by this check.

### B2. Unit tier

`n/a: no constraint, there is no limit operand to drive past.` Answered instead by A1 and A3: both operands are sizes of the same buffer, and both branches are shown above. (Optional sanity check for a reader: a small test constructing `new SafeMemoryWriter(16)`, writing 16 bytes, calling `trim()` and seeing `currentBuffer()` unchanged, shows the false branch; writing 17 bytes and seeing capacity change shows the true branch. This needs no build here.)

### B3. Cluster tier

`n/a: no constraint, no cluster workload moves a limit here.` A1-A3 answer the question: the only runtime path is index-summary building during flush/compaction, where the size follows the key count and the growth policy. B4 below applies only if the optional check is run.

**B4. Risks and cleanup.** None for design only. If the optional unit check is run, close the writer (`close()`) to free off-heap memory, and build outside the shared source tree.

## C. Sources read

- src/java/org/apache/cassandra/io/util/SafeMemoryWriter.java
- src/java/org/apache/cassandra/io/util/DataOutputBuffer.java (lines 48, 155-182)
- src/java/org/apache/cassandra/io/util/SafeMemory.java
- src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java

## D. Stage-4 feedback

`none yet`
