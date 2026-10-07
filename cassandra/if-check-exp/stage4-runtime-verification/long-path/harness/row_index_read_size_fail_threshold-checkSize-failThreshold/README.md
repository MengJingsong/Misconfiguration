# Harness — row_index_read_size_fail_threshold-checkSize-failThreshold

Instruments for the case's section 9 (stage 4). Written 2026-10-07 from the case's 9c table. The results are in
[`../../results/row_index_read_size_fail_threshold-checkSize-failThreshold.md`](../../results/row_index_read_size_fail_threshold-checkSize-failThreshold.md).

| File | What it is | Checked how |
|---|---|---|
| `RowIndexSizeGuardTest.java` | Unit tier. Package `org.apache.cassandra.db`; copy it into `test/unit/org/apache/cassandra/db/` of a clone at `cassandra-5.0.9`. Prints `STAGE4 check ...` and `STAGE4 info` lines (stdout and `-Dstage4.out`). | its own known-answer checks (the formula reproduces the message's estimate, exactly) |
| `unit-run.sh` | Runs the test on the measured node: `~/stage4-logs/rirs/unit/{run.out,ant.log}`. | — |
| `make-node-yaml.sh <label> <bytes\|none> [stock-cache]` | Rebuilds `conf/cassandra.yaml` from the tag plus the arm's lines. | the yaml tail is echoed into the log |
| `checksize.btm` | Byteman observation rules: one `checksize` line per call of `RowIndexEntry.Serializer.checkSize(int, int)`, **before** the check's gate, with `command=null` or `<keyspace.table>`. The rule fires for system-table deserializations too, so the run script filters on `ks1`. | Byteman `TestScript`: two rules, no errors |
| `Jmx.java` | A small JMX client (`get` several attributes in one JVM start, `set` one attribute); used instead of `nodetool sjk mx`, which is slow per call and has no checked setter. | `set` of the attribute to its own value succeeds at the instrument step |
| `send-read.py` | Cluster-tier client on the bundled driver, **protocol 5**. Modes `probe`, `load-ladder`, `load-rows`, `read`. | `probe` prints the protocol in use |
| `cluster-run.py <label>` | One run script (labels `16m`, `16k`, `64k`, `256k`, `s64k`, `s16m`, `none`): instrument checks, the ladder, and on the `64k` start the arms C1, C2 and C3; logs every command; writes `summary.txt` and `readings.csv`. **Python instead of the `cluster-run.sh` of the case's 9c table.** | the instrument checks run first and stop the run on failure |

Copy the folder to the node (`~/stage4-harness-run/rirs`) before a run. The node's clone is `~/cassandra-run1` at commit `b5f2a54210`.
