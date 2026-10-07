# Stage 4, long path — running a case

The long path's stage 4 is done entirely by an AI session in this repository, with no human approval at any step. It follows the
protocol in [`../README.md`](../README.md); this file holds what is specific to the long path's cases. It was split out of the shared
README on 2026-10-06, because the short path's executor reads that README and must not see how the long path designed or ran these
cases. **The short path's executor never reads this folder.**

| What | Where |
|---|---|
| Results, one file per case | `results/<stem>.md`, with small excerpts in `results/<stem>/run1/` |
| Harness, code the runs need | `harness/<stem>/` |
| Node setup specific to the closed cases (the two-node ring, the single measured node) | [`environment-notes.md`](environment-notes.md) |
| Generic node setup and lessons | [`../environment.md`](../environment.md) |

## Where to start

**Unit tiers first.** They test the run protocol cheaply before any cluster run. Four cases are far cheaper than the rest because
unit scaffolding already reaches the check:

| Case | Why it is cheap |
|---|---|
| `memtable_heap_space` | Done: the worked example. Its unit tier is two `ant testsome` commands on the restored `HeapPoolTest` (see "Prior art" below). |
| `cdc_total_space` | Done 2026-10-01. `CommitLogSegmentManagerCDCTest` has the scaffolding (`CQLTester`, the CDC setup) but **not** a usable sweep: its `testWithCDCSpaceInMb` is private, and its non-blocking assertion allows three times the limit. The run needed a new harness test (`CdcTotalSpaceCeilingTest`), a Byteman creation trace, a sampler for `cdc_raw`, and a consumer emulator. The unit yaml's `commitlog_segment_size` is 5 MiB, not the node's 32 MiB. |
| `MAX_HINT_BUFFERS` | Predicts an **exact** ceiling, `n × bufferSize` (96 MiB at defaults), not a trend, so it is the sharpest falsification in the set. `HintsBufferPoolTest.testBackpressure()` already proves the disallow branch via Byteman. Confirm Byteman resolves as a test dependency first. |
| `max_space_usable_for_compactions_in_percentage` | `DirectoriesTest`, `PartialCompactionsTest` and `CompactionsBytemanTest` between them cover the arithmetic, the injection point and all three disallow outcomes. |

**Two designs need a cluster before they say anything**, because their finding is a default-mode gap rather than a limit:
`native_transport_receive_queue_capacity` (the whole experiment is a comparison of `throw_on_overload` true vs. false, so a
single-mode run correctly observes nothing) and `DataDirectory_getAvailableSpace` (the guard does not run under the default
partitioner, so the two arms need **separate clusters**).

**Worked examples.** The first case run, `memtable_heap_space`: results in
[`results/memtable_heap_space-tryAllocate-limit.md`](results/memtable_heap_space-tryAllocate-limit.md), harness in
`harness/memtable_heap_space-tryAllocate-limit/`; its `run1/cluster-run.sh` is one example of a run script (borrow what fits, not
its structure). `cdc_total_space` and `MAX_HINT_BUFFERS` followed the same layout.

**Prior art.** The `memtable_heap_space` unit test, `HeapPoolTest.java`, is restored under `harness/` (its origin is recorded in
that folder's README). Earlier per-case trigger notes are in `git show e7f9963:HANDOFF.md`.

**Two cases run entirely on one session, 2026-10-07** — `local_read_size_fail_threshold` and `row_index_read_size_fail_threshold`, both tiers Confirmed. Their harnesses are the freshest examples of a
Python run script (`cluster-run.py`: instrument checks, calibration, scenarios, `EXPECTED:` lines, node stopped on any exit), a unit test that mirrors the check's own arithmetic from the code's
objects, a Byteman observation rule with a helper class on the boot class path (the node runs from the jar), and a small JMX client with a setter (`Jmx.java`); the lessons are in `../../../../HANDOFF.md`
("Stage 4 update (2026-10-07)") and in each harness README.

**Unaudited cases.** All 16 filed cases are in the new §9 layout (eight converted on 2026-10-06, the twelfth to sixteenth written in it); the fifteenth and sixteenth are closed, but the other eleven
have not passed the design audit and have no harness code; both come before a run, as [`../README.md`](../README.md) ("Step 0") says.
