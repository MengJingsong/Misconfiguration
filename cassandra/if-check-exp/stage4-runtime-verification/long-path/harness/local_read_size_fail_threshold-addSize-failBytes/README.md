# Harness — local_read_size_fail_threshold-addSize-failBytes

Instruments for the case's section 9 (stage 4). Written 2026-10-07 from the case's 9c table. The results are in
[`../../results/local_read_size_fail_threshold-addSize-failBytes.md`](../../results/local_read_size_fail_threshold-addSize-failBytes.md).

| File | What it is | Checked how |
|---|---|---|
| `LocalReadSizeGuardTest.java` | Unit tier. Package `org.apache.cassandra.db`; copy it into `test/unit/org/apache/cassandra/db/` of a clone at `cassandra-5.0.9`. Prints `STAGE4 check <name> <expected> <actual> ok\|MISMATCH` and `STAGE4 info` lines (to stdout and to the file named by `-Dstage4.out`). | its own known-answer checks (the mirror of the check's counter equals the check's warn parameter, exactly) |
| `unit-run.sh` | Runs the test on the measured node: `~/stage4-logs/lrs/unit/{run.out,ant.log}`. | — |
| `make-node-yaml.sh <label> <bytes\|none>` | Rebuilds `conf/cassandra.yaml` from the tag plus the arm's lines. | the yaml tail is echoed into the log |
| `Alloc.java`, `read-alloc.btm` | Byteman observation rules: one `read-alloc` line per local read command on `ks1` (bytes the thread allocated). **The helper `stage4.Alloc` is compiled into a jar on the boot class path** (`-Xbootclasspath/a:`), because the node runs from `build/apache-cassandra-*.jar`, not `build/classes/main`. | Byteman `TestScript`: three rules, no errors; a read writes one line, a `system.local` read none |
| `send-read.py` | Cluster-tier client on the bundled driver, **protocol 5**. Modes `probe`, `load`, `read`. | `probe` prints the protocol in use |
| `jmx.sh` | `nodetool sjk mx -mg` for one attribute. | the meter is read before every run |
| `cluster-run.py <label>` | One run script (labels `16m`, `256k`, `1m`, `4m`, `none`): instrument checks, calibration, scenarios A, B, C; logs every command; writes `summary.txt` (the `EXPECTED:` lines) and `readings.csv`. **Python instead of the `cluster-run.sh` of the case's 9c table**, to parse and compute in one place; the steps are the case's 9e. | the instrument checks run first and stop the run on failure |

Copy the folder to the node (`~/stage4-harness-run/lrs`) before a run. The node's clone is `~/cassandra-run1` at commit `b5f2a54210`.
