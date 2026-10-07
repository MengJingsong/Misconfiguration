# If-Check Exp — Handoff

For a new session picking up `if-check-exp` work. Read this first, then
[`cassandra/if-check-exp/README.md`](cassandra/if-check-exp/README.md) for
the full format spec. This file is self-contained: everything a session
needs is here or in the repo, with no external document required.

This handoff covers `if-check-exp` specifically, since that's the repo's
active experiment; it lives at the repo root (rather than under
`cassandra/if-check-exp/`) so a new session finds it immediately. The paused
sibling experiment has its own brief at
[`cassandra/entry-restriction-exp/HANDOFF.md`](cassandra/entry-restriction-exp/HANDOFF.md)
(split out 2026-09-23) — one handoff per experiment folder, rather than
overloading this one.

**Project context:** the three project-wide targets are in the repo-root
[`README.md`](README.md) §0. The running plan and findings live in two
Google Docs — [*Meeting Summary*](https://docs.google.com/document/d/1tldFFEk28qtQD0QdsnC2Br-BisTyOUp8OCwG1SZ_6Jk/edit)
(per-meeting decisions and next steps) and
[*Progress Report*](https://docs.google.com/document/d/1gMRFwaTvgahSiRi10ad_Y3CLDkxyF1QTYkAhZ4be4x8/edit)
(running log of entry points, cases and findings); a session with the Google
Drive connector enabled can read them directly.

## What this experiment is

Part of the **misconfiguration** research project (Target 1: identify resource
constraints that limit memory/CPU usage; Target 2: show how each constraint
restricts usage via its exact code path; Target 3: bypass analysis — out of
scope for this folder), scoped to **Apache Cassandra 5.0.9**. `if-check-exp`
inventories **capacity checks** and the **decision points** they feed: a
comparison of usage against a capacity limit, and the code where the outcome
diverges (one outcome lets a memory- or disk-significant allocation happen,
the other blocks, defers, or rejects it). Each case always covers Target 1
and Target 2 together: it names the constraint (found by tracing the limit
back to where it is first declared) and shows how the code enforces it.

It is a **standalone inventory** — deliberately not cross-referenced against
the sibling `entry-restriction-exp` folder, even when a line happens to
coincide. It also does **not** do bypass analysis or failure-mode scoring —
pure Target 1 + 2 — though bypass-relevant observations made along the way
are noted in case files for later Target-3 use, not chased down here.

**`if-check-exp` is its own independent experiment.** It does not share
infrastructure, cluster state, or config with any other experiment in this
repo — when setting up infrastructure for this folder, assume
nothing is already provisioned and build/configure it from scratch under
this folder's own scope.

## Working preferences (for a new session)

- **Plan before editing.** For changes to rules, naming, scope, or folder
  structure, first give an opinion or an update plan (which files, what
  changes) and wait for Jingsong's go-ahead. Show old-vs-new names or a
  file-by-file list when asked. Small factual fixes to a file you are
  already working on don't need this.
- **Stage 4 has no human gate (decided 2026-09-30).** The AI audits the case's §9, runs it, checks its own
  conclusion against the raw files and files the verdict; nothing waits for Jingsong, who may overrule a verdict at
  any time. The shared-infrastructure safety rules in the stage-4 README still apply.
- **Two solutions per case, each with a unit and a cluster tier; the short path decides nothing (decided 2026-10-02, revised
  2026-10-05).** Each case gets a long-path case file and a short-path solution. **The long path always goes first
  (decided 2026-10-06), so only the short path is blind** (to the long case file, its stage-4 results and harness, this file, and
  `comparison/`); the long path has no isolation rule and is done entirely by an AI session. **The short path is human plus AI**:
  a human starts the blind writer (`run-case.py`) and the blind stage-4 executor (`run-executor.py`) from a terminal, an AI
  session does everything around them (judge the audits, file, review, side-by-side). The short path carries no go/no-go, uses none of the long path's method (only the two-tier structure is asked of it), and its solution
  is frozen on filing (sha256 in `short-path/_INDEX.md`) and never edited; a new version is filed with `--supersede`.
  **Stage 4 runs both paths, both tiers each, with no rating of the two solutions and no cross-path scoring**; an executor
  reads only its own path's solution, and a side-by-side is written at the end. Scope stays memory and disk. The pilot on the
  three closed cases was skipped; the 17 filed cases have no short solution yet except `memtable_heap_space` (version 2, two
  tiers; version 1 kept as `--v1`).
- **Decided 2026-10-06:** (1) the long path always goes first, so only the short path is blind; (2) shared stage-4 files
  (`README.md`, `environment.md`, `_TEMPLATE.md`) stay free of the long path's case-specific designs, which live in
  `stage4-runtime-verification/long-path/`; (3) the repository copy on the CloudLab shared mount was removed.
- **Commit and push only on request.** "Commit" and "push" are asked for
  separately; never do either unprompted.
- **Sync before restructuring.** Jingsong also uploads files to GitHub
  directly, so `git fetch` and compare with `origin/main` before renaming or
  reorganizing files. If local edits exist, stash, fast-forward, then re-apply.
- **Keep settled decisions.** For example, the "no cross-referencing other
  experiments" rule in `cassandra/if-check-exp/README.md` §4 stays because
  Jingsong may not return to `entry-restriction-exp`; don't propose
  cross-check steps against it.

## Where things live

- **Repo:** `MengJingsong/Misconfiguration` on GitHub.
- **Local clone:** kept wherever the current working session's local
  machine keeps it — path and device vary by environment, not fixed
  (a session only writes local files, and commits or pushes only when
  Jingsong asks — see "Working preferences" below). **There is no checkout on
  the CloudLab shared mount any more** (removed 2026-10-06, so a node-side executor
  cannot read it; root `README.md` §2). Scripts find their own paths from where
  they sit, and the Cassandra clone as `$CASSANDRA_SRC` or `cassandra-src` beside
  this repo.
- **Folder:** `cassandra/if-check-exp/`
  - `README.md` — full format spec: scope, the three rules, required
    fields, naming rules, workflow, how to verify/link line numbers against
    the local Cassandra source, and **§1.1 targets vs. stages** (the two
    numberings are unrelated) and **§7.2 the three stages**.
  - `stage3-ai-deep-read/long-path/_INDEX.md` — master table of all cases and the coverage summary.
    **Cases only** — the "lines considered and rejected" table moved to
    `stage3-ai-deep-read/long-path/rejected.md` on 2026-09-23.


  - **`stage1-codeql-preprocessing/`** — stage-1 entry point. Holds no
    queries and no results, only pointers: the queries live at the repo root
    under `codeql-queries/`, the CSVs are gitignored. Also records stage 1's
    output counts and its structural blind spot.
  - **`stage2-ai-preprocessing/`** — stage-2 verdicts (lexical, rows only).
    - `README.md` — what stage 2 is, how a row is triaged, the
      "Progress at a glance" dashboard, and the batch-coverage table.
    - `playbook.md` — **start here to run a batch.** The one rule (rank,
      never rule out), the four bands (A–D), what band D looks like and the
      grounds that need the source instead, how to run a batch, the
      calibration rows, and the tricks and pitfalls learned so far.
    - `bands.md` — the banding result: bands explained, band A grouped by
      what the limit is, run provenance. Stage 3's 3a queue.
    - `bands.csv` — **the per-row verdicts**, committed because an AI band
      cannot be regenerated the way the old keyword tiers could.
  - **`stage3-ai-deep-read/`** — reads the source. **Two paths, two
    solutions per case** (decided 2026-10-02; the folder was split into
    `long-path/` and `short-path/` the same day).
    - `README.md` — the two paths, the rules both obey (the short path is blind to the
      long path, which goes first; frozen on filing; who does what), and the two feeds.
    - **`long-path/`** — the deciding path: the three rules, the case file. An AI session
      does all of it; no isolation rule.
      - `README.md` — what it is, its files, where its verdicts go.
      - `playbook.md` — how to run a pass: the order to check things, and the
        verified pitfalls.
      - `_TEMPLATE.md` — template for a new case file (the long path's output).
        Its §10 Provenance records the feed (`3a`/`3b`) and the date the cited
        lines were checked.
      - `_INDEX.md` — master table of all cases.
      - `rejected.md` — read with the source open, refused against the three
        rules. Moved here from `_INDEX.md` on 2026-09-23.
      - `cases/` — **the results**: one flat file per case (flattened from
        per-module folders 2026-09-23; module is a field, not a folder).
      - `deferred.md` — unjudged rows, identified but never read against the
        rules. Formerly the (b)/(c) parking lot; **unparked 2026-09-25**, so it
        is now a worklist. Kept apart from `rejected.md` because they are
        undecided, not refused. Moved here from the stage-2 folder, since
        **stage 2 cannot produce a pattern deferral**.
      - `pending.md` — qualified, not yet written up.
    - **`short-path/`** — an **experiment**, one case filed (`memtable_heap_space`). An AI
      traces the constraint and designs a verification solution **without**
      the rules, patterns, §8 design rules or template, and files **no
      verdict**. `README.md` is the contract (how a solution is made, isolated,
      audited and frozen); `BRIEF.md` + `_TEMPLATE.md` are the whole prompt the
      isolated agent gets; `_INDEX.md` records sha256, isolation and leakage
      audit; `cases/` holds the solutions; **`run-case.py` and `isolation-test.py` are the
      scripts a human runs** (the entry pointer comes from the long-path index). The AI that
      writes the long path never needs this folder.
  - **`stage4-runtime-verification/`** — opened 2026-09-25. Runs the §9 test
    designs and reports back. **No human approval or review is required**
    (revised 2026-09-30): an AI session audits the case's §9 against the
    README's requirements (step 0), runs it (run 1), checks its own conclusion
    against the raw files, and owns the verdict. Run 2, a fresh AI session, is
    optional insurance. Jingsong may overrule a verdict at any time.
    - `README.md` — the run protocol, safety rules for the shared
      infrastructure, and where each kind of feedback lands.
    - `environment.md` — **start here on a new node**: the exact install,
      clone and build steps that worked (JDK 11.0.32.1, Ant 1.10.12), more-than-one-node
      setup, and the lessons that apply to any run. Case-neutral on purpose: the short
      executor reads it. Case-specific node setup is in `long-path/environment-notes.md`.
    - `executor-prompts.md` — the short executor in brief, and the side-by-side writer's prompt.
    - `check-blindness.py` — the transcript audit for the short executor.
    - `_TEMPLATE.md` — template for a per-case results file.
    - `comparison/` — the **side-by-side** of a case's two paths, written at the
      end by the session that finishes the last run: verdicts by path and tier,
      whether the conclusions agree, findings only one path produced, defects,
      cost. It rates nothing. `_TEMPLATE.md`, `_INDEX.md`, `<stem>.md`. Rules: the
      README's "Two paths, two tiers each". (Replaced on 2026-10-05 the pre-run
      comparison that rated the solutions and chose one run or two.)
    - `long-path/README.md` — what is specific to the long path's runs: where to start,
      cheap cases, worked examples (moved out of the shared README on 2026-10-06).
    - `short-path/README.md`, `run-executor.py`, `EXECUTOR-PROMPT.md` — the human guide and
      script (`canary`, `run`, `collect`) for the short path's stage 4, and the executor's prompt.
    - `long-path/` and `short-path/` (split 2026-10-05) — one folder per
      path, each holding:
      - `harness/<case-file-stem>/` — committed test code every run uses
        (e.g. the restored `HeapPoolTest.java`).
      - `results/<case-file-stem>.md` — one per case, plus
        `results/<case-file-stem>/run1/` (and `run2/`, if one is done) for
        small log excerpts.
- **`codeql-queries/`** (repo root, [README](codeql-queries/README.md)) — the
  CodeQL query packs that feed `stage2-ai-preprocessing/`; the if-check queries
  and their
  [pipeline README](codeql-queries/cassandra/queries/if-check-exp/README.md)
  are under `codeql-queries/cassandra/queries/if-check-exp/`. Results land in
  the gitignored `codeql-queries/results/` and must be regenerated on a new
  machine.
- **Outside this repo (CloudLab shared mount, see root `README.md` §2):**
  `git-repos/cassandra-src`, `tools/codeql/`, `codeql-dbs/`.

## Cassandra source (for stage-3 reading)

- **Local clone:** `cassandra-src` beside this repo (on CloudLab
  `/proj/misconfiguration-PG0/git-repos/cassandra-src`), a git
  clone of `apache/cassandra` at tag `cassandra-5.0.9` (separate from this
  repo, not tracked by it). On another machine, clone it yourself (command in
  `cassandra/if-check-exp/README.md` §2). Unit-test verification runs
  `ant testsome` in this clone.
- Confirm the version with `git describe --tags` (prints `cassandra-5.0.9`);
  `build.xml`'s `base.version` and `CHANGES.txt`'s top entry both read `5.0.9`.
- **Always grep/read the local clone to verify a line number**, then build
  the GitHub link as `.../blob/cassandra-5.0.9/<path relative to repo
  root>#L<NN>`. Never cite a line from memory or from a GitHub fetch alone.

## Current state — 17 cases filed

All seventeen are stage-3 complete: judged against the three rules with the
source open, citations checked against the pinned `cassandra-5.0.9` tag, and
each carrying a §9 test design for stage 4.
**There is no `Status` field** — manual and runtime verification happen in
**stage 4** (opened 2026-09-25, see "Scope decisions"). A filed case is complete *as stage-3 evidence*, not a verified
result. `Feed` records which stage-3 feed found it (`3a` = via
stage 1/2, `3b` = direct source reading).

| Case (file under `cassandra/if-check-exp/`) | Pattern | Feed | Key finding |
|---|---|---|---|
| `memtable_heap_space-tryAllocate-limit.md` | (b) | 3b | Disallow parks the caller; a `markBlocking()` op overshoots the limit (escape hatch). |
| `memtable_offheap_space-tryAllocate-limit.md` | (b) | 3b | Same check on the `offHeap` `SubPool`; same escape hatch. |
| `internode_application_receive_queue_capacity-acquireCapacity-queueCapacity.md` | (b) | 3b | Per-connection byte cap (default 4MiB); disallow registers on a wait queue, message not dropped; no escape hatch found. |
| `native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md` | (b) | 3b | Same check via `CQLMessageHandler` (default 1MiB). With the default `native_transport_throw_on_overload=false` the message is still decoded; only `throwOnOverload=true` rejects. |
| `MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md` | (a) | 3b | JVM property cap (default 3) on off-heap `HintsBuffer`s; disallow blocks on `reserveBuffers.take()`; no escape hatch found. |
| `cdc_total_space-processNewSegment-allowance.md` | (b) | 3b | Byte cap on un-consumed CDC segments; `processNewSegment():335` sets a `CDCState`, `throwIfForbidden():214` throws `CDCWriteException` (clean reject). **Stage 4 closed it 2026-10-01:** the cap holds at `⌊A/S⌋` links, one more when the check's counter is stale (at most `A + S`); `cdc_block_writes=false` turns off the rejection but not the cap — the oldest links are deleted, data is lost. |
| `DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md` | (c) | 3b | Disk guard on compaction output vs. free space. **The guard does not dominate the allocation** — on the default `diskBoundaries != null` path the `SSTableWriter` is created with no space check at all. |
| `max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md` | (b) | **3a** | Compaction admission gate, per file store, counting in-flight compactions. Disallow is a **shrink-and-retry ladder**, not a refusal; abort only at the end of it. Fail-open on estimation error. First case from feed 3a. |
| `max_hints_size_per_host-shouldHint-maxHintsSize.md` | (b) | 3a | Per-host byte cap on hint files on disk. **Off by default** (`0B`). Disallow silently skips the hint while the write succeeds — the folder's first disallow that loses data; no metric fires on it. |
| `file_cache_size-allocateMoreChunks-memoryUsageThreshold.md` | (a) | 3b | Byte ceiling on the chunk-cache pool's off-heap macro chunks. Disallow withholds the `Chunk`, but the caller then allocates straight from the OS with no ceiling — the limit bounds the pool, not the node's off-heap use. |
| `column_index_cache_size-indexSamples-cacheSizeThreshold.md` | (b) | 3b | Threshold on a partition's block index: `IndexedEntry` (array on heap) vs. `ShallowIndexedEntry` (file position). **Both branches allocate** — the divergence is retained size. Key cache re-caps the total, so the ceiling claim is per entry. |
| `max_mutation_size-validateSize-MAX_MUTATION_SIZE.md` | (c) | **3a** | Per-entry byte cap on one commit-log entry (a **per-item** bound: the node-wide ceiling is `limit × N`). The guard is the first statement of `CommitLog.add()` and **does dominate** the buffer and the segment reservation. The same verdict is read at **five call sites**, only one of which precedes new allocation; the limit is frozen at class initialization (restart-only) and derived from `commitlog_segment_size / 2`. At stock settings the CQL transport's own caps equal it, so client writes are shadowed; replay is unguarded; a logged batch is the client route to the commit-log site. |
| `max_value_size-read-maxValueSize.md` | (c) | **3a** | Per-value sanity bound on a length decoded from a stream: the guard in `AbstractType.read()` throws before `new byte[l]`, which is allocated at full size before any byte is read. **It dominates the allocation for every production caller** (four call sites, all passing the configured limit; the unguarded `readBuffer(in)` overload has no production caller, which corrects the earlier note) **but not the 29 call sites of the sibling primitives** `readWithVIntLength` / `readWithLength`, **and not the write side**: nothing compares a value with it when written, so a value above the limit is accepted, held in the memtable and flushed, and fails only when read back, **as corruption** (the SSTable is marked suspect and left out of compaction, an inbound message is dropped, a commit-log replay stops the node starting). At stock settings a client cannot reach it (default 256 MiB, above the 16 MiB write-side caps); only the cell-value site can fire on data a client wrote. |
| `CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT.md` | (a) | **3a** | Byte threshold on **one mutation's serialized size**: below it the mutation keeps a heap copy of its serialized bytes (`CachedSerialization`, a `byte[]` of exactly that size), at or above it only the size, and the mutation is **still sent, logged and applied** (CPU is spent instead of memory). **Both outcomes allocate**, as in `column_index_cache_size`; what is withheld is a copy beside the mutation's own heap. A **per-copy** bound: the node-wide extra heap is about `limit × N`, and nothing bounds *N*. **Two check sites of different patterns:** `Mutation.serialization():451` (a) and, on the receive side, `TeeDataInputPlus.maybeWrite():58` (a for each buffer write, b for the copy via a `limitReached` flag), reached from every deserialization (network, commit-log replay, hints, batchlog). A **JVM property**, restart-only, no yaml key or JMX, frozen in a `static final`. **An escape value:** a limit of 0 caches nothing on the serialize side and removes the bound on the receive side (`limit <= 0` is the tee's "unbounded"). `validateSize()` reaches this check, so measuring a mutation below the limit builds its copy. |
| `local_read_size_fail_threshold-addSize-failBytes.md` | (c) | **3a** | Running total of the heap sizes of what **one local read command** pulls from storage; `>=` aborts. **Per command, not per query** (each page and each `IN` partition resets it); a one-row overshoot; names-filter point reads build their rows before the guard; it counts before the row filter; the replica swallows the abort and answers empty and the coordinator decides. **Off by default** (limit `null`, master switch false), live-settable. **Stage 4 closed it 2026-10-07: both tiers Confirmed** — *X* = *T*(*i\**) exactly at 262,144 · 1,048,576 · 4,194,304 B, allocation of an over-limit read equals that of an *i\**-row read (increments 0.2501 against 0.25), bypass as recorded for the names-filter read (13 times the guarded slice), paging and the unflagged read; one sub-prediction missed (names read 77 % of unlimited, not within 10 %). |
| `row_index_read_size_fail_threshold-checkSize-failThreshold.md` | (c) | **3a** | Limit on the **estimated** in-memory size of one partition's index entry, checked in `RowIndexEntry.Serializer.checkSize()` before either entry object is built. The estimate is made **before** `column_index_cache_size` decides whether the entry is built, so at stock settings it refuses only entries that would have been shallow and bounds no heap. **Inert unless a `ReadCommand` is on the thread:** key-cache hits, SSTables opened lazily after `executeLocally()` returns (derived) and scans are not checked. Off by default. **Stage 4 closed it 2026-10-07: both tiers Confirmed** — accepted iff est ≤ limit (88 B × blocks + bytes), largest admitted estimate 15,651 · 62,826 · 251,731 B at 16,384 · 65,536 · 262,144 B, refusals leave the key cache unchanged, cached weight 1.69 × the estimate; bypass as recorded for a key-cache hit, a lazily opened SSTable (the derived analysis observed on a node) and a scan; **at the stock `column_index_cache_size` every accepted entry weighs 128 B, so the limit bounds no heap**. |
| `internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes.md` | (b) | **3a** | Per-**link** byte allowance on unsent outbound messages (urgent, small and large link per peer), with the excess borrowed from a per-peer and a node-wide reserve; **the disallow drops the message and does not slow the sender**: the request's callback is failed at once with `TIMEOUT` and an ordinary write is **hinted** on the coordinator (a counter write is not). **The per-peer reserve is read from the receive-side key** `internode_application_receive_queue_reserve_endpoint_capacity` on the production path (`OutboundConnectionSettings:395`, `withDefaults()` runs before `withDefaultReserveLimits()`), so `internode_application_send_queue_reserve_endpoint_capacity` is inert there (**derived from reading, not observed**; unit step U10 and scenario C test it). **At the defaults the reserves, not the capacity, are the large term:** node ceiling `3·P·C + min(P·E, G)`, 12 MiB per peer against up to 128 MiB per peer and 512 MiB per node. A link to an unreachable peer borrows nothing (capacity is a hard cap); a connected, full, non-draining link sheds no expired message by itself (the refusal precedes `queue.add()`, where pruning runs). `:416` (the stage-2 row's "reserve sub-check") is bookkeeping, the reserve comparison is `:419` into `ResourceLimits:138`. **Rule 3 holds in a weaker form:** the message exists before the check, so the branches diverge on retention and serialization buffers, not on creation. |

Each case's full detail lives in its own file.

**Every case carries a §9 test design in the new layout** (§9a summary and conclusions table for a human; §9b–§9e a Linux
runbook). Template: `stage3-ai-deep-read/long-path/_TEMPLATE.md`. Status of the §9s:

- **Audited, run and closed at stage 4 (5):** `memtable_heap_space`, `MAX_HINT_BUFFERS`, `cdc_total_space`, `local_read_size_fail_threshold`, `row_index_read_size_fail_threshold`.
- **Not yet audited or run (12):** every other case. Each must pass the stage-4 step-0 audit and be frozen before its first run, and each lists the harness it
  needs (Java tests, Byteman rules, scripts) as step-1 work; none of that code exists yet. The eight cases converted to the new layout on 2026-10-06 and the cases
  written since (`max_mutation_size`, `max_value_size`, `CACHEABLE_MUTATION_SIZE_LIMIT`, `internode_application_send_queue_capacity`) record in their §10 Notes
  where they differ from earlier notes on the same lines, **for stage 3 to judge, not applied to §5–§8**.
- **Untested central finding:** the seventeenth case's claim that the per-peer reserve is read from the receive-side key
  `internode_application_receive_queue_reserve_endpoint_capacity` is derived from the source only; if unit step U10 or scenario C refutes it, amend the case's §4, §5, §8 and §10.

## Latest status (2026-10-07) and next steps

### Stage 3 — long path (the deciding path; an AI session does all of it)

- **Pipeline:** stage 1 (CodeQL, 5,588 rows) and stage 2 (AI banding, complete over all rows: A 134, B 174, C 94, D 4,387; verdicts in `stage2-ai-preprocessing/bands.csv`) are done.
  Stage 3 is the bottleneck. Band A splits into **A1 (65, fully judged)**, **A2 (30, fully judged)** and **A3 (39 grow-when-full reallocations, not yet read; judge as one group)**. B (174) and C (94, the insurance band, not optional) follow; D last.
- **17 cases filed** (9 from feed 3b, 8 from feed 3a), all stage-3 complete. Refusals are in `rejected.md` (the only rejection file); undecided rows in `deferred.md`.
- **Write-up queue** (`long-path/pending.md`, items 1–6 filed and struck): next is **item 7 `repair_session_max_tree_depth`** (establish which term of its `min` binds before designing §9),
  then 8 `MAX_MATERIALIZED_KEYS`, 9 `Integer_MAX_VALUE` (type bound; §6.1 naming judgement), 10 `networking_cache_size` (sibling of `file_cache_size`), 11 `coordinator_read_size_fail_threshold` (**unjudged**; may be post hoc under Rule 3).
  Four undecided rows to settle first or alongside: `IndexSummaryRedistribution:341`, `SystemKeyspace:1919`, `ResourceLimits:138` (`deferred.md` §5) and `Envelope:429` (§6).
- **Open stage-3 judgements fed back from stage 4:** `CommitLogSegmentManagerCDC:345` as a check site; 
  the recommendations in each closed results file's §8 (applied: `cdc_total_space`'s §9a stale-counter wording, 2026-10-06, and all five of `MAX_HINT_BUFFERS`, 2026-10-07; the others not yet); the two read-size cases' stage-4 feedback (names-filter read allocates 77–78 %, not within 10 %; §9a "Default" bullet names an `active` field the Byteman rule does not print).
  Link `ResourceLimits$Basic.tryAllocate():213` from the two net cases (not yet done).
- **To start a write-up session:** *"Read HANDOFF.md, then `long-path/README.md` §2, `playbook.md`, `pending.md`'s write-up queue and `_TEMPLATE.md`. Write up the first unstruck item: re-read the source in `cassandra-src` (tag `cassandra-5.0.9`), answer all nine fields, design both tiers in §9a–§9e, verify every citation, add the `_INDEX.md` row, strike the candidate in `pending.md`. Do not commit."* One candidate per session (2–3 if siblings).
- **Method for a §9:** (1) read the upstream tests that touch the check and reuse them as the unit tier; (2) find the check's own debug/metric line, else design a Byteman rule; (3) make the limit moveable on a small dedicated filesystem or tiny pool; (4) derive the prediction from the source with its tolerance, as numbers, before any run;
  (5) cross-check old prose against the code and record contradictions in §10 Notes; (6) keep §9a to claim, how-this-verifies, procedure, prediction and a Conclusions table with Refuted, Not confirmed and Invalid rows;
  (7) trace the whole disallow chain to its callers, trace each limit's config key to where it is really read (a getter may read a sibling key), find who releases the resource before predicting a drain, grep the whole tree for "only caller" claims, and expand and check every `file:line` with a script.
- **Filing checklist:** `cases/<stem>.md` (nine fields, §9a–§9e, §10 provenance with feed and date) → `_INDEX.md` row, module note and §2 counts → strike the entry in `pending.md` → for feed 3a note the batch in `stage2-ai-preprocessing/README.md` → update the case count in this file.

### Stage 3 — short path (blind, human plus AI)

- **One solution filed:** `memtable_heap_space-tryAllocate-limit.md` (version 2, current, sha256 `31f017fe…`, claude-sonnet-5, isolation and leakage audit pass, 2026-10-05); version 1 kept as `--v1`, superseded. Comparison column in `short-path/_INDEX.md` is still **pending**.
- **The other 16 cases have no short solution.** The pilot on the three first-closed cases was skipped. A human starts the blind writer with `run-case.py`; a filed solution is frozen and never edited (`--supersede` for a new version).

### Stage 4 — long path (AI audits §9, runs it, owns the verdict; no human gate)

Five cases closed, **no run 2** anywhere. Results: `stage4-runtime-verification/long-path/results/<stem>.md` (+ `<stem>/run1/`), harnesses in `.../harness/<stem>/`.

| Case | Closed | Verdict | Key reading |
|---|---|---|---|
| `memtable_heap_space` | 2026-09-30 | Confirmed, unit and cluster | Writers wait at the limit; peak follows the knob (first limit flush at 99.1–99.8 % of it); the `markBlocking()` escape hatch fired at every value, forcing 0.02–0.94 % of the limit through. |
| `MAX_HINT_BUFFERS` | 2026-09-30 | Unit: consistent with Confirmed. Cluster: Confirmed with one recorded deviation | The 4 MiB reading-rule band was exceeded at every value; the create-trace clause decides and a supplementary allocation trace attributes the excess to non-pool allocations (band question closed 2026-10-07: the band is not a hard constraint, so §9a was amended — the create trace decides, `MemoryUsed` is read by its steps; the five recommendations are applied). |
| `cdc_total_space` | 2026-10-01 | Confirmed with a one-segment overshoot, both tiers; non-blocking mode: bypass as recorded, bounded by deletion | Ceiling is `⌊A/S⌋` links, one more when the counter is stale (≤ `A + S`); `cdc_block_writes=false` deletes the oldest links, so data is lost. |
| `local_read_size_fail_threshold` | 2026-10-07 | Confirmed, unit and cluster; bypass as recorded (names-filter read, paging, unflagged read) | The check's counter equals the predicted value exactly at 256 KiB, 1 MiB, 4 MiB. One sub-prediction missed (names read 77 % of unlimited). |
| `row_index_read_size_fail_threshold` | 2026-10-07 | Confirmed, unit and cluster; bypass as recorded (key-cache hit, lazily opened SSTable, scan) | Accepted iff estimate ≤ limit; **at the stock `column_index_cache_size` every accepted entry weighs 128 B, so the limit bounds no heap.** |

**Next:** audit, freeze and run the other 12 cases. `max_space_usable_for_compactions_in_percentage` is the cheapest unit tier; the unit tiers of `max_mutation_size`, `max_value_size` and `CACHEABLE_MUTATION_SIZE_LIMIT` are also cheap but need their harness written; `internode_application_send_queue_capacity` is the heaviest design (four processes, a Byteman hold, a poller of `system_views.internode_outbound`).

### Stage 4 — short path (blind executor)

- **One case run:** `memtable_heap_space` (2026-10-06, first run of `short-path/run-executor.py`). Both tiers confirmed by the executor (unit: B2g rows 1 and 3; cluster: 24 `MEMTABLE_LIMIT` flushes at 64 MiB against 3 at 512 MiB); self-check holds, no run 2. Results in `stage4-runtime-verification/short-path/results/`, harness in `short-path/harness/`. One audit hit accepted (an `ls` of the shared git-repos directory); three runbook defects (B2h controls skipped, control heap raised to 768m, B3g row 4 partly checked).
- **The side-by-side is not written:** `comparison/_INDEX.md` is empty. Next: a new AI session writes `comparison/memtable_heap_space-tryAllocate-limit.md` per `executor-prompts.md` §2 (it rates nothing).

### Lessons for the next harness

- The node runs from `build/apache-cassandra-*.jar`: a Byteman helper class goes on the **boot class path** (`-Xbootclasspath/a:<jar>`); a rule on a JDK class needs `boot:`.
- The bundled Python driver works at **protocol 5**, the only one that returns the per-replica failure code; a client connection reads system tables (adds key-cache entries and Byteman lines), so warm it with a probe read before a before-snapshot and filter lines on the case's keyspace.
- `nodetool sjk mx -f` takes one attribute per call and each call starts a JVM; start a node only after `nodetool status` shows `UN` and `nodetool statusbinary` prints `running`; `JVM_EXTRA_OPTS` is scoped to the `bin/cassandra` command, never exported (the Byteman agent would clash on port 9091).
- Check the unit yaml's defaults against the node's (e.g. `commitlog_segment_size` 5 MiB vs 32 MiB); do not assume an upstream test helper is reusable.
- Read the real resource first and the check's counter second (the counter is an asynchronously refreshed estimate); put a trace next to the files so an overshoot can be attributed; state predictions with that tolerance.
- Make the harness record a mismatch and go on; build every table from raw files with a script and write an independent self-check.
- Settle the node before a control (a bulk commit-log write stalls logged writes 10–16 s at the first periodic sync).
- One run script per case, values run one at a time as background ssh tasks, each writing `summary.txt`, `readings.csv`, `phases.csv`, `session.log`; pull only small files into the repo and keep full logs on the node. Read `summary.txt` and greps, not whole logs.
- `grep '^ERROR' system.log` (a level starts the line); `cassandra-stress` prints every failed write's error, so pull only its header and results block. A foreground `pkill -f` over ssh matches its own command line.

### Nodes and access

- `pc80` and `pc66` are idle with no daemon. Each has JDK 11 + Ant and a clone `~/cassandra-run1` at `b5f2a54210` with the harness tests copied into `test/unit/org/apache/cassandra/db/` (untracked); harness copies in `~/stage4-harness-run/`, full logs in `~/stage4-logs/`. `pc72` was never needed. CloudLab nodes are rebuilt from scratch, so `HANDOFF.md`, `stage4-runtime-verification/environment.md` and the case files are the only record a new node inherits.
- The tool shell does not source `~/.shell_common_init`, so use literal hosts: `jason92@pc66.cloudlab.umass.edu` (NODE0), `…@pc80…` (NODE1), `…@pc72…` (NODE2; its host key is not in `known_hosts`). Use `ssh -o BatchMode=yes -n` for commands and **no `-n` when piping a script in**. Wait for a node run with a background `until` loop or the Monitor tool, not a foreground `sleep`.

### Commit state

Last pushed commit before this edit: `081dcca` (2026-10-07, the `MAX_HINT_BUFFERS` amendment; `82f5d3b` is the handoff rewrite). Older history (the 2026-09 banding procedure, the capacity-word pass, earlier resume blocks) is in git: `git show 2e9cf7b:HANDOFF.md`.
