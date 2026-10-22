# Harness — memtable_heap_space-needsCleaning-nextClean--autonomous

Stage-4 instruments for `cases/memtable_heap_space-needsCleaning-nextClean--autonomous.md` (run 1, 2026-10-21/22, `pc07`).

| File | Tier | What |
|---|---|---|
| `NextCleanBoundaryTest.java` | unit (B2e) | the case file's test with audit amendments U1 (off-heap control printed and asserted) and U2 (Part C helper chunk count and released bytes). Copied to `test/unit/org/apache/cassandra/utils/memory/` of a fresh clone. stdout goes through a logger that splits each `printf` token into its own log line; rebuild the `NCB` lines by joining the `SubstituteLogger` messages (see `unit-run.sh`'s log). |
| `unit-run.sh` | unit | copies the test, runs `ant testsome`, collects the XML |
| `ncl.btm` | cluster | Byteman observation rules (amendment K1): O7 line-128 true, O1b pool usage before each release ≥ 64 KiB, O5b refused `tryAllocate`. Writes to the file named by `-Dncl.trace` (CassandraDaemon closes `System.out` after start-up). Parse-checked with `org.jboss.byteman.check.TestScript`: no errors. |
| `cluster-run.sh` | cluster | one run of B3e: `bash cluster-run.sh <R> <L MiB> [<t>]`. Node on 127.0.0.5, JMX 7205, data `~/stage4-ncl`, logs `~/stage4-logs/ncl/<R>` (shared-host deviations). |
| `all-runs.sh` | cluster | R1..R5 in sequence |
| `analyze.py` | cluster | derived values and the B3f checks (`python3 -I analyze.py ~/stage4-logs/ncl`) |

Known limits found in run 1: the O7 rule de-duplicates by the `reclaiming` value, so an episode that starts with the same `reclaiming` as the last logged one (typically 0) is not logged, and a line can carry a snapshot read after a concurrent switch (then `used − reclaiming < T`); logback rolls `system.log` at local midnight, so a run spanning midnight needs the rolled zip prepended (done by hand for R4).
