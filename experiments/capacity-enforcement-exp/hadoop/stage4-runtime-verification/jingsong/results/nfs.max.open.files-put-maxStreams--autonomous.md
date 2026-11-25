# nfs.max.open.files-put-maxStreams--autonomous — stage-4 results  <!-- file: results/nfs.max.open.files-put-maxStreams--autonomous.md -->

> **Case:** [`nfs.max.open.files-put-maxStreams--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/nfs.max.open.files-put-maxStreams--autonomous.md) (queue order 18; check `OpenFileCtxCache.java:124`, `if (size() == this.maxStreams)` in `OpenFileCtxCache.put`)
>
> **Status:** verdict filed (run 1 + self-check; no run 2) — 2026-11-25
>
> **Outcome class:** **true positive** — estimate `positive`, effect `caps` in both tiers.
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); the feedback section is D.

Drafted outside the repository (`~/writeup-hadoop/out/o18/`); paths below marked `run1/…` are relative to that folder
(full copy of the node's `logs/` folder, 6 MB). Harness: `~/writeup-hadoop/out/o18/harness/`. Amended case file:
`~/writeup-hadoop/out/o18/case-amended.md`. Nothing was committed (no commit asked for).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository file at commit `bef6bc8a` (sha256 `cc391e66…d8ff8b`, as in `_INDEX.md` §4). After the audit's six dated amendments (2026-11-25), frozen before any reading: sha256 **`ae633d7aaec213ac91b4a50fdaab36b74c6aff62e98aef1fe77b7dfeece0cb97`** (`run1/frozen-sha256.txt`). The two runbook-defect fixes of §3 (no change to B2f/B2g/B3f/B3g) were added before the affected tiers restarted; file before section D: sha256 `f551e47e2adcc7ac171d8f2333b971478a1dcead011dc78a305079b7437698f8`. Section D was filled after the run and is not part of the frozen version. |
| **Harness** | `harness/nfs.max.open.files-put-maxStreams--autonomous/`: `TestMaxOpenFilesMemory.java` (unit), `unit-run.sh`, `NfsStreamLoad.java` (cluster load client), `NfsLauncher.java` (Option C gateway launcher, `s4.NfsLauncher`), `cluster-run.sh`, `driver.sh`, `analyze.py` — staged at `~/writeup-hadoop/out/o18/harness/`, not committed. Checks before run 1: `mvn -o test-compile` of the unit test (`run1/logs/instrument-check-test-compile.log`, exit 0) and `javac` of the client and launcher (`run1/logs/cluster-run-attempt1.log`, `=== compile`). |
| **Tiers and values** | Unit and cluster, each: K = 8, 32, 128, default (key unset → 256) with M = 64 files and a 983 040 B out-of-order write per file; plus K = 8 with a 1-byte write (overhead control). |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Met | A2/B1: a count of cached write streams, each a heap bundle (`DFSOutputStream` + streamer thread + pending `WriteCtx` payload); bytes derived as min(K, M) × 983 040 |
| A | knob varied, ≥ 3 values incl. default | Partly → Met after amendment 2 | B2b/B3b: 8 / 32 / 128, default 256 missing; added as a key-unset arm |
| A | real resource measured, not only the counter | Met | B2d heap after GC + pending bytes; B3d heap after GC, `[B` histogram, RSS, `listOpenFiles` |
| A | usage driven to the limit and past it | Met (default not driven to its limit) | M = 64 > K = 8, 32; the default 256 is a non-binding arm, like K = 128 (left for stage 3) |
| B | each step says what it establishes | Met | B2g/B3g rows, B2h/B3h controls |
| B | prediction in numbers | Met | B2f/B3f per-K counts and byte ranges |
| B | every plausible outcome has a row | Met | over-cap, memory-outside-cache, flat (control not moving), dump, early reaping rows present |
| B | confirmation needs ceiling-follows-knob and disallow evidence | Met (strengthened) | JUKEBOX and `Can't add …` lines; unit tier now decodes each WRITE reply (amendment 3) |
| B | alternative explanations and controls | Met | K = 128 no-cap control; 1-byte control; dump-file check; fresh cluster per K |
| C | a human can follow it | Met | B1 + B2f/B3f |
| C | an AI can run it without re-deriving the path | Partly | `-DargLine` ineffective; `start-dfs.sh` unusable on the nodes; Option C command — amendments 1, 5; defect 4 |
| C | values, commands, observables exact | Partly | thread-name observable wrong (defect 3, found in the run) |
| D | harness and environment prerequisites | Met | harness listed as work; node `pc75` has the 2026-11-24 build |
| D | workload arithmetic reaches the limit | Met | ≤ 60 MiB payload in a 1 GiB heap; < 100 MB disk |
| D | load-bearing citations spot-checked | Met | `OpenFileCtxCache.java:52-55,69-116,118-145`; `WriteManager.java:140-200`; `RpcProgramNfs3.java:843-917,993-1021`; `OpenFileCtx.java:206-208,562-573,642-682` (out-of-order UNSTABLE writes answered at once); `Nfs3Utils.java:140-145`; `Nfs3.java:39-58`; `XDR`/`CredentialsSys`/`RpcReply` APIs. `DataStreamer.java:664,680` cite the thread's *naming*, not its creation (defect 3) |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: `copy-source.sh`, no `-am install`, `mvn -o`, heap via `-Dmaven-surefire-plugin.argLine` | Applied, amendment 2026-11-25 (B2a) | `hadoop-project/pom.xml:2469` binds surefire `<argLine>`; no change to B2f |
| 2 | Add the default (key unset → 256) arm and make the 1-byte control a fixed arm, both tiers | Applied, amendments 2026-11-25 (B2b, B2f, B3b) with predictions | audit group A (default value) |
| 3 | B2d: decode each WRITE reply through an `EmbeddedChannel`; count log lines with an appender; heap before phase 1 too | Applied, amendment 2026-11-25 (B2d) | direct disallow evidence; instrument only |
| 4 | B3a/B3e: copy the node's built dist, `hdfs --daemon`, Option C (host rpcbind untouched), heap from `GC.heap_info` | Applied, amendment 2026-11-25 (B3a) | runbook would not run as written; B3f/B3g unchanged |
| 5 | Stage 3: drive the default (256) past its limit (M > 256) if the default's own behaviour matters | Left for stage 3 | not needed for the core question |
| 6 | Stage 3: correct A2's streamer-thread citation (see defect 3); state the heap ratio with the fixed offset | Left for stage 3 (section D) | wording only |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25, 04:40–05:06 MST (node clock); node lock held 04:40:44–05:06 |
| Node | `pc75` (`node3.jason92-326665`, CloudLab UMass, 40 cores, 125 GiB RAM) |
| OS / kernel | Ubuntu 22.04.2 LTS / `5.15.0-203-generic` |
| JDK | OpenJDK `1.8.0_514` (`/usr/lib/jvm/java-8-openjdk-amd64`); Maven 3.6.3 (`run1/logs/unit-run.log`) |
| Local source copy | `copy-source.sh` from `systems/hadoop/source/` at repository commit `cd9e1cde` → `/mydata/jingsong-s4/nfs.max.open.files-put-maxStreams-run1/src` (`rel/release-3.4.2`; `run1/logs/copy-source.log`) |
| Distribution (cluster) | copy of `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` (node build of 2026-11-24) |
| Case-file commit / harness | `bef6bc8a` + amendments (sha256 above) / not committed |
| Storage | `/mydata` (local disk); NN/DN/dump dirs under the run folder |
| Gateway start | **Option C**: `hadoop --config <conf> s4.NfsLauncher`, `HADOOP_CLIENT_OPTS="-Xms1g -Xmx1g"` (ParallelGC), no portmapper registration; system `rpcbind` untouched (`active`, only portmapper registered, checked after the run) |
| Full logs | node folder deleted except `logs/` and `harness/` (6 MB); full copy at `~/writeup-hadoop/out/o18/run1/logs/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Commit |
|---|---|---|---|---|---|---|
| 1 | audit | B2a | `-DargLine` is overridden by `<argLine>${maven-surefire-plugin.argLine}</argLine>`; `-am install` unnecessary | `-Dmaven-surefire-plugin.argLine=-Xmx1g`, `mvn -o` | amendment 2026-11-25, before run 1 | not committed |
| 2 | audit | B3a/B3e | `start-dfs.sh` needs ssh to localhost (unavailable); Option C picked so the host's rpcbind is not touched | `hdfs --daemon start …`; launcher | amendment 2026-11-25, before run 1 | not committed |
| 3 | unit run 1, attempts 1–2 | B2d (d), also B3d | Thread-name prefix `DataStreamer for file /.reserved/.inodes/` counted **0** at every K (attempt 1, `run1/logs/unit-attempt1/readings.txt`); a diagnostic in attempt 2 found no thread named `DataStreamer…` at all (`run1/logs/unit-attempt2/readings.txt`, `STREAMERS … =0`). Cause: the name is set only in `initDataStreaming()`/`endBlock()` (`DataStreamer.java:663-665,678-680`), once a block pipeline exists; these streams never send a packet, so their threads keep `Thread-N` names (confirmed in the cluster: `run1/logs/cluster/arm-K8/jstack-s45.txt`, `"Thread-33" … at org.apache.hadoop.hdfs.DataStreamer.run(DataStreamer.java:717)`) | unit: count live threads of class `org.apache.hadoop.hdfs.DataStreamer`; cluster: count `jstack` threads in `DataStreamer.run(` plus `DataStreamer` instances in the histogram | fix dated 2026-11-25 in B2d and B3d; **unit tier restarted from its beginning** (attempt 3 is run 1's evidence); the cluster tier had not started | not committed |
| 4 | cluster run 1, attempt 1 | B3a Option C | `hadoop --config <dir> NfsLauncher` → usage text: `hadoop_validate_classname` refuses a class without a package (`run1/logs/cluster-run-attempt1.log`, `STOP: gateway did not start`); no reading taken | launcher moved to package `s4` | fix dated 2026-11-25 in B3a; **cluster tier restarted from its beginning** (fresh format) | not committed |

Attempts 1–2 of the unit tier read the same values as attempt 3 for every other observable (`run1/logs/unit-attempt1/readings.txt`); they are not used as evidence.

## 4. Run 1

**Scope:** both tiers, all five arms. **Command logs:** `run1/logs/unit-run.log` (unit, attempt 3), `run1/logs/cluster-run.log` (cluster, attempt 2), `run1/logs/driver.out`.

### 4.1 Readings

**Unit tier** (`run1/logs/unit/readings.txt`; `run1/logs/unit/mvn-unit.log`: `Tests run: 5, Failures: 0, Errors: 0`). Phase 1 took 1.4–1.9 s, phase 2 0.2–0.5 s (under the 10 s eviction threshold).

| Arm | `Maximum open streams` (log) | max `size()` | cached after phase 2 | `Can't add more` / `Can't add new` | WRITE OK / JUKEBOX | pending bytes | DataStreamer threads (after 1 / after 2) | heap delta phase 2 (MiB) | dump files | evictions |
|---|---|---|---|---|---|---|---|---|---|---|
| K = 8 | 8 | 8 | 8 | 56 / 56 | 8 / 56 | 7 864 320 | 8 / 8 | 9.94 | 0 | 0 |
| K = 32 | 32 | 32 | 32 | 32 / 32 | 32 / 32 | 31 457 280 | 32 / 32 | 30.07 | 0 | 0 |
| K = 128 | 128 | 64 | 64 | 0 / 0 | 64 / 0 | 62 914 560 | 64 / 64 | 60.14 | 0 | 0 |
| default | 256 | 64 | 64 | 0 / 0 | 64 / 0 | 62 914 560 | 64 / 64 | 60.06 | 0 | 0 |
| K = 8, 1 B | 8 | 8 | 8 | 56 / 56 | 8 / 56 | 8 | 8 / 8 | 0.71 | 0 | 0 |

**Cluster tier** (`run1/logs/cluster/arm-*/samples.txt`, `client.txt`, `logcounts.txt`; table from `run1/cluster-analyze.txt`). Gateway log line per arm `Maximum open streams is 8 / 32 / 128 / 256 / 8` (`arm-*/gateway.log`; the default arm's `hdfs-site.xml` has no `nfs.max.open.files`). Client phase 1: 1.7–2.3 s. All creates returned 0. Readings at +15 s, +45 s, +90 s were identical in counts; heap shown at +45 s (range over the three samples in brackets).

| Arm | OpenFileCtx / WriteCtx / DFSOutputStream / DataStreamer objects | DataStreamer threads (`DataStreamer.run`) | `listOpenFiles` | client write 0 / 10008 | `Can't add new` / `Can't add more` / `Evict` | heap-after-GC delta vs baseline (MiB) | `[B` delta (MiB) | dump files | RSS (MiB, base → +45 s) |
|---|---|---|---|---|---|---|---|---|---|
| K = 8 | 8 / 8 / 8 / 8 | 8 | 8 | 8 / 56 | 56 / 56 / 0 | +8.73 (8.13–8.73) | +7.63 | 0 | 437 → 456 |
| K = 32 | 32 / 32 / 32 / 32 | 32 | 32 | 32 / 32 | 32 / 32 / 0 | +31.23 (30.84–31.72) | +30.24 | 0 | 448 → 512 |
| K = 128 | 64 / 64 / 64 / 64 | 64 | 64 | 64 / 0 | 0 / 0 / 0 | +60.42 (60.42–60.84) | +60.39 | 0 | 449 → 555 |
| default | 64 / 64 / 64 / 64 | 64 | 64 | 64 / 0 | 0 / 0 / 0 | +61.16 (60.75–61.16) | +60.39 | 0 | 451 → 550 |
| K = 8, 1 B | 8 / 8 / 8 / 8 | 8 | 8 | 8 / 56 | 56 / 56 / 0 | +1.45 (0.63–1.46) | +0.13 | 0 | 449 → 460 |

The named-thread count (`"DataStreamer for file`) was 0 in every sample, as defect 3 explains (`samples.txt`, `namedStreamers=0`). In K = 32 the 32 accepted writes are files 0–31, the first 32 creates (`arm-K32/client.txt`). No exception in any gateway log.

### 4.2 Conclusion and logic

1. **Validity** — Valid in both tiers. The cap was reached and passed: M = 64 opens against K = 8 and 32 [observed: `unit/readings.txt` `createOk=64`; `cluster/arm-K8/client.txt` `createOk=64`]. Held fixed: `nfs.stream.timeout = 600000` [observed: `cluster/arm-*/hdfs-site.xml`; unit test source], phase 1 well under 10 s [observed: `phase1Sec` 1.4–1.9, `phase1Ms` 1656–2321], no data dumped [observed: `dumpFiles=0` everywhere], fixed 1 GiB gateway heap [observed: `heapinfo-*.txt` totals 305664K+699392K], each K confirmed by its log line [observed: `logMaxStreams`, `gateway.log`].
2. **Readings** — No outlier among counts: every count equals min(K, 64) exactly, in every sample. The heap deltas are each inside the B2f/B3f ranges but the K = 128 / K = 8 heap ratio is 6.05× (unit) and 6.92× (cluster), below the "~8×" of B2g/B3g, while pending bytes and the `[B` delta are 8.0× and 7.9× [observed: tables above]. The difference is a fixed offset: the cluster heap delta is linear in min(K, 64) with slope ≈ 0.91 MiB per stream and intercept ≈ 2 MiB (31.23 at 32, 60.42 at 64) [inferred: arithmetic on `cluster-analyze.txt`]; in the unit tier the K = 8 arm (the first method in the JVM) carries ≈ 2.4 MiB above the 30.07/60.14 line [inferred: same arithmetic on `unit/readings.txt`].
3. **Matched row** — B2g: "max `size()` = min(K, M); pending bytes and heap delta scale with min(K, M); K = 128 shows ~8× the K = 8 delta" → max `size()` 8/32/64/64; pending bytes 8×/4×/1×; heap delta 9.94 → 30.07 → 60.14 MiB, within 6–12 / 25–40 / 50–75 MiB [observed: `unit/readings.txt`]. B3g: "Instances, threads and open files = min(K, 64); heap delta scales with min(K, 64); K = 128 delta ≈ 8× K = 8 delta" → instances, `DataStreamer.run` threads and `listOpenFiles` all 8/32/64/64; heap delta 8.73 → 31.23 → 60.42 MiB, inside 6–12 / 25–40 / 50–75 [observed: `cluster/arm-*/samples.txt`]. Disallow branch fired: JUKEBOX replies 56/32/0 equal 64 − min(K, 64) and equal the `Can't add new stream` count; `Can't add more stream` (create path) 56/32/0 [observed: unit `writeJukebox`, `cantAddNew`, `cantAddMore`; cluster `client.txt`, `logcounts.txt`]. The ratio part is met in shape (see part 2), not to "8×" on the heap; the byte-exact payload (`pendingBytes`, `[B`) meets it.
4. **Excluded rows** — *Refuted (cap not enforced)*: no count above K at any reading; JUKEBOX = 64 − K exactly [observed]. *Refuted for memory (K = 8 ≈ K = 128 delta)*: 9.94 vs 60.14 (unit), 8.73 vs 60.42 (cluster) [observed]. *Not confirmed (control did not move)*: the K = 128 and default arms moved heap by 60 MiB [observed]. *Dump > 0*: 0 [observed]. *Cached below min(K, M) / early reaping*: cached = min(K, 64) at all samples up to +90 s; `Evict stream ctx` 0 [observed].
5. **Observed vs. inferred** — Every part of the matched rows is observed. Inferred only: the fixed-offset explanation of the 6–7× heap ratio (part 2), which the conclusion does not need because the per-K ranges, the linear fit through 32 and 64, and the byte-exact payload counters are observed.
6. **Deviations and gaps** — Thread observable redefined (defect 3) and Option C launcher (defects 2, 4), both before the readings used. The JUKEBOX status in the unit tier comes from an `EmbeddedChannel` instead of the null channel (amendment 3). The default (256) was not itself driven past its limit (M = 64). Transient over-opening (A3: a stream opened before `put` is refused) is not sampled; the sampled state is after the refusals. RSS rose 19 / 64 / 106 / 99 / 11 MiB — it follows min(K, 64) too, but is secondary (fixed heap).
7. **Core question** — Hypothesis: the key caps the number of held write streams and so their heap. Test: K = 8, 32 (binding) against 128 and default (not binding) with the same 64-file out-of-order workload. Logic: the cache size, the live streams (objects, threads, HDFS open files) and the held payload all stop at min(K, 64) (part 3), the extra opens are refused with JUKEBOX (part 3), and the heap after GC follows min(K, 64) linearly at ≈ 0.9 MiB per stream (parts 2, 3), while the no-cap arms show the same workload holds 60 MiB when nothing binds (part 4). Usage follows the constraint and the constraint caps it.

**Conclusion (one line):** unit — B2g row 1 "Claim confirmed: the key caps the number of held streams, and so their buffered memory" — **confirmed**; cluster — B3g row 1 "Claim confirmed in the real daemon" — **confirmed**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `unit/readings.txt` (`createOk=64`, `phase1Sec`, `dumpFiles=0`, `logMaxStreams`); `cluster/arm-K128/heapinfo-base.txt`/`-s45.txt` (PSYoungGen 305664K/262656K total, ParOldGen 699392K; used 655K+27131K → 0K+89658K); `cluster/arm-Kdefault/hdfs-site.xml` has no `nfs.max.open.files` and `gateway.log` has `Maximum open streams is 256` |
| 2. Readings | yes | ratio and offset recomputed from `unit/readings.txt` and `cluster-analyze.txt`; histogram `arm-K128/histo-s45.txt`: `[B` 80 346 560 B, 64 `DataStreamer`, 64 `DFSOutputStream`, 64 `OpenFileCtx`, 64 `WriteCtx` |
| 3. Matched row | yes | client statuses recounted from the 64 `FILE` lines of each `arm-*/client.txt` (K8 0:8/10008:56; K32 32/32 with files 0–31 OK; K128 and default 64/0; K8null 8/56); `logcounts.txt`; `arm-K128/openfiles-s45.txt` 64 `nfsload-` lines; `arm-K8/jstack-s45.txt` 8 `DataStreamer.run(` frames |
| 4. Excluded rows | yes | every B2g/B3g row addressed; both Refuted rows ruled out by observed counts and deltas |
| 5. Observed vs. inferred | yes | the one inferred statement is not load-bearing |
| 6. Deviations and gaps | yes | defects 3–4 restarted their tiers before any reading used; attempts kept under `run1/logs/*attempt*` |
| 7. Core question | yes | the steps from readings to "caps" follow B1 and the B2g/B3g logic; the 6–7× heap ratio against "~8×" is recorded, not hidden, and does not change the row (no other row fits) |

### 5.2 Run 2?

**No** — 2026-11-25. The conclusion rests on observed statements in two independent tiers that agree; it confirms the estimate, does not refute the case and confirms no bypass.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** **true positive** (positive, caps) — both tiers Confirmed with effect `caps`.

**Claim tested (B1):** with `nfs.max.open.files = K` and a client that opens M > K files at once, each with pending out-of-order data, the gateway never holds more than K `OpenFileCtx` write streams, the extra opens are refused with `NFS3ERR_JUKEBOX`, and the gateway heap held by write streams grows with min(K, M), not with M.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g row 1 (max `size()` = cached = streamer threads = min(K, 64); JUKEBOX 56/32/0; pending bytes exact; heap delta 9.94 / 30.07 / 60.14 / 60.06 MiB; 1-byte control 0.71 MiB) | caps | run 1 + self-check | 2026-11-25 |
| Cluster | Confirmed — B3g row 1 (instances, threads, HDFS open files = min(K, 64); JUKEBOX = `Can't add new stream` = 56/32/0; heap-after-GC delta 8.73 / 31.23 / 60.42 / 61.16 MiB; 1-byte control 1.45 MiB) | caps | run 1 + self-check | 2026-11-25 |

The cap limits the number of streams, not bytes per stream (A2/A3): it bounds memory only through that count, as the claim says.

**Feedback filed:** section D of the amended case file (`~/writeup-hadoop/out/o18/case-amended.md`), plus the dated amendments and the two dated runbook fixes in B2a–B3e. Not committed; for the repository: the case file's section D and amendments, `_INDEX.md` (row order 18: stage-4 verdict, Outcome class `true positive`; §4 sha256 of the amended file), `queue.csv` `stage4`, and the harness under `harness/nfs.max.open.files-put-maxStreams--autonomous/`.
