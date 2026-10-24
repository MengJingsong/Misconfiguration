# Harness — range_tombstone_list_growth_factor-addInternal-capacity--autonomous

Stage-4 harness for the autonomous case file (case 1 of the three siblings (entry pointer `RangeTombstoneList.java:668`, `addInternal`)); written 2026-10-23 on `pc07` (`node0.jason92-320876`) by the autonomous stage-4 session.
The three sibling files share one design and one code base (copies of the same scripts, per-case grids selected by `CASE = A`);
each file has its own tree (`~/cassandra-rtl-a`, made by `copy-source.sh`, `ant build-test`), its own node data (`~/stage4-rtl-a/`) and its own logs
(`~/stage4-logs/rtl/a/<run>/`). Frozen versions and the audit are in the results file ([§1](../../results/range_tombstone_list_growth_factor-addInternal-capacity--autonomous.md)).

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `RangeTombstoneListGrowthProbeTest.java` | unit (B2) | One JUnit class, grid of this file's B2b/B2c: sorted and random-order adds, `copy()`, capacity read by reflection (`starts`, `ends`, `markedAts`, `delTimesUnsignedIntegers`), `unsharedHeapSize()`, Jamm `measureDeep` minus an empty list's, the controls. Writes `build/test/rtl-unit-A.txt`. | shakedown at 2,000 instead of 100,000 (renamed copy) |
| `unit-run.sh [run] [shakedown]` | unit | B2e: copy the probe into the tree, `ant testsome`, collect the output and junit XML, remove the probe, run `unit-analyze.py`. | shakedown |
| `unit-analyze.py <rtl-unit.txt>` | unit | B2f/B2g with the audit's R3/R6/R7 as `EXPECTED:` lines, a labelled POST-HOC line, the matched row. | shakedown |
| `client.py` | cluster | Bundled Python driver (protocol 4): `schema`, `load` (one request in flight per partition, ascending), `select`. | shakedown |
| `Jmx.java` | cluster | `get`, `setdouble` (the write-only attribute `RangeTombstoneListResizeGrowthFactor`), `poll` (2-s counter series). | shakedown found the setter is an attribute, not an operation |
| `HeapPoll.java` | cluster | Eden / old / survivor use every 250 ms over JMX (`jstat` cannot attach under `-XX:+PerfDisableSharedMem`); from the `tombstone_failure_threshold` harness. | shakedown |
| `growth.btm` | cluster | Byteman, observation only: samples `growToFree` (capacity, size, factor) and `grow(i, newLength)` every 1000th call. | shakedown |
| `cluster-run.py A all \| <lifetime>... \| down` | cluster | The B3 design as amended (R4/R5/R7/R8): per lifetime a fresh data directory, conf, start, schema, autocompaction off; per cell factor set/read back, baseline histogram, load with checkpoints (JMX metrics, `GC.class_histogram`, `RssAnon`), 2-s counter series, heap poll, Byteman trace. Appends `cells.jsonl`. Env `RTL_RUN`, `RTL_SCALE` (shakedown divisor), `RTL_DIR`. | scaled shakedowns (`RTL_SCALE=100`) |
| `cluster-analyze.py <cluster-dir>` | cluster | B3f/B3g with R3/R8 as `EXPECTED:` lines; writes `readings.csv`. | scaled shakedowns |
| `selfcheck.py unit <txt> <xml> \| cluster <dir>` | both | Independent re-parse of the raw files (own simulation of lines 683-686, raw `jcmd` histograms, `system.log` segments, trace); does not import the analyzers. | on run 1 |

Run order (run 1, on the node):

```bash
H=<repo>/cassandra/if-check-exp/stage4-runtime-verification/harness/range_tombstone_list_growth_factor-addInternal-capacity--autonomous
bash $H/unit-run.sh run1
RTL_RUN=run1 python3 -I $H/cluster-run.py A all          # one background job
python3 -I $H/cluster-analyze.py ~/stage4-logs/rtl/a/run1/cluster
python3 -I $H/selfcheck.py cluster ~/stage4-logs/rtl/a/run1/cluster
```

Not run: a single partition of 500,000 tombstones (R5: about 2.5 TB of array copying, infeasible), and the optional initial-allocation variants where the case lists them as optional.
