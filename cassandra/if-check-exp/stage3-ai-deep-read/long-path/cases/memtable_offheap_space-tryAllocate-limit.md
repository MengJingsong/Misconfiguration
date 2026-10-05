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


## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it.** Method and pitfalls:
[README.md §8](../../../README.md#8-designing-a-test-for-a-case). Where stage 4's
numbers go: [`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).

> **Unit tier already executed, 2026-09-16, before stage 4 existed.**
> The pre-existing `NativeAllocatorTest.testBookKeeping()` was run and passed
> (`Tests run: 1, Failures: 0, Errors: 0`), demonstrating the accounting
> capped at the limit and then forced past it by `markBlocking()`. **Its
> evidence is weaker than the heap sibling's** and the gap was recorded at the
> time: being a reused test, it confirms the numeric end-state but never
> isolates a proof that the normal-case call actually *parked*, as
> `HeapPoolTest`'s timed `Future.get()` does. Closing that gap — a
> purpose-built two-`@Test` harness on the off-heap path — is the first item
> below.

**This case needs a different experiment from its heap sibling**, and the
reason is §6b/§8: `NativeAllocator.allocate()` never reads `tryAllocate()`'s
return value, so the *accounted* bytes and the *physically allocated* native
bytes can diverge. **Stage 4 must measure both and compare them.** A design
that measures only one cannot see the case's most important finding.

| Field | Content |
|-------|---------|
| **Testability** | **Config-testable, restart-only** — same as the heap sibling: `Config.memtable_offheap_space` is not `volatile`, has no setter, and `MEMORY_POOL` is `static final` and built once ([`AbstractAllocatorMemtable.java:59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L59)). Each capacity value costs a restart. Checked 2026-09-28. |
| **Constraint knob** | `memtable_offheap_space` in `cassandra.yaml` (MiB), **and `memtable_allocation_type: offheap_objects`**, without which the `NativePool` is never built and this check is never reached. At the unit tier: `createMemtableAllocatorPoolInternal(offheap_objects, heapLimit, offHeapLimit, ...)` ([`:88-92`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L88-L92)) or `new NativePool(...)` directly. |
| **Capacity values to test** | `memtable_offheap_space` ∈ {`128MiB`, `256MiB`, `512MiB`, **default**}. As with the heap case the default is auto-sized to `maxMemory() / 4` ([`DatabaseDescriptor.java:583-584`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L583-L584)), so **pin `-Xmx`** across the sweep and record the resolved value from the startup log. |
| **Usage-side observable** | `allocated` on the **`offHeap`** `SubPool` — and, separately, the actual native bytes held by `NativeAllocator.Region`s. **These are two different quantities in this case**, which is the point. |
| **Instrument** | Two instruments, deliberately: (1) **accounted** — `pool.offHeap.used()` / `allocator.offHeap().owns()` at the unit tier (the operand itself); `TableMetrics.allMemtablesOffHeapDataSize` ([`TableMetrics.java:94-95`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TableMetrics.java#L94-L95)) as a per-table proxy on a cluster — no `MemtablePool` gauge exists (README §8.3). (2) **physical** — JVM Native Memory Tracking: start the node with `-XX:NativeMemoryTracking=summary` (**it must be set at JVM start**, so it belongs in `jvm.options` before the run), then `jcmd <pid> VM.native_memory summary`, with RSS as a cross-check. Report both curves on the same axes. |
| **Scope of the limit** | **Global — one `MEMORY_POOL` for the node**, shared by every table's memtable. `N = 1`, no multiplier, but no isolation either: a dedicated single-node instance with one user table. |
| **Suggested level** | **Both.** Unit: `ant testsome -Dtest.name=org.apache.cassandra.utils.memory.NativeAllocatorTest` (re-run as the control), then write the `HeapPoolTest`-style harness noted above. Cluster: required here more than for the heap sibling, because the accounted-vs-physical divergence is invisible at the unit tier unless the harness is written to look for it. |

### 9a. Workload — driving the usage operand

- Single node, **`memtable_allocation_type: offheap_objects`**, one table, `-Xmx` pinned, NMT enabled at JVM start.
- **Raise `memtable_cleanup_threshold` toward `1.0`** and disable periodic flush, for the same reason as the heap sibling: at the default the node flushes before the hard limit binds and nothing ever parks.
- Write with a fixed payload. **Vary payload size deliberately across two arms**: one with cells well under `MAX_CLONED_SIZE` (128 KiB), which are slab-allocated into `Region`s sized 8 KiB → 1 MiB, and one with oversize cells above it, which get a dedicated `Region` sized exactly to the request. §7 says these size differently, so the accounted-to-physical ratio should differ between the arms — a useful internal check on the instrument.

**Deterministic single-shot form:** at the unit tier, construct the pool with a
small `offHeapLimit`, allocate exactly to it, then request one more byte —
the `NativeAllocatorTest` pattern (`verifyUsedReclaiming(80, 0)` then
`verifyUsedReclaiming(110, 110)`), extended with the timed-block assertion.

### 9b. Scenario A — just reach capacity

Bring the `offHeap` `SubPool`'s `allocated` to just under `limit`.

Expect accounted usage ≈ `limit`, plateauing, and the plateau moving with the
knob across the four values. **Also record physical NMT at this point** — the
two should be close here, since slab regions are allocated in step with
accounting while nothing is being forced through. A gap already visible in
scenario A would mean the divergence is not confined to the disallow path, and
is worth reporting on its own.

### 9c. Scenario B — try to exceed capacity

Request more once `allocated == limit`. **The disallow branch parks rather
than rejecting** (§6b), and this case has a second, stronger bypass:

| Expected | Evidence to capture |
|---|---|
| The allocating thread **blocks** on `SubPool.hasRoom` | Timed `Future.get()` timeout (unit), or a thread dump parked at [`MemtableAllocator.java:195`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L195) (cluster). The existing test does **not** prove this — capturing it is the main thing the new harness adds. |
| Accounted usage unchanged while parked | `pool.offHeap.used()` still at `limit`; the disallow branch performs no CAS. |
| `markBlocking()` **overshoots** the accounted limit | `NativeAllocatorTest` already shows 110 past a limit of 100. On a cluster this happens during a flush barrier ([`ColumnFamilyStore.java:1238`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1238)). |
| **Physical native bytes exceed accounted bytes** | The finding unique to this case. Compare `jcmd VM.native_memory summary` against `allMemtablesOffHeapDataSize` at the plateau. §6b says `NativeAllocator.allocate()` never consults the verdict, so physical allocation is not gated at all — the size of this gap has never been measured and is the most valuable number stage 4 can produce here. |

### 9d. Expected dose-response

If the traced path is the binding limit, across the four values:

- **Accounted plateau is linear in `memtable_offheap_space`** and approximately equal to it — the same prediction as the heap sibling.
- **Physical native bytes track the accounted curve only loosely.** Expect them to be higher, and to exceed `limit`, because (i) slab `Region`s are allocated in 8 KiB → 1 MiB units so the last region is partly unused, and (ii) §6b says the physical call is ungated. The *shape* should still follow the knob if the check governs anything at all; a physical curve completely flat across the sweep would mean the accounting is decorative.
- **Time-to-first-block falls as the limit falls**, at constant write rate.
- The gap between the two curves is the headline result. Report it as a ratio at each capacity value, not as a single number.

### 9e. Interpretation — what each outcome means

| Observation at scenario B | Reading |
|---|---|
| Accounted usage plateaus at `limit` and tracks the knob; threads park; physical NMT tracks it with a bounded offset | The check enforces the accounting as traced, and the physical divergence is slab granularity. Record the offset. |
| Accounted plateau tracks the knob but physical NMT **does not**, or grows without bound | §6b's decoupling dominates. **Expected, and the most important outcome** — `memtable_offheap_space` then bounds a counter rather than memory. Target-3 material, and §8's claim needs amending with the measured gap. |
| Accounted usage exceeds `limit` during flushes | The `markBlocking()` escape hatch, as predicted. Not a refutation; record the magnitude. |
| Accounted plateau flat across all four values | The traced path is not the binding limit. Re-read, do not re-run. Check first that `memtable_allocation_type` is actually `offheap_objects`. |

### 9f. What would refute this case

The case claims the comparison on the `offHeap` `SubPool` gates memtable
off-heap allocation, so accounted off-heap memtable bytes are bounded by
`memtable_offheap_space`. It is refuted if the **accounted** plateau does not
move when the knob is changed across the sweep, with `offheap_objects`
confirmed active and flushing confirmed not to be binding.

**A physical-versus-accounted divergence does not refute it** — §8 states that
divergence as a finding of the case, on two independent grounds. Stage 4 should
quantify it, not treat it as a contradiction. The one result that *would*
sharpen §8 into something weaker is physical native memory showing **no**
response to the knob at all: that would mean the constraint limits bookkeeping
and nothing else, and §8's wording would need to say so outright rather than
calling it "doubly non-hard".

### 9g. Confounders and controls

- **`memtable_allocation_type`** — must be `offheap_objects`. With `heap_buffers` or `unslabbed_heap_buffers` the `NativePool` is never constructed and the run measures nothing. Assert it from the startup log in every arm.
- **`memtable_cleanup_threshold`** flushes before the hard limit binds. Hold it fixed and high; one control arm at default to show the difference.
- **NMT is not free and must be enabled at JVM start** — enabling it changes the process's own footprint slightly, so enable it in *every* arm including the baseline, or the arms are not comparable.
- **Other native consumers** — the chunk cache, compression buffers, Netty direct buffers and the JVM's own native memory all appear in NMT. Use NMT's per-category breakdown rather than the total, and take an idle-node NMT reading as the floor to subtract.
- **The pool is node-wide**: one user table, no other traffic.
- **`-Xmx`**, because the default limit derives from it. Pin and record.
- **Baseline** at default config; **idle control** with the node up and no writes, for both the accounted and the physical floor.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source; no stage-1/2 row led here. |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). |
| **Escape hatch / Target-3 note** | `markBlocking()`/`isBlocking()` forces the allocation through past `limit` instead of parking; see §6b. |
| **Stage-4 feedback** | none yet |

---

## 11. Notes

- `NativePool`/`NativeAllocator` is only reachable when `memtable_allocation_type` is `offheap_objects`; the sibling `offheap_buffers` type uses `SlabPool` (off-heap `ByteBuffer` slabs) instead — a third, not-yet-written variant if the off-heap-buffers path is wanted later.
