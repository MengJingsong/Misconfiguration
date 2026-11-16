# S2 design — heap combo: coordinator write retention (B6) + memtable + key/counter caches + flush overlap

Written 2026-11-16 ≈ 13:00–13:20 EST, **before any reading**. Campaign row S2 (S = combo, convergence +
bypass, `combo-playbook.md`); sources B6 (B = bypass: internode queue accounting mismatch), B7 (bypass: cache
weigher overhead), C2 (C = convergence: concurrent reads), R3/R4 (R = recheck of pre-protocol cases).
Agent run, one session, controller `pc96`.

**Time budget (stopping rule).** Hard: start ≈ 12:55 EST, stop measuring by 15:35 EST, all apt processes
stopped and evidence copied to `pc96:/mydata/s2-evidence/` by 15:45 EST (apt nodes are reclaimed 16:00).
At most ≈ 14 arms of ≈ 8 min. If the endpoint is not reached or repeated by then, file `candidate` with the
stage reached. No escalation after an OOM beyond the planned heap search.

## 1. Topology and roles

| Role | Node | Build (read-only) | Heap | Disk |
|---|---|---|---|---|
| V — victim: coordinator for every client write **and** a replica (dc `c`) | `apt140` (10.10.1.1), 8 c / 16 thr, 15 GiB | `~/cassandra-b1` (5.0.9) | **2 GiB** first; search upward 3 → 4 GiB | `/mydata/s2/V` (local, healthy) |
| R — slow replica (dc `r`) | `apt149` (10.10.1.5) | `~/cassandra-c1` (5.0.9) | 8 GiB | data/commitlog/hints on a dm-delay device over a loop file in `/mydata/s2/` |
| client | `apt138` (10.10.1.3) | jars of `~/cassandra-c1` | — | — |

Keyspace `s2` = `NetworkTopologyStrategy {c:1, r:1}`, writes at CL=ONE, client whitelisted to V only
(B6Load, run-4 version). Hence every write: V applies it locally (memtable, acks the client) and sends it to R;
the V-side write handler keeps the `Mutation` (`hintOnFailure`) until R answers or the callback expires.
Cache keyspace `s2c` = `NTS {c:1}` (V only). `num_tokens: 1`, GossipingPropertyFileSnitch (environment).

**Fault (external, labelled).** At t = 20 s into the load, R's disk write latency := 30 s via dm-delay
(as B6 condition A; a storage *stall*, not disk exhaustion); reset to 0 at the end of the load. R stays alive in
gossip, stops acknowledging (blocked `MutationStage`/commit log). This is an external fault, not a
supporting deviation (B6 A precedent, `deployment`). No Byteman, no patches, no timeout changes.

## 2. Stage-0 ceiling sheet (heap domain, V)

Resolved at V's heap H (cassandra.yaml of 5.0.9, `DatabaseDescriptor`):

| Pool | Domain | Contract C (default rule, resolved) | Reachable multiplicity (bound, source) | Predicted max U at H = 2 GiB | Counting basis of K |
|---|---|---|---|---|---|
| Baseline (schema, metrics, Netty, gossip) | heap | — | — | 100–200 MiB | — |
| **Stage 1:** retained `Mutation`s of outstanding writes to R (write handler `hintOnFailure`, `AbstractWriteResponseHandler.java:81,309`; callback in `RequestCallbacks`, expires at `message.expiresAtNanos` = `write_request_timeout` **2000 ms**, yaml l.1330) and the same objects queued in V's outbound connection to R | heap | **No byte contract for the callbacks** (K = none); outbound queue: on-wire 4 MiB per link + 128 MiB endpoint + 512 MiB global (`OutboundConnection.java:330`) | one per outstanding write: rate × 2 s (callback lifetime; queue entries expire on the same deadline). Rate bound: client in-flight (sessions × 256, client-set) and V's own local write path (`concurrent_writes` 32, `native_transport_max_threads` 128) | map (1000 tiny cells, 213 KiB heap, B6 run 1): rate × 2 s × 213 KiB = **416 MiB per 1k writes/s**; blob (11 000 B, 23.6 KiB heap): 46 MiB per 1k/s | outbound `pending_bytes` (on-wire, ≤ 132 MiB) |
| **Stage 2a:** memtable (`memtable_allocation_type: heap_buffers`, yaml l.825) | heap | `memtable_heap_space` = ¼ heap (`DatabaseDescriptor.java:586–587`) = **512 MiB** at 2 GiB (1 GiB at 4 GiB); flush at `memtable_cleanup_threshold` = 1/(1+2 flush writers) = 0.33 → ≈ 171 MiB; writers block at C | one pool (live + flushing memtables share it) | ≤ 512 MiB counted; real U vs K measured (map cells: unknown ratio) | memtable pool `owns` (on-heap) |
| **Stage 2b:** key cache, filled by distinct reads of 8-byte keys | heap | `key_cache_size` auto = min(5 % heap, 100 MiB) = **100 MiB** at ≥ 2 GiB | one cache | 100 MiB counted; **214 MiB** real (B7 2.14×) | Caffeine weight (`Size`) |
| **Stage 2b:** counter cache, filled by distinct counter updates | heap | `counter_cache_size` auto = min(2.5 % heap, 50 MiB) = **50 MiB** | one cache | 50 counted; **90 MiB** real (B7 1.80×) | Caffeine weight |
| **Stage 2c:** flush overlap (`nodetool flush s2` at t = 85 s, mid-stall) | heap | covered by the memtable pool (flushing memtable stays charged until written) | one flush per table | transient: writer buffers, ≤ few tens of MiB | memtable pool |
| C2 concurrent reads' working sets | heap | per-query thresholds only | — | **not run in S2** (time); listed as the next layer | — |
| Hint buffers (hints on, default) | **direct**, not heap | 32 MiB slabs | — | not in this domain; recorded | — |

**Ceiling (2 GiB).** Baseline 150 + stage 1 (map) 416 × r + memtable ≤ 512 + caches 304 (real) + overlap ≈ 30
→ 1.0 GiB + 0.41 GiB × r (r = write rate in k/s). Budget 2048 MiB is reached at r ≈ 2.5 k map writes/s (if the
memtable sits at its cap), or ≈ 3.3 k/s with the memtable near its flush threshold (171 MiB). B6 measured
≈ 2.3 k map writes/s through one coordinator on pc96 (32 cores); apt140 has 8 cores and also writes locally,
so **r is the decisive unknown**: the stage is feasible only if r ≳ 2.5 k/s (or if retention lasts longer than
2 s, e.g. queue entries not pruned until a later enqueue). Blob (stage 1–2 without the B6 gap): 150 + 46 r +
512 + 304 ≈ 1.1 GiB at r = 3 k/s → **predicted negative, ≈ 0.9 GiB headroom**.
At 4 GiB: memtable C = 1 GiB, caches unchanged → map ceiling 1.5 GiB + 0.41 r → needs r ≳ 6 k/s: predicted not
reachable. At the auto heap for apt140 (`cassandra-env.sh`: min(½ RAM, 15872) ≈ 7.5 GiB) not attempted.

## 3. Protection map (summary; full rows in §2)

| Domain | Allocation / owner / release | Local contract | Aggregate coverage | Lifetime | Budget |
|---|---|---|---|---|---|
| Coordinator retained mutations | `Mutation` decoded from the CQL request, referenced by the write handler (hint on failure) and the outbound `Message` | none in bytes; time-bounded by `write_request_timeout` | none (no counter charges the after-flush copy; on-wire queue counters only while queued) | until R acks or 2 s expiry | heap |
| Memtable | `Memtable` partitions/cells (heap_buffers) | `memtable_heap_space` | global pool, blocks writers | until flushed | heap |
| Key / counter cache | `CaffeineCache` entries | `key_cache_size` / `counter_cache_size` (weigher omits ≈ 90 B/entry, B7) | per cache | standing | heap |

Scope rule: stage-1 retention is compared with the **write timeout bound** (implicit, rate × timeout × size, not
a memory limit → *unprotected accumulation* if it alone fails); the queues' on-wire K vs heap U is the B6 gap;
cache U vs C is the B7 gap.

## 4. Configuration and budget audit

- V6: every constraint at its shipped default, resolved at V's heap: memtable_heap_space ¼ heap, caches auto
  (100/50 MiB at 2 GiB), internode queue capacities default, `write_request_timeout` 2 s, `native_transport_timeout`
  default, `concurrent_writes` 32, hints on (default), `memtable_allocation_type` default.
- Environment changes (disclosed): cluster name, addresses, `num_tokens: 1` + `initial_token`, snitch, seed,
  directories, `auto_bootstrap: false`, JMX port. GC: shipped G1 options.
- V7: V heap 2 GiB (ideal per standing rule) and the upward search 3 → 4 GiB (≥ 512 MiB → no per-case review
  needed). Direct memory at the `cassandra-env.sh` resolution (not limited further). The node's own auto heap
  (≈ 7.5 GiB) is above the search range; the 15 GiB node caps the search at 8 GiB.
- Faults: dm-delay stall of R's disk (external). Workloads (map vs blob payload, cache fill, flush) are
  experimental variables. Client: Java driver 3.12, CL=ONE, 8 sessions × 256 in flight unless stated.

## 5. Arms (in order) and predictions

Every arm is a clean start (both nodes regenerated from the build's conf, data dirs wiped, schema re-created).
Load 150 s; stall from t = 20 s to end of load; observe 60 s after.

| # | Arm | Stage | Payload | Caches filled | Flush at 85 s | Purpose | Prediction (2 GiB) |
|---|---|---|---|---|---|---|---|
| 1 | `st1-blob` | 1 | blob | no | no | stage-1 ledger without the gap | survives, live ≤ 40 % |
| 2 | `st2-blob` | 2 | blob | yes | yes | stack without the B6 gap (also the matched-payload control) | survives, live ≤ 60 % |
| 3 | `st3-map` | 3 | map | yes | yes | full stack + B6 gap | heap OOM or service loss if r ≳ 2.5 k/s; else survive with headroom 0.41 × (2.5 − r) GiB |
| 4 | `st1-map` | 1 + gap, layers off | map | no | no | intervention "remove stacked layers" (caches unfilled, no forced flush) | survives if the caches' 0.3 GiB were needed |
| — | repeats | | | | | endpoint ×3, control (`st2-blob`) ×3, intervention ×3 | |
| — | heap search | | | | | `st3-map` at 3 GiB, then 4 GiB, if 2 GiB fails | 3 GiB borderline, 4 GiB survives |

If `st1-map` also fails, the stacked layers are not needed and the endpoint is stage-1 + gap (B6 condition E
shape at 2 GiB); the intervention then becomes a lower client in-flight (1 session × 256) to bound multiplicity.

**Measurement per arm.** GC log (shipped unified logging) → post-GC live (`gcpeak.sh`), worst-60 s STW share
(`gcwin.py`; service-loss criterion = protocol default ≥ 90 % over ≥ 60 s). Every 5 s on V: `GC.heap_info` (no
forced GC), outbound `pending_bytes/count` to R (`system_views.internode_outbound`), memtable K
(`nodetool sjk mx` or `tablestats` memtable data size), cache K (`nodetool info`). Client completed writes/s and
errors. One diagnostic class histogram (`jcmd GC.class_histogram`, forces a full GC) at t = 120 s in the first
`st3-map` and `st2-blob` arm only (intrusive; marked). OOM: heap dump → per-class histogram with
`hprofhist.py`, then the dump is deleted unless small. R: GC log only.

**Endpoints.** Heap OOM of V (`java.lang.OutOfMemoryError` in system.log / `ReportJavaOutOfMemory` in gc.log /
dump), GC service loss of V (criterion above), or survival with headroom = 2048 − peak post-Full-GC live.

**Planned interventions** (one per ingredient): (a) layers off (`st1-map`); (b) gap off (`st2-blob`, matched
on-wire payload); (c) multiplicity: fewer client sessions (if time).

## Amendment A1 — 2026-11-16 13:16 EST (after arm `st1-blob-r1`, before any further reading)

**What arm 1 showed** (`st1-blob-r1`, stage 1, blob, 2 GiB, 8 sessions × 256, no fill/flush; one void attempt
before it: harness bug, `pkill -f` matched its own ssh command, no load ran): V died of **heap OOM ≈ 15–25 s
into the load, before the stall began** (the stall starts at t = 20 s; the client's ok-rate was already 0 at
t = 15 s; first Full GC at 2.09 GB 14 s into the load). The dump (2.2 GB) holds **61 923 `Mutation`s, each
with a `WriteResponseHandler` and a `StorageProxy$4`** (= `LocalMutationRunnable`, `StorageProxy.java:1676`,
verified with `javap`), 46 790 memtable partitions, 1 836 MiB of `byte[]`; only 122 `CallbackInfo` and 104
`Message`s. So the holder is **not** the predicted stage-1 holder (callbacks to a slow replica bounded by
rate × 2 s) but **V's own local writes queued on `MutationStage`** behind a memtable at its cap; the client's
CL=ONE acks come from R (8 GiB, faster), so the client's in-flight limit and the native-transport in-flight
byte limit (released when the response is sent) do not bound V's local backlog. Outbound queue to R also hit
its 130 MiB cap 4 s into the load (overload drops → hints).

**Amended plan** (stall dropped — not needed and not part of the endpoint; each arm `STALL=0`, `FILL=0`,
`FLUSH=0`, `LOAD=90`, R 8 GiB unchanged, everything else as §1/§4):

| Arm | Condition | n | Role | Prediction |
|---|---|---|---|---|
| `E-blob-2G` | blob, 2 GiB, 8 × 256, uncapped, CL=ONE | 3 | endpoint (V1) | heap OOM 3/3 within 60 s |
| `ctl-rate-2G` | same, client rate capped at 2 000 writes/s total | 3 | matched control, lower offered load (V2) | survives, live < 50 % |
| `int-lone-2G` | same as `E`, but **CL=LOCAL_ONE** (V's own write must ack; client in-flight then bounds V's local backlog) | 3 | intervention (V4) | survives 3/3; throughput recorded |
| `E-blob-4G`, `E-blob-8G` | heap search upward | 1 each (+2 at the largest failing) | V7 search | 4 GiB likely fails (memtable cap 1 GiB scales with heap, backlog grows with offered rate); 8 GiB open |
| `E-map-<H>` | stage 3 (B6 tiny-cell gap) at the smallest heap where blob survives | 1–3 | gap stage | fails where blob survives if the 213 KiB/mutation heap size dominates |
| stage-2 cache fill | only if time remains | — | — | — |

The planned dm-delay stall (B6 shape) and the coordinator-callback retention stay **untested** in S2 (recorded as
not reached). Measurement unchanged, plus MutationStage pending/blocked from `nodetool tpstats` in the sampler.
Client CL is set with `-Dcl=` (S2Load change, below).

## Amendment A2 — 2026-11-16 14:18 EST (after the 8 GiB arm, before batch-3 readings)

Readings so far: blob endpoint condition OOMs at 2 GiB (3/3, plus `st1-blob-r1`) and 4 GiB (1/1); 8 GiB survived
90 s of load (post-Full-GC 35 %, `MutationStage` pending up to 25 620). Matched control (2 000 writes/s) 3/3 and
CL=LOCAL_ONE 3/3 survived at 2 GiB. Remaining time ≈ 75 min, so:

1. `E-blob-4G` r2, r3 (largest failing heap, V1 there).
2. At 8 GiB (stage-1 negative with headroom), per the combo playbook: **stage 2** `st2-blob-8G` = caches filled
   to their default caps (100 / 50 MiB) + `nodetool flush b6` at t = 85 s, blob; then **stage 3** `st3-map-8G` =
   same + map payload (1 000 tiny cells, B6 heap/on-wire ≈ 19.7×). Prediction: stage 2 survives (adds ≈ 0.3 GiB
   real cache heap); stage 3 OOMs if ≥ ≈ 25 k map mutations queue (25 k × 213 KiB ≈ 5.1 GiB + memtable ≤ 2 GiB).
3. If time remains: repeat `st3-map-8G`. 8 GiB dumps are deleted unanalyzed (an 8 GB hprof cannot be parsed and
   copied back before 15:45); their evidence is the GC log and the safepoint markers.
The 4 GiB dump of `E-blob-4G-r1` was parsed on apt140 pinned to core 15 at `nice 19` while `E-blob-8G-r1`
ran (disclosed perturbation: 1 of 16 hardware threads).

## Amendment A3 — 2026-11-16 14:43 EST (after `st3-map-8G-r1`, before batch-5 readings)

Readings: 4 GiB blob stage 1 OOM 1/3 (survivors at 82.5 % and 96.4 % post-Full-GC live); 8 GiB stage 2 (caches at
100 / 50 MiB K, flush) survived at 35.5 %; 8 GiB stage 3 (map) survived at 57.5 % live, worst-60 s STW 52 %, map
rate only ≈ 1.1 k/s. Batch 4 was stopped after it had launched V for `st1-map-8G-r1` (no load ran; arm void).
Remaining time goes to the boundary heap instead: **`st2-blob-4G` ×3** (stage 1 + caches filled to their
default caps + flush at 85 s, blob, 4 GiB). Prediction: the layers add ≈ 0.3 GiB real heap (B7) + flush overlap
to a heap that already sits at 82–96 % live, so OOM in ≥ 2/3. This compares with `E-blob-4G` r1–r3 (stage 1
alone, 1/3) as the layer-off arm. Folder renamed to `coordinator-local-write-backlog--combo` (14:20) to match
the holder found.

## Amendment A4 — 2026-11-16 14:45 EST (before batch-5/6 readings)

After batch 5, if time allows (no arm starts after 15:24 EST): **`Eeq-blob-2G`** ×2 = condition A with R at a
2 GiB heap too (equal heaps; `arm6.sh` = `arm.sh` with `RX`). Question: does the OOM need a replica that is faster
because it is bigger? Prediction: V still OOMs (R, also at 2 GiB, may OOM too; whichever replica acks first
releases the client slot), but the backlog may split between both nodes.
