# Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE — stage-4 results  <!-- file: long-path/results/Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE.md -->

> **Case:** [`Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE`](../../stage3-ai-deep-read/cases/Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE--guided.md)
>
> **Status:** **Closed 2026-10-19 — all tiers verified at stage 4 (verdicts below).** verdict filed (2026-10-15) — **unit: Confirmed; cluster: Confirmed** (§9a row 1): one SSTable's summary keeps exactly ⌊*L*/(*K* + 8)⌋ entries at the real 2^31 − 1 (35,786 entries of 60,008 B, 2,147,446,288 B) and at Byteman-moved 8 · 32 · 128 MiB (8,322 · 33,288 · 133,152, 1 : 4 : 16), one refusal and one `ERROR` at `keysWritten` = *n*\*, gauge and `Summary.db` to the byte; reads past the last sample return their rows after *r* − *n*\* + 1 skipped index entries; the second site doubles the interval at the predicted boundary, and a start-up rebuild keeps its untrimmed 1.36 GB reservation; no run 2
>
> **Path:** long. One results file per path, each in its path's folder.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base commit `d47b932` (the last commit touching the case file) plus the step-0 amendments of 2026-10-15 (uncommitted at freeze). §9 hash before the amendments `26b14189232977b2b146c6948a666b09edbe60c3`, §9a `568eb6138f94062ced5a5aaf412088cffe1de143`; **after the amendments §9 `82abfe04a3a8080f7953a3ee2ecbeaef4b48a211`, §9a `568eb6138f94062ced5a5aaf412088cffe1de143` (unchanged)**. §9a is frozen at this version. Recorded 2026-10-15 03:24 EDT, before any reading of this case existed (no folder for it under `pc57:~/stage4-logs/` or `~/stage4-harness-run/`). |
| **Harness** | `../harness/Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE/`, written by this session after the freeze (§1.2). Node copy `pc57:~/stage4-harness-run/imv/`. |
| **Tiers and values** | Unit: upstream `IndexSummaryTest`; harness `IndexSummaryCapTest` (U1 real limit, U2 second site), `IndexSummaryMovedLimitTest` (U3, moved limit 8 · 32 · 128 MiB and offset 0). Cluster (one node on `pc57`, BIG, `min_index_interval` 1): lifetime 1 `c32` (control), `big` (real limit), `t8 t32 t32a t32b t32c t128` (moved), restart check; arm E lifetimes 2–4 (`cassandra.index_summary_expected_key_size` 65,536). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-15 |

### 1.1 Design audit

Citations re-read against the pinned clone `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Native bytes of one SSTable's summary (`entries` + `offsets`) and its `Summary.db` (§7, 9a). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | A type bound with no knob; moved by a Byteman offset on the sole caller's operand to 8 · 32 · 128 MiB plus the real 2^31 − 1 (9a Testability). `getEntrySize(DecoratedKey)` (`IndexSummaryBuilder.java:137-140`) has one caller, `:204`; the constructor uses the `long` overload (`:105`, `:146-149`), so the rule moves only the primary site. Stage 3's ruling (3) on a Byteman-moved limit is still open; U3 checks the moved rule against U1's formula, so a wrong offset would show. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Gauge `IndexSummaryOffHeapMemoryUsed`, `Summary.db` size, the `built` capacity; `RssAnon` as support; the gap (NMT cannot see `Native.malloc`) named in 9d. |
| A. Core question | usage driven to the limit and past it | Met | *N* = 1.25 *n*\* and 2.5 *n*\*, and the boundary pair *n*\*, *n*\* + 1 (9a table). |
| B. Logic | each step says what it establishes | Met | 9a "How this verifies", Logic (1)–(7). |
| B. Logic | prediction stated in numbers or a clear relation | Met | Integer table per table, exact relations, no tolerance (9a). Recomputed: *n*\* = ⌊*L*/(*K* + 8)⌋ = 8,322 · 33,288 · 133,152 · 35,786; U1 713,924 · 71,563 · 32,764; U2 boundary 29,826,161/29,826,162 (capacities 2,147,483,592 / 1,073,741,832); arm E *e* = 2, reservation 1,363,642,920 — all agree. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | Rows for over-cap, gauge vs count, flat across *L*, early stop, ERROR count, lost reads, skip counts, invalid (no refusal, two SSTables, silent instrument), arm E. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | *n*\* 1 : 4 : 16 and the `refused` trace plus the unique `ERROR` line. |
| B. Logic | alternative explanations and their controls | Met | `c32` without the rule; redistribution off (`ResizeIntervalInMinutes` −1); key cache off; one SSTable per table. |
| C. Specific | a human can follow it from the intro and §9a | Met | §9 intro, §9a. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | Rules, table options and commands are given (9b, 9c). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after rec. 1 | `load-keys.py` writes every key to a file: 2.4 GB for `big` (rec. 1). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Listed as step-1 work (9c). `pc57`: JDK 11.0.32.1, Ant 1.10.12, Byteman 4.0.20 (`byteman-submit` present), 251 GiB RAM, about 45 GB free on `/`. A second AI session runs another case's tier on the same node in `~/cassandra-run1`; this case uses its own clone `~/cassandra-run3` (built 2026-10-15 03:22, `ant build-test` 1 min 47 s) and takes the node only when the other run has released it (rec. 2). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | About 10 GB of disk for `big` (Data, Index, Summary, commit log); native peak about 5.5 GB; heap 24 GiB with a 4 GiB flush threshold over 2.4 GB of keys (9b). |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Read in context: `IndexSummaryBuilder.java:42`, `:100-132` (second site, clamp, reservations), `:137-149`, `:200-228` (check, disallow does not advance `nextSamplePosition` while `keysWritten++` continues, so one refusal ends all sampling), `:231-244`, `:246-252` (trim), `:261-278`; `SafeMemoryWriter.java:44-67`, `:99-104`; `BigTableWriter.java:253-258` (builder from `getKeyCount()` and the table's `minIndexInterval`); `BigTableReader.java:215-357` (key cache `:266-275`; the scan from the sampled position continues past `effectiveInterval` comparing decorated keys until found or passed, so reads past the last sample succeed with *r* − *n*\* + 1 skips); `IndexSummary.java:399-421` (24-byte header, offsets plus the base), `:465-476`; `IndexSummaryComponent.java:75-130`; `BigSSTableReaderLoadingBuilder.java:225-262`; `DatabaseDescriptor.java:4136-4142`; `IndexSummaryManager.java:130-139`; `conf/cassandra.yaml:941-947`; `Config.java:373`. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Regenerate keys from the seed in both scripts instead of writing a key file. | Applied 2026-10-15 (9 intro, 9c); uncommitted | Saves 2.4 GB of disk and time; the keys are a function of (seed, *N*, *K*). |
| 2 | Run in a private clone `~/cassandra-run3`; take the node only between the other session's node lifetimes. | Applied 2026-10-15 (9 intro) | A concurrent `ant` in a shared tree broke `bin/nodetool` for one call in another case's shakedown (DataDirectory results §1.2). |
| 3 | §5/§8: name in the case that the disallow leaves `nextSamplePosition` behind `keysWritten`, so the check is never reached again for that builder (the reason for "one ERROR per SSTable"). | Left for stage 3 | Already implied by §5's "final for the builder"; precision only. |

**Agreement criteria** — not filled (run 2 not chosen yet).

### 1.2 Instrument checks (not readings)

- **Byteman:** `summary-trace.btm` and the three `moved-limit-*.btm` type-check (`TestScript: no errors`). Two first forms
  failed and were rewritten before any node start: a cast inside `link(...)` does not parse, so the per-thread skip count uses
  Byteman counters keyed by `Thread.currentThread()` (`readCounter(t, true)` resets at entry, `incrementCounter(t)` per skip).
- **Unit instrument run 1** (`unit-run.sh instrument`, 03:26–03:29, `~/cassandra-run3`): U0 12/12, U1 and U2 every check ok;
  **U3 failed to load its rules**: the BMUnit agent's listener could not bind port 9091, held at that moment by the Byteman
  listener of the other session's node (`BindException`, `ant-IndexSummaryMovedLimitTest.log`), so the moved limit was not in
  force (12 MISMATCH lines, all U3). Environment defect, not a reading: the unit runners now pass
  `-Dorg.jboss.byteman.contrib.bmunit.agent.port=19091` and this case's node uses listener port 19091 (the case's 9b says 9091;
  the port is not part of §9a).
- **Unit instrument run 2** (`instrument2`, 03:30–03:32): 18/18 tests, 111 checks, 0 MISMATCH; U3 *n*\* 8,322 · 33,288 · 133,152
  with one `ERROR` each, offset 0 keeps all 41,610.
- **Shakedown 1** (`cluster-run.py shakedown1 life1 t8`, 03:44–03:46, `pc57:~/stage4-logs/imv/shakedown1/life1/`): node up in
  50 s, all 8 trace rules listed, `ResizeIntervalInMinutes` −1; the probe instrument check passed (`refused` at `keysWritten`
  8,322, one `ERROR`, reads past the last sample skip *r* − 8,322 + 1); `t8` every `EXPECTED` yes but one: the flush calls
  `IndexSummaryBuilder.build()` **twice** (two identical `built` lines, same builder id), so the harness's "one `built` line"
  expectation was relaxed to "at least one, all identical" before run 1 (a harness check, not part of §9a; §9a's "silent
  instrument" row is about no line at all). Harness re-synced, run 1 uses it.

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-15 | — |
| Node (CloudLab name and type) | `pc57` (`node0.jason92-319347`), 32 cores, 251 GiB RAM; the session ran on the node itself | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | — |
| Ant (`ant -version`) | 1.10.12 | — |
| Local `cassandra-src` clone commit | `~/cassandra-run3` at `cassandra-5.0.9` (`b5f2a54210d5`), cloned and built 2026-10-15 03:20 for this session's runs | — |
| Case-file commit / harness commit | case file: base commit plus the uncommitted step-0 amendments (§1); harness: uncommitted, node copy checked by `md5sum` (`~/stage4-harness-run/*.md5`) | — |
| Storage for node data | `~/stage4-imv/` on `/dev/sda3` (local disk, ext4) | — |
| Full logs (path, outside the repo) | `pc57:~/stage4-logs/imv/run1/{life1,armE}/` (unit: `~/stage4-logs/imv/unit-run1/`) | — |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | run 1, cluster lifetime 1 (04:17–04:51) | 9e lifetime 1 step 2, `load-keys.py` for `big` | The bundled driver's token-aware routing hashes every routing key with its pure-Python Murmur3: 9,129 of 40,000 rows of 60,000-B keys in 31 min (about 5 rows/s), against 9b's plan of one load | `imvdrv.py` uses `DCAwareRoundRobinPolicy` without token awareness and `token_metadata_enabled=False` (one node needs no routing); the load then took 29.1 s. The lifetime was stopped (the node stopped cleanly) and **the tier restarted from its beginning**; the stopped lifetime's records are kept as `life1.defect1/` (only `c32` was read in it; not counted). A harness change; §9 unchanged. | 2026-10-15 | none needed |

Before run 1 (instrument checks, §1.2): the BMUnit agent's port, the per-thread skip counter, the "one `built` line" harness
expectation.

## 4. Run 1

**Scope:** unit tier (U0–U3) 2026-10-15 03:35–03:38; cluster lifetime 1 04:51–05:06 (restarted after defect 1) and arm E
lifetimes 2–4 05:06–05:10 EDT, `chainB.sh`. **Command log:** `session.log` per lifetime on the node; excerpts in
`Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE/run1/` (`unit/`, `life1/` and `armE/` with `summary.txt`, `tables.csv`,
`reads.jsonl`, `trace-excerpt.txt` (trace without `scan` lines and system-table builders), `log-lines.txt`; `selfcheck.py`,
`selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/`): U0 upstream `IndexSummaryTest` 12/12; `IndexSummaryCapTest` 2/2 and `IndexSummaryMovedLimitTest`
4/4, **111 checks, 0 MISMATCH**. U1 at the real limit: (*K*, *N*) = (3,000, 1,000,000) → 713,924 entries, `entriesLength`
2,147,483,392; (30,000, 80,000) → 71,563 (2,147,462,504); (65,535, 40,000) → 32,764 (2,147,450,852); the boundary pair
(30,000, 71,563) → 71,563 entries, no `ERROR`, and (30,000, 71,564) → 71,563, one `ERROR` at `keysWritten` 71,563; interval 2
with 160,000 → 71,563, refusal at `keysWritten` 143,126; in every refusing case `nextSamplePosition` stays at the refused key,
`entries` length and capacity are unchanged by the next key, the trimmed regions equal `entriesLength` and 4 × size,
`binarySearch(last key)` = −(size + 1). U2: 29,826,161 expected keys → interval 1, capacity 2,147,483,592, no `WARN`;
29,826,162 → interval 2, capacity 1,073,741,832, one `WARN`; *E* = 3,000 with 1,000,000 → interval 2, 1,504,000,000. U3 (the
cluster's Byteman offsets): 8,322 · 33,288 · 133,152 entries with one `ERROR` each; offset 0 keeps all 41,610.

**Cluster tier, lifetime 1** (`life1/tables.csv`, `life1/summary.txt`; *K* + 8 = 1,008 B for 1,000-B keys, 60,008 B for `big`)

| Table | *L* | *N* | Entries kept (`built count`) | `entriesLength` = trimmed capacity | Refusal (`keysWritten`, `length`) | `ERROR` lines | Gauge | `Summary.db` | Highest read's skips | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| `c32` | real | 41,610 | 41,610 | 41,942,880 | — | 0 | 42,109,320 | 42,111,352 | 0 | `life1/` |
| `big` | real | 40,000 | **35,786** | **2,147,446,288** | 35,786, 2,147,446,288 | 1 | 2,147,589,432 | 2,147,709,464 | 4,214 | `life1/` |
| `t8` | 8 MiB | 10,403 | 8,322 | 8,388,576 | 8,322, 8,388,576 | 1 | 8,421,864 | 8,423,896 | 2,081 | `life1/` |
| `t32` | 32 MiB | 41,610 | 33,288 | 33,554,304 | 33,288 | 1 | 33,687,456 | 33,689,488 | 8,322 | `life1/` |
| `t32a` | 32 MiB | 33,288 | 33,288 | 33,554,304 | — | 0 | 33,687,456 | 33,689,488 | 0 | `life1/` |
| `t32b` | 32 MiB | 33,289 | 33,288 | 33,554,304 | 33,288 | 1 | 33,687,456 | 33,689,488 | 1 | `life1/` |
| `t32c` | 32 MiB | 83,220 | 33,288 | 33,554,304 | 33,288 | 1 | 33,687,456 | 33,689,488 | 49,932 | `life1/` |
| `t128` | 128 MiB | 166,440 | 133,152 | 134,217,216 | 133,152 | 1 | 134,749,824 | 134,751,856 | 33,288 | `life1/` |

Every table is one SSTable (one `Data.db`); one `writer` and `init` line each, two identical `built` lines per flush; the
submitted rule listed exactly the intended *L* before each moved table's flush and nothing after; every point read (5 ranks
below *n*\*, the 5 highest) returned its row with `v` = the key's index, skips 0 below *n*\* and *r* − *n*\* + 1 above
(`reads.jsonl`). `RssAnon`: idle 27,365,990,400 B; before `big`'s load 27,429,240,832; after its flush 29,594,357,760
(**+2,165,116,928**); 300 s later 29,596,069,888. Restart check: `big` loaded from `Summary.db` with no "Index summary file is
corrupted" line and no rebuild, gauge 2,147,589,432 before and after; the 10 reads after the restart skip 0 and 4,210–4,214.

**Arm E** (`armE/`): `e41` (41,610 keys, property 65,536): `init` effective interval **2**, `entriesCapacity`
**1,363,642,920**, one `WARN … using interval of 2 instead`; kept 20,805, `entriesLength` 20,971,440, gauge 21,054,660,
`Summary.db` 21,056,692. `e30` (30,000): interval 1, capacity 1,966,320,000, no `WARN`; kept 30,000, gauge 30,360,000,
`Summary.db` 30,362,032. Lifetime 3 (property): `e41`'s `Summary.db` refused ("min_index_interval changed from 2 to 1") and
rebuilt — `init expectedKeys=41649` (the loader's Ñ), effective 2, capacity 1,364,888,256 = 65,544 × 20,824, and `built`
count 20,805, `entriesLength` 20,971,440 with **capacity 1,364,888,256 (untrimmed)**; one `WARN`; gauge 21,054,660; `e30` loaded.
Lifetime 4 (no property): `e41` refused again, rebuilt at interval 1 (`built` count 41,610, `entriesLength` 41,942,880,
capacity 47,979,648, untrimmed), no `WARN`, gauge 42,109,320. Lifetime 4b: `e41` loads with no rebuild.

### 4.2 Conclusion and logic

1. **Validity.** Valid: every table refused where *N* > *n*\* and not where *N* ≤ *n*\* [observed: `tables.csv`]; one SSTable
   per table [observed]; redistribution off (`ResizeIntervalInMinutes` −1) and the moved rule in force only for its table
   [observed: `summary.txt`]; the probe instrument check passed [observed].
2. **Readings.** Two identical `built` lines per flush (the builder is built twice from one writer); none unusual otherwise.
3. **Matched row.** "Every table keeps min(*N*, *n*\*) entries with `entriesLength`, gauge and `Summary.db` as tabulated; one
   refusal line and one `ERROR` line exactly where *N* > *n*\*, at `keysWritten` = *n*\*; none in the control; *n*\* follows *L*
   1 : 4 : 16 and the real-limit arm matches the formula; every read returns its row with the predicted skips" —
   **Confirmed**, every figure equal to §9a's table [observed: `tables.csv`, `reads.jsonl`]; the `ERROR` count in
   `system.log` is 7 = 6 refusing tables + the probe [observed: `selfcheck.txt`].
4. **Excluded rows.** No table above *n*\* or above *L*; gauge and file follow the count exactly; *n*\* moves with *L*; no
   early stop; one `ERROR` per refusing SSTable; no read returned nothing; skips equal *r* − *n*\* + 1; arm E's intervals as
   predicted, and the derived restart sub-predictions are seen (rebuild with the untrimmed capacity).
5. **Observed vs. inferred.** The moved limits are a Byteman offset on the sole caller's operand, not a patched build (stage-3
   ruling (3) open); that they move only the check is shown by U3 against U1's formula and by `c32` = `t32`'s data with no
   rule keeping all 41,610. Nothing else is inferred.
6. **Deviations and gaps.** Runbook defect 1 (load client) restarted lifetime 1; the Byteman listener ran on port 19091, not
   9091 (§1.2). `RssAnon` is support only.
7. **Core question.** The type bound caps one SSTable's summary exactly at ⌊*L* / (*K* + 8)⌋ entries — at the real 2^31 − 1
   (2.0 GiB of entries) and, moved, 1 : 4 : 16 with *L* (Logic 1–3; part 3) — through the disallow branch at `:204`, whose one
   refusal ends sampling for the SSTable (Logic 4); the native gauge and `Summary.db` follow it to the byte (Logic 5), and the
   cost moves to index scans without losing a row (Logic 6). The second site caps the reservation at the predicted boundary
   (Logic 7).

**Conclusion (one line):** §9a row 1 — **confirmed**; arm E as predicted, its derived restart sub-predictions observed.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (none of the run script's code; `life1/imv.trace`, `system.log`, `debug.log`, `data-final.txt` and arm
E's) compares every table with the §9a table copied into it: **76 checks, 0 failed** (`selfcheck.txt`). Its first version
failed 11 checks on two defects of its own (it looked for `init` lines only after the `writer` line, which comes after them;
it assumed 10 distinct read ranks where *N* ≤ *n*\* + 4 gives 9); both fixed before the final result, no reading changed.

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | one `Data.db` per table in `data-final.txt`; refusals only where *N* > *n*\* |
| 2. Readings | yes | `built` lines identical per builder id |
| 3. Matched row | yes | every `built`/`refused` figure and `Summary.db` size equals §9a's table |
| 4. Excluded rows | yes | dose-response 8,322 : 33,288 : 133,152; reads found with exact skips |
| 5. Observed vs. inferred | yes | U3 vs U1 (`unit/run.out`), `c32` keeps all |
| 6. Deviations and gaps | yes | defect 1 recorded; the restarted lifetime is the one counted |
| 7. Core question | yes | follows Logic 1–7 |

### 5.2 Run 2?

**No** — 2026-10-15: every reading is an integer from the code that equals the frozen prediction; nothing rests on an
inferred statement except the Byteman-moved limit, which U3 checks against the real one.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed** (U1 exact at the real limit, boundary pair, interval 2; U2 at its boundary; U3 the moved limit) | run 1 + self-check | 2026-10-15 |
| Cluster | **Confirmed** (row 1); arm E as predicted, including the derived restart rebuild and its untrimmed reservation | run 1 + self-check | 2026-10-15 |

**Feedback filed:** the case file's §10 "Stage-4 feedback" (2026-10-15, uncommitted), with: a start-up rebuild keeps the
loader's **untrimmed** reservation (1,364,888,256 B for 20,971,440 B of entries with the property; 47,979,648 B for 41,942,880 B
without) — the loader never calls `prepareToCommit()`'s trim (§7 derived it; now observed); the summary is built twice per
flush; stage-3 ruling (3) (a Byteman-moved limit) — this run used one and checked it against the real limit at unit level.
