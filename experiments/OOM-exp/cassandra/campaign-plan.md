# Cassandra OOM campaign — 2026-11-06

Status: **active**, updated 2026-11-12. Current results and next actions are recorded
in the [run log](cases/_run-log.md). Source: Cassandra 5.0.9. Read the
[common protocol](../verification-protocol.md), selected playbook, and
[node requirements](node-requirements.md). Historical cases remain as filed.
The priority is new coverage mechanisms before additional cache combinations.
All leads below require source/path verification; inclusion does not confirm a bug.

## Prioritized queue

Direction/sub-direction names are from [`../README.md`](../README.md#two-directions):
convergence sub-directions are *multiplicity*, *concurrency/surge*,
*replacement-overlap* (and the done *standing-pool* shape); bypass sub-directions
are the mechanism rows of the bypass playbook (here *release-defect*, *accounting
mismatch*, *failed-reservation*, *pool-fallback*). Rows are ordered by priority. The
sub-direction is the hypothesis chosen up front; a case is separately tagged
**mixed** if the evidence crosses directions (see the C4/B5 row).

| ID / priority | Direction · sub-direction | Hypothesis and workload | Decisive evidence / control |
|---|---|---|---|
| C1 / P1 | convergence · multiplicity | **In progress.** Internode receive private allowances multiplied by loaded peers/links. Run 3 reached 543 MiB of its 544 MiB admission ceiling at N=8 with live senders. Physical-memory and OOM attribution remain open. | Continue the calibrated LARGE-message path. Verify coordinator timeout from measured drainage, then sweep Q=4/16/64 at N=8 and N=4/8 at fixed Q with matched aggregate load. Measure total admitted and live direct memory, reserve saturation, expiry and sender stability. Test a fixed-budget OOM boundary and reduced-Q/N intervention only after a reproducible physical-memory increment. See the [run log](cases/_run-log.md). |
| B1 / P1 | bypass · release-defect | **Run 1 done 2026-11-12: `negative · deployment`** ([case](cases/negatives/networking_cache_size-release-defect/networking_cache_size--release-defect.md)). Release defect confirmed 3/3 (`LargeMessage.onComplete()` never calls `releaseBuffers()`; patch removes it 3/3), but live direct memory plateaus at the 128 MiB pool cap and `OverflowSize` only drifts; 0/4 OOM at heap 2 GiB, direct 512 MiB–2 GiB. Next: JIRA re-check, upstream report; internode traffic on the shared pool untested. *(Original: recorded native-v5 large-request retention lead; repeat identical request/complete/idle cycles.)* | Outstanding ownership/pool slots and live allocation residual versus cycle count; healthy path and restored-release intervention. Distinguish plateau, accounting drift, allocator retention and accumulating leak. |
| C2 / P1 | convergence · concurrency/surge | Concurrent reads individually below an enabled size threshold; sweep actual simultaneous reads | Oversized-query rejection control, retained working sets and executor/admission bounds; no standing pool required. Unset/default thresholds are a separate arm, labeled **unprotected configuration** (protocol amendment 2026-11-10), not a bypass. |
| C3 / P1 | convergence · multiplicity | **Next multiplicity investigation after C1.** DOB retention multiplied by workers holding serialization buffers, at fixed payload and recycle threshold. Prior calibration measured about 337 MiB retained by 44 workers. | Sweep actual buffer-holding workers with matched total traffic/concurrency where feasible. Separate active allocation from idle retention, verify worker bounds, and test whether limiting worker count removes a repeatable fixed-budget failure. Reuse the [DOB calibration](cases/candidates/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom.md). |
| B6 / P1 | bypass · accounting mismatch · `source: flow:coordinator-write` (from C1) | **Verified 2026-11-11** ([final case](cases/bypass/internode_application_queue_capacity-accounting-mismatch/internode_application_queue_capacity--accounting-mismatch.md)): A `verified-gap · service-loss · deployment`, B `verified-OOM · diagnostic` (briefly `reproduced-OOM` on 2026-11-11; restored the same day: 2 GiB meets V7 under the standing budget rule), C candidate, **D `verified-OOM · diagnostic` (run 4, 2026-11-12: coordinator, two slow replicas, 60 s timeouts, largest failing heap 6 GiB)**, E candidate (default timeouts, 512 MiB 3/5, no working intervention). History: **Run 1 done 2026-11-10: bypass confirmed on two domains; heap OOM reproduced only with supporting deviations** ([case](cases/bypass/internode_application_queue_capacity-accounting-mismatch/history.md#run-1)). Internode send and receive queues charge on-wire bytes, but queued/deserialized `Mutation`s live on heap, and the coordinator write handler keeps each `Mutation` (`hintOnFailure`) after flush until the replica answers or the deadline, charged to no sender counter. Tiny-cell (1000-entry map) mutations are ≈ 19.7× (coordinator) / 16.7× (replica) their on-wire size; matched blob ≈ 2.2×. At a 2 GiB heap, coordinator and slow replica each OOM 3/3 with K ≤ 132 MiB (coordinator with its send queue empty); blob 0/3; 8 MiB endpoint reserves remove both OOMs (n=1). Depends on an injected slow replica and 60 s `write_request_timeout`/`native_transport_timeout`; the default-timeout arm is **not established** (client saturated at ≈ 2.3k inserts/s; needs ≈ 6k/s, ≥ 66 MiB/s). **Run 2 (2026-11-11, default timeouts, no Byteman, 4 coordinators, replica disk stall, 8/6 GiB):** map → replica 99% live with ~97% of 80–123 s in Full GC in 5/5 stall arms, 2 heap OOMs in 8 stall/hang arms; blob 0 Full GCs 4/4; receive endpoint reserve 8 MiB removes it ([run 2](cases/bypass/internode_application_queue_capacity-accounting-mismatch/history.md#run-2)). | **Run 3 (2026-11-11, [case](cases/bypass/internode_application_queue_capacity-accounting-mismatch/history.md#run-3)):** reserve intervention 3/3 per condition; run 2 and run 1's coordinator side meet V1–V5, run 1's replica side stays candidate. Filed 2026-11-11 (run 2 labelled `deployment`). Open (after run 2): heap dumps on one OOM arm *(done in run 3: coordinator dump)*; repeat the reserve intervention ×3 *(done)*; vary the stall length (5/15/60 s) to map service loss vs OOM; measure the coordinators (run 1's coordinator-side default-timeout arm still needs ≥ 66 MiB/s per destination); coordinator with ≥ 2 slow replicas at a deployment-sized 8 GiB heap *(done in run 4: [D/E](cases/bypass/internode_application_queue_capacity-accounting-mismatch/history.md#run-4))*; check JIRA history (CASSANDRA-15066 introduced these limits) for the on-wire accounting choice before any upstream report. Contract is on-wire bytes by design, so the interpretation is a documented-unit / sizing gap (plus the uncovered after-flush retention), not a counter defect. See [design](cases/bypass/internode_application_queue_capacity-accounting-mismatch/design/B6-design.md). |
| S1 / P1 | combo (convergence multiplicity → stack → bypass accounting gap) · JVM direct · `source: C1, C2, C3, R6-V, B1` | **New 2026-11-12, researcher's decision.** Run per the [combo playbook](../combo-playbook.md) at default constraints, direct 512 MiB / 2 GiB / auto (3982 MiB), heap 2 GiB. Stage 1: internode receive-queue multiplicity (C1; ceiling N·Q + min(G, N·E) ≈ 544 MiB at N=8). Stage 2 layers, in order: hint slabs parked at their 3 × 32 MiB cap (R6-V), DOB scratch on write workers (≤ 1 MiB × ≤ 165–177 holders, measured 131–195 MiB in R6-V/C3), concurrent reads whose encoded responses wait in Netty's outbound buffer (C2: per-query thresholds only), networking pool at its 128 MiB cap (B1); maintenance overlap (flush/compaction scratch) triggered by `nodetool`. Stage 3: pool fallback and release defect of the networking pool (B1), unbounded large-mutation DOB fill (U1). | Stage-0 ceiling sheet before any run; per-pool ledger (C, K, U from `Bits` / `DirectByteBuffer` dump) and headroom at every stage; each layer alone vs stacked; one intervention per ingredient (fewer peers, layer off, client in-flight cap). Reuse the C1 run 4 (pc96) and C2 (apt140/apt138) harnesses. |
| S2 / P1 | combo · heap · `source: B6, B7, R3/R4` | **New 2026-11-12, researcher's decision.** Same playbook, heap 2 GiB and larger (search upward), default constraints. Stage 1: coordinator write handlers retaining `Mutation`s per outstanding write (B6; bound ≈ write rate × timeout × mutation heap size), multiplied by coordinators/clients. Stage 2 layers: heap memtable at its default ¼ heap, key and counter caches filled to their default caps (100 / 50 MiB at ≥ 2 GiB), concurrent reads' working sets (C2), memtable flush overlap triggered by `nodetool flush`. Stage 3: on-wire vs heap mismatch of internode queues (B6, tiny-cell mutations ≈ 17–20×), cache weigher overhead (B7, 1.8–2.1× C). | As S1, with post-GC live heap, histograms/dumps per holder and worst-60 s STW share against the service-loss criterion. Default timeouts first; 60 s timeouts or slow-replica injection only as labeled supporting deviations. |
| R1 / P1 | convergence · standing-pool (pre-protocol recheck) | **Reproduced 2026-11-11** (V1–V5 met; `reproduced-OOM · diagnostic`, pc96; V6–V7 unmet: custom constraints, tightened budget): kernel memcg kill 3/3, alone 0/6, `file_cache_size` 300 MiB removes it 3/3. Open: deployment-budget arm; default `memtable_cleanup_threshold` arm. **Added 2026-11-11.** [`memtable_offheap_space + file_cache_size (run 7)`](cases/candidates/memtable_offheap_space+file_cache_size/memtable_offheap_space+file_cache_size.md): Off-heap memtable (`offheap_objects`, 1200 MiB) + chunk cache (`file_cache_size` 1200 MiB) under a 3500 MiB cgroup, `-Xmx768M`; chunk cache filled first, then the write burst. Both are hard standing caps, so the kill should repeat. | Kernel cgroup OOM-kill in converge ×3; each pool alone ×3 stays under budget; intervention ×3: lower one capacity so the pair fits the 3500 MiB budget; at the kill, per-pool readings (chunk cache size, memtable off-heap usage, NMT) next to the `dmesg` record. |
| R2 / P1 | convergence · standing-pool (pre-protocol recheck) | **Reproduced 2026-11-11** (V1–V5 met; `reproduced-OOM · diagnostic`, apt140; V6–V7 unmet: custom constraints, tightened budget): direct OOM 3/3, alone 0/6, L = 1 MiB removes it 3/3 (thin margin); dumps split 282 MiB DOB scratch + 256 MiB slabs. **Added 2026-11-11.** [`DOB_MAX_RECYCLE_BYTES + MAX_HINT_BUFFERS, custom (run 8)`](cases/candidates/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom.md): Hints pool parked at its 8-slab cap (2-node ring, N2 down), then 4 MB DOB writes with L = 8 MiB, at a 560 MiB `MaxDirectMemorySize`, `-Xmx3072M`. | Direct-buffer `OutOfMemoryError` in converge ×3; `H_alone` and `D_alone` ×3 stay under 70%; intervention ×3: `converge_Ldefault` (L back to 1 MiB) survives; first-error stack plus a histogram or dump showing `HintsBuffer` slabs and DOB scratch buffers. |
| R3 / P1 | convergence · standing-pool (pre-protocol recheck) | **Reproduced 2026-11-11** (V1–V5 met; `reproduced-OOM · diagnostic`, **mixed**, apt149; V6–V7 unmet: custom constraints, tightened budget): heap OOM + kill 3/3, alone 0/6, counter cache 50 MiB removes it 3/3; counter cache holds 327–337 MiB vs 300 MiB cap (see B7). **Added 2026-11-11.** [`memtable_heap_space + counter_cache_size (run 1)`](cases/candidates/memtable_heap_space+counter_cache_size/memtable_heap_space+counter_cache_size.md): `memtable_heap_space=550MiB` + `counter_cache_size=300MiB` at `-Xmx1024M`, concurrent `write` + `counter_write`. The endpoint filed was `OutOfMemoryError` throws with the JVM surviving. | `Java heap space` OOM in converge ×3 (state the endpoint: throws or JVM killed); M and C alone ×3 with 0 errors and a safe forced-GC heap; intervention ×3: lower one capacity so the sum fits the heap; heap dump at the first OOM with a histogram showing memtable and counter-cache holders. |
| R4 / P1 | convergence · standing-pool (pre-protocol recheck) | **Reproduced 2026-11-11** (V1–V5 met; `reproduced-OOM · diagnostic`, **mixed**, apt179; V6–V7 unmet: custom constraints, tightened budget): heap OOM + kill 3/3, alone 0/9, counter cache to auto removes it 3/3 (key cache to auto does not); caches 1.74× / 2.0× their counted weight (see B7). **Added 2026-11-11.** [`memtable_heap_space + counter_cache_size + key_cache_size (run 2)`](cases/candidates/memtable_heap_space+counter_cache_size+key_cache_size/memtable_heap_space+counter_cache_size+key_cache_size.md): 350 + 250 + 200 MiB at `-Xmx1024M`, concurrent `write` + `counter_write` + `read` (500,000 preloaded, flushed partitions for the key cache). | Heap OOM and JVM kill in converge ×3; M, C and K alone ×3; intervention ×3: lower one capacity (e.g. drop `key_cache_size` to its default) so the sum fits; histogram of the dump at failure showing the three holders (analyse run 2's 1.35 GB dump if still on the node). |
| R5 / P2 | convergence · standing-pool (pre-protocol recheck) | **Added 2026-11-11.** [`row_cache_size + index_summary_capacity, schedule B (run 6)`](cases/candidates/row_cache_size+index_summary_capacity--run6.md): Row cache (550 MiB, `SerializingCacheProvider`) filled first, then a 1.5M-partition index-summary burst, 2000 MiB cgroup, `-Xmx384M`, `index_summary_resize_interval=120m` (a supporting deviation). Timing-sensitive: schedule A did not OOM, so a rate below 3/3 is possible and must be stated. | Cgroup OOM-kill in schedule B ×3; R and I alone ×3; intervention ×3: lower `row_cache_size` so the pair fits (the 1-minute resize arm is not a clean intervention: its heap OOMed); per-pool readings at the kill; attribute or rule out the heap OOM seen in run 6's arm C. |
| R6 / P2 | convergence · standing-pool (pre-protocol recheck) | **Added 2026-11-11.** [`DOB_MAX_RECYCLE_BYTES + MAX_HINT_BUFFERS, defaults (default run 1)`](cases/candidates/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--default.md): Both settings at their defaults (hints pool 3 slabs, DOB buffers ≤ 1 MiB) at a 192 MiB `MaxDirectMemorySize` (design B). The OOM window is only about 15 MiB wide, so it may repeat at a rate below 3/3. | Direct-buffer OOM in `B_converge` ×3; `B_H_alone` and `B_D_matched` ×3; an intervention that survives ×3 at 192 MiB (design A's no-hints control also died, of compaction read-ahead), or documented infeasible with the status carrying `(no intervention)`; first-error stack and a direct-buffer holder breakdown. |
| C5 / P2 | convergence · multiplicity | **New candidate.** Compressed hints buffers retained per open destination writer. With LZ4 enabled and fixed hint size, vary the number of destinations whose writers simultaneously retain buffers. | Stage 4 measured 8.04 MiB for one destination and 16.07 MiB for two after accounting for slabs. Verify reachable writer count, replica placement, writer closure and other admission bounds. Separate compression buffers from shared hint slabs, compare with uncompressed controls, and measure direct-memory headroom before testing OOM. See [stage-4 evidence](../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous.md). |
| B7 / P2 | bypass · accounting mismatch · `source: R3/R4 recheck` | **Run 1 done 2026-11-12: `verified-gap · overshoot · deployment`** ([case](cases/bypass/key_cache_size+counter_cache_size-accounting-mismatch/key_cache_size+counter_cache_size--accounting-mismatch.md)) for both caches: at shipped defaults the key cache holds 2.14× and the counter cache 1.80× their caps (8 B keys; 1.15× at 512 B keys) with counters exactly at the cap, 3/3 at 512 MiB, 2 GiB and auto 7965 MiB heap; weigher + 104 B/entry removes it 3/3; contract is "in memory", so a documented-unit defect. No OOM at defaults (0/3; excess ≈ 154 MiB at 2 GiB is far below headroom). *(Lead, 2026-11-11:)* Caffeine-backed key and counter caches charge only the weigher's key+value size; the cache node, hash-map node/table and frequency sketch are uncounted. R3/R4 dumps: counter cache U ≈ 1.74× K and above C, key cache U ≈ 2.0× K. | Source-check the weighers (`CacheService`/`CaffeineCache`); fill each cache alone to its cap with small entries and measure U (dump/histogram) vs K vs C across entry sizes; intervention = a weigher that includes per-entry overhead (diagnostic build) or a capped entry count; decide whether the contract documents the unit. |
| B2 / P2 | bypass · failed-reservation | Memtable and pre-V5 failed-reservation exceptions (separate cases) | Failed acquisition followed by admitted allocation, outstanding operations, overshoot duration/bound and backpressure; bounded-admission intervention. |
| B3 / P2 | bypass · pool-fallback | BufferPool fallback beyond retained pool capacity | Separate pooled/fallback live memory, remaining admission bounds; reserve-before-allocation intervention. |
| B4 / P2 | bypass · release-defect | SerializingCache explicit-clear lifecycle | Fill/clear/idle cycles, ownership/release and residual allocations; healthy release/diagnostic repair control. |
| C4/B5 / P3 | mixed (replacement-overlap / periodic enforcement) | Replacement overlap or periodic index-summary enforcement | Old/new live allocations, enforcement intervals, format/path applicability; changed scheduling/interval control. Classify by whether local contracts hold. |

## First batch and completion

Investigate **C1, B1, C2** in that order unless source reachability or infrastructure
blocks one; record the blocker and continue an independent candidate. *(2026-11-10:
B6 was added to the batch and run first, ahead of B1 and C2, because it came out of
C1's write-path trace and reused that topology knowledge; C1 run 3's sweeps, B1 and
C2 are still outstanding.)* *(2026-11-11: R1–R6, the V1–V5 recheck of the six pre-protocol
convergence OOMs, were added by the researcher's decision: R1–R4 at P1, R5–R6 at P2;
they reuse existing harnesses and can run alongside the first batch.)* *(2026-11-11, later:
R1–R4 ran in parallel, one per node (pc96, apt140, apt149, apt179), and all four met V1–V5.
Under the V6–V7 amendment of the same day (constraints at defaults, acceptable budget) they are
`reproduced-OOM · diagnostic` in `candidates/`, R3 and R4 tagged mixed. Reaching *verified*
needs a new test of each mechanism at default constraints and an acceptable budget. R3/R4 gave
the new bypass lead B7. R5–R6 remain; see the [run log](cases/_run-log.md).)* *(2026-11-11, later: by the
researcher's decision, **B6 coordinator** (≥ 2 slow replicas, pc96), **B1** (apt140 victim, apt138
client) and **B7** (apt149) run in parallel, one agent each, ahead of C1's sweeps and C2. Budget
rule for all three: heap/direct ≥ 512 MiB, 2 GiB ideal, search for the largest budget that still
fails ([protocol V7](../verification-protocol.md#defaults-and-acceptable-budget-amended-2026-11-11)).)* *(2026-11-12, later: by the researcher's decision,
convergence continues as **staged stacking** per the [combo playbook](../combo-playbook.md):
multiplicity first, then standing-pool / concurrency / maintenance-overlap layers in the same budget domain, then
accounting gaps, with the distance to OOM measured at every stage. Rows **S1** (JVM direct) and **S2** (heap) are
its first cases; they reuse the harnesses and readings of C1, C2, C3, R6-V, B1, B6 and B7 as layers. Single-shape
negatives at defaults (R6-V, C3, B1) are inputs to S1, not closed directions.)*

**R1–R6 (pre-protocol recheck) share one rule.** Same build, budget, settings and
workload as the filed case, with its existing harness under `cases/candidates/`. Each
arm runs ×3 from clean starts. Run them in ID order: R1–R4 (P1) are hard standing caps;
R5–R6 (P2) are timing- or window-sensitive and the likeliest to end as `candidate`
with a rate below 3/3. A case that meets V1–V5 becomes `reproduced-OOM · diagnostic` in `candidates/` (every one
uses custom constraints and/or a tightened budget, so V6–V7 cannot be met by a recheck);
otherwise it stays `candidate` with the observed rate. No new combinations. Run source
and modest-load validation before exhaustion. The delivered batch consists of
three investigations with source map, executable design/harness, matched controls,
results or explicit blockers, boundary/repeat evidence, and causal intervention
where feasible. A protected/negative result is useful and is not discarded.

Within multiplicity, the order is **C1 → C3 → C5**. C3 is promoted to P1 on the
strength of its measured retained footprint. C5 starts with reachability and
writer-lifetime validation. B1 and C2 retain their places in the first batch.
Existing IDs identify individual investigations, and C5 extends that list.

Use assigned time/attempt limits; if none are assigned, state a finite proposed
limit before execution rather than silently running indefinitely. Initial boundary
validation uses three failing and three nearest-surviving runs; extend for mixed
outcomes. Report the initiating failure, not only Cassandra's shutdown response.
No experiments are launched by this documentation update.

## Lead-source pilots

Added 2026-11-10 (see [lead sources](../README.md#lead-sources)). Rows in the
prioritized queue above come from the if-check inventory unless they say
otherwise (B6 came from tracing C1's write path: `source: flow:coordinator-write`). New candidates found by these
pilots get normal C/B IDs (U for unprotected accumulation) and a
`source:` label. Not yet started.

| ID / priority | Lead source | Task | Output / done when |
|---|---|---|---|
| J1 / P1 | JIRA | Survey resolved CASSANDRA issues reporting OOM; classify per [jira-mining-playbook](../jira-mining-playbook.md). Then pick 3–5 positive controls and a variant shortlist. | `leads/jira-oom-survey.csv` + `.md` with counts per class/flow/fix kind and the two shortlists. Reproductions are separate follow-up rows. |
| F1 / P1 | data flow | Trace the **coordinator write** flow (client intake → coordinator → internode send → replica receive → mutation stage → memtable) per [dataflow-tracing-playbook](../dataflow-tracing-playbook.md). Much of it is mapped already in C1 and B6. | `leads/dataflow/coordinator-write.md` with the holder table and ranked leads. |
| J2 / P2 | JIRA | Same survey for Hadoop (HDFS, YARN, MAPREDUCE, HADOOP); does not need capacity-enforcement-exp Hadoop to finish. | `../hadoop/leads/jira-oom-survey.csv` + `.md`. |

Rank later flows for tracing by J1's per-flow counts.

## Scope and progress

Status is keyed by mechanism + allocation domain + capacity/budget regime. Consult
the current-status tables in the merged [run log](cases/_run-log.md) (parts A–C:
custom convergence, default convergence, bypass); their older domain-wide
"exhausted" or arithmetic exclusions describe only the older pool-combination
campaign. New mechanisms are open for source audit. Disk remains skipped and
disk-to-memory causal-chain work deferred; this campaign does not reopen either.

Default-capacity tests record the budget separately. Prefer fixed-budget workload
sweeps, and follow promising diagnostic failures with a deployment-budget arm.
One actual OOM is not enough to infer absence of global protection or an upstream
bug. Confirm the mechanism and report attribution limits.
