# Harness: compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous

Stage-4 instruments (not upstream). Amendments A1, U1-U3, C1-C5 of the case file govern.

- `StcsMinThresholdProbeTest.java`: unit tier. Copied into `test/unit/org/apache/cassandra/db/compaction/` of a `copy-source.sh` tree by `unit-run.sh <tree> <outdir>`; writes `R <section> <key> <value>` readings; asserts nothing. `unit-analyze.py <readings.txt>` prints PASS/FAIL per check against B2f/B2g/U2/U3.
- `cluster-run.py <arm>` (env `SM_TREE`, `SM_OUT`): one arm per node start on 127.0.7.1 (JMX 7170), data on `/dev/shm/s4b10sm`. Arms m2 m4 m16 m32 (m32 ends with the runtime flip) and mm4. `EXPECTED:` lines are instrument checks that stop the arm; the node is stopped on any exit.
- `cluster-chain.sh <tree> <outdir>`: the five arms in order, then `cluster-analyze.py` (B3f/B3g/C4/C5).
- `selfcheck.py <unit-outdir> <cluster-outdir>`: re-parses the raw logs (not the JSON the runner wrote) for stage 4's self-check.

Use separate trees for the unit tier (`ant testsome`) and the node.
