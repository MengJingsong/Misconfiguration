# Cassandra OOM campaign — 2026-11-06

Status: **planned; no new runtime results**. Source: Cassandra 5.0.9. Read the
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
| C1 / P1 | convergence · multiplicity | Internode private allowances multiplied by active peers/links; hold capacities/reserves, message size and victim budget fixed, sweep active peers | Private/reserve counters, live memory and admission decisions; low multiplicity control and bounded-multiplicity intervention. Start with small messages; audit actual link types. Native transport is a separate case. |
| B1 / P1 | bypass · release-defect | Recorded native-v5 large-request retention lead; repeat identical request/complete/idle cycles | Outstanding ownership/pool slots and live allocation residual versus cycle count; healthy path and restored-release intervention. Distinguish plateau, accounting drift, allocator retention and accumulating leak. |
| C2 / P1 | convergence · concurrency/surge | Concurrent reads individually below an enabled size threshold; sweep actual simultaneous reads | Oversized-query rejection control, retained working sets and executor/admission bounds; no standing pool required. Unset/default thresholds are a separate configuration arm. |
| C3 / P2 | convergence · multiplicity | DOB retention multiplied by workers that actually serialize; fixed payload/cap | Idle retained versus active buffer size; matched total traffic/concurrency and worker count, building on DOB/hints harnesses. |
| B2 / P2 | bypass · failed-reservation | Memtable and pre-V5 failed-reservation exceptions (separate cases) | Failed acquisition followed by admitted allocation, outstanding operations, overshoot duration/bound and backpressure; bounded-admission intervention. |
| B3 / P2 | bypass · pool-fallback | BufferPool fallback beyond retained pool capacity | Separate pooled/fallback live memory, remaining admission bounds; reserve-before-allocation intervention. |
| B4 / P2 | bypass · release-defect | SerializingCache explicit-clear lifecycle | Fill/clear/idle cycles, ownership/release and residual allocations; healthy release/diagnostic repair control. |
| C4/B5 / P3 | mixed (replacement-overlap / periodic enforcement) | Replacement overlap or periodic index-summary enforcement | Old/new live allocations, enforcement intervals, format/path applicability; changed scheduling/interval control. Classify by whether local contracts hold. |

## First batch and completion

Investigate **C1, B1, C2** in that order unless source reachability or infrastructure
blocks one; record the blocker and continue an independent candidate. Run source
and modest-load validation before exhaustion. The delivered batch consists of
three investigations with source map, executable design/harness, matched controls,
results or explicit blockers, boundary/repeat evidence, and causal intervention
where feasible. A protected/negative result is useful and is not discarded.

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
