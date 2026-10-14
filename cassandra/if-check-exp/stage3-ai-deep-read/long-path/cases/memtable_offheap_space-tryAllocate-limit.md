# memtable_offheap_space — region

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | MEMTABLE_OFFHEAP_SPACE-TRYALLOCATE-LIMIT |
| **Constraint** | `memtable_offheap_space` — configuration entry (`Config.java`) |
| **Enforcement pattern** | (b) — the capacity check returns a boolean verdict to its caller |
| **Capacity check** | [`MemtablePool.SubPool.tryAllocate():156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156) (on the `offHeap` `SubPool`) |
| **Decision point** | [`MemtableAllocator.SubAllocator.allocate():169-197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L169-L197) — same park-or-force-through decision as the heap case |
| **Allocation site** | [`NativeAllocator.allocate():138-190`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L138-L190) → a new `NativeAllocator.Region` via `MemoryUtil.allocate()` |
| **Related cases** | [`memtable_heap_space-tryAllocate-limit`](memtable_heap_space-tryAllocate-limit.md) (on-heap sibling; same check code) |

```java
boolean tryAllocate(long size)
{
    while (true)
    {
        long cur;
        if ((cur = allocated) + size > limit)
            return false;
        if (allocatedUpdater.compareAndSet(this, cur, cur + size))
            return true;
    }
}
```

Same method body as [`memtable_heap_space-tryAllocate-limit`](memtable_heap_space-tryAllocate-limit.md) —
`SubPool.tryAllocate()` is shared code. This case is a **different instance**
of `SubPool`: `MemtablePool.offHeap` rather than `MemtablePool.onHeap`
(see [`MemtablePool.java:48`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L48)),
constructed with a separately-configured `limit` and reached via a different
allocator (`NativeAllocator` instead of `HeapPool.Allocator`).

## 2. Context

Cassandra buffers newly-written data in memory (a "memtable") before it is
flushed to disk as an immutable SSTable file. When a table is configured to
keep those memtable cells off the JVM heap (to reduce garbage-collector
pressure from a large working set), the buffered bytes instead live in
native/off-heap memory, obtained directly from the OS rather than the JVM
allocator. Off-heap memory isn't garbage-collected, so without a cap a
burst of writes could grow this native allocation without bound just as
easily as its on-heap counterpart. This if-check is the same admission gate
as the on-heap case — "is there room for `size` more bytes under the
configured ceiling?" — applied to a separate off-heap accounting pool.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | Storage engine — memtable memory allocation (`utils/memory`, `db/memtable`) |
| **One-line role** | Tracks and bounds the off-heap (native) bytes used by in-memory memtables when Cassandra is configured to allocate memtable cells as off-heap objects rather than on-heap `ByteBuffer`s. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | Yes — a running-total counter (`allocated`) plus a requested increment (`size`) compared against a fixed ceiling (`limit`), on the `offHeap` `SubPool` instance. |
| **Usage-side operand** | `allocated` — `volatile long` on `SubPool`, running total of off-heap bytes currently allocated from `MemtablePool.offHeap`. |
| **Limit-side operand** | `limit` — `final long` on the `offHeap` `SubPool`, set once at construction from `maxOffHeapMemory`. |
| **Limit type** | Configuration (`memtable_offheap_space`), with an auto-sized default. |

**Limit initialization path** (declare → configure/derive → store → read at the check):

1. [`Config.java:188-189`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L188-L189) — declared: `memtable_offheap_space` (`DataStorageSpec.IntMebibytesBound`).
2. [`DatabaseDescriptor.java:583-584`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L583-L584) — configured/derived: if unset, auto-sized to `Runtime.getRuntime().maxMemory() / 4` (same fallback formula as the heap limit); [`DatabaseDescriptor.java:591-594`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L591-L594) logs when the resulting threshold is > 0.
3. [`DatabaseDescriptor.java:4060-4062`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4060-L4062) — exposed via `getMemtableOffheapSpaceInMiB()`.
4. [`AbstractAllocatorMemtable.java:82`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L82) — read and converted to bytes: `offHeapLimit = getMemtableOffheapSpaceInMiB() << 20`.
5. [`AbstractAllocatorMemtable.java:85,108`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L85) — passed through `createMemtableAllocatorPoolInternal(...)`; for `Config.MemtableAllocationType.offheap_objects`, routed to `new NativePool(heapLimit, offHeapLimit, ...)` at [line 108](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L108).
6. [`NativePool.java:23-25`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativePool.java#L23-L25) — `NativePool` constructor forwards `maxOffHeapMemory` to `super(...)` (`MemtablePool`).
7. [`MemtablePool.java:55-60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L55-L60) — stored: `MemtablePool` constructor calls `this.offHeap = getSubPool(maxOffHeapMemory, cleanThreshold)`, which sets `SubPool.limit` on the `offHeap` field ([line 48](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L48)) — this is what `tryAllocate()` reads at the check when called via `offHeap()`.

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`MemtableAllocator.SubAllocator.allocate():169-197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L169-L197) — same park-or-force-through decision as the heap case |
| **Verdict** | boolean return of `SubPool.tryAllocate()` (set at the check, `MemtablePool.java:156`), read by `SubAllocator.allocate()` (the decision point above). |

| Branch | Condition | Effect |
|--------|-----------|--------|
| **Allow** | `allocated + size <= limit` (the `if` is false, so the CAS is attempted) | CAS updates `allocated` on the `offHeap` `SubPool`; on success returns `true` — caller proceeds to slice off-heap memory. |
| **Disallow** | `allocated + size > limit` | Returns `false` immediately, no state change — caller does not allocate through this path (in `NativeAllocator`'s case, this return value is not even checked — see 6b). |

```java
// allow branch (falls through the if, line 158-159)
if (allocatedUpdater.compareAndSet(this, cur, cur + size))
    return true;
```

```java
// disallow branch (line 156-157)
if ((cur = allocated) + size > limit)
    return false;
```

## 6. Code path

### 6a. Allow branch → object creation

1. [`MemtablePool.java:156-160`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156-L160) — allow branch taken on the `offHeap` `SubPool`, `allocated` bumped via CAS, returns `true`.
2. [`MemtableAllocator.java:175-177`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L175-L177) — `SubAllocator.allocate()`: `if (parent.tryAllocate(size)) { acquired(size); return; }` — same shared logic as the heap case, called on the `offHeap` `SubAllocator`.
3. [`NativeAllocator.java:138-141`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L138-L141) — `NativeAllocator.allocate(int size, OpOrder.Group opGroup)` calls `offHeap().allocate(size, opGroup)` (steps 1-2 above) **for accounting only** — the boolean/blocking result of the tracked allocation is not used to gate what follows; `NativeAllocator` always proceeds to physically allocate (see 6b).
4. [`NativeAllocator.java:144-156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L144-L156) — size routing: allocations `> MAX_CLONED_SIZE` (128 KiB) go to `allocateOversize(size)`; smaller ones are sliced from `currentRegion`, swapping in a new `Region` via `trySwapRegion()` if the current one is full or absent.
5. [`NativeAllocator.java:176`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L176) (new region, via `trySwapRegion()`) or [`NativeAllocator.java:190`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L190) (oversize path) — **object creation**: `new Region(MemoryUtil.allocate(size), size)` — `MemoryUtil.allocate(size)` is the actual native/off-heap memory allocation (`Unsafe.allocateMemory` under the hood); `Region` wraps the returned peer address for slab-style sub-allocation.

### 6b. Disallow branch effect

**Accounting/allocation are decoupled here:** unlike the heap path
(where `ByteBuffer.allocate()` only runs after `tryAllocate()` returns
`true`, and `HeapPool.Allocator.allocate()` returns nothing if it doesn't),
`NativeAllocator.allocate()` calls `offHeap().allocate()` purely to update
the tracked/blocking accounting (`SubAllocator.allocate()` will block
the caller on `opGroup` if `tryAllocate()` keeps failing and the op isn't
already blocking — see [`MemtableAllocator.java:170-193`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L170-L193)) but does not
use its return value to conditionally skip the physical `MemoryUtil.allocate()`
call in 6a's step 5. The if-check still gates *whether the caller blocks/waits*,
but not *whether the native memory is eventually allocated* — worth flagging
for Target 3 (bypass analysis) even though this case itself is Target 1+2 only.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | `NativeAllocator.Region` (private inner class) wrapping a raw native memory address (`long peer`) obtained from `MemoryUtil.allocate(size)`. |
| **Resource consumed** | Off-heap (native) bytes — a `Region` sized `MIN_REGION_SIZE` (8 KiB) to `MAX_REGION_SIZE` (1 MiB), doubling each swap, or exactly `size` bytes for oversize (>128 KiB) allocations. |
| **Rough sizing** | Slab-allocated: region size scales exponentially (8 KiB → 1 MiB) independent of the individual cell's `size`; oversize allocations (`size > MAX_CLONED_SIZE`) get a dedicated `Region` sized exactly to `size`. |
| **Lifetime / release** | Freed via `MemoryUtil.free(region.peer)` in `NativeAllocator.setDiscarded()` ([`NativeAllocator.java:200-206`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L200-L206)) when the owning allocator is discarded (memtable flushed/discarded); tracked-accounting side released via `SubPool.released(size)` ([`MemtablePool.java:192-197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L192-L197)), same as the heap case. |

## 8. Maximum memory bound

Raising `memtable_offheap_space` raises the total off-heap bytes the
**tracked-accounting** side of the single JVM-wide `MEMORY_POOL`'s `offHeap`
`SubPool` will count before making writers wait; lowering it makes them
wait sooner. But this is doubly non-hard as a true memory ceiling. First,
same as the heap sibling: a write already marked "blocking" bypasses the
check via `markBlocking()` and pushes `allocated` past `limit` with no
ceiling of its own (6b). Second, and unique to this case: per 6b,
`NativeAllocator.allocate()` never conditions the physical
`MemoryUtil.allocate()` call on `tryAllocate()`'s return value at all — not
even via the escape hatch's `isBlocking()` check, it simply never reads the
boolean — so the *physical* off-heap bytes allocated can diverge from the
*accounted* bytes independent of any blocking state. A reader taking
`memtable_offheap_space` as a hard native-memory ceiling would be wrong on
two independent grounds; both flagged for Target 3, not resolved here.

**Stage 4 (2026-10-13, observed; §6b and the rest of §8 not rewritten):** the second ground does not hold
at the allocator: `SubAllocator.allocate()` parks before `NativeAllocator.allocate()` reaches its region
slice, and every discarded memtable held 0–1.6 MiB more region bytes than it had accounted. What does
escape the knob is the process: freed regions stay with the C allocator (`RssAnon` does not fall at a
discard), and with 192 KiB cells the process grew beyond the regions by more than the load explains at
512 MiB and the default (results file, §4.3). The regions are JNA `malloc`, invisible to NMT and outside
`-XX:MaxDirectMemorySize`.


## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers
and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).
The test changes `memtable_offheap_space`, writes faster than flushes free
memory, and checks that writers wait at the limit **and** how many native bytes
the node really holds against the pool's counter. **Done so far:** the unit tier's
existing `NativeAllocatorTest.testBookKeeping()` was run and passed on 2026-09-16,
before stage 4 existed (`Tests run: 1, Failures: 0`; prior evidence, not a
stage-4 result). It never showed that a writer *waited*; a harness test does
(9c). The cluster tier has never been run. Converted to this layout 2026-10-06. **Audited 2026-10-13 (stage-4
step 0): Ready after amendments** — the physical reading moved from NMT, which cannot see this memory, to a
Byteman region ledger, and the slack band was re-derived (9a to 9e, each dated); results in
`../../../stage4-runtime-verification/long-path/results/memtable_offheap_space-tryAllocate-limit.md`.

### 9a. Procedure and conclusions

**Testability:** config, **restart-only**. The test must use
`memtable_allocation_type: offheap_objects`; any other type never builds the
`NativePool`, and this check is not reached (§9b).

**Claim under test:** `memtable_offheap_space` caps the **accounted** off-heap
bytes of the node-wide memtable pool. When the pool is full a writer waits until
a flush frees memory; it is not rejected. Writes that a starting flush is waiting
on are forced past the limit (the escape hatch, §6b). Separately, §6b and §8 say
`NativeAllocator.allocate()` never reads the verdict, so the **physical** native
bytes may differ from the accounted bytes; the test measures both.

**How this verifies the hypothesis** (a restatement of the claim, procedure,
prediction and conclusions in this section; it adds none):

- **Hypothesis:** the accounted off-heap pool stops at `memtable_offheap_space`;
  past it a writer waits, except for bytes forced through the escape hatch; and the
  native memory actually allocated tracks the accounted bytes.
- **Test:** vary the limit (128, 256, 512 MiB and the default), write until the
  pool fills and keep writing faster than flushes finish, and read, side by side,
  the pool's accounted peak, the writers waiting, the bytes forced through, and
  the native bytes the allocator really holds (a ledger of every region it
  allocates and frees; amended 2026-10-13, NMT cannot see them, see Prediction).
- **Logic:** (1) at every value the pool must fill and flushes must start near the
  limit, or the run is invalid. (2) Writers wait and the accounted counter stops
  growing while they wait: the check **stops accounted usage at the limit**. (3)
  The accounted peak moves with the limit: usage **follows the constraint**. The
  peak alone is not proof, since the flush trigger is a fraction of the same limit,
  so the waits are what show this check fired. (4) Any accounted excess over the
  limit is no more than the bytes forced through the escape hatch (measured
  separately). (5) The physical bytes are set against the accounted bytes, per memtable when it
  is discarded and node-wide at the run's peak, at every value: this is §8's "doubly
  non-hard" claim, settled by a number.
- **Refuted if:** the accounted counter passes the limit by more than the escape
  hatch explains, or the accounted peak is flat across the values. **§8's second
  ground is refuted** (physical bytes stay near the accounted bytes) or **sharpened**
  (they do not) by the physical-gap rows. **Not confirmed** if no writer ever waits
  (rows of the Conclusions table).

**Procedure:**

1. **Unit tier** — (a) re-run `NativeAllocatorTest` (accounting, the cleaner, and
   the force-through at 110 against a limit of 100). (b) Run the harness test
   `NativePoolTest` (9c): the pool at its limit, a second allocation that does not
   return (it is parked, seen by thread state, not only by a timeout), release
   waking it, and `markBlocking()` forcing a third through.
2. **Cluster tier** — one node, four runs: `memtable_offheap_space` = 128, 256,
   512 MiB, and the default (1024 MiB with a 4 GiB heap), plus a control at the
   default `memtable_cleanup_threshold`.
3. **At each value:** idle control → **A**, write until the first limit-driven
   flush → **B**, keep writing faster than flushes finish → **C**, force a flush
   while writers are waiting, to trigger the escape hatch. Scenarios A to C run
   twice per value in the sense that they use two payload arms (9c): small cells
   (slab regions) and oversize cells (a dedicated region each).
4. **Compare** with the prediction and read the result below.

**Prediction** (derived from the source before any run; `SubAllocator.allocate()`,
`NativeAllocator.allocate()`, `trySwapRegion()`):

- **A:** each limit-driven flush starts at about 99 % of the limit
  (`memtable_cleanup_threshold: 0.99`), so the accounted peak is proportional to the
  knob. No writer has waited yet. **Physical rise over idle ≈ accounted peak**, with
  the slack below.
- **B:** writers wait while each flush runs; the `BlockedOnAllocation` count rises in
  every run, and the accounted counter does not grow while they wait. The physical
  bytes do not grow either: `NativeAllocator.allocate()` calls the accounting first
  and parks inside it, so no `MemoryUtil.allocate()` follows while a writer is parked.
- **C:** the accounted counter goes above the limit by no more than the bytes forced
  through the escape hatch (roughly concurrent writers × one write's size; an
  estimate, not traced line by line), and the excess disappears when the flush ends.
  Physical bytes follow it up by the same amount.
- **Physical against accounted, the headline reading.** **(Amended 2026-10-13, step-0 audit, before any reading:** the
  earlier reading, NMT category `Other`, cannot see this memory: `MemoryUtil.allocate()`
  is JNA's `Native.malloc()` ([`MemoryUtil.java:25`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemoryUtil.java#L25),
  [`:81-84`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemoryUtil.java#L81-L84)), a plain libc `malloc` that
  NMT does not track, so `P` would have read flat at every value and fired the
  "accounting is decorative" row. The earlier ±16 MiB band also left out part of the
  slack: the race stash alone can hold 15.94 MiB.) `P` is read from a **region
  ledger** (9c, `region-ledger.btm`): one line per `Region` built, which is one
  `MemoryUtil.allocate()` ([`NativeAllocator.java:176`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L176),
  [`:190`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L190)), and one per region freed
  ([`:183`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L183),
  [`:203`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L203)); `L(t)` is the bytes
  allocated by memtable allocators and not yet freed. Three readings:
  - **Per memtable, at its discard.** `NativeAllocator.setDiscarded()` frees the
    memtable's regions ([`:200-206`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L200-L206))
    before it releases the accounting (`super.setDiscarded()` →
    [`MemtableAllocator.java:93-97`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L93-L97)),
    so at that method's entry the memtable's accounted bytes `A_m`
    (`offHeap().owns()`) and its region bytes `P_m` (the sum of the regions it then
    frees) are both whole. Predicted **`0 ≤ P_m − A_m ≤ 1 MiB + 0.002 × A_m`**: every
    accounted byte sits in a region (the accounting call, `:141`, comes before the
    slice), and the excess is the unused rest of the last region (under 1 MiB,
    `MAX_REGION_SIZE`) plus the tail each full region leaves when the next slice does
    not fit (under one slice: about 1.1 KiB per 1 MiB region in the small arm; in the
    oversize arm each cell's region is exactly its size). The same bound holds in
    both arms.
  - **Node-wide, against the knob.** **`0.99 × limit − L_idle − 1 MiB ≤ max_t L(t) − L_idle ≤ limit
    + F + 19 MiB + 0.002 × limit`**, `F` = the bytes forced through the escape hatch
    in that run (Byteman trace). The 19 MiB is up to three live memtables' last
    regions (current, flushing, next: 3 × 1 MiB) plus the global race stash, which
    keeps up to 8 regions per size class
    ([`:50-57`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L50-L57),
    [`:209-227`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L209-L227);
    8 × (8 + 16 + … + 1,024 KiB) = 15.94 MiB) and never frees them. The lower bound
    holds because a flush starts above 99 % of the pool, whose bytes all sit in regions
    kept until the discard; `L_idle` (system tables' regions, part of the pool) and up to
    1 MiB of writes accounted but not yet sliced are the only terms taken off. The bound band is far below the 128 MiB step between capacity values.
  - **Process memory, the cross-check.** The process's anonymous resident memory
    (`RssAnon` in `/proc/<pid>/status`; the heap is pre-touched by
    `-XX:+AlwaysPreTouch`, `conf/jvm-server.options:128`, so it adds a constant)
    rises with `L`: **`max_t ΔRssAnon(t) ≤ max_t ΔL(t) + max_t ΔRssAnon_ctl(t) + 64 MiB`**,
    Δ over each run's own idle reading, `ctl` the load-floor control of the same arm. glibc may keep freed
    `malloc` memory rather than return it to the OS; if it does, this fails while
    the ledger holds, and the "process holds more" row applies.
  - Report `P_m / A_m` and `max L / limit` at each value and arm.

**Conclusions:**

| Result | Conclusion |
|---|---|
| Writers wait in every run, the accounted peak follows the knob, the counter never passes the limit except by bytes forced through a flush's escape hatch, and `P` is within the band of `A` (both ledger bounds of the Prediction; amended 2026-10-13) | **Confirmed** — the check enforces as traced, and the pool's counter tracks native memory. §8's second ground is not borne out by the numbers; report that. |
| As above, but `P` exceeds `A` by more than the band (`P_m − A_m` above its bound for some memtables, or `max L` above its bound, with `P / A` stable across values) | **Confirmed for the counter, bounded gap** — the check enforces the accounting, and native memory runs above it by a measured ratio. §8's second ground stands, with the ratio as its size (Target-3 material). |
| As above, but `P` follows the knob only loosely or grows without bound while the accounted counter is capped | **Refuted** — the counter does not track the resource; §8's ceiling claim is wrong, and `memtable_offheap_space` bounds bookkeeping, not memory. |
| The accounted counter passes the limit, by no more than the bytes forced through the escape hatch | **Escape hatch as recorded** — expected. Record its size (Target-3 material). |
| The accounted counter passes the limit by more than the escape hatch explains, or with no escape-hatch call at all | **Refuted** — the check does not cap usage. |
| The accounted peak is flat across the four values (and the startup log shows the limit did change) | **Refuted** — not the binding limit. Re-read, do not re-run. |
| The peak follows the knob and the pool reaches 100 %, but no writer ever waits | **Not confirmed** — the flush trigger, not this check, sets the ceiling; §6b is wrong. Re-read. |
| `P` is flat across the four values while `A` follows the knob | **Refuted** for §8's ceiling claim — the accounting is decorative; native memory does not respond to the knob at all. |
| `P` is within the band of `A`, but `max ΔRssAnon` exceeds `max ΔL + max ΔRssAnon_ctl + 64 MiB` (added 2026-10-13) | **Confirmed for the allocator; the process holds more** — the check bounds the bytes the memtable allocator holds, and the process keeps more native memory than that (allocator retention). Record the excess per value (Target-3 material). |
| The ledger has no line at all, or its malloc lines stop while writes continue (added 2026-10-13) | **Invalid run** — the instrument failed (9e instrument check). |
| No writer waits, and every flush starts well below the limit | **Invalid run** — flushing keeps up with the writes. Fix the setup (9b, 9c) and re-run. |
| `memtable_allocation_type` is not `offheap_objects` in the startup log | **Invalid run** — fix 9b. |

**Why the peak alone is not enough:** the automatic flush trigger is itself set
at a fraction of the same limit, so the accounted peak would follow the knob even
if this check never refused anything. Only the waits prove the check fired. **Why
the accounted counter alone is not enough:** it is a sum of requested sizes, not a
reading of the memory; the ledger shows what the allocator holds, and `RssAnon` what
the process holds (amended 2026-10-13: NMT does not see JNA `malloc`).

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `memtable_offheap_space` in `cassandra.yaml` (MiB), **and `memtable_allocation_type: offheap_objects`**. Restart-only: the `Config` field is not `volatile`, has no setter, and the pool is a `static final` built once at class load ([`AbstractAllocatorMemtable.java:59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L59), [`:78-86`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L78-L86)). Unit tier: construct `new NativePool(heapLimit, offHeapLimit, cleanThreshold, cleaner)` directly (as `NativeAllocatorTest.setUp()` does) or call the `@VisibleForTesting` `createMemtableAllocatorPoolInternal(offheap_objects, …)` ([`:88-92`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L88-L92)). |
| **Confirm it took effect** | `logs/system.log`: the line `Global memtable off-heap threshold is enabled at …` ([`DatabaseDescriptor.java:591-594`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L591-L594)). `logs/debug.log`: `Memtables allocating with off-heap objects` — the only line that proves the `NativePool` was built ([`AbstractAllocatorMemtable.java:107`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L107)). |
| **Capacity values** | `128MiB`, `256MiB`, `512MiB`, and unset. Unset means `maxMemory() / 4` ([`DatabaseDescriptor.java:583-584`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L583-L584)), so the heap size must be pinned for the default to be a fixed number (1024 MiB at `-Xmx4G`). |
| **Scope** | Global: one pool for the whole node, shared by every table. N = 1, but nothing is isolated — any other table's writes use the same budget. |
| **Level** | Both. Unit: `NativeAllocatorTest` (upstream) and `NativePoolTest` (harness, written in step 1; 9c). The cluster tier is required here more than for the heap sibling: the accounted-versus-physical gap is invisible at the unit tier. |

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| `memtable_allocation_type` | `offheap_objects` | The only type that builds a `NativePool` ([`AbstractAllocatorMemtable.java:106-108`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L106-L108)). `offheap_buffers` builds a `SlabPool` and is a different path (§11). Start from `conf/cassandra.yaml`; `conf/cassandra_latest.yaml` switches the memtable to `trie`. |
| `memtable_heap_space` | `2048MiB` (any value well above the off-heap limits) | `NativePool` also takes a heap limit and the cleaner fires on either pool; a large heap limit keeps it from being the one that binds. Record the startup line for it. |
| `memtable_cleanup_threshold` | `0.99` | The flush trigger. The default (`1 / (1 + memtable_flush_writers)`, 0.33 with two writers) flushes at a third of the limit, so writers rarely wait. `0.99` is the highest value accepted ([`DatabaseDescriptor.java:772-773`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L772-L773)). |
| JVM heap | `-Xms4G -Xmx4G` | The default limit derives from the heap size. |
| NMT | `-XX:NativeMemoryTracking=summary`, in every arm | Support only (amended 2026-10-13): it cannot see the memtable regions (JNA `malloc`), but it attributes the JVM's own native growth (direct buffers, threads) when `RssAnon` is read. It must be set at JVM start and changes the footprint slightly, so every arm has it. |
| Keyspace `durable_writes` | `false` | Stops commit-log-pressure flushes (`Reason: COMMITLOG_DIRTY`) from freeing memory mid-run. `cassandra-stress` creates its keyspace with `durable_writes = true`, so pre-create it (9c). |
| Table `memtable_flush_period_in_ms` | `0` (default) | A periodic flush would free memory on its own schedule. |
| `memtable_flush_writers` | ≥ 2 (default with one data directory) | Scenario C's forced flush needs a free flush thread. |
| `concurrent_writes` | `32` (default) | Sets how many writers can be waiting, and the escape-hatch excess. |
| `commitlog_total_space`, `cdc_enabled`, `file_cache_size`, `networking_cache_size` | defaults | Chunk-cache and buffer-pool memory is also native and appears in NMT; hold it fixed and read the idle floor (below). |
| Traffic | one user table, nothing else | The pool is node-wide. |

**Controls:**

- **Idle run** — node up for at least 60 s, no writes: the floors `L_idle` and `RssAnon_idle` (and NMT) to subtract.
- **Load-floor control** (added 2026-10-13) — once per payload arm, at `256MiB`, with `memtable_allocation_type: unslabbed_heap_buffers` and `memtable_heap_space: 256MiB`, everything else as 9b; idle, A and B only. Same load, no off-heap memtable: its `ΔRssAnon` is the native growth the load causes elsewhere (network buffers, flush writers), the floor for the process cross-check. The ledger must stay empty in it.
- **Cleanup-threshold control** — once, at `256MiB`, with `memtable_cleanup_threshold` at its default: shows what the flush trigger alone does to the peak.
- **Oversize arm** — the payload with cells above 128 KiB (9c): same limit, different region sizing (each cell gets a region of exactly its size, §7), so its region slack is smaller; the bounds of 9a are the same (amended 2026-10-13: the keys and clusterings still use slab regions, and the stash is global).

**Reset between runs:** stop the node (`bin/nodetool stopdaemon`), empty the
`data_file_directories`, `commitlog_directory` and `saved_caches_directory`
set in `cassandra.yaml`, move `logs/` aside, edit the knob, start again.

### 9c. Workload

Ordinary writes that are not flushed, faster than flushes can finish. For the
exact boundary prefer the unit tier: a limit of 100 bytes lands on it at the first
attempt, with no race against the flush.

**Harness.** `<harness>` below stands for
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/memtable_offheap_space-tryAllocate-limit`.
Work for step 1, before run 1 (the audit and the freeze come first):

| File | What it is |
|---|---|
| `NativePoolTest.java` | Unit tier. Package `org.apache.cassandra.utils.memory`, to reach `NativePool`/`NativeAllocator`. Two `@Test`s modelled on the heap sibling's `HeapPoolTest`; see 9e. |
| `region-ledger.btm` | Added 2026-10-13. Byteman, observation only: one line per `NativeAllocator$Region` built (`malloc peer=… cap=…`), per region freed by `trySwapRegion()` or `setDiscarded()` (`free peer=… cap=… site=…`), and at each `setDiscarded()` entry (`discard alloc=<id> owns=<A_m>`). Loaded with `escape-hatch.btm` (two `script:` entries). |
| `ledger.py` | Added 2026-10-13. Reads the ledger: `L(t)`, `L_idle`, `max L`, and per discard `P_m`, `A_m`. |
| `cluster-run.py`, `unit-run.sh` | Added 2026-10-13. One run script per tier, as the closed cases have: `EXPECTED:` lines, stops at the first failed instrument check, stops the node on any exit; the cluster script also runs an `RssAnon` sampler (`/proc/<pid>/status`, every 1 s). |
| `escape-hatch.btm` | Byteman, observation only. The heap sibling's rule (`harness/memtable_heap_space-tryAllocate-limit/escape-hatch.btm`) copied: it appends one line, `forced=<size> limit=<limit> ms=<epoch millis>`, per call to `MemtableAllocator$SubAllocator.allocated(long)`. That method runs for both pools, so **keep only the lines whose `limit` equals the off-heap knob in bytes**. |

```bash
# unit tier
ant testsome -Dtest.name=org.apache.cassandra.utils.memory.NativeAllocatorTest
cp <harness>/NativePoolTest.java test/unit/org/apache/cassandra/utils/memory/
ant testsome -Dtest.name=org.apache.cassandra.utils.memory.NativePoolTest

# cluster tier — pre-create the stress keyspace without durable writes
bin/cqlsh -e "CREATE KEYSPACE keyspace1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1} AND durable_writes = false;"
# small-cell arm
tools/bin/cassandra-stress write n=2000000 no-warmup -col 'size=FIXED(1024)' -rate threads=256
# oversize arm: one column of 192 KiB, above MAX_CLONED_SIZE (128 KiB)
tools/bin/cassandra-stress write n=60000 no-warmup -col 'n=FIXED(1)' 'size=FIXED(196608)' -rate threads=64
```

**Starting values.** Estimates, not measurements:

| Setting | Value | Why |
|---|---|---|
| Row size, small arm | 5 columns × `FIXED(1024)` ≈ 5 KiB | Fills memory faster than flushes empty it. Cells are far below `MAX_CLONED_SIZE`, so they are sliced from regions of 8 KiB growing to 1 MiB. |
| Rows, small arm | `n=2000000` ≈ 10 GiB, the same at every capacity value | At least about ten limit-driven flushes at the default limit (about 1 GiB). |
| Row size, oversize arm | one column of 192 KiB | Each cell is allocated as its own `Region` of exactly that size. |
| Rows, oversize arm | `n=60000` ≈ 11 GiB | The same order of volume; one flush cycle holds about 5,400 rows at 1 GiB. |
| Client threads | `threads=256` (small), `threads=64` (oversize) | Keeps all 32 `concurrent_writes` threads busy. |

**If writers do not wait** (the `BlockedOnAllocation` count does not rise in B):
stop, reset (9b), and repeat that capacity value with `threads=512`. Record each
step as a deviation. If no step makes writers wait, the run is invalid (9a).

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — `SubPool.allocated` on the `offHeap` pool | Unit: `pool.offHeap.used()`, `allocator.offHeap().owns()`. Cluster: no gauge exposes it. Two log lines do: `Flushing largest … Used total: <on>/<off>`, where `<off>` is `allocated / limit` ([`AbstractAllocatorMemtable.java:289-295`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L289-L295)); and `Enqueuing flush of <ks>.<table>, Reason: <reason>, Usage: …`, whose `Usage` is that memtable's peak. | Only when a flush fires | **Do not use `AllMemtablesOffHeapDataSize` for a peak.** It reads only the current memtable, so it drops to near zero when a flush starts, while the old memtable (where the escape-hatch excess lands) still counts; the heap sibling's 9d has the citation. Flushes with a `Reason` other than `MEMTABLE_LIMIT` (except scenario C's) contaminate that cycle. |
| **Disallow evidence** — writers waiting | Timer `org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation`: `bin/nodetool sjk mx -mg -b 'org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation' -f Count`. Thread dump (`jcmd <pid> Thread.print`): `MutationStage` threads with frame `MemtableAllocator$SubAllocator.allocate(MemtableAllocator.java:195)` ([link](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L195)). Unit: a thread state of `WAITING`/`TIMED_WAITING` with that frame. | Before and after each scenario; thread dumps during B | One timer serves both pools' `SubPool`s, so a wait on the **on-heap** pool also counts: with `memtable_heap_space` held at 2048 MiB that pool should not bind; if the count rises with the off-heap counter far from its limit, suspect it. The timer never counts an escape-hatch force-through. Client timeouts are a symptom, not evidence. |
| **Bypass volume** — bytes forced through the escape hatch | The Byteman trace (9c): count lines and sum `forced=`, **only lines whose `limit` equals the off-heap knob in bytes**. | Throughout; per window in scenario C | No stock read-out shows the excess reliably: `Used total` goes above `1.00` only if a flush happens to fire in that window. |
| **Real resource** — native memory (amended 2026-10-13) | **The region ledger** (`region-ledger.btm`, read with `ledger.py`): `L(t)` continuously; `P_m` and `A_m` at every discard. **The process:** `RssAnon` from `/proc/<pid>/status`, every 1 s (a file read, no JVM start). NMT summary (`jcmd <pid> VM.native_memory summary`) at idle and at the end of B, to attribute the JVM's own growth. | Ledger: throughout. `RssAnon`: every 1 s from the start to the stop. NMT: idle, end of B | **Not NMT `Other`:** `MemoryUtil.allocate()` is JNA `Native.malloc()`, invisible to NMT. `RssAnon` counts anonymous memory only (not page cache or mapped files); the heap is pre-touched, so it is a constant inside it. `P_m − A_m` is read at the `discard` line, not across it: the frees come before the accounting is released, so between them `L` is low against the pool. A ledger peer can be reused after a free; `ledger.py` matches frees to live peers in order. |

### 9e. Running the scenarios

**Unit tier.** Commands are in 9c. Record pass or fail and the asserted values.

1. Run `NativeAllocatorTest` (upstream). It passes if accounting, the cleaner and
   the force-through at 110 against 100 behave.
2. Run `NativePoolTest`. It builds `new NativePool(1, 100, 0.75f, cleaner)` as
   `NativeAllocatorTest` does, with a cleaner that does nothing, and:
   1. allocates exactly 100 bytes through `allocator.allocate(…)` in 10-byte
      pieces from the test thread, asserting `pool.offHeap.used() == 100`;
   2. starts a second thread that requests 10 more bytes, and asserts within 5 s
      that it is in a `WAITING` state under `SubAllocator.allocate` and has not
      returned (a timed `Future.get()` that times out is the second evidence);
   3. asserts `used()` is still 100 after 2 s: the disallow branch performs no CAS;
   4. releases 10 bytes (`allocator.offHeap().released(10)`) and
      asserts the second thread returns and `used()` is 100 again;
   5. with the pool full again, runs a third request from a thread whose `OpOrder`
      group has been marked blocking (the `markBlocking` helper in
      `NativeAllocatorTest.setUp()`), and asserts it returns at once with
      `used() == 110`;
   6. (added 2026-10-13, for the ledger's instrument check) discards the allocator
      (`setDiscarding()`, then `setDiscarded()`) and asserts `used() == 0`.

   Record pass or fail and, per step, the asserted numbers.

**Before the cluster tier.** The off-heap allocator's own trace must work before
any reading is trusted:

1. **Instrument check.** Run `NativePoolTest` with the rules attached, as the heap
   sibling does, and expect exactly one line with `forced=` equal to the forced
   request and `limit=100`, and in the ledger (added 2026-10-13) one `malloc` of
   `cap=8192` (the first region, `MIN_REGION_SIZE`), one `discard … owns=110` and one
   `free` of the same peer with `cap=8192` when the test discards its allocator:

   ```bash
   ant testsome -Dtest.name=org.apache.cassandra.utils.memory.NativePoolTest \
     -Dtest.jvm.args="-javaagent:$PWD/build/lib/jars/byteman-4.0.20.jar=script:<harness>/escape-hatch.btm,script:<harness>/region-ledger.btm -Dstage4.byteman.out=$HOME/stage4-logs/cluster/instrument-check.txt -Dstage4.ledger.out=$HOME/stage4-logs/cluster/instrument-ledger.txt"
   ```

2. **Start the node the same way for every run** (every capacity value, every
   scenario, the control), because every flush marks the writes it waits for as
   blocking and B's flushes can force writes through too:

   ```bash
   mkdir -p ~/stage4-logs/cluster/<value>
   export MAX_HEAP_SIZE=4G    # G1: gives -Xms4G -Xmx4G; do not set HEAP_NEWSIZE
   export JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -javaagent:$PWD/build/lib/jars/byteman-4.0.20.jar=script:<harness>/escape-hatch.btm,script:<harness>/region-ledger.btm,listener:true -Dstage4.byteman.out=$HOME/stage4-logs/cluster/<value>/escape-hatch.txt -Dstage4.ledger.out=$HOME/stage4-logs/cluster/<value>/ledger.txt"
   bin/cassandra -p cassandra.pid > ~/stage4-logs/cluster/<value>/stdout.txt 2>&1
   ```

   Once the node is up, confirm the rule is in place:
   `java -cp build/lib/jars/byteman-submit-4.0.20.jar org.jboss.byteman.agent.submit.Submit -l`
   must list `trigger method: org.apache.cassandra.utils.memory.MemtableAllocator$SubAllocator.allocated(long) void`,
   and (added 2026-10-13) the ledger's triggers on `NativeAllocator$Region.<init>`, `NativeAllocator.trySwapRegion` and
   `NativeAllocator.setDiscarded` once the first memtable has allocated.
   If it does not, stop: an empty trace would then mean nothing.

**Cluster tier, for each capacity value** (and for each payload arm of 9c):

1. **Control run** — set the knob, reset (9b), start the node as above, and grep
   both confirmation lines (9b). With no writes, take the idle readings (9d) after
   60 s of uptime: `L_idle` from the ledger, `RssAnon`, NMT (amended 2026-10-13).
2. **Scenario A — reach the limit** — pre-create the keyspace and start the stress
   command (9c), noting the time (`date +%s%3N`). Watch `logs/system.log` for the
   first `Reason: MEMTABLE_LIMIT`. Record the `Usage` line, the `Used total` line
   and the `BlockedOnAllocation` count; the ledger and `RssAnon` run throughout
   (amended 2026-10-13: no sample needs timing).
3. **Scenario B — try to exceed the limit** — keep writing past the first
   limit-driven flush. Record the `BlockedOnAllocation` count before and after,
   take two or three thread dumps during flushes, take the NMT summary at B's end,
   and list every `Enqueuing flush` line with its `Reason`.
4. **Scenario C — escape hatch** — wait until the `BlockedOnAllocation` count is
   rising, note the time, then run `bin/nodetool flush keyspace1 standard1`.
   Record any `Used total` above `1.00`.
5. **Stop and read the trace** — `bin/nodetool stopdaemon`, check
   `ps -eo cmd | grep '[C]assandraDaemon'` prints nothing (amended 2026-10-13, per the stage-4 README's safety rule), then sum
   the trace for the off-heap limit, in total and per scenario window, and read the ledger with `ledger.py`:

   ```bash
   T=~/stage4-logs/cluster/<value>/escape-hatch.txt
   awk -F'[= ]' -v lim=<offheap limit in bytes> '$4==lim {n++; s+=$2} END {print n+0 " calls, " s+0 " bytes"}' $T
   ```

   With `-F'[= ]'` the fields are `$2` = size, `$4` = limit, `$6` = ms (the line also
   carries a `thread=` field); check them on the instrument-check output. No trace file means nothing was forced through.

**Cleanup-threshold control (9b)** — once, at `256MiB`, small-cell arm: the control
run, A and B, with `memtable_cleanup_threshold` removed. No C. Reported as a
control; no §9a row depends on it.

**Load-floor control (9b, added 2026-10-13)** — once per payload arm, at `256MiB`, with
`memtable_allocation_type: unslabbed_heap_buffers` and `memtable_heap_space: 256MiB`: the control
run, A and B, no C, the same stress command. Record `RssAnon` and NMT as above; the ledger must have no
`malloc` line. Its peak `ΔRssAnon` is the floor of the process cross-check (9a).

Stop when each scenario's records are taken; a run where no writer ever waits is
invalid (9a) — fix the workload and repeat it.

**Record for stage 4:** the `cassandra.yaml` diff and JVM options in force, the
exact commands, every reading above, and the `Submit -l` output and the trace
file, per capacity value and payload arm.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source; no stage-1/2 row led here. |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). |
| **Escape hatch / Target-3 note** | `markBlocking()`/`isBlocking()` forces the allocation through past `limit` instead of parking; see §6b. |
| **Stage-4 feedback** | **2026-10-13, long path, run 1 on `pc57`: Confirmed at both tiers, escape hatch as recorded, no run 2** ([results](../../../stage4-runtime-verification/long-path/results/memtable_offheap_space-tryAllocate-limit.md); harness `../../../stage4-runtime-verification/long-path/harness/memtable_offheap_space-tryAllocate-limit/`; committed in `61c22b6`). Step-0 audit **Ready after amendments** (§9 hash `cebea151…`): NMT cannot see memtable regions (`MemoryUtil.allocate()` is JNA `Native.malloc()`), so the physical reading became a Byteman region ledger, and the slack band was re-derived. Unit: the over-limit request parks in `SubAllocator.allocate:195` under `NativeAllocator.allocate:141`, counter unchanged, release wakes it, blocking group forces 10 B (110/100). Cluster, 128 · 256 · 512 MiB · default, 5 × 1 KiB and 192 KiB cells: writers wait in every run (32 threads at `:195`); first limit flush at 99–100 % of the knob (1 : 2 : 4 : 8); physical region bytes exceed the memtable's accounted bytes by 0–1.6 MiB in all 436 discards (*P_m*/*A_m* ≤ 1.007 at ≥ 128 MiB memtables), so §8's second ground is not borne out; 24 memtables were seen above the limit, each by ≤ the bytes the escape hatch forced (≤ 19.9 MB, 14.8 % of 128 MiB with 192 KiB cells). **The process holds more:** `RssAnon` does not fall when a memtable's regions are freed, and with 192 KiB cells it rose 46 and 332 MiB beyond the bound at 512 MiB and the default (cause inferred: C-heap retention). For stage 3: §9a's node-wide slack omits race-loser regions in flight (the cleanup control exceeded it by 8.4 MiB on 15 of them). |
| **Notes** | **Found while converting §9 (2026-10-06), for stage 3 to judge, not applied to §6b/§8:** `SubAllocator.allocate()` parks or forces through before `NativeAllocator` calls `MemoryUtil.allocate()`, so the physical allocation happens only after the accounting call returns; the physical bytes are therefore expected within region slack of the accounted bytes, apart from the escape hatch. §9a states that as the prediction, which the test can contradict. |

---

## 11. Notes

- `NativePool`/`NativeAllocator` is only reachable when `memtable_allocation_type` is `offheap_objects`; the sibling `offheap_buffers` type uses `SlabPool` (off-heap `ByteBuffer` slabs) instead — a third, not-yet-written variant if the off-heap-buffers path is wanted later.
