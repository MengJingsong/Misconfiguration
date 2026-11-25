# Harness — commitlog_max_outstanding_replay_count-handlemutation-futures_size--autonomous (order o100)

Stage-4 harness, written 2026-11-25 for node `pc82` (x86_64), run data under `/mydata/jingsong-cass-s4/o100/` (synced there
as `harness/` and run from there). To become `cassandra/stage4-runtime-verification/harness/<stem>/` when the coordinator files it.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `case-as-filed.md` | — | the case file as filed (sha256 `81f0d466…62c6`, equal to `_INDEX.md` §4) | `sha256sum` |
| `freeze.sha256`, `freeze-pred.txt` | — | sha256 of the amended file at the freeze, and of B2f-B2h + B3f-B3h + the audit amendments | — |
| `ReplayOutstandingCountTest.java` | unit (B2) | the case's B2e.1 class verbatim except S4-A2 (`println(String.format(...))`) | known-answer run C = 2, N = 2000: `peak_queue=3`, `handled=2000` (`run1/unit/shakedown/`) |
| `unit-run.sh`, `unit-all.sh` | unit | copy the class, `ant testsome -Dtest.jvm.args=...` per configuration, extract the `RESULT` line from the XML / test log; `unit-all.sh` = shakedown, then 3 x C ∈ {16, 256, 4096}, then the two controls | shakedown |
| `mkconf.py` | cluster | B3a yaml (directories, 127.0.0.1, `concurrent_writes: 4`, periodic 1000 ms, `memtable_heap_space: 2048MiB`) | printed block in `run1/cluster/load/session.txt` |
| `slow-replay.btm` | cluster | B3c Byteman rule: park 1 ms at entry of `CommitLogReplayer$MutationInitiator$1.runMayThrow` | its effect: MutationStage Active 4 / Pending C − 3 in every Byteman sample; replay 86 s vs 2 s without it |
| `sampler.py` | cluster | every 5 s from the first `Replaying` line to `Log replay complete`: `jmap -histo:live` (task, `Mutation`, `PartitionUpdate`, `Total`), `jcmd GC.heap_info` used, `nodetool tpstats` MutationStage | first replay's samples (`run1/cluster/C1024-r1/samples-raw.txt`) |
| `cluster-run.sh`, `cluster-all.sh` | cluster | B3e.1 load (stress 1 + flush + 300000, `kill -9` by recorded PID, `snap.tar`) and B3e.2 `run()` per label; `cluster-all.sh` = load + the six runs twice | load session |
| `analyze.py` | both | B2f/B3f checks with the S4-A3/S4-A4 thresholds, from the raw files | output `run1/analysis.txt` |
| `md5.txt` | — | md5 of the harness files | — |
