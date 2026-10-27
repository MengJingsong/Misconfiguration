# max_region_size — trace-back only  <!-- file: traceback-only/max_region_size-tryswapregion-minsize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/utils/memory/NativeAllocator.java:166` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** The check at NativeAllocator.java:166 (`minSize > size`) compares the requested allocation size (`minSize`, passed from `allocate(int size, ...)` at NativeAllocator.java:154) against the candidate off-heap region size, which starts at `MIN_REGION_SIZE` (8 KiB, declared at NativeAllocator.java:48, used at :164) or doubles the current region capacity (:165), and is then bounded by the constant `MAX_REGION_SIZE` (1 MiB = `1 * 1024 * 1024`, declared at NativeAllocator.java:46, applied via `Math.min` at :168). The effective constraint is therefore a hard-coded constant (kind: constant, `private final static int`) that caps the size of each native memtable allocation region; the related `MAX_CLONED_SIZE` (128 KiB, NativeAllocator.java:47) sends larger allocations to `allocateOversize` (:144-145) instead. Unit: bytes. The default is the literal value in the source (no derivation from other settings). It is not settable through cassandra.yaml, a -D property or JMX; changing it requires editing the source and rebuilding, so it is not a runtime-tunable limit. It only bounds region granularity (the total off-heap memtable budget is governed separately by the memtable off-heap space settings and the `offHeap().allocate(size, opGroup)` accounting at :141).
