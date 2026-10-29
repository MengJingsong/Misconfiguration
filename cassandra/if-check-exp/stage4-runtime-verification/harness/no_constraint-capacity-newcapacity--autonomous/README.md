# Harness: no_constraint-capacity-newcapacity--autonomous

Written 2026-10-29 after the freeze of the case file (sha256 in the results file, section 1). Not upstream code. Unit tier only (B3 is `n/a`).

| File | Role |
|---|---|
| `BufferPoolCapacityTest.java` | one JUnit test in `org.apache.cassandra.net`: arms E / G / S / M per requested capacity C (fresh JVM per C) and control rows; raw rows to `<out>/raw.csv`; asserts nothing |
| `NetProbe.java` | Byteman-fed counter of `super.capacity` calls (line 124) and the gauge snapshot at line 128 |
| `rules.btm` | Byteman rules at `BufferPoolAllocator$Wrapped.capacity(int)` lines 124 and 128 |
| `unit-run.sh` | `bash unit-run.sh <tree> <harness-dir> <outdir>`: 5 sweep JVMs, 2 control JVMs (cache 128 / 0) and a 16 MiB known-answer JVM; `java -Xmx512m` + JUnitCore + Byteman |
| `analyze.py` | PASS/FAIL for each item of the frozen prediction |
| `selfcheck.py` | independent re-parse of the raw rows |

Instrument check before the run (not a reading, disclosed): one shakedown JVM at C = 4096 with 1 repetition, whose output was seen (E, G, S, M behaved as predicted) and deleted.
