# Deferred — the (b)/(c) worklist, now empty

Rows and follow-ups that are **undecided**, not refused.

**Unparked 2026-09-25, and cleared 2026-09-28.** All three enforcement
patterns are in scope
([`../README.md` §7.5](../README.md#75-active-scope-decisions-revised-2026-09-25)),
so nothing new arrives here: a (b) or (c) row is read and judged like any
other. The three entries this file held were the cheapest rows in the corpus,
because the reading behind them was already done — all three have now been
judged.

**No row in this file is awaiting judgement.** One scheduled follow-up
remains: the §2 re-audit, folded into the band-A pass.

| # | Entry | Pattern | Outcome, 2026-09-28 |
|---|---|---|---|
| 1 | `hasDiskSpaceForCompactionsAndStreams` (§1b) | (b) | **Filed** — [`max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md`](cases/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md) |
| 2 | `column_index_cache_size` (§1c) | (b) | **Filed** — [`column_index_cache_size-indexSamples-cacheSizeThreshold.md`](cases/column_index_cache_size-indexSamples-cacheSizeThreshold.md) |
| 3 | `TrackedDataInputPlus_limit` (§1c) | (c) | **Refused, Rule 1** — `limit` is the row's own serialized length, read from the data being deserialized. See [`rejected.md`](rejected.md), batch 2026-09-28. |
| 4 | The §2 re-audit | both | **Still scheduled** — rejections made under the old (a)-only assumption; run it inside the band-A pass, not separately. |

The per-entry sections below are kept as the reading record: they are what
made items 1–3 cheap to resolve, and §3–§4 document stage 1's limits
independently of any one row. Keeping this file apart from
[`rejected.md`](rejected.md) is still the point — nothing here was refused
*as a class*, and item 3's refusal now lives in the rejection store where it
belongs.

## 1. Live candidate parked by pattern — *resolved 2026-09-22*

**`DataDirectory_getAvailableSpace` (pattern (c), disk) — no longer parked.**
On Jingsong's call it was processed with stage-3 feed **3b** (direct AI
source reading) rather than waiting for the (b)/(c) resumption, and is now a
full case file:
[`DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md`](cases/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md).

This was a **deliberate single-candidate exception** to the then-current
pattern-(a)-only scope (since revised — all patterns are in scope as of
2026-09-25), not a reversal of it: feed 3b does not depend on the stage-1 CSV or
on the unwritten (b)/(c) queries, so one already-identified pattern-(c)
candidate could be written up without reopening (b)/(c) triage. Everything
else in this file stays parked.

**Worth carrying forward into the (b)/(c) reading:** writing it up showed the
guard **does not dominate** the allocation — on the default
`diskBoundaries != null` path the `SSTableWriter` is created with no
disk-space check at all. Pattern (c) asks for exactly this to be checked and
recorded, and the answer was "no" in the common case. Two lessons for the
(c) triage pass: (1) non-domination is a *finding to record*, not grounds for
rejection under Rule 3; (2) it is invisible in a stage-1 CSV row, which shows
only the comparison — establishing it requires reading the callers, so
budget for that in the (c) pass.

## 1b. Row surfaced by stage 2, judged and parked by stage 3 — `hasDiskSpaceForCompactionsAndStreams`

> **Resolved 2026-09-28 — filed as a case:**
> [`max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md`](cases/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md).
> The naming question this section left open was settled by §6.1's
> derived-limit rule in favour of the percentage entry, for the reason this
> section itself gave. Two line numbers below are **off by one** and were
> corrected in the case file: the decision point is `CompactionTask.java:412`
> (not `:411`) and the throw is `:442` (not `:441`). Two things the write-up
> added that are not below: the check can be **switched off** per table over
> JMX (`compactionDiskSpaceCheck`), and an exception while computing the
> check is **treated as allow**.

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

**When written up:** likely name
`DataDirectory_getAvailableSpaceForCompactions-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md`
under a `compaction` or `disk` module — but check §6.1's "derived from
several sources" rule first. `min_free_space_per_drive` and
`max_space_usable_for_compactions_in_percentage` both sit on the limit path,
and the latter is the one a user would tune for *this* check specifically, so
it may be the better constraint name.

## 1c. Found by the capacity-word pass, parked by pattern — 2026-09-22

> **Two entries here, but the capacity-word pass is summarised everywhere as "3
> deferred" (audit, 2026-09-24).** That summary is repeated in
> `rejected.md`, `../../../HANDOFF.md` and
> `../stage2-ai-preprocessing/README.md`, and its arithmetic is
> 4 candidates + 22 rejected + 3 deferred + 5 already covered = 34 rows.
> What is actually on file is 4 + 22 + **2** + 5 = **33**, so one row of the
> 34 is unaccounted for. The third deferral was either never written up or
> was folded into another entry without a note. Section 1b is *not* it — that
> row came from the stage-2 helper batch, not this one. Not reconstructible
> from the CSVs either, since the pass's keyword definition was dropped on
> 2026-09-23. **Treat "3 deferred" as unverified**; now that (b)/(c) are being
> read, one of its rows may need re-reading.

### `column_index_cache_size` — pattern (b) — **strong**

> **Resolved 2026-09-28 — filed as a case:**
> [`column_index_cache_size-indexSamples-cacheSizeThreshold.md`](cases/column_index_cache_size-indexSamples-cacheSizeThreshold.md).
> "Strong" held up. Every line number below was confirmed unchanged. The
> write-up found a **third check site** this section does not list —
> `RowIndexEntry.java:360` on the *read* path, which is pattern (a) and is the
> site that governs steady-state heap — and established that the total is
> re-capped by the key cache, so the ceiling claim is about per-entry cost.

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
  point in another class reads — textbook **pattern (b)**, which is why the
  then-current pattern-(a)-only scope parked it. A qualifying candidate, never
  a rejection; queued for writing up since 2026-09-25.
- **When written up:** trace `cacheSizeThreshold` to `column_index_cache_size`
  (`Config`), and record that raising it retains more `IndexInfo` arrays in
  heap via row index entries.

### `TrackedDataInputPlus_limit` — pattern (c) — weak

> **Resolved 2026-09-28 — refused, and moved to
> [`rejected.md`](rejected.md)** (batch 2026-09-28). The suspicion recorded
> below was right. `limit` comes from
> `new TrackedDataInputPlus(in, rowSize)` at `UnfilteredSerializer.java:587`,
> where `rowSize` is read out of the SSTable itself — so it is **data, not a
> capacity**, and the row fails Rule 1 before Rules 2 and 3 are reached. The
> other four production construction sites pass no limit at all
> (`limit = -1`), which disables the guard. Kept here as the reading record;
> the verdict lives in the rejection store.

- **Guard:** [`TrackedDataInputPlus.checkCanRead():184`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TrackedDataInputPlus.java#L184)
  — `limit >= 0 && bytesRead + size > limit`, which skips to the limit and
  throws `EOFException`.
- **Why deferred:** a guard clause before an allocation that is not inside a
  branch — **pattern (c)**. Also needs `limit`'s origin traced before it is
  clear whether it bounds a deserialized object's size or is merely a stream
  boundary; judge that when (c) resumes.

## 2. Re-audit of earlier rejections under (b)/(c)

**Raised 2026-09-20; parked 2026-09-22; scheduled 2026-09-25.**

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
- **How to run it:** fold it into the band-A reading rather than running it as
  a separate exercise — that pass covers those batches' rows anyway.

## 3. Stage-1 queries — useful, but not blockers

> **Corrected 2026-09-25.** This section previously said
> `NarrowedIfStatements.ql`'s filter "is precisely pattern (a)", and that the
> three queries below were "prerequisites for triaging (b)/(c)". Both claims
> were wrong, and together they understated the corpus badly enough to look
> like a coverage gap that does not exist. README §7.5 carried the same error.

The current pipeline only sees comparisons inside `if` conditions.
`NarrowedIfStatements.ql` selects `BinaryExpr` comparisons whose
`getEnclosingStmt()` is an `IfStmt`. That is a **syntactic** filter, and it
spans all three patterns — the patterns are defined by *where the decision sits
relative to the comparison*, not by syntax. Both parked candidates below prove
it: §1b's pattern-(b) check is an ordinary `if` that assigns a flag, and
§1c's pattern-(c) guard is an `if` that throws. Guard clauses *are* `if`
statements, so (c) is well covered already.

So **the existing corpus already contains (b) and (c) candidates**, and band A
is readable under all three patterns with no new query.

What the pipeline **cannot** surface is a comparison written as a ternary, an
assignment, a `return` expression or a method argument. Such a comparison
cannot be pattern (a) — (a) requires the comparison's own `if` — so every miss
of this kind is a (b) or (c) check. The implication runs one way only: *not in
an `if` ⟹ (b) or (c)*, never the reverse. Known miss: the
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

Of the three, only **#1 closes a coverage gap**; #2 and #3 are precision aids
that narrow rows already in the corpus. None of them gates the band-A pass, and
as with the existing queries they only shrink the search space — whether a row
qualifies is still decided by reading it.

## 4. Known limits of stage 1, whatever the pattern

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

## 5. Undecided rows from the band-A1 pass — 2026-09-28

Three A1 rows that a single read did not settle. They are **not refused** —
each needs one specific question answered, named below. The other 62 A1 rows
were resolved: 8 to [`pending.md`](pending.md), 33 to
[`rejected.md`](rejected.md), 21 already recorded by earlier passes.

| # | Row | What is undecided | What would settle it |
|---|---|---|---|
| 1 | [`IndexSummaryRedistribution.java:341`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryRedistribution.java#L341) — `extraSpaceRequired <= remainingSpace` | This line is **selection logic** inside the redistribution loop: it decides which SSTables keep their current sampling level out of a leftover budget, and both branches keep a summary. But the enclosing mechanism is a genuine off-heap ceiling — `index_summary_capacity` bounds the total memory all index summaries may occupy, and summaries are *downsampled* to fit. So the row is probably not the check, while the class probably contains one. | Read the class for the line that enforces the pool total rather than distributes it, and judge **that** line. If it exists, this row becomes a second check site; if the enforcement is spread across the redistribution rather than located at a comparison, the constraint may be real while no single if-check qualifies — which is itself worth recording. |
| 2 | [`SystemKeyspace.java:1919`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/SystemKeyspace.java#L1919) — `preparedBytesLoaded > preparedBytesLoadThreshold` | Returns early from the startup load of prepared statements, so it **does** withhold further object creation and bounds heap at startup. What is unclear is whether it is a *distinct* constraint or the prepared-statements cache capacity seen a second time — the comment calls it a safety valve for a known leak (CASSANDRA-19703). | Trace `preparedBytesLoadThreshold` to its declaration. If it derives from `prepared_statements_cache_size`, record it as a second check site of that constraint (whose primary comparison, `QueryProcessor.java:825`, is already refused) rather than a case. If it is independent, judge it on its own. |
| 3 | [`ResourceLimits.java:138`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/ResourceLimits.java#L138) — `next > limit` in `Concurrent.tryAllocate` | The `Basic` variant at [`:213`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/ResourceLimits.java#L213) is already in `pending.md`. Both are the **shared reserve mechanism** behind the two filed net cases, the `internode_application_send_queue_capacity` candidate, and the native-transport in-flight limits — but `limit` is a constructor parameter with no single declaration, so there is no one constraint to name it after (README §6.1). | Decide the filing question, not the code question: is `ResourceLimits` a case at all, or only a mechanism that other cases cite? The standing HANDOFF item says the two net cases should **cite** `:213` as the mechanism behind their reserve sub-checks. If citing is the answer, both rows leave this file for a note in those cases, and neither becomes a case. |

## 6. Undecided row from the band-A2 pass — 2026-09-29

One A2 row that a single read did not settle. It is **not refused**. The other
29 A2 rows were resolved: 21 to [`rejected.md`](rejected.md) (batch "band A2"),
1 as a second check site in [`pending.md`](pending.md), 7 already recorded.

| # | Row | What is undecided | What would settle it |
|---|---|---|---|
| 1 | [`Envelope.java:429`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Envelope.java#L429) — `totalLength > MAX_TOTAL_LENGTH` | Stage 2 filed this under A2, but the limit is **configuration**: `MAX_TOTAL_LENGTH = DatabaseDescriptor.getNativeTransportMaxFrameSize()` ([`:197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Envelope.java#L197)), i.e. `native_transport_max_frame_size`. On disallow the decoder enters discard mode and drops the frame's bytes; on allow it returns `null` until `totalLength` bytes have accumulated ([`:441-442`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Envelope.java#L441-L442)). So it may bound the bytes buffered **per connection** before a frame is decoded. On its face it is a per-item bound, like the refused `CQLMessageHandler.java:551` — but that refusal relied on a separate queue cap binding first. | Establish whether any byte cap binds **before** this decoder holds a frame. `Envelope.Decoder` is a Netty `ByteToMessageDecoder` on the pre-v5 pipeline ([`PipelineConfigurator.java:391`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L391)) and the initial handler (`:265`). If `native_transport_receive_queue_capacity` or `native_transport_max_request_data_in_flight` is only acquired after decode, nothing else bounds the cumulation buffer, and this is a per-connection memory cap (node-wide = `N connections × max_frame_size`) — a candidate. If one of them binds first, refuse it as a per-item bound. |
