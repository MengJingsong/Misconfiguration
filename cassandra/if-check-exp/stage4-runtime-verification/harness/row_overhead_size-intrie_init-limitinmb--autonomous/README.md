# Harness: row_overhead_size-intrie_init-limitinmb--autonomous

Written 2026-10-27 (stage 4, node pc41). Run copy: `~/c4-ros` (`copy-source.sh` of `cassandra/cassandra-5.0.9`, `ant build-test`).
Adapted from `../trie_2gb_hard_limit-allocateblock-leadbit--autonomous/` (the `make-node.sh`, `trie.yaml` and `Jmx.java` there; the node script
and analysis are re-written for this case's observables); nothing from that case's conclusions is used.

Unit tier (B2): `RowOverheadThresholdProbeTest.java` (package `org.apache.cassandra.db.tries`; copied to the run copy's `test/unit/.../tries/`),
`unit-run.sh` (one JVM per value through the java launcher), `unit-all.sh` (the whole tier).
Cluster tier (B3): `make-node.sh` (single-node conf, allocation type parameter), `trie.yaml` (cassandra-stress profile), `Jmx.java` (100 ms JMX poll),
`cluster-run.sh` (one arm end to end), `chain.sh` (all arms), `analyze.py` (readings of an arm from `system.log` and `samples.csv`).
