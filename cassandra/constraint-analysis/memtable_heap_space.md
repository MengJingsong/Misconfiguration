# `memtable_heap_space` — resource-constraint trace (Cassandra)

| | |
|---|---|
| **Config** | `memtable_heap_space` |
| **System / module** | Apache Cassandra — storage-engine memtable subsystem |
| **Source pin** | `apache/cassandra` @ tag `cassandra-5.0.9` — every `file:line` below is against this tag |
| **Aims covered** | Aim 1 (identify constraints) · Aim 2 (how the constraint restricts usage) |
| **Aim 3 (bypass)** | one lead only, flagged under *Open questions*; **not** verified here |
| **Verification** | every def-use edge below was resolved by `grep` over the pinned tree (declaration → binding → single accessor → single consumer → enforcement leaf); the def-use slice is **complete** for this cluster. The only *inferred* layer is the direct-vs-proxy classification, which rests on the quoted enforcement code. |

---

## TL;DR (Aim 2)

`memtable_heap_space` restricts on-heap memtable memory by **byte-accounting blocking backpressure on a single node-wide pool**. Each memtable allocation is admitted only if `allocated + size ≤ limit`; otherwise the writing thread **blocks** until a threshold-triggered flush frees memory and wakes it.

The enforced invariant is **not** a hard cap. It is:

> `allocated ≤ limit` **in steady state**, with a **bounded transient overshoot during flush** —

because the flush path deliberately lets pre-barrier in-flight writes exceed the limit to avoid deadlock. It is a **direct** limit on memtable-pool *counted* bytes, a **proxy** for total JVM heap, and it is **never off by default** (defaults to `maxHeap / 4`).

---

## Aim 1 — the constraint cluster

Tracing this one config to its enforcement point (`AbstractAllocatorMemtable.createMemtableAllocatorPool`, `AbstractAllocatorMemtable.java:77-85`) pulls in the full set of co-governing constraints that meet there:

| constraint | kind (per Aim 1) | role | anchor |
|---|---|---|---|
| `memtable_heap_space` | config, typed | on-heap pool ceiling (bytes) | `Config.java:187` |
| `memtable_offheap_space` | config, typed | off-heap pool ceiling | `Config.java` / `DatabaseDescriptor.java:582` |
| `memtable_cleanup_threshold` | config, float | reclamation (flush) trigger ratio | `AbstractAllocatorMemtable.java:83` |
| `memtable_allocation_type` | config, enum | selects Heap/Slab/Native pool → *what* is counted | `AbstractAllocatorMemtable.java:80,93-108` |
| `maxMemory() / 4` | hardcoded derivation | default when unset | `DatabaseDescriptor.java:587` |
| `DataStorageSpec.IntMebibytesBound` | variable type | imposes an int-MiB range bound on the value | `Config.java:187` |
| `SubPool.limit` / `allocated` / `reclaiming` | runtime fields | the actual enforcement state | `MemtablePool.java:105,111` |

**Methodological takeaway:** constraints do **not** live as isolated knobs — they *cluster* around a resource (the memtable pool). Enumerating at the **enforcement point** yields the whole co-governing set for free, including the non-config members (the type bound, the derived default). Scope note: this is **one cluster** seeded from a hand-picked config — a data point, not module/system coverage.

---

## Aim 2 — how it restricts usage (code path)

The mechanism is a **feedback loop**, not a linear chain: a limit, a block, a reclamation trigger, and a wake-up.

```
SETUP        Config value ──► onHeap.limit (bytes)
WRITE PATH   write ──► allocate() ──► tryAllocate(): allocated+size > limit ?
                                          │ no  ──► take it, allocated += size
                                          │ yes ──► block on hasRoom  ◄──────┐
RECLAIM LOOP allocated crosses cleanup threshold ──► cleaner.trigger()       │
                 ──► flushLargestMemtable ──► released(): allocated -= size   │
                 ──► hasRoom.signalAll() ──► woken writer retries ───────────┘
OVERRIDE     during flush: writeBarrier.markBlocking() ──► opGroup.isBlocking()
                 ──► allocate() force path bypasses the limit (overshoot)
```

### Phase A — the config value becomes the enforcement variable `onHeap.limit`

```java
// config/Config.java:186-187
@Replaces(oldName = "memtable_heap_space_in_mb", converter = ..., deprecated = true)
public DataStorageSpec.IntMebibytesBound memtable_heap_space;

// config/DatabaseDescriptor.java:586-589   (applyConfig)
if (conf.memtable_heap_space == null)
    conf.memtable_heap_space = new DataStorageSpec.IntMebibytesBound(maxMemory()/(4*1048576)); // default = heap/4
if (conf.memtable_heap_space.toMebibytes() == 0)
    throw new ConfigurationException("memtable_heap_space must be positive", false);           // only validation

// config/DatabaseDescriptor.java:4055-4058
public static long getMemtableHeapSpaceInMiB() { return conf.memtable_heap_space.toMebibytes(); }

// db/memtable/AbstractAllocatorMemtable.java:59, 80-85   (built once, at class-load)
public static final MemtablePool MEMORY_POOL = createMemtableAllocatorPool();
...
long heapLimit = DatabaseDescriptor.getMemtableHeapSpaceInMiB() << 20;   // MiB → bytes
return createMemtableAllocatorPoolInternal(allocationType, heapLimit, offHeapLimit,
                                           memtableCleanupThreshold,
                                           AbstractAllocatorMemtable::flushLargestMemtable); // the cleaner

// utils/memory/MemtablePool.java:55-70, 117-121
this.onHeap = getSubPool(maxOnHeapMemory, cleanThreshold);   // maxOnHeapMemory == heapLimit
SubPool getSubPool(long limit, float t) { return new SubPool(limit, t); }
public SubPool(long limit, float cleanThreshold) { this.limit = limit; ... }
```

**How it restricts:** the config value ends up as one immutable `long onHeap.limit` (bytes) on a **single node-wide `MEMORY_POOL`** built once at class-load. Everything downstream measures against this one number. The allocation type (`heap_buffers` / `offheap_buffers` / `offheap_objects` / …) decides which SubPool(s) the writes are counted against, but `heapLimit` is passed to the on-heap SubPool in every case.

### Phase B — restriction at allocation time (blocking, pre-consumption)

```java
// utils/memory/MemtablePool.java:151-160   (SubPool)
boolean tryAllocate(long size) {
    while (true) {
        long cur;
        if ((cur = allocated) + size > limit)   // ← THE LIMIT CHECK
            return false;                        //   refuse: would exceed
        if (allocatedUpdater.compareAndSet(this, cur, cur + size))
            return true;                         //   else CAS the running byte count up
    }
}

// utils/memory/MemtableAllocator.java:168-194   (on the write path, per allocation)
public void allocate(long size, OpOrder.Group opGroup) {
    while (true) {
        if (parent.tryAllocate(size)) { acquired(size); return; }   // :175 under limit → proceed
        if (opGroup.isBlocking())     { allocated(size); return; }  // :~180 override (Phase D)
        WaitQueue.Signal signal = parent.hasRoom().register(parent.blockedTimerContext(), ...);
        opGroup.notifyIfBlocking(signal);
        if (parent.tryAllocate(size)) { signal.cancel(); acquired(size); return; }  // :187 retry
        else signal.awaitThrowUncheckedOnInterrupt();               // ← BLOCK the writer here
    }
}
```

**How it restricts:** `allocated` is a running count of *real bytes* the memtable allocator has handed out. When the next write would cross `limit`, the write thread **parks on the `hasRoom` wait queue** (`MemtablePool.java:53`; its stall time is measured by the `BlockedOnAllocation` timer, `MemtablePool.java:50,63`). The restriction is **backpressure** — writers *wait*, they are not rejected and not merely warned — and it is applied **before** the memory is consumed.

### Phase C — the reclamation loop that makes the limit hold

A pure block would deadlock forever; the limit is enforceable only because crossing a *lower* threshold triggers a flush that frees bytes and wakes the parked writers.

```java
// utils/memory/MemtablePool.java:124-147   (SubPool)
boolean needsCleaning() { return used() > nextClean && updateNextClean(); }
void maybeClean()       { if (needsCleaning() && cleaner != null) cleaner.trigger(); }
private boolean updateNextClean() {
    long next = reclaiming + (long)(this.limit * cleanThreshold);   // ← memtable_cleanup_threshold × limit
    ...
    return used() > next;
}

// cleaner == AbstractAllocatorMemtable::flushLargestMemtable → flush frees a memtable's bytes → then:

// utils/memory/MemtablePool.java:191-196   (SubPool)
void released(long size) {
    adjustAllocated(-size);   // drop the running count
    hasRoom.signalAll();      // ← wake every writer parked in Phase B
}
```

**How it restricts:** the cleanup threshold (a *fraction* of `limit`) makes the pool start reclaiming **before** the hard wall, and `released → hasRoom.signalAll()` is what lets a blocked writer retry `tryAllocate` and slip through once room exists. This loop is what turns a static number into a sustained ceiling: **new writes proceed only at the rate flushes free memory.**

### Phase D — the ceiling goes soft during flush (bounded overshoot)

```java
// utils/memory/MemtablePool.java:164-167   (SubPool)
// "apply the size adjustment to allocated, bypassing any limits or constraints"
private void adjustAllocated(long size) { ... }   // used by the force path below

// db/ColumnFamilyStore.java:1236-1238   (the flush task)
// "mark writes older than the barrier as blocking progress,
//  permitting them to exceed our memory limit"
writeBarrier.markBlocking();     // sets opGroup.isBlocking() = true for pre-barrier writes
writeBarrier.await();
```

`markBlocking()` walks the op-groups and sets `isBlocking = true` (`OpOrder.java:319-321, 333-339, 407-413`). Back in Phase B, those writes now hit `if (opGroup.isBlocking()) { allocated(size); return; }`, which force-adds via `adjustAllocated` — **past the limit**.

**How it restricts (the honest version):** the enforced invariant is **not** `allocated ≤ limit`. It is *"`allocated ≤ limit` in steady state, with a bounded transient overshoot during flush,"* where the overshoot equals the volume of pre-barrier in-flight writes stuck at allocation when the flush trips the barrier. The bypass is deliberate — deadlock avoidance: the flush needs those writes to drain before it can reclaim their memory.

### Net statement (Aim 2)

`memtable_heap_space` restricts on-heap memtable memory by **byte-accounting backpressure on one shared pool** — block-on-overflow (Phase B), released by a threshold-triggered flush loop (Phase C) — with a **designed soft-ceiling override during flush** (Phase D). Direct limit on memtable-pool counted bytes; proxy for total JVM heap; never off by default.

---

## Structured record

| field | value |
|---|---|
| system / module | Cassandra 5.0.9 / storage-engine memtable |
| config | `memtable_heap_space` |
| kind | config param, typed (`DataStorageSpec.IntMebibytesBound`) |
| declaration | `Config.java:187` |
| default / validation | `maxMemory()/4`; must be > 0 — `DatabaseDescriptor.java:586-589` |
| accessor | `getMemtableHeapSpaceInMiB()` — `DatabaseDescriptor.java:4055` |
| consumption sites | **1** — `AbstractAllocatorMemtable.java:81` |
| resource governed | memtable on-heap allocated bytes (counted by the allocator) |
| enforcement mechanism | blocking backpressure (stall the writer on `hasRoom`) |
| enforcement point | allocation time, per-write, pre-consumption |
| hard vs soft | hard in steady state; soft (bounded overshoot) during flush |
| direct vs proxy | direct at subsystem; **proxy** at node-heap level |
| default-off? | no (always enabled) |

---

## Open questions (Aim 3 / empirical — not verified here)

1. **Overshoot magnitude.** The real bound is `limit + (pre-barrier in-flight write volume stuck at allocation when a flush marks the barrier blocking)`, bounded by write concurrency × write size — **not** by the knob. How large can it get in practice?
2. **Reachability to node OOM.** Is the overshoot amplifiable enough (relative to total JVM heap and concurrent consumers) to threaten OOM? This is a chaos-experiment question, not a static one.
3. **Scope caveat.** The trace followed the on-heap path. The off-heap/native pools share the same `SubPool` limit logic; the same Phase B–D behavior applies to `memtable_offheap_space`. Also, `allocated` counts only what the allocator *sizes* — per-object/JVM overhead outside the counted slab/native region is not bounded by this knob.

---

## Reproduction

```bash
git clone --depth 1 --single-branch --branch cassandra-5.0.9 \
    https://github.com/apache/cassandra.git

cd cassandra
# declaration + all references
grep -rn "memtable_heap_space" conf/cassandra.yaml src/java/org/apache/cassandra/config/
# accessor + its call sites (deterministic def-use)
grep -rn "getMemtableHeapSpaceInMiB" src/java/
# enforcement leaf + override
grep -n "tryAllocate\|adjustAllocated\|hasRoom\|isBlocking" \
    src/java/org/apache/cassandra/utils/memory/MemtablePool.java \
    src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java
grep -rn "markBlocking" src/java/org/apache/cassandra/db/ColumnFamilyStore.java
```
