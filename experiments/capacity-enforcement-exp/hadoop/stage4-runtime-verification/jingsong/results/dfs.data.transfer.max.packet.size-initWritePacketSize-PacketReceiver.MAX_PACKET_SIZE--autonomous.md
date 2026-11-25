# dfs.data.transfer.max.packet.size-initWritePacketSize-PacketReceiver.MAX_PACKET_SIZE--autonomous — stage-4 results  <!-- file: results/dfs.data.transfer.max.packet.size-initWritePacketSize-PacketReceiver.MAX_PACKET_SIZE--autonomous.md -->

> **Case:** [`dfs.data.transfer.max.packet.size-initWritePacketSize-PacketReceiver.MAX_PACKET_SIZE--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/dfs.data.transfer.max.packet.size-initWritePacketSize-PacketReceiver.MAX_PACKET_SIZE--autonomous.md) (queue order 10)
>
> **Status:** **verdict filed 2026-11-25** — unit **Confirmed** (does not cap), cluster **Confirmed** (does not cap). Claim tested: with `dfs.client-write-packet-size` C > `dfs.data.transfer.max.packet.size` MAX, a replicated HDFS output stream still allocates its first packet buffer at the configured size (`33 + 516·⌊(C−33)/516⌋` B), following C, not MAX; only later packets are clamped. Every reading equals its B2f / B3f prediction to the byte: first buffer 33553965 / 268435101 B at MAX 16 MiB and 8388129 B at MAX 4 MiB while the clamped `writePacketSize` reads MAX; second-packet buffers 16776741 / 4194081 B (the in-stream positive control); writes whose first packet carries more than the DataNode's MAX fail with the DataNode's "Incorrect value for packet payload size"; a client at `-Xmx192m` dies with `OutOfMemoryError` at C = 256 MiB and succeeds at C = 16 MiB. One run 1 per tier (one runbook defect in each tier, fixed and the tier restarted, §3), no run 2.
>
> **Outcome class:** **true negative** — stage-3 estimate `negative` against the stage-4 effect `does not cap` on both tiers ([definition](../../../../stage4-runtime-verification/README.md#outcome-class)). See the note in §8 on the Effect field.
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Layout.** Hadoop, Jingsong's share: this file belongs in `hadoop/stage4-runtime-verification/jingsong/results/`; the case file is in
`hadoop/stage3-ai-deep-read/jingsong/cases/`; the harness in `../harness/<stem>/`; the protocol is
[`../../../../stage4-runtime-verification/README.md`](../../../../stage4-runtime-verification/README.md#the-run-protocol);
the node is described in [`../environment.md`](../environment.md). **Written outside the repository** by the stage-4 agent
(2026-11-25): this file `~/writeup-hadoop/out/o10/results.md`, the harness `~/writeup-hadoop/out/o10/harness/`, the amended case
file `~/writeup-hadoop/out/o10/case-amended.md`, the small logs `~/writeup-hadoop/out/o10/run1/` (the parent session files them).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, committed at `bef6bc8a6` (repository HEAD `cd9e1cded` at audit time). sha256 at filing (`_INDEX.md` §4, 2026-11-24): `7415910f7cd1a44c78ed37a1a894222791448eea8ff30221f43a700f72684a13` (checked before the audit; the repository file still has it). After the audit's amendments A1–A6 (section D1), 2026-11-25 04:36 EST, before any reading: whole-file sha256 `e0af9e3b6dcae9ff9701e7f50bd3a8fbd9d03a26c61b901ddb98b86227d09b87`. After A7 (runbook defect, §3; B2f–B2h unchanged), before the unit tier restarted: **`3c3b0903197e0e221200787e36c8689de41dfddf6232fad6608ff360db0c744a`** (frozen version for both tiers' counted runs). Frozen prediction, conclusions and controls: sha256 of the text from `**B2f.` up to `**B2h.` `6c74eeb75cf4bb4bc1efb64f7533181f2e17488e49824b9ea7570e15c6f92e1d`; from `**B3f.` up to `**B3h.` `87b0d1c05d052431302eae6f902c6f9f3475326fa7b033479355443344c681a8` — both identical in the filed file and after every amendment (no amendment touches B1, B2f, B2g, B3f or B3g). |
| **After the run** | Section D2 added 2026-11-25 after run 1: whole-file sha256 `3f54f53eddc1d129f992343d7b1b1732635af21163b58a8bb80a4b2bc0d43c0e`; the B2f–B2h and B3f–B3h text hashes above re-computed and unchanged. |
| **Harness** | `harness/` (written after the freeze of A1–A6, before run 1; uncommitted, outside the repo): `WritePacketCapRunner.java` (shared test body; md5 `07825bcc` at attempt 1, changed by A7 before the restart), `TestWritePacketSizeCap.java` `36300116`, `TestWritePacketSizeCap4M.java` `2d2c72ec`, `maxpkt-4m-site.xml` `3d7a84ea`, `unit-run.sh` `250fdb07`, `cluster-run.sh` (input-file fix before cluster attempt 2, §3), `jfr-read.py`. md5 of each file as run is in `run1/unit/unit-run.log` and `run1/cluster/cluster-run.log`. Instrument checks: `unit-run.sh --compile-only` BUILD SUCCESS 02:35 MST (`run1/unit-attempt1/unit-run-compileonly.log`); known answers in the runs themselves: `ByteArrayManager$NewByteArrayWithoutLimit` in every unit row, `PacketReceiver.MAX_PACKET_SIZE` asserted 16777216 / 4194304 per class; cluster client heap read back from each JFR (`maxHeap` 1073741824 / 201326592, `-Xmx1024m` / `-Xmx192m`) and the C = 65536 control at 65072 B = ceil((65049+16)/8)·8. |
| **Tiers and values** | Unit (B2): MAX 16 MiB × C ∈ {65536, 16777216, 33554432, 268435456}; MAX 4 MiB × C ∈ {4194304, 8388608}; 1 MiB `/t/small` + 48 MiB `/t/big` per C; `MiniDFSCluster`, 1 DataNode. Cluster (B3): pseudo-distributed NN + DN on `pc72`; set 1 (client MAX 16 MiB, C ∈ {65536, 16 Mi, 32 Mi, 256 Mi} × {f1m, f48m}, H 1024m); set 2 / 2-ctl (C 256 Mi / 16 Mi, f1m, H 192m); set 3 (client MAX 4 MiB, DN 16 MiB, C ∈ {4 Mi, 8 Mi} × {f1m, f48m}). 14 client runs. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: client heap bytes of each `DFSPacket` buffer (`33 + packetSize`); the check's own operand `writePacketSize` is read separately (B2d (a)). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b/B3b: C at 4 values incl. the default 65536, and MAX at 2 values (default 16 MiB and 4 MiB), so both sides of the comparison move. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d (c) the allocated array's length, (d) thread-allocated bytes; B3d (1) JFR allocation events, (2)/(6) OOM at a fixed heap. Gap named: no RSS of the unit tier's client (B2d last bullet). |
| A. Core question | usage driven to the limit and past it | Met | C = MAX (boundary), 2×MAX, 16×MAX; f48m fills the first packet past MAX (B2c/B3c arithmetic). |
| A. Core question | positive control (negative estimate) | Met | B2g row 3 / B3g row 5: the second packet in the same stream, where `adjustChunkBoundary` applies the clamp (same workload, same instrument); set 3 moves the client MAX alone; set 2-ctl. |
| B. Logic | each step says what it establishes | Met | B2h/B3h: no-clamp controls (C ≤ MAX), in-stream control, MAX-scaling class, allocator check, alloc cross-check, fresh JVM. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f/B3f: exact bytes per (MAX, C) from A3 step 5; WARN exactly when C > MAX; set 2 OOM. JFR rounding made exact by A5 (no change to the predicted buffer sizes). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g: confirmed, refuted (first ≤ MAX + 33), clamp nowhere, instrument failure, DN accepts, alloc elsewhere; set 2 both ways. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | For this negative file: the check's firing is observed directly ((a) = MAX and the WARN (g)), and the usage is shown to follow C regardless. |
| B. Logic | alternative explanations and their controls | Met | ByteArrayManager pooling (B2h assert), stale static MAX (fresh JVM per class), instrument (C = 65536 known answer, (d) cross-check), DN vs client MAX (set 3). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, Ground, A3 steps 1–8, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met | B2a paths/`install` build, `start-dfs.sh` (no SSH to localhost on these nodes), cluster rebuild. **Amended** (A1, A4, A6). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | (e) "write exactly chunksPerPacket·512 then one chunk" is not observable at a `write` boundary (FSOutputSummer groups of 9 chunks); (f) can surface in `write`, `hflush` or `close`; JFR byte rounding and TLAB placement unstated. **Amended** (A3, A5). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met | Test classes are step-1 work. B2a's `static {}` order would let `hdfs-default.xml` override the 4 MiB resource (`HdfsConfiguration.java:33-40`). **Amended** (A2). JDK 8u514 has JFR and `jfr` (checked on `pc72`). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 268 MB buffer within the unit `-Xmx2048m` and cluster 1024m; < 1 GB disk; ~4 s per client command. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `systems/hadoop/source/` at `rel/release-3.4.2`: `DFSOutputStream.java:132` (field), `:136-153` (`createPacket`), `:229`, `:249-258` (check), `:261-274` (`:267` raw C), `:362`, `:401-403`, `:426-430`, `:440-455`, `:478-499` (`writeChunkPrepare`, allocation at `:494`), `:509-517`, `:531-543` (`adjustChunkBoundary`), `:636-700` (`flushOrSync` reuses `packetSize`, no clamp); `PacketReceiver.java:80-85` (static MAX), `:160-169` (DN check); `PacketHeader.java:61-64`; `HdfsConfiguration.java:33-40`; `HdfsClientConfigKeys.java:133` (CRC32C), `:417-421`. All as cited. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 (A1) | Node paths, no `install` build (3.4.2 in `~/.m2`), read surefire counts | Applied 2026-11-25 (uncommitted; sha256 above) | filed paths do not exist on the node |
| R2 (A2) | Load `HdfsConfiguration` before `addDefaultResource("maxpkt-4m-site.xml")` | Applied 2026-11-25 | otherwise `hdfs-default.xml` wins and the 4 MiB class tests 16 MiB |
| R3 (A3) | Define how (e), (f), (g) are read; per-test timeout | Applied 2026-11-25 | (e) as filed is not observable at a `write` boundary |
| R4 (A4, A6) | `hdfs --daemon` instead of `start-dfs.sh`; base distribution; ports; `dumponexit`; heap read-back | Applied 2026-11-25 | SSH to localhost does not work on the nodes; heap known answer |
| R5 (A5) | Exact JFR sizes (header + 8-byte rounding), fixed 16 KiB TLAB, InNewTLAB as backup | Applied 2026-11-25 | the C = 65536 control would otherwise risk "no event" (an instrument failure row) |
| R6 | A3 step 7 / A4: the striped (EC) stream is said to clamp before its first packet; not exercised by either tier | Left for stage 3 | outside the claim (B1 is about replicated streams) |
| R7 | B3g "Set 2" rows: with the allocation failing, the JFR of the OOM run has no `createPacket` event, which B3g's instrument-failure row would literally match; A5 says this is expected for set 2 | Applied 2026-11-25 (inside A5) | avoid a false "instrument failure" reading |

**Agreement criteria** — not filled (no run 2, §5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-11-25 (node clock MST): unit attempt 1 02:36–02:37:50, unit counted run 02:38:36–02:40:20; cluster attempt 1 02:40–02:54:26, cluster counted run 02:54–03:08:56 | not done |
| Node | `pc72` = `node2.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu` (in `environment.md` Node table), 40 cores, 125 GiB; `/mydata/jingsong-s4/hadoop-base` present (built 2026-11-24); node lock `/mydata/s4/NODE-LOCK` held for the whole run; no Java process before or after | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-203-generic` | — |
| JDK (`java -version`) | OpenJDK `1.8.0_514` (`/usr/lib/jvm/java-8-openjdk-amd64`) for the build, the tests, the daemons and the clients; `jfr` from the same JDK | — |
| Build tool | Apache Maven 3.6.3, offline (`-o`), `hadoop-hdfs` module compiled in the copy; other modules from `~/.m2` (3.4.2, node base build 2026-11-24) | — |
| Local source copy | `/mydata/jingsong-s4/dfs.data.transfer.max.packet.size-initWritePacketSize-PacketReceiver.MAX_PACKET_SIZE-run1/src`, by `copy-source.sh` from `systems/hadoop/source/` (clean) at repository HEAD `cd9e1cded`, tag `rel/release-3.4.2`; only the 3 test classes and `maxpkt-4m-site.xml` added (`git status` in `run1/unit/unit-run.log`). Cluster: the base distribution `hadoop-base/hadoop-dist/target/hadoop-3.4.2` copied to `…-run1/cluster/hadoop` (`Hadoop 3.4.2`) | — |
| Case-file commit / harness commit | `bef6bc8a6` + amendments (uncommitted, sha256 `3c3b0903…`) / uncommitted, md5 in §1 | — |
| Storage for node data | `/mydata/jingsong-s4/…-run1/` (local disk): unit `target/`; cluster `nn`, `dn`, `tmp`, `jfr`, `dumps`, `in`; ports 19000, 19864–19867, 19870, 19871 (checked free). Nothing on `/proj`. Bulk data deleted after the run (§8) | — |
| Full logs (path, outside the repo) | node: `…-run1/logs/` (2.2 MB, kept); copy at `~/writeup-hadoop/out/o10/run1/`: `unit/` (counted), `unit-attempt1/`, `cluster/` (counted: `cluster-run.log`, `readings.csv`, `selfcheck-jfr.txt`, `daemon-logs/`, `client-out/`), `cluster-attempt1/` | — |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | run 1, unit attempt 1 | B2d (c)/(d), B2e step 1.4 ("`write` 64 KiB; read (c) and (d)") | At C = 65536 the first packet holds 126 chunks (64512 B), so the first 64 KiB `write` fills and queues it; `currentPacket` is null when (c) is read: (c) = −1 (`run1/unit-attempt1/unit-run.log`, `IFCHK,RESULT,C=65536`). Every other reading of attempt 1 equalled B2f. | First write of 4608 B (one FSOutputSummer group, 9 chunks; cannot fill a packet at any C in B2b), (c)/(d) read after it, rest in 64 KiB writes to the exact file size. B2f–B2h unchanged. | A7, 2026-11-25; unit tier restarted from its beginning (02:38) | uncommitted, sha256 `3c3b0903…` |
| 2 | run 1, cluster attempt 1 | B3c input files (harness, not the case file) | The harness wrote `f1m`/`f48m` through its logging wrapper, which echoed the command line into the file: inputs were 1048629 and 50331702 B instead of 1048576 and 50331648 (`run1/cluster-attempt1/readings.csv`, `hdfsLen`). Every B3f reading of attempt 1 still matched (no prediction depends on the 53 B). | Harness fix (inputs written directly, sizes asserted); no case-file change. | 2026-11-25; cluster tier restarted from its beginning (02:54) | none needed (harness only) |

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command logs:** `run1/unit/unit-run.log`, `run1/cluster/cluster-run.log`. Raw readings: `run1/unit/ifchk-*.csv` (the `IFCHK` lines of the surefire `-output.txt`), `run1/unit/logcounts-*.txt`, `run1/cluster/readings.csv`.

### 4.1 Readings

**Unit tier** (`run1/unit/ifchk-TestWritePacketSizeCap.csv`, `…4M.csv`, `logcounts-*.txt`; every row: `bam = ByteArrayManager$NewByteArrayWithoutLimit`, small file ok with length 1048576; surefire 4/0/0 and 2/0/0)

| MAX | C | (a) writePacketSize | (b) packetSize / chunks after create | (c) first buf | (d) first-write alloc | (e) 2nd-packet buf (packetSize then) | big write | WARN (g) | DN "Incorrect value…" |
|---|---|---|---|---|---|---|---|---|---|
| 16777216 | 65536 | 65536 | 65016 / 126 | 65049 | 153152 | 65049 (65016) | ok, 50331648 B | 0 | 0 |
| 16777216 | 16777216 | 16777216 | 16776708 / 32513 | 16776741 | 16776904 | 16776741 (16776708) | ok, 50331648 B | 0 | 0 |
| 16777216 | 33554432 | **16777216** | **33553932** / 65027 | **33553965** | 33554128 | **16776741** (16776708) | **fails** in `write` at 44306944 B: `IOException: All datanodes […] are bad. Aborting...`; length 0 | 2 | 3 × `…payload size: 33553936` |
| 16777216 | 268435456 | **16777216** | **268435068** / 520223 | **268435101** | 268435264 | none (first never fills) | **fails** at `close`, same message; length 0 | 2 | 3 × `…payload size: 50724868` |
| 4194304 | 4194304 | 4194304 | 4194048 / 8128 | 4194081 | 4194248 | 4194081 (4194048) | ok, 50331648 B | 0 | 0 |
| 4194304 | 8388608 | **4194304** | **8388096** / 16256 | **8388129** | 8476248 | **4194081** (4194048) | **fails** in `write` at 12980736 B, same message; length 0 | 2 | 3 × `…payload size: 8388100` |

(WARN count 2 = one per stream, small and big. DN payload values: 33553936 = 4 + 65027·4 + 33293824; 50724868 = 4 + 98304·4 + 50331648; 8388100 = 4 + 16256·4 + 8323072.)

**Cluster tier** (`run1/cluster/readings.csv`; JFR sizes are `allocationSize` = array + 16 B header, 8-byte aligned (A5); "later" lists packet buffers ≥ 1 KiB after the first)

| Set | Client MAX | C | H | File | JFR first `createPacket` buffer | JFR later buffers | Client exit, WARN | DN "Incorrect value…" (new lines) | HDFS file |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 16M | 65536 | 1024m | f1m | 65072 | 65072 × 16 | 0, 0 | 0 | 1048576 B |
| 1 | 16M | 65536 | 1024m | f48m | 65072 | 65072 × 400 | 0, 0 | 0 | 50331648 B |
| 1 | 16M | 16777216 | 1024m | f1m | 16776760 | none | 0, 0 | 0 | 1048576 B |
| 1 | 16M | 16777216 | 1024m | f48m | 16776760 | 16776760 × 3 | 0, 0 | 0 | 50331648 B |
| 1 | 16M | 33554432 | 1024m | f1m | **33553984** | none | 0, 1 | 0 | 1048576 B |
| 1 | 16M | 33554432 | 1024m | f48m | **33553984** | **16776760 × 2** | **1**, 1; `put: All datanodes […] are bad. Aborting...` | **3** (`…payload size: 33553936`) | absent |
| 1 | 16M | 268435456 | 1024m | f1m | **268435120** | none | 0, 1 | 0 | 1048576 B |
| 1 | 16M | 268435456 | 1024m | f48m | **268435120** | none | **1**, 1; same `put:` message | **3** (`…payload size: 50724868`) | absent |
| 2 | 16M | 268435456 | 192m | f1m | no event (allocation failed) | — | **1**, 1; `java.lang.OutOfMemoryError: Java heap space`; heap dump 13734040 B | 0 | absent |
| 2-ctl | 16M | 16777216 | 192m | f1m | 16776760 | none | 0, 0 | 0 | 1048576 B |
| 3 | 4M | 4194304 | 1024m | f1m | 4194104 | none | 0, 0 | 0 | 1048576 B |
| 3 | 4M | 4194304 | 1024m | f48m | 4194104 | 4194104 × 12 | 0, 0 | 0 | 50331648 B |
| 3 | 4M | 8388608 | 1024m | f1m | **8388152** | none | 0, 1 (`exceeds 4194304 bytes as max`) | 0 | 1048576 B |
| 3 | 4M | 8388608 | 1024m | f48m | **8388152** | **4194104 × 11** | 0, 1 | 0 | 50331648 B |

Every JFR read back the heap in force: `maxHeap` 1073741824 with `-Xmx1024m`, 201326592 with `-Xmx192m`. Each command ran 3.7–4.2 s (the first, 10.9 s, includes JIT/cold start). Below-1 KiB `byte[]` events under `createPacket` (56, 64, 136, 152 B: the 33-byte end-of-block packet and small objects that opened a TLAB) are ignored per A5. One of the 17 C = 65536 / f1m buffers was recorded as `ObjectAllocationInNewTLAB` (TLAB 81456 B), the other 16 outside a TLAB (`run1/cluster/selfcheck-jfr.txt` and the re-read in §5) — the backup reading A5 provided for.

### 4.2 Conclusion and logic

1. **Validity** — valid, both tiers. Limit reached and passed: C = 2×MAX and 16×MAX at MAX 16 MiB, 2×MAX at 4 MiB; the check fired (a) = MAX and the client WARN appeared in exactly the C > MAX rows [observed: `run1/unit/ifchk-*.csv`, `logcounts-*.txt`; `run1/cluster/readings.csv` `clientWarn`]. Fixed settings held: default `ByteArrayManager` (no pooling) in every unit row; MAX asserted per test class (16777216 / 4194304); a fresh JVM per test class and per client command; client heap as set [observed: `bam=…NewByteArrayWithoutLimit`; surefire 4/0/0, 2/0/0 in `run1/unit/*.txt`; JFR `maxHeap`/`xmx` in `readings.csv`]. Instrument known answers: C = 65536 gives 65049 B (unit) and 65072 B (cluster) [observed].
2. **Readings** — no gap or outlier. Small notes: (d) exceeds (c) by ≈ 88 KB in the first test of each JVM (C = 65536 and C = 8388608, the first methods run) and by ≤ 163 B elsewhere — first-call class loading, not packet memory [inferred: the excess is the same 88 KB in both first tests and absent in later tests of the same JVM]. The failing streams surfaced the DataNode's refusal in a later `write` (C = 32 Mi, 8 Mi) or at `close` (C = 256 Mi), as A3 allowed [observed].
3. **Matched row** — B2g row 1 and B3g row 1: "For C > MAX, (a) = MAX but (c) = 33 + 516⌊(C−33)/516⌋ > MAX, and (c) grows with C (33.55 MB → 268.4 MB)" — unit (a) 16777216 with (c) 33553965 and 268435101 at MAX 16 MiB, (a) 4194304 with (c) 8388129 at MAX 4 MiB, each equal to the formula [observed: `ifchk-*.csv`]; (d) 33554128 / 268435264 / 8476248 confirms the allocation without reflection [observed]. Cluster: first `createPacket` buffer 33553984 / 268435120 (= formula + 16, aligned) at client MAX 16 MiB and 8388152 at 4 MiB, rising with C [observed: `readings.csv`]. Supporting rows that also hold: positive control B2g row 3 / B3g row 5 — second-packet buffer 16776741 (unit) / 16776760 × 2 (cluster) at C = 32 Mi and 4194081 / 4194104 × 11 at C = 8 Mi, i.e. `33 + 516⌊(MAX−33)/516⌋`, with the same workload [observed]; B3g row 3 — set 2 OOM at C = 256 Mi and success of 2-ctl at C = 16 Mi, same 192m heap [observed: `readings.csv`, `client-out/s2-268435456-f1m.out`]; downstream effect A3 step 6 — big writes with first packet > DN MAX fail with the DN line [observed: `logcounts-*.txt`, `readings.csv`, `daemon-logs/`].
4. **Excluded rows** — *Refuted: first buffer ≤ MAX + 33 (+16) for every C > MAX* (B2g row 2, B3g row 2): the first buffer is 2.0×, 16.0× and 2.0× MAX [observed]. *Set 2 succeeds at 256 Mi / 192m* (B3g row 4): it failed with `OutOfMemoryError` [observed]. *Clamp binds nowhere — (e)/later also ≈ C* (B2g row 4, B3g row 6): later buffers are MAX-sized [observed]. *Instrument failure — C = 65536 not 65049 / no createPacket events* (B2g row 5, B3g row 7): 65049 / 65072, and every run except the OOM run has packet events [observed; the OOM run's missing event is the failed allocation itself, A5]. *Big write succeeds with C > DN MAX* (B2g row 6, B3g row 8): all three such writes failed with the DN line; in set 3 (client MAX 4 MiB, DN 16 MiB) the 8.39 MB first packet was accepted, as B3f predicts [observed]. *(d) far below (c)* (B2g row 7): (d) ≥ (c) in every row [observed].
5. **Observed vs. inferred** — The conclusion rests on observed array lengths and allocation events. Inferred: (i) that the JFR `createPacket` events are the packet buffers [inferred: their sizes equal the unit tier's reflected `buf.length` + 16 aligned, for every C]; (ii) that "first buffer" in JFR time order is the first packet [inferred: it is the only buffer in the f1m runs, and the unit tier reads the first packet object directly].
6. **Deviations and gaps** — Both tiers were restarted after a runbook defect (§3); the counted runs are the restarts, and the discarded attempts gave the same readings in every other cell. Amendments A1–A7 change how things are run and read, not B1/B2f/B2g/B3f/B3g. Not covered: the striped (EC) stream and append paths (`:362`, `:401-403`) — the claim covers create; append was cited but not exercised. No RSS measurement of the unit-tier client (named gap; the cluster tier's set 2 supplies the real-heap effect).
7. **Core question** — Usage did not follow the constraint. The check fired (writePacketSize clamped to MAX, WARN logged — part 1), but the first packet buffer of every replicated stream was allocated at the configured size C, 2× to 16× MAX, rising with C and independent of MAX (parts 3, 4); only the packets after the first were clamped (positive control, part 3). The real heap demand follows C: a client at 192m dies at C = 256 Mi and succeeds at C = 16 Mi (part 3). The only thing that stops an oversized first packet is a different enforcement point, the DataNode's own `PacketReceiver` check, which fails the write after the client has already allocated the buffer.

**Conclusion (one line):** Unit: B2g row 1 — confirmed (with the positive control, row 3). Cluster: B3g row 1 — confirmed (with rows 3 and 5).

## 5. Self-check of run 1 — AI

Re-read after the run: the surefire `-output.txt` files (the `IFCHK,RESULT` lines and the DN/WARN lines directly, not only `ifchk-*.csv`), `cluster-run.log`, `readings.csv`, client outputs and the DataNode log; and an independent re-read of seven JFR recordings with `jfr print` (text) instead of `jfr-read.py` (`run1/cluster/selfcheck-jfr.txt`), plus a per-event-type count for `s1-65536-f1m`.

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `TestWritePacketSizeCap.txt` 4/0/0, `…4M.txt` 2/0/0; `assertEquals(MAX)` passed in each test; `bam` in each RESULT line; `readings.csv` maxHeap/xmx per run; `cluster-run.log` "ports … free", "Live datanodes (1)", "daemons left:" empty |
| 2. Readings | yes | RESULT lines as tabulated; the 88 KB (d) excess appears in exactly the first test of each JVM (`153152 − 65049`, `8476248 − 8388129`) |
| 3. Matched row | yes | text print: `s1-33554432-f48m` 1 × 32.0 MB + 2 × 16.0 MB; `s1-268435456-f1m/f48m` 1 × 256.0 MB; `s3-8388608-f48m` 1 × 8.0 MB + 11 × 4.0 MB; `s2ctl` 1 × 16.0 MB; `s2` none. Unit `firstBuf` values equal `33 + 516·⌊(C−33)/516⌋` (recomputed: 33553965, 268435101, 8388129) |
| 4. Excluded rows | yes | no first buffer ≤ MAX + 49 for C > MAX in either tier; `s2-268435456-f1m.out` holds `OutOfMemoryError: Java heap space`; DN log counts `uniq -c`: 3 × 33553936, 3 × 50724868 (cluster), plus 3 × 8388100 (unit 4M) |
| 5. Observed vs. inferred | yes | (i) JFR sizes = unit `buf.length` + 16, 8-aligned, for 65049, 16776741, 33553965, 268435101, 4194081, 8388129; (ii) f1m runs have exactly one large buffer except C = 65536 |
| 6. Deviations and gaps | yes | the restarts are recorded in §3 with the attempt logs kept; for `s1-65536-f1m` the JSON re-count shows 16 OutsideTLAB + 1 InNewTLAB events of 65072 B = 17 packets for 1 MiB (⌈1048576/64512⌉ = 17) |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1's refuted-if ("first-packet buffer ≤ MAX + 33 for every C > MAX") is not met at any C in either tier; the positive control moved |

### 5.2 Run 2?

**No** — decided 2026-11-25. The readings are exact byte counts that equal the predictions in every cell, the result confirms the stage-3 estimate (not a refutation or a bypass of a positive claim), the positive control moved in the same streams, both inferred statements are settled by cross-tier agreement, and the discarded attempts of both tiers already repeated every reading.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** **true negative** — estimate `negative`, effect `does not cap` on both tiers.

**Claim tested:** (B1) with `dfs.client-write-packet-size` > `dfs.data.transfer.max.packet.size`, a replicated HDFS output stream still allocates its first packet buffer at the configured size (`33 + 516·⌊(C−33)/516⌋` bytes), above the cap and following C, not MAX; only the packets after the first are capped at about MAX; a write whose first packet fills past MAX fails at the DataNode.
"Confirmed" below always means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (first buffer 33553965 / 268435101 B at MAX 16 MiB and 8388129 B at MAX 4 MiB while `writePacketSize` = MAX; second packet 16776741 / 4194081 B, row 3; big writes with first packet > MAX fail with the DN refusal) | does not cap | run 1 + self-check | 2026-11-25 |
| Cluster | **Confirmed** — B3g row 1 (JFR first `createPacket` buffer 33553984 / 268435120 / 8388152 B; later buffers MAX-sized, row 5; set 2 OOM at C = 256 Mi vs success at 16 Mi with 192m, row 3) | does not cap | run 1 + self-check | 2026-11-25 |

**Note on the Effect field.** The clamp at `DFSOutputStream.java:251` does bind on packets 2..n of a stream (the positive control), so a reader could file the effect as `caps only on some paths (bypass)`, which the outcome-class rule counts as `caps` (→ false negative). It is filed as `does not cap` because the file's own B1 and B2g/B3g define the cap as holding only if the first-packet buffer is ≤ MAX + 33, and because the resource the claim is about — the largest client packet buffer, and the per-stream packet heap it dominates — followed C at every value, not MAX; the "bypass" is the first packet of every replicated create stream, not a side path. Jingsong may overrule this.

**Positive control:** in the same streams and with the same instruments, the packets after the first were clamped to `33 + 516⌊(MAX−33)/516⌋`: 16776741 B (unit) / 16776760 B × 2 (cluster JFR) at C = 32 Mi, MAX 16 MiB; 4194081 B / 4194104 B × 11 at C = 8 Mi, MAX 4 MiB. Set 2-ctl: C = 16 Mi succeeds at the same 192m heap where C = 256 Mi runs out of memory.

**Feedback filed:** section D2 "Stage-4 result" of the amended case file (`~/writeup-hadoop/out/o10/case-amended.md`, 2026-11-25, uncommitted); amendments A1–A7 in the sections they change and in D1. `_INDEX.md`, `queue.csv`, `case-notes.md` and HANDOFF were not edited (left to the parent session).

**Left on the node:** `/mydata/jingsong-s4/dfs.data.transfer.max.packet.size-initWritePacketSize-PacketReceiver.MAX_PACKET_SIZE-run1/` (2.3 MB: `logs/` and `harness/`); the source copy (374 MB) and the cluster folder (1.2 GB: distribution, NN/DN data, JFR files, the 13.7 MB heap dump) were deleted after the logs were copied. No daemon, test JVM, client or driver left (`ps` for NameNode/DataNode/FsShell/surefire/mvn empty; `jps` empty in `cluster-run.log`). Node lock released. Undo: `rm -rf` of that folder.
