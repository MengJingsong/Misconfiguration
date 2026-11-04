# Harness — hints-HintsBuffer-put-slabCapacity--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 in the results file
[§1](../../results/hints-HintsBuffer-put-slabCapacity--autonomous.md)). Written 2026-10-26 after the step-0 audit and
before any run-1 reading. Run on `pc07` (local) from the tree `~/s4-hb` (`copy-source.sh`, `ant build-test`), node data in
`~/s4-hb-data/{A,B}` (local disk, wiped per lifetime), logs in `~/s4-hb-logs/<run>/`. Ports: JMX 7320 (A) · 7321 (B), Byteman
9320 (A), native 9342, storage 7020, loopback 127.0.20.1 (A) · .2 (B). Pattern from the `hints-CompressedHintsWriter` harness
(client, `Jmx.java`, node yaml, driver) and the closed `MAX_HINT_BUFFERS` case (`hold-flush.btm`, copied unchanged).

| File | Tier | What it does |
|---|---|---|
| `HintsSlabCapTest.java` | unit (B2) | Package `org.apache.cassandra.hints`. One `@Test`, scenarios `boundary` (S/2-12 / S/2-11 / S/2+1 at S = 1, 4, 32 MiB), `rotation` (S = 4 MiB, 8 writers, 200 ms recycling flushes, 20 x S bytes through; allocatedBuffers, direct `MemoryUsed`/`Count` sampled every 2 ms), `stall` (flush never returns a buffer; writer parked in `take()`), `derive` (the real `HintsService.instance`, `bufferSize` for `max_mutation_size` m, and a boundary hint on its pool). `STAGE4 check <name> ok\|MISMATCH <detail>` lines. |
| `unit-run.sh <run>` | unit | Upstream `HintsBufferTest`, `HintsBufferPoolTest`; the probe once per n in 1 2 3 5 (one forked JVM each); `derive` once per m in 4 16 24 40. |
| `hb.btm` | cluster (B3d) | Byteman, observation only: `created`, `waiting`, `alloc` (hints >= 1 MiB), `allocreject` (exception exit of `HintsBuffer.allocate(int)`), `flushrun`. |
| `hold-flush.btm` | cluster trigger | Delays every `FlushBufferTask.run` by `stage4.hold.ms` (2000), loaded at start with `hb.btm`. |
| `make-node-yaml.sh`, `client.py`, `Jmx.java` | cluster | Node yaml; protocol-4 driver (`schema`, `settings`, `probe`, `hints`, `one`); JMX reader/poller. |
| `cluster-run.py <arm>` | cluster (B3e) | One lifetime per arm; arms ctl A3 A2 A6 C3 D3 B3 L; `analyze` across arms. |

**Reading rules, fixed before run 1 (not tuned to readings).** Baseline = the sample 1.5 s after the idle baseline mark (B seen DN,
`GC.run` twice, 10 s). The idle node creates its first slab at the first periodic flush (`hints_flush_period` 10 s, case 9d), usually
before the baseline: `k0` = `created` lines at or before the baseline. **Pool bytes** = (direct `MemoryUsed` minus baseline) +
`k0` x slab; `peak_pool` is its maximum after the baseline. Band 2 MiB. The case's B3f statement ("growth above baseline at most
n x slab") is read on the delta; the stricter pool-bytes relation is also reported. Slabs created are counted exactly from `created`.
The large-hint arm gets the mutation size M from `alloc hint=` (M = hint - 11, 8 bytes creation time + 3 bytes gcgs vint); rejection is
`allocreject` (the exception is swallowed after `HintRunnable`, no log line).

Run order (run 1), each lifetime its own background job:

```bash
H=<repo>/cassandra/if-check-exp/stage4-runtime-verification/harness/hints-HintsBuffer-put-slabCapacity--autonomous
bash $H/unit-run.sh run1
for a in ctl A3 A2 A6 C3 D3 B3 L; do HB_RUN=run1 python3 -I $H/cluster-run.py $a; done
HB_RUN=run1 python3 -I $H/cluster-run.py analyze
```
