# Bypass playbook

Read [verification-protocol.md](verification-protocol.md) first. Method files
live here; cases/logs live under `<system>/`. Cassandra is pinned to 5.0.9.
An agent selects, designs, executes and records candidates within an assigned
attempt/time budget; there is no separate approval gate between design and run.

## Goal and selection

Identify a path or mechanism that allows growth outside a capacity control's
protection, then determine whether it can cause OOM. The suspect path may skip
the check completely. Establish the actual contract before claiming a violation:
a capped pool with uncapped fallback is not automatically a broken pool cap.
Record intentional soft enforcement separately from implementation defects.
A disabled limit is an unprotected configuration, not automatically a bypass.

Start with the system campaign queue, existing stage-4 leads, and source at the
pinned version. Leads may also come from the JIRA and data-flow lead sources
([README](README.md#lead-sources)); record the source label in the case. For Cassandra use [campaign-plan.md](cassandra/campaign-plan.md).
Re-check exact callers, protocols, defaults, allocation ownership and release.
Existing true-positive, weak, or undetermined cases can supply leads; a negative
case supplies no verified cap by itself. Establish an applicable control before
claiming it is bypassed. No candidate is a confirmed defect merely by inclusion.

## Mechanisms and test shapes

| Mechanism | Required comparison |
|---|---|
| Exempt caller, option, or mode | Protected path versus equivalent demand through the exemption |
| Pool fallback | Pool bytes versus separately measured live fallback allocations; identify remaining admission bounds |
| Failed reservation but admitted work | Failed acquisitions, continued allocations, outstanding work, overshoot duration and drainage |
| Periodic/late enforcement | Allocation peaks before enforcement versus interval/order changes |
| Ownership/release defect | Repeated fill/complete-or-clear/idle cycles; residual live allocations versus cycle count and healthy release control |
| Accounting mismatch | Fixed charged usage with varying object shape/copies; identify omitted allocation and lifetime |
| Arithmetic, ordering, race | Specific faulty transition, reachable input, and resulting excess live memory |

## Design and run

Use the common protection map, configuration audit, repetitions and controls.
Write the claim, expected counter/physical-memory trajectories, commands and stop
conditions before the run. Demonstrate the protected path's enforcement where
applicable; for soft targets document the intended timing/overshoot contract.
Measure actual resource consumption independently of the suspect counter.
The bypass claim is physical usage past the **contract** capacity (protocol,
*Classification by measurement*); record the counter alongside it — counter past
capacity means an enforcement failure, counter within it means an accounting or
release bypass.

For retention leads, use identical repeated batches and a defined idle window;
distinguish allocator retention/reuse and logical counter drift from unreleased
live allocations. For overshoot, determine whether outstanding work imposes a
finite bound and whether remaining budget headroom covers it. For temporal gaps,
compare enforcement intervals without silently changing workload or capacity.

Seek a causal intervention such as restored release or pre-allocation reservation.
Save diagnostic patches separately and reproduce the original on unmodified
source. A bounded overshoot or confirmed leak need not reach OOM to be a useful
result; label the achieved endpoint exactly. If background memory is needed to
reach OOM, demonstrate its separate controls and classify the result as mixed.

## Output

Write `<system>/cases/bypass/<constraint>-<mechanism>.md` with four sections:

1. **Constraint and capacity:** pinned source/case links, contract and protection
   map, hypothesis, capacity/budget labels, intentional exception versus defect.
2. **Verification solution:** pre-run claim, executable matched controls and
   suspect path, measurements, repetitions, intervention and stop conditions.
3. **Runtime results:** charged and actual usage, overshoot/residual growth,
   concurrency/completion, per-repeat outcomes, original error and log references.
4. **Conclusion:** protection gap confirmed/refuted/unresolved separately from
   OOM reached/not reached, attribution limits, other controls, and whether an
   upstream defect investigation is justified. Upstream reporting is separate.

Add closed cases to `<system>/cases/_INDEX.md` (a verified OOM by bypass goes in
`<system>/cases/bypass/`, an unresolved one in `<system>/cases/candidates/`,
regime as a label). Append batches to the chronological `<system>/cases/_run-log.md`,
including considered candidates, precise status/range, failed or invalid
attempts, raw-log locations and stopping reason.
Follow the common protocol's owned-node, local-storage and cleanup rules.
