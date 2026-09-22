# Negatives — rows read and refused

Stage-2 AI filtering verdicts for rows that **fail** one of the three rules
([`../README.md` §3.4–§3.6](../README.md#3-core-concept-the-if-check-case)).
Each entry cites the rule it failed, so a later pass doesn't re-derive the
judgment. See [`README.md`](README.md) for how rows are judged and for batch
coverage.

**Refused, not merely unjudged.** A row dropped only because patterns (b)/(c)
are currently out of scope is *not* a negative — it goes to
[`deferred.md`](deferred.md).

## Where existing rejections live

Two things to know before adding here:

1. **Method-1 rejections stay in [`../_INDEX.md`](../_INDEX.md)'s "lines
   considered and rejected" section.** Those come from the direct-AI-search
   method and differ in kind — few, narrative, sometimes deferred rather than
   firmly refused (e.g. `ConnectionLimitHandler`). They are not moved here.
2. **Stage-2 rejections made before 2026-09-22 are also in `_INDEX.md`**, because
   this file did not exist yet. They were not migrated: the entries are
   detailed and already cross-referenced from several places, and moving them
   would churn those references for no analytical gain. They cover the
   `concurrent/`, `cache/`, `transport/` and `db/compaction/` batches (see
   `README.md`'s coverage table).

**So: `_INDEX.md` is authoritative for every rejection recorded up to
2026-09-22; this file is authoritative for stage-2 rejections from that date
on.** Either way the rule holds — one line is recorded in exactly one place.
Before adding a row here, check `_INDEX.md` first; if it is already there,
leave it there.

## Rejected rows (from 2026-09-22)

_None yet — the first stage-2 batch under the new layout has not been run._

Format for new entries, grouped by batch:

| Row (`file:line`, comparison) | Rule failed | Why |
|---|---|---|
| | | |

Recurring rejection reasons already established (cite these rather than
re-arguing them):

- **Thread-pool / concurrency / permit caps** — Rule 2: bounds parallelism,
  not total bytes. Precedent: `concurrent_compactors`.
- **Rate / throughput limiters** — Rule 2: bounds speed, not the ceiling.
- **Writer-switch-on-full** — Rule 2's writer-rollover edge case: the write
  proceeds either way, just chunked across more files. Precedent:
  `CommitLogSegment.java:242`, `HintsBuffer.java:190`.
- **Config validation / derived arithmetic** — startup-time checks or plain
  math, not a runtime allocation gate.
- **Selection / bucketing logic** — comparisons that choose *which* objects to
  act on, not whether to create one. Precedent: the compaction strategies.
- **Ref-counting and overflow guards** — not a usage-vs-capacity comparison.
