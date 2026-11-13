# C1 reopen — design v3 (DRAFT for approval): decoupled load via a fast co-replica

**Reopens again.** Run 2 (default-convergence) and reopen 2 (custom-convergence) both confirmed the
admission mechanism to the MiB but failed to produce a **Q/N-attributable** OOM, for *dual* reasons:

- **Run 2:** senders OOM reaching the ceiling (RF fanout → coordinator retention).
- **Reopen 2:** the RF=1/CL=ONE-on-victim fix removed sender-OOM, but the client then **blocks on the slow
  victim** → the victim's receive queue settles at a **closed-loop equilibrium (~266 MiB), BELOW the
  ceiling** (`throttled_count ≡ 0`). Raising Q only re-buckets reserve→exclusive; total is Q-invariant.

**v3's single job:** make the victim's receive queue actually reach its ceiling (`throttled_count > 0`,
occupancy ≈ **G + N·Q**) so that raising Q/N grows *total* live memory — WITHOUT re-creating sender-OOM.

**This is a falsifiable make-or-break premise** (gate G3 below). If the victim still won't saturate, v3 is
the third dual obstacle and we **close C1** as a thoroughly bounded negative.

## The idea: decouple the client's ack from the slow victim

Add **one fast co-replica** to the replica set and keep **CL=ONE**. Every write replicates to BOTH the
victim and the fast co-replica; the client's ack comes from whichever replica answers first — the **fast**
one — so the client **never blocks on the victim** and submits at the fast replica's (high) rate. The
coordinator sends each mutation to the victim too, at that high rate; the slow victim is offered far more
than it can drain → its receive queue **floods to the ceiling** → throttle fires. The coordinator's excess
to the victim backs up in its *outbound* queue and **expires/drops** (bounded coordinator memory), so
senders don't OOM. This is the open-loop flood reopen 2 lacked.

Realism: this models a **single degraded replica in a healthy cluster taking writes at line rate** — a real
operational scenario. The victim's slowness is the disclosed intervention (Byteman apply-delay /
`concurrent_writes=2`), the rest is ordinary write + hint/drop behavior.

## Topology (5 hosts)

- **Victim:** apt140 / 10.10.1.1, dc=v, **slow** (Byteman 100 ms `MutationVerbHandler.doVerb` +
  `concurrent_writes=2`), budget-bounded `-XX:MaxDirectMemorySize`, cgroup-isolated, swap off.
- **Fast co-replica:** a dedicated instance on apt179 / dc=f, **normal/fast** apply, ample heap — must
  sustain the full client write rate (it satisfies CL for every write).
- **Coordinators:** N coordinator-only instances (dc=c, no replica, small heap) across apt138/190/149 (and
  spare apt179 capacity), distinct LAN IP aliases, explicit initial_token.
- **Keyspace:** `NetworkTopologyStrategy {'v':1,'f':1}` (RF=2: victim + fast), **CL=ONE**. GossipingPropertyFileSnitch,
  per-node rackdc. LARGE (>64 KiB, e.g. 1 MiB) mutations → off-heap frames. Fixed aggregate offered load.

## Calibration gates (G3 is decisive — run it before the sweep)

- **G1** every key's replicas = {victim, fast} (`getendpoints`); coordinators coordinate; victim sees N
  inbound handlers; quantify background traffic.
- **G2 (client decoupled):** with the victim slow, client throughput stays high (≈ fast-replica rate), i.e.
  the client does **not** block on the victim. Measure completed ops vs victim drain rate.
- **G3 (THE premise — victim reaches the ceiling):** at N=8, Q=4, confirm **`throttled_count > 0`** and the
  victim's receive-queue occupancy ≈ **G + N·Q** (each exclusive queue full at ~Q, reserve ≈ G) — i.e.
  occupancy is at the ceiling, NOT the ~266 MiB reopen-2 equilibrium. **If `throttled_count` stays 0 /
  occupancy stays below the ceiling, STOP and file negative — C1 is closed.**
- **G4 (senders survive):** coordinators drop/expire to the slow victim and stay within heap (no sender
  OOM); the fast co-replica keeps up without OOM.
- **G5** freeze `-XX:MaxDirectMemorySize` so low-Q/low-N survives and high-Q/high-N OOMs; cgroup MemoryMax above it.

## Arms (only meaningful once G3 passes)

- **S2 (multiplicity, the headline):** fix Q, sweep **N = 1/4/8** → ceiling = G + N·Q grows with N → direct-buffer
  OOM at high N, survives low N. **This is the multiplicity attribution run 2/reopen 2 couldn't get.**
- **S1 (allowance):** fix N=8, sweep **Q = 4/16/64** → ceiling grows with Q → total live memory now tracks
  N·Q (the discriminator vs reopen 2's Q-invariant 266 MiB) → OOM at high Q.
- **Default-Q boundary** retained; **reduced-Q (→1 MiB) causal control** at the failing point → OOM must disappear.
- **≥3 clean-start repeats** of the failing and nearest-surviving arms.

## Decision rule (unchanged, strict)

Supported C1 positive requires ALL: G saturated at the reference; **`throttled_count > 0` at the ceiling**;
total live direct memory **tracks N·Q** across S1 and S2; a reproducible direct-buffer OOM while local
admission/reserve contracts still hold; and reduced-Q removes it. If total stays Q-invariant or the victim
won't saturate → **negative, C1 closed** (three bounded obstacles: sender-OOM, closed-loop equilibrium, and
whatever v3 hits). An OOM dominated by the fast replica, coordinators, or background → unresolved.

## Measurement / safety / budget / deliverable

As reopen 2: synchronized ~250 ms sums; per-handler queueSize + `throttled_count` (the key new signal);
per-endpoint + global reserve; jcmd VM.native_memory (NMT) + java.nio direct (post-GC); cgroup memory.events;
coordinator + fast-replica heap/pending; stress offered/accepted/completed. One measured victim; victim
cgroup-isolated + swap off; data/logs/dumps on /mydata, never /proj; internode port firewalled to the ring;
no writes to systems/cassandra/source; **all processes/aliases/rules/linger removed and verified on success or
abort**. Wall ≤ ~3 h after ready; per-workload ~5 min cap. File under
`cases/custom-convergence/` as a dated **reopen-2 amendment / run 3** of the same case file (or a sibling
`--run3` file), cross-linking runs; update `_INDEX` + custom-convergence `_batch-log`. Do NOT commit/push.

### Honest risks
- G3 may fail: message **expiry** might drain the victim's queue enough to hold it just below the ceiling even
  under open-loop flood, or the outbound drop/backpressure may cap arrivals at the victim's drain rate (a
  third dual obstacle). That's a legitimate close-out, not a failure to engineer around further.
- The fast co-replica must genuinely keep up; if it can't, the client re-couples to the victim (reopen-2 redux).
- Still depends on the Byteman delay (disclosed) — natural victim slowness isn't assumed.
