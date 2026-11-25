# ipc.server.max.response.size-setupResponse-maxRespSize--autonomous — stage-4 results  <!-- file: results/ipc.server.max.response.size-setupResponse-maxRespSize--autonomous.md -->

> **Case:** [`ipc.server.max.response.size-setupResponse-maxRespSize--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/ipc.server.max.response.size-setupResponse-maxRespSize--autonomous.md) (Jingsong's queue, order 8)
>
> **Status:** verdict filed (run 1 + self-check; no run 2), 2026-11-25
>
> **Outcome class:** true negative — estimate `negative`; unit tier Confirmed (does not cap), cluster tier Confirmed (does not cap)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the case file's feedback section is section D.

Written outside the repository (stage-4 agent, 2026-11-25): this file is `~/writeup-hadoop/out/o8/results.md`; the harness is
`~/writeup-hadoop/out/o8/harness/` (`unit/`, `cluster/`); the amended case file is `~/writeup-hadoop/out/o8/case-amended.md`;
the raw files cited below are under `~/writeup-hadoop/out/o8/logs/node/` (copied from `pc91:/mydata/jingsong-s4/ipc.server.max.response.size-setupResponse-maxRespSize-run1/`, which keeps the same small files).
Nothing in the repository was edited and nothing was committed.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository commit `bef6bc8a6` (file unchanged at HEAD `cd9e1cded`), sha256 as filed `5d19c6129327c6feaeb3cf369ea30d8f0c5e4a1269ab62a42bbcc766a1f514c3` (= `_INDEX.md` §4). After the audit's two dated amendments (below, before any reading): sha256 **`2af7adf26947364a07e270a3af1fb7cfbbeddc47a85392eb2d42b19409766343`** (`case-amended.md` before its section D was filled). This is the frozen version. |
| **Harness** | `harness/unit/TestMaxRespSizeVerification.java` (typed from B2a's outline, with amendment 1), `harness/unit/run-unit.sh`; `harness/cluster/run-cluster.sh`, `harness/cluster/jfrsum.py` (JFR JSON summariser), `harness/cluster/diag-heap.sh` (supplementary diagnostic, not runbook). Not committed (outside the repo by instruction). |
| **Tiers and values** | Unit: K ∈ {1024, 1048576 (default), 67108864} × N ∈ {512 KiB, 4 MiB, 16 MiB} × {protobuf, Writable} path, 3 repetitions. Cluster: K ∈ {1024, 1048576, 67108864} then K = 1024 repeated; 20 × `hdfs dfs -ls /big` (10000 entries, `dfs.ls.limit=10000`) per K; client-cap positive control at 1 MiB / 4 MiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: response bytes and the handler heap allocated to hold them. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b/B3b: 1024, 1048576 (default), 67108864. |
| A. Core question | real resource measured, not only the counter | Met | Unit: per-thread allocated bytes D (`ThreadMXBean`), bytes sent S, received size R; cluster: JFR allocation size, JMX `SentBytes`, heap after GC. The gap (instantaneous peak inside `setupResponse`) is named in B2d/B3d. |
| A. Core question | usage driven to the limit and past it | Met | B2c: responses on both sides of every K; B3c: ≈ 2.6 MB vs 1 KiB / 1 MiB / 64 MiB. |
| A. Core question | positive control (negative estimate) | Met | Unit: Writable-path retained buffer (same key, same server class) — B2g row 4; cluster: client `ipc.maximum.response.length` (B3e step 7). |
| B. Logic | each step says what it establishes | Met | B2e/B3e plus B2h/B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f (±64 KiB / ±5 %, exact C values), B3f (±1 % / ±5 %). |
| B. Logic | every plausible outcome has a conclusions row | Met | B2g/B3g cover confirm, reject/truncate, usage follows K, control fails, WARN never fires, instrument gap. |
| B. Logic | confirmation needs flat usage + direct evidence the check ran | Met | WARN lines (count and printed `response.length`) prove the check ran at each K. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h. |
| C. Specific | a human can follow it from the intro and B1 | Met | |
| C. Specific | an AI can run B2e/B3e without re-deriving the code path | Partly | B2a outline has a bug (amendment 1); `RpcMetrics` has no `sentBytes` getter (noted in amendment 1). |
| C. Specific | knob, values, workload, commands, observables exact | Partly | B3c prose says "5-digit index (200 chars)" but the command pads to 4 digits (199 chars) (amendment 2). |
| D. Runnable | harness and environment prerequisites | Met | Node `pc91` has the 3.4.2 build, JDK 8 and JDK 11 (with `jfr`), Maven. |
| D. Runnable | workload arithmetic reaches the limit | Met | 16 MiB max unit response under a 2 GB surefire heap; cluster ≈ 2.6 MB per listing, 1 GB NN heap, < 1 GB disk. |
| D. Runnable | load-bearing citations spot-checked | Met | `Server.java:3551-3561` (check, WARN, `setResponse` on both branches), `:3564-3581` (Writable path, reset at `:3576`), `:3585-3608` (`new byte[length+4]`), `:3332-3334` (read once), `:262`, `:486-493`; `CommonConfigurationKeys.java:62-67`; `Client.java:1937-1940`; `RpcMetrics.java:121`; `FSDirectory.java:368-371`. All match the pinned source. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a outline, `ProbeImpl.echo`: take A1 only on non-probe calls; as written the probe's own echo overwrites the big call's A1 before D = a2 − a1 is read, so D would measure the probe only. Also note `RpcMetrics.sentBytes` must be read by reflection. | Applied, dated amendment 2026-11-25 in `case-amended.md` B2a (before any reading; found reviewing the harness) | Needed for a valid D on the protobuf path; B2d/B2f/B2g unchanged. |
| 2 | B3c: "5-digit index (200 chars)" → the command gives a 4-digit index, 199-char names. | Applied, dated amendment 2026-11-25 in `case-amended.md` B3c | Each fact stated once and correctly; prediction unchanged. |
| 3 | B3d: `jfr print` without `--json` prints sizes rounded ("2.5 MB"); recommend `--json` for exact `allocationSize`. | Used in the harness; left for stage 3 | Instrument detail; no effect on the design. |
| 4 | B3f: the "Old/humongous after GC.run ±5 %" column is sensitive to whether a handler still references the last listing at GC time (≈ 4 MB); recommend several samples or dropping the column. | Left for stage 3 | See §4.2 part 2. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25 (unit 02:11–02:13 MST incl. instrument check; cluster 02:13–02:18; diagnostic 02:19–02:21) |
| Node | `pc91` (`node0.jason92-326665`), 32 cores, 125 GiB RAM; node lock `/mydata/s4/NODE-LOCK` held 02:07:36–02:21 MST |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-203-generic` |
| JDK | Unit tier and build: OpenJDK `1.8.0_514`; cluster daemons and clients: OpenJDK `11.0.33` (B3a asks for JDK 11 for `jfr`) |
| Build tool | Maven 3.6.3 (no Ant in Hadoop) |
| Local source copy | `copy-source.sh` → `/mydata/jingsong-s4/ipc.server.max.response.size-setupResponse-maxRespSize-run1/src` from `systems/hadoop/source/` at repository commit `cd9e1cded` (clean) |
| Distribution | `cp -a /mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` (built 2026-11-24, environment.md §3) |
| Case-file commit / harness | `bef6bc8a6` + amendments (sha256 above) / harness outside the repo |
| Storage | `/mydata` (local, 753 GB) |
| Full logs | `~/writeup-hadoop/out/o8/logs/` (this machine) and the run folder on `pc91` (8.3 MB kept; source copy, distribution copy and HDFS data deleted) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| — | — | — | None during run 1. The two audit amendments (§1) were made before any reading. | | | |

Deviations that are not defects (equivalent steps):
- B2a "`mvn -pl hadoop-common-project/hadoop-common -am install`" was not run: the node's `~/.m2` already holds every 3.4.2 module from the full build (environment.md §3), and `mvn -pl hadoop-common-project/hadoop-common test` compiled the module and the added test in the local copy.
- B3a "`mvn package -Pdist`" replaced by a copy of the node's already-built distribution (same source, same command, environment.md §4).
- Harness post-processing fix: `jfrsum.py` first matched class names with dots, but JFR's JSON uses slashes (`org/apache/hadoop/ipc/Server`), so the K = 1024 summary printed by the run script showed 0 matching events. Fixed (`replace("/", ".")`) and all four JSON files re-summarised afterwards; the recordings themselves were unaffected (`cluster-out/jfr-*.txt` are the re-summarised files; `cluster-out/run-cluster.log` shows the original K = 1024 output).

## 4. Run 1

**Scope:** both tiers, all values. **Command logs:** `logs/node/unit-out/run-unit.log`, `logs/node/unit-out/mvn-rep{1,2,3}.log`, `logs/node/cluster-out/run-cluster.log`; instrument check `logs/node/unit-check/`.

**Instrument check (before run 1):** one full pass of the unit test (rep `check`, `logs/node/unit-check/maxresp-*.csv`): the Writable positive control moved exactly as B2f predicts (C = 10240 when `response.length` > K, C = N + 31 otherwise), WARN count 2 / 0 as predicted, so the knob reached the server and the reflection/MXBean readings work. Identical numbers to run 1.

### 4.1 Readings

**Unit tier** (`logs/node/unit-out/maxresp-protobuf.csv`, `maxresp-writable.csv`; 3 repetitions, every value identical across repetitions except D2 varying by ≤ 560 bytes; surefire: `Tests run: 2, Failures: 0, Errors: 0` in each `mvn-rep*.log`)

*Protobuf path (target check).* R = N, S per big call identical across K, C = 10240 at every probe.

| N | K | R | S (big + 1 probe) | D1 / D2 (bytes) | WARN (count, length) |
|---|---|---|---|---|---|
| 512 KiB | 1024 | 524288 | 524361 | 536480 / 535784 | 2 × 524326 |
| 512 KiB | 1 MiB | 524288 | 524361 | 526992 / 526856 | 0 |
| 512 KiB | 64 MiB | 524288 | 524361 | 526992 / 526856 | 0 |
| 4 MiB | 1024 | 4194304 | 4194379 | 4205768 / 4205800 | 2 × 4194344 |
| 4 MiB | 1 MiB | 4194304 | 4194379 | 4205448 / 4205800 | 2 × 4194344 |
| 4 MiB | 64 MiB | 4194304 | 4194379 | 4197008 / 4196872 | 0 |
| 16 MiB | 1024 | 16777216 | 16777291 | 16791696 / 16788736–16788760 | 2 × 16777256 |
| 16 MiB | 1 MiB | 16777216 | 16777291 | 16791696 / 16788760 | 2 × 16777256 |
| 16 MiB | 64 MiB | 16777216 | 16777291 | 16780240 / 16779808 | 0 |

Largest D difference across K for one N: 11456 bytes (16 MiB; 0.07 %), 9488 bytes (512 KiB; 1.8 %) — all within B2f's ±64 KiB. The difference appears exactly where the WARN fires.

*Writable path (positive control).* R = N and S identical across K (524358 / 4194374 / 16777286).

| N | K | C1 = C2 | D1 | D2 | WARN |
|---|---|---|---|---|---|
| 512 KiB | 1024 | 10240 | 1068288 | 1067384 | 2 × 524323 |
| 512 KiB | 1 MiB | 524319 | 1049848 | 525696–526256 | 0 |
| 512 KiB | 64 MiB | 524319 | 1049848 | 525368 | 0 |
| 4 MiB | 1024 | 10240 | 8407624 | 8407440 | 2 × 4194339 |
| 4 MiB | 1 MiB | 10240 | 8407536 | 8407472–8408032 | 2 × 4194339 |
| 4 MiB | 64 MiB | 4194335 | 8390200 | 4195384 | 0 |
| 16 MiB | 1024 | 10240 | 33573368 | 33576336 | 2 × 16777251 |
| 16 MiB | 1 MiB | 10240 | 33573368 | 33573336 | 2 × 16777251 |
| 16 MiB | 64 MiB | 16777247 | 33556024 | 16778320 | 0 |

**Cluster tier** (`logs/node/cluster-out/summary.txt`, `lines-*.txt`, `warn-lengths-*.txt`, `jfr-*.txt`, `heap-*.txt`, `histo-after-*.txt`, `pc-*.std*`; NN log `logs/node/logs/hadoop-jason92-namenode-*.log`)

| K | Lines per ls (20 runs) | New `Large response size` lines | ΔSentBytes (20 ls) / ΔNumOps | JFR `setupResponseForProtobuf` allocations | Old-gen used after `GC.run` (before → after loop) |
|---|---|---|---|---|---|
| 1024 | 10001 × 20 | 20, all `2600042 … ClientProtocol.getListing` | 52003864 / 59 | 20 × 2600064 B | 49071K → 47489K |
| 1048576 | 10001 × 20 | 20, all `2600042 … getListing` | 52003864 / 59 | 20 × 2600064 B | 46000K → 47488K |
| 67108864 | 10001 × 20 | 0 | 52003863 / 59 | 20 × 2600064 B | 45993K → 51528K |
| 1024 (repeat) | 10001 × 20 | 20, all `2600042 … getListing` | 52004322 / 62 | 20 × 2600064 B | 46016K → 47491K |

Per `getListing`: `response.length` L = 2600042 bytes (WARN), JFR array allocation 2600064 B (= L + 16-byte array header, 8-byte aligned), ΔSentBytes/20 = 2600193 (L + ≈ 150 B of `getFileInfo` and other small responses).

Positive control at K = 64 MiB: `-D ipc.maximum.response.length=1048576` → exit 1, 0 lines, `ls: RPC response has a length of 2600038 exceeds maximum data length` (`pc-1048576.stderr`); `=4194304` → exit 0, 10001 lines.

Supplementary diagnostic (not runbook; `logs/node/cluster-out/diag/diag-heap.log`, `histo-d*.txt`), same namespace, 20 ls each: K = 64 MiB → 45634K; K = 1024 → 49666K, with 10001 `HdfsFileStatusProto` + 10001 `FsPermissionProto` still live in the histogram; K = 64 MiB → 46658K. 20 more WARN lines at K = 1024 only.

### 4.2 Conclusion and logic

1. **Validity.** Valid. Each K reached the server: WARN present at K = 1024 and 1 MiB, absent at 64 MiB, on both tiers [observed: `maxresp-*.csv` warn columns; `cluster-out/summary.txt` warn_new]; on the Writable path the retained buffer follows K exactly [observed: `maxresp-writable.csv` C1/C2]. The limit was reached and exceeded on both sides of each K (responses 512 KiB–16 MiB unit, 2.6 MB cluster) [observed: WARN lengths]. Hold-fixed settings: one handler and fresh server per (K, N) in the unit tier [observed: test source, `harness/unit/`]; same namespace and `dfs.ls.limit=10000` for every K, NN restarted per K [observed: `run-cluster.log` restart lines and `lines-*.txt` = 10001].
2. **Readings.** (a) Protobuf D is ≈ 9–11 KiB higher where the WARN fires [observed: csv]; consistent with building the log string and log4j event [inferred: it appears at K = 1 MiB for N = 4 MiB but not N = 512 KiB, i.e. it tracks the WARN, not K]. (b) Cluster old-gen after GC at K = 64 MiB was 51528K vs ≈ 47490K elsewhere (+8.5 %, outside B3f's ±5 % column) [observed: `heap-after-*.txt`]. The diagnostic shows the ≈ 4 MB difference moves between K values from one run to the next (high at K = 1024 in `diag`, low at both 64 MiB runs) and consists of one still-referenced listing (10001 `HdfsFileStatusProto`) [observed: `diag/histo-d2-K1024.txt`], not response buffers; it does not follow K [inferred from the three diag readings]. (c) The K = 1024 repeat had 3 more RPCs (62 vs 59 ops) and 459 more bytes sent; per-`getListing` values are identical [observed: `summary.txt`].
3. **Matched row.** Unit, B2g row 1: "Protobuf path: R = N, S and D the same across K, C stays 10240, WARN only when length > K" — R = N; S identical; D within 11.5 KiB (≤ 1.8 %) across K; C = 10240; WARN exactly when `response.length` > K. Together with B2g row 4 (Writable C = 10240 exactly when length > K, ≈ N + 31 otherwise: control moves) and row 7 (large D on both paths, K-independent on the protobuf path). Cluster, B3g row 1: "Listing complete, SentBytes and JFR allocation size equal across K; WARN only at 1024 and the default; positive control fails at 1 MiB" — 10001 lines × 20 at every K; ΔSentBytes 52003864 / 52003864 / 52003863; JFR 20 × 2600064 at every K; WARN 20 / 20 / 0 / 20; control fails at 1 MiB and succeeds at 4 MiB.
4. **Excluded rows.** Unit: row 2 (R < N or failure when N > K) — R = N in all 108 big calls (3 reps × 2 paths × 9 (K, N) × 2); row 3 (D or S shrinks as K falls) — S identical, D slightly *larger* at small K and within tolerance; row 5 (C does not change with K) — C changes; row 6 (WARN never at K = 1024) — WARN at every N. Cluster: row 2 (fewer lines / RPC error at small K) — 10001 always; row 3 (ΔSentBytes or JFR size falls with K) — equal to the byte; row 4 (WARN count does not change with K) — 20 vs 0; row 5 (control does not fail at 1 MiB) — it failed; row 6 (no JFR events) — 20 per K.
5. **Observed vs. inferred.** The conclusion depends on: (i) D is a fair proxy for the per-call heap used to build and hold the response (B2d names the gap) — supported by the Writable path, where the same instrument shows ≈ 2N vs ≈ N exactly as the source predicts; (ii) the extra ≈ 10 KiB of D at small K is WARN-string building — inferred from where it appears; (iii) the K = 64 MiB heap outlier is not K-dependent — inferred from the diagnostic.
6. **Deviations and gaps.** No runbook defects; build steps replaced by the node's equivalent build (§3); JFR summariser fixed in post-processing (§3); heap column outside ±5 % once (part 2b), not a B3g row. The instantaneous peak heap inside `setupResponse` is not observed directly (as the design states).
7. **Core question.** Usage did not follow the constraint: on the path every HDFS/YARN daemon uses (protobuf), the response size, the bytes sent and the per-call allocation (unit D, cluster JFR 2600064 B per call) are the same at K = 1 KiB, 1 MiB and 64 MiB, and responses far above K are sent whole (parts 3–4). The key only decides whether `Large response size` is logged; its one memory effect is on the Writable path's retained thread-local buffer after a call, which it trims to 10240 bytes — and that makes the per-call allocation larger, not smaller (D2 ≈ 2N at K below the response vs ≈ N above). It does not cap usage.

**Conclusion (one line):** Unit B2g row 1 (with control row 4) — confirmed; cluster B3g row 1 — confirmed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read both CSVs (warn columns, C values), `summary.txt` (warn_new 20/20/0/20), `run-cluster.log` (each K set in `core-site.xml` and NN restarted), `lines-*.txt` (20 × 10001 each). |
| 2. Readings | yes | Re-read `heap-after-*.txt` (47489K/47488K/51528K/47491K), `diag/diag-heap.log` (45634K/49666K/46658K) and `diag/histo-d2-K1024.txt` (10001 `HdfsFileStatusProto`). |
| 3. Matched row | yes | Re-read B2g/B3g in `case-amended.md`; every clause has a reading in §4.1. |
| 4. Excluded rows | yes | Each of B2g rows 2, 3, 5, 6 and B3g rows 2–6 has a contradicting reading; the Refuted rows (B2g 2–3, B3g 2–3) are addressed. |
| 5. Observed vs. inferred | yes | The inferred statements do not decide the verdict: the cluster JFR allocation (2600064 B at every K) and SentBytes are direct and give the same answer as D. |
| 6. Deviations and gaps | yes | NN log re-read: 81 WARN lines = 1 (workload step) + 20 + 20 + 0 + 20 + 20 (diag K = 1024); all `2600042 … getListing`. `pc-1048576.stderr` re-read. |
| 7. Core question | yes | B1's refuted-if (size, bytes sent or allocation move with K, or a response > K rejected/truncated) is contradicted by every reading. |

### 5.2 Run 2?

**No** — 2026-11-25. Every load-bearing reading is observed and exact (identical across 3 unit repetitions and the cluster repeat); the result confirms the file's own claim, not a refutation or a bypass.

## 6. Run 2 — not done

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap).

**Claim tested (B1):** Changing `ipc.server.max.response.size` (1 KiB, 1 MiB, 64 MiB) does not change the size of any RPC response a Hadoop IPC server builds and sends, nor the heap allocated per call to build it; at the target check it changes only whether `Large response size` is logged.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g row 1 (protobuf path flat across K; WARN only when length > K), positive control row 4 moved | does not cap | run 1 + self-check | 2026-11-25 |
| Cluster | Confirmed — B3g row 1 (10001 entries, SentBytes and JFR allocation equal across K, WARN 20/20/0, client cap fails at 1 MiB) | does not cap | run 1 + self-check | 2026-11-25 |

**Positive control:** unit — the Writable-path retained buffer (same key, same `Server` class) was 10240 bytes exactly when `response.length` > K and N + 31 otherwise; cluster — the same 2.6 MB listing was rejected by the client cap `ipc.maximum.response.length=1048576` (`RPC response has a length of 2600038 exceeds maximum data length`) and returned whole at 4194304.

**Feedback filed:** section D of `~/writeup-hadoop/out/o8/case-amended.md` (outside the repo; the repository case file is untouched); amendments 1–2 in B2a and B3c of the same file. `_INDEX.md`, `queue.csv` and `HANDOFF-Jingsong.md` not edited (by instruction).
