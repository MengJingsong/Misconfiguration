# C1 — internode application receive-queue exclusive allowance × active peers (multiplicity)

**Direction / sub-direction:** convergence · multiplicity.
**Allocation domain:** internode inbound application receive queues (per-connection exclusive
allowance Q, per-endpoint reserve E, global reserve G) — off-heap LARGE-message frame buffers.
**Capacity regime:** default capacities for Q / E / G (4 MiB / 128 MiB / 512 MiB), with disclosed
supporting deviations (see §1 audit). **Budget regime:** deliberately tightened diagnostic direct-memory
budget (`-XX:MaxDirectMemorySize`), victim cgroup-isolated, swap off.
**Pinned source:** cassandra-5.0.9 (upstream `b5f2a54210`; local build baselines `46cb80db…` victim /
`28adf490…` peers — separate `copy-source.sh` copies of the same tag, per the stage-4 environment note).

> **Follow-ups:** [run 2 (custom Q)](internode_application_receive_queue_capacity--multiplicity--run2-customQ.md) and [run 3 (fast co-replica)](internode_application_receive_queue_capacity--multiplicity--run3-fastcoreplica.md). All C1 design files are in [`design/`](design/).

**Date:** 2026-11-09. **Verdict:** mechanism **confirmed at the admission level**; a
**multiplicity-attributable OOM is a sensitivity limit / UNRESOLVED** (see §4).

This case executes the approved method in `design/C1-design-codex-v1.md`
(Codex v1) under `../../../../verification-protocol.md` and the
[default-convergence playbook](../../../../default-convergence-playbook.md).

---

## 1. Constraints, protection map, defaults audit

### Mechanism (from the C1 source audit, re-verified here)
Victim inbound admission `AbstractMessageHandler.acquireCapacity` (`AbstractMessageHandler.java:411–459`):
bytes that fit within a connection's exclusive queue **Q** are admitted touching **no reserve**
(`:415–419`); only overflow beyond Q is charged to the **global** reserve G first (`:428`) then the
**endpoint** reserve E (`:431`). Because global gates endpoint, `Σ_peers endpoint.using ≤ global.using ≤ G`,
so the per-peer reserve **cannot converge past G**. The only term with no process-global byte cap is the
**exclusive per-connection queue Q**. Admitted-byte ceiling: **A_max(N,k) = N·k·Q + min(G, N·E)**.

| Symbol | Scope | Default | Source | Resolved here |
|---|---|---|---|---|
| Q | exclusive per receive connection | **4 MiB** | `Config.java:257` | default (4 MiB); 1 MiB in the reduced-Q control only |
| E | reserve shared by one endpoint's receive conns | **128 MiB** | `Config.java:259` | default, unchanged |
| G | reserve shared across endpoints (process-global) | **512 MiB** | `Config.java:261` | default, unchanged |
| N | active data-bearing peers coordinating writes | swept | — | 4, ~6–8 reached; 16/32 blocked (§3) |
| k | loaded connection types per sender | 1 (LARGE) | — | 1 (mutations > 64 KiB → LARGE) |

Live `Config.java:1371` dump at run time confirmed `internode_application_receive_queue_capacity=4MiB`,
`…reserve_endpoint_capacity=128MiB`, `…reserve_global_capacity=512MiB` on the default-arm victim.

### Protection map (verification-protocol §Protection map)
- **Allocation/ownership:** LARGE (>64 KiB) internode frame bytes held in the victim's inbound queues; the
  backing buffers are off-heap (`ByteBuffer.allocateDirect`, networking `BufferPool`), released after the
  MUTATION verb runs on MutationStage or after message expiry.
- **Local contract:** hard per-connection cap Q=4 MiB exclusive; hard reserves E=128 MiB/endpoint and
  G=512 MiB/process. Charged quantity = serialized frame bytes.
- **Scope/multiplicity:** per receive connection; bounded simultaneous instances = N active senders. G caps
  total borrowed reserve; **the exclusive Q term (N·Q) escapes every aggregate counter**.
- **Aggregate coverage:** G (512) gates E (128); one peer can borrow ≤ E so **one peer cannot saturate G**
  — G saturates only at **N ≥ 4**. Backpressure (`throttledCount`) returned when reserve is exhausted.
- **Lifetime:** transient; released post-verb or at `write_request_timeout` expiry.
- **Budget:** `-XX:MaxDirectMemorySize` (direct pool) governs the LARGE-frame region; cgroup `memory.max`
  above the JVM budget so the JVM OOM fires first.

### Config / JVM audit (every change classified)
| Change | Class | Value | Why |
|---|---|---|---|
| Q / E / G | **tested capacity** | 4/128/512 MiB (**default**) | the constraint under test (default arms) |
| `internode_application_receive_queue_capacity` | **tested capacity (custom)** | **1 MiB** | reduced-Q causal control only (§3) — custom-capacity sub-result |
| `-XX:MaxDirectMemorySize` | **budget** (tightened diagnostic) | 2048 MiB (calibration) / 450 MiB (OOM test) | the stopping budget for Arm D |
| cgroup `MemoryMax` / `MemorySwapMax` | budget / env | 4096 MiB / 0 | isolate victim, JVM OOM first, swap off (victim only) |
| `concurrent_writes` | **supporting deviation** | 2 | backpressure the MutationStage |
| Byteman mutation apply-delay | **supporting deviation (intervention)** | 100 ms at `MutationVerbHandler.doVerb` ENTRY | natural backpressure unreachable (§3); diagnostic, frozen, saved (`harness/mutation-delay.btm`) |
| `write_request_timeout` | **supporting deviation** | 30000 ms (default 2000) | raise the message-expiry ceiling so queues can fill at modest arrival |
| `num_tokens`, `initial_token`, `auto_bootstrap`, `listen/rpc_address`, `seeds`, dirs | environment/topology | — | multi-instance ring on one LAN; explicit tokens avoid random-token collisions |
| `key_cache_size`, `counter_cache_size` | environment | 0 | keep peers light; not a tested capacity |

This is **default capacities (Q/E/G) with supporting deviations**; the budget is a *deliberately
tightened diagnostic direct-memory budget*. Default capacities ≠ entirely default deployment.

---

## 2. Dated executable design (2026-11-09)

Hypothesis: multiplying the exclusive per-connection allowance (N·Q) raises live direct memory beyond a
fixed victim budget while G/E admission rules still hold. Predicted protective response: G caps shared
reserve; the escaping term is N·Q (16 MiB at N=4 → 128 MiB at N=32).

Topology (CloudLab, one experiment, LAN 10.10.1.0/24): victim `apt140`/10.10.1.1; peer instances on
`apt179/138/190/149` via LAN IP aliases, own conf/data/logs under `/mydata`, distinct JMX ports. Fixed
ring, SimpleStrategy RF = ring size; **vary N by restricting the stress coordinator whitelist** to N peers
(membership constant). Arm D: mutations with a 128 KiB blob (`-col size=FIXED(131072) n=FIXED(1)`) →
> 64 KiB → LARGE connections → off-heap frames; CL=ONE. Victim bounded by `-XX:MaxDirectMemorySize`.
Harness: `harness/{peer-ctl.sh,victim-ctl.sh,arm.sh,analyze.py,mutation-delay.btm}`. Instrumentation:
`system_views.internode_inbound` (per-peer `using_bytes`, `using_reserve_bytes`, `throttled_count`) sampled
~2 s; global reserve traced as `Σ using_reserve_bytes`; RssAnon + cgroup `memory.current`/`memory.events`
sampled 1 s; `jcmd VM.native_memory` (NMT enabled). Per-workload cap ≤ ~5 min; batch ≤ ~3 h.

**Intended** topology was a 33-node RF=33 ring (victim + 32 peers, 8/host) to reach N=32. It was reduced to
a **9-node RF=9 ring** (victim + 8 peers, 2/host, 2 GiB heap each) after the 512 MiB-heap coordinators
OOMed under the RF=33 fanout (§3). Calibration gates G1–G5 per Codex v1 §5.

Calibration gates, controls, repeats and the predeclared reduced-Q control (Q=1 MiB at fixed N) follow
Codex v1 §5–6 and verification-protocol §Design-and-execution.

---

## 3. Runtime results (per-arm)

Ring ready ~16:22; batch within the ~3 h budget. Full logs on the nodes:
`/mydata/c1/victim/logs{,.prev}` and `/mydata/c1/arms/<arm>/` (`queue.log`, `mem.csv`, `stress.out`,
`qfinal.txt`, `arm.log`); peer logs `/mydata/c1/inst-*/logs`. Small excerpts in `logs/`.

| Arm | N | Q | direct budget | Byteman | Peak admitted (using) | Peak reserve | Outcome |
|---|---|---|---|---|---|---|---|
| G1 reachability | 4 | 4 MiB | 2048 MiB | off | **0.4 MiB** | 0 | schema RF-agreed; **no natural backpressure** (queues drain) |
| G2 natural high-load | 4 | 4 MiB | 2048 MiB | off | n/a | n/a | **void** — 512 MiB coordinators OOMed (heap); sender bottleneck |
| **D_cal_n4 (reference)** | 4 | 4 MiB | 2048 MiB | 100 ms | **527.8 MiB** | **511.8 MiB (≈G)** | **survives; G saturated**; per-conn 4.0 MiB excl + 127.9 MiB rsv |
| D_cal_n8 | ~6–8 | 4 MiB | 2048 MiB | 100 ms | 438.0 MiB | 414.0 MiB | survives; **≤ N=4, non-monotonic/noisy**; coordinators dying |
| **RQ_n4_q1 (reduced-Q control)** | 4 | **1 MiB** | 2048 MiB | 100 ms | 383.9 MiB | 379.9 MiB | survives; **per-conn exclusive = 1.00 MiB (=Q)** |
| D_oom_n4_b450 | — | 4 MiB | **450 MiB** | 100 ms | — | — | **Direct-buffer OOM ~17 s after startup**, before load (baseline/ring-reconnect) |

### Mechanism confirmation (D_cal_n4, G3)
Peak sample, each of the 4 coordinator connections (`logs/n4-peak-per-peer.txt`):
`using 131.9 MiB = reserve 127.9 MiB (≈ E=128) + exclusive 4.0 MiB (= Q=4)`. Σreserve 511.6 MiB ≈ **G=512
saturated**; total admitted **527.8 MiB = A_max(4) = 4·4 + 512 = 528 MiB** — the model to within 0.2 MiB.
`throttled_count` nonzero (admission backpressure active). Victim survived at the 2048 MiB budget
(RssAnon 2696 MiB, no cgroup kill). This meets G1–G3: reachability, endpoint-borrowing/throttle validated,
and G demonstrably saturated at N=4. One peer reaching only ≤ E=128 MiB confirms "one peer cannot saturate G."

### Higher-N (G4) and the sender bottleneck
Natural backpressure is unreachable: at modest load the victim's MutationStage keeps up (queues ~0); forcing
higher arrival OOMs the peer **coordinators** (512 MiB heap → G1 Old Gen full → `OnOutOfMemoryError kill`;
even 2 GiB coordinators died repeatedly), because a coordinator retains 128 KiB Mutation objects destined
for the slow victim. This is the **sender bottleneck** the verification-protocol names. Consequently N=16/32
could not be sustained on a stable ring; the RF=33 topology was reduced to RF=9. At N≈6–8, peak reserve
(414 MiB) and admitted (438 MiB) did **not** exceed N=4 and varied non-monotonically — occupancy is governed
by transient fill/drain and coordinator survival, not by N.

### Reduced-Q causal control (custom-capacity sub-result)
At fixed N=4 with **Q=1 MiB**, per-connection exclusive dropped to exactly **1.00 MiB** (vs 4.0 MiB at
default), while the reserve still filled (→ 379.9 MiB) — cleanly isolating the exclusive allowance as the
Q knob. The **memory effect is ~12 MiB** (4→1 MiB × 4 conns), i.e. below the occupancy noise floor.

### Terminal outcome characterization
A **direct-buffer OOM** (`OutOfMemoryError: Direct buffer memory`, then forced heap OOM) is reachable at a
450 MiB budget, but it fired ~17 s after startup on `Messaging-EventLoop` threads **before the load arm
connected** — i.e. from the baseline networking `BufferPool` + ring-reconnect, not the C1 multiplicity term.
Recorded separately per verification-protocol: direct-buffer OOM = yes (baseline/reserve-driven);
cgroup OOM-kill = no; GC service loss = no.

### Noise vs signal
Within the D_cal_n4 arm, per-sample total occupancy swung **~81 → 528 MiB (±~350 MiB)**. The entire
multiplicity signal available between N=4 and N=32 is **N·Q = 16 → 128 MiB (≤ 112 MiB)** — smaller than the
observed noise, and far smaller than the invariant reserve G=512 MiB.

---

## 4. Conclusion and limits of attribution

**The C1 admission mechanism is confirmed exactly.** At N=4 the measured occupancy matches A_max(N)=N·Q+G
to within 0.2 MiB; the per-connection exclusive allowance is Q (4.0 MiB default; 1.0 MiB under the reduced-Q
control), the endpoint reserve saturates at E=128 MiB/peer, and the global reserve saturates at G=512 MiB
with N≥4 — one peer alone cannot saturate G. The reduced-Q control cleanly attributes the exclusive term to Q.

**A multiplicity-attributable OOM is a sensitivity limit — UNRESOLVED for C1 in this environment.** Three
independent, measured obstacles, each anticipated by the design's decision rules:
1. **The exclusive term is small and dominated by the invariant reserve.** Live receive-queue memory is
   dominated by G=512 MiB, which is identical at every N; the escaping N·Q term is 16 MiB at N=4 and at most
   128 MiB at N=32. Any OOM reached by tightening the direct budget fires when the **shared reserve** (plus
   baseline networking pool) overflows the budget — a reserve-driven / budget-sizing failure, not an
   exclusive-allowance multiplicity gap. Per Codex v1 §8 / verification-protocol, a failure dominated by
   rising reserve use leaves the exclusive-allowance claim unresolved.
2. **Noise ≫ signal.** Observed occupancy fluctuation (±~350 MiB) exceeds the whole N=4→32 multiplicity
   window (≤112 MiB); the distributions overlap substantially, so the sensitivity limit is filed honestly
   rather than forced.
3. **Sender bottleneck.** The peer coordinators OOM under RF fanout to the slow victim before a high-N
   arm can be sustained, so N=16/32 (where N·Q becomes comparable to the noise) could not be tested on a
   stable ring; the topology had to be reduced from RF=33 to RF=9.

No OOM was manufactured. The reference (N=4, G saturated) survives at the frozen 2048 MiB budget; a
direct-buffer OOM exists only at a budget (450 MiB) so tight that the baseline + shared reserve alone
exceed it, independent of multiplicity.

**Supporting-deviation dependence:** the queue-fill results are *conditional on the Byteman apply-delay*
and the 30 s write timeout; without a slowed consumer the victim drains and queues stay ~0 (G1). Reproduction
without injection was negative (no natural backpressure at reachable load; higher load OOMs the senders).

**Status:** C1 / internode private allowances / default capacities, tightened diagnostic budget — mechanism
validated, multiplicity-OOM **sensitivity-limited / unresolved**; blocked at high N by sender resources.
Reopen with coordinators that survive RF-fanout to a slow victim (far larger heaps or dedicated load hosts)
to test the N=4 vs N=32 window directly.
