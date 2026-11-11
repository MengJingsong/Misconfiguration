# Harness — index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous

Stage-4 harness for the autonomous case file (audit freeze sha256 `5bc45c0d…`; see the results file
[§1](../../results/index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous.md)). Written 2026-10-21 and
run on `pc12` (`node1.jason92-320876`) from a copy in `~/stage4-harness-run/isc/` (md5 in `~/stage4-harness-run/isc.md5`) against a
fresh clone `~/cassandra-isc` (`cassandra-5.0.9`, `b5f2a54210`, `ant build-test`). Logs go to `~/stage4-logs/isc/<run>/` on the
node; node data to `/tmp/isc-jason92` (local `/dev/sda3`). No Byteman: the line-341 evidence is the class's own TRACE lines.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `IndexSummaryCapacityProbeTest.java` | unit (B2) | The case file's B2e test with amendment R1 only: each `PROBE` line is formatted once and also appended whole to `-Dprobe.out`; `NUM_PARTITIONS` reads `-Dprobe.partitions` (2048 for run 1). | compiled and run by `ant testsome` in shakedown1 (256 partitions) |
| `unit-run.sh [run] [partitions]` | unit | Copies the test into `~/cassandra-isc/test/unit/org/apache/cassandra/io/sstable/indexsummary/`, runs `ant testsome` twice (B2e steps 2 and 4), keeps `rep{1,2}.probe`, ant logs, junit XML and per-test logs, runs `unit-analyze.py`. `--remove` deletes the copied test (B2e step 5). | shakedown1 |
| `unit-analyze.py <dir>` | unit | B2f/B2g + R2 as `EXPECTED:` lines and the R2 verdict mapping. | shakedown1 |
| `cluster-run.py` | cluster (B3) | `ISC_RUN=<run> [ISC_N=4000000] [ISC_N2=1000000]`. Builds `$RUN/conf` per B3a (+ the R4 TRACE appender), the stress profiles `isc.yaml` / `isc2.yaml`; lifetimes L0 load (4096) · L1 4096 · L2 default · L3 400 · L4 100 · L5 0 · L6 0 + step 5 (`max_index_interval = 1`) · L7 step 6 (100, interval `null`, manual `redistributeSummaries` over `nodetool sjk`, +N2 partitions, 120 s). Per lifetime: a 2-s RssAnon sampler (R4), the first "Completed resizing" line after the lifetime's log offset, +30 s, five RssAnon samples at 10 s, `tablestats`, Summary.db sizes, TRACE keep / re-sample counts for `isc/t`. Writes `session.log`, `phases.json`, `rss-<life>.csv`, `system-<life>.log`, `isr-trace-<life>.log`, `stress-*.out`, `summary.txt`. Stops the node on every exit. | shakedown2 (N = 300,000) |
| `cluster-analyze.py <dir>` | cluster | B3f/B3g + R3–R6 as `EXPECTED:` lines and the R5 verdict mapping. | shakedown2 |
| `selfcheck.py <unit dir> <cluster dir>` | both | Independent re-parse of the raw files (junit XML / per-test logs, `system-<life>.log`, `isr-trace-<life>.log`, `rss-<life>.csv`, `session.log`), not `phases.json`'s derived numbers. | run on run 1 |

Run order (run 1):

```bash
H=~/stage4-harness-run/isc
bash $H/unit-run.sh run1
ISC_RUN=run1 python3 $H/cluster-run.py          # one background job, about 30 min
python3 $H/selfcheck.py ~/stage4-logs/isc/run1/unit ~/stage4-logs/isc/run1/cluster
bash $H/unit-run.sh --remove
```

Defects found with this harness (details in the results file §3): H1, H2 (`cluster-run.py`, shakedowns 2–3), H3 (`selfcheck.py`: the
PROBE cross-check reads the ant log, since the junit XML holds no stdout), D1 (stress `population: seq(…)` on the key repeats keys:
removed; step 6 uses `-pop seq=N+1..N+N2`), D2 (the step-5 ALTER must name `min_index_interval = 1` too), D3 (R5's RSS-agreement row
compares ΔR_w only where the run changed T by ≥ 16 MiB; `cluster-analyze.py` and `selfcheck.py` follow it). Run 1 cluster attempt 1
(before D3) is in `~/stage4-logs/isc/run1-attempt1-cluster/`; attempt 2 is `run1/cluster/`.
