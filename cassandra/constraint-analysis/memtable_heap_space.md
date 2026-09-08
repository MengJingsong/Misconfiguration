# `memtable_heap_space` — resource-constraint trace (Cassandra)

| | |
|---|---|
| **Config** | `memtable_heap_space` |
| **System / module** | Apache Cassandra — storage-engine memtable subsystem |
| **Source pin** | `apache/cassandra` @ tag `cassandra-5.0.9` — every `file:line` below is against this tag |
| **Aims covered** | Aim 1 (identify constraints) · Aim 2 (how the constraint restricts usage) |
| **Aim 3 (bypass)** | one lead only, flagged under *Open questions*; **not** verified here |
| **Verification** | every def-use edge below was resolved by `grep` over the pinned tree (declaration → binding → single accessor → single consumer → enforcement leaf); the def-use slice is **complete** for this cluster. The *inferred* layers are (a) the direct-vs-proxy classification and (b) the accounting-fidelity discussion, both grounded in the quoted code but not empirically measured here. |

---

## TL;DR (Aim 2)

`memtable_heap_space` restricts on-heap memtable memory by **byte-accounting blocking backpressure on a single node-wide pool**. Each memtable allocation is admitted only if `allocated + size ≤ limit`; otherwise the writing thread **blocks** until a threshold-triggered flush frees memory and wakes it.

Two important qualifications, both code-verified:

- The counter it governs (`allocated`) is an **estimate of the memtable's on-heap footprint** (cloned data **+ metadata**), not measured JVM heap — see *What the counter actually measures*.
- The invariant is **not** a hard cap. It is *"`allocated ≤ limit` in steady state, with bounded transient overshoots,"* because two paths deliberately let it exceed the limit.

It is a **direct** limit on the memtable pool's *estimated* footprint, a **proxy** for total JVM heap, and it is **never off by default** (defaults to `maxHeap / 4`).

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

### In plain terms — how the throttle works

Think of it as a **bounded buffer** (producer/consumer):

- **Producers** = writes; each clones its data into the memtable and asks the pool for `size` bytes.
- **Buffer capacity** = `limit` (this config).
- **Drain** = flush; flushing a memtable to an SSTable on disk is what *reclaims* the bytes.

Blocking an allocation does **not** free memory — it only stops *new* memory from being taken. The throttle works because blocking is paired with flushing:

1. **Below the limit** → every allocation succeeds; writes run at full speed.
2. **Crossing the cleanup threshold** (a fraction of `limit`) → the pool triggers a flush *before* the wall; normally this keeps usage bouncing below `limit` and nobody blocks.
3. **At the limit** → the next allocation would exceed `limit`, so the write thread **parks** on the `hasRoom` queue, holding no new memory.
4. **A flush completes** → `released()` drops the counter and `hasRoom.signalAll()` wakes the writer, which retries and proceeds only if there is now room (else blocks again).

**Net effect:** the rate at which new memtable bytes are admitted is **clamped to the rate flushes free them**, so usage cannot run away past ~`limit`. In effect it **converts memory pressure into write latency** — under sustained overload you get blocked (slow) writes, not unbounded memtable growth. Neither half throttles alone: block-only would deadlock; flush-only can't keep up under overload.

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

**How it restricts:** the config value ends up as one immutable `long onHeap.limit` (bytes) on a **single node-wide `MEMORY_POOL`** built once at class-load. Everything downstream measures against this one number. The allocation type decides which SubPool(s) writes are counted against, but `heapLimit` is passed to the on-heap SubPool in every case.

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

**How it restricts:** `allocated` is a running count of the memtable's (estimated) bytes. When the next write would cross `limit`, the write thread **parks on the `hasRoom` wait queue** (`MemtablePool.java:53`; stall time measured by the `BlockedOnAllocation` timer, `MemtablePool.java:50,63`). The restriction is **backpressure** — writers *wait*, they are not rejected and not merely warned — and it is applied **before** the memory is consumed.

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

### Phase D — the ceiling goes soft (bounded overshoots)

There are **two** independent, deliberately-documented paths that let `allocated` exceed `limit`:

```java
// (1) flush-drain override — utils/memory/MemtablePool.java:164-167 ; db/ColumnFamilyStore.java:1236-1238
// "apply the size adjustment to allocated, bypassing any limits or constraints"
private void adjustAllocated(long size) { ... }   // used by the force path below
// ...
// "mark writes older than the barrier as blocking progress,
//  permitting them to exceed our memory limit"
writeBarrier.markBlocking();     // sets opGroup.isBlocking() = true for pre-barrier writes
writeBarrier.await();

// (2) row-overhead charged AFTER insert — db/memtable/SkipListMemtable.java:122-125
// "allocate the row overhead after the fact; ... means we can overshoot our declared limit."
int overhead = (int) (cloneKey.getToken().getHeapSize() + ROW_OVERHEAD_HEAP_SIZE);
allocator.onHeap().allocate(overhead, opGroup);
```

For path (1), `markBlocking()` sets `isBlocking = true` (`OpOrder.java:319-321, 333-339, 407-413`); back in Phase B those writes take the `allocated(size)` branch that force-adds past the limit (deadlock avoidance — the flush needs those writes to drain before it can reclaim their memory). For path (2), partition/row structural overhead is charged only after the partition is inserted, so it can push past the limit.

**How it restricts (honest version):** the enforced invariant is *"`allocated ≤ limit` in steady state, with bounded transient overshoots,"* not `allocated ≤ limit` always.

### What the counter actually measures

`allocated` is **not** raw data bytes and **not** measured JVM heap — it is the memtable's **estimated on-heap footprint, metadata included**:

- cloned data bytes (via the slab/native cloner), **plus**
- structural overhead charged explicitly: partition/row overhead `Token.getHeapSize() + ROW_OVERHEAD_HEAP_SIZE` (`SkipListMemtable.java:124-125`, `ShardedSkipListMemtable.java:367`) and per-row/column/stats/deletion `unsharedHeapSize*()` estimates pushed via `onAllocatedOnHeap → allocator.onHeap().adjust(...)` (`BTreePartitionUpdater.java:131-132, 154-164, 86, 91, 121, 175-182`).

So the limit governs `Σ estimated_size`. Its fidelity depends on those size models: if `unsharedHeapSize()` or `ROW_OVERHEAD_HEAP_SIZE` under-count real object footprint, **actual heap can exceed `allocated` while the counter still reads "within limit."**

### Net statement (Aim 2)

`memtable_heap_space` restricts on-heap memtable memory by **byte-accounting backpressure on one shared pool** — block-on-overflow (Phase B), released by a threshold-triggered flush loop (Phase C) — over an **estimated** footprint (data + metadata), with **two designed overshoot paths** (Phase D). Direct limit on the memtable pool's estimated footprint; proxy for total JVM heap; never off by default.

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
| resource governed | memtable on-heap footprint — **estimated** (cloned data + metadata via `unsharedHeapSize` / `ROW_OVERHEAD_HEAP_SIZE`), tracked by the `allocated` counter |
| enforcement mechanism | blocking backpressure (stall the writer on `hasRoom`) + threshold-triggered flush drain |
| enforcement point | allocation time, per-write, pre-consumption |
| hard vs soft | hard in steady state; soft (two bounded overshoot paths) |
| direct vs proxy | direct on the *estimated* memtable footprint; **proxy** at node-heap level |
| default-off? | no (always enabled) |

---

## Open questions (Aim 3 / empirical — not verified here)

1. **Estimate fidelity (the real proxy gap).** The limit governs an *estimated* footprint (see *What the counter actually measures*), not measured heap. Crafting data whose true retained size exceeds its `unsharedHeapSize` estimate would let real memory exceed `allocated` while staying "under limit" — the proxy-mismatch failure mode. How large can that divergence be made?
2. **Overshoot magnitude & OOM reachability.** Two documented overshoot paths (flush `markBlocking`; row overhead charged after insert) let `allocated` exceed `limit`; the flush-drain overshoot is bounded by pre-barrier in-flight write volume (concurrency × size). Is the combined overshoot amplifiable enough — relative to total JVM heap and concurrent consumers (caches, compaction, request state) — to threaten OOM? This is a chaos-experiment question, not a static one.
3. **Scope.** `allocated` is bounded per-*subsystem* (memtables only), not node heap. The trace followed the on-heap path; the off-heap/native pools share the same `SubPool` logic, so the same Phase B–D behavior applies to `memtable_offheap_space`.

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
# what the counter measures (data + metadata estimate)
grep -n "ROW_OVERHEAD_HEAP_SIZE\|onHeap().allocate\|overshoot" \
    src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java
grep -n "unsharedHeapSize\|onAllocatedOnHeap\|onHeap().adjust" \
    src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java
```
