# B6 — run history (internode queue accounting mismatch)

The per-run case files of B6, kept verbatim after the case was verified and consolidated into
[`internode_application_queue_capacity--accounting-mismatch.md`](internode_application_queue_capacity--accounting-mismatch.md)
(filing rule: protocol *Case evidence and batch status*, amended 2026-11-11). Only two mechanical
changes: every heading is demoted one level, and links between the run files point to the
anchors below. Relative links to `design/`, `harness*/` and `logs*/` are unchanged.

| Run | Original file |
|---|---|
| [Run 1 — 2026-11-10: slow replica (Byteman), 60 s timeouts, 2 GiB heap](#run-1) | `internode_application_queue_capacity--accounting-mismatch--run1.md` |
| [Run 2 — 2026-11-10/11: replica disk stall, default timeouts, 8/6 GiB](#run-2) | `internode_application_queue_capacity--accounting-mismatch--run2-diskstall.md` |
| [Run 3 — 2026-11-11: reserve intervention ×3 and same-day positives](#run-3) | `internode_application_queue_capacity--accounting-mismatch--run3-intervention.md` |
| [Run 4 — 2026-11-11/12: coordinator, two slow replicas, budget search](#run-4) | written directly here (no separate run file) |

---

<a id="run-1"></a>

# Run 1 — 2026-11-10: slow replica (Byteman), 60 s timeouts, 2 GiB heap

## B6 run 1 — internode queues charge on-wire bytes; tiny-cell mutations hold ~17–20× that on heap

**Direction / sub-direction:** bypass · accounting mismatch (protocol *Classification by measurement*:
U > C while the control's counter K ≤ C). **Allocation domains:** (1) coordinator heap holding
`Mutation`s bound for a slow replica — in the send queue and, after flush, in the write callback;
(2) replica heap holding deserialized `Mutation`s waiting on `MutationStage` while charged to the
receive queue. **Capacity regime:** default internode queue capacities (4 MiB / 128 MiB / 512 MiB,
send and receive). **Budget regime:** deliberately tightened diagnostic heap (`-Xmx 2G`) on the
measured instance; others ample. **Pinned source:** cassandra-5.0.9 (`b5f2a54210`), local copy
`/mydata/b6/cassandra` (repository `8b83bbfb`). **Date:** 2026-11-10.
**Design:** [`design/B6-design.md`](design/B6-design.md) (amendments in §2).

**Verdict: bypass (accounting mismatch) confirmed on both sides; heap OOM reproduced with
supporting deviations.** A mutation of 1000 tiny map cells is 10.80 KiB on the wire but
**213 KiB on the coordinator heap and 181 KiB on the replica heap (R ≈ 19.7× / 16.7×)**; a blob
mutation of the same on-wire size is 23.6 KiB on both (R ≈ 2.2×). With every queue counter at or
below its 132 MiB contract, live heap reached **5.6 GiB on the coordinator and 2.2 GiB on the
replica**. At a 2 GiB heap: coordinator **3/3 heap OOM** (map) vs **0/3** (blob); replica **3/3
heap OOM** (+1 unplanned in A1) vs **0/3**. Shrinking both endpoint reserves to 8 MiB removed both
OOMs (n=1 each). The coordinator OOMs happened with its **send queue empty** (K = 0): the heap was
filled by mutations already flushed and held by the write callback, which no sender counter
charges. **Conditional on** a slow replica (Byteman), 60 s write and native-transport timeouts,
hints off and a tightened heap; at **default timeouts** no OOM was reached at the client rate this
single host could generate (≈ 2.3k inserts/s ≈ 25 MiB/s on-wire; ≥ 66 MiB/s is needed) —
unresolved, not negative.

### Summary

- **Root cause:** internode send and receive queues limit messages by **on-wire size**, but queued
  writes live on the heap as Java objects. A 1000-tiny-cell write is 10.8 KiB on the wire, ≈ 213 KiB on
  the coordinator heap and ≈ 181 KiB on the replica heap (≈ 20× / 17×). The coordinator also keeps each
  sent write until the replica answers, which no sender counter charges.
- **Conclusion:** with all counters ≤ 132 MiB, a 2 GiB coordinator and a 2 GiB slow replica each ran
  out of heap 3/3; matched blob writes 0/3; endpoint reserves of 8 MiB removed both OOMs.
- **Conditional:** needed a Byteman-slowed replica and 60 s write/native timeouts; at default timeouts
  the client could not fill the queues (unresolved). Run 2 removes these deviations.
- **Interpretation:** documented behaviour (limits are on-wire bytes) → sizing gap, not a code bug.

---

### 1. Constraint, contract, protection map

| Field | Evidence |
|---|---|
| Control | Internode application queues. Send: `OutboundConnection.enqueue` charges `message.serializedSize()` (`OutboundConnection.java:330,1045–1048`) to per-link 4 MiB, then endpoint 128 MiB + global 512 MiB reserves; on failure prunes expired once, then **drops** (`:335–345`, `onOverloaded :456`). Receive: `AbstractMessageHandler.acquireCapacity` charges the frame size to the same three tiers; on failure the connection stops reading (back-pressure). |
| Contract | `cassandra.yaml`: "These limits are applied to the **on-wire size** of the message." Capacity per destination per link type: 4 + 128 = **132 MiB**. |
| Allocation / ownership | Sender: `Message<Mutation>` objects on heap while queued (serialized only at flush). After flush, the write handler keeps the `Mutation` as `hintOnFailure` (`Mutation.hintOnFailure()` returns `this`, `Mutation.java:158`; `AbstractWriteResponseHandler.java:81,309`) until the replica answers or the callback expires — even with hints disabled. Receiver: small messages are deserialized, then wait on `MutationStage` as heap objects; receive capacity is released only after processing. |
| Uncovered memory | Heap size of a `Mutation` is not its on-wire size. After flush, the sender's copy is charged to **no** sender counter (only to the replica's receive queue, in another JVM). |
| Lifetime | Until processed or expired. Expiry deadline = min(`write_request_timeout`, `native_transport_timeout` from client admission) (`Dispatcher.RequestTime.computeDeadline`, `Dispatcher.java:238–245`) — found during A0 (§2). |
| Budget | Java heap (`-Xmx`). |

C = 132 MiB on-wire per destination (one link type: these mutations are < 64 KiB → SMALL).
K = `internode_outbound.pending_bytes` (sender) / `internode_inbound.using_bytes` (receiver).
U = live heap from `jcmd GC.class_histogram` (full GC) minus the idle baseline.

### 2. Executed design and amendments (2026-11-10)

Single host `node0.jason92-325405` (32 cores, 125 GiB, Ubuntu 22.04, OpenJDK 11.0.33, Ant 1.10.12),
three instances on loopback, `GossipingPropertyFileSnitch`, one token each, hints off, key/counter
cache 0, keyspace `NetworkTopologyStrategy {v:1, f:1}`, CL=ONE:

| Instance | Address | Role | Notes |
|---|---|---|---|
| V | 127.0.0.11 dc=v | slow replica | Byteman 100 ms at `MutationVerbHandler.doVerb` entry, `concurrent_writes: 2` (drains ≈ 20 mutations/s) |
| F | 127.0.0.12 dc=f | fast replica, 8 GiB | acks CL=ONE so the client never waits on V |
| S | 127.0.0.13 dc=c | coordinator; client talks only to S | owns no replica |

Client: Python driver bundled with cqlsh, async prepared inserts, 256 in flight, to S only.
- **map (tiny cells):** `t_map(pk int PRIMARY KEY, m map<int,int>)`, 1000 entries per insert →
  **10.80 KiB on-wire** per mutation (`pending_bytes / pending_count`).
- **blob (control):** `t_blob(pk int PRIMARY KEY, b blob)`, 11000-byte blob → **10.80 KiB on-wire**
  (matched to 0.1%).

Harness: `harness/` (`ctl.sh`, `ring-up.sh`, `load.py`, `sample.sh`, `snap.sh`, `arm.sh`, `armx.sh`,
`analyze.sh`, `mutation-delay.btm`, `batch1.sh`, `batch2.sh`). Raw data `/mydata/b6/runs/<arm>/`.

**Configuration audit**

| Change | Class | Value |
|---|---|---|
| internode send/receive queue capacities | tested capacity (default) | 4 / 128 / 512 MiB (intervention arm: endpoint reserves 8 MiB) |
| measured instance `-Xmx` | budget (tightened diagnostic) | 2 GiB; 8 GiB in calibration |
| `write_request_timeout` | supporting deviation | 60 s (default 2 s); default in D arms |
| `native_transport_timeout` | supporting deviation | 60 s (default 12 s); default in D arms |
| V Byteman delay, `concurrent_writes: 2` | supporting deviation (intervention) | 100 ms |
| `hinted_handoff_enabled` | supporting deviation | false |
| addresses, snitch, dc, tokens, caches 0 | environment | — |

**Amendments.**
- *A0 (dropped):* with only `write_request_timeout` raised, V expired 77% of messages at a mean
  12.5 s cross-node latency. In 5.0 the message deadline is also capped by `native_transport_timeout`
  (12 s) from client admission; raised to 60 s on all instances.
- *A1:* the slow replica V (then 2 GiB heap) **died of heap OOM** while its receive queue held
  ≤ 129 MB from S (`throttled_count` 0) and `MutationStage` pending was 11 746. This receive-side
  instance of the same mismatch was not in the design; it is added as domain (2) with its own arms.
- `jstat` cannot attach (Cassandra sets `-XX:+PerfDisableSharedMem`); heap is sampled with
  `jcmd GC.heap_info` (no forced GC) and measured with `GC.class_histogram` (forced full GC).

---

### 3. Results

Excerpts: [`logs/calibration-histograms.txt`](logs/calibration-histograms.txt),
[`logs/arm-outcomes.txt`](logs/arm-outcomes.txt), [`logs/oom-evidence.txt`](logs/oom-evidence.txt).
Heap dumps (2.9 GB each, A1 replica and `B_S2g_map_r1` coordinator) stay on node0 under
`/mydata/b6/runs/`.

#### 3.1 Calibration — R at full queues (A2 map, A3 blob; S and V at 8 GiB)

Snapshot 55 s into a 75 s load; histograms force a full GC (live objects only).

| Payload | On-wire / mutation | S live `Mutation`s | S Δheap | S heap / mutation | **R (S)** | V live `Mutation`s | V Δheap | **R (V)** |
|---|---|---|---|---|---|---|---|---|
| map, 1000 entries | 10.80 KiB | 27 720 | 5 763 MiB | 212.9 KiB | **19.7** | 12 513 | 2 211 MiB | **16.7** |
| blob, 11 000 B | 10.80 KiB | 28 165 | 648 MiB | 23.6 KiB | **2.2** | 12 519 | 289 MiB | **2.2** |

Counters at the map snapshot: S→V `pending_bytes` 138 407 744 B = **132.0 MiB = C**, 12 512 messages,
`overload_count` 11 278 (dropping); V←S `using_bytes` 138 406 293 B = **C**, `throttled_count` 553;
V `MutationStage` pending 12 511. So **K = C on both sides while U = 5.6 GiB (S) and 2.2 GiB (V)**.

Where the coordinator's 27 720 mutations are: 12 502 are in queued `Message`s; the other ≈ 15 200 were
already flushed (sitting in TCP buffers and V's receive queue) and are reachable only from the write
handler's `hintOnFailure`. Heap per tiny cell on S ≈ 212 B (two `HeapByteBuffer`s 48 B each, two
`byte[]` ≈ 30 B each, `BufferCell` 40 B, `CellPath` 16 B) against ≈ 11 B on the wire. On V the cells are
`ArrayCell`s (deserialized form), ≈ 181 B each.

#### 3.2 Boundary — one instance at a 2 GiB heap, the other at 8 GiB (`arm.sh`, clean starts)

| Arm | Payload | Budgeted | Outcome | Queue counters near failure / at peak |
|---|---|---|---|---|
| `B_S2g_map_r1–r3` | map | S 2 GiB | **3/3 S heap OOM** (`ReportJavaOutOfMemory`, `OnOutOfMemoryError` kill; dump 2.85 GB in r1) | **S→V pending 0**, sent 7.7–9.4k; V←S using 95–97 MiB, throttled 0 |
| `B_S2g_blob_r1–r3` | blob | S 2 GiB | 0/3 (≈ 490k inserts each, 0 errors) | S→V pending **132.0 MiB**, overload 431–441k; V←S **132.0 MiB**, throttled ≈ 1.2k |
| `B_V2g_map_r1–r3` (+ A1) | map | V 2 GiB | **3/3 V heap OOM** (+ A1: dump 2.86 GB) | V←S using ≤ 122 MiB, throttled 0 at last sample |
| `B_V2g_blob_r1–r3` | blob | V 2 GiB | 0/3 | V←S **132.0 MiB**, throttled ≈ 1.2k |

The blob controls fill both queues to the contract and keep dropping for the whole run, yet stay
alive: measured live ≈ 715 MiB (S, 35% of 2 GiB) and ≈ 366 MiB (V, 18%). The map arms die **before**
any counter reaches C. Client throughput is not matched (map ≈ 700 inserts/s, blob ≈ 5.4k/s, both
Python-bound): the control offers ~7× **more** on-wire bytes and still survives.

#### 3.3 Intervention — endpoint reserves 8 MiB on send and receive (`armx.sh`, 60 s timeouts)

| Arm | Outcome | Counters |
|---|---|---|
| `C_S2g_map_rsv8m` | S alive (66k inserts, 0 errors) | S→V pending **12.0 MiB** (= 4 + 8), overload 55k; V←S 12.0 MiB, throttled 1118 |
| `C_V2g_map_rsv8m` | V alive (70k inserts, 0 errors) | same caps reached, throttled 1243 |

Bounding the on-wire charge to 24 MiB per pair (≈ 0.5 GiB of heap at R ≈ 20) removes both OOMs under
the same map load. n = 1 per arm.

#### 3.4 Default timeouts (2 s write, 12 s native transport) — realism check

| Arm | Clients | Inserts/s | Outcome | Peak counters |
|---|---|---|---|---|
| `D_S2g_map_deftimeout_c4` | 4 | ≈ 1.7k | alive | S→V pending 0.3 MiB; V←S 45 MiB; no throttle/overload |
| `D_V2g_map_deftimeout_c4` | 4 | ≈ 2.0k | alive | V←S 56 MiB |
| `D_S2g_map_deftimeout_c16` | 16 | ≈ 1.8k | alive | V←S 43 MiB |
| `D_V2g_map_deftimeout_c16` | 16 | ≈ 2.3k | alive | V←S 55 MiB |

At default deadlines the queues hold ≈ 2–3 s of arrivals and expire before reaching C. Filling 132 MiB
in 2 s needs ≥ 66 MiB/s of these mutations to one slow replica (≈ 6k inserts/s); the Python client on
this host saturated at ≈ 2.3k/s with 4–16 processes. Default-timeout reproduction is **not
established** (blocked by load-generator rate), not shown safe.

---

### 4. Conclusion and limits of attribution

**Classification (protocol, *Classification by measurement*): bypass · accounting mismatch, on two
allocation domains.** For both the coordinator and the slow replica, U > C while K ≤ C:
- **Replica (receive queue):** charged on-wire bytes ≤ 132 MiB; live deserialized mutations waiting on
  `MutationStage` ≈ 16.7× that. Same objects, measured directly (12 513 `Mutation`s = stage pending).
- **Coordinator (send side):** the send queue charges on-wire bytes ≤ 132 MiB, but (a) queued messages
  are ≈ 19.7× larger on heap, and (b) after flush the `Mutation` stays on the coordinator heap via the
  write handler until the replica answers or the deadline passes, charged to no sender counter. In the
  2 GiB arms (b) alone was enough: the coordinator died with an empty send queue.

**Causal evidence:** matched on-wire size, the blob payload (R ≈ 2.2) survives 6/6 with queues full and
dropping, while the tiny-cell payload (R ≈ 17–20) OOMs 6/6 (+1) with counters below C; capping the
endpoint reserves at 8 MiB removes the OOM at the same load (n = 1 each).

**Interpretation:** the contract states the limits are applied to the on-wire size, so this is a
**documented accounting unit that does not bound heap** — a sizing/validation gap — rather than an
implementation defect of the counters. The after-flush coordinator retention is a separate uncovered
path. A heap budget sized from the documented limits (`N*3*(send+receive capacity)` plus reserves) can
be wrong by ≈ 20× for collection-heavy writes.

**Limits / dependence on supporting deviations:**
- Slow replica injected with Byteman (100 ms per mutation, `concurrent_writes: 2`).
- Deadlines raised to 60 s (`write_request_timeout` *and* `native_transport_timeout`); at defaults, no
  OOM within the reachable client rate (§3.4).
- Hints off; single host, all instances on loopback; tightened 2 GiB heap on the measured instance.
  At 8 GiB the coordinator survived one slow replica (live ≈ 5.7 GiB). Each further slow destination can
  add another ≈ 264 MiB on-wire (≈ 5 GiB of heap at R ≈ 20) until the 512 MiB global reserves fill —
  predicted, not tested.
- Intervention n = 1 per side; client rates not matched between payloads (the control is heavier).

**Next steps:** a faster load generator (Java driver or several hosts) for the default-timeout arm;
coordinator with ≥ 2 slow replicas at a deployment-sized heap (8 GiB); repeat the intervention ×3;
compare against the JIRA history for this accounting choice before any upstream report.

All instances stopped after each batch; no Java process left on node0 (checked with `pgrep java`).

---

<a id="run-2"></a>

# Run 2 — 2026-11-10/11: replica disk stall, default timeouts, 8/6 GiB

## B6 run 2 — replica disk stall, default timeouts, no Byteman, 4 coordinators

**Direction / sub-direction:** bypass · accounting mismatch (receive side). **Allocation domain:**
replica heap holding deserialized `Mutation`s that wait on a blocked `MutationStage` while charged to
the internode receive queue at on-wire size. **Capacity regime:** default (4 / 128 / 512 MiB).
**Budget regime:** replica heap 8 GiB (deployment-like) and 6 GiB. **Pinned source:** cassandra-5.0.9,
local copy `/mydata/b6/cassandra`. **Date:** 2026-11-10/11. **Design:**
[`design/B6-run2-design.md`](design/B6-run2-design.md). **Follows:**
[run 1](#run-1).

**Verdict: run 1's deviations are not needed for the memory effect; a hard OOM is intermittent.**
With **default timeouts, no Byteman, default `concurrent_writes`**, and a 30 s storage stall on the
replica, tiny-cell writes pushed the replica to **98.7–99.5% of heap live in 5/5 map arms** (8 GiB ×2,
6 GiB ×3), with back-to-back Full GCs for **80–123 s (79–120 s of pause, ≈ 97% of the window)**; one
6 GiB arm threw a real **heap OOM** and was killed. The matched **blob** payload had **0 Full GCs in
4/4** stall arms while carrying ≈ 4× more on-wire traffic. **Receive endpoint reserve 8 MiB** removed
the effect (max 21.6% live, 1 Full GC). Without a stall the replica stayed ≤ 27% live. A full disk
**hang** (600 s write delay) instead froze the whole replica JVM in 2/3 map arms (≈ 136–138 s
"local pause", nothing accumulates) and **OOM-killed an 8 GiB replica in 1/3**.
Per protocol the main outcome is **GC-driven service loss** (not OOM) with **2 heap OOMs** among 8
map stall/hang arms.

### Summary

- **Root cause:** internode queues limit messages by **on-wire size**, but a queued write lives on the
  heap as Java objects. A 1000-tiny-cell write is 10.8 KiB on the wire and ≈ 180–210 KiB on heap
  (≈ 17–20×, ~200 B of object overhead per cell), so a receive queue within its 528 MiB limit can hold
  ≈ 9 GiB of heap. Expired writes are only removed when a write thread runs them.
- **Trigger:** a replica whose writes stall (here a slow/stalled disk): write threads block, received
  writes pile up on heap.
- **Conclusion:** reproduced with default timeouts, default threads and an 8 GiB heap — 99% heap and
  ≈ 2 min of nonstop Full GC in 5/5 stall runs; real heap OOM in 2/8 stall/hang runs. Mostly
  **service loss, not a deterministic OOM**.
- **Proof it is the accounting:** blob writes of the same on-wire size (4× the traffic) never hit a
  Full GC; a receive endpoint reserve of 8 MiB removes the problem.
- **Interpretation:** documented behaviour (limits are on-wire bytes) → sizing gap, not a code bug.

---

### 1. Constraint and protection map

As run 1, receive side: `AbstractMessageHandler.acquireCapacity` charges the frame's on-wire size
(per connection 4 MiB, per endpoint 128 MiB, global 512 MiB); a small message (< 64 KiB) is
deserialized on arrival (`InboundMessageHandler.java:156`) and waits on `MutationStage` as heap objects;
capacity is released after processing; an expired message is dropped **only when a stage thread runs
it** (`:408–423`). With 4 senders the on-wire ceiling is 4·4 + 512 = 528 MiB; at run 1's R ≈ 17 that is
≈ 9 GiB of heap. Contract: on-wire bytes (`cassandra.yaml`). C = 528 MiB on-wire; K = Σ
`internode_inbound.using_bytes`; U = live heap (GC log after-Full-GC occupancy; class histogram in P1).

### 2. Executed design (2026-11-10)

Single host node0 (`jason92-325405`, 32 cores, 125 GiB), six instances on loopback
(`harness-run2/ctl.sh`): **V** 127.0.0.11 (dc=v, replica; data, commit log and hints on
`/mydata/b6/slow`, an ext4 on a **dm-delay** device over a loop file), **F** 127.0.0.12 (dc=f, fast
replica, 8 GiB), **S1–S4** 127.0.0.13–16 (dc=c, coordinators, 8 GiB). `NetworkTopologyStrategy
{v:1, f:1}`, CL=ONE, hints off, key/counter cache 0, **all timeouts default**, no Byteman, default
`concurrent_writes`.

Client: `harness-run2/B6Load.java` (Java driver 3.12.1, async, 256 in flight per coordinator, value
serialized once and bound with `setBytesUnsafe`), one session per coordinator. Map 1000 entries
(10.80 KiB on-wire) or blob 11 000 B (10.80 KiB). Throughput with a healthy replica ≈ 2.1k map
inserts/s — the same as run 1's Python client, so the limit is server-side (cell apply rate), not the
client.

Arm (`harness-run2/arm.sh`, clean start): load 150 s on S1–S4; at t = 20 s V's disk write delay is
set to the stall value (`slowdisk.sh`); at t = 150 s back to 0; V observed 60 s more. Outcome from V's
GC log (`gcsum.sh`): `ReportJavaOutOfMemory`, Full GCs with > 95% of heap live, and the longest
"local pause" reported by V's failure detector.

**Configuration audit:** capacities default (intervention: `internode_application_receive_queue_reserve_endpoint_capacity`
8 MiB); V heap 8/6 GiB (budget); disk stall = environment fault injection (dm-delay); hints off
(supporting deviation); topology/addresses/caches (environment).

### 3. Results

Evidence: [`logs-run2/arm-outcomes.txt`](logs-run2/arm-outcomes.txt),
[`logs-run2/P1-probe.txt`](logs-run2/P1-probe.txt). Raw: `/mydata/b6/runs2/<arm>/` on node0.

#### 3.1 30 s stall (write delay 30 000 ms from t = 20 s to t = 150 s)

| Arm | V heap | Payload | Outcome | Max live after Full GC | Window of Full GCs > 95% live (pause total) |
|---|---|---|---|---|---|
| P1 (probe) | 8 GiB | map | **service loss, no recovery** (still at 99.4% 3 min after the stall; killed) | 8 141 MiB (99.4%) | 22:01:34 → 22:06:57+ |
| R2_V8g_map_stall_r1 | 8 GiB | map | service loss, recovered | 8 088 MiB (98.7%) | 107 s (104 s) |
| R2_V8g_map_stall_r2 | 8 GiB | map | service loss, recovered | 8 136 MiB (99.3%) | 109 s (106 s) |
| R2_V6g_map_stall_r1 | 6 GiB | map | service loss, recovered | 6 088 MiB (99.1%) | 123 s (120 s) |
| **R2_V6g_map_stall_r2** | 6 GiB | map | **heap OOM, JVM killed** | 6 111 MiB (99.5%) | 80 s (79 s) |
| R2_V6g_map_stall_r3 | 6 GiB | map | service loss, recovered | 6 099 MiB (99.3%) | 123 s (119 s) |
| R2_V8g_blob_stall_r1–r3 | 8 GiB | blob | survived, **0 Full GCs** | — | — |
| R2_V6g_blob_stall_r1 | 6 GiB | blob | survived, **0 Full GCs** | — | — |
| R2_V8g_map_nostall | 8 GiB | map | no stall: 15 Full GCs, healthy | 2 207 MiB (26.9%) | — |
| **R2_V8g_map_stall_rsv8m** | 8 GiB | map | **intervention** (receive endpoint reserve 8 MiB): survived | 1 770 MiB (21.6%), 1 Full GC | — |

Blob arms completed 1.09–1.27 M inserts (≈ 4× the on-wire bytes of the map arms' ≈ 0.27–0.31 M) and
still had no Full GC. Clients saw few errors in map arms (F acks CL=ONE), so the replica's distress is
invisible to the client; blob arms had ≈ 27–31 k write timeouts from F under its own load.

P1 live histogram in the spiral: **37 217 `Mutation`s / 37.2 M `ArrayCell`s waiting** (≈ 393 MiB
on-wire, below C = 528 MiB) plus ≈ 13 M `BufferCell`s (memtable); 7.95 GiB live of 8 GiB.
`MutationStage` 20 s into the stall: 32 active, 30 411 pending. The sampler's JMX/CQL queries to V time
out during the spiral, so K during the spiral is known from the histogram (P1) only; the coordinator
send queues stayed ≤ 2.5 MiB with tens of thousands of expired messages (2 s deadline at the sender).

Why it does not always OOM: with a 30 s write delay the commit-log sync completes every ~30 s, the
blocked stage threads advance in bursts, and each burst drops expired messages; heap settles at the
edge (each Full GC frees ≈ 16 MiB), so G1 rarely fails an allocation outright.

#### 3.2 Full disk hang (write delay 600 000 ms, cleared at t = 150 s)

| Arm | V heap | Payload | Outcome | Longest JVM "local pause" |
|---|---|---|---|---|
| R2H_V8g_map_hang_r1 | 8 GiB | map | whole JVM frozen, no accumulation (19% max) | **137.9 s** |
| **R2H_V8g_map_hang_r2** | 8 GiB | map | **heap OOM, JVM killed** (99.6% live, 42 Full GCs, 106 s pause) | 39.3 s |
| R2H_V6g_map_hang_r1 | 6 GiB | map | whole JVM frozen, no accumulation (23% max) | **135.7 s** |
| R2H_V8g_blob_hang_r1 | 8 GiB | blob | survived, 0 Full GCs | 39.3 s |

A full hang usually stops the **entire** replica JVM (likely a thread blocked in commit-log mmap /
dirty-page writeback delaying safepoints — not verified), so it stops reading the network and nothing
accumulates. When the JVM keeps running (r2) the receive queues fill and the 8 GiB replica OOMs.

### 4. Conclusion and limits

**The mismatch reproduces under realistic conditions.** Default timeouts, default thread pools, a
deployment-sized 8 GiB heap and four ordinary coordinators: a replica whose writes stall on storage
fills its heap to ≈ 99% with waiting tiny-cell mutations while the on-wire counters stay at or below
the 528 MiB ceiling (P1: 393 MiB on-wire waiting ↔ 7.95 GiB live). The blob control (same on-wire size,
4× the traffic) never triggers a Full GC, and capping the receive endpoint reserve at 8 MiB removes the
effect — the charged unit, not the traffic volume, decides the outcome.

**Outcome type:** mostly **GC-driven service loss** (≈ 97% of an 80–123 s window spent in Full GC; in
P1 no recovery after the stall), which the protocol does not count as OOM; **2 genuine heap OOMs**
(6 GiB stall r2, 8 GiB hang r2) out of 8 map stall/hang arms. Not a deterministic OOM.

**Limits:**
- Fault injection is a storage stall via dm-delay on a loop file (one host; all instances share CPU).
- 30 s and 600 s write delays are two points; the outcome depends on whether the JVM freezes (hang)
  or advances in bursts (30 s).
- Hints off (supporting deviation). Coordinator heaps were not measured in run 2 (8 GiB, default
  deadlines — run 1 showed the coordinator side needs long deadlines or ≥ 66 MiB/s per destination).
- Intervention n = 1; blob 6 GiB n = 1; V-side K during the spiral only from one histogram.
- The OOM thread/stack was not preserved (`OnOutOfMemoryError` kill; heap dumps disabled in run 2).

**Next:** heap dumps on for one OOM arm; repeat the intervention ×3; vary the stall length (5 / 15 /
60 s) to map service loss vs OOM; measure the coordinators; check JIRA for receive-queue/heap issues
(CASSANDRA-15066 introduced these limits) before reporting upstream.

All instances stopped and the delay device reset to 0 after each batch (`pgrep java` = 0;
`dmsetup table b6slow` shows delay 0). The dm-delay device and loop file remain on node0 for reuse.

---

<a id="run-3"></a>

# Run 3 — 2026-11-11: reserve intervention ×3 and same-day positives

## B6 run 3 — repeated reserve intervention and same-day positives (V1/V4 of the promotion rule)

**Direction:** bypass · accounting mismatch · `source: flow:coordinator-write`. **Regime:** default
capacities. **Source:** Cassandra 5.0.9, local copy `/mydata/b6/cassandra` (same build as runs 1–2).
**Date:** 2026-11-11. **Design:** [`design/B6-run3-design.md`](design/B6-run3-design.md) (written before
the readings). **Earlier runs:** [run 1](#run-1),
[run 2](#run-2).

### Summary

- **Purpose:** test runs 1 and 2 against the protocol's promotion rule V1–V5 (amended 2026-11-11):
  three fresh repeats of the endpoint-reserve intervention per condition, a same-day positive per
  condition, and a third clean-start repeat of run 2's failing condition. Nothing else changed.
- **Run 2 condition (8 GiB replica, 30 s disk stall, default timeouts):** positive reproduced
  (99.3% live, 98% of a 126 s window in Full GC); with the receive endpoint reserve at 8 MiB, 3/3
  arms had 1 Full GC each and 22–31% live, no service loss, no client errors. **V1–V5 met.**
- **Run 1 condition, coordinator at 2 GiB:** positive reproduced (heap OOM, dump kept); with send +
  receive endpoint reserves at 8 MiB, 3/3 survived. **V1–V5 met.** The capped coordinator still held
  69–75% live with 20–26 Full GCs in 90 s: the OOM is removed, the pressure is not.
- **Run 1 condition, replica at 2 GiB:** positive **did not reproduce** (98.2% live, 131 Full GCs,
  57% of 83 s in Full GC, alive at the end of load); by the pre-stated rule it stays a candidate.
  The capped arms 3/3 had no Full GC (≤ 25% heap after any GC).
- **Root cause (unchanged):** the internode queues charge on-wire bytes while queued mutations hold
  ≈ 17–20× that on heap; bounding the charged bytes per endpoint bounds the heap that follows.
- **What the reserve costs:** it protects by shedding. Run-1 condition: the coordinator dropped
  ≈ 51–58k writes to the slow replica per arm (overload) and delivered ≈ 10.5–11.8k; clients saw no
  errors only because the fast replica acknowledged at CL=ONE.

---

### 1. Constraint and protection map

Unchanged from runs 1–2: `internode_application_{send,receive}_queue_capacity` (per endpoint 4 MiB
exclusive + `*_reserve_endpoint_capacity` 128 MiB default + global reserve 512 MiB), charged in on-wire
bytes; contract and protection map in run 1 §1 and run 2 §1. The intervention lowers the endpoint
reserve from 128 MiB to 8 MiB (run 1 condition: send and receive, all instances; run 2 condition:
receive only, all instances), so the charged ceiling per endpoint pair is 4 + 8 = 12 MiB.

Labels: run-1 condition `diagnostic` (Byteman delay and `concurrent_writes: 2` on V, 60 s write and
native-transport timeouts, 2 GiB heap). Run-2 condition: default timeouts and threads, 8 GiB, external
disk stall; hints off, key/counter cache 0, single host — conditions label to be decided (hints off).

### 2. Executed design (2026-11-11)

As [`design/B6-run3-design.md`](design/B6-run3-design.md), no amendments. Batch
[`harness-run3/batch.sh`](harness-run3/batch.sh) calls the run-1 (`harness/arm.sh`, `harness/armx.sh`)
and run-2 (`harness-run2/arm.sh`) harnesses unchanged, in this order, each from a clean start:
`R3B_V8g_map_stall_r3`, `R3B_V8g_map_stall_rsv8m_r2–r4`, `R3A_B_S2g_map_pos`,
`R3A_C_S2g_map_rsv8m_r2–r4`, `R3A_B_V2g_map_pos`, `R3A_C_V2g_map_rsv8m_r2–r4`. Heap dumps on for the
positives, off for the interventions. Live heap = occupancy after Full GC from the GC log
([`harness-run3/gcpeak.sh`](harness-run3/gcpeak.sh)); occupancy after a young pause is not a live
bound (validated on run 2's reserve arm: 99.8% after a young pause, 21.6% after its Full GC).
Service-loss criterion: protocol default (≥ 90% of wall time in Full GC over ≥ 60 s).

Batch 11:46–12:52 on node0 (`pc96`, 32 cores, 125 GiB). Excerpt:
[`logs-run3/arm-outcomes.txt`](logs-run3/arm-outcomes.txt). Raw: `/mydata/b6/runs2/R3B_*`,
`/mydata/b6/runs/R3A_*` on node0 (coordinator logs of `R3B_..._rsv8m_r4` copied into its run dir).

### 3. Results

#### 3.1 Run-2 condition — V 8 GiB, 30 s disk stall, 4 coordinators, default timeouts

| Arm | Outcome | Full GCs | Live after Full GC | Full-GC window > 95% heap | Client | V receive per sender (max) |
|---|---|---|---|---|---|---|
| `R3B_V8g_map_stall_r3` (positive) | **service loss**, recovered | 78 | 8 131 MiB (99.3%) | 126 s, 123 s paused (98%) — MET | 305k sent, 113 err | using 74 MiB, reserve 70 MiB, expired 34.6k |
| `R3B_V8g_map_stall_rsv8m_r2` | survived | 1 | 1 981 MiB (24.2%) | — | 333k, 0 err | using 28 MiB, reserve 8 MiB, throttled 6 |
| `R3B_V8g_map_stall_rsv8m_r3` | survived | 1 | 1 812 MiB (22.1%) | — | 328k, 0 err | using 28 MiB, reserve 8 MiB, throttled 5 |
| `R3B_V8g_map_stall_rsv8m_r4` | survived | 1 | 2 533 MiB (30.9%) | — | 308k, 0 err | using 24 MiB, reserve 8 MiB, throttled 4 |

With the earlier runs at this condition: failing **3/3** clean starts (run 2 r1, r2; run 3 r3), all
meeting the service-loss criterion (96–98%); blob control 0/3 Full GCs (run 2); intervention **4/4**
(run 2 + 3 fresh). Client throughput with the reserve (308–333k) is not lower than without (269–305k).
Coordinators in `rsv8m_r4` (n = 1): S1–S4 ≤ 668 MiB (8.2%) after any GC, no Full GC — the throttled
backlog did not move onto the coordinators' heaps.

#### 3.2 Run-1 condition — coordinator S at 2 GiB (V 8 GiB, Byteman slow V, 60 s timeouts)

| Arm | Outcome | Full GCs | Live after Full GC | S→V pending / overload / sent | Client |
|---|---|---|---|---|---|
| `R3A_B_S2g_map_pos` | **heap OOM, JVM killed**, dump 2.85 GB | 87 | 2 012 MiB (98.2%) | 0 MiB / 0 / 7.5k | 19.1k sent, 9.5k err (after S died) |
| `R3A_C_S2g_map_rsv8m_r2` | survived | 20 | 1 418 MiB (69.2%) | 12 MiB / 55.5k / 10.9k | 66.4k, 0 err |
| `R3A_C_S2g_map_rsv8m_r3` | survived | 26 | 1 536 MiB (75.0%) | 12 MiB / 50.6k / 11.8k | 63.3k, 0 err |
| `R3A_C_S2g_map_rsv8m_r4` | survived | 23 | 1 501 MiB (73.3%) | 12 MiB / 53.5k / 11.4k | 65.3k, 0 err |

With run 1: failing **4/4** (3 + same-day), blob control 0/3, intervention **4/4** (1 + 3 fresh). The
positive again died with its send queue empty (after-flush `hintOnFailure` retention, run 1 §4).

#### 3.3 Run-1 condition — replica V at 2 GiB (S 8 GiB)

| Arm | Outcome | Full GCs | Live after Full GC | Full-GC window > 95% heap | Client |
|---|---|---|---|---|---|
| `R3A_B_V2g_map_pos` | **alive** at end of load — no OOM | 131 | 2 011 MiB (98.2%) | 83 s, 48 s paused (57%) — not met | 58.3k, 0 err |
| `R3A_C_V2g_map_rsv8m_r2–r4` | survived | 0 / 0 / 0 | — (≤ 512 MiB, 25.0%, after any GC) | — | 66.8k / 69.0k / 69.5k, 0 err |

The positive reached the same live heap as run 1's three OOMs (98%+) but finished the 90 s load
alive; run 1's `B_V2g_map_r1` OOMed after a 30 s window. The OOM at this condition is therefore
timing-dependent at 90 s; this was not investigated further (no escalation, per the design).

### 4. Conclusion and limits

**Promotion rule (protocol *Verification status*):**

| Case / condition | V1 | V2 | V3 | V4 | V5 | Result |
|---|---|---|---|---|---|---|
| Run 2 — replica 8 GiB, disk stall | 3/3 service loss | blob 0/3 | P1 histogram, counters | 4/4 | GC logs | **meets V1–V5 → `verified-gap · service-loss`**, conditions label pending (hints off) |
| Run 1 — coordinator 2 GiB | 4/4 heap OOM | blob 0/3 | histograms | 4/4 | dumps (run 1 r1, run 3) | **meets V1–V5 → `verified-OOM · diagnostic`** |
| Run 1 — replica 2 GiB | 3/4 (same-day positive survived) | blob 0/3 | histograms | 4/4 | dumps (run 1) | **candidate**: positive not reproduced (pre-stated rule) |

**Interpretation (unchanged):** the limits are documented as on-wire bytes, so this is a
documented-unit / sizing gap plus the uncovered after-flush coordinator retention, not a counter
defect. The intervention shows the charged ceiling, not the traffic, decides the outcome.

**Limits:**
- The reserve protects by shedding: at the run-1 condition ≈ 83% of writes to the slow replica were
  dropped by the coordinator (overload) — invisible to the CL=ONE client because F acknowledged. At
  the run-2 condition the receive side throttled only 4–6 times per sender; coordinators measured in
  one arm only.
- The capped 2 GiB coordinator still ran at 69–75% live with a Full GC every ≈ 4 s: the OOM is
  removed, memory pressure is not.
- Run-1 replica condition: OOM timing-dependent at 90 s; a longer load or more repeats would settle it.
- Single host, loopback, hints off, key/counter cache 0 (as runs 1–2).

**Next:** decide run 2's conditions label (hints off) and move the promoted cases into `bypass/`;
JIRA check (CASSANDRA-15066) before any upstream report; optionally a longer-load repeat for the
replica-side run-1 condition.

All instances stopped at the end of the batch (`pgrep java` empty) and the dm-delay device reset to 0
(`dmsetup table b6slow`: delay 0). Heap dump `R3A_B_S2g_map_pos` kept on node0.

---

<a id="run-4"></a>

# Run 4 — 2026-11-11/12: coordinator, two slow replicas, budget search

## B6 run 4 — coordinator side with two slow replicas (storage stall), default and 60 s timeouts

**Direction:** bypass · accounting mismatch (coordinator side) · `source: flow:coordinator-write`.
**Regime:** default capacities. **Source:** Cassandra 5.0.9, `/mydata/b6/cassandra` (same build as runs
1–3); diagnostic patch build `/mydata/b6/cassandra-p4`. **Date:** 2026-11-11 21:30 → 2026-11-12 ≈ 03:40
(pc96). **Design:** [`design/B6-run4-design.md`](design/B6-run4-design.md) (written before readings;
amendments A1–A3 dated inside). **Earlier runs:** [run 1](#run-1), [run 2](#run-2), [run 3](#run-3).

### Summary

- **Question:** does the coordinator, which keeps every sent `Mutation` until each replica answers,
  run out of heap when **two replicas** (owning disjoint halves of the ring) stall on storage — with
  default timeouts and no Byteman — and what is the largest coordinator heap that still fails?
- **Default timeouts (phase D, deployment settings):** the coordinator holds about *write rate × 2 s*
  of mutations (≈ 1.3 GiB live at ≈ 2k writes/s). It **survives at 2 GiB, 1 GiB, 768 MiB and
  640 MiB** (63–89% live) and reaches the endpoint only at the **512 MiB floor: 3/5** (2 heap OOM + service
  loss, 1 service loss; plus 1/1 with a rate-capped client). Rate-matched blob writes survive 0/3 failures
  (37–42% live). Neither the 8 MiB endpoint reserves (3/3 still OOM) nor a patch that drops the
  `hintOnFailure` reference (3/3 still OOM) removes it: with the patch the same ≈ 1 850 mutations
  simply sit in the send queue instead (K ≈ 19 MiB on-wire ≪ C). **Not verified** (V4 unmet; boundary at
  the minimum acceptable budget).
- **60 s write/native timeouts (phase X, diagnostic, no Byteman):** the coordinator fails at **2 GiB
  (service loss), 4 GiB (OOM 3/3) and 6 GiB (OOM + service loss 3/3)** and survives at **8 GiB (2/2,
  but ≈ 99% live)**. Blob 0/3 and 8 MiB reserves 3/3 at both 4 and 6 GiB → V1–V5 met at **6 GiB** (largest failing) →
  `reproduced-OOM · diagnostic` (raised timeouts).
- **Root cause (refined):** the bypass is the on-wire charge of the send queue plus the uncharged
  after-flush `hintOnFailure` retention; the bound that actually applies is *rate × request deadline ×
  ≈ 213 KiB per 10.8 KiB write*. At default deadlines that is ≈ 1–1.3 GiB on this host — dangerous only to
  heaps ≤ 512 MiB; at 60 s deadlines it reaches the send-queue capacity (132 MiB on-wire per slow
  destination ≈ 2.6 GiB of heap) times the number of slow destinations.

---

### 1. Constraint and protection map (coordinator S)

| Holder | Charged to (K) | Bound | Release |
|---|---|---|---|
| (a) queued `Message<Mutation>` to each slow replica | send queue, on-wire: 4 MiB/link + 128 MiB endpoint + 512 MiB global | C = 132 MiB per destination | flush, overload drop, expiry (pruned on enqueue) |
| (b) flushed `Mutation` via `RequestCallbacks` → `WriteResponseHandler.hintOnFailure` | nothing on S | implicit: rate × deadline (2 s default; 60 s in phase X), reaped every ≈ 0.5 s | replica response or expiry |
| (c) in-flight client requests | `native_transport_max_request_data_in_flight` (heap/10) and `_per_ip` (heap/40), frame bytes | resolved at S's heap (512 MiB: 51 / 13 MiB) | response sent |

One `Mutation` object is shared by (a), (b), (c) and both destinations of a write; "two slow replicas"
therefore means **disjoint ranges** (V1 token MIN, V2 token 1, dc v, `{v:1, f:1}`), each with its own
send reserve. K = `system_views.internode_outbound.pending_bytes` (S → V1/V2); U = live heap from the GC
log (occupancy after Full GC) and HPROF class histograms of OOM dumps (`harness-run4/hprofhist.py`).

**Labels.** Capacities default (V6). Phase D: timeouts and threads default, no Byteman, storage stall by
dm-delay on V1+V2 (external), hints off and key/counter cache 0 (accepted documented values, as
condition A), single host on loopback (environment) → `deployment` settings. Phase X: plus
`write_request_timeout` and `native_transport_timeout` 60 s on all instances (supporting deviation) →
`diagnostic`. Budget: S `-Xmx` 512 MiB–8 GiB (standing rule: ≥ 512 MiB meets V7, 2 GiB ideal);
`cassandra-env.sh` resolved `MaxDirectMemorySize=15872M` (not a factor: no direct OOM).

### 2. Executed design

Topology (`harness-run4/ctl.sh`, `ring-up.sh`): V1 127.0.0.11 and V2 127.0.0.17 (dc v, 8 GiB, data on
`/mydata/b6/slow` — the run-2 dm-delay device), F 127.0.0.12 (dc f, 8 GiB, acks CL=ONE), S 127.0.0.13
(dc c, measured, owns no data). Client: `B6Load`, 8 sessions × 256 in flight to S only; payload map 1000
cells (10.80 KiB on-wire) or 11 000-byte blob (10.80 KiB). Arm (`harness-run4/arm.sh`, clean start):
load 150 s, write delay 30 s on V1+V2 from t = 20 s to t = 150 s, observe 60 s. Endpoint: heap OOM
(HotSpot `HeapDumper` / `ReportJavaOutOfMemory` safepoints in the GC log — Cassandra's `system.log` was
starved in all but one OOM) or service loss (≥ 90% of wall time in STW pauses over ≥ 60 s, all pauses,
`harness-run4/gcwin.py`). Batches: `batch-d.sh` (stopped by the agent's tool time limit during uncapped
blob r3, rerun in `batch-r.sh`), `batch-d-rest.sh`, `batch-d2.sh`, `batch-x.sh`, `batch-r.sh`,
`batch-x6.sh`. Amendments: A1 rate-matched blob control (`RATE=2000` writes/s, run-4 `B6Load.java`) after
the uncapped blob failed at 512 MiB; A2 dumps for one patched and one reserve arm, 6 GiB bisection; A3
controls at 6 GiB. Diagnostic patch: [`harness-run4/no-hint-retention.diff`](harness-run4/no-hint-retention.diff)
(`StorageProxy.java:1391` passes `null` instead of `mutation.hintOnFailure()` when hints are disabled).

**Contention caveat:** another session's Cassandra stage-4 workload (`/mydata/jingsong-cass-s4`) ran on
pc96 during part of this run (from ≈ 22:40 recorded per arm in `foreign.txt`; load average 8–18 of 32
cores). The phase-D boundary depends on the write rate and is sensitive to it (pre-stall rates
1.46–2.43k/s at 512 MiB).

### 3. Results

Raw: `/mydata/b6/runs4/<arm>/` on pc96 (dumps kept there). Excerpts: [`logs-run4/arm-outcomes.txt`](logs-run4/arm-outcomes.txt),
[`logs-run4/oom-histograms.txt`](logs-run4/oom-histograms.txt), [`logs-run4/oom-evidence.txt`](logs-run4/oom-evidence.txt).

#### 3.1 Phase D — default timeouts, budget search (map, uncapped client)

| S heap | Arms | Endpoint | Live after Full GC | Max STW share in 60 s | Client ok |
|---|---|---|---|---|---|
| 2 GiB | r1 | survived | 1 285 MiB (62.7%) | 40% | 286k |
| 1 GiB | r1 | survived | 881 MiB (86.0%) | 61% | 198k |
| 768 MiB | r1 | survived | 661 MiB (86.1%) | 76% | 162k |
| 640 MiB | r1 | survived | 570 MiB (89.1%) | 82% | 122k |
| **512 MiB** | r1 | **heap OOM** (t = 52 s, JVM not killed) **+ service loss** (262 s window, 93%) | 479 MiB (93.6%) | 100% | 36k |
| 512 MiB | r2 | survived | 471 MiB (92.0%) | 84% | 95k |
| 512 MiB | r3 | **heap OOM** (t = 128 s, killed t = 204 s) **+ service loss** (174 s) | 479 MiB | 100% | 36k |
| 512 MiB | r4 | **service loss** (267 s window, no OOM) | 482 MiB (94.1%) | 100% | 51k |
| 512 MiB | r5 | survived | 437 MiB (85.4%) | 89% | 100k |
| 512 MiB, client capped 2k/s | r1 | **heap OOM + service loss** (231 s) | 481 MiB | 100% | 37k |

At 2 GiB the send queue to each slow replica peaked at **24 MiB on-wire** (K ≪ C = 132 MiB), while
each slow replica's receive counter sat at its 140 MiB cap. At 512 MiB the queues stayed ≤ 6 MiB.
**Largest failing default-timeout budget: 512 MiB, 3/5 (4/6 with the capped arm); first surviving:
640 MiB (n = 1; 768 MiB, 1 GiB, 2 GiB also survived, n = 1 each).**

Holder at OOM (dumps r1, r3, capped r1): **1 845–1 893 `Mutation`s / 1.85–1.89 M `BufferCell`s ≈ 460 MiB**
of a 512 MiB heap, reachable from 1 837–1 884 `WriteResponseHandler`s (1 866–1 984 callbacks); only
13–77 queued `Message`s. First error (capped r1, the only arm whose `system.log` kept it): `ERROR
[Native-Transport-Requests-76] JVMStabilityInspector … java.lang.OutOfMemoryError: Java heap space`,
2 min after the native in-flight limit (13 MiB/IP) had triggered backpressure.

#### 3.2 Phase D — controls and interventions at 512 MiB

| Arm | n | Endpoint | Detail |
|---|---|---|---|
| blob, uncapped client | 3 | **heap OOM 3/3** (t = 35–39 s) | **not matched**: blob runs at several times the map rate; reported, not used as V2 |
| **blob, client capped at 2 000/s** (≈ map rate) | 3 | **0/3** | 189–217 MiB live (37–42%), max 60 s STW 5%, 299k ok each; send queue ≤ 24 MiB |
| map, no stall | 1 | 0/1 | 355 MiB (69.3%), max 69% |
| map, send + receive endpoint reserves 8 MiB | 3 (+1 dump) | **heap OOM 3/3** (t = 52, 130, 52 s); dump arm also OOM | dump: 1 857 `Mutation`s, 26 `Message`s — same callback holder |
| map, patch (no `hintOnFailure` when hints off) | 3 (+1 dump) | **heap OOM 3/3** (t = 51–52 s); dump arm also OOM | dump: 1 824 `Mutation`s held by **1 829 queued `Message`s** (≈ 19 MiB on-wire) |

The patch moves the holder from (b) to (a) without changing its size: once V1/V2 stop reading, about
rate × 2 s of mutations waits in the send queue, still ≈ 15% of the on-wire capacity C.

#### 3.3 Phase X — 60 s write/native timeouts (diagnostic), budget search (map)

| S heap | Arms | Endpoint | Live after Full GC | Notes |
|---|---|---|---|---|
| 2 GiB | r1 | **service loss** (265 s window), alive | 2 018 MiB (98.5%) | |
| 4 GiB | r1–r3 | **heap OOM + service loss 3/3** | 4 060–4 062 MiB (99.1–99.2%) | dump r1: 19 027 `Mutation`s ≈ 4.4 GiB; 16 907 queued `Message`s (≈ 178 MiB on-wire for both destinations, ≤ 2 × C) |
| **6 GiB** | r1–r3 | **service loss 3/3, heap OOM 3/3** (r1: OOM + dump but no kill, JVM alive at stop; r2, r3 killed) | 6 109–6 111 MiB (99.4–99.5%) | dump r1: 20 517 `Mutation`s, 20 514 callbacks, 45 queued `Message`s |
| 8 GiB | r1–r2 | survived 2/2 | 8 097–8 101 MiB (98.8–98.9%) | max 60 s STW 74% / 83% (criterion not met); S → V1/V2 queues reached **132 MiB = C** and dropped (2.4k–24k overloads) |
| 4 GiB blob | r1–r3 | 0/3 | 1 345–1 359 MiB (33%) | 18.6k writes/s pre-stall; queues full at C, 170k–250k overloads |
| 4 GiB, reserves 8 MiB | r1–r3 | **0/3** (survived) | 1 964–2 273 MiB (48–56%) | 240k–347k ok |
| 6 GiB blob | r1–r3 | 0/3 | no Full GC; ≤ 2 271–3 772 MiB (37–61%) after any pause | 859k–908k ok |
| 6 GiB, reserves 8 MiB | r1–r3 | **0/3** (survived) | 1 798–2 124 MiB (29–35%) | max 60 s STW 6–8%; 190k–391k ok |

**Largest failing phase-X budget: 6 GiB, 3/3; first surviving: 8 GiB (2/2, at ≈ 99% live).** The
design predicted ≈ 11 GiB of holders and a boundary at 12–16 GiB; the 8 GiB survivals show the actual
plateau is ≈ 8 GiB on this host (both send queues at C, the rest dropped).

### 4. Conclusion and limits

| Condition | V1 | V2 | V3 | V4 | V5 | V6 | V7 | Result |
|---|---|---|---|---|---|---|---|---|
| D: default timeouts, two slow replicas, S 512 MiB | 3/5 (endpoint mixed: 2 OOM + SL, 1 SL) | rate-matched blob 0/3; no stall 0/1 | dumps: U ≈ 460 MiB `Mutation`s, K ≤ 6 MiB | **no**: reserves 0/3, patch 0/3 removed it | `HeapDumper`/`ReportJavaOutOfMemory`, dumps, one `system.log` first error; GC logs | yes | yes (512 MiB, the floor) | **candidate** (V4 unmet) |
| X: 60 s timeouts, S 4 GiB | 3/3 OOM | blob 0/3 | dump: U ≈ 4.4 GiB, K ≈ 178 MiB ≤ 264 MiB | reserves 3/3 | dumps + safepoints | yes | yes | **reproduced-OOM · diagnostic** (raised timeouts) |
| **X: 60 s timeouts, S 6 GiB (largest failing)** | 3/3 OOM + SL | blob 0/3 | dump: 20 517 `Mutation`s ≈ 4.9 GiB shallow vs K ≤ 132 MiB per destination | reserves 3/3 | dumps + safepoints | yes | yes | **reproduced-OOM · diagnostic** (raised timeouts) |

**Interpretation.** The coordinator side of B6 is real but, at shipped deadlines, bounded by
*rate × 2 s*: on this host ≈ 1.3 GiB at ≈ 2k map writes/s, which only a 512 MiB coordinator cannot
hold. Two slow replicas do not add memory at default deadlines (every write already waits on one slow
replica); they matter when deadlines are long enough for each destination's 132 MiB send capacity to
fill, which is what raises the failing budget to 6 GiB under 60 s timeouts. The 8 MiB reserve protects
at 4 GiB (diagnostic) but not at 512 MiB, where even 2 × 12 MiB on-wire is ≈ 0.5 GiB of heap. Removing the
`hintOnFailure` reference is not a fix by itself: the same backlog waits in the send queue, charged at
on-wire size.

**Limits.**
- Phase D's endpoint is at the protocol's minimum acceptable heap and is rate-sensitive (pre-stall
  1.46–2.43k/s; another session's workload shared the host for part of the run). 640 MiB–2 GiB n = 1 each.
- 512 MiB heap OOMs often did not trigger `OnOutOfMemoryError` (no kill; JVM left in a Full-GC loop) and
  Cassandra's own log was starved; OOMs are read from HotSpot safepoints and dumps. Two dumps were
  truncated (0 bytes) because the arm stopped the JVM while the dump was being written.
- Single host on loopback; client on the same host; hints off.
- HPROF histograms are shallow sizes over the whole dump (no reachability filter); the dumps were taken at
  OOM after back-to-back Full GCs.

**Next:** a coordinator-side intervention that bounds rate × deadline (e.g. a byte-based in-flight limit
on the write path charged at heap size, or a much smaller send reserve together with the
`hintOnFailure` patch) to settle V4 at default timeouts; repeat 640 MiB–1 GiB ×3 on an otherwise idle host.

All run-4 instances stopped after the last batch; dm-delay `b6slow` (created in run 2) left at delay 0;
no run-4 process left (checked).
