# no-constraint — BufferPoolAllocator.Wrapped.capacity(int) equality short-circuit — verification solution  <!-- file: cases/no_constraint-capacity-newcapacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`BufferPoolAllocator.java:121`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/BufferPoolAllocator.java#L121) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative` (no constraint): the check is a no-op short-circuit on "resize to the same size"; it caps nothing. |
| Ground | Both operands are runtime values (requested capacity vs current capacity); the check only avoids a redundant reallocation and sets no limit. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands: `newCapacity`, the int parameter of `Wrapped.capacity(int)` ([`BufferPoolAllocator.java:119`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/BufferPoolAllocator.java#L119)), supplied by Netty callers; and `capacity()`, the current capacity of the wrapped direct buffer (Netty `UnpooledUnsafeDirectByteBuf`, set from `wrap` in the constructor at `BufferPoolAllocator.java:112-115`). No declared constant, no numeric literal, no yaml entry or JVM property is involved. The condition is `newCapacity == capacity()` ([`BufferPoolAllocator.java:121`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/BufferPoolAllocator.java#L121)).

**A2. What it caps.** Nothing. It could in principle relate to the off-heap network buffer-pool buffer held by the `Wrapped` ByteBuf, but it only tests equality of requested and current size, so it bounds no memory or disk object.

**A3. Mechanism.** Enclosing method: `Wrapped.capacity(int newCapacity)` ([`BufferPoolAllocator.java:119-131`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/BufferPoolAllocator.java#L119-L131)), an override of Netty's `ByteBuf.capacity(int)`. If-statement: [`BufferPoolAllocator.java:121`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/BufferPoolAllocator.java#L121).
- True: returns `this` unchanged (line 122); no reallocation, nothing returned to the pool.
- False: `super.capacity(newCapacity)` (line 124) allocates/reallocates via `allocateDirect` (line 134-137, `bufferPool.getAtLeast(initialCapacity, OFF_HEAP)`), the old `wrapped` buffer is returned to the pool via `bufferPool.put(wrapped)` (line 128), and `wrapped` is replaced (line 129). Growth size is chosen by Netty (e.g. `ensureWritable`/`calculateNewCapacity`, bounded by the ByteBuf's `maxCapacity` set in the constructor, line 114), not by this check.
- Callers: no direct call in the Cassandra tree (`grep "\.capacity("` in `net/` finds only `ByteBuffer.capacity()` uses, e.g. `FrameEncoder.java:65`, `FrameDecoder.java:393`); it is invoked by Netty internals on resize. Bypass: none relevant; the pool's own caps are enforced in `BufferPool`, not here.

**A4. Other consumers.** The network `BufferPool` (`BufferPools.forNetworking()`, line 40) is shared by all network ByteBufs and is capped separately by its own limit in `BufferPool`; this check does not interact with it.

**A5. Evidence beyond the source.** Netty `AbstractByteBuf.capacity(int)` contract (a resize to the same capacity is a no-op). Searched: Cassandra callers of `Wrapped.capacity`, config keys naming this check (none), tests (`BufferPoolAllocator` tests do not cover a limit here). No history relied on.

## B. Verification solution

**B1. Claim under test.** This check does not cap memory or disk usage; it only skips a redundant resize when the requested capacity equals the current capacity.

### B2. Unit tier

n/a: no constraint, there is no limit operand to drive. Evidence in A answers it instead: A1 (both operands are plain runtime sizes, no limit), A3 (true branch returns `this`, false branch resizes with the size chosen by the caller).

#### B2 amendment, 2026-10-29 (stage-4 audit; applies `none-type-design.md` §3-§4; changes no estimate; B2 as filed is `n/a` and is replaced by this design)

**Operand kind: 3** (`newCapacity` is the capacity asked of a direct `Wrapped` ByteBuf). "Usage follows the operand" is expected and is not a finding; the finding is what the branch changes at equal operand. Audit corrections to the filed trace and to the stage-4 draft: (1) the pool serves a request from a chunk only up to `NORMAL_CHUNK_SIZE` = 128 KiB (BufferPool.java:128, 908-923); a larger request, or any request when the pool cannot add a macro chunk (8 MiB, `MACRO_CHUNK_SIZE`, :385; refused when `networking_cache_size` is below it, :443-448), goes to `allocate` -> `ByteBuffer.allocateDirect` and is counted in `overflowMemoryInBytes()` (BufferPool.java:233-264, 290-293). The draft's "64 KiB and above overflows" was wrong; the boundary is 128 KiB, so the sweep below has two pooled and two overflow points. (2) Requests of at most 1 KiB use the tiny pool (unit 32 B, :129-132); other pooled requests round up to 2 KiB units (`roundUp`, :1595-1608), so `capacity()` after allocation can exceed the request; an overflow buffer has exactly the requested size. The arms therefore use `cap0 = buf.capacity()` measured after allocation. (3) `Wrapped.capacity` has no Cassandra caller; `GlobalBufferPoolAllocator.wrap` (GlobalBufferPoolAllocator.java:39) builds a `Wrapped` with `maxCapacity = buffer.capacity()`, so only buffers made by `buffer(initial, max)` can resize. Netty's growth path (`ensureWritable`) asks for a size larger than the current capacity (inference from the Netty contract; not re-read in the jar), so the equal branch is reached by a direct call `buf.capacity(buf.capacity())`. (4) `bufferPool.put(wrapped)` at line 128 for an overflow buffer only subtracts from the gauge; the JDK direct memory of the old buffer is released at garbage collection (the Cleaner), not at that call.

**a. Trigger.** New JUnit class `BufferPoolCapacityTest` in package `org.apache.cassandra.net` (needed: `overflowMemoryInBytes()` is package-private), run with `java` + JUnitCore, with the Byteman agent. It follows `BufferPoolAllocatorTest` (test/unit/org/apache/cassandra/net/BufferPoolAllocatorTest.java): `DatabaseDescriptor.clientInitialization()` and `networking_cache_size` set in `@BeforeClass` **before** the first use of `BufferPools` (the threshold is read once at class load, BufferPools.java:44); buffers from `GlobalBufferPoolAllocator.instance.buffer(initial, max)`; `usedSizeInBytes()` and `overflowMemoryInBytes()` as in its assertions (lines 58-62, 209-213).

**b. Sweep (stated before the run).** Requested initial capacity C in {128 B, 4 KiB, 64 KiB, 1 MiB, 16 MiB}; max capacity = 4C + 8192. Fresh JVM per C (`-Xmx512m`), `networking_cache_size` = 128 MiB, one discarded warm-up cycle, then 5 repetitions of four arms on freshly allocated buffers, each followed by `release()`:
- **E** `buf.capacity(cap0)` (check true, returns `this`).  **G** `buf.capacity(cap0 + 1)` (check false, grows by one byte; the nearest call to "E without the check").  **S** `buf.capacity(cap0 / 2)` (check false, shrinks).  **M** `buf.capacity(max + 1)` (check false; Netty rejects it).
Control JVMs (B2h): C = 4 KiB with `networking_cache_size` = 128 MiB and = 0; and a 16 MiB buffer (known answer).

**c. Measure.** Per call: `usedSizeInBytes()`, `overflowMemoryInBytes()` and `BufferPools.forNetworking().sizeInBytes()` before and after; the JDK `BufferPoolMXBean` "direct" `getMemoryUsed()` before, after, and after `System.gc()` plus a wait until stable (at most 5 s); `buf.capacity()` after; `getThreadAllocatedBytes` around the call (on-heap residue; direct memory is invisible to it). Byteman counters (harness class `NetProbe`, package `org.apache.cassandra.net`): rule at BufferPoolAllocator.java:124 (calls of `super.capacity`, SC) and rule at line 128, just before the old buffer is returned, which records `usedSizeInBytes()` and `overflowMemoryInBytes()` at that moment (the transient peak with old and new buffer both held). After `release()`, `usedSizeInBytes()` and `overflowMemoryInBytes()` must be 0 (the existing test's invariant).

**d. Branch flip.** E against G at the same cap0; S as the shrink side; M as the bound that does bind (in Netty's `checkNewCapacity`, not at line 121).

**e. Prediction (frozen with this amendment).** For every C and repetition (capnew = `buf.capacity()` after the call):
- Allocation: used after allocation = cap0 (exact); overflow after allocation = cap0 for C = 1 MiB and 16 MiB (cap0 = C), and 0 for C = 128 B, 4 KiB, 64 KiB.
- **E:** SC = 0; used, overflow and direct memory unchanged (delta 0); capnew = cap0; residue at most 1 KiB.
- **G:** SC = 1; capnew >= cap0 + 1 and, for the two overflow sizes, capnew = cap0 + 1 exactly, for pooled sizes at most cap0 + 2048; **used after = capnew** (one buffer, not cap0 + capnew); overflow after = capnew for the overflow sizes and 0 for the pooled ones; the line-128 record shows used = cap0 + capnew (both buffers held).
- **S:** SC = 1; used after = capnew, capnew at most cap0/2 + 2048; the line-128 record shows used = cap0 + capnew.
- **M:** an `IllegalArgumentException` from Netty's `AbstractByteBuf.checkNewCapacity` (checked in the netty-buffer 4.1.130 bytecode on 2026-10-29, after the freeze and before any run; the first wording of this line said `IndexOutOfBoundsException`, which is what `writeBytes` throws through `ensureWritable`, not `capacity(int)`), usage unchanged after the call; SC = 1 (the call reaches line 124).
- Direct memory (JDK gauge), overflow sizes only: after G, delta = capnew (the old region still counted until collection); after `System.gc()` and the wait, delta between capnew - cap0 - 4096 and capnew - cap0 + 4096. E: delta 0 at both points.
- After `release()`: used 0 and overflow 0, in every arm.
- Residue: E at most 1 KiB; G and S at most 16 KiB. The residue spread over the repetitions is the noise floor for these figures; the usage gauges are exact integers.
- Control: with `networking_cache_size` = 128 MiB, `sizeInBytes() - overflowMemoryInBytes()` after allocating the 4 KiB buffer = 8,388,608 (one macro chunk) and overflow 0; with 0, pooled bytes 0 and overflow = cap0 (= 4096). The 16 MiB known answer: overflow = 16,777,216.

**f. Positive control (B2h).** `networking_cache_size` is the cap on the pool's chunk memory (the threshold test at BufferPool.java:443-448). Moving it from 128 MiB to 0 must move the pooled-bytes reading from 8,388,608 to 0 and the overflow reading from 0 to cap0, with the same instrument. It shows the gauges register a cap that binds on this memory; it is **not** a cap on this check, and it is not a cap on the overflow path (the closed `networking_cache_size` case reported large-request buffers left in the overflow, see case-notes.md). Said openly: no setting caps the resize at line 121.

**g. Conclusions table (B2g).**

| Reading | Verdict | Effect on the constraint |
|---|---|---|
| E leaves every gauge unchanged with SC = 0; G and S leave steady-state used equal to the one new buffer's capacity (not the sum), with the transient of two buffers visible only at line 128; M is rejected by Netty; control moved; release returns to 0 | **Confirmed** | `does not cap` (the check skips a redundant same-size reallocation; it bounds no retained size) |
| E changes a gauge or SC > 0; or steady state after G or S equals cap0 + capnew (both buffers retained); or a request within the max capacity is clamped or refused at line 121 | **Refuted** | `caps` (or a mechanism misread) |
| The control did not move, or SC = 0 for G (the rule did not fire), or a gauge does not return to 0 after `release()` | **Invalid** / **Not confirmed** | `undetermined` |
| A residue or direct-memory sub-prediction misses while the pool gauges hold | **Confirmed** with the miss recorded | `does not cap` |

Same judgement as in the sibling `none` file filed the same day, stated before the run: the branch gates a transient (a second buffer held until line 128) that is replaced by a buffer of equal steady-state size; no retained size is bounded by line 121.

**h. Hold fixed.** JDK 11, `-Xmx512m`, one thread, Byteman 4.0.20 from the build, a fresh JVM per C (so pool state from other sizes does not leak), `networking_cache_size` as stated per JVM.

### B3. Cluster tier

n/a: no constraint, nothing to push to a boundary. **B3 amendment, 2026-10-29:** stays `n/a`: a network workload only resizes upward through Netty's own growth path and never exercises the equal branch (no Cassandra caller of `Wrapped.capacity`), pool memory is bounded by `networking_cache_size` and overflow accounting in `BufferPool` (other statements, one already closed), and the sweep reaches 16 MiB in the unit tier, below heap noise on a node. Evidence in A answers it instead: A3 shows the true branch is an early return and the resulting memory is bounded by the buffer pool and the ByteBuf `maxCapacity`, neither of which this check sets.

**B4. Risks and cleanup.** None; no run is proposed.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/net/BufferPoolAllocator.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameDecoder.java (lines 385-400)
- grep of src/java/org/apache/cassandra/net/*.java for `.capacity(`, `ensureWritable`, `BufferPoolAllocator`

## D. Stage-4 feedback

**2026-10-29 — unit tier run and self-checked; B3 `n/a`.** Results: [`results/no_constraint-capacity-newcapacity--autonomous.md`](../../stage4-runtime-verification/results/no_constraint-capacity-newcapacity--autonomous.md). Verdict **Confirmed — does not cap** (outcome class: true negative). The frozen text is everything above this section (B2 amendment of 2026-10-29 with its same-day pre-run correction); the estimate is unchanged.

- Readings (C = 128 B to 16 MiB, 5 repetitions, exact integers): E (`capacity(cap0)`) made 0 `super.capacity` calls and moved no gauge; G (`cap0 + 1`) and S (`cap0 / 2`) made 1 call, left steady-state used equal to the one new buffer's capacity, and the line-128 snapshot showed both buffers held (used = cap0 + capNew, e.g. 33,554,433 at 16 MiB); M (`max + 1`) is rejected by Netty (`IllegalArgumentException`) with usage unchanged. After `release()` every gauge returned to 0. Control: `networking_cache_size` 128 MiB vs 0 moved the pooled bytes 8,388,608 to 0 and the overflow 0 to 4096; known answer 16 MiB overflow = 16,777,216.
- Audit corrections: (1) the pool serves from chunks only up to 128 KiB (BufferPool.java:128), not 64 KiB as the stage-4 draft said; (2) the first wording of the M prediction said `IndexOutOfBoundsException`; `capacity(int)` throws `IllegalArgumentException` (`AbstractByteBuf.checkNewCapacity`, netty-buffer 4.1.130 bytecode), corrected before any run; (3) the amendment's statement that an overflow buffer's JDK memory is freed only at garbage collection was **wrong**: `BufferPool.LocalPool.put` calls `FileUtils.clean(buffer)` (BufferPool.java:817), so the old region is released at line 128; the frozen direct-gauge prediction "delta = capNew after the call" missed (delta was 1 byte = capNew - cap0 at both points); (4) `Wrapped.capacity` has no Cassandra caller and `GlobalBufferPoolAllocator.wrap` gives maxCapacity = capacity, as recorded.
- Other missed sub-prediction: G's on-heap residue was 1,888 to 2,520 B in three of five repetitions and 15,920 to 17,008 B in repetitions 3 and 5 (bound 16,384 B; exceeded by 72 B at C = 64 KiB and by up to 624 B at 1 MiB and 16 MiB; within the bound at C = 128 B and 4 KiB). Pool-gauge predictions all held.
- Runbook defect D1: the run needed `--add-exports/--add-opens java.base/jdk.internal.ref` (`conf/jvm11-clients.options`) because `put` of an overflow buffer reaches `FileUtils.clean`; the first attempt aborted in four JVMs and the tier was rerun from the start with the options (results section 3).
- Weaker than it looks: no setting caps the resize, so the positive control is the pool's own cap (`networking_cache_size`) moving the gauges, not a cap on line 121; unit tier only (B3 `n/a`).
