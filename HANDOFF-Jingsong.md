# If-Check Exp — Handoff for Jingsong (set A)

Created 2026-10-23. The shared background (what the experiment is, where things live, the
stage-4 lessons, node access) stays in [`HANDOFF.md`](HANDOFF.md); this file holds only
Jingsong's next job. Yang works on set B in parallel ([`HANDOFF-Yang.md`](HANDOFF-Yang.md)).

## The job

Use **fresh autonomous agents** to write up a case file for every target in **set A**, then
verify each case at **stage 4** (audit, run 1 at both tiers, results file, outcome class).

- **The list:** [`cassandra/if-check-exp/stage3-ai-deep-read/writeup-set-A.csv`](cassandra/if-check-exp/stage3-ai-deep-read/writeup-set-A.csv) —
  **159 targets covering 168 stage-2 units** (band A 46, B 64, C 58), every one a negative estimate.
  Mostly `cache/`, `config/`, `cql3/`, `db/`, `hints/` and the first part of `index/` (up to
  `index/sai/disk/v1/vector/`), plus a few `io/`, `utils/` and other lines tied to the same queue rows.
- **Where the list came from (2026-10-23):** the 402 band A/B/C units of
  `stage2-ai-preprocessing/bands.csv`, minus the 65 that are already the target of a case file
  (a guided file's **Capacity check** or an autonomous file's **Entry pointer**), leaves **337**.
  They were split into two sets of near-equal size by source area, keeping every unit of one
  source file and every unit of one `predicted-negative.md` row in the same set, so siblings are
  written up by one person. Set B has 169 units / 161 targets.
- **A target** is one `file:line` (units on the same line, `#1`/`#2`, are merged) or one helper
  method (`helper <class>.<method>()`; give the agent the comparison line inside the helper,
  found with `grep -n` in `cassandra/cassandra-5.0.9/`).
- **CSV columns:** `order` (suggested order), `target`, `units`, `band`, `estimate`,
  `stage3_record` (where stage 3 recorded the line: a `predicted-negative.md` section, or a note),
  `stage2_reason`, and two columns to fill as you go: `case_file` (the stem) and `stage4`
  (the outcome class, or "running").
- **Special rows** (read the `stage3_record` note before writing them up):
  `SystemKeyspace.java:1919` (settled 2026-10-21 as a second check site of
  `prepared_statements_cache_size`, not a case) and `CommitLogSegmentManagerCDC.java:345`
  (an open stage-3 question fed back from stage 4). Decide per row whether a separate case is
  worth it; record the decision in the CSV either way.

## How to do one target

### 1. Write-up (stage 3, autonomous agent)

1. Make a copy of the source **outside the repository**, so the agent cannot read other cases:
   `rsync -a cassandra/cassandra-5.0.9/ ~/cassandra-5.0.9/`.
2. Open a **fresh** Claude Code session in that copy. Give it only
   [`playbook-autonomous.md`](cassandra/if-check-exp/stage3-ai-deep-read/playbook-autonomous.md),
   [`_TEMPLATE-autonomous.md`](cassandra/if-check-exp/stage3-ai-deep-read/_TEMPLATE-autonomous.md)
   and the target as `file:line`. Nothing else about the line (not the stage-3 ground, not the CSV).
3. File the result as `cases/<stem>--autonomous.md`. The stem follows the existing ones:
   `<constraint>-<method>-<operand>`; check `ls cases/` first and add `-2` if the stem is taken.
4. Add the `_INDEX.md` §1 row (Agent `autonomous`, the file's own estimate, Stage 4 empty) and its
   sha256 in `_INDEX.md` §4. Put the stem in the CSV's `case_file` column. Leave the line in
   `predicted-negative.md` until stage 4 has closed the case.

### 2. Verification (stage 4, a separate agent)

Protocol: [`stage4-runtime-verification/README.md`](cassandra/if-check-exp/stage4-runtime-verification/README.md)
("The run protocol"); environment: [`environment.md`](cassandra/if-check-exp/stage4-runtime-verification/environment.md).

1. **Step-0 audit** (A–D) against `cassandra/cassandra-5.0.9/`; fixes go in the case file as dated
   amendments (section D). Write the audit and the frozen hash of the predictions and conclusions
   tables (B2f–g, B3f–g) into a new results file from `_TEMPLATE.md` **before any reading**.
2. Harness under `harness/<stem>--autonomous/`; working trees from
   [`copy-source.sh`](cassandra/if-check-exp/stage4-runtime-verification/copy-source.sh), one per case.
3. Run 1, unit tier then cluster tier; independent self-check from the raw logs; fill the results
   file, including the **Outcome class**.
4. Close the case: `_INDEX.md` §1 Stage 4 and Outcome class cells, the new sha256 in §4 if the case
   file was amended, remove the line from `predicted-negative.md`, fill the CSV's `stage4` column.

### Rules that hold for every case

- **No conclusions row or prediction is changed after any reading.** A reading that matches no
  frozen row is "Not confirmed (no matching row)".
- A negative-estimate case needs a **positive control** (a knob or arm that does move usage), so a
  "does not cap" result cannot come from a workload that never reached the check.
- Nothing is left running on a node; each results file lists what stays on the node.
- Commit per closed batch; `git pull --rebase` before every push (Yang commits to the same `main`).

## Suggested batching

- **4–5 targets per batch, one stage-4 agent per node**, as in the four batches of 2026-10-21/22.
- Keep the targets of one `predicted-negative.md` row in one batch (they share a design).
- Order within the CSV is band A → B → C, then by source area. Low-value rows (§14 package surveys,
  §12 emptiness tests, §1 configuration validation) can wait until the rest is done.

## What the earlier write-up batches teach (19 lines tested, 2026-10-21/22)

- "Counts items, not bytes" and "a soft target, not a ceiling" were weak grounds when each item has
  a known size or the target is a configurable byte count: those lines mostly came back **caps**.
  Hard-coded water marks and pool-internal bookkeeping did not.
- The cluster tier is where negative cases go **undetermined** (12 of 58 cases): plan a cluster arm
  that isolates the line (hold `native_transport_max_threads`, throttle the load, add a Byteman
  `AT LINE` mutant) and a positive control that is known to move.
- `cassandra-stress` limits itself to 1,024 requests in flight (raise `connectionsPerHost`); any
  request held longer than 12 s needs `native_transport_timeout` raised; read live heap from the
  `GC.class_histogram` total, not `GC.heap_info` after `GC.run`.
- More in `HANDOFF.md` ("Lessons") and each closed results file's §8.

## Nodes

Split with Yang until agreed otherwise: **Jingsong `pc07` and `pc12`**, Yang `pc06` and `pc13`
(experiment `jason92-320876`; access and state in `environment.md` §7 and `HANDOFF.md`).
Two cases on one node need separate copies, data directories, JMX ports and Byteman ports.

## Progress

| | Targets | Written up | Stage 4 closed |
|---|---|---|---|
| Set A | 159 | 78 | 78 |

**Batch log.** 2026-10-24, batch 1 (CSV rows 4, 5, 6, 8, 9; §6 `RangeTombstoneList` and §4
`CommitLogSegment`): `range_tombstone_list_growth_factor` ×3 true negative (do not cap), `commitlog_segment_size` ×2
true positive (cap per segment; the CSV said negative, the autonomous files estimated positive).
Write-ups were run as headless `claude -p` sessions in `~/cassandra-5.0.9` from `~/writeup-A/`.
Next: rows 1–3 (§14 cache bounds), 10–15 (`CommitLogSegmentManagerCDC.java:345`, `LeveledManifest`, `MajorLeveledCompactionWriter`), with row 7 a decision.

2026-10-24, batch 2 (CSV rows 11–15, §14 `LeveledManifest` and `MajorLeveledCompactionWriter`):
`lcs-maxBytesForLevel`, `sstable_size_in_mb-getCandidatesFor`, `sstable_size_in_mb-getnextlevel`,
`lcs-level-capacity-shouldSwitchWriter…` true negative (do not cap); `sstable_size_in_mb-shouldSwitchWriter…`
true positive (caps each file, soft by one partition). §14 lines have no own row in `predicted-negative.md`
(package survey row only), so nothing was removed there. The `lcs-level-capacity` cluster tier missed two
frozen numeric predictions (data volume 605 MiB, not 650 MB); the agent kept "Confirmed" because the
deciding rows held, a stricter reading is "Not confirmed (no matching row)".
Next: row 10 (`CommitLogSegmentManagerCDC.java:345`), rows 1–3 (§14 cache bounds), then CSV order 16 on.

2026-10-25, batch 3 (CSV rows 1, 2, 3, 10, 16: §14 `CaffeineCache`/`SerializingCache`, `CommitLogSegmentManagerCDC.java:345`,
`SplittingSizeTieredCompactionWriter.java:84`): `key_cache_size-create-size`, `row_cache_size-create-serialized_size`
and `cdc_total_space-processNewSegment-sizeInProgress` true positive (cap; row cache and CDC are soft);
`entry-size-limit-serialize-serializedSize` and `DEFAULT_SMALLEST_SSTABLE_BYTES-…` true negative (do not cap).
Four of five estimates differ from the CSV's "negative". Write-ups and stage 4 were run by Agent-tool subagents (the
headless `claude -p --dangerously-skip-permissions` launch was refused by the permission classifier), rows 1–3 on `pc07`,
rows 10 and 16 on `pc12`; leftovers in `~/s4-{kc,rc,es}` (pc07) and `~/s4-{cdc,ss}` (pc12). §14 lines have no own
`predicted-negative.md` row, so nothing was removed. `entry-size-limit` missed three unit and one cluster frozen numeric
bound (kept Confirmed; a strict reading of the cluster one is "Not confirmed (no matching row)"). Upstream bug candidate
(JIRA check first): `SerializingCache.clear()` does not free native memory (seen in two cases). The CDC row 10 question
("check site of `cdc_total_space`?") is answered: yes, the non-blocking branch deletes oldest `cdc_raw` links.
Next: CSV order 7 (decision), 17 on (`NativeCell`, `CompressedInputStream`, `Stack`, tries, hints).

2026-10-25, batch 4 (CSV rows 17–21, §3 `NativeCell` and §6 array-growth lines): all five **true negative**
(do not cap): `nativecell-int-max-size-NativeCell-size`, `chunk_length_in_kb-loadNextChunk-compressedChunk`,
`transform-stack-capacity-splice-newCount`, `BACKTRACK_INITIAL_SIZE-addBacktrack-backtrack`,
`partition-key-max-size-descend-data-length`. Rows 17, 19, 20 on `pc07`, 18 and 21 on `pc12`; leftovers in
`~/s4-{nc,st,bt}` and `~/s4-{ci,pk}`. First batch with **time measured** (raw log:
`stage4-runtime-verification/timing/set-A-batch-4.log`; agents appended `date -u` lines per step).
Stage 3 write-up, 5 in parallel: 0.95–1.8 min each (17:47:56–17:49:44Z), filing by hand ~0.3 min.
Stage 4, 5 in parallel, minutes (wall = first audit line to last report line; `bt` redid the harness as `harness2`):

| Case | audit | harness | unit run | cluster run | self-check | report | wall |
|---|---|---|---|---|---|---|---|
| `transform-stack` (st) | 5.2 | 7.6 | 0.3 | 8.2 | 0.1 | 1.5 | 23.1 |
| `partition-key` (pk) | 3.7 | 8.3 | 0.2 | 8.3 | 0.4 | 2.3 | 24.2 |
| `nativecell` (nc) | 4.6 | 15.9 | 0.8 | 17.1 | 0.5 | 1.6 | 40.7 |
| `chunk_length` (ci) | 4.9 | 17.0 | 0.8 | 24.8 | 0.8 | 1.7 | 50.2 |
| `BACKTRACK` (bt) | 8.5 | 2.4 + 14.0 | 0.9 | 23.5 | 0.2 | 2.0 | 52.2 |

The batch took ~55 min from launch to the last report. Harness and cluster run are ~80% of each case's time; the
unit run, self-check and report steps are under 3 min each. A case that needs a second node or many node
restarts (`nativecell`: 8 restarts; `chunk_length`: 11 runs of ~2.25 min) takes about twice as long as a
single-node one. Findings: write-up errors found by the audit in all five (probe arithmetic, piece counts,
invalid table syntax); `MEMTABLE_TRIE_SIZE_LIMIT` (`cassandra.trie_size_limit_mb`) appears unused (trie threshold is
read from `cassandra.memtable.row_overhead_size`, `InMemoryTrie.java:63`): upstream/doc candidate, JIRA check first.
Next: CSV order 7 (decision), 22 on (`TriePathReconstructor`, `CompressedChecksummedDataInput` and the other §6 lines).

2026-10-25/26, batch 5 (CSV rows 22–26, §6 `TriePathReconstructor` :33/:41 and hints buffers): all five **true negative**
(do not cap): `trie-pathreconstructor-keybytes-growth`, `trie-pathreconstructor-keybytes-addPathBytes-growth`,
`file_cache_size-CompressedChecksummedDataInput-readBuffer-compressedBuffer`, `hints-CompressedChecksummedDataInput-readBuffer-uncompressedSize`,
`hints-CompressedHintsWriter-compressionBuffer-capacity`. Rows 22, 24, 26 on `pc07`, 23 and 25 on `pc12`; leftovers in
`~/s4-{tp33,fc,hw}` (+ `-logs`/`-run`/`-data`) on pc07 and `~/s4-{tp41,hu}` (+ `~/stage4-logs/hu`, `~/stage4-harness-run/hu`) on pc12.
Timing: `stage4-runtime-verification/timing/set-A-batch-5.log`. Write-up, 5 in parallel: 1.5-2.3 min; stage 4, 5 in parallel: ~87 min
launch to last report (the longest batch so far; `hu` and `hw` ~85 min).
Open points for you to overrule: (1) `hw` cluster B3g row 2 sub-prediction was refuted (F1, `max_hints_file_size` 1 MiB closes the
writer after every hint) but the agent kept the cluster tier "Confirmed" (the strict reading is undetermined); (2) `tp33` made a
dated amendment (R9) after unit run 1a and reran the unit tier as 1b; `fc` saw shakedown numbers before the freeze (disclosed in
results §1); `tp41` missed one frozen numeric bound (B3f <0.1%; 0.35%) while B3g held. Write-up errors found by the audits: 8 MiB (not
1 MiB) macro chunk in two hints cases, the 65535 bound applies to the key not the trie path (key + 12), wrong `~` line cites.
Upstream candidates (JIRA first): `ChecksummedDataInput.close()` leaves the pooled/overflow buffer unreturned; unchecked block-header
size in `CompressedChecksummedDataInput`. `predicted-negative.md` §6 rows were left in place (they list sibling lines still open).
Next: CSV order 7 (decision), 27 on (`EncryptedChecksummedDataInput`, `HintsBuffer`, `HintsWriteExecutor`).

2026-10-26, batch 6 (CSV rows 27-37, ten cases; rows 29 and 30 are one line, so one case): **8 true negative, 2 true positive**.
True positive (cap binds): `hints-HintsBuffer-put-slabCapacity` (hint pool = n x max(2 x max_mutation_size, 32 MiB), `MAX_HINT_BUFFERS=1` deadlocks) and
`sasi-max_compaction_flush_memory-PerSSTableIndexWriter-estimatedMemoryUse` (cap binds; real heap ~1.8x the estimate; flush writers ignore the option).
True negative: `hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer`, `max_hints_file_size-HintsWriteExecutor.flushInternal-session.position`
(rows 29+30), `sai-SegmentRowIdOrdinalPairs-add-capacity`, `sasi-max_term_size-{OnDiskIndexBuilder-add,PerSSTableIndexWriter-addTerm,TrieMemIndex-add}-termSize`,
`compressed-sequentialwriter-resetandtruncate-compressedbuffer`, `compression-metadata-writer-addOffset-maxCount`. Write-ups: 10 in parallel, ~2-3.5 min each; filed by hand.
Stage 4 ran in a rolling window of 5 (pc07: hb, od, sr, cm, pw, pm; pc12: mh, cs, tm, ec); a session rate limit (reset 00:20 ET)
stopped the last five agents mid-run and they were resumed with SendMessage; the interruptions are logged in the results files (no frozen reading was lost).
Timing: `stage4-runtime-verification/timing/set-A-batch-6.log`. Leftovers: `~/s4-{hb,od,sr,cm,pw,pm}` (+ logs) on pc07, `~/s4-{mh,cs,tm,ec}` (+ logs) on pc12; no process running.
Open points for you to overrule: `hb` reran its cluster tier with a 10 s hold after the 2 s hold proved too short, and its B3f extract hash changed after a post-run
correction of one audit sentence (results §3); `tp` style frozen-number misses: `ec` S1/F1 (245 KiB, not the predicted size), `pm` amended one prediction (log lines = cuts + 1)
before freeze. Upstream/doc candidates (JIRA first): forged 512 MiB header in the encrypted reader (~537 MB heap + ~537 MB direct); stale 1G text in `IndexMode.java:60/:192`;
scrub raises `AssertionError: Buffer holder has not been acquired` on every run of a corrupted compressed sstable (`cs`, not investigated); a SASI LIKE query on 4095-char indexed
terms returned nothing (`tm`, unexplained). `predicted-negative.md` rows were left in place (siblings still open).
Next: CSV order 7 (decision), 38 on (`Walker`, `AbstractReplicaCollection`, `HistogramBuilder`, and the rest of the §6 lines).

2026-10-26, batch 7 (CSV rows 38-47, ten cases): **7 true negative, 2 true positive, 1 undetermined**. Stage 3 write-ups: 10 in parallel, ~1.5-3 min each; filed by hand
(four stems were chosen by the agents; r40's stem came from the agent's file comment). Stage 4 ran as a rolling window of 5 (pc07: tc, st, mo, mc, sr7; pc12: rl, hv, ie, mr, ck;
tags `s4-b7-<tag>`, port slot per case). Outcome classes: true negative `transition-bytes-collector-add-buffer-length`, `maximum_replication_factor-ReplicaList.add-newSize`,
`repair-session-space-histogram-add-values`, `sasi-compaction-flush-memory-ensurecapacity-tmp`, `initial-buffer-capacity-ensurecapacity-datalengthinbytes`,
`max-cloned-size-allocate-size`, `slab-region-size-region-allocate-capacity`; true positive `memtable-offheap-space-allocate-size` (the pool charge at `:141` caps; `MAX_CLONED_SIZE` is a routing
constant), `cache-keys-to-save-writer-keysToSave` (caps entries written to disk, not memory); **undetermined** `max-region-size-region-allocate-capacity` (unit Confirmed, cluster
"Not confirmed (no matching row)": the charged gauge followed `memtable_offheap_space` but the frozen RssAnon relation failed on noise; the agent's evidence points to true negative).
Timing: `stage4-runtime-verification/timing/set-A-batch-7.log` (wall: first launch 13:31Z, last report 16:03Z; `st` ~2.5 h, the longest). Leftovers: `~/s4-b7-{tc,st,mo,mc,sr7}` (+ `-logs`) on pc07, `~/s4-b7-{rl,hv,ie,mr,ck}` (+ `-logs`) on pc12; no process running.
Open points for you to overrule: (1) `mr` cluster tier undetermined, a rerun with the charged gauge primary and an RssAnon tolerance of at least 40 MiB would likely give true negative; (2) `ie` B3f
JFR-share figure missed at K >= 32 KiB (kept Confirmed); (3) `mc` B1/B2g waste text says 12.3% but readings show 12.6% (the exact region formula held; literal row is "Not confirmed");
(4) `mo` pre-registered RssAnon relations failed for the 1 KiB cluster arms and hold only after subtracting the heap_buffers control (post-hoc); (5) `hv` frozen B3f sentence "2^20 leaves in debug.log" cannot be
checked (the log line is written before `init()`), TN vs FN depends on reading "indirect"; (6) `tc` "never exercised" holds only for the tested workload (repair/streaming not run); `ck` heap peak of `hottest(n)` not isolated.
Many audits found write-up errors (wrong Lucene growth arithmetic, NMT cannot see JNA malloc, guardrails skipped for superusers, `nodetool getcachekeystosave` does not exist, region constants).
Upstream/doc candidates (JIRA first): see `HANDOFF.md` follow-ups (int overflow in `ValidationManager`, mis-named memtable gauges, `setcachekeystosave` doc, `Guardrail.fail` with null state only logs).
`predicted-negative.md`: the three rows for `NativeAllocator:273`, `SlabAllocator:201` and `:144/:92` were removed; multi-line rows (`Walker`, `AbstractReplicaCollection`, `HistogramBuilder`, `ByteSourceInverse`, `AutoSavingCache`, ...) stay (siblings still open). An untracked `stage4-runtime-verification/cassandra.logdir_IS_UNDEFINED/` (two logs, 09:48 Oct 26) is not from this batch and was not committed.
Next: CSV order 7 (decision), 48 on (`AutoSavingCache.java:388`, `DatabaseDescriptor.java:726/:741`, ...).

2026-10-26, batch 8 (CSV rows 48-54, seven cases; row 7 still open): **4 true positive, 3 true negative**. Stage 3 write-ups: 7 in parallel, ~1-2 min each; filed by hand.
True positive: `cache_keys_to_save-saveCache-keysEstimate` (caps entries written to disk, not memory; the "N=100 are the hot keys" clause failed, 0 of 100),
`commitlog-total-space-calculateDefaultSpaceInMiB-minSizeInMiB` (caps, soft: peak 1.7-1.9x the limit unthrottled), `native-transport-max-request-data-in-flight-set...Concurrent...` (unit Confirmed; cluster **Refuted**:
counter holds at L but V5 requests under `LARGE_MESSAGE_THRESHOLD` are copied on heap in full, +246 MiB at every L), `native_transport_max_request_data_in_flight_per_ip-...` (unit Confirmed; cluster
"Not confirmed (no matching row, C7)": `PausedConnections` goes negative on V5). True negative: `data-free-space-warn-threshold`, `local_system_data_file_directory-applySimpleConfig-freeBytes`, `max-unsigned-short-validate-key-remaining`.
Stage 4 ran as 5 + 2 (pc07: kt, cl, fs, then ls, uk; pc12: pi, cr; tags `s4-b8-<tag>`, port slots 1-7). Timing: `stage4-runtime-verification/timing/set-A-batch-8.log` (pi ~2.8 h, cr ~1.9 h, the others 0.3-0.9 h).
Open points for you to overrule: (1) `cr` outcome class filed as true positive (counter caps, V4 and V5-large heap follow L, live setter works); the V5/100 KB arm alone would read false positive;
(2) `pi` C3 needs `PausedConnections` max >= 1, which reads 0 (negative); every other clause held, so Confirmed (C3) is a defensible overrule; (3) `cl` row-4 "soft cap" reading and the flush-lag cause are inferred; the throttled arm (R6) was not run;
(4) `uk` and `kt` saw shakedown numbers before run 1 (disclosed in results); `kt` unit run 1a lacked a lookup control, rerun as 1b; (5) `fs` S-arm node died with SIGBUS on the full tmpfs (attributed to the volume, not the threshold).
Upstream/doc candidates (JIRA first): `Client.PausedConnections` negative on V5; V5 sub-large requests buffered on heap while the in-flight counter sits at L; `getCDCTotalSpace()` returns bytes but `getTotalCommitlogSpaceInMiB()` MiB;
`QueryProcessor.java:255` "Key may not be unset" is dead code; `nodetool tablestats` memtable data size omits partition-key bytes; log line "Completed loading (n keys)" prints the key cache size for every cache type (`AutoSavingCache.java:189-192`).
`predicted-negative.md`: rows `DatabaseDescriptor.java:3369/:3386` and `:1152` removed; `:726/:741` (§2) and `QueryProcessor.java:259` (§3) sit in multi-line rows whose siblings are open, so they stay. `AutoSavingCache.java:388` is a §14 survey line (no own row).
Leftovers: `~/s4-b8-{kt,cl,fs,ls,uk}` (+ `-logs`, `-u`/`-n`/work dirs) on pc07; `~/s4-b8-{pi,cr}` (+ logs, harness, node dirs) on pc12; no process running.
Next: CSV order 7 (decision), 55 on (`QueryProcessor.java:758`, `Validation.java:51`, `BatchStatement.java:340/:388`, ...).

2026-10-26/27, batch 9 (CSV rows 55-61, seven cases; row 7 still open): **6 true negative, 1 true positive**. Stage 3 write-ups: 7 in parallel, ~1-1.6 min each; filed by hand (stems from the agents; the stem comment was requested in the prompt).
True negative: `max-unsigned-short-prepare-boundTerms`, `max-unsigned-short-validateKey-keyRemaining`, `max-unsigned-short-ClusteringPrefix-validate-accessor-size`, `max-unsigned-short-validate-sum`,
`batch_size_warn_threshold-verifyBatchSize-size` (unit **Refuted**, cluster **Not confirmed** on an allocation clause only: the warn branch adds +14-20% coordinator allocation; rows, writes and disk bytes identical),
`unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet`. True positive: `rows_per_partition-isFilterFullyCoveredBy-rowsPerPartitionToCache` (soft cap: live rows only).
Stage 4 ran as 5 + 2 (pc07: bs, rp, bt, then cp; pc12: bu, vk, then cs; tags `s4-b9-<tag>`, port slots 1-7). Timing: `stage4-runtime-verification/timing/set-A-batch-9.log` (rp ~57 min, bs ~29 min, cp ~24 min).
Findings for Target 3 / upstream (JIRA first): (1) warn threshold above fail threshold disables the batch fail check (`BatchStatement.java:338-352`; seen by `bs` and `bu`); (2) `INSERT ... IF NOT EXISTS` with a 65536-byte clustering skips `validate()` (`ModificationStatement.java:573`), fails at `NativeClustering.java:50` and the client sees a WriteTimeout;
(3) a range delete with a 70000-byte clustering bound is accepted and the later flush throws in `StatsMetadata` serialization (`cp`, `cs`; node stayed up, restart/replay not tested); (4) through CQL `Validation.java:51` never rejects, `ClusteringPrefix.validate` rejects first (`vk`), so `QueryProcessor.java:259` (`max-unsigned-short-validate-key-remaining`, batch 8) likely has the same attribution;
(5) a prepared SELECT kept the old `rows_per_partition` after `ALTER TABLE` plus a restart (`rp`); (6) `verifyBatchSize` formats a table name per mutation; (7) the unlogged-batch WARN log line is limited to one per minute.
Open points for you to overrule: (1) `bs` verdict wording (Refuted/Not confirmed vs both Confirmed if the claim is read as "does not cap"); (2) `vk` missed one frozen number (Data+Index ratio 14.3, predicted 8-12, a compaction was running);
(3) `cp` and `cs` missed side-bounds on Index.db (3.005x, the key is stored twice) and `cs`'s ordering of two arms, neither in a B3g row; (4) `rp` RssAnon rose 0.3-0.7 GB in arms with a small cache (cause not isolated, kept out of the verdict) and two harness changes after shakedowns (unprepared reads, warm-up);
(5) `bt` per-entry weight in the cluster tier was up to 3% below the unit weight, self-check widened to a 5% band after the strict form failed; (6) `bu` restarted its cluster tier once (count(*) read timeout) and wrote one non-standard line to the timing log; `cs` reran its cluster tier after logback rolled `system.log` at 00:00 UTC;
(7) shakedowns showed similar numbers before run 1 in `uk`-style cases (`vk`, `cp`, `rp`), disclosed in the results files.
`predicted-negative.md`: row `BatchStatement.java:340/:388` removed; the §3 row (`QueryProcessor.java:259/:758`, `Validation.java:51`, `ClusteringPrefix.java:278/:284`, `CassandraIndex.java:618`) and the §5 row (`ColumnFamilyStore.java:1931` / `isFilterFullyCoveredBy`) stay because `CassandraIndex.java:618` and CSV row 62 are still open.
Leftovers: `~/s4-b9-{bs,rp,bt,cp}` (+ `-logs`, `-n`, `-drv`) on pc07; `~/s4-b9-{bu,vk,cs}` (+ `-logs`, `-unit`, `-node`) on pc12; no process running.
Next: CSV order 7 (decision), 62 on (`ColumnFamilyStore.java:1931`, ...).

2026-10-27, batch 10 (CSV rows 63-70, eight cases; row 62 is the same line as row 61's helper case and is recorded as covered by `rows_per_partition-isFilterFullyCoveredBy-rowsPerPartitionToCache`; row 7 still open):
**1 undetermined, 1 false negative, 6 true negative**. Stage 3 write-ups: 8 in parallel, ~1-1.5 min each; filed by hand.
Undetermined: `tombstone-failure-threshold-withMetricsRecording-failureThreshold` (estimate positive; unit Confirmed, caps per read; cluster "Not confirmed (partial)": per-read allocation follows T, node heap peak saturates under 8 clients; same outcome as its twin `tombstone_failure_threshold-countTombstone-tombstones`).
False negative: `max-compaction-threshold-getCandidatesFor-candidatesSize` (unit and cluster Confirmed, "caps only on some paths (bypass)": L0 part capped at N, but every overlapping L1 sstable is added to the task; run 1 cluster was "Not confirmed (no matching row)" on a heap clause, run 2 re-used the same fixtures with a live-heap measure and matched; same session, not independent).
True negative: `commitlog-segment-size-addAdditionalInformationIfPossible-segmentSize` (cluster Confirmed on the three LZ4 arms only; the three default mmap arms died of SIGBUS before any log line), `tombstone-threshold-worthDroppingTombstones-droppableRatio`,
`max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount`, `max-threshold-getEstimatedTasks-l0SstableCount`, `compaction-min-threshold-mostInterestingBucket-minThreshold`, `bucket-low-bucket-high-getBuckets-oldAverageSize`.
Stage 4 ran as 5 + 3 (pc07: tf, sg, td, then lm, sb; pc12: lz, lc, then sm; tags `s4-b10-<tag>`, port slots 1-8). Timing: `stage4-runtime-verification/timing/set-A-batch-10.log` (tf ~3.6 h, lm ~2 h, lc ~1.7 h, the others 0.5-1 h).
Open points for you to overrule: (1) `lc` effect "bypass" vs "does not cap" (the 1.4 GiB L1 offset, unbounded L0 sstable size; the readings are the same); (2) `td` effect "does not cap" although an sstable above the threshold is rewritten when all gates are open, and its P2 correction (A8) follows from the source, not a measurement;
(3) `lm` phase B: in-flight STCS-in-L0 output grew with `max_threshold` (54/94/172 MB), a different path from line 655, recorded under C6 and not counted; (4) `sg` Z8 control reached 104 MiB against its pre-fixed 72 MiB bound (the cap is a reclaim target; the frozen sentence is literally false in both Z arms) and two arms (A5L, ZH) were added after reading earlier arms;
(5) `lz` Confirmed rests on the unit routes (1 of 7 debug lines came during the write window); (6) `sb` default arm ended with 3 sstables, not the predicted 2 (no B3g row depends on it); (7) `sm` memory shown only by per-sstable counters, RssAnon and live heap flat; (8) `tf` all B3f numeric bands missed (a tombstone is 11.7 B, not 100 B).
Upstream/doc candidates (JIRA first): the commit-log free-space message prints total capacity as "bytes available" (`CommitLog.java:570-573`, `getTotalSpace`); default mmap commit log on a full volume dies with SIGBUS instead of `commit_failure_policy`; `ReadCommand.java:639` uses `<` so a read finishing with exactly T tombstones logs the warning but does not count `tombstoneWarnings`;
`LeveledManifest.java:516-524` comment says at most `max_threshold` L0 sstables per task but the task also takes all overlapping L1 sstables; STCS-in-L0 trigger (`:306`) uses a hard-coded 32 while the estimate (`:655`) uses `max_threshold`; `validateOptions` for `tombstone_threshold` says "greater than 0" but accepts 0 and silently disables above 1.
`predicted-negative.md`: no row removed; the §2 row `ReadCommand.java:639; DatabaseDescriptor.java:726, :741; CommitLog.java:609; SimpleSeedProvider.java:110` has one open sibling (`SimpleSeedProvider.java:110`), and the `db/compaction/` survey rows are package surveys.
Leftovers: `~/s4-b10-{tf,sg,td,lm,sb}` (+ logs, `-u`/`-n`/`-src` trees) on pc07; `~/s4-b10-{lz,lc,sm}` (+ logs, `-unit`, `-node`) on pc12; no process running.
Next: CSV order 7 (decision), 71 on.

2026-10-27, batch 11 (CSV rows 71-80, ten cases; row 7 still open): **7 true negative, 2 true positive, 1 undetermined**. Stage 3 write-ups: 10 in parallel, ~1-2 min each; filed by hand (stems from the agents' file comments).
True positive: `rows-per-partition-hasEnoughLiveData-rowLimit` (estimate positive: the `rows_per_partition`/`row_cache_size` caps hold, `DataLimits.java:417` itself moves no memory), `group-by-row-limit-incrementRowCount-rowsCounted` (GROUP BY page size is the internal row limit; a row-count cap, 4 KiB rows at fetch 100000 killed a 512 MB node).
Undetermined: `group-per-partition-limit-isdoneforpartition-groupinCurrentPartition` (unit Confirmed, does not cap; cluster "Not confirmed (no matching row)": peak heap 54.9 MB at N=absent vs 8.4 MB at N=1 against a 30 MB rule chosen at the audit; heap floor drifted 0 to 40 MB during the arm, so a drift-corrected rerun would likely give true negative).
True negative: `min-threshold-getEstimatedCompactionsByTasks-bucketSize`, `group-limit-isdone-groupcounted`, `cql-row-limit-hasEnoughLiveData-rowLimit`, `cql-row-limit-incrementRowCount-rowsCounted`, `per-partition-limit-incrementRowCount-rowsincurrentpartition`, `group-by-limit-incrementGroupCount-groupLimit`, `group-per-partition-limit-incrementGroupInCurrentPartitionCount-groupPerPartitionLimit`.
Stage 4 ran as a rolling window of 5 (pc07: m71, g72, g73, then q77, b78; pc12: c74, p75, then c76, l79, g80; tags `s4-b11-<tag>`, port slots 1-10). Timing: `stage4-runtime-verification/timing/set-A-batch-11.log` (launch 06:29Z, last report 08:48Z).
Open points for you to overrule: (1) `m71` live-heap tolerance 5% missed at 5.4% (arm order not randomized), kept Confirmed; (2) `b78` +314 MB at fetch 10000 is 4.8% above the filed band, and the 100-byte-row control read +112-128 MB against a 100 MB analyzer threshold; (3) `g73` verdict follows the frozen 30 MB rule, the drift reading would give Confirmed; (4) `g72` read B3g "heap above 90%" as live heap after GC (G1 ran 64-67 full GCs per 5 queries at P=100); (5) `c74` discarded its first unit pass after a harness bug (disclosed in results §3) and the attributable-RSS tolerance margin was 62.3 vs 64 MiB; (6) `q77` added `-XX:-UseTLAB` and restarted the unit tier after seeing attempt 1; (7) `p75` RssAnon bound missed for n5 and n50 (recorded as reported overshoot, Size decides); runtime shrink via `setcachecapacity` left Size unchanged for 60 s (informational, not retested); (8) `l79` peak-heap comparison for the small-group table rests on three cells; sizes scaled down; (9) `c76` one B3f control sub-prediction missed (`local_read_size_fail_threshold` counts row heap, not payload).
Findings / upstream or doc candidates (JIRA first): `LIMIT` and `PER PARTITION LIMIT` on a GROUP BY bound groups/rows, not bytes scanned; under `GROUP BY <partition key>` `PER PARTITION LIMIT` never stops reading a partition (`groupInCurrentPartition` stays 0); for GROUP BY the page size is the internal row limit (`SelectStatement.java:899-912`); `aggregation_subpage_size_in_kb` does not exist in 5.0.9; `min_threshold` cannot exceed `max_threshold` (setter rejects it); `PendingCompactions` is stale while autocompaction is disabled; `row_cache_size` is split per OHC segment so an entry above a segment is not stored; node killed by `cassandra-env.sh` `kill -9` on OOM leaves no log line.
`predicted-negative.md`: the `DataLimits.java:414/:417` row and the `:509/:511/:986` row were removed; the `:993/:1000/:1041` row stays (`:1041` is open), as do the `AtomicBTreePartition` rows.
Leftovers: `~/s4-b11-{m71,g72,g73,q77,b78}*` on pc07; `~/s4-b11-{c74,p75,c76,l79,g80}*` on pc12; no process running.
Next: CSV order 7 (decision), 81 on (`DataLimits.java:1041`, `AtomicBTreePartition`, ...).

## Trace-back only (set A rows 81-159)

2026-10-27. Jingsong asked for the "trace back" step alone for every set A target that still had no
case file (CSV rows 81-159; row 7 skipped, it is settled as a second check site of
`prepared_statements_cache_size`). **Not case files:** these are unfinished, kept out of `cases/`,
`_INDEX.md`, `predicted-negative.md` and the CSV (`case_file` and `stage4` columns left empty).

- **Where:** `cassandra/if-check-exp/stage3-ai-deep-read/traceback-only/<stem>--autonomous.md`, 79 files (one per target). Each has the template's
  field table (only Entry pointer and Pinned source) and **A1. The constraint** filled; A2-A5, B, C and D are absent.
- **How:** one fresh Agent-tool subagent per target, 8 batches (10 x 7, then 9), each given only
  `file:line` (or helper), a read-only copy of the source (`~/cassandra-5.0.9`) and the A1 definition.
  Agents wrote A1 to a scratch file; the stem and file were filed by hand. Stems follow
  `<constraint>-<method>-<operand>` (lowercased by the filing script; `-2` added when taken).
- **Checked by hand:** the enclosing method in stems (`applySimpleConfig` for the `DatabaseDescriptor` rows),
  and line numbers the agents flagged as unverified (rows 125, 134, 137, 159; fixed where off by one).
  Other citations were not re-checked.
- **Result:** 69 targets trace to a constraint, 10 are marked "no constraint" (bookkeeping or a format check).
  Many traced constraints are hard-coded constants or format limits, not memory or disk caps: the A1 text says so; no
  estimate was recorded.
- **Duplicates by constraint:** rows 82/83/84/139 (`EXCESS_WASTE_BYTES`, rows 82 and 84 are the same check), 100/101 (`min_compress_ratio`), 115/116
  (`repair_session_space`), 134/135 (`sstable_size_in_mb`), 143/144 (`InMemoryTrie` soft/hard limit), 145/154/155 (`max_top_k`), 127/128/130/131/132 (`counter_cache_size`/`row_cache_size`).
  These can share one design when written up.
- **Rule (2026-10-27):** for trace-back-only work, `traceback-only/_INDEX.md` records only the cases whose constraint type is **not** a yaml entry or a JVM (`-D`) property. Yaml and JVM-property cases still get their file in the folder but no index row.
- **Index:** `traceback-only/_INDEX.md` (constraint, constraint type, case file) lists the 48 cases whose type is not a yaml entry or JVM property (32 hard-coded constants, 6 per-table/per-index options, 10 with no constraint); the other 31 are not listed.
- **Next:** turn rows into full cases (A2-A5, B, estimate), or decide per row that a line is not a case.

| Row | Target | File stem |
|---|---|---|
| 81 | `db/filter/DataLimits.java:1041` | `default_page_size-cqlgroupbylimits_onclose-rowlimit` |
| 82 | `helper db.partitions.AtomicBTreePartition.updateWastedAllocationTracker()` | `excess_waste_bytes-updatewastedallocationtracker-wastedbytes` |
| 83 | `helper db.partitions.AtomicBTreePartition.useLock()` | `excess_waste_bytes-uselock-wastetracker` |
| 84 | `db/partitions/AtomicBTreePartition.java:272` | `excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2` |
| 85 | `db/virtual/LogMessagesTable.java:193` | `cassandra.virtual.logs.max.rows-boundedlinkedlist.add-maxsize` |
| 86 | `diag/store/DiagnosticEventMemoryStore.java:56` | `diagnostic_event_memory_store_max_size-store-keyhead` |
| 87 | `hints/ChecksummedDataInput.java:161` | `none-checklimit-length` (no constraint) |
| 88 | `hints/HintsWriter.java:205` | `hints_write_buffer_size-append-hint_remaining` |
| 89 | `hints/HintsWriter.java:214` | `write_buffer_size-append-hint` |
| 90 | `index/internal/CassandraIndex.java:618` | `max_unsigned_short-validateindexedvalue-value_remaining` |
| 91 | `index/sai/disk/v1/bbtree/BlockBalancedTreeWriter.java:528` | `max_points_in_leaf_node-add-leafvaluecount` |
| 92 | `index/sai/disk/v1/bbtree/BlockBalancedTreeWriter.java:651` | `max_array_length-checkmaxleafnodecount-numleaves` |
| 93 | `index/sai/disk/v1/bitpack/AbstractBlockPackedWriter.java:62` | `block_size-add-blockindex` |
| 94 | `index/sai/disk/v1/postings/PostingsWriter.java:222` | `block_size-writeposting-blocksize` |
| 95 | `index/sasi/disk/AbstractTokenTreeBuilder.java:297` | `max_offset-createentry-offset` |
| 96 | `index/sasi/disk/AbstractTokenTreeBuilder.java:323` | `overflow_trailer_capacity-createoverflowentry-overflowcollisions` |
| 97 | `index/sasi/disk/AbstractTokenTreeBuilder.java:520` | `tokens_per_block-add-pos` |
| 98 | `index/sasi/disk/OnDiskIndexBuilder.java:497` | `super_block_size-flushsuperblock-datablockscnt` |
| 99 | `index/sasi/disk/OnDiskIndexBuilder.java:598` | `max_keys_sparse-addinternal-keys` |
| 100 | `io/compress/CompressedSequentialWriter.java:160` | `min_compress_ratio-flushdata-maxcompressedlength` |
| 101 | `io/compress/CompressedSequentialWriter.java:163` | `min_compress_ratio-flushdata-maxcompressedlength-2` |
| 102 | `io/util/SafeMemoryWriter.java:52` | `dob_doubling_threshold_mb-resizeto-newcapacity` |
| 103 | `locator/SimpleSeedProvider.java:110` | `seed_count_warn_threshold-getseeds-seeds_size` |
| 104 | `net/BufferPoolAllocator.java:121` | `networking_cache_size-capacity-newcapacity` |
| 105 | `utils/logging/VirtualTableAppender.java:125` | `logs_virtual_table_default_rows-addtobuffer-messagebuffer_size` |
| 106 | `utils/memory/NativeAllocator.java:166` | `max_region_size-tryswapregion-minsize` |
| 107 | `cache/NopCacheProvider.java:39` | `row_cache_size-setcapacity-capacity` |
| 108 | `config/DatabaseDescriptor.java:911` | `native_transport_max_request_data_in_flight-applysimpleconfig-maxcqlmessagesize` |
| 109 | `config/DatabaseDescriptor.java:914` | `native_transport_max_request_data_in_flight_per_ip-applysimpleconfig-maxcqlmessagesize` |
| 110 | `config/DatabaseDescriptor.java:978` | `internode_application_receive_queue_reserve_endpoint_capacity-applysimpleconfig-maxmessagesize` |
| 111 | `config/DatabaseDescriptor.java:981` | `internode_application_receive_queue_reserve_global_capacity-applysimpleconfig-maxmessagesize` |
| 112 | `config/DatabaseDescriptor.java:984` | `internode_application_send_queue_reserve_endpoint_capacity-applysimpleconfig-maxmessagesize` |
| 113 | `config/DatabaseDescriptor.java:987` | `internode_application_send_queue_reserve_global_capacity-applysimpleconfig-maxmessagesize` |
| 114 | `config/DatabaseDescriptor.java:1016` | `max_space_usable_for_compactions_in_percentage-applysimpleconfig-max_space_usable_for_compactions_in_percentage` |
| 115 | `config/DatabaseDescriptor.java:4093` | `repair_session_space-setrepairsessionspaceinmib-sizeinmib` |
| 116 | `config/DatabaseDescriptor.java:4096` | `repair_session_space-setrepairsessionspaceinmib-sizeinmib-2` |
| 117 | `config/DatabaseDescriptor.java:5347` | `repair_disk_headroom_reject_ratio-setrepairdiskheadroomrejectratio-value` |
| 118 | `config/GuardrailsOptions.java:1219` | `guardrail_size_fail_threshold-validatewarnlowerthanfail-fail` |
| 119 | `config/GuardrailsOptions.java:1257` | `data_disk_usage_max_disk_size-validatedatadiskusagemaxdisksize-maxdisksize` |
| 120 | `config/StorageAttachedIndexOptions.java:41` | `sai_options.segment_write_buffer_size-validate-segment_write_buffer_size` |
| 121 | `cql3/QueryProcessor.java:251` | `max_unsigned_short-validatekey-key.remaining` |
| 122 | `cql3/Validation.java:47` | `none-validatekey-key_remaining` (no constraint) |
| 123 | `cql3/functions/UDFDataType.java:177` | `none-compose-buffer_remaining` (no constraint) |
| 124 | `cql3/functions/types/CodecUtils.java:101` | `native_protocol_v1_v2_collection_size_limit-writesize-size` |
| 125 | `cql3/functions/types/CodecUtils.java:250` | `native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize` |
| 126 | `cql3/statements/schema/CreateIndexStatement.java:213` | `name_length-validatecustomindexcolumnname-name` |
| 127 | `helper db.ColumnFamilyStore.isCounterCacheEnabled()` | `counter_cache_size-iscountercacheenabled-capacity` |
| 128 | `helper db.ColumnFamilyStore.isRowCacheEnabled()` | `row_cache_size-isrowcacheenabled-capacity` |
| 129 | `db/ColumnFamilyStore.java:2185` | `filename_length-validatesnapshotname-snapshotname` |
| 130 | `db/ColumnFamilyStore.java:2501` | `counter_cache_size-getcachedcounter-capacity` |
| 131 | `db/ColumnFamilyStore.java:2508` | `counter_cache_size-putcachedcounter-capacity` |
| 132 | `db/CounterMutation.java:213` | `counter_cache_size-processmodifications-countercache_getcapacity` |
| 133 | `db/RangeTombstoneList.java:213` | `none-addall-size` (no constraint) |
| 134 | `db/compaction/LeveledCompactionStrategy.java:78` | `sstable_size_in_mb-leveledcompactionstrategy-configuredmaxsstablesize` |
| 135 | `db/compaction/LeveledCompactionStrategy.java:81` | `sstable_size_in_mb-leveledcompactionstrategy-configuredmaxsstablesize-2` |
| 136 | `db/compaction/unified/Controller.java:305` | `max_shard_split-getnumshards-count` |
| 137 | `db/compaction/unified/Controller.java:613` | `min_sstable_size-validateoptions-sizeinbytes` |
| 138 | `db/monitoring/MonitoringTask.java:221` | `cassandra.monitoring_max_operations-offer-maxoperations` |
| 139 | `db/partitions/AtomicBTreePartition.java:283` | `excess_waste_offset-updatewastedallocationtracker-delta` |
| 140 | `db/partitions/AtomicBTreePartition.java:300` | `no_constraint-avoidreservedvalues-wastetracker` (no constraint) |
| 141 | `db/rows/ThrottledUnfilteredIterator.java:234` | `repair_mutation_repair_rows_per_batch-throttle-maxbatchsize` |
| 142 | `db/tries/InMemoryTrie.java:64` | `cassandra_memtable_row_overhead_size-static_initializer-limitinmb` |
| 143 | `db/tries/InMemoryTrie.java:145` | `trie_size_threshold-allocateblock-allocatedpos` |
| 144 | `db/tries/InMemoryTrie.java:148` | `trie_2gb_hard_limit-allocateblock-leadbit` |
| 145 | `index/sai/StorageAttachedIndex.java:503` | `sai_vector_search_max_top_k-validate-command.limits.count` |
| 146 | `index/sai/StorageAttachedIndex.java:791` | `sai_term_size_guardrail-validatetermsizeforcell-cellbuffer_remaining` |
| 147 | `index/sai/disk/v1/SAICodecUtils.java:129` | `block_packed_max_block_size-checkblocksize-blocksize` |
| 148 | `index/sai/disk/v1/SSTableIndexWriter.java:221` | `none-addterm-term_remaining` (no constraint) |
| 149 | `index/sai/disk/v1/segment/SegmentBuilder.java:260` | `last_valid_segment_row_id-exceedssegmentlimit-sstablerowid` |
| 150 | `helper index.sai.disk.v1.segment.VectorIndexSegmentSearcher.shouldUseBruteForce()` | `no_constraint-shouldusebruteforce-numrows` (no constraint) |
| 151 | `index/sai/disk/v1/vector/RandomAccessReaderAdapter.java:69` | `none-readfully-dest_length` (no constraint) |
| 152 | `index/sai/disk/v1/vector/RandomAccessReaderAdapter.java:117` | `none-read-count` (no constraint) |
| 153 | `index/sai/memory/TrieMemoryIndex.java:228` | `max_recursive_key_length-addterm-term` |
| 154 | `index/sai/memory/VectorMemoryIndex.java:190` | `sai_vector_search_max_top_k-orderby-resultkeys` |
| 155 | `index/sai/memory/VectorMemoryIndex.java:229` | `sai_vector_search_max_top_k-orderresultsby-resultsinrange_size` |
| 156 | `index/sasi/conf/IndexMode.java:190` | `max_compaction_flush_memory_in_mb-getmode-maxmembytes` |
| 157 | `schema/KeyspaceMetadata.java:68` | `schemaconstants_name_length-validatekeyspacename-keyspacename` |
| 158 | `schema/TableMetadata.java:517` | `table_name_length-validatetablename-name_length` |
| 159 | `utils/memory/NativeAllocator.java:194` | `none-allocateoversize-peer` (no constraint) |
