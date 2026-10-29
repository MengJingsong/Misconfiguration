# Harness: super_block_size-flushsuperblock-datablockscnt--autonomous

Written 2026-10-28 (stage 4, node pc29). Run copy `~/s4-b34/c`. Case file amendments U1-U4 (B2) and C1-C3 (B3).

Unit tier (B2): `make-overlays.sh` (compiles `OnDiskIndexBuilder` and `OnDiskIndex` with `SUPER_BLOCK_SIZE` 16 / 64 / 256, plain `ovN` and print-patched `ovNp`, into `~/s4-b34/ov`), `SuperBlockProbeTest.java` (builds an SASI `OnDiskIndexBuilder` over N Int32 terms, finishes it, parses the file tail independently for the number of super blocks and data blocks, md5 of the file), `unit-run.sh` (one JVM per index), `unit-all.sh` (the whole tier), `analyze-unit.py` (table and `EXPECTED` lines for B2f/U3).
Cluster tier (B3): `lib.sh`, `Jmx.java`, `sasi.yaml`, `cluster-run.sh <arm> <option MiB> <constant> <SPARSE|PREFIX>` (overlay classes for 16 and 256 are copied into the node's conf directory), `chain.sh`, `analyze.py`, `selfcheck.py`.
Logs stay on the node: `pc29:~/stage4-logs/b34/superblock/run1/`.
