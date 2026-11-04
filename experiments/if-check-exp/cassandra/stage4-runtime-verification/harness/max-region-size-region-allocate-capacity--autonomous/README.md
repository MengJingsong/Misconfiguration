# Harness — max-region-size-region-allocate-capacity--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 in the results file
[§1](../../results/max-region-size-region-allocate-capacity--autonomous.md)). Written 2026-10-26 after the step-0 audit and before any
run-1 reading. Host `pc12`, port slot 4: loopback 127.0.4.1, storage 7000, native 9042, JMX 7140. Node data on tmpfs `/dev/shm/s4-b7-mr`
(wiped per lifetime); logs `~/s4-b7-mr-logs/<run>/`. Three trees (all `copy-source.sh` copies): `~/s4-b7-mr` (stock, `ant build-test`),
`~/s4-b7-mr-m256` and `~/s4-b7-mr-m4096` (`MAX_REGION_SIZE` edited to `256 * 1024` / `4096 * 1024` in `NativeAllocator.java:46`, `ant jar`).
Adapted from the `memtable-offheap-space-allocate-size--autonomous` harness.

| File | Tier | What it does |
|---|---|---|
| `RegionCapProbe.java` | unit (B2) | Package `org.apache.cassandra.utils.memory`, compiled outside the trees. `fill N s`: N allocations of s bytes on one `NativeAllocator` (1 GiB pool, every page written), then region count, sum and max of capacities by reflection, `RssAnon`; `threads N s`: the same with 8 threads and the `RACE_ALLOCATED` stash read by reflection; `limit L s`: case E (fill to L, parked extra allocation, blocking-group overshoot). `MAX_REGION_SIZE` is read from the loaded class. `STAGE4 reading k=v` raw lines and `STAGE4 check <name> ok|MISMATCH`. Checks include a replay of the :163-168 rule (`model`) and the B2f literals (instrument and prediction). |
| `unit-run.sh <run> [instrument]` | unit | Stock build first (case B, the first-trigger check), then A to D on stock, m256, m4096; `threads` and `limit` on stock. `instrument` runs only the hand-computed known answer (1024 x 1 KiB: 2,088,960 in 8 regions). |
| `instrument-check.sh` | both | `javap -constants` of `MAX_REGION_SIZE` in each tree's class dir and jar, and `git diff --stat` of each tree. |
| `make-node-yaml.sh` | cluster | Node yaml: the tag's `cassandra.yaml` plus the B3a lines as amended (offheap_objects, cleanup threshold 0.99, flush writers 1, heap space 256MiB, commitlog 4096MiB, timeouts, tmpfs dirs); `JMX_PORT` 7140. |
| `client.py`, `Jmx.java` | cluster | Protocol-4 driver client (`probe`, `schema` = `ks.t` uncompressed, `settings`, `big`: 20,000 x 100,000 B, `pk = i // 20, ck = i % 20`, 16 in flight); JMX `get`/`poll` reader. |
| `cluster-run.py <arm>` | cluster (B3e) | One lifetime per arm `m256 m1024 m1024b m4096 o128 o256`; node from the arm's tree; settings read-back; first-trigger check (gauge reaches 1 MiB within 90 s); `analyze` writes the B3f relations as `EXPECTED` lines; `down`. |
| `selfcheck.py <run>` | both | Independent re-parse of the raw files (unit `.out`, `jmx.csv`, `rss.csv`, `system.log`, `big.out`), no import of the run scripts. |

**Reading rules, fixed before run 1.** Tracked off-heap = JMX `Table AllMemtablesOffHeapDataSize` (200 ms); `peak_off` = its maximum between the
workload start and the end of the final flush. Real resource = `RssAnon` of the node JVM (baseline: after the node serves, 20 s idle, two `GC.run`;
`AlwaysPreTouch` is on), `rss_peak_delta` = max over the same window minus the baseline. Disallow evidence = growth of `MemtablePool BlockedOnAllocation`
Count and `Enqueuing flush of ks.t, Reason: MEMTABLE_LIMIT` lines in `system.log`. Knob axis "flat": the three tracked peaks within 0.05 L; the three
`rss_peak_delta` spread <= 0.25 L and max/min <= 1.3. Sweep: tracked peaks ordered 64 < 128 < 256 MiB, each in [0.9 L, 1.05 L], `rss_peak_delta` ratios
128/64 in [1.5, 2.5] and 256/64 in [3.0, 5.0]. The `m1024`/`m1024b` pair is the noise estimate.

Run order (run 1), each lifetime its own background job:

```bash
H=<repo>/cassandra/if-check-exp/stage4-runtime-verification/harness/max-region-size-region-allocate-capacity--autonomous
bash $H/instrument-check.sh; bash $H/unit-run.sh instrument-1 instrument
bash $H/unit-run.sh run1
for a in m1024 m256 m4096 m1024b o128 o256; do MR_RUN=run1 python3 -I $H/cluster-run.py $a; done
MR_RUN=run1 python3 -I $H/cluster-run.py analyze
python3 -I $H/selfcheck.py run1
```
