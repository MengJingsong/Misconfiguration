# Harness: nativecell-int-max-size-NativeCell-size--autonomous

Written 2026-10-25 after the freeze of the case file (sha256 in the results file, section 1). Not upstream code.

| File | Role |
|---|---|
| `NativeCellGuardTest.java` | unit tier (B2 as amended B2i), package `org.apache.cassandra.utils.memory`; one JUnit test; arms S (sizes), R (repeat), P (pool-limit control), O (overshoot), H (heap control), G1/G2 (guard probes with a real ~2 GiB direct buffer); csv lines to `$STAGE4_OUT/results.csv` |
| `unit-run.sh` | `bash unit-run.sh <tree> <harness-dir> <outdir> [arms] [scale]`; copies the test into a `copy-source.sh` tree and runs `ant testsome` with `-Dtest.jvm.args=-XX:MaxDirectMemorySize=6g` and the malloc variables of B2i.3 |
| `analyze_unit.py` | PASS/FAIL per numeric prediction of B2i.5 from `results.csv` |
| `JmxSampler.java` | cluster sampler (100 ms): RssAnon of the node PID, `AllMemtablesOffHeapSize`, `MemtableOffHeapSize`, `OverSizedMutations` Count; compiled with `javac -d <dir>` |
| `cluster-run.py` | `python3 -I cluster-run.py <nodetree> <nodedir> <outdir> <driver-dir> <sampler-dir> [arms]`; arms A A2 B K64 K128 K256 K512 hb (B3i.3); single node on 127.0.0.31 (ports 7031/9031/7331), fresh data directory and restart per arm, protocol v4 |
| `analyze_cluster.py` | PASS/FAIL per numeric prediction of B3i.4 |
| `selfcheck.py` | independent re-parse of the raw files (results file section 5) |

Instrument checks (not readings; outputs deleted): unit arms S P O H at `STAGE4_SCALE=16` and G at full scale ran once, which found one bug (an `int` page-touch loop overflowed for the 2 GiB buffer; fixed). `analyze_unit.py` gave 30 of 30 PASS on that shakedown. Cluster arms A A2 B K64 hb ran at `STAGE4_SCALE=0.05` (5 rows instead of 100); the analyser's row-count checks FAIL there by construction, the rest PASS; it proved the sampler, the three refusal texts (frame limit, `validateSize`) and the off-heap gauge.
