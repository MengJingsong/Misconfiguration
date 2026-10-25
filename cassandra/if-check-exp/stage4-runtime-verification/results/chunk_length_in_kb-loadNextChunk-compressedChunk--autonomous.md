# chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous — stage-4 results  <!-- file: results/chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous`](../../stage3-ai-deep-read/cases/chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous.md)
>
> **Status:** verdict filed (2026-10-25) — run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap`) — [definition](../README.md#outcome-class)
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g (cluster) as amended by B2i and B3i; "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base repository commit `25b4a70`; the case file is **untracked** in the working tree (no commit holds it). **Final frozen version: sha256 `4075fd9139c6108e258e3d50d3d545a2852d100256376eb9b53296ac4679955f`** (after B2i, B3i and the second cluster amendment B3i.9, dated 2026-10-25, written 2026-10-25 18:08 UTC, before run 1 and before any reading). First freeze (B2i and B3i only): `aa9f36892def04a0336739b47cce3c95b627d6c7e28f10c97edee05d813a7ea2`, written before the harness existed; superseded because the instrument check found that the cluster cap control at 48m cannot work (the idle node holds 54.7 MiB of direct buffers), see B3i.9 and section 3. Both hashes are in `pc12:~/s4-ci/logs/freeze.sha`. The unit-tier text (B2f, B2g, B2i) and B3f/B3g/B3i.1-8 are identical in the two versions except the cap value (48m -> 100m) and the run count note. written to `pc12:~/s4-ci/logs/freeze.sha` and to this file at 2026-10-25 13:55:54 EDT, before the harness existed and before any reading. B2f, B2g, B3f, B3g (with B2i, B3i) are frozen at this hash. The original file (before amendments) had sha256 `438efc0d88de4eb84409f4cb4a34115db229343dd758a4d811ffbb937974c4f6`. Section D (the feedback) is filled after the runs; the sha256 with D filled is `98175f1b164ae6a117d923fb389cabd0916005f2eb8ffcfd8d8910eead779e3c` (section D adds no change to B2/B3). |
| **Harness** | `harness/chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous/`: `CompressedInputStreamOversizeTest.java` (unit tier), `unit-run.sh`, `analyze_unit.py`, `PoolSampler.java` (JMX direct-pool sampler, 20 ms), `loader.py`, `cluster-run.py` (one cluster run), `cluster-all.sh` (the 11 runs), `analyze_cluster.py`, `selfcheck.py`, `README.md`; written after the first freeze; not committed (md5s in `run1/harness.md5.*`). |
| **Tiers and values** | **Unit (B2 + B2i):** n in {4096, 16384, 65536, 1 MiB, 16 MiB} natural LZ4 arm; boundary arms L = n-1, n, n+1, 1.5n+1; wire-declared 32 MiB and 128 MiB; ratio 1.1 raw-path arm; pool deltas; positive controls under `-XX:MaxDirectMemorySize` 16m and 38m. **Cluster (B3 + B3i):** two nodes on pc12, bootstrap stream of 256 MiB of random 1 MiB blobs; `chunk_length_in_kb` in {4, 16, 64, 1024, 16384}, `min_compress_ratio` 0 and 1.1, repeats at 16384, entire-sstable control, B-side `MAX_DIRECT_MEMORY_SIZE=48m` cap control. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25 |

### 1.1 Design audit

Estimate: **negative** (the receive buffer follows the wire chunk length, not a receiver-side limit). Audited against `cassandra/cassandra-5.0.9/` (`git status` of it clean at `25b4a70`). Citations re-read in the pinned source: `CompressedInputStream.java:54,73-88,95-108,130-171,183-193,210-224`; `CompressionInfo.java:175-200`; `CompressionMetadata.java:555-570`; `CompressionParams.java:40-60,175-200,235-245,336-380,515-545`; `CompressedSequentialWriter.java:98,120-185`; `CassandraCompressedStreamReader.java:60-100`; `CassandraIncomingFile.java:68-90`; `CassandraOutgoingFile.java:79-125,181-202`; `LZ4Compressor.java:105-120`; `Config.java:165,699`; `conf/cassandra-env.sh:130-245`; `build.xml:94,1153,1192`; `CompressedInputStreamTest.java`.

Trigger reaches the check: a bootstrap (or rebuild/repair) stream of a compressed table whose SSTable is only partly covered by the requested ranges is read by `CassandraIncomingFile.read` (`:80-84`) into `CassandraCompressedStreamReader`, which constructs `CompressedInputStream` (`:74`) and calls `position()` then `loadNextChunk`. `stream_entire_sstables` (default true) bypasses it only when `contained()` (`CassandraOutgoingFile.java:194-202`) says the sections cover the whole SSTable; so with a half-ring bootstrap the class is used even at the default, and the filed `false` is a safe superset. OperationType is the bootstrap's `BOOTSTRAP` stream.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: direct (off-heap) memory held by one inbound compressed-SSTable stream. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b varies chunkLength (4096, 16384 default, 65536) and B3b varies 4/64/1024 KiB; B3i.2 adds the default 16 KiB and 16384 KiB. The wire length is a second, non-config variable (the claim). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met | B2d reads field capacities (the check's operand) and the JVM's direct BufferPool `MemoryUsed` (real reserved bytes); B3d's `jcmd NMT "Other"` is replaced by a JMX `BufferPool` sampler every 20 ms (B3i.3). Gap named: Netty arenas are not in the pool. |
| A. Core question | usage driven to the limit and past it | Partly → Met | "Limit" is the option: the unit tier drives L past n, 1.5n and to 128 MiB (B2i.4); the cluster tier at 64 KiB gives an effect of 32 KiB, which cannot be resolved; B3i.2/B3i.4 move the cluster arm to 16 MiB chunks (effect 8 MiB). |
| A. Core question | positive control for a negative estimate | Partly → Met | B2h/B3h name the JVM limit only as an OOM at 16m; a binding cap that discriminates the 1.5x from the 1.0x footprint is added (B2i.7c, 38m pair) and a B-side cap at 48m for the cluster (B3i.6c). The ratio 1.1 arm is the second condition under the same instruments. |
| B. Logic | each step says what it establishes | Met | B2e/B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met | B2f is numeric; B3f was a relation in N x chunk; B3i.5 gives numbers and tolerances (P about 4.5 n, D about 0.5 n, noise <= 2 MiB). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met | Missing rows added: B2i.8 (natural arm without regrow, 128 MiB short, 38m pair not discriminating) and B3i.7 (resolved, unresolved, instrument sees different allocations, control inconclusive). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | For a "does not cap" claim: capacity follows the wire length and not the option (B2i.4), and the only stopping branch is the JVM limit (B2i.7), read as OOM "Direct buffer memory" at the regrow line. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h plus the ratio 1.1 raw-path arm, boundary arms, the entire-sstable control (B3i.6b). |
| C. Specific | a human can follow it from the intro and B1 | Met | A3, B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly → Met | Missing: the 3-JVM-limit invocations, how the test JVM limit is passed, JMX ports, loopback addresses, the stream-window log lines, tokens (B2i.1, B3i.1-3). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | Sampling interval, baseline and peak definitions, table DDL, load size, node counts supplied. Filed `/users/jason92/...` and `/tmp/c509-*` paths replaced by run-node paths (environment deviation). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Built tree via `copy-source.sh`, `ant build-test`, `ant jar`; the unit test, run scripts and the JMX sampler are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly → Met | 256 MiB per run on tmpfs; the cluster effect at the filed chunk sizes (4 to 1024 KiB) is 2 KiB to 0.5 MiB, not resolvable against Netty and other direct users, so B3i raises the chunk to 16 MiB (effect 8 MiB per stream) and states the stream count is 1. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met (one number off) | All re-read; the incompressible overshoot is about 70 B at 16 KiB (n + 4 + 2 + floor((n-15)/255)), not 84 (that is an upper bound); the regrow still happens. `CompressionParams.java:195` (the ratio-free constructor) is added. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Natural real-LZ4 arm, boundary arms (L = n, n+1), wire-declared 128 MiB | Applied, B2i.2-4, 2026-10-25 | Hand-declared lengths alone do not show the real sender overshoots; the unbounded half needs a length far above 1.5n. |
| 2 | Ratio 1.1 raw-path arm in the unit tier | Applied, B2i.5 | The cluster control had no unit counterpart. |
| 3 | Pool-delta numeric prediction and close check | Applied, B2i.6 | B2f only gave capacities. |
| 4 | Sharp positive control: 38m limit, n = 16 MiB, regrow needs 40 MiB, raw path needs 32 MiB | Applied, B2i.7 | A bare 16m OOM only shows allocation of 32 MiB fails; it cannot show the cap binds on the regrow step. |
| 5 | Cluster chunk raised to 16 MiB, JMX `BufferPool` sampler, D = P(ratio 0) - P(ratio 1.1) with numbers and a repeat | Applied, B3i.2-5 | The filed effect (few MiB at N streams) is below the noise; the write-up itself says so. |
| 6 | Entire-sstable and B-side cap controls | Applied, B3i.6 | Isolate the class and give the cluster tier a positive control. |
| 7 | Parallel streams (N > 1) | Left for stage 3 | One peer on one host gives N = 1; the 16 MiB chunk replaces it. |
| 8 | A1 says `stream_entire_sstables: true` bypasses the class; it only does when the whole SSTable is contained | Left for stage 3 | Cosmetic for this run (the yaml is set to false). |

**Agreement criteria** — not applicable (run 2 not chosen).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-25 (unit 18:13 UTC, cluster 18:13:54 to 18:38:34 UTC) | not done |
| Node (CloudLab name and type) | `pc12` = `node1.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB; shared with another agent (tag `pk`) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-ci/cassandra` made by `copy-source.sh` from repository commit `25b4a70` (local baseline `5b97879`, tag `cassandra-5.0.9`), `ant build-test` 1 min 9 s, `ant jar` 10 s; the unit test was added only there. The nodes ran from `~/s4-ci/node-tree`, a `cp -a` of that built copy, in which `ant` was never run. Nothing was built in the repository's `cassandra/cassandra-5.0.9/`. | |
| Case-file commit / harness commit | case file untracked at `25b4a70` (sha256 in section 1); harness uncommitted (md5s: `chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous/run1/harness.md5.{unit-start,cluster-start,final}`) | |
| Storage for node data | cluster tier: `/dev/shm/s4-ci/<label>` (tmpfs, removed after each run); unit tier: no node, heap/direct buffers only | |
| Full logs (path, outside the repo) | `pc12:~/s4-ci/run1/{unit,cluster}/` (full `ant-*.log`, per-run `samples.csv` at 20 ms, `B-system.log`, `B-debug.log`, `A-system.log`, `session.log`, `summary.json`), `~/s4-ci/shake-*` (shakedowns, not readings); excerpts in `chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous/run1/` | |

**Environment deviations (none changes B1):** (1) the filed paths (`/users/jason92/...`, `/tmp/c509-*`) became `~/s4-ci/...` and tmpfs. (2) Loopback addresses 127.0.12.1/2 with ports 7012/9112/7212/7213 (shared host), `nodetool -p`. (3) The yaml `stream_entire_sstables` is `false` in all runs but the entire-sstable control (a half-ring bootstrap uses `CompressedInputStream` even at the default `true`, `CassandraOutgoingFile.java:194-202`). (4) JMX `BufferPool` sampler instead of `jcmd VM.native_memory` (B3i.3). (5) The idle node already holds 52.13 MiB (54,664,5xx B) of direct buffers; B3i.9 and the amendment text quote this as "54.7 MiB", which is the figure in MB, and "at least 118 MiB" for the stream footprint is 116 MiB (52.1 + 64); neither changes the cap choice of 100m (nor the failure of 48m). (6) Unit tier: Java 11 test JVM with `-Dtest.jvm.args=-XX:MaxDirectMemorySize=...` and default 1 GiB heap.

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B2c | Random bytes alone cannot show that the real sender produces an overshoot; the filed L = chunk + 84 is a bound, the real LZ4 length is about chunk + 70. | Real-LZ4 "natural" arm, boundary arms, 128 MiB arm: B2i.2-4. | 2026-10-25, before the first freeze | none (case file untracked) |
| 2 | audit | B3b/B3c/B3f | A 4 to 1024 KiB chunk gives an effect of 2 KiB to 0.5 MiB at N = 1; the filed prediction is a relation in N. | Chunk 16 MiB, JMX sampler, numeric predictions, controls: B3i.1-8. | 2026-10-25, before the first freeze | none |
| 3 | step 1 (instrument check) | B3i.6c | Cap control `MAX_DIRECT_MEMORY_SIZE=48m` kills B before the stream starts: the idle node holds 52.13 MiB of direct buffers (shakedown, `OutOfMemoryError: Direct buffer memory` in `HintsWriteExecutor` at start-up). | Cap raised to 100m (B3i.9); second freeze. | 2026-10-25 18:08 UTC, after the shakedown, before run 1; no run reading existed | none |
| 4 | step 1 | harness | The first cap-mode stop condition matched the JVM argument `HeapDumpOnOutOfMemoryError`; the bundled Python driver zip needs the `/cassandra-driver-3.29.0` sub-path; a shakedown overlapped with the previous one (still stopping) and collided on ports and tmpfs. | Regex tightened to `java.lang.OutOfMemoryError|Direct buffer memory|...`; sub-path added; strictly serial runs. | 2026-10-25, before run 1 | n/a (harness only) |
| 5 | self-check | harness | `selfcheck.py` first required exactly one `*-Data.db` on A; the glob ran right after `nodetool compact`, while the obsolete input file was still on disk. All checks failed on that line only. | Check replaced by "the compaction output named in `A-system.log` is the live SSTable" (a checker fix; no reading changes). | 2026-10-25 | n/a |

## 4. Run 1

**Scope:** unit tier, all 21 arms in three JVMs (512m, 16m, 38m); cluster tier, 11 runs (section 1). **Command log:** `chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous/run1/unit/session.log`, `.../run1/cluster/chain.log` and per-run `session.log` on the node.

**Instrument checks before run 1 (not readings).** A complete unit pass of the same harness and six cluster shakedowns on 64-row loads ran first (section 3, defects 3 and 4). The unit pass already matched all predictions, so run 1 is a repeat of it, byte for byte the same harness; nothing in B2f/B2g/B2i was changed after it. The shakedown of chunk 16 MiB / ratio 0 gave P = 73.07 MiB, inside the frozen range [50, 95]; the frozen text was not changed after it (B3i.9 changed only the cap value, for the start-up reason above). Run 1 is not independent of these checks.

### 4.1 Readings

**Unit tier** (`run1/unit/results-{main,cap,cap38}.csv`, `analysis.txt`: 82 of 82 frozen checks PASS)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| natural LZ4 chunk, n = 4096 / 16384 / 65536 / 1 MiB / 16 MiB: wire length W | n + 22 / n + 70 / n + 262 / n + 4118 / n + 65798 (inside [n+5, n+4+n/255+16]); the real compressor makes the chunk larger than n | `unit/results-main.csv` |
| same chunks: `compressedChunk.capacity()` after `position(0)`; `buffer.capacity()` | 6144 / 24576 / 98304 / 1572864 / 25165824 (= int(1.5 n) each); `buffer` = n; the decompressed bytes equal the input, no exception | `unit/results-main.csv` |
| boundary, n = 16384: L = 16383, 16384 | capacity 16384 (no regrow) | `unit/results-main.csv` |
| boundary, n = 16384: L = 16385, 16468, 24576 | capacity 24576 | `unit/results-main.csv` |
| n = 16384, L = 24577 | capacity 24577 (= L) | `unit/results-main.csv` |
| n = 16384, L = 32 MiB / 128 MiB (hand-declared) | capacity 33554432 / 134217728 (= L; 8192 x the option at 128 MiB); `buffer` stays 16384; decompression throws afterwards, caught | `unit/results-main.csv` |
| n = 4096 L = 4180; n = 65536 L = 65620 | capacity 6144; 98304 | `unit/results-main.csv` |
| direct-pool delta after `position(0)`; after `close()` | = `buffer` + `compressedChunk` capacity, exactly, in every arm; 0 after close | `unit/results-main.csv` (poolPos - pool0, poolClose - pool0) |
| ratio 1.1 raw path, n = 1 MiB / 16 MiB | `compressedChunk` stays n; pool delta 2n; bytes equal the input | `unit/results-main.csv` |
| positive control, 16m: L = 32 MiB, n = 16 KiB | `OutOfMemoryError: Direct buffer memory` in `position()`; capacity read afterwards 16384 | `unit/results-cap.csv` |
| positive control, 16m: natural n = 16 MiB | the constructor throws the same error (32 MiB needed) | `unit/results-cap.csv` |
| sharp pair, 38m, n = 16 MiB: natural chunk | constructor fine (32 MiB), `position()` throws `Direct buffer memory` at the regrow (16 MiB `buffer` + 24 MiB new buffer = 40 MiB; the old buffer is freed first: pool 16.8 MB after the failure) | `unit/results-cap38.csv` |
| sharp pair, 38m, n = 16 MiB: raw (ratio 1.1) chunk | succeeds, bytes equal, pool 32 MiB | `unit/results-cap38.csv` |

**Cluster tier** (`run1/cluster/analysis.jsonl`, `selfcheck.out`; baseline = 52.13 MiB idle direct pool on B; P = peak in the stream window minus baseline; N = 1 stream; 256 MiB of random 1 MiB blobs on A, one live SSTable after compaction, about 140 MiB streamed to B)

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| 4 KiB / 16 KiB / 64 KiB, ratio 0 | r03 / r01 / r02 | P (direct pool peak above baseline) | 1.02 / 1.08 / 1.29 MiB (not resolved against the other direct users; no ratio-1.1 pair run at these sizes) | `cluster/analysis.jsonl` |
| 1024 KiB, ratio 0 / ratio 1.1 | r04 / r05 | P | 5.51 / 5.01 MiB; D = 0.50 MiB (= 0.5 n) | `cluster/analysis.jsonl` |
| 16384 KiB, ratio 0, rep a / rep b | r06 / r08 | P | 73.07 / 73.07 MiB (4.57 n), peak 125.20 MiB | `cluster/analysis.jsonl`, `cluster/r06_c16384_r0_a/samples-window-every10th.csv` |
| 16384 KiB, ratio 1.1, rep a / rep b | r07 / r09 | P | 65.07 / 65.07 MiB (4.07 n), peak 117.20 MiB | same |
| 16384 KiB: D = P(ratio 0) - P(ratio 1.1) | a / b | D | 8.00 / 8.00 MiB (= 0.5 n); repeat differences 0.00 MiB | `selfcheck.out` (C-predD, C-noise) |
| 16384 KiB, ratio 0, B capped at 100m (control) | r10 | stream window; log; P | window opened ("Executing streaming plan for Bootstrap"), B hit `java.lang.OutOfMemoryError: Direct buffer memory` inside `SequentialWriterOption.allocateBuffer` (the receiving writer, after the reader pair was allocated), no "All sessions completed", B exited (rc -9); peak 92.14 MiB; B received 0 bytes | `cluster/r10_cap100m_c16384/B-stream-lines.txt`, `selfcheck.out` |
| 16384 KiB, ratio 0, whole-ring ownership, `stream_entire_sstables: true` (control) | r11 | P; debug line | P = 0.00 MiB; 2 x "Incoming stream entireSSTable=true"; 257 MiB moved | `cluster/r11_entire_c16384/` |
| all normal runs | r01 to r09 | stream path | only "entireSSTable=false" lines (the compressed reader), 2 per run | `cluster/r*/B-stream-lines.txt` |

### 4.2 Conclusion and logic

1. **Validity** — Valid. The limit of the claim (the receive buffer exceeds the option) was reached in both tiers. Each hold-fixed setting is confirmed: JVM direct limit per arm in the CSV header [observed: `unit/results-*.csv`; `selfcheck.out` U-limit]; random data and compression options in each table [observed: `cluster/r*/ddl.txt`]; `stream_entire_sstables` false except r11, and the stream path [observed: debug lines in `B-stream-lines.txt`]; one live SSTable on A [observed: `A-system.log` compaction line, `selfcheck.out`]; ratio 1.1 arms took the raw path [inferred: pool 2n at the unit tier, D = 0.5 n at the cluster tier].
2. **Readings** — Unusual: P is identical (to the byte) in repeats, because the counter reports reserved capacity, not touched pages [observed: `selfcheck.out` C-noise]. The 1024 KiB difference D = 0.50 MiB was resolved after all (B3i.5 expected it to be unresolved); the 4/16/64 KiB runs have no ratio-1.1 partner and are unresolved. The cap run died at the writer's buffer, not at the reader's regrow.
3. **Matched row** — Unit: B2g row 1, "`compressedChunk.capacity() > chunkLength` for L = chunkLength + 84, and 32 MiB for L = 32 MiB: claim confirmed" [observed: natural arms 1.5 n; `hand_16384_32MiB` and `wire128MiB` capacity = L] with the control row (L = n - 1, `buffer` constant at n) [observed], the positive control row (`Direct buffer memory` at 16m) [observed] and B2i.7c (38m pair separates the 1.5x from the 1.0x footprint) [observed]. Cluster: B3i.7(i): D in [5, 11] MiB in both repeats (8.00, 8.00), repeat noise 0 (<= 2), both ratios completed, the cap control stopped the stream with "Direct buffer memory" [observed: `selfcheck.out`].
4. **Excluded rows** — "Capacity stays <= chunkLength for all L" (unit refuted-if): excluded by every L above n [observed]. "Failure before line 150": `ctorEx` empty, capacity set before the decompression error [observed]. "L = 32 MiB succeeds but pool delta below L": delta 33570816 = 32 MiB + 16 KiB [observed]. "Delta ratio 0 equals ratio 1.1" (cluster refuted-if): 73.07 vs 65.07 [observed]. "Delta flat across 4/64/1024 KiB": 1.02, 1.29, 5.51 and 73.07 MiB at 16384 [observed]. B3i.7(ii) to (iv): D resolved, P inside [50, 95], cap control conclusive [observed].
5. **Observed vs. inferred** — Inferred: (a) the reserved-capacity pool delta equals resident usage [inferred: `allocateDirect` memory is reserved and, when touched, resident; the harness did not read RSS]; (b) the 8 MiB of D is the reader's regrow and not some other consumer [inferred: ratio is the only difference; the unit tier shows the same 0.5 n in `compressedChunk`; the entire-file control shows the rest of the pool is quiet]; (c) the 100m cap is "a cap that binds" and the option does not [inferred: the OOM is in the writer's allocation after the reader pair; the cap run does not discriminate the regrow itself (the unit 38m pair does)].
6. **Deviations and gaps** — N = 1 stream only (B3i.4 said so); no run with a sender that declares a chunk far above 1.5 n in a live cluster (the wire-declared 128 MiB case is unit-only); direct pool counts `allocateDirect` buffers, not Netty arenas; the first unit pass and the cluster shakedowns were seen before run 1 (section 4); a normal honest sender reaches only 1.5 n (4.5 n total with the writer), a constant factor above the option, and only a corrupt or hostile header gives a length that is not tied to the option; the claim "not bounded by the option" therefore rests on the unit tier for the unbounded half.
7. **Core question** — Usage follows the option only as the initial allocation (2 n at ratio 1.1, with the writer 4 n) and exceeds it on the real path by the regrow (+0.5 n, 8 MiB at 16 MiB chunks; exact in the unit tier and in the cluster tier), and the unit tier shows that `compressedChunk` takes any declared length (128 MiB under a 16 KiB option) with only the JVM's direct-memory limit stopping it (OOM at 16m and at 38m). So `chunk_length_in_kb` does not cap the receive-side direct memory of a compressed stream.

**Conclusion (one line):** unit B2g row 1 (with its control and positive-control rows) and cluster B3i.7(i) — the claim (usage not bounded by the option) is confirmed at both tiers.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous/selfcheck.py` re-parsed the raw CSVs, ant logs, `samples.csv`, `B-system.log`, `B-debug.log`, `A-system.log` and `session.log` without using `analyze_*.py` (it recomputes the expected capacities from the formulas, the windows from log timestamps with `datetime`, the baseline and peak itself); result `run1/selfcheck.out`: 61 checks hold, 0 do not (the first version of the checker failed on a stale-file glob, section 3 defect 5, and was fixed before this result; the other checks were unchanged).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `results-*.csv` header JVM args = 512m/16m/38m; `ant-*.log` "Tests run: 1, Failures: 0"; each cluster run has one live SSTable (compaction line), `entireSSTable` lines as expected, DDL as labelled (`selfcheck.out`). |
| 2. Readings | yes | Peak/baseline recomputed independently: 125.20/52.13 MiB (r06, r08), 117.20 (r07, r09), 57.64, 57.14; identical to `analyze_cluster.py`. |
| 3. Matched row | yes | Unit capacities equal the frozen table exactly; cluster P in [50, 95], D = 8.00 and 8.00 in [5, 11], noise 0 <= 2, dose 73.07 > 5.51 > 1.29. |
| 4. Excluded rows | yes | No arm has capacity <= n for L > n; ratio 0 and 1.1 differ by 8.00 MiB; P rises with the option. |
| 5. Observed vs. inferred | yes | The three inferred statements are listed and stay inferred; (c) is weaker: the cap control is conclusive that a JVM cap stops the stream, not that it stops the regrow. |
| 6. Deviations and gaps | yes | Stated, including the shakedown overlap with run 1 and N = 1. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1, the B2i.8 effect rule (capacity > option and = L for wire arms: does not cap) and the cluster row (i). |

### 5.2 Run 2?

**No** — decided 2026-10-25. The unit tier is deterministic (capacities to the byte) and the cluster tier repeats to the byte; the one inferred step that matters (the +8 MiB is the regrow) is confirmed by the unit 38m pair and the exact 0.5 n arithmetic. The result confirms the filed negative estimate, so it neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap).

**Claim tested:** (B1) the direct memory held by a `CompressedInputStream` is not bounded by the table's `chunk_length_in_kb`: `compressedChunk` grows beyond `chunkLength()` (to 1.5x for naturally incompressible data and to the wire-declared length in a hand-built stream). "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g row 1 (capacity above the option, = L up to 128 MiB), control row, positive-control rows (16m, 38m pair) | does not cap | run 1 + self-check | 2026-10-25 |
| Cluster | Confirmed — B3i.7(i) (D = 8.00 MiB = 0.5 n at 16 MiB chunks, repeat noise 0, cap control OOM, entire-file control P = 0) | does not cap | run 1 + self-check | 2026-10-25 |

**Positive control** (a negative-estimate file only): the JVM direct-memory limit, a cap known to bind the same resource. Unit: n = 16 MiB under 38m, the regrow (40 MiB needed) throws `Direct buffer memory` while the raw-path chunk (32 MiB) succeeds; 16m stops the 32 MiB declared chunk and the 32 MiB constructor. Cluster: B capped at 100m stops the 16 MiB-chunk bootstrap with `OutOfMemoryError: Direct buffer memory` (in the receiving writer's buffer). Plus a second condition under the same instruments: ratio 1.1 (no regrow) and the entire-file path (class not used) move P in the predicted direction (65.07 and 0.00 MiB against 73.07).

**Caveat on "does not cap":** the overshoot of an honest stream is a constant factor of the option (1.5x on the reader's second buffer); that the buffer follows an arbitrary declared length is shown only in the unit tier (hand-built `CompressionInfo`), not on a live sender.

**Feedback filed:** the case file's section D "Stage-4 feedback" filled (case file untracked, no commit); amendments B2i, B3i and B3i.9 are in the case file (dated 2026-10-25). `_INDEX.md`, `writeup-set-A.csv` and the HANDOFF files were not edited (instruction); the new sha256 is in the final report.

## 9. Leftovers

Nothing running on `pc12` (checked: no `CassandraDaemon` of this run, ports 7012/9112/7212/7213 free, `/dev/shm/s4-ci` removed). Kept on disk: `pc12:~/s4-ci/` (953 MB: source copy, node tree, harness copy, shakedown and run-1 logs). The repository copy of the case file is untracked and modified; nothing was committed.

## 10. Time spent

| Step | Start (UTC) | End (UTC) | Minutes | Remarks |
|---|---|---|---|---|
| audit | 17:51:00 | 17:55:54 | 4.9 | reading the protocol, the case, the source; amendments B2i and B3i; freeze 1; build ran in the background meanwhile (build-test 1 min 9 s, jar 10 s) |
| harness | 17:55:58 | 18:12:58 | 17.0 | unit test, one unit pass as instrument check, JMX sampler, loader, cluster script; six cluster shakedowns (about 2 min each, two overlapped by mistake); the 48m cap finding, amendment B3i.9 and freeze 2 |
| unit-run | 18:13:03 | 18:13:54 | 0.9 | three `ant testsome` JVMs (about 14 s each, build already done) |
| cluster-run | 18:13:54 | 18:38:43 | 24.8 | 11 runs in series, about 2.25 min each (two nodes start, 256 MiB load, compact, bootstrap, stop); no reruns |
| selfcheck | 18:38:43 | 18:39:30 | 0.8 | plus one fix of the checker and rerun (section 3, defect 5) |
| report | 18:39:30 | 18:41:10 | 1.7 | excerpts, results sections, case-file section D |

Total wall time (first start to last end): 17:51:00 to 18:41:10 UTC = 50.2 min.
