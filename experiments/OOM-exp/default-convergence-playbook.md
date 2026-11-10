# Default-capacity convergence playbook

Read [verification-protocol.md](verification-protocol.md) and
[custom-convergence-playbook.md](custom-convergence-playbook.md). This variant
inherits their eligible shapes, controls, repetitions, outcomes and four-section
case format. A case may replicate one local constraint or use temporary overlap;
a standing pool and two distinct constraints are not required.

## What defaults mean

Leave the tested capacity constraints at their shipped/resolved defaults. Record
for each: source `file:line` for its default rule, resolved value at the chosen
heap/topology, and evidence from config diffs/command lines that it was not set.
Derived defaults must be recomputed after every budget change.

Audit every config/JVM change:

| Class | Treatment |
|---|---|
| Environment | Addresses, paths, topology, instrumentation; disclose even when allowed because they may affect memory |
| Budget | Heap, direct limit, cgroup/process budget; allowed but labeled independently |
| Supporting deviation | Other knobs, including executor sizes, allocation mode, cleanup thresholds, timeouts; justify and test without them where feasible |
| Tested capacity | Must remain at its resolved default; otherwise file a custom-capacity case |

A case without supporting deviations is **default capacities, no supporting
deviations** (historically called "strict default"). Always append the budget
label: automatic/resolved, explicit deployment budget, or deliberately tightened
diagnostic budget. Preserve historical labels but explain them when citing cases.
The existing DOB/hints result is default capacities at an explicit 192 MiB direct
budget; it is not evidence of OOM at the node's automatic budget.

Compare the chosen heap and direct limit with the pinned startup script's resolved
values for this machine. For claims about recommended deployment sizing, cite
version-appropriate operating guidance and record its source/date. Keep heap and
direct-memory guidance separate. Test a larger deployment-budget arm for a
promising diagnostic case when practical, and report the result or blocker.

Workload, schema, concurrency, data volume, timing and topology are experimental
variables; disclose them. Per-table options that are tested constraints must stay
default. A pool off at default contributes nothing; enabling it is a deviation
(and a custom case if its enabling capacity is the tested constraint). An unlimited
default is an unprotected-configuration lead, not a default bounded pool or an
automatically confirmed bypass.

## Picking and sizing

Use the system's campaign queue and this variant's own batch status. Custom-case
exhaustion does not imply default-case exhaustion. Disk remains skipped by request.

Express each capacity in terms of heap/budget, object footprint and multiplicity.
Predict baseline + distinct live increments + temporary overlap. Fixed fractions
alone cannot exclude default convergence when baseline, absolute defaults,
reachable concurrency, or temporary memory are omitted. A fixed absolute pool
occupies a **larger** fraction of a smaller budget. Arithmetic exclusions apply
only to the named consumers, assumptions and tested range.

Try workload multiplicity and overlap at fixed defaults/budget before shrinking
the budget solely to force failure. Verify actual reachable concurrency and any
aggregate or executor bounds. Safe-alone margins must be stated and measured.

## Continuing from a custom case

Reuse its harness and mechanism evidence, then move one capacity at a time toward
default, preserving new dated designs and controls. There are three independent
dials: capacity settings, budget, and workload/multiplicity. Absolute default
capacities do not force a budget-only search: workload can change instance count
or overlap. State which dial changes at each step.

Do not assume monotonicity: lowering a cap can increase flushing or change another
consumer; changing heap can change defaults. At every step confirm the same
allocation mechanism and initiating error. If the mechanism changes, file a new
hypothesis rather than claiming continuation reproduced the original defect.
A direct default-case design is equally valid; a custom predecessor is optional.

## Execution and output

Follow the common protocol for controls, repeated boundary runs, intervention,
measurement and outcomes. All arms use the same budget/build and config except
explicit intervention/deviation tests. Match total concurrency and background
work where relevant. An enabled-threshold arm and an unset/unlimited-default arm
must be labeled separately.

Write the case under the status-first folder that matches its outcome
(`<system>/cases/convergence/` for a verified OOM, `<system>/cases/candidates/`
while unresolved/parked, `<system>/cases/negatives/` for a verified no-OOM),
labeling the capacity regime **default** in the case header and `_INDEX.md`
rather than in a folder name. Keep existing combination filenames (disambiguate
with a `--<regime>`/`--runN` suffix on collision). In the four case sections include:

1. Default rules, resolved values, unchanged-knob evidence, protection map and
   separate capacity/budget labels.
2. Complete defaults audit, prediction/window/range, executable workload and
   controls, repetitions, interventions and stop conditions.
3. Per-arm/per-repeat outcomes and memory trajectories with evidence.
4. Exact conditions establishing a gap or protection, dependency on supporting
   deviations, budget realism and limits of attribution.

Append batch records to the chronological `<system>/cases/_run-log.md` and
closed cases to the system index (`<system>/cases/_INDEX.md`). Preserve
historical results; do not rewrite old runs as if they satisfied newly
introduced requirements.
