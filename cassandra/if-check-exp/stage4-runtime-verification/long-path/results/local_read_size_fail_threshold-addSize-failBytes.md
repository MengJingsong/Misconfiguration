# local_read_size_fail_threshold-addSize-failBytes — stage-4 results

> **Case:** [`local_read_size_fail_threshold-addSize-failBytes`](../../../stage3-ai-deep-read/long-path/cases/local_read_size_fail_threshold-addSize-failBytes.md)
>
> **Status:** verdict filed (run 1 and self-check; no run 2)
>
> **Path:** long. Unit tier and cluster tier, run 2026-10-07.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Commit `986cf19`, §9's hash `74f5a8e19e00350724c8bd8904f2bbb973d54d61` (`sed -n '/^## 9\. /,/^## 10\. /p' <case file> \| git hash-object --stdin`). §9a is frozen at this version and was **not** edited afterwards. Later, dated documentation-only amendments to §9c (the harness actually used) change §9's hash but not §9a's; the hash of §9a alone, `sed -n '/^### 9a\. /,/^### 9b\. /p'`, is recorded in §8. |
| **Harness** | [`../harness/local_read_size_fail_threshold-addSize-failBytes/`](../harness/local_read_size_fail_threshold-addSize-failBytes/): `LocalReadSizeGuardTest.java`, `unit-run.sh`, `make-node-yaml.sh`, `Alloc.java`, `read-alloc.btm`, `send-read.py`, `jmx.sh`, `cluster-run.py`; committed with this file (see `git log` for the folder). |
| **Tiers and values** | Unit: 65,536 · 262,144 · 1,048,576 · 8,388,608 B and unset, in one JVM. Cluster: 262,144 · 1,048,576 · 4,194,304 · 16,777,216 B and unset, one node start each. Not run: the optional upstream dtest, the master-switch-off control. |
| **Audit bottom line** | **Ready** — 2026-10-07. No amendment to §9a was needed. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | heap bytes of the rows one command builds and of the response buffer (§4, §7, §8) |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | three limits plus a value above the data plus unset, in both tiers (9b) |
| A. Core question | real resource measured, gap named | Met | bytes the thread allocates (unit `ThreadMXBean`, cluster Byteman); 9d names that allocated is not retained |
| A. Core question | usage driven to the limit and past it | Met | scenarios A and B read to `p*` and one row more (9a) |
| B. Logic | each step says what it establishes | Met | the "How this verifies" block matches 9a's steps |
| B. Logic | prediction in numbers or a clear relation | Met | *i\**(*F*), *T*(*i*) from measured *b0* and *h*; ratios 1 : 4 : 16 and 1 : 4 |
| B. Logic | every plausible outcome has a row | Met | refuted (completes at or above the limit; allocation keeps growing; flat), not confirmed, invalid, bypass |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | the two rules under the conclusions table |
| B. Logic | alternative explanations and controls | Met | slice versus names read, no-flag, warn twin, unlimited |
| C. Specific | a human can follow it from the intro and 9a | Met | |
| C. Specific | an AI can run 9b–9e without re-deriving the code path | Partly | the Byteman helper's class-path need and the runner's language were left to step 1; both are documentation amendments to 9c |
| C. Specific | knob, values, workload, commands, observables, stop conditions exact | Met | 9b–9e |
| D. Runnable | harness and prerequisites exist or are listed | Met | listed in 9c; written 2026-10-07 |
| D. Runnable | workload arithmetic reaches the limit | Met | *T*(*N*) is 9.7 MB against limits of at most 4 MiB; 2.4 MB in the unit tier against 1 MiB |
| D. Runnable | load-bearing citations spot-checked | Met | every cited line was checked by a script when the case was filed; `ReadCommand.java:715-724`, `BaseRows.java:133-157` and `SinglePartitionReadCommand.java:1062-1075` re-read in context |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | 9c: the runner is `cluster-run.py`, the Byteman helper must be on the boot class path | applied to the case file, dated 2026-10-07 (documentation only) | the node runs from the jar |
| 2 | 9d lists a trace event as a disallow signal; the harness does not collect it | applied (same amendment): the coordinator's WARN line carries the same number | `--trace` is best effort in the client |
| 3 | The C1 prediction says "within 10 %"; the response serialization that the abort skips makes the limited names read cheaper than the unlimited one | **left for stage 3** — §9a may not be edited after a reading | see §4.2 and §8 |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-07 |
| Node (CloudLab name and type) | `pc80` (`node0.jason92-318546…`), 40 cores, 125 GiB, PERC H710P disk |
| OS and kernel | Ubuntu 22.04.2, 5.15.0-187-generic |
| JDK | openjdk 11.0.32.1 |
| Ant | Apache Ant 1.10.12 |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `b5f2a54210` (`cassandra-5.0.9`), built with `ant build-test` |
| Case-file commit / harness commit | `986cf19` / the commit that adds this file |
| Storage for node data | local disk `/` (`/dev/sda3`, 63 GB), under the clone's `data/` |
| Full logs (path, outside the repo) | `pc80:~/stage4-logs/lrs/` (`unit/`, `16m/`, `256k/`, `1m/`, `4m/`, `none/`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | shakedown of the `16m` start, before the frozen run | 9c, `read-alloc.btm` | the helper class `stage4.Alloc` was compiled into `build/classes/main`, which is **not** on the node's class path (it runs from `build/apache-cassandra-5.0.9-SNAPSHOT.jar`): the rule never fired, no `read-alloc` line | helper compiled to a jar on the boot class path (`-Xbootclasspath/a:`); the tier restarted | 2026-10-07; documentation amendment to 9c, §9a unchanged | with this file |
| 2 | — | 9c table | `cluster-run.sh` and `jmx.sh`'s call pattern replaced by `cluster-run.py` | recorded | 2026-10-07; documentation | with this file |

The shakedown's readings were discarded; every reading below is from the runs after the fix, on the frozen version.

## 4. Run 1

**Scope:** unit tier (one JVM, 5 limit settings plus the arms), cluster tier (`16m`, `256k`, `1m`, `4m`, `none`). **Command logs:** `local_read_size_fail_threshold-addSize-failBytes/run1/` (`unit/run.out`, `cluster/<label>/summary.txt`, `readings.csv`, `alloc.trace`, `coordinator-warn-lines.txt`); the harness's `session.log` files stay on the node.

### 4.1 Readings

**Unit tier** (`run1/unit/run.out`; 43 checks, 42 ok, 1 MISMATCH)

| Test or assertion | Result | Evidence |
|---|---|---|
| table read: 2,000 rows, one SSTable; every row has the same heap size *h* = 1,216 B; *b0* = 72 B | ok | `info b0 72 h 1216` |
| known answer: warn param (limit 1 B) equals the mirror's *T*(*N*) = 2,432,072 | ok | `known_answer_T(N)` |
| *F* = 65,536 / 262,144 / 1,048,576: delivered rows 53 / 215 / 862 (= *i\**−1); *X* = 65,736 / 262,728 / 1,049,480 = *T*(*i\**) in both the message and the fail parameter; *F* ≤ *X* < *F* + *h* | ok | `stop_*` |
| boundary: *F* = *T*(100) → 99 rows delivered; *F* = *T*(100)+1 → 100 delivered, *X* = *T*(101) | ok | `boundary_*` |
| above the data (8,388,608): all 2,000 rows, no fail parameter | ok | `above_data_*` |
| allocation: Δ0 = 13,408 B; Δ(*F*) = 220,400 / 856,976 / 3,400,456 B; (Δ−Δ0) ratios 1 : 4.08 : 4.02 (predicted 4 and 4 within 15 %) | ok | `info ratios`, `alloc_ratio_4` |
| C1: names filter (*M* = 1,000) at *F* = 65,536 aborts; allocation 6,601,984 B limited vs 8,466,624 B unlimited = **78 %** (predicted within 10 %); the guarded slice of the same rows 226,472 B | **MISMATCH** (the 10 % prediction); `C1_names_aborts` ok, `C1_slice_alloc_small` ok | `info C1`, `C1_names_alloc_within_10pct` |
| C2: 20 pages of 100 rows (`forPaging()`) at 262,144: 2,000 rows, 0 aborts; at 65,536 the first page aborts after 53 rows | ok | `info C2` |
| C3: a row filter that matches nothing aborts at 262,144 with 0 rows delivered; unlimited it completes with 0 rows | ok | `C3_*` |
| controls: no `trackWarnings()` at 65,536 completes, all rows, no parameter; warn twin completes with warn param = *T*(*N*) | ok | `control_*` |

**Cluster tier** — one node, RF 1, 8,000 rows of 1,000 B in one SSTable, calibration *b0* = 72, *h* = 1,216 at every start (`run1/cluster/calibration.json`); *T*(*N*) = 9,728,072. Allocation = bytes the replica read thread allocated (`alloc.trace`).

| Capacity value | Run | Observable | Reading | Evidence |
|---|---|---|---|---|
| 262,144 (`256k`) | A `ck<215` | outcome, *X*, alloc | OK, 215 rows, *X* = 261,512 = *T*(215) < *F*; 846,336 B | `256k/summary.txt` |
| | B1 `ck<216` | outcome, *X*, code, meter, alloc | aborts, *X* = 262,728 = *T*(216) ≥ *F*, code `{127.0.0.1: 4}`, `LocalReadSizeAborts` 0→1; 938,000 B | |
| | B2 whole partition | same | aborts, *X* = 262,728, meter 1→2; 846,552 B (within 10 % of B1) | |
| 1,048,576 (`1m`) | A `ck<862` | | OK, *X* = 1,048,264 < *F*; 3,360,864 B | `1m/summary.txt` |
| | B1 `ck<863` / B2 | | aborts, *X* = 1,049,480 = *T*(863), code 4, meter +1 each; 3,439,104 / 3,350,944 B | |
| 4,194,304 (`4m`) | A `ck<3449` | | OK, *X* = 4,194,056 < *F*; 13,415,208 B | `4m/summary.txt` |
| | B1 `ck<3450` / B2 | | aborts, *X* = 4,195,272 = *T*(3450), code 4, meter +1 each; 13,454,448 / 13,363,144 B | |
| 16,777,216 (`16m`) | calibration, B2 | | `ck<100`, `ck<200` and the whole partition complete: *X* = 121,672 / 243,272 / 9,728,072; whole partition 28,281,776 B; no meter change | `16m/summary.txt` |
| unset (`none`) | B2 | | completes, 8,000 rows, no warn text (nothing counted); 28,306,096 B | `none/summary.txt` |
| all | C1 names (`ck IN`, *M* = 2,000) | | 256k aborts, 11,244,616 B; 1m aborts, 12,911,768 B; 4m completes, 14,697,792 B; unlimited 14,647,512 B (256k: **76.8 %**, 1m: 88.1 % of unlimited); the slice `ck<2000`: 849,472 B (256k), 3,353,104 B (1m), 7,027,640 B (unlimited) | `*/readings.csv` |
| all | C2 `fetch_size` 100 / 1000 | | 100: completes with 8,000 rows at 256k, 1m, 4m; 1000: aborts at 256k and 1m (first page), completes at 4m | |
| all | C3 filter | | aborts at 256k, 1m, 4m; completes with 0 rows at 16m and unset | |
| 256k, 1m, 4m | evidence | | the coordinator's WARN line `1 nodes loaded over <X> bytes and aborted the query` for every abort (6, 6 and 3 lines); the `LocalReadSizeAborts` meter counted every abort | `*/coordinator-warn-lines.txt` |

### 4.2 Conclusion and logic

1. **Validity** — valid. [observed: `cluster/*/summary.txt`] The limit was reached at 256k, 1m and 4m (aborts) and not at 16m or unset (completion). The hold-fixed settings: the yaml tail echoed at each start (`read_thresholds_enabled: true`, warn 1 B, the fail value) and no sibling limits set [observed: `summary.txt` first lines]; one SSTable [observed: `DATASET … Data.db files 1`]; protocol 5 [observed: `INSTRUMENT probe`]; calibration equal at every start [observed: `calibration equals the 16m run — yes`]; idle control [observed: no `read-alloc` line in 10 s]. The unit tier ran with the unit yaml's switch on and the warn and row-index limits cleared by the harness [observed: harness source].
2. **Readings** — one unusual reading: C1's allocation (below). The paged reads' *X* is 72 (the last, empty page's total) and is not used. The cluster allocation figures come from single reads, while the unit tier's five repeats were identical to the byte or within 1 %.
3. **Matched row** — **Confirmed — the check enforces as traced, per command.** [observed] Unit: the mirror equals the check's counter (`known_answer`), each read delivers exactly *i\**−1 rows and aborts with *X* = *T*(*i\**) (three limits), the `>=` boundary pair behaves as predicted, the allocation follows *i\** (ratios 4.08 and 4.02). Cluster: *p\** = 215 / 862 / 3,448 (ratio 1 : 4.01 : 16.04), *X* equals *T*(*i\**) exactly at every value, the whole-partition read aborts with the same *X* as the *i\**-row read (so *X* does not depend on *N*), every abort carries failure code 4, one meter increment and the coordinator's WARN line, and the replica thread's allocation for the whole-partition read at each limit equals (within 10 %) that of the *i\**-row read; its increments between values are 2,504,392 and 10,012,200 B, a ratio of 0.2501 (predicted 0.25), while the unlimited read allocates 28.3 MB, 33.4 times the 256k abort. In addition the **bypass row** applies for C1, C2 and the no-flag control: the names-filter read is not capped (11.2 MB at 256k against 0.85 MB for the guarded slice of the same rows, 13 times), a paged read of the whole partition completes at 256k although its total is far above the limit, and a read without the flag completes. **Deviation:** the C1 sub-prediction "within 10 % of the same read with the limit unset" did not hold in either tier (78 % and 76.8 % at the smallest limit, 88 % at 1m): the abort skips the later response serialization, which the prediction ignored; the bypass volume (the rows built before the guard) is the figure in §4.1.
4. **Excluded rows** — [observed] *Refuted: a read completes at or above the limit* — no: every completed read had *X* < *F* (A) and every read that reached *F* aborted. *Refuted: the aborted read keeps allocating as the partition grows* — no: whole-partition and *i\**-row allocations agree within 10 % at all three values. *Refuted: not the binding limit (X depends on N, or p\* the same at every value)* — no: *p\** moves 1 : 4 : 16 and *X* is the same for 216 rows and 8,000 rows. *Not confirmed: moves but lacks the guard's message or code 4* — no: every abort has the message, the code and the meter. *Refuted in part (C3): a filtered read that returns nothing is not aborted* — no: it aborted at 256k, 1m and 4m. *Invalid* — no row applies: the mirror equals the counter, the limit read back equals the value set, *T*(*N*) = 9.7 MB < 16 MiB, `getThreadAllocatedBytes` is supported, the rows came from one SSTable, and every failure was the guard's.
5. **Observed vs. inferred** — [inferred: allocated bytes are not retained bytes; the response buffer, the retained part, is ≤ the serialized rows and is not read directly (unit tier: serialized size 2,020,028 B for 2,000 rows, `responseBytes`)]; [inferred: the abort is attributed to the guard by its message and `X` equalities, not by a stack trace]; [inferred: the names read's materialization precedes the guard — from 13 times the allocation, not from a trace of `ImmutableBTreePartition.create`].
6. **Deviations and gaps** — the trace event of 9d was not collected (the client's `--trace` is best effort and was not used; the coordinator's WARN line prints the same number); the optional master-switch-off control and the upstream dtest were not run, so the "system keyspace" and "switch off" members of the bypass row are source-derived only; one node, RF 1, *N* = 1: the replica-to-spare behaviour and the `limit × N` multiplier are not tested; C1's tolerance is missed (above); memtable-resident rows were not tested (the data was flushed).
7. **Core question** — Usage followed the constraint and the constraint caps usage: the rows one local read command builds stop at the first row whose running heap total reaches the limit (*X* = *T*(*i\**), *F* ≤ *X* < *F* + *h*), the replica thread's allocation for an over-limit read equals that of a read of exactly *i\** rows and follows the limit one for one (ratio 0.2501 against 0.25), and the abort leaves with the guard's message, code `READ_SIZE` and meter. The cap is per command (paging escapes it), counts before the filter, and does not reach the rows of a names-filter read, which are built first.

**Conclusion (one line):** **Confirmed** at both tiers — per command, one row of overshoot, counted before the filter — with **bypass as recorded** for the names-filter read (C1), paging (C2) and the unflagged read, and the C1 magnitude sub-prediction missed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

The numbers of §4 were recomputed from the raw files in `run1/` by [`run1/selfcheck.py`](local_read_size_fail_threshold-addSize-failBytes/run1/selfcheck.py); its output is `run1/selfcheck.txt` (22 lines, all "holds").

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt`: calibration equals the unit tier's *b0* and *h*; the yaml, one SSTable and protocol 5 re-read in `summary.txt` |
| 2. Readings | yes | the C1 fractions (0.768, 0.881) recomputed from `readings.csv` |
| 3. Matched row | yes | *X* equalities and the 0.2501 ratio recomputed; the unit `ratios` line re-read |
| 4. Excluded rows | yes | no completed read has *X* ≥ *F*; whole and *i\**-row allocations within 10 % (9.75 % at 256k: close to the bound, recorded) |
| 5. Observed vs. inferred | yes | the three inferred statements are the ones the verdict does not depend on for its row |
| 6. Deviations and gaps | yes | listed |
| 7. Core question | yes | the steps from reading to answer follow the audited logic (hypothesis, test, logic 1 to 5) |

### 5.2 Run 2?

**No** (2026-10-07). The readings are exact equalities (*X* = *T*(*i\**)) reproduced at three values and in two tiers; the one bypass confirmed at runtime (names filter) was measured in both tiers and at two cluster limits with the same sign and size; and nothing in the matched row rests on a statement that §4.2 part 5 marks inferred.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

| Tier | Verdict | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed**; bypass as recorded (C1 names filter, C2 paging, unflagged read); C1's 10 % sub-prediction missed | run 1 + self-check | 2026-10-07 |
| Cluster | **Confirmed**; bypass as recorded (C1, C2); C1's 10 % sub-prediction missed; the master-switch-off and system-keyspace members of the bypass row not run | run 1 + self-check | 2026-10-07 |

§9a's own hash at the freeze: `740f120b05f79f8daad1fed111a8c9ab76795231`. **Feedback filed:** the case file's §10 "Stage-4 feedback" field and a dated amendment to §9c (documentation only); §5 and §8 are unchanged because the readings agree with them; recommendation 3 above is left for stage 3.
