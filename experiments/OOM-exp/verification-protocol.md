# OOM verification protocol

Effective 2026-11-06 for new runs. Read this together with the selected playbook.
Historical results remain as filed; amendments must identify new evidence and dates.

## Question and classifications

Under which reachable workloads and accepted configurations do individual and
aggregate capacity controls fail to keep live memory within its budget?
A reproducible counterexample establishes a gap under those conditions; passing
runs establish protection only within the tested range.

- **Convergence:** local controls work, but multiple instances, independent
  consumers, or overlapping temporary allocations exceed a shared budget.
- **Bypass:** a path, accounting omission, release defect, delayed enforcement,
  or faulty reservation allows allocations outside a control's protection.
- **Mixed:** a demonstrated bypass contributes to aggregate exhaustion.

Separately classify the interpretation: intentional exception/soft target,
configuration-sizing or validation gap, or suspected implementation defect.
A disabled limit is an unprotected configuration, not automatically a bypass.
A retention cap is not necessarily a cap on all allocations using that pool.

## Protection map (required before execution)

Record one row per distinct allocation domain, citing the pinned source and
relevant if-check-exp case/results. Existing verdicts are leads, not substitutes
for checking the exact path, scope, and configuration used here.

| Field | Required evidence |
|---|---|
| Allocation and ownership | Allocation site, owner, release/reuse point; identify aliases of the same allocation |
| Local contract | Charged quantity, units, threshold, hard cap versus soft target/retention cap |
| Scope and multiplicity | Per request/connection/thread/table/peer/process; actual simultaneous instances and what bounds them |
| Aggregate coverage | Reservations, executor/queue bounds, backpressure, exceptions, and uncovered allocations |
| Lifetime | Standing, transient, replacement overlap, delayed cleanup; when memory is actually reusable |
| Budget | Heap, JVM direct-buffer limit, or process/cgroup memory; native routes covered by each metric |

Count-based controls are eligible when live object footprint is measured or
bounded. No global byte counter does not imply unlimited reachable concurrency.

## Configuration and budget audit

Record source tag and repository commit, build/patches, OS/kernel, JDK, GC,
CPU/RAM, swap, cgroup version/limits, command lines, and complete config diffs.
Classify each change as environment, budget, capacity, or supporting deviation.
Even environment/topology changes can affect memory and must be disclosed.
Label capacity settings (default/custom) independently from budget selection
(automatic/resolved, explicit deployment budget, deliberately tightened diagnostic
budget). Record all resolved values, including defaults derived from heap size.
Do not equate default capacities with an entirely default deployment.

## Design and execution

1. State the mechanism and predicted protective response before readings. Name
   the stopping budget (wall time, attempts, maximum workload/resources).
2. Confirm reachability at modest load. Measure completed operations and actual
   concurrency; client thread count alone is insufficient. Verify the intended
   check rejects or defers an oversized operation when applicable.
3. Predict peak memory as baseline plus distinct incremental live allocations
   plus temporary/unaccounted memory. Avoid adding complete standalone process
   totals (which double-count baseline). For replicated instances use measured
   instance count × footprint; for count caps also vary object size. Show error
   bounds and which combinations of peaks are reachable.
4. Calibrate multiplicity, footprint, and overlap separately. Measure whether
   other controls arrest growth. Fix one dial for the boundary search; step it
   geometrically then refine the surviving/failing interval. Do not assume
   monotonic behavior when configuration changes alter reclamation or defaults.
5. Run matched controls and experiment arms under the same budget/build. Match
   payloads, data state, background work, and total concurrency where relevant.
   For convergence show components or low multiplicity safe alone (declare a
   margin; 30% is a starting target, not a universal validity rule). For bypass
   compare protected and suspect paths. Reuse controls only with documented
   equivalence of configuration, workload, instrumentation, and initial state.
6. Repeat the proposed failing condition and nearest surviving control at least
   three times each from clean starts. Report n/N and peak distributions, even
   for standing pools. Expand repetitions if timing produces mixed outcomes.
7. Attempt a causal intervention: remove one consumer, bound multiplicity,
   restore release, or reserve before allocation. A diagnostic patch belongs in
   a separate build and its exact diff must be saved; reproduce the original
   failure on the unmodified build. Record throughput/rejection rates so an
   intervention that stops useful work is not mistaken for effective protection.
   If an intervention is infeasible, document the missing attribution evidence.
8. Stop after the planned endpoint, preserve logs, recover and clean up only
   processes/state created for the run. No arbitrary escalation after an OOM.

Use only allocated researcher-controlled nodes; one measured experiment per
victim node at a time. Peers and clients may run on other owned nodes. Build and
write data, commit logs, dumps, and full run logs on local storage, not shared
NFS. Isolate victim budgets so the controller remains available. Disk-exhaustion
and disk-to-memory causal-chain experiments remain skipped/deferred until
explicitly reopened; do not infer reopening from this protocol.

## Measurement and outcomes

Capture synchronized timestamps, admissions/rejections, local/aggregate counters,
heap/GC, relevant direct/native allocations, process memory, cgroup usage/events,
and workload completion/latency. Choose a sampling interval shorter than the
expected growth/overlap window. Validate instrumentation overhead. Intrusive
histograms, forced GC, and dumps belong on failure or separate diagnostic runs
when they alter the mechanism. RSS alone does not establish a leak: distinguish
live allocations from allocator retention. A counter drift alone does not prove
physical memory growth. Direct-buffer metrics do not cover every native route.

Record the mechanism verdict separately from the terminal outcome:

- Java heap OOM; JVM direct-buffer OOM; other native allocation OOM (give cause).
- Kernel/container OOM-kill, supported by kernel or cgroup event evidence.
- GC-driven service loss, with predefined latency/availability criterion;
  **not an OOM** unless an actual OOM event is evidenced.
- Protective rejection/backpressure; no failure within the tested range.
- Invalid/blocked experiment (e.g. workload never started or wrong path).

Preserve the initiating error if Cassandra forces another OOM during shutdown.
A bypass can be confirmed without OOM; an OOM can occur without establishing the
proposed mechanism. Report both facts. Observing OOM does not prove no aggregate
control exists: it may be incomplete, late, or sized above available headroom.

## Case evidence and batch status

Keep the four case sections: (1) constraints/protection map and configuration
labels, (2) dated pre-run design and executable commands, (3) per-arm/per-repeat
results with log references, (4) conclusion and limits of attribution. Preserve
predictions; record changed designs as dated amendments before new readings.
Record raw-log location, small committed excerpts, harness, config diffs, source
patches, original failure, controls, intervention, and repeat counts.

Track progress by **mechanism + allocation domain + configuration regime**.
Statuses: open, parked (specific blocker), exhausted within an explicitly tested
range, skipped by request, or deferred. Arithmetic-only exclusions apply to the
modeled consumers/range, not an entire memory domain. Preserve historical rows;
new scope is recorded in a dated current table. Do not silently reopen skipped
work. Append a batch record even when no candidate succeeds. Commit/push only
when requested.
