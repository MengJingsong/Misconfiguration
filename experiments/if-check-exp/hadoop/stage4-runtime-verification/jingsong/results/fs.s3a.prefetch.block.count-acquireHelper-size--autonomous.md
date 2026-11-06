# fs.s3a.prefetch.block.count-acquireHelper-size--autonomous — stage-4 results  <!-- file: results/fs.s3a.prefetch.block.count-acquireHelper-size--autonomous.md -->

> **Case:** [`fs.s3a.prefetch.block.count-acquireHelper-size--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/fs.s3a.prefetch.block.count-acquireHelper-size--autonomous.md)
>
> **Status:** **verdict filed 2026-11-06** — unit **Not confirmed** (A4 row v, "counter capped, heap not"), cluster **Not confirmed**
> (A9 row iv, "counter capped, heap not"; row vi also met). Claim tested (B1): an S3A prefetching stream over a file larger than one
> block never allocates more than `fs.s3a.prefetch.block.count + 1` prefetch buffers, so its retained prefetch heap is at most
> `(count + 1) × block.size` and grows with `count`. The buffer count followed the knob exactly on both tiers (n + 1 created, never
> more), and the disallow branch fired directly (unit denials at a full pool; real client waiting in `BufferPool.acquire` at a full
> pool). The frozen heap tolerances failed: the unit tier by a first-test heap baseline about 12.5 MiB high; the cluster tier because
> every prefetched block also makes a transient full-block `byte[]` copy (`BufferData.getChecksum`, JDK 8 `CRC32.update(ByteBuffer)`)
> outside the pool. That copy adds one extra 32 MiB array at the `[B` peak for n = 4 and 8, and an OOM at n = 4 under a 256 MiB heap.
>
> **Outcome class:** **undetermined** — stage-3 estimate `positive`; neither tier settled the effect (unit Not confirmed, so the weak-class rule does not apply) ([definition](../../../../stage4-runtime-verification/README.md#outcome-class))
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Layout.** Hadoop, Jingsong's share: this file is in `hadoop/stage4-runtime-verification/jingsong/results/`; the case file is in
`hadoop/stage3-ai-deep-read/jingsong/cases/`; the harness is in `../harness/fs.s3a.prefetch.block.count-acquireHelper-size--autonomous/`;
the protocol is [`../../../../stage4-runtime-verification/README.md`](../../../../stage4-runtime-verification/README.md#the-run-protocol);
the node is described in [`../environment.md`](../environment.md).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, repository HEAD `38acb6bf` plus the uncommitted case file (untracked at audit time). sha256 at filing (queue order 3): `a31a6adfb29b46adadeffb96876a084d83d5cf915b8cc84d02a1f17a484c942b` (checked before the audit). After the audit's amendments A1–A9 (section D1), 2026-11-06 14:19 EST, before any harness run or reading: whole-file sha256 **`8c7ae49646cdb796a2e433df04eb27fabff64b634fac610e6fb74344800acb32`** (frozen version). Frozen text hashes (sha256 of `sed -n` ranges): from `**B2f.` up to `**B2h.` (B2f, B2g, A4) `8d72e7ddcf90cf1eccaee2ea379b0542e58ee62033be0797bfcb22712d24f851`; from `**B3f.` up to `**B3h.` (B3f, B3g, A9) `9d6d42197b66103bc1739a5b60a8f5bcfea3fbb701d81c98a085479393720b6d`; the whole section B (`## B. ` up to `## C. `, includes A7's predictions) `5857f605867ad9b2347bf736e62ccd8694a9490c38c63e04aae321802a0d54ef`. Section D takes the feedback after the run, so the whole-file hash changes then; these text hashes do not. |
| **Harness** | `../harness/fs.s3a.prefetch.block.count-acquireHelper-size--autonomous/` (written after this freeze, before run 1): `TestPrefetchPoolBound.java`, `unit-run.sh` (unit); `cluster-run.py`, `RandomReads.java`, `throttle.py`, `hprof_count.py` (cluster); `instrument-check.sh` + `KnownArrays.java` (known-answer checks); `selfcheck.py` (§5); `hprof_refs.py`, `JfrBigAllocs.java` (diagnostics only, §4.2 part 6). Uncommitted at run time (the parent session commits); md5 in §2. |
| **Later amendments (runbook defects, §3)** | A10 (A7, client class package) → whole-file sha256 `833aabb024714be2cf3e4cc9e4d9b5981ec971c6063844e4ac6a96784906064a`; A11 (A7, progress lines + `jstack` before a timeout kill) → `6b9a4850a89f7cdfced055ae371d5eb75723b1507083f23aa498e60816ce9f9c` (the version the counted cluster tier ran against; the unit tier ran against `8c7ae496…`, and A10/A11 do not touch B2). The B2f–B2h and B3f–B3h text hashes above are unchanged by both (re-computed after each). Section D2 was added after the runs; whole-file sha256 after D2: `b32b1259baf8ac7851d4a06f42ba277ca454b5f8553226999fe14c289492b547` (B2f–B2h and B3f–B3h hashes still `8d72e7dd…` and `9d6d4219…`). |
| **Tiers and values** | Unit (B2): `prefetchBlockCount` ∈ {1, 2, 4, 8, 16}, block 1 MiB, file 64 MiB (fakes), sequential pass with 20 ms per MiB then 100 random 1-byte reads; controls in-memory 512 KiB, CRC, count = 0. Cluster (B3): S3A client JVM (`hadoop fs -cat`), block 32 MiB, 2 GiB object on a local S3-compatible endpoint; n ∈ {1, 4, 8, 16} at `-Xmx1g`; n ∈ {4, 8} at `-Xmx256m -Xmn32m`; `RandomReads` pressure client at n ∈ {1, 8}; controls classic stream (n = 1, 16), 16 MiB object (n = 1, 16), local `file://` baseline. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-06 |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: client heap held by the stream's prefetch `ByteBuffer`s, a count (`createdItems.size()`) with an exact byte size (`block.size` each, `BufferPool.java:102-105`). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b {1, 2, 4, 8, 16} and B3b {1, 4, 8, 16}, both including the default 8 (`Constants.java:1649`). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Unit: `#created` plus GC'd heap (`MemoryMXBean`) — heap made exact in A4 (the fake's 64 MiB contents named). Cluster: live `byte[]` of exactly 32 MiB in a heap dump, `[B` histogram, OOM under a tight heap. Which `byte[]` is the pool's is inferred from the exact length (named in B3d). |
| A. Core question | usage driven to the limit and past it | Partly → Met | Both tiers saturate the pool on the first block (n prefetches + 1 current). Past the limit: the unit random sub-workload was ambiguous (**A2**) and nothing observed the false branch (**A3**); a sequential `-cat` never asks for more than n+1 buffers (the released buffer is reused at `BoundedResourcePool.java:169-172` before the check), so the cluster tier never passed the limit (**A7**: random-read pressure client). |
| A. Core question | positive control (negative estimate) | n/a | Estimate `positive`. |
| B. Logic | each step says what it establishes | Met | B2h/B3h: printed size shows the knob reached the pool; CRC rules out early failure; classic stream attributes the heap to the prefetch pool; small file shows the A3a bypass; local baseline. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met | B2f/B3f exact (`count + 1`, (n+1) × 32 MiB, OOM at n=8/256m), but "≈", "roughly" and "baseline" were undefined, and the gauge column cannot be read (below). **Amended** (A4, A8). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met | B2g/B3g rows gave meanings, not verdicts; missing: *counter capped but the real heap grows*, *disallow never observed*, *tight-heap n=4 fails*, *controls fail*. **Amended** (A4, A9). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Not met → Met | Neither tier observed the false branch of `:176`. **Amended**: unit denials through a block-manager hook (A3); cluster wait samples of `BufferPool.acquire`'s retry loop in a real client (A7). |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: wiring (printed size), reads failing early (CRC / byte count), other heap users (classic control, exact array length), bypass (small file). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3 steps 1–5, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met | B2a/B3a paths and `install`/`package` builds are not needed on the node; MinIO and `pv` are not available; no tool to count arrays in a dump. **Amended** (A1, A5). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | Random sub-workload, heap sample points, run timeouts, control parameters (a 16 MiB file at 40 MiB/s closes before a dump) were missing. **Amended** (A2, A3, A6). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met (after A5) | Test class and scripts are step-1 work. Checked at audit on `pc39`: JDK 8 and 11, Maven, built distribution with `hadoop-aws-3.4.2.jar` and `bundle-2.29.52.jar`; MinIO download answers HTTP 410, so S3Proxy 2.1.0 from Maven Central (sha1 checked) was set up and passed an environment smoke test (1 MB and 200 MB put / cat / md5, objects deleted; no heap reading taken). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly → Met | Unit: 17 × 1 MiB pool, 64 MiB fake file, < 2 GiB surefire heap. Cluster: 2 GiB object ×2 on disk (local copy + S3Proxy store) + dumps ≤ 1 GiB each on `/mydata` (708 GB free); pool ≤ 544 MiB in a 1 GiB heap. As filed, the n=4 run at `-Xmx256m` with ParallelGC could OOM from the generation layout (old ≈ 171 MiB) — **amended** (A6: `-Xmn32m`). ≈ 51 s per 2 GiB read at 40 MiB/s. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `systems/hadoop/source/` (HEAD `38acb6bf`, clean): `BoundedResourcePool.java:60` (size), `:154-158` (toString), `:165-194` (check at `:176`, null at `:191-192`); `BufferPool.java:100-105` (pool, `allocate`, `memoryAllocated`), `:125-141` (`acquire` retry), `:258-274` (`close`, `memoryFreed`); `CachingBlockManager.java:119,128`, `:145-159` (`get`), `:257-268` (`requestPrefetch`, `tryAcquire`, skip); `S3ACachingInputStream.java:84-85` (`count + 1`), `:135-151`, `:159-175`; `PrefetchingInputStreamFactory.java:68-81`; `S3AUtils.java:903-910`; `PrefetchOptions.java:46`; `Constants.java:1642-1649, 1583, 1628`; `S3APrefetchingInputStream.java:111-118`; `S3APrefetchFakes.java:269-285, 367-417`; `MockS3ARemoteObject.java:65-68, 94-96`. All as cited, except R6. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 (A1) | Node paths, no install build, module test command, read surefire counts | Applied 2026-11-06 (uncommitted; frozen sha256 above) | filed paths do not exist on the node; the build returns 0 on test failures |
| R2 (A2, A3) | Exact random sub-workload; observe the operand and the false branch directly (hook, denials); heap sample points; output columns | Applied 2026-11-06 | confirmation needs direct disallow evidence; "100 times" was ambiguous |
| R3 (A4, A9) | Numbers for "≈"/"roughly", a verdict for every row, the missing rows | Applied 2026-11-06 | every plausible outcome needs a row before any reading |
| R4 (A5) | S3Proxy for MinIO, `throttle.py` for `pv`, `hprof_count.py` for MAT/jhat, distribution copy for `package` | Applied 2026-11-06 | MinIO (HTTP 410) and `pv` unavailable; same S3 API and the same client path |
| R5 (A6) | `-Xmn32m` for the tight runs; completion/OOM definitions; 300 s stop; controls exactly | Applied 2026-11-06 | avoids an OOM caused by the generation layout; stop conditions were missing |
| R6 (A8) | The gauge `stream_read_active_memory_in_use` is 0 at close by construction (`BufferPool.close` frees it first): informational only | Applied 2026-11-06 | B3f's gauge column cannot be read as designed |
| R7 (A7) | Random-read pressure client for the cluster tier | Applied 2026-11-06 | a sequential `-cat` never reaches the false branch |
| R8 | B3d cites `S3AInstrumentation.java:1438-1445` for `memoryAllocated/memoryFreed` (as found) but does not mention that the gauge is per stream and returns to 0 at close; the A2 text "Memory bound per stream = (count + 1) × block.size" is right. Mention in the claim that the cap is reached on the first block of every sequential read (the knob sets the demand as well as the limit) | Left for stage 3 | wording, not load-bearing for a run |

**Agreement criteria** — only if run 2 is chosen (see 5.2). Not chosen.


## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-11-06, node clock (UTC−7): unit 12:21–12:22; cluster attempt 1 12:26–12:38 (defect 1), attempt 2 12:41–13:03 (defect 2), **attempt 3 13:04–13:26 (counted)**; diagnostic JFR run 13:27–13:28 (not counted) | not done |
| Node | `pc39` = `node1.jason92-323989.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB; a second Jingsong case ran on the node at the same time (separate folder; this run used port 9000 only) | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` | — |
| JDK (`java -version`) | openjdk `1.8.0_504` (`/usr/lib/jvm/java-8-openjdk-amd64`) for the test, the client JVMs, `jcmd`/`jstack`; JDK 11.0.32 for S3Proxy only | — |
| Build tool | Apache Maven 3.6.3 (unit tier; 3.4.2 artifacts from the node's `~/.m2`, built 2026-11-06 from repository commit `38acb6bf`) | — |
| Local source copy | `/mydata/jingsong-s4/fs.s3a.prefetch.block.count-acquireHelper-size-run1/src`, made by `../copy-source.sh` from `systems/hadoop/source/` at HEAD `38acb6bf` (clean), local tag `rel/release-3.4.2`; only `TestPrefetchPoolBound.java` added | — |
| Cluster distribution | `…-run1/hadoop`: `cp -a` of `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2`; `HADOOP_CONF_DIR=…-run1/conf` (core-site per B3a/A5, `hadoop-env.sh` + `HADOOP_OPTIONAL_TOOLS=hadoop-aws`, JDK 8) | — |
| Object store (environment deviation) | S3Proxy 2.1.0 (`jar-with-dependencies`, Maven Central, sha1 `40f6b0b6…`), filesystem backend `…-run1/s3store`, `127.0.0.1:9000`, JDK 11, `-Xmx1g` — MinIO not obtainable (A5b) | — |
| Case-file version / harness | case file sha256 `8c7ae496…` (unit), `6b9a4850…` (counted cluster attempt; A1–A11) / uncommitted; md5 (first 8): `TestPrefetchPoolBound.java` dc518de8, `unit-run.sh` 7d22f2a1, `cluster-run.py` 1b297a86, `RandomReads.java` 4ec87528, `throttle.py` 744e3133, `hprof_count.py` 4529cbda, `instrument-check.sh` 9199309a, `KnownArrays.java` 8eef4da9, `selfcheck.py` 35c1b5f5, `hprof_refs.py` e43ee12d, `JfrBigAllocs.java` 766e7bbc | — |
| Instrument checks (before the counted runs) | `instrument-check.sh`: a JVM holding 3 × `byte[33554432]` → `hprof_count.py` `len33554432=3`, `jcmd GC.class_histogram` `[B` line parsed (100694296 B); `throttle.py 20` on 50 MiB → 2.5 s. Unit: `--compile-only` BUILD SUCCESS. S3Proxy smoke test (1 MB and 200 MB put/cat, md5 equal). Fixed class after A10: `hadoop ifchk.RandomReads` with no args → loads (`ArrayIndexOutOfBoundsException: 0`) | — |
| Storage | `/mydata` (local disk `/dev/mapper/emulab-node1--bs`); nothing on `/proj` except this repository's text files | — |
| Full logs (path, outside the repo) | `/mydata/jingsong-s4/fs.s3a.prefetch.block.count-acquireHelper-size-run1/`: `logs/unit/` (surefire reports, `unit-run.log`), `logs/cluster/` + `out/` (counted attempt 3), `logs/cluster-attempt{1,2}/` + `out-attempt{1,2}/`, `logs/diag/` (JFR summary, OOM-dump reference lists), `logs/selfcheck.txt` | — |

Excerpts in the repository: `fs.s3a.prefetch.block.count-acquireHelper-size--autonomous/run1/` (`unit/`, `cluster/`, `diag/`, `selfcheck.txt`).

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | 1, cluster attempt 1 | A7 (`hadoop RandomReads …`) | The `hadoop` script rejects a class name without a dot (`hadoop_validate_classname`, `libexec/hadoop-functions.sh:1107-1119`) and printed its usage; both pressure runs had no reading (`out-attempt1/rr-n*.out`). | A10: class `ifchk.RandomReads`. B1, B3f, B3g and A7's prediction unchanged; cluster tier restarted from its beginning. | Amendment, 2026-11-06 | uncommitted; sha256 `833aabb0…` |
| 2 | 1, cluster attempt 2 | A7 / A6c (300 s stop) | Both `RandomReads` runs did not finish within 300 s and were killed; the client printed its readings only on a normal exit, so a killed run left none (`out-attempt2/rr-n*.out` hold only the chain line). | A11: a flushed progress line every 1 s; `jstack` saved before any timeout kill. B1, B3f, B3g and A7's prediction unchanged; cluster tier restarted from its beginning. | Amendment, 2026-11-06 | uncommitted; sha256 `6b9a4850…` |

Readings of the discarded attempts existed when A10 and A11 were written (attempt 1: the sequential, control and tight runs; attempt 2: the same plus the stall of `RandomReads`). Neither fix depends on a value: A10 is the shell's class-name rule, and A11 only keeps the readings that a timeout would otherwise lose. Neither changes a prediction or conclusions row. The counted cluster readings are attempt 3's. Attempts 1 and 2 gave the same sequential/control/tight readings within a few kB (`out-attempt*/`), including the extra 32 MiB array at n = 4 or 8 and the n = 4 OOM hang.

## 4. Run 1

**Scope:** unit tier, all counts and controls, once; cluster tier, all 13 runs of B3e/A6/A7, once (attempt 3). **Command logs:**
`fs.s3a.prefetch.block.count-acquireHelper-size--autonomous/run1/unit/unit-run-excerpt.log`, `…/run1/cluster/cluster-run-key-lines.txt`
(full: `/mydata/…-run1/logs/unit/unit-run.log`, `/mydata/…-run1/logs/cluster/cluster-run.log`).

### 4.1 Readings

**Unit tier** (`run1/unit/ifchk.csv`; surefire 6 run, 0 failures, 0 errors, `run1/unit/surefire-summary.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| printed `size` / pool `size` field, c = 1, 2, 4, 8, 16 | 2/2, 3/3, 5/5, 9/9, 17/17 (= c + 1) | `run1/unit/ifchk.csv` |
| max `#created` sequential / random / hook | c+1 / c+1 / c+1 for every c; never above `size` | same |
| denials sequential / random / at a full pool | c=1: 0 / **38** / 38; c ≥ 2: 0 / 0 / 0 | same |
| CRC of the sequential pass; random mismatches | 2552085854 for all c; 0 | same |
| heap before / at 32 MiB / after close (MiB) | c=1 **15.20** / 71.29 / 66.92; c=2 2.71 / 69.81 / 66.90; c=4 2.71 / 72.50 / 66.90; c=8 2.71 / 77.28 / 66.90; c=16 2.71 / 84.61 / 66.90 | same |
| `Δ(c) − Δ(1) − (c − 1)` (MiB; frozen tolerance ≤ +4) | c=2 **+10.01**, c=4 **+10.70**, c=8 **+11.48**, c=16 **+10.80** | `run1/selfcheck.txt` |
| `heapPeak − heapAfter` vs `(c+1) − 4` MiB | 4.38, 2.91, 5.60, 10.38, 17.71 — all above the bound | same |
| controls | in-memory 512 KiB: 524288 bytes, no `#created` in `toString`; count 0 rejected by `PrefetchOptions` and `S3AUtils.intOption` | `run1/unit/ifchk.csv` |

**Cluster tier** — attempt 3. `[B` = `jcmd GC.class_histogram` (live) every ~2.4 s; rise = max `[B` − 4699120 B (classic n=1 max); arrays = live dump at ~12 s.

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| n=1, 1g | seq | 32 MiB arrays / `[B` rise / bytes | **2** / 60.2 MiB (pred 64 ± 16) / 2147483648, exit 0 0 | `run1/cluster/seq-n1.tsv`, `run1/selfcheck.txt` |
| n=4, 1g | seq | same | **5** / **188.2 MiB** (pred 160 ± 16; one sample at 9.5 s holds a 6th 32 MiB array, else ~156) / all bytes | `run1/cluster/seq-n4.tsv` |
| n=8, 1g | seq | same | **9** / **316.3 MiB** (pred 288 ± 16; samples at 22.3 and 39.1 s hold a 10th array, else ~284) / all bytes | `run1/cluster/seq-n8.tsv` |
| n=16, 1g | seq | same | **17** / 540.4 MiB (pred 544 ± 16) / all bytes | `run1/cluster/seq-n16.tsv` |
| n=1, 16, 1g | classic control | arrays / `[B` max | 0 and 0 / 4.48 and 4.48 MiB (difference −1.7 kB) / all bytes | `run1/cluster/classic-n*.tsv` |
| — | local `file://` baseline | `[B` max | 1.21 MiB, all bytes | `run1/cluster/local.tsv` |
| n=1, 16 | small 16 MiB object | 16 MiB / 32 MiB arrays | 1 / 0 for both n (A3a bypass as predicted) | `run1/selfcheck.txt` |
| n=4, `-Xmx256m -Xmn32m` | tight | outcome | **did not complete**: OOM inside a prefetch thread at start (HeapDumpOnOutOfMemoryError dump: 6 × 32 MiB, 5 reachable pool buffers + 1 unreachable), then the reader waited in `CachingBlockManager.get` until the 300 s stop; no OOM text in stderr (the JVM prints it to stdout, i.e. into the pipe) | `run1/cluster/tight-n4.tsv`, `run1/cluster/jstack-main.txt`, `run1/diag/oom-tight-n4-refs.txt` |
| n=8, `-Xmx256m -Xmn32m` | tight | outcome | **OOM** `java.lang.OutOfMemoryError: Java heap space` in stderr at `HeapByteBuffer.<init>` after 33554650 bytes; exit 1 | `run1/cluster/err-excerpts.txt`, `run1/diag/oom-tight-n8-refs.txt` |
| n=1, 1g | `RandomReads` | size / maxCreated / wait samples / created at wait | 2 / **2** / **237838** / 2; 23 of 100 iterations in 300 s, 0 mismatches; killed at the stop; main thread in `Retryer.continueRetry` ← `BufferPool.acquire:141` | `run1/cluster/rr-n1.out`, `run1/cluster/jstack-main.txt` |
| n=8, 1g | `RandomReads` | same | 9 / **9** / **716** / 9; 21 of 100 iterations, 0 mismatches; killed at the stop; main thread in `CachingBlockManager.get:167` with the log `pool: size = 9, #created = 9`, buffers stuck in CACHING | `run1/cluster/rr-n8.out`, `run1/cluster/err-excerpts.txt` |
| n=1, 8 | `RandomReads` `[B` max − base | 94.2 MiB (A7 bound 80) / 286.3 MiB (bound 304) | `run1/cluster/rr-n*.tsv` |
| all | gauge `stream_read_active_memory_in_use` | not printed in any stderr (A8a: informational) | `run1/selfcheck.txt` |

**Diagnostic (not counted, after the run):** one more seq n=8 run with JFR allocation events. Of the 73 `byte[]` allocations of
≥ 16 MiB, 9 are the pool (`BufferPool$1.createNew:103`) and 64 (one per block) are 33554448-byte temporaries made by
`CRC32.update` ← `BufferData.getChecksum:166` ← `BufferData.setReady:215` ← `CachingBlockManager.readBlock:373`, in the prefetch
threads (`run1/diag/jfr-seq-n8-big-allocs.txt`). On JDK 8, `CRC32.update(ByteBuffer)` on a buffer without an accessible array (the
read-only duplicate made at `BufferData.java:213`) copies the whole remaining buffer into a new `byte[]`.

### 4.2 Conclusion and logic

1. **Validity** — Unit: valid; 6/6 tests passed, every printed `size` = c + 1, CRC equal, no mismatches, count 0 rejected [observed: `run1/unit/ifchk.csv`, `run1/unit/surefire-summary.txt`]. Cluster: valid; every 1g sequential and control read delivered 2147483648 bytes [observed: `run1/selfcheck.txt`]; the stream chain is `S3APrefetchingInputStream > S3ACachingInputStream > S3ACachingBlockManager` with `type=prefetch`, `blockSize=32M` [observed: `run1/cluster/rr-n1.out`]; the classic control has no 32 MiB array and the same `[B` at n=1 and 16 [observed: `run1/cluster/classic-n*.tsv`]. The pool was saturated at every n (n + 1 arrays).
2. **Readings** — (a) Unit c=1 `heapBefore` is 15.20 MiB against 2.71 MiB for every other count; c=1 ran first after the control test in the same JVM. From c=2 on the peaks follow `c` (peak(c) − peak(2) = 2.69, 7.47, 14.80 MiB against 2, 6, 14) [observed: `run1/unit/ifchk.csv`]. (b) Cluster n=4 and n=8 have one to two histogram samples holding one extra 32 MiB array; the n=1 and n=16 runs have none [observed: `run1/cluster/seq-n*.tsv`]. (c) Both `RandomReads` runs stalled: 21–23 of 100 iterations in 300 s [observed: `run1/cluster/rr-n*.out`].
3. **Matched row** — Unit, A4 row (v) "Not confirmed (counter capped, heap not) — `Δ(c) − Δ(1) > (c − 1) MiB + 4 MiB` for some count": +10.0 to +11.5 MiB for c = 2, 4, 8, 16, with `#created` capped at c + 1 [observed: `run1/selfcheck.txt`]. Cluster, A9 row (iv) "Not confirmed (counter capped, heap not) — n+1 arrays but a `[B` rise above `(n+1) × 32 MiB + 16 MiB` at some n": n=4 188.2 > 176, n=8 316.3 > 304, with exactly 5 and 9 arrays in the dumps [observed: `run1/selfcheck.txt`]. Row (vi) (tight heap) also holds: n=4 at 256 MiB did not complete.
4. **Excluded rows** — Unit: (i) invalid — tests pass, CRC equal, sizes c+1, count 0 rejected [observed]; (ii) refuted — no `#created` > size, and max `#created` differs across counts (2…17) [observed]; (iii) not saturated — max = c+1 for all [observed]; (iv) disallow never observed — 38 denials at c=1, all at a full pool [observed]; (vi) Confirmed — excluded by (v). Cluster: (i) invalid — classic 0 arrays, `[B` difference 1.7 kB, all bytes delivered, 0 mismatches [observed]; (ii) refuted — no dump with more than n+1 arrays (the 10 s live dumps; the OOM dumps, which are not the A8c instrument, hold 5 reachable pool buffers + 1 unreachable array for n=4 and 6 reachable for n=8 ≤ 9), `maxCreated` ≤ size in both `RandomReads` runs, and arrays/rise differ between n=1 and 16 (2 vs 17) [observed: `run1/diag/oom-tight-n*-refs.txt`, `run1/cluster/rr-n*.out`]; (iii) not saturated — n+1 arrays at every n [observed]; (v) disallow never observed — 237838 and 716 wait samples [observed]; (vii) Confirmed — excluded by (iv) and (vi).
5. **Observed vs. inferred** — (a) That the unit row (v) comes from a contaminated `heapBefore` of the first count, not from extra heap held by the stream [inferred: only c=1's baseline differs (15.20 vs 2.71 MiB); the peaks of c ≥ 2 follow c within 1.5 MiB; c=1's peak is 1.5 MiB above c=2's]. (b) That the cluster's extra 32 MiB array is the transient checksum copy [observed in the diagnostic JFR run (64 per-block allocations of 33554448 B in `BufferData.getChecksum`) and in the OOM dump (the 6th array unreachable); inferred for the counted histogram samples themselves, which carry no stacks]. (c) That the tight n=4 failure is the same copy [inferred: pool 5 × 32 = 160 MiB plus one 32 MiB temporary per prefetch in flight exceeds the 224 MiB old generation once two copies coincide; the OOM dump shows 6 arrays].
6. **Deviations and gaps** — S3Proxy instead of MinIO, `throttle.py` instead of `pv` (A5); live dumps taken at 11.9–12.3 s (sequential/classic) and 7.2 s (small) instead of 10 s and 5 s (the 2-s sampling loop) — stream open and pool saturated in all; `RandomReads` killed at the stop, its reading is the last progress line (A11); the n=4 tight run's OOM text went to stdout (the data pipe), so A6b's "OOM in stderr" is seen only through the HeapDumpOnOutOfMemoryError file; the gauge printed nothing (A8a, informational); the per-stream scope (B3h 4) is not exercised; the JFR run is a diagnostic outside the frozen design.
7. **Core question** — Does the check cap usage, and does usage follow the knob? The pool part does, exactly: the number of prefetch buffers ever created was n + 1 for every n on both tiers and never more (parts 3, 4). When demand exceeded the pool, the disallow branch fired: unit denials at a full pool, and a real client waiting in `BufferPool.acquire`'s retry loop at a full pool (part 4). But the stream's heap is not bounded by `(n + 1) × block.size` as the claim states. On JDK 8 each prefetched block also allocates a transient block-sized checksum copy outside the pool (part 5b). That pushed the cluster `[B` peak one block above the frozen tolerance at n = 4 and 8, and made the n = 4 run fail under a heap that holds the pool. The unit tier's heap tolerance failed for a baseline reason (part 5a). Under the frozen rows neither tier confirms the claim.

**Conclusion (one line):** Unit: A4 row (v) — not confirmed. Cluster: A9 row (iv) (and vi) — not confirmed.

## 5. Self-check of run 1 — AI

`../harness/<stem>/selfcheck.py` re-parses the raw files (the surefire `-output.txt` and report, not `ifchk.csv`; the per-run TSVs, throttle and status files, stderr, the cluster log's dump counts, `RandomReads` output and `jstack`, and the OOM dumps through `hprof_count.py`). It evaluates the frozen rows in order; output in `run1/selfcheck.txt`: unit → (v), cluster → (iv), no JVM of the run left.

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt`: surefire 6/0/0; CRC single value; sizes c+1; 1g reads `bytes=2147483648` with `PIPESTATUS=0 0`; classic 0 arrays |
| 2. Readings | yes | `ifchk.csv` heapBefore 15939800 vs 2838552…2845488 B; `seq-n4.tsv` 9.5 s = 202037712 B, `seq-n8.tsv` 22.3/39.1 s = 336355952/336… B; `rr-n*.out` last progress lines 23 and 21 iterations |
| 3. Matched row | yes | excess +10.01…+11.48 MiB (unit); rise − upper bound +12.2 (n=4), +12.3 (n=8) MiB (cluster); rows taken in the frozen order |
| 4. Excluded rows | yes | each excluded row's condition re-evaluated by `selfcheck.py` (flags in `selfcheck.txt`); OOM-dump references re-read in `diag/oom-tight-n*-refs.txt` |
| 5. Observed vs. inferred | yes | (a) and (c) are explanations, not used to choose the row; (b) supported by the JFR stacks and the unreachable array; the rows matched rest on observed numbers only |
| 6. Deviations and gaps | yes | none changes the pool path; the dump-time shift keeps every dump inside an open, saturated stream (`cluster-run-key-lines.txt`) |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1's refuted-if (`#created` > bound) not met; confirmation needs the heap relation too, which failed on both tiers, so "not confirmed" and not "confirmed" |

### 5.2 Run 2?

**No** — decided 2026-11-06 (the brief for this session: run 1 only). A run 2 by the same runbook would hit the same unit baseline effect (same test order in one JVM) and the same JDK 8 checksum copy. What would settle the case is an amended design (a heap baseline after a warm-up or one JVM per count; a cluster tolerance that counts in-flight checksum copies, or a JDK whose `CRC32.update(ByteBuffer)` does not copy whole buffers). Under the protocol that is a new audit before a new run, recommended to stage 3 (§8).

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** **undetermined** — neither tier settled the effect: unit Not confirmed (so no weak class), cluster Not confirmed.

**Claim tested:** for an S3A prefetching stream over a file larger than one block, the number of prefetch `ByteBuffer`s ever allocated never exceeds `fs.s3a.prefetch.block.count + 1`, so the stream's retained prefetch heap is at most `(count + 1) × fs.s3a.prefetch.block.size` and grows with `count` (B1).
"Confirmed" below always means this claim held.

| Tier | Verdict (B2g / B3g row, as amended A4 / A9) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Not confirmed** — A4 row (v), counter capped, heap not: `#created` = c+1 for c ∈ {1,2,4,8,16}, never more, 38 denials at a full pool (c=1); `Δ(c) − Δ(1)` exceeded `(c−1) + 4` MiB by 6–7.5 MiB because c=1's heap baseline was 12.5 MiB higher | undetermined | run 1 + self-check | 2026-11-06 |
| Cluster | **Not confirmed** — A9 row (iv) (and vi), counter capped, heap not: live dumps 2/5/9/17 arrays of 32 MiB for n = 1/4/8/16; wait samples at a full pool (n=1: 237838, n=8: 716); `[B` rise 188.2 and 316.3 MiB at n=4 and 8 (bound 176, 304) from a transient per-block checksum copy; n=4 at 256 MiB failed (OOM + stall), n=8 OOM | undetermined | run 1 + self-check | 2026-11-06 |

**Positive control:** not required (estimate positive). The classic-stream control and the small-file control behaved as predicted.

**Findings for stage 3 (not re-estimated; section D2 of the case file):** (1) The check caps the pool exactly. The *count* of retained buffers is n + 1 and the disallow branch fires under pressure, but on JDK 8 every block that becomes READY also allocates one transient block-sized `byte[]` (`BufferData.setReady:215` → `getChecksum:161-166`, `CRC32.update` of a read-only duplicate). Transient heap per stream is therefore up to `(n + 1 + prefetches in flight) × block.size`, outside the check; an OOM in a prefetch thread leaves the block in PREFETCHING and the reader waits (here until killed). (2) Random reads with caching stalled the real client at n = 1 and n = 8 (buffers stuck in CACHING, reader retrying for up to `bufferPoolSize × 120 s`), a liveness issue of the bounded pool. (3) B3d's gauge cannot be read at close (A8a).

**Feedback filed:** the case file's section D2 "Stage-4 result" (2026-11-06, uncommitted); amendments A1–A9 (audit, before any reading) and A10–A11 (runbook defects) in the sections they change and in D1. `_INDEX.md` and `queue.csv` not edited (the parent session files them).

**Left on the node `pc39`:** `/mydata/jingsong-s4/fs.s3a.prefetch.block.count-acquireHelper-size-run1/` (1.5 GB: `src/` with `target/`, `hadoop/` distribution copy, `conf/`, `tools/` (S3Proxy jar + config), `logs/`, `out*/`, empty `s3a-buf/`, `tmp/`, `classes/`). The 2 GiB data, the S3Proxy store and all heap dumps were deleted. No Hadoop client, S3Proxy, surefire or other JVM of this run is running; port 9000 is free. Undo: `rm -rf /mydata/jingsong-s4/fs.s3a.prefetch.block.count-acquireHelper-size-run1`.
