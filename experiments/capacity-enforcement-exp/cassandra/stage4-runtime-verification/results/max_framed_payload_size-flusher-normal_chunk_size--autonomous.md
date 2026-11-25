# max_framed_payload_size-flusher-normal_chunk_size--autonomous — stage-4 results  <!-- file: results/max_framed_payload_size-flusher-normal_chunk_size--autonomous.md; written outside the repo at ~/writeup-ext/out/o132/results.md -->

> **Case:** `max_framed_payload_size-flusher-normal_chunk_size--autonomous` (stage-3 order 132, extension set, band B; filed case file `experiments/capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/max_framed_payload_size-flusher-normal_chunk_size--autonomous.md`; the amended copy is `~/writeup-ext/out/o132/case-amended.md`, outside the repo)
>
> **Status:** verdict filed (2026-11-25). Run 1 is done at both tiers and self-checked. There is no run 2.
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap`; both tiers Confirmed). See the [definition](../../../stage4-runtime-verification/README.md#outcome-class).
>
> **Agent:** autonomous (the suffix of the case-file stem). Below, "§9a" means each tier's predictions and readings table: B2f/B2g for the unit tier and B3f/B3g for the cluster tier. "§9b–§9e" means B2a–B2e or B3a–B3e. The case file's feedback section is section D. The run was done as Jingsong by a fresh stage-4 agent. Earlier interrupted attempts (2026-11-24) left no run folder on `ms0625`, and their draft (`~/writeup-ext/out/o132/max_framed_payload_size-…--autonomous.md`, identical to the filed file) was not used.

## 1. Before run 1: design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed at repo commit `bef6bc8a6`; repo HEAD at the audit `cd9e1cded`. sha256 as filed: `13d77aa74b4d16e870ba1dda96c59f05d9aa01f6cef8bb463a700c4374041274` (matches `_INDEX.md` §4). **The audit added two dated amendments before any reading** (2026-11-25: the `nopause` argument for B3e step 8, and a clarification of the B2f LZ4 `dSize` line). **sha256 after them, frozen: `d5a479e58cb748087acdf4431bd55aa1b3b80f85360ad602203a3cb2307633d7`.** A runbook-defect fix (§3 #1) was then added before the cluster tier restarted. sha256 with that fix: `cb67bdde2ab9ad7f3509dc4343400aebd49623a4b49891cb7359e0c3667465ee`. For the hash with section D filled, see §8. B1, B2f, B2g, B3f and B3g are unchanged by any amendment. |
| **Harness** | `~/writeup-ext/out/o132/harness/`, not committed (md5): `FlusherProbe.java` `134f0b7c…` (verbatim from B2a), `ClusterProbe.java` `ec2d9623…` (B3a + the `nopause` amendment + the defect-1 fix; as filed: `ClusterProbe.java.asfiled` `c9696d6c…`), `pause-proxy.py` `10d13eab…` (verbatim), `Flusher-patch.java.txt` `68ce6381…` (the shared test patch, verbatim), `build.sh` `e8574445…`, `unit.sh` `e725a3b1…`, `cluster.sh` `d22c8f78…`, `smoke.sh` `1999055d…` (the defect-1 fix check only), `summarize_unit.py` `988494d2…` and `summarize_cluster.py` `76354b1e…`. |
| **Instrument checks** | **Patch:** the built jar's `Flusher.class` is dated after the patch, and `Flusher.java` sha256 is `f8811506…` after the patch. The node logged `MAX_FRAMED_PAYLOAD_SIZE=<K>` from its own `Native-Transport-Requests-1` thread for each K (`raw/cluster/cluster.csv` `KLINE` rows). **Unit known-answer** (`raw/unit/instrument-check.log`): N = 1 MiB crc, K unset → `K=131060, frames=9, maxFrame=131064, wire=1048675, dUsed=1048768, AFTER_RELEASE 0`; K = 16384 → `frames=65, wire=1049235, dUsed=1180064`. Both are byte-exact to hand computation: `wire = N+9+10F`; `dUsed = (F−1)·roundUp(K+4) + roundUp(last+10)`, that is 8·131072+192 and 64·18432+416. **Cluster:** the probe-fix smoke test (`raw/cluster/smoke.log`, M = 4, hold 2 s, not a reading) gave `RESULT,ok,responses=4`, with held `UsedSize` 14.3 MB and after 0. |
| **Tiers and values** | **Unit (B2):** K ∈ {unset = 131060, 65536, 16384, 4096} × N ∈ {1, 4, 16 MiB}, crc, cache 512 MiB, 3 reps each (36 runs). Positive control: K unset, N = 16 MiB, cache 4 MiB (3 reps). LZ4: K unset and 16384, N = 4 MiB (3 reps each). 45 JVMs in all. **Cluster (B3):** 64 rows of 4 MiB loaded once. Reads through the pausing proxy, M = 32 at each K (3 reps each). Positive control 1: M = 64. Positive control 2: `networking_cache_size: 32MiB`. Unpaused control: `nopause`. 21 reads, 5 node starts. |
| **Audit bottom line** | **Ready after amendments** (2026-11-25) |

### 1.1 Design audit

Estimate: **negative**. K = `Flusher.MAX_FRAMED_PAYLOAD_SIZE` sets only the per-frame slice of outbound CQL v5 responses. Outbound off-heap usage follows response bytes × pending responses.

Citations spot-checked against the pinned source (`systems/cassandra/source/`, `cassandra-5.0.9`, `git status` clean):
- `Flusher.java:43-49` (`logger` is declared before the constant, so the patch's static block compiles), `:98-130`, `:148-206`
- `FrameEncoder.java:31-140`
- `FrameEncoderCrc.java:33-96`
- `FrameEncoderLZ4.java:36-41, 76-110` (the compressed-≥-uncompressed fallback)
- `BufferPool.java:128, 233-292, 385, 820-892, 904-950, 1600-1605`
- `BufferPools.java:37-49`
- `BufferPoolMetrics.java:26-40`
- `PipelineConfigurator.java:139` (a `grep` for `isWritable`/`channelWritabilityChanged` under `transport/` finds nothing)
- `SimpleClient.java:67, 187-245, 310-345`
- `DatabaseDescriptor.java:319-365, 3796-3804`
- `Config.java:288, 493-494`
- `Envelope.java:71, 82`
- `QueryOptions.java:62`
- `QueryMessage.java:82`
- `CBUtil.java:60`

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1 and A2: off-heap bytes of the networking `BufferPool` holding outbound v5 frames. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | K is a constant. The B "shared test patch" adds a `-D` that can only lower it. Four values (131060, 65536, 16384, 4096), 32× span, at both tiers. |
| A. Core question | real resource measured, not only the check's counter | Partly | K has no counter of its own. The readings are the pool's own accounting (`usedSizeInBytes`, `sizeInBytes`, `overflowMemoryInBytes`). The cluster tier adds `java.nio` direct `MemoryUsed`, NMT "Other" and RSS. Gap named in B2d/B3d: the Netty arena memory for response bodies is not observed. |
| A. Core question | usage driven to the limit and past it | Met | Every response is ≫ K (1–16 MiB unit, 4 MiB cluster), so the large-message branch `Flusher.java:152` is always taken. |
| A. Core question | positive control for a negative estimate | Met | `networking_cache_size` binds the pooled part (unit 4 MiB, cluster 32 MiB), and N/M doubling shows the instruments move. |
| B. Logic | mapped "How this verifies" block | Met | Hypothesis B1; test B2b–e / B3b–e; prediction B2f / B3f; refuted-if = B2g rows 2–3, B3g row 2. |
| B. Logic | prediction in numbers | Met | B2f gives exact dUsed per cell (±1 allocation unit). B3f gives Δ bands in MiB per K. |
| B. Logic | every plausible outcome has a row | Partly | Rows exist for confirmed, refuted (bounded or ∝ K), instrument broken, control failed, kernel absorbed the load, wrong K and timeout. There is no row for "AFTER_RELEASE negative" (see §4.1 deviation 1). Left as a recommendation. |
| B. Logic | confirmation needs ceiling-follows-knob and disallow evidence | Met (negative form) | For "does not cap": usage follows N/M and not K, every frame is produced (`frames = F`) and every response is delivered (`RESULT,ok`). There is no disallow branch to fire (A3.5). |
| B. Logic | alternatives and their controls | Met | B2h and B3h: fresh JVM per run, release check, unpaused control, Send-Q accounting, random data. |
| C. Specific | a human can follow it | Met | A3 and B1. |
| C. Specific | an AI can run it without re-deriving | Partly → Met | B3e step 8 offered no runnable way to skip the pause. The `nopause` argument was added (amendment 1). |
| C. Specific | values, commands, observables exact | Met | Commands, JVM options, sample points and hold window are exact. |
| D. Runnable | prerequisites exist or are listed | Met | `ms0625`: JDK 11.0.33, Ant 1.10.12, a built `/mydata/s4/cassandra-base`. Probes and the patch are step-1 work. (The base copy lacks `src/`, `test/` and `.build/`; see §2.) |
| D. Runnable | workload arithmetic | Met | 291 MB data. Peak Δ 254 MiB < 512 MiB pool < 1 GiB `MaxDirectMemorySize`. 27 GB free on `/mydata`. 61 GiB available RAM. |
| D. Runnable | load-bearing citations spot-checked | Met | All match. B2a's probe compiles against the pinned classes. Note: the B3a probe's *client* side was not runnable as written (§3 #1). The audit missed this; it appeared only at run time. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Give `ClusterProbe` a way to skip the pause for B3e step 8 (`nopause`, same 5000 ms hold) | **Applied**, amendment 2026-11-25 next to B3e step 8 and in B3a | The step could not run as written. |
| 2 | B2f LZ4 K = 131060: `dSize − dOverflow` grows in 8 MiB macro chunks (`BufferPool.java:385`), and the pre-compression input buffer is pooled. Read "≈ 0 for frames" from `dUsed − dOverflow`. | **Applied** (clarification), dated, next to the B2f line | Removes an ambiguity in how to read a prediction. The prediction is unchanged. |
| 3 | B2g: add a row for a negative `AFTER_RELEASE` on unpooled buffers | Not applied (stage 3) | Found only from readings, so it cannot be changed now (§4.1 deviation 1). |
| 4 | B3f: the drain correction is `D·roundUp(K+4)/(K+4)` pool bytes, not `D` | Not applied (stage 3) | Bands hold either way; see §4.2. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25 (UTC). Lock 08:20:43Z; build 08:21–08:30Z; unit tier 08:31:07–08:33:41Z; cluster attempt 1 (defect) 08:33:59–08:44:16Z; fix and smoke 08:45–08:46Z; cluster tier 08:46:32–08:56:03Z; lock released 08:57:24Z. |
| Node | `ms0625` = `node0.jason92-326377.misconfiguration-pg0.utah.cloudlab.us`, **aarch64** (Utah m400), 8 cores, 62 GiB RAM (61 GiB available at start). Lock `/mydata/s4/NODE-LOCK` held throughout. |
| OS and kernel | Ubuntu 22.04.1 LTS, `5.15.0-191-generic` |
| JDK | OpenJDK 11.0.33 (`11.0.33+9-post-1ubuntu1-22.04.1-Ubuntu`), arm64 |
| Ant | 1.10.12 |
| Local copy | `/mydata/jingsong-cass-s4/o132/src` = `cp -a /mydata/s4/cassandra-base`. That base holds a built tree **without `src/`, `test/` or `.build/`**, so the pinned `systems/cassandra/source/` tree (repo HEAD `cd9e1cded`, `cassandra-5.0.9`, `git status` clean) was rsync'd over it, excluding `build/`. The patch was then applied, followed by `ant -Dno-checkstyle=true jar` (3 min 29 s, `BUILD SUCCESSFUL`). Nothing was built in the repository. |
| Case-file / harness commit | Case file outside the repo (sha256 in §1). Harness not committed. |
| Storage | `/dev/mapper/emulab-node0--bs` on `/mydata`, 39 GB, 27 GB free. Node data was in `/mydata/jingsong-cass-s4/o132/data` (291 MB, deleted). |
| Unit JVM | `conf/jvm-clients.options` + `jvm11-clients.options`, `-XX:MaxDirectMemorySize=2g` (B2a `CJ`) |
| Node JVM | `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`, `JVM_EXTRA_OPTS="-XX:MaxDirectMemorySize=1g -XX:NativeMemoryTracking=summary [-Dcassandra.test.max_framed_payload_size=K]"` (scoped to `bin/cassandra`). Ports 7000/7199/9042, proxy 19042, all free beforehand. `net.ipv4.tcp_wmem = 4096 16384 4194304`. |
| Full logs | `~/writeup-ext/out/o132/raw/`: `unit/` (`unit.csv`, `unit.log`, `instrument-check.log`, `build.log`, `unit-summary.csv`); `cluster/` (`cluster.csv`, `cluster.log`, `cluster-summary.csv`, `smoke.log`, `cluster/{read,held}-*.txt|log`, `load.log`, `proxy.log`, `out-*.log`); `cluster-attempt1/` (the failed first attempt); `node-logs/` (all node logs, `node-system/system.log.gz`, `cassandra.yaml.used`, `Flusher.java.patched`). Small logs also remain on the node in `/mydata/jingsong-cass-s4/o132/` (5.4 MB). |

**Environment deviations (none changes B1):**
1. The copy is `cp -a` of the base plus an rsync of the pinned source, not a plain `rsync -a <source>/` (B2a). The patched classes were built with `ant jar` as written.
2. The node is aarch64; no x86 node was used. Frame sizes and pool units are architecture-independent (Java code).
3. The held-window `ss`/`jcmd`/RSS readings were taken by the driver 2.5 s after the pause flag appeared, within B3e's "about 2–4 s".

## 3. Runbook defects

| # | Step | Problem | Fix | Effect |
|---|---|---|---|---|
| 1 | B3e step 4 (B3a `ClusterProbe`, client side) | Every `read` timed out on the warm-up `SELECT` (`RuntimeException: timeout`, `NullPointerException` at `ClientMetrics.markRequestDiscarded` via `CQLMessageHandler.processFirstFrameOfLargeMessage:553`; `raw/cluster-attempt1/cluster/read-*.log`). In a client-mode JVM, `clientInitialization()` never sets the cached `nativeTransportMaxMessageSizeInBytes` (only `applySimpleConfig`, `DatabaseDescriptor.java:903-918`), so it stays 0. SimpleClient's own handler then rejects every multi-frame response (`CQLMessageHandler.java:550-553`). The load phase worked (requests outbound, small responses). | One line in the probe: `DatabaseDescriptor.setNativeTransportMaxMessageSizeInBytes(256L << 20)` after `clientInitialization()`. Client only; the node is unchanged. Recorded in the case file (dated, next to B3a). | B3f/B3g unchanged. The cluster tier restarted from step 1 with fresh data. Attempt 1 produced no readings: no `SAMPLE` rows (`raw/cluster-attempt1/cluster.csv`). |
| 2 | B3e step 8 | Not runnable as written (no skip-pause option) | Audit amendment 1 (§1) | Found at audit, before run 1. |
| — | build (`environment.md` copy) | `cp -a /mydata/s4/cassandra-base` has no `src/`, `test/`, `.build/`, so `ant jar` failed twice (`build-resolver.xml` missing; `test/anttasks` missing) | rsync of the pinned source tree | Environment, not the case (§2 deviation 1). |

## 4. Run 1

### 4.1 Readings

**Unit tier** (`raw/unit/unit.csv`, summarized in `raw/unit/unit-summary.csv`). All 3 repetitions of every cell gave identical numbers. The `K` column is `Flusher.MAX_FRAMED_PAYLOAD_SIZE` as the JVM reports it.

| K (reported) | N | frames F | maxFrame | wire (= N+9+10F?) | dUsed (B) | dUsed/N | B2f dUsed (exact) | AFTER_RELEASE |
|---|---|---|---|---|---|---|---|---|
| 131060 | 1 MiB | 9 | 131064 | 1048675 ✓ | 1,048,768 | 1.0002 | 1,048,768 | 0 |
| 131060 | 4 MiB | 33 | 131064 | 4194643 ✓ | 4,194,912 | 1.0001 | 4,194,912 | 0 |
| 131060 | 16 MiB | 129 | 131064 | 16778515 ✓ | 16,781,312 | 1.0002 | 16,781,312 | 0 |
| 65536 | 1 MiB | 17 | 65540 | 1048755 ✓ | 1,081,472 | 1.0314 | 1,081,472 | 0 |
| 65536 | 4 MiB | 65 | 65540 | 4194963 ✓ | 4,325,792 | 1.0313 | 4,325,792 | 0 |
| 65536 | 16 MiB | 257 | 65540 | 16779795 ✓ | 17,303,552 | 1.0314 | 17,303,552 | 0 |
| 16384 | 1 MiB | 65 | 16388 | 1049235 ✓ | 1,180,064 | 1.1254 | 1,180,064 | 0 |
| 16384 | 4 MiB | 257 | 16388 | 4196883 ✓ | 4,720,640 | 1.1255 | 4,720,640 | 0 |
| 16384 | 16 MiB | 1025 | 16388 | 16787475 ✓ | 18,882,560 | 1.1255 | 18,882,560 | 0 |
| 4096 | 1 MiB | 257 | 4100 | 1051155 ✓ | 1,574,912 | 1.5020 | 1,574,912 | 0 |
| 4096 | 4 MiB | 1026 | 4100 | 4204573 ✓ | 6,301,696 | 1.5024 | 6,301,696 | 0 |
| 4096 | 16 MiB | 4103 | 4100 | 16818255 ✓ | 25,202,752 | 1.5022 | 25,202,752 | 0 |

`dOverflow = 0` in all 36 main runs. For every K, dUsed(16 MiB)/dUsed(4 MiB) is between 3.9996 and 4.0005, so it is linear in N. F matches B2f's 33/65/257/1026 at N = 4 MiB.

| Control cell | Reading | B2f prediction |
|---|---|---|
| Positive control: K unset, N = 16 MiB, cache 4 MiB | `dUsed = dOverflow = dSize = 16,778,515`; `dSize − dOverflow = 0`; frames 129, maxFrame 131064; `AFTER_RELEASE −768` | pooled ≤ 4 MiB ✓, overflow ≥ 12 MiB ✓, total ≈ 16 MiB as with 512 MiB ✓ |
| LZ4, K unset, N = 4 MiB | frames 33, maxFrame 131072, `dOverflow = 4,194,304` (32 × 131072), `dUsed = 4,194,720` (+416 pooled: the small last frame), `dSize = 12,582,912` (`dSize − dOverflow` = 8 MiB = one macro chunk, as in amendment 2); `AFTER_RELEASE −16,928` | F = 33 ✓, overflow ≈ 4.0 MiB ✓, pooled frames ≈ 0 ✓ (32 of 33 frames unpooled, not all 33) |
| LZ4, K = 16384, N = 4 MiB | frames 257, maxFrame 16396, `dOverflow = 0`, `dUsed = 4,718,624` (1.125 N); `AFTER_RELEASE 0` | pooled ✓, overflow ≈ 0 ✓, ≈ 4.5 MiB ✓ |

**Deviation 1 (AFTER_RELEASE negative in two control cells).** B2g's last row reads "`AFTER_RELEASE dUsed` ≠ 0 → leak in the probe harness; the run is invalid". The two negative values are not leftover buffers. They are an exact accounting asymmetry in Cassandra's `BufferPool`, read from the source:
- For an unpooled (overflow) buffer, `LocalPool.putUnusedPortion` subtracts the trimmed tail from `overflowMemoryUsage` (`BufferPool.java:880-885`, `chunk == null` branch).
- `BufferPool.put` later subtracts the buffer's full `capacity()` (`:241-247`), and that capacity was never reduced.
- Predicted drift: crc at cache 4 MiB, 128 full frames × (131070 − 131064) = −768 ✓. LZ4, 32 frames × (131601 − 131072) = −16,928 ✓.
- The same drift appears in the cluster tier: positive control 2 gives −4,500 per read = 750 overflow frames × 6 B (93.74 MiB / 131072 ≈ 750); positive control 1 gives −18/−12.
- Every cell with only pooled buffers gives exactly 0.

So the row's purpose (detect buffers left held by the probe) is met: nothing is left held, and the counter is over-decremented. The row text cannot be edited after readings. This is recorded as a deviation and as stage-3 feedback (§8). The main matrix, which carries the verdict, is unaffected (0 in all 36 runs).

**Cluster tier** (`raw/cluster/cluster.csv`, summarized in `raw/cluster/cluster-summary.csv`). Δ = held − baseline networking `UsedSize`. D = server Send-Q on port 9042 in the held window.

| Run | K in `system.log` | Δ, reps 1/2/3 (MiB) | B3f band | Send-Q D (MiB) | held `Size − OverflowSize` / `OverflowSize` (MiB) | after − baseline (B) | RESULT |
|---|---|---|---|---|---|---|---|
| K = 131060, M = 32 | 131060 | 125.64 / 125.64 / 125.64 | 124–128 ✓ | 2.37 | 392 / 0 | 0 | ok, 32 |
| K = 65536 | 65536 | 129.44 / 129.50 / 129.44 | 128–132 ✓ | 2.36–2.42 | 256 / 0 | 0 | ok, 32 |
| K = 16384 | 16384 | 141.23 / 141.23 / 141.27 | 140–144 ✓ | 2.40–2.43 | 144 / 0 | 0 | ok, 32 |
| K = 4096 | 4096 | 186.37 / 186.37 / 186.32 | 186–192 ✓ | 3.86–3.87 | 256 / 0 | 0 | ok, 32 |
| PC1: M = 64 | 131060 | 253.66 / 253.66 / 253.54 | 250–256, ≈ 2× ✓ (2.019×) | 2.36–2.42 | 512 / 0.25–0.37 | −18/−18/−12 | ok, 64 |
| PC2: cache 32 MiB | 131060 | 125.64 / 125.64 / 125.64 | pooled ≤ 32 ✓, overflow ≥ 90 ✓, Δ 124–128 ✓ | 2.36–2.39 | **32.00 / 93.74** | −4500 ×3 | ok, 32 |
| Unpaused (M = 32) | 131060 | 0.00 / 0.00 / 0.00 | 0–8 ✓ | 0 | 512 / 0 | 0 | ok, 32 |

- `KCHECK` matched the intended K for all five node starts. The lines come from the node's `Native-Transport-Requests-1` thread.
- Supporting readings, rep 1 (`raw/cluster/cluster/held-*.txt`), NMT "Other" committed:
  - K = 131060: 510,909 KB, which includes the baseline residue below
  - K = 65536: 346,959 KB
  - K = 16384: 224,036 KB
  - K = 4096: 338,726 KB
  - PC2: 205,291 KB
  - PC1: 651,101 KB
  - RSS 2.9–3.5 GB
  - `java.nio` direct `MemoryUsed` rises with `Size` in every held sample (e.g. 52.9 → 313.3 MB at K = 4096).
- 0 `^ERROR` lines in the node's `system.log` over all starts (`raw/node-logs/node-system/system.log.gz`). 0 exceptions in the 21 read logs.

**Observation outside the claim (baseline residue).** In the first node JVM, the only one that served the load phase (64 prepared inserts of 4 MiB over v5), the networking pool's `UsedSize` stood at **268,518,368 B (= 64 × 4 MiB + 81 KiB)** at every baseline and every `after`, across 9 reads over ~6 minutes. Every later node start (no load) had baseline 0. Reads release their frames fully (after = baseline), so the residue comes from the **inbound large-message (write) path**. That is not K's path, and it does not affect Δ. The cause was not traced. It is listed for stage 5 (§8).

### 4.2 Conclusion and logic

**Unit tier.**
- **Validity:**
  - Patch effective: the reported K differs per run and maxFrame = K + 4.
  - Instruments byte-exact on the known-answer check.
  - Fresh JVM per run.
  - Release check 0 on all pooled-only cells; deviation 1 explained.
- **Readings:**
  - dUsed equals B2f's exact prediction in all 12 main cells, 3/3 repetitions.
  - dUsed/N is 1.000, 1.031, 1.125 and 1.502 for K = 131060, 65536, 16384 and 4096: usage **rises** as K falls.
  - Usage is linear in N at every K.
- **Matched row:** B2g row 1, "dUsed ≈ N·roundUp(K+4)/(K−6) for all K; linear in N; maxFrame = K+4 → Claim confirmed".
- **Excluded rows:**
  - Row 2 (bounded by ~2K): at K = 4096, dUsed = 25.2 MB ≫ 8 KB.
  - Row 3 (falls ∝ K): it rises.
  - Row 4 ("flat across K"): not flat. It rises by the predicted rounding ratio, which is row 1, not row 4.
  - Row 5: frames and maxFrame change with K, and dUsed moves with N.
  - Row 6: positive control pooled part 0 ≤ 4 MiB.
  - Row 7: see deviation 1; not a leak.
- **Observed vs inferred:**
  - Observed: pool bytes in use per frame, frame counts and wire bytes.
  - Inferred: that `usedSizeInBytes` reflects real off-heap memory. This follows from `BufferPool` accounting per allocated buffer capacity (`:950`, `:824`, `:891`), and `dSize` grows in real 8 MiB macro chunks.

**Cluster tier.**
- **Validity:**
  - The node ran the intended K each time.
  - The proxy stalled the reader: D is only ≈ 2.4 MiB (3.9 at K = 4096), and the unpaused control gives Δ = 0.
  - All responses were delivered.
  - after − baseline ≈ 0 (±4.5 KB, the deviation-1 drift).
- **Readings:**
  - Δ at K = 131060/65536/16384/4096 is 125.6/129.5/141.2/186.4 MiB, all inside B3f's bands. Δ **rises** as K falls.
  - Δ + D reproduces `M·B·roundUp(K+4)/(K−6)`. At K = 131060: 125.64 + 2.37 = 128.0 MiB = 32 × 4 MiB × 1.0001.
  - At K = 4096 the pool-side drain is D × 6144/4100 = 5.8 MiB, so the prediction is 192.3 − 5.8 = 186.5 MiB vs 186.37 observed.
  - PC1 doubles Δ (2.019×).
  - PC2 pins the pooled part at exactly 32.00 MiB while overflow takes 93.74 MiB, and Δ is unchanged at 125.64 MiB.
- **Matched row:** B3g row 1 ("Δ ≈ M·B·roundUp(K+4)/(K−6) − D at every K; Δ does not fall when K falls → Claim confirmed"). The control conditions of row 3 hold as well (PC1 doubles, PC2 pins the pooled part at 32 MiB).
- **Excluded rows:**
  - Row 2: Δ is never ≤ ~2 MiB, and it does not shrink ∝ K.
  - Row 4: Δ ≫ 0, and Send-Q holds only ≈ 2 % of the bytes.
  - Row 5: the controls moved as predicted.
  - Row 6: K is right in `system.log`.
  - Row 7: no timeout.
- **Observed vs inferred:**
  - Observed: JMX pool counters, Send-Q, NMT, RSS.
  - Inferred: that the frames sit in Netty's outbound buffer. This rests on the unpaused control, where Δ = 0 with the same allocation path, and on `writeAndFlush` with no writability check (`Flusher.java:201-206`, `PipelineConfigurator.java:139`).
- **Gap:** the Netty arena memory for response bodies (`CBUtil.allocator`) is not observed. It is outside K's control anyway (B3d).

**Answer to the core question:** K does **not** cap outbound memory. The off-heap memory held for pending v5 responses follows the response bytes (N, or M × B) and is unbounded by K. A smaller K slightly *increases* it, by the 2 KiB allocation-unit rounding. The only cap seen binding on this resource is `networking_cache_size`, and it bounds only the *pooled* part: the rest overflows unpooled.

## 5. Self-check of run 1 (AI)

### 5.1 Check of run 1's conclusion

Each part was re-read from the raw files (`raw/unit/unit.csv`, `raw/cluster/cluster.csv`, `held-*.txt`, `system.log.gz`), not from the summaries.

| # | Part | Holds? | Note |
|---|---|---|---|
| 1 | The patch set K as intended (inferred from the probe's own K) | holds | `RESULT,K=4096,…,maxFrame=4100` (unit); `KLINE … Native-Transport-Requests-1 … MAX_FRAMED_PAYLOAD_SIZE=4096` (cluster). |
| 2 | Unit dUsed follows N, not K | holds | `K=4096,N=16777216 … dUsed=25202752` against `N=4194304 … 6301696` (×3.9994); `K=131060,N=16777216 … 16781312`. |
| 3 | Usage rises as K falls (refutes "K caps") | holds | Unit 1.000 → 1.502 × N; cluster 125.64 → 186.37 MiB. |
| 4 | `UsedSize` is real off-heap (inferred) | holds, with the named gap | `Size` (allocated chunks) and `nioDirect` rise together in held samples (K=4096: `size=268435456`, `nioDirect=313284635`). Bodies in the Netty arena are not observed. |
| 5 | Frames are held because the reader is stalled (inferred) | holds | Unpaused rep 1: `held used=268518320` = baseline; paused: +131.7 MB; Send-Q 2,488,848 B only. |
| 6 | Positive controls moved | holds | PC2 `held … size=131852432,overflow=98298000` → pooled 33,554,432 B = 32 MiB exactly; PC1 Δ 265,986,024 B = 2.019 × 131,747,840. |
| 7 | AFTER_RELEASE deviation is accounting, not a leak (inferred from source) | holds | The values (−768, −16,928, −4,500, −18) equal the source-predicted trim sums exactly. The sign is negative. Pooled-only cells are exactly 0. |
| 8 | Baseline residue does not affect Δ | holds | It is constant (268,518,368) at baseline, held-minus and after, in the first JVM. Later JVMs have baseline 0 with Δs consistent with the first (K = 131060 PC2 run in a fresh JVM: Δ 125.64 MiB, the same as in the first JVM). |
| 9 | No errors on the node | holds | `zgrep -c '^ERROR' system.log.gz` = 0. |

### 5.2 Run 2?

Not run. The conclusion rests on byte-exact readings that match an exact a-priori model, and 3 repetitions per cell were identical. No part of the self-check is open, and the result confirms rather than refutes the case.

## 6. Run 2 (fresh AI session, optional)

None.

## 8. Verdict (AI)

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap; both tiers Confirmed).

**Claim tested (B1):** "Outbound off-heap memory held for pending CQL v5 responses grows in proportion to (number of pending responses × response size) and is **not** bounded by `MAX_FRAMED_PAYLOAD_SIZE` (K). Lowering K does not lower that usage. It raises it slightly, by the ratio `roundUp(K+4)/(K−6)` from the 2 KiB pool unit. The constant only bounds the size of each single frame buffer (≤ `roundUp(K+4)` bytes)." "Confirmed" below means this held.

| Tier | Verdict (row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed**: B2g row 1. dUsed = B2f's exact value in all 12 K × N cells (3/3 reps); dUsed/N is 1.000/1.031/1.125/1.502 for K = 131060/65536/16384/4096; linear in N; maxFrame = K + 4. | does not cap | run 1 + self-check | 2026-11-25 |
| Cluster | **Confirmed**: B3g row 1, with row 3's controls. Δ = 125.6/129.5/141.2/186.4 MiB for K = 131060/65536/16384/4096 with 32 × 4 MiB responses held behind a stalled reader; PC1 doubles Δ; PC2 pins the pooled part at 32.00 MiB with 93.7 MiB overflow; unpaused Δ = 0. | does not cap | run 1 + self-check | 2026-11-25 |

**Positive control:** `networking_cache_size` (unit 4 MiB, cluster 32 MiB) binds the pooled part exactly, read with the same instruments. Load doubling (N ×4, M ×2) moves usage proportionally.

**Nuance:**
- K is a frame-split size. It bounds each frame buffer (≤ `roundUp(K+4)`) and nothing more.
- With no writability check in `transport/`, a client that does not read lets the node hold every frame of every pending response off-heap.
- `networking_cache_size` limits only how much of that is pooled; the rest overflows unpooled without a total limit.
- Smaller K costs slightly more memory: +50 % at K = 4096.

**Feedback filed:**
- The case file's section D "Stage-4 feedback" is filled in `~/writeup-ext/out/o132/case-amended.md` (outside the repo). sha256 with D filled: `a42372f2c71914ce0120d08efe6a4dc10d9882f0a62cbd4ee8be8b317fb5ae0a`.
- Dated amendments: the `nopause` argument (B3a/B3e step 8), the B2f LZ4 clarification, and the runbook-defect-1 fix in B3a.
- B1, B2f, B2g, B3f and B3g are unchanged.
- Nothing was written in the repository: no `_INDEX.md`, CSV, HANDOFF or results-folder edit. Filing into the repo is left to the workflow.

**Other findings for stage 3:**
1. Runbook defect 1: a client-mode `SimpleClient` must set `DatabaseDescriptor.setNativeTransportMaxMessageSizeInBytes(…)` before it can receive multi-frame v5 responses. This applies to any design that reads large results through `SimpleClient` in a separate JVM.
2. B2g's "AFTER_RELEASE ≠ 0 → invalid" row should read "> 0". Unpooled buffers drift the overflow counter negative by their trimmed tails (`BufferPool.java:880-885` vs `:241-247`). This is a small Cassandra metric bug: `OverflowSize`/`UsedSize` under-count after trimmed overflow buffers.
3. B3f's drain correction is `D·roundUp(K+4)/(K+4)` in pool bytes. It matters only at small K (2 MiB at K = 4096); the bands still held.
4. LZ4 at K = 131060: 32 of 33 frames are unpooled (the small last frame is pooled), not "every frame".
5. Environment: `/mydata/s4/cassandra-base` on `ms0625` has no `src/`, `test/` or `.build/`. A case that patches source must rsync the pinned source over the copy first (`environment.md` §7 may want a line).

**Candidate for stage 5 (not verified):**
- After 64 v5 prepared inserts of 4 MiB each, the node's networking `BufferPool` `UsedSize` stayed at 268,518,368 B (≈ the inbound request bytes) until restart.
- It never returned to 0 across 9 reads, while a node that served no such writes had 0.
- It suggests inbound multi-frame (large) request buffers that are not returned to the pool, or are not decremented from `memoryInUse`, on the v5 large-message path (`CQLMessageHandler` `LargeMessage`).
- Evidence: `raw/cluster/cluster.csv` baselines; `size=276824064` at the first baseline.

**Left on the node (`ms0625`):**
- Nothing running: no `CassandraDaemon`, proxy or probe JVM; ports 7000/7199/9042/19042 free (checked after the run).
- Files: `/mydata/jingsong-cass-s4/o132/` (5.4 MB: `harness/`, `probe/`, `logs/`, `unit.csv`, `cluster.csv`, `cluster-attempt1.csv`, `classpath.txt`).
- The source copy (with its build), data, commit log and saved caches were deleted.
- Lock `/mydata/s4/NODE-LOCK` released at 08:57:24Z; `/mydata/s4/DRIVER-*.pid` removed.
- `/mydata/s4/cassandra-base` and the other users' folders (`o57`, `o72`, `3b-*`) were not touched.

## Time spent (UTC, 2026-11-25)

| Step | Start | End | Minutes | Remarks |
|---|---|---|---|---|
| Read protocol, audit, harness | 08:18 | 08:31 | 13 | Overlaps the build |
| Copy and build | 08:20 | 08:30 | 10 | Two failed `ant jar` attempts (base lacks `.build/`, `test/`) |
| Unit tier | 08:31 | 08:34 | 3 | 45 JVMs |
| Cluster attempt 1 | 08:34 | 08:44 | 10 | Defect 1, no readings |
| Fix, smoke, cluster tier | 08:45 | 08:56 | 11 | 21 reads, 5 node starts |
| Cleanup, lock release, write-up | 08:56 | 09:10 | 14 | |
