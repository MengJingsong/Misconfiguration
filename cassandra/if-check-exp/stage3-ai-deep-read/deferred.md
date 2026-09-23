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

Keeping these apart from [`negatives.md`](../stage2-ai-preprocessing/negatives.md) is the point: when
(b)/(c) resume, this file is the worklist — no re-scan of the corpus is
needed.

## 1. Live candidate parked by pattern — *resolved 2026-09-22*

**`DataDirectory_getAvailableSpace` (pattern (c), disk) — no longer parked.**
On Jingsong's call it was processed with stage-3 feed **3b** (direct AI
source reading) rather than waiting for the (b)/(c) resumption, and is now a
full case file:
[`../compaction/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md`](../compaction/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md).

This is a **deliberate single-candidate exception** to the pattern-(a)-only
scope, not a reversal of it: feed 3b does not depend on the stage-1 CSV or
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

## 1b. Row surfaced by stage 2, judged and parked by stage 3 — `hasDiskSpaceForCompactionsAndStreams`

Row surfaced 2026-09-22 by the first stage-2 batch (the helper rows inside the four
previously-triaged subtrees). **Passes all three rules; parked because it is
pattern (b).**

- **Capacity check:** [`Directories.hasDiskSpaceForCompactionsAndStreams():551`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L551)
  — `availableForCompaction < toWrite.getValue()`, evaluated per `FileStore`.
- **Limit side:** `availableForCompaction` =
  [`getAvailableSpaceForCompactions():563-568`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L563-L568)
  — the file store's usable bytes, minus `min_free_space_per_drive`, then
  **multiplied by `max_space_usable_for_compactions_in_percentage`**
  ([`Config.java:344`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L344),
  default `.95`, read via `getMaxSpaceForCompactionsPerDrive()`). Two tunable
  config entries on the limit path, not one.
- **Usage side:** the total bytes to write = this compaction's estimated
  output **plus** the remaining write of all compactions already running
  (`CompactionManager.instance.active.estimatedRemainingWriteToDiskBytes()`),
  summed per file store.
- **Verdict path (why (b)):** the comparison does not branch to an
  allocation. It sets a local `hasSpace = false`, continues the loop over
  file stores, and returns the boolean. The decision points are in
  [`CompactionTask.buildCompactionCandidatesForAvailableDiskSpace()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L411):
  `if (...hasDiskSpaceForCompactionsAndStreams(...)) break;` at `:411`, then
  either dropping an SSTable from the compaction via
  `reduceScopeForLimitedSpace()` or, when nothing more can be dropped,
  `throw new RuntimeException("Not enough space for compaction ...")` at
  `:441`.
- **Why it matters — it is not a duplicate of the filed compaction case.**
  `DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace` checks
  *one chosen directory* against *this* compaction's output, at writer-setup
  time, and is skipped entirely on the default disk-boundaries path. This one
  checks *every file store* against *all in-flight compaction output*, before
  the task starts, and it reserves a configurable fraction of the drive
  (`max_space_usable_for_compactions_in_percentage`, default 95%) rather than
  only a flat floor. It also
  has a graceful degradation path — shrink the compaction — that the filed
  case lacks. Different limit, different scope, different disallow effect.
- **How it was found:** the helper query surfaced it via
  `buildCompactionCandidatesForAvailableDiskSpace()`, whose *reported*
  comparisons (`size() > 0`, `sstablesRemoved > 0`) are both noise. The
  method name pointed the read in the right direction and the real check was
  two calls further in. Worth remembering: a helper row's value can be the
  method it names, not the comparison it reports.

**When (b) resumes:** likely name
`DataDirectory_getAvailableSpaceForCompactions-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md`
under a `compaction` or `disk` module — but check §6.1's "derived from
several sources" rule first. `min_free_space_per_drive` and
`max_space_usable_for_compactions_in_percentage` both sit on the limit path,
and the latter is the one a user would tune for *this* check specifically, so
it may be the better constraint name.

## 1c. Found by the P1 pass, parked by pattern — 2026-09-22

### `column_index_cache_size` — pattern (b) — **strong**

- **Capacity check:** [`BigFormatPartitionWriter.indexSamples():113`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L113)
  — `indexSamplesSerializedSize + columnIndexCount * TypeSizes.sizeof(0) <= cacheSizeThreshold`,
  returning the sample list or `null`. Second check site at
  [`:171`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L171),
  which switches to byte-buffer mode at the same threshold.
- **Verdict path:** the `null`/list return is read at
  [`RowIndexEntry.create():227`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L227).
- **Decision point & divergence:** with samples, it builds an `IndexedEntry`
  holding `indexSamples.toArray(new IndexInfo[...])` — the full `IndexInfo`
  array retained in memory. With `null`, it builds a `ShallowIndexedEntry`
  carrying only a file position. **Real object-creation divergence**, so
  Rule 3 is satisfied.
- **Why deferred:** the comparison sets a verdict that a *separate* decision
  point in another class reads — textbook **pattern (b)**, parked by the
  pattern-(a)-only scope. It is a qualifying candidate, not a rejection.
- **When (b) resumes:** trace `cacheSizeThreshold` to `column_index_cache_size`
  (`Config`), and record that raising it retains more `IndexInfo` arrays in
  heap via row index entries.

### `TrackedDataInputPlus_limit` — pattern (c) — weak

- **Guard:** [`TrackedDataInputPlus.checkCanRead():184`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TrackedDataInputPlus.java#L184)
  — `limit >= 0 && bytesRead + size > limit`, which skips to the limit and
  throws `EOFException`.
- **Why deferred:** a guard clause before an allocation that is not inside a
  branch — **pattern (c)**. Also needs `limit`'s origin traced before it is
  clear whether it bounds a deserialized object's size or is merely a stream
  boundary; judge that when (c) resumes.

## 2. Re-audit of earlier rejections under (b)/(c)

**Raised 2026-09-20; parked 2026-09-22.**

Every batch in [`README.md`](README.md)'s coverage table, and every rejection
in [`_INDEX.md`](_INDEX.md), was judged under the older assumption that
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

Recorded so they aren't rediscovered as surprises. Does not block the current
pass:

- The queries capture the **form** only. Rule 3 — do the branches actually
  diverge on object creation? — can be answered **only by the deep-read
  pass**: neither stage 1 nor stage 2 sees the branches.

**Closed 2026-09-22:** the boolean-helper gap (a pattern-(a) check whose
comparison hides behind a helper such as `if (!pool.hasRoom())`, leaving the
`if` itself with no comparison) is now covered by
`HelperGuardedIfStatements.ql`. Stage 1's pattern-(a) input is therefore
`NarrowedIfStatements.csv` **plus** `HelperGuardedIfStatements.csv`.
