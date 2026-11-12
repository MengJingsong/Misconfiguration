# Harness — commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-usedbuffers--autonomous

Stage-4 harness for the autonomous case file (`SimpleCachedBufferPool.atLimit()` via `AbstractCommitLogSegmentManager.atSegmentBufferLimit()`); written 2026-11-11 for node `apt138` (tag o45).
Frozen versions and the audit are in the results file (`../../results/commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-usedbuffers--autonomous.md`, section 1).
On the node: build tree `/mydata/jingsong-cass-s4/o45/src` (`copy-source.sh` copy, `ant build-test`), node tree `/mydata/jingsong-cass-s4/o45/node` (copy of the built tree, `JMX_PORT=7499`, `conf/cassandra.yaml.orig`), harness copy `/mydata/jingsong-cass-s4/o45/harness`, outputs `/mydata/jingsong-cass-s4/o45/run1/`.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `SimpleCachedBufferPoolCapTest.java` | unit (B2c Test 1) | pool alone, N ∈ {1, 2, 3, 6, 12}, 1 MiB off-heap buffers; prints `POOL` lines (atLimit, `toString`, direct delta) | it is its own known-answer check (direct delta = k MiB) |
| `gen_test2.py` | unit (B2c Test 2, B2h) | applies the case file's sed loop to `CommitLogSegmentBackpressureTest` (N = 2, 3, 6) and adds the `CAP` print points of amendment M2; builds the control class `CommitLogBufferCapCtlTest` (no compression → mmap) | generated sources inspected; first version leaked `\"` into Java (fixed before the run) |
| `unit-run.sh [run]` | unit | copies/generates the classes, `ant testsome` per class with BMUnit agent port 9391, collects `TEST-*.log`/XML, removes the sources, checks no test JVM is left, runs `unit-analyze.py` | run log `run1/unit-summary.txt`. Its "CAP/POOL lines: 0" counts are a cosmetic bug (anchored grep; the lines carry a log prefix); the analyzer finds them anywhere in the line |
| `unit-analyze.py <dir>` | unit | B2f as `EXPECTED` lines, B2g row per amendment M7 | known-answer run on synthetic lines (row 1 for exact values, row 2 when one `active` is N+1) |
| `cluster-setup.sh` | cluster | copies the built tree to the node tree, moves JMX to 7499, compiles `O45Jmx` | log `logs/cluster-setup.log` on the node |
| `patch_yaml.py` | cluster | writes `cassandra.yaml` per configuration (N3, N6, N12 Zstd-19; C1 LZ4 N=12; C2 no compression N=3; N1), removing each overridden key from the original first; seed port 7300 | yaml diffed by hand; the first version wrote `parameters` as a map (runbook defect D1, found by the shakedown) |
| `O45Jmx.java` | cluster (B3d, M6) | JMX poller, 1 s: direct MemoryUsed/Count, mapped MemoryUsed, `WaitingOnSegmentAllocation` and `WaitingOnCommit` Count, BufferPool Size (networking, chunk-cache), heap used | shakedown: all columns readable, no `-1` |
| `cluster-run.sh <run> <cfg>` | cluster (B3e) | start node (4G heap, 4G MaxDirect via env), poller, `ctx.csv` (RSS, RssAnon, commit-log files and MiB every 10 s), 30 s idle, `jstack` every 10 s, stress (`DUR` override for the shakedown only), 30 s post, drain and stop on any exit | shakedown `DUR=20s` N3 (`/mydata/jingsong-cass-s4/o45/shakedown/`): node up, stress 0 errors, drain, no daemon left |
| `cluster-analyze.py <run-dir>` | cluster | B3f as `EXPECTED` lines, B3g row per amendment M8 | run on the shakedown (N3 only): blocked state detected in a jstack dump |
| `selfcheck.py <run-dir>` | both | re-parses the raw files with its own code | — |
