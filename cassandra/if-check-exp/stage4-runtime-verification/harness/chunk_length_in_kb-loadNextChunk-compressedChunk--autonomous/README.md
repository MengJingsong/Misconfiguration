# Harness: chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous

Written 2026-10-25 after the first freeze of the case file (hashes in the results file, section 1). Not upstream code.

| File | Role |
|---|---|
| `CompressedInputStreamOversizeTest.java` | unit tier (B2 as amended B2i): one JUnit test, `STAGE4_SET=main|cap|cap38` picks the arms (natural LZ4 chunks at 5 sizes, hand-declared wire lengths up to 128 MiB, boundary arms, ratio 1.1 raw path, OOM controls); reads `compressedChunk`/`buffer` capacities by reflection and the JVM direct `BufferPoolMXBean`; writes `$STAGE4_OUT/results-<set>.csv`. The class name must end in `Test` (`check-test-names`). |
| `unit-run.sh` | copies the test into a `copy-source.sh` tree and runs `ant testsome` three times with `-Dtest.jvm.args=-XX:MaxDirectMemorySize=512m|16m|38m`; `bash unit-run.sh <tree> <harness-dir> <outdir> ["main cap cap38"]` |
| `analyze_unit.py` | PASS/FAIL per frozen numeric unit prediction (B2f, B2i.2-7) |
| `PoolSampler.java` | samples `java.nio:type=BufferPool,name=direct` over JMX every 20 ms (`epoch_ms,direct_used,direct_count,mapped_used`) |
| `loader.py` | creates `ks.t` with the compression options and loads N rows of random blobs through the bundled Python driver (protocol 4) |
| `cluster-run.py` | one cluster run: two nodes on 127.0.12.1/2 from `~/s4-ci/node-tree`, data on `/dev/shm`, bootstrap of B from A, sampler on B; modes `normal`, `entire` (full-range ownership, `stream_entire_sstables: true`), `cap` (B with `MAX_DIRECT_MEMORY_SIZE=100m`); stops both nodes on any exit |
| `cluster-all.sh` | the 11 runs of run 1 in order, stops at the first failed trigger check |
| `analyze_cluster.py` | per-run window, baseline, peak and P (B3i.3) |
| `selfcheck.py` | independent re-parse of the raw files and the frozen-prediction checks |

Instrument checks (not readings): a full unit pass (all 21 arms; it matched the predictions, which is why run 1 repeats it unchanged, not because anything was tuned) and cluster shakedowns on 64-row loads (chunk 16384/ratio 0 normal, entire, cap at 48m, 1024/ratio 1.1, cap at 100m twice) ran before run 1; their outputs are in `pc12:~/s4-ci/shake-*` and are not used. Findings of the checks: the JMX window lines exist in B's `system.log`; the entire-sstable debug line appears; the idle node holds 54.7 MiB of direct buffers (cap 48m invalid, raised to 100m: B3i.9); the first cap-mode regex matched the JVM argument `HeapDumpOnOutOfMemoryError` and was tightened; two shakedowns collided because the first was still stopping when the second started (not a harness defect; `cluster-all.sh` runs strictly in series).
