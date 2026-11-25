# dfs.datanode.max.locked.memory-addNewPendingCached-pendingCapacity--autonomous — stage-4 results  <!-- file: results/dfs.datanode.max.locked.memory-addNewPendingCached-pendingCapacity--autonomous.md -->

> **Case:** [`dfs.datanode.max.locked.memory-addNewPendingCached-pendingCapacity--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/dfs.datanode.max.locked.memory-addNewPendingCached-pendingCapacity--autonomous.md)
> (stage-3 queue order 23; at run time the amended case file is `/users/jason92/writeup-hadoop/out/o23/case-amended.md`, outside the repository)
>
> **Status:** **verdict filed 2026-11-25** — unit **Confirmed** (caps), cluster **Confirmed** (caps). Claim tested (B1): with
> `dfs.datanode.max.locked.memory = C`, caching a path larger than C leaves exactly `floor(C/B)` blocks cached on the DataNode, cache
> used = `floor(C/B)·B ≤ C`, locked memory ≤ C, and the NameNode check at `CacheReplicationMonitor.java:745` is what keeps it from
> scheduling more (no DataNode reserve failures). Cached blocks / CacheUsed / BYTES_CACHED followed C exactly at both tiers (unit
> 0 / 4 / 8 / 16 blocks at C = 0 / 16 / 32 / 64 KiB; cluster real `VmLck` 0 / 2048 / 4096 / 6144 kB at C = 0 / 2 / 4 / 6 MiB and
> 65536 / 131072 / 262144 kB at C = 64 / 128 / 256 MiB), the check's TRACE line fired in every over-cap row, the DataNode logged no
> reserve refusal, and with line 745 disabled the NameNode commanded all 32 blocks and the DataNode refused 2000+ reservations.
> `NumBlocksFailedToCache` was not 0 as B2f/B3f said: every count is a duplicate cache command (block ids sent − distinct ids),
> read through the pre-registered A3/A7 rows. One run 1, no run 2.
>
> **Outcome class:** **true positive** — stage-3 estimate `positive` against the stage-4 effect `caps` at both tiers
> ([definition](../../../../stage4-runtime-verification/README.md#outcome-class))
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

**Layout.** Hadoop, Jingsong's share, run by a fresh autonomous stage-4 agent on node `pc82`. At run time this file, the harness and the
raw excerpts are outside the repository: this file `~/writeup-hadoop/out/o23/results.md`, harness `~/writeup-hadoop/out/o23/harness/`,
raw excerpts `~/writeup-hadoop/out/o23/run1/` (cited below as `run1/...`), amended case file `~/writeup-hadoop/out/o23/case-amended.md`.
When filed in the repository they go to `hadoop/stage4-runtime-verification/jingsong/results/` (this file and `results/<stem>/run1/`) and
`.../jingsong/harness/<stem>/`. Protocol: `experiments/capacity-enforcement-exp/stage4-runtime-verification/README.md` "The run protocol";
node environment: `hadoop/stage4-runtime-verification/jingsong/environment.md` (`pc82` is in its Node table). Earlier stage-4 attempts on this
case (2026-11-24) never started a run: no `/mydata/jingsong-s4/<stem>-run1` existed on `pc82` at the start (checked 2026-11-25 05:08 MST);
the old draft `~/writeup-hadoop/out/o23/<stem>.md` is byte-identical to the repository case file and was ignored.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, repository commit `bef6bc8a6` (2026-11-24), repository HEAD at the audit `cd9e1cded`; sha256 as filed `46fe6c3e625c84bbc582a585309f45fd61b5f289b4420cb34169ea1ea3afe257` (= `_INDEX.md` §4). After the audit's dated amendments A1–A7 (2026-11-25, before any reading): whole-file sha256 **`759f0d3ad3f8fce2c5608623f058b9f1f5a4af9d6730add5b336722749e1e2d3`** (frozen version, `case-amended.md` before its section D was filled). |
| **After the run** | Section D (D1, D2) filled 2026-11-25 after run 1; whole-file sha256 `0555efaf136350d1931a07b60e43d2df8099c288273e385271fb55fb47b539b3`; sections A–C unchanged since the freeze. |
| **Harness** | `~/writeup-hadoop/out/o23/harness/` (written after the freeze, before run 1): `TestCacheCapacityCheck.java` md5 `1e452c96`, `unit-run.sh` `39d78e1b`, `cluster-run.sh` `ec09e41b`, `sampler.py` `31f11ce7`. Not committed (outside the repository). Instrument checks: `python3` parse of `sampler.py` and `bash -n` of both scripts OK; `unit-run.sh compile` BUILD SUCCESS 2026-11-25 05:12:58 MST (node time) (`run1/unit/unit-run.log`); `cluster-run.sh setup`: native `hadoop-common` BUILD SUCCESS (38 s), `hadoop checknative` → `hadoop: true …/lib/native/libhadoop.so.1.0.0` 05:14:22 MST (`run1/cluster/cluster-run.log`). Known answers inside the runs: unit `IFCHK,instr` (NoMlock manipulator, page size 4096, DN cache capacity = C); cluster DataNode log "Starting DataNode with maxLockedMemory = C" and JMX/NN capacity = C before each phase, `VmLck` baseline. |
| **Tiers and values** | Unit (B2): MiniDFSCluster, 1 DN, B = 4096-byte blocks, `/big` 32 blocks; C ∈ {0 (default), 16384, 32768, 65536}; positive control `/small` 2 blocks at C = 32768; mutation control (line 745 disabled) at C = 32768. Cluster (B3): pseudo-distributed NN + DN with native mlock, 1-MiB blocks, `/big` 16 MiB; C ∈ {0 (default), 2, 4, 6 MiB}; positive control `/small` 4 MiB at 6 MiB; larger series (A6) 16-MiB blocks, `/big2` 512 MiB, C ∈ {64, 128, 256 MiB}. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity named, memory bytes | Met | A2: mlocked DataNode memory (`VmLck`), DN `CacheUsed`; B1. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b 0/16K/32K/64K; B3b 0/2/4/6 MiB; default 0 is a value at both tiers. |
| A. Core question | real resource measured, not only the counter | Met | B3d `VmLck` of the DN process; B2d names the gap (mlock stubbed at the unit tier). |
| A. Core question | usage driven to and past the limit | Met | B2c 131072 B needed vs C ≤ 65536; B3c 16 MiB vs C ≤ 6 MiB. |
| A. Core question | negative-claim positive control | n/a | estimate positive; the `/small` controls show usage moves with the workload below the cap. |
| B. Logic | hypothesis / test / logic / refuted-if mapped | Met | B1 ↔ B2b–e/B3b–e ↔ B2f/B3f ↔ B2g/B3g ("CacheUsed > C", "flat across C"). |
| B. Logic | prediction in numbers before the run | Met | B2f/B3f exact blocks, bytes, kB. Small control had no B2f row → **amended** (A3). |
| B. Logic | every plausible outcome has a row | Partly → Met | `NumBlocksFailedToCache` also counts duplicate cache commands (`FsDatasetCache.java:276-281`), so "failures > 0" alone does not prove a past-C assignment; no row for a failed control or a mutation not in effect; no row for an unsettled cluster phase → **amended** (A3, A7). |
| B. Logic | confirmation needs ceiling following the knob + disallow-branch evidence | Met | TRACE line of `:745-752` ("is not a valid possibility because the block has size") counted at both tiers; the mutation run isolates `:745` from the DN reserve. |
| B. Logic | alternative explanations and their controls | Met | DN reserve backstop (mutation run, "could not reserve" lines), caching not working (`/small` controls), other locked memory (`VmLck` baseline, C = 0), rescanCachedBlockMap trim `:519-541` (mutation row of B2g). |
| C. Specific | human can follow; AI can run without re-deriving | Partly → Met | Settle rule "5 polls of 500 ms" can stop before the first rescan and ignores the 30-s cache-command resend window → **amended** (A2, A5). Node specifics (copy script, `~/.m2`, native build) → **amended** (A1, A4). |
| D. Runnable | harness and environment prerequisites | Partly → Met | Test class and scripts are step-1 work; the base distribution on `pc82` has no `libhadoop`, and CMake/zlib headers were absent → **amended** (A4: apt install, native `hadoop-common` build in the case copy). |
| D. Runnable | workload arithmetic | Met | ≤ 256 MiB locked vs 125 GiB RAM and `ulimit -l` 16492912 kB; ≤ 600 MiB HDFS data on `/mydata` (658 GB free). |
| D. Runnable | citations spot-checked against the pinned source | Met | `CacheReplicationMonitor.java:745` (the `if`), `:746-752` TRACE text, `:519-541` trim; `DataNode.java:1892-1914` (mlock/ulimit checks, "Starting DataNode with maxLockedMemory"); `FsDatasetCache.java:415-423` ("could not reserve more bytes"), `:276-281` (duplicate counts as failure); `DatanodeManager.java:1785-1789` (resend gate). |

**Recommendations**

| # | Recommendation | Action | Why |
|---|---|---|---|
| R1 (A1) | Unit tier: node specifics (`copy-source.sh`, no `-am install`, exact test selectors) | Applied 2026-11-25 | runnable as written on `pc82` |
| R2 (A2) | Unit settle rule: 10 equal polls and ≥ 35 s after the directive, max 90 s | Applied 2026-11-25 | 2.5 s can settle before the first rescan; resend interval 30 s |
| R3 (A3) | Count DN "could not reserve" lines and TRACE "added to PENDING_CACHED" lines; B2f small-control row; B2g rows for duplicate-command failures, failed control, mutation not in effect | Applied 2026-11-25 | `NumBlocksFailedToCache` is not specific to reserve refusal |
| R4 (A4) | Cluster tier: native build on `pc82`, base-dist copy, both files written at first DN start, DN-ready check on JMX + NN capacity = C | Applied 2026-11-25 | a DN with C > 0 does not start without native mlock |
| R5 (A5) | Cluster settle rule (≥ 60 s, last 4 samples equal, max 120 s); "≈" = within 16 kB | Applied 2026-11-25 | unambiguous plateau and tolerance |
| R6 (A6) | Run the optional larger series (`ulimit -l` allows it) with explicit B3f rows | Applied 2026-11-25 | a clearer `VmLck` dose-response (64–256 MiB) |
| R7 (A7) | B3g rows for duplicate-command failures and an unsettled phase | Applied 2026-11-25 | every plausible outcome needs a row before any reading |
| R8 | Stage 3: B2a's `rsync`/`-am install` and B3a's `mvn package -Pdist,native` are generic; name the per-person `copy-source.sh` and the `~/.m2` shortcut | Not applied (stage-3 recommendation) | — |

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-11-25 (node clock MST: compile 05:12, unit 05:14–05:21, cluster setup 05:13–05:14, cluster run 05:21:59–05:35:47) | not done |
| Node | `pc82` = `node1.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu` (in `environment.md`'s Node table), 40 cores, 125 GiB; node lock `/mydata/s4/NODE-LOCK` held 05:08:50–05:36 MST; no Java process (`jps`) and ports 9000/9870/9864/9866/9867 free before the cluster run | — |
| OS, kernel, limits | Ubuntu 22.04.2 LTS, `5.15.0-203-generic`; `ulimit -l` 16492912 kB hard and soft | — |
| JDK | OpenJDK `1.8.0_514` (`/usr/lib/jvm/java-8-openjdk-amd64`) for build, unit tests and daemons | — |
| Build tool | Maven 3.6.3; node `~/.m2` 3.4.2 artifacts from the base build; native: CMake 3.22.1, `zlib1g-dev`, `libssl-dev`, `pkg-config` installed with apt on 2026-11-25 for A4 (log `~/o23-apt.log` on `pc82`) | — |
| Local source copy | `/mydata/jingsong-s4/<stem>-run1/src` by `copy-source.sh` from `systems/hadoop/source/` (repository HEAD `cd9e1cded`, source clean), tag `rel/release-3.4.2`; only `TestCacheCapacityCheck.java` added; line 745 mutated only during the mutant run and restored with `git checkout` (`run1/unit/unit-run.log`, `run1/unit/mutation.diff`); `hadoop-common` built with `-Pnative` there. Deleted after the run | — |
| Cluster distribution | copy of `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` + `libhadoop.so.1.0.0` from the case copy; configs in `run1/cluster/daemon-logs/{core,hdfs}-site.xml` (C as last set) | — |
| Case-file / harness version | sha256 `759f0d3a…` (frozen, A1–A7) / md5s in §1, uncommitted | — |
| Storage | MiniDFSCluster data `/mydata/jingsong-s4/<stem>-run1/test-data`; cluster `…/cluster/{nn,dn,tmp,data}` (≈ 550 MiB of blocks); nothing on `/proj` | — |
| Full logs | On `pc82`: `/mydata/jingsong-s4/dfs.datanode.max.locked.memory-addNewPendingCached-pendingCapacity--autonomous-run1/logs/` (11 MB: `unit/` with surefire reports, `cluster/` with `cluster-run.log`, `samples-*.csv`, native build log, `daemon-logs/` NN + DN logs with the TRACE lines). Copies of the evidence used here: `~/writeup-hadoop/out/o23/run1/` | — |

## 3. Runbook defects

None. Every step ran as written (with A1–A7) on the first attempt; no step was repeated.

## 4. Run 1

**Scope:** both tiers, every row of B2f and B3f (with A3/A6 rows). **Command logs:** `run1/unit/unit-run.log`, `run1/cluster/cluster-run.log`.
Raw data: `run1/unit/unmutated-ifchk.csv`, `run1/unit/mutant-ifchk.csv` (the `IFCHK` lines of the surefire `-output.txt`),
`run1/cluster/samples-<phase>.csv` (every 5-s sample) and the `CLCHK` lines in `cluster-run.log`; cache commands per row:
`run1/unit/unmutated-dna-cache.txt`, `run1/cluster/dn-cache-commands.txt` (from the DataNode logs).

### 4.1 Readings

**Unit tier** (B = 4096; settled under A2 in every unmutated row: 10 equal polls, 35.1–35.3 s):

| C | blocks cached (pred.) | DN CacheUsed | BytesCached / Needed | NN pending after settle | NumBlocksFailedToCache | DN "could not reserve" | TRACE reject / added | DNA_CACHE commands (ids each) |
|---|---|---|---|---|---|---|---|---|
| 0 | 0 (0) | 0 | 0 / 131072 | 0 | 0 | 0 | 1152 / 0 | none |
| 16384 | 4 (4) | 16384 | 16384 / 131072 | 0 | 4 | 0 | 1012 / 4 | 2 (4, 4: same blocks) |
| 32768 | 8 (8) | 32768 | 32768 / 131072 | 0 | 8 | 0 | 864 / 8 | 2 (8, 8) |
| 65536 | 16 (16) | 65536 | 65536 / 131072 | 0 | 16 | 0 | 576 / 16 | 2 (16, 16) |
| 32768, `/small` 2 blocks (control) | 2 (2) | 8192 | 8192 / 8192 | 0 | 4 | 0 | 0 / 2 | 3 (2, 2, 2) |
| **mutant** 32768 (line 745 disabled) | 8 (8) | 32768 | 32768 / 131072 | 24 (max 32) | 2168 (growing; `settled=false` at 90 s) | 2180 in the test stdout (2463 in the capturer) | 0 / 2192 | 91 in 90 s; first two 32 ids each, then 24 |

The maximum DN CacheUsed over all polls equalled the final value in every row (`maxDnCacheUsed`, `withinCap=true` ×6).

**Cluster tier** (1-MiB blocks for `/big` 16 MiB and `/small` 4 MiB; 16-MiB blocks for `/big2` 512 MiB; every phase settled under A5 at 62.2–62.3 s; `VmLck` baseline 0 kB before every phase and 0 kB after every removal):

| Phase | C | DN start line | NumBlocksCached (pred.) | CacheUsed = BYTES_CACHED (pred.) | VmLck kB (pred.) | max VmLck / max CacheUsed | Failed | DN "could not reserve" | NN reject / added lines | block ids sent / distinct |
|---|---|---|---|---|---|---|---|---|---|---|
| C0 | 0 | `maxLockedMemory = 0` | 0 (0) | 0 (0) | 0 (0) | 0 / 0 | 0 | 0 | 336 / 0 | 0 / 0 |
| C2M | 2097152 | `= 2097152` | 2 (2) | 2097152 (2097152) | 2048 (≈ 2048) | 2048 / 2097152 | 2 | 0 | 310 / 2 | 4 / 2 |
| C4M | 4194304 | `= 4194304` | 4 (4) | 4194304 | 4096 (≈ 4096) | 4096 / 4194304 | 4 | 0 | 268 / 4 | 8 / 4 |
| C6M | 6291456 | `= 6291456` | 6 (6) | 6291456 | 6144 (≈ 6144) | 6144 / 6291456 | 6 | 0 | 226 / 6 | 12 / 6 |
| ctrl `/small` | 6291456 | `= 6291456` | 4 (4) | 4194304 (4194304) | 4096 (≈ 4096) | 4096 / 4194304 | 6 | 0 | **2** (pred. 0) / 4 | 10 / 4 |
| L64M | 67108864 | `= 67108864` | 4 (4) | 67108864 | 65536 (≈ 65536) | 65536 / 67108864 | 4 | 0 | 620 / 4 | 8 / 4 |
| L128M | 134217728 | `= 134217728` | 8 (8) | 134217728 | 131072 (≈ 131072) | 131072 / 134217728 | 8 | 0 | 536 / 8 | 16 / 8 |
| L256M | 268435456 | `= 268435456` | 16 (16) | 268435456 | 262144 (≈ 262144) | 262144 / 268435456 | 16 | 0 | 368 / 16 | 32 / 16 |

BYTES_NEEDED 16777216 (`/big`), 4194304 (`/small`), 536870912 (`/big2`). NN `dfsadmin -report` Cache Used equalled the DN's CacheUsed in every final sample.

| Disallow-branch line (example) | `Block 1073741873: DataNode 7c66a236-… is not a valid possibility because the block has size 16777216, but the DataNode only has 0 bytes of cache remaining (0 pending bytes, 0 already cached.)` | `run1/cluster/nn-check-excerpt.txt` |
|---|---|---|

### 4.2 Conclusion and logic

1. **Validity** — valid. Unit: instruments as configured in every row (`IFCHK,instr`: NoMlock manipulator, page size 4096, DN cache capacity = C) [observed]; every unmutated row settled under A2 [observed: `unmutated-ifchk.csv`]; surefire 5/0/0 and 1/0/0 [observed]; the mutant ran on a copy whose line 745 reads `if (false && …)` and was restored afterwards [observed: `mutation.diff`, `unit-run.log`]. Cluster: `hadoop: true` [observed: `cluster-run.log` setup block]; each DataNode started with `maxLockedMemory = C` and reported capacity C on JMX and on the NameNode before the directive [observed: `dn-excerpt.txt`, `cluster-run.log`]; every phase settled under A5; the cache was empty (CacheUsed 0, VmLck 0) before and after every phase [observed]. The limit was passed in every C > 0 `/big` row (needed 2.7×–8× C) [observed: BYTES_NEEDED].
2. **Readings** — blocks cached, CacheUsed, BYTES_CACHED and VmLck equal B2f/B3f/A6 exactly in all 5 unmutated unit rows and all 8 cluster phases; VmLck = CacheUsed/1024 with baseline 0 [observed]. Two numbers differ from the frozen tables: `NumBlocksFailedToCache` (predicted 0) and the control's NN reject-line count (predicted 0, read 2) — parts 4 and 6.
3. **Matched row** — Unit: B2g row 1 ("blocks cached = C/4096 and CacheUsed = C for each C, pending empty, failures 0") as read through the A3 row "failures > 0 with 0 'could not reserve' lines, CacheUsed = C, pending empty → duplicate cache commands; reads as row 1" [observed: failures = ids sent − distinct ids in every row, `unmutated-dna-cache.txt`]; plus B2g "mutated run shows failures > 0 and non-empty pending, unmutated shows 0 [reserve refusals]" → line 745 is the scheduling cap [observed]. Cluster: B3g row 1 ("VmLck and CacheUsed step 2 → 4 → 6 MiB with C, BYTES_CACHED < BYTES_NEEDED, failures 0") through the A7 duplicate-command row, and the same staircase at 64/128/256 MiB (A6) [observed]. The confirmation condition holds at both tiers: the ceiling follows C, and the check's own TRACE line ("is not a valid possibility because the block has size") fired in every over-cap row [observed].
4. **Excluded rows** — *CacheUsed > C* / *VmLck > C/1024 + baseline*: max CacheUsed and max VmLck over every poll/sample equal C (or C/1024) at most [observed]. *Flat across C*: 0/4/8/16 and 0/2048/4096/6144, 65536/131072/262144 kB [observed]. *CacheUsed = C but VmLck ≈ 0*: VmLck = CacheUsed/1024 [observed]. *Cap held via the DN reserve, NN over-assigned* (B2g row 4, B3g row 5): 0 "could not reserve" lines in every unmutated row and phase, and the NameNode never commanded more than C/B distinct blocks (`distinct` column) [observed]. *Mutated run identical to unmutated*: no — 32 vs C/B blocks commanded, 2000+ refusals vs 0 [observed]. *Setup broken / control fails*: controls cached 2 and 4 blocks in full [observed].
5. **Observed vs. inferred** — Inferred: (a) the non-zero `NumBlocksFailedToCache` counts are duplicate commands, not refusals [inferred from: `FsDatasetCache.java:276-281` increments the counter for a block already cached/caching; in every row the count equals block ids sent − distinct ids in the DataNode's DNA_CACHE lines (unit 4/8/16/4, cluster 2/4/6/4+2/4/8/16), and the reserve-refusal WARN is absent]; (b) the cut-off is made by line 745 and not by the DataNode reserve or by the trim at `:519-541` [inferred from: the reject TRACE text is emitted only inside the `if` at `:745`; with that `if` disabled the NameNode commands all 32 blocks and the DataNode refuses the excess, so the reserve is a backstop that fires only when the NN check is gone]; (c) `VmLck` is the cache's locked memory [inferred from: 0 kB baseline, VmLck = CacheUsed/1024 in every phase, back to 0 after each directive removal].
6. **Deviations and gaps** — (i) B2f/B3f predicted `NumBlocksFailedToCache = 0`; the counter read 1–2 per cached block because the NameNode re-sent the pending blocks on the next heartbeat before the cache report moved them to cached (the DataNode counts a repeat as a failure). Read through A3/A7, written before any reading. (ii) Cluster control: 2 reject lines for `/small` blocks (B3f said 0). `nn-check-excerpt.txt` 12:29:08: blocks 41, 42 were cached but still pending, so the trim at `:519-541` dropped 43, 44 from pending (remaining 2 MiB already spent on 41, 42) and line 745 then rejected them with `pendingCapacity = 0 (-2097152 pending, 2097152 remaining)`. The DataNode had already cached all 4 from the first command, and the final state is 4 blocks, 4096 kB, as predicted. This is the double-count window the case's A3 overshoot note describes ("under-assigns, never over-assigns"); a missed count in B3f, not a reading against the claim. (iii) The mutant row did not settle (`settled=false`, counter growing), which B2f predicted ("growing with resends"); resends came about every second (91 commands in 90 s), not every 30-s retry interval as B2f assumed. (iv) Mutant: the LogCapturer counted 2463 "could not reserve" lines and the test stdout 2180, against 2168 failures read at the last poll (later lines and the capturer's own buffering); every count is far above the predicted ≥ 24. (v) Unit tier: mlock stubbed (named in B2d); real locked memory only at the cluster tier.
7. **Core question** — Usage follows the constraint. Real DataNode locked memory was 0, 2048, 4096, 6144, 65536, 131072, 262144 kB at C = 0, 2, 4, 6, 64, 128, 256 MiB with demand well above C, never above C, and released to 0 on uncache; unit DN cache accounting showed the same `floor(C/B)·B` staircase. The NameNode check at line 745 fired for every block past C and kept the commands within C (no reserve refusal); with it disabled the NameNode over-scheduled and only the DataNode reserve held the cap. So `dfs.datanode.max.locked.memory` caps the DataNode's mlocked cache memory, and line 745 is the scheduling half of that cap.

**Conclusion (one line):** Unit: B2g row 1 (via A3) + mutation row — confirmed. Cluster: B3g row 1 (via A7) and A6 rows — confirmed.

## 5. Self-check of run 1 — AI

Re-read the raw files (not the tables above) after the run: the `IFCHK,row` lines in both surefire `-output.txt` copies, the 8 `CLCHK` lines in `cluster-run.log`, each `samples-*.csv` (max VmLck, max CacheUsed, final values recomputed with a short script), the DNA_CACHE lines of both DataNode logs (`unmutated-dna-cache.txt`, `dn-cache-commands.txt`), and the NN TRACE/DEBUG lines of the control phase.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `IFCHK,instr` ×6 with `dnCacheCapacity=C`; `Tests run: 5, Failures: 0` and `1, 0`; `hadoop:  true`; `Starting DataNode with maxLockedMemory = C` ×10 in `dn-excerpt.txt`; `CacheUsed=0 after … VmLck=0 kB` ×8 |
| 2. Readings | yes | `samples-*.csv`: max VmLck 0/2048/4096/6144/4096/65536/131072/262144, max CacheUsed = C (control 4194304); `IFCHK,row` values as in §4.1 |
| 3. Matched row | yes | staircase at 4 (unit) and 7 (cluster) C values incl. the default 0; reject lines > 0 in every over-cap row; A3/A7 conditions (0 refusals, pending 0, CacheUsed = C) all true |
| 4. Excluded rows | yes | `dnCouldNotReserveLines=0` in every unmutated `IFCHK`/`CLCHK`; `distinct_blocks_commanded` = C/B in every `DNSUM` line |
| 5. Observed vs. inferred | yes | (a) ids sent − distinct = Failed in all 12 rows/phases; (b) `mutation.diff` + mutant first DNA_CACHE with 32 ids (`mutant-excerpt.txt`); (c) VmLck×1024 = CacheUsed in every plateau sample |
| 6. Deviations and gaps | yes | `nn-check-excerpt.txt` 12:29:08 lines quoted in part 6(ii); mutant counts in `mutant-ifchk.csv` and `grep -c` of the stdout |
| 7. Core question | yes | the C = 0 rows, the controls, the mutation and the VmLck baseline rule out the alternatives named in B2h/B3h |

### 5.2 Run 2?

**No** — decided 2026-11-25. The result confirms the stage-3 estimate (no refutation, no bypass); the two count deviations are explained from run 1's own raw files and do not touch the claim; the inferred statements are settled by direct log evidence.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** **true positive** — estimate `positive`, effect `caps` at the unit and the cluster tier.

**Claim tested:** (B1) for a DataNode with `dfs.datanode.max.locked.memory = C` (DRAM cache, page-aligned blocks of size B), caching a path larger than C leaves exactly `floor(C/B)` blocks cached on that DataNode, cache used = `floor(C/B)·B ≤ C`, and its locked memory does not exceed C; the NameNode check at `CacheReplicationMonitor.java:745` is what keeps it from scheduling more, so the DataNode records no reserve failures. "Confirmed" below always means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 via A3 (blocks 0/4/8/16 = C/4096, CacheUsed = C, pending 0, 0 reserve refusals; failures 4/8/16 are duplicate commands) + mutation row (line 745 disabled: 32 blocks commanded, 2168 failures, 2000+ refusals, cap held only by the DN reserve) | caps | run 1 + self-check | 2026-11-25 |
| Cluster | **Confirmed** — B3g row 1 via A7 + A6 rows: VmLck 0/2048/4096/6144 kB and 65536/131072/262144 kB = CacheUsed/1024 = C/1024; reject TRACE lines in every over-cap phase; 0 reserve refusals | caps | run 1 + self-check | 2026-11-25 |

**Positive control:** unit `/small` (2 blocks under C = 32 KiB) cached whole (8192 B); cluster `/small` (4 MiB under C = 6 MiB) cached whole (4096 kB locked).

**Feedback filed:** the case file's audit amendments A1–A7 (2026-11-25, before any reading, inline in B2a, B2d, B2f, B2g, B3a, B3d, B3f, B3g) and section D "Stage-4 result" (2026-11-25) in `/users/jason92/writeup-hadoop/out/o23/case-amended.md`. Recommendations for stage 3 (not applied): R8 (§1), and R9 — B2f/B3f should not predict `NumBlocksFailedToCache = 0`: the NameNode re-sends pending blocks each heartbeat until the cache report arrives, and the DataNode counts a repeat as a failure (`FsDatasetCache.java:276-281`); predict 0 reserve-refusal lines instead, and allow transient reject lines in a below-cap control (double-count window). Nothing in the repository was edited (`_INDEX.md`, `queue.csv`, HANDOFF are left to the parent session).

**Left on the node:** `/mydata/jingsong-s4/dfs.datanode.max.locked.memory-addNewPendingCached-pendingCapacity--autonomous-run1/` (11 MB: `harness/`, `logs/`); the source copy, the distribution copy, MiniDFSCluster data and all NN/DN data were deleted. No daemon, test JVM or Maven process (`jps` showed only `Jps`), ports free, driver PID file removed. apt packages `cmake`, `zlib1g-dev`, `libssl-dev`, `pkg-config` stay installed on `pc82` (needed for any native build; `environment.md` notes them only for `pc75`). Node lock released. Undo: `rm -rf /mydata/jingsong-s4/dfs.datanode.max.locked.memory-addNewPendingCached-pendingCapacity--autonomous-run1/`.

