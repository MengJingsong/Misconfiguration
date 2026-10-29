# Harness: overflow_trailer_capacity-createoverflowentry-overflowcollisions--autonomous

Written 2026-10-28 (stage 4, node pc29). Run copy `~/s4-b34/c`. Case file amendments U1-U4 (B2) and C1-C4 (B3).

Unit tier (B2): `OverflowCapacityProbeTest.java` (cases C1-C8, plus a 600-token control and a full-leaf extra; per-leaf slot counts parsed from the written bytes) and `unit-run.sh` (same launcher as the max_offset harness).
Cluster tier (B3): `lib.sh`, `Jmx.java`, `CollKeys.java` (collision keys by `MurmurHash.inv_hash3_x64_128`, each checked with `Murmur3Partitioner.getToken`), `overflow.btm` (Byteman trace on `createOverflowEntry`: entry and throw), `sasi.yaml` (stress profile for the clean-row arms), `cluster-run.sh <arm> collide <t> <g> | rows <n> | mem <MiB>`, `chain.sh`, `analyze.py`, `selfcheck.py`.
Logs stay on the node: `pc29:~/stage4-logs/b34/overflow/run1/`.
