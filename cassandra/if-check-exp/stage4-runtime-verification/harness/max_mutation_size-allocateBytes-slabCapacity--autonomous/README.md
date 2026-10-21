# Harness — max_mutation_size-allocateBytes-slabCapacity--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 `8ecb18b2…`, see the results file
[§1](../../results/max_mutation_size-allocateBytes-slabCapacity--autonomous.md)). Written 2026-10-20 after the step-0
audit and before any reading. Run on `pc06` (node2 of `jason92-320876`) from `~/stage4-harness-run/mss/` against the
clone `~/cassandra-run1` (`cassandra-5.0.9`, `b5f2a54210`, `ant build-test` done). Logs go to `~/stage4-logs/mss/<run>/`
on the node, node data to `~/stage4-mss/{A,B}` (local disk).

**Environment deviation (recorded in results §2):** the audit assumed the two-node setup `pc57` + `pc50`, which is no
longer in the experiment. Node A (`127.0.0.2`, JMX 7102, the seed, coordinator and measured node) and node B (`127.0.0.3`,
JMX 7103) run on loopback on one host, as the `internode_max_message_size-inferMessageSize` harness did on 2026-10-20.
B is stopped before every workload, so the hint arms need nothing from a second host.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `SlabCapacityProbeTest.java` | unit (B2) | Package `org.apache.cassandra.hints`. For C = 1 · 4 · 32 MiB and h = 100 · 1,024 · C/2 − 12: direct pool `MemoryUsed`/`Count` around `HintsBuffer.create(C)`; fill to the first null (n = ⌊C/(h+12)⌋, Σ ≤ C, `remaining()` = C − Σ after every allocation, then 0 and closed); 5 more allocations null; no direct growth while filling; `recycle()` gives the same n with no growth; `C/2 − 12` accepted, `C/2 − 11` and `C/2` throw; `free()` (extra). The derived slab `max(2·mms, 32 MiB)` for 4 · 16 · 32 MiB (arithmetic, B2b). One `STAGE4 check … ok\|MISMATCH` line per relation. | the shakedown (compiles, all checks run) |
| `unit-run.sh <run>` | unit | Upstream `HintsBufferTest`, `HintsBufferPoolTest`, then the harness test with `-Dstage4.out`. | the shakedown |
| `slab.btm` | cluster (B3d) | Byteman, observation only, on A: `created` (new slab: count, size, `MAX_ALLOCATED_BUFFERS`), `closed` (the true branch of `HintsBuffer.java:190`, with `prev`, `totalSize`, capacity), `waiting` (a writer at `take()`), `offer` (a recycled slab back in the reserve), `slowhint` (a `HintsBufferPool.write` of ≥ 5 ms), `direct` (every `ByteBuffer.allocateDirect` ≥ 1 MiB, with its stack). `boot:` because of the last rule. | `TestScript` in each lifetime; the shakedown (lines of each kind) |
| `make-node-yaml.sh <A\|B> [k=v …]` | cluster (B3a) | `~/stage4-mss/<node>/conf`: the tag's yaml plus loopback address, 4 tokens, `SimpleSnitch`, seed 127.0.0.2, directories under `~/stage4-mss/<node>/`, `hinted_handoff_enabled: true`, `max_hints_size_per_host: 0B`, `hints_flush_period: 3600000ms` (R3), `commitlog_segment_size: 32MiB`, then the arm's lines; JMX port; `-XX:MaxDirectMemorySize=2g`. | yaml tail in the summary; the `system_views.settings` read-back |
| `client.py` | cluster (B3c) | Bundled Python driver, **protocol 4** (large v5 requests leave direct frame buffers behind, the `networking_cache_size` arm L), one host, no retries: `schema`, `settings`, `bulk` (n INSERTs of 2,048 B at CL ONE, 64 in flight, latency mean/p50/p99/max), `one` (one INSERT into `ks.big`). | the shakedown |
| `Jmx.java` | cluster (B3d) | JMX client (`get`, `query`, `poll`), from the `inferMessageSize` harness. | the shakedown |
| `cluster-run.py <arm> <rep> \| analyze \| down` | cluster (B3e) | One lifetime of both nodes per call (wipe, yaml, A with the agent, B, UN, schema, read-back, B drained and stopped and seen DN, GC, baseline), then **S** 200,000 × 2 KiB, **L** 4 × 8 MiB, **X** one 17 MiB write, all at CL ONE through A; A sampled every 1 s (direct `MemoryUsed`/`Count`, heap, `TotalHints`, `TotalHintsInProgress`, VmRSS, hints directory bytes, B's process). `summary.txt` with `EXPECTED:` lines, `phases.json`, `samples.csv`, `mss.trace`. Arms: `OFF` (`hinted_handoff_enabled: false`, B3h control 1), `D` (default), `M4` (`max_mutation_size: 4096KiB`), `M32` (`32768KiB` + `commitlog_segment_size: 64MiB`), `B1` (`-Dcassandra.MAX_HINT_BUFFERS=1`). `analyze` writes the cross-arm relations. | the shakedown (`MSS_RUN=shakedown MSS_N=20000`) |

**Reading rules, fixed before run 1 (not tuned to readings).** B3f says "plus noise" and B3h asks for controls; these
make that decidable:

- *Hint-attributable direct memory* X = (A's direct `MemoryUsed` − its pre-write baseline) in the arm − the same delta in
  the `OFF` control at the same mark (end of S + 10 s, end of L + 5 s, end of X + 10 s; the peak over the run against the
  control's peak). The `OFF` control runs the same workload with hints off, so it carries every non-hint direct
  allocation (netty, scratch buffers).
- *Slabs made before the baseline* (found in shakedown 2, 2026-10-20, before any reading): on an idle node the first slab
  is created about RING_DELAY after start by `BatchlogManager` → `HintsService.flushAndFsyncBlockingly` →
  `HintsWriteExecutor$PartiallyFlushBufferPoolTask` → `HintsBufferPool.currentBuffer()`, before any hint (trace
  `created n=1 … thread=HintsWriteExecutor:1`, stack in the `direct` line). It is in the pre-write baseline of every arm.
  The pool's direct memory is therefore X + (pre-baseline `created` lines × slab), and that is what is compared with
  B3f's numbers; the literal X (from the pre-write baseline) is reported beside it. Where B3f gives a number, B3f's
  number is the prediction; these rules only say how a reading is formed.
- *Band* B = 8 MiB (a quarter of the smallest slab; cannot hide one). "Between 32 and 96 MiB" reads as
  32 − B ≤ X ≤ 96 + B; "about one slab" as 32 ± B; "same as default" as within [min, max] of the two default runs ± B.
- *Grows past k slabs* (B3g row 2): X at the end differs from (created lines × slab) by more than B, or the peak exceeds
  `MAX_HINT_BUFFERS` × slab + B.
- *The one-slab step doubles* (M32): X / k for M32 over the mean X / k of the default runs in [1.8, 2.2].
- *RSS rises by about the same amount*: (ΔRSS arm − ΔRSS `OFF`) within 25 % of X at the end.
- *Hint write latency rises* (B1, R1): the number of `HintsBufferPool.write` calls of ≥ 5 ms and their maximum are both
  above every default run's; the client's latency is reported beside it.
- *The 1.5-slab reading* (B3e step 5): the first sample at or after the midpoint of the first two `closed` lines.
- The trace (`created` count, `direct` lines from `HintsBuffer.create`) attributes the direct pool's steps; it is the
  counter beside the real resource, not a replacement for it.

Run order (run 1), each lifetime its own background job:

```bash
H=~/stage4-harness-run/mss
bash $H/unit-run.sh run1
for a in "OFF 1" "D 1" "M4 1" "M32 1" "B1 1" "D 2"; do MSS_RUN=run1 python3 $H/cluster-run.py $a; done
MSS_RUN=run1 python3 $H/cluster-run.py analyze
```
