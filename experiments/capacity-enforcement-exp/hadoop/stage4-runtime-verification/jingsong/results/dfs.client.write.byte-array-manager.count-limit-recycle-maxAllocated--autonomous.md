# dfs.client.write.byte-array-manager.count-limit-recycle-maxAllocated--autonomous — stage-4 results  <!-- file: results/dfs.client.write.byte-array-manager.count-limit-recycle-maxAllocated--autonomous.md -->

> **Case:** [`dfs.client.write.byte-array-manager.count-limit-recycle-maxAllocated--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/dfs.client.write.byte-array-manager.count-limit-recycle-maxAllocated--autonomous.md) (queue order 13, band A)
>
> **Status:** verdict filed (2026-11-25): audited, run 1 on `pc75` 03:20–03:54 MST (unit tier restarted once, defect D1 → A10), self-checked; no run 2
>
> **Outcome class:** **weak true positive** — estimate `positive`; unit **Confirmed — caps** (U1); cluster **Not confirmed** (C3: heap bands against the disabled baseline missed by 0.5–0.6 MiB while the pool count was exact)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster) with amendments A3/A4 and A6/A7; "§9b–§9e" means
> B2a–B2e / B3a–B3e; the case file's feedback section is its section D.

**Where things are (drafted outside the repository, per the task).** This file: `~/writeup-hadoop/out/o13/results.md`. Harness:
`~/writeup-hadoop/out/o13/harness/`. Amended case file (A10 + section D): `~/writeup-hadoop/out/o13/case-amended.md`. Raw logs
(copied back from the node, 12 MB): `~/writeup-hadoop/out/o13/run1/logs/` (`unit/`, `unit-attempt1/`, `diag/`, `cluster/`,
`diag-cluster/`, `unit-run.log`, `cluster-run.log`); analyzer output `~/writeup-hadoop/out/o13/run1/analysis.txt`. On `pc75` the
run folder `/mydata/jingsong-s4/dfs.client.write.byte-array-manager.count-limit-recycle-maxAllocated-run1/` keeps only `logs/`,
`conf/`, `harness/`, `probe/` (12 MB). The 2026-11-24 partial drafts (`~/writeup-hadoop/out/o13/ignored-partial-draft-2026-11-24/`)
were not used; the partial run folder of that attempt is on `pc99` (not touched by this run).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Starting point: the filed file at repository commit `bef6bc8a` (2026-11-24, A1–A9), sha256 `d8d148063a1f7a8d32ed89c923e670d3db0d2077b53e5a567fd7cee0f857deab` (matches `_INDEX.md` §4). Audit: no new amendment before run 1. Defect fix **A10** (2026-11-25, unit tier restarted; §3 D1) → frozen version sha256 `89c0f302189f0aee7bdee54c38a5650d55b4442b7de0e539a6dacba99c2b639b` (`run1/case-frozen-after-A10.md`). Section D was then filled (`case-amended.md`, final sha in the return note). |
| **Harness** | `harness/` (outside the repo, uncommitted): `TestByteArrayManagerCountLimitPool.java` (md5 `3d01921b…`), `unit-run.sh` (`122942ad…`), `BamProbe.java` (`7d45bfc9…`), `cluster-run.sh` (`22ce5e1b…`), `analyze.py` (`1b5bdc21…`); diagnostics only: `BamHeapDiag.java`, `diag-run.sh`, `hprof_bytearrays.py`. Instrument checks: known answer (one retained `byte[65536]`) in every unit mode; probe heap/GC printed per cluster run. |
| **Tiers and values** | Unit (B2): L ∈ {1, 4, 16, 64, 1024} × 3 reps, modes managed / disabled / mutation (line 209 → `if (true) {`), case 2, case 3, wiring. Cluster (B3): pseudo-distributed HDFS 3.4.2, T = 64 writers × 64 MiB, packet 1 MiB; runs disabled, L = 8, 16, 32, 4096 (threshold 0), L = 8 threshold 32; 3 reps interleaved. |
| **Audit bottom line** | **Ready** — 2026-11-25 (A1–A7 of the 2026-11-24 audit already applied and re-checked; A8–A9 instrument fixes kept) |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: client heap in pooled packet `byte[]`, `count-limit × arrayLength` per length. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach | Partly | B2b/B3b: 5 unit and 4 cluster values plus disabled; default 2048 not run (reason given in B2b: test heap; L = 4096 is the uncapped control). |
| A. Core question | real resource measured, not only the counter | Met | B2d retained heap (A8 non-eden pools), B3d `jcmd GC.class_histogram` `[B` bytes; counter (`free=`) as the mechanism cross-check. |
| A. Core question | usage driven to the limit and past it | Met | B2c: L + 10 extra releases past the cap; B3c: demand 64–384 buffers vs L ≤ 32. |
| B. Logic | each step says what it establishes | Met | B2c cases 1–3, B2h/B3h controls. |
| B. Logic | prediction in numbers | Met | A3 (unit bands), A6 (cluster bands). |
| B. Logic | every plausible outcome has a row | Met | A4 U1–U5, A7 C1–C4. |
| B. Logic | confirmation needs ceiling-follows-knob and disallow evidence | Met | Pool = L through the extra releases (disallow branch: release returns stay at L) plus mutation control 2L + 10. |
| B. Logic | alternative explanations and controls | Met | disabled control, mutation, fresh JVM per reading (A9), uncapped control L = 4096. |
| C. Specific | a human can follow it | Met | B1 + B2f/B3f tables. |
| C. Specific | an AI can run it | Met | A1/A5 give commands, ports, paths. |
| C. Specific | exact knobs, commands, sampling, stop conditions | Met | A2/A5/A6 (sampling 3 × 10 s, 900 s timeout). |
| D. Runnable | prerequisites exist or listed | Met | `pc75` has JDK 8, Maven 3.6.3, `/mydata/jingsong-s4/hadoop-base` dist (environment.md); harness written in step 1. |
| D. Runnable | workload arithmetic reaches the limit | Met | 4 GiB per cluster run on 701 GB free; heap ≤ 1 GiB on 125 GiB RAM. |
| D. Runnable | load-bearing citations spot-checked | Met | `ByteArrayManager.java:166-216` (line 209 is the cited check, also asserted by `unit-run.sh`), `:296-313`, `:360-405`; `DfsClientConf.java:326-345`; `ClientContext.java:181-182,210-223`; `DFSOutputStream.java:136-152,426-430,493-495`; `DataStreamer.java:1004-1012`. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Include the default 2048 as a unit value | left for stage 3 | Not needed for a valid run (1024 and 4096 bracket it). |
| R2 | (after the cluster readings) Take the cluster baseline from the capped runs' own non-pool `[B` bytes, or count managed-length arrays in a heap dump, instead of a separate disabled run | left for stage 3 (section D) | Depends on readings, so it cannot change this run's frozen bands. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25, 03:17 (lock) – 03:54 MST (lock released); session clock EST (+2 h) |
| Node | `pc75` = `node3.jason92-326665` (CloudLab UMass, 40 cores, 125 GiB RAM); node lock `/mydata/s4/NODE-LOCK` held for the whole run |
| OS and kernel | Ubuntu 22.04, `5.15.0-203-generic` |
| JDK | OpenJDK `1.8.0_514` (`/usr/lib/jvm/java-8-openjdk-amd64`) for build, tests, daemons and probe |
| Maven | 3.6.3 |
| Local source copy | `copy-source.sh` from the repository's `systems/hadoop/source/` (tag `rel/release-3.4.2`), repository HEAD `cd9e1cde` → `$R/src` (deleted after the run) |
| Distribution | copy of `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` (node's 2026-11-24 full build) → `$R/hadoop` (deleted after the run) |
| Case-file commit / harness | `bef6bc8a` + A10 (outside the repo) / harness outside the repo (md5s in §1) |
| Storage | `/mydata` (local, 753 GB) |
| Full logs | `~/writeup-hadoop/out/o13/run1/logs/` (this machine) and `$R/logs/` on `pc75` |

`$R` = `/mydata/jingsong-s4/dfs.client.write.byte-array-manager.count-limit-recycle-maxAllocated-run1`.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| D1 | 1 (unit, attempt 1) | B2d/B2e (A8/A9 heap reading) | The instrument known answer read −609,896 B (managed), −591,504 B (disabled), −607,688 B (mutation), outside 65,536 ± 64 KiB → row U5 Invalid by A4's instrument condition; every case-1 Δ was shifted by the same ≈ −0.6 MB (`run1/logs/unit-attempt1/readings-*.csv`). Pool readings, case 2, case 3, wiring and the disabled |Δ| ≤ 1 MiB all held. Diagnostic `BamHeapDiag` (`run1/logs/diag/diag1.txt`): first post-warm-up reading Tenured 1,955,800 B, then 1,278,496 / 1,278,544 / 1,278,672 (5 s pause) with no allocation; one `byte[65536]` then +65,632 B. | **A10**: one unrecorded settling reading (same routine) after the warm-up, before reading (a). Logged per child as `SETTLE` (≈ 1,956,700 B every time, confirming the cause). | 2026-11-25, claim/predictions/conclusions unchanged; unit tier restarted from its beginning | sha256 `89c0f302…` |

No cluster-tier defect: `cluster-run.sh` ran every step of B3e/A5 as written.

## 4. Run 1

**Scope:** both tiers, all values. **Command logs:** `run1/logs/unit-run.log` (attempt 2; attempt 1 in `unit-attempt1/unit-run.log`),
`run1/logs/cluster-run.log`; per-mode surefire output `run1/logs/unit/surefire-<mode>/…-output.txt`; probe logs and histograms
`run1/logs/cluster/`.

### 4.1 Readings

**Unit tier** (attempt 2, after A10; all from `run1/logs/unit/readings-<mode>.csv`; checks in `run1/analysis.txt`, 121/121 pass)

| Test or assertion | Result | Evidence |
|---|---|---|
| argLine reached every JVM (1 GiB, Serial) | maxHeap 1,037,959,168, GC `Copy|MarkSweepCompact` in the surefire JVM and all 48 children | `ENV` lines, all modes |
| Instrument known answer | +65,584 B in managed, disabled and mutation (bound 0…131,072) | `KNOWN` lines |
| Case 1 managed, pool | L = 1, 4, 16, 64, 1024: pool after the L managed releases = L, max and final pool during the L + 10 extra releases = L, every rep | `CASE1,managed`, `TRACE1` |
| Case 1 managed, Δ | L = 1: 66,160; 4: 262,960; 16: 1,050,016; **64: 4,198,528** (band 3,145,728–6,292,480); **1024: 67,170,408** (band 66,060,288–69,222,400) — identical in all 3 reps | `CASE1,managed` |
| Disabled control | every release returns 0; Δ = 224 … 9,368 B (≤ 1 MiB) | `CASE1,disabled` |
| Mutation control (line 209 → `if (true)`) | pool after managed releases = L, final = 2L + 10 (12, 18, 42, 138, 2058); Δ(L = 1024) = 134,975,992 B (≥ 133,824,512) | `CASE1,mutation`; `unit-run.log` (`git diff --stat` 1 line changed, reverted, diff empty) |
| Case 2 (in-use cap) | every L: `[65536: L/L, free=0]` after L allocations; extra allocator WAITING at 500 ms, TERMINATED 0 ms after one release | `CASE2` |
| Case 3 (unmanaged releases) | allocations 1–16 unmanaged, 17–20 managed `4/4`; pool 1, 2, 3, 4 then 4 for every later release; `numAllocated` = 0 after the 4th unmanaged release while 4 managed arrays were held; final `[65536: 0/4, free=4]` | `CASE3` |
| Wiring | enabled + count-limit 16 → `ByteArrayManager$Impl`, `[65536: 1/16, free=0]`; enabled unset → `NewByteArrayWithoutLimit` | `WIRE` |

**Cluster tier** (reading = median of 3 `[B` totals; B = median of disabled readings = 7,049,384 B; `run1/logs/cluster-run.log`, `cluster/probe-*.log`, `cluster/histo-*.txt`)

| Run | Rep | Manager string (1 MiB) | `[B` reading | delta = reading − B | A6 band | Write ms |
|---|---|---|---|---|---|---|
| disabled | 1 / 2 / 3 | no manager | 8,305,008 / 7,049,384 / 4,889,192 | +1,255,624 / 0 / **−2,160,192** | B ± 2,097,152 | 6249 / 4902 / 4906 |
| L = 8 | 1 / 2 / 3 | `[1048576: 0/8, free=8]` | 12,760,112 / 12,761,240 / 12,746,432 | **5,710,728 / 5,711,856 / 5,697,048** | 6,291,584–10,485,888 | 4689 / 5610 / 4836 |
| L = 16 | 1 / 2 / 3 | `[1048576: 0/16, free=16]` | 21,159,640 / 21,145,688 / 21,151,856 | **14,110,256 / 14,096,304 / 14,102,472** | 14,680,320–18,874,624 | 3169 / 2839 / 2988 |
| L = 32 | 1 / 2 / 3 | `[1048576: 0/32, free=32]` | 38,003,128 / 37,996,528 / 38,002,120 | **30,953,744 / 30,947,144 / 30,952,736** | 31,457,792–35,652,096 | 2560 / 2419 / 2510 |
| L = 4096 (control) | 1 / 2 / 3 | `[1048576: 0/4096, free=384]` | 407,951,656 / 410,842,488 / 409,907,968 | 400,902,272 / 403,793,104 / 402,858,584 (k × 1,048,592 = 402,659,328) | ± 2 MiB of k × 1,048,592 | 2826 / 2849 / 2688 |
| L = 8, thr 32 | 1 / 2 / 3 | `[1048576: 0/8, free=8]` (64-byte manager `free=8/8/6`) | 12,824,240 / 12,763,296 / 12,752,424 | **5,774,856 / 5,713,912 / 5,703,040** | 6,291,584–10,485,888 | 2656 / 2744 / 3096 |

Every run: probe exit 0, 0 writer failures, `hdfs dfs -du -s /bam/<run>` = 4,294,967,296, probe maxHeap 1,037,959,168 with Serial GC.
Bold = outside the A6 band.

**Post-run diagnostic (not a reading; no effect on the verdict)** — `run1/logs/diag-cluster/`: the same probe with a live heap
dump at POSTGC, `byte[]` lengths ≥ 4096 counted by `hprof_bytearrays.py`:
disabled #1: 128 × 65,536 + 6 × 8,192 + 1 × 6,563 (`[B` 8,588,720); disabled #2: 73 × 65,536 + 6 × 8,192 (`[B` 4,965,224);
L = 8: **8 × 1,048,576** + 64 × 65,536 + 6 × 8,192 (`[B` 12,769,160). With the manager disabled no 1 MiB-class packet buffer is
retained; with L = 8 exactly 8 are. The baseline's spread (and its excess over the capped runs' non-pool part, ≈ 4.36 MB) is a
variable number of retained 64 KiB `byte[]` (64 to 128) outside the manager; their owner was not attributed.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — valid. argLine reached every JVM [observed: `ENV` lines, `unit/readings-*.csv`]; known answer +65,584 B in each
   mode [observed: `KNOWN`]; one child JVM per reading with warm-up and A10 settling reading [observed: `SETTLE`/`CHILD-EXIT` lines,
   16 children per mode, exit 0]; the cap was reached and passed (L + 10 extra releases) [observed: `TRACE1`].
2. **Readings** — Δs are identical to the byte across repetitions (deterministic layout after a settled full GC); L = 1, 4, 16 Δs
   are L × 65,552 + ≈ 560 B (manager/list overhead), not decisive per A3 [observed: `CASE1,managed`].
3. **Matched row — U1 "Confirmed — caps"**: every A3 pool and Δ reading holds in all three reps (pools = L; Δ64 = 4,198,528,
   Δ1024 = 67,170,408), case 3 holds, wiring holds, disabled control holds (returns 0, |Δ| ≤ 9,368), mutation reaches 2L + 10
   [observed: `run1/analysis.txt`, 121/121].
4. **Excluded rows** — U2 (Refuted): no pool ever exceeded L (or 4 in case 3) with line 209 unmodified [observed: `TRACE1,managed`,
   `CASE3`]. U3: both decisive Δs inside their bands. U4: mutation pool = 2L + 10, not L. U5: disabled returns 0, |Δ| ≤ 1 MiB, wiring
   holds, known answer inside 65,536 ± 64 KiB, argLine reached. Case 2 blocked as predicted.
5. **Observed vs. inferred** — that the heap Δ is the pooled arrays [inferred: Δ = L × 65,552 + small constant at every L, and the
   mutation's Δ follows 2L + 10 — the only change is the pool size].
6. **Deviations and gaps** — attempt 1 was Invalid by the instrument (D1); A10 restarted the tier. Default 2048 not run (R1).
7. **Core question** — retained heap follows `count-limit` exactly (L × 64 KiB arrays) and the line-209 disallow branch is what
   holds it (mutation removes the cap); the in-use cap blocks allocation at L. The constraint caps usage at the mechanism level.

**Conclusion (unit):** U1 — **Confirmed — caps**.

**Cluster tier**

1. **Validity** — valid by A7's C4 conditions: every enabled run printed `/L` with the intended L, disabled runs printed no manager,
   every `-du` = 4,294,967,296, probe heap 1 GiB Serial [observed: `cluster-run.log`, `cluster/probe-*.log`]. The cap was reached:
   the uncapped control pooled 384 buffers (≥ 64) [observed: POSTGC `free=384`].
2. **Readings** — capped runs are tightly repeatable (± 15 KB across reps); the disabled baseline is not (4.89–8.31 MB). The `[B`
   slope is 1,049,941 B (L 8 → 16) and 1,052,718 B (L 16 → 32) per unit of L (rep 1), i.e. one 1 MiB array (+ ≈ 64-byte arrays)
   per unit [observed: §4.1 table]. Disabled r3 is −2,160,192 B from B (outside B ± 2 MiB).
3. **Matched row — C3 "Not confirmed"**: "a capped run has `free` = L but delta outside its band (another consumer or retention;
   record `jmap -histo:live`)". Every capped run has `free` = L, and every capped delta is 0.5–0.6 MiB below its band (L = 8:
   ≈ 5.70–5.77 MB vs ≥ 6.29 MB; L = 16: ≈ 14.10 MB vs ≥ 14.68 MB; L = 32: ≈ 30.95 MB vs ≥ 31.46 MB) [observed: §4.1]. The live
   histogram was recorded (`GC.class_histogram` is live) and the heap-dump diagnostic located the other consumer (64 KiB arrays).
4. **Excluded rows** — C1: A6 deltas not met (and disabled r3 outside B ± 2 MiB). C2 (Refuted): `free` never exceeded L, threshold-32
   run included (`free=8`); deltas are not flat (5.7 → 14.1 → 31.0 MB) nor equal to the control (≈ 400 MB). C4: none of its
   conditions holds. "Writers hang" (C3 alt.): all 64 writers finished in 2.4–6.2 s.
5. **Observed vs. inferred** — that the band miss comes from the baseline, not the pool [inferred: capped-run readings minus
   L × 1,048,592 leave ≈ 4.37 MB in every capped run, below B; supported by the diagnostic dumps (outside the frozen runbook)].
6. **Deviations and gaps** — none in the runbook. The diagnostic was an extra, post-verdict step with separate probe runs.
7. **Core question** — the pool count follows `count-limit` exactly (free = L at 8/16/32, 384 uncapped) and the retained `[B`
   bytes rise by one 1 MiB array per unit of L, but the frozen heap test (delta vs a disabled-run baseline within ± 2 MiB of L MiB)
   failed in every capped run, so by the file's own table the heap claim is not confirmed at this tier.

**Conclusion (cluster):** C3 — **Not confirmed**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read `ENV`/`KNOWN`/`SETTLE` lines in `unit/surefire-*/…-output.txt` (known 65,584 in all three); probe `ENV` and `POSTGC` lines (e.g. `cluster/probe-L8t32-r1.log`: maxHeap 1,037,959,168, `Copy|MarkSweepCompact`); `DU` lines in `cluster-run.log`. |
| 2. Readings | yes | Re-read `histo-L8-r1-s2.txt` (12,760,112), `histo-disabled-r3-s2.txt` (4,889,192), `histo-L4096-r2-s2.txt` (410,842,488); match §4.1. |
| 3. Matched row | yes | Unit: `analysis.txt` UNIT 121/121; cluster: every capped delta below its A6 lower bound while every manager string is `0/L, free=L` → exactly C3's wording. |
| 4. Excluded rows | yes | C2 needs `free` > L or flat deltas; neither in the POSTGC lines. C4 conditions all false. U2–U5 excluded by the re-read CSVs (case 3 releases 4/5/20 all `free=4`). |
| 5. Observed vs. inferred | yes | The only inferred cluster statement (cause of the miss) does not change the row; C3 is chosen from observed bands alone. |
| 6. Deviations and gaps | yes | D1/A10 recorded; A10 is instrument-only (the known answer and the `SETTLE` value explain it without any case reading). |
| 7. Core question | yes | Unit answers "caps" with disallow evidence (mutation); cluster cannot by its frozen bands, stated as such. |

### 5.2 Run 2?

**No** — 2026-11-25. The unit verdict rests on observed, exactly repeatable readings with all controls; the cluster verdict (Not
confirmed) is fixed by the frozen bands and a run 2 with the same baseline method would reproduce the miss (capped readings repeat
to ± 15 KB; the shortfall is 0.5–0.6 MiB in all 12 capped runs). The remedy is a design change (R2), which is stage 3's.

## 6. Run 2 — not done

## 8. Verdict — AI

**Stage-3 estimate:** `positive`. **Outcome class:** **weak true positive** — unit Confirmed — caps; cluster Not confirmed only
because its frozen heap bands missed (weak-class rule of 2026-10-29: classed from the unit tier).

**Claim tested (B1):** with `dfs.client.write.byte-array-manager.enabled=true`, the number of packet buffers of one array length
retained in the client pool never exceeds `count-limit`, so the retained client heap after a write burst is ≈ min(count-limit,
peak) × arrayLength and moves with `count-limit`; with the manager disabled nothing is retained.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | U1 — **Confirmed — caps** | caps | run 1 (attempt 2, after A10) + self-check | 2026-11-25 |
| Cluster | C3 — **Not confirmed** | undetermined (pool count capped exactly at L; heap delta bands missed by 0.5–0.6 MiB against a variable disabled baseline) | run 1 + self-check | 2026-11-25 |

**Feedback filed:** section D of `~/writeup-hadoop/out/o13/case-amended.md` (with amendment A10 next to A9). Not committed (the
task keeps the repository untouched; the parent session files it). `_INDEX.md` row for order 13 should read: unit Confirmed — caps,
cluster Not confirmed — weak true positive; new sha256 of the case file with A10 and D.
