# dfs.client.socketcache.capacity-putInternal-capacity--autonomous — stage-4 results  <!-- file: results/dfs.client.socketcache.capacity-putInternal-capacity--autonomous.md (draft outside the repo: ~/writeup-hadoop/out/o11/results.md) -->

> **Case:** [`dfs.client.socketcache.capacity-putInternal-capacity--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/dfs.client.socketcache.capacity-putInternal-capacity--autonomous.md) (queue order 11)
>
> **Status:** **verdict filed 2026-11-25** (run 1 of both tiers, self-checked; no run 2). Claim tested (B1): `dfs.client.socketcache.capacity` bounds the number of idle cached client→DataNode sockets to `min(N, C)` but does **not** bound any memory or disk quantity (client heap/RSS differ between C = 0 and C = 1024 by ≤ ~4 KB per entry, ≤ 4 MB; no disk use depends on C).
> - **Unit tier: Confirmed — does not cap** (A4 row 1). Part 1 exact for every C (`maxSize = size = min(2048, C)`, `closed = 2048 − min(2048, C)`); part 2 `size = min(1024, C)` = 0/16/256/1024 in both reps; the client-side cache objects cost **232 B per entry** (B_client(1024) = 237,496 B in both reps); whole-JVM ΔH(1024) = −98.9 / −99.6 MiB (MemoryMXBean; noisy, see §4.2 part 2) and +3.96 / +3.90 MiB by the live class histogram (DataNode-side idle-xceiver objects); positive control +65.06 MiB direct and +5114–5127 FDs in every run.
> - **Cluster tier: Confirmed — does not cap** (A7 row 1). Window-2 client connections = printed `size` = DN XceiverCount = 0/16/256/1024 in both reps; client heap after GC ΔH2(1024) = **+0.75 / +0.76 MiB** (≈ 770 B per cached socket), ΔRSS2(1024) = +2.64 / +2.62 MiB; disk (dn+nn+tmp) changed by 0 B in every run; positive control +64.54 MiB direct and 1024 connections in window 1 of every run.
> - Reported, not judged (A7): on the DataNode each cached socket keeps one idle `DataXceiver` thread — NMT Thread +1046.7 MiB *reserved/committed stack* and RSS +25 to +44 MiB at C = 1024 vs C = 0.
>
> **Outcome class:** **true negative** — stage-3 estimate `negative` against the stage-4 effect `does not cap`, both tiers Confirmed ([definition](../../../../stage4-runtime-verification/README.md#outcome-class))
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Layout.** Hadoop, Jingsong's share. Drafted outside the repository (task rule for this session): this file, the harness
(`harness/`), small raw files (`run1/`) and the amended case file (`case-amended.md`) are in `~/writeup-hadoop/out/o11/`. When
filed, they go to `hadoop/stage4-runtime-verification/jingsong/results/`, `…/harness/dfs.client.socketcache.capacity-putInternal-capacity--autonomous/`
and `hadoop/stage3-ai-deep-read/jingsong/cases/`. Node: [`../environment.md`](../environment.md) (`pc82`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, repository commit `cd9e1cded` (HEAD at the start of this session; the file was last committed in `bef6bc8a6`). sha256 as written by stage 3: `f824ab0d…50feee84` (`_INDEX.md` §4). The filed file already carries the audit amendments A1–A7 of the interrupted 2026-11-24 stage-4 attempt (section D1, all "before any reading"); sha256 checked at the start of this session: **`54b7f50d7cb08cf74f52fb278b8e8ee61a534a9b9c3f51bb55e65712254f1bb5`** = `_INDEX.md` §4 "filed with … A1–A7 (audit; frozen)". This session re-audited that version (below), found it runnable as written and added **no new amendment before run 1**; the frozen version is `54b7f50d…`. The interrupted attempt's partial run folder on `pc82` was deleted (no daemon of it was running at 2026-11-25 02:54 MST) and its draft results/harness were set aside unread (`~/writeup-hadoop/out/o11/_interrupted-2026-11-24/`). |
| **Harness** | Outside the repository (task rule): `~/writeup-hadoop/out/o11/harness/` — `TestPeerCacheCapacityProbe.java` (md5 `39b36034`), `unit-run.sh` (`be42bb00`), `PeerCacheProbe.java` (`176a6d35`), `sample.sh` (`29b90395`), `cluster-run.sh` (`f8fc7cf7`), `summarize.py` (`d97d2471`); copied to `R/harness/` on `pc82`. Not committed (the repository is not edited by this session). Instrument checks: `mvn -B -o test-compile` of the module with the probe test BUILD SUCCESS in 38 s (`R/logs/compile-check.log`); known answers inside run 1: part 1 is the operand known answer (exact counts), the surefire JVM prints `maxHeap=2075918336 gc=Copy,MarkSweepCompact` and the `-Dprobe.*` args (A1 options applied), the cluster probe prints its own args/heap/GC and `hdfs getconf` echoes the keepalive. |
| **Tiers and values** | Unit (B2, A1–A4): part 1 C ∈ {0, 1, 16, 256, 1024}, N = 2048 fake puts; part 2 C ∈ {0, 16, 256, 1024} × rep {1, 2}, N = 1024 real 64 KiB one-block files through a 1-DataNode `MiniDFSCluster`. Cluster (B3, A5–A7): pseudo-distributed HDFS on `pc82`, C ∈ {0, 16, 256, 1024} × rep {1, 2}, N = 1024 files × 256 KiB. |
| **Audit bottom line** | **Ready** (as amended by A1–A7, frozen 2026-11-24) — re-audited 2026-11-25 |

### 1.1 Design audit (re-audit of the frozen version)

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1: the claim is that client heap/RSS and disk do **not** follow C; the bounded quantity itself is a count of cached sockets (`PeerCache.size()`), named as such (A2). |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b/B3b: C ∈ {0, 16 (default), 256, 1024} (part 1 adds 1). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d/A3: whole-JVM heap after GC, class histogram, FDs, direct pool; the shared-JVM gap (DataNode objects in the same heap) is named and handled by B_client and A4 row 2. B3d/A6: client heap (`jstat` after `GC.run`), RSS, NMT, DN threads/RSS. Kernel socket memory not observable (named). |
| A. Core question | usage driven to the limit and past it | Met | N = 1024 puts reach C = 1024 exactly and pass C = 16 by 1008 evictions; part 1 N = 2048 passes every C. |
| A. Core question | positive control (negative estimate) | Met | Direct buffers ≥ 64 MiB and ≥ 2000 FDs (unit) / ≥ 1000 connections (cluster) with all readers open, the same instruments as the judged readings (A3, A7). |
| B. Logic | each step says what it establishes | Met | Part 1 = operand bound; part 2 / cluster window 2 = cached entries vs memory; window 1 = instrument sensitivity. |
| B. Logic | prediction in numbers | Met | A3 (ΔH(1024) ≤ 4 MiB, B_client ≤ 1.5 KiB × size, size = min(N, C)); B3f/A7 (ΔH2 ≤ 4 MiB, ΔRSS2 ≤ 8 MiB, disk ≤ 1 MiB). |
| B. Logic | every plausible outcome has a row | Met | A4 and A7: confirmed, shared-JVM excess, refuted (memory, entry bound, disk), limit never reached, positive control missed, reps disagree. |
| B. Logic | confirmation needs ceiling-follows-knob and disallow evidence | Met | For this negative file: `size = min(N, C)` and part-1 `closed = 2048 − min(2048, C)` show the eviction branch fired; the memory readings must stay flat while it does. |
| B. Logic | alternative explanations and controls | Met | B2h/B3h: C = 0 baseline per rep, fresh JVM and context per run, long expiry/keepalive, full GC, reps, `ss` filtered by pid. |
| C. Specific | a human can follow it | Met | Estimate, Ground, A3 steps 1–7, B1. |
| C. Specific | an AI can run it without re-deriving the path | Met | A1, A5, A6 give node paths, Maven/surefire options, daemon commands and sampling. |
| C. Specific | exact values, commands, sampling, stop conditions | Met | A2 (run order), A6 (sampling 20 s after each PHASE line, wait for xceivers to return). |
| D. Runnable | prerequisites exist or are listed | Met | `pc82` in `environment.md` Node table, `hadoop-base` dist present (`bin/hadoop`, 19 YARN jars), JDK 1.8.0_514, Maven 3.6.3, `~/.m2` 3.4.2; ports 9000/9864/9866/9867/9868/9870 free; `curl` present. |
| D. Runnable | workload arithmetic | Met | Unit 64 MiB test data, ~2.7 min per part-2 JVM (file creation dominates); cluster 256 MiB local + 256 MiB HDFS, ~3 min per run; 125 GiB RAM, 656 GB free on `/mydata`. |
| D. Runnable | load-bearing citations spot-checked | Met | `systems/hadoop/source/` (clean): `PeerCache.java:97-107` (ctor), `:181-191` (`put`, C ≤ 0 closes), `:193-201` (check at `:196`, `evictOldest`, insert), `:228-240` (`evictOldest`), `:262-283` (`clear`/`close`); `ClientContext.java:174-175, 210-233`; `BlockReaderRemote.java:101` (PacketReceiver), `:231-239` (status sent after last packet), `:307-315` (put only if status sent); `BlockReaderFactory.java:821-831`; `PacketReceiver.java:273-289`; `TcpPeerServer.java:85` (DN peers are `NioInetPeer` too); `DataXceiver.java:260-302` (keepalive loop); `HdfsClientConfigKeys.java:96-101`; `hadoop-project/pom.xml:187, 2469` (surefire argLine). All as cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | A1–A7 of the interrupted attempt (node paths, surefire options, both-ends-in-one-JVM predictions, a verdict for every row, `hdfs --daemon`, `jstat` on JDK 8, sampling) | Already in the frozen file (2026-11-24, before any reading) | needed for an unambiguous run; re-checked, kept unchanged |
| R2 | B2f's "`fdClosed − fd0` ≈ 2 × `size`" and A3's "± 20" ignore the per-thread NIO selectors of `SocketIOWithTimeout` (3 FDs and, under `ulimit -n 65536`, a 64 KiB `EPollArrayWrapper` byte array each on JDK 8) held by blocked DataNode xceivers or pooled after they exit | Left for stage 3 (recorded as a finding after the run; not a verdict condition in A4) | it does not enter any A4/A7 verdict condition; noticed only after the first unit reading, so it may not amend the prediction |

**Agreement criteria** — not filled; no run 2 (see 5.2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25; unit tier 02:57–03:16 MST, cluster tier 03:17–03:46 MST (node clock) |
| Node | `pc82` = `node1.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 125 GiB RAM (`environment.md` Node table) |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-203-generic` |
| JDK | OpenJDK `1.8.0_514` (`/usr/lib/jvm/java-8-openjdk-amd64`) for build, unit and cluster; Serial GC confirmed from inside every JVM (`gc=Copy,MarkSweepCompact`) |
| Build tool | Apache Maven 3.6.3 (`mvn -B -o`, offline; 3.4.2 artifacts from the node's base build in `~/.m2`) |
| Local source copy | `R/src` by `jingsong/copy-source.sh` from `systems/hadoop/source/` (rel/release-3.4.2) at repository commit `cd9e1cded` (`run1/copy-source.log`); deleted after the run |
| Distribution (cluster) | `cp -a /mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2 $RUN/hadoop` (`hadoop version` → 3.4.2, `cluster/cluster-run.log`) |
| Case-file commit / harness | case file sha256 `54b7f50d…` (committed in `bef6bc8a6`, HEAD `cd9e1cded`); harness md5s in §1, not committed |
| Storage | `R = /mydata/jingsong-s4/dfs.client.socketcache.capacity-putInternal-capacity-run1` (local LVM, 656 GB free); `$RUN = R/cluster`; MiniDFSCluster data under `R/src/…/target/test/data` |
| Settings held fixed | unit: `-Xmx2g -XX:+UseSerialGC`, `ulimit -n 65536`, DN keepalive and client expiry 600 000 ms, fresh JVM and context name per (C, rep); cluster: `ulimit -n 65536`, `HADOOP_HEAPSIZE_MAX=1g`, client `-Xmx1g -XX:+UseSerialGC -XX:NativeMemoryTracking=summary`, DN `-XX:NativeMemoryTracking=summary`, `dfs.datanode.socket.reuse.keepalive=600000` (echoed by `hdfs getconf`), `dfs.datanode.max.transfer.threads=4096`, client `-D dfs.client.socketcache.expiryMsec=600000` (echoed by the probe) |
| Full logs | on `pc82` at `R/logs/` (unit-run.log, cluster-run.log, samples, `cluster/daemon-logs.tgz`); copies in `~/writeup-hadoop/out/o11/run1/` (`unit/`, `cluster/`, surefire outputs in `unit/surefire-outputs.tgz`, unit histograms in `unit/histo/`) |

## 3. Runbook defects

None. Every step ran as written in the frozen file (A1–A7). Two harness details that the design leaves open and do not change
§9a: (i) the unit probe also prints `xceivers0`, `xceiversOpen`, `sizeOpen`, `directClosed` and `bytesRead` (extra readings);
(ii) the cluster sampler also records `ss` socket counts from the DataNode side and the NMT total. The B4 "`stop-dfs.sh`" step was
`hdfs --daemon stop` per A5.

## 4. Run 1

**Scope:** unit tier (part 1 once; part 2 C ∈ {0, 16, 256, 1024} × rep {1, 2}, 8 fresh surefire JVMs) and cluster tier
(C ∈ {0, 16, 256, 1024} × rep {1, 2}, 8 client JVMs against one NameNode + DataNode). **Command logs:** `run1/unit/unit-run.log`,
`run1/cluster/cluster-run.log`. **Summaries:** `run1/unit/summary.txt`, `run1/cluster/summary.txt` (from `harness/summarize.py`).

### 4.1 Readings

**Unit tier** — part 1 (`run1/unit/part-lines.txt`; surefire 1 test, 0 failures, `run1/unit/TEST-part1.xml`):

| C | maxSize | size | closed (of 2048) | Predicted |
|---|---|---|---|---|
| 0 | 0 | 0 | 2048 | 0 / 0 / 2048 |
| 1 | 1 | 1 | 2047 | 1 / 1 / 2047 |
| 16 | 16 | 16 | 2032 | 16 / 16 / 2032 |
| 256 | 256 | 256 | 1792 | 256 / 256 / 1792 |
| 1024 | 1024 | 1024 | 1024 | 1024 / 1024 / 1024 |

Part 2 (`run1/unit/part-lines.txt`, histograms `run1/unit/histo/histo-C<C>-r<rep>.txt`; every run 1 test, 0 failures, `bytesRead = 67,108,864`):

| C | rep | size | xceivers (closed) | Key / Value / Node | NioInetPeer / SocketChannelImpl | B_client (B) | B_client per entry | ΔH MemoryMXBean (MiB) | Δ live histogram total vs C=0 (B) | directOpen − direct0 (MiB) | fdOpen − fd0 | fdClosed − fd0 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 1 | 0 | 0 | 0 / 0 / 0 | 1 / 5 | 0 | – | 0 (base; heapClosed − heap0 = 163.2) | 0 (149,106,432) | 65.06 | 5117 | 3069 |
| 16 | 1 | 16 | 16 | 17 / 16 / 16 | 32 / 36 | 3,664 | 229 | −80.8 | −3,177,760 | 65.06 | 5127 | 3101 |
| 256 | 1 | 256 | 256 | 257 / 256 / 256 | 512 / 516 | 59,344 | 232 | −96.0 | −2,150,408 | 65.06 | 5114 | 3578 |
| 1024 | 1 | 1024 | 1024 | 1024 / 1024 / 1024 | 2048 / 2052 | 237,496 | 232 | −98.9 | **+4,149,664** | 65.06 | 5114 | 5114 |
| 0 | 2 | 0 | 0 | 0 / 0 / 0 | 1 / 5 | 0 | – | 0 (base; 168.6) | 0 (149,192,688) | 65.06 | 5114 | 3066 |
| 16 | 2 | 16 | 16 | 17 / 16 / 16 | 32 / 36 | 3,664 | 229 | −45.7 | −1,580,528 | 65.06 | 5117 | 3101 |
| 256 | 2 | 256 | 256 | 257 / 256 / 256 | 512 / 516 | 59,344 | 232 | −54.0 | −52,720 | 65.06 | 5117 | 3581 |
| 1024 | 2 | 1024 | 1024 | 1024 / 1024 / 1024 | 2048 / 2052 | 237,496 | 232 | −99.6 | **+4,085,720** | 65.06 | 5117 | 5117 |

(`Key` 17 at C = 16/256 includes one `PeerCache$Key` held outside the multimap, e.g. by the last lookup; it is present in the C > 0
runs only and is ≤ 24 B.)

**Cluster tier** — one row per (C, rep); window 1 = all 1024 readers open, window 2 = all closed, sampled 20 s after the `PHASE`
line (`run1/cluster/samples.txt`, `run1/cluster/phase-lines.txt`, `run1/cluster/du.txt`):

| C | rep | W1 client ESTABLISHED | W1 DN XceiverCount | probe direct OPEN − START (MiB) | W2 client ESTABLISHED | W2 printed `size` | W2 DN XceiverCount / `DataXceiver` threads | W2 client heap after `GC.run` (B) | ΔH2 vs C=0 (MiB) | W2 client RSS (KiB) | ΔRSS2 (MiB) | client histogram W2 (Key/Value/Node/NioInetPeer/SocketChannelImpl) | disk dn+nn+tmp after − before (B) | W2 DN NMT Thread − C=0 (MiB) | W2 DN RSS − C=0 (MiB) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 1 | 1024 | 1024 | 64.54 | 0 | 0 | 0 / 0 | 8,483,840 | 0 | 461,296 | 0 | none | 0 | 0 | 0 |
| 16 | 1 | 1024 | 1024 | 64.54 | 16 | 16 | 16 / 16 | 8,532,275 | +0.046 | 451,656 | −9.41 | 17/16/16/16/16 | 0 | +22.4 | +27.2 |
| 256 | 1 | 1024 | 1024 | 64.54 | 256 | 256 | 256 / 256 | 8,704,717 | +0.211 | 451,012 | −10.04 | 257/256/256/256/256 | 0 | +269.3 | +36.7 |
| 1024 | 1 | 1024 | 1024 | 64.54 | 1024 | 1024 | 1024 / 1024 | 9,272,934 | **+0.753** | 464,000 | **+2.64** | 1024 each | 0 | +1046.7 | +43.6 |
| 0 | 2 | 1024 | 1024 | 64.54 | 0 | 0 | 0 / 0 | 8,492,339 | 0 | 470,668 | 0 | none | 0 | 0 | 0 |
| 16 | 2 | 1024 | 1024 | 64.54 | 16 | 16 | 16 / 16 | 8,552,038 | +0.057 | 474,892 | +4.12 | 17/16/16/16/16 | 0 | +21.8 | +4.3 |
| 256 | 2 | 1024 | 1024 | 64.54 | 256 | 256 | 256 / 256 | 8,728,986 | +0.226 | 448,108 | −22.03 | 257/256/256/256/256 | 0 | +269.2 | +21.1 |
| 1024 | 2 | 1024 | 1024 | 64.54 | 1024 | 1024 | 1024 / 1024 | 9,290,957 | **+0.762** | 473,356 | **+2.62** | 1024 each | 0 | +1046.7 | +25.4 |

(ΔH2 is the `jstat` reading after `jcmd GC.run` (A6a); the probe's own after-GC reading at `PHASE CLOSED` gives the same deltas to
three decimals, `run1/cluster/summary.txt`. Every client exited 0; the DN XceiverCount was 0 again 10 s after each client exit
(`…-post10` samples), so no run carried over. The client-side five-class histogram at C = 1024 sums to 237,568 B = 232 B per entry,
the unit tier's B_client per entry.)

### 4.2 Conclusion and logic

1. **Validity.** Valid for both tiers. The limit was reached and passed: part 1 drove 2048 puts at every C [observed:
   `run1/unit/part-lines.txt`]; part 2 and the cluster returned 1024 peers per run, reaching C = 1024 exactly and passing C = 16 by
   1008 evictions (C = 16: `size` stays 16 after 1024 puts) [observed: `part-lines.txt`, `cluster/phase-lines.txt`]. Held-fixed
   settings: Serial GC and heap limits printed from inside every JVM [observed: `PART2-JVM` lines, `PROBE` lines]; keepalive 600000
   [observed: `hdfs getconf` in `cluster-run.log`]; client expiry 600000 [observed: `PROBE … expiryMsec=600000`]; no expiry happened
   (`PHASE END size` = `PHASE CLOSED size` in every cluster run) [observed: `phase-lines.txt`]; fresh JVM per run (one Maven/`hadoop jar`
   invocation each) [observed: logs].
2. **Readings.** (a) The unit tier's MemoryMXBean ΔH is dominated by noise of tens of MiB and is *negative* (−45.7 to −99.6 MiB):
   the C = 0 runs read 163–169 MiB above `heap0` at the closed state, the C = 1024 runs 64–69 MiB. The live class histograms
   (`GC.class_histogram`, which collects first) show no such difference (totals 149.1 / 149.2 MB at C = 0 vs 153.3 / 153.3 MB at
   C = 1024), so the MemoryMXBean excess at C = 0 is garbage not reclaimed by the three `System.gc()` calls or allocated in the 200 ms
   after them, while 1024 DataNode xceivers in the same JVM were exiting [inferred: the histograms of the same runs at the same state;
   not re-measured]. The live-histogram ΔH is reported beside it. (b) `fdClosed − fd0` is ≈ 3 × 1024 at C = 0 and 5 × 1024 at
   C = 1024, not A3's 2 × `size` ± 20: each NIO selector of Hadoop's `SocketIOWithTimeout` pool holds 3 FDs and 1204 /
   1203 `EPollSelectorImpl` live at C = 0 (`histo-C0-r*.txt`), pooled after the 1024 DataNode xceivers exit [observed: histogram;
   inferred: FD attribution]. Not a verdict condition. (c) Cluster ΔRSS2 at C = 16 and 256 is negative (−9 to −22 MiB): RSS noise
   of ~±10–20 MiB between client JVMs; at C = 1024 it is +2.6 MiB in both reps [observed: `samples.txt`].
3. **Matched rows.**
   *Unit, A4 row 1* — "Part 1 exact for every C …, part-2 `size = min(1024, C)` in every run, the positive control met in every run,
   ΔH(1024) ≤ 4 MiB in both reps and B_client(1024) ≤ 4 KiB × `size`": part 1 exact (table above); `size` 0/16/256/1024 in all 8 runs;
   `directOpen − direct0` = 68,223,891–68,223,921 B ≥ 67,108,864 and `fdOpen − fd0` 5114–5127 ≥ 2000 in every run; ΔH(1024) =
   −103,754,224 / −104,475,680 B ≤ 4,194,304 (and the live-histogram ΔH, +4,149,664 / +4,085,720 B, is also ≤ 4,194,304);
   B_client(1024) = 237,496 B ≤ 4096 × 1024 = 4,194,304 [observed: `part-lines.txt`, `histo/`, `summary.txt`]. Flags: none
   (ΔH(16) < 0.5 MiB, B_client ≤ 1.5 KiB × `size` at every C).
   *Cluster, A7 row 1* — "Connections2 = printed `size` = min(1024, C) ± 2 for every C in both reps; positive control met in every
   run; ΔH2(1024) ≤ 4 MiB and ΔRSS2(1024) ≤ 8 MiB in both reps; disk flat": Connections2 = `size` = 0/16/256/1024 exactly;
   direct +64.54 MiB (≥ 64 MiB) and window-1 ESTABLISHED 1024 (≥ 1000) in all 8 runs; ΔH2(1024) = 789,094 / 798,618 B; ΔRSS2(1024)
   = 2,704 / 2,688 KiB; disk change 0 B in all 8 runs [observed: `samples.txt`, `phase-lines.txt`, `du.txt`]. Flag: none (ΔH2(16) =
   0.046 / 0.057 MiB ≤ 0.5 MiB).
4. **Excluded rows.**
   Unit: row 2 (ΔH(1024) > 4 MiB with B_client small) — ΔH(1024) negative; the live-histogram variant also ≤ 4 MiB, though only by
   44,640 / 108,584 B. Row 3 (**Refuted**, B_client(1024) > 4 KiB × `size`) — 232 B per entry, 18× below. Row 4 (**Refuted**, `maxSize`
   or `size` > C) — never (part 1, part 2). Row 5 (limit never reached) — `size` = C at 256 and 1024. Row 6 (positive control missed) —
   met in every run. Row 7 (reps disagree) — both reps in row 1.
   Cluster: row 2 (**Refuted**, ΔH2(1024) > 4 MiB or ΔRSS2(1024) > 8 MiB following `size`) — 0.75–0.76 MiB and 2.6 MiB. Row 3 (memory
   not settled) — neither bound exceeded in any rep. Row 4 (**Refuted** for disk) — disk change 0 B everywhere. Row 5 (limit never
   reached) — Connections2 = C. Row 6 (positive control missed) — met. Row 7 (reps disagree) — both reps in row 1.
5. **Observed vs. inferred.** The verdicts rest on observed readings only. Inferred and used only in part 2: that the MemoryMXBean
   excess at C = 0 is unreclaimed/transient garbage (supported by the live histograms of the same runs); that the extra FDs are pooled
   selectors; that the +4.0 MiB live-histogram ΔH at C = 1024 is DataNode-side: the largest diff items are 1024 × `[Ljava.nio.ByteBuffer;`
   of 4112 B (the JDK's per-thread temporary-buffer cache, one per live idle xceiver thread), 1025 `org.apache.hadoop.util.Daemon` and the
   thread-name `char[]`/`String`s [observed: histogram diff; inferred: owner]. The client-side share is the 232 B per entry of B_client.
6. **Deviations and gaps.** No deviation from the frozen runbook. Gaps (named in B2d/B3d): kernel socket buffer memory not measured
   (only counted, `client_skmem_sockets`); the unit tier cannot separate client and DataNode heap except through the histogram; the
   MemoryMXBean ΔH is too noisy at this scale to resolve 4 MiB, so the unit row-1 condition "ΔH(1024) ≤ 4 MiB" is met but not
   informative by itself — the conclusion leans on B_client (unit) and on the separate-JVM cluster tier, whose client-heap noise is
   < 0.1 MiB. A3's FD prediction (2 × `size` ± 20) missed (part 2 (b)); not a verdict condition.
7. **Core question.** The knob does what A3 traced — it bounds the count of idle cached sockets exactly (`size` = min(N, C), oldest
   evicted, parts 3 and 1) — but the memory it bounds on the client is ~232 B of cache objects (≈ 770 B of client heap in all) per
   socket: at C = 1024 the client heap is +0.76 MiB and RSS +2.6 MiB over C = 0, and no disk use depends on C (part 3). Client memory
   and disk usage therefore do not follow the constraint in any significant way; the knob caps connections, not memory or disk. The
   one memory quantity that does follow it is on the DataNode (one idle `DataXceiver` thread per cached socket: RSS +25–44 MiB, NMT
   Thread +1 GiB reserved stack at C = 1024), which B1 does not claim and A7 reports without judging.

**Conclusion (one line):** unit — A4 row 1, **Confirmed (does not cap)**; cluster — A7 row 1, **Confirmed (does not cap)**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read `part-lines.txt` (PART1 counts, PART2 `size`, `PART2-JVM` args/GC), `cluster/phase-lines.txt` (`PROBE … expiryMsec=600000`, `PHASE CLOSED/END size` equal), `cluster-run.log` (`getconf` 600000, `ls-count=1025`, `/probe` 268,435,456 B). |
| 2. Readings | yes | Re-read `histo/histo-C0-r1.txt` (`EPollSelectorImpl` 1204, `[B` 82 MB, `Total` 149,106,432) and `histo-C1024-r*.txt` (`Total` 153,256,096 / 153,278,408); the MemoryMXBean/histogram disagreement is recorded, not hidden. |
| 3. Matched row | yes | Re-read the C1024 histogram lines (Key 1024 × 24 B, Value 1024 × 24 B, Node 1024 × 40 B, NioInetPeer 2048 × 32 B, SocketChannelImpl 2052 × 112 B) — B_client recomputed by hand: 24,576 + 24,576 + 40,960 + ½(65,536 − 32 + 229,824 − 560) = 237,496 B. Cluster `samples.txt` C0/C1024 w2 heap 8,483,840 / 9,272,934 / 8,492,339 / 9,290,957 B and RSS 461,296 / 464,000 / 470,668 / 473,356 KiB re-read; `du.txt` before = after for every run. |
| 4. Excluded rows | yes | Every Refuted row (unit 3, 4; cluster 2, 4) checked against the same files; the narrowest margin (live-histogram ΔH 44,640 B under 4 MiB) is stated and is not the A4 quantity. |
| 5. Observed vs. inferred | yes | The inferred items (garbage at C = 0, selector FDs, DataNode ownership of the +4 MiB) do not enter either matched row; removing them leaves both verdicts unchanged. |
| 6. Deviations and gaps | yes | No deviation; gaps listed. |
| 7. Core question | yes | The steps follow B1: entry bound observed (part 1, part 2, window 2), memory flat on the client (B_client, cluster ΔH2/ΔRSS2), disk flat, positive control moved every time. |

### 5.2 Decision

No part fails. Run 2 not chosen: both tiers land in the Confirmed row with wide margins on the judged client quantities (cluster ΔH2
0.76 MiB vs a 4 MiB bound in both reps; B_client 232 B vs 4 KiB per entry), and the only inferred statements are not load-bearing.
Verdict: run 1's rows.

## 6.–7. Run 2 and comparison

Not run.

## 8. Verdict and feedback

| Tier | Verdict | Claim tested | Effect on the constraint |
|---|---|---|---|
| Unit (B2) | **Confirmed** (A4 row 1) | B1 | `does not cap` |
| Cluster (B3) | **Confirmed** (A7 row 1) | B1 | `does not cap` |

**Outcome class: true negative** — estimate `negative`, both tiers `does not cap`.

**Findings for stage 3 (not applied):**
- F1. A3's unit prediction `fdClosed − fd0 = 2 × size ± 20` misses the NIO selectors of `SocketIOWithTimeout`'s pool (3 FDs each;
  on JDK 8 under `ulimit -n 65536` each also holds a 64 KiB `EPollArrayWrapper` byte array): measured `fdClosed − fd0` ≈ 3 × 1024 at
  C = 0 and 5 × 1024 at C = 1024. Not a verdict condition.
- F2. The unit tier's MemoryMXBean "heap after 3 × System.gc() + 200 ms" is not a usable retained-heap reading in a JVM that also hosts
  a DataNode with 1024 exiting threads (noise −46 to −100 MiB); a live class-histogram total is the stable whole-JVM reading. A design
  with a shared-JVM unit tier should define ΔH from the histogram total.
- F3. Ground and A7: the DataNode-side cost per cached socket was measured (one idle `DataXceiver` thread; RSS +25–44 MiB and NMT
  Thread +1 GiB reserved stack at C = 1024, bounded by `dfs.datanode.socket.reuse.keepalive` and `dfs.datanode.max.transfer.threads`).
  It is a thread-count effect on another process, outside B1; it does not change the negative estimate.

**Filed (outside the repository, for the parent session):** this file; `case-amended.md` (the frozen case file with section D2
appended; whole-file sha256 after D2 `8c240e88046b5aeb64819dcc4e5fa2e8a2f053fbd6d130b2157eb900a8a3e3f6`; sections A–C unchanged from `54b7f50d…`); harness and raw files under `~/writeup-hadoop/out/o11/`. Not done by this session (task rule: no repository
edits): `_INDEX.md` row 11 and §4 sha256, `queue.csv` stage4 column, `HANDOFF-Jingsong.md`, `FLOWCHART.md` counts.

**Cleanup (2026-11-25 03:47–03:50 MST):** NameNode and DataNode stopped with `hdfs --daemon stop` (`leftover:` empty in
`cluster-run.log`); no NameNode/DataNode/RunJar/surefire JVM on `pc82` afterwards; both detached drivers (unit pid 1239051, cluster pid
1287818) had exited; `/mydata/s4/DRIVER-jingsong-s4-o11.pid` removed; node lock released. Deleted on `pc82`: `R/src` (source copy and
MiniDFSCluster data), `R/cluster/{hadoop,files,dn,nn,tmp,probe,probe.jar,pids}`, unit surefire outputs and histograms (copied here
first). Kept on `pc82`: `R/logs/` and `R/cluster/{conf,logs}` (3.1 MB in all).
