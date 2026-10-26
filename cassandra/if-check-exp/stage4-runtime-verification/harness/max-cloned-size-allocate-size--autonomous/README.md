# Harness — max-cloned-size-allocate-size--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 in the results file
[§1](../../results/max-cloned-size-allocate-size--autonomous.md)). Written 2026-10-26 after the step-0 audit and before any run-1
reading; patterned on the closed sibling `memtable-offheap-space-allocate-size--autonomous`. Host `pc07` (local), tree `~/s4-b7-mc`
(`copy-source.sh`, `ant jar`), port slot 4: loopback 127.0.4.1, storage 7000, native 9042, JMX 7140. Node data on tmpfs
`/dev/shm/s4-b7-mc` (wiped per lifetime); logs `~/s4-b7-mc-logs/<run>/`.

| File | Tier | What it does |
|---|---|---|
| `SlabCapProbe.java` | unit (B2) | Package `org.apache.cassandra.utils.memory`, compiled outside the tree. One scenario per JVM: `fill` (offheap_buffers `SlabPool(heap, L)`; phase 1 at N1 = floor(L/2/S), phase 2 to the plateau, parked extra allocate on a second allocator, discard, release), `blocking` (`Barrier.issue()` + `markBlocking()`, K = ceil(16 MiB/S) allocations past L), `control` (heap_buffers `SlabPool(L, 0)`: the heap counter plateaus at L, off-heap stays 0). `STAGE4 reading k=v` raw lines and `STAGE4 check <name> ok|MISMATCH` lines (B2f as amended). Real resource: `BufferPoolMXBean` "direct" (exact) and `RssAnon`; NMT "Other" recorded. A replay of the region rule (`model`) is an instrument check. |
| `unit-run.sh <run> [instrument]` | unit | L = 32/64/128 x S = 65536, 102400, 116736, 131072, 131073, 163840, 262144 (fill); blocking at S = 102400, 262144; control at S = 102400, 131072, 131073, 262144; stops if the first run does not reach the plateau. `instrument`: hand-computed known answers (L = 4 MiB, S = 116736: 17 allocations in 3 regions, plateau 35 in 5 regions; S = 131073: 31 dedicated buffers). |
| `make-node-yaml.sh` | cluster | Node yaml: tag's cassandra.yaml plus the B3a lines as amended (offheap_buffers, heap space 512MiB, cleanup threshold 0.99, flush writers 1, commit log 4096MiB, timeouts, caches off, tmpfs dirs); JMX_PORT 7140. |
| `client.py`, `Jmx.java` | cluster | Protocol-4 driver client (`probe`, `schema`, `settings`, `big`); JMX `get`/`poll` reader. |
| `cluster-run.py <arm>` | cluster (B3e) | One lifetime per arm s128 s256 s512 (V = 102400), d128 d256 d512 (V = 204800), cs cd (heap_buffers controls), hp (heap-limit positive control); `analyze` writes the B3f relations as `EXPECTED` lines; `down`. |

**Reading rules, fixed before run 1 (not tuned to readings).** Tracked off-heap = JMX `Table AllMemtablesOffHeapDataSize` (global
gauge, 200 ms); `peak_off` = its maximum between workload start and the end of the final flush. Bound: `peak_off <= L + 16 V`.
"Limit reached" = `peak_off >= 0.9 L`, or `BlockedOnAllocation` grew with >= 2 flushes. Blocking evidence = growth of
`MemtablePool BlockedOnAllocation` Count. Equal-peak relation at each L: V=100 KiB and V=200 KiB peaks within 15 % (refuted if > 25 %).
Scaling: peaks at 256/128 in [1.7, 2.3], 512/128 in [3.2, 4.8]. Real resource, net of the control of the same V (`cs` for 100 KiB,
`cd` for 200 KiB; `heap_buffers`, same payload): net `BufferPool` direct peak delta in [0.9 L, 1.13 L + 4 MiB], net `RssAnon` peak delta in
[0.9 L, 1.3 L], and the same 1.7-2.3 / 3.2-4.8 ratios across L. Baseline = 23 s after the node serves, after two `GC.run`. Controls: `cs`, `cd`
tracked off-heap `< 1 MiB`; `hp` on-heap peak in [0.9, 1.05] x 128 MiB (+4 MiB) with blocked growth. NMT "Other" is sampled every 5 s as a secondary reading.
The allocation type is confirmed by the settings read-back plus the gauges (the DEBUG log line of B3h is not enabled).

Run order (run 1), each lifetime its own background job:

```bash
H=<repo>/cassandra/if-check-exp/stage4-runtime-verification/harness/max-cloned-size-allocate-size--autonomous
bash $H/unit-run.sh run1                       # after: bash $H/unit-run.sh instrument-1 instrument
for a in s128 s256 s512 d128 d256 d512 cs cd hp; do MC_RUN=run1 python3 -I $H/cluster-run.py $a; done
MC_RUN=run1 python3 -I $H/cluster-run.py analyze
```
