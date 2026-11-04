# native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous — stage-4 results  <!-- file: results/native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous.md -->

> **Case:** [`native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous`](../../stage3-ai-deep-read/cases/native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous.md)
>
> **Status:** verdict filed, 2026-10-24. **Unit: Confirmed — caps only on some paths (bypass). Cluster: Confirmed — caps only on some paths (bypass).**
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous/`](../harness/native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-24, on the advisor's machine (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `f361777` (sha256 `5ee9434b…bb95`). Frozen after the step-0 audit's seventeen amendments (2026-10-24): sha256 **`deeefe3fb980bb48836a7dc5a8882b77bea17f09037672ac4a46c9b5c318f9c2`** (new row in `_INDEX.md` §4). Both tiers ran at this version; no runbook fix was needed. Nothing is committed (no commit was asked for). |
| **Harness** | [`../harness/native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous/`](../harness/native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous/): `FrameCapBase.java`, `FrameCap1MiBTest.java`, `FrameCap4MiBTest.java`, `FrameCapDefaultTest.java`, `FrameCap2048MiBTest.java`, `unit-run.sh` (unit); `frame-client.py`, `cluster-run.sh`, `cluster-chain.sh` (cluster). Not committed. Instrument checks before run 1: (i) `unit-run.sh instrument` — the five classes compiled in the run clone and the upstream known-answer test `ProtocolErrorTest` passed, 9 tests, 0 failures (incl. `testBodyLengthOverLimit`, "Request is too big") ([`run1/unit-instrument/`](native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous/run1/unit-instrument/)); (ii) a cluster shakedown, one full start at `2MiB` (`cluster-run.sh cluster-shake s2 2MiB`): every step ran as written, no runbook defect and no harness bug found ([`shakedown/`](native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous/shakedown/)); its readings are not used below. |
| **Tiers and values** | Unit (B2): N = 1, 4, 16 (default, unset) MiB; envelopes with total length N·2^20, N·2^20 + 1, 2·N·2^20 + 9; v5 `extractHeader` control; `2048MiB` rejection. Cluster (B3): one node, K = default (unset → 16 MiB), 2 MiB, 8 MiB (one start each), then a start with `2048MiB`. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-24. |

### 1.1 Design audit

Citations re-read in `~/cassandra-src` at `cassandra-5.0.9` (`git describe --tags`), the same commit as the run clone.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: bytes of one legacy envelope buffered in the decoder's cumulation (direct memory on a node). |
| A. Core question | knob varied, ≥ 3 values incl. default | Not met → Met after amendment | B2b had 1, 4 MiB; B3b 2, 8 MiB; neither had the default. Added (B2a/B2b `FrameCapDefaultTest`; B3b unset start), with read-backs. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | Unit: bytes retained in the cumulation per chunk (the real buffer of the harness). Cluster: NMT `Other` (direct memory) during floods; the metric `BytesReceivedPerRequest` is the check's own neighbour. Defined in the B3d amendment; NMT is sampled at about 1 s, so a peak shorter than a sample can be missed (named). |
| A. Core question | usage driven to the limit and past it | Met | Total = knob (at the limit), knob + 1, 2× / 1.1× / 3×. |
| B. Logic | each step says what it establishes | Partly | Implied by B2g/B3g. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | "max retained ≈ N MiB", "≤ 64 KiB", "well below 8 × 3 × knob" and "max ≤ knob" were not exact; and "max ≤ knob" cannot hold literally for a bucketed histogram (`Max` is a bucket's upper offset, `DecayingEstimatedHistogramReservoir.java:537-549`; B(8 MiB) = 8,409,007 > 8,388,608). Amended (B2f, B3f) with B(K) and the exact counter `BytesReceived`. |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met after amendment | Missing: at-limit rejected, knob not taken, trace differs, control fails, memory part not shown, other failure, startup accepted. Added (B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | Row 1 now needs the rejection message naming the knob, the exact per-chunk retention (unit) and ΔBytesReceived < K plus NMT (cluster). |
| B. Logic | alternative explanations and their controls | Met | v5 control (B2h/B3h); accepted flood as the NMT positive control (B3h, ordered before/after by amendment B3c because pooled arenas keep memory). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1 and the tables read on their own. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Header bytes, chunking, cumulation (B2c); client, concurrency, order (B3c). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | Sampling every 5 s too coarse; no bounds or test for startup "fails" (B3d, B3e amended). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Mapped to this host (§2): clone `$W/cassandra-run5`, node dirs `$W/node-ntmfs`. |
| D. Runnable | workload arithmetic reaches the limit | Met (B4 amended) | Unit buffers ≤ 32 MiB in a 1 GiB test JVM. Cluster: blobs ≤ 48 MiB; v5 1.1× at 16 MiB exceeds `native_transport_max_message_size` (16 MiB at this heap, `DatabaseDescriptor.java:3237-3245`) — stated before the run in B3f. B4's "≤ 1 GB" ignored the accepted flood; bounded by the commit log's total space (B4 amended). |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `DatabaseDescriptor.java:619-626`, `:3153-3161`, `Config.java:284-285`, `DataStorageSpec.java:442-445`, `Envelope.java:197`, `:221-252`, `:343`, `:425-452`, `:478-486`, `PipelineConfigurator.java:265`, `:391`, `ClientMessageSizeMetrics.java:31-34`, `CQLMessageHandler.java:369` match. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone; `FrameCapDefaultTest`, `FrameCap2048MiBTest`, shared helper; one JVM per class | Amendment 2026-10-24 (uncommitted) | CloudLab path; default missing. |
| 2 | B2b: default added; read-back of `getNativeTransportMaxFrameSize()` | Amendment 2026-10-24 | Group A. |
| 3 | B2c: exact header bytes, three Ls, 65,536-byte chunks, heap cumulation with `discardReadBytes()` | Amendment 2026-10-24 | Not exact. |
| 4 | B2d: outcome, chunk index, max(`before`), max(`after`); control observables | Amendment 2026-10-24 | Undefined. |
| 5 | B2e: order and stop conditions | Amendment 2026-10-24 | Open. |
| 6 | B2f: exact values, message, chunk of the rejection; control; `2048MiB` message | Amendment 2026-10-24 | "≈", "≤ 64 KiB". |
| 7 | B2g: five rows added; row 1 needs all B2f items | Amendment 2026-10-24 | Group B. |
| 8 | B2h: the control's scope stated | Amendment 2026-10-24 | Wording. |
| 9 | B3a: this host's node, heap, NMT flag, the node's other limits | Amendment 2026-10-24 | CloudLab paths; B3f needs the v5 limit. |
| 10 | B3b: default (unset) added; settings-table read-back | Amendment 2026-10-24 | Group A. |
| 11 | B3c: client, driver policy, 8 worker processes, phase order (rejected flood before accepted) | Amendment 2026-10-24 | Open; pooled arenas. |
| 12 | B3d: `Max` vs B(K); `BytesReceived` counter; NMT `Other` every 1 s; per-phase reads | Amendment 2026-10-24 | Bucketed histogram; undefined NMT figure. |
| 13 | B3e: sequence, bounds, the test for "fails" | Amendment 2026-10-24 | No bounds. |
| 14 | B3f: exact form; ΔD < 6K; v5 at 16 MiB rejected by `native_transport_max_message_size` | Amendment 2026-10-24 | "Well below", "max ≤ knob". |
| 15 | B3g: definitions and seven rows | Amendment 2026-10-24 | Group B. |
| 16 | B3h: comparison = ΔD | Amendment 2026-10-24 | No observable. |
| 17 | B4: disk estimate including the accepted flood | Amendment 2026-10-24 | "≤ 1 GB" wrong. |
| 18 | B1: say that `BytesReceivedPerRequest` is a bucketed histogram and use the exact `BytesReceived` counter | Left for stage 3 | B1's wording; B3f amended instead. |
| 19 | Measure the per-connection cumulation directly (e.g. a Byteman rule on `ByteToMessageDecoder` cumulation size) rather than NMT `Other` | Left for stage 3 | NMT answered the B3g rows; a direct reading would remove the sampling gap. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-24 (unit 21:08–21:09 EDT; cluster shakedown 21:10–21:14; cluster run 1 21:15–21:27 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM; internal SSD (APFS), 157 GiB free at start, 156 GiB at the end; loopback 127.0.0.1–.3 present (only .1 used); ports 7000, 7199, 9042, 9091 free before and after; no `CassandraDaemon` before or after |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit: junit fork of `ant testsome`. Node: G1, `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`, shipped `jvm-server.options` + `-XX:NativeMemoryTracking=summary`; shipped `jvm11-server.options` (`io.netty.allocator.maxOrder=11`) |
| Ant | 1.10.18 |
| Local `cassandra-src` clone commit | `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`) in `$W/cassandra-run5` (`ant -Dlocal.repository=$W/m2 build-test`, 52 s), `W=~/Library/Caches/stage4`; Python 3.8.11 with the bundled driver 3.29.0 |
| Case-file commit / harness commit | filed `f361777`; amendments and harness uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-ntmfs/{data,commitlog,hints,saved_caches,cdc_raw,logs,conf}`, wiped before and after every start (1.6–6.1 MB of data at drain: the floods overwrite one key per worker) |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/native_transport_max_frame_size-applySimpleConfig/` — `clone.log`, `build-test-run5.log`, `unit-instrument/`, `unit/` (ant logs, JUnit XML, `stage4.out`), `cluster-shake/s2/`, `cluster-run1/` (`chain.log`; per start `default/`, `s2/`, `s8/`: `commands.log`, `client.jsonl`, `flood-{rejected,accepted}.jsonl`, `metrics.txt`, `nmt.txt`, `markers.txt`, `node.out`, `system.log`, `gc.log*`; `startup-2048MiB/`) |

## 3. Runbook defects

None. The cluster shakedown ran every amended step as written.

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command logs:** [`run1/unit/`](native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous/run1/unit/) (`commands.log`, `summary.txt`, `stage4.out`, `junit-testsuite.txt`); [`run1/cluster/`](native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous/run1/cluster/) (`chain.log`; per start `commands.log`, `metrics.txt`, `readback.txt`, `client.jsonl`, `flood-*.jsonl`, `markers.txt`, `nmt-other.txt`, `startup.txt`, `yaml-overrides.txt`, `error-warn-head.txt`; `startup-2048MiB/lines.txt`).

### 4.1 Readings

**Unit tier** (all from `run1/unit/stage4.out`; four JUnit suites, 1 test each, 0 failures, 0 errors)

| N | read-back | envelope (total) | outcome | at chunk (of) | max `before` | max `after` |
|---|---|---|---|---|---|---|
| 1 MiB | 1,048,576 | L1 (1,048,576) | `Envelope`, body 1,048,567, v4 QUERY | 15 (16) | 1,048,576 | 983,040 |
| | | L2 (1,048,577) | `WrappedException(InvalidRequestException)` "Request is too big: length 1048577 exceeds maximum allowed length 1048576." | 16 (17) | 65,536 | 0 |
| | | L3 (2,097,161) | same, "length 2097161 … 1048576." | 32 (33) | 65,536 | 0 |
| 4 MiB | 4,194,304 | L1 (4,194,304) | `Envelope`, body 4,194,295 | 63 (64) | 4,194,304 | 4,128,768 |
| | | L2 (4,194,305) | rejected, "length 4194305 … 4194304." | 64 (65) | 65,536 | 0 |
| | | L3 (8,388,617) | rejected, "length 8388617 … 4194304." | 128 (129) | 65,536 | 0 |
| default | 16,777,216 | L1 (16,777,216) | `Envelope`, body 16,777,207 | 255 (256) | 16,777,216 | 16,711,680 |
| | | L2 (16,777,217) | rejected, "length 16777217 … 16777216." | 256 (257) | 65,536 | 0 |
| | | L3 (33,554,441) | rejected, "length 33554441 … 16777216." | 512 (513) | 65,536 | 0 |
| control v5 | — | L1, L2, L3 at each N | `extractHeader`: `isSuccess=true`, `bodyLength` = L (9 of 9) | — | — | — |
| 2048 MiB | — | — | `ConfigurationException` "native_transport_max_frame_size must be positive value < 2147483647B, but was 2147483647B" | — | — | — |

**Cluster tier** (K in bytes; client lines from `client.jsonl`, metrics from `metrics.txt`/`commands.log`, NMT from `nmt.txt` via `markers.txt`)

| K | read-back | v4 0.5× / 0.9× | v4 1.1× / 3× | ΔBytesReceived 0.9× / 1.1× / 3× / rejected flood (B) | `Max` after v4 + floods (B(K)) | rejected flood: inserts, ΔD | accepted flood: inserts, ΔD | v5 1.1× |
|---|---|---|---|---|---|---|---|---|
| 16,777,216 (default) | `16MiB` | 20/20 OK, 20/20 OK | 20/20 and 20/20 `InvalidRequest` "Request is too big: length 18454993 / 50331704 exceeds maximum allowed length 16777216." | 301,992,314 / 1,314 / 1,314 / 10,584 | 17,436,917 (17,436,917) | 1,122 rejected, 0 OK; ΔD 31 KiB | 1,351 OK; ΔD 426.7 MiB | 20/20 `InvalidRequest` "CQL Message of size 18455005 bytes exceeds allowed maximum of 16777216 bytes" |
| 2,097,152 | `2MiB` | 20/20, 20/20 OK | 20/20, 20/20 rejected, "length 2306923 / 6291512 … 2097152." | 37,751,154 / 1,314 / 1,314 / 10,584 | 1,955,666 (2,346,799) | 18,405 rejected, 0 OK; ΔD 41 KiB | 27,985 OK; ΔD 35.3 MiB | 20/20 OK |
| 8,388,608 | `8MiB` | 20/20, 20/20 OK | 20/20, 20/20 rejected, "length 9227524 / 25165880 … 8388608." | 150,997,374 / 1,314 / 1,314 / 10,584 | 8,409,007 (8,409,007) | 2,676 rejected, 0 OK; ΔD 27 KiB | 4,105 OK; ΔD 213.9 MiB | 20/20 OK |
| `2048MiB` (startup) | — | — | — | — | — | — | — | process exited after 3 s (status 3); "Exception (org.apache.cassandra.exceptions.ConfigurationException) encountered during startup: native_transport_max_frame_size must be positive value < 2147483647B, but was 2147483647B"; no `Startup complete` (`startup-2048MiB/startup.txt`, `lines.txt`) |

NMT samples per flood window: 48–52 (a `jcmd` call takes ≈ 1.2 s). Every rejection is logged by the node as a `WARN … Unknown exception in client networking` with the `InvalidRequestException` (1,162 / 18,445 / 2,716 lines after start at 16 / 2 / 8 MiB; `error-warn-head.txt`).

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — four JVMs, each test ran to the end [observed: `run1/unit/summary.txt`]; read-backs 1,048,576 / 4,194,304 / 16,777,216 equal N·2^20 [observed: `stage4.out`]. Valid.
2. **Readings** — nothing unusual; every value exact. max(`after`) for L1 is N·2^20 − 65,536 (the partly received envelope before its last chunk), which B2f does not constrain [observed].
3. **Matched row** — B2g row 1, "over-limit bodies skipped, error raised — cap works as traced", with the amended items at N = 1, 4, 16: L1 decoded at the last chunk with max retained = N·2^20; L2 and L3 rejected only at the last chunk with the exact message naming N·2^20, max(`before`) = 65,536 (one chunk) and max(`after`) = 0; `2048MiB` refused with the exact message [observed: `stage4.out`].
4. **Excluded rows** — "over-limit body fully retained": max(`before`) 65,536, not the body [observed]. "Over-limit envelope decoded": none [observed]. "2048 MiB accepted": exception [observed]. Added rows: L1 rejected — no; read-back or message ≠ N·2^20 — no; early rejection / other exception — no; control fails — 9/9 success; class not run — none [observed].
5. **Observed vs. inferred** — none load-bearing.
6. **Deviations and gaps** — the decoder is fed by the test, not by Netty's cumulator (B2c as amended mimics it with `discardReadBytes()`); the cluster tier covers the real pipeline.
7. **Core question** — an envelope larger than the knob by one byte is never accumulated: each 64 KiB read is skipped as it arrives and the rejection follows the last byte; an envelope at the knob is buffered whole and decoded. The retained bytes follow the knob exactly (1, 4, 16 MiB) and stop there. The v5 header path carries no such check.

**Conclusion (unit tier):** B2g row 1 — **confirmed**; the v5 control shows the bypass path.

**Cluster tier**

1. **Validity** — every start reached `UN`/`running` (36–39 s) and the read-backs are `16MiB`, `2MiB`, `8MiB`; each rejection message names the same K, so the decoder took the knob [observed: `readback.txt`, `client.jsonl`]; the over-limit phases ran 20 inserts each and the floods had 8 workers each [observed: `client.jsonl`, `flood-*.jsonl`]; each node was drained, stopped and wiped [observed: `commands.log`, `chain.log`]. Valid.
2. **Readings** — the v5 1.1× inserts at 8 MiB (9.2 MB) left `Max` and `BytesReceived` unchanged (Δ 1,363 B) [observed: `metrics.txt`]: these v5 messages are not recorded by either metric, so the histogram line `CQLMessageHandler.java:369` is not on their path [inferred: the message is larger than one v5 frame and goes through the large-message path]. Not a B3f item. The rejected floods made very different numbers of attempts (1,122 / 18,405 / 2,676), i.e. the client's speed at 48 / 6 / 24 MB per insert [observed].
3. **Matched row** — B3g row 1, "v4 over-limit rejected, max ≤ knob — claim confirmed", with the amended items at all three K: 0.5× and 0.9× 20/20 OK; 1.1× and 3× 20/20 `InvalidRequest` "Request is too big … maximum allowed length K."; ΔBytesReceived over the 1.1× and 3× phases 1,314 B and over the rejected flood 10,584 B, all < K, while the 0.9× phase added ≥ 20 × 0.9K; `Max` = the 0.9× message's bucket bound ≤ B(K); ΔD(rejected) 27–41 KiB < 6K (12 / 48 / 96 MiB) and below ΔD(accepted) 35.3 / 213.9 / 426.7 MiB (the B3h control); `2048MiB` start fails with the exact message [observed: `client.jsonl`, `metrics.txt`, `nmt.txt`, `markers.txt`, `startup-2048MiB/`].
4. **Excluded rows** — "v4 over-limit accepted": 0 accepted of 120 single and 22,203 flood attempts [observed]. "NMT grows ≈ 8 × 3 × knob" (ΔD ≥ 12K): ≤ 41 KiB [observed]. "v5 over-limit rejected too" (row 4): only at the default, as B3f predicted, by `native_transport_max_message_size` ("exceeds allowed maximum of 16777216 bytes"); at 2 and 8 MiB 20/20 OK [observed]. Added rows: at-limit rejected — no; knob not taken — no; counted but rejected — ΔBytesReceived < K, `Max` ≤ B(K); memory not shown — ΔD(rejected) ≪ 6K and < ΔD(accepted); other failure — none; `2048MiB` starts — no [observed].
5. **Observed vs. inferred** — that NMT `Other` holds the cumulation buffers [inferred: Netty's direct buffers are allocated with `Unsafe.allocateMemory`, NMT category `Other`; supported by the accepted flood's rise]. The match needs it only for the memory part; the rejection and counter parts are observed directly.
6. **Deviations and gaps** — (i) NMT sampled at ≈ 1.2 s, so a peak shorter than that can be missed; the pooled arenas keep memory once allocated (`maxOrder=11`, 16 MiB chunks), and the accepted floods show that retention, so a rejected flood that had cumulated envelopes would very likely have left a rise. (ii) The node logs each rejection as a WARN with the exception (up to 18,445 lines in a minute) — a log-volume cost of the reject path, not a buffer. (iii) The accepted floods sent 20.4 / 52.8 / 31.0 GB (ΔBytesReceived) at 16 / 2 / 8 MiB, written through the commit log as overwrites of one key per worker; data at drain 1.6–6.1 MB.
7. **Core question** — on protocol v4 the knob is a ceiling: envelopes up to the knob pass, any envelope over it is refused before it is counted or buffered (direct memory flat during a flood of 3× envelopes, rising by tens to hundreds of MiB during a flood of accepted 0.9× envelopes), and this holds at 2, 8 and 16 MiB; values ≥ 2048 MiB stop startup. On protocol v5 the same 1.1× envelope is accepted at 2 and 8 MiB: the knob does not apply there (only `native_transport_max_message_size` does, which bound at 16 MiB).

**Conclusion (cluster tier):** B3g row 1 — **confirmed**; the v5 phase records the bypass.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous/run1/selfcheck.py) (independent of the harness: it re-reads `unit/stage4.out` and the four JUnit XML files; for each cluster start the raw `client.jsonl`, both flood files, the `METRIC` lines of `commands.log`, the **raw `jcmd` NMT dump** `nmt.txt` with `markers.txt`, `startup.txt`; the 2048 MiB start's `node.out` and `system.log`; and `chain.log`; it recomputes the histogram bucket offsets from `EstimatedHistogram.newOffsets`' rule) recomputes every amended B2f/B3f prediction: **136 checks, 0 failed**, exit 0 ([`run1/selfcheck.out`](native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous/run1/selfcheck.out)).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Read-backs, startup, stop and wipe lines, worker counts. |
| 2. Readings | yes | The v5 metric observation re-read in `metrics.txt` (Δ 1,363 B at 8 MiB); it is not used by the matched row. |
| 3. Matched row | yes | Per K: 20/20 outcomes and the K in every message; ΔBytesReceived per phase; `Max` = bucket(0.9K + 56) ≤ B(K), with 56 B the overhead read from the 1.1× messages; ΔD from the raw NMT lines; `2048MiB` message and no `Startup complete`; unit lines exact. |
| 4. Excluded rows | yes | Every rejected-flood worker had 0 OK and only "Request is too big"; v5 at 16 MiB rejected by the message-size limit, at 2 and 8 MiB 20/20 OK. |
| 5. Observed vs. inferred | yes | The NMT attribution is supported by ΔD(accepted) > ΔD(rejected) at every K (checked). |
| 6. Deviations and gaps | yes | Stated; none changes the matched rows. |
| 7. Core question | yes | Knob → rejection message's K → nothing over K counted or buffered; knob not used on v5. |

### 5.2 Run 2?

**No** — decided 2026-10-24. The readings are exact outcomes and counter deltas matched to exact predictions at three values in each tier, the
self-check over the raw files holds with no failures, and the bypass is the one the case file itself predicted (B2h/B3h, scoped Estimate),
not a new finding.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

**Stage-3 estimate:** positive (scoped to protocol v3/v4 and the initial handler; v5 named as not governed).

**Claim tested:** "For protocol v4, an envelope with `bodyLength + 9 > native_transport_max_frame_size` is rejected with "Request is too big"
without buffering it, so the largest inbound request size observed (`ClientMessageSizeMetrics` bytesReceivedPerRequest max) never exceeds the
entry; envelopes at or below it are accepted. Values ≥ 2048 MiB fail startup." (B1; "max ≤ entry" read as `Max` ≤ B(K) per the B3f amendment)

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (row 1: at N = 1, 4, 16 MiB the at-limit envelope is decoded with N·2^20 retained; one byte over is skipped chunk by chunk, 65,536 B retained at most, and rejected at the last byte with the message naming N·2^20; `2048MiB` refused; v5 `extractHeader` accepts all sizes) | caps only on some paths (bypass) | run 1 + self-check | 2026-10-24 |
| Cluster | **Confirmed** (row 1: at 2, 8, 16 MiB, v4 0.5×/0.9× accepted, 1.1×/3× rejected naming K; nothing over K counted (ΔBytesReceived ≤ 10,584 B); `Max` ≤ B(K); direct memory flat (≤ 41 KiB) in the rejected flood vs. 35–427 MiB in the accepted one; `2048MiB` stops startup; v5 1.1× accepted at 2 and 8 MiB) | caps only on some paths (bypass) | run 1 + self-check | 2026-10-24 |

The bypass is protocol v5 (the bundled driver's default and the current version, `ProtocolVersion.java:82`): the knob does not limit a v5
message; `native_transport_max_message_size` does.

**Feedback filed:** the case file's section D (uncommitted); the seventeen step-0 amendments are in the case file, dated, with the frozen
sha256 as a new row in `_INDEX.md` §4; `_INDEX.md` §1 Stage 4 column and the coverage line updated. No section was amended
for a refutation (none occurred).
