# Harness: DEFAULT_SMALLEST_SSTABLE_BYTES-shouldSwitchWriterInCurrentLocation-getEstimatedOnDiskBytesWritten--autonomous

Written 2026-10-25 after the freeze of the case file (sha256 in the results file section 1). Not upstream code. Helper code adapted from the closed sibling
harness `sstable_size_in_mb-shouldSwitchWriterInCurrentLocation-maxSSTableSize--autonomous/`.

| File | Role |
|---|---|
| `SplitWriterHarnessBase.java` | builds a one-sstable input (distinct seeded 1 KiB blobs), drives `SplittingSizeTieredCompactionWriter` (`RecSplit`) and `MaxSSTableSizeWriter` (`RecMax`, positive control) directly; one line per `shouldSwitchWriterInCurrentLocation` call (operand, returned, ratio index, `currentBytesToWrite`); writes `calls-<arm>.csv`, `files-<arm>.csv`, `arms.txt` |
| `SplittingConstantProbeTest.java` | unit tier (B2 as amended B2i): arms `d50 d0 d5 dbig small d50z ctl20 ctl40` |
| `unit-run.sh` | copies the two Java files into a `copy-source.sh` tree and runs `ant testsome`; `bash unit-run.sh <tree> <harness-dir> SplittingConstantProbeTest <outdir> [parts]` (`parts` is a shakedown scale only) |
| `analyze_unit.py` | RESULT / MODEL / INFO lines against B2f and B2g (as amended B2i) |
| `cluster-run.py`, `loader.py` | cluster tier (B3 as amended B3i): `python3 cluster-run.py <tree> <nodedir> <outdir> <arm>...`; one node lifetime per tree; node on 127.0.0.77, JMX 7277; DEBUG logging of the writers and `Directories`; 0.25 s `du` sampler on the table directory, `RssAnon` and `jcmd GC.heap_info` samplers (jstat cannot attach to the node); per-arm `summary.json` |
| `analyze_cluster.py` | RESULT lines against B3f and B3g (as amended B3i) from the three trees' `summary.json` |
| `selfcheck.py` | independent re-parse of the raw logs (written after run 1's analyzers; see the results file) |
