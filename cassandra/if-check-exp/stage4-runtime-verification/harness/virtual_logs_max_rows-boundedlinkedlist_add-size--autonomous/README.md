# Harness: virtual_logs_max_rows-boundedlinkedlist_add-size--autonomous

Written 2026-10-27 (stage 4, node pc41). Run copy: `~/c4-vlr` (`copy-source.sh` of `cassandra/cassandra-5.0.9`, `ant build-test`).

Unit tier (B2): `VirtualLogsMaxRowsProbeTest.java` (package `org.apache.cassandra.db.virtual`; copy to the run copy's
`test/unit/org/apache/cassandra/db/virtual/` and `javac` against `build/`), `unit-run.sh` (one JVM: `java @jvm11 module flags -Xmx1g`
+ JUnitCore; modes `cap`, `mt`, `resolve`), `unit-all.sh` (the whole unit tier, one JVM per line).
Cluster tier (B3): `make-node.sh` (single-node conf with the CQLLOG appender enabled at a given threshold, or left commented out as
shipped), `cluster-run.sh` (one arm end to end: node with `-Dcassandra.virtual.logs.max.rows`, TRACE workload in cumulative stress
steps, a snapshot after each step), `analyze.py` (readings of an arm; with an OFF arm, the ON-minus-OFF byte totals).
Instrument checks before run 1: see the results file, section 1.
