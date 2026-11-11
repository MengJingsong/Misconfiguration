# Harness: sasi-max_term_size-PerSSTableIndexWriter-addTerm-termSize--autonomous

Written 2026-10-26 (UTC) after the audit and the freeze (hashes in the results file, section 1). Not upstream code. Own harness; the sibling case's harness (`sasi-max_term_size-OnDiskIndexBuilder-add-termSize--autonomous`) was read for lessons only.

| File | Role |
|---|---|
| `WriterProbeTest.java` | unit tier (B2 as amended B5): one JUnit test; every arm drives `PerSSTableIndexWriter.Index.add` (the writer's own check, `:218`) with one key per add. Arms: boundary S=1022..1025 (N=10,000); growth S=1023 at N=1k/10k/100k; cap control at option 1/8/default (N=100k, COMPACTION) and default at N=200k; FLUSH reference; tokenized 1 MiB value (131,072 distinct words) at default and option 1. Writes `writer-results.csv`, `writer-estimates.csv` |
| `unit-run.sh` | copies the test into a `copy-source.sh` tree and runs `ant testsome`; optional scale argument is for the instrument check only |
| `analyze_unit.py` | PASS/FAIL per frozen B2f prediction (EXPECTED/GOT lines) |
| `loader.py` | schema, load and prefix-query actions (python driver, protocol 4) for the kinds `m` (a=1023 B, b=1024 B), `a`, `tc` (tokenized) |
| `HeapSampler.java` | samples JVM heap used over JMX every 500 ms |
| `cluster-run.py` | one label: one node on 127.0.30.1 (JMX 7330, native 9352, storage 7030; Byteman 9330 unused) from `~/s4-pw`, heap 2 GiB, data under `~/s4-pw-data/<label>`, autocompaction disabled; load, flush, compact with per-window log counts, file sizes, heap samples, class histogram sampled every 3 s during the compaction; stops the node on any exit |
| `cluster-all.sh` | the four labels (m, c1, c16, tc) in series |
| `analyze_cluster.py` | PASS/FAIL per frozen B3f prediction |
| `selfcheck.py` | independent re-parse of the raw files, including the full gzipped node log (kept on the node) for the rejection totals |

Instrument checks (not readings): unit test at scale 20 (N/20) once; cluster shakedown of all four labels at scale 100 (rows/100) once, which found two harness bugs before run 1 (zombie children made the stop wait 90 s then SIGKILL; the gzip target path), plus a missing prefix query for kind `a`. No frozen prediction was changed by them.
