# memtable_flush_writers — Pair 01 · Summary

> **Codepath:** [memtable_flush_writers-01-codepath.md](memtable_flush_writers-01-codepath.md) · **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

**Formatting note:** Link every code reference (`` `File.java:NN` `` or `` `Class.method():NN` ``) to the pinned source on GitHub. Use the format: `` [`File.java:NN`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/<path>#LNN) `` (ranges use `#LNN-LMM`). Place the link *outside* the backticks so code renders as clickable text.

## Identity

| Field | Content |
|-------|---------|
| **Entry Point ID** | MEMTABLE_FLUSH_WRITERS |
| **Name** | memtable_flush_writers |
| **Type** | Configuration (cassandra.yaml) |
| **Declaration Location** | [`Config.java:185`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L185) |
| **Default Value** | 0 (auto-sized: 2 for single-directory, 1 for multi-directory) |
| **Value Type / Size** | `int` threads |
| **Description** | Controls maximum concurrent memtable flush operations to disk; defines thread pool size for `flushExecutor` |
| **Restriction Location** | [`DatabaseDescriptor.java:753-765`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L753) (auto-sizing and validation at startup) |
| **Pair** | 01 of 03 |

**Restriction character:** Config-time soft limit enforcement (thread pool sizing); does not prevent queue accumulation at runtime.

## Key Decision Points

_Critical nodes in the enforcement chain for this configuration parameter._

1. **read/declare:** [`Config.java:185`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L185) — Field declared with default 0
2. **auto-calculate:** [`DatabaseDescriptor.java:753-755`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L753) — Auto-sizing logic: `1 if multi-dir else 2`
3. **validate:** [`DatabaseDescriptor.java:758-759`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L758-L759) — Min bound check (≥1), no upper bound
4. **allocate:** [`ColumnFamilyStore.java:206-210`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L206) — Pool created once (static final) with unbounded queue
5. **dispatch:** [`ColumnFamilyStore.java:1033-1043`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1033) — Tasks queued; no queue depth limit or backpressure

## Enforcement

| Field | Content |
|-------|---------|
| **Enforcement Point** | [`DatabaseDescriptor.java:758-759`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L758-L759) (startup validation only) |
| **Action on Breach** | `ConfigurationException` if value < 1; no action for queue overflow at runtime |

## Failure Mode Analysis

| Mode | Status (✓/✗/⚠) | Notes |
|------|-----------------|-------|
| **Proxy Match** | ⚠ | Thread count is weak proxy for throughput: 1 thread on fast SSD (~500 MB/s) vs. slow HDD (~10 MB/s) = 50x variance. Actual drain depends on I/O performance and CPU, not thread count alone. |
| **Enforcement Point** | ⚠ | Config-time check only (startup in `DatabaseDescriptor`); cannot adapt to runtime conditions. Pool size fixed (static final). Unbounded queue at runtime circumvents thread-count soft limit — tasks queue indefinitely with no rejection or backpressure. |
| **Default State** | ✗ | Default auto-calc (1 for multi-directory) is minimum allowed and severely under-provisioned. No upper bound validation. Typical production writes (50K–100K ops/sec) exceed 1-thread drain capacity. For N data directories, should be ≥N, not 1. |

## Related / Dependent Constraints

- **`memtable_cleanup_threshold`** — Auto-calculated: `1.0 / (1 + flushWriters)`. With flushWriters=1, threshold=0.5 (flush at 50% of heap). Lower threshold with fewer workers = more frequent flushes but same drain rate → queue accumulates faster.
- **`memtable_heap_space`** (memtable_heap_space pair 01/02) — Hard memory cap. Low `flushWriters` prevents reaching it via soft cleanup; OOM occurs via unbounded queue instead of heap overflow, making heap_space limit ineffective.
- **`memtable_allocation_type`** — With `offheap_buffers`, native OOM instead of JVM heap OOM; worsens impact of queue buildup.
- **Per-disk pool contention** (Pair 03, pending) — With multiple directories and low `flushWriters`, one slow disk blocks all flushing.

## Bypass Potential (Target 3 seed)

**Primary Attack: Throughput Starvation via Queue Overflow**
- Setup: `memtable_flush_writers=1` (default for multi-dir), sustained write rate 100K ops/sec (generates ~100 MB/s)
- Sequence: Memtable fills → soft cleanup fires at 50% threshold → single flush thread (I/O bound at ~50 MB/s) falls behind → new memtables queue up → old memtables held in unbounded queue → OOM despite `memtable_heap_space` limit
- Overshoot: 10–20 memtable generations (20–40 GB) accumulate before OOM, well exceeding stated heap_space limit

**Secondary Attacks:**
- **Auto-sizing bypass:** Explicit low value (1) in multi-directory setup → single thread contends across all disks
- **Threshold interaction compound:** Low flushWriters auto-sets cleanup_threshold to 0.5, triggering more frequent flushes, single thread cannot keep pace → faster queue growth
- **Per-disk bottleneck:** One slow disk's queue blocks flushing for other directories (Pair 03 detail)

## Verification

| Field | Content |
|--------|---------|
| **Status** | verified |
| **Verified By / Date** | Code review against cassandra-5.0.9 tag; traced 5 key decision points and 4 attack scenarios |
| **Notes** | Pair 02 documents the queue depth bypass mechanism in detail. Pair 03 (pending) addresses per-disk pool contention. Key interaction: this constraint's default + unbounded queue (Pair 02) + slow drain = silent OOM despite memtable_heap_space hard cap. |

---

## Notes

- **Soft vs. Hard:** This pair (01) is the *soft* thread-pool limit; Pair 02 is the *hard* queue bypass. Together they show how a soft limit with unbounded queue creates a compound weakness.
- **Cascade insight:** Low default (1) + config-time-only check + unbounded queue + multi-directory contention = memory exhaustion is silent and unavoidable under typical production load. No single fix sufficient; needs both thread count increase *and* queue depth limit.

---

## Correction Log

- 2026-09-10: Verified against local `cassandra-cassandra-5.0.9` clone. Two fixes: (1) `Config.java` declaration line 184 → **185** (line 184 is blank); (2) the "validate" step and Enforcement Point cited `DatabaseDescriptor.java:755-757`, which is actually the closing brace of the auto-sizing block — the real min-bound check and throw are at **758-759**.
