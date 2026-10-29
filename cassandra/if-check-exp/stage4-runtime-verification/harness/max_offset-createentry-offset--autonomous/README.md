# Harness: max_offset-createentry-offset--autonomous

Written 2026-10-28 (stage 4, node pc29). Run copy `~/s4-b34/c` (`copy-source.sh` of `cassandra/cassandra-5.0.9`, `ant build-test`). Case file amendments U1-U4 (B2) and C1-C5 (B3).

Unit tier (B2): `MaxOffsetProbeTest.java` (package `org.apache.cassandra.index.sasi.disk`; compiled by `unit-run.sh` against the build into the log directory, not into the run copy) and `unit-run.sh`. One JVM, JUnitCore, JDK 11 module flags from `conf/jvm11-server.options`. It builds `DynamicTokenTreeBuilder` trees, writes them to a `DataOutputBuffer`, parses the entry types from the bytes, and prints `READ` lines and `EXPECTED ... PASS|FAIL` lines (the frozen B2f/U3 numbers next to the reading).
Cluster tier (B3): `lib.sh` (node helpers, identical in the three harness folders of this batch), `Jmx.java` (500 ms heap poll; copied from the `row_overhead_size` harness), `sasi.yaml` (cassandra-stress profile), `cluster-run.sh <arm> <rows> <index yes|no> <heap> <format big|bti> <commitlog MiB>` (one arm end to end), `chain.sh` (all arms in order), `analyze.py` (readings and `EXPECTED` lines), `selfcheck.py` (independent re-parse for results section 5).
Logs stay on the node: `pc29:~/stage4-logs/b34/maxoffset/run1/`.
Run the scripts from a local copy of this folder (`cp -r` to the node's disk), not from the NFS checkout: editing a script on NFS while it runs made bash fail with "Stale file handle" once (defect D3 in the results). `chain2.sh` of the run (s16 and the bti arm run again) is not kept; it called `cluster-run.sh` for those two arms.
