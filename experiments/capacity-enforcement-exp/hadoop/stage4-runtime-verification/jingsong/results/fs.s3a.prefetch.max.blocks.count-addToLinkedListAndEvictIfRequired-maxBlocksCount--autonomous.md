# fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous — stage-4 results  <!-- file: results/fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.md -->

> **Case:** [`fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.md)
>
> **Status:** verdict filed (2026-11-06) — unit Confirmed — caps; cluster Confirmed — caps
>
> **Outcome class:** true positive
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Layout.** Hadoop, Jingsong's share: this file is in `hadoop/stage4-runtime-verification/jingsong/results/`; the case file is in
`hadoop/stage3-ai-deep-read/jingsong/cases/`; the harness is in
`../harness/fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous/`; the protocol is
[`../../../../stage4-runtime-verification/README.md`](../../../../stage4-runtime-verification/README.md#the-run-protocol);
the node is described in [`../environment.md`](../environment.md). Below, `R` =
`/mydata/jingsong-s4/fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount-run1` on `pc29`.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, repository HEAD `38acb6bf` plus the uncommitted case file (untracked at audit time). sha256 at filing (`_INDEX.md` §4, queue order 4): `33c11116e6d482e0e4a0905528e99b6d5d560468ce983089d60c299a91354ef3` (checked before the audit). After the audit's amendments A1–A7 (section D1), 2026-11-06, before any harness run or reading: whole-file sha256 **`33757ad15d04db66aedc0f10f3f2df33faf67d890ba98e8b9d1925612d32b5d4`** (frozen version). Frozen predictions and conclusions (text from the line starting `**B2f.` up to, not including, the line starting `**B2h.`, i.e. B2f + B2g + A3; `sed -n '/^\*\*B2f\./,/^\*\*B2h\./p' <file> \| sed '$d' \| sha256sum`): **`ea49b2d1868b453cb32a1a6d6b5932e59de1502b53e048cf081066b9c4c2f314`**; the same for `**B3f.` … `**B3h.` (B3f + A6 + B3g + A7): **`646b6fb984ff997ddd0ec02ea92d63e1acc1bc5b0238bf70285aaaa6f5adbcd3`**. Section D takes the feedback after the run, so the whole-file hash changes then; these text hashes do not. |
| **Harness** | `../harness/fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous/` (written after this freeze, before run 1). Uncommitted at run time (the parent session commits); md5 of each file in the run logs. |
| **Tiers and values** | Unit (B2): `maxBlocksCount` ∈ {1, 2, 4, 8} + control 1000, 20 puts of 1 MiB, 3 repetitions; LRU test (max 4); lock-timeout test (max 2). Cluster (B3): client runs N ∈ {1, 4, 16} + control 1000 (3× each), key unset (1×), sequential `-cat` (1×); container variant N ∈ {2, 1000} (1× each); 64 MiB object, 1 MiB blocks. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-06 |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: local-disk bytes of the per-stream prefetch block-file cache (`fs-cache-*.bin` in `fs.s3a.buffer.dir`); count × block size. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b: 1, 2, 4 (default), 8 + control 1000; B3b: 1, 4 (and unset), 16 + control 1000. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d/B3d: files and bytes counted on disk next to `cache.size()`, `entryListSize` and the gauge; the gap (orphans visible only as file count − gauge) is named. |
| A. Core question | usage driven to the limit and past it | Met | B2c: 20 puts > every finite max; B3c: 63–64 cache puts > every finite N (A6). |
| A. Core question | positive control (negative estimate only) | n/a (positive estimate) | A control that does not cap (max/N = 1000) is still present: it shows the workload grows disk without the cap. |
| B. Logic | each step says what it establishes | Met | B2h/B3h: control, on-disk count vs bookkeeping, dedicated dir, LRU test, repetitions, sequential-read control. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met | B2f exact. B3f evictions assumed 63 cache puts; from the source the prefetched block is also cached by `cancelPrefetches`, giving 63 or 64. **Amended** (A6). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met | B2g/B3g had no verdict wording, and lacked "counter capped but real resource grows", "limit never reached", "plateau ≠ max", repetition disagreement, container disagreement. **Amended** (A3, A7). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Ceiling following the knob (files vs max/N) plus the eviction counter `stream_evict_blocks_from_cache` / `blockEvictedFromFileCache`, incremented only inside the true branch after a successful delete (`SingleFilePerBlockCache.java:458-463`). |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: control 1000 (workload grows), dedicated dir (other writers), unset = 4 (default), sequential read (caching due to seeks), repetitions (timing). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3 steps 1–6, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met | B2a/B3a paths (`~/hadoop-3.4.2`, `/local/$USER`) do not exist; MinIO binaries are not served (`dl.min.io` HTTP 410); `start-yarn.sh` needs SSH to localhost, which does not work on the node. **Amended** (A1, A4). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | Parameterisation, repetitions, log format, sampler implementation, container script and order were open. **Amended** (A2, A5). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Test class, `SeekReader`, sampler, run scripts are step-1 work. JDK 8, Maven 3.6.3, the 3.4.2 distribution with `hadoop-aws-3.4.2.jar` + `bundle-2.29.52.jar`, distributed-shell jar present on `pc29`; moto 5.2.5 installed in `R/venv` (A4). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Unit: ≤ 20 MiB per (max, rep) in a temp folder. Cluster: ≤ 64 MiB cache + 64 MiB object (local file and moto in memory); ~45 s per client run, ~15 client runs + 2 container runs ≈ 15 min. `/mydata` has ~700 GB free. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `systems/hadoop/source/` (clean): `SingleFilePerBlockCache.java:94` (`entryListSize`), `:228-229`, `:285` (`readFile`), `:371-413` (`put`), `:421-439` (check at `:426`), `:446-471` (eviction, 5 s lock, `:458-463`), `:478` (`writeFile`), `:503-538` (close), `:610`, `:649-658`; `PrefetchConstants.java:36,42`; `CachingBlockManager.java:126-131`, `:295-306` (`cancelPrefetches`), `:439-481`, `:484-548`, `:554-564`; `S3ACachingInputStream.java:93-94`, `:105-111`, `:133-150`; `S3APrefetchingInputStream.java:111-128`; `StreamIntegration.java:139-143`; `Constants.java:547, 1583, 1642, 1684, 1690`; `S3AStoreImpl.java:290-295`; `core-default.xml:1805-1806`; `S3AInstrumentation.java:1418-1430`. All as cited, except that B3c missed the `cancelPrefetches` caching (A6). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 (A1) | Node paths, no install build, surefire counts | Applied 2026-11-06 (uncommitted; frozen sha256 above) | filed paths do not exist; the build returns 0 on test failures |
| R2 (A2) | Loop instead of JUnit parameterisation, 3 repetitions per B2h, exact log lines, no early assertions on readings | Applied 2026-11-06 | unambiguous run and evidence |
| R3 (A3, A7) | Verdict wording for every row; added rows (counter capped/real resource grows, limit never reached, plateau ≠ max, repetitions, container disagreement, unset ≠ 4, sequential leaves files) | Applied 2026-11-06 | every plausible outcome needs a row before any reading |
| R4 (A4) | moto server instead of MinIO; `yarn --daemon start`; aux-services unset; vmem check off; container configuration without `fs.s3a.buffer.dir` | Applied 2026-11-06 | MinIO binaries are not served; no SSH to localhost; shuffle not needed; vmem kill would void the container runs |
| R5 (A5) | Exact procedure: `IFCHK,stats` line, Python sampler, order, container script by absolute path, stop conditions | Applied 2026-11-06 | an AI can run it without choices |
| R6 (A6) | Cache puts P ∈ {63, 64}; evictions `P − N` | Applied 2026-11-06 | source: `cancelPrefetches` caches the prefetched block (`CachingBlockManager.java:295-306`) |
| R7 | A3.4/B1 "never exceeds max + 1": two puts in flight on the future pool (e.g. a left block and a cancelled prefetch at the same seek) can transiently hold max + 2 files; the bound is `max + #puts in flight` | Left for stage 3 | not reachable by the 100 ms sampler; does not change B3f for this workload (one put per seek once the cache is full) |

**Agreement criteria** — only if run 2 is chosen (see 5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-11-06 (unit 12:17–12:18, cluster 12:21–12:35 node local time) | not done |
| Node (CloudLab name and type) | `pc29` (`node2`, experiment `jason92-323989`), 40 cores, 251 GiB RAM | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` | |
| JDK (`java -version`) | OpenJDK `1.8.0_504` (`JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64`) | |
| Ant (`ant -version`) | n/a (Hadoop: Maven 3.6.3) | |
| Local source copy | `copy-source.sh` → `R/src` from `systems/hadoop/source/` (rel/release-3.4.2) at repository commit `38acb6bf`; distribution copied from `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` (built 2026-11-06) to `R/hadoop` | |
| Case-file commit / harness commit | uncommitted (parent session commits). Case file frozen at sha256 `33757ad1…12d32b5d4` (A1–A7); after the run-1 defect fixes A8, A9 `a03e6496…453def3` (prediction/conclusion text hashes unchanged, §1). Harness md5: `TestBlockCacheLruCap.java` `8c28f837…`, `unit-run.sh` `59a9df6e…` (in `run1/unit/unit-run.log`); cluster files' md5 in `run1/cluster/cluster-run.log` | |
| Storage for node data | `/mydata` (local LVM volume, 754 GB, ~700 GB free); unit temp folders `R/tmp-unit`; client cache dir `R/s3abuf`; NM local dir `R/nm-local` | |
| S3 store (deviation, A4) | moto server 5.2.5 (Python 3.10 venv `R/venv`, `127.0.0.1:9000`, in-memory), bucket `ifchk-pf` (A8), object `obj64m` 64 MiB random (md5 `a9862cb1…` read back equal) | |
| Full logs (path, outside the repo) | `R/logs/` on `pc29` (`unit/`, `cluster/`, `cluster-attempt1..3/`, `selfcheck.txt`); `R = /mydata/jingsong-s4/fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount-run1` | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | 1, cluster attempt 1 | B3e step 1 (create bucket) | the harness's unsigned `curl -X PUT` got HTTP 400 from moto; S3A then failed with `NoSuchBucket` at `-put` | create the bucket with `boto3` from the venv (harness only; the case file names no command) | 2026-11-06, tier restarted | n/a (harness) |
| 2 | 1, cluster attempt 2 | B3c/B3e (bucket `pf`) | `pf` is not a valid S3 bucket name (3–63 chars): `InvalidBucketName` | bucket `ifchk-pf` (A8) | 2026-11-06, tier restarted; B3f/B3g unchanged | uncommitted (A8) |
| 3 | 1, cluster attempt 3 | B3e step 3, N = 1 rep 2 | `SeekReader` died at block 1: `NoSuchFileException` on a cache file evicted by a concurrent put between `getEntry` and the read lock (upstream race; `run1/cluster/attempts-1-3-stops.txt`) | `SeekReader` retries a failing block (≤ 3 attempts) and logs `IFCHK,readerror` (A9). Attempt 3's one finished reading (N = 1 rep 1) was discarded | 2026-11-06, tier restarted; B3f/B3g unchanged | uncommitted (A9) |

The unit tier ran once, without defects. The reported cluster run is attempt 4 (`R/logs/cluster/`).

## 4. Run 1

**Scope:** unit tier (B2) in full; cluster tier (B3) in full: client runs N = 1, 4, 16, 1000 (3× each), unset (1×), sequential
`-cat` (1×), container variant N = 2, 1000 (1× each). **Command logs:** `fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous/run1/unit/unit-run.log`,
`fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous/run1/cluster/cluster-run.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/ifchk.csv`, from the surefire output `R/logs/unit/…TestBlockCacheLruCap-output.txt`; surefire
`Tests run: 3, Failures: 0, Errors: 0`, `run1/unit/surefire-summary.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `testCapScales`, all 300 put rows (5 max × 3 reps × 20 puts) against B2f: files = min(b+1, max), `cacheSize == files == entryListSize`, bytes = files × 1 MiB, in-put peak = min(b+1, max+1), evictions = max(0, b+1−max) | 300 / 300 match | `run1/unit/ifchk.csv` (`IFCHK,cap,…`), `run1/selfcheck.txt` |
| after 20 puts, max = 1 / 2 / 4 / 8 | files 1 / 2 / 4 / 8 (1,048,576 / 2,097,152 / 4,194,304 / 8,388,608 B); evictions 19 / 18 / 16 / 12; peak 2 / 3 / 5 / 9; all 3 reps identical | same |
| control max = 1000 | files 20 (20,971,520 B), evictions 0, peak 20, all 3 reps | same |
| files after close (15 caches) | 0 in every case; `blockRemovedFromFileCache` = 20 | `IFCHK,close,…` |
| `testLruOrder` (max 4, 3 reps) | `containsBlock(0)` true, `containsBlock(1)` false; files 4, 1 eviction | `IFCHK,lru,…` |
| `testEvictionLockTimeoutLeaks` (max 2, 3 reps) | `put(2)` 5006 ms; then files 3, `cacheSize` 3, `entryListSize` 3, evictions 0; after puts 3, 4: files 3, `entryListSize` 3, evictions 2, `containsBlock(0)` true; after close 0; one "deletion would not be attempted" ERROR per rep (3) | `IFCHK,bypass,…`, `run1/unit/lock-timeout-errors.txt` |

**Cluster tier** (`run1/cluster/readings.tsv`; raw: `R/logs/cluster/<label>.samples.csv` and `<label>.client.log` /
container stdout; P = gauge + evictions)

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| N = 1 | client r1 / r2 / r3 | sampled max files (bytes); end of hold; gauge; evictions; P; after exit | 2 (2,097,152) / 2 (2,097,152) / 2 (1,048,576); 1 / 1 / 1; 1 / 1 / 1; 63 / 65 / 65; 64 / 66 / 66; 0 / 0 / 0. Read errors 0 / 1 / 1 (block 1, `NoSuchFileException`, retried) | `readings.tsv`, `ifchk-lines.txt`, `client-N1-r2.client.log` |
| N = 4 | client r1 / r2 / r3 | same | 5 / 5 / 5 (max 5,242,880 B); 4; 4; 60; 64; 0 — all three | `readings.tsv`, `client-N4-r1.samples.csv` |
| unset (default) | client r1 | same | 5 (4,194,304 B); 4; 4; 60; 64; 0 | `readings.tsv` |
| N = 16 | client r1 / r2 / r3 | same | 16 / 16 / 17 (max 17,825,792 B); 16; 16; 48; 64; 0 | `readings.tsv` |
| N = 1000 (control) | client r1 / r2 / r3 | same | 64 (67,108,864 B); 64; 64; 0; 64; 0 — all three | `readings.tsv` |
| — | sequential `hadoop fs -cat` | sampled max cache files | 0 (124 samples) | `cluster-run.log` (READING client-seqcat) |
| N = 2 | container | same; buffer dir | 3 (3,018,752 B); 2; 2; 62; 64; 0; `fs.s3a.buffer.dir` resolved to `R/nm-local/usercache/jason92/appcache/<app>/s3a` | `readings.tsv`, `container-N2.…stdout` |
| N = 1000 | container | same | 64 (67,108,864 B); 64; 64; 0; 64; 0 | `readings.tsv` |
| all | all | lock-timeout ERRORs; "Caching disabled"; cache-put errors | 0; 0; 0 in every run | `readings.tsv` |

### 4.2 Conclusion and logic

1. **Validity** — Unit: the limit was reached and passed (20 puts > max for every finite max; 19…12 evictions)
   [observed: `run1/unit/ifchk.csv`]; block size fixed at 1 MiB and one temp folder per (max, rep) [observed: `IFCHK,instr`, code].
   Cluster: the stream was the prefetching stream with 1 MiB blocks and 64 blocks [observed: `IFCHK,start`/`IFCHK,stream` in
   `ifchk-lines.txt`]; the key reached the stream (gauge = N) [observed: `readings.tsv`]; the limit was passed (P = 64 cache puts
   > N + 1 for every finite N) [observed]; caching was never disabled and the cache dir was dedicated and empty before each run
   (sequential run 0 files) [observed: `readings.tsv`, `cluster-run.log`]. Valid.
2. **Readings** — (a) Two N = 1 runs hit the eviction/get race at block 1 (A9) and re-cached it, so P = 66 there instead of 63 or
   64 [observed: `client-N1-r2.client.log`, `readings.tsv`]; files stayed ≤ 2 and the end-of-hold count 1. (b) `maxBytes` is
   sometimes below `maxFiles × 1 MiB` (N = 1 r3, N = 4 r2): a sample caught a freshly created, still empty temp file
   [inferred: `getTempFilePath` creates the file before `writeFile`, `SingleFilePerBlockCache.java:393-402`]. (c) The transient
   N + 1 was sampled in 9 of the 11 finite-N runs, not in N = 16 r1/r2 (100 ms sampling) — expected (B3d).
3. **Matched row** — Unit, B2g row 1 (A3): "Files plateau at `max` and peak at `max+1`, for every finite max; control grows to
   20" → files after 20 puts = max and in-put peak = max + 1 for max 1, 2, 4, 8 in all reps, control 20, `cacheSize == files ==
   entryListSize`, 0 after close [observed: `ifchk.csv`]; disallow branch fired: `blockEvictedFromFileCache` = 20 − max
   [observed]. Cluster, B3g row 1 (A7): "Files plateau at N, never above N+1, scaling with N; control reaches ~63" → sampled max
   ≤ N + 1 (2, 5, 17 and container 3), end-of-hold = gauge = N (1, 4, 16; container 2) in every run, control 64 (≥ P − 1), 0
   after exit [observed: `readings.tsv`]; disallow branch fired: `stream_evict_blocks_from_cache` = P − N (63/60/48, container
   62) [observed].
4. **Excluded rows** — Unit: row 2 / added row 7 (above max + 1, or counter capped but files higher) — never: files = counter =
   `entryListSize` in all 300 rows; row 3 (same plateau) — plateaus 1, 2, 4, 8 differ; row 4 (control plateaus) — control 20;
   row 6 (files after close) — 0 in all 15; row 8 (plateau ≠ max) — = max; row 10 (limit never reached) — 20 puts all
   succeeded; row 11 — the three reps are identical; bypass "files stay at 2" — files 3, ERROR logged; bypass "rising per put" —
   stayed 3; row 9 (LRU) — LRU held. Cluster: row 2 (> N + 1, no ERROR) — max ≤ N + 1 everywhere; row 3 (leak with ERROR) — 0
   ERRORs; rows 4/5 (same plateau / control low) — 1/4/16 differ, control 64; row 6 (files after exit) — 0 in all 17 runs;
   added row 7 (gauge ≤ N, files > N + 1) — files = gauge; row 8 (end-of-hold ≠ N) — = N; row 9 (unset ≠ 4) — unset = 4;
   row 10 (sequential leaves files) — 0; row 11 (container disagrees) — container N = 2 → 2 (max 3), N = 1000 → 64; row 12 —
   reps agree on every decisive column.
5. **Observed vs. inferred** — The conclusion rests on observed counts only. Inferred: (i) the cause of P = 66 (re-caching after
   the race) — it touches only the evictions column, which no row uses; (ii) the race mechanism of A9 (from the stack trace and
   `SingleFilePerBlockCache.java:273-277`, `:446-466`), a finding, not part of the verdict.
6. **Deviations and gaps** — moto instead of MinIO (A4; S3A requests are the same HEAD/ranged GET/PUT); bucket `ifchk-pf` (A8);
   `SeekReader` retry (A9); evictions column: P = 66 in 2 of 15 client runs (A6 predicted 63–64; explained in 2a); the 100 ms
   sampler cannot see sub-100 ms peaks (an N + 2 transient from two concurrent puts, R7, would be missed; in the unit tier the
   in-put peak was measured exactly); the NM/RM daemon logs were deleted in the cleanup after the readings were taken (the
   container stdout/stderr were copied first).
7. **Core question** — Usage followed the constraint: the steady cache size was exactly `max` / N blocks (1, 2, 4, 8 in the unit
   tier; 1, 4, 16 and 2 in the cluster tier) with a peak of one block more, while the uncapped control grew to every block
   cached (20; 64 = 64 MiB) (parts 1, 3). The disallow branch is what held it there (evictions = puts − limit) and a single
   failed eviction leaves exactly one orphan file until close (unit bypass test) (parts 3, 4). So the key caps the per-stream
   cache disk at `(N + 1) × block size`, softly (one file per failed eviction).

**Conclusion (one line):** unit B2g row 1 — confirmed; cluster B3g row 1 — confirmed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous/selfcheck.py` re-parses the raw files (the surefire output; each sampler CSV and client log / container stdout), not
`readings.tsv`. Output: `run1/selfcheck.txt` (`R/logs/selfcheck.txt`). It flags two client runs (N = 1 r2, r3) because it also
demands P ∈ {63, 64}; every other check holds.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `ifchk-lines.txt`: every `IFCHK,start` shows `streamType=prefetch`, 64 blocks of 1,048,576; the client buffer dir `R/s3abuf`, the container one under `nm-local/…/appcache/…/s3a`; selfcheck confirms the stream class in all 17 runs. |
| 2. Readings | yes | P = 66 re-read in `client-N1-r2.client.log` (`stream_evict_blocks_from_cache=65`, gauge 1, one `IFCHK,readerror,1,1`); N = 1 r3 the same in `ifchk-lines.txt`. |
| 3. Matched row | yes | selfcheck: 300/300 unit rows; cluster end-of-hold = gauge = N for 1/4/16 and container 2, max ≤ N + 1, control 64 = P, 0 after exit, in all runs. |
| 4. Excluded rows | yes | 0 lock-timeout ERRORs in all cluster logs, 3 in the unit output (one per bypass rep); sequential run 0 files; unset = 4. |
| 5. Observed vs. inferred | yes, with the noted deviation | The only prediction that did not hold is B3f's evictions column for 2 of 15 client runs (65 vs 63–64), from the A9 retry; no B3g row uses it, so the matched row stands. |
| 6. Deviations and gaps | yes | listed in 4.2.6; none changes a decisive reading. |
| 7. Core question | yes | ceiling follows the knob (both tiers), control uncapped, disallow branch observed (eviction counters), soft-cap leak observed exactly as B1 states. |

### 5.2 Run 2?

**No** — 2026-11-06. The conclusion rests on observed counts, not inferred statements; both tiers agree; the result confirms the
case without a bypass beyond the one B1 already states; the one prediction miss (evictions in 2 runs) is explained and not
decisive.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** **true positive** (estimate `positive`, effect `caps` in both tiers; a soft
cap — one orphan file per failed eviction — still counts as `caps`).

**Claim tested (B1):** for one S3A prefetching input stream, the number of `fs-cache-*.bin` files in `fs.s3a.buffer.dir` (and
their bytes) never exceeds `maxBlocksCount + 1` blocks and settles at `min(maxBlocksCount, #distinct partially read blocks)`,
scaling with `fs.s3a.prefetch.max.blocks.count`; if the write lock cannot be taken for eviction, files exceed the cap by one per
failed eviction until close. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g row 1 (files = max, peak max + 1, control 20; bypass leak exactly as predicted) | caps | run 1 + self-check | 2026-11-06 |
| Cluster | Confirmed — B3g row 1 (end of hold = N for 1, 4, 16 and container 2; max ≤ N + 1; control 64) | caps | run 1 + self-check | 2026-11-06 |

**Positive control:** not required (positive estimate). The uncapped control (max/N = 1000) grew to every block cached (unit 20,
cluster 64 = 67,108,864 B) with the same workload and instruments.

**Findings beyond the verdict.** (1) An eviction/get race: with a small N two concurrent puts (left block and a cancelled
prefetch at one seek) can evict a block a reader has looked up but not yet read-locked; the read then fails with
`NoSuchFileException` (2 of 3 N = 1 client runs at block 1; A9). It is a read failure, not a cap violation. (2) The prefetched
block is cached on every out-of-order seek (`cancelPrefetches`), so the cache sees all 64 blocks, one more than the left-block
count (A6, observed P = 64).

**Feedback filed:** the case file's section D (D1 amended for A8, A9; D2 verdict) — uncommitted (the parent session commits). Case-file sha256 after the feedback: `4439f62729d6e390c02d365dc46a18cf232c9455cf13699c1820ca4ac2cf78f7` (prediction/conclusion text hashes unchanged: `ea49b2d1…`, `646b6fb9…`).

## 9. What stays on the node

`pc29:/mydata/jingsong-s4/fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount-run1/` (1.4 MB):
`logs/` (unit, cluster, cluster-attempt1..3, selfcheck), `conf/`, `conf-ctr/`, `jar/` (SeekReader), `ds-2.sh`, `ds-1000.sh`.
Removed after the run: the source copy, the distribution copy, the moto venv, the object, NM local/log dirs, temp dirs. No
Hadoop daemon, container, moto server, sampler or test JVM of this run is left (checked: `ps`, `ss`, `jps` after teardown and
after the cleanup). Undo: `rm -rf` that folder.
