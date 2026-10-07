# row_index_read_size_fail_threshold-checkSize-failThreshold — stage-4 results

> **Case:** [`row_index_read_size_fail_threshold-checkSize-failThreshold`](../../../stage3-ai-deep-read/long-path/cases/row_index_read_size_fail_threshold-checkSize-failThreshold.md)
>
> **Status:** verdict filed (run 1 and self-check; no run 2)
>
> **Path:** long. Unit tier and cluster tier, run 2026-10-07.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Commit `986cf19`, §9's hash `622d104101682450234abc2c26154daa39bb5135` (`sed -n '/^## 9\. /,/^## 10\. /p' <case file> \| git hash-object --stdin`). §9a is frozen at this version and was **not** edited afterwards. Later, dated documentation-only amendments to §9c (the harness actually used) change §9's hash but not §9a's; the hash of §9a alone (`sed -n '/^### 9a\. /,/^### 9b\. /p'`) is recorded in §8. |
| **Harness** | [`../harness/row_index_read_size_fail_threshold-checkSize-failThreshold/`](../harness/row_index_read_size_fail_threshold-checkSize-failThreshold/): `RowIndexSizeGuardTest.java`, `unit-run.sh`, `make-node-yaml.sh`, `checksize.btm`, `Jmx.java`, `send-read.py`, `cluster-run.py`; committed with this file (see `git log` for the folder). |
| **Tiers and values** | Unit: 8,192 · 32,768 · 131,072 · 8,388,608 B and unset, in one JVM, plus the boundary, stock-cache, key-cache-hit, late-SSTable, scan and switch-off arms. Cluster: 16,384 · 65,536 · 262,144 · 16,777,216 B and unset with `column_index_cache_size` 4 MiB, and 65,536 and 16,777,216 B with the stock 2 KiB; the arms C1, C2, C3 on the 65,536 B start. Not run: the optional upstream dtest. |
| **Audit bottom line** | **Ready** — 2026-10-07. No amendment to §9a was needed. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | the heap of one partition's index entry, by the estimate and by the entry's real weight (§4, §7, §8) |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | three limits plus a value above the data plus unset, in both tiers, plus the stock cache size (9b) |
| A. Core question | real resource measured, gap named | Met | the cached entry's `unsharedHeapSize()` (unit) and the key cache's size (cluster); 9d names that an entry that is not cached is not seen |
| A. Core question | usage driven to the limit and past it | Met | a ladder of partitions whose estimates straddle every limit (9a) |
| B. Logic | each step says what it establishes | Met | the "How this verifies" block matches 9a's steps |
| B. Logic | prediction in numbers or a clear relation | Met | accepted iff *est* ≤ *F* with *est* = *o*·*B* + bytes; largest admitted estimate within 1.42 of *F*; 1 : 4 : 16 |
| B. Logic | every plausible outcome has a row | Met | refuted (admitted above the limit, a cached entry after a refusal, formula wrong), not confirmed, scope, bypass, invalid |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | the two rules under the conclusions table |
| B. Logic | alternative explanations and controls | Met | single-row partition, no command, switch off, key cache emptied before every read, system-table lines filtered |
| C. Specific | a human can follow it from the intro and 9a | Met | |
| C. Specific | an AI can run 9b–9e without re-deriving the code path | Partly | the runner's language, the JMX client and the system-table noise of the Byteman rule were left to step 1; documentation amendments to 9c |
| C. Specific | knob, values, workload, commands, observables, stop conditions exact | Met | 9b–9e |
| D. Runnable | harness and prerequisites exist or are listed | Met | listed in 9c; written 2026-10-07 |
| D. Runnable | workload arithmetic reaches the limit | Met | estimates of the ladder run from 11,099 to 356,676 B against limits of 16,384 to 262,144 B; 10,684 rows (about 13 MB) |
| D. Runnable | load-bearing citations spot-checked | Met | every cited line was checked by a script when the case was filed; `RowIndexEntry.java:341-419`, `BigTableReader.java:265-275, 325, 343` and `MergeIterator.java:355-375` re-read in context |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | 9c: the runner is `cluster-run.py`; `Jmx.java` replaces `jmx.sh`; the Byteman rule fires for system-table deserializations (about 70 lines at start-up, and about 9 from every client connection), so the checks look at `ks1` lines only; the key cache must be warmed with system entries (a `probe` after the invalidation) before a before-snapshot | applied to the case file, dated 2026-10-07 (documentation only) | the client's connection reads system tables, which adds key-cache entries and `checksize` lines |
| 2 | 9a's "Default" bullet speaks of a `checksize` line with `active` true; the rule prints `command=` and fires **before** the thresholds-null gate, so the default control is judged by `RowIndexSize`'s count and the outcomes | **left for stage 3** — §9a may not be edited after a reading; see §3 defect 4 | the observable named is not what the rule prints |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-07 |
| Node (CloudLab name and type) | cluster tier: `pc66` (`node0.jason92-317394…`), 40 cores, 125 GiB, PERC H710P disk; unit tier: `pc80` (same type) |
| OS and kernel | Ubuntu 22.04.2, 5.15.0-187-generic (both) |
| JDK | openjdk 11.0.32.1 (both) |
| Ant | Apache Ant 1.10.12 (both) |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `b5f2a54210` (`cassandra-5.0.9`) on both nodes, built with `ant build-test` |
| Case-file commit / harness commit | `986cf19` / the commit that adds this file |
| Storage for node data | local disk `/` (`/dev/sda3`, 63 GB), under the clone's `data/`; `saved_caches/` wiped at every start |
| Full logs (path, outside the repo) | `pc66:~/stage4-logs/rirs/` (cluster), `pc80:~/stage4-logs/rirs/unit/` (unit) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | shakedown (`16m`) | 9e instrument (iii), (vi) | the harness stopped because a `checksize` line appeared before any `ks1` read: the Byteman rule fires for **every** deserialization, including system tables (73 lines at start-up) | the instrument checks look only at lines with a `ks1` command or an entry count of the ladder | 2026-10-07; documentation amendment to 9c (§9a unchanged); shakedown discarded, tier restarted | with this file |
| 2 | shakedown 2 (`16m`, partial) | 9d real resource | the client's connection reads system tables, which adds key-cache entries (entries 0→2 for one accepted read) and about 9 `checksize` lines (schema scans, `command=null`) to every read | after the invalidation a `probe` read warms the system entries before the "before" snapshot; lines are filtered on `ks1` | same; shakedown discarded, tier restarted | with this file |
| 3 | first `64k` start | 9e scenario C1 | the harness's own expectation "writes no `checksize` line" counted the connection's system-table lines, so it printed `NO`; the reading itself (no `ks1` line, entries and count unchanged) matched | the expectation ignores system-table lines | same; the `64k` start was rerun with the fixed script; the first run is kept at `run1/cluster/64k-first-run/` | with this file |
| 4 | — | 9a "Default" | the bullet names a `checksize` line with `active` true; the rule prints `command=` and fires before the thresholds-null gate: in the default control there are lines with `command=ks1.t` and `RowIndexSize`'s count stays 0 | the control is judged by the count and the outcomes (both as predicted); §9a is **not** edited | 2026-10-07; recommendation 2 for stage 3 | none |

Every reading below is from the runs after fixes 1 to 3, on the frozen version. (The six starts other than `64k` ran with the script as it was before fix 3, which differs only in the C1 expectation, executed on the `64k` start alone.)

## 4. Run 1

**Scope:** unit tier (one JVM), cluster tier (`16m`, `16k`, `64k`, `256k`, `s64k`, `s16m`, `none`; the bypass arms on `64k`). **Command logs:** `row_index_read_size_fail_threshold-checkSize-failThreshold/run1/` (`unit/run.out`, `cluster/<label>/summary.txt`, `readings.csv`, `checksize.trace`, `coordinator-warn-lines.txt`); `session.log` files stay on the node.

### 4.1 Readings

**Unit tier** (`run1/unit/run.out`; 144 checks, 0 MISMATCH)

| Test or assertion | Result | Evidence |
|---|---|---|
| BIG format; blocks per partition 20 · 40 · 80 · 160 · 320 · 640 · 1,280 (no command on the thread: not checked); one SSTable | ok | `blocks_pk*` |
| *o* = 88 B (IndexInfo 40 + ArrayClustering 24 + DeletionTime 24) | printed | `info o` |
| known answer at *F* = 1: every indexed partition is refused with `total entries` = *B* and `estimated to be` = 88·*B* + `total bytes` (2,219 · 4,439 · 8,879 · 17,760 · 35,520 · 71,040 · 142,080); the fail parameter equals it; the single-row partition is not refused and the `RowIndexSize` count does not move | ok | `known_*`, `single_row_*`, `info est` |
| boundary, *B* = 160 (*est* 17,760): *F* = *est*−1 refused, key cache entries 0, no cached position; *F* = *est* accepted, one entry, an `IndexedEntry` of 30,152 B | ok | `boundary_*` |
| ladder at *F* = 8,192 · 32,768 · 131,072 · 8,388,608 · unset: accepted iff *est* ≤ *F*, accepted set a prefix, refusals leave the key cache unchanged, unset leaves the count unchanged | ok | `ladder_*` |
| real weight: *w*(*B*) = 3,832 · 7,592 · 15,112 · 30,152 · 60,232 · 120,392 · 240,712 B; slope *w*/*est* 1.6935 to 1.6937 for every pair (linear); *w*/*est* = 1.694 | ok | `info slopes` |
| scenario S (stock 2 KiB, *F* = 32,768): same accepted set; the accepted partition with bytes above 2,048 is a `ShallowIndexedEntry` of 72 B; the refused partitions (bytes 7,360 to 29,440) are ones that would not have been built | ok | `S_*`, `info S` |
| C0: a direct `getRowIndexEntry()` with no command at *F* = 1 returns the entry | ok | `C0_*` |
| C1: at *F* = 131,072 the *B* = 320 partition is cached; with *F* = *est*−1 it completes (one entry, count unchanged); after the invalidation it is refused | ok | `C1_*` |
| C2: two SSTables (ck 0 to 9; ck 1000 to 1639, *est* 71,040), *F* = *est*−1: `ck >= 1000` refused; the full ascending read **completes** with 650 rows and the count rises by **one**; the full descending read is refused | ok | `C2_*` |
| C3: a full-range scan at *F* = 1 completes (2,541 rows), count unchanged | ok | `C3_*` |
| control: switch off, *F* = 1: not refused | ok | `switch_off_*` |

**Cluster tier** — one node, RF 1, 10,684 rows of 1,200 B in 11 partitions, `column_index_size` 1 KiB, one SSTable; *o* = 88 B, the 11 estimates 11,099 · 15,651 · 22,200 · 31,413 · 44,400 · 62,826 · 88,800 · 125,541 · 177,600 · 251,731 · 356,676 B (`run1/cluster/calibration.json`, from the `16m` start, from the `checksize` lines and the clients' warning text).

| *B* | *est* | 16,384 | 65,536 | 262,144 | 16 MiB | unset | stock cache 65,536 | stock cache 16 MiB | key-cache weight added, 4 MiB cache (`16m`) | key-cache weight added, stock (`s16m`) |
|---|---|---|---|---|---|---|---|---|---|---|
| 100 | 11,099 | accepted | accepted | accepted | accepted | accepted | accepted | accepted | 18,928 | 128 |
| 141 | 15,651 | accepted | accepted | accepted | accepted | accepted | accepted | accepted | 26,640 | 128 |
| 200 | 22,200 | refused | accepted | accepted | accepted | accepted | accepted | accepted | 37,728 | 128 |
| 283 | 31,413 | refused | accepted | accepted | accepted | accepted | accepted | accepted | 53,336 | 128 |
| 400 | 44,400 | refused | accepted | accepted | accepted | accepted | accepted | accepted | 75,328 | 128 |
| 566 | 62,826 | refused | accepted | accepted | accepted | accepted | accepted | accepted | 106,536 | 128 |
| 800 | 88,800 | refused | refused | accepted | accepted | accepted | refused | accepted | 150,528 | 128 |
| 1,131 | 125,541 | refused | refused | accepted | accepted | accepted | refused | accepted | 212,760 | 128 |
| 1,600 | 177,600 | refused | refused | accepted | accepted | accepted | refused | accepted | 300,928 | 128 |
| 2,263 | 251,731 | refused | refused | accepted | accepted | accepted | refused | accepted | 425,576 | 128 |
| 3,200 | 356,676 | refused | refused | refused | accepted | accepted | refused | accepted | 601,728 | 128 |

Every refusal gave the client `ReadFailure` with failure-map code `{127.0.0.1: 4}`, `RowIndexSizeAborts` +1, **no change in the key cache** (entries and size), and a coordinator WARN line `1 nodes loaded over <est> bytes in RowIndexEntry and aborted the query` (`coordinator-warn-lines.txt`). Every read that passed the gate, accepted or refused, raised `RowIndexSize`'s count by one; with both limits unset the count stayed 0 for all 11 reads (`none/readings.csv`). The key-cache columns are the difference of `Size` before and after the read (the entry's weight plus the key's).

| Capacity value | Run | Observable | Reading | Evidence |
|---|---|---|---|---|
| 16 MiB (`16m`) | calibration | *o* from the `checksize` lines | (estimate − bytes)/entries = 88 for all 11 partitions; all accepted | `16m/summary.txt` |
| 16,384 · 65,536 · 262,144 | A and B, the ladder | largest accepted *est* | 15,651 · 62,826 · 251,731 (ratios 4.01 and 4.01; each in (*F*/1.42, *F*]) | `*/summary.txt` `LARGEST ACCEPTED` |
| `s64k` | S | weight added by the 6 accepted partitions | 128 B each, whatever *B*; the 5 refused partitions (*B* ≥ 800) would also have been shallow | `s64k/readings.csv` |
| `s16m` | S | weight added, nothing refused | 128 B for all 11 partitions: the key cache's weight does not grow with *B* | `s16m/readings.csv` |
| `64k` | C1 | the *B* = 566 partition (*est* 62,826): first read accepted (cache entries 1→2); limit lowered over JMX to 62,825 B; second read | completes, entries 2→2, `RowIndexSize` count +0 (the two reads with the gate passed: +1 each), no `ks1.t` line and none with 566 entries in the trace; after `invalidatekeycache` the same read is refused (code 4, aborts +1) | `64k/summary.txt` |
| `64k` | C2 | `ks1.t2`: 2 SSTables (10 rows; 2,263 rows, *est* 251,731) | `ck >= 1000 LIMIT 1` refused; full ascending **completes** with 2,273 rows, the trace shows the 10-block entry with `command=ks1.t2` and the **2,263-block entry with `command=null`**; the full descending read is refused | |
| `64k` | C3 | `SELECT ck FROM ks1.t` at 16,384 B | completes with 10,684 rows although partitions with *est* above the limit exist; every `checksize` line has `command=null` | |
| `16m`, `none` | control | the 11 reads | all accepted | |

### 4.2 Conclusion and logic

1. **Validity** — valid. [observed: `summary.txt` of each start] The limit was reached: refusals at 16,384, 65,536, 262,144 B and at the stock 65,536 B, none at 16 MiB or unset. The hold-fixed settings: the yaml tail echoed at each start (`read_thresholds_enabled: true`, warn 1 B except `none`, the fail value, `column_index_size: 1KiB`, `column_index_cache_size: 4MiB` except the stock starts), protocol 5 and the setter check at the instrument step, one `Data.db` file, the idle control (no `ks1` `checksize` line in 10 s), `saved_caches/` wiped at every start. The unit tier asserted BIG, the block counts and the empty key cache before every read.
2. **Readings** — nothing unusual beyond the defects of §3. The estimate for a refused partition is read from the coordinator's WARN line and equals the Byteman line's `o`·`entries` + `bytes` (the calibration) [observed: `summary.txt` `CALIBRATION`, `coordinator-warn-lines.txt`].
3. **Matched row** — **Confirmed — the check enforces as traced, per entry, on its estimate.** [observed] Unit: the formula reproduces the message's estimate for every partition, the boundary pair behaves as `>` predicts, every accepted partition has *est* ≤ *F* and every refused one *est* > *F*, and a refused read leaves no cached entry. Cluster: at every limit a partition is accepted exactly when its estimate is at most the limit; the largest accepted estimate follows the knob (15,651 · 62,826 · 251,731, ratio 4.01 and 4.01, within the ladder's step of 1.41); every refusal has code 4, one meter increment, the coordinator's WARN line and an unchanged key cache, while an accepted read adds one entry whose weight grows linearly with *B* (slope 1.679 to 1.694 against the estimate). Also **bypass as recorded** (C0, C1, C2, C3, switch off) and **scope as recorded** (S): the key-cache hit is not checked (completes with the limit below its estimate), a read with no command is not checked, an SSTable opened after `executeLocally()` returned is not checked (the full ascending read of two SSTables completes while the same entry refuses `ck >= 1000` and the descending read), a range scan is not checked, nothing is checked with the switch off (unit); and at the stock cache size the accepted entries all weigh 128 B (72 B entry) whatever their block count, so the refused partitions would not have been built and the limit bounds no heap there.
4. **Excluded rows** — [observed] *Refuted: a partition with est above the limit is accepted, or a refused read leaves a cached entry* — no: 0 of 66 cluster reads at limits (and 0 in the unit ladder) broke the rule, and 0 refusals changed the key cache. *Refuted in part: the estimate is not o·entries + bytes, or the boundary is not `>`* — no: the known answer and the boundary pair match. *Refuted: est\* is the same at every value* — no. *Not confirmed: moves but lacks the guard's message or code 4* — no: every refusal has them. *Refuted in part: the late SSTable (C2) or the scan (C3) is refused* — no: both completed; the window analysis of §5 held. *Refuted in part: the cached read is refused after the limit is lowered (C1)* — no: it completed. *Invalid* — no row applies: the known answer holds, the key cache held only the one system entry (80 B) before every ladder read (after `invalidatekeycache` and the probe), BIG was selected, the Byteman rule loaded, the smallest limit refused some partitions and the largest did not.
5. **Observed vs. inferred** — [inferred: that the refused entry "would have been shallow" at the stock cache size rests on the shallow weights of the accepted entries and the serialized sizes above 2 KiB, not on observing a refused read's object]; [inferred: the lazy-opening mechanism behind C2 (lower-bound merge) — the observed facts are the `command=null` line for the late SSTable's entry and the completed read]; [inferred: the key cache's `Size` difference is the entry's weight plus the key's — the unit tier read the entry's own `unsharedHeapSize()`, and the two differ by 56 B in every pair].
6. **Deviations and gaps** — the optional upstream dtest and the master-switch-off control on a node were not run (the switch-off control ran in the unit tier); the `64k` start was run twice (the first kept as `64k-first-run`, superseded by defect 3); one node, RF 1, *N* = 1: the replica-to-spare behaviour, the `trackWarnings` mismatch and the `limit × N` multiplier are not tested; the compaction and key-cache-reload bypasses (a restart arm) are not tested; the abort's failure code requires protocol 5, which was available.
7. **Core question** — Usage followed the constraint and the constraint caps usage — of the **estimated** entry size: a partition's index entry is opened exactly when its estimated in-memory size is within the limit, the largest admitted estimate follows the limit (1 : 4 : 16 within the ladder's step), and an over-limit entry is never built or cached. What the cap means for heap depends on `column_index_cache_size`: with it large the cached entry's real weight is 1.69 times the estimate and follows the limit; at the stock 2 KiB every entry that passes weighs 128 B (shallow) and the limit bounds nothing in memory. And the cap is not on every path: the key-cache hit, an SSTable opened after the read command's setup returns, and the scan are not checked.

**Conclusion (one line):** **Confirmed** at both tiers — per entry, on an estimate, refusing before either object is built — with **bypass as recorded** (key-cache hit, late-opened SSTable, scan, no command) and **scope as recorded** (at the stock cache size the limit bounds no heap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

The numbers of §4 were recomputed from the raw files in `run1/` by [`run1/selfcheck.py`](row_index_read_size_fail_threshold-checkSize-failThreshold/run1/selfcheck.py); its output is `run1/selfcheck.txt` (20 lines, all "holds").

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt`: *o* equals the unit tier's; the yaml tails, one `Data.db` file and the setter check re-read in `summary.txt` |
| 2. Readings | yes | the coordinator's WARN estimates equal the calibration's for every refusal (`coordinator-warn-lines.txt`) |
| 3. Matched row | yes | accepted-iff-est ≤ *F* recomputed for all 7 starts; the largest-accepted ratios 4.01 and 4.01; the weight slope 1.679 to 1.694; the stock weights all 128 |
| 4. Excluded rows | yes | no refusal changed the key cache (recomputed from `readings.csv` columns `cache_entries_*`, `cache_size_*`) |
| 5. Observed vs. inferred | yes | the three inferred statements are labelled; the verdict's row does not depend on them |
| 6. Deviations and gaps | yes | listed |
| 7. Core question | yes | the steps follow the audited logic (hypothesis, test, logic 1 to 5) |

### 5.2 Run 2?

**No** (2026-10-07). The readings are exact (the estimate formula, the accepted-iff rule at 7 starts, the key-cache invariants) and agree between two tiers on two nodes; the bypasses confirmed at runtime (C1, C2, C3) were each measured in both tiers with the same sign; and the inferred statements of §4.2 part 5 do not carry the matched row.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

| Tier | Verdict | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed**; bypass as recorded (C0, C1, C2, C3, switch off); scope as recorded (S) | run 1 + self-check | 2026-10-07 |
| Cluster | **Confirmed**; bypass as recorded (C1, C2, C3); scope as recorded (S: the weight added is 128 B whatever *B*); the default control judged by count and outcomes (defect 4) | run 1 + self-check | 2026-10-07 |

§9a's own hash at the freeze: `196befcf90457333dc5dc23bab31b459fcf90f57`. **Feedback filed:** the case file's §10 "Stage-4 feedback" field and a dated amendment to §9c (documentation only); §5 and §8 are unchanged because the readings agree with them (§5's lazy-opening analysis is now observed on a node, §4.1 C2); recommendation 2 is left for stage 3.
