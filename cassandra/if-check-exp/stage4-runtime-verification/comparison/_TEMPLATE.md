# [case-file stem] — solution comparison  <!-- file: comparison/[case-file stem].md -->

> **Long-path case:** [`[case-file stem]`](../../stage3-ai-deep-read/long-path/cases/[case-file stem].md)
>
> **Short-path solution:** [`[case-file stem]`](../../stage3-ai-deep-read/short-path/cases/[case-file stem].md)
>
> **Status:** compared / run plan filed / runs done / conclusions filed

Written by a fresh AI session that wrote neither solution; no human gate. The
rules are in the README's [Solution comparison](../README.md#solution-comparison).
Edit neither solution.

## 1. What was compared

| Field | Content |
|---|---|
| Long-path version | the commit that holds the case file, and the hash of §9's text (`sed -n '/^## 9\. /,/^## 10\. /p' <case file> \| git hash-object --stdin`) |
| Short-path version | the commit, and `sha256sum` of the file — it must equal the value in `short-path/_INDEX.md` |
| Compared by / date | |

## 2. The seven points

| # | Point | Rating (Same / Differs, immaterial / Differs, material) | Long path | Short path |
|---|---|---|---|---|
| 1 | Constraint named | | | |
| 2 | Mechanism claimed | | | |
| 3 | Knob and values | | | |
| 4 | Workload | | | |
| 5 | Instruments and observables, and the gaps they name | | | |
| 6 | Predictions | | | |
| 7 | What would refute the claim | | | |

Cite the section on each side (long: §4, §5, §6, §9a–§9e; short: A1–A3, B3–B8).

## 3. Outcome

**Can one run produce the readings both solutions call for, and settle both
predictions?** yes / yes, with additions / no — and why, in two or three sentences.

**Outcome:** Equivalent / Partly different / Different

## 4. Run plan

- **Equivalent:** one run from the long-path runbook; results file `results/[case-file stem].md`.
- **Partly different:** one run on the union. List the additions (arms, observables, knob values), who contributed each, and where the union is written down (results §1, harness path).
- **Different:** two runs. Results files `results/[case-file stem].md` and `results/[case-file stem]--short.md`; harness `harness/[case-file stem]--short/`. Say what makes them incompatible.

## 5. Conclusions — filled after the runs

| Path | Run (results file) | Prediction row matched | Verdict | Date |
|---|---|---|---|---|
| Long | | | | |
| Short | | | | |

**Do the conclusions agree?** yes / no. If no: the point where the designs
differ, how it was settled (re-run, or settled against the readings), and which
conclusion was wrong and why.

**What each design could see that the other could not** — findings only one
design's observables or arms produced, or none.
