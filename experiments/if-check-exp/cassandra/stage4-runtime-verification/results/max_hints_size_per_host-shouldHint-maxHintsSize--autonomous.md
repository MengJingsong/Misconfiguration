# max_hints_size_per_host-shouldHint-maxHintsSize--autonomous — stage-4 results  <!-- file: results/max_hints_size_per_host-shouldHint-maxHintsSize--autonomous.md -->

> **Case:** [`max_hints_size_per_host-shouldHint-maxHintsSize--autonomous`](../../stage3-ai-deep-read/cases/max_hints_size_per_host-shouldHint-maxHintsSize--autonomous.md)
>
> **Status:** verdict filed (2026-10-27)
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/max_hints_size_per_host-shouldHint-maxHintsSize--autonomous/`](../harness/max_hints_size_per_host-shouldHint-maxHintsSize--autonomous/).
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e;
> the case file's feedback section is its section D. Session: Claude Opus 5.5 (claude-opus-5-5), advisor-run, on the advisor's Mac.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Branch `advisor-run`, uncommitted on 2026-10-27 (last commit holding the file: `df78e44`'s tree, as filed with sha256 `ddd8e09b…680b`). Frozen after the audit's 17 amendments: sha256 `e4410a2f78b19fe5cb2d7c86154145f19f234f452f3a1b17278f95aaeeb2b477`. After one runbook fix found by the shakedown (B3d (i), an observable in no relation): sha256 `5975b2434bdc7380764995440dec9b35a7c4008fea3466ee6aca16b68e9937a2`; **both tiers of run 1 ran at this version**. Both rows are in `_INDEX.md` §4. Section D is filled after the last hash. |
| **Harness** | `harness/max_hints_size_per_host-shouldHint-maxHintsSize--autonomous/`: `HintsSizeCapUnitTest.java` (unit test, copied into the clone only for the run), `unit-run.sh`, `HintsSizeSampler.java` (JMX + file-size sampler), `cluster-run.sh`; self-check `results/max_hints_size_per_host-shouldHint-maxHintsSize--autonomous/run1/selfcheck.py`. Not committed (the user has not asked for a commit). `unit-run.sh` and `cluster-run.sh` adapt the structure and node start/stop functions of `harness/maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous/` (`unit-run.sh`, `cluster-run.sh`), and `HintsSizeSampler.java` its JMX read pattern (`HintsSampler.java`); no value or derivation was taken from that case. |
| **Tiers and values** | Unit: C ∈ {0, 1, 4, 16} MiB, N = 20,000 hints of a 4,096-byte value, flush every 256. Cluster: two nodes on loopback, C ∈ {0, 32, 128, 512} MiB on the coordinator, 1,000,000 stress writes (1,024-byte value, RF = 2, CL = ONE) with the replica down. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: on-disk size of one host's hint files on the coordinator. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b {0 (default), 1, 4, 16} MiB; B3b {0, 32, 128, 512} MiB. |
| A. Core question | real resource measured, not only the counter | Met | B2d `File.length()` sum next to the operand; B3d file-length sum (`du`). Gap: the in-memory buffer between flushes is not observable (named in B2d/B3d). |
| A. Core question | usage driven to the limit and past it | Met | Unit 20,000 × ~4.1 KB ≈ 80 MiB ≫ 16 MiB; cluster ≈ 1.1 GB ≫ 512 MiB. |
| B. Logic | each step says what it establishes | Partly | B2c/B3c say what the workload does; the disallow evidence was not tied to a step (amended B2d, B3d (ii)). |
| B. Logic | prediction stated in numbers or a clear relation | Partly | B2f ranges were approximate and in mixed units ("80–85 MiB" vs 20,000 × (4 KiB + overhead) ≈ 79 MiB); B2e's bound C + 1 MiB is smaller than one batch of 256 × h > 1 MiB; B3f approximate. Amended B2e, B2f, B3f to exact relations derived from source. |
| B. Logic | every plausible outcome has a conclusions row | Partly | B2g/B3g lacked "limit never reached" (cluster), "refused for another reason", "counter capped, real grows" (unit, implicit in row 3). Rows added (B2g, B3g amendments). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Not met | Row 1 of B2g/B3g required only the plateau. Amended: unit — rejected ≥ 1 with the operand at the first rejection > C; cluster — trace events with the size message (`StorageProxy.java:2494`) and TotalHints < writes. |
| B. Logic | alternative explanations and their controls | Met | C = 0 positive control in both tiers; batchlog bypass excluded by plain writes (B3h); hint window 3 h. |
| C. Specific | a human can follow it from the intro and §9a | Met | A3 and B1 state the mechanism and the soft overshoot. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Not met | B2c calls `StorageProxy.instance.getHintsInProgress()`, which does not exist at the tag; B2e reuses one host id across C, but `deleteAllHints()` keeps the open writer's file (`HintsStore.java:167-181`, `HintsCatalog.java:126`), so every C after the control would reject from the first hint. Amended B2c (i), (iii). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | B2b file size "if accessible"; loop bound "0 … 20,000"; B3b `sjk`; B3c warm-up adds 50,000 hinted writes (`StressAction.java:105-110`); B3d `du -cb` (GNU) and trace optional; B3e reset "restart or wipe". Amended. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | `/local` paths, `--depth 1` clone, `ant jar` replaced by this host's clone `$W/cassandra-run48` and `build-test` (B2a, B3a, B4). |
| D. Runnable | workload arithmetic reaches the limit | Met | Unit ≈ 80 MiB in one 128 MiB file (no rollover); cluster ≈ 1.1 GB on 125 GiB free disk; 2 × 2 GiB heaps on 32 GiB. |
| D. Runnable | load-bearing citations spot-checked | Met | `StorageProxy.java:2442-2502` (check, strict `>`, trace at `:2494`), `DatabaseDescriptor.java:3590-3603`, `Config.java:448`, `HintsService.java:79,110,253-259`, `HintsStore.java:260-271`, `HintsDescriptor.java:230-243`, `HintsWriter.java:84,269-275` all match the clone at `b5f2a54210`. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a/B3a/B4: this host's clone, paths, ring (loopback, `auto_bootstrap: false`, JMX 7199/7299) | applied, amendment 2026-10-27 | filed paths do not exist here |
| 2 | B2b: leave `max_hints_file_size` at 128 MiB | applied | "if accessible" was open |
| 3 | B2c: wait on `StorageMetrics.totalHintsInProgress`; N = 20,000 exactly; one fake endpoint and host id per C | applied | missing method; open writer survives `deleteAllHints()` |
| 4 | B2d: exact h from the serializer, 42-byte header, operand at first rejection | applied | exact predictions and disallow evidence |
| 5 | B2e/B2f: bound C·2^20 < final ≤ C·2^20 + 256·h; final = 42 + admitted·h; ordering | applied | filed bound smaller than one batch |
| 6 | B2g/B3g: row 1 requires disallow evidence; rows added | applied | group B |
| 7 | B2h: `pauseDispatch`, `excise` in `finally` | applied | cleanup order |
| 8 | B3b: C in n1's yaml per fresh round, read back over JMX | applied | `sjk` unreliable here |
| 9 | B3c: `no-warmup`; exact command; stress creates the table | applied | warm-up adds 50,000 hinted writes |
| 10 | B3d: file-length sum instead of `du -cb`; trace probability 0.001 in every round with a COPY export; TotalHints sampled every 5 s | applied | GNU tool; disallow evidence |
| 11 | B3e: exact per-round sequence, wipe and recreate | applied | order and reset open |
| 12 | B3f: exact bands (C = 0 in [1.0, 1.2]·10^9 B; C < du ≤ C + 100 MiB; ordering) | applied | approximate values |
| 13 | B3h: DN check after the run | applied | implied only |
| 14 | Stage 3: say that `deleteAllHints`/`truncatehints` keep the file being written | left for stage 3 | a fact for A3/A4, not needed for the run |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 01:48, cluster 01:48–01:58 local time) |
| Node | `yangwang-mbp`, the advisor's MacBook Pro (Apple T6000, arm64), single host; 10 cores, 32 GiB (`hw.memsize` 34359738368) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 (xnu-13432.1.9~1) |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64) |
| Ant | Apache Ant 1.10.18 |
| Local `cassandra-src` clone commit | `$W/cassandra-run48` (`W=~/Library/Caches/stage4`), fresh `git clone --branch cassandra-5.0.9 ~/cassandra-src`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`; `ant -Dlocal.repository=$W/m2 build-test` BUILD SUCCESSFUL in 52 s; `git status` clean after the runs |
| Case-file commit / harness commit | case file uncommitted at sha256 `5975b243…37a2` (on `df78e44`); harness uncommitted |
| Storage for node data | internal SSD, APFS `/dev/disk3s1`, 125 GiB free; node files `$W/node-mhs48/n1|n2`, removed after each round |
| Loopback / ports | `127.0.0.1`–`127.0.0.3` on `lo0`; 7000, 7199, 7299, 9042, 9091 free before the run |
| Full logs (outside the repo) | `$W/logs/max_hints_size_per_host-shouldHint/` (`build-test.log`, `unit-shake/`, `unit-r1/`, `cluster-shake/`, `cluster-r1/`) |

Machine facts relied on: workspace `$W` and `env.sh`; unsandboxed commands; `-Dlocal.repository=$W/m2` on every ant call; no `setsid` (nodes started as tracked background processes with `bin/cassandra -f`); `auto_bootstrap: false` on both nodes (zero-copy streaming fails here); BSD tools (no `du -cb`, so a Java file-length sum; `sed -i ''`); a JMX client instead of `nodetool sjk`; cassandra-stress warm-up of min(50,000, n/4) unless `no-warmup`; test stdout in `build/test/logs/**/TEST-<class>.log`; `pkill`/`pgrep` patterns written with `Cassandra[D]aemon`; long steps in the background; self-check written before readings and run end to end on the shakedown output.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| 1 | shakedown before run 1 (cluster, n = 60,000, C ∈ {0, 16}) | B3d (i) as amended at the audit | The audit amendment named the per-host created-hints counter `type=HintedHandOffManager`; it is `type=HintsService` (`HintedHandoffMetrics.java:43,53`), so the sampler read 0 | sampler reads `type=HintsService`; dated runbook fix in B3d | 2026-10-27; B3f/B3g unchanged (the observable is in no relation); no run-1 reading existed | sha256 `5975b243…37a2` |

Erratum (no effect, not a defect): amended B2c (ii) says "79 batches of 256 and one of 32"; 20,000 = 78 × 256 + 32, so the loop makes **78** batches of 256 and one of 32, **79 flushes** in all. The harness and the self-check use the formula (flush after every 256th iteration and after the last), and the run shows 79 flushes per C (`run1/unit/stdout.txt`, `flushes=79`). No prediction depends on the count.

## 4. Run 1

**Scope:** unit tier (C = 0, 1, 4, 16 MiB) and cluster tier (C = 0, 32, 128, 512 MiB), both at sha256 `5975b243…37a2`. **Command logs:** `max_hints_size_per_host-shouldHint-maxHintsSize--autonomous/run1/unit/commands.log`, `run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/stdout.txt`, `summary.txt`, JUnit XML; h = 4,161 B for every mutation, header 42 B)

| C (MiB) | admitted | rejected | operand at 1st rejection (index) | final operand = dirBytes (B) | C·2^20 + 256·h (B) | 42 + admitted·h | Evidence |
|---|---|---|---|---|---|---|---|
| 0 | 20,000 | 0 | — | 83,220,042 (79.37 MiB) | — | 83,220,042 | `run1/unit/summary.txt` (END C=0) |
| 1 | 256 | 19,744 | 1,065,258 (256) | 1,065,258 | 2,113,792 | 1,065,258 | END C=1 |
| 4 | 1,024 | 18,976 | 4,260,906 (1,024) | 4,260,906 | 5,259,520 | 4,260,906 | END C=4 |
| 16 | 4,096 | 15,904 | 17,043,498 (4,096) | 17,043,498 | 17,842,432 | 17,043,498 | END C=16 |

Operand = dirBytes after every one of the 79 flushes in every C (`eq_all_rows=true`; re-checked row by row by the self-check). One file per C; `excise` left 0 bytes; knob read back as C. JUnit: 1 test, 0 failures, 0 errors. All harness relations PASS (`DONE relation_fails=0`).

**Cluster tier** (`run1/cluster/C<v>/`; du = sum of file lengths of n2's `*.hints` files on n1, read 5 s after stress ended)

| C (MiB) | Run | du_final (B) | du_final − C·2^20 | TotalHints final | size-message trace events / all events | stress (partitions, errors, rate) | Evidence |
|---|---|---|---|---|---|---|---|
| 0 | control | 1,098,314,487 (1,047.4 MiB) | — | 1,005,365 | 0 / 3,219 | 1,000,000, 0, 48,789 op/s | `C0/final.txt`, `C0/sampler.csv`, `C0/trace-events-excerpt.txt`, `C0/stress.out` |
| 32 | A | 57,567,347 (54.90 MiB) | 24,012,915 (22.90 MiB) | 52,674 | 950 / 3,983 | 1,000,000, 0, 43,151 op/s | `C32/…` |
| 128 | B | 153,926,135 (146.80 MiB) | 19,708,407 (18.80 MiB) | 140,871 | 857 / 3,851 | 1,000,000, 0, 46,155 op/s | `C128/…` |
| 512 | C | 583,899,955 (556.85 MiB) | 47,029,043 (44.85 MiB) | 534,356 | 456 / 3,408 | 1,000,000, 0, 45,663 op/s | `C512/…` |

Per round: pre-stress du = 0 after `truncatehints`, `MaxHintsSizePerHostInMiB` read back = C before and after, n2 `DN` before and after stress, trace probability 0.001, `Hints_created-/127.0.0.2:7000` = TotalHints (`C<v>/pre.txt`, `final.txt`, `status-pre.txt`, `status-post.txt`, `traceprob.txt`). Sampler (`C<v>/sampler.csv`, every 5 s): with C > 0 du and TotalHints stop changing within one or two samples after the first non-zero sample and stay flat to the end (C = 32: 57,567,347 from the first non-zero sample on; C = 128: 125,842,143 then 153,926,135 flat; C = 512: 109,064,195, 369,095,392, then 583,899,955 flat); with C = 0 du rises at every sample to 1,098,314,487. The size-message trace events report the cap and the operand (`run1/cluster/trace-size-messages.txt`): the first refusals saw an operand just above C (C = 32: 41,946,702; C = 128: 134,231,635; C = 512: 536,919,278), and most saw the final du exactly (948/950, 831/857, 419/456).

### 4.2 Conclusion and logic

1. **Validity.** The limit was reached and passed for every C > 0 in both tiers (unit final > C; cluster du_final > C) [observed: `run1/unit/summary.txt`, `run1/cluster/C<v>/final.txt`]. Held settings: unit — knob read back = C, file size 128 MiB, one file, hinted handoff on, window 3 h [observed: `summary.txt` START/BEGIN]; cluster — yaml lines `hints_flush_period: 1000ms`, `max_hints_file_size: 8MiB`, `max_hint_window: 3h`, `auto_hints_cleanup_enabled: false`, `max_hints_size_per_host: <C>MiB` [observed: `C<v>/n1-yaml.diff`], JMX read-back = C [observed: `pre.txt`, `final.txt`], n2 DN throughout [observed: `status-pre.txt`, `status-post.txt`], stress 1,000,000 partitions with 0 errors [observed: `stress.out`]. The run is valid.
2. **Readings.** No gap or contradiction. Two things beyond the predictions: in the unit tier every refusal happened exactly at a batch boundary (admitted = 256·k), because no timed 10 s flush fell inside the 3 s test [inferred: flush period 10,000 ms in START, test time 2.96 s in the JUnit line]; in the cluster tier one sampler row (C = 128, epoch_ms 1793080518588) shows TotalHints 129,713 with only 125,842,143 B on disk, i.e. hints created but not yet flushed — the unobservable buffer content the design names [observed: `C128/sampler.csv`; inferred: ≈ 1.09 KB per hint at C = 0].
3. **Matched row.** Unit B2g row 1, "Plateau at C + ≤ 1 flush batch for each C > 0, linear growth for C = 0 — claim holds", with every amended B2f item: (a) C = 0 admitted 20,000, final 83,220,042 = 42 + 20,000 × 4,161; (b) for C = 1, 4, 16 rejected ≥ 1, operand at first rejection 1,065,258 / 4,260,906 / 17,043,498 > C·2^20, and C·2^20 < final ≤ C·2^20 + 256·h; (c) operand = dirBytes after every flush and final = 42 + admitted·h; (d) 1,065,258 < 4,260,906 < 17,043,498 < 83,220,042 [observed: `run1/unit/stdout.txt`, `summary.txt`]. Cluster B3g row 1, "du plateaus near C (overshoot ≤ 100 MiB) for every C > 0 while C = 0 grows to ~1 GB — claim confirmed", with every amended B3f item: (a) C = 0 du_final 1,098,314,487 ∈ [1.0, 1.2]·10^9, TotalHints 1,005,365 ≥ 1,000,000, 0 size-message events; (b) for C = 32, 128, 512: overshoot 22.90, 18.80, 44.85 MiB ∈ (0, 100] MiB, TotalHints 52,674 / 140,871 / 534,356 < 1,000,000, 950 / 857 / 456 size-message events; (c) 57.6 M < 153.9 M < 583.9 M < 1,098.3 M bytes [observed: `run1/cluster/C<v>/final.txt`, `trace-events-excerpt.txt`, `stress.out`].
4. **Excluded rows.** Unit: "keeps growing past C + 1 batch" (Refuted) — every final ≤ C + 256·h and no hint was admitted after the first rejection [observed: ROW lines]; "operand ≠ dirBytes" (Refuted in mechanism) and the added "counter capped, real resource grows" — equal at all 79 × 4 flush rows [observed]; "C = 0 also plateaus" — C = 0 grew linearly to 83.2 MB with 0 rejections [observed]; "operand never reaches C" — it passed C in every C > 0 [observed]; added "refused with operand ≤ C" — every first-rejection operand > C [observed]. Cluster: "grows past C + 100 MiB and keeps tracking volume" (Refuted) — max sample per round ≤ C + 44.9 MiB and flat after the cap [observed: `sampler.csv`]; "plateau does not scale with C" — finals ordered with C [observed]; "C = 0 does not grow" — 1.098 GB [observed]; added "limit never reached" — du_final > C every round; "no disallow evidence" — ≥ 456 size-message events per C > 0; "n2 not DN / stress errors" — DN before and after, 0 errors [observed].
5. **Observed vs. inferred.** The conclusion rests on observed readings only. Inferred and not load-bearing: that refusals fell on batch boundaries because no timed flush intervened (part 2); that the C = 128 sampler row shows buffered, not-yet-flushed hints (part 2); that the size-message events come from `StorageProxy.java:2494` (the message text is unique to that line; checked in the source).
6. **Deviations and gaps.** Erratum in the amended B2c (ii) text (78, not 79, full batches), no effect (§3). The in-memory buffer content is not observed (named by the design). The cluster overshoot was measured once per C at one write rate (≈ 45,000 writes/s, ≈ 50 MB/s of hints); the B3f bound (≤ 100 MiB) comes from the buffer capacity, not from the rate, and the readings stay under half of it. TotalHints includes the hints of the traced sessions' `system_traces` writes (5,365 at C = 0), which the design anticipates.
7. **Core question.** Hypothesis (B1): with C > 0 the dead host's hint files stop growing at C plus a bounded overshoot; with C = 0 they grow with the write volume. Test and logic (B2b–B2e, B3b–B3e): the unit tier shows the cap binding on the operand with the real file size equal to it, refusal starting exactly when the operand passes C, and a final size within one batch of C (parts 1, 3); the cluster tier shows the same on a real coordinator: with the same 1,000,000 writes the files grow to 1.10 GB uncapped but stop at 54.9, 146.8 and 556.9 MiB for caps of 32, 128 and 512 MiB, while the refusal trace fires and TotalHints stops (parts 1, 3, 4). **Usage follows the constraint and the constraint caps it, softly: the overshoot (one batch in the unit tier; 19–45 MiB in the cluster tier) comes from the stale, flush-updated operand, as A3 predicted.**

**Conclusion (one line):** unit — B2g row 1, claim holds — confirmed; cluster — B3g row 1, claim confirmed — confirmed.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` re-parses the raw files (the unit test log's `HSC` lines and JUnit XML; per cluster round `pre.txt`, `final.txt`, `sampler.csv`, `status-*.txt`, `stress.out`, `n1-yaml.diff`, `traceprob.txt`, `trace-events.csv`, `times.txt`) and recomputes every amended B2f/B3f relation without using the harness's PASS/FAIL lines. It was written before run 1 and run end to end on the shakedown outputs (unit `unit-shake`, cluster `cluster-shake`: 0 failed, exit 0). On run 1: **159 checks, 0 failed, exit status 0** (76 unit, 83 cluster); output `run1/selfcheck.out`.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: knob read-backs, yaml lines, DN before/after, 0 stress errors and 1,000,000 partitions, pre du = 0 — all PASS. |
| 2. Readings | yes | Re-read `C128/sampler.csv` row 1793080518588: 125,842,143 B, 129,713 hints; `summary.txt` START flush_period_ms=10000; JUnit 2.962 s. |
| 3. Matched row | yes | Every B2f (a)–(d) and B3f (a)–(c) relation recomputed from raw rows: PASS. |
| 4. Excluded rows | yes | No admission after the first rejection (row-by-row), every sample ≤ C + 100 MiB, ordering, ≥ 1 size event — PASS; the excluded rows' conditions are the negations. |
| 5. Observed vs. inferred | yes | The three inferences are not used by any relation; the message text appears only at `StorageProxy.java:2494` (grep of the clone's `src/`). |
| 6. Deviations and gaps | yes | The 79-flush count is from the formula: the self-check expects ⌈20,000/256⌉ = 79 rows and finds 79 per C. |
| 7. Core question | yes | Ceiling follows the knob in both tiers with direct disallow evidence (rejections with operand > C; size-message traces) and the C = 0 control growing. |

### 5.2 Run 2?

**No** — 2026-10-27. The conclusion rests on observed readings only, every self-check part holds, and the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):** With `max_hints_size_per_host = C` > 0 and one target host down, the on-disk size of that host's hint files on the coordinator stops growing at C plus a bounded overshoot (≤ one flush period of hint traffic plus ≤ 3 hint buffers). With C = 0 it grows in proportion to the write volume.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1) — final size = 42 + admitted·h, in (C, C + 256·h] for C = 1, 4, 16 MiB; refusals start when the operand passes C; C = 0 admits all 20,000 | caps | run 1 + self-check | 2026-10-27 |
| Cluster | Confirmed (B3g row 1) — du_final 54.9 / 146.8 / 556.9 MiB at C = 32 / 128 / 512 MiB (overshoot 19–45 MiB ≤ 100 MiB), 1.098 GB at C = 0; size-message traces 950 / 857 / 456 | caps | run 1 + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D updated (uncommitted, after sha256 `5975b243…37a2`); B2a–B4 carry the 17 dated audit amendments and one dated runbook fix (B3d (i)); `_INDEX.md` §4 has two new rows and §1's Stage 4 column for this file is filled. Recommendation 14 (the open writer's file survives `deleteAllHints`/`truncatehints`) is left for stage 3.
