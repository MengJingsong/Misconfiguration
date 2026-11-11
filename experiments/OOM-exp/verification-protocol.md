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

### Classification by measurement (amended 2026-11-10)

Decide the direction from measurements, per controlled allocation domain:

- **C** = the control's **contract** capacity, including any documented soft
  overshoot (e.g. admit one oversized item when empty, periodic enforcement
  window). Not merely the configured number.
- **U** = peak **physical** live memory owned by that domain, measured
  independently of the control's counter (NMT, heap histogram, direct-buffer
  stats, RSS/cgroup deltas). **K** = the control's own counter.
- **Scope:** compare U against the control whose contract claims to cover that
  memory, fixed in the protection map *before* the run. The same bytes can look
  in-bounds against a per-owner cap and uncovered against an aggregate one
  (C1: per-connection exclusive ≤ Q, but N·Q is outside G by contract, so it is
  multiplicity convergence, not a G bypass).

| Observation | Classification |
|---|---|
| U ≤ C in every domain, and ΣU (simultaneous) + baseline > budget | **Convergence** (pools need not be full) |
| U > C, K > C | **Bypass** — enforcement failure (late/periodic check, admitted after failed reservation, race) |
| U > C, K ≤ C | **Bypass** — accounting omission/mismatch or release defect |
| A bypass excess plus other domains are both needed for the OOM | **Mixed** |
| No applicable control, or control disabled | **Unprotected** (neither) — configuration or accumulation, see below |

Overshoot within the documented contract is an intentional exception, not a
bypass. Track U as peak **and** trend: transient overshoot (periodic enforcement)
and growth across fill/clear/idle cycles (release defects) are missed by a single
sample. A bypass with U > C is a result without OOM. For convergence, check
feasibility first: if Σ contract capacities + baseline < budget, convergence is
impossible even with every pool full, under that configuration and budget.

### Unprotected results (amended 2026-11-10)

New evidence: the JIRA and data-flow lead sources (README, *Lead sources*) target
memory that no capacity check guards. Such results are **in scope** and
recorded as **unprotected**, not as a third direction, in two kinds:

- **Unprotected configuration:** a control exists but is disabled or set to
  unlimited (default or custom). Label the setting; it is not a bypass.
- **Unprotected accumulation:** no control applies to the holder at all, or the
  only bound is implicit (concurrency × size, timeout × rate) and not enforced
  as a memory limit.

An unprotected accumulation is a finding only when the workload stays within
documented guardrails, protocol limits and accepted configuration, and the
excess comes from the system's own accumulation (retention, copies,
amplification, backlog) rather than from input the system is documented not to
accept. State whether the project documents the behavior as by design. The
protection map, controls, repetitions and intervention rules apply unchanged;
the intervention is usually adding a bound and showing the failure stops.
File these cases in the status-first folders with the label **unprotected**.

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
- GC-driven service loss, with predefined latency/availability criterion
  (default criterion under *Verification status*);
  **not an OOM** unless an actual OOM event is evidenced.
- Protective rejection/backpressure; no failure within the tested range.
- Invalid/blocked experiment (e.g. workload never started or wrong path).

Preserve the initiating error if Cassandra forces another OOM during shutdown.
A bypass can be confirmed without OOM; an OOM can occur without establishing the
proposed mechanism. Report both facts. Observing OOM does not prove no aggregate
control exists: it may be incomplete, late, or sized above available headroom.

## Verification status (amended 2026-11-11)

New evidence: B6 runs 1–2 (Cassandra) confirmed a bypass (U > C, K ≤ C) and, on a
deployment-sized heap, sustained GC service loss with only intermittent OOM. The
earlier rules had no explicit promotion rule and no status for a confirmed gap
that does not end in OOM, so such results could only stay in `candidates/`.
This section makes the rule explicit. It does not lower the evidence bar.

**Promotion rule.** A case is *verified* only when all of V1–V5 hold for one
fixed condition (same build, configuration, budget and workload):

| | Requirement |
|---|---|
| V1 Repetition | The claimed endpoint is reached in ≥ 3 runs from clean starts. Report n/N; a rate below N/N is allowed if stated in the Result phrase. |
| V2 Matched control | The nearest surviving control (convergence: component or low multiplicity alone; bypass: protected path or matched payload) runs ≥ 3 times under the same budget/build and does not reach the endpoint. |
| V3 Measurement | U is measured independently of K for each domain claimed (*Classification by measurement*). |
| V4 Intervention | The causal intervention removes the endpoint in ≥ 3 runs at matched or recorded load. If infeasible, state why and name the missing attribution; the status then carries `(no intervention)`. |
| V5 Initiating failure | OOM: the first error with its thread/stack, or the kernel/cgroup OOM record, plus a histogram or dump at or near failure showing the claimed holder. Service loss: the GC log over the window. |

**Statuses** (the `_INDEX.md` Status column):

| Status | Meaning | Folder |
|---|---|---|
| `verified-OOM` | V1–V5 met; endpoint is an OOM (heap, direct, other native, or kernel/cgroup kill) | `convergence/` or `bypass/` by direction |
| `verified-gap` | V1–V5 met; the protection gap is confirmed but the endpoint is not OOM: **service loss**, or for bypass a sustained **overshoot** (U > C) or growing **leak** | `convergence/` or `bypass/` by direction |
| `candidate` | anything not yet meeting V1–V5 (in progress, parked, unresolved) | `candidates/` |
| `negative` | V1–V3 met and no failure within the stated tested range | `negatives/` |

**Service-loss criterion (default).** ≥ 90% of wall time in stop-the-world GC
pauses over a window of ≥ 60 s, from the GC log. A design may predefine another
criterion before its readings; record which one was used.

**Conditions label.** Every verified status also carries `deployment` or
`diagnostic`:

- `deployment`: every setting is a default or an accepted, documented value; the
  budget is deployment-sized (state the reasoning); faults, if any, are external
  (disk, network, process), and no instrumentation (Byteman, patches) alters timing.
- `diagnostic`: the result depends on at least one supporting deviation (raised
  timeouts, injected delays, a tightened budget, a disabled subsystem used only to
  isolate the path). Name the deviations in the case file.

Example Status cell: `verified-gap · service-loss · deployment`.

**Cases filed before 2026-11-06** keep their status with the suffix
`(pre-protocol)`. They were judged under earlier rules, often from a single
failing run, and must be rechecked against V1–V5 before being cited as verified
in an upstream report. Do not move them between folders on this account alone.

## Case evidence and batch status

Keep the four case sections: (1) constraints/protection map and configuration
labels, (2) dated pre-run design and executable commands, (3) per-arm/per-repeat
results with log references, (4) conclusion and limits of attribution.
Start every case file with a **Summary** block, right after the header lines and
before section 1, stating in short plain words (a few bullets) the **conclusion**
(what happened, outcome type, how conditional) and the **root cause** (which
control fails to bound which memory, and why). Keep it consistent with section 4;
numbers and caveats stay in the body. (Amended 2026-11-11.) Preserve
predictions; record changed designs as dated amendments before new readings.
Record raw-log location, small committed excerpts, harness, config diffs, source
patches, original failure, controls, intervention, and repeat counts.

**Filing a verified case (amended 2026-11-11).** When a case meets the promotion
rule (*Verification status*), it keeps **one final case file** in its status
folder: Summary, the four sections, a per-condition status table and a V1–V5
table citing which run supplies each piece of evidence. The per-run case files
move **verbatim** into `history.md` in the same case folder (headings demoted one
level, cross-links pointed at its anchors); designs, harnesses and log excerpts
stay beside it. Nothing is deleted: predictions and original results remain
readable, and the chronological run log keeps its entries with links repointed.

Track progress by **mechanism + allocation domain + configuration regime**.
Statuses: open, parked (specific blocker), exhausted within an explicitly tested
range, skipped by request, or deferred. Arithmetic-only exclusions apply to the
modeled consumers/range, not an entire memory domain. Preserve historical rows;
new scope is recorded in a dated current table. Do not silently reopen skipped
work. Append a batch record even when no candidate succeeds. Commit/push only
when requested.
