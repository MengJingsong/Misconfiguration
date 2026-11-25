# dfs.datanode.pmem.cache.dirs-chooseVolume-availableBytes--autonomous — stage-4 results  <!-- file: results/dfs.datanode.pmem.cache.dirs-chooseVolume-availableBytes--autonomous.md -->

> **Case:** [`dfs.datanode.pmem.cache.dirs-chooseVolume-availableBytes--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/dfs.datanode.pmem.cache.dirs-chooseVolume-availableBytes--autonomous.md)
> (stage-3 queue order 31; at run time the amended case file is `/users/jason92/writeup-hadoop/out/o31/case-amended.md`, outside the repository)
>
> **Status:** **verdict filed 2026-11-25** — unit **Confirmed** (caps), cluster **Confirmed** (caps). Claim tested (B1): with
> `dfs.datanode.pmem.cache.dirs` set, the cache-file bytes in each pmem directory never exceed that directory's usable space measured at
> DataNode start, and a block that fits no single volume is refused at `PmemVolumeManager.java:407` and not written. Cached bytes followed
> the volume size exactly at both tiers (unit 32/10/64/20 reserves for M × B pairs, U2 14 blocks at 30720 B/volume against 16 at 32768;
> cluster 8/16/10 blocks = 128/256/160 MiB on tmpfs volumes of 136m/264m/264m-minus-100-MiB-filler), per-volume file bytes never above the
> logged `maxBytes`, and the line-407 refusal fired where only fragmentation blocked the block (U2: 35 refusals "max available space is
> 2048"; cluster K3 44m + 204m: 14 blocks = 2 + 12, 76 refusals "max available space is 12582912"). One run 1, no run 2. Caveats:
> K4 (filler written after start) showed the stale snapshot (`CacheCapacity` unchanged at 264 MiB, only 10 blocks fit) but the failures were
> "checksum verification failed: premature EOF", not ENOSPC, so the frozen K4 caveat row reads "not confirmed"; the U3 replay of the
> cancel-path order leaves a 4096-byte cache file with used bytes 0 (leak, as A3 traced).
>
> **Outcome class:** **true positive** — stage-3 estimate `positive` against the stage-4 effect `caps` at both tiers
> ([definition](../../../../stage4-runtime-verification/README.md#outcome-class))

>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

**Layout.** Hadoop, Jingsong's share, run by a fresh autonomous stage-4 agent on node `pc91`. At run time this file, the harness and the
raw excerpts are outside the repository: this file `~/writeup-hadoop/out/o31/results.md`, harness `~/writeup-hadoop/out/o31/harness/`,
raw excerpts `~/writeup-hadoop/out/o31/run1/` (cited below as `run1/...`), amended case file `~/writeup-hadoop/out/o31/case-amended.md`.
When filed in the repository they go to `hadoop/stage4-runtime-verification/jingsong/results/` (this file and `results/<stem>/run1/`) and
`.../jingsong/harness/<stem>/`. No stage-4 work existed for this case before (no run folder on `pc91`; checked 11:13 MST). Order 30 (another
check of the same key) ran in parallel on `pc82` and was not touched.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, repository commit `cd9e1cded` (2026-11-24), repository HEAD at the audit `8bd1dfb31`; sha256 as filed `859de27561c1cba2a03641961199dfe0e87a6094782121f5bcc2ce4b355150dd` (= `_INDEX.md` §4). After the audit's dated amendments A1–A7 (2026-11-25, before any reading): whole-file sha256 **`e15f7c6778662e6d202829768302a5054d1c5d5a16b4bdd4bf7ca837bc7b8fcb`** (frozen version). |
| **Frozen prediction / conclusion blocks** | sha256 of each block (header line to the next block's header, `harness/freeze-hashes.sh`, `run1/freeze-hashes.txt`), recorded 2026-11-25 13:17 EST before any reading: B2f `aa2e8fd5c6792070086572b2f07140565a54968dce6a25e9e2376310b26aa708`, B2g (+A4) `71d84451eca3f4fc41692874d4e237cad9f8b2ded11decd77f94af53464f2b6d`, B3f `39756124b9f98ed2bbcc552ebec27e49dc79cbf01ad81c8cbd22453c163593b4`, B3g (+A7) `48d0df9696df5627a60b33f33a60bb379d1a5bfa872ec361e3c0dc5f15f78aef`. |
| **After the run** | Section D filled 2026-11-25 after run 1: whole-file sha256 `8661c3b8b697d4069b3e42ce3d65b41ca41d9027ce30c66ebece03381687ba6f`; sections A–C and the amendments unchanged since the freeze (B2f/B2g/B3f/B3g block hashes re-checked equal after the run, `run1/freeze-hashes-after.txt`). |
| **Harness** | `~/writeup-hadoop/out/o31/harness/` (written after the freeze, before run 1; md5 prefixes): `TestPmemCapO31.java` `c38c3f6b`, `unit-run.sh` `7cb160c7`, `cluster-run.sh` `5cfff458` (after the setup fix of §3), `selfcheck.py` `9aa896b4`, `freeze-hashes.sh` `39d2c0ce`. Not committed (outside the repository). Instrument checks: `bash -n` of both scripts; the test class compiled in the case copy (BUILD SUCCESS, `run1/unit/mvn-summary.txt`); known answers inside the runs: unit `U2INSTR` lines (loader `PmemMappableBlockLoader`, DN cache capacity = 2 × `setMaxBytes`), U1's hand-checked arithmetic; cluster DataNode-ready check (A5: logged `maxBytes` sum = DN JMX `CacheCapacity` = NN "Configured Cache Capacity" before every directive, `run1/cluster/cluster-run.log` "DN-ready" lines). |
| **Tiers and values** | Unit (B2): `PmemVolumeManager` direct with `setMaxBytes` M ∈ {65536, 131072} × B ∈ {4096, 12288}, two volumes; U1-real (`setMaxBytes(-1)`, the production `getUsableSpace` path); MiniDFSCluster U2 30720 B/volume × 2 (fragmented) and U2-control 32768 B/volume × 2, 4096-byte blocks, 24-block file; U3 cancel-order replay. Cluster (B3): pseudo-distributed NN + DN, 16-MiB blocks, 384-MiB file; tmpfs pmem volumes K1 136m, K2 264m, K3 44m + 204m, K4 264m with 100 MiB filler after DN start, K5 264m with 100 MiB filler before DN start. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: bytes of cache files in each pmem directory (disk / pmem-as-file-system), per volume `maxBytes`. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach | Met | The key's default is empty (no pmem cache: nothing to measure); the derived cap is varied through the volume size: unit M 65536/131072 and 30720/32768, cluster 136m/264m/44m+204m and 164 MiB free (K5). Five cluster arms, the default named in A1. |
| A. Core question | real resource measured, not only the counter | Met | B2d sums `File.length()` of the cache files per volume; B3d `du -sb` and `df` of each tmpfs next to JMX `CacheUsed`. U1 is counter-only by design (named; U2/cluster carry the real bytes). |
| A. Core question | usage driven to the limit and past it | Met | U1 loops to refusal; U2 needs 98304 B vs 61440/65536; cluster 384 MiB vs ≤ 264 MiB. |
| A. Core question | negative-claim positive control | n/a | estimate positive; K2 vs K1 and U2-control are the positive controls the file names. |
| B. Logic | each step says what it establishes | Met | B2b/B3b "Why" columns; B2h/B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f/B3f exact counts and bytes; "≈" for tmpfs `maxBytes` defined in A6; K4 "about 10" defined in A7. |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met | Missing: U1 counts off without overshoot; U2-control with refusals or < 16; K3 < 14; K1/K2/K5 off without overshoot; K4 other readings; no rule combining rows into a tier verdict → **amended** (A4, A7). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met (after A3) | Disallow evidence = the line-407 WARN text "There is no enough persistent memory space … max available space is X" (`PmemVolumeManager.java:414-416` logged at `:207`), counted in U2/K3. `NumBlocksFailedToCache` also counts duplicate cache commands (`FsDatasetCache.java:276-282`, lesson of order 23), so B2f's "rising" failures are not disallow evidence → A3/A6 name the WARN line as the evidence. |
| B. Logic | alternative explanations and their controls | Met | NN total-capacity filter (U2-control, K3 vs K1/K2), stale snapshot (K4 vs K5), recovered files (fresh dirs/mounts, recovery off), pool limit (none), static state (reset in `@Before/@After`). |
| C. Specific | a human can follow it from the intro and B1/B2f/B3f | Met | B1 and the two tables. |
| C. Specific | an AI can run B2e/B3e without re-deriving the code path | Partly → Met | U2 "poll for 20 s after BlocksCached stops rising" and B3c "flat for 60 s" are open-ended and ignore the NN resend window; node paths and the existing build are not used → **amended** (A1, A3, A5, A6). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | as above; DataNode-ready check before each directive added (A5); log counts per DataNode start (A6). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met (after A2/A5) | No persistent memory on the nodes: emulated as Hadoop's own pmem tests do (plain directories in the unit tier, tmpfs in the cluster tier), pure-Java loader since neither the copy nor the base distribution has `libhadoop`/PMDK (A2). `sudo` works on `pc91` (checked). Test class and scripts are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit | Met | ≤ 264 MiB tmpfs per arm (≤ 248 MiB in K3) against 118 GiB free RAM; 384 MiB input + 384 MiB HDFS blocks on `/mydata` (703 GB free). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `PmemVolumeManager.java:407` (the `if`), `:395-417` (round robin, message text incl. the missing space before "is required"), `:73-84` (CAS re-check `:77`), `:197-210` (reserve, WARN at `:207`), `:221-224` (release removes the key), `:243-252` (`getUsableSpace` / `maxBytesPerPmem`, "Added persistent memory - {} with size={}"), `:238-241`/`:268-274` (cleanup of `hdfs_pmem_cache` only), `:467-473` (`getCachePath` null); `FsDatasetCache.java:415-423` ("could not reserve"), `:448-450` ("Failed to cache the block [key="), `:478-484` (release before close), `:276-282` (duplicate counts as failure); `PmemMappableBlockLoader.java:95-114` (transferTo, delete on failure); `PmemMappedBlock.java:63-74` (WARN "Failed to delete the mapped File: {}!"); `FsDatasetUtil.java:226-235` (null path throws); `MappableBlockLoaderFactory.java:42-50`; `CacheReplicationMonitor.java:515-541, 723-755` (NN filter on total `getCacheRemaining`); `DFSConfigKeys.java:482-487`. All as cited. |

**Recommendations**

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 (A1) | Unit tier on `pc91`: `copy-source.sh`, `~/.m2` instead of `-am install`, exact `mvn` line | Applied 2026-11-25 (case-amended.md, uncommitted) | runnable as written on the node |
| R2 (A2) | State the persistent-memory emulation and the pure-Java loader | Applied 2026-11-25 | no pmem hardware; the run must say what stands in for it |
| R3 (A3) | U2 settle rule (20 s unchanged, ≥ 35 s, max 90 s); refusal WARN lines as the disallow evidence; `NumBlocksFailedToCache` read as ≥ refusals | Applied 2026-11-25 | open-ended stop; counter also counts duplicate commands |
| R4 (A4) | B2g rows for off-count U1, U2-control with refusals or < 16, and the unit tier rule; U3 outside the verdict | Applied 2026-11-25 | every plausible outcome needs a row before any reading |
| R5 (A5) | Cluster tier on `pc91`: base-distribution copy, env vars, tmpfs under the run folder, DataNode-ready check | Applied 2026-11-25 | node specifics; capacity must be in place before the directive |
| R6 (A6) | Cluster settle rule (60 s flat, ≥ 90 s, max 300 s), per-start log counts, "≈" = 1 MiB | Applied 2026-11-25 | unambiguous plateau; log appended across restarts |
| R7 (A7) | B3g rows for K3 < 14, off-count K1/K2/K5, K4 = 9/10 and other K4 readings; cluster tier rule; K4 outside the verdict | Applied 2026-11-25 | as R4 |
| R8 | Stage 3: name the per-person `copy-source.sh` and the base distribution instead of generic `rsync`/`mvn package -Pdist`; do not predict on `NumBlocksFailedToCache` (duplicate commands count) | Not applied (stage-3 recommendation) | — |

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-11-25. Node clock MST (session clock EST = MST + 2 h; daemon and surefire log lines are UTC = MST + 7 h): lock 11:13:52, freeze 11:17 (13:17 EST), unit 11:19:29–11:21:17, cluster attempt 0 11:21:30–11:21:35 (setup failed, §3), cluster run 11:21:45–11:32:12, cleanup 11:33:47 | not done |
| Node | `pc91` = `node0.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu` (in `environment.md`'s Node table), 32 cores, 125 GiB (118 GiB free at start); node lock `/mydata/s4/NODE-LOCK` held from 11:13:52 MST; no Java process and ports 9000/9870/9864/9866/9867/9868 free before the run | — |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-203-generic` | — |
| JDK | OpenJDK `1.8.0_514` (`/usr/lib/jvm/java-8-openjdk-amd64`) for the unit tests and the daemons | — |
| Build tool | Maven 3.6.3; node `~/.m2` 3.4.2 artifacts from the 2026-11-24 base build; no native code (`hadoop checknative` → `hadoop: false`) | — |
| Local source copy | `/mydata/jingsong-s4/dfs.datanode.pmem.cache.dirs-chooseVolume-availableBytes-run1/src` by `copy-source.sh` from `systems/hadoop/source/` (repository HEAD `8bd1dfb31`, source clean), tag `rel/release-3.4.2`; only `TestPmemCapO31.java` added. Deleted after the run | — |
| Cluster distribution | copy of `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` (`Hadoop 3.4.2`); config as last written in `run1/cluster/hdfs-site.xml` (K5) | — |
| Case-file / harness version | sha256 `e15f7c67…` (frozen, A1–A7) / md5s in §1, uncommitted | — |
| Storage | Unit: pmem directories `target/test/data/dfs/o31/<method>/pmem{0,1}` on `/mydata` ext4 (U1 uses `setMaxBytes`; U1-real reads the real free space of `/mydata`). Cluster: tmpfs mounts `…/cluster/pmem0`, `pmem1` (A2: persistent memory emulated, pure-Java loader `PmemMappableBlockLoader` in every DataNode start); NN/DN data under `…/cluster/{nn,dn,tmp}`; nothing on `/proj` | — |
| Full logs | On `pc91`: `/mydata/jingsong-s4/dfs.datanode.pmem.cache.dirs-chooseVolume-availableBytes-run1/logs/` (2.0 MB: `unit/` surefire reports and `mvn-test.log`; `cluster/` `cluster-run.log`, `samples-K*.csv`, `files-K*.txt`, `dnlog-K*.log`, `daemon-logs/` NN + DN logs). Excerpts cited here: `~/writeup-hadoop/out/o31/run1/` | — |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | run 1, cluster | B3e step 1 (setup, harness) | Harness bug, not a runbook defect: `cluster-run.sh setup` copied the distribution into `$C/hadoop` before creating `$C`, so the copy, the format and the NameNode start failed; the script stopped at "NameNode did not start" and tore down. No DataNode started, no directive, no reading (`run1/cluster/cluster-run-attempt0-setup-failed.log`). | `mkdir -p $C` moved before the copy, copy failures made fatal; the cluster tier restarted from its beginning 10 s later | 2026-11-25 11:21 MST | none (harness only; case file unchanged) |

No step of the case's runbook needed a change beyond A1–A7.

## 4. Run 1

**Scope:** both tiers, every row of B2f and B3f. **Command logs:** `run1/unit/unit-run.log` (+ `run1/unit/mvn-summary.txt`),
`run1/cluster/cluster-run.log`. Raw data: `run1/unit/o31-lines.txt` (every `O31,` line of the surefire `-output.txt`, incl. 140 U2 polls),
`run1/unit/unit-log-excerpt.txt` (loader, "Added persistent memory", refusal and WARN lines); `run1/cluster/samples-K*.csv` (5-s samples),
`run1/cluster/files-K*.txt` (every file on the tmpfs volumes at the end of each arm), `run1/cluster/dn-excerpt-K*.txt` (DataNode log lines
of that arm's start). Self-check output: `run1/selfcheck.txt`.

### 4.1 Readings

**Unit tier** (surefire `Tests run: 5, Failures: 0, Errors: 0`; loader `PmemMappableBlockLoader` in both MiniDFSCluster starts):

| Test | Reading | B2f | Evidence |
|---|---|---|---|
| U1 M=65536 B=4096 | 32 reserves, `getCacheUsed` 131072, keys 16/16, used/max per volume 65536/65536 both; refusal "max available space is 0, but 4096is required" | 32, 131072, 16/16, 0 | `o31-lines.txt` `O31,U1` |
| U1 M=65536 B=12288 | 10, 122880, 5/5, used 61440 of 65536 each; "… is 4096, but 12288is required" | 10, 122880, 5/5, 4096 | same |
| U1 M=131072 B=4096 | 64, 262144, 32/32; "… is 0, but 4096is required" | 64, 262144, 32/32, 0 | same |
| U1 M=131072 B=12288 | 20, 245760, 10/10, used 122880 of 131072 each; "… is 8192, but 12288is required" | 20, 245760, 10/10, 8192 | same |
| U1-real | `getCacheCapacity` 1508262834176 = Σ `getUsableSpace` 1508262830080 + 4096 (each of the two directories on `/mydata` got the whole file system's free space, 754131419136 and 754131415040); used 0 | Σ usable ± 1 MiB | `O31,U1REAL` |
| U2 fragmented (30720 B/vol) | settled at 35.0 s; 14 blocks cached (`BlocksCached` metric 14), `getCacheUsed` 57344 (max over 70 polls 57344), file bytes 28672/28672 (7/7 files), used/max 28672/30720 each; **35 refusal lines, all "max available space is 2048, but 4096is required"**, 35 "could not reserve"; refusals rose about 1 per second (4 at 4.0 s … 32 at 32.0 s); `NumBlocksFailedToCache` 49 (35 refusals + 14 more, duplicate cache commands per A3); BYTES_CACHED 57344 of 98304; NN cache capacity 61440, used 57344 | 14, 57344, 28672/28672, ≥ 1 refusal at 2048 | `O31,U2,u2frag`, `O31,U2POLL,u2frag`, `O31,U2REFUSAL` |
| U2-control (32768 B/vol) | settled at 35.0 s; 16 cached, 65536, file bytes 32768/32768 (8/8), **0 refusal lines**, 0 "could not reserve"; failures 16 (duplicate commands); BYTES_CACHED 65536 of 98304; NN capacity 65536, used 65536 | 16, 65536, 32768/32768, 0 refusals | `O31,U2,u2ctrl` |
| U3 cancel order | after `release` then `close`: `getCacheUsed` 0, file `…/u3/pmem0/hdfs_pmem_cache/BP-o31/subdir0/subdir0/1` exists, 4096 bytes; WARN "Failed to delete the mapped File: null!" captured. Uncache order (k2): file deleted, used 0; 4096 bytes left on the volume (the k file) | file stays, used 0, WARN; k2 no file | `O31,U3CANCEL`, `O31,U3UNCACHE`, `unit-log-excerpt.txt` |

**Cluster tier** (16-MiB blocks, `/o31.bin` 24 blocks = 402653184 B; every arm settled under A6 at t = 90–91 s; loader `PmemMappableBlockLoader` at every DataNode start; DataNode-ready check passed before every directive):

| Arm | tmpfs (filler) | `maxBytes` logged | NumBlocksCached (pred.) | CacheUsed = cache-file bytes (pred.) | per volume (files) | max `du` / min `df` avail | line-407 refusals (pred.) | other failures | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| K1 | 136m | 142606336 | **8** (8) | 134217728 (134217728) | pmem0 8 | 134218108 / 8388608 | 0 (0) | none | `samples-K1.csv`, `files-K1.txt`, `dn-excerpt-K1.txt` |
| K2 | 264m | 276824064 | **16** (16) | 268435456 (268435456) | pmem0 16 | 268435996 / 8388608 | 0 (0) | none | `…-K2…` |
| K3 | 44m + 204m | 46137344 + 213909504 | **14** (14) | 234881024 (234881024) | pmem0 2 = 33554432, pmem1 12 = 201326592 | 33554692 and 201327052 / 12582912 | **76** (≥ 1, rising): 44 by settle at 91 s, 76 at 151 s; all "max available space is 12582912, but 16777216is required"; 76 "could not reserve" | none | `…-K3…` |
| K4 | 264m, 100 MiB filler after DN start | 276824064 (unchanged; JMX `CacheCapacity` 276824064 throughout) | **10** (about 10) | 167772160 (≈ 167772160) | pmem0 10 (+ filler 104857600) | 170566072 / **0** | 0 (0) | 270 "Failed to cache the block", each `IOException: checksum verification failed: premature EOF`; 0 "No space left on device"; no partial file left | `…-K4…` |
| K5 | 264m, 100 MiB filler before DN start | 171966464 | **10** (10) | 167772160 (167772160) | pmem0 10 (+ filler) | 167772580 / 4194304 | 0 (0) | none | `…-K5…` |

NN `dfsadmin -report` "Configured Cache Capacity" = logged `maxBytes` sum and "Cache Used" = CacheUsed at the end of every arm; directive
BYTES_NEEDED 402653184, BYTES_CACHED = CacheUsed (`cluster-run.log`). `NumBlocksFailedToCache` from JMX: 0/0/73/252/0, below the log counts
in K3 and K4 (part 6).

| Disallow-branch line (cluster K3, example) | `WARN …PmemVolumeManager: There is no enough persistent memory space for caching. The current max available space is 12582912, but 16777216is required.` followed by `WARN …FsDatasetCache: Failed to cache 1073741839_BP-…: could not reserve more …` | `run1/cluster/dn-excerpt-K3.txt` |
|---|---|---|

### 4.2 Conclusion and logic

1. **Validity** — valid. Unit: surefire 5/0/0 [observed: `mvn-summary.txt`]; the pure-Java loader in both MiniDFSCluster starts and DN cache capacity = 2 × `setMaxBytes` (61440, 65536) before the directive [observed: `O31,U2INSTR`]; `reset()`/`setMaxBytes(-1)` around every method and fresh directories per method [observed: test source `harness/TestPmemCapO31.java`]; both U2 runs settled under A3 (`settled=true`, 35.0 s) [observed]. Cluster: each DataNode start logged the expected `maxBytes` and the same value reached JMX and the NameNode before the directive [observed: "DN-ready … ok=1" lines in `cluster-run.log`]; recovery off and a fresh tmpfs per arm (`umount` + `mount` logged); pool without limit; replication 1, one DataNode; every arm settled at 90–91 s. The limit was passed in every arm: 402653184 B needed against at most 276824064 B of capacity [observed: BYTES_NEEDED].
2. **Readings** — every unit and cluster count and byte figure equals B2f/B3f exactly. Unusual: (a) K4's failures are checksum "premature EOF", not ENOSPC (part 6); (b) JMX `NumBlocksFailedToCache` is lower than the log's failure lines in K3 (73 vs 76) and K4 (252 vs 270), although every logged failure increments it (part 6); (c) U1-real: the two directories share one file system, and each was given its whole free space (part 6).
3. **Matched row** — Unit: B2g row 1 ("Reserves and cached bytes match B2f, refusal at the predicted point") for all four U1 pairs and U1-real [observed: `O31,U1`, `O31,U1REAL`], and the A4 tier rule: U2 caches 14 with 35 refusals at "max available space is 2048", U2-control caches 16 with 0 refusals [observed: `O31,U2`] → **Confirmed (caps)**. U3 separately: row "U3 file remains while used = 0" → cancel-order leak confirmed (replay) [observed: `O31,U3CANCEL`]. Cluster: B3g row 1 ("K1 = 8, K2 = 16, K5 = 10 blocks, `du` ≤ log `maxBytes` per volume") [observed: `samples-K1/K2/K5.csv`, `files-K*.txt`] and the row "K3 = 14 with refusal lines" (2 + 12 files, 76 refusals at 12582912) [observed: `files-K3.txt`, `dn-excerpt-K3.txt`] → A7 tier rule **Confirmed (caps)**. The confirmation condition holds: the ceiling follows the volume size (8 → 16 → 10 blocks for 136 / 264 / 164 MiB free at start; 14 vs 16 at unit level) and the disallow branch fired with the predicted operand value.
4. **Excluded rows** — *A volume's file bytes or `usedBytes` > its `maxBytes`* (B2g row 2, B3g row 2): per-volume file bytes and used bytes ≤ `maxBytes` in every U1/U2 row and every arm; max `du` over all samples never above the logged `maxBytes` (K1 134218108 ≤ 142606336; K3 pmem0 33554692 ≤ 46137344, pmem1 201327052 ≤ 213909504) [observed]. *U2 caches 15 or 16 at 30720/vol* / *K3 ≥ 15*: 14 and 14 [observed]. *U2 < 14*, *K3 < 14*: no. *U2 / K3 = 14 without refusal lines*: 35 and 76 lines [observed]. *U1-real ≠ Σ usable beyond tolerance*: diff 4096 B ≤ 1 MiB [observed]. *A4 off-count U1*, *U2-control with refusals or < 16*: no [observed]. *U3 file deleted*: the file exists with 4096 bytes [observed]. *K2 not > K1* (control did not move): 16 > 8 [observed]. *Fewer blocks than predicted in K1/K2 with "could not reserve"*, *A7 off-count K1/K2/K5*: counts as predicted, 0 "could not reserve" [observed]. *K4 caches 16*: 10 [observed]. K4 rows: see part 6 — the frozen "K4 ≈ 10 with ENOSPC failures" row and its A7 twin do not match literally, so K4 falls to A7's "K4 any other reading with `du` ≤ every `maxBytes`" → stale-snapshot caveat **not confirmed** by the frozen rows (outside the tier verdict by A7).
5. **Observed vs. inferred** — Inferred: (a) the 14-block ceiling in U2/K3 is made by the per-volume check at line 407 and not by the NameNode [inferred from: the NN had room (U2 NN capacity 61440 − used 57344 = 4096 ≥ 4096; K3 260046848 − 234881024 = 25165824 ≥ 16777216) and kept re-sending; the refusal text and its `maxAvailableSpace` operand (2048 = 30720 − 7 × 4096; 12582912 = 46137344 − 2 × 16 MiB = 213909504 − 12 × 16 MiB) are produced only by `chooseVolume`'s throw at `:414-416` when every volume fails the `if` at `:407`; U2-control and K1/K2/K5, where totals are not fragmented, show 0 refusals]. (b) K4's 270 "premature EOF" failures are cache copies cut short by the full tmpfs [inferred from: `df` avail on pmem0 reached 0 while a copy was in flight (`samples-K4.csv` 11:30:03, `du` 170566072 = 10 blocks + a 2.79 MB partial file); no such failure in K5, which cached the same 16-MiB blocks with the same code but with room; `PmemMappableBlockLoader.load` ignores `transferTo`'s return count (`:97`), so a short copy is caught only by `verifyChecksum` (`MappableBlockLoader.java:157`)]. (c) The JMX failure counter lags the log [inferred from: every "Failed to cache …" path increments `numBlocksFailedToCache` in `finally` (`FsDatasetCache.java:478-485`), yet JMX read lower; the query `name=FSDatasetState*` matches both the direct `FSDatasetState-<uuid>` bean and the metrics-source `FSDatasetState` bean, whose JMX values are cached; not load-bearing: no row uses the counter after A3/A6].
6. **Deviations and gaps** — (i) K4: B3f predicted "the rest fail in `load` with ENOSPC"; the failures came from `load` as predicted ("Failed to cache the block", not line 407; `CacheCapacity` unchanged; 10 blocks; nothing left on disk), but as a checksum premature EOF because the short `transferTo` is not checked (finding below). By the frozen rows the K4 caveat is "not confirmed"; the stale-snapshot behaviour itself (capacity 264 MiB reported while 164 MiB fit) is observed. K4 is outside both tier verdicts (A7). (ii) The cluster setup's first attempt failed on a harness bug before any reading (§3). (iii) U1-real: two pmem directories on one file system each get the full free space, so the DataNode reported 1.508 TB of cache capacity on a 753-GB disk — the cap over-states the room when directories share a mount (finding below); the case's U1-real row predicts exactly this sum, so it is a match, not a deviation, but it is worth stating. (iv) U3 is a replay of the `finally` order on the manager and `PmemMappedBlock`, not a raced cancel through `FsDatasetCache`; it shows the accounting order leaks a file, not how often a real cancel hits it. (v) Persistent memory is emulated (A2): plain directories and tmpfs, pure-Java loader; PMDK/native path and real pmem not exercised. (vi) `NumBlocksFailedToCache` read lower in JMX than in the log (part 5c) and includes duplicate commands (U2: 49 against 35 refusals); no conclusion uses it.
7. **Core question** — Usage follows the constraint. The bytes cached per pmem directory equalled `floor(maxBytes_v / block) × block` at every value tried — unit 4 (M, B) pairs and 30720 vs 32768 B/volume, cluster 136 / 264 / 164 MiB free at start → 8 / 16 / 10 blocks — and never exceeded the volume's startup free space (parts 3, 4). The per-volume check at line 407 fired where only fragmentation stood in the way (U2 14 vs 16; K3 2 + 12 = 14 while the NameNode saw room for 15), with the predicted operand (part 5a). So `dfs.datanode.pmem.cache.dirs` caps the DataNode's cache files at each directory's usable space taken at start; the cap is a snapshot (K4) and counts a shared file system once per directory (U1-real).

**Conclusion (one line):** Unit: B2g row 1 + A4 tier rule (U2 14 with refusals at 2048, control 16) — confirmed; U3 leak row — confirmed (replay). Cluster: B3g row 1 + "K3 = 14 with refusal lines" — confirmed; K4 caveat — not confirmed (failures by checksum EOF, not ENOSPC).

## 5. Self-check of run 1 — AI

Re-read after the run, by `harness/selfcheck.py` (output `run1/selfcheck.txt`), which recomputes from the raw files only (the `O31,U1/U1REAL/U2/U2POLL/U3` lines, the
unit log excerpt, every `samples-K*.csv` row, the `files-K*.txt` listings and the `dn-excerpt-K*.txt` lines), not from the `CLCHK` summaries; plus a
by-hand re-read of `dn-excerpt-K4.txt` (exception text), `samples-K4.csv` (11:30:03 row) and the U2 poll series.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `Tests run: 5, Failures: 0`; loader `PmemMappableBlockLoader` 2× in `unit-log-excerpt.txt` and in all five `dn-excerpt-K*.txt`; "DN-ready(Kn): ok=1" with logSum = jmxCapacity = nnConfiguredCacheCapacity ×5; settle at 90–91 s ×5, U2 `settled=true` ×2 |
| 2. Readings | yes | `selfcheck.txt` reproduces every count and byte figure of §4.1 from the samples and file listings (K3 cache files pmem0 2 / 33554432, pmem1 12 / 201326592) |
| 3. Matched row | yes | U1 ×4, U1-real diff 4096, U2 14 + 35 refusals all at 2048, control 16 + 0; K1/K2/K5 8/16/10, K3 14 + 76 refusals all at 12582912 |
| 4. Excluded rows | yes | per-volume file bytes ≤ logged `maxBytes` in every arm (`selfcheck.txt` "<= maxBytes … True" ×6); max `du` per sample ≤ `maxBytes`; K2 16 > K1 8 |
| 5. Observed vs. inferred | yes | (a) NN room and operand arithmetic recomputed; 0 refusals in U2-control/K1/K2/K5; (b) `samples-K4.csv` 11:30:03 `dfavail0=0`, `du0=170566072`; 270/270 failure lines carry "checksum verification failed: premature EOF"; K5 0 failures; (c) K3 73 < 76 and K4 252 < 270 re-read in `samples-K3/K4.csv` last rows and the excerpts |
| 6. Deviations and gaps | yes | K4 rows re-read: neither "K4 ≈ 10 with ENOSPC failures" nor A7's "≥ 1 'Failed to cache the block' with ENOSPC" is met literally (no ENOSPC text) → "any other reading" row; recorded as not confirmed, not re-worded |
| 7. Core question | yes | the staircase across volume sizes (unit and cluster), the fragmentation refusals with the predicted operand, and the controls (U2-control, K2 vs K1, K5 vs K2) answer "does it cap" through the audited steps |

### 5.2 Run 2?

**No** — decided 2026-11-25. The result confirms the stage-3 estimate at both tiers with exact matches; no refutation and no bypass is
claimed; the inferred statements (a)–(c) are settled from run 1's own raw files, and (c) is not load-bearing. The one unmatched caveat (K4)
is outside the tier verdicts.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** **true positive** — estimate `positive`, effect `caps` at the unit and the cluster tier.

**Claim tested:** (B1) with `dfs.datanode.pmem.cache.dirs` set, the bytes of block-cache files the DataNode keeps in each pmem cache directory
never exceed that directory's usable space measured at DataNode start; a block that does not fit in any single volume is refused at
`PmemVolumeManager.java:407` and not written, so total cached bytes follow the volume sizes and fragmentation across volumes can leave unused
room. "Confirmed" below always means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 for U1 (32/10/64/20 reserves, refusal operands 0/4096/0/8192) and U1-real (capacity = Σ usable + 4096 B), A4 tier rule: U2 14 blocks with 35 line-407 refusals "max available space is 2048", U2-control 16 with 0. U3 (outside the verdict): cancel-order leak confirmed (replay) | caps | run 1 + self-check | 2026-11-25 |
| Cluster | **Confirmed** — B3g row 1 (K1 8, K2 16, K5 10 blocks = 128/256/160 MiB on 136m / 264m / 264m − 100 MiB volumes, file bytes ≤ logged `maxBytes`) + "K3 = 14 with refusal lines" (2 + 12, 76 refusals at 12582912). K4 (outside the verdict): stale-snapshot caveat **not confirmed** by the frozen rows (10 blocks with `CacheCapacity` unchanged, but the failures were checksum premature EOF, not ENOSPC) | caps | run 1 + self-check | 2026-11-25 |

**Positive control:** U2-control (no fragmentation) cached 16 with 0 refusals; K2 (264m) cached 16 against K1's 8 with the same workload.

**Findings beyond the verdict** (upstream / doc candidates; check JIRA first):
- `PmemMappableBlockLoader.load` ignores the return value of `blockChannel.transferTo(0, length, …)` (`PmemMappableBlockLoader.java:97`). On a
  full pmem file system the copy is short and the block is rejected only by the checksum check as "premature EOF" (K4: 270 times in the 91-s arm,
  while the NameNode kept re-sending because the DataNode still reported 104 MiB free). The `transferTo` contract also allows a short
  return on a file system with room, which the same unchecked call would turn into a failed block.
- The capacity is measured per directory with `getUsableSpace()` (`PmemVolumeManager.java:245`): two configured directories on one file
  system each get its whole free space (U1-real: 1.508 TB reported on a 753-GB disk), so the NameNode schedules up to twice what fits; the
  docs ("the volume capacity will be detected") do not warn against it.
- The cancel-path order (`FsDatasetCache.java:479-484`: `release` before `close`) leaves a cache file on the volume that is no longer
  counted (U3: 4096 bytes on disk, used 0, WARN "Failed to delete the mapped File: null!"). With recovery off the file is removed at the next
  restart; with recovery on it is re-counted as cached.
- No memory holder worth an OOM look (heap not measured here): the pmem cache is files on the volume; the DataNode keeps one map entry per
  cached block (`blockKeyToVolume`, `mappableBlockMap`).

**Feedback filed:** the case file's audit amendments A1–A7 (2026-11-25, before any reading, inline in B2a, B2d, B2g, B3a, B3c, B3g) and
section D (D1 audit, D2 result; 2026-11-25) in `/users/jason92/writeup-hadoop/out/o31/case-amended.md`; whole-file sha256 after section D
`8661c3b8b697d4069b3e42ce3d65b41ca41d9027ce30c66ebece03381687ba6f` (sections A–C and the amendments unchanged since the freeze). Recommendations for stage 3 (not applied): R8 (§1). Nothing in the repository was edited (`_INDEX.md`, `queue.csv`, HANDOFF are
left to the parent session).

**Left on the node:** `/mydata/jingsong-s4/dfs.datanode.pmem.cache.dirs-chooseVolume-availableBytes-run1/` (2.1 MB: `harness/`, `logs/`
with `unit/` surefire reports and `cluster/` run log, samples, file listings, per-arm DataNode log slices and the NN/DN daemon logs). The
source copy, the distribution copy, MiniDFSCluster data, NN/DN data and the 384-MiB input were deleted; both tmpfs volumes unmounted (no
`pmem` mount, no loop device). No daemon, test JVM or Maven process left (checked 11:33:47 MST), ports free, driver PID file
`/mydata/s4/DRIVER-jingsong-h31.pid` removed, node lock released at the end. Undo: `rm -rf /mydata/jingsong-s4/dfs.datanode.pmem.cache.dirs-chooseVolume-availableBytes-run1/`.
