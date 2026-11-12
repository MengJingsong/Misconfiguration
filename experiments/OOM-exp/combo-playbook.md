# Combo playbook (convergence + bypass)

Added 2026-11-12. Read [verification-protocol.md](verification-protocol.md),
[default-convergence-playbook.md](default-convergence-playbook.md) and
[bypass-playbook.md](bypass-playbook.md) first. This playbook inherits their
controls, repetitions, outcomes, defaults audit and four-section case format. It
adds a **staged escalation**: start from one convergence sub-direction, and when
it does not reach OOM, stack more sub-directions onto the same budget, then
accounting gaps. At every stage, measure **how far from OOM** the node is.

**Why.** At default constraints and an acceptable budget, single sub-directions
have so far stayed well below the budget. Examples: DOB + hints peaked at about
260 MiB of 512 MiB direct, with a ceiling of about 398 MiB (R6-V); per-worker DOB
retention peaked at 183–195 MiB (C3); the cache overshoot was about 154 MiB at a
2 GiB heap (B7). A negative from one shape does not rule out the sum of several
shapes. Each verified failure so far needed a control that charges less than the
memory it holds (B6, B7).

## Stages

| Stage | Adds | Variable | Proceed when |
|---|---|---|---|
| 0 Ceiling sheet | nothing; arithmetic from source | — | always first |
| 1 Multiplicity | more owners of one local allowance | owner count N | always (the base) |
| 2 Stack | standing pools / independent consumers, concurrency/surge, replacement/maintenance overlap, in the **same budget domain** | one added layer at a time | stage 1 is a measured negative with headroom left |
| 3 Accounting gap | bypass, escape hatch, or counted-vs-real mismatch in a pool already in the stack | the gap (on/off) | stage 2 is a measured negative with headroom left |

A case may start at stage 1 with any multiplicity lead, or at stage 2 from an
existing single-shape negative (reuse its harness and readings as the stage-1
layer). Do not skip stage 0. Stop as soon as a stage reaches the endpoint; the
later stages are not needed.

## Stage 0 — ceiling sheet (before any run)

For the chosen budget domain (heap, JVM direct, or native/cgroup; see below) write
a table, one row per pool or consumer:

| Pool | Domain | Contract C (default rule, `file:line`, resolved value) | Reachable multiplicity (bound and its source) | Predicted max U | Counting basis of K |
|---|---|---|---|---|---|

- **Reachable multiplicity** comes from source: thread pools
  (`native_transport_max_threads`, `concurrent_writes`, shared-pool permits),
  peer or connection counts, writer counts, per-client in-flight limits. State
  which bound binds and whether the client or the server sets it.
- **Ceiling** = baseline + Σ predicted max U + temporary overlap. Compare with the
  budget at 512 MiB, 2 GiB and the auto-resolved value.
- If the ceiling is below the budget, a run can only confirm a negative: run one
  confirming arm, record the margin, and go on to the next stage (or another
  stack). If it is above, the stage is feasible; say which pools carry the excess.
- Write the sheet into the design before any reading (dated, like any design).

## Budget domains

Stack only pools that draw on the same budget; otherwise their sum never meets.

| Domain | Budget | Live reading | Typical pools |
|---|---|---|---|
| Heap | `-Xmx` | post-GC live (GC log, forced-GC heap), histogram/dump per holder | memtable (heap), key/row/counter caches, queued or retained `Mutation`s, read working sets |
| JVM direct | `-XX:MaxDirectMemorySize` | `Bits` reserved/count (JMX `BufferPool` MXBean), dump of `DirectByteBuffer` holders | networking and chunk-cache `BufferPool`s, DOB scratch, hint slabs, internode LARGE frames, Netty response buffers |
| Native / cgroup | container limit (memcg) | memcg `memory.current`, NMT, RSS, `dmesg` | off-heap memtable (JNA `malloc`), off-heap row cache, plus heap + direct as a whole |

A cgroup budget covers all three domains at once. Use it only when the stack
deliberately spans domains, and argue the limit under V7 before any reading.

## The ledger (every arm, every stage)

Record per pool and in total, at the peak and at the end of the arm:

| Pool | Stage added | C (contract) | K (control's own counter) | U (real memory, measured independently of K) | U/C | U/K | Share of budget |
|---|---|---|---|---|---|---|---|

and the **distance to OOM**:

- **Headroom** = budget − peak live (post-GC for heap; reserved for direct;
  `memory.current` for cgroup), in MiB and as % of the budget.
- **Missing multiplicity** = headroom ÷ per-owner footprint, i.e. how many more
  owners (or requests) would close the gap, next to the reachable maximum from
  stage 0. "Needs 50 more peers; at most 8 reachable" is a result.
- **GC pressure** (heap): % of wall time in stop-the-world pauses over the worst
  60 s, against the protocol's service-loss criterion (≥ 90%).

Collect K and U from stage 1 on, not only in stage 3: a U/K above 1 found in an
early stage is the stage-3 lead (B7 came out of R3/R4 dumps this way).

## Stage 1 — multiplicity

Follow the multiplicity rules of [README](README.md#direction-1--convergence): vary
the number of owners holding memory at a fixed per-owner allowance, with matched
total traffic where feasible. Sweep N up to the reachable maximum from stage 0.
Separate memory held while active from memory retained while idle. Report the
ledger at each N and fit footprint per owner.

## Stage 2 — stack

Add one layer at a time, each with its own workload, to the stage-1 load:

- **Standing pool / independent consumer:** fill it to its default cap first,
  then start the other layers (a standing pool parked at its cap is the cheapest
  way to remove headroom).
- **Concurrency / surge:** overlapping requests each below their own per-request
  limit; vary the number of simultaneous requests.
- **Replacement / maintenance overlap:** trigger it deterministically at a planned
  time (e.g. `nodetool flush`, `compact`, `repair`, cache save/load, index-summary
  redistribution) so old and new allocations are live together during the peak of
  the other layers. Uncontrolled timing makes 3/3 unreachable (R5).

After each added layer, rerun the ledger. Check that the layers really coexist:
a layer can shrink another (flush pressure, backpressure, eviction, executor
sharing); report each layer's U alone and in the stack. Order layers by their
expected share of the remaining headroom.

## Stage 3 — accounting gap

For pools already in the stack, test whether real memory exceeds what the control
lets in, using the [bypass-playbook](bypass-playbook.md) mechanisms: accounting
mismatch (U > K), exempt caller or escape hatch, pool fallback, failed reservation
then admitted, release defect, late or periodic enforcement. A gap is shown by
the ledger (U/C or U/K > 1, with an independent U), not assumed. Turn on the
workload shape that maximizes the gap (e.g. tiny-cell mutations for B6, small
keys for B7) while keeping the stack running.

A result that needs a demonstrated gap is tagged **mixed**, as in the protocol.

## Attribution and interventions

Plan one intervention per ingredient before the run, and report which remove the
endpoint (≥ 3 runs each, V4):

- reduce multiplicity (fewer owners or a lower in-flight limit);
- remove one stacked layer (pool off or unfilled, surge serialized, maintenance
  not triggered);
- close the gap (diagnostic build that counts real size, or a lower cap that
  absorbs the excess).

An endpoint that no single intervention removes, but removing any two does, is
reported as joint. An endpoint no intervention removes stays `candidate` (V4).

## Budgets and endpoints

Budgets follow the standing rule (heap/direct ≥ 512 MiB, 2 GiB ideal; argue
cgroup limits case by case under V7). Report each stage's ledger at 512 MiB,
2 GiB and the auto-resolved value where feasible, and search for the largest
budget that still fails. Endpoints, recorded separately: heap OOM, direct/native
OOM, kernel/cgroup kill, GC service loss.

Constraints stay at their defaults (V6). The stage 2 and 3 workloads are
experimental variables; disclose them. Supporting deviations (timeouts, executor
sizes, slow-replica injection) follow the default-convergence audit and make the
result `diagnostic`.

## Stopping rules

- Stop a stage when the ceiling sheet or the measured ledger shows the budget
  cannot be reached in the tested range (record the margin), or when the endpoint
  is reached.
- Stop the case after stage 3, or when no further layer in that domain is
  reachable. A stacked negative states every layer, its measured U, and the
  headroom left.
- State a finite time or attempt limit before execution when none is assigned.

## Output

File the case as the default-convergence playbook says (`convergence/`,
`candidates/` or `negatives/`; regime **default**), named after the stack, e.g.
`<stack-name>--combo`. In the header give the domain, the stages run and the
layers per stage. Begin with the protocol's **Summary** block, then the four
sections with these additions:

1. Ceiling sheet (stage 0) and protection map for every layer.
2. Design per stage, layer order, deterministic triggers, planned interventions.
3. Ledger per stage and arm (C, K, U per pool; total; headroom; missing
   multiplicity; GC pressure).
4. Which stage reached the endpoint (or the final headroom), attribution per
   ingredient, and which gaps were needed (mixed or not).

Append the batch to `<system>/cases/_run-log.md` and the closed case to
`<system>/cases/_INDEX.md`.
