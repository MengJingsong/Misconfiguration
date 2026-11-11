# OOM-exp — Cassandra case index

Master status table for every OOM-exp Cassandra case. Cases are filed in
**status-first** folders, not by direction:

- **`convergence/`** — verified OOM reached by **convergence** (several bounded
  usages exhausting a shared budget together).
- **`bypass/`** — verified OOM reached by **bypass** (getting past a single
  capacity check). *(none yet; B6 run 1 is a conditional candidate)*
- **`candidates/`** — in-progress, parked, or unresolved (mechanism confirmed but
  no attributable OOM manufactured, or blocked before a valid arm ran).
- **`negatives/`** — verified **no-OOM** (safe). *(none yet)*

The capacity **regime** (**custom** raised values | **default** shipped values)
is a *label* here, not a folder. So is the **lead source** (if-check inventory
unless stated; otherwise `JIRA-KEY` — a reproduced fixed bug is a *positive
control* — or `flow:<name>`), stated in the case file and in the Result phrase
when not if-check. **Unprotected** results (no applicable control) are filed in
the same status folders with that label. Lead-source outputs (JIRA survey,
data-flow holder tables) live in `cassandra/leads/`, not here.
Chronological run narrative, infra notes and
shared-budget survey status live in [`_run-log.md`](_run-log.md); the constraint
survey is in [`_constraint-groups.md`](_constraint-groups.md); the planned next
campaign is in [`campaign-plan.md`](../campaign-plan.md).

**Table-width rule.** Keep the table narrow enough that it never needs a
horizontal scrollbar: **Case**/link text is the short case name only (no full
URL), and **Result** is a one-line verdict phrase — detail, numbers and the
conclusion live in the linked case file.

| Case | Mechanism | Regime | Status | Result (one line) | Link |
|---|---|---|---|---|---|
| internode receive queue × tiny cells, replica disk stall (B6 run 2) | bypass | default | candidate | **Service loss, 2 OOMs** — default timeouts, no Byteman, 8/6 GiB replica: 99% live + ~97% time in Full GC in 5/5 stall arms, heap OOM in 2/8 stall/hang arms; blob 0 Full GCs; 8 MiB reserve removes it | [`internode_application_queue...--run2-diskstall`](candidates/internode_application_send_queue_capacity-accounting-mismatch/internode_application_queue_capacity--accounting-mismatch--run2-diskstall.md) |
| internode queues × tiny-cell mutations (B6 run 1) | bypass | default | candidate | **OOM reproduced (conditional)** — counters charge on-wire bytes; heap ≈ 17–20×; 2 GiB coordinator and replica OOM 3/3, blob 0/3; needs slow replica + 60 s deadlines | [`internode_application_queue...--run1`](candidates/internode_application_send_queue_capacity-accounting-mismatch/internode_application_queue_capacity--accounting-mismatch--run1.md) |
| internode receive-queue ×peers (fast co-replica, C1 run 3) | convergence | custom | candidate | **Incomplete — ceiling reached** — fast co-replica decouples the client; at N=8, Q=4 the victim queue hit A_max (543 = 8×4 excl + 511 rsv), throttling on, senders alive; Q/N sweeps and OOM stage not yet run | [`internode...--run3-fastcoreplica`](candidates/internode_application_receive_queue_capacity-multiplicity/internode_application_receive_queue_capacity--multiplicity--run3-fastcoreplica.md) |
| internode receive-queue ×peers (custom Q, C1 reopen) | convergence | custom | candidate | **Sensitivity limit / unresolved** — mechanism confirmed to the MiB (exclusive = N·Q); victim hits a closed-loop occupancy equilibrium (~266 MiB) below the ceiling, so raising Q only re-buckets reserve→exclusive; a direct-buffer OOM is reachable but fires at the same budget for Q=4 and Q=64 (Q-invariant), so not Q-attributable | [`internode...--run2-customQ`](candidates/internode_application_receive_queue_capacity-multiplicity/internode_application_receive_queue_capacity--multiplicity--run2-customQ.md) |
| internode receive-queue ×peers (default Q, C1 multiplicity) | convergence | default | candidate | **Sensitivity limit / unresolved** — mechanism confirmed exactly (N=4: per-conn exclusive=Q, Σreserve=G saturated, admitted=A_max); but N·Q (≤112 MiB) is dominated by the invariant G=512 reserve + occupancy noise, and senders OOM before high N | [`internode...--run1-defaultQ`](candidates/internode_application_receive_queue_capacity-multiplicity/internode_application_receive_queue_capacity--multiplicity--run1-defaultQ.md) |
| commitlog_total_space + max_hints_size_per_host | convergence | custom | candidate | **Blocked / parked** — control arm ran the disk budget full from flush/compaction overhead before a convergence arm could run; retryable, not exhausted | [`commitlog_total_space+max_hints_size_per_host`](candidates/commitlog_total_space+max_hints_size_per_host.md) |
| DOB_MAX_RECYCLE_BYTES + MAX_HINT_BUFFERS (default) | convergence | default | verified-OOM | **OOMed, strict default** — alone 63% / 69% of a 192 MiB `MaxDirectMemorySize`; together a direct-buffer `OutOfMemoryError`, JVM killed; narrow default window only | [`DOB...--default`](convergence/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--default.md) |
| DOB_MAX_RECYCLE_BYTES + MAX_HINT_BUFFERS (custom) | convergence | custom | verified-OOM | **OOMed, JVM killed** — alone 50% / 70% of a 560 MiB `MaxDirectMemorySize`; together a direct-buffer `OutOfMemoryError`; default-L control did not OOM | [`DOB...--custom`](convergence/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom.md) |
| memtable_offheap_space + file_cache_size | convergence | custom | verified-OOM | **OOMed** — each alone 78% of a 3500 MiB cgroup budget; chunk cache full, then a write burst: kernel OOM-kill 16 s in (3465 MiB anon) | [`memtable_offheap_space+file_cache_size`](convergence/memtable_offheap_space+file_cache_size.md) |
| row_cache_size + index_summary_capacity (run 6) | convergence | custom | verified-OOM | **OOMed (schedule B)** — row cache full, then index-summary burst: kernel cgroup OOM-kill at 1973 MiB of 2000 (alone 78% / 80%); concurrent schedule A peaked 93%, no kill. Run 4 (not reached) and run 5 (void) are superseded prior attempts in the same folder | [`row_cache_size+index_summary_capacity--run6`](convergence/row_cache_size+index_summary_capacity--run6.md) |
| memtable_heap_space + counter_cache_size + key_cache_size | convergence | custom | verified-OOM | **OOMed, JVM killed** — safe alone, combined drove heap to 96.6% and crashed the process | [`memtable_heap_space+counter_cache_size+key_cache_size`](convergence/memtable_heap_space+counter_cache_size+key_cache_size.md) |
| memtable_heap_space + counter_cache_size | convergence | custom | verified-OOM | **OOMed** — safe alone, combined usage exceeded the heap (14 `OutOfMemoryError` throws) | [`memtable_heap_space+counter_cache_size`](convergence/memtable_heap_space+counter_cache_size.md) |

**Superseded / void prior attempts** (kept in `convergence/`, same folder as run 6, not given their own rows):

- [`row_cache_size+index_summary_capacity`](convergence/row_cache_size+index_summary_capacity.md) — run 4, **not reached** (combined peak 90% of a 2000 MiB cgroup budget, under the 106% naive sum); superseded by run 6.
- [`row_cache_size+index_summary_capacity--run5`](convergence/row_cache_size+index_summary_capacity--run5.md) — run 5, **void** (the concurrent burst wrote 0 partitions; the stress client's CREATE TABLE timed out); superseded by run 6.
