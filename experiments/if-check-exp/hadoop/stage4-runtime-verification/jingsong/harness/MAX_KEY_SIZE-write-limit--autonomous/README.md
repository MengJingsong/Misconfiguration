# Harness — MAX_KEY_SIZE-write-limit--autonomous

Stage-4 instruments for the case file
[`../../../../stage3-ai-deep-read/jingsong/cases/MAX_KEY_SIZE-write-limit--autonomous.md`](../../../../stage3-ai-deep-read/jingsong/cases/MAX_KEY_SIZE-write-limit--autonomous.md)
(section B2 with amendments A1–A6; B3 is n/a, A7). Results:
[`../../results/MAX_KEY_SIZE-write-limit--autonomous.md`](../../results/MAX_KEY_SIZE-write-limit--autonomous.md).
Written 2026-11-06, after the audit's freeze, before run 1.

| File | What it is |
|---|---|
| `TestBoundedLimitHeap.java` | The B2e test (package `org.apache.hadoop.io`, hadoop-common test classpath). `testDirect`: 9 (C, L) rows of A2/A3 (100 passes of `W = L + 1024` single-byte writes, in-limit-only passes, exception cost at the same stack depth, retained heap) plus an instrument line (support, zero, 1 MiB known answer, heap size and GC name, which shows the A1 JVM options applied). `testTFileKey`: the three TFile key cases on `LocalFileSystem` (warm-up round discarded). `testControl`: the A5 control (`ByteArrayOutputStream(32)`, `DataOutputBuffer`). Prints `IFCHK,…` CSV lines. |
| `unit-run.sh <run-dir> [--compile-only]` | Copies the test into `<run-dir>/src` (made by `../../copy-source.sh`), runs it in `hadoop-common` with JDK 8 and `-Dmaven-surefire-plugin.argLine="-Xmx512m -XX:+UseSerialGC -Difchk.tmp=<run-dir>/tmp"`, then the existing `TestBoundedByteArrayOutputStream,TestTFileStreams`; prints the frozen `EXPECTED:` lines; stops when the instrument line is missing, a surefire count is not clean (the build returns 0 on failures) or the row counts are wrong; deletes the TFile files. `--compile-only` is the instrument check (test-compile). |
| `selfcheck.py <run-dir>` | Results §5: re-parses the raw surefire output and reports independently of the run script and prints PASS/FAIL against B2f/A4/A5 and the A4 "grows" test. Run with `python3 -I`. |

Outputs (full logs stay on `/mydata`): `<run-dir>/logs/unit/` (`unit-run.log`, `mvn-test-*.log`, surefire reports and
`-output.txt`, `ifchk.csv`, `selfcheck.txt`). Run 1 used `/mydata/jingsong-s4/MAX_KEY_SIZE-write-limit-run1`. No daemons, no ports.
