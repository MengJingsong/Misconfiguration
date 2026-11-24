# CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous — stage-4 results  <!-- file: results/CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous.md -->

> **Case:** [`CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous.md) (stage-3 queue order 21; at run time the case file is
> `/users/jason92/writeup-hadoop/out/o21/CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous.md`, outside the repository)
>
> **Status:** **verdict filed 2026-11-24** — unit **Confirmed** (caps), cluster **Confirmed** (caps). Claim tested: for a cache
> pool with limit L, the bytes the HDFS centralized cache holds for the pool's directives never exceed L once the rescan has
> settled; files are admitted in name order while the cumulative `size × replication` stays ≤ L, everything after the first
> crossing is skipped, and lowering L on a live pool uncaches down to ≤ L. Every predicted number matched exactly at both
> tiers (unit 55/55 checks, cluster 71/71): cached bytes 0 / 2 / 2 / 4 / 6 blocks at L = 0 / 2 / 2.5 / 4 / ≥ 6 blocks, real
> DataNode locked memory (`VmLck`) 0 / 2048 / 2048 / 4096 / 6144 kB at the cluster tier, the skipped files named by the
> check's own DEBUG line. One run 1, no run 2.
>
> **Outcome class:** **true positive** — stage-3 estimate `positive` against the stage-4 effect `caps` at both tiers
> ([definition](../../../../stage4-runtime-verification/README.md#outcome-class))
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Layout.** Hadoop, Jingsong's share, run by an autonomous stage-4 agent on node `pc75`. At run time this file, the harness and the
raw excerpts are outside the repository: this file `~/writeup-hadoop/out/o21/results.md`, harness `~/writeup-hadoop/out/o21/harness/`,
raw excerpts `~/writeup-hadoop/out/o21/run1/` (cited below as `run1/...`). When filed in the repository they go to
`hadoop/stage4-runtime-verification/jingsong/results/` (this file and `results/<stem>/run1/`) and `.../jingsong/harness/<stem>/`.
Protocol: `experiments/capacity-enforcement-exp/stage4-runtime-verification/README.md` "The run protocol"; node environment:
`hadoop/stage4-runtime-verification/jingsong/environment.md` (`pc75` is not yet in its Node table; see §2).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file written by stage 3 on 2026-11-24 (not in the repository at audit time; repository HEAD `8f76f2390`). sha256 as received: `8bbbfa2b2651ff72d68ac0b12c4fb2e771ea2810943e828028075402bc64735a`. After the audit's amendments A1–A8 (section D1), 2026-11-24 01:18 EST, before any harness run or reading: whole-file sha256 **`b60c6fe5a33ef49ea2b369bf77fed3069fc13059ad0d9d433ef6702942764265`** (frozen version). Frozen prediction, conclusions and controls: sha256 of the text from `**B2f.` up to `### B3.` (B2f–B2h with A7) `4d9b2cb792bdc821ebc68219e7787cf35235a3d44a39d92142c73826c0866d5a`; from `**B3f.` up to `**B4.` (B3f–B3h with A7) `4911289743483bc282514bf5e2cead1d8e3328005b25d6e76cfba2e781a19c9d`. |
| **After the run** | Section D2 added 2026-11-24 after run 1: whole-file sha256 `b22392a8ca78015c8e2f58e44fea06911ad146b42e63cb859a72ef857f2a4f10`; the two text hashes above re-computed and unchanged. |
| **Harness** | `~/writeup-hadoop/out/o21/harness/` (written after the freeze, before run 1): `TestPoolLimitRescanCap.java` md5 `d8c2823e`, `unit-run.sh` `4fb331f1`, `cluster-run.sh` `f12be118` (final; two harness defects fixed before any cluster reading, §3), `sampler.py` `c9198160`, `selfcheck.py` `6d475714` (final; one parser fix after the unit run, §3). Not committed (outside the repository). Instrument checks: `unit-run.sh --compile-only` BUILD SUCCESS 2026-11-23 23:17 MST (node time) (`run1/unit/unit-run.log`); known answers in the runs themselves: unit `IFCHK,instr` (NoMlock manipulator, DN cache capacity 65536 / 12288 as configured), the unlimited row caches all 6 blocks and the DN-cap control stops at 3; cluster `hadoop checknative` → `hadoop: true` (`run1/cluster/cluster-run.log`), DataNode started with `maxLockedMemory = 8388608` / `3145728` (`run1/cluster/dn-native-excerpt.txt`), `VmLck` baseline 0 kB and 6144 kB in the unlimited row (6 × 1 MiB). |
| **Tiers and values** | Unit (B2): B = 4096, 1 DN with 64 KiB cache, six 1-block files; L ∈ {0, 2B, 2.5B, 4B, 6B, unlimited}, live lowering unlimited → 3B, order case (q, L = 3B; 1B/3B/1B), add-time contrast (pool r, L = 2B, without and with FORCE), DN-cap control (pool unlimited, DN cap 3B). Cluster (B3): pseudo-distributed NN + DN, native mlock, U = 1 MiB, DN cap 8U, six 1-MiB files; L ∈ {unlimited, 0, 2U, 2.5U, 4U}, live lowering unlimited → 3U, `-force` into L = 2U, DN-cap control (DN cap 3U). The default value of the constraint (unlimited) is one of the values at both tiers. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-24 |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: DataNode off-heap locked memory (mmap + mlock of block replicas) attributable to a cache pool; the check's operand `pool.getBytesNeeded()` is named as the counter. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b: 6 values (0 … unlimited = default) plus live lowering; B3b: 5 values incl. unlimited plus live lowering; set through the real admin path (`addCachePool`/`-addPool -limit`, `modifyCachePool`/`-modifyPool`). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B3d: `/proc/<DN>/status` `VmLck` (real locked memory) besides JMX `CacheUsed` and pool stats; B2d names the gap at the unit tier (mlock stubbed, DN accounting only). |
| A. Core question | usage driven to the limit and past it | Met | Demand 6 blocks / 6U exceeds every finite L except 6B (equality row) at both tiers; DN capacity above demand so only L binds. |
| A. Core question | positive control (negative estimate) | Met (n/a for a positive estimate) | Controls present anyway: unlimited row (workload fills the cache) and DN-cap control (a known binding cap moves the same instruments), B2h/B3h. |
| B. Logic | each step says what it establishes | Met | B2h/B3h: empty-directory directive isolates the rescan check from the add-time check; `-force` row shows the add-time bypass does not lift the cap; single DN, replication 1. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f/B3f: exact bytes, block counts and VmLck kB per row; relation CacheUsed ≤ L. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met | B2g/B3g lacked a row for "≤ L but a count differs from the prediction", for missing disallow-branch evidence, and (cluster) for "counter capped, VmLck above L". **Amended** (A7). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met | The DEBUG line of the check (`not scanning file … because bytesNeeded for pool …`) was optional in B2d/B3d. **Amended** (A2, A7, A8: required, with the expected skipped-file set per row). |
| B. Logic | alternative explanations and their controls | Met | DN capacity (DN cap > demand; DN-cap control), add-time check (empty directory; `-force` row), caching not working (unlimited row), other locked memory (VmLck baseline). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3 steps 1–5, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met | B2a/B3a named generic paths and a `-Pnative` build without node specifics; **amended** (A1, A4). Steady-state rule ("two consecutive readings") too weak for a 1-s rescan; **amended** (A2, A6). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | The add-time contrast shared cache state with other pools (A3, A5). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met | Test class and scripts are step-1 work. Native code: the base distribution on `pc75` has no `libhadoop`; CMake and zlib headers were absent; **amended** (A4: apt install, native `hadoop-common` build in the case copy). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly → Met | Arithmetic fine (6 MiB of blocks, ≤ 8 MiB locked, `ulimit -l` 16 GB). But B3c/B3e as filed re-add the directive on the populated `/d`, which the add-time check rejects for every finite L < 6U: the cluster rows could not run as written. **Amended** (A8: files moved out to `/stash` and back after the directive). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `systems/hadoop/source/` (HEAD `8f76f2390`, clean): `CacheReplicationMonitor.java:389-411` (rescanFile, check at 403, `return`), `:364-372` (directory children), `:413-456` (block marking); `CacheManager.java:456-469` (`checkLimit`), `:586-589` (FORCE), `:876-882` (`setLimit` + `setNeedsRescan`); `CachePool.java:250-257, 281, 297-304`; `CachePoolInfo.java:54-55, 221-223`; `DataNode.java:1892-1911`; `FsDatasetCache.java:386-389`. All as cited. |

| # | Recommendation | Applied? (amendment date, or "left for stage 3") | Why |
|---|---|---|---|
| R1 (A1) | Node paths, no `install` step, surefire counts | Applied 2026-11-24 (case file outside the repo; frozen sha256 above) | filed paths generic; `install` unnecessary with the node's `~/.m2` |
| R2 (A2) | Steady-state rule; required DEBUG evidence with the expected skipped-file set | Applied 2026-11-24 | two equal readings 500 ms apart can fall between rescans; confirmation needs direct disallow evidence |
| R3 (A3, A5) | Add-time contrast on an otherwise empty cache | Applied 2026-11-24 | with pool `p` still holding f01–f03, the DN reading for pool `r` would be 3 MiB, not 2 MiB |
| R4 (A4) | Native build on `pc75` | Applied 2026-11-24 | a DataNode with `max.locked.memory > 0` does not start without native mlock |
| R5 (A6) | Cluster plateau rule and VmLck baseline | Applied 2026-11-24 | "last 10 samples equal" needed a minimum and maximum duration |
| R6 (A7) | Missing conclusions rows | Applied 2026-11-24 | every plausible outcome needs a row before any reading |
| R7 (A8) | Directive on an empty `/d` for every cluster knob value | Applied 2026-11-24 | runbook defect: the add-time check would reject the re-added directive |
| R8 | B3f says "within ~10 s" for the live-lowering transition without defining which observable; state it per observable (VmLck vs CacheUsed) | Left for stage 3 | not load-bearing: the plateau rule (A6) defines the reading |

**Agreement criteria** — only if run 2 is chosen (see 5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-11-24 EST (node clock MST: unit 23:18–23:21, cluster attempt 1 23:37:07–23:37:30 aborted, attempt 2 23:37:58–23:56:19) | not done |
| Node | `pc75` = `node3.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 125 GiB; node lock `/mydata/s4/NODE-LOCK` held for the whole run; no other Java process (`jps`) and ports 8020/9870/9864/9866/9867 free before the cluster run. `pc75` is not in `environment.md`'s Node table (base build by `setup-node.sh` finished 2026-11-24, `BUILD SUCCESS` 30:55 min, `Hadoop 3.4.2`, 19 YARN jars, per `~/jingsong-setup-node.log` on `pc75`) — table update left to the parent session | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-203-generic`; `ulimit -l` 16492912 KB | — |
| JDK (`java -version`) | OpenJDK `1.8.0_504` (`/usr/lib/jvm/java-8-openjdk-amd64`) for build, unit tests and daemons | — |
| Build tool | Apache Maven 3.6.3; node `~/.m2` 3.4.2 artifacts from the base build; native: CMake 3.22.1, zlib1g-dev, libssl-dev (installed with apt on 2026-11-24 for A4; log `~/o21-apt.log` on `pc75`) | — |
| Local source copy | `/mydata/jingsong-s4/CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous-run1/src` by `copy-source.sh` from `systems/hadoop/source/` (repository HEAD `8f76f2390`, source clean), tag `rel/release-3.4.2`; only `TestPoolLimitRescanCap.java` added (`git status` in `run1/unit/unit-run.log`); `hadoop-common` built with `-Pnative` there. Deleted after the run | — |
| Cluster distribution | copy of `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` + `libhadoop.so.1.0.0` from the case copy; configs `run1`-local (`core-site.xml`, `hdfs-site.xml` kept in the node's logs dir) | — |
| Case-file / harness version | sha256 `b60c6fe5…` (frozen, A1–A8) / md5s in §1, uncommitted | — |
| Storage for node data | `/mydata/jingsong-s4/…-run1/cluster/{nn,dn,tmp}` on local disk (6 MiB of blocks); nothing on `/proj` | — |
| Full logs (path) | On `pc75`: `/mydata/jingsong-s4/CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous-run1/logs/` (`unit/` with surefire reports; `cluster/` with `cluster-run.log`, `samples-*.csv`, native build logs, `daemon-logs/` NN + DN logs with the DEBUG lines, `aborted-233759/`). Copies of the evidence used here: `~/writeup-hadoop/out/o21/run1/` | — |

## 3. Runbook defects

| # | Step | Problem | Fix | Effect on §9a |
|---|---|---|---|---|
| D-0 | B3c/B3e (audit) | Directive re-added on the populated `/d` would fail the add-time check for finite L < 6U | A8 (dated, before any reading) | none (claim and numbers unchanged) |
| D-1 | A4, cluster setup | the non-native distribution has no `lib/native/` directory; `cp` of `libhadoop.so*` failed (`STOP: copy native`, `run1/cluster/cluster-run.log` first block) | harness: `mkdir -p $RUN/hadoop/lib/native` | none; setup re-run, no reading existed |
| D-2 | B3e step 2, cluster attempt 1 | harness bug: the "1 live DataNode" wait parsed `Live datanodes (1):` with the wrong field separator and would have looped to failure; attempt aborted 23:37:30, 18 s after the DataNode started, before any workload or reading; daemons stopped (`ps` check clean) | harness: parse with `grep -oE`; each attempt starts from a fresh NN/DN state (previous daemon logs kept in `logs/cluster/aborted-233759/`); cluster tier restarted from format (attempt 2) | none |
| D-3 | self-check parser | `selfcheck.py` read the `directivesAfterNoForce` field from the same line as the exception message, but the unit test prints the server stack inside that message, so the field sits 18 lines lower (`run1/unit/…-output.txt` line 4396) | parser: search the whole output | none; the raw reading (0) was already there |

## 4. Run 1

**Scope:** both tiers, every row of B2f and B3f. **Command logs:** `run1/unit/unit-run.log`, `run1/cluster/cluster-run.log`
(attempt 2 after the line `##### attempt 2`). Raw data: `run1/unit/ifchk.csv` (the `IFCHK` lines of the surefire
`-output.txt`), `run1/cluster/samples-<phase>.csv` (every 2-s sample), `CLCHK` lines in `cluster-run.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/ifchk.csv`; B = 4096; every row `settled=true` within 5.5–9.4 s; NN cached-block count = DN blocks in every row)

| Case | BYTES_NEEDED | BYTES_CACHED | DN cacheUsed | DN blocks | BYTES_OVERLIMIT | skipped files (DEBUG, steady window) | B2f |
|---|---|---|---|---|---|---|---|
| L = 0 | 24576 | 0 | 0 | 0 | 24576 | /d/f01 … f06 | = |
| L = 8192 (2B) | 24576 | 8192 | 8192 | 2 | 16384 | /d/f03 … f06 | = |
| L = 10240 (2.5B) | 24576 | 8192 | 8192 | 2 | 14336 | /d/f03 … f06 | = |
| L = 16384 (4B) | 24576 | 16384 | 16384 | 4 | 8192 | /d/f05, f06 | = |
| L = 24576 (6B) | 24576 | 24576 | 24576 | 6 | 0 | none | = |
| unlimited | 24576 | 24576 | 24576 | 6 | 0 | none | = |
| lowering, before | 24576 | 24576 | 24576 | 6 | 0 | none | = |
| lowering, after (L = 12288) | 24576 | 12288 | 12288 | 3 | 12288 | /d/f04 … f06 | = |
| order (q, L = 3B; a1 = 1B, a2 = 3B, a3 = 1B) | 20480 | 4096 | 4096 | 1 | 8192 | /e/a2, /e/a3 | = |
| FORCE into r (L = 2B) | 24576 | 8192 | 8192 | 2 | 16384 | /d/f03 … f06 | = |
| DN-cap control (pool unlimited, DN cap 12288) | 24576 | 12288 | 12288 | 3 | 0 | none | = |

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Add-time check without FORCE | `InvalidRequestException: Caching path /d of size 24576 bytes at replication 1 would exceed pool r's remaining capacity of 8192 bytes.` (from `CacheManager.checkLimit(CacheManager.java:467)`); 0 directives afterwards | `run1/unit/…-output.txt` lines 4378–4396 |
| Add-time with FORCE | accepted (directive id 1), then the FORCE row above | `run1/unit/ifchk.csv` |
| Surefire `TestPoolLimitRescanCap` | 10 run, 0 failures, 0 errors, 113.8 s | `run1/unit/org.apache.hadoop.hdfs.server.namenode.TestPoolLimitRescanCap.txt` |

**Cluster tier** (`CLCHK` lines in `run1/cluster/cluster-run.log`; U = 1048576; VmLck baseline 0 kB before every phase and after the DN restart; every phase `settled=True` at 61.0–61.6 s, 28–29 samples; BYTES_NEEDED 6291456 in every row)

| Case | BYTES_CACHED | CacheUsed (JMX) | NumBlocksCached | VmLck Δ (kB) | max CacheUsed in phase | skipped files (NN DEBUG, last 10 samples) | B3f |
|---|---|---|---|---|---|---|---|
| unlimited | 6291456 | 6291456 | 6 | 6144 | 6291456 | none | = |
| L = 0 | 0 | 0 | 0 | 0 | 0 | /d/f01 … f06 | = |
| L = 2U | 2097152 | 2097152 | 2 | 2048 | 2097152 | /d/f03 … f06 | = |
| L = 2.5U | 2097152 | 2097152 | 2 | 2048 | 2097152 | /d/f03 … f06 | = |
| L = 4U | 4194304 | 4194304 | 4 | 4096 | 4194304 | /d/f05, f06 | = |
| unlimited → 3U, before | 6291456 | 6291456 | 6 | 6144 | — | none | = |
| unlimited → 3U, after | 3145728 | 3145728 | 3 | 3072 | 6291456 (before the drop) | /d/f04 … f06 | = |
| `-force` into r, L = 2U | 2097152 | 2097152 | 2 | 2048 | 2097152 | /d/f03 … f06 | = |
| DN cap 3U, pool unlimited | 3145728 | 3145728 | 3 | 3072 | 3145728 | none | = |

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `-addDirective -path /d -pool r` without `-force` | `InvalidRequestException: … would exceed pool r's remaining capacity of 2097152 bytes.`, rc 2; `-listDirectives -pool r` → 0 entries | `run1/cluster/cluster-run.log` (23:52:38–41) |
| Live-lowering transition | pool BYTES_CACHED 3145728 at the first sample (2.2 s); VmLck 6144 → 3072 kB between 2.2 s and 4.4 s; JMX CacheUsed 6291456 until 10.9 s, 3145728 from 13.1 s | `run1/cluster/samples-lowering-after.csv` |
| `dfsadmin -report` at plateau | Cache Used 4 MB (L = 4U), 6 MB (lowering before), 3 MB (DN-cap) — same as JMX | `run1/cluster/cluster-run.log` |
| Disallow-branch lines | 821 `not scanning file` lines in the NN log in all; e.g. `Directive 2: not scanning file /d/f01 because bytesNeeded for pool p is 1048576, but the pool's limit is 0` | `run1/cluster/nn-skip-excerpt.txt` |

### 4.2 Conclusion and logic

1. **Validity** — valid. Unit: every row settled under A2's rule (10 equal polls, ≥ 5 s) [observed: `ifchk.csv`]; instruments as configured (`IFCHK,instr`: NoMlock manipulator, DN cache capacity 65536, and 12288 for the control) [observed]; surefire 10/0/0 [observed]. Cluster: native code loaded (`hadoop: true`), DataNode started with `maxLockedMemory = 8388608` (3145728 after the restart), cache capacity reported 8 MB / 3 MB, VmLck baseline 0 kB [observed: `cluster-run.log`, `dn-native-excerpt.txt`]; every phase plateaued under A6's rule; the cache was empty (CacheUsed 0, VmLck 0) before every phase [observed: `waitzero` lines]. The limit was passed in every finite-L row (BYTES_NEEDED 6 blocks / 6U > L) [observed].
2. **Readings** — all §4.1 rows equal B2f / B3f to the byte, block and kB; the skipped-file sets equal those of A2 / A8 [observed: `run1/selfcheck.txt`, 126 PASS, 0 FAIL].
3. **Matched row** — Unit: B2g row 1 ("rows match B2f; BYTES_CACHED and DN cache used step with L and never exceed it"), with rows 2 (L = 2.5B caches 2, 2B caches 2, 6B caches 6) and 3 (order case caches a1 only although a3 fits) [observed]. Cluster: B3g rows 1–3 (CacheUsed and VmLck Δ follow B3f, ≤ L, stepping by 1 MiB; L = 2.5U gives 2 MiB; live lowering drops VmLck to 3072 kB) [observed]. The A7 condition for confirmation holds at both tiers: the ceiling follows L and the check's own DEBUG line names exactly the files predicted to be skipped [observed].
4. **Excluded rows** — *> L at steady state* (Refuted): max steady BYTES_CACHED / CacheUsed / VmLck Δ never above L in any finite-L row [observed]. *L = 0 / 2B (2U) caches all 6* (Refuted): 0 and 2 [observed]. *Live lowering leaves 6 cached > 60 s*: 3 blocks from 13.1 s (JMX), VmLck from 4.4 s [observed]. *Setup broken* (unlimited < 6, DN-cap ≠ 3, VmLck not moving): 6 / 3 / VmLck moves with CacheUsed [observed]. A7 rows: *count differs while ≤ L* — none [observed]; *no DEBUG line* — present in every row with < 6 cached, absent in the unlimited, 6B and DN-cap rows [observed]; *counter capped but VmLck above L* — VmLck Δ = CacheUsed / 1024 in every row, c = 0 [observed]. *VmLck larger by a constant* — no offset (baseline 0, L = 0 row 0 kB) [observed].
5. **Observed vs. inferred** — The claim rests on observed readings. Inferred: (a) that the cut-off is made by the check at `CacheReplicationMonitor.java:403` and not by DN capacity [inferred from: the DEBUG line is emitted only inside that `if`, it names exactly the uncached files, and DN capacity (16B / 8U) exceeds demand; the DN-cap control shows a different signature — no DEBUG line, BYTES_OVERLIMIT 0]; (b) that `VmLck` is the cache's locked memory [inferred from: baseline 0 kB with daemons up and no directive, and VmLck Δ = CacheUsed/1024 in all 9 rows, including the transition rows].
6. **Deviations and gaps** — (i) Harness defects D-1, D-2 and D-3 (§3) occurred before any cluster reading (D-1, D-2) or concern only the parser (D-3); the cluster tier was restarted from a fresh format. (ii) At the unit tier mlock is stubbed (named in B2d); real locked memory is covered at the cluster tier only. (iii) Live-lowering lag: real locked memory dropped within ~4 s, but the DataNode's `CacheUsed` counter lagged until ~13 s (B3f's "within ~10 s", read with the 2-s sampling grid: last 6 MiB sample at 10.9 s). The lag is in the counter, below the real memory, so it cannot refute the cap; recorded as recommendation R8. (iv) The unit tier ran while the node's base build was finishing its last modules (CPU contention only; readings settled normally).
7. **Core question** — Usage follows the constraint. With the same six files, the real locked memory of the DataNode was 0, 2048, 2048, 4096 and 6144 kB at L = 0, 2U, 2.5U, 4U and unlimited, i.e. the largest whole-file prefix ≤ L, and the unit tier showed the same staircase in DN cache accounting at six L values (parts 2–3). The disallow branch fired for exactly the files past the first crossing, including a file that would have fit (order case, a3) (part 3). Lowering L on a live pool uncached down to the new L, and `-force` lifted only the add-time check, not the cap (part 4). So the pool limit caps the pool's cached (mlocked) bytes.

**Conclusion (one line):** Unit: B2g row 1 (with rows 2, 3) — confirmed. Cluster: B3g rows 1–3 — confirmed.

## 5. Self-check of run 1 — AI

`harness/selfcheck.py` re-parses the raw surefire `-output.txt` and the `CLCHK` lines of `cluster-run.log` (not the tables above) and compares every value with B2f/B3f and A2/A8; output `run1/selfcheck.txt`: **126 PASS, 0 FAIL** (unit 55, cluster 71).

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `ifchk.csv`: `settled=true` ×11, `IFCHK,instr` ×10; `…TestPoolLimitRescanCap.txt` 10/0/0; `cluster-run.log` attempt 2: `hadoop:  true`, `Configured Cache Capacity: 8388608`, `VmLck baseline (kB) = 0`, `CacheUsed=0 after 2 s; VmLck=0 kB` before each phase; `dn-native-excerpt.txt` maxLockedMemory lines |
| 2. Readings | yes | `selfcheck.txt` every value check PASS; §4.1 tables re-read against `ifchk.csv` and the `CLCHK` lines |
| 3. Matched row | yes | ceiling follows L at 6 (unit) and 5 (cluster) values incl. the default; DEBUG sets equal A2/A8 in every row |
| 4. Excluded rows | yes | `maxDnCacheUsed` ≤ L in every unit row (lowering-after's 24576 is the pre-change value; its steady reading 12288); cluster `maxCacheUsed` ≤ L in every finite-L phase except lowering-after (pre-change 6 MiB, documented) |
| 5. Observed vs. inferred | yes | (a) `nn-skip-excerpt.txt` shows the message text of `:404-410`; DN-cap row: `skipWindowLines=0`, BYTES_OVERLIMIT 0; (b) `samples-*.csv`: `VmLck_kB` × 1024 = `CacheUsed` in every plateau row |
| 6. Deviations and gaps | yes | `samples-lowering-after.csv` rows at 2.2–13.1 s as quoted; defects §3 with their log lines |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B2h/B3h logic: empty-directory directive (add-time check passed, `noForce=accepted` in every `IFCHK,directive`) → only the rescan check can cut; DN capacity > demand → not the DN cap; unlimited row → workload caches; DN-cap control → instruments move under a different cap |

### 5.2 Run 2?

**No** — decided 2026-11-24. Every reading matched the frozen prediction exactly at both tiers, the result confirms the stage-3 estimate rather than refuting it or confirming a bypass, both controls behaved, and the only inferred statements (part 5) are settled by run 1's own raw files.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** **true positive** — estimate `positive`, effect `caps` at the unit and the cluster tier.

**Claim tested:** (B1) for a cache pool with limit L, the bytes the HDFS centralized cache actually holds for that pool's directives (cached replica bytes on DataNodes, i.e. mlocked DataNode memory) never exceed L once the rescan has settled: files are admitted in directive-ID / file-name order while the cumulative `size × replication` stays ≤ L, everything after the first crossing is not cached, and lowering L on a live pool uncaches down to ≤ L; with L = unlimited the workload is cached in full.
"Confirmed" below always means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (+ rows 2, 3): DN cache 0 / 8192 / 8192 / 16384 / 24576 / 24576 B at L = 0 / 2B / 2.5B / 4B / 6B / unlimited; lowering → 12288; order case a1 only; FORCE row = 2B row; DEBUG lines name the skipped files | caps | run 1 + self-check | 2026-11-24 |
| Cluster | **Confirmed** — B3g rows 1–3: VmLck Δ 6144 / 0 / 2048 / 2048 / 4096 kB at L = unlimited / 0 / 2U / 2.5U / 4U = CacheUsed = BYTES_CACHED; lowering 6144 → 3072 kB; `-force` into 2U → 2048 kB; DEBUG lines name the skipped files | caps (`-force` bypasses only the add-time check, not the cap) | run 1 + self-check | 2026-11-24 |

**Positive control:** the unlimited pool caches all six files (6 blocks, 6144 kB locked), and with the pool unlimited a DataNode cap of 3 blocks / 3U stops the same workload at 3 with the same instruments and no DEBUG line of the pool check.

**Feedback filed:** the case file's section D1 (audit amendments A1–A8, 2026-11-24, before any reading, with inline markers in B2a, B2c, B2d, B2g, B3a, B3c, B3d, B3e, B3g) and D2 "Stage-4 result" (2026-11-24) in `/users/jason92/writeup-hadoop/out/o21/CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous.md`. Nothing in the repository was edited (`_INDEX.md`, `queue.csv`, `environment.md` Node table for `pc75`, HANDOFF are left to the parent session).

**Left on the node:** `/mydata/jingsong-s4/CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous-run1/` (2.4 MB: `harness/`, `logs/`); the source copy, the distribution copy and all NN/DN data were deleted. No daemon, test JVM or Maven process, ports free (`jps` showed only `Jps`). apt packages `cmake`, `zlib1g-dev`, `libssl-dev`, `pkg-config` stay installed on `pc75` (needed for any native build). Node lock released. Undo: `rm -rf /mydata/jingsong-s4/CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous-run1/`.
