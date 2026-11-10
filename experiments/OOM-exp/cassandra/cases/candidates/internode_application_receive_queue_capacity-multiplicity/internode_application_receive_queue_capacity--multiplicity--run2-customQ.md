# C1 reopen — internode receive-queue exclusive allowance × peers, CUSTOM Q (multiplicity)

**Direction / sub-direction:** convergence · multiplicity.
**Allocation domain:** internode inbound application receive queues (per-connection exclusive
allowance Q, per-endpoint reserve E, global reserve G) — off-heap LARGE-message frame buffers.
**Capacity regime:** **CUSTOM** per-connection capacity Q (swept 4 / 16 / 64 MiB, plus a 1 MiB
reduced-Q control); E / G left at defaults (128 / 512 MiB). Disclosed supporting deviations in §1.
**Budget regime:** deliberately tightened diagnostic direct-memory budget (`-XX:MaxDirectMemorySize`),
victim cgroup-isolated (`MemoryMax` above the JVM budget), swap off (victim only).
**Pinned source:** cassandra-5.0.9 (victim build `~/cassandra-b1`, peers `~/cassandra-c1`).

> **Follow-up:** [run 3 (fast co-replica)](internode_application_receive_queue_capacity--multiplicity--run3-fastcoreplica.md) decouples the client from the victim and reaches the admission ceiling at N=8. All C1 design files are in [`design/`](design/).

**Date:** 2026-11-09. **Verdict:** mechanism **confirmed exactly** (exclusive allowance = N·Q to the
MiB); the two topology fixes this reopen introduced **both succeeded** (RF=1-to-victim keeps coordinators
alive at N=8; natural backpressure is now reachable). A genuine **load-driven receive-path direct-buffer
OOM is now reachable** (3/3 at a 384 MiB budget — better than run 2's startup-only OOM), **but it is NOT
Q/multiplicity-attributable**: in the single-replica (CL=ONE-on-victim) topology the victim receive-queue
reaches a **closed-loop occupancy equilibrium (~266 MiB) below the admission ceiling** (`throttled_count`
≡ 0), so raising Q only **re-buckets** this fixed total from reserve into the exclusive allowance — total
live memory is **Q-invariant** and the OOM fires at the **same budget for Q=4 and Q=64**. Q-attribution
**UNRESOLVED / negative**. See §4.

Reopens the run-2 default-Q negative:
[`internode_application_receive_queue_capacity--multiplicity--run1-defaultQ.md`](internode_application_receive_queue_capacity--multiplicity--run1-defaultQ.md).
Executes the approved method `design/C1-design-v2.md` under `../../../../verification-protocol.md`
and the [custom-convergence playbook](../../../../custom-convergence-playbook.md).

---

## 1. Constraints, protection map, configuration labels

### Mechanism (re-verified live here)
Victim inbound admission `AbstractMessageHandler.acquireCapacity`: bytes that fit a connection's
exclusive queue **Q** are admitted touching **no reserve**; only overflow beyond Q is charged to the
**global** reserve G first, then the **endpoint** reserve E. Because global gates endpoint,
`Σ endpoint.using ≤ global.using ≤ G`, so per-peer reserve cannot converge past G. The only term with no
process-global byte cap is the **exclusive per-connection queue Q**. Admitted-byte ceiling:
**A_max(N,k) = N·k·Q + min(G, N·E)**; E=128, G=512 MiB, k=1 (LARGE), defaults.

| Symbol | Scope | Default | Resolved here |
|---|---|---|---|
| Q | exclusive per receive connection | 4 MiB | **CUSTOM, swept 4 / 16 / 64 MiB; 1 MiB reduced-Q control** |
| E | reserve shared by one endpoint's receive conns | 128 MiB | default, unchanged |
| G | reserve shared across endpoints (process-global) | 512 MiB | default, unchanged |
| N | active data-bearing peers coordinating writes | — | swept 1 / 4 / 8 |
| k | loaded connection types per sender | 1 (LARGE) | 1 (mutations > 64 KiB → LARGE) |

Live `Config.java:1371` dump at run time confirmed `internode_application_receive_queue_capacity`
= 4 / 16 / 64 / 1 MiB per arm, `…reserve_endpoint_capacity=128MiB`, `…reserve_global_capacity=512MiB`.

### Protection map
- **Allocation/ownership:** LARGE (>64 KiB) internode frame bytes held in the victim's inbound queues;
  off-heap (`BufferPool`/`allocateDirect`), released after the MUTATION verb runs or at message expiry.
- **Local contract:** hard per-connection cap Q (custom) exclusive; hard reserves E=128/endpoint,
  G=512/process. Charged quantity = serialized frame bytes.
- **Scope/multiplicity:** per receive connection; simultaneous instances = N active senders; the exclusive
  N·Q term escapes every aggregate counter.
- **Aggregate coverage:** G gates E; one peer borrows ≤ E so G saturates only at N ≥ 4. Backpressure
  (`throttled_count`) when reserve is exhausted.
- **Lifetime:** transient; released post-verb or at `write_request_timeout` expiry.
- **Budget:** `-XX:MaxDirectMemorySize` governs the LARGE-frame direct region; cgroup `MemoryMax` above it.

### Topology (design v2 — the premise under test)
Victim owns the **only** replica: keyspace `keyspace1` = `NetworkTopologyStrategy {v:1}`,
`GossipingPropertyFileSnitch`, victim datacenter `v`, 8 coordinator instances datacenter `c`
(2 per host on apt179/138/190/149, LAN IP aliases .32/.33/.48/.49/.64/.65/.80/.81, 1 GiB heap, own no
replica). **CL=ONE** → the single replica (victim) must ack. Explicit evenly-spaced `initial_token` per
instance. N varied by the stress coordinator whitelist (membership constant at 8).

### Config / JVM audit (every change classified)
| Change | Class | Value | Why |
|---|---|---|---|
| `internode_application_receive_queue_capacity` | **tested capacity (CUSTOM)** | **4 / 16 / 64 / 1 MiB** | the swept constraint |
| E / G reserves | tested capacity (default) | 128 / 512 MiB | left default |
| `-XX:MaxDirectMemorySize` | budget (tightened diagnostic) | 3072 MiB (calibration) / tightened (OOM test, §3) | stopping budget |
| cgroup `MemoryMax` / `MemorySwapMax` | budget / env | 7168 MiB / 0 | isolate victim, JVM OOM first, swap off |
| `concurrent_writes` | supporting deviation | 2 | backpressure MutationStage |
| Byteman `MutationVerbHandler.doVerb` apply-delay | supporting deviation (intervention) | 100 ms | slow the consumer so queues fill (`harness/mutation-delay-100.btm`) |
| `write_request_timeout` | supporting deviation | 30000 ms (default 2000) | raise expiry ceiling so queues fill past arrival×2 s |
| snitch / dc / rack / `initial_token` / NTS {v:1} | **environment / topology** | — | single-replica-on-victim premise (design v2) |
| `key_cache_size`, `counter_cache_size` | environment | 0 | keep instances light |

CUSTOM per-connection capacity with supporting deviations; budget is a tightened diagnostic direct-memory
budget. (Co-reported with the run-2 **default**-Q negative, the confirmatory boundary arm.)

---

## 2. Dated executable design (2026-11-09)

Hypothesis: multiplying the **custom (raised)** exclusive allowance N·Q raises live direct memory beyond a
fixed victim budget while G/E rules still hold. Predicted protective response: G caps shared reserve; the
escaping term is N·Q. Run 2 (default Q=4) was negative for three reasons; design v2 fixes each:
(a) raise Q so N·Q dominates; (b) victim owns the only replica, RF=1, so senders retain ~one in-flight
mutation (no sender OOM); (c) concentrate all load on one victim so backpressure is natural.

Arms (LARGE 1 MiB mutations → off-heap frames; CL=ONE; victim bounded by `-XX:MaxDirectMemorySize`):
- **S1 (allowance):** N=8 fixed, Q = 4 / 16 / 64 MiB. Predicted admitted ceiling 544 / 640 / 1024.
- **S2 (multiplicity):** Q=64 fixed, N = 1 / 4 / 8. Predicted ceiling 192 / 768 / 1024.
- **Reference (survives):** low ends (S1 Q=4; S2 N=1).
- **Reduced-Q causal control:** Q=1 MiB at N=8, same E/G/budget/load.
- **Default-Q boundary:** the run-2 negative (cross-linked).

Harness `harness/{victim-ctl2.sh, peer-ctl2.sh, arm2.sh, analyze.py, mutation-delay-100.btm}` (adapts the
run-2 harness with snitch/dc, explicit tokens, per-arm Q via `setq`, NTS {v:1}, `no-warmup`, large stress
heap). Instrumentation: `system_views.internode_inbound` (`using_bytes`, `using_reserve_bytes`,
`throttled_count`, `received/processed/expired_count`) sampled ~2 s; exclusive = using − reserve; live
java.nio direct via `nodetool gcstats`; `jcmd VM.native_memory` (NMT); RssAnon + cgroup `memory.current`/
`memory.events` 1 s. Per-workload ≤ ~5 min; batch ≤ ~3 h.

Full logs on the nodes: `/mydata/c1r/victim/logs{,.prev}` and `/mydata/c1r/arms/<arm>/`
(`queue.log`, `mem.csv`, `stress.out`, `qfinal.txt`, `nmt-final.txt`, `arm.log`). Small excerpts in `logs/`.

---

## 3. Runtime results (per-arm)

Ring ready ~19:20 (9 instances: 1 victim dc=v + 8 coordinators dc=c, all `UN`). Blobs 1 MiB (LARGE),
Byteman 100 ms, `write_request_timeout`=30 s, calibration budget 3072 MiB unless noted.

### Calibration gates
- **G1 (replica only on victim):** `nodetool getendpoints keyspace1 probe <k>` → **10.10.1.1 only** for
  10/10 sample keys; `DESCRIBE keyspace1` = `NetworkTopologyStrategy {'v':'1'}`. Victim sees all 8
  coordinator inbound handlers (idle `using_bytes`=0; background gossip only). **PASS.**
- **G2 (confirm the RF=1 fix — coordinators survive at N=8):** under the N=8 load, coordinator heap stayed
  **~336–384 / 1024 MiB** (`nodetool info`), no sender OOM across all arms. **PASS — the whole premise of
  design v2 holds.** (Run 2's 512 MiB *and* 2 GiB coordinators OOMed under RF-fanout; RF=1 removes that.)
- **G3 (noise band):** at N=8, per-sample total occupancy swung **~±8–10 MiB** around the plateau — vs
  run 2's **±~350 MiB**. Concentrating load on one victim shrank the band ~35×. **PASS.**
- **G5 (backpressure):** *natural* backpressure IS now reachable — without Byteman each inbound queue fills
  to ~1.5–1.7 MiB/conn (run 2: 0.4 MiB), but writes time out at the default 2 s and queues do not reach Q.
  With the **declared Byteman 100 ms delay** the exclusive allowance fills to exactly Q per connection
  (arms labelled conditional on the delay; reproduction without it below).
- **G4 (freeze budget):** frozen at **384 MiB** for the OOM test (clean idle direct 34 MiB, equilibrium
  queue ~266 MiB + networking-pool overflow). Because total occupancy is Q-invariant (§3 ladders), no
  budget both lets a low-Q arm survive and makes Q=64,N=8 OOM *by the N·Q term*: the 384 MiB OOM fires
  identically at Q=4 and Q=64 — it is aggregate-occupancy/pool-driven, not an exclusive-allowance gap.

### The ladders — occupancy is Q-invariant; raising Q re-buckets reserve → exclusive
Steady-state sums over the ~250 ms–2 s samples (exclusive = using − reserve). `throttled_count` stayed
**0 in every arm** — the admission ceiling was never reached.

**S1 (N=8, vary Q):**
| Arm | Q | predicted ceiling | **using (total)** | **exclusive = N·Q** | reserve | live direct (gcstats) | throttle | outcome |
|---|---|---|---|---|---|---|---|---|
| S1_q4_n8 (reference) | 4 MiB | 544 | **~266 MiB** | **32.0 MiB (=8×4)** | ~234 MiB | ~400 MiB | 0 | survives |
| S1_q16_n8 | 16 MiB | 640 | **~266 MiB** | **128.0 MiB (=8×16)** | ~138 MiB | ~430 MiB | 0 | survives |
| S1_q64_n8 | 64 MiB | 1024 | **~267 MiB** | **267 MiB (all; per-conn ~33 < Q)** | **~0 MiB** | ~428 MiB | 0 | survives |

The "live direct" column is `nodetool gcstats` Direct Memory Bytes (post-GC, noisy, and inflated by the
allocator's retained BufferPool after earlier heavy arms — NMT shows the retained "Other" region stays
~700 MiB even when `using_bytes`=0; a *clean-start* idle is only ~34 MiB, see the OOM test). The reliable
live-queue metric is `using_bytes`. At Q=64 each connection's ~33 MiB of queued frames fits entirely in
its 64 MiB exclusive allowance, so **reserve falls to 0** — the same ~267 MiB total as Q=4/16, now labelled
entirely "exclusive". Total queued (and total live direct) is **Q-invariant**.

**S2 (Q=64, vary N):**
| Arm | N | predicted ceiling | using (total) | exclusive | reserve | live direct | throttle | outcome |
|---|---|---|---|---|---|---|---|---|
| S2_q64_n1 (reference) | 1 | 192 | **~34 MiB** | **~34 MiB (all)** | ~0 | ~180 MiB | 0 | survives |
| S2_q64_n4 | 4 | 768 | **~140 MiB** | **~140 MiB (all)** | ~0 | ~266 MiB | 0 | survives |
| S2_q64_n8 | 8 | 1024 | **~267 MiB** | **267 MiB (all)** | ~0 | ~428 MiB | 0 | survives |

Occupancy scales ~linearly with N (per-connection equilibrium ~33–38 MiB, below Q=64), **not** toward the
predicted admission ceilings (192 / 768 / 1024) — `throttled_count` ≡ 0, so the ceiling (which carries the
N·Q term) is never the binding constraint.

**Reduced-Q control (N=8, Q=1 MiB):** using **266 MiB**, exclusive **8.0 MiB = exactly N·Q** (1.000 MiB
per connection = Q), reserve **258 MiB**, throttle 0. Dropping Q from 64→1 moves bytes **exclusive→reserve**
with the **total unchanged (266 MiB)**. The pre-declared reduced-Q causal control therefore **does not
reduce the footprint** — there is no Q-driven memory to remove. (It still cleanly attributes the exclusive
term to Q: per-connection exclusive = Q to the byte at every Q = 1 / 4 / 16 / 64.)

**Occupancy invariance:** with 800 vs 1500 client threads the N=8/Q=4 plateau was identical (~266 MiB) —
occupancy is a **closed-loop server-side equilibrium**, not thread-bound. See §4.

### OOM attempt / terminal outcome — direct-buffer OOM is reachable, but Q-independent
Budget tightened to **`-XX:MaxDirectMemorySize=384 MiB`** (clean start: idle NMT "Other" = 34 MiB).

| Arm | Q | budget | outcome | OOM site |
|---|---|---|---|---|
| OOM_q64_n8_b384 | 64 MiB | 384 | **direct-buffer OOM, victim JVM killed** ~23 s into load | — |
| OOM_q4_n8_b384 (control) | 4 MiB | 384 | **direct-buffer OOM, victim JVM killed** ~load | identical |

Both fired **after** startup (02:59:26 ready → 02:59:51 OOM; 03:01 ready → 03:01:43 OOM), **under load**,
as `java.lang.OutOfMemoryError: Direct buffer memory` on a `Messaging-EventLoop` thread at the **inbound
receive path**: `EpollRecvByteAllocatorHandle.allocate` → `BufferPoolAllocator.newDirectBuffer` →
`BufferPool.allocate` → `ByteBuffer.allocateDirect` → `Bits.reserveMemory`, preceded by
`Maximum memory usage reached (128.000MiB) for networking buffer pool, cannot allocate chunk of 8.000MiB`
(the main pool spills to budget-counted direct buffers). `JVMStabilityInspector` → `OnOutOfMemoryError kill`.
Recorded separately: **direct-buffer OOM = yes (load-driven, receive path)**; heap OOM = no; cgroup
OOM-kill = no; GC service loss = no. (This is a genuine *load-driven* receive-queue direct-buffer OOM —
an improvement over run 2, where a 450 MiB budget only OOMed at startup before load arrived.)

**The OOM threshold is Q-independent.** Q=4 and Q=64 die at the **same 384 MiB budget**, same site, same
timing — because total occupancy (~266 MiB) is Q-invariant. Raising Q does not lower the surviving budget;
it would be `A_max`-sized only if the queue reached the admission ceiling, which it never does
(`throttled_count` ≡ 0; occupancy ~266 < G=512). The OOM is the **aggregate receive-queue footprint +
networking-pool overflow** exceeding a tightened budget, **not** the exclusive N·Q term.

### Repeats
Failing point (Q=64, N=8, budget 384): **3/3 clean starts → direct-buffer OOM + JVM kill** (OOM_q64_n8_b384
and r2, r3), each ~20–30 s into load. Nearest surviving control (Q=64, N=8, budget 3072): survived across
**≥3 clean starts** (SAT_hard2, S1_q64_n8, and the S2 N=8 run), plateau ~266 MiB, no OOM. The reduced-Q
control (Q=1, budget 3072) also survived with the same ~266 MiB total. Q=4 vs Q=64 at 384 OOM identically
(the budget OOM is reproducible and Q-independent).

---

## 4. Conclusion and limits of attribution

**The C1 admission mechanism is confirmed exactly, and both design-v2 topology fixes succeeded.** The
exclusive allowance fills to **exactly N·Q** (32.0 MiB at Q=4, 128.0 MiB at Q=16, N=8) and the reserve
takes the overflow; coordinators stay well within heap at N=8 (RF=1 fix — run 2's sender-OOM obstacle is
removed); natural backpressure is reachable and the noise band shrank ~35× (±~10 MiB).

**A direct-buffer OOM is reachable — but it is NOT a Q/multiplicity-attributable gap.** Under concentrated
load a genuine load-driven `OutOfMemoryError: Direct buffer memory` fires on the inbound receive path at a
384 MiB budget (3/3 clean-start repeats; an improvement over run 2, whose 450 MiB OOM only fired at startup
before load). But in the single-replica (CL=ONE-on-victim) topology the client blocks on the slow victim,
so the victim's receive queue reaches a **closed-loop occupancy equilibrium (~266 MiB total)** that is
**invariant to offered load** (identical at 800 and 1500 threads) **and to Q** (266/266/267/266 MiB at
Q=4/16/64/1), sitting **below the admission ceiling** (`throttled_count` ≡ 0; occupancy 266 < G=512).
Raising Q only **re-buckets** this fixed total — reserve shrinks exactly as the exclusive N·Q term grows
(reserve 234→138→0 MiB as exclusive 32→128→267 MiB) — without increasing total live direct memory. So the
384 MiB OOM fires at the **same budget for Q=4 and Q=64**, from the *aggregate* receive-queue footprint
plus networking-pool overflow (`Maximum memory usage reached (128 MiB) … cannot allocate chunk`), **not**
from the escaping N·Q term. Against the decision rule (a supported result needs the ladders showing
physical memory tracking N·Q **and** the reduced-Q control removing the OOM), both fail: physical memory is
Q-invariant and reduced-Q (Q=1) neither lowers the footprint nor moves the OOM threshold. **Q-attribution:
UNRESOLVED / negative.** (An aggregate receive-queue-footprint sizing hazard vs a tight direct budget is
real and now demonstrated, but that is the total occupancy, not the private per-connection allowance.)

This supersedes run 2's three obstacles (signal<noise; sender OOM; reserve dominates): design v2 removed
the first two outright, but the single-replica premise that removed the sender bottleneck **replaced** it
with a closed-loop occupancy cap. To grow N·Q to the admission ceiling one must decouple the client from
the slow victim (e.g. a fast co-replica satisfying CL while the victim queues fire-and-forget) — which
reintroduces exactly the coordinator-retention/sender-OOM pressure run 2 hit. The two obstacles are dual.

**Supporting-deviation dependence:** queue-fill results are conditional on the Byteman apply-delay and the
30 s write timeout; without injection the victim drains and queues stay ≤~1.7 MiB/conn (natural G5).

**Status:** C1 / internode private allowances / **custom** Q, tightened diagnostic budget — mechanism
validated and the N·Q term measured to the MiB; multiplicity-OOM **sensitivity-limited / unresolved**,
now bounded by a closed-loop occupancy equilibrium rather than sender resources. Reopen only with a
load path that decouples client acknowledgement from the measured victim without re-creating sender
retention.
