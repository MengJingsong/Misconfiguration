# Harness: partition-key-max-size-descend-data-length--autonomous

Stage-4 instruments for the case file's B2 (unit) and B3 (cluster) tiers, with the B2i / B3i amendments of 2026-10-25.

| File | Role |
|---|---|
| `PkStackTest.java` | unit tier; package `org.apache.cassandra.db.tries` (reads package-private `ApplyState.data`); modes `lengths`, `bulk`, `depth` |
| `unit-run.sh` | compiles it outside the tree and runs the JVMs (separate JVM for `-Dcassandra.memtable.row_overhead_size=1`) |
| `analyze_unit.py` | compares the TSVs with the frozen B2f / B2i predictions, writes `summary.txt` |
| `cluster-run.py` | one node start per invocation: private conf and data dirs, one-node ring on 127.0.31.1 (7131 / 9131 / JMX 7331), arms or the positive control |
| `analyze_cluster.py` | compares `arms.csv` (h64, h256) and `poscontrol.csv` with B3f / B3i.3-5 |
| `selfcheck.py` | independent re-parse of the raw node logs and histograms (not the CSVs) |

Usage on the node (tree built with `ant build-test`, no `ant` while a node runs):

    bash unit-run.sh ~/s4-pk/src ~/s4-pk/unit-run1 && python3 -I analyze_unit.py ~/s4-pk/unit-run1
    python3 -I cluster-run.py --src ~/s4-pk/src --out ~/s4-pk/cluster-run1/h64 --label h64 --heap-space 64 --mode arms
    python3 -I cluster-run.py --src ~/s4-pk/src --out ~/s4-pk/cluster-run1/h256 --label h256 --heap-space 256 --mode arms
    python3 -I cluster-run.py --src ~/s4-pk/src --out ~/s4-pk/cluster-run1/pc --label pc --heap-space 16 --mode poscontrol
    python3 -I analyze_cluster.py ~/s4-pk/cluster-run1
