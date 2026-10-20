# Stage 4 — notes from the closed cases

Read after [`README.md`](README.md) (the protocol). This file holds what the closed cases teach: where to start, which cases
are cheap, worked examples. All 24 closed cases were guided files; their results are `results/<stem>--guided.md` and their
harnesses `harness/<stem>--guided/`. It was split out of the shared README on 2026-10-06 and is no longer hidden from any
executor (the blind short-path executor was removed on 2026-10-19). Names below are the case stems; add `--guided` for the file.

| What | Where |
|---|---|
| Results, one file per case file | `results/<stem>--<agent>.md`, with small excerpts in `results/<stem>--<agent>/run1/` |
| Harness, code the runs need | `harness/<stem>--<agent>/` |
| Node setup specific to the closed cases (the two-node ring, the single measured node) | [`environment-notes.md`](environment-notes.md) |
| Generic node setup and lessons | [`../environment.md`](environment.md) |

## Where to start

**Unit tiers first.** They test the run protocol cheaply before any cluster run. Four cases are far cheaper than the rest because
unit scaffolding already reaches the check:

| Case | Why it is cheap |
|---|---|
| `memtable_heap_space` | Done: the worked example. Its unit tier is two `ant testsome` commands on the restored `HeapPoolTest` (see "Prior art" below). |
| `cdc_total_space` | Done 2026-10-01. `CommitLogSegmentManagerCDCTest` has the scaffolding (`CQLTester`, the CDC setup) but **not** a usable sweep: its `testWithCDCSpaceInMb` is private, and its non-blocking assertion allows three times the limit. The run needed a new harness test (`CdcTotalSpaceCeilingTest`), a Byteman creation trace, a sampler for `cdc_raw`, and a consumer emulator. The unit yaml's `commitlog_segment_size` is 5 MiB, not the node's 32 MiB. |
| `MAX_HINT_BUFFERS` | Predicts an **exact** ceiling, `n × bufferSize` (96 MiB at defaults), not a trend, so it is the sharpest falsification in the set. `HintsBufferPoolTest.testBackpressure()` already proves the disallow branch via Byteman. Confirm Byteman resolves as a test dependency first. |
| `max_space_usable_for_compactions_in_percentage` | `DirectoriesTest`, `PartialCompactionsTest` and `CompactionsBytemanTest` between them cover the arithmetic, the injection point and all three disallow outcomes. **Done 2026-10-07: audited, run 1 at both tiers and self-checked, Confirmed** (H1 as predicted, H2 bypass as recorded; the independent `run1/selfcheck.py` is the freshest example of a checker that re-parses the raw logs): see its [results file](results/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction--guided.md) and harness folder (adds `CompactionLadderTest`, `cluster-run.py`). |

**Two designs need a cluster before they say anything**, because their finding is a default-mode gap rather than a limit:
`native_transport_receive_queue_capacity` (the whole experiment is a comparison of `throw_on_overload` true vs. false, so a
single-mode run correctly observes nothing; **done 2026-10-15**, one node, both modes and both request sizes, Confirmed: see its
[results file](results/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md)) and `DataDirectory_getAvailableSpace` (the guard does not run under the default
partitioner, so the two arms need **separate clusters**).

**Worked examples.** The first case run, `memtable_heap_space`: results in
[`results/memtable_heap_space-tryAllocate-limit.md`](results/memtable_heap_space-tryAllocate-limit--guided.md), harness in
`harness/memtable_heap_space-tryAllocate-limit/`; its `run1/cluster-run.sh` is one example of a run script (borrow what fits, not
its structure). `cdc_total_space` and `MAX_HINT_BUFFERS` followed the same layout.

**Prior art.** The `memtable_heap_space` unit test, `HeapPoolTest.java`, is restored under `harness/` (its origin is recorded in
that folder's README). Earlier per-case trigger notes are in `git show e7f9963:HANDOFF.md`.

**Two cases run entirely on one session, 2026-10-07** — `local_read_size_fail_threshold` and `row_index_read_size_fail_threshold`, both tiers Confirmed. Their harnesses are the freshest examples of a
Python run script (`cluster-run.py`: instrument checks, calibration, scenarios, `EXPECTED:` lines, node stopped on any exit), a unit test that mirrors the check's own arithmetic from the code's
objects, a Byteman observation rule with a helper class on the boot class path (the node runs from the jar), and a small JMX client with a setter (`Jmx.java`); the lessons are in `../../../../HANDOFF.md`
("Stage 4 update (2026-10-07)") and in each harness README.

**`concurrent_compactors` (2026-10-20, the first negative-estimate file run; Refuted).** Lessons for the next cases:
(1) `nodetool disableautocompaction` does not survive a restart; a node restored from a data-directory backup compacts at once unless the
yaml sets `autocompaction_on_startup_enabled: false`. (2) Building the data once and restoring it per run (`cp -a` of the data directory
on the same loop filesystem, about 1 min for 8.6 GB) is far cheaper than reloading, and keeps `available` identical across runs.
(3) `max_space_usable_for_compactions_in_percentage` is checked per task at its start, so it cannot limit the *sum* of tasks that start
together; a control built on it must set the budget below one task. (4) `debug.log` and `system.log` accumulate across runs in one
clone: parse only from the offset taken at the start of the run. (5) `system_views.sstable_tasks` gives the running compactions per
table every 2 s without a JMX client. Harness: `harness/concurrent_compactors-submitBackground-getMaximumPoolSize--guided/`.

**Unaudited cases.** All 24 filed cases are in the new §9 layout (eight converted on 2026-10-06, the twelfth to nineteenth written in it; the nineteenth, `SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS`, filed 2026-10-14); **all twenty-four are closed** (see `../../../../HANDOFF.md`; the last three, run 2026-10-15 by one session, unit tiers in `~/cassandra-run3` and cluster tiers from `~/cassandra-run1`: `coordinator_read_size_fail_threshold` (one node, one driver session for the lifetime, a warm-up abort before any allocation reading, Byteman `guard-fail`/`result`/`coord-alloc`/`frame` lines), `repair_disk_headroom_reject_ratio` (two nodes on loopback, the denominator capped at 1 GiB and the usage set by a sparse pad, so the check's 5-decimal operand is exact; a real 269 MB stream for the admission-only arm), `DOB_MAX_RECYCLE_BYTES` (a Byteman ledger of every thread-local scratch buffer, a 5-s hold at `CommitLog.add()` for 16 distinct threads, 20 node starts, the client on protocol 4 to keep the v5 large-request residue out of the direct pool); before them, run 2026-10-15 from `~/cassandra-run3`: `networking_cache_size` (a raw native-v5 client that never reads, a Byteman slab and overflow ledger, arm L shows the large-request leak), `Integer_MAX_VALUE` (a Byteman-moved type bound checked against the real one, a 2 GiB summary on one node with a 24 GiB heap), `DataDirectory_getAvailableSpace` (a fresh 4 GiB loop filesystem and a ballast per label, two partitioners, a background compaction as the trigger); before them, `SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS`, runs one node with its own `CASSANDRA_CONF` and directories (the host was shared with another session's node), counts the list at the check and the plan taken with Byteman lines per query, holds 8 concurrent queries at one of three points gated by flag files for a class histogram, and its unit test extends `CQLTester` because `SAITester` attaches a second Byteman agent; before it `native_transport_receive_queue_capacity`, runs one node with a Java client on the in-tree `SimpleClient` (protocol v5, the `THROW_ON_OVERLOAD` option per connection, a window of requests per connection, the JDK 11 module options from `conf/jvm11-clients.options`), reads the operand and the decoded bytes per handler from a Byteman trace (acquire, release, decode, release-of-decoded) and checks the trace's integrity in the self-check, and reads live decoded requests with class histograms; before it `internode_application_receive_queue_capacity`, runs a five-node ring on loopback with node data on a tmpfs, reads the operand per handler from a Byteman trace at every acquire and release and per peer from `system_views.internode_inbound`, and reads where the accepted bytes live with class histograms and the networking pool's gauge; before it `max_hints_size_per_host`, runs a three-node ring on loopback in one lifetime, sets each phase boundary from the trace (the first refusal) with a fixed-rate writer that logs every key, and reads each down host alone after the replay to compare key sets; before it `file_cache_size`, sets the demand with a Byteman read hold and reads the pool's exact reservation from a per-chunk trace line, since two JMX gauges read under load are two moments; before it `column_index_cache_size`, observes the entry class per read with Byteman rules joined through link maps and windows each pass by its census file; before it `CACHEABLE_MUTATION_SIZE_LIMIT` holds writes 45 s with Byteman and reads the heap with collecting class histograms, so its node yaml raises `native_transport_timeout` past the hold; before it `max_value_size` re-did a lost audit and counts only a fresh run; before that `repair_session_space` runs a two-node ring on one host on loopback addresses and keeps each repair's raw log segments under `raw/` for the self-check), but the others
have not passed the design audit and have no harness code; both come before a run, as [`../README.md`](README.md) ("Step 0") says.
