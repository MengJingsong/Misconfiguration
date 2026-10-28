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

### B3. Cluster tier

n/a: no constraint, nothing to push to a boundary. Evidence in A answers it instead: A3 shows the true branch is an early return and the resulting memory is bounded by the buffer pool and the ByteBuf `maxCapacity`, neither of which this check sets.

**B4. Risks and cleanup.** None; no run is proposed.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/net/BufferPoolAllocator.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameDecoder.java (lines 385-400)
- grep of src/java/org/apache/cassandra/net/*.java for `.capacity(`, `ensureWritable`, `BufferPoolAllocator`

## D. Stage-4 feedback

`none yet`
