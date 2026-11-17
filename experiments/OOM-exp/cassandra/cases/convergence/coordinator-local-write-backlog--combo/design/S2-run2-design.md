# S2 run 2 design — equal-heap RF=3 follow-up on Utah m400 (aarch64)

Written 2026-11-16 ≈ 21:30 EST, **before any reading of run 2**. Campaign row S2 (S = stacked combo case,
`combo-playbook.md`). Run 1 (2026-11-16, x86 APT nodes) verified condition A: heap OOM 3/3 of a 2 GiB victim V
whose own CL=ONE local writes queue on `MutationStage` while a faster replica (8 GiB heap) acknowledges first.
With one equal 2 GiB replica V survived 1/1 (81 % live). The researcher queued an equal-heap RF=3 ring ×3.
One agent, controller `pc96`.

**Question.** Does the local-write backlog form, and does V die of heap OOM, when V's replicas are no faster than
V (all heaps 2 GiB, RF=3, CL=ONE, shipped defaults)? And the in-between: RF=3 with two faster (8 GiB) peers.

**Time budget (stopping rule).** Start ≈ 21:15 EST; node setup until ≈ 22:00; arms until ≈ 01:45; all processes
stopped and verified by ≈ 02:00; filing by ≈ 02:15. Arm ≈ 7 min. No arm starts after 01:35.

## 1. Platform and topology

| Role | Node | LAN IP | Heap | Notes |
|---|---|---|---|---|
| V — victim: coordinator for every client write **and** a replica | `ms0640` | 10.10.1.2 | 2 GiB | seed, `initial_token` −2^63 |
| R1 — replica | `ms0604` | 10.10.1.3 | 8 GiB (A, G2) / 2 GiB (G1) | |
| R2 — replica (RF=3 arms only) | `ms0611` | 10.10.1.4 | 8 GiB (G2) / 2 GiB (G1) | |
| client | `ms0617` | 10.10.1.5 | — | S2Load (run 1's, `-Drepl` added), 8 sessions × 256 in flight, all to V (whitelist) |

All four: Utah m400, aarch64 (APM X-Gene, 8 cores), 62 GiB RAM, 8 GiB swap on, Ubuntu 22.04, kernel 5.15,
cgroup v2, OpenJDK 11.0.33 (apt), Ant 1.10.12. One build: repository `systems/cassandra/source/` (5.0.9) copied with
`copy-source.sh` to `/mydata/s2r2/cassandra` on ms0640, `ant jar`, rsynced to the other three. **Never compared
arm-by-arm with run 1's x86 arms** (platform rule): run 2 has its own positive control.

Each server JVM runs in `systemd-run --user --scope -p MemorySwapMax=0` (no `MemoryMax`: the budget is the Java
heap; swap 0 so the heap cannot be paged out), linger enabled for the run and disabled after. `memory.current` of
the scope is sampled (no `memory.peak` on 5.15).

Topologies (`num_tokens: 1`, fixed `initial_token`s, GossipingPropertyFileSnitch):
- **A** (run 1's): V in dc `c`, R1 in dc `r`, keyspace `b6` = `NTS {c:1, r:1}`; R2 not started.
- **G** (RF=3 single DC): V, R1, R2 in dc `c`, `b6` = `NTS {c:3}`; every node holds every key.

## 2. Ceiling sheet (unchanged from run 1, resolved at 2 GiB)

Holder: `LocalMutationRunnable` (`StorageProxy$4`) → `Mutation` queued on `Stage.MUTATION` (unbounded), ≈ 30 KiB
heap per 11 000 B blob write (run 1). C = none, K = none. Memtable C = ¼ heap = 512 MiB. Caches empty. Run 1 OOM
at ≈ 61.5 k queued. `MaxDirectMemorySize` auto = ¼ RAM = 15 872 MiB (not the domain). V7: 2 GiB = ideal
(standing rule); the m400's own auto heap would be min(½ RAM, 15 872 MiB) = 15.5 GiB.

**Mechanism prediction for equal heaps.** The backlog grows when the offered rate exceeds V's local apply rate
while the client slot is released by another replica's ack. With equal heaps a replica is not bigger but is still
**less loaded** than V: V also decodes every CQL request, serializes and sends each mutation to 1 (A) or 2 (G)
replicas and processes their responses. So V's local apply should still lag the replicas'; with RF=3 the client is
released by the faster of **two** replicas. Run 1's single equal-heap arm built 43 k pending and reached 81 % live.

## 3. Arms (each ×3, clean starts, identical client load: blob 11 000 B, 8 × 256, CL=ONE, 90 s, 60 s observe)

| Order | Arm | Topology / heaps | Role | Prediction |
|---|---|---|---|---|
| 1 | `A-2G` r1–r3 | A, V 2 G, R1 8 G | same-platform positive control (run 1 condition A) | heap OOM ≥ 2/3 **if** the m400 client offers more than V's local apply rate; if not (slower client), no backlog — then report before going on |
| 2 | `G1-2G` r1–r3 | G, all 2 G | the question | backlog forms (max pending ≥ 20 k); OOM 1–3/3 (uncertain; run 1's RF=2 equal-heap arm reached 81 %) |
| 3 | `G2-2G` r1–r3 | G, V 2 G, R1 = R2 = 8 G | in-between | heap OOM 3/3 (two faster peers) |
| 4 | interventions for each failing condition | A: CL=LOCAL_ONE (run 1's); G: client rate cap below V's measured local apply rate (run 1's control shape; value fixed from the A/G readings before it runs and recorded as an amendment) | V4 ×3 | survive 3/3 |
| 5 | if G1 survives at 2 GiB: `G1-<smaller>` (all nodes equal, ≥ 512 MiB), labelled **boundary probe** | | | |
| 6 | if time: `Eeq-2G-long` (A with R1 2 G, 300 s load) | | run 1's next step (1) | |

Interleaving: A first (×3, the go/no-go), then G1 and G2 interleaved per repetition.

**Measurement per arm (all nodes).** Shipped unified GC log → max post-Full-GC (`gcpeak.sh`), worst-60 s STW share
and the protocol's service-loss criterion over all pauses (`gcwin.py`), `HeapDumper`/`ReportJavaOutOfMemory`
safepoints. Sampler (nice 10) every ≈ 5–15 s: `jcmd GC.heap_info` (no forced GC), scope `memory.current` /
`memory.swap.current`, `nodetool tpstats` (`MutationStage` active/pending), on V also `nodetool info`, memtable data
size, outbound pending. OOM: shipped `HeapDumpOnOutOfMemoryError` → dump moved to the node's `/mydata/s2r2/dumps/`
and reduced to a class histogram (`hprofhist.py`, `Mutation` / `StorageProxy$4` counts). Client: completed writes,
errors, 5 s rates.

**Endpoints.** Heap OOM of V; GC service loss of V (protocol default ≥ 90 % STW over ≥ 60 s); else survival with
headroom = 1 − max post-Full-GC live / heap.

**Status rules fixed now.** A on aarch64 reproduces if ≥ 2/3 OOM (it is a platform check of a verified condition).
G1 / G2: `verified-OOM · deployment` proposal only with V1 (≥ 3 failing), V2 (matched control ≥ 3: the A-platform
LOCAL_ONE/rate-cap arms or the condition's own rate cap), V4 (intervention ×3), V5 (dump). G1 3/3 survive with
no service loss and V1–V3 met → `negative` within the stated range (2 GiB, 90 s burst, this client).

## Amendment R2-A1 — 2026-11-16 22:02 EST (after A r1–r4 and G1-2G-r1; before reading G2 or any intervention arm)

**Readings so far.** A (aarch64): heap OOM in the shakedown arm r1 (old nodetool sampler) and r2–r4 3/3 (JMX poller),
62–64 k queued `Mutation` = `StorageProxy$4` in the dumps, service loss in r2–r4. Go: the platform reproduces
run 1's condition A. G1-2G-r1 (all 2 GiB, RF=3): V heap OOM, 62.7 k pending on V, replicas' `MutationStage` pending
≤ 77. V's local apply ≈ 2.9 k writes/s from `MutationStage` completed tasks (in steps), replicas ≈ 3.7 k/s; client
offered 3–6 k/s.

**Interventions and controls (×3 each, interleaved by repetition), batch 2:**
1. `G1-all-2G` — G1 with **CL=ALL**: the LOCAL_ONE-style intervention for a single-DC ring (LOCAL_ONE = ONE there):
   the client slot is released only after V's own local write has applied, so the client window bounds V's backlog.
2. `G1-rate-2G` — G1 with the client capped at **1 500 writes/s** total (run 1's control shape; ≈ 0.5 × V's
   measured apply rate, as run 1's 2 000/s was ≈ 0.6 × its LOCAL_ONE throughput).
3. `A-lone-2G` — A with **CL=LOCAL_ONE** (run 1's intervention, same platform).
4. `G2-all-2G` — G2 with CL=ALL, only if G2 fails.
Predictions: all survive 3/3; CL=ALL completes ≥ the uncapped arms' pre-OOM writes.

Batch 3 if time (no arm after 01:35): `Eeq-2G-long` (A with R1 2 GiB, LOAD=300) ×3 — run 1's next step (1); then
the upward heap search for G1 (`G1-4G`, all nodes 4 GiB) ×1–3. The ≥ 512 MiB boundary probe is dropped (G1 failed
at 2 GiB).

## Amendment R2-A2 — 2026-11-16 22:33 EST (after batch 1: A 3/3 + shakedown, G1 3/3, G2 3/3 heap OOM; before any batch-2 reading)

Batch 3 order fixed: **`G1-4G` ×3 first** (protocol: search upward for the largest failing budget; all three nodes
4 GiB, so the ring stays equal-heap), then **`Eeq-2G-long` ×3** (A topology, R1 2 GiB, 300 s load). Prediction:
G1-4G OOM ≥ 1/3 (needs ≈ 129 k queued at ≈ 30 KiB; a 90 s burst with offered − apply ≈ 1–3 k/s may fall short:
run 1's 4 GiB A was 1/3). Eeq-2G-long: OOM ≥ 2/3 (G1 shows an equal-heap peer still out-acks V on this platform).
Dumps beyond one per condition are reduced to histograms and deleted from V (disk 37 GiB).

## Amendment R2-A3 — 2026-11-16 23:40 EST (after batch 2 and G1-4G-r1; before the other batch-3 readings)

Batch 2: all 12 arms survived (G1 CL=ALL, G1 rate cap 1 500/s, A CL=LOCAL_ONE, G2 CL=ALL, each 0/3). G2 has no matched
control of its own yet (V2), so **batch 4 = `G2-rate-2G` ×3** (G2 with the 1 500/s cap), after batch 3, same cutoff
(no arm after 01:35). Prediction: survives 3/3.

## Amendment R2-A4 — 2026-11-16 23:50 EST (after G1-4G r1–r3; before the Eeq-2G-long and G2-rate readings)

G1-4G r1–r3: V alive when the harness stopped it 60 s after the client exited, but at 97.4–98.0 % post-Full-GC live,
with GC service loss in r2 and r3 (67 s, 84 s windows ≥ 90 % STW). At 2 GiB, OOMs came up to 320–460 s after load
start, i.e. after a 60 s observation window would have ended. So the 4 GiB outcome is censored by the window.
**Batch 5 = `G1-4G-obs300` ×3**: G1 at 4 GiB, identical load, observation 300 s after the client exits (`OBS=300`),
after batch 4, same cutoff (no arm after 01:35). Prediction: heap OOM ≥ 2/3 (the backlog does not drain once V is in
back-to-back Full GCs). The 2 GiB arms' outcome is not affected (all OOMed within their windows).

## Amendment R2-A5 — 2026-11-17 00:15 EST (after Eeq-2G-long r1–r3; before the G2-rate and G1-4G-obs300 readings)

Eeq-2G-long (A topology, R1 2 GiB, 300 s): heap OOM 3/3 within 92 s. To give it its own intervention (V4),
**batch 6 = `Eeq-lone-2G-long` ×3**: same topology and 300 s load with CL=LOCAL_ONE (run 1's intervention), after
batch 5, same cutoff (no arm after 01:35). Prediction: survives 3/3. No rate-cap control for this topology (time).
