# Cassandra OOM campaign — 2026-11-06

Status: **active**, updated 2026-11-10. Current results and next actions are recorded
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
| B1 / P1 | bypass · release-defect | Recorded native-v5 large-request retention lead; repeat identical request/complete/idle cycles | Outstanding ownership/pool slots and live allocation residual versus cycle count; healthy path and restored-release intervention. Distinguish plateau, accounting drift, allocator retention and accumulating leak. |
| C2 / P1 | convergence · concurrency/surge | Concurrent reads individually below an enabled size threshold; sweep actual simultaneous reads | Oversized-query rejection control, retained working sets and executor/admission bounds; no standing pool required. Unset/default thresholds are a separate arm, labeled **unprotected configuration** (protocol amendment 2026-11-10), not a bypass. |
| C3 / P1 | convergence · multiplicity | **Next multiplicity investigation after C1.** DOB retention multiplied by workers holding serialization buffers, at fixed payload and recycle threshold. Prior calibration measured about 337 MiB retained by 44 workers. | Sweep actual buffer-holding workers with matched total traffic/concurrency where feasible. Separate active allocation from idle retention, verify worker bounds, and test whether limiting worker count removes a repeatable fixed-budget failure. Reuse the [DOB calibration](cases/convergence/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom.md). |
| B6 / P1 | bypass · accounting mismatch · `source: flow:coordinator-write` (from C1) | **Run 1 done 2026-11-10: bypass confirmed on two domains; heap OOM reproduced only with supporting deviations** ([case](cases/candidates/internode_application_send_queue_capacity-accounting-mismatch/internode_application_queue_capacity--accounting-mismatch--run1.md)). Internode send and receive queues charge on-wire bytes, but queued/deserialized `Mutation`s live on heap, and the coordinator write handler keeps each `Mutation` (`hintOnFailure`) after flush until the replica answers or the deadline, charged to no sender counter. Tiny-cell (1000-entry map) mutations are ≈ 19.7× (coordinator) / 16.7× (replica) their on-wire size; matched blob ≈ 2.2×. At a 2 GiB heap, coordinator and slow replica each OOM 3/3 with K ≤ 132 MiB (coordinator with its send queue empty); blob 0/3; 8 MiB endpoint reserves remove both OOMs (n=1). Depends on an injected slow replica and 60 s `write_request_timeout`/`native_transport_timeout`; the default-timeout arm is **not established** (client saturated at ≈ 2.3k inserts/s; needs ≈ 6k/s, ≥ 66 MiB/s). **Run 2 (2026-11-11, default timeouts, no Byteman, 4 coordinators, replica disk stall, 8/6 GiB):** map → replica 99% live with ~97% of 80–123 s in Full GC in 5/5 stall arms, 2 heap OOMs in 8 stall/hang arms; blob 0 Full GCs 4/4; receive endpoint reserve 8 MiB removes it ([run 2](cases/candidates/internode_application_send_queue_capacity-accounting-mismatch/internode_application_queue_capacity--accounting-mismatch--run2-diskstall.md)). | Open: a faster load generator (Java driver or several hosts) for the default-timeout arm; coordinator with ≥ 2 slow replicas at a deployment-sized 8 GiB heap; repeat the reserve intervention ×3; check JIRA history for the on-wire accounting choice before any upstream report. Contract is on-wire bytes by design, so the interpretation is a documented-unit / sizing gap (plus the uncovered after-flush retention), not a counter defect. See [design](cases/candidates/internode_application_send_queue_capacity-accounting-mismatch/design/B6-design.md). |
| C5 / P2 | convergence · multiplicity | **New candidate.** Compressed hints buffers retained per open destination writer. With LZ4 enabled and fixed hint size, vary the number of destinations whose writers simultaneously retain buffers. | Stage 4 measured 8.04 MiB for one destination and 16.07 MiB for two after accounting for slabs. Verify reachable writer count, replica placement, writer closure and other admission bounds. Separate compression buffers from shared hint slabs, compare with uncompressed controls, and measure direct-memory headroom before testing OOM. See [stage-4 evidence](../../if-check-exp/cassandra/stage4-runtime-verification/results/hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous.md). |
| B2 / P2 | bypass · failed-reservation | Memtable and pre-V5 failed-reservation exceptions (separate cases) | Failed acquisition followed by admitted allocation, outstanding operations, overshoot duration/bound and backpressure; bounded-admission intervention. |
| B3 / P2 | bypass · pool-fallback | BufferPool fallback beyond retained pool capacity | Separate pooled/fallback live memory, remaining admission bounds; reserve-before-allocation intervention. |
| B4 / P2 | bypass · release-defect | SerializingCache explicit-clear lifecycle | Fill/clear/idle cycles, ownership/release and residual allocations; healthy release/diagnostic repair control. |
| C4/B5 / P3 | mixed (replacement-overlap / periodic enforcement) | Replacement overlap or periodic index-summary enforcement | Old/new live allocations, enforcement intervals, format/path applicability; changed scheduling/interval control. Classify by whether local contracts hold. |

## First batch and completion

Investigate **C1, B1, C2** in that order unless source reachability or infrastructure
blocks one; record the blocker and continue an independent candidate. *(2026-11-10:
B6 was added to the batch and run first, ahead of B1 and C2, because it came out of
C1's write-path trace and reused that topology knowledge; C1 run 3's sweeps, B1 and
C2 are still outstanding.)* Run source
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
| J2 / P2 | JIRA | Same survey for Hadoop (HDFS, YARN, MAPREDUCE, HADOOP); does not need if-check-exp Hadoop to finish. | `../hadoop/leads/jira-oom-survey.csv` + `.md`. |

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
