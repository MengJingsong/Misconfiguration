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

#### B2 amendment, 2026-10-29 (stage-4 audit; applies `none-type-design.md` §3-§4; changes no estimate; B2 as filed is `n/a` and is replaced by this design)

**Operand kind: 3** (`newCapacity` is a byte size asked of an off-heap `SafeMemory`). "Usage follows the operand" is expected here (the operand is the size) and is not a finding; the finding is what the branch changes at equal operand. Audit corrections to the filed trace (none changes the claim): `Memory(long)` rejects `bytes <= 0` with an `AssertionError` (Memory.java:62-63) and allocates at Memory.java:65 (`MemoryUtil.allocate`, an `Unsafe` malloc that `ThreadMXBean.getThreadAllocatedBytes` cannot see); `SafeMemory.copy` is SafeMemory.java:70-75 (allocation at 72); `SafeMemoryWriter.expandToFit` (45-48) does not have `DataOutputBuffer.expandToFit`'s `count <= 0` early return; growth sizes come from `DataOutputBuffer.calculateNewSize` (DataOutputBuffer.java:158-172, `DOUBLING_THRESHOLD` default 64 MiB from `CassandraRelevantProperties.java:203`), and an equal size is reached from `trim()` only (SafeMemoryWriter.java:69-72) on an exactly full writer; the production caller is `IndexSummaryBuilder.prepareToCommit` (IndexSummaryBuilder.java:250-251).

**a. Trigger.** New JUnit class `SafeMemoryResizeToTest` in package `org.apache.cassandra.io.util` (the harness), run with `java` + JUnitCore, **not** `ant testsome`, with the Byteman agent attached (B2c). It builds `new SafeMemoryWriter(C)`, fills it with a known byte pattern through `write(byte[])` (an exact fit does not call `doFlush`, BufferedDataOutputStreamPlus.java:87-113), then calls the public `trim()` (the production caller). The existing `SafeMemoryWriterTest.testTrim` is the neighbour; it asserts nothing about allocation.

**b. Sweep (stated before the run).** Capacity C in {1 KiB, 64 KiB, 1 MiB, 64 MiB, 512 MiB} (five orders). Fresh JVM per C (`-Xmx512m`), one discarded warm-up cycle, then 5 repetitions of four arms on fresh writers:
- **E** (check false): fill C, `trim()`.  **D** (check true, differs by 1): fill C-1, `trim()`.  **H** (check true, half): fill C/2, `trim()`.
- **X** (the counterfactual the check skips, at the same operand as E): fill C, then call `currentBuffer().copy(C)` directly and close the copy. It is what the true branch would do at equal size.
Control JVM (B2h): C = 8 MiB, filled, then one more byte written (`expandToFit(1)`), with the default threshold and with `-Dcassandra.DOB_DOUBLING_THRESHOLD_MB=1`.

**c. Measure.** A Byteman ledger (helper class `NativeLedger` in the harness, compiled into the test classes) fed by three rules: entry of `SafeMemory.copy` (counts copies), line 65 of `Memory.<init>(long)` (records `$bytes` of every native allocation) and entry of `SafeMemory$MemoryTidy.tidy` (records the freed size when `peer != 0`). Before each call the ledger is reset with `live = capacity`; it reports per call: copies, allocation count and bytes, free count and bytes, **peak live native bytes** (the transient peak, old and new region together) and live bytes after. Also: `writer.capacity()` after (SafeMemoryWriter.java:89-92), three read-back bytes (offsets 0, middle, length-1) against the pattern, and `getThreadAllocatedBytes` around the call for the on-heap residue (this instrument is blind to the malloc; it is used only for residue).

**d. Branch flip.** E against X at the same C (what the check skips), and E against D at the same C (retained size, differs by one byte).

**e. Prediction (frozen with this amendment; every figure is an exact integer unless a bound is given).** For every C and every repetition:
- **E:** copies 0, allocations 0, allocated bytes 0, frees 0, peak live = C, live after = C, capacity after = C.
- **D:** copies 1, allocations 1, allocated bytes C-1, frees 1 (freed bytes C), **peak live = 2C-1**, live after = C-1, capacity after = C-1.
- **H:** copies 1, allocated bytes C/2, peak live = C + C/2, live after = C/2, capacity after = C/2.
- **X:** allocated bytes C, peak live = 2C, live after = C (copy closed); the retained capacity of the writer is C, equal to E.
- Retained capacity of E and D differs by exactly 1 byte; read-back bytes match the pattern for D and H.
- On-heap residue: E at most 1 KiB; D, H, X at most 16 KiB; and for each arm the largest residue over the five C minus the smallest at most 4 KiB (the residue does not follow C).
- Control: default threshold, allocated bytes 16,777,216 (2C); threshold 1, allocated bytes 12,582,912 (1.5C); the two differ by exactly 4,194,304 (arithmetic of DataOutputBuffer.java:166-169).
- Noise floor: the five repetitions of one arm give identical native figures (spread 0 bytes); the residue spread is recorded and any residue claim smaller than it is "not resolved".

**f. Positive control (B2h).** The growth knob `cassandra.DOB_DOUBLING_THRESHOLD_MB` (read once at class load, DataOutputBuffer.java:48, so each value needs its own JVM) moves the same ledger by 4 MiB (item e). It is a *sibling* control: it acts in `calculateNewSize`, not at line 52, and it is a growth policy, not a cap; **no setting binds the native bytes of a `SafeMemoryWriter` as a limit**, which the results file states. It shows the instrument reads an allocation-size change of the right size. Known-answer: arm X must read exactly C.

**g. Conclusions table (B2g).**

| Reading | Verdict | Effect on the constraint |
|---|---|---|
| E allocates 0 bytes and makes 0 copies, X allocates C with peak 2C, D allocates C-1 with peak 2C-1, retained capacity after is C (E and X) and C-1 (D), control moved by 4 MiB, ledger counted | **Confirmed** | `does not cap`. The check skips a redundant same-size copy (a transient of one extra region); it bounds no retained size and no operand. |
| Retained capacity after the call differs by more than 1 byte between E and X, or E allocates | **Refuted** | `caps` (or a mechanism misread; the case file would be amended) |
| Control did not move by 4 MiB, or D shows 0 allocations (the rule did not fire), or the ledger live-after disagrees with `capacity()` | **Invalid** / **Not confirmed** | `undetermined` |
| A residue sub-prediction misses while every native figure holds | **Confirmed** with the miss recorded | `does not cap` (the residue is a side figure; it cannot decide the verdict) |

Judgement recorded before the run: the design's §4 row "the check gates an allocation" would read `caps` if applied mechanically. Here it gates a **transient** copy whose result has the same size as what it replaces, and only on an exactly full writer; the retained size is identical on both branches. A cap would bound a retained or requested size. This is why the row above reads `does not cap`; a reader who defines "caps" as "changes any allocation" would call it otherwise, and the results file shows the figures for both readings.

**h. Hold fixed.** JDK 11, `-Xmx512m`, Byteman 4.0.20 from the build, one writer at a time, single thread, writers closed after each call; no `Unsafe` allocation outside the ledger's window.

### B3. Cluster tier

`n/a: no constraint, no cluster workload moves a limit here.`

**B3 amendment, 2026-10-29.** Stays `n/a`: the exact-fit equal branch needs an exactly full writer, which a flush or compaction reaches only by coincidence, and the transient copy it skips is an index summary (key count x entry size, MiB scale), below the heap noise of a node (about 16 MiB with G1) and native memory is outside the heap sampler. The sweep above reaches 512 MiB in the unit tier, so the unit tier decides. A1-A3 answer the question: the only runtime path is index-summary building during flush/compaction, where the size follows the key count and the growth policy. B4 below applies only if the optional check is run.

**B4. Risks and cleanup.** None for design only. If the optional unit check is run, close the writer (`close()`) to free off-heap memory, and build outside the shared source tree.

## C. Sources read

- src/java/org/apache/cassandra/io/util/SafeMemoryWriter.java
- src/java/org/apache/cassandra/io/util/DataOutputBuffer.java (lines 48, 155-182)
- src/java/org/apache/cassandra/io/util/SafeMemory.java
- src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java

## D. Stage-4 feedback

**2026-10-29 — unit tier run and self-checked; B3 `n/a`.** Results: [`results/no_constraint-resizeto-newcapacity--autonomous.md`](../../stage4-runtime-verification/results/no_constraint-resizeto-newcapacity--autonomous.md). Verdict **Confirmed — does not cap** (outcome class: true negative). The frozen text is everything above this section (B2 amendment of 2026-10-29); the estimate is unchanged.

- Readings (five orders, C = 1 KiB to 512 MiB, 5 repetitions each, exact integers): E (exactly full, `trim()`) made 0 copies and 0 native allocations; D (one byte less) made 1 copy of C-1 bytes and freed C, transient peak 2C-1, retained C-1; H (half) allocated C/2; X (`copy(C)`, what the check skips at equal size) allocated C with peak 2C and retained C. Retained capacity E minus D = 1 byte at every C. Control: `DOB_DOUBLING_THRESHOLD_MB` 64 (default) vs 1 moved the growth allocation 16,777,216 to 12,582,912 (exactly 4,194,304).
- What the check does: at an exactly full writer it skips a redundant same-size copy whose transient peak would be 2C. It bounds no retained size. This is the judgement written into B2g before the run (a skipped redundant transient is not a cap).
- Audit corrections (none changes the claim): `Memory(long)` throws `AssertionError` for `bytes <= 0` (Memory.java:62-63) and allocates at :65; `SafeMemoryWriter.expandToFit` (45-48) lacks the `count <= 0` return of `DataOutputBuffer.expandToFit`; the stage-4 draft's lines held (SafeMemory.java:70-75, SafeMemoryWriter.java:50-72, IndexSummaryBuilder.java:250-251, CassandraRelevantProperties.java:203).
- Missed sub-prediction (recorded, verdict-neutral by the B2g last row): the on-heap residue of arm D was 3,976 B in three of five repetitions but 18,832 B and 17,432 B in repetitions 2 and 5 at every C (above the 16 KiB bound and the 4 KiB spread); the same values at every C, so the residue does not follow C.
- Weaker than it looks: no setting caps the native bytes of a `SafeMemoryWriter`, so the positive control is a sibling (growth policy); it shows the ledger reads a size change of the right size, not a cap. Unit tier only; B3 stays `n/a` (reason in B3).
