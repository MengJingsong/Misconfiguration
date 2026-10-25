# Harness: row_cache_size-create-serialized_size--autonomous

Written 2026-10-25, tag `rc`, node `pc07`. Not upstream code. The case file's sha256 at the freeze is in the results file §1.

| File | Role |
|---|---|
| `SerializingCacheCapTest.java` | unit tier (B2 as amended B2i): `main` with modes `control <rep>`, `point <C_MiB> <S> <rep>`, `clear <rep>`; one JVM per call; writes `OBS ...` lines |
| `unit-run.sh` | compiles against `<tree>/build/classes/main` and runs the 27 points x 3 reps, controls and the `clear` arm, each in a fresh `-Xmx512m -Xms512m -XX:+AlwaysPreTouch` JVM: `bash unit-run.sh <tree> <harness-dir> <outdir> [scale]` (`scale` > 1 is a shakedown divisor only) |
| `analyze_unit.py` | RESULT lines against B2f from `obs.txt` |
| `Jmx.java` | row-cache gauge reader (`Size`, `Capacity`, `Entries`) over JMX: `once` or `poll <ms> <file>` |
| `loader.py` | Python-driver client: `load`, `scan`, `rand` modes (B3i.2) |
| `cluster-run.py` | cluster tier: `... load` (create `ks.t`, load 32,768 partitions, flush, drain) then `... arm c0 c128 c512 c1024 n128 c128b` (one node lifetime per arm; own ports 7390/7391/9390, JMX 7399, address 127.0.9.1) |
| `analyze_cluster.py` | RESULT lines against B3f from each arm's `ckpt.jsonl`, `jmx.csv` |
| `selfcheck.py` | independent re-parse of the raw files (stage-4 self-check) |
| `SerializingCacheDiag.java`, `diag-run.sh` | **post-hoc diagnostic** written after unit run 1 (a 16-thread put storm showed `RssAnon` far above `C`): samples `weightedSize()`, `size()*(S+4)` and `RssAnon`, and reads `RssAnon` before and after `malloc_trim(0)`, with and without `MALLOC_ARENA_MAX=1`. Not a B2f reading. |

Instrument checks (not readings): a scaled unit sequence (`scale` 16) and a small cluster sequence (2,048 partitions, 20 s random phase, arms `c0` and `c128`) ran before the freeze; outputs are in `~/s4-rc/shake-*` on `pc07` and are not used. The scaled run exposed two instrument defects, both fixed before run 1: freed blocks reused across points inside one JVM (now one JVM per point, B2i.8), and NMT "committed" is not resident memory (now `RssAnon` differences to the 0 MiB arm, B3i.3). The `clear` arm at full scale was also run once during the checks (it showed the leak direction); its output is not used.
