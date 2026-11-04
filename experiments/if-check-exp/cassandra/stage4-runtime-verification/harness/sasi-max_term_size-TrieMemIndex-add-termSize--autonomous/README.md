# Harness: sasi-max_term_size-TrieMemIndex-add-termSize--autonomous

Written 2026-10-25 after the audit and freeze (hashes in the results file, section 1). Not upstream code.

| File | Role |
|---|---|
| `TrieMemIndexSizeTest.java` | unit tier (B2 as amended B5): one JUnit test driving `IndexMemtable.index` on a `ColumnIndex` (PREFIX / CONTAINS, `analyzed=false`) and an int SkipList column; writes `unit-results.csv`, `unit-estimates.csv` |
| `unit-run.sh` | copies the test into a `copy-source.sh` tree and runs `ant testsome` |
| `analyze_unit.py` | PASS/FAIL per frozen unit prediction (EXPECTED/GOT) |
| `Sampler.java` | JMX sampler every 100 ms: heap used, `MemtableOnHeapDataSize`, `MemtableSwitchCount` of `ks.t` |
| `loader.py` | `schema` / `load` (stop file, pause file, row log) / `verify` (read by key, one LIKE) over native protocol 4 |
| `cluster-run.py` | one label: node on 127.0.31.1 (JMX 7331, native 9353, storage 7031) from `~/<tree>`, heap 2 GiB, `memtable_heap_space` per label, load to three switches, mid-load histogram with the loader paused, flush-line extraction; node and sampler stopped on any exit |
| `cluster-all.sh` | the seven labels in series |
| `analyze_cluster.py` | PASS/FAIL per frozen cluster prediction (optional tolerance argument) |
| `selfcheck.py` | independent re-parse of the raw files |

Instrument checks (not readings): five shakedowns of the cluster script (`shake*`, 16 MiB and 256 MiB pools, 100 rows) found the switch-count baseline, OOM-string, zombie-PID and pause-file defects; the unit test ran once as the run itself.
