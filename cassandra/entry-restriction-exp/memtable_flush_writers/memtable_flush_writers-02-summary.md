# memtable_flush_writers — Pair 02 · Summary

> **Codepath:** [memtable_flush_writers-02-codepath.md](memtable_flush_writers-02-codepath.md) · **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

**Formatting note:** Link every code reference (`` `File.java:NN` `` or `` `Class.method():NN` ``) to the pinned source on GitHub. Use the format: `` [`File.java:NN`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/<path>#LNN) `` (ranges use `#LNN-LMM`). Place the link *outside* the backticks so code renders as clickable text.

## Identity

| Field | Content |
|-------|---------|
| **Entry Point ID** | MEMTABLE_FLUSH_WRITERS |
| **Name** | memtable_flush_writers (unbounded queue depth) |
| **Type** | Hardcoded constant (executor factory default) |
| **Declaration Location** | [`ExecutorFactory.pooled():281`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutorFactory.java#L281) → [`ThreadPoolExecutorBuilder.newQueue():159-167`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorBuilder.java#L159-L167) (factory method chain) |
| **Default Value** | Queue sized `Integer.MAX_VALUE` (unbounded) when `queueLimit` is unset and thread count is finite |
| **Value Type / Size** | Queue depth (no config parameter, no limit) |
| **Description** | Executor factory creates unbounded queue for flush tasks; queue depth cannot be tuned and has no backpressure mechanism |
| **Restriction Location** | [`ThreadPoolExecutorBuilder.newQueue():159-167`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorBuilder.java#L159-L167) (no enforcement) |
| **Pair** | 02 of 03 |

**Restriction character:** Hardcoded queue factory default (unbounded); no configuration option and no runtime enforcement.

## Key Decision Points

_Critical nodes showing how this constraint fails to limit queue depth._

1. **factory-definition:** [`ExecutorFactory.pooled():281`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutorFactory.java#L281) → [`ThreadPoolExecutorBuilder.newQueue():159-167`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorBuilder.java#L159-L167) — Factory chain sizes the queue at `Integer.MAX_VALUE` when no capacity is given
2. **pool-initialization:** [`ColumnFamilyStore.java:206-210`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L206) — Pool assigned unbounded queue at startup (static final)
3. **task-submission:** [`ColumnFamilyStore.java:1033-1043`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1033) — Flush task submitted; queue always accepts (never rejects)
4. **no-config-parameter:** No `cassandra.yaml` tuning option for queue depth
5. **no-backpressure:** No rejection policy, no monitoring, callers never see queue saturation

## Enforcement

| Field | Content |
|-------|---------|
| **Enforcement Point** | None — unbounded queue at pool creation; no depth check at dispatch |
| **Action on Breach** | No action; tasks queue indefinitely. Saturation is silent (no exception, no rejection). |

## Failure Mode Analysis

| Mode | Status (✓/✗/⚠) | Notes |
|------|-----------------|-------|
| **Proxy Match** | ⚠ | Queue depth is orthogonal to thread count. Thread pool size (Pair 01) is independent of queue depth; both can be weak simultaneously. Unbounded queue defeats thread-count soft limit. |
| **Enforcement Point** | ✗ | No enforcement: queue created with `Integer.MAX_VALUE` capacity; factory method has no config knob. No check at dispatch time. Designed bypass: rejecting tasks breaks Cassandra semantics, so queueing is "correct" but unbounded. |
| **Default State** | ✗ | Hardcoded default (unbounded); cannot be tuned via config. No monitoring/metrics for queue depth. Silently queues all excess tasks; OOM via memory hold (memtables in queue) not detectable until heap exhaustion. |

## Related / Dependent Constraints

- **`memtable_flush_writers`** (Pair 01) — Thread count soft limit. When dispatch rate exceeds thread throughput, queue absorbs overflow; queue depth thus depends on *both* thread count (Pair 01) and write rate.
- **`memtable_heap_space`** (memtable_heap_space pair 01/02) — Hard memory cap per-memtable. Queued memtables bypass this check (held in queue, not subject to heap allocation check). Queue buildup + heap limit = OOM via queue, not heap.
- **`memtable_cleanup_threshold`** — Auto-derived from thread count. Lower threshold (more frequent flushes) with few threads → queue builds faster.
- **Per-disk pool contention** (Pair 03, pending) — Per-disk queues also unbounded; one slow disk's queue holds memtables for all writes to that directory.

## Bypass Potential (Target 3 seed)

**Primary Bypass: Unbounded Queue Under High Write Load**
- Setup: Any write rate that exceeds flush thread throughput + unbounded queue
- Mechanism: Pool accepts all flush task submissions; queue length grows without limit. Queued memtables not subject to `memtable_heap_space` hard cap (cap is per-memtable, not per-queue).
- Overshoot: With 1 flush thread and 100+ MB/s write rate, queue can hold 50–100 memtables (100–200 GB) before OOM.

**Designed Bypass (by semantic choice):**
- Cassandra prioritizes write availability over predictable backpressure. Rejecting flush tasks would force writes to fail, so queue is deliberately unbounded.
- This choice creates implicit bypass: `memtable_heap_space` cannot actually limit total memory because queued memtables are excluded from the check.

**Attack Vectors:**
- **Write-burst attack:** Sustained high write rate → memtable generation exceeds flush rate → queue accumulates
- **Slow disk attack:** Disk I/O latency increases → thread throughput drops → queue grows
- **Contention attack:** Multiple tables flushing concurrently on same pool → queue saturation
- **Threshold-interaction:** Low cleanup_threshold (from low thread count) forces more frequent flushes into same queue

## Verification

| Field | Content |
|--------|---------|
| **Status** | verified |
| **Verified By / Date** | Code review against cassandra-5.0.9 tag; traced factory method and identified absence of queue-depth config/enforcement |
| **Notes** | This is a *designed* weakness: queue is unbounded because Cassandra chooses queueing over rejection. Pair 01 (soft thread limit) makes this weakness severe (low throughput → queue buildup). Pair 03 (pending) shows how per-disk pools compound the issue. Fix requires *both* increasing thread count (Pair 01) and adding queue depth limit (here). |

---

## Notes

- **Orthogonal constraints:** Pair 01 limits thread count; Pair 02 has no limit on queue depth. Both must be tuned together for effective backpressure.
- **Compound weakness:** Pair 01 (default 1 thread) + Pair 02 (unbounded queue) = silent OOM cascade. The queue absorbs all excess tasks, old memtables never flush, heap fills despite `memtable_heap_space` hard cap applying per-memtable.
- **Semantic choice:** Queue is intentionally unbounded because rejecting flush tasks violates Cassandra's durability model (writes must be flushed eventually). But this choice makes OOM silent and hard to diagnose.

---

## Correction Log

- 2026-09-10: `Declaration Location`, `Restriction Location`, and Key Decision Point 1 previously cited `ExecutorPlus.java` (`#L1`, an arbitrary anchor) for the queue factory. Verified against the local `cassandra-cassandra-5.0.9` clone: `ExecutorPlus.java` is a plain interface with no `pooled()` implementation and no queue-construction code. Corrected to the actual chain: `ExecutorFactory.pooled()` at `ExecutorFactory.java:281`, delegating to `ThreadPoolExecutorBuilder.pooled()`/`newQueue()` at `ThreadPoolExecutorBuilder.java:57,159-167` (the latter is where the `Integer.MAX_VALUE` sizing decision is actually made). The technical claim — unbounded queue, no backpressure — is unchanged.
