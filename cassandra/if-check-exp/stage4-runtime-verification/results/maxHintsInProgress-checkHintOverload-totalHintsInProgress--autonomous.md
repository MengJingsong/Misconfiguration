# maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous — stage-4 results  <!-- file: results/maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous.md; the stem ends in --guided or --autonomous -->
> **Case:** [`maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous`](../../stage3-ai-deep-read/cases/maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous.md)
>
> **Status:** **Closed 2026-10-21: unit Confirmed, cluster Confirmed, does not cap** (estimate negative, matched). One sub-prediction missed: F-MAX's old-gen peak was 2.2 × O-MAX's, from GC timing. No run 2.
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
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
| **Case-file version** | Autonomous file. As filed: sha256 `2cda58a133d25f3aa3b6546739289d9d525cfcc178557e647b4769f8249e39e4`. After the audit's amendments R1–R6 (the frozen version, `sha256sum` at 2026-10-21 11:45 EDT, before any harness or run): **`af8d24c24d212b7c05896cec190eeeaa3eb6205ad75a378c0f69f80999dc3312`** (copy `~/stage4-logs/mhp/case-file-frozen.md`). Commit holding the file: **none**, because the case file is untracked in the working tree (filed the same day, not committed). After section D: `a8405af450f7f934e88f5b869ece4b16f85ea9d4145525425ccb7ac699c15dd6`. |
| **Harness** | [`harness/maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous/`](../harness/maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous/README.md): `hintsInProgress-LoadingCache.diff` (the positive-control patch), `HintOverloadCheckTest.java` + `unit-run.sh` (B2), `jmx.jsh` (the filed sampler/setter, unchanged), `Jmx.java`, `cluster-run.py` (B3), `selfcheck.py`. Not committed; md5 of the node copy in `~/stage4-logs/mhp/harness.md5`. **Instrument checks (not readings):** `javap` of both jars and class trees (field type `CacheLoader` vs `LoadingCache`); `javac` of the test against the original clone; cluster shakedown1 (O-1 and F-1 at n = 50,000), which found D1; shakedown2 (O-1, the replacement old-gen poll). |
| **Tiers and values** | Unit (B2): L ∈ {1, 128, 1000, `Integer.MAX_VALUE`}, 2000 hints of 64 KiB, original and patched builds, run twice. Cluster (B3): O-1, O-128, O-MAX (original) and F-1, F-MAX (patched), 1,000,000 writes of 1 KiB at 400 threads, n2 down. |
| **Audit bottom line** | **Ready after amendments**, 2026-10-21 |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: heap held by queued `HintRunnable`s (each holding a `Mutation`); the knob is a count with a derivable byte size (mutation size). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly | B2b four values, B3b three values. The host default (128 × 40 = 5,120) is not among them: 128 stands in as "the 1-CPU default", and MAX is the uncapped baseline. For a claim that the check never fires at any L, this does not weaken the test. Left for stage 3 (R7). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d heap delta after GC; B3d heap, old gen, hint bytes on disk. The gap is named in B2d/B3d: the heap held by queued hints cannot be isolated. |
| A. Core question | usage driven to the limit and past it | Met | B2c: 2000 hints against L ≤ 1000; B3c: 400 threads against L = 1 and 128. |
| A. Core question | positive control for a negative estimate | Met | B2a item 5 / B3b: a patched build that makes the per-destination counter real, so the same knob binds on the same workload and instruments. |
| B. Logic | each step says what it establishes | Met | B2d/B2h and B3d/B3h say what each observable rules in or out. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact table (queued = min(L+1, 2000)); B3f relations (0 Unavailables, ±25 %, ±5 %, ≤ ~130). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g: confirmed, refuted (cap binds), mechanism refuted, limit never reached, control did not move, heap instrument too coarse, unexpected throttling. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | For this negative claim, Confirmed needs no refusal in the original build and a refusal in the patched one. The filed F-1 evidence included "Overloaded log lines > 0", which the node never writes (R5). Amended. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: same harness, two builds; MAX baseline; `shouldHint` printed; n2 `DN` and `TotalHints` checked; fresh data per run. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | Header Ground and A3.3 explain the bare `CacheLoader`. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Partly | The B2e test code does not compile (R2); the paths are those of another host (R1, R3). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Stress's default 9 retries would re-send refused writes in F-1 (R4); `pgrep -f CassandraDaemon` cannot be empty on a shared host (R6). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | The test, the patch and the jshell script are given in full; the patched clone and the cluster runner were step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | About 1.2 GB of hints plus about 1.1 GB of data per cluster run, wiped between runs, against 54 GB free; unit 125 MiB against a 1 GiB test heap (R1). |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked in `~/cassandra-mhp`: `StorageProxy.java:202-209` (bare `CacheLoader`), `:1585-1599` (the check; `if` at :1592-1593), `:2764-2768` (`load()` called directly), `:2822-2827` (increment), `:2727-2732` (decrement), `:941-946` (Unavailables), `:1505`, `:1563-1564`, `:2748`; `StorageMetrics.java:45`; `DatabaseDescriptor.java:565` (`concurrent_writes` ≥ 2); `Stage.java:46`; Guava 32.0.1-jre (`.build/parent-pom-template.xml:307-309`). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | B2a environment: the two clones `~/cassandra-mhp` / `~/cassandra-mhp-patched`, the diff kept in the harness, test heap 1 GiB (`build.xml:1153`; the cited `:1245-1255` is the `testlist` macro) | Applied 2026-10-21 (note after B2a; not committed) | the filed paths do not exist on `pc07` |
| R2 | B2e test: build the mutation through `PartitionUpdate.SimpleBuilder` (`row()` returns `Row.SimpleBuilder`, which has no `buildAsMutation`), import `HintsService`, print one INFO line | Applied 2026-10-21 (note in B2e) | the filed code does not compile |
| R3 | B3a: n1 = 127.0.0.21 / JMX 7221, n2 = 127.0.0.22 / JMX 7222, `$WORK` = `~/stage4-mhp` | Applied 2026-10-21 (note after B3a) | another stage-4 session shares the host |
| R4 | B3c: `-errors ignore retries=0` | Applied 2026-10-21 (note after B3c) | stress retries 9 times by default (`SettingsErrors.java:41,49`), which would re-send refused writes and blur F-1's hint volume |
| R5 | B3f/B3g: no node log line for this `OverloadedException` (`ExecuteMessage.java:205-210`, `QueryMessage.java:125-131`). The disallow evidence is the write Unavailables delta plus stress's errors | Applied 2026-10-21 (note before B3g; changes the F-1 "log lines" cell, for a source reason, before any reading) | the filed F-1 prediction "log lines > 0" could not hold whatever the cap does |
| R6 | B3e step 8 / B4: check only this run's PIDs | Applied 2026-10-21 (note before B4) | shared host |
| R7 | Include the host's default (128 × cores) as a value, and size a workload that can reach it (more native request threads, or several coordinators) | Left for stage 3 | not needed for this claim; see finding (1) in §8 |

**Agreement criteria:** not filled (no run 2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-21, 11:45–12:30 EDT (unit 11:46–11:50 incl. the repeat; cluster shakedowns 11:53–12:02; cluster run 1 12:02–12:22) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB); session ran on it directly. **Environment deviation E1:** both nodes on this host on loopback (n1 127.0.0.21 / JMX 7221, n2 127.0.0.22 / JMX 7222), not the filed 127.0.0.1/.2. **E2:** a concurrent stage-4 session (`~/cassandra-sep`) shared the host's CPU, disk and loopback during the whole run | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | — |
| Ant (`ant -version`) | 1.10.12 | — |
| Local `cassandra-src` clone commit | `~/cassandra-mhp` at `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`), built earlier with `build-test`, no change under `src/` (untracked harness tests of other cases under `test/unit` compiled fine and were left). Patched: `~/cassandra-mhp-patched` = `cp -a` of it + `hintsInProgress-LoadingCache.diff`, `ant jar build-test` 19 s `BUILD SUCCESSFUL` | — |
| Case-file commit / harness commit | none / none (both untracked); frozen sha256 `af8d24c2…` verified before the run | — |
| Storage for node data | `~/stage4-mhp/run1/<run>/{n1,n2}` on local `/dev/sda3`, 53 GB free at start; each run's copies removed after it | — |
| Full logs (path, outside the repo) | `pc07:~/stage4-logs/mhp/` (`run1/unit-{orig,fixed}/`, `run1-rep2/unit-*/`, `run1/cluster/<run>/` with node logs, gc.log, full stress output, samplers; `shakedown{1,2}/`; `build-patched.log`; `selfcheck.txt`) | — |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | cluster shakedown1 (instrument check, before run 1) | B3d / B3e step 5 | `jstat -gcutil <n1pid> 1000` printed `MonitorException: <pid> not found`: the node runs with `-XX:+PerfDisableSharedMem` (`conf/jvm-server.options:137`), so jstat cannot attach. | The same observable, old-gen occupancy every 1 s, read over JMX: `java.lang:type=MemoryPool,name=G1 Old Gen` `Usage.used` (jstat's O column) and `CollectionUsage.used` (after GC), by `Jmx.java poll`. Checked in shakedown2. B3f/B3g unchanged ("peak post-GC heap (jstat O%)" is read as peak old-gen use). | 2026-10-21, harness only (the case file is not edited for it before run 1; noted in section D) | none |
| H1 | unit run 1 | B2e step 3 | The test JVM routes `System.out` through a logger (`SubstituteLogger`) that logs each piece of a `printf` as its own line, so `grep RESULT` caught only `RESULT L=`. The readings are complete in `ant.log`. | `unit-run.sh` joins the pieces back into lines (`lines.txt`); run 1's summaries were re-extracted from their `ant.log`; a repeat (`run1-rep2`) ran with the fixed script and the unchanged test. `selfcheck.py` re-joins them by its own method. | 2026-10-21 | — |
| H2 | cluster (all runs) | B3d `jmx.jsh` | jshell takes the filed script's `else {` on its own line as a separate, incomplete snippet. In `MODE=set` the `if` line set and read back L, then the else-block statements failed (NPE on `OUT`) and jshell exited. In `MODE=sample` the else-block statements ran at top level and wrote the CSV. Both modes did their job and printed parse errors (`sampler.out`, `session.log`). | Used as filed; the read-back (`MaxHintsInProgress=<L>`) and the sampler's limit column confirm L in force in every run. | 2026-10-21 | — |
| E1, E2 | environment | B3a | see §2 | — | 2026-10-21 | — |

## 4. Run 1

**Scope:** unit B2 (both builds, all four L, twice); cluster B3 (O-1, O-128, O-MAX, F-1, F-MAX, one each). **Command
log:** [`maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous/run1/`](maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous/run1/)
(`unit/<build>[-rep2]/{summary.txt,lines.txt,ant-test-output-excerpt.txt,TEST-*.xml}`, `cluster/<run>/{summary.txt,session.log,readings.json,samples.csv,oldgen.csv,stress-main-excerpt.txt,n1-log-excerpt.txt,n1-yaml.diff}`,
`cluster/analysis.txt`, `shakedowns.txt`, `selfcheck.py`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/*/lines.txt`; JUnit 1/1 passed in each; INFO: test heap 1007 MiB, `concurrentWriters` 32, total in progress 0 at start, `127.0.0.2` not self)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| orig, L = 1 · 128 · 1000 · MAX | queued 2000 · 2000 · 2000 · 2000; rejected 0 at every L; perDest 0; same false; shouldHint true; heap +124 · 126 · 127 · 127 MiB (rep2 the same, 124 · 126 · 127 · 127) | `unit/orig/lines.txt`, `unit/orig-rep2/lines.txt` |
| fixed, L = 1 · 128 · 1000 · MAX | queued 2 · 129 · 1001 · 2000; rejected 1998 · 1871 · 999 · 0; perDest = queued; same true; shouldHint true; heap −6 · 8 · 63 · 126 MiB (rep2 −3 · 8 · 63 · 126) | `unit/fixed/lines.txt`, `unit/fixed-rep2/lines.txt` |
| drain, every L and build | `DRAINED remaining=0` | same |
| build identity | `hintsInProgress` field `CacheLoader` (orig), `LoadingCache` (fixed) | `unit/*/summary.txt` |

**Cluster tier** (`run1/cluster/<run>/summary.txt`, `samples.csv`, `stress-main-excerpt.txt`; each run wrote 1,050,000 times: 1,000,000 plus stress's 50,000 warm-up writes, `StressAction.java:107`)

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| L = 1 · 128 · MAX | O-1 · O-128 · O-MAX | write Unavailables delta; stress errors | 0 · 0 · 0; 0 · 0 · 0 | `<run>/summary.txt`, `stress-main-excerpt.txt` |
| | | "Too many in flight hints" in n1 logs | 0 · 0 · 0 | `<run>/n1-log-excerpt.txt` |
| | | peak `TotalHintsInProgress` (200 ms); samples above L | 129 · 129 · 129; 89 samples > 1 (O-1), 22 > 128 (O-128) | `<run>/samples.csv` |
| | | peak MutationStage pending | 255 · 255 · 255 | same |
| | | hints on disk (30 s after); `TotalHints` delta | 1,150,800,378 B in all three; 1,050,000 in all three (1,096.0 B per hint) | `<run>/summary.txt` |
| | | peak heap used (200 ms); peak old-gen use (1 s) | 1,982 · 1,758 · 2,002 MiB; 924 · 884 · 857 MiB; one Full GC in each | `samples.csv`, `oldgen.csv`, `n1-log-excerpt.txt` |
| L = 1 (patched) | F-1 | write Unavailables delta; stress errors | 833,479; 804,749 (main phase), `OverloadedException … Too many in flight hints: N … destination: Full(/127.0.0.22:7000,…)`, printed twice per refused write (1,666,958 lines); N re-read in the message 0–35 | `F-1/summary.txt`, `F-1/stress-main-excerpt.txt` |
| | | peak `TotalHintsInProgress`; peak pending | 4; 4 | `F-1/samples.csv` |
| | | hints on disk; `TotalHints` delta | 237,307,100 B (0.206 × O-1); 216,521 = 1,050,000 − 833,479 | `F-1/summary.txt` |
| | | peak heap; old gen; stress time | 1,514 MiB; 345 MiB; 72 s (vs 26–27 s) | same |
| L = MAX (patched) | F-MAX | Unavailables; errors; peak in progress; pending; hints | 0; 0; 129; 255; 1,150,800,378 B (= O-MAX) | `F-MAX/summary.txt` |
| | | peak heap used; peak old-gen use | 1,978 MiB (O-MAX 2,002); **1,882 MiB (O-MAX 857)**. Two Full GCs, the second after the stress window: 1,993 → 80 MiB | `F-MAX/oldgen.csv`, `F-MAX/n1-log-excerpt.txt` |
| cross-run | analysis | X1–X8 | 10/10 yes | `cluster/analysis.txt` |

Run-script totals: O-1 8/8, O-128 8/8, O-MAX 7/7, F-1 6/6, F-MAX 7/7, analysis 10/10 `EXPECTED` yes.

### 4.2 Conclusion and logic

1. **Validity.** Unit: the stage was blocked by 32 latch tasks and every submitted hint stayed queued until the gate opened (orig queued 2000; fixed queued = min(L+1, 2000)), `shouldHint` true, drained to 0 each time [observed: `unit/*/lines.txt`]. Cluster: n2 `DOWN` in n1's log and `DN` at the end of every run; every write that was not refused was hinted (`TotalHints` + Unavailables = 1,050,000 in each run); L read back and in force in every sampler row; `concurrent_writes: 2` and the addresses in the yaml diff [observed: `summary.txt`, `samples.csv`, `n1-yaml.diff`, `n1-log-excerpt.txt`]. The limit was passed: in-flight 129 against L = 1 and 128 [observed]. Valid.
2. **Readings.** (a) The in-flight count stops at 129 in every uncapped run, at L = 128 as at MAX, so O-128 passed its limit only just and in 22 samples [observed]. The cause is very likely the 128 native request threads, each waiting for its own local write [inferred: `native_transport_max_threads` default 128 and the response waiting on the local apply; not tested]. (b) The node's heap is dominated by the write path, not the queued hints: 129 hints of about 1.1 KB are about 0.15 MB against peaks of 1.8–2.0 GiB [inferred: arithmetic]. Every uncapped run had a Full GC, and F-MAX's old-gen peak fell at a different point of the GC cycle [observed: `n1-log-excerpt.txt`]. (c) In F-1 the operand re-read in the refusal messages reached 35 at L = 1, which is the check-then-increment overshoot of A3.5 [observed: `F-1/stress-main-excerpt.txt`].
3. **Matched rows.** Unit, **B2g row 1**, "orig: rejected = 0 and queued = 2000 for all L, perDest = 0, same = false; fixed: queued = min(L+1, 2000)": exactly, in both reps. Cluster, **B3g row 1**, "O-*: 0 overloaded lines, 0 Unavailables, max hintsInProgress > L (for L = 1, 128), hints bytes and heap peaks the same across L; F-1 shows Overloaded errors (R5: Unavailables and stress errors > 0) and lower hint volume and pending": 0/0/0 Unavailables and errors; 129 > 1 and 129 > 128; identical hint bytes; heap peaks within 1.14× (heap used) and 1.08× (old gen); F-1 833,479 Unavailables, 804,749 errors, 0.206 × the hints and pending 4 vs 255.
4. **Excluded rows.** Unit: "rejected > 0 or queued ≈ L+1 in orig" — 0 and 2000 everywhere; "perDest > 0 or same = true in orig" — 0 and false; "queued < 2000 with rejected = 0, or shouldHint = false" — no; "fixed rejected = 0 at L = 1" — 1998; "heap does not differ between fixed L = 1 and MAX" — −6 vs 126 MiB. Cluster: **Refuted** row ("Too many in flight hints" or Unavailables > 0 in O-1/O-128, or in-flight capped near L) — 0 and 0, in-flight 129 at L = 1; "O-1 hint volume or heap > 25 % below O-MAX" — equal bytes, heap 1,982 vs 2,002 MiB; "max hintsInProgress ≤ L throughout O-1" — 89 samples above 1; "F-1 no Overloaded errors" — 833,479.
5. **Observed vs. inferred.** Inferred: the cause of the 129 plateau (part 2a); that queued hints are a negligible share of the heap (2b); that F-MAX's old-gen excess is GC timing (2b, supported by the observed Full GC 1,993 → 80 MiB). None of these is used by the matched rows: they rest on counts (Unavailables, errors, the in-flight counter, `TotalHints`) and on byte totals on disk.
6. **Deviations and gaps.** E1/E2 (one shared host, other addresses and ports); D1 (old gen over JMX instead of jstat); H1, H2 (harness output); R4 (`retries=0`) and R5 (no log line) applied before the run; stress's 50,000 warm-up writes counted in every run alike. **One sub-prediction missed:** B3f's "F-MAX peak heap matches O-MAX" does not hold for the old-gen reading (1,882 vs 857 MiB); the heap-used peak matches. The heap readings cannot isolate the hints (the gap B3d names), so the cluster's memory statement rests on the in-flight count and hint bytes.
7. **Core question.** Usage does not follow `maxHintsInProgress`. With the shipped counter, the check never refused a hint at L = 1, 128, 1000 or MAX. The per-destination counter read 0 and was a new object on every call [part 3, unit], so in-flight hints, the heap they hold and the hint bytes written were the same at every L [part 3, cluster]. The positive control shows that the same knob and workload do cap usage once the counter is a real cache: unit queued = min(L+1, 2000) and heap ∝ queued; cluster F-1 refused 79 % of the writes and wrote 0.21 × the hints [parts 3, 4]. The knob caps nothing in 5.0.9.

**Conclusion (one line):** unit B2g row 1, cluster B3g row 1: **Confirmed** (claim: the check never fires and usage does not follow the knob). One sub-prediction missed (F-MAX old-gen peak).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Independent script [`run1/selfcheck.py`](maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous/run1/selfcheck.py) re-reads the raw files on the node. For the unit tier it re-joins the test's output fragments from `ant.log` by its own method (concatenation and regex, not `unit-run.sh`'s `sed`). For the cluster it reads the 200 ms sampler CSVs, the old-gen poll, the full stress output (results block, warm-up line, every refusal message), n1's `system.log`/`debug.log` and the yaml diff. From `summary.txt` it takes only the JMX before/after and the hint-directory size. It re-applies B2f/B2g and B3f/B3g. Output [`run1/selfcheck.txt`](maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous/run1/selfcheck.txt): **177 ok, 1 FAIL**. The one failure is the missed sub-prediction (F-MAX old gen 2.20 × O-MAX). Its figures agree with the run scripts' for every run.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | re-checked: `shouldHint` true and drain 0 in all 16 unit RESULT/DRAINED pairs; `TotalHints` + Unavailables = 1,050,000 and n2 DOWN once in each cluster run; L in every sampler row |
| 2. Readings | yes | the 129 plateau in four runs and the samples above L (89, 22) recounted from `samples.csv`; the F-1 operand range 0–35 recounted from the full stress output; GC pauses re-read in `gc.log` |
| 3. Matched row | yes | unit: queued/rejected/perDest/same recomputed against min(L+1, 2000) for both reps; cluster: Unavailables, errors, bytes, ratios recomputed |
| 4. Excluded rows | yes | each excluded row's contrary reading recomputed (the Refuted row: 0 Unavailables and 0 refusal text in O-1/O-128) |
| 5. Observed vs. inferred | yes | the three inferences are not used by the matched rows |
| 6. Deviations and gaps | yes | D1, H1, H2, E1, E2 and R4/R5 recorded; the missed sub-prediction is the self-check's only failure |
| 7. Core question | yes | follows B1: the check never throws in the unmodified build (unit and cluster), usage flat across L, and the positive control moves on the same workload |

### 5.2 Run 2?

**No.** Decided 2026-10-21. The conclusion rests on exact counts that a repeat of the unit tier reproduced to the hint, and the self-check settled every part from run 1's files. The result confirms the file's own negative estimate and neither refutes the case nor confirms a bypass. The missed sub-prediction concerns a heap proxy the design names as unable to isolate the hints.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2); §7 left out.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its
date and reason.

**Stage-3 estimate:** negative. The ground is a dead condition: the per-destination counter is a bare Guava `CacheLoader`, so clause 2 at `StorageProxy.java:1593` is always false.

**Claim tested:** B1. "In Cassandra 5.0.9, `checkHintOverload` never throws `OverloadedException`, whatever `MaxHintsInProgress` is set to (including 1, when `TotalHintsInProgress` is far above it). As a result, the number of queued hint tasks and the heap they retain do not follow `MaxHintsInProgress`." "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed**, B2g row 1. Original build: 2000 queued, 0 rejected, per-destination counter 0 and a new object on each call, heap +124–127 MiB at L = 1 · 128 · 1000 · MAX. Patched: queued 2 · 129 · 1001 · 2000 = min(L+1, 2000), heap −6 · 8 · 63 · 126 MiB. Repeated exactly | does not cap | run 1 + self-check | 2026-10-21 |
| Cluster | **Confirmed**, B3g row 1. O-1/O-128/O-MAX: 0 Unavailables, 0 errors, in flight 129 (above L = 1 and 128), 1,150,800,378 B of hints each. F-1: 833,479 refused writes, 0.206 × the hints, pending 4 vs 255. One sub-prediction missed (F-MAX old-gen peak 1,882 vs 857 MiB, GC timing) | does not cap | run 1 + self-check | 2026-10-21 |

**Positive control:** the patched build (`hintsInProgress-LoadingCache.diff`: `LoadingCache` + `get`) on the same harness and workload. In the unit tier queued = min(L+1, 2000) exactly, with rejections 1998 · 1871 · 999 · 0 and heap following queued. In the cluster tier, F-1 refused 833,479 of 1,050,000 writes with "Too many in flight hints", cut hint bytes to 0.206 × O-1, and held MutationStage pending at 4. F-MAX equals O-MAX.

**Findings beyond the claim (no §9a row):** (1) Client writes to one coordinator plateau at 129 hints in flight at any L, plausibly bounded by the 128 native request threads (inferred). So the host default, 5,120, is out of reach of this workload even with a working counter. (2) With the counter fixed, the check still overshoots (operand re-read up to 35 at L = 1, A3.5). (3) The filed jshell sampler parses with errors in jshell (H2), and `jstat` cannot attach to a stock node (D1). Both are worth knowing for any design that names them.

**Feedback filed:** the case file's section D was updated on 2026-10-21; only section D changed after the freeze. The case file is not committed. New sha256: `a8405af450f7f934e88f5b869ece4b16f85ea9d4145525425ccb7ac699c15dd6` (frozen `af8d24c2…`, filed `2cda58a1…`). Also updated: the stage-3 index (§1 row, §2 counts, §4 three hash lines) and `predicted-negative.md` §10 (the `StorageProxy.java:1592` row removed per that file's rule, and the "Re-examine first" note updated).
