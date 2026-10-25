# Harness: entry-size-limit-serialize-serializedSize--autonomous

Written 2026-10-25 after the freeze of the case file (sha256 in the results file, section 1). Not upstream code.

| File | Role |
|---|---|
| `SerializingCacheLimitTest.java` | unit tier (B2 as amended B2i): one JUnit test, arms `guard_*`, `nocache`, `agg64`, `agg64_repeat`, `agg128`, `agg256`, `shrink256to128`, `over1_512MiB`, `over8x256MiB`, `over8x512MiB`, `agg3072`, `clear_probe64`; Blob values, `RssAnon` sampler every 10 ms, RESULT lines to `$STAGE4_OUT/results.csv`. The class name must end in `Test` (the build's `check-test-names` rejects other names; the first draft was called `...Probe`). |
| `unit-run.sh` | copies the Java into a `copy-source.sh` tree and runs `ant testsome` with the malloc variables of B2i.2; `bash unit-run.sh <tree> <harness-dir> <outdir> [arms] [scale]` (`arms`/`scale` are shakedown switches only) |
| `analyze_unit.py` | PASS/FAIL per frozen numeric prediction (B2i.6) from `results.csv` |
| `cluster-run.py` | cluster tier (B3 as amended B3i): `python3 cluster-run.py <tree> <nodedir> <outdir> <driver-dir> [phases]`; phases `c0 c64 c256 c1024 big` (run 1) and `c0b bigctl` (added controls, same script with two extra phase names); single node on 127.0.0.77 with its own ports, restart per `row_cache_size`, `RssAnon` sampler, `nodetool info` poller, `jcmd GC.class_histogram` |
| `analyze_cluster.py` | PASS/FAIL per frozen numeric prediction (B3i.4) from the phase files |
| `selfcheck.py` | independent re-parse of the raw files (section 5 of the results file) |

Instrument checks (not readings): a unit shakedown at `STAGE4_SCALE=8` and a cluster shakedown (`STAGE4_SMALL=800 STAGE4_BIGROWS=4 STAGE4_BIG256ROWS=8`, phases c0 c256 big) ran before run 1; their outputs were deleted and not used. The cluster-run.py of run 1 is kept as `results/.../run1/cluster-run.py.as-run1`; the later copy only adds the two phase names and `startswith('big')`.
