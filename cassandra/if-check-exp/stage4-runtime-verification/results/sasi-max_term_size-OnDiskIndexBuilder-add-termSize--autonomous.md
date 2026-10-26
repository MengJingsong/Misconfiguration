# sasi-max_term_size-OnDiskIndexBuilder-add-termSize--autonomous — stage-4 results  <!-- file: results/sasi-max_term_size-OnDiskIndexBuilder-add-termSize--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`sasi-max_term_size-OnDiskIndexBuilder-add-termSize--autonomous`](../../stage3-ai-deep-read/cases/sasi-max_term_size-OnDiskIndexBuilder-add-termSize--autonomous.md)
>
> **Status:** self-checked; verdict filed (2026-10-25)
>
> **Outcome class:** true negative — the stage-3 estimate (negative) against the effect found below (does not cap) ([definition](../README.md#outcome-class)); fill it when both tiers are filed
>
> **Agent:** guided / autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Case file untracked at audit time (committed by the orchestrator); sha256 after the audit's amendments (B5) and before the feedback in section D was written: `0469ade488b27cff7541e17c0570ed16242006a432461737b6bbf8391f42084e`. Final sha256 after the section D feedback (2026-10-25): `d17d4a73624e23cbd856dcd275d5f8e0e071736cf59aa8fbf4fe7e329b78a3b1`. Frozen tables, written before any reading: B2f-g (from `**B2f.` to before `**B2h.`) sha256 `819debb87bc8014d022691ccd4dfc9a8bdc0f11ec97458c4aa94af1ed7fc357d`; B3f-g (from `**B3f.` to before `**B3h.`) sha256 `23f72a5f851b130ccd85f90adaa026df775e6cab32847882652fb466f1e6218b`. (Edits to B2f before any reading: the zero-length-file bracket (B5.2) and the S=1 value (B5.6); B2g/B3g rows unchanged.) Template note: **Guided file:** the commit that holds the case file, and the hash of §9's text (`sed -n '/^## 9\. /,/^## 10\. /p' <case file> \| git hash-object --stdin`), recorded after the audit's amendments; §9a is frozen at this version. **Autonomous file:** the commit that holds the file, and the sha256 of the whole file (`sha256sum`) recorded after the audit's amendments; this hash goes in `_INDEX.md` (column sha256) |
| **Harness** | `harness/sasi-max_term_size-OnDiskIndexBuilder-add-termSize--autonomous/` (written before run 1; committed by the orchestrator). Template note: committed paths under `harness/sasi-max_term_size-OnDiskIndexBuilder-add-termSize--autonomous/`, and their commit — or "none" |
| **Tiers and values** | Unit: term size {1,512,1023,1024,1025,4096} B x N=100,000; writer control cap {1,4,16} MB at S=512. Cluster: value size {1000,1023,1024,2000} B x 200,000 rows, index cap control 1 vs 64 MB at 1023 B (compaction). Template note: which tiers (unit / cluster) and capacity values this file covers |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: term bytes in the builder heap map and the SASI `.db` file; estimate in bytes (B2d, `OnDiskIndexBuilder.java:182,194`). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b/B3b: the constant is hard-coded (A1), so term/value size is varied (6 / 4 values around 1024) with a second knob as control; reason stated. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B2d/B3d: the estimate is a counter (jol-derived); real resource is index file bytes plus `GC.class_histogram`/heap, named as indicative. Gap named. |
| A. Core question | usage driven to the limit and past it | Met | Sizes 1023 (at the limit) and 1024-4096 (past it); control caps reached: 1 MiB cap needs 843 terms at S=1023 (B2c), 100,000 terms is far past (B5.3 for the flush cap, unreachable and unused). |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps with B2g/B3g rows. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact per-term 1243 B / 124.3e6; B3f relations (file ~ rows*(size+~100) under PREFIX; 0 at 1024). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | B2g/B3g cover step, refute, control-moved and control-flat, 1024 accepted; no row for 'rejected term still adds to estimate' (covered by step row). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Negative-claim: step at 1024 with rejection logs (disallow fired) plus linear growth below and a moving control. |
| B. Logic | alternative explanations and their controls | Met | B2h(a)-(d), B3h; two copies of the check separated (d). |
| C. Specific | a human can follow it from the intro and §9a | Met | Header table, A3 steps and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | Writer-test construction not spelled out (existing PerSSTableIndexWriterTest shows `sasi.getFlushObserver(descriptor, LifecycleTransaction.offline(OperationType.COMPACTION))`); harness supplies it. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Cluster loader and sampling interval left to the harness (python driver, 5 s samples); amendments B5.1-B5.4 added missing mode, heap and control observable. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | None exist; listed as step-1 work (test class, loader, run scripts). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | Unit arithmetic checked (B5). Cluster: CONTAINS file and heap sizes were wrong (52 GB, 0.82 GB longs; B5.1), 1 GiB flush cap unreachable (B5.3), 1 GiB heap too small (B5.4). Fixed by amendment; PREFIX runs fit 38 GB free. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | All cites in A1-A4/B2d re-read (B5 head); no wrong line numbers found; the Short.MAX_VALUE note at :171 is correct. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Run PREFIX mode only | Applied 2026-10-25 (B5.1), commit by orchestrator | CONTAINS file/heap sizes unreachable |
| 2 | Empty builder yields a zero-length file | Applied 2026-10-25 (B5.2) | `OnDiskIndexBuilder.java:247-251` |
| 3 | Judge the cap control on segment-flush count; 1 GiB flush cap unreachable | Applied 2026-10-25 (B5.3) | `PerSSTableIndexWriter.java:368` |
| 4 | Node heap 2 GiB | Applied 2026-10-25 (B5.4) | live-set arithmetic |
| 6 | S=1 prediction 22.1e6 impossible (62 distinct terms): 10,807,006 | Applied 2026-10-25 (B5.6) | duplicates add 108 B only |
| 5 | Message at `OnDiskIndexBuilder.java:171` prints `Short.MAX_VALUE`, not 1024 (cosmetic upstream inconsistency) | left for stage 3 | does not affect the claim |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-25 (UTC 2026-10-26 01:49 to 02:09) | not done |
| Node (CloudLab name and type) | `pc07` (`node0.jason92-320876...`), 40 cores, 251 GiB; shared with other agents (another agent's nodes on JMX 7320/7321 were running) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-od` by `copy-source.sh` at repository commit `1ae567d` (source clean); `ant build-test` 1 min 18 s; the unit tier ran with `ant testsome` in it, then the node ran from it with no further `ant` | |
| Case-file commit / harness commit | case file untracked at run time (sha256 in section 1); harness uncommitted (orchestrator commits) | |
| Storage for node data | local `/dev/sda3` (38 GB free before), `~/s4-od-data/<label>` (removed after each label) | |
| Full logs (path, outside the repo) | `pc07:~/stage4-logs/od/` (`run1-unit/`, `run1-cl/<label>/`, shakedowns `shake*` are not readings) | |

Ports for the node: JMX 7326, native 9348, storage 7026, loopback 127.0.26.1 (checked free with `ss -ltn` before every label by the script); Byteman 9326 not used.

## 3. Runbook defects

Fixes were made before any frozen reading, as audit amendments (case file B5); none stopped a run. Defects found while running:

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B2c, B3c | CONTAINS mode would build a suffix array (S entries per term): about 52 GB and 0.82 GB of longs at S=1023 | PREFIX only (B5.1) | 2026-10-25, before the freeze | orchestrator |
| 2 | audit | B2f | "file not created" at S>=1024; `finish` creates a zero-length file | B5.2 | 2026-10-25 | orchestrator |
| 3 | audit | B2f | S=1 cannot have 100,000 distinct terms (62 exist) | B5.6 | 2026-10-25 | orchestrator |
| 4 | audit | B3g/B3d | the cap control cannot be told apart by peak heap; the 1 GiB flush cap is unreachable at 200,000 rows; 1 GiB heap too small | B5.3, B5.4 | 2026-10-25 | orchestrator |
| 5 | run 1 | analyzer (not a frozen row) | `analyze_cluster.py` as run expected base-table `Data.db` >= rows*size and printed FAIL for v1024 and v2000; the table is LZ4-compressed and the values repeat a pad string, so the expectation was wrong (harness mistake, not a B3f row; B3f only says the base table "still grows") | replaced by "v1024 within 5% of v1023; v2000 larger than v1024"; the as-run output is kept in `run1/cluster/analysis-as-run.txt` | 2026-10-25 | n/a |
| 6 | self-check | `selfcheck.py` first attempt | assumed every "Flushed index segment" line came from the major compaction (background compactions during the load also write segments) and matched the JVM argument `HeapDumpOnOutOfMemoryError` as an OOM; format-string error | fixed; first attempt kept in `run1/selfcheck-first-attempt.txt` | 2026-10-25 | n/a |

## 4. Run 1

**Scope:** unit tier, all arms (6 term sizes at N=100,000; writer caps 1/4/16 MB with 229,197 adds; writer boundary 1023/1024 with 20,000 adds). Cluster tier, six labels in series of 200,000 rows each: v1000, v1023, v1024, v2000 (default cap) and c1, c64 (1023 bytes, `max_compaction_flush_memory_in_mb` 1 and 64). **Command log:** `results/sasi-max_term_size-OnDiskIndexBuilder-add-termSize--autonomous/run1/` (`unit/session.log`, `cluster/*/summary.json`).

### 4.1 Readings

**Unit tier** (all in `run1/unit/unit-results.csv`, `unit-estimates.csv`; `unit/analysis.txt` is 26/26 PASS)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| S=1 (62 terms), 512, 1023 at N=100,000: accepted, estimate | 100,000 each; 10,807,006 / 73,200,000 / 124,300,000 | `unit/unit-results.csv` rows `direct,1/512/1023` |
| S=1023 `finish` | true, file 341,748,424 bytes | same |
| S=1024, 1025, 4096 | 0 accepted, 100,000 ERROR lines each, estimate 0, `finish` false, file length 0 | same, `finish_returned` rows |
| Estimate series S=1023 | 10k steps equal 10k*1243*k | `unit/unit-estimates.csv` |
| Writer COMPACTION, same 229,197 adds at S=512 | cap 1/4/16 MB: segment cut every 1433 / 5730 / 22920 terms (estimate at cut 1,048,956 / 4,194,360 / 16,777,440 bytes), segments before complete 159 / 39 / 9, final file 290,904,576 bytes each | `unit/unit-results.csv`, `unit-estimates.csv` |
| Writer at S=1023 / 1024 (cap 16 MB, 20,000 adds) | 1 segment, 0 rejections / 0 segments, 20,000 INFO rejections, file length 0 | same |
| Heap delta (indicative, after GC) | S=1 16.4 MB, 512 89.8 MB, 1023 141.0 MB, 1024+ about 0 | same |

**Cluster tier** — 200,000 rows per label; default cap = 161,061,273 bytes of estimate (`IndexMode.java:60`). Index component bytes are the sum of `SI_*.db` after flush (all memtable flushes in the load plus the final `nodetool flush`) and after `nodetool compact`.

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| default | v1000 | index bytes after flush / compaction; rejection logs; compaction segment lines | 478,434,304 / 478,401,408; 0; 2 (load: 2 from a background compaction) | `cluster/v1000/summary.json` |
| default | v1023 | same | 683,488,680 / 683,459,872; 0; 2 | `cluster/v1023/summary.json` |
| default | v1024 | same, plus memtable-path "Can't add term" | 0 / 0 (all components 0 bytes); `Rejecting value (size` 200,000; `Can't add term` 200,000; ERROR `(value size` 0; base table Data.db 66.3 MB | `cluster/v1024/summary.json` |
| default | v2000 | same | 0 / 0; 200,000; 200,000; base table 136.8 MB | `cluster/v2000/summary.json` |
| 1 MB | c1 (1023 B) | `Flushed index segment` lines in the major compaction; index bytes after | 237 (load window: 159 from background compactions); 683,459,872 | `cluster/c1/summary.json`, `flushed-segment-lines.txt` |
| 64 MB | c64 (1023 B) | same | 4 (load window 3); 683,459,872 | `cluster/c64/summary.json` |
| all | six | heap used, peak in the load / flush / compact windows (MiB, indicative) | v1000 1398/327/1160; v1023 1162/339/1191; v1024 1160/1169/1216; v2000 1454/899/1200; c1 1242/346/1268; c64 1383/340/1243 | `cluster/*/heap.csv` |
| all | six | `GC.class_histogram` (OnDiskIndexBuilder instances) | taken at idle only (before flush, after compaction): no builder instance present, so the builder's heap was not read directly | `cluster/*/histogram-lines.txt` |

Per-sstable check inside v1023 (flush files nb-1/2/3): index 458.5 / 114.6 / 110.4 MB against data 44.3 / 11.1 / 10.7 MB, a constant ratio of about 10.3 [observed: `cluster/v1023/summary.json`].

### 4.2 Conclusion and logic

1. **Validity** — valid. The "limit" in this negative claim is reached from both sides: terms of 1023 bytes accepted and 1024 rejected in both tiers [observed: `unit/unit-results.csv`, `cluster/v1023|v1024/summary.json`]; the control cap was reached (237 segments at 1 MB) [observed: `cluster/c1/summary.json`]. Hold-fixed settings: heap 2 GiB (`node-cmdline.txt` in each cluster dir shows `-Xms2G -Xmx2G`), PREFIX mode (`loader.py` prints the options), 200,000 rows each [observed: `cluster/*/summary.json`]. The 1 GiB flush cap (the cap actually used by flushes) was never reached, by design (B5.3) [inferred: 200,000 x 1243 B = 249 MB < 1 GiB, and no flush produced a segment line].
2. **Readings** — the as-run cluster analyzer printed two FAILs for a base-table size expectation that ignored compression (defect 5 in section 3); not a frozen row. Peak heap does not separate the caps (c1 1268 MiB, c64 1243 MiB, compaction window) nor the sizes (G1 `used` includes garbage); heap is not read as evidence. The final index file after compaction is the same size at cap 1, cap 64 and default (683,459,872) [observed].
3. **Matched row** — Unit B2g rows 1 and 3 ("Estimate step from ~1.2e3 per term at 1023 to exactly 0 at 1024; linear in N elsewhere" and "Estimate grows past 1024*k for any k with S<1024 (e.g. 124 MB at N=100k)") and row 4 ("Writer: segments count rises as C falls, estimate per segment ~C"): estimate 124.3e6 at 1023 and exactly 0 at 1024 [observed: `unit/unit-results.csv`]; writer segments 159 / 39 / 9 for caps 1 / 4 / 16 MB at the same adds, with estimate at each cut within [C, C+732) [observed: `unit/unit-estimates.csv`]. Cluster B3g rows 1 and 3: index 683 MB at 1023 and 0 bytes at 1024 and 2000, with 200,000 rejections [observed]; control: segments 237 vs 4 for the same data [observed]. Row 3's "peak heap" wording was re-pointed to segment count before the run (B5.3); the heap peak itself did not move [observed], which is why the control is read on segments.
4. **Excluded rows** — Unit/cluster "estimate/index capped independent of N" (Refuted): the S=1023 estimate is 124.3e6 and the index file 341.7 MB (unit) and 683.5 MB (cluster), both far above any multiple of 1024 that a per-term bound would give, and per-sstable index size tracks per-sstable row count (constant 10.3 ratio) [observed]. "S=1024 accepted": excluded, 0 accepted, 0 estimate, zero-length file in both tiers and both copies of the check [observed]. "Control did not move / limit never reached" (Not confirmed): excluded for segment count (159/39/9; 237/4) [observed]; for peak heap the control did not move (see 2), which B5.3 says is indicative only.
5. **Observed vs. inferred** — inferred: (a) that the byte counts in the files stand for index memory (the estimate formula is jol-derived and the heap was not isolated: unit heap deltas 141 MB at 1023 vs estimate 124 MB are consistent but indicative); (b) the 1 GiB flush cap is the cap in force during flushes [inferred: `PerSSTableIndexWriter.java:368`]; (c) the rejection counts of 200,000 come from in-run counting of log text, and the raw log lines were not kept (only the filtered log), so the counts cannot be re-derived from files [observed in-run only]; the zero-byte index components are independent evidence of the same fact.
6. **Deviations and gaps** — CONTAINS mode not run (B5.1); node heap 2 GiB instead of 1 GiB (B5.4); the unit JVM is 1 GiB, not 512 MB (B5.5); the cap control uses one common workload of 229,197 adds for all three caps instead of "10 x C each" (harness choice before run 1, in `harness/.../README.md`); the cluster has one row count per label (a dose-response over rows exists only across the sstables of one label and in the unit tier's 10k-step series); the real heap of the builder was not measured; index file size is a step function of 4 KiB block packing (2,392 B/row at 1000 bytes, 3,417 B/row at 1023), not "size + ~100" as B3f's approximate relation says, which does not change any row. Background compactions during the load also write segments (counted in the load window).
7. **Core question** — Usage did not follow the constraint. The 1024-byte constant admits or drops a single term; below it, the index builder's estimate (124.3e6 for 100,000 terms) and the index file (342 MB unit, 683 MB cluster) are hundreds of thousands of times the 1024-byte figure and grow with the number of terms, and above it a term adds exactly nothing in either copy of the check [steps 1-4 above]. What did cap the builder in the same workload was the separate `maxMemorySize` (segments 159/39/9 at 1/4/16 MB, 237/4 at 1/64 MB in the cluster), so the control shows the workload could have shown a cap if one bound [step 3].

**Conclusion (one line):** B2g/B3g row "limit is a per-term filter only; usage does not follow it" — confirmed (claim: does not cap), with the control moving on segment count.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses the raw CSV, `summary.json`, `heap.csv`, `node-cmdline.txt` and `system.log.filtered` independently of the analyzers (output `run1/selfcheck.txt`: ALL HOLD; first attempt in `run1/selfcheck-first-attempt.txt` had script errors, fixed, section 3 defect 6).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `node-cmdline.txt` (Xms/Xmx 2G, jmx port 7326) and `loader.py` output for all six labels; 1023 accepted / 1024 rejected re-read from `unit-results.csv`. |
| 2. Readings | yes | `analysis-as-run.txt` vs `analysis-revised.txt` both kept; heap `heap.csv` covered each phase. |
| 3. Matched row | yes | segment lines re-counted per phase from `system.log.filtered`: v1000 2/0/2, c1 159/0/237, c64 3/0/4, v1024 and v2000 0; unit series recomputed by hand. |
| 4. Excluded rows | yes | SI components 0 bytes for v1024 and v2000 re-read from `summary.json`; 683,459,872 equal at all caps. |
| 5. Observed vs. inferred | yes, with a gap | the 200,000 rejection counts exist only as in-run counts (raw lines not kept); recorded in 4.2 part 6 and 5. |
| 6. Deviations and gaps | yes | listed. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | |

### 5.2 Run 2?

**No** (2026-10-25). The two tiers agree, the claim is negative with a moving control, and the decisive readings are exact (estimates equal their formulas, zero-byte files). The remaining inferred statement is the rejection-log count, which the zero-byte components cover.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 7. Comparison — only if run 2 was done

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** usage (builder heap estimate, real heap, index file size) does NOT follow `MAX_TERM_SIZE`: the constant only rejects individual terms of >= 1024 bytes; total usage scales with distinct term count and is capped only by `maxMemorySize` (B1). "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g rows 1, 3, 4) | does not cap | run 1 + self-check | 2026-10-25 |
| Cluster | Confirmed (B3g rows 1, 3, with the control read on segment count, B5.3) | does not cap | run 1 + self-check | 2026-10-25 |

**Positive control** (a negative-estimate file only): the writer's `maxMemorySize` (index option `max_compaction_flush_memory_in_mb`): unit, 159 / 39 / 9 segments at 1 / 4 / 16 MB for the same 229,197 adds, estimate at each cut in [C, C+732); cluster, 237 vs 4 segments at 1 vs 64 MB for the same 200,000 rows. Peak heap did not separate the caps, so the cluster control rests on segment count.

**Leftovers:** none running. Removed: `~/s4-od-data/*` per label and `unit-tmp`. Kept: `~/s4-od` (tree with `MaxTermSizeProbeTest.java` untracked in `test/unit/.../sasi/disk/` and a built `build/`), `~/stage4-logs/od/` (logs, shakedown outputs `shake`, `shake2`, `shake-cl`). No Byteman or JMX client left; the other agent's `s4-hb` nodes (JMX 7320/7321) are not mine.

**Feedback filed:** the case file's section D updated and amendments B5.1-B5.6 in B (case-file commit by the orchestrator, file sha256 in section 1 and below); upstream note (left for stage 3): `OnDiskIndexBuilder.java:171` prints `Short.MAX_VALUE` as the maximum size.
