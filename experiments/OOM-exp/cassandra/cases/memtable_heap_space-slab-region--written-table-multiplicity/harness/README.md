# C6 stage-2 harness (2026-11-18, pc91, `/mydata/s4/c6-w2`)

| File | Use |
|---|---|
| `run.py` | one node lifetime: `build <label> <restore|-> <first> <last> <out>` (schema template, 8 GiB), `life <label> <T|C|I|D8> <2G|4G|8G> <template> <M>`, `shakedown`, `down` |
| `client.py` | bundled Python driver: `probe`, `settings`, `tablecount`, `schema`, `spread`, `fill` (rate-paced, ≤ 8 in flight, retry passes) |
| `Jmx.java` | stage-4 JMX reader; its `poll` mode is the 1 s sampler (amendment A2) |
| `hprof_scan.py` | HPROF scan: `byte[1048576]` count/bytes, totals, OOM thread traces (A3) |
| `HoldRegions.java`, `instrument-check.sh` | known-answer check of the scan (40 regions) |
| `analyze.py` | per-lifetime readings and P-checks |
| `plan.sh`, `plan-*.txt` | sequence runner (no new lifetime after 06:50 New York) and the plans run |
| `excerpts.sh` | builds small per-lifetime excerpts on the node |

Launch: `( setsid nohup bash harness/plan.sh harness/plan-h2.txt < /dev/null > logs/plan-h2.out 2>&1 & )` from `/mydata/s4/c6-w2`.
