# Harness — default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous

Written 2026-10-27 on `pc39`. Adapted from the sibling harness `group-by-row-limit-incrementRowCount-rowsCounted--autonomous` (same code path; here the knob is the compile-time constant `SelectStatement.DEFAULT_PAGE_SIZE`, client page size unset). Frozen versions and audit: `../../results/default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous.md` section 1.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `DefaultPageSizeProbeTest.java` | unit (B2) | CQLTester probe, prints `DPS` lines: L limits strings (constant read by reflection), W white-box counter of the first sub-read, B first-read serialised size (`count(v)` and `count(*)`), E real `AggregationQueryPager` over a counting wrapper (rows, sub-reads, per-sub-read allocated bytes), P plain aggregate | shakedown at 4000 rows (const 1000): all predictions passed; found that `count(*)` and `count(v)` serialise equally (amendment U1 reworded) |
| `unit-run.sh <run> <constant> [shakedown]` | unit | edits line 114 in `~/cassandra-run1`, `ant testsome`, collects, restores | shakedown |
| `unit-analyze.py <run-dir>` | unit | B2f/B2g as `EXPECTED:` lines | shakedown |
| `DpsJmx.java` | cluster | JMX heap poller (100 ms) | shakedown |
| `rowlimit.btm` | cluster | Byteman observation rule on `GroupByAwareCounter.onClose`: `GB ms rows groups unfinished done` per local read (K=2 lines per read) | shakedown: first-trigger check (fetch-1000 reads of exactly 1000 rows) passed on all three variants |
| `cluster-run.py <run> [shakedown]` | cluster | one node, load with stock build and 2 GiB heap, then variants stock / 500 / 200000 at 512 MB: first-trigger check, 3 x GROUP BY unset, 3 x plain `count(payload)`, stock-only client fetch 500 / 200000 arms, guardrail arm | shakedown at 20000 rows (scale 100) |
| `cluster-analyze.py <dir>` | cluster | B3f/B3g as `EXPECTED:` lines; definitions fixed in its docstring before any reading | shakedown |
| `selfcheck.py <dir>` | cluster | independent re-parse of cells, traces and GC logs, with the last GC pauses of every dead cell | written for step 4 |

Builds: `mkvar.sh`-style copies `~/s4-dps-v500`, `~/s4-dps-v10000`, `~/s4-dps-v200000` (`copy-source.sh`, `sed` on line 114, `ant jar`). Logs on pc39: `~/s4-dps-logs/`.
