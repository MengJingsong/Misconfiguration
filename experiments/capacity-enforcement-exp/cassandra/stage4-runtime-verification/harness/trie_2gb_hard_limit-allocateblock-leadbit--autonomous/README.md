# Harness: trie_2gb_hard_limit-allocateblock-leadbit--autonomous

Unit tier (B2): `Trie2GbLimitProbeTest.java` (package `org.apache.cassandra.db.tries`, copied to the run copy's `test/unit/.../tries/`,
compiled by `ant build-test`/`javac`), `unit-run.sh` (one JVM per run), `RunOne.java` + `unit-control.sh` (positive control
`testOver1GSize` with `@Ignore` removed in the run copy only).
Cluster tier (B3): `make-node.sh` (single-node conf), `trie.yaml` (cassandra-stress profile), `Jmx.java` (1 Hz JMX poll),
`cluster-run.sh` (one arm end to end), `analyze.py` (readings from an arm's folder).
Written 2026-10-27. Checks before run 1: see results file section 1.
