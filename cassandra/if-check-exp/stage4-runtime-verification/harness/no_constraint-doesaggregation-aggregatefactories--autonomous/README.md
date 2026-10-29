# Harness: no_constraint-doesaggregation-aggregatefactories--autonomous

Written 2026-10-29 after the freeze of the case file (sha256 in the results file). Not upstream code. Unit tier only; the cluster tier is `n/a` (B3).

| File | Role |
|---|---|
| `NoneDoesAggregationAllocTest.java` | the unit test (`extends CQLTester`, package `org.apache.cassandra.cql3`): arms P, P2, A1, A2 and control C over N, per-call thread allocation and `ObjectSizes.measureDeep(ResultSet.rows)`. Writes `raw.csv` and `proof.txt` to `-Dstage4.out`; asserts only instrument and set-up errors |
| `rules.btm` | Byteman rules (counts only, run in a second JVM): `doesAggregation` returns, `AggregationQueryPager.fetchPageInternal` entries, `mark()` markers (prepare and run). |
| `unit-run.sh` | `bash unit-run.sh <tree> <harness-dir> <outdir> [byteman 0/1] [sizes]`; compiles the test into a `copy-source.sh` tree (built with `ant build-test`) and runs plain `java ... JUnitCore` (jamm attached; Byteman if the 4th argument is 1) |
| `analyze.py` | PASS/FAIL per frozen prediction, plus the key numbers |
| `selfcheck.py` | independent re-parse of the raw files (written for the self-check; does not import `analyze.py`) |
| `../chain-run1-none-kind2.sh` | runs the three none-type cases one after another (plain, Byteman, analyze) |

Instrument checks (not readings): an 8 MiB `byte[]` must read 8,388,608 to 8,454,144 allocated bytes (`proof.txt`, line `CHECK`). A pre-run shakedown at N = 200 and 400 read only `proof.txt` and the Byteman counts, never `raw.csv`; its output was deleted.
