# Harness: no_constraint-allocateblock-inchunkpointer--autonomous

Written 2026-10-29 after the freeze of the case file (sha256 in the results file, section 1). Not upstream code. Unit tier only (B3 is `n/a`).

| File | Role |
|---|---|
| `InMemoryTrieAllocBlockTest.java` | one JUnit test in `org.apache.cassandra.db.tries`: for i in {1,3,7,11,15,19}, setup outside the window, then window A (one mid-chunk block) and window B (one chunk-start block), plus an empty-window floor; off-heap arm at i = 11, 15; control mode (i = 22 and the hard limit at S_23); no Byteman |
| `unit-run.sh` | `bash unit-run.sh <tree> <harness-dir> <outdir>`: sweep JVM (`-Xmx1g`) and control JVM (`-Xmx6g`), `java` + JUnitCore; not `ant testsome` |
| `analyze.py` | PASS/FAIL for each item of the frozen prediction |
| `selfcheck.py` | independent re-parse of the raw rows |

Instrument check before the run (not a reading, disclosed): one shakedown JVM with `stage4.reps=0` (warm-up cycle only) whose output was seen (A allocated 0 bytes, B allocated N + about 100 bytes, `sizeOnHeap` steps on A) and deleted.
