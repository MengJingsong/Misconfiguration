# Harness: min-threshold-getEstimatedCompactionsByTasks-bucketSize--autonomous

Stage-4 harness for the case file's B2 (unit) and B3 (cluster) as amended 2026-10-27. Port slot 1 (127.0.1.1, JMX 7110; no Byteman).
Work dirs on pc07: trees `~/s4-b11-m71-u` (`ant build-test`) and `~/s4-b11-m71-n` (`ant jar`) from `copy-source.sh`; node conf
`~/s4-b11-m71-node`; data on tmpfs `/dev/shm/s4-b11-m71`; logs `~/s4-b11-m71-logs/<run>/{unit,cluster}/`.

| File | Purpose |
|---|---|
| `MinThresholdProbeTest.java` | unit tier; a `CQLTester` in package `org.apache.cassandra.db.compaction`; writes `STAGE4` lines to `-Dstage4.out`; warm-up table, forward and reverse sweeps, two positive controls |
| `unit-run.sh` | copies the test into the tree, `ant testsome`, then `analyze-unit.py` |
| `analyze-unit.py` | EXPECTED lines for the instrument checks I1-I3, predictions P1-P4, controls C1-C2 |
| `make-node-yaml.sh` | rebuilds the node's conf for slot 1 (tmpfs directories, JMX port 7110) |
| `cluster-run.py` | cluster tier: node start, 9 estimate arms (min 2/4/16 x 3) and 2 control arms; ingest by `cassandra-stress`, baseline sample, `enableautocompaction`, polling, node stop |
| `analyze-cluster.py` | EXPECTED lines for P1-P3, C1-C3 from `summary.txt` and the per-arm series |
| `selfcheck.py` | re-parses the raw logs (test.out, series CSVs, system.log copies) independently of the analyzers |

Instrument checks (before any reading): one bucket of all SSTables, the min>max setter rejection, estimate flips with min (unit); ten SSTables
of equal size, thresholds read back, no compaction before the enable, estimate gauge readable through `nodetool sjk mx`, the `Compacted (id) N sstables`
log line parsed (cluster). Shakedown runs (`shake`, `shake2`) test plumbing only and are not readings; the first showed +2 MiB heap in the
first unit cell, so a warm-up table was added before the recorded sweeps.
