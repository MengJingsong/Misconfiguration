# dfs.client.mmap.cache.size-demoteOldEvictableMmaped-maxEvictableMmapedSize--autonomous — stage-4 results  <!-- file: results/dfs.client.mmap.cache.size-demoteOldEvictableMmaped-maxEvictableMmapedSize--autonomous.md -->

> **Case:** `dfs.client.mmap.cache.size-demoteOldEvictableMmaped-maxEvictableMmapedSize--autonomous` (stage-3 queue order 12;
> at run time the amended case file is `/users/jason92/writeup-hadoop/out/o12/case-amended.md`, outside the repository)
>
> **Status:** **verdict filed 2026-11-25** — unit **Confirmed** (caps), cluster **Confirmed** (caps). Claim tested (B1): for a
> DFSClient doing zero-copy short-circuit reads that releases each buffer, the number of idle block-file mappings kept by one
> `ShortCircuitCache`, and the memory they hold, stays at or below `max(S−1, 0)` mappings (S = `dfs.client.mmap.cache.size`)
> and grows with S until it reaches the number of blocks read. Every predicted number matched exactly at both tiers (unit
> 1351/1351 checks, cluster 520/520): idle mappings after close 0 / 0 / 1 / 2 / 4 / 7 / 12 / 12 at S = 0 / 1 / 2 / 3 / 5 / 8
> / 13 / 256 (unit, 1 MiB blocks) and 0 / 0 / 1 / 4 / 8 / 16 / 16 at S = 0 / 1 / 2 / 5 / 9 / 17 / 256 (cluster, 64 MiB
> blocks, RssFile +0 … +1020 MiB), with the size branch's own TRACE line fired `N − M(S)` times. The off-by-one (`S − 1`, not
> `S`) traced in A3 holds at runtime. One run 1, no run 2.
>
> **Outcome class:** **true positive** — stage-3 estimate `positive` against the stage-4 effect `caps` at both tiers
> ([definition](../../../../stage4-runtime-verification/README.md#outcome-class))
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f
> and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its
> section D, not §10. One results file per case file.

**Layout.** Hadoop, Jingsong's share, run by an autonomous stage-4 agent on node `pc91`. At run time this file, the harness and
the raw excerpts are outside the repository: this file `~/writeup-hadoop/out/o12/results.md`, harness
`~/writeup-hadoop/out/o12/harness/`, raw excerpts `~/writeup-hadoop/out/o12/run1/` (cited below as `run1/...`), amended case
file `~/writeup-hadoop/out/o12/case-amended.md`. When filed in the repository they go to
`hadoop/stage4-runtime-verification/jingsong/results/` (this file and `results/<stem>/run1/`) and `.../jingsong/harness/<stem>/`.
Protocol: `experiments/capacity-enforcement-exp/stage4-runtime-verification/README.md` "The run protocol"; node environment:
`hadoop/stage4-runtime-verification/jingsong/environment.md` (`pc91` row, built 2026-11-24).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file written by stage 3 on 2026-11-24, in the repository since commit `bef6bc8a6` (repository HEAD at run time `cd9e1cded`); sha256 as received `b3d27ac5c34441477d99e1ea681ce01a9c6aa6040b8b94fac31866b3cbeeb67d` (= `_INDEX.md` §4 row). After the audit's amendments A1–A8 (section D1), 2026-11-25 03:12 MST, before any harness run or reading: whole-file sha256 **`d03cfaa7ace27764b34e3da6c4899a072d4fe95a17e71eac3193ba3a2776bbb8`** (frozen version). |
| **After the run** | A9 (runbook defect D-2, probe imports; after the unit readings, before any cluster reading; B3f/B3g unchanged): sha256 `9b31bc40999d63af31646d1239f692a47d3b07b4bf3fbbbab3e0747c72c31bac`. Section D filled after run 1: sha256 `845eb5bf75f42a22a0905cefd897421cdae76016289c602f492ea50f268ef987`. |
| **Harness** | `~/writeup-hadoop/out/o12/harness/` (written after the freeze, before run 1; copied to `R1/harness/` on the node): `prep.sh` md5 `b9092a7d`, `TestMmapCacheSizeCap.java` `cb96fb93`, `unit-run.sh` `9a7210ae`, `MmapCapProbe.java` `f37fcffd` (the case file's B3a probe verbatim, extracted from the amended file, A9), `cluster-run.sh` `2cc71ced` (final; harness defect D-1 fixed before any reading), `selfcheck_unit.py` `7a1b1840`, `selfcheck_cluster.py` `afb06956` (one parser fix before its first output, §3). Not committed (outside the repository). Instrument checks: `unit-run.sh --compile-only` BUILD SUCCESS 03:13:43 (node time, MST); known answers in the runs: `IFCHK,env native=true` (unit), `hadoop checknative -a` → `hadoop: true` (cluster), unit baseline 0 mappings and S = 256 row 12 mappings (instrument sees all 12 when no cap binds), cluster `-cat` baseline 0 mappings with 16 `REQUEST_SHORT_CIRCUIT_FDS` DataNode lines (short-circuit active). |
| **Tiers and values** | Unit (B2): MiniDFSCluster, 1 DN, file of N = 12 × 1 MiB blocks, zero-copy read + release per block; S ∈ {0, 1, 2, 3, 5, 8, 13, 256}; controls: positive (S = 256, streams cache 4), time (S = 256, timeout 500 ms), baseline (heap pool, mmap off); whole sweep twice. Cluster (B3): pseudo-distributed NN + DN on `pc91`, native libhadoop, file of N = 16 × 64 MiB blocks (1 GiB); S ∈ {0, 1, 2, 5, 9, 17, 256} by `-D` per client JVM; controls: positive (S = 256, streams cache 4), unmap (S = 256, timeout 2000 ms), `hdfs dfs -cat` baseline; repeats S = 2, 9, 256; JDK 11 client runs S = 5, 256, unmap control. The default (256) is one of the values at both tiers. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: client off-heap file-backed mappings (one `mmap` per idle block replica), measured as `/proc` mappings, mapped bytes and RssFile; the check's operand `evictableMmapped.size()` is named as the counter. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b: 8 values incl. 256 (default); B3b: 7 values incl. 256, each a fresh client JVM via `-D`. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d/B3d: `/proc/self/maps` `blk_` mappings and bytes, `RssFile`/`VmSize`, external `/proc/<pid>/maps` and `pmap -x`; counter `outstandingMmapCount` named as unreliable on the close path (A3). |
| A. Core question | usage driven to the limit and past it | Met | 12 (unit) / 16 (cluster) idle replicas offered, more than `S − 1` for every S below N + 1. |
| A. Core question | positive control (negative estimate) | Met (n/a for a positive estimate) | Controls present anyway: streams-cache cap (a second cap binding on the same mappings), timeout/unmap control, non-mmap baseline (B2h/B3h). |
| B. Logic | each step says what it establishes | Met | B2h/B3h: positive control shows the instrument sees unmapping when a cap binds; time/unmap control shows munmap really removes `/proc` mappings on this JDK; baseline shows mappings come from zero-copy only. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f/B3f: per-step and after-close counts and bytes per S; relation `M(S) = min(N, max(S−1, 0))`. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met | B2g/B3g covered refuted, flat, counter-capped-memory-not, never-reached; missing rows for missing disallow evidence, other bounded numbers, failed controls and repeat mismatch. **Amended** (A5, A8). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met | The TRACE demotion line of the size branch was optional in B2d/B3d. **Amended** (A3, A6: required, counted per phase; A4, A7: predicted counts `N − M(S)`). |
| B. Logic | alternative explanations and their controls | Met | streams cache (fixed at 256, positive control at 4), timeout (1 h; time control), context reuse (distinct contexts; "counts identical for all S" row), zero-copy inactive (row + baseline). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3 steps 1–6, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met | B2a/B3a generic paths (`~/hadoop-3.4.2`, `/mydata/<run>`), no node specifics. **Amended** (A1, A6). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | B2b's context name `mmapcap-S<S>` would be reused by the B2h repeat (static `ClientContext` cache), and old phases' mappings would stay in the JVM. **Amended** (A2). RssFile had no tolerance. **Amended** (A7). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met | Test class and scripts are step-1 work; native prerequisites absent on `pc91` (installed with apt, A1). Cluster socket path `$R/sock/dn_socket` is 134 bytes on this node, over the 108-byte `sun_path` limit. **Amended** (A6). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 12 MiB (unit) and 1 GiB + 1 GiB block copy (cluster) on a 703 GB free `/mydata`; 125 GiB RAM; ~1 min per cluster run. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `systems/hadoop/source/` (HEAD `cd9e1cded`, source clean): `ShortCircuitCache.java:543` (check), `:532-563` (`demoteOldEvictableMmaped`, TRACE text `:550-555`), `:496-498`/`:516-517` (insert + trim on unref), `:568-587` (`trimEvictionMaps`, purge TRACE), `:369-391` (`fromConf`, `>= 0`), `:909-920` (close), `:964-993` (visitor); `ClientContext.java:210-235` (static cache by name); `DFSInputStream.java:1803-1912` (zero-copy read, `seek` past the block end so the reader is closed at the next read); `HdfsClientConfigKeys.java:502-510`. All as cited. |

| # | Recommendation | Applied? (amendment date, or "left for stage 3") | Why |
|---|---|---|---|
| R1 (A1, A6) | Node paths, native build in the case copy, surefire counts; socket directory short enough for `sun_path` | Applied 2026-11-25 (case file outside the repo; frozen sha256 above) | filed paths generic; `$R/sock/dn_socket` would make the DataNode fail to bind |
| R2 (A2) | Distinct context name and base directory per phase; per-phase `/proc` filter; close the phase's cache after its last reading | Applied 2026-11-25 | the static `ClientContext` cache keeps the first phase's `ShortCircuitCache` (and its mappings) for a reused name |
| R3 (A3, A4, A6, A7) | TRACE count of the size branch required, with predicted counts | Applied 2026-11-25 | confirmation needs direct evidence that the disallow branch fired |
| R4 (A5, A8) | Missing conclusions rows | Applied 2026-11-25 | every plausible outcome needs a row before any reading |
| R5 (A7) | RssFile tolerance; JDK 11 runs as optional client runs | Applied 2026-11-25 | "≈" is not decidable |
| R6 | B2f's `replicas` column says "stays 12 throughout after the loop" for every row, but the positive control purges replicas (4 remain); state it per row | Left for stage 3 | not load-bearing: the positive control's prediction is the after-close mapping count |
| R7 | B3a's probe imports both `java.nio.file.*` and `org.apache.hadoop.fs.*` (ambiguous `Path`/`FileSystem`) | Applied 2026-11-25 as A9 after the defect was hit (D-2) | runbook defect, not caught by the audit |

**Agreement criteria** — only if run 2 is chosen (see 5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-11-25 (node clock MST): prep 03:09:54–03:10:43, unit 03:14:18–03:15:55, cluster setup attempts 03:16:12 (D-1), 03:16:42 (D-2, daemons stopped 03:17:39), 03:17:39–03:18:12, cluster run 03:18:25–03:26:31 | not done |
| Node | `pc91` = `node0.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu`, 32 cores, 125 GiB (119 GiB free at start); node lock `/mydata/s4/NODE-LOCK` held 03:08:58–end; no Java process and ports 9000/9870/9864/9866/9867 free before the cluster run; base build per `environment.md` (2026-11-24, `hadoop-base/.../bin/hadoop` present) | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-203-generic`; `ulimit -n` 1024 | — |
| JDK (`java -version`) | OpenJDK `1.8.0_514` (`/usr/lib/jvm/java-8-openjdk-amd64`) for build, unit test, daemons and client; OpenJDK `11.0.33` (`/usr/lib/jvm/java-11-openjdk-amd64`) for the three JDK 11 client runs only | — |
| Build tool | Apache Maven 3.6.3 (offline `-o` for the unit tier; node `~/.m2` 3.4.2 artifacts from the base build); native: CMake 3.22.1, zlib1g-dev, libssl-dev, pkg-config installed with apt on 2026-11-25 (log `~/o12-apt.log` on `pc91`); `hadoop-common -Pnative` package 29.5 s (`run1/prep.log`) | — |
| Local source copy | `R1/src` (`R1=/mydata/jingsong-s4/<stem>-run1`) by `copy-source.sh` from `systems/hadoop/source/` (repository HEAD `cd9e1cded`, source clean), tag `rel/release-3.4.2`; only `TestMmapCacheSizeCap.java` added (`git status` in `run1/unit/unit-run.log`). Deleted after the run | — |
| Cluster distribution | copy of `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` + `libhadoop.so*` from the case copy in a created `lib/native/`; configs `R1/logs/cluster/{core,hdfs}-site.xml` (+ the TRACE line in `log4j.properties`, `run1/cluster/cluster-run.log`) | — |
| Case-file / harness version | sha256 `d03cfaa7…` (frozen, A1–A8), cluster tier on `9b31bc40…` (A9) / md5s in §1, uncommitted | — |
| Storage for node data | `R1/cluster/{nn,dn,tmp,data}` on local disk (1 GiB file + 1 GiB of blocks); socket `/mydata/jingsong-s4/o12-sock/dn_socket`; nothing on `/proj` | — |
| Full logs (path) | On `pc91`: `R1/logs/` (9.4 MB in all with `R1/harness/`): `prep/` (prep + native build log), `unit/` (surefire reports incl. the 6.9 MB `-output.txt` with all TRACE lines), `cluster/` (`cluster-run.log`, `format.log`, `daemon-logs/` NN + DN logs, `probe-out/` every probe's stdout+stderr and external check, the first 20 kB of the 97 MB `-cat` TRACE stderr). Copies of the evidence used here: `~/writeup-hadoop/out/o12/run1/` | — |

## 3. Runbook defects

| # | Step | Problem | Fix | Effect on §9a |
|---|---|---|---|---|
| D-0 | B3a (audit) | `$R/sock/dn_socket` is 134 bytes, over the 108-byte UNIX socket path limit | A6 (dated, before any reading) | none |
| D-1 | B3a step 3 (`checknative`), harness | `hadoop checknative -a` exits 1 when an optional library (zstd, bzip2) is absent; under `set -o pipefail` the harness read that as "libhadoop not loaded" although the output said `hadoop:  true` (`run1/cluster/cluster-run.log` lines 1–58) | harness: capture the output, test the `hadoop:` line only | none; no daemon had started, no reading existed |
| D-2 | B3e step 4 (compile the probe) | the probe as filed does not compile: `reference to Path is ambiguous` / `FileSystem is ambiguous` (`java.nio.file.*` vs `org.apache.hadoop.fs.*`) (`cluster-run.log` lines 238–253). Daemons and data of that attempt were up, no probe had run | case file A9 (two single-type imports); daemons stopped, the cluster tier restarted from B3e step 1 (fresh format, fresh data) at 03:17:39 | none (B3f/B3g unchanged) |
| D-3 | self-check parser | `selfcheck_unit.py` failed on the `IFCHK` header line that has no `step=` field (Python traceback, before printing any result) | parser: skip lines without `step=` | none |

## 4. Run 1

**Scope:** both tiers, every row of B2f and B3f plus the controls of B2h and B3h. **Command logs:** `run1/unit/unit-run.log`,
`run1/cluster/cluster-run.log` (the valid attempt after `##### setup attempt 3`). Raw data: `run1/unit/ifchk.txt` (the 375
`IFCHK` lines of the surefire `-output.txt`; the full output with the TRACE lines stays on the node), `run1/cluster/<tag>.log`
(every probe's stdout and stderr, TRACE lines included) and `run1/cluster/<tag>.ext` (external `/proc` check during the hold).

### 4.1 Readings

**Unit tier** (`run1/unit/ifchk.txt`, rep 1; rep 2 identical in every value; N = 12, block 1 MiB; `after-close` and `end` (+2 s) equal in every S row)

| S | after-close evictableMmapped | outstanding | blkMaps | blkMappedBytes | evictable (non-mmapped) | replicas | demoteNeed | demoteOld | purge | B2f + A4 |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 12 | 12 | 12 | 0 | 0 | = |
| 1 | 0 | 0 | 0 | 0 | 12 | 12 | 12 | 0 | 0 | = |
| 2 | 1 | 1 | 1 | 1048576 | 11 | 12 | 11 | 0 | 0 | = |
| 3 | 2 | 2 | 2 | 2097152 | 10 | 12 | 10 | 0 | 0 | = |
| 5 | 4 | 4 | 4 | 4194304 | 8 | 12 | 8 | 0 | 0 | = |
| 8 | 7 | 7 | 7 | 7340032 | 5 | 12 | 5 | 0 | 0 | = |
| 13 | 12 | 12 | 12 | 12582912 | 0 | 12 | 0 | 0 | 0 | = |
| 256 | 12 | 12 | 12 | 12582912 | 0 | 12 | 0 | 0 | 0 | = |
| posctl (256, streams 4) | 4 | **12** | 4 | 4194304 | 0 | 4 | 0 | 0 | 8 | = (outstanding see 4.2 part 6) |
| timectl (256, 500 ms), after-close → end (+3 s) | 12 → 0 | 12 → 0 | 12 → 0 | 12582912 → 0 | 0 → 12 | 12 | 0 | 0 → 12 | 0 | = |
| baseline (heap pool, mmap off) | 0 | 0 | 0 at every snapshot | 0 | 12 | 12 | 0 | 0 | 0 | = |

Per step (B2f columns 2–4): for every S row and both reps, after step i `evictableMmapped = min(i, M(S))`, `outstanding = blkMaps
= evictableMmapped + 1`, `blkMappedBytes = blkMaps × 1 MiB` (`run1/unit/selfcheck-unit.txt`). `blkMapsJvm` (all `/blk_` mappings
in the test JVM) equalled the per-phase `blkMaps` in every line, and was 0 after each phase's cleanup.

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Native code in the test JVM | `IFCHK,env native=true java=1.8.0_514` (the test asserts it, no `Assume` skip) | `run1/unit/ifchk.txt` line 1 |
| Every zero-copy read returned the full 1 MiB block | assertion in the loop; `reads=12 bytes=12582912` in every after-close line | `run1/unit/ifchk.txt` |
| Surefire `TestMmapCacheSizeCap` | 1 run, 0 failures, 0 errors, 0 skipped, 64.5 s | `run1/unit/mvn-test.log` line 155 |
| Raw TRACE lines `because we need more space` | 116 in the surefire output = 2 × (12+12+11+10+8+5+0+0) | `grep -c` on `R1/logs/unit/…-output.txt` (node) |

**Cluster tier** (`run1/cluster/<tag>.log`, `<tag>.ext`; N = 16, block 64 MiB = 67108864 B; RssFile Δ against the S = 0 run's `end` (28864 kB), JDK 11 rows against their own `before`; counts split at the probe's `after-close` line)

| Run | after-close blkMaps | blkMappedBytes | end (+30 s) blkMaps | external maps | RssFile end (kB) | RssFile Δ (MiB) | predicted Δ ± tol (MiB) | VmSize Δ (MiB) | demoteNeed | demoteOld | purge | B3f + A7 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S = 0 | 0 | 0 | 0 | 0 | 28864 | 0.0 | 0 ± 16 | 0.0 | 16 | 0 | 0 | = |
| S = 1 | 0 | 0 | 0 | 0 | 28976 | 0.1 | 0 ± 16 | −1.3 | 16 | 0 | 0 | = |
| S = 2 | 1 | 67108864 | 1 | 1 | 94548 | 64.1 | 64 ± 19.2 | 63.1 | 15 | 0 | 0 | = |
| S = 5 | 4 | 268435456 | 4 | 4 | 291076 | 256.1 | 256 ± 28.8 | 255.5 | 12 | 0 | 0 | = |
| S = 9 | 8 | 536870912 | 8 | 8 | 553100 | 511.9 | 512 ± 41.6 | 506.4 | 8 | 0 | 0 | = |
| S = 17 | 16 | 1073741824 | 16 | 16 | 1073736 | 1020.4 | 1024 ± 67.2 | 1020.6 | 0 | 0 | 0 | = |
| S = 256 | 16 | 1073741824 | 16 | 16 | 1073488 | 1020.1 | 1024 ± 67.2 | 1020.8 | 0 | 0 | 0 | = |
| posctl (256, streams 4) | 4 | 268435456 | 4 | 4 | 290880 | 255.9 | 256 ± 28.8 | 257.7 | 0 | 0 | 12 | = |
| unmapctl (256, 2000 ms) | 16 | 1073741824 | **0** | 0 | 25208 | −3.6 | 0 ± 16 (end) | −5.5 | 0 | 16 (all in the hold) | 0 | = |
| S = 2 rep 2 | 1 | 67108864 | 1 | 1 | 94496 | 64.1 | 64 ± 19.2 | 62.5 | 15 | 0 | 0 | = (= rep 1) |
| S = 9 rep 2 | 8 | 536870912 | 8 | 8 | 552988 | 511.8 | 512 ± 41.6 | 507.5 | 8 | 0 | 0 | = (= rep 1) |
| S = 256 rep 2 | 16 | 1073741824 | 16 | 16 | 1073724 | 1020.4 | 1024 ± 67.2 | 1020.0 | 0 | 0 | 0 | = (= rep 1) |
| S = 5, JDK 11 client | 4 | 268435456 | 4 | 4 | 290200 | 256.1 | 256 ± 28.8 | 263.2 | 12 | 0 | 0 | = (= JDK 8) |
| S = 256, JDK 11 client | 16 | 1073741824 | 16 | 16 | 1074112 | 1021.7 | 1024 ± 67.2 | 1027.4 | 0 | 0 | 0 | = (= JDK 8) |
| unmapctl, JDK 11 client | 16 | 1073741824 | **0** | 0 | 24524 | −3.2 | 0 ± 16 (end) | 9.0 | 0 | 16 (all in the hold) | 0 | = (= JDK 8) |

During the loop (B3f column 2), after step i: `blkMaps = 1` for S = 0, 1 and `min(i+1, S)` for S ≥ 2, `blkMappedBytes = blkMaps ×
64 MiB`, in every S run (`run1/cluster/selfcheck-cluster.txt`). Every probe printed its `conf dfs.client.mmap.cache.size=` line
with the value passed.

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Native code and socket | `hadoop:  true …/lib/native/libhadoop.so.1.0.0`; DataNode `Listening on UNIX domain socket: /mydata/jingsong-s4/o12-sock/dn_socket` | `run1/cluster/cluster-run.log` (attempt 3), `run1/cluster/dn-shortcircuit-excerpt.txt` line 1 |
| Data | `Total blocks (validated): 16 (avg. block size 67108864 B)`, HEALTHY | `cluster-run.log` (attempt 3, `hdfs fsck`) |
| Short-circuit in use | 256 `REQUEST_SHORT_CIRCUIT_FDS … success: true` DataNode lines in all = 16 blocks × 16 client runs (`-cat` + 15 probes) | `run1/cluster/dn-shortcircuit-excerpt.txt`, `cluster-run.log` last lines |
| `hdfs dfs -cat` baseline (B3e step 5) | 26 samples of the `-cat` JVM, max 0 `blk_` mappings | `cluster-run.log` `BASELINE samples=26 maxBlkMaps=0` |
| Disallow-branch lines | e.g. `TRACE shortcircuit.ShortCircuitCache: demoteOldEvictable: demoting ShortCircuitReplica{key=1073741825_…}…: because we need more space` | `run1/cluster/S5.log` line 339 |
| Daemons after the run | `no NameNode/DataNode/probe process` | `cluster-run.log` end of `run` |

### 4.2 Conclusion and logic

1. **Validity** — valid. Unit: native code loaded and asserted (`IFCHK,env native=true`), every read a full 1-MiB zero-copy
   mapping, surefire 1/0/0/0, each phase in its own context and cluster with `blkMapsJvm = blkMaps` (no leak between phases)
   [observed: `ifchk.txt`, `mvn-test.log`]. Cluster: `hadoop: true`, the DataNode listening on the domain socket, 16 blocks of
   64 MiB, short-circuit FDs served for every run, each probe's `conf` line equal to the value passed [observed:
   `cluster-run.log`, `dn-shortcircuit-excerpt.txt`, `<tag>.log`]. The limit was passed in every row with S ≤ N (12 / 16 idle
   replicas offered) [observed: `demoteNeed > 0` in those rows].
2. **Readings** — every value in 4.1 equals B2f/B3f and A4/A7 (unit 1351 checks, cluster 520 checks, 0 mismatches)
   [observed: `run1/unit/selfcheck-unit.txt`, `run1/cluster/selfcheck-cluster.txt`].
3. **Matched row** — Unit: B2g row 1 ("after-close evictableMmapped = M(S) for every S, and blkMaps equals it — claim
   confirmed; mechanism as traced, including the off-by-one"). Cluster: B3g row 1 ("after-close blkMaps = M(S) and
   RssFile/VmSize deltas ≈ M(S) × 64 MiB — the key caps idle mapped memory at S−1 entries"). The confirmation condition holds
   at both tiers: the ceiling follows S (0 → 16 mappings, 0 → 1 GiB) and the size branch's own TRACE line fired exactly
   `N − M(S)` times [observed].
4. **Excluded rows** — B2g/B3g row 2 (`min(N, S)`, no off-by-one): S = 1 keeps 0, S = 2 keeps 1, S = 5 keeps 4 [observed].
   Row 3 (> S): never [observed]. Row 4 (count capped, memory not): `blkMaps` (the `/proc` mappings) and RssFile fall with
   the count; the unmap control returns RssFile to below the S = 0 level on JDK 8 and JDK 11 [observed]. Row 5 (identical
   for all S): 0 … 16 [observed]. Row 6 (zero-copy inactive): mappings present at every step [observed]. A5/A8 rows: missing
   disallow evidence — `demoteNeed` > 0 in every S ≤ N row; other bounded numbers — none; failed control — none (positive
   control 4, time/unmap control 0, baselines 0); repeat mismatch — none; RssFile gap — none (all within tolerance) [observed].
5. **Observed vs. inferred** — The claim rests on observed readings. Inferred: (a) that the demotions are made by the check at
   `ShortCircuitCache.java:543` and not by the streams-cache purge or the timeout [inferred from: the TRACE text "because we
   need more space" is emitted only when that `if` falls through (`needMoreSpace = true`, `:545`), `purge` = 0 and
   `demoteOld` = 0 in every S row, and the positive control (a different cap on the same mappings) shows the other signature
   — `purge` = 12/8, `demoteNeed` = 0]; (b) that `blkMaps` after close is the cache's `evictableMmapped` at the cluster tier,
   where the internal list is not visible [inferred from: equality of the two at every unit-tier snapshot, and no reader
   holds a mapping after close].
6. **Deviations and gaps** — (i) Harness defect D-1 and runbook defect D-2 (§3) occurred before any cluster reading; the
   cluster tier restarted from a fresh format after D-2. (ii) In the unit positive control the cache's
   `outstandingMmapCount` read 12 while 4 mappings remained: replicas purged by `trimEvictionMaps` are unmapped by
   `ShortCircuitReplica.close` without the decrement — the "Close path" note of A3, observed; the `/proc` count, not the
   counter, is the reading B2g uses. (iii) VmSize is shape only (A7); its deltas follow blkMappedBytes within 10 MiB in every run
   (largest gap: +9.0 MiB at the JDK 11 unmap control's end with 0 mappings, i.e. JVM arenas). (iv) The cluster TRACE configuration also reached the
   `hdfs dfs -cat` client (97 MB of TRACE stderr, truncated to 20 kB in the evidence); it does not affect any reading.
7. **Core question** — Usage follows the constraint. With the same workload, the idle mapped memory the client kept was
   0, 0, 64, 256, 512, 1024, 1024 MiB (mappings 0, 0, 1, 4, 8, 16, 16; RssFile +0 … +1020 MiB) at S = 0, 1, 2, 5, 9, 17, 256,
   i.e. `max(S−1, 0)` block mappings until all 16 blocks fit, and the unit tier showed the same staircase at eight values
   with the cache's own list size equal to the mapping count (parts 2–3). The size branch fired for exactly the entries over
   the limit (part 3). So `dfs.client.mmap.cache.size` caps the client's idle mmap footprint, at `S − 1` entries per cache,
   one fewer than `hdfs-default.xml` states.

**Conclusion (one line):** Unit: B2g row 1 — confirmed. Cluster: B3g row 1 — confirmed.

## 5. Self-check of run 1 — AI

`harness/selfcheck_unit.py` re-parses every `IFCHK` line (`run1/unit/ifchk.txt`, 375 lines) and `harness/selfcheck_cluster.py`
re-parses every probe log and external check (`run1/cluster/<tag>.log`, `<tag>.ext`), not the tables above, and compares each
value with B2f/B3f, B2h/B3h and A4/A7: **unit 1351 ok, 0 mismatches; cluster 520 ok, 0 mismatches**.

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `ifchk.txt` line 1 `native=true`; `reads=12 bytes=12582912` in all 22 after-close lines; `mvn-test.log` line 155 `Tests run: 1, Failures: 0, Errors: 0, Skipped: 0`; `cluster-run.log` attempt 3: `hadoop:  true`, `Total blocks (validated): 16`; `dn-shortcircuit-excerpt.txt` socket line and 256 FD lines; each `<tag>.log` `conf` line |
| 2. Readings | yes | `selfcheck-unit.txt`, `selfcheck-cluster.txt`; 4.1 tables re-read against `ifchk.txt` after-close/end lines and the cluster table printed by `selfcheck_cluster.py` |
| 3. Matched row | yes | ceiling follows S at 8 (unit) and 7 (cluster) values incl. the default; `demoteNeed` = 12 − M(S) / 16 − M(S) in every row; TRACE text checked in `S5.log` line 339 |
| 4. Excluded rows | yes | S = 1 → 0 and S = 2 → 1 rule out `min(N, S)`; unmap control `end blkMaps=0 … RssFile: 25208 kB` (`unmapctl.log`) and `24524 kB` (`unmapctl-jdk11.log`) rule out "count capped, memory not" |
| 5. Observed vs. inferred | yes | (a) source `ShortCircuitCache.java:542-556` re-read: the "need more space" rationale is set only after the size check falls through; `purge`/`demoteOld` 0 in all S rows; posctl `purge=12` (`posctl.log` line 339 first purge line); (b) unit `evictableMmapped` = `blkMaps` in every snapshot (`ifchk.txt`) |
| 6. Deviations and gaps | yes | D-1/D-2 lines in `cluster-run.log` (58, 253) precede the attempt-3 marker (259); posctl `outstanding=12 … replicas=4` in `ifchk.txt` |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B2h/B3h logic: streams cache 256 and timeout 1 h keep the other two trimming paths out (their counts 0); baseline shows mappings come only from zero-copy; time/unmap control shows `munmap` removes `/proc` mappings on JDK 8 and 11, so a falling mapping count is falling memory |

### 5.2 Run 2?

**No** — decided 2026-11-25. Every reading matched the frozen prediction exactly at both tiers (including the off-by-one and
the disallow-branch counts), the result confirms the stage-3 estimate rather than refuting it or confirming a bypass, the
repeats within run 1 were identical, every control behaved, and the inferred statements (part 5) are settled by run 1's own
raw files.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** **true positive** — estimate `positive`, effect `caps` at the unit and the
cluster tier.

**Claim tested:** (B1) for a DFSClient doing zero-copy short-circuit reads that releases each buffer, the number of idle
block-file mappings kept by one `ShortCircuitCache`, and the memory they hold (mapped bytes, file-backed RSS), stays at or
below `max(S−1, 0)` mappings, S = `dfs.client.mmap.cache.size`, and grows with S until it reaches the number of blocks read.
"Confirmed" below always means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1: after-close `evictableMmapped` = `/proc` mappings = 0 / 0 / 1 / 2 / 4 / 7 / 12 / 12 at S = 0 / 1 / 2 / 3 / 5 / 8 / 13 / 256; `demoteNeed` = 12 − M(S); rep 2 identical | caps (at `S − 1` idle mappings) | run 1 + self-check | 2026-11-25 |
| Cluster | **Confirmed** — B3g row 1: after-close mappings 0 / 0 / 1 / 4 / 8 / 16 / 16 (0 … 1 GiB mapped, RssFile +0 … +1020 MiB) at S = 0 / 1 / 2 / 5 / 9 / 17 / 256; `demoteNeed` = 16 − M(S); repeats and JDK 11 client identical | caps (at `S − 1` idle mappings; in-use mappings are not counted, per A3) | run 1 + self-check | 2026-11-25 |

**Positive control:** with S = 256 (not binding) and `dfs.client.read.shortcircuit.streams.cache.size = 4`, the same workload
and instruments stop at 4 mappings (4 MiB unit, 256 MiB cluster) through the purge path; with a short mmap timeout, all
mappings are removed from `/proc` and RssFile returns to baseline (JDK 8 and JDK 11).

**Feedback filed:** the amended case file's section D1 (audit amendments A1–A8, 2026-11-25, before any reading, and A9 after
defect D-2) and D2 "Stage-4 result" (2026-11-25), in `/users/jason92/writeup-hadoop/out/o12/case-amended.md`; R6 left for stage 3.
Nothing in the repository was edited (`_INDEX.md`, `queue.csv`, HANDOFF are left to the parent session).

**Left on the node:** `/mydata/jingsong-s4/dfs.client.mmap.cache.size-demoteOldEvictableMmaped-maxEvictableMmapedSize--autonomous-run1/`
(9.4 MB: `harness/`, `logs/`); the source copy, the distribution copy, the 1 GiB data file, all NN/DN data, the socket directory
`/mydata/jingsong-s4/o12-sock` and the 97 MB `-cat` TRACE file were deleted. No daemon, test JVM, Maven or probe process (`jps`
showed only `Jps`), ports free, driver PID file removed. apt packages `cmake`, `zlib1g-dev`, `libssl-dev`, `pkg-config` stay
installed on `pc91` (needed for any native build; `environment.md` lists them only for `pc75`). Node lock released. Undo:
`rm -rf /mydata/jingsong-s4/dfs.client.mmap.cache.size-demoteOldEvictableMmaped-maxEvictableMmapedSize--autonomous-run1/`.
