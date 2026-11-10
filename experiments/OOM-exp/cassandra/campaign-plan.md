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
are the mechanism rows of the bypass playbook (here *release-defect*). The
sub-direction is the hypothesis chosen up front; a case is separately tagged
**mixed** if the evidence crosses directions (see the C4/B5 row).

| ID / priority | Direction · sub-direction | Hypothesis and workload | Decisive evidence / control |
|---|---|---|---|
| C1 / P1 | convergence · multiplicity | **In progress.** Internode receive private allowances multiplied by loaded peers/links. Run 3 reached 543 MiB of its 544 MiB admission ceiling at N=8 with live senders. Physical-memory and OOM attribution remain open. | Continue the calibrated LARGE-message path. Verify coordinator timeout from measured drainage, then sweep Q=4/16/64 at N=8 and N=4/8 at fixed Q with matched aggregate load. Measure total admitted and live direct memory, reserve saturation, expiry and sender stability. Test a fixed-budget OOM boundary and reduced-Q/N intervention only after a reproducible physical-memory increment. See the [run log](cases/_run-log.md). |
| B1 / P1 | bypass · release-defect | Recorded native-v5 large-request retention lead; repeat identical request/complete/idle cycles | Outstanding ownership/pool slots and live allocation residual versus cycle count; healthy path and restored-release intervention. Distinguish plateau, accounting drift, allocator retention and accumulating leak. |
| C2 / P1 | convergence · concurrency/surge | Concurrent reads individually below an enabled size threshold; sweep actual simultaneous reads | Oversized-query rejection control, retained working sets and executor/admission bounds; no standing pool required. Unset/default thresholds are a separate configuration arm. |
| C3 / P1 | convergence · multiplicity | **Next multiplicity investigation after C1.** DOB retention multiplied by workers holding serialization buffers, at fixed payload and recycle threshold. Prior calibration measured about 337 MiB retained by 44 workers. | Sweep actual buffer-holding workers with matched total traffic/concurrency where feasible. Separate active allocation from idle retention, verify worker bounds, and test whether limiting worker count removes a repeatable fixed-budget failure. Reuse the [DOB calibration](cases/convergence/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom.md). |
| C5 / P2 | convergence · multiplicity | **New candidate.** Compressed hints buffers retained per open destination writer. With LZ4 enabled and fixed hint size, vary the number of destinations whose writers simultaneously retain buffers. | Stage 4 measured 8.04 MiB for one destination and 16.07 MiB for two after accounting for slabs. Verify reachable writer count, replica placement, writer closure and other admission bounds. Separate compression buffers from shared hint slabs, compare with uncompressed controls, and measure direct-memory headroom before testing OOM. See [stage-4 evidence](../../if-check-exp/cassandra/stage4-runtime-verification/results/hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous.md). |
| B2 / P2 | bypass · failed-reservation | Memtable and pre-V5 failed-reservation exceptions (separate cases) | Failed acquisition followed by admitted allocation, outstanding operations, overshoot duration/bound and backpressure; bounded-admission intervention. |
| B3 / P2 | bypass · pool-fallback | BufferPool fallback beyond retained pool capacity | Separate pooled/fallback live memory, remaining admission bounds; reserve-before-allocation intervention. |
| B4 / P2 | bypass · release-defect | SerializingCache explicit-clear lifecycle | Fill/clear/idle cycles, ownership/release and residual allocations; healthy release/diagnostic repair control. |
| B6 / P1 | bypass · accounting mismatch | **New 2026-11-10 (from C1).** Coordinator send queue charges on-wire size, but queued `Message<Mutation>` objects live on heap; tiny-cell mutations make heap ≫ on-wire. The write handler also keeps each `Mutation` until the slow replica answers or the timeout, after it leaves the send queue. Slow replica + fast co-replica (C1 run-3 topology), client only to the measured coordinator. | Heap-to-on-wire ratio R for tiny-cell vs matched blob payload at a full send queue (`pending_bytes` ≈ 132 MiB, `overload_count` > 0); coordinator heap OOM with K ≤ C for tiny cells while blob survives; reserve/timeout intervention. Contract is on-wire bytes by design, so interpretation is documented-unit / sizing gap unless shown otherwise. See [design](cases/candidates/internode_application_send_queue_capacity-accounting-mismatch/design/B6-design.md). |
| C4/B5 / P3 | mixed (replacement-overlap / periodic enforcement) | Replacement overlap or periodic index-summary enforcement | Old/new live allocations, enforcement intervals, format/path applicability; changed scheduling/interval control. Classify by whether local contracts hold. |

## First batch and completion

Investigate **C1, B1, C2** in that order unless source reachability or infrastructure
blocks one; record the blocker and continue an independent candidate. Run source
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

## Scope and progress

Status is keyed by mechanism + allocation domain + capacity/budget regime. Consult
current sections in the custom/default batch logs; their older domain-wide
"exhausted" or arithmetic exclusions describe only the older pool-combination
campaign. New mechanisms are open for source audit. Disk remains skipped and
disk-to-memory causal-chain work deferred; this campaign does not reopen either.

Default-capacity tests record the budget separately. Prefer fixed-budget workload
sweeps, and follow promising diagnostic failures with a deployment-budget arm.
One actual OOM is not enough to infer absence of global protection or an upstream
bug. Confirm the mechanism and report attribution limits.
