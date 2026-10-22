# Harness — memtable_heap_space-adjustMemtableSize-0--autonomous

Stage-4 instruments for `cases/memtable_heap_space-adjustMemtableSize-0--autonomous.md` (run 1, 2026-10-22, `pc07`).
Run copies live in `pc07:~/stage4-harness-run/sai/` (unit tier, attempt 1 of the cluster tier) and `pc07:~/stage4-harness-run/sai/attempt2/` (cluster tier run 1), each with `SHA256SUMS`; never edit a running copy. Fixes after R1 attempt 1 (no load written): `sai-profile.yaml` `CREATE INDEX IF NOT EXISTS` (defect D1), and `cluster-run.sh` OOM count matches `OutOfMemoryError: ` only (the JVM flag `-XX:+HeapDumpOnOutOfMemoryError` matched the bare word).

| File | Tier | What |
|---|---|---|
| `SaiMemtableChargeTest.java` | unit (B2e) | the case file's test, verbatim (extracted from B2e). Copied to `test/unit/org/apache/cassandra/index/sai/memory/` of the fresh clone `~/cassandra-sai`. |
| `unit-run.sh` | unit | U1/U2 at 512MiB, U3 at 32MiB and 96MiB (all `unslabbed_heap_buffers`, amendment A-U1); writes `~/stage4-sai/unit.csv`, logs `~/stage4-logs/sai/unit/`; waits if 127.0.0.1:7012 is taken by another agent's unit JVM |
| `sai-profile.yaml`, `plain-profile.yaml` | cluster (B3c) | the case file's stress profile, and its plain twin (no `extra_definitions`, table `t_plain`) |
| `SaiPoll.java` | cluster (A-K3) | JMX sampler, 2 s, run with the JDK source launcher (`java SaiPoll.java <port> <table> <index or -> <ms> <stop file>`) |
| `cluster-run.sh` | cluster (B3e) | one run: `bash cluster-run.sh <R> <L MiB> <sai/plain>`. Node on 127.0.0.5, JMX 7205, data `~/stage4-sai/node`, logs `~/stage4-logs/sai/<R>` (shared-host deviations); yaml adds `segment_write_buffer_size: 16MiB` (A-K2); histograms every 30 s (A-K3) |
| `all-runs.sh` | cluster | R1..R6 (A-K1) in sequence |
| `analyze.py` | both | readings, sub-predictions and the decision tables A-U2 / A-K5: `python3 -I analyze.py unit <unit.csv>`; `python3 -I analyze.py cluster ~/stage4-logs/sai <unit.csv>` |

Instrument checks before run 1: the unit test compiles in the clone (`ant build-test`, BUILD SUCCESSFUL); `SaiPoll.java` compiles with `javac`;
the yaml edits were dry-run on a copy of `conf/cassandra.yaml` (14 changed lines, parsed by PyYAML: `sai_options.segment_write_buffer_size: 16MiB`,
seeds `127.0.0.5:7000`); `analyze.py unit` was run on a synthetic CSV and returned the row its numbers imply.
