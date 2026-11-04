# Harness — index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous

Stage-4 harness for the autonomous case file (audit freeze sha256 `fd688570…`; see the results file
[§1](../../results/index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous.md)). Written 2026-10-21 and run on
`pc12` (`node1.jason92-320876`) from a copy in `~/stage4-harness-run/is2/` (md5 in `~/stage4-harness-run/is2.md5`) against a fresh
clone `~/cassandra-is2` (`cassandra-5.0.9`, `b5f2a54210`, `ant build-test` 1 min 11 s). Logs go to `~/stage4-logs/is2/<run>/` on the
node; node data to `~/stage4-is2` (local `/dev/sda3`). Borrowed from the `:341` harness
(`../index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous/`): the probe-file output, the TRACE appender,
the lifetime / sampler structure; new here: the operand at line 258 (reflection and `getCompactionInfo()` in the unit test, a
Byteman rule on the node), runtime capacity changes over JMX within one lifetime, and the forced-upsample restore (R7).

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `IndexSummaryCapacityProbeTest.java` | unit (B2) | The case file's B2e test with amendments R1–R3: 10 sstables × `-Dprobe.partitions` (10,000) partitions, min/max index interval 8/256; reset with read meters 100 (R2); for P0–P4 reads `remainingSpace` at `:258` by reflection and as `pool − getCompleted()`, the predicted `R = P − N·F'`, k, T; appends whole `PROBE` lines to `-Dprobe.out`. | shakedown1 (1,000 partitions) |
| `unit-run.sh [run] [partitions]` | unit | Copies the test into `~/cassandra-is2`, runs `ant testsome` twice (rep1 reading, rep2 repeat), keeps probe files, ant logs, junit XML, runs `unit-analyze.py`. `--remove` deletes the copied test. | shakedown1 |
| `unit-analyze.py <dir>` | unit | B2f/B2g + R3 as `EXPECTED:` lines and the R3 verdict mapping. | shakedown1 (found H1) |
| `r258.btm.in` | cluster | Byteman rule `AT LINE 258` of `IndexSummaryRedistribution.adjustSamplingLevels`: writes `$this.remainingSpace` and the pool (`$4`) to `logs/r258.log` (R6 item 2). `@OUT@` is filled by `cluster-run.py`. | shakedown2: one line per run, `R = pool − ΣF'` to the byte |
| `cluster-run.py` | cluster (B3) | `IS2_RUN=<run> [IS2_BATCH=100000] [IS2_BATCHES=20] [IS2_NEG_S=300]`. Builds `~/stage4-is2/conf` (R4: ports 17000/17001/19042/17199, cap 64 MiB, interval null, TRACE appender), the B3c profile without `population:` (R5); L0: load 20 batches with a flush each, baseline, C = 4096 · 1024 · 512 · 64 · 8 set over `nodetool sjk mx -ms`, each followed by the R7 restore (ALTER min = max = 1, cap 8192, run, ALTER back to 1/2048), negative control (cap 64, 300 s, no run); L1: auto default (yaml empty) run. Per run: RssAnon 30 s before (6 × 5 s), the trigger (`sjk mx -mc -op redistributeSummaries`), the Beginning / downsample / Completed lines, TRACE keep / re-sample counts, the R258 line, 30 s, RssAnon 5 × 10 s, JMX `MemoryPoolSizeInMB`, `tablestats`, `IndexIntervals`, Summary.db sizes, `compactionstats`. A 2-s RssAnon sampler runs for each lifetime. Writes `session.log`, `phases.json`, `rss-<life>.csv`, `system-<life>.log`, `isr-trace-<life>.log`, `r258-<life>.log`, `stress-*.out`, `summary.txt`. Stops the node on every exit. | shakedown2 (20 × 10,000) |
| `cluster-analyze.py <dir>` | cluster | B3f/B3g + R8 as `EXPECTED:` lines (sub-predictions marked) and the R8 verdict mapping. | shakedown2 |
| `selfcheck.py <unit dir> <cluster dir>` | both | Independent re-parse of the raw files (ant-log PROBE lines, the B2f values typed in; every Beginning / Completed line in order, R258 lines, TRACE per run, the 2-s RssAnon csv as a second reader, stress outputs), compared with the B3f table typed in. | run 1: 109 / 109 |

Run order (run 1):

```bash
H=~/stage4-harness-run/is2
bash $H/unit-run.sh run1
IS2_RUN=run1 python3 $H/cluster-run.py          # one background job, about 32 min
python3 $H/selfcheck.py ~/stage4-logs/is2/run1/unit ~/stage4-logs/is2/run1/cluster
bash $H/unit-run.sh --remove
```

Defects found with this harness: H1 (`unit-analyze.py` did not parse the bare `PROBE done` line and returned "Invalid" on
shakedown1; regex fixed, harness only). The audit's runbook fixes R2 (unit reset), R5 (stress key population) and R7 (restore by
forced upsample) were made before any reading; run 1 met no defect.
