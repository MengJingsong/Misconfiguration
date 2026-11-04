# Harness — tombstone_failure_threshold-countTombstone-tombstones--autonomous

Stage-4 harness for the autonomous case file (audit freeze sha256 `9e62de3a…`; run 1 used the version with runbook fixes
D1–D3, sha256 `b509de1d…`; see the results file [§1 and §3](../../results/tombstone_failure_threshold-countTombstone-tombstones--autonomous.md)).
Written 2026-10-21, run on `pc13` (`node3.jason92-320876`) from a copy in `~/stage4-harness-run/tft/` (md5 in
`~/stage4-harness-run/tft.md5`) against a fresh clone `~/cassandra-tft` (`cassandra-5.0.9`, `b5f2a54210`, `ant build-test`).
Logs go to `~/stage4-logs/tft/<run>/` on the node; node data to `/local/tft-run` (local `/dev/sda3`).

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `TombstoneFailureThresholdMemoryTest.java` | unit (B2) | The case file's B2e test with audit amendments R1 (`UPDATE … SET v = null`), R2 (`ORIGINAL` in `@BeforeClass`) and runbook fix D1 (read thresholds off, as on a default node). | unit shakedown (N = 300 copy); run-1 attempt 1 found D1 |
| `unit-run.sh [run] [shakedown]` | unit | B2e steps 1–5: copies the test into the clone, `ant testsome`, collects `tft-unit.tsv` and the junit XML, removes the test, runs `unit-analyze.py`. `shakedown` runs a renamed copy with N = 300 and T / 100. | shakedown1 |
| `unit-analyze.py <tsv>` | unit | B2f/B2g with R4's definitions as `EXPECTED:` lines and the matched row. | shakedown1 |
| `cluster-run.py all \| down` | cluster (B3) | B3a conf (+ R3), node start/stop per T, schema, `ingest.cql` (R1) loaded with `cqlsh -f`, flush, traced check; per T a fresh lifetime: sjk read-back, traced warm-up, idle window, `ThreadAlloc` (R5), JFR, the 8 × 5 `cqlsh` storm with `HeapPoll` alongside (D3), metrics, `system.log` segment. Env `TFT_*` scales it down for a shakedown. | shakedown2 (found D3 and a stop-wait bug), shakedown2b/3 (N = 2,000 / 20,000) |
| `cluster-analyze.py <dir> [unit tsv]` | cluster | B3f/B3g with R4 (and D2: criterion (c) on the OU rise) as `EXPECTED:` lines, `readings.csv`, the matched row. | on shakedown3 |
| `HeapPoll.java` | cluster | EU / OU / SU from the JMX memory pools every 250 ms (D3: `jstat` cannot attach under `-XX:+PerfDisableSharedMem`). | shakedown3 |
| `ThreadAlloc.java` | cluster | Sum of `getThreadAllocatedBytes` over the node's live threads (R5). | shakedown2/3 |
| `JfrBuf.java` | cluster | Lists `ObjectAllocationOutsideTLAB` / `InNewTLAB` events of a `.jfr`; `buf` = stack holds `DataOutputBuffer.expandToFit`. | shakedown3 |
| `selfcheck.py <unit> <cluster> <RUN>` | both | Independent re-parse: junit XML, every client output, `system.log` ERROR lines and config dump, raw `.jfr` through the JDK's `jfr print --json`, `HeapPoll` files, gc logs. | — |

Run order (run 1):

```bash
H=~/stage4-harness-run/tft
bash $H/unit-run.sh run1
python3 $H/cluster-run.py all                       # one background job, about 30 min
python3 $H/cluster-analyze.py ~/stage4-logs/tft/run1/cluster ~/stage4-logs/tft/run1/unit/tft-unit.tsv
python3 $H/selfcheck.py ~/stage4-logs/tft/run1/unit ~/stage4-logs/tft/run1/cluster /local/tft-run   # run 1; /local/tft-run was then removed, re-run with ~/stage4-logs/tft/run1/cluster-raw
```
