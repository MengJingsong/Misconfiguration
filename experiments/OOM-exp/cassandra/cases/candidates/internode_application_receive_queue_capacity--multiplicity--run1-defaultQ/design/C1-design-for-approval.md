# C1 run design — convergence · multiplicity (DRAFT for approval)

**Case:** internode **exclusive per-connection receive queue** × active peers, default capacities.
**Direction/sub-direction:** convergence · multiplicity. **Capacity regime:** default (Q, E, G all shipped
defaults). **Budget regime:** deliberately tightened diagnostic budget on the victim.
**Pinned source:** cassandra-5.0.9 (`b5f2a54210`). **Date:** 2026-11-09.

---

## 1. Mechanism and protection map (from the C1 audit)

Per-message inbound admission on the victim, `AbstractMessageHandler.acquireCapacity`
(`AbstractMessageHandler.java:411–459`):

1. If `queueSize + bytes ≤ queueCapacity` (Q) → admit against the connection's **exclusive** permits,
   touching **neither reserve** (`:419–423`). Doc: "every connection has 4MiB of exclusive permits
   before needing the per-endpoint and global reserves" (`InboundMessageHandler.java:63–64`).
2. Only overflow beyond Q is charged to **global** reserve first (`:428`), then **endpoint** (`:431`).
   Because global gates endpoint, `Σ_peers endpoint.using ≤ global.using ≤ G` — **the per-peer reserve
   cannot converge past G** (proven negative).
3. **The multiplicity gap is the exclusive queue.** It has **no process-global byte cap**:

   **Admitted in-flight ceiling = G + Σ_connections Q = 512 MiB + N·k·4 MiB**

   where N = active peers, k = active connection types (1 for a pure small- *or* large-message flood).
   Only the `N·k·Q` term escapes every aggregate counter. Physical peak ≈ baseline + inflation × admitted;
   inflation ≈ **1.4–1.5× off-heap** for LARGE (>64 KiB) frames, higher and verb-dependent on-heap for
   SMALL (≤64 KiB) deserialized mutations.

**Defaults (verified `Config.java:256–261`):** Q = 4 MiB (per connection, exclusive), E = 128 MiB
(per peer), G = 512 MiB (process-global). Large/small split threshold ≈ 64 KiB (`CassandraRelevantProperties.java:388`).

**Critical realism constraint:** exclusive queues fill **only under a backpressured victim** — permits
release only after the verb handler runs on the Stage (`InboundMessageHandler.java:66`). The victim must
be a naturally slow consumer (saturated MutationStage), or an artificial hold is declared as the intervention.

---

## 2. Topology

One ring, all on LAN `10.10.1.0/24` (internode port restricted to the ring; clocks are NTP-synced):

- **Victim:** apt140 / node0 / 10.10.1.1 — one Cassandra instance, **budget-bounded and cgroup-isolated**.
- **Peer hosts:** apt179 (10.10.1.2), apt138 (10.10.1.3), apt190 (10.10.1.4), apt149 (10.10.1.5) —
  each runs **multiple small Cassandra instances** (distinct identities), unbounded-but-small, as the
  peers. Target up to **8 instances/host → 32 peers**.
- **Peer identity:** each peer instance binds a **distinct LAN IP alias** (`ip addr add 10.10.1.<host>.<i>`
  style, e.g. secondary `/24` addresses) at the standard storage port 7000, so each is a distinct
  `InetAddressAndPort` on the victim. (Avoids same-IP/port ambiguity; matches the if-check loopback-alias
  precedent.) Native/JMX ports offset per instance.
- **Load generator:** `cassandra-stress` (built on every peer host) driven against the peer instances'
  native ports, so **every peer coordinates writes** that replicate to the victim.

## 3. How peers load the victim

Keyspace with **SimpleStrategy RF = (N+1)** (every node, victim included, replicates everything), so a
write coordinated at **any** peer sends a mutation to the victim over a distinct internode connection →
N distinct `InboundMessageHandlers` on the victim, each with its own 4 MiB exclusive queue. Two message-size
arms select the budget that OOMs:

- **Arm D (direct-memory):** mutations **> 64 KiB** → LARGE connections → off-heap frame buffers.
  Victim bounded by **`-XX:MaxDirectMemorySize`**. Expected failure: `OutOfMemoryError: Direct buffer memory`.
- **Arm H (heap):** mutations **≤ 64 KiB** → SMALL connections → on-heap deserialized mutations + queue.
  Victim bounded by **`-Xmx`**. Expected failure: Java heap `OutOfMemoryError`.

Run **Arm D first** (cleaner, measured ~1.5× inflation); Arm H as the second arm.

**Backpressure (natural):** victim `concurrent_writes: 2`, commitlog+data on the spinning RAID5 disk,
large mutations — so MutationStage cannot drain as fast as 32 peers send. Calibration gate: confirm each
peer's `queueSize` plateaus at ~Q **without** code injection; if unreachable naturally, declare a Byteman
apply-delay as the **intervention** and reproduce the OOM on the unmodified build.

## 4. Budget sizing (calibrated on the victim, then frozen)

Illustrative (Arm D, k=1): admitted ≈ G + N·Q; physical off-heap ≈ 1.5 × admitted.

| N peers | Admitted (MiB) | ~Direct peak (MiB) |
|---|---|---|
| 1 | 516 | ~774 |
| 8 | 544 | ~816 |
| 16 | 576 | ~864 |
| 32 | 640 | ~960 |

Set the victim `-XX:MaxDirectMemorySize` in the **margin between N=1 and N=32** (e.g. ~800 MiB) so the
**N=1 control survives** and a high-N arm OOMs — isolating multiplicity from the 512 MiB reserve. Exact
value frozen after calibration. Victim cgroup `MemoryMax` set above the JVM budget (to let the JVM's own
OOM fire first and be attributable), **`MemorySwapMax=0`** (swap off for the victim only), controller/stress
outside the victim cgroup.

## 5. Sweep, controls, repeats, intervention (per verification-protocol.md)

1. **Reachability** at modest load: confirm N distinct inbound handlers on the victim and that each
   `queueSize` reaches ~Q under backpressure (vtable `using_bytes`/`using_reserve_bytes`,
   `InboundMessageHandlers.java:321–329`); measure completed ops + actual concurrency, not just thread count.
2. **Peer sweep** N = 1, 2, 4, 8, 16, 32 (geometric), then refine the surviving/failing interval.
3. **Mandatory N=1 control** saturating G at the frozen budget → survives; high-N → OOMs. Separates
   multiplicity from reserve sizing. Matched build/budget/payload/data-state across arms.
4. **Repeats:** failing N and nearest surviving N each **≥3×** from clean starts; report n/N and peak dist.
5. **Causal intervention:** bound multiplicity (cap active peers to 1 via the internode firewall, or raise
   the budget to cover N·Q) → OOM disappears. Record throughput so a stall isn't mistaken for protection.
6. **Outcomes recorded separately:** direct-buffer OOM / heap OOM / cgroup kill (evidence: JVM error +
   heap/`VM.native_memory` + `memory.events`). GC loss ≠ OOM.

## 6. Measurement

Synchronized (epoch-ms) sampling, interval < growth window: per-connection `queueSize` and per-endpoint
reserve use; global reserve (via trace — not exposed); `ThrottledCount`; heap+GC; `jcmd VM.native_memory`
and `java.nio` direct (post-GC to separate live from allocator retention); cgroup `memory.current`/`memory.events`;
stress completion/latency. Preserve the initiating OOM if Cassandra forces another during shutdown.

## 7. Stopping budget (proposed)

- **Wall time ≤ ~3 h** for this batch.
- Peer sweep **up to 32**; if 32 doesn't converge at a sensible budget, **stop and file** the boundary
  (bigger N is a follow-up, not this batch).
- Stop at: **first clean OOM + its N=1 control + 3 repeats of each + one causal intervention.**
- No escalation after an OOM beyond the planned endpoint.

## 8. Safety

One measured experiment on the victim at a time; victim cgroup-isolated, swap off for the victim; all data,
commitlog, logs, heap dumps on **local disk** (`/mydata`, 1.7 TB) — never `/proj` (not mounted on APT anyway);
internode port restricted to the ring LAN (in-memory iptables, per environment.md §5); **every process a run
starts is stopped and verified gone afterward**; no files added to `systems/cassandra/source`.

## 9. Deliverable

One case file under `experiments/OOM-exp/cassandra/cases/candidates/ (run1-defaultQ) ` (default capacities, tightened
diagnostic budget), 4-section template, with `_INDEX.md` + `_run-log.md` rows, harness scripts, and small log
excerpts (full logs stay on the node). Commit/push on request.

---

### Open calibration gates (settled before the sweep, not after)
- G1: N instances really register as N distinct inbound handlers on the victim (IP-alias addressing works).
- G2: each peer's `queueSize` plateaus at ~Q under natural backpressure (else declare the hold as intervention).
- G3: which budget (direct vs heap) binds first at the target inflation — freeze the value from calibration.
- G4: enough `native_transport`/sender headroom that peers actually keep Q occupied (if-check hit a 128-thread cap).
