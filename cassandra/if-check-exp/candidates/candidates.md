# Candidates working list

Survivors of semantic triage (step 4 of the CodeQL pipeline, see
[../../codeql-queries/cassandra/queries/if-check-exp/README.md](../../codeql-queries/cassandra/queries/if-check-exp/README.md))
against `results/cassandra/NarrowedIfStatements.csv`, pending promotion to a
full case file under a `<module>/` folder. Rejected rows are logged directly
in [`../_INDEX.md`](../_INDEX.md)'s "Lines considered and rejected" table
instead of here, so this file only tracks live candidates.

Triage proceeds by directory batch (grouping `NarrowedIfStatements.csv` rows
by their `src/java/org/apache/cassandra/<dir>/` path) rather than
top-to-bottom, since 4,490 rows is too many to read linearly in one pass —
each batch's coverage is recorded below so later sessions don't re-scan it.

## Re-audit needed (2026-09-20): patterns (b) and (c)

Every batch below was triaged, and every earlier rejection in `_INDEX.md`
was made, under the older assumption that the capacity check is an `if`
whose own branches decide allow vs. disallow (pattern (a)). The README now
also recognizes (b) verdict-then-decision-point and (c) guard-clause
enforcement (README §3.2), and `NarrowedIfStatements.csv` cannot contain a
pattern-(b) check written as a ternary or assignment (the `cdc_total_space`
case was found by accident). Follow-ups:

- Rows rejected only because "the if's own branches don't diverge" should be
  re-read to see whether the compared value is stored or returned and
  consumed elsewhere. Rejections on other grounds (config validation,
  concurrency limits, time-based checks, writer rollover) stand.
- The batches already triaged (`concurrent/`, `cache/`, `transport/`,
  `db/compaction/`) get one re-read for rows whose operand is
  capacity-shaped but whose branches looked non-diverging.
- The disk candidate below (`getWriteDirectory():282`) is pattern (c): a
  guard that throws before the write proceeds.
- New CodeQL queries for comparisons outside `if` conditions, guard clauses
  and verdict links are planned in
  [`codeql-queries/.../if-check-exp/README.md`](../../../codeql-queries/cassandra/queries/if-check-exp/README.md).

## Batches triaged so far

| Batch (subpackage) | Rows | Date | Result |
|---|---|---|---|
| `concurrent/` | 17 | 2026-09-18 | 0 survivors — all thread-pool/permit concurrency checks (Rule 2 fail, same reasoning as `concurrent_compactors`). |
| `cache/` | 15 | 2026-09-18 | 0 survivors — ref-counting, overflow guards, and trivial validation; no capacity-vs-limit divergence found. |
| `transport/` | 89 | 2026-09-18 | 1 survivor (below) + rejects logged in `_INDEX.md`. |
| `db/compaction/` | 208 | 2026-09-18 | 0 survivors — extends the earlier informal compaction survey to the whole subpackage; rejects logged in `_INDEX.md` (three recurring patterns: candidate-selection logic, writer-switch-on-full, config validation). |

Remaining un-triaged subpackages (row counts from the same grouping;
`db/compaction/` now done, so `db`'s remaining un-triaged rows are
982 − 208 = 774, spread across `marshal` (143), `tries` (80),
`commitlog` (78, `CommitLogSegment.java:242` already rejected — see
`_INDEX.md` — but not the rest of the file/subpackage), `rows` (67),
`RangeTombstoneList.java` (48), `context` (39), `filter` (33),
`ColumnFamilyStore.java` (27), `Slices.java` (23), `partitions` (18),
`streaming` (16, db-local), `lifecycle` (15), `view` (14), `Columns.java`
(13), `memtable` (13, partially covered by existing memtable cases),
`ClusteringPrefix.java` (12), `monitoring` (11), `ReadCommand.java` (10),
`virtual` (10), and many smaller single-digit files):
`utils` (717), `index` (487), `io` (466), `cql3` (368),
`service` (267), `tools` (167), `config` (154), `net` (140, partially
covered by the existing `internode_application_receive_queue_capacity`
case), `locator` (98), `serializers` (91), `dht` (78), `gms` (74),
`repair` (62), `schema` (48), `metrics` (44), `hints` (34, partially
covered by the existing `HintsBufferPool_MAX_ALLOCATED_BUFFERS` case),
`auth` (30), `streaming` (23, top-level), `batchlog` (10), `security` (10),
`tracing` (6), `audit` (4), `diag` (3), `exceptions` (3), `triggers` (2).

## Scope change (2026-09-18): disk added alongside memory

This folder was originally memory-only; **disk (on-disk bytes) is now also
in scope**, per Jingsong's call — see
[`../README.md` § Core concept](../README.md#3-core-concept-the-if-check-case)
for the updated Rule 2 wording. One line previously rejected for being
disk-scoped rather than memory-scoped (`CompactionAwareWriter.getWriteDirectory():282`,
found during the `db/compaction/` triage batch) is reclassified below as a
live candidate as a direct result.

## Live candidates

### `Directories_DataDirectory_availableSpace` — `sstable`

- **If-statement:** [`CompactionAwareWriter.getWriteDirectory():282`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L282):
  `if (availableSpace < estimatedWriteSize) throw new RuntimeException(...)`.
- **Context:** before a compaction/flush writer starts writing its output
  SSTable(s) to a chosen data directory, this check confirms the directory's
  physical free disk space covers the estimated size of what's about to be
  written. Without it, a compaction could start writing and fail partway
  through (or fill the disk) once space runs out mid-write.
- **Limit-side operand:** `availableSpace` — `d.getAvailableSpace()`, a
  live query of the target `Directories.DataDirectory`'s free space on
  disk (not a static config value; the "limit" here is the physical device's
  remaining capacity, queried fresh at call time). Usage-side operand:
  `estimatedWriteSize`, the caller-supplied estimate of how many bytes the
  compaction's output will occupy.
- **Rules check:** Rule 1 (yes — `availableSpace` is a hardware-bound
  capacity, not configured/hardcoded but still a legitimate constraint per
  the folder's "config, hardcoded constants, variable types, etc." framing
  in Project context). Rule 2 (yes, under the new disk scope — gates whether
  an on-disk SSTable write proceeds, bounded by disk bytes, not
  rate/concurrency). Rule 3 (yes — disallow branch `throw new
  RuntimeException(...)` is a clean, unambiguous reject; no escape hatch
  visible in this method).
- **Enforcement pattern:** (c) — the check is a guard that throws before the write proceeds; the disallow path is a clean reject, and the allocation must be shown to be dominated by it when the case is written up. Its file name under the current policy would be `getWriteDirectory-availableSpace-DataDirectory_getAvailableSpace.md`.
- **Also note:** the same method has a second disk-capacity check later —
  `getDirectories().getWriteableLocation(estimatedWriteSize)` returning
  `null` (also throws) — a fallback path when no single directory's
  `descriptor` was already pinned; likely the same underlying
  disk-capacity logic reached a different way, worth checking when writing
  up the full case rather than treating as a separate one.
- **Status:** candidate, not yet written up as a full case file or
  verified. Likely module: a new `compaction` or `io`/`disk`-named module
  folder (no existing module fits; per README naming rules, invent a broad
  one — `disk` would also plausibly hold future disk-capacity cases like
  commitlog/hints file allocation, if any surface later).

### ~~`native_transport_receive_queue_capacity` — `message`~~ — promoted 2026-09-18

Written up as a full case file:
[`net/acquireCapacity-queueCapacity-native_transport_receive_queue_capacity.md`](../net/acquireCapacity-queueCapacity-native_transport_receive_queue_capacity.md).
Notable finding surfaced while writing it up: under the *default*
`native_transport_throw_on_overload=false` config, this if-check's
disallow branch does not withhold object creation at all — a stronger,
default-mode version of the memtable cases' escape-hatch pattern. See the
case file's §6b/§8/Notes.

<details>
<summary>Original triage notes (kept for reference)</summary>

- **If-statement:** same enforcement point as the already-filed
  [`acquireCapacity-queueCapacity-internode_application_receive_queue_capacity`](../net/acquireCapacity-queueCapacity-internode_application_receive_queue_capacity.md)
  case — [`AbstractMessageHandler.acquireCapacity():419`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L419) —
  but reached via `CQLMessageHandler` (extends `AbstractMessageHandler`,
  confirmed `codeql-queries/cassandra/queries/if-check-exp/README.md` line
  78) instead of `InboundMessageHandler`, for CQL client connections
  instead of internode peer connections.
- **Limit-side operand:** `queueCapacity`, sourced from
  `native_transport_receive_queue_capacity` (`Config.java:301-302`, default
  `1MiB`) via
  `DatabaseDescriptor.getNativeTransportReceiveQueueCapacityInBytes()`
  (`DatabaseDescriptor.java:3208-3210`), passed in at
  `PipelineConfigurator.java:306` and threaded to `CQLMessageHandler`'s
  constructor (`CQLMessageHandler.java:124,134`).
- **Why it's a distinct candidate, not a duplicate:** this is exactly the
  precedent set by `tryAllocate-limit-memtable_heap_space` /
  `tryAllocate-limit-memtable_offheap_space` — same if-check, different `SubPool`
  instance and config source. Here it's the same `acquireCapacity()`
  if-check, different config (`native_transport_receive_queue_capacity` vs.
  `internode_application_receive_queue_capacity`) and different object
  created (a CQL `Message` decoded from a client, e.g. a query/execute
  request, rather than an internode peer `Message`). The existing case file
  already flagged this exact sibling in its own "Notes" section
  (`net/acquireCapacity-queueCapacity-internode_application_receive_queue_capacity.md`) as "could
  be filed... following the same memtable heap/offheap precedent" — this
  triage pass confirms it independently by reading `CQLMessageHandler`'s
  source and config wiring, rather than just accepting the earlier note at
  face value.
- **Rules check:** Rule 1 (yes — `queueCapacity` is a configured byte cap).
  Rule 2 (yes — bounds total queued-and-deserializing bytes per CQL
  connection, same reasoning as the internode case). Rule 3 (yes — disallow
  branch backpressures via the same `endpointWaitQueue`/`globalWaitQueue`
  registration as the internode case, per `AbstractMessageHandler.java:401-403`).
- **Status:** candidate, not yet written up as a full case file or verified.
  Next step: write `net/acquireCapacity-queueCapacity-native_transport_receive_queue_capacity.md`
  from `_TEMPLATE.md` (mirroring the internode case's structure — §1 note
  about the reserve-capacity sub-checks likely applies here too, since
  `CQLMessageHandler` shares `acquireCapacity()`'s full body), then design a
  verification trigger per the README's methodology.

</details>
