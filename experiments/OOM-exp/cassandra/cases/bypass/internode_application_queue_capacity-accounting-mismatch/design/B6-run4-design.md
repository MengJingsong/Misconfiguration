# B6 run 4 design — coordinator side with ≥ 2 slow replicas (2026-11-11)

Written before any run-4 reading. Node `pc96` (node0 `jason92-325405`, 32 cores, 125 GiB), same build
as runs 1–3 (`/mydata/b6/cassandra`, cassandra-5.0.9 `b5f2a54210`, OpenJDK 11.0.33, G1).
Harness [`harness-run4/`](../harness-run4/) (reuses `harness-run2/load.sh`, `B6Load`, `slowdisk.sh`,
`harness-run3/gcpeak.sh`). Raw data `/mydata/b6/runs4/<arm>/`.

## 1. Question

Condition B (2 GiB coordinator, Byteman-slowed replica, 60 s write/native timeouts) is
`reproduced-OOM · diagnostic`. Open item: does the **coordinator**, which keeps every sent `Mutation`
(`hintOnFailure`, `AbstractWriteResponseHandler.java:81`, `StorageProxy.java:1391`) until each replica
answers or the callback expires, reach heap OOM or the protocol's service-loss criterion when **≥ 2
replicas are slow**, preferably with **default timeouts, no Byteman, an external storage stall** (so the
label can be `deployment`), at the **largest coordinator heap** that still fails?

## 2. Protection map for the coordinator (source-checked 2026-11-11)

| Holder on S | Charged to | Bound | Release |
|---|---|---|---|
| (a) `Message<Mutation>` in the outbound queue to Vi | send queue, on-wire bytes: 4 MiB per link + 128 MiB endpoint reserve + 512 MiB global | per destination 132 MiB on-wire (C), global 512 MiB | flushed, dropped on overload, or pruned when expired (`OutboundMessageQueue.maybePruneExpired`, run on enqueue) |
| (b) flushed `Mutation` held by the write handler (`hintOnFailure`) via `RequestCallbacks` | **nothing** on S (only Vi's receive queue in another JVM) | implicit: arrival rate × lifetime; lifetime = until Vi answers or the callback expires at min(`write_request_timeout`, `native_transport_timeout` from admission), reaped every min-RPC-timeout/2 | Vi's response, expiry, or overload/expiry of the message |
| (c) in-flight client requests | `native_transport_max_request_data_in_flight` (heap/10) and `_per_ip` (heap/40), frame bytes | per-IP and global frame bytes; threads 128 | response sent |

The same `Mutation` object is shared by (a), (b) and (c) and by all destinations of one write.
C (contract) = 132 MiB on-wire per destination for (a); (b) has no control. K =
`system_views.internode_outbound.pending_bytes` on S per destination. U = S's live heap: occupancy after
Full GC from the GC log (`gcpeak.sh`), plus one class histogram in a separate diagnostic arm.

**Why "≥ 2 slow replicas" means distinct ranges here.** If both slow replicas held the same mutations
(e.g. `{v:2}`) S would keep one shared `Mutation` per write: no more heap than one slow replica. The test
therefore uses two slow replicas that own **disjoint halves of the ring** (V1 token MIN, V2 token 1 in
dc v, `{v:1, f:1}`), so each destination has its own 132 MiB send reserve and its own receive queue, and
the coordinator's holders scale with the number of slow destinations — until the 512 MiB global send
reserve is reached (> 3 destinations). Both V1 and V2 live on the same dm-delay device (one shared
storage stall, e.g. a SAN hiccup).

## 3. Topology, workload, settings

| Instance | Address | dc | Role | Heap |
|---|---|---|---|---|
| V1, V2 | 127.0.0.11 / .17 | v | slow replicas, data/commitlog/hints on `/mydata/b6/slow` (dm-delay) | 8 GiB |
| F | 127.0.0.12 | f | fast replica, acks CL=ONE | 8 GiB |
| **S** | 127.0.0.13 | c | **measured coordinator**, owns no data; the only node the client talks to | **budget dial** |

Client: `B6Load` (Java driver 3.12, async, value serialized once), **8 sessions × 256 in flight**, all to S,
CL=ONE. Payloads unchanged: `map<int,int>` 1000 entries (10.80 KiB on-wire) vs **11 000-byte blob**
(10.80 KiB, matched control). Arm (`harness-run4/arm.sh`, clean start): load 150 s; at t = 20 s the disk
write delay := 30 s (run 2's stall); at t = 150 s := 0; observe 60 s.

**Configuration audit.** Capacities: internode send/receive queues default (4/128/512 MiB) — the
constraints the endpoint depends on (V6); native-transport in-flight limits default (heap-derived,
resolved at S's heap: heap/10 and heap/40). Budget: S `-Xmx` (dial), `MaxDirectMemorySize` unset by the
harness, i.e. as `cassandra-env.sh` leaves it (JVM default = `-Xmx`). Environment: single host on
loopback, `num_tokens: 1`, explicit tokens, `GossipingPropertyFileSnitch`, key/counter cache 0, hints off
(accepted documented setting, as condition A). Fault: external storage stall on V1+V2 (dm-delay).
Supporting deviations only in phase X (below).

**Budget (V7, standing rule 2026-11-11).** Cassandra would resolve for this node (125 GiB) a 15 872 MiB
heap and 7 936 MiB direct limit; a 2 GiB heap is the protocol's ideal and anything ≥ 512 MiB meets V7.
The search starts at 2 GiB and goes up (4, 8, 12, 16 GiB, refining between the last failing and first
surviving budget). If 2 GiB does not fail at default timeouts, budgets below 2 GiB down to 512 MiB are
tried (still V7-acceptable) to find the largest failing one.

## 4. Predictions (before readings)

- **Default timeouts (phase D).** The write deadline is 2 s, callbacks are reaped every ≤ 1 s, and
  expired messages are pruned on enqueue, so holders (a)+(b) on S are ≈ arrival rate × ≈ 2–3 s,
  **independent of the number of slow replicas** (every write already waits on one slow replica). Filling
  even one 132 MiB send reserve within 2 s needs ≈ 6.2k writes/s per destination; run 2 measured ≈ 2.1k
  map writes/s for the whole ring (server-bound). Prediction: S holds ≈ 2.1k × 2.5 s × 213 KiB ≈
  **1.1 GiB** (error ± 50%) → survives at 2 GiB (≈ 60% live, frequent mixed/young GC), **service loss or
  OOM plausible at 1 GiB**, survives at ≥ 4 GiB. The queue counters stay far below C, so the 8 MiB
  reserve intervention is predicted **not** to change the outcome; the predicted causal intervention at
  default timeouts is a diagnostic patch that drops `hintOnFailure` when hints are disabled (phase P).
- **Raised timeouts (phase X, diagnostic).** With 60 s deadlines the stalled V1/V2 stop reading once
  their receive queues hold 132 MiB each; S's send queue to each fills to 132 MiB and overloads. Holders
  per slow destination ≈ 132 MiB queued + ≈ 132 MiB held at Vi via (b) (+ TCP buffers) ≈ 264 MiB on-wire
  × R ≈ 20 ≈ **5.2–5.6 GiB** (run 1 measured 5.6 GiB live with one slow replica). With two:
  **≈ 11 GiB** + baseline → OOM at 2, 4, 8 GiB; boundary predicted between 12 and 16 GiB. Blob control
  ≈ 2 × 264 MiB × 2.2 ≈ 1.2 GiB → survives at the largest failing map budget. 8 MiB send+receive endpoint
  reserves → 2 × 24 MiB × 20 ≈ 1 GiB → survives.

## 5. Phases, arms and decision rules

Each arm from a clean start. n/N reported per arm type and budget. Heap dumps on for map positives
(`HEAPDUMP=1`), off for controls and interventions.

- **D — deployment candidate: default timeouts, no Byteman, stall on V1+V2.**
  D0 map at S 2 GiB (n = 1, also confirms reachability: S→V1/V2 messages sent, client ok counts, stall
  visible in V stage pending). Then the budget search: if 2 GiB fails, go up (4 → 8 → …) with n = 1 per
  step, refine, then ×3 map at the largest failing budget; if 2 GiB survives, go down (1 GiB, then
  1.5 GiB or 768/512 MiB) the same way. Endpoint = heap OOM (`java.lang.OutOfMemoryError` in S's
  `system.log` / `ReportJavaOutOfMemory`) or service loss (default criterion: ≥ 90% of wall time in Full
  GC over ≥ 60 s, `gcpeak.sh`). At the largest failing budget: blob ×3, intervention ×3.
- **P — causal intervention for the callback path (diagnostic patch, separate build).** Only if phase D
  or X fails with S's send queue far below C. Patch: `StorageProxy.java:1391` passes `null` instead of
  `mutation.hintOnFailure()` when `DatabaseDescriptor.hintedHandoffEnabled()` is false (hints are off
  here, so no hint is lost). Build copy `/mydata/b6/cassandra-p4`, diff saved in `harness-run4/`. ×3 at
  the failing condition.
- **R — reserve intervention:** send + receive endpoint reserves 8 MiB on all instances (as run 3), ×3
  at the largest failing budget of each phase that fails.
- **X — diagnostic fallback (only if D does not fail at ≥ 512 MiB, or after D to answer the
  ≥ 2-slow-replica question at large heaps):** as D plus `write_request_timeout=60000ms`,
  `native_transport_timeout=60000ms` on all instances (supporting deviation; no Byteman). Budget search
  2 → 4 → 8 → 12 → 16 GiB (n = 1 each until the first survival), then ×3 map at the largest failing,
  blob ×3, reserves ×3 there.
- **H — one diagnostic histogram arm** (intrusive `GC.class_histogram` at t ≈ 70 s) at the failing
  condition, to attribute U to `Mutation`/cells separately from K. Not counted in V1.

**Decision rules.** A failing condition needs ≥ 3/3 (or n/N stated) from clean starts at one budget. If
the same-condition repeats disagree, add up to 2 repeats and report n/N. The largest failing budget is
the largest with ≥ 1 failure in the search and then ≥ 3 failures in its repeats; the first budget with
0/1 (confirmed by a second survival) is the boundary.

**Labels.** Phase D result → `deployment` if it meets V1–V7 (defaults, budget ≥ 512 MiB, external fault,
no instrumentation). Phase X → `diagnostic` (raised timeouts). Phase P is an intervention only.

## 6. Stopping budget

≤ 8 h wall time from the first arm, ≤ 45 arms in total; abort after 2 consecutive RING FAILs. No
escalation after an OOM beyond the planned budget search. At the end: `harness-run4/ctl.sh stop all`,
slow-disk delay 0 (`dmsetup table b6slow`), `pgrep java` empty. The b6slow dm-delay device and its loop
file predate this run (run 2) and are left in place at delay 0; run 4 creates no new device.

## Amendment A1 (2026-11-11, ≈ 23:00, after readings of D 2G/1G/768M/640M/512M r1–r3 and blob r1)

**Observed so far (phase D):** S survived at 2 GiB, 1 GiB, 768 MiB, 640 MiB (live after Full GC 63–89%,
max 60 s pause share 40–82%); at 512 MiB map: r1 heap OOM + service loss, r2 survived (84%), r3 heap
OOM + service loss. The dumps show the holder: ≈ 1 850 `Mutation`s ≈ 460 MiB reachable through
≈ 1 850 `WriteResponseHandler`s (callbacks), **13** queued `Message`s (send queue ≈ empty).
**Blob r1 at 512 MiB also died of heap OOM** (t = 39 s): with the uncapped client, blob writes run at
several times the map rate (they are cheap to apply), so rate × 2 s × 23.6 KiB also fills 512 MiB. The
uncapped blob arm is therefore **not a matched control** (it offers far more on-wire bytes per second);
its r2–r3 still run in the batch and are reported as "blob, uncapped rate".

**Changes (before the readings they affect):**
1. **Rate-matched controls.** `harness-run4/B6Load.java` (= run-2 client + optional total rate cap,
   Guava `RateLimiter`), `RATE=2000` writes/s ≈ 21.6 MiB/s on-wire — at least the map arms' healthy rate
   (≈ 1.8–2.1k/s). Arms: blob at 2 000/s ×3 at 512 MiB (`R4D_S512m_blob_rate2k_r*`), and map at
   2 000/s ×1 to show the cap does not by itself change the map outcome.
2. **Decision rule applied:** map at 512 MiB is 2/3 → two more repeats (r4, r5); report n/N.
3. **Outcome markers:** Cassandra's `system.log` is starved at these OOMs (no `OutOfMemoryError`
   line), so heap OOM is read from HotSpot's `HeapDumper` / `ReportJavaOutOfMemory` safepoints in the GC
   log and the dump (`harness-run4/gcwin.py`); service loss uses **all** STW pauses over a sliding
   ≥ 60 s window (`gcwin.py`), the protocol's literal default criterion (`gcpeak.sh`'s > 95%-of-heap
   filter misses spirals that settle at 92–94% of a small heap). `launch.log` / `debug.log` are kept
   from now on for HotSpot's own OOM report.
4. Phase X then runs as designed (`harness-run4/batch-x.sh`).

## Amendment A2 (2026-11-12 02:05, resuming after an agent usage cut-off; all chained batches had completed)

Readings since A1: map 512 MiB r4 service loss, r5 survived (89% max-60 s); rate-capped blob 0/3;
rate-capped map 1/1 OOM; reserves 8 MiB 3/3 OOM; **diagnostic patch 3/3 OOM at t ≈ 51 s** (dumps were
off). Phase X: 2 GiB service loss, 4 GiB OOM 3/3, 8 GiB survived 2/2 (≈ 99% live after Full GC, max
60 s pause share 74–83%), blob 4 GiB 0/3, reserves 4 GiB 3/3 survived. Final batch (`batch-r.sh`):
(1) rerun the uncapped blob r3 that the tool time limit interrupted; (2) one patched and one reserve arm
at 512 MiB **with heap dumps** (diagnostic, not counted in V4 n) to identify the holder that kills the
512 MiB coordinator when the callback path is removed; (3) phase-X bisection at 6 GiB (n = 1; if it
fails, ×2 more; if it survives, confirm once). Stop after this batch regardless of outcome (≈ 5 h used).

## Amendment A3 (2026-11-12 02:48, after 6 GiB r1–r2, before r3's reading)

6 GiB failed r1 and r2 (service loss, heap OOM). The matched blob and reserve controls ran at 4 GiB
(the largest failing budget known when `batch-x.sh` ran). If 6 GiB r3 also fails, blob ×3 and send +
receive 8 MiB reserves ×3 are run at 6 GiB (`batch-x6.sh`) so that V2/V4 are tested at the largest
failing budget; if r3 survives, 6 GiB is reported as n/3 and nothing more is run. Hard stop at
2026-11-12 05:30 (8 h after the first arm).
