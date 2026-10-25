# Harness: transform-stack-capacity-splice-newCount--autonomous

Written 2026-10-25 after the freeze of the case file (sha256 in results §1). Not upstream code.

| File | Role |
|---|---|
| `StackSpliceCapacityTest.java` | unit tier (B2/B2i): one JUnit test in package `org.apache.cassandra.db.transform`, arms buildup / refill grid / heap / control; writes raw observations to `$STAGE4_OUT/raw.csv` (asserts nothing) |
| `rules.btm` | Byteman rules: line 94 (every `splice`), line 95 (grow branch), `ShortReadPartitionsProtection.moreContents` entry; trace file from `-Dstage4.trace` |
| `unit-run.sh` | `bash unit-run.sh <tree> <harness-dir> <outdir> [byteman 0/1] [arms]`; compiles into a `copy-source.sh` tree and runs `java -Xmx512m ... JUnitCore` |
| `analyze_unit.py` | PASS/FAIL per frozen prediction U1-U5 and the Byteman cross-check |
| `cluster-run.py` | cluster tier (B3/B3i): two loopback nodes, load, diverge, scans at L, key-cache control; stops nodes by PID |
| `analyze_cluster.py` | PASS/FAIL per frozen prediction C1-C5 |
| `selfcheck.py` | independent re-parse of the raw files |

Instrument checks (not readings): unit shakedown of the buildup and refill arms under Byteman (S and G totals equal the test's counts), heap and control arms (ctl_cap first crashed in the OOM handler on `MemoryMXBean`; fixed to use `Runtime`); cluster shakedown at 4000 rows (LS=10,500, 8 s) showing both nodes up, short reads occurring (log line), Byteman trace written, histograms parsed, key cache moving. Shakedown outputs were deleted and are not used.
