# B6 — internode queues charge on-wire bytes; tiny-cell mutations hold ≈ 17–20× that on heap

**Direction:** bypass · accounting mismatch (U > C while K ≤ C). **Lead source:** `flow:coordinator-write`
(traced from C1). **Regime:** default capacities. **Source:** Cassandra 5.0.9 (`b5f2a54210`), local copy
`/mydata/b6/cassandra` on `pc96`. **Runs:** 1 (2026-11-10), 2 (2026-11-10/11), 3 (2026-11-11); full
per-run records in [`history.md`](history.md). **Consolidated:** 2026-11-11.

| Condition | Status (protocol *Verification status*) |
|---|---|
| A — replica 8 GiB, 30 s storage stall, default timeouts and threads, 4 coordinators | **`verified-gap · service-loss · deployment`** |
| B — coordinator 2 GiB, slow replica (Byteman), 60 s write/native timeouts | **`reproduced-OOM · diagnostic`** (V7 unmet: tightened 2 GiB heap; amended 2026-11-11) |
| C — replica 2 GiB, slow replica (Byteman), 60 s timeouts | `candidate` (same-day positive survived; OOM timing-dependent) |

## Summary

- **Root cause:** the internode send and receive queues limit messages by **on-wire size**
  (documented), but queued writes live on the heap as Java objects. A 1000-tiny-cell write is
  10.8 KiB on the wire, ≈ 213 KiB on the coordinator heap and ≈ 181 KiB on the replica heap. The
  coordinator also keeps each sent write (`hintOnFailure`) until the replica answers, charged to no
  sender counter. A receive queue within its 528 MiB limit can therefore hold ≈ 9 GiB of heap.
- **Conclusion:** on a deployment-sized 8 GiB replica with default settings, a 30 s storage stall
  drives the heap to ≈ 99% live with ≈ 97% of two minutes in Full GC (3/3); blob writes of the same
  on-wire size never trigger a Full GC (0/3). Heap OOM is occasional there (2/8 stall/hang arms in
  run 2), so the verified outcome is **service loss**. Under diagnostic settings a 2 GiB coordinator
  **OOMs 4/4** with its send queue empty; blob 0/3.
- **Causal test:** an 8 MiB endpoint reserve removes the effect 4/4 in both A and B.
- **Interpretation:** a documented accounting unit that does not bound heap — a sizing/validation
  gap plus an uncovered after-flush retention path — not a counter defect.

## 1. Constraint, contract, protection map

| Field | Evidence |
|---|---|
| Control | Internode application queues. Send: `OutboundConnection.enqueue` charges `message.serializedSize()` (`OutboundConnection.java:330,1045–1048`) to per-link 4 MiB, endpoint 128 MiB and global 512 MiB reserves; on failure prunes expired once, then drops (`:335–345`). Receive: `AbstractMessageHandler.acquireCapacity` charges the frame size to the same three tiers; on failure the connection stops reading. |
| Contract | `cassandra.yaml`: "These limits are applied to the **on-wire size** of the message." Per destination 4 + 128 = 132 MiB; with 4 senders the receive ceiling is 4·4 + 512 = 528 MiB. |
| Allocation / ownership | Sender: `Message<Mutation>` on heap while queued; after flush the write handler keeps the `Mutation` as `hintOnFailure` (`Mutation.java:158`; `AbstractWriteResponseHandler.java:81,309`) until response or expiry, even with hints off. Receiver: small messages (< 64 KiB) are deserialized on arrival (`InboundMessageHandler.java:156`) and wait on `MutationStage`; capacity is released after processing; an expired message is dropped only when a stage thread runs it (`:408–423`). |
| Uncovered memory | Heap size ≠ on-wire size (R ≈ 19.7 coordinator / 16.7 replica for map cells, ≈ 2.2 for blobs). The sender's after-flush copy is charged to no sender counter. |
| Lifetime | Until processed or expired; deadline = min(`write_request_timeout`, `native_transport_timeout`) (`Dispatcher.java:238–245`). Blocked stage threads (storage stall) stop expiry. |
| Budget | Java heap (`-Xmx`). |

C = contract capacity on-wire; K = `internode_outbound.pending_bytes` / `internode_inbound.using_bytes`;
U = live heap (class histogram after full GC, or GC-log occupancy after Full GC).

**Labels.** A: capacities default; timeouts, threads, GC default; budget 8 GiB (deployment-sized);
storage stall by dm-delay (external fault); hints off, key/counter cache 0 (accepted documented
values); single host on loopback, `num_tokens: 1` (environment) → **deployment** (decided 2026-11-11).
B and C: Byteman 100 ms per mutation and `concurrent_writes: 2` on the replica, 60 s timeouts, 2 GiB
heap (supporting deviations) → **diagnostic**.

## 2. Verification design

Designs (each written before its readings): [`design/B6-design.md`](design/B6-design.md) (run 1),
[`design/B6-run2-design.md`](design/B6-run2-design.md), [`design/B6-run3-design.md`](design/B6-run3-design.md).

- **Topology:** one host (`pc96`), instances on loopback. Slow or stalled replica V (dc=v), fast replica
  F (dc=f, acks CL=ONE), coordinators S (run 1: one; run 2–3 condition A: four, 8 GiB each).
  `NetworkTopologyStrategy {v:1, f:1}`.
- **Payloads:** `map<int,int>` with 1000 entries vs an 11 000-byte blob, both 10.80 KiB on the wire.
- **Condition A arm** (`harness-run2/arm.sh`): Java driver load 150 s on S1–S4 (256 in flight each); at
  t = 20 s V's disk write delay := 30 s; at t = 150 s := 0; V observed 60 s more.
- **Conditions B/C arm** (`harness/arm.sh`, `harness/armx.sh`): Python client 90 s, 256 in flight;
  one instance at 2 GiB, the other at 8 GiB.
- **Intervention:** `internode_application_receive_queue_reserve_endpoint_capacity=8MiB` (A); send
  and receive endpoint reserves 8 MiB (B, C); all instances.
- **Measurement:** queue counters from `system_views` every 2–3 s; GC logs (`harness-run3/gcpeak.sh`:
  live = occupancy after Full GC; service loss = ≥ 90% of wall time in Full GC over ≥ 60 s); class
  histograms; heap dumps on OOM for positives.

## 3. Results

### 3.1 Mismatch (run 1 calibration, S and V at 8 GiB, queues full)

| Payload | On-wire / mutation | S heap / mutation | R (S) | R (V) | K at snapshot | U |
|---|---|---|---|---|---|---|
| map, 1000 entries | 10.80 KiB | 212.9 KiB | **19.7** | **16.7** | S→V 132.0 MiB = C; V←S = C | S 5.6 GiB, V 2.2 GiB |
| blob, 11 000 B | 10.80 KiB | 23.6 KiB | 2.2 | 2.2 | = C | S 0.65 GiB, V 0.29 GiB |

Replica in a condition-A spiral (run 2 probe P1): 37 217 `Mutation`s waiting ≈ 393 MiB on-wire
(< C = 528 MiB) ↔ 7.95 GiB live of 8 GiB.

### 3.2 Condition A — replica 8 GiB, storage stall, default timeouts

| Arms | n | Outcome | Live after Full GC | Full GC in window |
|---|---|---|---|---|
| map, stall (run 2 r1, r2; run 3 r3) | 3 | **service loss 3/3**, recovered | 98.7–99.3% | 96–98% of 108–126 s |
| blob, stall (run 2) | 3 | 0 Full GCs | — | — |
| map, stall, receive reserve 8 MiB (run 2 r1; run 3 r2–r4) | 4 | **survived 4/4**, 1 Full GC each, 0 client errors | 21.6–30.9% | — |
| map, no stall (run 2) | 1 | healthy | 26.9% | — |

Also observed (not part of the verified condition): 6 GiB replica, stall: service loss 3/3 and **heap
OOM 1/3**; 600 s hang at 8 GiB: JVM froze in 1/2, **heap OOM** in 1/2. Client throughput with the
reserve (308–333k writes) was not lower than without (269–305k); the four coordinators stayed ≤ 8.2%
of heap after any GC (one arm measured).

### 3.3 Condition B — coordinator 2 GiB (V 8 GiB)

| Arms | n | Outcome | Live after Full GC | S→V pending / overload |
|---|---|---|---|---|
| map (run 1 r1–r3; run 3 positive) | 4 | **heap OOM 4/4**, JVM killed; dumps kept (run 1 r1, run 3) | 98.2% (run 3) | **0 MiB** / 0 — send queue empty |
| blob (run 1) | 3 | 0/3 OOM | 35% | 132 MiB / ≈ 435k |
| map, send + receive reserves 8 MiB (run 1; run 3 r2–r4) | 4 | **survived 4/4**, 0 client errors | 69.2–75.0% (20–26 Full GCs) | 12 MiB / 50–58k |

### 3.4 Condition C — replica 2 GiB (S 8 GiB)

| Arms | n | Outcome |
|---|---|---|
| map (run 1 r1–r3, + A1) | 3 + 1 | heap OOM 3/3 (+1) |
| map (run 3 same-day positive) | 1 | **no OOM**: 98.2% live, 131 Full GCs, 57% of 83 s in Full GC, alive at end of load |
| blob (run 1) | 3 | 0/3 |
| map, reserves 8 MiB (run 1; run 3 r2–r4) | 4 | survived 4/4, no Full GC |

### 3.5 Default timeouts at the coordinator side (run 1)

At 2 s / 12 s deadlines the queues hold only ≈ 2–3 s of arrivals; filling 132 MiB needs ≥ 66 MiB/s per
destination (≈ 6k map writes/s); this host reached ≈ 2.3k/s. Not established, not shown safe.

Raw logs: `/mydata/b6/runs/` (run 1, run 3 `R3A_*`) and `/mydata/b6/runs2/` (run 2, run 3 `R3B_*`) on
`pc96`; excerpts in [`logs/`](logs/), [`logs-run2/`](logs-run2/), [`logs-run3/`](logs-run3/).

## 4. Conclusion and limits

**Promotion rule** (V6–V7 added by the protocol amendment of 2026-11-11, *Defaults and acceptable budget*; condition B moved from `verified-OOM` to `reproduced-OOM` on that date, evidence unchanged):

| Condition | V1 repetition | V2 matched control | V3 U apart from K | V4 intervention | V5 initiating failure | V6 default constraints | V7 acceptable budget | Status |
|---|---|---|---|---|---|---|---|---|
| A | 3/3 service loss | blob 0/3 | P1 histogram; GC-log live | 4/4 | GC logs | yes | 8 GiB heap (argued deployment-sized; researcher review pending) | **verified-gap · service-loss · deployment** |
| B | 4/4 heap OOM | blob 0/3 | histograms (run 1) | 4/4 | `ReportJavaOutOfMemory` + 2 dumps | yes | **no** (2 GiB, tightened) | **reproduced-OOM · diagnostic** |
| C | 3/4 (same-day survived) | blob 0/3 | histograms | 4/4 | run 1 dump | yes | no (2 GiB) | candidate |

**Interpretation:** the limits are documented as on-wire bytes, so the gap is a documented unit that
does not bound heap — sizing a heap from `N·3·(send+receive capacity)` plus reserves can be wrong by
≈ 20× for collection-heavy writes — plus the coordinator's after-flush retention that no sender
counter covers. Not an implementation defect of the counters. The intervention shows the charged
ceiling, not the traffic volume, decides the outcome.

**Limits:**
- The reserve protects by shedding: in B ≈ 83% of writes to the slow replica were dropped by the
  coordinator, invisible to a CL=ONE client. In A the receive side throttled only 4–6 times per sender.
- The capped 2 GiB coordinator still ran at 69–75% live with a Full GC every ≈ 4 s.
- In A, heap OOM is occasional, not deterministic; outcome depends on stall shape (30 s delay vs hang).
- Single host, loopback; coordinators in A measured in one arm; coordinator side at default timeouts
  not established (client rate).

**Next:** JIRA history check (CASSANDRA-15066 introduced these limits) before any upstream report;
stall-length sweep (5/15/60 s); coordinator with ≥ 2 slow replicas at 8 GiB; condition C with a longer
load to settle its OOM timing.
