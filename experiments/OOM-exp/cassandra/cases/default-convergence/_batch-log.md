# Default-value convergence playbook — batch log

Append one entry per playbook run, per [`../../../default-value-convergence-playbook.md`](../../../default-value-convergence-playbook.md).
Same format as [`../convergence/_batch-log.md`](../convergence/_batch-log.md), plus the default-arithmetic verdict for each group surveyed.

## Shared-budget group status

Independent of the original convergence playbook's table: a group exhausted there (raised values) is a separate question at defaults. Statuses as in the original (**open**, **exhausted**, **parked**, **skipped**, **deferred (causal-chain, not picked)**), plus **cannot converge at defaults** (the default arithmetic shows no budget where each is safe alone and the sum exceeds it; state the arithmetic).

**Rule: disk is skipped (carried over from the original playbook's 2026-11-02 request).** Do not pick a disk-group combination until it is lifted here.

| Shared budget | Constraints tried | Status | Why |
|---|---|---|---|
| On-heap JVM heap | none built (arithmetic only, run 1) | **cannot converge at defaults** | Every capped heap pool is a heap fraction or a small floor. At capacity, with if-check-exp's overhead factors: memtable 1.1 × H/4, key cache 2.0 × 5% H, counter cache 2.1 × 2.5% H, paxos cache ~2 × 1% H, prepared statements 10 MiB, baseline ≈ 57 MiB. Sum = 67 + 0.45H MiB, which exceeds H only below H ≈ 121 MiB. But the memtable alone needs H ≥ 134 MiB to stay ≥ 30% free. No window at any heap; above ~2 GiB the key/counter caps make it worse. The memtable also flushes at the default cleanup threshold (1/3 of its limit), so it rarely reaches H/4. Smallest non-default change: convergence run 1 (raise `memtable_heap_space` + `counter_cache_size`, cleanup 0.99). See run 1 below. |
| Off-heap/direct memory (`MaxDirectMemorySize`, `allocateDirect` pools) | `DOB_MAX_RECYCLE_BYTES` + `MAX_HINT_BUFFERS` (run 1) | **open** | Run 1 **OOMed, strict default**, at a 192 MiB direct limit. Both defaults are absolute (96 MiB hints pool, 1 MiB × shared-pool workers), so a window exists only at small direct budgets (about 173-200 MiB here), far below the automatic limit. Left open for the other default `allocateDirect` consumers seen in run 1: the networking `BufferPool` (`networking_cache_size` = min(128 MiB, heap/16), in-flight only) and compaction read-ahead buffers (256 KiB × compaction threads, not yet in `_constraint-groups.md`). |
| Off-heap JNA/malloc (cgroup budget) | none built (arithmetic only, run 1) | **cannot converge at defaults** | Only one pool exists at defaults: `index_summary_capacity` (5% heap). `memtable_allocation_type: heap_buffers` (shipped yaml line 825) keeps memtables on heap, so `memtable_offheap_space` holds nothing. `row_cache_size: 0MiB` (line 564) and `file_cache_enabled: false` (line 742) are off. A cgroup budget that mixes heap + direct + JNA is a cross-group question, not this group. |
| Disk | none | **skipped** (carried over, 2026-11-02 request) | See the original batch log. |

## 2026-11-04 — run 1

**Node:** `pc41` (`node0.jason92-323989...`, 40 cores, 251 GiB), same build as convergence runs 1-8 (`~/cassandra-run1`, cassandra-5.0.9). Shipped yaml read from the pristine `systems/cassandra/source/conf/cassandra.yaml`; note that `~/cassandra-run1/conf/cassandra.yaml` still carries run 7's edits. Harnesses use `git archive HEAD conf`, so they are unaffected.

**Counts:** 1 combination built and filed as a case (two workload designs); 2 groups judged by arithmetic only (on-heap, off-heap JNA); disk skipped.

**Default arithmetic per group:** see the status table. In summary:
- heap fractions never sum past the heap;
- the JNA group has one live pool at defaults;
- the direct group has two absolute defaults (hints pool 96 MiB; DOB 1 MiB × *T*), so a window exists at a small direct budget.

**Combinations attempted:**

1. `DOB_MAX_RECYCLE_BYTES` + `MAX_HINT_BUFFERS`, both unset, 500,000-byte values (so the doubled scratch buffer stays at or under 1 MiB) and a down replica. Case file: [`DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS.md`](DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS.md).
   - **Design A** (185 MiB, 64 hints threads): controls 66% / 67%; converge OOMed 2 of 2. **But the no-hints attribution control also died.** The extra writers raised the DOB pool to 99.5% by themselves, and compaction read-ahead buffers ended it. Not filed as the result.
   - **Design B** (192 MiB, 8 hints threads, DOB control run at matched concurrency): alone 63% / 69.3%. Converge: `OutOfMemoryError: Direct buffer memory` 7 s into the burst, forced heap OOM, JVM killed. **OOMed, strict default.**

**Considered and not picked:**
- Every on-heap and JNA combination: no window at defaults (table).
- `max_hints_size_per_host` (default 0 = unlimited): not a cap at its default; disk group anyway. A candidate for an "unbounded at default" note.
- `networking_cache_size` (default min(128 MiB, heap/16)): in-flight only, as in the original batch log.

**Stopping reason:** the one viable group at defaults produced a filed OOM, with a clean attribution control after one redesign. The other memory groups were closed by arithmetic.

**Notes for the next run:**
1. At defaults the DOB pool is about 1 MiB × the shared-pool workers that ever serialize a mutation of up to ~0.5 MB. Any concurrent traffic raises that count, so a DOB control must run at the convergence arm's total concurrency (`B_D_matched`), not alone.
2. 8 client threads of 1 KiB hinted writes fill the default 3-slab hints pool within 10 s.
3. `ThreadLocalReadAheadBuffer` (compaction, direct, 256 KiB each) is a third default direct consumer that can end an arm sitting near the limit.
4. `start_node` clears `N1-logs`, deleting the previous arm's heap dump. Copy the dump out first if it is needed.
