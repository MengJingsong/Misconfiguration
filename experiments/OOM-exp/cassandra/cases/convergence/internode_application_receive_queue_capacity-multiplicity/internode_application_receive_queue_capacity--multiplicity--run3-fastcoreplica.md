# C1 run 3 — internode receive-queue exclusive allowance × peers, FAST CO-REPLICA decoupling

**Direction / sub-direction:** convergence · multiplicity.
**Allocation domain:** internode inbound application receive queues (per-connection exclusive
allowance Q, per-endpoint reserve E, global reserve G) — off-heap LARGE-message frame buffers.
**Capacity regime:** default Q/E/G (4 / 128 / 512 MiB) in the calibration arms run; the custom-Q (S1)
and N (S2) sweeps were **not run**. **Budget regime:** generous calibration budget
(`-XX:MaxDirectMemorySize=3072 MiB`, cgroup `MemoryMax=7168 MiB`, swap off); the tightened-budget OOM
stage was **not run**.
**Pinned source:** cassandra-5.0.9 (victim `~/cassandra-b1`, fast replica + coordinators `~/cassandra-c1`).
**Date:** 2026-11-10. **Verdict: INCOMPLETE — calibration only, and stopped early by an analysis error.**
The decoupling topology **works and the victim's receive queue reaches the admission ceiling with live
senders**: at N=8, Q=4 the queue held **543 MiB = 8×4.0 MiB exclusive + 511 MiB reserve (A_max = 544)**,
`throttled_count` > 0, victim and all 8 coordinators alive, client at the offered rate. This is the
first time in runs 1–3 that the ceiling was reached at N=8 without sender OOM. The run was then stopped
on a **false negative** (sampler bug, §3.1); S1/S2, reduced-Q and the OOM boundary remain to be run.

> **Correction (2026-11-10, same day).** An earlier version of this file reported "G3 FAIL — receive
> queue never fills; capacity is released at dispatch; C1 parked". That was wrong. The live sampler
> summed the `|` separator fields of cqlsh output, so it printed 0 for `using`/`reserve`/`throttled`
> regardless of the data. The raw `queue.log` files written by `arm3.sh` show the ceiling was reached.
> The "dispatch-time release" explanation was never supported by the source either: in
> `InboundMessageHandler.ProcessMessage.run()` capacity is released in `finally` **after**
> `consumer.accept` (`:430–440`). It is withdrawn.

Executes [`design/C1-run3-plan-review.md`](design/C1-run3-plan-review.md)
under [`../../../../verification-protocol.md`](../../../../verification-protocol.md). Follows
[run 1](internode_application_receive_queue_capacity--multiplicity--run1-defaultQ.md) and
[run 2](internode_application_receive_queue_capacity--multiplicity--run2-customQ.md).

---

## 1. Constraints, protection map, configuration labels

Mechanism as in runs 1–2: `AbstractMessageHandler.acquireCapacity` admits bytes within a connection's
exclusive Q without touching reserves; overflow is charged to global G then endpoint E.
**A_max(N,k) = N·k·Q + min(G, N·E)**, k=1 (LARGE, 1 MiB mutations).

### Topology
`keyspace1` = `NetworkTopologyStrategy {v:1, f:1}`, `GossipingPropertyFileSnitch`, **CL=ONE**: every write
goes to the victim and the fast co-replica; the client is acked by the fast one.

| Node | LAN IP | Role | Heap |
|---|---|---|---|
| apt140 | 10.10.1.1 | victim (dc=v, slow, cgroup-isolated, swap off) | 1 GiB |
| apt179 | 10.10.1.2 | fast co-replica (dc=f), normal apply | 4 GiB |
| apt138 / apt190 / apt149 | .31–.33 / .41–.43 / .51–.52 | 8 coordinators (dc=c, aliases, no replica) | 1 GiB each |

### Config / JVM audit
| Change | Class | Value | Note |
|---|---|---|---|
| Q / E / G | tested capacity (default) | 4 / 128 / 512 MiB | sweeps not run |
| `-XX:MaxDirectMemorySize`, cgroup | budget (calibration) | 3072 / 7168 MiB, swap 0 | |
| `concurrent_writes` (victim) | supporting deviation | 2 | |
| Byteman `MutationVerbHandler.doVerb` | supporting deviation | 100 ms | `harness/mutation-delay.btm` |
| `hinted_handoff_enabled` | supporting deviation | false (all instances) | plan point 3 |
| `write_request_timeout` | supporting deviation | **victim 120 s; coordinators left at 2 s (defect, §3.2)** | plan point 1 only half-applied |
| snitch / dc / tokens / NTS {v:1,f:1}; key/counter cache 0 | environment | — | |

---

## 2. Executed design (2026-11-10)

Plan-review requirements: (1) size the timeout from the measured drain rate D; (2) open-loop generator
(`cassandra-stress -rate fixed=<r>/s`) just above D; (3) hints off. Harness `harness/` (`victim-ctl3.sh`,
`peer-ctl3.sh`, `arm3.sh`, `analyze.py`, `mutation-delay.btm`; `qsample-BUGGY.sh` kept as the record of
the faulty live sampler). Raw data on the nodes under `/mydata/c1r3/arms/<arm>/` (`queue.log` is
authoritative). Excerpts in `logs/` — **read `logs/README.md` first**.

---

## 3. Runtime results

10 instances UN. 1 MiB LARGE mutations, Byteman 100 ms, hints off, budget 3072 MiB.

| Gate / arm | Result |
|---|---|
| **G1** replica placement | **PASS** — `getendpoints` → {10.10.1.1, 10.10.1.2} for all sampled keys; coordinators own nothing |
| Drain rate D | ≈ 20 mutations/s ≈ 20 MiB/s (from `processed_count` over a 60 s arm; consistent with 2 threads × 100 ms; not re-verified after the parse bug) |
| **G2** client decoupled | **PASS** — `fixed=40/s`: client 40 op/s, mean 22.4 ms, 0 errors while the victim drains ~20/s |
| probe2 `fixed=40/s`, N=4 | peak 85 MiB (16 excl + 69 rsv), throttled 0 — below ceiling |
| probe3 `fixed=150/s`, N=4 | **peak 524 MiB = 16 excl + 508 rsv** (A_max(4)=528), throttled 31 |
| **burst `fixed=300/s`, N=8** | **peak 543 MiB = 32 excl + 511 rsv (A_max(8)=544)**, throttled 129; every connection exclusive = 4.0 MiB |
| threadtest `threads=1200`, N=8 | peak 543 MiB, throttled 289; client got `WriteTimeoutException` (0 acks) at this load |
| victim / coordinators | victim alive in all arms (no OOM, no cgroup kill); **no `java.lang.OutOfMemoryError` on any coordinator** |
| MutationStage (victim) | pending 130–315 during load (`tpstats`, valid column) |

**G3 (ceiling reached, throttling active, senders alive): PASS at N=4 and N=8, Q=4.** Evidence:
`logs/G3-queue-reparse.txt`.

### 3.1 The analysis error that stopped the run
Live sampling during the run used `qsample.sh`/inline awk that summed fields `$4/$6/$8` of cqlsh's
`addr | a | b | c` output; those are `|` separators, so every value read 0. On that reading the run was
stopped and filed as "G3 FAIL", and a mechanism ("capacity released at dispatch") was invented to explain
it. The raw logs contradict both.

### 3.2 Open defects for the continuation
- **Coordinator timeout left at 2 s.** The message's `expiresAt` is set by the *sender*, so plan point 1
  was not actually in force: `expired_count` reached ~10–16 k (cumulative). The Q=4 ceilings were still
  reached because the offered rate was high, but the Q=64 arms (A_max/D ≈ 51 s) cannot reach their
  ceiling until the coordinators also run with T > A_max/D.
- Much of the queued data at the ceiling is already expired when it is dequeued; this is load-bearing for
  the C1 interpretation and must be measured per arm (expired vs processed).
- Coordinator heap was not sampled; survival is established from logs only.
- `threads=1200` exceeded the client/fast path (WriteTimeout); stay with fixed-rate arms.

---

## 4. Conclusion and limits

**Mechanism:** reproduced again, now at N=8 with live senders (exclusive = N·Q to the MiB, reserve ≈ G,
throttling active). **Multiplicity/Q attribution: not yet tested.** The run reached the point where run 2
was blocked (ceiling reachable without client coupling or sender OOM) and then stopped by mistake. This
does **not** show that total live memory grows with N·Q or that any OOM is attributable to it; those are
Stage C/D.

**Status:** C1 run 3 — G1–G3 pass; Stage C (S1 Q=4/16/64 at N=8, S2 N=4 vs 8, reduced-Q) and Stage D
(frozen budget, ≥3 repeats, reduced-Q intervention) outstanding. Fix the coordinator timeout first.

All 10 instances stopped, aliases removed; 0 Cassandra JVMs on every node (verified with `ps`); the
failed victim systemd unit record cleared and linger (enabled for this run) disabled on all five nodes.
