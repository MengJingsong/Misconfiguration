# Harness: tombstone-threshold-worthDroppingTombstones-droppableRatio--autonomous

Stage-4 harness for the case file's B2 (unit) and B3 (cluster) as amended 2026-10-26. Port slot 3 (127.0.3.1, JMX 7130; no Byteman).
Work dirs on the run node: trees `~/s4-b10-td-u` (`ant build-test`) and `~/s4-b10-td-n` (`ant jar`) from `copy-source.sh`; node conf
`~/s4-b10-td-node`; data on tmpfs `/dev/shm/s4-b10-td`; logs `~/s4-b10-td-logs/<run>/{unit,cluster}/`; the bundled Python driver is
unzipped to `~/s4-b10-td-drv`.

| File | Purpose |
|---|---|
| `TombstoneThresholdProbeTest.java` | unit tier; a `CQLTester` in package `org.apache.cassandra.db.compaction`; writes `STAGE4` lines to `-Dstage4.out` |
| `unit-run.sh` | copies the test into the tree, `ant testsome`, then `analyze-unit.py` |
| `analyze-unit.py` | EXPECTED lines for the instrument checks I1-I3 and the predictions P1-P4 |
| `make-node-yaml.sh` | rebuilds the node's conf for slot 3 (tmpfs directories, JMX port 7130) |
| `load.py` | Python-driver loader: `UPDATE ... USING TTL` for a percentage of keys, plain `UPDATE` for the rest; `extra` mode writes the overlap sstable of `go` |
| `cluster-run.py` | cluster tier: node start, 14 tables, load, flush, wait, ratios, one `enableautocompaction`, 300 s of `du`, `nodetool compact ks pc`, node stop |
| `analyze-cluster.py` | EXPECTED lines for R1-R2, C1-C2, H1-H3, K1, S1 (the B3f predictions) from a run directory |

Instrument checks (before any reading): the strategy's `tombstoneThreshold` is read after every ALTER (unit); ratio r within f +/- 0.1 and the X=0.0 known answer
(unit); schema options read back from `system_schema.tables`, one sstable per table (two for `go`), peak `du` 30-90 MB, no compaction before the enable (cluster).
Shakedown runs (run name `shake`, `TD_ROWS`/`TD_TTL`/`TD_WAIT`/`TD_OBS` overrides) test plumbing only and are not readings.
