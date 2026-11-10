# Convergence playbook (custom capacities)

Read [verification-protocol.md](verification-protocol.md) first. Method files
live here; cases and logs live under `<system>/`. Cassandra is pinned to 5.0.9.
An agent may select, design, execute, and file a batch within its assigned
attempt/time budget. There is no separate approval gate between design and run.

## Goal and eligible shapes

Demonstrate that local controls function while the reachable total of live
allocations exceeds a shared memory budget. Eligible shapes are:

- multiple instances of **one** constraint (connections, threads, peers, tables);
- independent bounded consumers sharing memory;
- overlapping individually bounded requests, with or without a standing pool;
- old/new allocations overlapping during growth, replacement, or maintenance.

A standing floor is optional. Floor/surge describe allocation lifetime, not the
presence of aggregate protection. An aggregate control may exist yet leave
private allowances, temporary copies, or outstanding work insufficiently bounded.
Record a mixed result when a demonstrated bypass contributes to aggregate
exhaustion. Disk pressure affecting drainage is a separate causal-chain
hypothesis, currently deferred.

## Picking cases

Start with the system's campaign plan (for Cassandra,
[campaign-plan.md](cassandra/campaign-plan.md)), its current batch status, and
[constraint survey](cassandra/cases/_constraint-groups.md).
Leads may also come from the JIRA and data-flow lead sources
([README](README.md#lead-sources)); record the source label in the case.
Use if-check-exp source/case/runtime evidence to populate the protocol's
protection map. True positives and false negatives with measured caps are leads;
weak outcomes need confirmation. A true negative is not proof of a usable cap,
but does not exclude other checks or allocation domains with a verified bound.

Prefer the smallest mechanism that addresses an unanswered coverage question.
Two different knobs are not required. Do not combine counters that describe the
same underlying allocation. Count limits qualify when count × live footprint is
meaningful. Inspect executor, queue, connection, and reserve limits before
assuming multiplicity can grow. Preserve explicit skipped/deferred statuses.

## Design and run

Follow the common protocol, including repeated controls and causal intervention.
Hold capacity values and budget fixed while sweeping one workload variable where
possible. For multiple subsystems, run each alone, then align their measured live
usage. Sequential prefill is valid when retained memory overlaps the later load;
sequential workloads that fully recover between steps do not prove convergence.
For multiplicity, vary the number of owners holding memory under the same local
allowance. Include idle owners that retain memory, and measure simultaneous live
footprints. For temporary-only cases measure simultaneous live working sets.
Before the run, check feasibility (Σ contract capacities + baseline > budget);
during it, show every domain's physical usage stays ≤ its contract capacity —
see the protocol's *Classification by measurement*. A domain past its contract
makes the result bypass or mixed.

Predict baseline + distinct live increments + temporary overhead, not merely the
sum of nominal knobs. Verify local enforcement in the combined arm, and record
aggregate admission decisions and outstanding admitted work. Compare original
and intervention arms at matched concurrency, accounting for background tasks.
For diagnostic budgets, pursue a deployment-budget follow-up when practical.

## Output

Write the case under the status-first folder that matches its outcome —
`<system>/cases/convergence/<mechanism-stem>.md` for a verified OOM by
convergence, `<system>/cases/candidates/<mechanism-stem>.md` while it is
in-progress/parked/unresolved, `<system>/cases/negatives/` for a verified
no-OOM. Record the capacity regime (**custom** | **default**) as a label in the
case header and `_INDEX.md`, not as a folder; existing
`<constraint-1>+<constraint-2>.md` names remain valid (disambiguate with a
`--<regime>`/`--runN` suffix on collision). Use a unique descriptive
stem for a single replicated constraint or overlap case. Four sections:

1. **Constraints and capacities:** source/case links, protection map, distinct
   allocations, defaults/chosen values, capacity and budget labels.
2. **Verification solution:** dated hypothesis, arithmetic, workload/dial/range,
   instruments, executable controls/experiment/intervention, repetitions and stops.
3. **Runtime results:** per-arm/per-repeat local and aggregate usage, actual
   concurrency, terminal outcome, original error, log evidence and prediction fit.
4. **Conclusion:** mechanism established or unresolved; which protection failed
   or intervened; boundary/range, interpretation, realism and remaining evidence.

Do not infer absence of an aggregate mechanism merely from OOM. Negative,
protected, invalid, and blocked attempts are also filed once designed and run.
Add closed cases to the system index (`<system>/cases/_INDEX.md`) and append
every batch to the chronological `<system>/cases/_run-log.md`, including
considered/skipped candidates, status changes and stopping reason. Historical
cases remain as filed.
