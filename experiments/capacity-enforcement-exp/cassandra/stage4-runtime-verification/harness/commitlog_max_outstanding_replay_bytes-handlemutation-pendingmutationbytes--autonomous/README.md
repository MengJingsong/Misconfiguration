# Harness — commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous

Stage-4 harness for the autonomous case file (`CommitLogReplayer.java:75`, check at `:525-530`), case tag `o32`; written 2026-11-11
for node `apt138` (shared; ports 7300/7301/7499/9342). Frozen versions, audit and amendments M1-M6: results file
(`../../results/commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous.md`, sections 1 and 3).
Working trees (made by `copy-source.sh` on the coordinating machine, rsynced to the node): `/mydata/jingsong-cass-s4/o32/src`
(`ant build-test`; unit tier) and `/mydata/jingsong-cass-s4/o32/node-tree` (`ant jar`; cluster tier). The harness is synced to
`/mydata/jingsong-cass-s4/o32/harness/` and run from there.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `OutstandingReplayBytesProbeTest.java` | unit (B2) | Copied into `test/unit/org/apache/cassandra/db/commitlog/`. Per limit L (env `O32_LIMITS`, default 1 MiB, 4 MiB, 16 MiB, 1 GiB): `resetUnsafe(true)`, truncate, 1000 durable writes of a 60000-char value (M6), set `MAX_OUTSTANDING_REPLAY_BYTES` and a probe `MutationInitiator`, `resetUnsafe(false)` (replay). The probe reads `pendingMutationBytes` by reflection at each call (= the operand after line 517), keeps its maximum, the maximum of not-finished probe tasks, `s`, and `calls` (ReplayProbe) / `callsOther` (M4); a single-thread executor sleeps 5 ms per task. Prints `O32 LIMIT=...` lines. | Shakedown 1 (L = 1 byte) found defect D1: `applyUnsafe()` skips the commit log (`calls=0`). Shakedown 2 (L = 1 byte, after the fix): `peakPending = s = 60050`, `maxQueued = 1`, `calls = 1000` — the known answer for L = 1 (`run1/unit-shakedown-o32.txt`). |
| `unit-run.sh <tree> <out> [shakedown]` | unit | copies the probe, `ant testsome`, extracts `O32` lines to `unit-o32.txt` | shakedowns |
| `unit-analyze.py <unit-o32.txt>` | unit | B2f checks as `EXPECTED:` lines, a strict automatic B2g match (thresholds in the results file, section 4) | run on the shakedown line |
| `mkconf.py <tree> <nodedir> load\|replay [bytes count]` | cluster | writes the B3a yaml block (M1-M3), `JMX_PORT=7499`, and the two `-D` lines in `conf/jvm-server.options` for replay | printed config in each `session.txt` |
| `sampler.py <pid> <system.log> <out.jsonl>` | cluster | every 2 s until `Log replay complete`: `jcmd GC.class_histogram` (Mutation, PartitionUpdate, Total) and `jcmd GC.heap_info` used (M5) | instrument check on the idle load node (`run1/cluster-load-session.txt`: ok=true, Mutation 0) |
| `cluster-run.sh load` / `cluster-run.sh replay <label> <bytes> <count>` | cluster | B3e.1 (start, stress 24000 x 64 KiB, SSTable count 0, 15 s, `kill -9` of the recorded PID, pristine copy) / B3e.3-4 (restore, configure, start, sampler, stop by recorded PID) | load phase itself (`run1/cluster-load-session.txt`) |
| `replay-all.sh` | cluster | the five replay runs in order: 16 MiB, 64 MiB, 256 MiB, 4 GiB (count 10^8), count-cap control (4 GiB, count 16) | — |
| `cluster-analyze.py <cluster dir>` | cluster | B3f checks as `EXPECTED:` lines, strict automatic B3g match | — |
| `selfcheck.py <run1 dir> <cluster dir>` | both | re-derives the cited numbers from the raw files with its own parsing | — |
