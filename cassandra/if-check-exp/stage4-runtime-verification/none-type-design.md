# Stage 4 — verification design for `none`-type cases (operand sweep)

Recorded 2026-10-28 as a **proposal**; no case has been run with it yet. It is written to be reused for every `none`-type case, now and later.
The protocol in [`README.md`](README.md) still applies (audit, freeze, run 1, self-check, verdict); this file only says how to design the
experiment when the case has no limit to vary.

## 1. When this applies

A case is **`none` type** when the compared line has no limit that anyone sets: no yaml entry, no JVM property, no hard-coded constant that
bounds a resource, no runtime-queried value, no per-table option and no query parameter. Stage 3 estimates all of them `negative`
(50 cases at 2026-10-28: 8 already run, 42 not run; 11 of the 42 have a real unit and cluster design, 31 declare both tiers `n/a`).

For a case with a limit, the stage-4 question is "does usage follow the **limit**?" (dose-response on the limit). A `none` case has no limit,
so the same question is asked of the **operand** instead:

> **Does the memory or disk usage that the check guards follow the operand, and does the check's outcome change what is allocated?**

Both halves are needed. Usage often follows an operand only because the operand *is* the data (a row count, a buffer length): that alone says
nothing about the check. The check caps usage only if flipping its branch changes the allocation.

## 2. Classify the operand first (step 0 of the audit)

Record the kind in results §1. It decides the instrument and whether the cluster tier is worth running.

| Kind | The operand is | Examples | Sweep | Instrument | Cluster tier |
|---|---|---|---|---|---|
| **1. Count or size of held data** | a count or size of a collection or buffer that is already in memory | `ResultSet.isEmpty()` (`rows.size()`), restriction counts, clustering counts, remaining counts | the count across the branch point: 0, 1, small, large (at least four values) | per-call allocation; heap only if the data itself is large | only if the sweep reaches MiB |
| **2. Value, flag or character** | a boolean, enum, sign, bit or character; no size | equality tests, `isNegative`, modulo precision tests, header-bit decodes, `isQuoted` | both sides of the branch, plus one more value per side | per-call allocation (exact to a few kB) | **no**: a fixed-size object is below heap noise (about ±16 MiB with G1) |
| **3. Requested or current buffer length** | a capacity or length that a caller sets | `resizeTo(newCapacity)`, `capacity(newCapacity)` | the length over at least three orders of magnitude, both sides of the equality or growth point | retained heap and per-call allocation | yes, if the sweep reaches the heap |

A case whose operand fits none of these is sent back to stage 3 as feedback, not improvised.

## 3. The design (fill into B2 / B3 of the case file)

This replaces the `n/a: no constraint` text; it is a **dated amendment before the freeze** (the audit applies it), because the case file as filed
declares the tiers `n/a`. If the audit cannot make a design for a case, the `n/a` stays and the results file closes the case as
*Confirmed from source, not run* (not a true negative; see §6).

1. **Trigger.** Find the production caller that reaches the check and drive it from a unit test or the smallest real workload. Prove the check
   executed (Byteman counter, a log line, or the method's return value). A run in which the check never executed is *Invalid*.
2. **Sweep.** Vary the operand over the values chosen for its kind (table above). At least three values, and **both sides of the branch**.
   State the values before the run.
3. **Measure the guarded quantity, per branch.** Not the heap in general: the allocation or retained size of the object the check guards, taken
   once per value. Kind 2 and the unit tier of kind 1 use `ThreadMXBean.getThreadAllocatedBytes` around the call (as in
   `harness/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided/`), repeated at least 5 times per value; report the median and range.
4. **Branch-flip comparison.** For each pair of values on opposite sides of the check, compare the allocation at equal operand magnitude where
   possible (for example 1 row vs 0 rows, and 1,000 rows via the path with and without the check's effect). The finding is the **difference caused
   by the branch**, separate from the growth caused by the operand.
5. **Positive control.** The same instrument on a known capping setting that binds on the same resource (a closed `Confirmed` case, for example
   `memtable_heap_space`), shown to move the reading. Without it, "flat" cannot be told from "the instrument could not see an effect".
6. **Noise floor.** Run the instrument twice on identical input and record the difference. A branch effect smaller than this is "not resolved",
   never "none".

## 4. Prediction and conclusions table (frozen before any reading)

State numbers: the expected per-call allocation for each value, and the tolerance. Every file needs at least these rows.

| Reading | Row | Verdict | Effect on the constraint |
|---|---|---|---|
| Allocation (or retained size) independent of the branch, operand sweep flat or growing only as the data itself grows; control moved | usage does not follow the check | **Confirmed** | `does not cap` |
| Allocation differs by branch by more than the noise floor and the difference is explained by what the branch skips or allocates | the check gates an allocation | **Refuted** | `caps` (or `caps only on some paths (bypass)`) |
| Usage grows with the operand, but equally on both branches | usage follows the data, not the check | **Confirmed** | `does not cap` |
| Control did not move, or the check never executed | the experiment could not show an effect | **Not confirmed** / **Invalid** (never Confirmed) | `undetermined` |
| Difference below the noise floor | not resolved | **Not confirmed** | `undetermined` |

## 5. Outcome class

Use the README's definition (stage-3 estimate against the stage-4 effect). Almost every `none` case is a `negative` estimate, so the expected
outcomes are: *true negative* (does not cap), *false negative* (the branch gates an allocation) and *undetermined*.

## 6. What to claim, and what not

- **Do not report a `n/a` case as a true negative.** A case closed from source alone is recorded as *Confirmed from source, not run* with the
  reason; the index cell says `n/a` and the outcome class column stays empty, so the true-negative count only holds measured cases.
- A kind-2 result is a **unit-tier measurement only**; say so in the results file. The cluster tier is declared `n/a: operand has no size`
  with the noise figure above as the reason.
- Note when the operand is the data itself (kind 1 and 3): "usage follows the operand" is expected there and is not a positive finding.
- Do not tune the sweep values or the tolerance after a reading (README, "Predictions are not tuned to data").

## 7. Adapting it to a new `none` case

1. Read the case file's A1 to A3 and find the operand and its kind (§2).
2. Write the §3 steps into B2 (and B3 if the kind allows) as a dated audit amendment; fill the §4 rows with numbers.
3. Reuse the instruments of a closed case: per-call allocation from `batch_size_fail_threshold`, the Byteman counter pattern from any closed
   `autonomous` file, the retained-heap reader from `transform-stack-capacity-splice-newCount--autonomous`.
4. Run, self-check, file the verdict as for any other case.

## 8. Status

- Proposal only. The eight `none` cases already closed (`transform-stack-capacity-splice-newCount`, the two `hints-*` buffer cases, `sai-SegmentRowIdOrdinalPairs-add-capacity`,
  `compression-metadata-writer-addOffset-maxCount`, `transition-bytes-collector-add-buffer-length`, `trie-pathreconstructor-keybytes-addPathBytes-growth`, `largestRatio-flushLargestMemtable`)
  were run with a design written for each case before this file existed; they are examples of kinds 1 and 3, not of this template.
- Counts by kind among the 31 `n/a` cases (approximate, from the Ground text): kind 1 about 8, kind 2 about 18, kind 3 about 5.
- Suggested order: kinds 1 and 3 first, then kind 2 as a unit-only batch.
