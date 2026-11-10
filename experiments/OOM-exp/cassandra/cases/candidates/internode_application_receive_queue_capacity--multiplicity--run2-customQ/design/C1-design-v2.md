# C1 reopen — design v2 (DRAFT for approval)

**Reopens** the run-2 sensitivity-limit result
(`cases/candidates/internode_application_receive_queue_capacity--multiplicity--run1-defaultQ.md`).
Mechanism is already confirmed to the byte (A_max(4)=528, per-conn=Q+E, Σreserve=G). v2 does **not**
re-litigate that — it answers the reachability question run 2 left open: **can multiplied exclusive
allowances drive the victim to OOM, and where is the boundary.**

**Direction/sub-direction:** convergence · multiplicity. **Primary capacity regime:** CUSTOM (Q raised) —
files under `cases/candidates/`, cross-linking the run-2 default-Q negative.
**Budget regime:** tightened diagnostic direct-memory budget. **Pinned source:** cassandra-5.0.9.

---

## 1. Why v2 changes the question (from run 2's three failures)

| Run-2 failure | Root cause | v2 fix |
|---|---|---|
| (a) signal < noise | escaping `N·Q` ≤128 MiB ≪ invariant G=512 + ±350 noise | **Raise Q** (operator knob) so `N·Q` dominates G and noise → attributable OOM |
| (b) senders OOM before high N | RF-fanout made coordinators retain mutations (ring 33→9) | **Victim-owns-all, RF=1, coordinator-only peers** → senders retain ~one in-flight mutation |
| (c) backpressure unreachable (queues peak 0.4 MiB) | load spread across RF=33 | **Concentrate all load on the one victim** → retry natural saturation; Byteman only as declared fallback |

**At default Q, C1 is effectively negative** (run 2). v2's value: demonstrate the convergence mechanism
*does* OOM once the private allowance is sized up — a reportable **configuration-sizing hazard** on
`internode_application_receive_queue_capacity` — with default Q retained as the documented boundary.

## 2. Topology (fixes the sender bottleneck)

- **Victim:** apt140 / 10.10.1.1, single instance, datacenter `v`, rack `r1`. Budget-bounded
  (`-XX:MaxDirectMemorySize`), cgroup `MemoryMax` above the JVM budget, `MemorySwapMax=0`, controller/stress
  outside the cgroup. `GossipingPropertyFileSnitch`.
- **Coordinator peers:** up to 8 instances/host on apt179/138/190/149 (10.10.1.2–.5) → **32 peers**, each a
  distinct LAN IP alias, datacenter `c`, **small heap** (e.g. `-Xmx1G`). They own **no replica** (see §3), so
  they forward one mutation to the victim and retain only bounded in-flight work.
- **Load:** `cassandra-stress` against the N selected coordinators' native ports, fixed aggregate offered
  load across N, bounded per-coordinator outstanding (keeps coordinator heap small).

## 3. How all data lands on the victim (RF=1 → victim)

Keyspace with **`NetworkTopologyStrategy, {v:1}`** (replica only in the victim's datacenter). Every write,
whichever coordinator in dc `c` receives it, has its single replica = the victim → each coordinator opens a
distinct internode connection to the victim and forwards the mutation. **CL=ONE** (the one replica, the
victim, must ack). Result: N distinct inbound handlers on the victim, all write load concentrated there,
coordinators near-stateless. (Per-node `cassandra-rackdc.properties`: victim `dc=v`; peers `dc=c`.)

## 4. Allocation domain and arms

LARGE internode mutations (>64 KiB) → off-heap frame buffers → bounded by `-XX:MaxDirectMemorySize`
(Arm D). k=1 (LARGE connection type only). Admitted model at the victim: **A = N·Q + min(G, N·E)**,
E=128, G=512 MiB defaults.

**Two sweeps isolate the two axes; reserve stays pinned at G throughout (N≥4), so only the exclusive term moves:**

| Sweep | Fixed | Varied | Isolates | Predicted admitted (MiB) |
|---|---|---|---|---|
| **S1 (allowance)** | N=8 (G saturated) | **Q = 4 / 16 / 64 MiB** | the exclusive allowance size | 544 / 640 / 1024 |
| **S2 (multiplicity)** | Q=64 MiB | **N = 1 / 4 / 8** | peer count | 192 / 768 / 1024 |

- **Reference (survives):** the low end of each sweep at the frozen budget (e.g. S1 Q=4 → 544; S2 N=1 → 192),
  with G demonstrably saturated where N≥4.
- **Failing arm:** the high end (Q=64,N=8 → ~1024 MiB admitted) → **direct-buffer OOM**, attributable to N·Q.
- **Default-Q boundary:** Q=4 across N (run-2 result, one confirmatory arm) → no OOM (negative boundary).
- **Reduced-Q causal control:** at the failing (Q=64, N=8) point, drop **Q→1 MiB**, same E/G/budget/offered
  load → OOM should disappear (multiplicity held constant; isolates the exclusive allowance). Report whether
  it merely stops useful work.

Budget: freeze `-XX:MaxDirectMemorySize` in calibration (seed: baseline networking pool ~450 MiB measured in
run 2 + admitted frame bytes) so the reference survives and the failing arm OOMs. cgroup `MemoryMax` above it.

## 5. Backpressure

All load concentrated on the victim + `concurrent_writes:2` (disclosed supporting deviation) + data/commitlog
on the spinning disk + large mutations. **Gate:** confirm the victim's inbound queues fill (each ≥~Q) under
*natural* saturation now that load isn't fanned out. If still unreachable, the frozen **Byteman 100 ms
`MutationVerbHandler.doVerb` apply-delay** is the declared intervention (save the rule, label arms conditional,
attempt reproduction without it).

## 6. Calibration gates (before freezing)

G1 ring healthy; dc/rack correct; the keyspace's only replica is the victim; selected coordinators actually
coordinate; victim sees N data-bearing inbound handlers; quantify background/urgent/replica-response traffic.
G2 coordinators stay within heap under offered load (confirm the RF=1 fix — no sender OOM) at N=8.
G3 at N=8, Q=4: G saturated, each inbound queue ~Q; measure the ±noise band (should shrink vs run 2's ±350).
G4 freeze the direct budget so S1-low / S2-low survive and the Q=64,N=8 arm OOMs with margin > noise.
G5 confirm natural backpressure or declare Byteman.

## 7. Controls, repeats, outcomes

N≥4 reference with G saturated; S1 and S2 ladders (predicted vs observed admitted + physical); **≥3
clean-start repeats** of the failing arm and nearest surviving arm (report n/N, peak distribution);
reduced-Q control ×3 if a causal success is claimed. Record separately: direct-buffer OOM / heap OOM /
cgroup kill / GC loss / protective throttling. Preserve the initiating OOM. **Decision rule:** a supported
result needs the reference surviving (G saturated) + the ladders showing physical memory tracking N·Q +
a reproducible OOM while local admission/reserve rules still hold + the reduced-Q control removing it. A
failure dominated by reserve, fanout, sender limits or background allocations stays unresolved.

## 8. Measurement

Synchronized (~250 ms) sums, not added independent peaks: per-handler queueSize/type/peer; per-endpoint
reserve; instrumented global reserve; ThrottledCount; heap+GC; `jcmd VM.native_memory` (NMT at startup) +
java.nio direct (post-GC); cgroup `memory.current`/`memory.events`; stress offered/accepted/completed/latency;
coordinator heap + pending. RSS alone ≠ leak; counter drift ≠ physical growth.

## 9. Safety & budget

One measured victim at a time; victim cgroup-isolated, swap off (victim only); all data/logs/dumps on
**/mydata** (local), never /proj; internode port 7000 firewalled to the ring (undo after); no writes into
`systems/cassandra/source`; **every process/alias/rule removed and verified on success or abort**. Wall
budget **≤ ~3 h** after the ring is ready; per-workload ~5 min cap; stop at: both ladders + first clean
OOM + its surviving reference + 3 repeats each + the reduced-Q control.

## 10. Deliverable

New case `cases/candidates/internode_application_receive_queue_capacity--multiplicity--run2-customQ.md`
(4-section), cross-linking the run-2 default-Q negative; harness + small excerpts in a sibling
folder (full logs on /mydata); rows in `_INDEX.md` and the `_run-log.md`. Reuse
the run-2 harness (peer-ctl/victim-ctl/arm/analyze/mutation-delay.btm) with the snitch/dc + per-arm Q edits.
Do **not** commit/push — leave in the working tree for review.

### Open questions
- Does RF=1-to-victim actually keep coordinators under heap at N=8 (the whole point of the topology change)?
- Is natural backpressure now reachable, or is Byteman still required?
- Does the ±noise band shrink enough (load concentrated) for the ladder to read cleanly below the raised signal?
