# batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous — stage-4 results  <!-- file: results/batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous.md -->

> **Case:** [`batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous`](../../stage3-ai-deep-read/cases/batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous.md)
>
> **Status:** verdict filed, 2026-10-26. **Unit: Confirmed. Cluster: Confirmed. The count cap (≤ 128 decoded batches per page) caps; the 4 MiB byte target caps only on some paths (bypass).**
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous/`](../harness/batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous/).
>
> **Agent:** autonomous. In this file, "§9a" means each tier's predictions and conclusions table: B2f and B2g for the unit tier, B3f and B3g for the cluster tier. "§9b–§9e" means B2a–B2e or B3a–B3e. The case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-26, on the advisor's machine (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | **Filed:** sha256 `c2d2f659…8223`. **After the step-0 audit's fifteen amendments (2026-10-26), frozen:** `d04e9c87881db9f6f83d3e8260fdedf9a1c9276567b8feebfe79a71f96f6d056`. **Unit attempt 0 hit runbook defect 1.** Its dated fix to B2c, plus a correction of the A3 amendment's item (iv), gave `e39a7514e20dbee8362b659ac760fd78736b17bc49d602090583f4fc05c72ea3`. The unit tier's run 1 ran at this version. **The cluster shakedown hit defects 2 and 3.** Their dated fixes to B3c and B3a gave `70b0f972520bb8cc0e04b97f3c9fa204ce837e57484c1251d0f32fb3b9d22226`. The cluster tier's run 1 ran at this version. No prediction, band or row changed after the first freeze. All four hashes are rows in `_INDEX.md` §4. Nothing is committed (no commit was asked for). |
| **Harness** | [`../harness/batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous/`](../harness/batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous/) (not committed). Unit: `BatchlogPageBudgetTest.java` (BMUnit: two Byteman rules, `finishAndClearBatches` AT ENTRY and `calculatePageSize` AT EXIT) and `unit-run.sh`. Cluster: `make-node-conf.sh`, `bl.btm` (the four rules of B3a), `big.yaml`, `small.yaml` and `cluster-run.sh`. Instrument checks: (i) the test compiled in the run clone at the audit (`audit-compile.log`); (ii) `bl.btm` type-checks with Byteman's `TestScript` (`run1/cluster/btm-check.txt`), and the cluster script now runs this check before any start (added for defect 3); (iii) cluster shakedowns `shake 40 40 A B C` ([`shakedown/`](batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous/shakedown/)). Attempt 0 found defect 2, and attempt 1 found defect 3. Attempt 2 ran every step and showed each frozen observable measurable: governing `BLPAGESIZE` = derived from the tablestats mean, `BLPAGE` lines, `ReplayingBatch` counts in the histograms, and baseline drift ≤ 0.2 MB. The shakedown readings are not used. |
| **Tiers and values** | **Unit (B2):** effective page size 128 / 57 / 128 / 3 in cases A–D (64 KiB batches memtable-only; the same flushed; a 500-tiny-batch SSTable plus 260 unflushed large batches; 1 MiB batches flushed), three runs. **Cluster (B3):** one node with 4 GiB heap; 256 LOGGED batches of 2 × 512 KiB per case; A memtable-only, B flushed, C a 2,000-tiny-batch SSTable plus 256 large unflushed batches; a fresh node for each case. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

### 1.1 Design audit

Citations were re-read in `~/cassandra-src` at `cassandra-5.0.9` (`b5f2a54210`), the commit of the run clone.

**Why the arms answer "does it cap usage?" (B1 amendment).** The constant cannot be set: there is no yaml key, `-D` property or JMX setter. The only inputs to `calculatePageSize` are whether `system.batches` has SSTables and how big its rows are. The arms vary exactly these inputs while the batches to be replayed stay the same:
- A vs B: flushed or not.
- B vs D (unit): row size.
- C: statistics from other batches.

This turns the knob into a dose-response on the effective page size: 128 / 57 / 3 in the unit tier and 128 / 3 on the node. Every arm replays at least two pages. The results are kept as two findings: **(1) count cap** (≤ `pageSize` ≤ 128 decoded batches held; replay heap follows `pageSize`) and **(2) the 4 MiB byte target**.

**Derived from the source (A3 amendment):**
- **When replay runs.** `start()` from `StorageService:1238` schedules a pass after `RING_DELAY` (30 s) and then every 10 s. `forceBatchlogReplay` and `nodetool replaybatchlog` queue on the same single-thread executor.
- **Which batches are due.** Batches older than 2 × `write_request_timeout` = 4 s, in time order: `system.batches` uses `LocalPartitioner(TimeUUIDType)`.
- **The cursor persists.** `lastReplayedUuid` survives between passes in one JVM, so the unit tier resets it.
- **Deletion.** Replayed batches are deleted only at the end of a pass.
- **`getMeanPartitionSize()`.** It returns 0 without SSTables (memtable never counted). Otherwise it returns the upper bucket offset of the partition-size histogram, which gives exact page sizes of 57 (64 KiB rows, mean 73,457) and 3 (1 MiB rows, mean 1,131,752).
- **The B3 Byteman rules leave the replay path unmodified.** Rule 1 only stops the coordinator's `asyncRemoveFromBatchlog`; replay deletes through `BatchlogManager.remove`. Rule 2 changes `getBatchlogTimeout()` only until the flag file exists.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2/B1: a count of decoded batches, each with a byte size, plus a 4 MiB byte target; both are named. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly → Met after amendment | Not settable; flush state and batch size vary the effective page size. The reason was added (B1 amendment). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Unit: `replayedBytes` proxy (a lower bound, one copy; gap named in B2d). Cluster: live heap from the class histogram (replacing jmap/heap_info), with a drift control. |
| A. Core question | usage driven to the limit and past it | Partly → Met after amendment | Unit N ≥ 2 pages. Cluster: the filed `n=256` gave 128 batches plus a warm-up (stress counts partitions), so it was raised to `n=512 no-warmup`. |
| B. Logic | each step says what it establishes | Met | B2g/B3g rows, B2h/B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | Exact page sizes, page counts, maxBytes bands, delta bands and drift tolerance (B2f, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | Rows added and split by finding (B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The `:296` boundary is observed directly (list size at `finishAndClearBatches`, `BLPAGE` traces). |
| B. Logic | alternative explanations and their controls | Met | B vs A positive control; offheap memtables; one node (no hints or remote sends); hold-rule check (no `BLPAGE` before `go`). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | The unit cursor reset, output location and the governing `BLPAGESIZE` rule were open. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | B3a had a top-level `seeds:` key the yaml loader rejects; stress counts. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Mapped to this host (B2a, B3a). |
| D. Runnable | workload arithmetic reaches the limit | Met after amendment | ≈ 256 MiB of batches per case on a 4 GiB heap; ≈ 1 s per batch at the default throttle. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Partly | `BatchlogManager.java:90-118, :183-335, :340-540`; `ColumnFamilyStore.java:3123-3134`; `EstimatedHistogram.java:91-108, :235-258`; `SystemKeyspace.java:211-221`; `StorageProxy.java:1173-1320`; `ReplicaPlans.java:235-268`; stress `PartitionOperation`, `WorkManager`, `StressAction`, `SchemaInsert`. The A3 amendment's item (iv) (read thresholds do not apply) was wrong, found by unit attempt 0 and corrected (defect 1). The filed Byteman rule 2 did not parse, found by the shakedown (defect 3). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | A3: replay scheduling and forcing, due condition, cursor, mean-partition-size arithmetic, read thresholds, retention, Byteman rule scope | Amendment 2026-10-26 | Asked by the audit; exact predictions |
| 2 | B1: why the arms answer the core question; two findings | Amendment 2026-10-26 | README; caller |
| 3 | B2a: this host | Amendment 2026-10-26 | CloudLab path |
| 4 | B2c: blob column type, ids, `lastReplayedUuid` reset | Amendment 2026-10-26 | Cursor survives passes in one JVM |
| 5 | B2d: test-log output; `replayPs` rule | Amendment 2026-10-26 | Output location; page size inside the pass |
| 6 | B2e: `unit-run.sh` r1–r3 | Amendment 2026-10-26 | Procedure |
| 7 | B2f: exact values | Amendment 2026-10-26 | Group B |
| 8 | B2g: rows by finding | Amendment 2026-10-26 | Group B; caller |
| 9 | B3a: this host; drop `seeds:`; scoped agent; timestamped traces | Amendment 2026-10-26 | CloudLab paths; invalid key |
| 10 | B3c: `n=512 no-warmup` / `n=4000` | Amendment 2026-10-26 | Stress counts partitions and warms up |
| 11 | B3d: class histogram; governing `BLPAGESIZE` from the text after `go`; tablestats mean | Amendment 2026-10-26 | Live heap on this JDK; scheduled passes print too |
| 12 | B3e: procedure as run; shakedown | Amendment 2026-10-26 | Open order, drift control |
| 13 | B3f: exact values, baseline median, drift ≤ 10 MiB | Amendment 2026-10-26 | Group B |
| 14 | B3g: rows by finding | Amendment 2026-10-26 | Group B; caller |
| 15 | B4: this host's cleanup | Amendment 2026-10-26 | CloudLab paths |
| 16 | Measure the decoded heap per batch directly (the node held ≈ 3 MiB of live heap per 1 MiB batch, §4.2) | Left for stage 3 | Not needed for the frozen bands |
| 17 | Cover a node with `read_thresholds_enabled: true` (replay fails at a page over the coordinator fail threshold, defect 1) | Left for stage 3 (section D) | Outside this file's claim |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26. Audit and unit attempt 0 at 02:15–02:18; unit run 1 (r1–r3) at 02:20–02:23; shakedown attempts at 02:24, 02:26–02:31 and 08:50–09:01 (the laptop slept during attempt 2, case B; not judged); cluster run 1 at 09:45:32–10:03:20 EDT, under `caffeinate -ims`, with no sleep or wake event between start and end (`pmset` log: last wake 09:44:14). |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM; internal SSD (APFS), 135 GiB free; loopback 127.0.0.1, .2, .3 on `lo0` (only .1 used); ports 7000, 7199, 9042, 9091 free; no `CassandraDaemon` before ([`run1/stepE.txt`](batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous/run1/stepE.txt)) |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit: the junit fork of `ant testsome`. Node: `MAX_HEAP_SIZE=4G` (`-Xms4G -Xmx4G`, G1; `HEAP_NEWSIZE` is ignored with G1, as `cassandra-env.sh` notes), Byteman 4.0.20 agent with `listener:true` |
| Ant | 1.10.18 |
| Local `cassandra-src` clone commit | `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), `$W/cassandra-run28`, `ant -Dlocal.repository=$W/m2 build-test` `BUILD SUCCESSFUL`; `W=~/Library/Caches/stage4`. After the unit runs, the test class and `build/test/cassandra` were removed; `git status` is clean, and the test yaml was never edited |
| Case-file commit / harness commit | uncommitted (sha256 values in §1) |
| Storage for node data | local SSD, `$W/node-bl/n1` (wiped before each case and at the end); JMX 7199 |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries/`: `stepE.txt`, `clone-build-run28.log`, `audit-compile.log`, `unit-attempt0-r{1,2,3}/`, `unit-r{1,2,3}/` (ant log, JUnit XML, test log), `cluster-shake-attempt0/`, `cluster-shake-attempt1/` (with `NOTE.txt`), `cluster-shake/`, `cluster-run1/` (`commands.log`, `summary.txt`, `btm-check.txt`, and per case `A|B|C/`: `n1/` node logs including `node.out` and `gc.log`, `histo/h-<epoch>.txt`, `hist-base-{1,2,3}.txt`, `hist-post.txt`, `heap_info.log`, `cql-count-*.txt`, `tablestats-*.txt`, `stress-*.log`, `go-offset.txt`, `go-time.txt`, `node-out-after-go.txt`), `run1-start-epoch.txt`, `run1-end-epoch.txt`, `run1-pmset-tail.txt` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| 1 | Unit attempt 0 | B2c/B2e (and the A3 amendment's item (iv)) | All four cases errored. The unit yaml enables read thresholds with `coordinator_read_size_fail_threshold: 4096KiB`. `SelectStatement.maybeFail` also runs in the internal pager's `select.process`, so a replay page over 4 MiB reached it, and `loggableTokens` threw `IndexOutOfBoundsException` on the internal statement's unbound markers ([`run1/unit/attempt0/error-excerpt-r1.txt`](batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous/run1/unit/attempt0/error-excerpt-r1.txt)). The audit had wrongly concluded that thresholds do not apply. | `DatabaseDescriptor.setReadThresholdsEnabled(false)` in `@BeforeClass`, the node default (`Config.java:526`); dated correction of A3 (iv) | Applied 2026-10-26; §9a unchanged; the unit tier restarted from r1 | `e39a7514…` |
| 2 | Cluster shakedown attempt 0 | B3c | `cassandra-stress user` rejects a profile without `queries` (`AssertionError: queries map is required`) ([`shakedown/attempt0-stress-error.txt`](batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous/shakedown/attempt0-stress-error.txt)) | `queries: {}` appended to both profiles | Applied 2026-10-26, before cluster run 1; §9a unchanged | `70b0f972…` |
| 3 | Cluster shakedown attempt 1 | B3a (rule 2) | The filed `IF !(new java.io.File(…).exists())` does not parse in Byteman 4.0.20 (`TestScript`: ParseException). The agent silently skipped the rule, so the scheduled pass replayed before `go` (`ReplayingBatch` objects in the baseline; first `BLPAGE` line from a pass started before `go`: [`shakedown/attempt1-summary.txt`](batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous/shakedown/attempt1-summary.txt), [`shakedown/attempt1-A-blpage-lines.txt`](batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous/shakedown/attempt1-A-blpage-lines.txt), whose last line is the `go` epoch, appended when the excerpt was made) | `BIND flag:java.io.File = new java.io.File(…)`, `IF !flag.exists()`, same action; `TestScript` check before any node start | Applied 2026-10-26, before cluster run 1; §9a unchanged | `70b0f972…` |

Two operator slips, not steps of the case file:
- During shakedown attempt 1 the harness script was edited while it ran. It stopped after case C's node stop and before its final check. The node had stopped; `$W/node-bl` was wiped by hand (`shakedown/attempt1-NOTE.txt`).
- Two status polls timed out because the laptop slept (08:53–08:58) during shakedown attempt 2. Run 1 was then wrapped in `caffeinate`.

## 4. Run 1

**Scope:** both tiers, all cases in §1. **Command logs:**
- Unit: [`run1/unit/`](batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous/run1/unit/). For each of `r1`–`r3`: `commands.log`, `summary.txt`, `blp-lines.txt` (the `BLP` lines copied from the raw test log) and `junit-testsuite.txt`; plus `attempt0/`.
- Cluster: [`run1/cluster/`](batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous/run1/cluster/). `commands.log`, `summary.txt` and `btm-check.txt`. For each case: `cql-count-{before,after}.txt`, `tablestats-before-excerpt.txt`, `node-out-blpage-lines.txt`, `go-{offset,time}.txt`, `stress-*-results.txt`, `hist-base-{1,2,3}-top.txt`, `hist-peak-top.txt` and `replaybatchlog.out`.

### 4.1 Readings

**Unit tier.** Each run: JUnit 4 tests, 0 failures, 0 errors. r1, r2 and r3 printed identical lines. Setup: `endpoints=1 batchlogTimeout=4000 DEFAULT_PAGE_SIZE=128 maxMutationSize=2621440 readThresholdsEnabled=false`.

| Case | SSTables | mean | ps = replayPs | per-call counts | maxCount | maxBytes | replayed / after | Predicted (B2f as amended) |
|---|---|---|---|---|---|---|---|---|
| A (64 KiB, memtable) | 0 | 0 | 128 = [128] | 128, 128, 4 | 128 | 8,401,920 B = 8.013 MiB | 260 / 0 | 128; 128,128,4; [8.0, 9.0] MiB |
| B (64 KiB, flushed) | 1 | 73,457 | 57 = [57] | 57, 57, 57, 57, 32 | 57 | 3,741,480 B = 3.568 MiB | 260 / 0 | 57; [3.5625, 4.0] MiB |
| C (tiny SSTable + 64 KiB unflushed) | 1 | 215 | 128 = [128] | 128 ×5, 120 | 128 | 8,401,920 B = 8.013 MiB | 760 / 0 | 128; ≤ 16,400 mean; [8.0, 9.0] MiB |
| D (1 MiB, flushed) | 1 | 1,131,752 | 3 = [3] | 3, 3, 3, 3 | 3 | 3,146,040 B = 3.000 MiB | 12 / 0 | 3; [3.0, 4.0] MiB |

Evidence: `run1/unit/r*/blp-lines.txt` and `junit-testsuite.txt`.

**Cluster tier.** One node, a fresh start per case. Big load: 512 partitions = 256 batches, 0 errors, in each case. Small load (C): 4,000 partitions = 2,000 batches, 0 errors. 0 `ERROR` lines in `system.log` in each case.

| Case | count before / after | SSTables · tablestats mean · derived ps | governing BLPAGESIZE | `BLPAGE` lines (values) | `BLPAGE` before `go` | baseline (median) · drift | peak sample Total · `ReplayingBatch` peak | live delta | replay time |
|---|---|---|---|---|---|---|---|---|---|
| A (memtable-only) | 256 / 0 | 0 · 0 · 128 | 128 | 2 (128, 128) | 0 | 46,348,800 · 0.28 MiB | 443,387,224 · 125 (max over samples 125) | **378.6 MiB** | 256 s |
| B (flushed) | 256 / 0 | 1 · 1,131,752 · 3 | 3 | 86 (85 × 3, 1) | 0 | 45,585,752 · 0.08 MiB | 55,599,808 · 3 | **9.6 MiB** | 257 s |
| C (diluted) | 2256 / 0 | 1 · 215 · 128 | 128 | 18 (17 × 128, 80) | 0 | 47,337,360 · 0.08 MiB | 452,513,912 · 128 | **386.4 MiB** | 286 s |

Ratios: delta(A)/delta(B) = 39.6 and delta(C)/delta(B) = 40.5. In every sample of every case, `ReplayingBatch` ≤ the governing BLPAGESIZE. In the post samples, `ReplayingBatch` = 0, and the Totals were 47.4, 46.9 and 50.3 MB.

Evidence: `run1/cluster/summary.txt` and `run1/cluster/<case>/*`. The full histograms are in the logs.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity.** Each run had 4 tests and 0 failures or errors [observed: `junit-testsuite.txt`]. stored = replayed = N and afterCount = 0 in every case; the SSTable preconditions held [observed: `blp-lines.txt`]. Every case replayed at least two pages, so the limit was passed. Valid.
2. **Readings.** Nothing unusual. The three runs are identical [observed]. The means equal the derived bucket offsets exactly (73,457 and 1,131,752), and C's tiny-row mean is 215 [observed].
3. **Matched rows.** All of these hold [observed: `blp-lines.txt` r1–r3]:
   - **Finding 1**, row "maxCount ≤ ps ≤ 128 in A–D, replayPs = ps, in all three runs": maxCount 128, 57, 128, 3 equals ps in every case; the per-call counts match B2f exactly.
   - **Finding 2**, row "B and D: ps < 128 and maxBytes ≤ 4 MiB": 3.568 and 3.000 MiB.
   - **Finding 2**, row "A and C: ps = 128 and maxBytes > 4 MiB (in [8.0, 9.0] MiB)": 8.013 MiB, 2.0 × the target.
4. **Excluded rows.** None of these occurred [observed]:
   - maxCount > ps: no.
   - Per-call counts different from the derived pages: no.
   - replayPs ≠ ps: no.
   - B or D maxBytes > 4 MiB: no.
   - B or D ps = 128: no.
   - A or C ps < 128: no.
   - calls = 0, delta < N or after > 0: no.
   - A failing precondition, or runs that disagree: no.
5. **Observed vs. inferred.** The bytes reading is `replayedBytes`, the serialized mutation size of the retained batches. It is a proxy for the decoded heap (a lower bound, about one copy), as B2d names. The count reading needs no inference.
6. **Deviations and gaps.** `lastReplayedUuid` is reset by reflection between cases (B2c amendment), and read thresholds are off (defect 1). Neither changes the replay code.
7. **Core question.** The count cap holds exactly: no page ever held more than `pageSize` ≤ 128 decoded batches. `pageSize` follows the SSTable mean, giving 57 for 64 KiB rows and 3 for 1 MiB rows, and bytes per page then stay ≤ 4 MiB. With a memtable-only or diluted `system.batches`, the page falls back to 128, and the bytes per page are 8 MiB, twice the target.

**Conclusion (unit tier):** B2g (as amended): finding 1 confirmed; finding 2 confirmed as "target holds with matching statistics, bypassed otherwise". **Confirmed.**

**Cluster tier**

1. **Validity.**
   - count_before was 256, 256 and 2,256, exactly as expected; count_after was 0 in every case [observed: `cql-count-*.txt`].
   - No `BLPAGE` line appeared before `go`, so the hold rule held. The governing `BLPAGESIZE` came from the pass after `go` [observed: `node-out-blpage-lines.txt`, `go-offset.txt`].
   - Baseline drift was ≤ 0.28 MiB, and the rules type-checked [observed: `btm-check.txt`].
   - No sleep event occurred during the run [observed: `run1-pmset-tail.txt`, in the logs].
   - Valid.
2. **Readings.** The A and C deltas, 379 and 386 MiB, are well above the "expected ≈ 250 MiB" in B3f's informational note, though inside its frozen band (≥ 150 MiB). In the peak histograms, `[B` (byte arrays) grew by ≈ 396 MB over the baseline [observed: `hist-peak-top.txt`, `hist-base-3-top.txt`]. That is about 3 MiB of live heap per 1 MiB batch at 125 decoded batches. The model of B3f counted 1 MiB raw plus 1 MiB decoded. The extra copy is not identified [inferred: likely a further copy of each decoded blob during deserialization or replay; not measured]. The relations and bands are unaffected.
3. **Matched rows.** All of these hold [observed: `summary.txt` TRACE/SAMPLE, `selfcheck.out`]:
   - **Finding 1**, row 1: `BLPAGE` max = governing BLPAGESIZE (128, 3, 128) ≤ 128; `ReplayingBatch` ≤ BLPAGESIZE in every sample; deltas 378.6 and 386.4 MiB (≥ 150) and 9.6 MiB (≤ 30); ratios 39.6 and 40.5 (> 5). The `BLPAGE` page arithmetic is exact: 2, 86 and 18 lines.
   - **Finding 2**, "A and C: BLPAGESIZE = 128 with delta ≫ 8 MiB": the bypass.
   - **Finding 2**, "B: BLPAGESIZE = 3 (= derived from m = 1,131,752) and delta ≤ 30 MiB": the target holds.
4. **Excluded rows.** None of these occurred [observed]:
   - `BLPAGE` or `ReplayingBatch` > BLPAGESIZE: no.
   - delta(A) ≈ delta(B): no (ratio 39.6).
   - A delta outside its band: no.
   - B at 128, or A/C below 128: no.
   - count_before short, count_after > 0, no `BLPAGE` lines, `BLPAGE` before `go`, or drift > 10 MiB: no.
5. **Observed vs. inferred.** The conclusion does not depend on the inference in part 2. The rows rest on the live-heap readings and the traces.
6. **Deviations and gaps.**
   - Fault injection: rule 1 suppresses the coordinator cleanup, and rule 2 holds replay until `go`, as designed (A3 (vi)).
   - One node, so no remote sends or hints.
   - The live delta includes the raw page held by `FromPager`, which the design counts as part of replay heap (A3 (v)).
   - The 10 s sampling saw the A ramp at 125 of 128.
7. **Core question.**
   - On a node, replay never held more decoded batches than the page size.
   - Replay heap followed the page size: about 380 MiB above baseline with pages of 128 large batches, against about 10 MiB with pages of 3, for the same 256 batches.
   - When `system.batches` had a matching SSTable, the page size followed the 4 MiB target (3 × 1 MiB). When it was memtable-only (A), or its only SSTable held tiny rows (C), the target did not bind and a page held 128 MiB of batches. Those 128 MiB of rows held about 380 MiB of live heap, about 90 × the 4 MiB target.

**Conclusion (cluster tier):** B3g (as amended): finding 1 confirmed; finding 2 confirmed as "target holds with matching statistics, bypassed when memtable-only or diluted". **Confirmed.**

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

The self-check script is [`run1/selfcheck.py`](batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous/run1/selfcheck.py). It was written before any reading and has not been changed since. It is independent of the harness and does not read `summary.txt` or `stdout.txt`. What it re-reads:
- Unit: the raw JUnit XML and the raw test log of each run, recomputing the maxima from the per-call lists.
- Cluster, per case: the raw `node.out` cut at `go-offset.txt`, the raw class histograms, the cqlsh outputs, the tablestats outputs, the stress logs and `system.log`.

Result: **173 checks, 0 failed** ([`run1/selfcheck.out`](batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous/run1/selfcheck.out)).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | JUnit counts; stored/replayed/after; preconditions; counts before and after; no `BLPAGE` before the offset; drift; agent on the JVM command line. |
| 2. Readings | yes | Means, page sizes and per-call lists recomputed from the raw logs; deltas from the raw histograms (median baseline). |
| 3. Matched row | yes | Every finding-1 and finding-2 check passes in r1–r3 and in A, B, C. |
| 4. Excluded rows | yes | Each excluded condition is absent in the raw files. |
| 5. Observed vs. inferred | yes | The only inference (the ≈ 3 MiB per batch) is not used by any row. |
| 6. Deviations and gaps | yes | Stated; defects 1–3 fixed before the runs they affect. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Count: largest list at `:296` and live instances ≤ pageSize. Heap: A ≫ B with only the flush state differing. Byte target: ps × row ≤ 4 MiB only when the SSTable statistics describe the batches. |

### 5.2 Run 2?

**No.** Decided 2026-10-26. Both tiers match exactly, three unit runs agree, and the self-check holds without depending on an inferred statement. The bypass of the byte target is a direct consequence of `:254`, observed on both tiers.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

**Stage-3 estimate:** positive, with a known overshoot (count cap holds; byte target only with matching SSTable statistics).

**Claim tested:** (B1)
- (i) During one replay pass, the number of live `ReplayingBatch` objects never exceeds `pageSize` ≤ 128, so replay heap grows with `pageSize` × the batch size.
- (ii) `pageSize` follows ⌊4 MiB / mean SSTable partition size⌋ when SSTables exist, and is 128 when `system.batches` is memtable-only, so the byte target is then not a cap.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed**. Finding 1 row 1: maxCount = ps (128, 57, 128, 3), per-call counts exact, in three runs. Finding 2: B and D at 3.57 and 3.00 MiB per page (≤ 4 MiB); A and C at 8.01 MiB per page with ps 128 | **count cap: caps**; **4 MiB byte target: caps only on some paths (bypass)** | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed**. Finding 1 row 1: `BLPAGE` max and `ReplayingBatch` ≤ BLPAGESIZE (128, 3, 128); live delta 378.6 / 9.6 / 386.4 MiB; ratios ≈ 40. Finding 2: B's page of 3 holds the target; A and C pages of 128 (≈ 128 MiB of rows, ≈ 380 MiB live) bypass it | **count cap: caps**; **4 MiB byte target: caps only on some paths (bypass)** | run 1 + self-check | 2026-10-26 |

**Feedback filed:** the case file's section D (uncommitted). The fifteen step-0 amendments and the three runbook-fix amendments (with the A3 correction) are in the case file, dated. All three post-filing hashes are new rows in `_INDEX.md` §4. The §1 Stage 4 column and the coverage line are updated. No section was amended for a refutation (none occurred).
