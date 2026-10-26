# Harness: sasi-compaction-flush-memory-ensurecapacity-tmp--autonomous

Stage-4 instruments (not upstream code). Frozen with the case file at the sha256 values in `results/<stem>.md` section 1.

| File | Tier | What it does |
|---|---|---|
| `SasiSuffixMemoryTest.java` | unit | JUnit class copied into `test/unit/org/apache/cassandra/index/sasi/disk/`. Cell `p1`: `LongTimSort` on n x shape. Cell `p2:<mode>:<M>:<L>[:<reps>]`: fills an `OnDiskIndexBuilder` to the estimate crossing, then `finish()` with a full-GC class-histogram sampler (every ~2 s) and the thread-allocation counter. |
| `lts.btm` | both | Byteman rules: `LongTimSort.sort` entry/exit (`a.length`), every write of `tmp` (constructor and `ensureCapacity`). Trace file from `-Dstage4.trace`. |
| `unit-run.sh` | unit | `check` (ant testsome + agent known answers) or `run [parallel]` (one JUnitCore JVM per cell, cells listed in the script). |
| `unit-analyze.py` | unit | Tables from the raw CSV and trace files. |
| `cluster-run.py`, `loader.py`, `cql.py`, `PoolSampler.java` | cluster | One node on 127.0.2.1; per arm: keyspace, index (before load), 200,000 rows in 25,000-row chunks with flush, baseline histogram, `nodetool compact` with a histogram sampler (1 s) and the SASI pool sampler (250 ms); keyspace dropped. |
| `cluster-analyze.py` | cluster | Per-arm table from `summary.json`, `histo-<arm>.jsonl`, `pool.csv`, `lts-trace.txt`. |
| `selfcheck.py` | both | Independent re-parse of the raw files; PASS/FAIL per statement. |

Run (on the run node, tree built with `ant build-test`):
`bash unit-run.sh ~/s4-b7-st <out> check`, then `bash unit-run.sh ~/s4-b7-st <out> run 3`;
`python3 cluster-run.py <out> 8g c2:CONTAINS:2:200,c8:CONTAINS:8:200,c32:CONTAINS:32:200,p8:PREFIX:8:200,p32:PREFIX:32:200,c8s:CONTAINS:8:50,none:NONE:def:200,cdef:CONTAINS:def:200 200000 main`;
the OOM probe is `python3 cluster-run.py <out> 512m c32:CONTAINS:32:200 200000 oom`.
