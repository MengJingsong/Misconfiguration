# Default-value convergence playbook — batch log

Append one entry per playbook run, per [`../../../default-convergence-playbook.md`](../../../default-convergence-playbook.md).
Same format as [`../custom-convergence/_batch-log.md`](../custom-convergence/_batch-log.md), plus the default-arithmetic verdict for each group surveyed.

## Current campaign status — 2026-11-06

This dated table governs new candidate selection. Historical domain-wide statuses
below describe only the earlier standing-pool combinations/arithmetic; they do
not exclude replicated local limits or transient overlap. No new runtime results
are asserted. See [campaign plan](../../campaign-plan.md).

| Mechanism / allocation domain / regime | Status | Next action |
|---|---|---|
| C1 / internode private allowances / default capacities, budget separately labeled | **sensitivity-limited / unresolved** (run 2, 2026-11-09) | Mechanism confirmed exactly (N=4: per-conn exclusive=Q, Σreserve=G saturated, admitted=A_max); but N·Q (≤112 MiB) is dominated by the invariant G=512 reserve + occupancy noise, and senders OOM before high N. Reopen only with senders that survive RF-fanout to a slow victim (large heaps / dedicated load hosts) to test N=4 vs N=32 |
| C2 / per-query live memory / default capacities, budget separately labeled | open | Verify threshold applicability and actual concurrent working sets; unlimited defaults are a separate unprotected arm |
| C3 / per-worker DOB allocations / default capacities, budget separately labeled | open | Audit worker multiplicity and active versus retained buffers |
| Existing standing-pool combinations / original regimes | historical scope only | Preserve results; new runs need a distinct mechanism or boundary question |
| Disk exhaustion / all regimes | skipped by request | No new disk runs or retries until explicitly reopened |
| Disk-to-memory causal chain / all regimes | deferred | Outside this batch; not implicitly reopened |

## Historical shared-budget group status

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

## 2026-11-09 — run 2 (C1, internode receive queues)

**Nodes:** CloudLab APT, one experiment, LAN 10.10.1.0/24, user jason92. Victim `apt140` (10.10.1.1,
16 threads, 15 GiB, cgroup v2, swap 8G). Peer hosts `apt179/138/190/149` (10.10.1.2–.5), each 16 threads/
15 GiB. cassandra-5.0.9 built locally (`~/cassandra-b1` victim, `~/cassandra-c1` peers). Run data on
`/mydata` only. Internode port 7000 restricted to 10.10.1.0/24 during the run (removed after).

**Mechanism / allocation domain / regime:** C1, internode inbound receive queues (exclusive Q=4 MiB,
endpoint E=128 MiB, global G=512 MiB — **defaults**), tightened diagnostic direct-memory budget. First
convergence case in this project driven by **multiplicity of active peers** rather than two stacked pools,
and the first multi-instance ring (up to 33 Cassandra instances via LAN IP aliases).

**Attempted:** one case — [`internode_application_receive_queue_capacity--multiplicity.md`](internode_application_receive_queue_capacity--multiplicity.md).
Arms: G1 reachability; D_cal_n4 (reference, Byteman 100 ms apply-delay, Q=4, 2048 MiB budget); D_cal_n8;
RQ_n4_q1 (reduced-Q causal control, Q=1 MiB); D_oom_n4_b450 (450 MiB budget). **Result: mechanism confirmed
exactly, multiplicity-OOM sensitivity-limited / UNRESOLVED.** At N=4 the admitted bytes = 527.8 MiB =
A_max(4)=N·Q+G=528, per-connection = 4.0 MiB exclusive (=Q) + 127.9 MiB (=E), Σreserve = 511.8 MiB (G
saturated); reduced-Q drops per-conn exclusive to exactly 1.00 MiB. But the escaping term N·Q (16→128 MiB
over N=4→32) is dominated by the invariant reserve G=512 MiB and by ±~350 MiB occupancy noise, and the peer
coordinators OOM (heap, retaining 128 KiB mutations for the slow victim) before a high-N arm can be
sustained — so N=16/32 could not be reached and the RF=33 ring was reduced to RF=9.

**Key empirical blockers (all anticipated by the design's decision rules):**
1. **No natural backpressure** — at reachable load the victim's MutationStage drains and queues stay ~0;
   the designed **Byteman apply-delay** (frozen, saved) was required to fill them, so queue-fill results are
   conditional on injected delay; reproduction without it is negative.
2. **Sender bottleneck** — 512 MiB (and even 2 GiB) peer coordinators OOM under RF fanout to a slow victim.
3. **Reserve dominates** — receive-queue memory is ~all the shared G=512 MiB reserve, invariant across N; a
   direct-buffer OOM is reachable only at a budget (450 MiB) so tight that baseline + reserve exceed it
   before load — reserve/baseline-driven, not multiplicity.

**Infrastructure notes for the next run (multi-instance Cassandra rings):**
1. `num_tokens: 1` without `initial_token` causes **random-token collisions** across many simultaneous
   fresh nodes — nodes get dropped from the ring. Assign explicit evenly-spaced `initial_token` per instance.
2. A `systemd-run --user` transient **service** (not `--scope`) survives the launching ssh session, but
   needs `loginctl enable-linger` or the user manager tears it down when the session closes.
3. Do **not** wipe a node's `data/` to "freshen" it between restarts — it erases `system.local` and the
   rejoin hits an endpoint collision; keep the data to rejoin, or use `replace_address_first_boot` +
   `allow_unsafe_replace=true`.
4. Peers need distinct JMX ports: `cassandra-env.sh` hardcodes `JMX_PORT="7199"`; sed it per instance. JMX
   binds to 127.0.0.1 — use `nodetool -h 127.0.0.1 -p <port>`.
5. `cassandra-stress -node whitelist <csv>` restricts coordinators to exactly those peers (WhiteListPolicy).
6. Byteman on a Cassandra class (`MutationVerbHandler.doVerb`) needs no `boot:`; confirm the rule actually
   fires (`bmsubmit -l`) — a loaded rule that isn't delaying usually means the arm hit a *dead* coordinator,
   not a Byteman failure.
7. Raising `write_request_timeout` (here 30 s) lifts the message-expiry ceiling so the receive queue can
   hold more than `arrival × 2 s` before expiry releases permits.

**Stopping reason:** the mechanism was confirmed to the model and the sensitivity limit was reached and
quantified (noise ≫ multiplicity signal; senders fail before high N). No OOM was manufactured. Reopen only
with senders that survive RF-fanout to a slow victim (much larger heaps or dedicated load hosts) to test the
N=4 vs N=32 window directly. Cleanup verified: no Cassandra JVMs, IP aliases, or port-7000 rules left on any
node; lingering disabled.
