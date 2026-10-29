# Harness - filename_length-validatesnapshotname-snapshotname--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 `752b8b60...`, see the results file). Written 2026-10-28 on `pc41`; copy `~/s4-b2/base` made by `copy-source.sh` (`ant build-test`); logs in `~/s4-b2/logs/<stem>/<run>/` on the node.

| File | Tier | What it does |
|---|---|---|
| `SnapshotNameLengthTest.java` | unit (B2) | CQLTester in `org.apache.cassandra.db`; N rows (1k, 100k), flush, then `snapshotWithoutMemtable("a"*L)` for L in 1/100/255/256/300 x validation false/true x 3 reps; records outcome, snapshot bytes, manifest/schema sizes, physical (inode-deduped) growth of the table dir, heap delta; 90 `STAGE4 check` lines. |
| `unit-run.sh [run]` | unit | copies the test into the copy, `ant testsome`, writes `summary.txt`. `--remove` deletes it. |
| `cluster-run.py [run]` | cluster (B3) | one node (127.0.0.1) with `-Dcassandra.snapshot.validation`, 2G heap, stress 200k then 2M rows, `nodetool snapshot` for the L list, 30 s settle, heap (`GC.run`+`GC.heap_info`), RSS, physical growth, `listsnapshots`; restart with validation false for L=256/255. `EXPECTED` lines. |
| `noise-probe.py [run]` | cluster | supplementary: six alternating L=100/255 snapshots on the run-1 data to characterise heap-delta noise (added after one heap tolerance missed). |
| `selfcheck.py <run1 dir>` | both | independent re-parse of the raw files. |
