# OOM-exp — Cassandra case index

Master status table for every OOM-exp Cassandra case. Cases are filed in
**status-first** folders, not by direction:

- **`convergence/`** — verified result by **convergence** (several bounded
  usages exhausting a shared budget together): `verified-OOM` or `verified-gap`.
  *(none yet)* A case whose OOM also needs a demonstrated accounting excess
  (U > C in one domain) is tagged **mixed** in the Mechanism column.
- **`bypass/`** — verified result by **bypass** (getting past a single
  capacity check): `verified-OOM` or `verified-gap`.
- **`candidates/`** — not yet meeting the promotion rule: `reproduced-*` (V1–V5
  met, but only with custom constraints or a tightened budget), in progress,
  parked, unresolved, blocked before a valid arm ran, or a pre-protocol OOM
  awaiting its recheck.
- **`negatives/`** — verified **no-OOM** within a stated range. *(none yet)*

**Status vocabulary (amended 2026-11-11).** A case is verified only when it meets
the promotion rule V1–V7 of the protocol's
[*Verification status*](../../verification-protocol.md#verification-status-amended-2026-11-11)
(≥ 3 failing runs of one condition, ≥ 3 matched controls, U measured
independently of K, intervention ×3 or documented infeasible, initiating failure
kept, **constraints at their defaults, and a heap/memory budget argued acceptable
case by case**; see [*Defaults and acceptable budget*](../../verification-protocol.md#defaults-and-acceptable-budget-amended-2026-11-11)).
Statuses: `verified-OOM`, `verified-gap` (confirmed gap ending in service
loss, overshoot or leak, not OOM), `reproduced-OOM` / `reproduced-gap` (V1–V5 met
but V6 or V7 not; always `diagnostic`, filed in `candidates/`), `candidate`,
`negative`; verified and reproduced statuses also carry `deployment` or `diagnostic`. **`(pre-protocol)`** marks cases filed
before the 2026-11-06 protocol: judged under earlier rules (one failing run
each) and to be rechecked against V1–V5 before being cited as verified upstream.
On 2026-11-11 the six pre-protocol convergence OOMs were moved from
`convergence/` to `candidates/` as `candidate (pre-protocol)`: each had one
failing run, one run per control and at most one intervention run (V1, V2, V4
unmet). Their OOM readings stand; only the verification status changed. A
rerun that meets V1–V5 moves a case back to `convergence/`. **2026-11-11 recheck:**
R1–R4 (runs 7, 8, 1, 2) met V1–V5, but all four use raised capacities and a
tightened budget, so under the V6–V7 amendment of the same day they are
`reproduced-OOM · diagnostic` in `candidates/` (R3, R4 tagged mixed). R5–R6
remain candidates.

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

**One row per case** *(2026-11-16)*. A case with several conditions (sub-cases) has one row, for a
representative condition: the strongest `deployment` condition when there is one. The other conditions and
their statuses are listed in the case file's status table, and the Result cell names them.

| Case | Mechanism | Regime | Status | Result (one line) | Link |
|---|---|---|---|---|---|
| internode queues × tiny-cell mutations — replica 8 GiB, storage stall (B6, representative: A) | bypass | default | verified-gap · service-loss · deployment | **Service loss** — default settings: 99% live, ≈ 97% of 2 min in Full GC 3/3 with counters ≤ C; blob 0/3; 8 MiB endpoint reserve removes it 4/4; heap OOM occasional. Other conditions (B, D verified-OOM · diagnostic; C, E candidate) in the case file | [`internode_application_queue...accounting-mismatch`](bypass/internode_application_queue_capacity-accounting-mismatch/internode_application_queue_capacity--accounting-mismatch.md) |
| DOB_MAX_RECYCLE_BYTES + MAX_HINT_BUFFERS at defaults, 512 MiB direct (R6-V) | convergence | default | negative | **No OOM 0/3** at 512 MiB direct / 2 GiB heap, demand pushed to the default ceiling: peak ≈ 260 MiB (hints 96 + ≈ 175 DOB buffers); ceiling ≈ 398 MiB < 512. Fails only ≤ 250 MiB (3/3, diagnostic) | [`DOB...--default-v7`](negatives/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--default-v7/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--default-v7.md) |
| DOB scratch buffers × worker threads (C3) | convergence · multiplicity | default | negative · deployment | **No OOM 0/7** at 512 MiB direct / 2 GiB heap with up to 165 buffer-holding threads: peak 183–195 MiB (≤ 1 MiB kept per thread; ceiling ≈ 330 MiB all stages saturated). Retention alone OOMs only ≤ 176 MiB (160 MiB 3/3, diagnostic; L=0 removes it 3/3) | [`DOB...worker-multiplicity`](negatives/DOB_MAX_RECYCLE_BYTES-worker-multiplicity/DOB_MAX_RECYCLE_BYTES--worker-multiplicity.md) |
| key + counter cache weigher omits per-entry overhead (B7) | bypass | default | verified-gap · overshoot · deployment | **Key cache 2.14×, counter 1.80× their default caps** (100 / 50 MiB) with counters at the cap, 3/3 at 512 MiB, 2 GiB and auto 7965 MiB heap; 1.15× at 512 B keys; 0.35×C fill 0/3; weigher + 104 B/entry removes it 3/3. No OOM at defaults (0/3, 512 MiB / 2 GiB) | [`key_cache...accounting-mismatch`](bypass/key_cache_size+counter_cache_size-accounting-mismatch/key_cache_size+counter_cache_size--accounting-mismatch.md) |
| memtable_offheap_space + file_cache_size (R1) | convergence | custom | reproduced-OOM · diagnostic | **Kernel memcg OOM-kill 3/3** — superseded at defaults by R1-V (verified); off-heap memtable fills on top of a full 1200 MiB chunk cache (3500 MiB cgroup); each alone 76–78% (0/6); `file_cache_size` 300 MiB removes it 3/3 | [`memtable_offheap_space+file_cache_size`](candidates/memtable_offheap_space+file_cache_size/memtable_offheap_space+file_cache_size.md) |
| DOB_MAX_RECYCLE_BYTES + MAX_HINT_BUFFERS (custom, R2) | convergence | custom | reproduced-OOM · diagnostic | **Direct-buffer OOM 3/3** at 560 MiB — 8 hint slabs (256 MiB) + 36 kept 7.63 MiB DOB scratch buffers; alone 50% / 70–71% (0/6); L = 1 MiB removes it 3/3 (thin margin, peaks 93%) | [`DOB...--custom`](candidates/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom.md) |
| memtable_heap_space + counter_cache_size (R3) | convergence (mixed) | custom | reproduced-OOM · diagnostic | **Heap OOM 3/3, JVM killed** — M/C alone 0/6; `counter_cache_size` 50 MiB removes it 3/3; counter cache holds 327–337 MiB vs its 300 MiB cap (weigher omits overhead) → mixed | [`memtable_heap_space+counter_cache_size`](candidates/memtable_heap_space+counter_cache_size/memtable_heap_space+counter_cache_size.md) |
| memtable_heap_space + counter_cache_size + key_cache_size (R4) | convergence (mixed) | custom | reproduced-OOM · diagnostic | **Heap OOM 3/3, JVM killed** — M/C/K alone 0/9; counter cache to auto 25 MiB removes it 3/3 (key cache to auto does not, 3/3 OOM); caches hold 1.74× / 2.0× their counted weight → mixed | [`memtable_heap_space+counter_cache_size+key_cache_size`](candidates/memtable_heap_space+counter_cache_size+key_cache_size/memtable_heap_space+counter_cache_size+key_cache_size.md) |
| native-v5 large requests × networking pool (B1) | bypass · release-defect | default | negative · deployment | **No overshoot, no OOM 0/4** (heap 2 GiB, direct 512 MiB–2 GiB, 10 min, ~30k 1 MB v5 requests). Release defect confirmed 3/3: `LargeMessage.onComplete()` never calls `releaseBuffers()` → pool pinned at its 128 MiB cap, `OverflowSize` drifts unbounded; patch removes it 3/3; v4/self-contained 0/6. Upstream report recommended | [`networking_cache_size-release-defect`](negatives/networking_cache_size-release-defect/networking_cache_size--release-defect.md) |
| concurrent reads × slow clients, shipped defaults (C2, representative: S-A) | convergence · concurrency/surge (unprotected configuration) | default | verified-OOM · deployment | **Netty direct OOM 3/3** at heap 2 GiB / auto direct 3,982 MiB: 1,024 outstanding 3.5 MiB reads to clients draining 128 MiB/s; ≈ 4.4 MiB Netty direct per outstanding read; nothing bounds unsent responses. 128 outstanding 0/3; client cap 512 0/3. Other conditions (S-B, F-B verified-OOM · diagnostic; F-A negative) in the case file | [`coordinator_read_size...concurrent-reads`](convergence/coordinator_read_size_fail_threshold-concurrent-reads/coordinator_read_size_fail_threshold--concurrent-reads.md) |
| internode receive-queue ×peers, default capacities (C1 run 4) | convergence · multiplicity | default | verified-OOM · diagnostic | **Direct OOM 10/10 with 8 loaded peers** (shipped yaml 7/7, hints off 3/3) at 2 GiB heap / 512 MiB direct; 1 peer 0/6, 2 peers 0/6 at matched load; largest failing direct 640 MiB (4/5), none ≥ 672. Dumps: receive-path frames 66–68% (+ pool 93–94%). Diagnostic: budget below `cassandra-env.sh` resolution | [`internode...--multiplicity--run4`](convergence/internode_application_receive_queue_capacity-multiplicity/internode_application_receive_queue_capacity--multiplicity--run4.md) |
| receive-queue ×peers + hint slabs + DOB + net pool + 15 MiB mutations (S1) | combo: convergence (stacked) + unprotected (U1) | default | verified-OOM · deployment | **Direct OOM 3/3 at heap 2 GiB / direct 768 MiB**; stages 1–2 alone negative at 2 GiB direct; gap off, 1 peer, layers off each 0/3 (joint); 832–2048 survive | [`…--direct-combo`](convergence/internode_receive_queue+hint_slabs+DOB+networking_pool--direct-combo/internode_receive_queue+hint_slabs+DOB+networking_pool--direct-combo.md) |
| coordinator's own CL=ONE local-write backlog, combo (S2) | combo: unprotected accumulation (4 GiB stage 2: mixed, candidate) | default | verified-OOM · deployment | **Heap OOM 3/3 at 2 GiB**: ≈ 61.5k local mutations queued on MutationStage behind a faster 8 GiB replica; rate cap 0/3, LOCAL_ONE 0/3; 4 GiB 1/3 → 2/3 with caches + flush; 8 GiB survives; **run 2 (aarch64, proposed, review pending): equal-heap RF=3 ring (all 2 GiB) heap OOM 3/3, CL=ALL 0/3, rate cap 0/3; no faster replica needed** ([run 2](convergence/coordinator-local-write-backlog--combo/coordinator-local-write-backlog--combo--run2-equal-heap.md)) | [`coordinator-local-write-backlog--combo`](convergence/coordinator-local-write-backlog--combo/coordinator-local-write-backlog--combo.md) |
| memtable_offheap_space + file_cache_size at defaults (R1-V, condition A-768 on pc96) | convergence · standing-pool | default | verified-OOM · deployment | **Heap = 50 % of the container (pc96): memcg kill 3/3 at heap 768 / container 1536** and 3/3 at 1024; each pool alone 0/6, `file_cache_size` 64 MiB 0/3; 1536 survives 0/3. apt149 B (heap 60 %) superseded; platform-dependent (apt149 1/5 at 768) / direct 1 GiB / container 3,413 MiB (+1/1 at 3,500; 4,096 survives); both pools at default 512 MiB and each under its cap at the kill; each alone 0/6; `file_cache_size` 128 MiB removes it 3/3. With container = 2 × heap: heaps 1–2 GiB survive, 768 MiB 1/5 (candidate) | [`memtable_offheap...--default`](convergence/memtable_offheap_space+file_cache_size--default/memtable_offheap_space+file_cache_size--default.md) |
| internode receive-queue ×peers (fast co-replica, C1 run 3) | convergence | custom | superseded by run 4 (history) | **Incomplete — ceiling reached** — fast co-replica decouples the client; at N=8, Q=4 the victim queue hit A_max (543 = 8×4 excl + 511 rsv), throttling on, senders alive; Q/N sweeps and OOM stage not yet run | [`internode...--run3-fastcoreplica`](convergence/internode_application_receive_queue_capacity-multiplicity/internode_application_receive_queue_capacity--multiplicity--run3-fastcoreplica.md) |
| internode receive-queue ×peers (custom Q, C1 reopen) | convergence | custom | superseded by run 4 (history) | **Sensitivity limit / unresolved** — mechanism confirmed to the MiB (exclusive = N·Q); victim hits a closed-loop occupancy equilibrium (~266 MiB) below the ceiling, so raising Q only re-buckets reserve→exclusive; a direct-buffer OOM is reachable but fires at the same budget for Q=4 and Q=64 (Q-invariant), so not Q-attributable | [`internode...--run2-customQ`](convergence/internode_application_receive_queue_capacity-multiplicity/internode_application_receive_queue_capacity--multiplicity--run2-customQ.md) |
| internode receive-queue ×peers (default Q, C1 multiplicity) | convergence | default | superseded by run 4 (history) | **Sensitivity limit / unresolved** — mechanism confirmed exactly (N=4: per-conn exclusive=Q, Σreserve=G saturated, admitted=A_max); but N·Q (≤112 MiB) is dominated by the invariant G=512 reserve + occupancy noise, and senders OOM before high N | [`internode...--run1-defaultQ`](convergence/internode_application_receive_queue_capacity-multiplicity/internode_application_receive_queue_capacity--multiplicity--run1-defaultQ.md) |
| commitlog_total_space + max_hints_size_per_host | convergence | custom | candidate | **Blocked / parked** — control arm ran the disk budget full from flush/compaction overhead before a convergence arm could run; retryable, not exhausted | [`commitlog_total_space+max_hints_size_per_host`](candidates/commitlog_total_space+max_hints_size_per_host.md) |
| DOB_MAX_RECYCLE_BYTES + MAX_HINT_BUFFERS (default) | convergence | default | candidate (pre-protocol) | **1 run, recheck V1–V5** · OOMed, strict default** — alone 63% / 69% of a 192 MiB `MaxDirectMemorySize`; together a direct-buffer `OutOfMemoryError`, JVM killed; narrow default window only | [`DOB...--default`](candidates/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--default.md) |
| row_cache_size + index_summary_capacity (run 6) | convergence | custom | candidate (pre-protocol) | **1 run, recheck V1–V5** · OOMed (schedule B)** — row cache full, then index-summary burst: kernel cgroup OOM-kill at 1973 MiB of 2000 (alone 78% / 80%); concurrent schedule A peaked 93%, no kill. Run 4 (not reached) and run 5 (void) are superseded prior attempts in the same folder | [`row_cache_size+index_summary_capacity--run6`](candidates/row_cache_size+index_summary_capacity--run6.md) |

**Superseded / void prior attempts** (kept in `candidates/`, same folder as run 6, not given their own rows):

- [`row_cache_size+index_summary_capacity`](candidates/row_cache_size+index_summary_capacity.md) — run 4, **not reached** (combined peak 90% of a 2000 MiB cgroup budget, under the 106% naive sum); superseded by run 6.
- [`row_cache_size+index_summary_capacity--run5`](candidates/row_cache_size+index_summary_capacity--run5.md) — run 5, **void** (the concurrent burst wrote 0 partitions; the stress client's CREATE TABLE timed out); superseded by run 6.
| in-flight DOB scratch of 15 MiB mutations × `MutationStage` writers (U1, standalone) | unprotected accumulation (JVM direct, `CommitLog.add`) | default | candidate | Direct OOM 2/14 at heap 2 GiB / direct 576 MiB (V1 unmet); 512–640 touch the cap, rescued by `Bits` retry; auto 15,872 and 1,024 survive (U_peak 632–752); `concurrent_writes: 8` 0/7, 512 KiB control 0/5; Netty-counter frames kill 4 arms first (side lead) | [`…--inflight-DOB-fill`](candidates/concurrent_writes+max_mutation_size--inflight-DOB-fill/concurrent_writes+max_mutation_size--inflight-DOB-fill.md) |
| commit-log replay counts serialized bytes (B8, representative: A) | bypass | default | proposed: negative · deployment (S: verified-OOM · diagnostic); review pending | **No replay OOM at defaults 0/10** (512 MiB–2 GiB): replayed tail = one memtable pool, reader-bound replay; queue at its bound holds 15× its count (947 vs 63 MiB). Restore emulation + injected flush stall: heap OOM in replay 3/3 at 1 GiB; blob 0/3, replay count 64 0/3; 2 GiB survives | [`commitlog_max_outstanding_replay_bytes...accounting-mismatch`](bypass/commitlog_max_outstanding_replay_bytes-accounting-mismatch/commitlog_max_outstanding_replay_bytes--accounting-mismatch.md) |
