# Harness: sstable_size_in_mb-shouldSwitchWriterInCurrentLocation-maxSSTableSize--autonomous

Written 2026-10-24 after the freeze of the case file (sha256 in the results file §1). Not upstream code.

| File | Role |
|---|---|
| `WriterHarnessBase.java` | shared with the `lcs-level-capacity-…` harness (identical file): builds a one-sstable input (distinct seeded 1 KiB blobs), drives `MajorLeveledCompactionWriter` through a recording subclass (one line per `shouldSwitchWriterInCurrentLocation` call: operand, returned boolean, `currentLevel`, `totalWrittenInLevel`), writes `calls-<arm>.csv`, `files-<arm>.csv`, `arms.txt` |
| `MajorLeveledSizeCapTest.java` | unit tier (B2, as amended B2i): arms `s10 s50 s200 smax s50z wide` |
| `unit-run.sh` | copies the Java into a `copy-source.sh` tree and runs `ant testsome`; `bash unit-run.sh <tree> <harness-dir> MajorLeveledSizeCapTest <outdir> [parts]` (`parts` is a shakedown scale only) |
| `analyze_unit.py` | RESULT lines against B2f (read from `calls-*.csv`, `files-*.csv`, `arms.txt`) |
| `cluster-run.py`, `loader.py` | cluster tier (B3, as amended B3i): `python3 cluster-run.py sml1 <tree> <nodedir> <outdir> s5 s20 s80 s160 stcs wide20`; one node lifetime, auto-compaction disabled, deterministic loader, 0.25 s `du` sampler on the table directory, per-file sizes and levels (`sstablemetadata`), paged read-back count |
| `analyze_cluster.py` | RESULT lines against B3f from each arm's `summary.json`, `files.csv` |

Instrument checks (not readings): a shakedown at `STAGE4_PARTS=400` / `STAGE4_PER_PHASE=400` (unit class and three cluster arms) ran before run 1; its output is in `~/stage4-sml1/shake*` on `pc12` and is not used.
