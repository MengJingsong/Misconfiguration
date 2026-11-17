# S2 — run history (coordinator's own local-write backlog, heap combo)

The per-run case files of S2 kept verbatim after their conditions were consolidated into
[`coordinator-local-write-backlog--combo.md`](coordinator-local-write-backlog--combo.md)
(filing rule: protocol *Case evidence and batch status*, amended 2026-11-11). Only mechanical changes: every
heading is demoted one level. Relative links to `design/`, `harness*/` and `logs*/` are unchanged. Run 1's case
file is the final file itself (its conditions A–C and text were kept in place), so only run 2 is here.

| Run | Original file |
|---|---|
| Run 1 — 2026-11-16: victim 2 GiB + faster 8 GiB replica (x86, apt140/149/138) | the final file, [`coordinator-local-write-backlog--combo.md`](coordinator-local-write-backlog--combo.md) |
| [Run 2 — 2026-11-16/17: equal-heap RF=3 ring (aarch64, Utah m400)](#run-2) | `coordinator-local-write-backlog--combo--run2-equal-heap.md` (moved here 2026-11-17) |

---

<a id="run-2"></a>

## S2 run 2 — the local-write backlog without a faster replica: equal-heap RF=3 ring (Utah m400, aarch64)

**Campaign row:** S2 (S = stacked combo case, per [`combo-playbook.md`](../../../../combo-playbook.md)), run 2 = the
follow-up the researcher queued on 2026-11-16 after S2 run 1 (final file
[`coordinator-local-write-backlog--combo.md`](coordinator-local-write-backlog--combo.md), not edited here).
**Domain:** Java heap of the victim. **Stage:** 1 only (multiplicity = offered write load; no stacked layers,
no accounting gap). **Regime:** default constraints. **Source:** Cassandra 5.0.9 (repository
`systems/cassandra/source/`, repo HEAD `ff569335`), one `ant jar` build on `ms0640`, same tree on all nodes.
**Run:** S2 run 2, 2026-11-16 21:15 – 01:21 EST, one agent, controller `pc96`; design
[`design/S2-run2-design.md`](design/S2-run2-design.md) (written before readings; amendments R2-A1 22:02,
R2-A2 22:33, R2-A3 23:40, R2-A4 23:50, R2-A5 00:15 EST, each before the readings it plans). **Platform: aarch64** (Utah m400): never pooled with run 1's x86 arms; run 2 has its own
positive control.

**Question.** Run 1 verified the OOM with a replica *faster* than the victim (8 GiB vs 2 GiB heap); one equal-heap
RF=2 arm survived (81 % live). Does the backlog form, and does the victim die, when no replica is bigger than the
victim — all heaps 2 GiB, RF=3, CL=ONE, shipped defaults? And with two faster peers?

| Condition (aarch64, blob 11 000 B, 8 × 256 in flight to V only, CL=ONE, uncapped, 90 s, defaults) | Proposed status (protocol *Verification status*) |
|---|---|
| **A-aarch64** — run 1's condition A on this platform: RF=2 `{c:1, r:1}`, V 2 GiB, R1 8 GiB | **Platform reproduction** of the verified condition A: heap OOM **3/3** (+ 1/1 shakedown arm), service loss in 3/3; CL=LOCAL_ONE 0/3. Proposed: no status change (`verified-OOM · deployment`); record "reproduced on aarch64 (run 2)". |
| **G1** — RF=3 single DC, **all three heaps 2 GiB** | Proposed **`verified-OOM · deployment`** (unprotected accumulation): heap OOM **3/3**; matched control (rate cap 1 500/s) 0/3; intervention CL=ALL 0/3 with 2.4× the completed writes; dumps 3/3 (≈ 63.4 k queued `Mutation`); defaults; 2 GiB. **The faster replica is not part of the condition** on this platform. |
| **G2** — RF=3 single DC, V 2 GiB, two 8 GiB peers | Proposed **`verified-OOM · deployment`** (unprotected accumulation): heap OOM **3/3**, service loss 2/3; CL=ALL 0/3; matched control (rate cap 1 500/s) 0/3; dumps 3/3; defaults; 2 GiB. Adds nothing beyond G1 except that two bigger peers do not change the outcome. |
| G1 at 4 GiB (all three nodes 4 GiB; upward search) | Heap OOM **0/6** (3 arms with 60 s and 3 with 300 s observation); **GC service loss 3/6** (61–84 s windows ≥ 90 % STW), max live 97.1–98.0 %, ≈ 128–136 k queued at the peak; the backlog drains once the client stops (300 s arms: pending 0, V recovers). Proposed: `candidate` (service loss 3/6; no control or intervention at 4 GiB). Largest heap with heap OOM: **2 GiB** (3/3). |
| Eeq-RF2 — run 1's topology with R1 at 2 GiB (equal-heap RF=2), 300 s load | Heap OOM **3/3**, 66–92 s after load start (the longer burst was not needed); 63.0 k queued `Mutation`; intervention CL=LOCAL_ONE (same topology, 300 s) **0/3**, 43.7–55.5 % live, ≈ 1.02–1.05 M writes. Proposed: `candidate` — V1, V3–V7 met; **V2 missing** (no matched rate-cap control on this topology; ≈ 20 min to add). **Contrasts with run 1's x86 arm (1/1 survived at 81 %)**: platform-dependent. |


### Summary

- **Conclusion:** on aarch64 the S2 failure does **not** need a replica that is faster because it is bigger. With an
  RF=3 single-DC ring where **all three nodes have a 2 GiB heap** (G1), the node coordinating every CL=ONE write dies
  of **Java heap OOM 3/3**, with ≈ 63.4 k of its own local writes queued on `MutationStage` (≈ 90 % of the heap),
  exactly the holder and count of run 1 and of this run's positive control (A-aarch64: run 1's 2 GiB victim + 8 GiB
  replica, OOM 3/3). Two faster 8 GiB peers (G2) give the same 3/3. The equal-heap replicas stay at ≤ 25 % live
  with ≤ 77 pending.
- **Why it generalizes:** the coordinator is itself the slowest replica. During the load V is CPU-bound (93 % busy
  vs ≈ 50 % on the replicas, one reading); its copies to the peers pass through bounded internode queues (expired
  ones dropped and hinted), so the peers apply what reaches them at once and ack first. At CL=ONE that ack releases
  the client slot, the native-transport in-flight bytes and the request, while V's local copy waits on the unbounded
  stage; 33–64 k local copies per arm expire and are **re-queued as hints on the same stage** instead of shed.
- **Attribution (G1, 2 GiB):** CL=ALL (the client slot is held until V's own write applies) survives 3/3 at ≈ 30 %
  live and completes **2.4×** the writes; a 1 500 writes/s cap survives 3/3 at ≤ 9 % live. G2 likewise: CL=ALL 0/3 (26–30 % live), rate cap 0/3 (≤ 9.7 %).
- **Budget search:** **2 GiB is the largest heap with heap OOM** (3/3). With all three nodes at 4 GiB: heap OOM 0/6, GC service loss 3/6, 97–98 % live, the backlog drains after the 90 s burst. Equal-heap **RF=2** (run 1's topology, R1 2 GiB, 300 s load) also OOMs **3/3** here, all within 92 s, where run 1's single x86 arm survived at 81 % live.
- **Scope:** one client whitelisted to V (every write coordinated by V, which is also a replica), blob 11 000 B,
  8 × 256 in flight, m400 (8 slow cores). Run 1's single x86 equal-heap RF=2 arm survived at 81 % live; here the
  same topology fails 3/3. The likely difference is the coordinator's CPU headroom (the x86 victim had 8 cores /
  16 threads; the same client shape offered 13–17 k writes/s there vs 3–8 k here): whether "equal heap" also means "equal speed" is a platform property. Untested on x86.

### 1. Ceiling sheet, protection map, configuration

**Ceiling sheet and protection map:** unchanged from run 1 (final file §1): the holder is the coordinator's own local
write, a `LocalMutationRunnable` (`StorageProxy$4`) holding the `Mutation` and its `WriteResponseHandler`, queued on
`Stage.MUTATION` (unbounded queue, `concurrent_writes` 32 threads). C = none, K = none. Client-facing limits
(client window 8 × 256, `native_transport_max_request_data_in_flight` heap/10, `native_transport_max_threads` 128)
are released when the response is sent, i.e. at the first replica ack at CL=ONE. An expired local runnable is
counted as a *self-dropped* `MUTATION_REQ` and resubmitted as a `HintRunnable` that applies the same mutation on the
same stage (`StorageProxy.java:2633–2652`, re-read on the run-2 tree).

**What run 2 adds to the map — why the replicas are protected and V is not** (readings, §3.4). On the replica
side, a mutation reaches `MutationStage` only through V's internode outbound queue (bounded: 4 MiB per link +
128 MiB per endpoint + 512 MiB global, `OutboundConnection.java:330`; messages whose timeout expires before
reaching the network are dropped and hinted) and the replica's inbound limits. On V's own copy no such bound
applies. So the asymmetry needs no bigger replica: the coordinator itself is the bottleneck (it decodes every CQL
request, applies its copy, serializes and sends 1–2 copies, handles the responses), its sends to the replicas are
throttled by bounded queues, and the replicas apply what reaches them almost at once and ack, releasing the
client slot while V's local copy waits.

**Configuration and budget audit.**

| Item | Value | Class |
|---|---|---|
| Source / build | 5.0.9 from the repository (`copy-source.sh` → `/mydata/s2r2/cassandra` on `ms0640`, `ant jar` BUILD SUCCESSFUL 5 min 1 s), tarred (without `src/`, `test/`, `.git`) to `ms0604`, `ms0611`, `ms0617`; client = Java driver 3.12.1 (`S2Load.java` = run 1's + `-Drepl`) | — |
| Nodes | Utah m400 (`jason92-326377`): `ms0640` V 10.10.1.2, `ms0604` R1 .3, `ms0611` R2 .4, `ms0617` client .5; each aarch64 APM X-Gene 8 cores, 62 GiB RAM, 8 GiB swap on, Ubuntu 22.04, kernel 5.15, cgroup v2; LAN ≈ 0.1 ms | environment |
| JDK / GC | OpenJDK 11.0.33 (apt `openjdk-11-jdk`), Ant 1.10.12; shipped G1 options (`jvm11-server.options`), `-Xms = -Xmx`, `HEAP_NEWSIZE` 256M (as run 1; ignored under G1), `MaxDirectMemorySize` auto = ¼ RAM = 15 872 MiB, shipped `HeapDumpOnOutOfMemoryError` and `OnOutOfMemoryError=kill -9 %p` | environment |
| Memory scope | every server JVM in `systemd-run --user --scope -p MemorySwapMax=0` (`memory.swap.max` 0 verified per arm, `memory.max` = max: the budget is the heap); `loginctl enable-linger` for the run, disabled after; scope `memory.current` sampled (no `memory.peak` on 5.15); `memory.swap.current` 0 in every arm | environment |
| Topology A | V dc `c`, R1 dc `r`, keyspace `b6` `NTS {c:1, r:1}` (run 1's) | environment |
| Topology G | V, R1, R2 dc `c`, `b6` `NTS {c:3}` (every node replicates every key) | environment |
| yaml diffs (per instance `yaml.diff`) | cluster name, `num_tokens: 1` + `initial_token` (−2^63 / −3074457345618258603 / 3074457345618258602), listen/rpc address, seed 10.10.1.2, GossipingPropertyFileSnitch, data/commitlog/hints/saved_caches dirs, `auto_bootstrap: false` | environment |
| Constraints (V6) | all at the shipped default resolved at each heap: `memtable_heap_space` ¼ heap, `memtable_allocation_type: heap_buffers`, caches auto (empty here), internode queue capacities, `native_transport_max_request_data_in_flight` heap/10, `concurrent_writes` 32, `write_request_timeout` 2 s, hints **on** | default |
| Budget (V7) | V heap 2 GiB (ideal, standing rule) and 4 GiB (upward search); the m400's own auto heap would be min(½ RAM, 15 872 MiB) = 15.5 GiB | acceptable (standing rule) |
| Workload | blob 11 000 B, 8 sessions × 256 in flight, all to V (whitelist), CL=ONE (interventions: CL=ALL in G, CL=LOCAL_ONE in A), rate cap 1 500/s in the control; load 90 s (300 s in the `Eeq-*-long` arms), observation 60 s after the client exits (300 s in `G1-4G-obs300`) | experimental variable |
| Instrumentation | one long-lived JMX poller JVM per server node (`S2Poll`, nice 10, every 3 s: heap used/committed without forced GC, `MutationStage` pending/active/completed, memtable size, hints, scope memory); GC log; heap dump on OOM (parsed on pc96 by `hprofhist.py`). Shakedown arm `A-2G-r1` used run 1's nodetool/jcmd/cqlsh loop instead (≈ 30 s per cycle on the loaded m400; disclosed, reported, not counted) | disclosed |

### 2. Design

Design and amendments: [`design/S2-run2-design.md`](design/S2-run2-design.md). Harness:
[`harness-run2/`](harness-run2/) — `arm.sh` (controller on pc96: clean start of all instances, schema with the
arm's replication, samplers, load, observation) → `collect.sh` (dump wait, GC readings per node via run 1's
`gcpeak.sh` / `gcwin.py`, dump moved to the node's `/mydata/s2r2/dumps/`, stop, copy back), `ctl.sh` (per-node
instance controller with the swap-0 scope), `sample.sh` + `S2Poll.java` (sampler), `client.sh` + `S2Load.java`,
`dumpparse.sh` (dump → histogram on pc96), `batch1–6.sh` (arm order per amendment), `summ.sh`, `table.py` (the table
below), `excerpt.sh` (`logs-run2/`). The shakedown arm ran from an `arm.sh` that was overwritten while it ran; its
collection was done by hand with `collect.sh` (same steps).

| Ingredient | Intervention / control | Arm |
|---|---|---|
| CL=ONE ack from another replica releasing every upstream bound | CL that waits for V's own write: CL=LOCAL_ONE in A (run 1's), **CL=ALL** in G (in a single-DC ring LOCAL_ONE = ONE) | `A-lone-2G`, `G1-all-2G`, `G2-all-2G` |
| offered write load above V's local apply rate | client capped at 1 500 writes/s (≈ 0.5 × V's measured apply rate) | `G1-rate-2G`, `G2-rate-2G` |
| a replica faster than V | removed: all heaps equal (G1); in-between: two faster peers (G2) | `G1-2G`, `G2-2G` |
| budget | upward: all three nodes at 4 GiB (60 s and 300 s observation) | `G1-4G`, `G1-4G-obs300` |
| replica count | equal-heap RF=2 (run 1's topology, R1 2 GiB), 300 s load; intervention CL=LOCAL_ONE | `Eeq-2G-long`, `Eeq-lone-2G-long` |

Endpoints (as run 1): heap OOM of V (`HeapDumper` / `ReportJavaOutOfMemory` safepoints, dump, `OutOfMemoryError`
in `system.log` when not starved); GC service loss (protocol default ≥ 90 % STW over ≥ 60 s, all pauses,
`gcwin.py`).

### 3. Results

Raw per-arm data: `pc96:/mydata/s2r2-evidence/runs/<arm>/` (arm.log; `V/`, `R1/`, `R2/`: GC logs, system.log,
`poll.log`, outcome, dump histogram; `client/load.log`). Committed excerpts: [`logs-run2/`](logs-run2/). Kept dumps
(one per condition): `ms0640:/mydata/s2r2/dumps/{A-2G-r2,G1-2G-r1,G2-2G-r1,Eeq-2G-long-r1}-V.hprof` (2.24–2.25 GB each); the other dumps were reduced to histograms and deleted. Columns: V outcome · OOM =
`HeapDumper` safepoint, seconds after load start · V max post-Full-GC live · worst-60 s STW share · longest window
with ≥ 90 % STW (service loss if ≥ 60 s) · V max `MutationStage` pending (sampler) · dump `Mutation` /
`StorageProxy$4` · client completed / errors · client peak 5 s rate · replicas: max post-Full-GC (or none) / max
`MutationStage` pending.

| Arm | V | OOM at (s) | Max live after Full GC MiB | Worst-60 s STW | Longest ≥ 90 % window | V max pending | Dump `Mutation` / `StorageProxy$4` | Completed / errors | Peak 5 s rate | Replicas |
|---|---|---|---|---|---|---|---|---|---|---|
| `A-2G-r1` (shakedown, old sampler; not counted) | **OOM** | 65 | 2031 (99.2 %) | 47 % | 0 s (no) | 0 | 62906 / 62906 | 172,242 / 4,062,773 | 5,193 | R1 no Full GC (≤ 13.5 % after any GC) / 0 |
| `A-2G-r2` | **OOM** | 320 | 2030 (99.1 %) | 99 % | 321 s (yes) | 62022 | 63153 / 63152 | 142,652 / 3,078 | 6,422 | R1 no Full GC (≤ 13.6 % after any GC) / 2 |
| `A-2G-r3` | **OOM** | 115 | 2030 (99.1 %) | 99 % | 289 s (yes) | 63828 | 63969 / 63967 | 140,336 / 4,544 | 6,097 | R1 no Full GC (≤ 13.6 % after any GC) / 7 |
| `A-2G-r4` | **OOM** | 257 | 2031 (99.2 %) | 99 % | 248 s (yes) | 62723 | 63340 / 63340 | 141,030 / 2,061 | 6,723 | R1 no Full GC (≤ 13.7 % after any GC) / 2 |
| `A-lone-2G-r1` | alive | — | 818 (39.9 %) | 6 % | 0 s (no) | 7393 | — | 316,307 / 2,014 | 6,255 | R1 no Full GC (≤ 27.9 % after any GC) / 2 |
| `A-lone-2G-r2` | alive | — | 809 (39.5 %) | 7 % | 0 s (no) | 3431 | — | 328,987 / 2,090 | 6,256 | R1 no Full GC (≤ 39.1 % after any GC) / 17 |
| `A-lone-2G-r3` | alive | — | 879 (42.9 %) | 7 % | 0 s (no) | 5651 | — | 317,291 / 1,920 | 6,716 | R1 no Full GC (≤ 37.3 % after any GC) / 138 |
| `G1-2G-r1` | **OOM** | 62 | 2029 (99.1 %) | 82 % | 0 s (no) | 62752 | 63349 / 63336 | 140,553 / 2,947 | 6,044 | R1 24.9 % / 77; R2 18.2 % / 4 |
| `G1-2G-r2` | **OOM** | 460 | 2033 (99.3 %) | 100 % | 466 s (yes) | 64046 | 63427 / 63427 | 124,475 / 4,690 | 5,362 | R1 16.3 % / 54; R2 17.9 % / 32 |
| `G1-2G-r3` | **OOM** | 176 | 2033 (99.3 %) | 100 % | 161 s (yes) | 63634 | 63520 / 63507 | 140,746 / 4,736 | 6,145 | R1 16.4 % / 14; R2 24.0 % / 0 |
| `G1-all-2G-r1` | alive | — | 613 (29.9 %) | 4 % | 0 s (no) | 203 | — | 329,758 / 1,329 | 5,909 | R1 20.2 % / 15; R2 15.4 % / 1 |
| `G1-all-2G-r2` | alive | — | 624 (30.5 %) | 4 % | 0 s (no) | 209 | — | 328,721 / 1,355 | 6,161 | R1 21.6 % / 4; R2 17.3 % / 7 |
| `G1-all-2G-r3` | alive | — | 612 (29.9 %) | 4 % | 0 s (no) | 199 | — | 329,571 / 1,101 | 6,158 | R1 14.8 % / 14; R2 20.2 % / 5 |
| `G1-rate-2G-r1` | alive | — | 182 (8.9 %) | 1 % | 0 s (no) | 2 | — | 130,115 / 0 | 1,800 | R1 10.4 % / 46; R2 5.5 % / 1 |
| `G1-rate-2G-r2` | alive | — | no Full GC (≤ 1344 (65.6 %) after any GC) | 1 % | 0 s (no) | 1 | — | 130,076 / 0 | 1,800 | R1 10.6 % / 5; R2 11.7 % / 1 |
| `G1-rate-2G-r3` | alive | — | no Full GC (≤ 1568 (76.6 %) after any GC) | 1 % | 0 s (no) | 2 | — | 130,053 / 0 | 1,798 | R1 no Full GC (≤ 50.0 % after any GC) / 1; R2 11.1 % / 96 |
| `G2-2G-r1` | **OOM** | 264 | 2025 (98.9 %) | 99 % | 299 s (yes) | 61706 | 61986 / 61985 | 123,272 / 4,938 | 6,537 | R1 no Full GC (≤ 13.5 % after any GC) / 2; R2 no Full GC (≤ 13.6 % after any GC) / 6 |
| `G2-2G-r2` | **OOM** | 232 | 2029 (99.1 %) | 99 % | 229 s (yes) | 62016 | 63431 / 63430 | 109,476 / 3,625 | 5,225 | R1 no Full GC (≤ 13.4 % after any GC) / 3; R2 no Full GC (≤ 14.3 % after any GC) / 4 |
| `G2-2G-r3` | **OOM** | 52 | 2030 (99.1 %) | 46 % | 0 s (no) | 62759 | 63412 / 63411 | 126,419 / 9,957,240 | 5,544 | R1 no Full GC (≤ 13.3 % after any GC) / 11; R2 no Full GC (≤ 13.3 % after any GC) / 2 |
| `G2-all-2G-r1` | alive | — | 536 (26.2 %) | 4 % | 0 s (no) | 308 | — | 328,771 / 1,359 | 6,221 | R1 no Full GC (≤ 47.5 % after any GC) / 0; R2 no Full GC (≤ 47.7 % after any GC) / 22 |
| `G2-all-2G-r2` | alive | — | 535 (26.1 %) | 4 % | 0 s (no) | 390 | — | 317,101 / 1,324 | 6,128 | R1 no Full GC (≤ 46.1 % after any GC) / 10; R2 no Full GC (≤ 45.9 % after any GC) / 1 |
| `G2-all-2G-r3` | alive | — | 612 (29.9 %) | 4 % | 0 s (no) | 202 | — | 328,793 / 1,387 | 6,160 | R1 no Full GC (≤ 47.6 % after any GC) / 4; R2 no Full GC (≤ 47.4 % after any GC) / 13 |
| `G2-rate-2G-r1` | alive | — | 198 (9.7 %) | 1 % | 0 s (no) | 2 | — | 130,011 / 0 | 1,800 | R1 no Full GC (≤ 4.5 % after any GC) / 1; R2 no Full GC (≤ 4.4 % after any GC) / 0 |
| `G2-rate-2G-r2` | alive | — | 164 (8.0 %) | 1 % | 0 s (no) | 1 | — | 130,188 / 0 | 1,800 | R1 no Full GC (≤ 3.8 % after any GC) / 1; R2 no Full GC (≤ 4.4 % after any GC) / 1 |
| `G2-rate-2G-r3` | alive | — | 193 (9.4 %) | 1 % | 0 s (no) | 2 | — | 130,078 / 0 | 1,800 | R1 no Full GC (≤ 4.4 % after any GC) / 27; R2 no Full GC (≤ 4.5 % after any GC) / 1 |
| `G1-4G-r1` | alive | — | 3990 (97.4 %) | 83 % | 0 s (no) | 128862 | — | 283,898 / 2,586 | 7,915 | R1 5.5 % / 108; R2 14.0 % / 3634 |
| `G1-4G-r2` | alive | — | 4015 (98.0 %) | 96 % | 67 s (yes) | 131497 | — | 283,368 / 3,536 | 7,261 | R1 22.0 % / 50; R2 22.7 % / 2007 |
| `G1-4G-r3` | alive | — | 4005 (97.8 %) | 98 % | 84 s (yes) | 135945 | — | 221,641 / 4,157 | 7,799 | R1 25.0 % / 24; R2 21.7 % / 18 |
| `G1-4G-obs300-r1` | alive | — | 3995 (97.5 %) | 92 % | 62 s (yes) | 130277 | — | 282,897 / 3,819 | 7,612 | R1 6.0 % / 2; R2 21.0 % / 32 |
| `G1-4G-obs300-r2` | alive | — | 3979 (97.1 %) | 78 % | 0 s (no) | 133495 | — | 283,026 / 2,560 | 7,535 | R1 23.0 % / 562; R2 25.7 % / 2 |
| `G1-4G-obs300-r3` | alive | — | 3976 (97.1 %) | 72 % | 0 s (no) | 128401 | — | 282,387 / 3,279 | 8,163 | R1 13.5 % / 6; R2 25.6 % / 19 |
| `Eeq-2G-long-r1` | **OOM** | 66 | 2028 (99.0 %) | 51 % | 0 s (no) | 57151 | 63083 / 63083 | 173,424 / 91,058,699 | 5,477 | R1 24.1 % / 66 |
| `Eeq-2G-long-r2` | **OOM** | 81 | 2028 (99.0 %) | 83 % | 0 s (no) | 62416 | 62866 / 62865 | 156,446 / 90,545,622 | 5,873 | R1 25.1 % / 2 |
| `Eeq-2G-long-r3` | **OOM** | 92 | 2029 (99.1 %) | 91 % | 61 s (yes) | 62981 | 63016 / 63015 | 172,188 / 83,696,747 | 5,440 | R1 18.1 % / 13 |
| `Eeq-lone-2G-long-r1` | alive | — | 935 (45.7 %) | 7 % | 0 s (no) | 12891 | — | 1,045,581 / 9,620 | 6,276 | R1 32.5 % / 12487 |
| `Eeq-lone-2G-long-r2` | alive | — | 1136 (55.5 %) | 7 % | 0 s (no) | 23728 | — | 1,015,448 / 11,274 | 6,709 | R1 26.5 % / 8402 |
| `Eeq-lone-2G-long-r3` | alive | — | 895 (43.7 %) | 7 % | 0 s (no) | 7277 | — | 1,045,970 / 9,234 | 6,734 | R1 24.2 % / 12487 |

#### 3.1 Positive control on aarch64 (A-aarch64, run 1's condition A)

Heap OOM in **3/3** counted arms (`A-2G-r2–r4`) and in the shakedown arm `A-2G-r1` (old sampler, not counted),
`HeapDumper` 65 (r1), 115–320 s after load start; the counted arms first spent 248–321 s in GC service loss (≥ 90 % STW).
Dumps: 62 906–63 969 `Mutation`, each with one `StorageProxy$4` (`LocalMutationRunnable`) and one
`WriteResponseHandler`; `byte[]` 1 862–1 870 MiB of 2 068–2 070 MiB shallow heap — run 1's holder and count
(≈ 61.5 k there). Memtable on-heap ≤ 170 MiB (C = 512 MiB). R1 (8 GiB) never needed a Full GC and its
`MutationStage` pending stayed ≤ 7. The client offered 3.1–6.7 k writes/s (x86 run 1: 13–17 k/s): the m400 is
slower end to end, but V's apply rate is still below the offered rate. CL=LOCAL_ONE (`A-lone-2G` r1–r3): 0/3,
39.5–42.9 % live, ≈ 317–329 k completed writes (vs 140–143 k before the OOM). **The platform reproduces condition A**,
so the G arms below are interpretable.

#### 3.2 G1 — equal heaps, RF=3 (the question)

**Heap OOM 3/3** (`HeapDumper` 62, 460, 176 s after load start; service loss in r2 and r3: 466 s and 161 s windows;
r1 died at 82 % worst-60 s STW before a 60 s window formed). Max post-Full-GC 99.1–99.3 %. Sampler: V `MutationStage`
pending up to 62.8–64.0 k; dumps 63 349 / 63 427 / 63 520 `Mutation` with as many `StorageProxy$4` (≤ 14 fewer) and
`WriteResponseHandler` — the same holder as A and run 1. The two 2 GiB replicas: one Full GC each (16–25 % live after
it), `MutationStage` pending ≤ 77, alive. Completed writes 124–141 k (≈ A's).

#### 3.3 G2 — RF=3, two faster (8 GiB) peers

**Heap OOM 3/3** (52–264 s after load start; service loss in r1, r2: 299 s, 229 s), 98.9–99.1 % live, dumps
61 986 / 63 431 / 63 412 `Mutation`. Same as G1 within run-to-run spread: two bigger peers add nothing to an outcome
that equal peers already produce. First recorded error (r1, `system.log` not starved this time):
`ERROR [Native-Transport-Requests-69] … OutOfMemory error letting the JVM handle the error: java.lang.OutOfMemoryError:
Java heap space` (then 16 more request threads); r2's first is `OptionalTasks:1`. Matched control `G2-rate-2G` (1 500 writes/s): 0/3, 8.0–9.7 % live, pending ≤ 2, ≈ 130.1 k writes, 0 errors.

#### 3.4 Why only V queues when no replica is bigger (readings, not a separate arm)

| Reading (OOM arms at 2 GiB) | V | replicas |
|---|---|---|
| `MutationStage` max pending (sampler) | 61.7–64.0 k | ≤ 77 |
| self-dropped (expired) local `MUTATION_REQ`, resubmitted as hints (`MessagingMetrics` "internal") | 33–64 k per arm (G1 40–64 k); mean age at drop 2.3–7.4 s (per-5 s log lines) | — |
| cross-node `MUTATION_REQ` dropped on arrival | — | 24–789 per arm (both replicas) |
| V's outbound mutations to the replicas | "dropping message of type MUTATION_REQ whose timeout expired before reaching the network" in every arm | — |
| CPU, 10 s during load (one reading, `G1-4G-r1`, [`logs-run2/cpu-snapshot-G1-4G-r1.txt`](logs-run2/cpu-snapshot-G1-4G-r1.txt)) | **93 % busy, load 12.9** | 49–52 % busy, load ≈ 2.7 (client 8 %) |

With all heaps equal, the replicas are still "faster" than V because V is the coordinator of every write: it is
CPU-bound (decode, local apply, serialize and send to two peers, process responses), and the copies it sends pass
through bounded internode queues where expired messages are dropped and hinted. The replicas receive only what V
delivers, apply it at once and ack, which releases the client slot, the in-flight bytes and the request at CL=ONE
while V's own copy is still queued. Expired local copies are re-queued as hints on the same stage (3.4 row 2), so
the timeout does not shed V's backlog. Under CL=ALL the self-drops fall to 0.9–1.1 k per arm and pending to ≤ 390 (LOCAL_ONE in A: 1.8–1.9 k).

#### 3.5 Interventions and controls (2 GiB)

| Condition | Intervention (CL waits for V's own write) | Control (client cap 1 500 writes/s) |
|---|---|---|
| A-aarch64 | CL=LOCAL_ONE 0/3: 39.5–42.9 % live, worst-60 s STW 6–7 %, pending ≤ 7.4 k, 316–329 k writes | (run 1: rate cap; not repeated here) |
| G1 | **CL=ALL 0/3**: 29.9–30.5 % live, STW 4 %, pending ≤ 209, **328.7–329.8 k writes** (vs 124–141 k in the OOM arms) | **0/3**: ≤ 8.9 % live after Full GC (r2, r3 no Full GC), STW 1 %, pending ≤ 2, 130.1 k writes, 0 errors |
| G2 | CL=ALL 0/3: 26.1–29.9 % live, STW 4 %, pending ≤ 390, 317–329 k writes | **0/3**: 8.0–9.7 % live, STW 1 %, pending ≤ 2, 130.0–130.2 k writes, 0 errors |

CL=ALL completes ≈ 2.4× the writes of the failing arms at the same offered load, so the intervention does not work by
stopping useful work (as LOCAL_ONE in run 1). The rate cap (≈ 0.5 × V's measured apply rate) keeps every node idle
enough that nothing queues.

#### 3.6 Upward heap search: G1 at 4 GiB (all three nodes)

| | Outcome | Max live after Full GC | Worst-60 s STW | Service loss | V max pending | Completed |
|---|---|---|---|---|---|---|
| `G1-4G` r1–r3 (60 s observation) | alive when stopped 60 s after the client exited | 97.4 / 98.0 / 97.8 % | 83 / 96 / 98 % | **2/3** (67 s, 84 s) | 128.9 / 131.5 / 135.9 k | 284 / 283 / 222 k |
| `G1-4G-obs300` r1–r3 (300 s observation, amendment R2-A4) | alive at the end; `MutationStage` pending back to 0 after the client exited | 97.5 / 97.1 / 97.1 % | 92 / 78 / 72 % | **1/3** (62 s) | 130.3 / 133.5 / 128.4 k | 283 / 283 / 282 k |

Memtable on-heap ≤ 340 MiB (C = 1 GiB). V self-dropped 152–225 k local mutations per arm (re-queued as hints).
Over six arms at 4 GiB: **heap OOM 0/6, GC service loss 3/6**, every arm at 97–98 % live with ≈ 128–136 k local
writes queued at the peak (≈ 2× the 2 GiB count, as the heap is 2×). The 300 s observation (amendment R2-A4)
removes the censoring concern: once the 90 s burst ends, V's stage drains the backlog (pending 0; r1's next Full GC
3 979 → 66 MiB) and V recovers. So with this client the 4 GiB ring sits just at the boundary — the burst fills the
heap to ≈ 97 % and stalls V in Full GCs, but the backlog stops growing when the offered load stops. Run 1 (x86, A,
4 GiB): OOM 1/3. A longer burst at 4 GiB was not run (time).

#### 3.7 Equal-heap RF=2 with a longer burst (run 1's next step 1)

`Eeq-2G-long` r1–r3 = run 1's amendment-A4 arm (A topology, R1 at 2 GiB = V) with a 300 s load. **Heap OOM 3/3**,
66 / 81 / 92 s after load start (r3 after a 61 s service-loss window), 99.0–99.1 % live, dumps 63 083 / 62 866 /
63 016 `Mutation` = `StorageProxy$4`; V self-dropped 69–86 k local writes per arm (re-queued as hints); R1 (2 GiB)
18–25 % live after its Full GC, pending ≤ 66, 640 cross-node drops over the three arms. All three failed by 92 s (two inside the
first 90 s), so on this platform a burst about as long as run 1's already fails with an equal-heap RF=2 replica; the
300 s burst only shows that the client then spins on `NoHostAvailableException` (83–91 M errors after V died). Intervention
`Eeq-lone-2G-long` r1–r3 (CL=LOCAL_ONE, same topology and 300 s load, amendment R2-A5): **0/3**, 43.7–55.5 % live,
worst-60 s STW 7 %, V pending ≤ 23.7 k (R1 ≤ 12.5 k: with LOCAL_ONE the 2 GiB remote replica now queues instead),
1.02–1.05 M writes completed with 0.9–1.1 % errors. **Run 1's x86 arm
(`Eeq-blob-2G-r1`, 1/1) survived at 81 % live with 43 k pending**: on x86 the equal-heap RF=2 condition sits near
the boundary, on the m400 it is well past it. Not pooled across platforms.


### 4. Conclusion

**How far S2 generalizes (answer to the queued question).** On the m400 platform the backlog forms and the OOM
happens with **no faster replica**: G1 (all 2 GiB, RF=3, CL=ONE, defaults) 3/3, G2 (two faster peers) 3/3, A
(run 1's condition) 3/3. The ingredient run 1 labelled "a faster replica" is, more precisely, **any replica that acks
before the coordinator's own local apply**, and a node that coordinates the writes is the slowest replica by
construction when it is CPU-bound. The equal-heap RF=2 ring fails too (3/3 within 92 s), unlike run 1's single x86 arm (81 % live): whether "equal heap" yields an equal-speed replica depends on how much CPU the coordinator has left, which is a platform property, not a heap property. The holder, its count at 2 GiB (≈ 62–64 k `Mutation` ≈ 1.86 GiB
`byte[]`), the hint resubmission of expired local writes, and both interventions behave as in run 1.

**Classification:** unprotected accumulation (as run 1): C = none for the coordinator's local `MutationStage`
backlog, K = none (pending is a gauge), U = dump histograms + post-Full-GC live. Not mixed (blob payload, no stacked
layers). Known-open upstream: CASSANDRA-19958 (local hints and mutations share the unbounded MUTATION queue); also
13213, 6510/4753 (J1 prior-art check, `cassandra/leads/jira-prior-art-verified-cases.md`, not redone).

**V1–V7 for G1 (2 GiB) and G2 (2 GiB):**

| | Requirement | G1 evidence | G2 evidence | Met |
|---|---|---|---|---|
| V1 | ≥ 3 failing runs | `G1-2G` r1–r3 heap OOM 3/3 | `G2-2G` r1–r3 heap OOM 3/3 | yes / yes |
| V2 | matched control ≥ 3 | `G1-rate-2G` r1–r3 survive (same build, heaps, topology, payload, client; offered rate 1 500/s) | `G2-rate-2G` r1–r3 survive (1 500/s, amendment R2-A3) | yes / yes |
| V3 | U independent of K | dumps 3/3 → class histograms (≈ 63.4 k `Mutation` = `StorageProxy$4` = `WriteResponseHandler`); post-Full-GC from GC logs; K: none exists | dumps 3/3 (62.0–63.4 k) | yes / yes |
| V4 | intervention ×3 | CL=ALL 3/3 survive, 2.4× writes | CL=ALL 3/3 survive | yes / yes |
| V5 | initiating failure | `HeapDumper` + `ReportJavaOutOfMemory` safepoints per arm, `OnOutOfMemoryError=kill -9` fired (V dead), dumps with the holder; first error's thread not logged in G1 (`system.log` starved) | same + first error logged in r1 (`Native-Transport-Requests-69`, `Java heap space`) and r2 | yes / yes |
| V6 | default constraints | all defaults resolved at 2 GiB; hints on | same | yes / yes |
| V7 | acceptable budget | 2 GiB (ideal); 4 GiB: service loss 3/6, no OOM in 0/6 (boundary) | 2 GiB | yes / yes |

**Proposed statuses** (the researcher decides how they merge into the final S2 file; this file does not edit it):
- **G1 (equal-heap RF=3, 2 GiB): `verified-OOM · deployment`** — every constraint default, acceptable budget, no
  fault, no instrumentation altering timing (samplers at nice 10 are disclosed). The workload is the same uncapped
  CL=ONE burst the researcher accepted for condition A on 2026-11-16; the same judgement applies.
- **G2 (RF=3, two 8 GiB peers): `verified-OOM · deployment`** (unprotected accumulation), V1–V7 met; it is the in-between condition and adds no new mechanism to G1.
- **Condition A:** no change (`verified-OOM · deployment`); add "reproduced on aarch64, run 2 (3/3, LOCAL_ONE 0/3)".
- **4 GiB (G1):** `candidate` toward `verified-gap · service-loss · deployment` (endpoint 3/6, V1 met at that rate; V2/V4 not run at 4 GiB). The heap-OOM boundary is between 2 and 4 GiB for a 90 s burst.
- **Equal-heap RF=2, 300 s:** `candidate` (heap OOM 3/3, dumps, CL=LOCAL_ONE 0/3; V2 missing). Upgradeable to `verified-OOM · deployment` with a rate-cap control ×3 on the same topology (≈ 20 min).
- Suggested scope sentence for the final file: *"Verified for a coordinator that is also a replica and acks after
  another replica at CL=ONE; a faster (bigger) replica is not required (run 2, equal-heap RF=3 ring, aarch64)."*

**Limits.** One platform for the G arms (aarch64 m400, 8 slow cores); the x86 question (does an equal-heap ring fail
when the coordinator has more CPU headroom?) is not answered here. One client whitelisted to V (all coordination on
V; a token-aware client spreading coordination over the ring was not tested). Blob 11 000 B only; 90 s bursts
(300 s in Eeq). The CPU asymmetry rests on one 10 s reading at 4 GiB. Samplers ran on the server nodes at nice 10
(one long-lived JMX poller JVM each). The 2 GiB OOM arms' first error thread is in `system.log` only for G2 r1/r2.
The 60 s observation window censors slower failures (amendment R2-A4). Node clocks are MST (2 h behind EST);
`system.log` is UTC.

**Next step.** (1) The same G1 ring on x86 (16+ threads) to bound the platform dependence; (2) a token-aware client
(coordination spread over the three nodes) at the same total load; (3) the diagnostic patch from run 1's next step
(drop, do not hint, an expired local runnable when another replica already acked) as a second intervention.
