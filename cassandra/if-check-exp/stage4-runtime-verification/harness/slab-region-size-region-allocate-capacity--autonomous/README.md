# Harness — slab-region-size-region-allocate-capacity--autonomous

Stage-4 harness for the autonomous case file (frozen hashes in the results file
[§1](../../results/slab-region-size-region-allocate-capacity--autonomous.md)). Written 2026-10-26 after the step-0 audit and before any
run-1 reading; the cluster tier is patterned on the closed sibling `max-cloned-size-allocate-size--autonomous` (code only). Host `pc07`
(local), tree `~/s4-b7-sr7` (`copy-source.sh`, `ant jar`, stock), port slot 5: loopback 127.0.5.1, storage 7000, native 9042, JMX 7150.
Node data on tmpfs `/dev/shm/s4-b7-sr7` (wiped per lifetime); logs `~/s4-b7-sr7-logs/<run>/`.

| File | Tier | What it does |
|---|---|---|
| `replay.py` | both | The rule of `Region.allocate` replayed (B2f table, limit stalls, cluster row layout). Run before any probe; its output is the source of the frozen numbers. |
| `SlabWasteProbe.java` | unit (B2) | Package `org.apache.cassandra.utils.memory`, compiled outside the tree. `waste <offheap\|heap> S N`; `limit <type> L S N` (worker thread, 5 s join, stack printed); `threads S rounds` (8 threads, fresh allocator per round, `RACE_ALLOCATED` size read). Reads regionCount / unslabbedSize / REGION_SIZE by reflection, `BufferPoolMXBean` direct, RssAnon, retained heap. `STAGE4 reading k=v` and `STAGE4 check`. Pool = `new SlabPool(...)` as `createMemtableAllocatorPoolInternal` builds it (the factory class needs `DatabaseDescriptor` at class init). |
| `unit-run.sh <run> [instrument]` | unit | Compiles the probe and the 512 KiB / 2 MiB `SlabAllocator` class directories (line 51 edited in a copy outside the tree, `diff` saved). `instrument`: hand-computed known answers (1024 x 1 KiB = 1 region; L 4 MiB, S 116509 = 35 allocations in 5 regions; variants report 524288 / 2097152). Full run: first-trigger check (regionCount 50), then the B2c cases. |
| `instrument-check.sh` | both | Stock tree, variant diffs, `javap -constants` of REGION_SIZE. |
| `make-node-yaml.sh`, `client.py`, `Jmx.java` | cluster | Node yaml (B3a as amended); protocol-4 driver client (`big n S conc [rows/s [first key]]`); JMX `get`/`poll`. |
| `cluster-run.py <arm>` | cluster (B3e) | One lifetime per arm `a64 a128 a64b e64 f64 h64`; phase A 3000 rows at 50 rows/s, phase B 2000 rows unthrottled; settings read-back; first-trigger check; `analyze` writes the B3f relations as `EXPECTED` lines; `down`. |
| `selfcheck.py <run>` | both | Independent re-parse of the raw files, literals typed again, no import of the run scripts. |

**Shakedown finding (no capacity reading used).** `AllMemtablesOffHeapDataSize` reports the table's current memtable only
(`TableMetrics.java:876-883`); with an unthrottled writer the flushing memtable's regions sit in the direct reading and not in the gauge, so the
workload has a throttled phase A (clean samples for `rho`, `peak_acc`, `peak_dir`, RssAnon) and an unthrottled phase B (blocked-on-allocation evidence).

**Reading rules, fixed before run 1** (B3d): `acc` = the gauge (200 ms); `dir` = BufferPool direct MemoryUsed minus baseline (23 s after the node serves,
two `GC.run`); `rho` = median `dir/acc` over phase-A samples with `acc` >= 0.9 L; bands in B3f. Disallow evidence = `BlockedOnAllocation` Count growth and
`Enqueuing flush of ks.t ... Reason: MEMTABLE_LIMIT` lines.

Run order (run 1), each lifetime its own background job:

```bash
H=<repo>/cassandra/if-check-exp/stage4-runtime-verification/harness/slab-region-size-region-allocate-capacity--autonomous
python3 -I $H/replay.py; bash $H/instrument-check.sh; bash $H/unit-run.sh instrument-1 instrument
bash $H/unit-run.sh run1
for a in a64 a128 e64 f64 a64b h64; do SR_RUN=run1 python3 -I $H/cluster-run.py $a; done
SR_RUN=run1 python3 -I $H/cluster-run.py analyze
python3 -I $H/selfcheck.py run1
```
