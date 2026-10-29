# If-Check Exp — Handoff

For a new session picking up `if-check-exp` work. Read this first, then
[`cassandra/if-check-exp/README.md`](cassandra/if-check-exp/README.md) for the full format spec.
The paused sibling experiment has its own brief at
[`cassandra/entry-restriction-exp/HANDOFF.md`](cassandra/entry-restriction-exp/HANDOFF.md).

## Which handoff file to use (read first)

**Always check this file first.** It holds the notes common to everyone; personal instructions
and progress live in a per-person file. Work out who you are (ask if unclear), then:

| If you are | Also read | Leave your personal handoff notes in |
|---|---|---|
| **Jingsong Meng** | [`HANDOFF-Jingsong.md`](HANDOFF-Jingsong.md) | `HANDOFF-Jingsong.md` |
| **Yang Wang** | [`HANDOFF-Yang.md`](HANDOFF-Yang.md) | `HANDOFF-Yang.md` |

- **Common notes** (shared background, decisions in force, lessons, nodes, follow-ups that concern
  both people) go in this file, `HANDOFF.md`.
- **Personal notes** (your set's job, progress, batch log, your nodes) go only in your own file.
  Do not edit the other person's file.

**Cleaned up 2026-10-23.** The dated batch logs, per-case run narratives and old node notes were
removed; every closed case's detail is in its case file and results file. The full previous
version is in git: `git show d40ee0c:HANDOFF.md` (older: `git show 2e9cf7b:HANDOFF.md`).

**Project context:** the three project-wide targets are in the repo-root [`README.md`](README.md) §0.
The running plan and findings live in two Google Docs —
[*Meeting Summary*](https://docs.google.com/document/d/1tldFFEk28qtQD0QdsnC2Br-BisTyOUp8OCwG1SZ_6Jk/edit)
and [*Progress Report*](https://docs.google.com/document/d/1gMRFwaTvgahSiRi10ad_Y3CLDkxyF1QTYkAhZ4be4x8/edit).

## Next job (2026-10-23): two people, two sets

The 337 band A/B/C units that no case file targets yet are split into two sets. Each person uses
fresh autonomous agents to write up a case per target and verifies each at stage 4.

| Owner | Handoff | List | Units / targets |
|---|---|---|---|
| Jingsong | [`HANDOFF-Jingsong.md`](HANDOFF-Jingsong.md) | [`writeup-set-A.csv`](cassandra/if-check-exp/stage3-ai-deep-read/writeup-set-A.csv) | 168 / 159 |
| Yang | [`HANDOFF-Yang.md`](HANDOFF-Yang.md) | [`writeup-set-B.csv`](cassandra/if-check-exp/stage3-ai-deep-read/writeup-set-B.csv) | 169 / 161 |

The personal handoffs hold the job, the procedure and the progress; this file holds what both
share. Update the "Current state" numbers below when a batch closes (last: 2026-10-27, set A batch 11).

## What this experiment is

Part of the **misconfiguration** project (Target 1: find resource constraints that limit memory or
disk usage; Target 2: show how the code enforces each; Target 3, bypass analysis, is out of scope
here), on **Apache Cassandra 5.0.9**. `if-check-exp` inventories **capacity checks** — a comparison
of usage against a limit — and the **decision points** they feed, where one outcome lets a memory-
or disk-significant allocation happen and the other blocks, defers or rejects it. It is a standalone
inventory: no cross-referencing with `entry-restriction-exp`, no shared infrastructure; bypasses
noticed along the way are noted in case files for Target 3, not chased.

**Four stages:** (1) CodeQL finds the comparisons; (2) an AI ranks every row into bands A–D;
(3) agents read the source and write a **case file** per line, with an **estimate** and a two-tier
(unit + cluster) verification design; (4) an AI audits and runs each design and files the verdict.

## Current state (2026-10-25)

- **Stage 1:** 17,343 `if` statements → 4,489 numeric comparisons + 1,099 helper-guarded rows.
- **Stage 2:** 4,789 units banded (A 134, B 174, C 94, D 4,387); `stage2-ai-preprocessing/bands.csv`.
- **Stage 3:** bands A, B and C fully read; **115 case files** (29 guided, 86 autonomous; estimate
  positive 56, negative 59). 65 of the 402 A/B/C units were a case's target before the two-set job;
  the other **337** are that job (2 accepted candidates in `predicted-positive.md`, the rest rejected
  lines in `predicted-negative.md`, ~151 rows). Set A has written up **78** of its 159 targets
  (batches 1–11, 2026-10-24/27); set B none yet. Nothing is undecided. Band D is not read.
- **Stage 4:** **all 115 closed**, run 1 only (set A batch 10: `lc` also ran a second cluster pass, same session): 94 Confirmed, 4 Refuted,
  16 partial, 1 not confirmed. **Outcome class:** 51 true positive, 0 false positive, 46 true
  negative, 5 false negative, 13 undetermined (all autonomous, mostly the cluster tier).
  Per-case verdicts: `stage3-ai-deep-read/_INDEX.md` §1. *(The counts above predate set A's later
  batches; `_INDEX.md` §1 is the current record.)*
- **2026-10-27, four non-config positives closed** on nodes `pc39`, `pc32`, `pc29`, `pc41` of
  experiment `jason92-321705` (JDK 11.0.32.1, Ant 1.10.12, 40 cores, 251 GiB; one case per node, run 1 only,
  no run 2): `default_page_size-cqlgroupbylimits_onclose-rowlimit` (U/C Confirmed), `diagnostic_event_memory_store_max_size-store-keyhead`
  (U/C Confirmed), `trie_2gb_hard_limit-allocateblock-leadbit` (U/C Confirmed), `max_compaction_flush_memory_in_mb-getmode-maxmembytes`
  (U Confirmed, C Partial: bypass at a 1 MiB cap). All four true positive. `predicted-positive.md` has no open stage-4 rows now.
- **2026-10-28, 14 hard-coded-constant cases from the non-config job closed at stage 4** (set A rows 7, 85, 103, 107, 114, 115, 117, 120, 127, 130, 131, 138, 141, 142; nodes `pc39`, `pc32`, `pc29`, `pc41`, run 1 only, no run 2): 8 true positive (`counter_cache_size` at three sites, `nopcache_capacity`, `monitoring_max_operations`, `virtual_logs_max_rows`, `mutation_repair_rows_per_batch`, `row_overhead_size`), 5 true negative (`seed_count_warn_threshold`, `max_space_usable_for_compactions_in_percentage` range, `repair_session_space` minimum, `repair_disk_headroom_reject_ratio`, SAI `segment_write_buffer_size`), 1 false negative (`prepared_statements_cache_size` preload threshold: Not confirmed, bypass through eviction tombstones in the `system.prepared_statements` memtable). The `counter_cache_size` cases share one run. Verdicts: `stage3-ai-deep-read/_INDEX.md` §1. Open: `predicted-negative.md` still lists the entries of the 27 set A rows written up on 2026-10-27; row 7's note in `undetermined.md` §5.2 still says "not a case".
- **2026-10-28, hard-coded-constant batch 1 closed at stage 4** (7 of the 28 remaining hard-coded-constant cases, grouped in `cassandra/if-check-exp/stage4-runtime-verification/hardcoded-batches.md`; nodes `pc39`, `pc32`, `pc29`, run 1 only, no run 2): all 7 true negative, U/C Confirmed, does not cap: `excess_waste_bytes` at three sites and `excess_waste_offset` (AtomicBTreePartition), `max_region_size` (NativeAllocator), `hints_write_buffer_size` and `write_buffer_size` (HintsWriter). Caveat: `excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2` cluster verdict rests on the small-batch workload only (the big-batch workload WE failed on the node, runbook defect D2). Batches 2-4 (21 cases) not started. Open: `predicted-negative.md` still lists these entries.
- **2026-10-28, hard-coded-constant batch 2 closed at stage 4** (nodes `pc39`, `pc32`, `pc29`, `pc41`, run 1 only): 5 true negative (`logs_virtual_table_default_rows`, `max_unsigned_short` validateIndexedValue, `name_length` custom index column name, `filename_length` snapshot name, `schemaconstants_name_length` keyspace name) and 2 undetermined: `max_shard_split` (U Confirmed, C Not confirmed: the positive control `max_sstables_to_compact` never bound) and `table_name_length` (U Confirmed, C Refuted: heap after GC +60.7 MB at 500 tables with 222-char names vs 8-char, probably per-table metric MBean names; reads as a false negative at cluster level). Caveats: `filename_length` cluster heap missed its 1 MiB tolerance by 0.5 MiB (G1 noise about 16 MiB; filed Confirmed, overrule if strict); `schemaconstants_name_length` shows +4.2 MB, probably a small real effect inside cluster resolution. Batches 3-4 (14 cases) not started.
- **2026-10-28, hard-coded-constant batches 3 and 4 closed at stage 4** (14 cases, nodes `pc39`, `pc32`, `pc29`, `pc41`, run 1 only): 11 true negative and 3 undetermined. Undetermined: `block_size-add-blockindex` (U Confirmed, C Refuted on a frozen 10% disk bound: 26.8% difference, all in numeric-values files), `block_size-writeposting-blocksize` (C Not confirmed on a frozen 5% bound; the agents filed both as true negative, the index says undetermined per the README rule and each results file notes it), `super_block_size` (C Not confirmed; heap too noisy). All 28 hard-coded-constant cases are now closed. Caveats: `max_array_length` is true negative only if the claim is read as "in practice" (one writer's start-value list is bounded near 2 GiB at artificial widths; strictly an FN); the pc32 agent ran up to six nodes at once on pc32 against the one-run-per-node rule; many frozen sub-range predictions were missed and left unedited (see each results file). **Harness side effect:** a blanket `sed -i` over `harness/*/unit-run.sh` on 2026-10-28 ~19:45 removed `-XX:+UseSerialGC` from about 160 scripts; the two tracked files that had it were restored, but untracked scripts (batches 1-2 and others) may have lost it and the script text may not match what ran; verdicts rest on run logs on the nodes.
- **2026-10-28, design for `none`-type cases recorded** (proposal, not yet run): `cassandra/if-check-exp/stage4-runtime-verification/none-type-design.md`. 42 of the 50 `none` cases are unrun; 31 of those declare both tiers `n/a`. Not yet decided: whether to run the 11 with designs, write new designs for the 31 (kinds 1 and 3 first), or close the 31 as "Confirmed from source, not run" and keep them out of the true-negative count.
- **2026-10-29, first `none`-type batch run at stage 4** (13 cases, unit tier only, cluster `n/a`; nodes `pc39`, `pc32`, `pc29`, `pc41`, run 1 only), designs from `stage4-runtime-verification/none-type-design.md` and the drafts `none-type-drafts-kind1.md` / `-kind3.md`, applied to each case file as dated B2 amendments. 10 Confirmed / does not cap / true negative: `readfully-dest_length`, `read-count`, `checklimit-length`, `compose-buffer_remaining`, `addall-size`, `hascomponent-i_nextsize`, `isempty-size`, `resizeto-newcapacity`, `capacity-newcapacity`, `allocateblock-inchunkpointer`. 3 Not confirmed / undetermined, all on small-cell noise criteria: `iscolumnrange` (reading with the noise row set aside: does not cap, TN), `doesaggregation` (set aside: bypass, caps by query shape, FN; retained result 12.4 MB plain vs 168 B for `max`), `needfiltering` (set aside: bypass, soft gate that ALLOW FILTERING skips, FN; rejected query costs 13.4 kB vs 0.4/3.9/39.2 MB with ALLOW FILTERING). Open: overrule the three, if wanted. `resizeto`/`capacity` verdicts rest on the ruling that a skipped transient copy is not a cap (added to `none-type-design.md` §4). Audit finding for stage 3: `RangeTombstoneList.add()` line 178 double-counts `boundaryHeapSize`, inflating `unsharedHeapSize()` by 240,000 B per 1000 adds and feeding memtable accounting (`BTreePartitionUpdater.java:121`); effect on flush timing not measured. Not run: 5 `none` cases to close "from source, not run" (`isempty-size-2`, `hasunrestrictedclusteringcolumns`, `isdone-remainingcount`, `hascomponent-componentbounds_size`, `allocateoversize-peer`) and the 18 kind-2 cases. 21 of 50 `none` cases now have a verdict (17 true negative, 4 undetermined); 29 are not run.
- **2026-10-29, weak outcome classes added** (rule in `stage4-runtime-verification/README.md`, Outcome class): a case whose cluster tier could not settle the effect is classed from its unit tier alone when that tier is Confirmed or Refuted, as *weak* true positive / false positive / true negative / false negative, counted apart from the strong classes. Applied to 18 of the 23 undetermined cases in `_INDEX.md` §1: 5 weak TP, 12 weak TN, 1 weak FN (`largestRatio`, unit Refuted, cluster Confirmed). 3 carry `(cluster disagrees)`: `largestRatio`, `block_size-add-blockindex`, `table_name_length`. 5 stay undetermined: `flushLowWaterMark`, `OTCP_LARGE_MESSAGE_THRESHOLD` (unit Not confirmed) and the three kind-2 `none` cases (`iscolumnrange`, `doesaggregation`, `needfiltering`). Strong counts unchanged: 67 TP, 0 FP, 98 TN, 6 FN, 43 not run.

## Decisions in force

- **Two agents** (2026-10-19): the **autonomous agent** gets only
  `playbook-autonomous.md`, `_TEMPLATE-autonomous.md` and a `file:line`, run by hand in a fresh
  Claude Code session in a copy of the source outside this repo; the **guided agent** gets human
  suggestions and asks per case whether to read the autonomous file. A case file's agent is its
  suffix: `<stem>--autonomous.md`, `<stem>--guided.md`. No leakage control beyond that.
- **Estimate vocabulary:** stage 3 predicts `positive` (usage follows the constraint), `negative`
  (it does not, with a **Ground**) or `undetermined`. A negative line still gets a full two-tier
  design that tests that usage does **not** follow the constraint, with a positive control.
- **Every rejected line is a write-up item** (2026-10-19): it leaves `predicted-negative.md` once
  its case is verified at stage 4. `predicted-negative.md` is the only rejection file.
- **Stage 4 has no human gate** (2026-09-30): the AI audits, runs, self-checks and files the
  verdict; Jingsong may overrule any verdict (record it with date and reason).
- **Verdict wording:** "Confirmed" always means the file's own claim held; each results file
  records the claim tested and the **Effect on the constraint**, and since 2026-10-22 the
  **Outcome class** (estimate vs stage-4 effect, stage 4 taken as truth; definition in
  `stage4-runtime-verification/README.md`).
- **Frozen predictions** (2026-10-22): no conclusions row or prediction is changed after any
  reading; an unmatched reading is "Not confirmed (no matching row)". Amendments are dated and made
  before the first reading.

## Working preferences

- **Plan before editing** rules, naming, scope or folder structure: give an opinion or a
  file-by-file plan and wait for Jingsong's go-ahead. Small factual fixes need no plan.
- **Commit and push only on request**, asked separately. Two people now commit to `main`:
  `git pull --rebase` before every push.
- **Sync before restructuring:** files are also uploaded to GitHub directly, so `git fetch` and
  compare with `origin/main` before renaming or reorganizing.
- **Keep settled decisions** (for example, no cross-referencing `entry-restriction-exp`).

## Where things live

- **Repo:** `MengJingsong/Misconfiguration` on GitHub; no checkout on the CloudLab shared mount.
- **`cassandra/cassandra-5.0.9/`** — the pinned source (`apache/cassandra` tag `cassandra-5.0.9`,
  commit `b5f2a54`, unmodified, committed 2026-10-22). Read and cite from it; never build in it.
  Confirm with `build.xml` `base.version` = `5.0.9` and `git status cassandra/cassandra-5.0.9`
  (nothing changed). GitHub links: `.../blob/cassandra-5.0.9/<path>#L<NN>`, line checked in the
  local file. Records before 2026-10-22 name the old `cassandra-src` clone (same files).
- **`cassandra/if-check-exp/`**
  - `README.md` — format spec, the three rules (§3.4–§3.6), required content, version pinning (§2).
  - `stage1-codeql-preprocessing/` — pointers only; queries in `codeql-queries/`, CSVs gitignored.
  - `stage2-ai-preprocessing/` — `bands.csv` (per-row verdicts), `bands.md`, `playbook.md`, `README.md`.
  - `stage3-ai-deep-read/` — both playbooks and templates, `cases/`, `_INDEX.md` (master index; §4
    holds the autonomous files' sha256), `predicted-negative.md`, `predicted-positive.md`,
    `undetermined.md`, `writeup-set-A.csv`, `writeup-set-B.csv`.
  - `stage4-runtime-verification/` — `README.md` (run protocol, safety rules, outcome class),
    `environment.md` (**start here on a new node**), `environment-notes.md`, `case-notes.md`,
    `_TEMPLATE.md`, `copy-source.sh` (local working tree with a git baseline), `results/<stem>.md`
    + `results/<stem>/run1/`, `harness/<stem>/`.
- **`codeql-queries/`** — the CodeQL packs; results gitignored, regenerated per machine.
- **Outside the repo (CloudLab `/proj/misconfiguration-PG0/`):** `tools/codeql/`, `codeql-dbs/`,
  and the superseded `git-repos/cassandra-src` clone.

## Stage-4 recipe

Protocol: `stage4-runtime-verification/README.md` ("The run protocol").

1. **Step-0 audit** against `cassandra/cassandra-5.0.9/`: re-read every load-bearing citation,
   check the trigger really reaches the check (find the `OperationType` / caller it produces),
   check the predictions have numbers and the workload arithmetic reaches the limit. Fix what the
   source shows as dated amendments; write the audit and the frozen hash of the prediction tables
   into the results file **before any reading**.
2. Harness in `harness/<stem>/` (unit test + one run script per case with `EXPECTED:` lines, a stop
   on a failed first-trigger check, node stopped on any exit); instrument-check it. Shakedowns are
   not readings. Write audit, amendments, freeze hash and harness to the repo before run 1.
3. Run 1: unit tier, then each cluster label as a background job; read `summary.txt`, not whole
   logs; pull small excerpts to `results/<stem>/run1/`, full logs stay on the node.
4. **Independent self-check** that re-parses the raw logs; fill the results file and outcome class,
   the case file's feedback section, `_INDEX.md`; decide run 2 and say why.

## Lessons

**Design**
- With one table, "how much to reclaim" logic is invisible: use several tables plus a Byteman
  `AT LINE` mutant. Unthrottled stress puts peaks at flush throughput, not the limit.
- "Counts items, not bytes" and "soft target, not a ceiling" are weak rejection grounds when each
  item has a known size or the target is a configurable byte count (those lines mostly cap).
  Hard-coded water marks and pool-internal bookkeeping did not cap.
- Read the real resource first and the check's counter second (counters are asynchronous
  estimates); a counter's own trace does not show it tracks the resource.
- Any request held longer than 12 s needs `native_transport_timeout` raised (the coordinator waits
  for the nearer of it and the verb timeout). 5.0 also caps the internode mutation deadline at it.
- `native_transport_max_threads` (128) limits messages held per sender and queued depth;
  `cassandra-stress` limits itself to 1,024 requests in flight (raise `connectionsPerHost`).
- Check a request's size against `LARGE_MESSAGE_THRESHOLD` (131,071 B on the CQL side) before
  predicting its path. Large native-v5 requests leave unreturned direct buffers: use protocol 4
  for direct-memory readings with large client writes.
- `nodetool compact` is a `MAJOR_COMPACTION`; a background compaction (`enableautocompaction`) is
  `COMPACTION`. The first abort or first use in a JVM carries one-off allocation: warm up first.

**Running**
- The node runs from `build/apache-cassandra-*.jar`: Byteman helper classes go on the boot class
  path; a rule on a JDK class needs `boot:`; Byteman's parser needs `(new X(…)).m()`;
  `CassandraDaemon` closes stdout, so trace to a file. Move Byteman listeners off 9091 when two
  JVMs share a host (BMUnit: `-Dorg.jboss.byteman.contrib.bmunit.agent.port=19091`).
- A standalone client JVM on Cassandra classes needs `conf/jvm11-clients.options` on JDK 11. The
  bundled Python driver: use protocol 5 for per-replica failure codes; on one node use
  `DCAwareRoundRobinPolicy` and `token_metadata_enabled=False`.
- Guardrail tests need `PasswordAuthenticator` plus an ordinary role (with `AllowAllAuthenticator` every client is a superuser and guardrails never fire); `bti` needs `storage_compatibility_mode: NONE`; memtable regions come from JNA `malloc`, so NMT cannot see them (read `RssAnon`), and set `memtable_cleanup_threshold: 0.99` or the pool limit is never reached (set A batch 7).
- Several local nodes applying every write stall on a spinning disk: put data on a tmpfs.
  Timed-out writes expire in the sender's queue and are hinted: truncate hints between arms.
- `ant testsome` forks a 1 GiB JVM (`maxmemory` overrides `-Xmx`); every test copied into a tree
  is compiled by every later `testsome` there; Ant's 1 s timestamps defeat a mutant built from a
  copied `build/` (delete the class files). Never run `ant` in a tree a node runs from.
- A node refuses `concurrent_writes: 1` (set 2, then `nodetool setconcurrency <stage> <n>`, the
  two-argument form). Live heap: the `GC.class_histogram` total, not `GC.heap_info` after `GC.run`.
  Read `RssAnon`, not `VmRSS`. logback rolls `system.log` at local midnight.
- Launch node scripts as `( setsid nohup … < /dev/null > /dev/null 2>&1 & )`; wait with bounded
  background polls, never a foreground `sleep`, and inside the agent's turn. Kill by PID
  (`pkill -f` can match its own shell); match daemons by `java` and working directory. Scripts
  synced to a node can lose the execute bit (call them with `bash`); never edit a running script.
- `grep '^ERROR'` misses messages on the next line; compare numbers in Python, not ad hoc `awk`;
  a self-check matching log seconds takes the last line at or before the second.

## Open follow-ups (not assigned)

- **Upstream bug candidates (JIRA check first):** native-v5 large-request frame buffers never
  returned (`networking_cache_size`, `OverflowSize` grows); `BufferPool` overflow trims drive
  `OverflowSize` negative (`NORMAL_CHUNK_SIZE`); pre-V5 THROW-path direct-memory retention;
  `MAX_HINT_BUFFERS=1` deadlocks the hint path; `sendWriteWithCallback` holds a refused write until
  the timeout (`internode_max_message_size`); `maxHintsInProgress` can never fire (bare
  `CacheLoader`, `StorageProxy.java:203`); `SerializingCache.clear()` does not free native memory (removal cause EXPLICIT, the listener frees
  only evictions; seen in `entry-size-limit` and `row_cache_size` cases, 2026-10-25); `ChecksummedDataInput.close()` never returns the decompressed hint block (BufferPool `OverflowSize` drifts ~6.6 MB per closed hints file) and `CompressedChecksummedDataInput` allocates a forged block-header size unchecked (512 MiB header → 563.7 MB; set A batch 5, 2026-10-25); a forged 512 MiB block header in `EncryptedChecksummedDataInput` allocates ~537 MB heap garbage plus ~537 MB direct memory cached on the reading thread (set A batch 6, 2026-10-26); `ValidationManager.java:62-63` computes `repair_session_space * 1048576 / RF` in `int` (wraps for ≥ 2048 MiB: tree depth 1; set A batch 7); `MemtableOffHeapDataSize` gauge registered under the name `MemtableOnHeapDataSize` (`TableMetrics.java:507`) and `AllMemtablesOffHeapDataSize` covers only the current memtable; `nodetool setcachekeystosave` says "0 to disable" but 0 means save all (`AutoSavingCache.java:305`); stale "1G default" text/log message in `IndexMode.java:60`/`:192` (real default of `max_compaction_flush_memory_in_mb` is 0.15 GiB); `MEMTABLE_TRIE_SIZE_LIMIT`
  (`cassandra.trie_size_limit_mb`) has no reader (the trie threshold uses `cassandra.memtable.row_overhead_size`).
- **Reruns that could settle undetermined cluster tiers:** the `SEPExecutor` cases (pin
  `native_transport_max_threads`, throttle the load), `flushLowWaterMark`, the SAI sawtooth,
  `NORMAL_CHUNK_SIZE` with held frames, a throttled arm for `commitlog_total_space` `:259`.
- **Stage-3 notes not yet applied to filed cases:** `SystemKeyspace.java:1919` as a second check
  site of `prepared_statements_cache_size`; stream receive (`StreamSession.checkDiskSpace()`) as a
  second decision point of `max_space_usable_for_compactions_in_percentage`; `max_mutation_size` §5
  calls `commitlog_total_space` a ceiling (it is a reclaim target); `file_cache_size` §4 names
  `applyConfig()` (it is `applySimpleConfig()`). Older rulings and notes: previous version above.
- **Remaining band-D lines in `predicted-negative.md` §10** (`SEPWorker`, `SharedExecutorPool.java:137`,
  `SEPExecutor.java:373`): low value after the `SEPExecutor` results.
- **`undetermined.md` §2 re-audit** (rejections made under the old pattern-(a)-only scope) and
  **band D** (4,387 units, one filed case already came from it).

## Nodes and access (checked 2026-10-21)

Experiment `jason92-320876`, Ubuntu 22.04, 40 cores, 251 GiB each; JDK 11.0.32.1, Ant 1.10.12,
`~/cassandra-run1` built with `build-test`; no Cassandra process left on any.

| Node | Host | Control | LAN | Suggested user (2026-10-23) |
|---|---|---|---|---|
| `pc07` | node0 | `198.22.255.17` | `10.10.1.1` | Jingsong |
| `pc12` | node1 | `198.22.255.22` | none (ring uses control addresses) | Jingsong |
| `pc06` | node2 | `198.22.255.16` | `10.10.1.3` | Yang |
| `pc13` | node3 | `198.22.255.23` | `10.10.1.4` | Yang |

- `ssh pcNN` works once `setup-node.sh --peers "..."` has been re-run on the node (the `~/.ssh/config`
  stanzas use the shared `id_ed25519` deploy key, which the peers accept). Peers' `ulimit -n` is 1024:
  raise it in the shell that starts a node.
- Untracked test files and `~/stage4-*` folders from closed cases remain on each node (listed in
  each results file). Two cases on one node need separate working trees, data directories, JMX and
  Byteman ports, and loopback addresses (recorded as an environment deviation).
- Full table and setup history: `stage4-runtime-verification/environment.md` §7. CloudLab nodes are
  rebuilt from scratch, so this repo is the only record a new node inherits.
