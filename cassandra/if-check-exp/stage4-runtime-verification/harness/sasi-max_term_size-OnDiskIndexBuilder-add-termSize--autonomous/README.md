# Harness: sasi-max_term_size-OnDiskIndexBuilder-add-termSize--autonomous

Written 2026-10-25 after the audit and freeze (hashes in the results file, section 1). Not upstream code.

| File | Role |
|---|---|
| `MaxTermSizeProbeTest.java` | unit tier (B2, as amended B5): one JUnit test; part 1 calls `OnDiskIndexBuilder.add` N=100,000 times for term sizes 1/512/1023/1024/1025/4096 (PREFIX) and `finish`; part 2 drives `PerSSTableIndexWriter.Index.add` (COMPACTION source) at caps 1/4/16 MB with the same 229,197 adds, and at 1023/1024 bytes through the writer's own filter; writes `unit-results.csv` and `unit-estimates.csv` |
| `unit-run.sh` | copies the test into a `copy-source.sh` tree and runs `ant testsome`; optional N argument is for the instrument check only |
| `analyze_unit.py` | PASS/FAIL per frozen unit prediction (EXPECTED/GOT lines) |
| `HeapSampler.java` | samples JVM heap used over JMX every 500 ms |
| `loader.py` | creates `ks.t` + SASI index (PREFIX, optional `max_compaction_flush_memory_in_mb`) and loads rows of one value size over protocol 4 |
| `cluster-run.py` | one cluster label: one node on 127.0.26.1 (JMX 7326, native 9348, storage 7026) from `~/s4-od`, heap 2 GiB, data under `~/s4-od-data/<label>`; load, `nodetool flush`, `nodetool compact`, log counts and index/data file sizes per phase, class histograms; stops the node on any exit |
| `cluster-all.sh` | the six labels (v1000, v1023, v1024, v2000, c1, c64) in series |
| `analyze_cluster.py` | PASS/FAIL per frozen cluster prediction |
| `selfcheck.py` | independent re-parse of the raw files |

Instrument checks (not readings): unit test at N=2000 twice (the writer-cap arms were changed from "10 x C each" to one common 229,197-add workload after the first), and one cluster shakedown (3,000 rows, 1023 bytes, cap 1 MB). No frozen prediction was changed by them.
