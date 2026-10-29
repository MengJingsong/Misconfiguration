# Harness: no_constraint-resizeto-newcapacity--autonomous

Written 2026-10-29 after the freeze of the case file (sha256 in the results file, section 1). Not upstream code. Unit tier only (B3 is `n/a`).

| File | Role |
|---|---|
| `SafeMemoryResizeToTest.java` | one JUnit test in `org.apache.cassandra.io.util`: arms E / D / H / X per C (fresh JVM per C), control arm `grow1`; raw rows to `<out>/raw.csv`; asserts nothing |
| `NativeLedger.java` | static ledger of native allocations/frees (copies, allocation count and bytes, frees, peak live), fed by Byteman |
| `rules.btm` | Byteman: `SafeMemory.copy` entry, `Memory.<init>(long)` line 65 (`$bytes`), `SafeMemory$MemoryTidy.tidy` entry |
| `unit-run.sh` | `bash unit-run.sh <tree> <harness-dir> <outdir>`: compiles into a `copy-source.sh` tree, runs 5 sweep JVMs and 2 control JVMs (`java -Xmx512m` + JUnitCore + Byteman agent); not `ant testsome` |
| `analyze.py` | PASS/FAIL for each item of the frozen prediction (B2 amendment, item e) |
| `selfcheck.py` | independent re-parse of the raw rows |

Instrument check before the run (not a reading, disclosed): one shakedown JVM at C = 1024 with 1 repetition, whose output was seen (it matched the prediction) and deleted. Native figures are exact integers; the ledger was checked against `capacity()` in every row (live after == capacity after).
