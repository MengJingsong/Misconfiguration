# native_transport_max_frame_size-decode-bytesToDiscard--autonomous — stage-4 results  <!-- file: results/native_transport_max_frame_size-decode-bytesToDiscard--autonomous.md -->

> **Case:** [`native_transport_max_frame_size-decode-bytesToDiscard--autonomous`](../../stage3-ai-deep-read/cases/native_transport_max_frame_size-decode-bytesToDiscard--autonomous.md)
>
> **Status:** verdict filed (2026-10-27)
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/native_transport_max_frame_size-decode-bytesToDiscard--autonomous/`](../harness/native_transport_max_frame_size-decode-bytesToDiscard--autonomous/).
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e;
> the case file's feedback section is its section D. Session: Claude Opus 5.5 (claude-opus-5-5), advisor-run, on the advisor's Mac.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Branch `advisor-run`, uncommitted on 2026-10-27 (as filed in `6f54566`'s tree, sha256 `c9b1f9ee…cb8e`). Frozen after the audit's 17 amendments (U1–U8, C1–C9): sha256 `9118745e97ddd595557a10fe522d8aeaa170a3f8e20db4c02125e05a91462715`, recorded in `_INDEX.md` §4 before any harness run or reading. Runbook fix D1 (§3), found at the cluster shakedown before run 1, gives sha256 `b7591e0c28994fb49997b0b4ab2d10d05737feadee6b02243b83629426166067` (new §2 row); **both tiers of run 1 ran at this version**. Section D is filled after this hash. |
| **Harness** | `harness/native_transport_max_frame_size-decode-bytesToDiscard--autonomous/`: `FrameSizeDiscardProbeTest.java` (unit probe, copied into the clone only for the run), `unit-run.sh`; `hold_frames.py` (the case's B3c client verbatim through the hold, plus the C3 final byte and response read), `ntfs.btm` (observe-only Byteman rules `NTFDISCARD`, `NTFFAIL`, discard-call counter, `NTFMEM`), `cluster-run.sh`. Structure of `unit-run.sh`, `cluster-run.sh` and the `NTFMEM` trigger (`nodetool version`) adapted from `harness/native_transport_max_concurrent_connections-channelActive-limit--autonomous/` (tools only; every number, band and expectation here derived from source). Self-check: `results/<stem>/run1/selfcheck.py`. Uncommitted (no commit asked). |
| **Tiers and values** | Unit: one JVM per value, `4MiB`, `8MiB`, `16MiB` (default); sub-runs MAIN (`L` = 8,388,608, header alone, 64 KiB body calls to `L-1`, final byte) at every value; CTRL1M (`L` = 1,048,576) and C436 (whole frame in one call) at `4MiB`; EDGE (`L` = 8,388,599, `totalLength = MAX`) at `8MiB`. Cluster: one node (127.0.0.1, 1 GiB heap, `MaxDirectMemorySize=2G`, NMT summary, heap-allocator flag per D1), values `16MiB` (A), `4MiB` (B), `8MiB` (C), a fresh node per value; 32 raw v4 connections each sending a 9-byte OPTIONS header declaring `L` = 8,388,608 and `L-1` body bytes, held 120 s, then the final byte. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: bytes a connection's `ByteToMessageDecoder` cumulation holds for an incomplete legacy envelope (direct memory). |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly | B2b/B3b: two values (4MiB, 16MiB). Third value 8MiB added to both tiers (U2, C2); at 8MiB the 8 MiB frame exceeds the limit by the 9 header bytes. |
| A. Core question | real resource measured, not only the counter | Met (unit: Partly) | Unit: `readableBytes()` of the cumulation the test drives (the bytes themselves, not process memory). Cluster: NMT `Other` committed delta (real direct memory); RSS as context (C4). |
| A. Core question | usage driven to the limit and past it | Met | 8 MiB frames against 4/8/16 MiB; boundary `totalLength = MAX` (EDGE, U3). |
| B. Logic | each step says what it establishes | Met | B2h/B3h: 16MiB positive control, 1 MiB control, release check. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | Unit start value of `bytesToDiscard` wrong by source (`discard` at `:434` starts at the frame start, so after a header-only call it is `L`, not `L+9-firstChunkBody`); exact sequence written (U6). Cluster: "about 230 MiB", "similar" RSS; numeric thresholds written (C6), RSS made context. |
| B. Logic | every plausible outcome has a conclusions row | Partly | B2g/B3g rows lacked verdicts, drift, release, control-failure, disallow-evidence and catch-all rows; added (U7, C7). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | Unit: exact `WRAPPED` outcome (Met). Cluster: B3d says the decoder state cannot be observed and no error appears while the byte is withheld; added `NTFDISCARD`/`NTFFAIL` (C4) and the final byte with response read (C3). |
| B. Logic | alternative explanations and their controls | Partly | B3h's idle baseline not in B3e; added as the 50-s drift control (C5). The filed heap-allocator retry of "A also flat" rests on a premise the source contradicts; not run (C7 h1). |
| C. Specific | a human can follow it from the intro and §9a | Met | A3 traces `:345-350`, `:424-449`, `:478-498`; B1 states the claim. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | `/local`, Linux `/proc`, `bin/cassandra -p` (U1, C1, C4); property pass-through (U2). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Feed schedule (header alone or not), print points, stop conditions, sample times (U3–U5, C5). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11, Ant, Python 3, Byteman jar from the build. |
| D. Runnable | workload arithmetic reaches the limit | Met | Run A: 32 × 12,582,912 B (cumulation capacity at 8,388,616 readable bytes by Netty 4.1.130 `calculateNewCapacity`, 4 MiB steps above 4 MiB) = 384 MiB direct, under 2 GiB; ≈ 5 min per value. |
| D. Runnable | load-bearing citations spot-checked | Met | Clone at `b5f2a54210`: `Config.java:284-285`; `DatabaseDescriptor.java:619-625, 3153-3161, 245-250, 391`; `Envelope.java:134-136, 197-201, 345-350, 424-449, 478-498`; `CBUtil.java:59-60`; `PipelineConfigurator.java:138, 265, 388-391`; `InitialConnectionHandler.java:52, 66-95`; `ErrorMessage.java:484-503`; `PreV5Handlers.java:320-360`; `build.xml:94, 1192`; `conf/cassandra.yaml:1040-1044`; Netty `AbstractByteBufAllocator.calculateNewCapacity`/`ioBuffer`, `UnpooledByteBufAllocator.newDirectBuffer` (`javap -c`, 4.1.130). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1 | B2a: this host's clone `$W/cassandra-run54`, harness test path and script | applied 2026-10-27 (in hash `9118745e…`) | `/local` does not exist here |
| U2 | B2b: third value 8MiB; `-Dtest.jvm.args`; read-back of getter and `MAX_TOTAL_LENGTH` | applied | ≥ 3 values; ant passes `-D` only through `test.jvm.args` |
| U3 | B2c: exact feed schedule; sub-runs CTRL1M, C436 (line 436), EDGE (boundary) | applied | the schedule decides the exact values; line 436's true branch otherwise unexercised |
| U4 | B2d: PROBE line format | applied | observables exact |
| U5 | B2e: exact commands, stdout collection, stop condition | applied | procedure open |
| U6 | B2f: exact predictions; discard start value corrected from source | applied | source error in the filed start value, not a reading |
| U7 | B2g: rows with verdicts, order, catch-all | applied | every outcome needs a row |
| U8 | B2h: where the controls run | applied | placement open |
| C1 | B3a: macOS paths, node start, NMT and Byteman flags | applied | host differs from the design's Linux node |
| C2 | B3b: third value 8MiB | applied | ≥ 3 values |
| C3 | B3c: client verbatim through the hold, then final byte + one response per socket | applied | direct disallow evidence (line 349 at runtime) |
| C4 | B3d: NMT committed delta of `Other`; RSS via `ps`, context only; Byteman `NTFDISCARD`/`NTFFAIL`/`NTFMEM`; source expectation 384 MiB | applied | no `/proc`; decoder state otherwise unobservable |
| C5 | B3e: exact procedure, sample times, 50-s drift control, stop conditions | applied | B3h's idle control was not in B3e |
| C6 | B3f: numeric bands (235,929.6–524,288 KiB; ≤ 32,768 KiB; release ≤ 51,200 KiB) | applied | "about" values made decidable |
| C7 | B3g: rows with verdicts; heap retry not run | applied | every outcome needs a row; the retry's premise is contradicted by source |
| C8 | B3h: drift and release controls located | applied | |
| C9 | B4: clean-up on this host | applied | paths |
| R1 | Stage 3: when a design reads direct memory through NMT or the allocator metric, check the pooled allocator's chunk granularity (`-Dio.netty.allocator.maxOrder=11` → 16 MiB chunks per arena, committed on first use and kept) | left for stage 3 | led to D1 |
| R2 | Stage 3: state the feed schedule and where `discard()` starts counting (the header is discarded too) before writing exact predictions | left for stage 3 | U6 |

**Agreement criteria** — not filled (no run 2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 05:52–05:53, cluster 05:59–06:14 local time; node logs in UTC) |
| Node | `yangwang-mbp`, the advisor's laptop (Apple T6000, arm64), single host; 10 cores, 32 GiB |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64) |
| Ant | 1.10.18 |
| Python | 3.8.11 (client) |
| Local `cassandra-src` clone commit | `$W/cassandra-run54`, fresh `git clone --branch cassandra-5.0.9 ~/cassandra-src`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`; `ant -Dlocal.repository=$W/m2 build-test` BUILD SUCCESSFUL in 50 s |
| Case-file commit / harness commit | uncommitted on `advisor-run` (HEAD `6f54566`); case file sha256 `b7591e0c…6067`; harness uncommitted |
| Storage for node data | internal APFS SSD, `$W/node-ntfs` (fresh per value, removed); ≈ 121 GiB free |
| Loopback | 127.0.0.1–.3 on `lo0` (only .1 used) |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/native_transport_max_frame_size-decode-bytesToDiscard--autonomous/` (`build-test.log`, `unit-shake/`, `unit-r1/`, `cluster-shake/`, `cluster-shake2/`, `cluster-r1/`) |

Machine facts relied on: workspace `$W` and `env.sh`; every ant call with `-Dlocal.repository=$W/m2`; no `setsid` (node as a tracked
background `bin/cassandra -f`); `JVM_EXTRA_OPTS` is appended after `cassandra-env.sh`'s `MaxDirectMemorySize` so the later 2G flag wins
(`jvm-flags.txt` shows both, 2G last); test stdout in `build/test/logs/**/TEST-<class>.log`; a `-D` reaches the test JVM only through
`-Dtest.jvm.args`; Netty `ioBuffer()` is direct whenever Unsafe is available; `nodetool version` as an on-demand Byteman trigger;
node `system.log` timestamps in UTC; bash 3.2 trap guarded to the main shell; shakedown before run 1; long steps in the background.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| D1 | cluster shakedown (before run 1) | B3d (C4) instruments, B3a (C1) node flags | With the default pooled `CBUtil.allocator` the node runs with `-Dio.netty.allocator.maxOrder=11` (`conf/jvm11-server.options:145`), so each direct arena commits 16 MiB chunks on first use and keeps them. NMT `Other` and the allocator metric then count chunks, not held bytes: the shakedown's discarding node (`1MiB`, 4 connections, 2 MiB frames, every frame discarded) read `Other` +65,536 KiB and `usedDirectMemory` 67,108,864 at all samples and after close, the same as the buffering node (`run1/cluster-shake/`). The instrument could not tell retained from discarded. | Run every node of the tier with `-Dcassandra.netty_use_heap_allocator=true`: `CBUtil.allocator` becomes `UnpooledByteBufAllocator(false)`, whose `ioBuffer()` read buffers are unpooled exact-size direct buffers (Unsafe no-cleaner, charged to `Other`), grown in place by `calculateNewCapacity`; `NTFMEM` binds the unpooled allocator. Claim, bands, rows and the unit tier unchanged. Shakedown repeated (`run1/cluster-shake2/`: buffering node +16,384 KiB = 4 × 4 MiB, discarding node 0). | applied 2026-10-27, cluster tier (not yet started) run from its beginning | sha256 `b7591e0c…6067` (`_INDEX.md` §4) |

## 4. Run 1

**Scope:** both tiers, all values. **Command logs:** `native_transport_max_frame_size-decode-bytesToDiscard--autonomous/run1/unit-r1/commands.log`,
`run1/cluster-r1/commands.log`. Raw excerpts are under `run1/` (`unit-r1/TEST-<value>.log`; `cluster-r1/<value>/` with `nmt-*.txt`,
`client.out`, `btm-lines.txt`, `ntfmem-*.txt`, `rss.txt`, `config.txt`, `jvm-flags.txt`, `system-excerpt.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit-r1/TEST-<value>.log`; every PROBE value compared with the self-check's model of the decoder)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| CONFIG read-back (getter, `MAX_TOTAL_LENGTH`) | `4MiB` 4,194,304/4,194,304; `8MiB` 8,388,608/8,388,608; `16MiB` 16,777,216/16,777,216 | `TEST-4MiB.log`, `TEST-8MiB.log`, `TEST-16MiB.log` |
| 4MiB MAIN | 130 calls; call 0 `bytesToDiscard` 8,388,608, `discarding=true`; call 1 8,323,072; call 127 65,536; call 128 1; call 129 `WRAPPED(1,Request is too big: length 8388617 exceeds maximum allowed length 4194304.)`, `discarding=false`; `readableAfter` 0 at every call; capacity ≤ 65,536 | `TEST-4MiB.log` |
| 4MiB CTRL1M | 18 calls, no discard; `readableAfter` 1,048,584 after call 16; call 17 `readableBefore` 1,048,585 → `ENVELOPE(OPTIONS,1,1048576)` | `TEST-4MiB.log` |
| 4MiB C436 | call 0 (8,388,617 bytes) → `WRAPPED(1,…4194304.)`, `readableAfter` 0, `discarding=false` | `TEST-4MiB.log` |
| 8MiB MAIN | same sequence as 4MiB MAIN; call 129 `WRAPPED(1,Request is too big: length 8388617 exceeds maximum allowed length 8388608.)`; `readableAfter` 0 throughout | `TEST-8MiB.log` |
| 8MiB EDGE | no discard; `readableAfter` 8,388,607 after call 128; call 129 `readableBefore` 8,388,608 → `ENVELOPE(OPTIONS,1,8388599)` | `TEST-8MiB.log` |
| 16MiB MAIN | no discard; `readableAfter` 9 + 65,536·k, 8,388,616 after call 128; call 129 `readableBefore` 8,388,617 → `ENVELOPE(OPTIONS,1,8388608)`; capacity 12,582,912 | `TEST-16MiB.log` |
| All values as modelled | 6 sub-runs, 539 PROBE lines, 0 mismatches | `run1/selfcheck.out` |

**Cluster tier** (ΔOther = NMT `Other` committed delta in KiB against the baseline taken after 60 s idle)

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| all | — | effective value / flags | `native_transport_max_frame_size=16MiB`/`4MiB`/`8MiB`, idle timeout 0 ms; `MaxDirectMemorySize=2G` last, heap-allocator flag set, `NTFMEM` allocator `UnpooledByteBufAllocator` | `cluster-r1/<v>/config.txt`, `jvm-flags.txt`, `ntfmem-*.txt` |
| all | drift | D0 (50 s idle) | 0 / 0 / 0 | `cluster-r1/<v>/nmt-D0.txt` |
| 16MiB | A | ΔOther S1/S2/S3 | +393,216 / +393,216 / +393,216 (= 32 × 12,582,912 B) | `cluster-r1/16MiB/nmt-S1..S3.txt` |
| 16MiB | A | `usedDirectMemory` S1–S3 | 402,653,184 each (base 0) | `cluster-r1/16MiB/ntfmem-S*.txt` |
| 16MiB | A | release R / `usedDirectMemory` | +5 KiB / 0 | `cluster-r1/16MiB/nmt-R.txt`, `ntfmem-R.txt` |
| 16MiB | A | disallow evidence | `NTFDISCARD` 0, `NTFFAIL` 0; 32 responses opcode 6 (`SUPPORTED`), stream 1 | `cluster-r1/16MiB/btm-lines.txt`, `client.out` |
| 16MiB | A | RSS (context) | max +257,248 KiB during the hold (≈ 32 × 8 MiB written); not released after close | `cluster-r1/16MiB/rss.txt` |
| 4MiB | B | ΔOther S1/S2/S3; R | 0 / 0 / 0; +3 | `cluster-r1/4MiB/nmt-*.txt` |
| 4MiB | B | disallow evidence | 32 `NTFDISCARD tooLongTotalLength=8388617`; 32 `NTFFAIL … stream=1`; 32 `ERROR` 0x2200 "Request is too big: length 8388617 exceeds maximum allowed length 4194304."; discard calls 4,309 during the hold, 4,341 after | `cluster-r1/4MiB/btm-lines.txt`, `client.out` |
| 8MiB | C | ΔOther S1/S2/S3; R | 0 / 0 / 0; +3 | `cluster-r1/8MiB/nmt-*.txt` |
| 8MiB | C | disallow evidence | 32 `NTFDISCARD tooLongTotalLength=8388617`; 32 `NTFFAIL`; 32 `ERROR` "… maximum allowed length 8388608."; discard calls 4,320 / 4,352 | `cluster-r1/8MiB/btm-lines.txt`, `client.out` |
| 4MiB, 8MiB | B, C | server log (context) | 32 `WARN … WrappedException` "Request is too big" each, all at the final-byte time (10:08:34 / 10:13:30 UTC), none during the hold | `cluster-r1/<v>/system-excerpt.txt` |

### 4.2 Conclusion and logic

1. **Validity.** Unit: each JVM read back its value [observed: `unit-r1/TEST-<v>.log` CONFIG lines]; the 16MiB MAIN cumulation grew to
   8,388,616 bytes, so the buffering path was reached [observed: `TEST-16MiB.log`]. Cluster: each node ran with its value, idle timeout 0,
   the 2G direct cap and the D1 flag [observed: `config.txt`, `jvm-flags.txt`]; the client held 32 connections on every node
   [observed: `client.out` `holding 32`]; drift 0 on every node [observed: `nmt-D0.txt`]. The limit was crossed: 8 MiB frames against
   4 MiB and 8 MiB (by 9 bytes), and held below it at 16 MiB. Valid.
2. **Readings.** Nothing unusual. Run A's ΔOther equals 32 × 12,582,912 B exactly, the capacity derived from source before the run (C4)
   [observed: `nmt-S1.txt`; inferred: `calculateNewCapacity`]. RSS rose by about the written bytes, not the capacity, and did not fall
   after close; RSS is context only (C4) [observed: `rss.txt`; inferred: untouched pages are not resident, macOS keeps freed pages].
   The error responses carry version byte 0x85 and `SUPPORTED` 0x84 (context; not a row condition) [observed: `client.out`].
3. **Matched rows.** Unit **g4**: "every U6 value holds for all six sub-runs" — 539 PROBE lines equal the model's values
   [observed: `selfcheck.out`]; lines 349 (MAIN call 129) and 436 (C436 call 0) fire [observed: `TEST-4MiB.log`, `TEST-8MiB.log`].
   Cluster **h4**: B and C ≤ 32,768 KiB at S1–S3 (0, 0, 0 each); A in [235,929.6, 524,288] at S1–S3 (393,216 each); A's R = +5 ≤ 51,200;
   32 `NTFDISCARD` (8,388,617) in each of B and C and 0 in A; 32 `ERROR` "Request is too big" and 32 `NTFFAIL` in each of B and C;
   32 `SUPPORTED` and 0 `NTFFAIL` in A [observed: `cluster-r1/<v>/nmt-*.txt`, `btm-lines.txt`, `client.out`].
4. **Excluded rows.** Unit: g0 — CONFIG lines right and 16MiB MAIN grows to 8,388,616; g1 (Refuted) — 4MiB/8MiB MAIN `readableAfter`
   0 at all 260 calls, no `ENVELOPE`; g2 — first `WRAPPED` at call 129 in both; g3 — CTRL1M and EDGE end in their predicted `ENVELOPE`;
   g5 — no mismatch. Cluster: h0 — values, `holding 32` and D0 = 0 all right; h1 — A ≥ 393,216; h2 (Refuted) — B and C max 0;
   h3 — B and C ≤ 32,768; h5 — A ≤ 524,288, R ≤ 51,200, disallow evidence complete; h6 — h4 matched.
5. **Observed vs. inferred.** Inferred and load-bearing: (a) under the heap-allocator flag the cumulations are direct allocations charged
   to NMT `Other` (D1, from Netty bytecode and `CBUtil.java:59-60`), supported by `usedDirectMemory` = 402,653,184 B = ΔOther × 1,024 in A;
   (b) the D1 flag does not change the decoder path (`Envelope.Decoder` has no allocator dependency); (c) the `NTFDISCARD` rule fires at
   discard-mode entry (`AFTER WRITE tooLongTotalLength` in `decode(ByteBuf)`; one write there, `:433`).
6. **Deviations and gaps.** The cluster tier runs with `-Dcassandra.netty_use_heap_allocator=true` (D1), not the default pooled
   allocator; with the pooled allocator the same decoder behaviour holds but per-connection bytes are hidden inside 16 MiB arena chunks
   (shakedown). The unit tier measures the cumulation's readable bytes in a test-driven buffer, not process memory. Protocol v5
   (framed path, a named bypass in A3) is outside B1's claim and was not run. The number of connections is not bounded by this knob.
7. **Core question.** At 16 MiB each connection holding an incomplete 8 MiB frame kept the whole frame (12 MiB of direct capacity,
   384 MiB for 32), while at 4 MiB and 8 MiB the same frames were skipped as they arrived and direct memory did not move (parts 1, 3);
   the decoder entered discard mode once per connection and failed the frame with "Request is too big" only when its last byte arrived
   (parts 3, 4). Usage follows the limit: retained bytes per connection are about one frame below it and about zero above it, so
   `native_transport_max_frame_size` caps the per-connection buffered bytes on the unframed path (B1).

**Conclusion (one line):** unit **g4** — confirmed; cluster **h4** — confirmed.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (written before the shakedown, run end to end on both shakedowns, exit status 0; a negative known-answer run with a
wrong `--L` reported 4 mismatches and row g3) re-reads the raw files (`TEST-<v>.log`; `nmt-*.txt`, `client.out`, `btm-lines.txt`,
`config.txt`, `jvm-flags.txt`), re-derives every unit value from its own model of the decoder, and applies the U7/C7 rows. Output:
`run1/selfcheck.out` (exit 0): **UNIT ROW g4 Confirmed**, **CLUSTER ROW h4 Confirmed**. Shakedowns: `run1/selfcheck-shakedown.out`
(cluster-shake2 h4, unit-shake g4, both exit 0).

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | CONFIG lines in the three `TEST-<v>.log`; `config.txt`/`jvm-flags.txt` of each node (2G after 8192M; heap-allocator flag); `client.out` `holding 32` ×3; `nmt-D0.txt` no delta ×3. |
| 2. Readings | yes | `16MiB/nmt-S1.txt` `committed=451208KB +393216KB`; `rss.txt` max +257,248 KiB; `client.out` version bytes. |
| 3. Matched row | yes | `selfcheck.out` g4 (0 mismatches over 6 sub-runs) and h4 (all parts true); `4MiB/btm-lines.txt` and `8MiB/btm-lines.txt` 32 + 32 lines with 8,388,617 and stream 1. |
| 4. Excluded rows | yes | each g/h flag printed false in `selfcheck.out`; B/C S1–S3 all 0. |
| 5. Observed vs. inferred | yes | (a) `ntfmem-S1.txt` `direct=402653184`, `allocator=UnpooledByteBufAllocator`, = 393,216 KiB; (b) `Envelope.java:345-449` reads no allocator; (c) the rule's location type-checked (`btm-check.txt`) and its counts (32/0) match the client responses. |
| 6. Deviations and gaps | yes | D1 recorded in §3 and the case file; v5 out of scope (B1). |
| 7. Core question | yes | the logic runs: knob decides retain vs. skip (unit, exact; cluster, 393,216 vs 0 KiB), with disallow evidence on both tiers. |

### 5.2 Run 2?

**No** (2026-10-27). Both tiers match their Confirmed rows on observed readings; the inferred statements are each backed by a second
observed reading (allocator metric, counts); the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested** (B1): on the unframed CQL path a connection never holds more than about `native_transport_max_frame_size` (plus one
Netty growth step) of buffered bytes for an incomplete frame; a frame that declares more than the limit is skipped as it arrives, so
lowering the limit below the declared frame size turns per-connection retained memory from about the frame size into about zero.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g row g4) | caps | run 1 + self-check | 2026-10-27 |
| Cluster | **Confirmed** (B3g row h4) | caps | run 1 + self-check | 2026-10-27 |

Effect "caps" is for the path the claim covers (the unframed v3/v4 decoder; protocol v5's framed path is outside B1 and was not run).

**Feedback filed:** the case file's section D (uncommitted), the runbook fix D1 in the case file (B3d, before B3e), `_INDEX.md`
§2 rows (two) and §1 Stage-4 cell (uncommitted).
