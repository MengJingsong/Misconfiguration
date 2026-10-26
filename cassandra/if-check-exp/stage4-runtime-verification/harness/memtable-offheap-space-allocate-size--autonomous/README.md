# Harness — memtable-offheap-space-allocate-size--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 in the results file
[§1](../../results/memtable-offheap-space-allocate-size--autonomous.md)). Written 2026-10-26 after the step-0 audit and before any
run-1 reading. Host `pc07` (local), tree `~/s4-b7-mo` (`copy-source.sh`, `ant build-test`), port slot 3: loopback 127.0.3.1,
storage 7000, native 9042, JMX 7130. Node data on tmpfs `/dev/shm/s4-b7-mo` (wiped per lifetime); logs `~/s4-b7-mo-logs/<run>/`.

| File | Tier | What it does |
|---|---|---|
| `OffheapCapProbe.java` | unit (B2) | Package `org.apache.cassandra.utils.memory`, compiled outside the tree. One scenario per JVM: `fill` (non-blocking group; plateau, parked extra allocate on a second allocator, discard, release), `blocking` (`Barrier.issue()` + `markBlocking()`, then 10 allocations past L), `control` (`SlabPool` heap_buffers, `SlabAllocator.allocate`). `STAGE4 reading k=v` raw lines and `STAGE4 check <name> ok|MISMATCH` lines (B2f as amended). RssAnon is read with every allocation touched page by page (NMT cannot see JNA malloc, case file B2d note); a replay of the region-size rule (`model`) is an instrument check. |
| `unit-run.sh <run> [instrument]` | unit | L = 32/64/128 x S = 100, 1024, 102400, 131072, 131073, 1048576 (fill); blocking and control at L = 64; L = 1 MiB tiny pools; stops if the first run does not reach the plateau. `instrument` runs only the hand-computed known answer (L = 1 MiB, S = 1 KiB: capacity 2,088,960 in 8 regions). |
| `make-node-yaml.sh` | cluster | Node yaml: tag's cassandra.yaml plus the B3a lines as amended (offheap_objects, cleanup threshold 0.99, flush writers 1, heap 1024MiB, timeouts, tmpfs dirs); JMX_PORT 7130. |
| `client.py`, `Jmx.java` | cluster | Protocol-4 driver client (`probe`, `schema`, `settings`, `big`); JMX `get`/`poll` reader. |
| `cluster-run.py <arm>` | cluster (B3e) | One lifetime per arm k128 k256 k512 b128 b256 b512 ctl hp; `analyze` writes the B3f relations as `EXPECTED` lines; `down`. |

**Reading rules, fixed before run 1 (not tuned to readings).** Tracked off-heap = JMX `Table AllMemtablesOffHeapDataSize` (global
gauge, 200 ms); `peak_off` = its maximum between workload start and the end of the final flush. Tolerance: 1 KiB arms `<= 1.05 L`;
256 KiB arms `<= L + 4 MiB`. "Limit reached" = `peak_off >= 0.9 L`. Blocking evidence = growth of `MemtablePool BlockedOnAllocation` Count.
Real resource = `RssAnon` of the node JVM (baseline: 23 s after the node serves, after two `GC.run`; `AlwaysPreTouch` is in the shipped
`jvm-server.options`), `rss_peak_delta` = max over the same window minus baseline; `<= 1.3 L`; ratios 256/128 in [1.5, 2.5] and 512/128 in
[3.0, 5.0]. NMT "Other" is sampled every 5 s only to show that it does not see the regions. Flushes = "Enqueuing flush of" lines for the table
in `system.log`. Controls: `ctl` tracked off-heap `< 1 MiB`, `RssAnon` delta `<= 0.3 x 256 MiB`; `hp` on-heap peak `<= 1.05 x 128 MiB + 4 MiB`, blocked grew, peak `>= 0.9 x 128 MiB`.

Run order (run 1), each lifetime its own background job:

```bash
H=<repo>/cassandra/if-check-exp/stage4-runtime-verification/harness/memtable-offheap-space-allocate-size--autonomous
bash $H/unit-run.sh run1                       # after: bash $H/unit-run.sh instrument-1 instrument
for a in k128 k256 k512 b128 b256 b512 ctl hp; do MO_RUN=run1 python3 -I $H/cluster-run.py $a; done
MO_RUN=run1 python3 -I $H/cluster-run.py analyze
```
