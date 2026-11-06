# Harness — yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous

Stage-4 instruments for the case file
[`../../../../stage3-ai-deep-read/yang/cases/yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous.md`](../../../../stage3-ai-deep-read/yang/cases/yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous.md)
(sections B2, B3; amendments A1–A9 in its section D). Results:
[`../../results/yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous.md`](../../results/yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous.md).
Written 2026-11-06, after the audit's freeze, before run 1.

| File | What it is |
|---|---|
| `TestIfCheckAutoQueueGuaranteeVsUsage.java` | The B2e test (package `...scheduler.capacity`), as filed, plus the print lines of A2 and the AM launch of A9 (heartbeat until u3's attempt is ALLOCATED). Prints `IFCHK` lines: `create` (operand `avail`, leaf abs cap, `active`, activated sum, effective max), `amAlloc`, `usage` every 10 heartbeats, `end`. |
| `unit-run.sh <run-dir> [--compile-only]` | Copies the test into `<run-dir>/src` (made by `../../copy-source.sh`), runs it three times in the ResourceManager module with JDK 8 against the node's `~/.m2`, prints the frozen `EXPECTED:` lines, extracts `IFCHK` lines per repeat. Stops when the first trigger (`IFCHK U1 create u1`) is missing, a test fails (surefire count; the build ignores failures and returns 0), or there are not four `end` lines. `--compile-only` is the instrument check. |
| `cluster-run.py <run-dir>` | B3 on one node (run with `python3 -I`): prechecks (no Hadoop daemon, ports free), copies the built distribution and adds the YARN module jars (A4), writes the configuration, checks the RSS sampler on a standalone `hog.py` (known answer ~600 MiB), starts HDFS, runs C1–C4 (RM restarted per run, NM once), samples REST + `ps` every 2 s for 120 s, kills the apps and checks no hog is left. Any failed step or 180 s timeout stops the run; the first-trigger check is `root.parent.u1` appearing. On any exit (including signals) it kills apps and clients, stops all four daemons, kills anything left whose command line names the run directory, and logs `jps` and the daemon `ps` check. |
| `selfcheck.py <run-dir>` | Results §5: re-parses the raw files (surefire output and reports, `run-C*.tsv`, REST snapshots, the RM log's policy DEBUG lines inside each 120 s window, the NodeManager log, client logs) independently of the run scripts and prints PASS/FAIL against the frozen B2f/B3f values. Run with `python3 -I`. |
| `hog.py` | The B3c container payload (600 MiB touched, then sleep). `hog.sh` is generated in the run directory with the path written out. |

Outputs (full logs stay on `/mydata`): `<run-dir>/logs/unit/rep{1,2,3}/`, `<run-dir>/logs/cluster/{cluster-run.log,run-C*.tsv,summary.txt,client-*.log,scheduler-*.json,apps-*.json}`,
daemon logs in `<run-dir>/logs/`. Run 1 used `/mydata/yang-s4/<stem>-run1`.
