# dfs.datanode.pmem.cache.dirs-reserve-maxBytes--autonomous — stage-4 results  <!-- file: results/dfs.datanode.pmem.cache.dirs-reserve-maxBytes--autonomous.md -->

> **Case:** [`dfs.datanode.pmem.cache.dirs-reserve-maxBytes--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/dfs.datanode.pmem.cache.dirs-reserve-maxBytes--autonomous.md)
> (stage-3 queue order 30; at run time the amended case file is `/users/jason92/writeup-hadoop/out/o30/case-amended.md`, outside the repository)
>
> **Status:** **verdict filed 2026-11-25** — unit **Confirmed**, cluster **Confirmed**; effect: caps only on some paths (bypass). The pmem cache followed
> the per-directory cap exactly: unit refusals at M = 32768 / 65536 / 131072 (used = on-disk = M; line 77's own branch returns −1); cluster 4 / 8 / 16
> blocks = X at tmpfs 128 / 256 / 512 MiB with 20 demanded, never above X. Bypass confirmed: two directories on one 256-MiB tmpfs advertised
> 512 MiB and the DataNode hit 240 `No space left on device` copy failures. One run 1, no run 2.
>
> **Outcome class:** **true positive** — stage-3 estimate `positive` against the stage-4 effect `caps` (with a recorded bypass) at both tiers
> ([definition](../../../../stage4-runtime-verification/README.md#outcome-class))
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

**Layout.** Hadoop, Jingsong's share, run by a fresh autonomous stage-4 agent on node `pc82`. At run time this file, the harness and the
raw excerpts are outside the repository: this file `~/writeup-hadoop/out/o30/results.md`, harness `~/writeup-hadoop/out/o30/harness/`,
raw excerpts `~/writeup-hadoop/out/o30/run1/` (cited below as `run1/...`), amended case file `~/writeup-hadoop/out/o30/case-amended.md`.
When filed in the repository they go to `hadoop/stage4-runtime-verification/jingsong/results/` (this file and `results/<stem>/run1/`) and
`.../jingsong/harness/<stem>/`. No stage-4 work existed for this case: no `/mydata/jingsong-s4/dfs.datanode.pmem.cache.dirs-*` folder on
`pc82` at the start (checked 2026-11-25 10:58 MST). Order 31 (another check of the same key) is not touched here.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, repository commit `cd9e1cded` (2026-11-24), repository HEAD at the audit `8bd1dfb31`; sha256 as filed `1417061346818758ec2c00caf1a3f13437ac9844d673d61ce408b3bf6081bf9d` (= `_INDEX.md` §4). After the audit's dated amendments S1–S6 and the B5 note (2026-11-25, before any reading): whole-file sha256 **`f096ea6d81f09a6285ecfc289ddc4aee7c120eb451be6a5834ecd2af5e55cd48`** (frozen version, `case-amended.md` before its section D is filled). |
| **Frozen tables** (sha256 of the text, 2026-11-25 13:00 EST = 11:00 MST, before any reading) | Unit predictions + conclusions, `sed -n '/^\*\*B2f\. /,/^\*\*B2h\. /p'` (B2f, B2g, S3; 61 lines): `146b76d2571af445e2b04064827621ba96f2b13fa0ae89f4ac573eb057a40531`; unit S2 block (`/Amendment S2 /,/^\*\*B2c\. /`): `2b4109412ee96ea816a9cc80690c6996b5a7a27b32fdd0d896ca86b0c33546ac`; cluster predictions + conclusions `sed -n '/^\*\*B3f\. /,/^\*\*B3h\. /p'` (B3f, B3g, S6; 63 lines): `80ae5d5318dab22cb1c67e727f16fe60466eb07fa3ffe0ebf6ed8888cf8ad0aa`. |
| **After the run** | Section D filled 2026-11-25 after run 1; whole-file sha256 `f750c618433f9da7145795e3d1360dcde9c1db6455cd0e807cf940949bed87b9`; the three frozen-table hashes above recomputed after the run are unchanged (`146b76d2…`, `2b410941…`, `80ae5d53…`), so no prediction or conclusions row changed after any reading. |
| **Harness** | `~/writeup-hadoop/out/o30/harness/` (written after the freeze, before run 1); md5s in §2. `apply-amendments.py` (md5 `6b5bc884`) wrote S1–S6 into `case-amended.md`. Not committed (outside the repository). |
| **Tiers and values** | Unit (B2 + S1–S3): `PmemVolumeManager` direct (U1) at M ∈ {32768, 65536, 131072}; default path `setMaxBytes(-1)` → `getUsableSpace()` with one and two directories on one file system (U2); MiniDFSCluster, 1 DN, 4-KiB blocks, `/f1` 16 blocks + `/f2` 4 blocks at M ∈ {32768, 65536, 131072 (control)} (U3). Cluster (B3 + S4–S6): pseudo-distributed NN + DN, 32-MiB blocks, `/f` 640 MiB (20 blocks); tmpfs pmem directory S ∈ {128m (A0), 256m (A), 512m (B)}; run C two directories on one 256m tmpfs (double-count path); run D key unset (default, DRAM loader with locked memory 0). |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: bytes of block copies in the pmem cache directories (storage on the pmem device / mapped file system); `CacheUsed` and on-disk file bytes. |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met | B2b had two `M` values (+ default path in U2), B3b two sizes (+ default run D). **Amended:** S2 adds M = 32768; S5 adds S = 128m. The key's default (empty) is run D; the cap's default source (`-1` → `getUsableSpace()`) is U2 and every cluster run. |
| A. Core question | real resource measured, not only the counter | Met | B2d on-disk sum of cache files; B3d `du`, `df`, file count beside JMX `CacheUsed`. Gap named in S1/S4: no real pmem on the node; local-disk directories (unit) and a tmpfs (cluster) stand in through the pure-Java mapped-file loader, as Hadoop's own pmem tests do. |
| A. Core question | usage driven to the limit and past it | Met | U1 M/4096 + 4 reserves; U3 `/f2` past a full cache (and `/f1` past M = 32768); cluster 20 blocks (640 MiB) against ≤ 16 that fit. |
| A. Core question | negative-claim positive control | n/a | estimate positive; controls: U3 M = 131072, cluster B vs A, run D. |
| B. Logic | hypothesis / test / logic / refuted-if mapped | Met | B1 ↔ B2c–e/B3c–e ↔ B2f/B3f ↔ B2g/B3g ("claim wrong if" rows). |
| B. Logic | each step says what it establishes | Met | U1 (accounting at the check), U2 (runtime-queried cap, double count), U3 (a) NN gate vs (b) DN gate; cluster A/B dose, C bypass, D attribution. |
| B. Logic | prediction stated in numbers | Partly → Met | B3f's 7/15 blocks assume X a few KiB below S; on tmpfs X can equal S (8/16). **Amended** (S6.1): N = floor(X/B) with X from the DataNode's own log line — the claim-wrong conditions are unchanged. |
| B. Logic | every plausible outcome has a row | Partly → Met | Missing: duplicate-command counts in `NumBlocksFailedToCache` (order 23's finding, `FsDatasetCache.java:276-281`); control (b) is a duplicate, not a refusal; ENOSPC can surface as "premature EOF" because `load:97` ignores `transferTo`'s count; cluster run not settled; C with no failures. **Amended** (S3, S6). |
| B. Logic | confirmation needs ceiling-follows-knob + direct disallow evidence | Partly → Met | Unit has `-1` returns and "could not reserve" lines; which check refuses (`chooseVolume :407` vs `:77`) was not separated, and the cluster tier had no disallow observable but "few or no could not reserve". **Amended:** S3.1 (count "no enough persistent memory space" WARNs; reflective call for `:77`), S3.2 and S4/S6.5 (NN TRACE reject lines). |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: doubled cap, static-state reset, independent on-disk count, NN vs DN gate, run D, uncache to 0. |
| C. Specific | a human can follow it from the intro and B | Met | B1 and the A3 mechanism read on their own. |
| C. Specific | an AI can run B2e/B3e without re-deriving the path | Partly → Met | Generic `rsync`/`-am install`/`mvn package -Pdist`/`start-dfs.sh`; loader choice unchecked. **Amended** (S1, S4: `copy-source.sh`, `~/.m2`, base distribution copy, `--daemon`, loader log line). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | No settle rule for `/f1`, no timeout on step 7, `du --apparent-size` counts directories. **Amended** (S3.5, S6.2, S6.6). |
| D. Runnable | harness and environment prerequisites | Met | Test class and scripts are step-1 work; `pc82` has JDK 8, Maven 3.6.3, the base build, passwordless `sudo` for `mount -t tmpfs`; no `libhadoop` (pure-Java loader, as designed). |
| D. Runnable | workload arithmetic | Met | Unit: ≤ 128 KiB of cache files. Cluster: tmpfs ≤ 512 MiB of RAM (125 GiB, ~123 GiB available); 640 MiB input + 640 MiB replica on `/mydata` (658 GB free); 5 runs × (restart + 90 s + uncache) ≈ 15 min. |
| D. Runnable | load-bearing citations spot-checked | Met | `PmemVolumeManager.java:73-84` (`:77` the `if`), `:197-210` reserve, `:231-266` loadVolumes (`:245` getUsableSpace, `:251-252` log line), `:395-417` chooseVolume, `:448-462` path; `PmemMappableBlockLoader.java:47-58, 82-116, 128-131`; `MappableBlockLoaderFactory.java:42-50`; `FsDatasetCache.java:183-186, 272-289, 409-491, 558-563`; `CacheReplicationMonitor.java:744-753`; `DataNode.java:1892-1915`; `DNConf.java:269-270`; `FsDatasetImpl.java:2526-2591` (cacheBlock/cache), `:749-785` getters, `:2641-2651` MBean `FSDatasetState-<uuid>`; `PmemMappedBlock.close` deletes the cache file. All match the pinned source (`rel/release-3.4.2`). |

**Recommendations**

| # | Recommendation | Action | Why |
|---|---|---|---|
| R1 (S1) | Unit: node specifics, pmem emulation, loader check, no assertions | Applied 2026-11-25 | runnable as written on `pc82`; a wrong loader would test another path |
| R2 (S2) | Third cap value M = 32768 at U1 and U3 | Applied 2026-11-25 | ≥ 3 knob values |
| R3 (S3) | Count `chooseVolume` WARNs, NN TRACE rejects, refusal lines by `/f2` id; duplicate-command and control-(b) rows; settle rules | Applied 2026-11-25 | which check refuses; counter not specific |
| R4 (S4) | Cluster: base distribution copy, `--daemon`, loader log line, NN TRACE | Applied 2026-11-25 | runnable on `pc82`; disallow evidence |
| R5 (S5) | Third tmpfs size S = 128m | Applied 2026-11-25 | ≥ 3 sizes |
| R6 (S6) | N = floor(X/B); cache bytes as regular-file sum; ENOSPC forms; settle/stop; extra B3g rows | Applied 2026-11-25 | exact prediction, every plausible outcome has a row |
| R7 | Stage 3: `PmemMappableBlockLoader.load:97` ignores `transferTo`'s return value; a short copy is caught only by the checksum pass — worth a sentence in A3's overshoot list | Not applied (stage-3 recommendation) | — |
| R8 | Stage 3: B2a/B3a generic build commands; name the per-person `copy-source.sh`, `~/.m2` shortcut and `--daemon` | Not applied (stage-3 recommendation) | — |

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-11-25 (node clock MST; daemon logs UTC, +7 h): node lock 10:58:12 MST; amendments frozen 11:00 MST; source copy 11:03; compile 11:03:43–11:04:26; unit run 11:05:02–11:07:03; cluster setup 11:05:04; cluster run 11:07:20–11:17:13; cleanup 11:19; lock released 11:20:12 | not done |
| Node | `pc82` = `node1.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu` (in `environment.md`'s Node table), 40 cores, 125 GiB RAM; lock `/mydata/s4/NODE-LOCK` (owner `jingsong-h30-stage4`); no Java/Hadoop process of the user and ports 9000/9864/9866/9867/9870 free at the start | — |
| OS, kernel, limits | Ubuntu 22.04.2 LTS, `5.15.0-203-generic`; `ulimit -n` 1024, `ulimit -l` 16492912 kB | — |
| JDK | OpenJDK `1.8.0_514` (`/usr/lib/jvm/java-8-openjdk-amd64`) for build, tests and daemons | — |
| Build tool | Maven 3.6.3; node `~/.m2` 3.4.2 artifacts from the base build (no `-am install`) | — |
| Native / PMDK | none: base distribution has no `lib/native`; `hadoop checknative` → `hadoop: false`, `PMDK: false` (`run1/cluster/cluster-run.log`, setup) → pure-Java `PmemMappableBlockLoader` | — |
| Local source copy | `/mydata/jingsong-s4/dfs.datanode.pmem.cache.dirs-reserve-maxBytes-run1/src` by `copy-source.sh` from `systems/hadoop/source/` (repository HEAD `8bd1dfb31`, source clean), tag `rel/release-3.4.2`; only `TestPmemCapacityCap.java` added (`git status`: one untracked file) | — |
| Cluster distribution | copy of `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` in `…-run1/cluster/hadoop`; configuration `…-run1/cluster/conf` (`log4j.properties` + CacheReplicationMonitor TRACE) | — |
| Pmem stand-in | unit: directories `…/target/test/data/dfs/pmem-o30-{0,1}` on `/mydata` (ext4); cluster: tmpfs mounted at `…-run1/cluster/pmem0` (size per run, unmounted after each) | — |
| Case-file / harness version | sha256 `f096ea6d…` (frozen, S1–S6) / md5: `TestPmemCapacityCap.java` `3ac29176`, `unit-run.sh` `802b299b`, `cluster-run.sh` `6e9b222e`, `sampler.py` `d0f8f997`, `apply-amendments.py` `6b5bc884`, `selfcheck.py` (after the run); uncommitted | — |
| Instrument checks | `bash -n` of both scripts and a Python parse of `sampler.py` OK; `unit-run.sh compile` BUILD SUCCESS 11:04:26 MST (41 s); `cluster-run.sh setup` OK 11:05:05 MST; known answers inside the runs: unit `PMCHK,u3,instr` (loader class, native/PMDK flags, DN capacity = M), reflective `reserve(0)` on a full counter (must succeed, `next == maxBytes`); cluster "Added persistent memory … size=X" and JMX `CacheCapacity` = NN "Configured Cache Capacity" before each directive | — |
| Full logs | on `pc82`: `/mydata/jingsong-s4/dfs.datanode.pmem.cache.dirs-reserve-maxBytes-run1/logs/` (`unit/`: `unit-run.log`, `compile.log`, `test.log`, `surefire/`, `pmchk.csv`; `cluster/`: `cluster-run.log`, `samples-*.csv`, `dn-*.log`, `nn-gate-*.log`). Copies of the evidence used here: `~/writeup-hadoop/out/o30/run1/` | — |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | 1, cluster | B3c `head -c 671088640 /dev/urandom > in.bin` | Harness defect, found after the run: `cluster-run.sh`'s `run` wrapper wrote its trace line and `rc=0` (67 B) into the redirected file, so `/f` had a 21st block of 67 B | None needed for this run: the NameNode rejected the 67-B block in every run (0 "added" lines), so it was never cached and no row reads it; the step otherwise ran as written. A reuse of the harness should call `head` without the wrapper | Not restarted, 2026-11-25 (the case file is unchanged; the deviation is in §4.2 part 6) | — |

Otherwise every step ran as written (with S1–S6) on the first attempt; no step was repeated.

## 4. Run 1

**Scope:** both tiers, every row of B2f (with S2/S3) and B3f (with S5/S6). **Command logs:** `run1/unit/unit-run.log`,
`run1/cluster/cluster-run.log`. Raw data: `run1/unit/pmchk.csv` (the `PMCHK` lines of the surefire `-output.txt`),
`run1/unit/loader-lines.txt` (loader and "Added persistent memory" lines), `run1/cluster/samples-<run>.csv` (every 2-s sample),
`run1/cluster/dn-<run>-excerpt.txt` and `run1/cluster/nn-gate-<run>-excerpt.txt` (DataNode and NameNode-gate lines per run).

### 4.1 Readings

**Unit tier** (surefire `Tests run: 7, Failures: 0, Errors: 0, Skipped: 0`, 76 s, `run1/unit/surefire-summary.txt`; every U3 row on the
pure-Java `PmemMappableBlockLoader`, `nativeAvailable=false`, `pmdkAvailable=false`, `dnCacheCapacity = M`, `run1/unit/pmchk.csv` `u3,instr`):

| Row | Prediction (B2f / S2 / S3) | Reading | Evidence |
|---|---|---|---|
| U1 M = 32768 | r₁..r₈ = 4096…32768, r₉..r₁₂ = −1; used 32768; map 8; release → 28672, next → 32768; reflective `reserve(1)` → −1, used 32768 | `r=4096;…;32768;-1;-1;-1;-1`, ok 8 / fail 4, used = maxUsed = 32768, map 8, 4 "no enough persistent memory space" WARNs; release 28672, next 32768; reflective `reserve1=-1`, used 32768 → 32768; known answer `reserve0=32768` | `pmchk.csv` `u1,*,M=32768` |
| U1 M = 65536 | 16 successes then −1 ×4; used 65536; map 16; release 61440 → next 65536; reflective −1 | ok 16 / fail 4, used = maxUsed = 65536, map 16, 4 WARNs; 61440 → 65536; `reserve1=-1`, used unchanged; `reserve0=65536` | `u1,*,M=65536` |
| U1 M = 131072 | 32 successes then −1; used 131072 | ok 32 / fail 4, used = maxUsed = 131072, map 32, 4 WARNs; 126976 → 131072; `reserve1=-1`; `reserve0=131072` | `u1,*,M=131072` |
| U2 one directory | capacity = usable within 1 MiB | capacity 704039297024, usable 704039297024, diff 0 | `u2,one` |
| U2 two directories, same file system | capacity ≈ 2 × usable within 2 MiB | capacity 1408078589952, usable 704039292928, diff from 2× = 4096 B, ratio 2.000000, both on `/mydata (/dev/mapper/emulab-node1--bs)` | `u2,two` |
| U3 M = 32768, `/f1` (16 blocks) | 8 cached, CacheUsed 32768 = capacity, on-disk 32768 | 8 cached (metric 8), CacheUsed 32768 / capacity 32768, on-disk 32768 in 8 files; NN reject lines 608, added 8; 0 refusals | `u3,f1,M=32768` |
| U3 M = 32768 (a) `/f2` directive | still 8; no new files; NN rejects > 0 | 8 cached, 32768, on-disk 32768, `/f2` files 0; NN reject Δ 1200, added Δ 0 | `u3,a,M=32768` |
| U3 M = 32768 (b) direct `cache()` | 4 refusal lines for `/f2` ids, 4 WARNs, counter Δ ≥ 4, CacheUsed 32768, on-disk 32768, no `/f2` file | refusal lines 4 (all 4 `/f2` ids), "no enough" WARNs 4, counter Δ 4, CacheUsed 32768, on-disk 32768, `/f2` files 0 | `u3,b,M=32768`, `u3,b,line` |
| U3 M = 32768 max over the test | CacheUsed and on-disk ≤ M | max CacheUsed 32768, max on-disk 32768 (48 samples) | `u3,max,M=32768` |
| U3 M = 65536, `/f1` | 16 cached, CacheUsed 65536 = capacity, on-disk 65536 | 16 (metric 16), 65536 / 65536, on-disk 65536 in 16 files; NN reject 0, added 16 | `u3,f1,M=65536` |
| U3 M = 65536 (a) | still 16, no new files; NN rejects > 0 | 16, 65536, on-disk 65536, `/f2` files 0; NN reject Δ 400, added Δ 0 | `u3,a,M=65536` |
| U3 M = 65536 (b) | 4 refusals, 4 WARNs, Δ ≥ 4, 65536, no `/f2` file | refusals 4 (all `/f2` ids), WARNs 4, Δ 4, CacheUsed 65536, on-disk 65536, `/f2` files 0 | `u3,b,M=65536` |
| U3 M = 65536 max | ≤ M | max CacheUsed 65536, max on-disk 65536 (45 samples) | `u3,max,M=65536` |
| U3 M = 131072 (control) `/f1` + (a) | all 16 + 4 cached, CacheUsed 81920, on-disk 81920 | `/f1`: 16, 65536; after (a): 20 cached, CacheUsed 81920, on-disk 81920 in 20 files, `/f2` files 4; NN reject 0, added Δ 4 | `u3,f1/a,M=131072` |
| U3 control (b) | 0 refusals, counter +4 (duplicates), CacheUsed 81920 | refusals 0, WARNs 0, counter Δ 4, CacheUsed 81920 | `u3,b,M=131072` |
| Teardown (all U3) | uncache releases to 0 | CacheUsed 0, on-disk 0, files 0 after 0.5–1 s | `teardown` ×3 |

`NumBlocksFailedToCache` after `/f1` read 9 (M = 32768) and 17 (M = 65536 and 131072) with 0 refusal lines: repeat commands for blocks
already cached or caching (`FsDatasetCache.java:276-281`), as S3.3 registered; no row uses this count.

**Cluster tier** (pseudo-distributed NN + DN on `pc82`, 32-MiB blocks; NameNode format 11:07:20 MST, runs 11:07:51–11:17:03 MST =
18:07:51–18:17:03 UTC in the daemon logs; every run: DataNode live with JMX capacity = NN "Configured Cache Capacity" before the directive,
`Starting DataNode with maxLockedMemory = 0`, 46 samples over 90 s, cache drained to 0 with no cache file in 2–8 s after the directive was removed;
`run1/cluster/cluster-run.log`, `samples-<run>.csv`, `dn-<run>-excerpt.txt`, `nn-gate-<run>-excerpt.txt`):

| Run | tmpfs S / df size | Loader; "Added persistent memory" size X | Predicted N = floor(X/B) (S6.1) | Final NumBlocksCached / CacheUsed | Cache-file bytes final / max over samples | max CacheUsed | max df Used | BYTES_CACHED / NEEDED | DN refusals / ENOSPC-form failures | NN reject / added lines (distinct blocks commanded) |
|---|---|---|---|---|---|---|---|---|---|---|
| A0 | 128m / 134217728 | Pmem; 134217728 | 4 | 4 / 134217728 | 134217728 (4 files) / 134217728 | 134217728 | 134217728 (100 %) | 134217728 / 671088707 | 0 / 0 | 531 / 4 (4) |
| A | 256m / 268435456 | Pmem; 268435456 | 8 | 8 / 268435456 | 268435456 (8 files) / 268435456 | 268435456 | 268435456 (100 %) | 268435456 / 671088707 | 0 / 0 | 424 / 8 (8) |
| B | 512m / 536870912 | Pmem; 536870912 | 16 | 16 / 536870912 | 536870912 (16 files) / 536870912 | 536870912 | 536870912 (100 %) | 536870912 / 671088707 | 0 / 0 | 160 / 16 (16) |
| C (two dirs `a`, `b` on one 256m tmpfs) | 256m / 268435456 | Pmem; two lines, 268435456 each; JMX/NN capacity **536870912** | ≤ 8 complete files (S6.4) | 8 / 268435456 (4 in `a`, 4 in `b`) | 268435456 (8 files) / 268435456 | 268435456 | 268435456 (100 %) | 268435456 / 671088707 | 0 refusals / **240** "Failed to cache the block" with `java.io.IOException: No space left on device` from `FileChannelImpl.transferTo0` (0 "premature EOF", 0 checksum) | 163 / 24 (16: first command 16 ids) |
| D (key unset) | — | `MemoryMappableBlockLoader`; capacity 0 | 0 | 0 / 0 | — | 0 | — | **268435456** / 671088707 (stale NN view, below) | 240 "could not reserve more bytes … 0 exceeded" / 0 | 160 / 256 (8, each re-added 32 times) |

The dose: N = 4 / 8 / 16 at S = 128 / 256 / 512 MiB (B/A ratio 2.0); on tmpfs X equalled S exactly in every run, so the cap filled the file system
to the byte with no ENOSPC (`samples-A0/A/B.csv`, `cluster-run.log` "Added persistent memory" lines). In C the per-directory counters
(256 MiB each) never bound: each directory held 128 MiB when the file system was full, and the NameNode commanded 16 blocks (= 2X/B),
of which the 8 that did not fit failed with ENOSPC and were re-sent every 3 s (240 failures in 90 s, `dn-C-excerpt.txt`). NumBlocksFailedToCache
read 4 / 8 / 16 in A0 / A / B with 0 refusals (duplicate commands, S3.3 / order 23).

**Run D's NameNode view.** The DataNode with capacity 0 cached nothing (JMX `CacheCapacity = CacheUsed = NumBlocksCached = 0` in all 46 samples),
yet the NameNode reported BYTES_CACHED 268435456 and commanded blocks `1073741833–1073741840` 32 times each, all refused by the DataNode
(`dn-D-excerpt.txt`, `nn-gate-D-excerpt.txt`). The full DataNode daemon log shows why: at every DataNode restart the NameNode sent a
DNA_UNCACHE for the previous run's blocks (18:09:47, 18:11:37, 18:13:28, 18:15:22 UTC), i.e. its per-DataNode cached list survives the
restart until the next cache report; a pmem DataNode's first cache report (every 3 s) cleared it, but a DataNode whose cache capacity is 0
sends **no** cache report (`BPServiceActor.java:490-494`), so in run D the NameNode kept run C's 8 blocks as "cached" (BYTES_CACHED) and as
pending-uncache (DNA_UNCACHE of run C's 8 ids, 1073741825–1073741832, sent 32 times during D), and the pending-uncache bytes (+8 × 32 MiB) were credited to `pendingCapacity`
(`CacheReplicationMonitor.java:731-744`), letting 8 blocks past the line-745 gate on a DataNode with 0 bytes of cache.

**Workload deviation (harness).** `/f` is 671088707 B, not 671088640: the `run` wrapper's trace line ("+ head -c 671088640 /dev/urandom …",
67 B incl. "  rc=0") went into the redirected `in.bin`, giving a 21st block of 67 B (`1073741845`). The NameNode rejected it in every run
(31–32 TRACE lines "has size 67, but the DataNode only has 0 bytes of cache remaining", 0 "added"), so it was never cached and no reading
counts it; demand stayed above every cap. Recorded in §3.

### 4.2 Conclusion and logic

1. **Validity** — valid. Unit: surefire 7/0/0/0 [observed: `surefire-summary.txt`]; every U3 row on `PmemMappableBlockLoader` with native and
   PMDK unavailable and DN capacity = M [observed: `pmchk.csv` `u3,instr`, `loader-lines.txt`]; static state reset per method (U1 capacities
   = M each time; U2 starts at `-1`) [observed]; the cap was reached and passed in every U1/U3 row (refusals logged) [observed]. Cluster:
   every pmem run used `PmemMappableBlockLoader`, `maxLockedMemory = 0`, a fresh tmpfs of the stated size with recovery off (0 cache files before
   each directive) [observed: `cluster-run.log`]; demand 20 × 32 MiB > X in every run [observed: BYTES_NEEDED]; every run drained to 0 [observed].
2. **Readings** — all unit readings equal B2f/S2/S3 exactly (`selfcheck.txt`, 27 unit checks). Cluster A0/A/B equal floor(X/B) exactly; C as S6.4;
   D's DataNode as B3f. Unusual: (i) D's NameNode BYTES_CACHED 268435456 and DataNode refusals (explained above; NameNode bookkeeping, not cache
   usage); (ii) the 67-B 21st block; (iii) the LogCapturer prefixes some U3 FsDatasetCache lines with `impl.PmemVolumeManager` (shared capture
   appenders; the text and the location `FsDatasetCache.java:run(419)` are unambiguous, and the refusal count comes from the FsDatasetCache capturer only).
3. **Matched row** — Unit: B2g "U1/U3 match B2f (refusal exactly at M, used = M)" → claim holds at the check; "Reflective call returns −1 when
   full" → `:77`'s own refusal works (`reserve1=-1`, used unchanged, known answer `reserve0=M`); S3 row "manager-level −1 with the matching
   WARNs" (4 per M); "U2: one-directory capacity ≈ usable space" (diff 0) and "U2: two-directory capacity ≈ 2 × usable" (ratio 2.000000) →
   double-count path confirmed in-JVM [observed: `pmchk.csv`]. Cluster: B3g row 1 as restated by S6.1 — A0/A/B cache floor(X/B) = 4/8/16
   blocks, cache bytes ≤ X in every sample [observed: `samples-*.csv`]; "C: CacheCapacity ≈ 2X and ENOSPC failures" → double-count bypass
   confirmed (capacity 536870912 on a 268435456-B file system, 240 `No space left on device`) [observed: `cluster-run.log`, `dn-C-excerpt.txt`].
   Disallow evidence: DataNode refusals naming the `/f2` blocks (unit (b)), the `chooseVolume` WARNs and the reflective `:77` −1 (unit), and the
   NameNode gate's TRACE line in every over-cap unit row and cluster run [observed].
4. **Excluded rows** — *a reserve succeeds past M / CacheUsed > M / on-disk > M*: max used and max on-disk equal M at most in every U1/U3 row
   [observed]; *U3 (b) `/f2` cached at M ≤ 65536*: 0 `/f2` files [observed]; *U3 (b) nothing logged*: 4 refusals each [observed]; *U2 two dirs ≈ 1×*:
   ratio 2.0 [observed]; *control does not move to 81920*: it did [observed]; *control (b) refusals > 0*: 0 [observed]; *loader not Pmem*: Pmem
   [observed]. Cluster: *cache bytes or CacheUsed > X* (A0/A/B): max = X [observed]; *A and B cache the same count*: 8 vs 16 [observed];
   *A: No space left*: 0 ENOSPC forms in A0/A/B [observed]; *C: CacheCapacity ≈ X*: 2X [observed]; *C: no failure of any kind (Partly)*: 240
   failures [observed]; *fewer than floor(X/B), not settled*: final = floor(X/B) from the first minute on [observed: samples];
   *D: anything cached*: DataNode cached 0 bytes, 0 blocks, no pmem directory [observed: `samples-D.csv`] — the NameNode's BYTES_CACHED is
   its stale list, not caching (part 5).
5. **Observed vs. inferred** — (a) D's BYTES_CACHED and DataNode refusals come from a stale NameNode cached/pending-uncache list, not from any
   cache path [inferred from: DNA_UNCACHE of the previous run's ids at each DataNode restart in the full DataNode log; `BPServiceActor.java:490-494`
   skips cache reports at capacity 0; DataNode JMX 0/0/0 throughout D; the 8 commanded ids are exactly the next 8 after run C's cached ids and the
   reject TRACE reads "0 pending bytes, 0 already cached" after them]. (b) In C the physical bound, not the accounting, stopped the copies
   [inferred from: per-directory caps 268435456 each vs 128 MiB held per directory; ENOSPC stack in `transferTo0`; df Used = size]. (c) U1's
   manager-level −1 is the `chooseVolume` check (`:407`) applying `:77`'s inequality [inferred from: one WARN per refusal, text of `:414-416`].
6. **Deviations and gaps** — (i) pmem emulated (local-disk directories, tmpfs) through the pure-Java mapped-file loader (S1/S4); the native PMDK
   loader is not exercised. (ii) `/f` carried a 67-B 21st block (harness artefact), rejected by the NameNode in every run; no row affected.
   (iii) B3f's BYTES_NEEDED 671088640 reads 671088707 for the same reason. (iv) D's NameNode BYTES_CACHED was not predicted (B3f says nothing
   about the NameNode in D); the DataNode observables B3f names hold. (v) X equalled S exactly on tmpfs, so each pmem run filled its file system
   to 100 % without ENOSPC — the cap and the file-system size coincide; the claim's "refused before any byte is written" is shown by the unit
   tier (refusals with no file) and by the NameNode gate here. (vi) per-directory `usedBytes` not exported; C's split (4 + 4) read from the files.
7. **Core question** — Usage follows the constraint. Unit: reservations, CacheUsed and on-disk bytes stop exactly at M = 32768 / 65536 / 131072
   and further requests are refused before any file is written, both at the volume choice and at line 77 itself; the default cap is the
   runtime-queried usable space. Cluster: the pmem cache held 4 / 8 / 16 blocks = X at S = 128 / 256 / 512 MiB with 20 blocks demanded, never more
   than X; the key unset gives zero cache. On the traced bypass — two directories on one file system — capacity is advertised as 2X, the
   accounting cap never binds, and only the file system's ENOSPC stops the copies (with repeated failing copies). So the key's cap bounds the
   pmem cache per directory, with a confirmed overstatement when directories share a file system.

**Conclusion (one line):** Unit: B2g row 1 + reflective row + U2 one-dir and two-dir (≈ 2×) rows — confirmed. Cluster: B3g row 1 (as S6.1:
floor(X/B) = 4/8/16) + "C: CacheCapacity ≈ 2X and ENOSPC failures" (double-count bypass) — confirmed.

## 5. Self-check of run 1 — AI

`harness/selfcheck.py run1` recomputes every reading used above from the raw files (`pmchk.csv`, `cluster-run.log`, `samples-*.csv`), not from
this file, and tests it against the frozen B2f/B3f (+ S2/S3/S6): 47 checks, **ALL OK** (`run1/selfcheck.txt`, 2026-11-25). The D anomaly, the
67-B block and the C ENOSPC stack were re-read in the DataNode daemon log and the NN gate log on the node (excerpts `dn-*-excerpt.txt`,
`nn-gate-*-excerpt.txt`).

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `u3,instr` ×3 loader `PmemMappableBlockLoader`, `nativeAvailable=false`; `Tests run: 7, Failures: 0`; cluster "Initializing cache loader: …PmemMappableBlockLoader" ×4, "MemoryMappableBlockLoader" in D; `cache files before directive: 0 0` ×5; drained ×5 |
| 2. Readings | yes | selfcheck 47/47; D's BYTES_CACHED line `5 p1 … 671088707 268435456` in `cluster-run.log` |
| 3. Matched row | yes | `u1,reserves` lists, `u1,reflect reserve1=-1`, `u2,two ratio=2.000000`; `samples-A0/A/B.csv` last rows 4/8/16; run C two "Added persistent memory" lines and `No space left on device: 240` |
| 4. Excluded rows | yes | max columns ≤ X in all 46 samples per run; `couldNotReserveF2=4` and `f2FilesOnDisk=0`; control `couldNotReserveNew=0`; A0/A/B ENOSPC-form counts 0 |
| 5. Observed vs. inferred | yes | (a) DNA_UNCACHE lines at 18:09:47/18:11:37/18:13:28/18:15:22 UTC and 32 in D (run C's 8 ids); first D reject "0 pending bytes, 0 already cached"; `BPServiceActor.java:490-494` re-read; (b) file list 4 in `a`, 4 in `b`; stack `FileChannelImpl.transferTo0`; (c) `noSpaceWarns=4` per M |
| 6. Deviations and gaps | yes | `in.bin` first line "+ head -c 671088640 /dev/urandom  [2026-11-25 11:07:33 MST]" and tail "rc=0"; block 1073741845 "has size 67" rejected 31–32× per run, 0 added |
| 7. Core question | yes | the C = 0 (key unset) run, the M = 131072 control, the B-vs-A dose and the independent on-disk/`df` byte counts rule out the B2h/B3h alternatives |

### 5.2 Run 2?

**No** — decided 2026-11-25. Both tiers confirm the stage-3 claim with exact numbers, including the bypass the claim itself predicted; the
inferred statements are settled from run 1's own raw logs; the D anomaly concerns NameNode bookkeeping outside the claim and is reproducible from
the logs kept on the node.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** **true positive** — estimate `positive`, effect `caps` with a recorded bypass (two directories
on one file system) at the unit and the cluster tier (`caps` includes caps with a recorded bypass, README "Outcome class").

**Claim tested:** (B1) for each directory in `dfs.datanode.pmem.cache.dirs`, the bytes of cached block replicas the DataNode holds in that
directory (`CacheUsed` and cache-file bytes) never exceed that directory's `maxBytes`, the usable space measured at DataNode start; requests
beyond it are refused before any byte is written. Corollary: with two directories on one file system the advertised capacity is about twice the
real space, and only ENOSPC limits the copies. "Confirmed" below always means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (U1: refusal exactly at M = 32768/65536/131072, used = M; U3: 8/16 blocks, CacheUsed = on-disk = M, 4 refusals and no file for `/f2`), reflective row (`:77` returns −1, state unchanged), U2 rows (capacity = usable space, diff 0; two directories 2.000000 ×); control 81920 | caps only on some paths (bypass): two directories on one file system double the cap | run 1 + self-check | 2026-11-25 |
| Cluster | **Confirmed** — B3g row 1 as S6.1 (4/8/16 blocks = X at S = 128/256/512 MiB; cache bytes ≤ X in all samples; 0 ENOSPC) + "C: CacheCapacity ≈ 2X and ENOSPC failures" (536870912 on a 268435456-B tmpfs, 240 `No space left on device`); D: zero capacity, nothing cached | caps only on some paths (bypass) | run 1 + self-check | 2026-11-25 |

**Positive control** (estimate positive; controls as designed): unit M = 131072 cached `/f1` + `/f2` whole (81920 B); cluster B (512m) cached
twice A's blocks; run D (key unset) cached nothing on the DataNode.

**Findings beyond the verdict** (upstream / doc candidates; check JIRA first):
- **Double-count bypass** (confirmed): pmem directories on one file system each get `maxBytes = getUsableSpace()` (`PmemVolumeManager.java:243-248`),
  capacity is their sum, the NameNode schedules to it, and the DataNode churns ENOSPC copy failures (240 in 90 s for 8 surplus blocks).
- **Stale NameNode cache view for a DataNode with cache capacity 0**: no cache reports (`BPServiceActor.java:490-494`), so after a restart that
  turns caching off the NameNode keeps the old cached list (BYTES_CACHED 256 MiB on a DataNode caching nothing), re-sends DNA_UNCACHE every
  heartbeat interval, and its pending-uncache credit lets blocks past the `CacheReplicationMonitor.java:745` check onto a 0-byte cache (DataNode refuses them).
- `PmemMappableBlockLoader.load:97` ignores `transferTo`'s return value (here ENOSPC surfaced as an exception, so no short copy was seen).
- Memory holder worth an OOM look (not measured): `MappableBlockLoader.verifyChecksum:147-148` allocates an 8-MiB heap buffer (+ checksums) per
  caching task, up to `dfs.datanode.fsdatasetcache.max.threads.per.volume` (4) at once per data volume.

**Feedback filed:** the case file's audit amendments S1–S6 and the B5 note (2026-11-25, before any reading, at the end of B2a, B2b, B2g, B3a, B3b, B3g)
and section D "Stage-4 result" (2026-11-25) in `/users/jason92/writeup-hadoop/out/o30/case-amended.md`. Recommendations for stage 3 (not applied):
R7, R8 (§1), and R9 — on tmpfs the usable space can equal the size exactly; state cluster block counts as floor(X/B). Nothing in the repository
was edited (`_INDEX.md`, `queue.csv`, HANDOFF, FLOWCHART are left to the parent session).

**Left on the node:** `pc82:/mydata/jingsong-s4/dfs.datanode.pmem.cache.dirs-reserve-maxBytes-run1/` (9.5 MB: `harness/`, `logs/unit` (surefire
reports, `pmchk.csv`), `logs/cluster` (`cluster-run.log`, `samples-*.csv`, `dn-*.log`, `nn-gate-*.log`, excerpts), `cluster/logs` (NameNode and
DataNode daemon logs, UTC), `cluster/conf`). Deleted: the source copy, the distribution copy, NN/DN data, `in.bin`, MiniDFSCluster data. No daemon,
test JVM, Maven, sampler or tail process; no tmpfs mounted (each unmounted after its run; `pmem0` removed); no driver PID file; ports free. Node lock
taken 10:58:12 and released 11:20:12 MST. Undo: `rm -rf /mydata/jingsong-s4/dfs.datanode.pmem.cache.dirs-reserve-maxBytes-run1/`.
