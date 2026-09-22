# Stage 1 results & stage 2 playbook

What the CodeQL stage produced, and how to work through it. Written
2026-09-22, after stage 1 was finished for enforcement **pattern (a)**.
See [`README.md`](README.md) for the folder's rules and batch coverage, and
[`../README.md` §7.2](../README.md#72-discover-candidate-capacity-checks-target-1)
for how the two discovery methods relate.

---

## Part 1 — Stage 1 results

### What exists

Two CSVs feed pattern-(a) triage. Both live in the **gitignored**
`codeql-queries/results/cassandra/` and are regenerated per machine:

```bash
export PATH="/proj/misconfiguration-PG0/tools/codeql:$PATH"
cd /proj/misconfiguration-PG0/git-repos/misconfiguration/codeql-queries
./scripts/run-query.sh cassandra cassandra/queries/if-check-exp/NarrowedIfStatements.ql
./scripts/run-query.sh cassandra cassandra/queries/if-check-exp/HelperGuardedIfStatements.ql
```

| File | Rows | What it contains |
|---|---|---|
| `NarrowedIfStatements.csv` | 4,489 | Numeric comparisons written **directly in an `if` condition**. Nulls, literal-only pairs and non-numeric operands already dropped. |
| `HelperGuardedIfStatements.csv` | 1,099 | Comparisons **one call frame down**, inside a boolean helper the `if` calls (`if (!pool.hasRoom())`). Adds `helper` and `helperLine` columns. |

Columns: `path, line, pkg, declaringType, method, lhs, op, rhs, opClass`
(+ `helper, helperLine`). Rows are `order by`-ed, so runs are reproducible
across machines.

Narrowing so far: **17,343** `if` statements → **10,147** comparisons →
**4,489** numeric non-trivial, plus **1,099** helper-guarded.

### Why these two files are the complete pattern-(a) input

Pattern (a) is "the capacity check is itself the `if` whose branches decide".
`NarrowedIfStatements.ql` keeps comparisons whose enclosing statement is an
`if` — structurally exactly that. `HelperGuardedIfStatements.ql` covers the
one way an (a) check can hide from it: the comparison living inside a boolean
helper, leaving the `if` with no comparison of its own.

Patterns (b) and (c) are **not** covered and are parked (see
[`deferred.md`](deferred.md)). Do not go looking for them in these files.

### Sanity check: the known cases are all in there

Every already-filed case whose check sits in an `if` appears in
`NarrowedIfStatements.csv`, all magnitude-class:

| Case | Row |
|---|---|
| `MAX_HINT_BUFFERS` | `HintsBufferPool.java:113` — `allocatedBuffers >= MAX_ALLOCATED_BUFFERS` |
| both memtable cases | `MemtablePool.java:156` — `... + ... > limit` |
| both `*_receive_queue_capacity` cases | `AbstractMessageHandler.java:419` — `... + ... <= queueCapacity` |
| the compaction disk case | `CompactionAwareWriter.java:282` — `availableSpace < estimatedWriteSize` |

(`cdc_total_space` is absent by design — it is a ternary, hence pattern (b),
and was found by method 1.)

This matters for calibration: **these four rows are what a true positive
looks like in the CSV.** Note how little the row itself tells you — two of
them render the usage side as `... + ...`. The row locates the check; it
never decides it.

---

## Part 2 — Stage 2 playbook

### Prioritization ladder

The remaining corpus is 5,145 rows, but it is nothing like 5,145 units of
work. Peel it in this order:

| Step | Rows | Rationale |
|---|---|---|
| All remaining | 5,145 | — |
| **Magnitude only** (`opClass`) | **2,941** | A capacity check is inherently a magnitude comparison. Equality (`==`, `!=`) is 2,204 rows of mostly `index == 0` sentinel tests — sweep later, don't delete. |
| **minus fast-reject** (below) | **~1,895** in the narrowed file | Mechanical, and verified not to drop any known case. |
| **Positive-signal rows first** | ~470 | See "signals" below — read these before the rest of the batch. |

### Fast-reject: two rules that cut ~29% of magnitude rows

Both verified against all four known cases — **neither drops any of them**:

1. **Limit side is a bare literal.** 602 magnitude rows compare against `0`,
   711 against some small literal. `x > 0` is an emptiness or sign test;
   a real limit has a *name*. (Careful: `getCapacity() > 0` is an
   enabled-check, not a capacity check — correctly rejected here.)
2. **Either operand is `compareTo()` / `compare()`.** 67+ rows. These are
   ordering tests, never capacity.

"Limit side" means the right operand of `<`/`<=` and the left of `>`/`>=` —
i.e. the side the usage is being tested *against*.

### Positive signals: what a real one looks like

- **The usage side is an arithmetic expression** — `... + ...`, rendered by
  CodeQL when the operand is compound. This is the classic
  `current + requested vs limit` shape. Only **36 rows** corpus-wide, and it
  is the shape of *two* of the four known cases. Read every one of them.
- **The limit side's name contains a capacity word** — `limit`, `capacity`,
  `max`, `threshold`, `space`, `bytes`, `free`, `avail`, `quota`, `reserve`,
  `allowance`. **461 rows.** This is a *prioritization* heuristic, never a
  filter: the folder's rules deliberately reject a fixed keyword list,
  because `memtable_heap_space` and `MAX_HINT_BUFFERS` share no vocabulary.
  Use it to order reading, then read the rest anyway.
- **Both signals at once: 11 rows corpus-wide.** One is the known
  `AbstractMessageHandler.java:419`. The others are the single
  highest-yield thing to read first — e.g.
  `BigFormatPartitionWriter.java:113` (`cacheSizeThreshold`),
  `IncrementalTrieWriterPageAware.java:167` (`maxBytesPerPage`),
  `TeeDataInputPlus.java:58` (`limit`).

### Tricks that save real time

**Judge the helper, not the row.** In `HelperGuardedIfStatements.csv`, 1,099
rows come from only ~300 distinct helpers; the 577 magnitude rows come from
197. Sort a batch by `helper`, judge each helper **once**, apply the verdict
to all its call sites. The most repeated ones are obviously not capacity
checks (`ProtocolVersion.isGreaterOrEqualTo()` 40 rows,
`DeletionTime.supersedes()` 28), so a handful of judgments clears a large
share.

**Read by file, not by row.** Rows are sorted by `pkg, path, line`. Group a
batch's rows by file, then open that file **once** in the local clone and
window around all its lines together. Reading the same file once per row is
the single biggest waste available here.

**Trace the limit operand to its declaration — that is the answer to Target 1.**
`grep` the operand name in `config/Config.java` and
`config/CassandraRelevantProperties.java` first. A hit there is a strong
positive signal *and* hands you the constraint name for the file name
(README §6.1). No hit means it is a constant, a derived value, or a runtime
accessor — all still valid, just name them by the §6.1 rules.

**Look for siblings deliberately.** Three of the seven filed cases are
siblings of another: same check, different pool or config
(`memtable_heap_space`/`memtable_offheap_space`;
`internode_`/`native_transport_receive_queue_capacity`). When a row
qualifies, immediately ask what *other* instance reaches the same code with a
different limit. That is the cheapest new case available.

**Assume there is an escape hatch.** Every case filed so far has one:
`markBlocking()` overshoots the memtable limit; `throw_on_overload=false`
decodes the message anyway; `cdc_block_writes=false`; and the compaction
guard is skipped entirely on the default path. If a check looks like a clean
reject, you have probably not read far enough. Record it for Target 3 in §9
and move on — do not chase it.

### Pitfalls, learned from the cases already filed

**The row is not the case — Rule 3 needs the branches.** The CSV tells you a
comparison exists. It says nothing about whether the outcomes diverge on
object creation, which is what actually qualifies a candidate. Always read
the `if`'s two branches.

**For anything guard-shaped, read the callers, not just the method.** The
compaction disk case looked airtight in isolation and turned out not to
dominate its allocation at all — its only caller skips it entirely on the
default path. That was invisible in the CSV row *and* in the method itself.

**Write verdicts down in the same pass.** Every row you read goes to
[`positives.md`](positives.md), [`negatives.md`](negatives.md) or
[`deferred.md`](deferred.md) before you move on. A row judged and not
recorded gets re-read by the next session at full cost — which is exactly
what the batch-coverage table exists to prevent.

**Cite the established reject archetypes rather than re-arguing them.**
[`negatives.md`](negatives.md) lists the recurring ones (thread-pool and
concurrency caps, rate limiters, writer-rollover, config validation,
selection/bucketing logic, ref-counting). Most rejections are one of these;
naming the archetype is a complete justification.

**Check `_INDEX.md` before recording a rejection.** It holds every rejection
made up to 2026-09-22, including method-1 findings. One line is recorded in
exactly one place.

### Suggested batch order

1. **The 114 unread helper rows inside the four "done" batches**
   (`transport` 63, `db/compaction` 43, `concurrent` 6, `cache` 2). These
   subtrees are already familiar, and they are currently marked done while
   containing rows the pipeline could not produce at the time.
2. **`config` (115 magnitude) and `net` (98)** — small, dense, adjacent to
   constraints already understood. Good for calibrating judging pace.
3. **`db`, `utils`, `index`, `io`** — over half the remaining work; attempt
   once the pace and the reject archetypes are second nature.

A session of roughly 100–200 magnitude rows appears to be the right size:
large enough to finish a real subpackage, small enough to record verdicts
properly before context runs short.
