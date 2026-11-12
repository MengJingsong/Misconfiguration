# networking_cache_size — native-v5 large-request release defect (B1, run 1)

**Direction:** bypass · release-defect · `source: capacity-enforcement-exp` (networking_cache_size arm L)
**Date:** 2026-11-11 (UTC 2026-11-12 on the nodes) · **Nodes:** victim `apt140` (10.10.1.1), client `apt138` (10.10.1.3)
**Status:** `negative · deployment` for memory (filed 2026-11-12 in `negatives/`) (no physical overshoot of any control's contract, no OOM at heap 2 GiB / direct 512 MiB–2 GiB, 0/4); **release defect confirmed** (V1–V4 met for the defect itself: pool capacity lost and counters drifting). Upstream defect report recommended (re-run the JIRA search first).

## Summary

- **Conclusion.** The defect is real and reproduces exactly 3/3. Every native-protocol-v5 request large enough to span frames (≥ 128 KiB) leaves its frame buffers unreleased. The pooled part is pinned forever: chunks grow by 24 MiB per 200 one-MB requests until the networking pool is permanently full at its cap (`networking_cache_size`, 128 MiB), after about 1,000 requests. From then on every networking buffer is an unpooled overflow allocation. `OverflowSize` drifts without bound (1.9 GB after 2,400 requests, 21 GB after a 10-minute load). Physical live memory does **not** exceed any control's contract: post-GC direct memory plateaus at +131 MiB (= the pool cap) and overflow stashes are reclaimed by GC. No OOM at heap 2 GiB with direct 2 GiB or 512 MiB (0/4, 10 min each, about 30k large requests). So the memory endpoint is `negative` within that range, while the release defect is confirmed.
- **Side effects measured.** (a) At the smallest acceptable direct budget (512 MiB), the unreleased overflow stashes fill direct memory between collections. `Bits.reserveMemory` then forces about 125 `System.gc()` Full GCs per 10 min: 15 s of pause, 2.5% of wall time, well below the 90% service-loss criterion. The patched build ran 14 (n=1). (b) RSS grows by +625–688 MiB over 12 cycles, against +104–137 (v4) and +50–61 (patched). This is glibc allocator retention from the extra `malloc`/`free` churn, not live memory: NMT total is flat at about +280 MiB, and `System.trim_native_heap` returned 468–552 MiB at the end of each probe (122 MiB on the patched build).
- **Root cause.** `CQLMessageHandler.LargeMessage.onComplete()` (5.0.9 `CQLMessageHandler.java:821-835`) processes the assembled envelope but never calls `releaseBuffers()`. Only abort, corruption and expiry release a large message's `ShareableBytes` slices, unlike the self-contained path and the internode twin. Restoring the release after `processRequest` (diagnostic patch) removes every residual 3/3 at equal throughput. The native-transport in-flight limits are not involved: `RequestsSize` returned to 0 at every idle.

## 1. Constraint and capacity

Pinned source: Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` base.version 5.0.9); victim build
`apt140:~/cassandra-b1` (`src/` identical to the pristine copy, jar sha256 `3e17de6b…d147`). Lead:
[stage-3 §6b/§10](../../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md),
[stage-4 arm L](../../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md).
Full source audit and protection map: [design §1–2](design/B1-design.md).

**Mechanism (source).** A v5 request whose envelope spans frames (≥ 131,071 B) is kept as
`ShareableBytes` slices of its frame buffers (`AbstractMessageHandler.java:565-579`). On success
`CQLMessageHandler.LargeMessage.onComplete()` (`CQLMessageHandler.java:821-835`) decodes and dispatches
the assembled envelope but never calls `releaseBuffers()` (`AbstractMessageHandler.java:593-596`), which
only `abort()`, corruption and expiry reach. The self-contained path and the internode twin
(`InboundMessageHandler.deserialize`) release theirs. So each large request's frame buffers never go back
to the networking `BufferPool`:

- **pooled** buffers (≤ 128 KiB: the last partial frame's stash, read buffers): their slots stay
  allocated; the networking pool does not recycle partially free chunks, so chunks are lost to the pool
  until its reserve reaches `networking_cache_size`, after which every networking buffer is an unpooled
  overflow `allocateDirect`;
- **overflow** buffers (each full-frame stash, 131,081 B): physically freed by their Cleaner at the next
  GC, but `OverflowSize` is never decremented.

**Protection map (abridged).**

| Domain | Contract C | K (counter) | U (independent) |
|---|---|---|---|
| D1 networking pool chunks/slots | `networking_cache_size`, default min(128 MiB, heap/16) = **128 MiB** at 2 GiB heap; a retention cap, overflow above it by design | `Size − OverflowSize` (chunks), `UsedSize − OverflowSize` (slots) | `java.nio` direct, NMT `Other`, after `GC.run` |
| D2 overflow stashes | none (unbounded by design, freed on `put`) | `OverflowSize` | `java.nio` direct before/after `GC.run` |
| D3 in-flight request bytes | `native_transport_max_request_data_in_flight` heap/10 = 204.8 MiB, per IP heap/40 | `RequestsSize` | — |

**Labels.** Capacity settings: all **default** (V6), resolved at the 2 GiB heap. Budget: heap 2 GiB,
`MaxDirectMemorySize` 2 GiB (V7 standing rule: ≥ 512 MiB, 2 GiB ideal); no cgroup limit. Supporting
deviations: `-XX:NativeMemoryTracking=summary` (measurement); periodic `jcmd GC.run` at idle readings in
the cycle arms (measurement; not in the OOM probe). Environment: listen/rpc/seed 10.10.1.1, directories
under `/mydata/b1/node` (`yaml.diff` per run). Interpretation: **suspected implementation defect**
(missing release on the success path), not an intentional exception.

## 2. Verification solution

Pre-run design dated 2026-11-11: [design/B1-design.md](design/B1-design.md) (claims, predictions and stop
conditions written before readings). Harness: [harness/](harness/) — `victim-ctl.sh` (victim lifetime,
readings, GC), `B1Sampler.java` (1 s JMX), `b1client.py` (bundled Python driver 3.29.0, no compression,
prints negotiated and server-side protocol), `run-arm.sh` (one cycle lifetime), `batch-cycles.sh` /
`batch-cycles2.sh` (arm order), `run-probe.sh` (OOM probe), `reduce.py`, and the diagnostic patch
`patch-release-large-buffers.diff` (intervention build `apt140:/mydata/b1/cassandra-patched`, jar sha256
`e00ee23d…307b`; `releaseBuffers()` after `processRequest` in `onComplete`).

Cycle lifetime: fresh JVM and data dir; schema over v4; 20 s idle; reading c0 (pre/post `GC.run`); then
12 cycles of 200 prepared INSERTs (pk = i mod 64, one connection, 4 in flight), 20 s idle, reading
`c<k>-pre`, `GC.run`, 5 s, `c<k>-post`.

| Arm | Build | Protocol / value | Role | Runs |
|---|---|---|---|---|
| S | unmodified | v5, 1,000,000 B | suspect path | ×3 |
| H4 | unmodified | v4, 1,000,000 B | healthy path, same payload | ×3 |
| H5s | unmodified | v5, 100,000 B (self-contained) | healthy v5 release | ×3 |
| I | patched | v5, 1,000,000 B | restored release (intervention) | ×3 |
| P | unmodified | v5, 1 MB, 8 connections × 4 in flight, no forced GC | OOM probe / budget search | see §3.3 |

Stop conditions: ≤ 6 h wall, ≤ 30 lifetimes; client errors > 1% invalidate an arm; any
`java.lang.OutOfMemoryError` stops the arm.

**Amendments (dated, before the readings they affect).** 2026-11-12 02:33Z: the smoke lifetime showed the
pidfile is written late by the daemon; `victim-ctl.sh` takes the PID from `$!` and launches the sampler
outside a subshell (no readings affected). 2026-11-12 03:10Z (after S-1): NMT *total committed* appended
to each reading, because RSS rose while NMT `Other` stayed flat; S-1 has no NMT-total column. 2026-11-12
03:29Z: the controller was stopped at a 30-min tool limit during I-1 cycle 1; that lifetime is kept as
`runs/I-1-aborted` and unused, and I-1 was rerun from a clean start (`batch-cycles2.sh`). After the main arms:
`System.trim_native_heap` was added at the end of each probe (allocator-retention check), and one
intervention probe PI-512M-1 (patched, n=1) was added to attribute the explicit-GC count. The session was
paused by a usage limit between 05:05Z and 07:00Z (no processes running); the probes ran afterwards.

## 3. Runtime results

### 3.1 Preflight and calibration

`apt140` (r320, 16 hyperthreads, 15 GiB, 8 GiB swap unused, kernel 5.15.0-198, OpenJDK 11.0.33, G1, cgroup v2,
no limit) and `apt138` (same; Python 3.10.12, no `lz4`). Every lifetime logged `Global buffer pool limit is
512.000MiB for chunk-cache and 128.000MiB for networking` and `-Xms2G -Xmx2G -XX:MaxDirectMemorySize=<2G|512M>`.
Protocol selection was confirmed per cycle: the client reported `proto_client=5 proto_server=[5]` (from
`system_views.clients`) in S, H5s and I, and `4/[4]` in H4. Smoke lifetime (64 + 64 requests, [log](logs/controller-smoke.out)):
`OverflowSize` +58,724,288 B and slots in use +5,373,952 B per 64 requests, exactly arm L's figures.

### 3.2 Cycle arms (12 × 200 requests per lifetime, heap 2 GiB, direct 2 GiB; deltas from c0, post-`GC.run`)

S c1 is exact for every S run: `OverflowSize` **+183,513,400 B = 200 × 917,567**; slots in use
**+16,793,600 B = 200 × 83,968**.

| Run | Chunks reserved c1 / c4 / c5 / c12 (MiB) | Slots in use c12 (MiB) | `OverflowSize` c12 (MiB) | Overflow per cycle c2–5 / c6–12 (MiB) | `java.nio` direct c12 (MiB) | NMT total c12 (MiB) | RSS c12 (MiB) | `RequestsSize` at idle | Pool-exhausted INFO | Throughput (MB/s) | Errors |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S-1 | 32 / 104 / **128** / **128** | 82.0 | 1,902 | 175.0 / 146.7 | +131.3 | n/a | +688 | 0 | cycle 5 | 125 | 0/2400 |
| S-2 | 32 / 104 / 128 / 128 | 82.0 | 1,863 | 175.0 / 141.2 | +131.3 | +280 | +625 | 0 | yes | 126 | 0 |
| S-3 | 32 / 104 / 128 / 128 | 82.0 | 1,879 | 175.0 / 143.4 | +131.3 | +279 | +684 | 0 | yes | 126 | 0 |
| H4-1/2/3 | 0 | 0 | 0 | 0 | +3.3 | +150–172 | +104–137 | 0 | no | 75–116 | 0 |
| H5s-1/2/3 | 8 (one chunk) | 0 | 0 | 0 | +10.1–10.6 | +153–170 | +27–75 | 0 | no | 60–100 | 0 |
| I-1/2/3 | 8 (one chunk) | 0 | 0 | 0 | +10.3–11.3 | +142–175 | +50–61 | 0 | no | 116–125 | 0 |

Pre-GC direct memory in S rose to +323 MiB (c12) and fell back to +131 MiB after `GC.run`: the overflow
stashes are garbage, not live. The pooled residual is linear in requests until the pool's reserve reaches
its 128 MiB cap at cycle 5. From cycle 6 it is flat, and every networking buffer becomes a miss: Misses grow
1,400 per cycle before the plateau (7 full-frame stashes per request) and 5,000–9,000 per cycle after it.
After the plateau `OverflowSize` grows more slowly (141–147 instead of 175 MiB per cycle), which the source
reading did not predict; the counter still rises monotonically in every cycle (not explained, recorded).
Reduced tables per run: `logs/<run>/reduced.txt`.

### 3.3 OOM probe and budget search (8 connections × 4 in flight, 1 MB v5 INSERTs, 600 s, no forced GC during load)

| Run | Build | Direct | OOM / dead | Peak `java.nio` direct | Post-GC direct (vs p0) | Slots in use (max) | `OverflowSize` end | Full GCs (`System.gc()`) / pause sum | Other GC pauses | RSS end → after trim | Client ok / err (per 8 procs) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P-2G-1 | unmod | 2 GiB | no | 686 MiB | +131 MiB | 82 MiB | 21.0 GB | 14 / 1.6 s | 126 / 2.6 s | 3,069 → 2,517 MiB (−552) | ≈ 3,830 / 690 |
| P-512M-1 | unmod | 512 MiB | no | 512 MiB | +131 MiB | 82 MiB | 21.7 GB | **124 / 14.9 s** | 9 / 0.1 s | 2,965 → 2,497 (−468) | ≈ 3,800 / 675 |
| P-512M-2 | unmod | 512 MiB | no | 512 MiB | +132 MiB | 82 MiB | 20.8 GB | **129 / 15.0 s** | 9 / 0.1 s | 2,999 → 2,524 (−475) | ≈ 3,830 / 680 |
| P-512M-3 | unmod | 512 MiB | no | 512 MiB | +132 MiB | 82 MiB | 21.0 GB | **131 / 14.9 s** | 9 / 0.1 s | 2,987 → 2,510 (−476) | ≈ 3,820 / 678 |
| PI-512M-1 | patched | 512 MiB | no | 184 MiB | +68 MiB (chunks in use) | 3.2 MiB | **0** | 14 / 1.4 s | 121 / 2.8 s | 2,563 → 2,440 (−122) | ≈ 3,710 / 686 |

`java.lang.OutOfMemoryError`, `failed to allocate`, hprof, hs_err: none in any run. About 15% of client
requests ended in `WriteTimeout` (default 2 s `write_request_timeout`) in every probe, unmodified and patched
alike. Eight connections exceed the commit-log disk throughput, so these are coordinator write timeouts after
each request body had been fully received; the receive path was exercised in full. `RequestsSize` peaked at
22.5 MiB (8 × 4 × ≈ 1 MB, far below the 204.8 MiB limit). The Full-GC count at 512 MiB counts explicit
`System.gc()` collections that `Bits.reserveMemory` forces once unreleased overflow stashes fill the
direct limit. On the patched build each stash is freed at `put` (`FileUtils.clean`), and the count falls
back to the 2 GiB level. Excerpts: `logs/P-*/`, `logs/PI-512M-1/`, controller logs `logs/controller-*.out`.

**Budget search.** The leak cannot reach OOM: after the plateau its live footprint is fixed at the pool cap
(≤ 128 MiB), and the overflow residue is reclaimed by GC, forced by the JVM when the direct limit is reached.
The smallest acceptable direct budget, 512 MiB, did not fail (0/3), so no larger budget fails either. **No
failing budget ≥ 512 MiB exists within this workload; the largest failing budget is "none" (0/4 runs at
512 MiB–2 GiB).** Budgets below 512 MiB (tightened, V7 unmet) were not tested.

### 3.4 Raw logs

Victim: `apt140:/mydata/b1/runs/<run>/` (`samples.csv` 1 s JMX, `readings.csv`, `logs/system.log`, `logs/gc.log*`,
`stdout.log`, `run.meta`, `yaml.diff`, `conf/`). Client: `apt138:/mydata/b1/runs/<run>/client.log` (cycle arms),
`client-<i>.log` (probes). Patched tree and build log: `apt140:/mydata/b1/cassandra-patched`, `/mydata/b1/patched-build.log`.
Runs: `smoke`, `S-1..3`, `H4-1..3`, `H5s-1..3`, `I-1..3` (`I-1-aborted` unused), `P-2G-1`, `P-512M-1..3`, `PI-512M-1`.
Cleanup verified 2026-11-12 ≈ 08:20Z: no Cassandra JVM, sampler or client process on `apt140` or `apt138`.

## 4. Conclusion

**Protection gap: the release defect is confirmed; a memory bypass is refuted within the tested range.**

- *Confirmed.* On the success path, native-v5 large requests never return their frame buffers to the
  networking `BufferPool`. The defect is reproducible to the byte (83,968 B pinned and 917,567 B of
  `OverflowSize` per one-MB request), absent on v4 and on self-contained v5 requests, and removed 3/3 by
  restoring `releaseBuffers()` after `processRequest`. Consequences in a running node: (1) about 1,000 large
  requests permanently exhaust the networking pool, so every later networking buffer is an unpooled
  `allocateDirect`/`free`. In a multi-node cluster that includes internode messaging, which was not
  measured here. (2) The `OverflowSize`/`UsedSize`/`Size` metrics become meaningless, since they grow by tens
  of GB per hour under load. (3) Under a small direct limit, the unreleased stashes trigger repeated
  JVM-forced Full GCs: about 0.2 per second and 2.5% pause time at 512 MiB. (4) RSS grows by several hundred
  MiB of glibc allocator retention.
- *Refuted (memory).* Live memory past a contract does not occur. The pinned bytes stay inside
  `networking_cache_size` (U = 128 MiB of chunks = C; K counted them), and the overflow stashes are
  GC-reclaimable (U returns to the plateau after GC while K drifts). The protocol's "counter drift alone does
  not prove physical growth" applies: no `U > C`, no OOM, no service loss (2.5% ≪ 90%).
- *OOM.* Not reached: 0/4 at heap 2 GiB with direct 2 GiB or 512 MiB, constraints at defaults.
- *Attribution limits.* The intervention for the explicit-GC count is n=1. Allocator retention is shown by
  trim, not by a malloc profiler. A single node and a single client host were used, with no internode
  traffic. The reduced overflow growth after the plateau is unexplained. The probes saw about 15% write
  timeouts, from disk-bound commit-log writes. Larger requests (up to the 16 MiB message limit), more
  connections, and a direct budget below 512 MiB were not tested.
- *Interpretation and upstream.* This is a suspected implementation defect, not an intentional exception:
  the self-contained and internode paths release their buffers. An upstream report is justified as a
  functional/metrics defect, with pool exhaustion, a drifting `OverflowSize` and forced GCs at small direct
  limits, and with the one-line restoration as the proposed fix. The earlier JIRA search (2026-10-15) found
  no ticket; repeat it before filing.

### V1–V7

| | Status | Evidence |
|---|---|---|
| V1 Repetition | met: defect endpoint 3/3 (S-1..3), no-OOM endpoint 0/4 (P runs) | §3.2, §3.3 |
| V2 Matched control | met: H4 ×3 and H5s ×3, no residual or drift | §3.2 |
| V3 Measurement | met: U (`java.nio` direct pre/post GC, NMT total, RSS, trim) independent of K (pool gauges, `RequestsSize`) | §3.2–3.3 |
| V4 Intervention | met for the residual (I ×3); explicit-GC excess n=1 (PI-512M-1) | §3.2, §3.3 |
| V5 Initiating failure | n/a (no failure); GC logs over every probe window kept | §3.3, raw logs |
| V6 Default constraints | met: `networking_cache_size`, in-flight limits, message size and receive queue at defaults (128 MiB / 204.8 MiB / 51.2 MiB / 16 MiB at a 2 GiB heap) | §1, `yaml.diff` |
| V7 Acceptable budget | met: heap 2 GiB; direct 2 GiB and 512 MiB (standing rule, ≥ 512 MiB) | §1, §3.3 |

Per-condition status: **memory/OOM: `negative · deployment`** (heap 2 GiB, direct 512 MiB–2 GiB, defaults,
1 MB v5 requests, up to 8 connections, 10 min). **Release defect: confirmed (no memory endpoint)**, upstream
report recommended. Supporting deviations: NMT summary, `jcmd GC.run` at cycle readings (cycle arms only),
1 s JMX sampler.

