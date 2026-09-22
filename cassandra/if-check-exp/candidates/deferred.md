# Deferred — read but not yet judged

Rows and follow-ups that are **undecided**, not refused. Everything here is
parked by the scope decision in
[`../README.md` §7.5](../README.md): candidate triage is currently restricted
to enforcement **pattern (a)** (the capacity check is itself the deciding
`if`), while patterns **(b)** (check sets a verdict read by a separate
decision point) and **(c)** (guard clause before an allocation outside any
branch) are left untouched rather than half-done.

**Patterns (b) and (c) are parked, not descoped.** They remain in scope, their
rules in [`../README.md` §3.2](../README.md#32-enforcement-patterns) stand
unchanged, and they resume once pattern (a) is finished. Nothing here has
been judged against them.

Keeping these apart from [`negatives.md`](negatives.md) is the point: when
(b)/(c) resume, this file is the worklist — no re-scan of the corpus is
needed.

## 1. Live candidate parked by pattern — *resolved 2026-09-22*

**`DataDirectory_getAvailableSpace` (pattern (c), disk) — no longer parked.**
On Jingsong's call it was processed with discovery **method 1** (direct AI
source reading) rather than waiting for the (b)/(c) resumption, and is now a
full case file:
[`../compaction/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md`](../compaction/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md).

This is a **deliberate single-candidate exception** to the pattern-(a)-only
scope, not a reversal of it: method 1 does not depend on the stage-1 CSV or
on the unwritten (b)/(c) queries, so one already-identified pattern-(c)
candidate could be written up without reopening (b)/(c) triage. Everything
else in this file stays parked.

**Worth carrying forward when (b)/(c) resume:** writing it up showed the
guard **does not dominate** the allocation — on the default
`diskBoundaries != null` path the `SSTableWriter` is created with no
disk-space check at all. Pattern (c) asks for exactly this to be checked and
recorded, and the answer was "no" in the common case. Two lessons for the
(c) triage pass: (1) non-domination is a *finding to record*, not grounds for
rejection under Rule 3; (2) it is invisible in a stage-1 CSV row, which shows
only the comparison — establishing it requires reading the callers, so
budget for that in the (c) pass.

## 2. Re-audit of earlier rejections under (b)/(c)

**Raised 2026-09-20; parked 2026-09-22.**

Every batch in [`README.md`](README.md)'s coverage table, and every rejection
in [`../_INDEX.md`](../_INDEX.md), was judged under the older assumption that
a capacity check is an `if` whose own branches decide allow vs. disallow —
i.e. pattern (a) only. Patterns (b) and (c) were added to
[`../README.md` §3.2](../README.md#32-enforcement-patterns) afterwards.

- **What needs re-reading:** rows rejected *solely* because "the `if`'s own
  branches don't diverge". Under (b) the compared value may be stored or
  returned and consumed elsewhere; under (c) the allocation may sit outside
  any branch behind a guard. Such a rejection is not wrong, just incomplete.
- **What does not:** rejections on pattern-independent grounds — thread-pool
  or concurrency caps, rate limiters, config validation, time-based checks,
  writer rollover. Those stand settled regardless of pattern.
- **Scope of the re-read:** the four batches triaged so far — `concurrent/`,
  `cache/`, `transport/`, `db/compaction/`.
- **How to run it:** fold it into the stage-2 pass when (b)/(c) resume,
  rather than as a separate exercise — that pass re-reads those batches from
  stage 1 anyway.

## 3. Stage-1 queries needed before (b)/(c) can be triaged

The current pipeline only sees comparisons inside `if` conditions.
`NarrowedIfStatements.ql` selects `BinaryExpr` comparisons whose
`getEnclosingStmt()` is an `IfStmt` — which is precisely pattern (a), and
therefore exactly the right filter under the present scope, needing no
changes.

But it **structurally cannot** surface a (b)/(c) check written as a ternary,
an assignment, a `return` expression or a method argument. Known miss: the
`cdc_total_space` comparison in `CDCSizeTracker.processNewSegment()` line
335 is a ternary inside a method argument, so it never appeared in the
results — it was found by direct AI search instead. That case is the standing
evidence that this gap is real, not theoretical.

Three structural (still non-keyword) queries are specified in the
[CodeQL pipeline README](../../../codeql-queries/cassandra/queries/if-check-exp/README.md)
and **none is written yet**:

1. **Comparisons anywhere** — the same numeric narrowing, but over all
   comparison expressions rather than only those inside an `IfStmt`
   condition, reporting the enclosing statement kind.
2. **Guard clauses** — `if` statements with a numeric comparison whose
   then-branch ends in `throw` or `return`, for pattern (c); candidates are
   then checked for an allocation the guard dominates.
3. **Verdict links** — writes of a boolean/enum field (or a returned
   boolean/enum) whose value derives from a comparison, joined to the `if`
   conditions that read that field or call that method, for pattern (b).

These are prerequisites for triaging (b)/(c), **not** for the pattern-(a)
pass. As with the existing queries, they only shrink the search space;
whether a row qualifies is still decided by reading it.

## 4. Known limits of stage 1 even for pattern (a)

Recorded so they aren't rediscovered as surprises. Neither blocks the current
pass:

- The query captures the **form** only. Rule 3 — do the branches actually
  diverge on object creation? — remains entirely a stage-2 judgment.
- A pattern-(a) check whose comparison hides behind a boolean helper (e.g.
  `if (!pool.hasRoom())`) keeps its comparison in the callee, so the `if`
  itself carries no comparison and the row will not appear. Stage 1 is a
  near-complete superset for pattern (a), not a provably complete one.
