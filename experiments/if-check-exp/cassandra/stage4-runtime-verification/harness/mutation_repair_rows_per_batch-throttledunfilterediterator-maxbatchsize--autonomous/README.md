# Harness: mutation_repair_rows_per_batch-throttledunfilterediterator-maxbatchsize--autonomous

Written 2026-10-27 (stage 4, node pc41). Run copy: `~/c4-mrb` (`copy-source.sh` of `cassandra/cassandra-5.0.9`, `ant build-test`).

Unit tier (B2): `MutationRepairBatchProbeTest.java` (a `CQLTester` in package `org.apache.cassandra.db.rows`; copy to the run copy's
`test/unit/org/apache/cassandra/db/rows/`), run by `unit-run.sh` (`ant testsome`, environment `PROBE_VAR`/`PROBE_OUT`).
Cluster tier (B3): `make-node.sh <A|B>` (loopback node conf: cdc_enabled, off-heap buffers, JMX port), `node.sh` (start/stop/status),
`prep-data.sh <rows> <valueBytes>` (node A alone, `LoadWide.java` loads two wide-partition tables, flush, compact, backup of A's data),
`cluster-run.sh <label> <N|unset> <wide_cdc|wide_plain>` (one arm: A restored, B new with the property, Byteman `bm.btm`, GC log, class-histogram
sampler, `nodetool repair -full` on B), `chain.sh` (all arms), `analyze.py` (readings of an arm).
