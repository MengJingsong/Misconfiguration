# Harness: counter_cache_size (three autonomous cases, one shared instrument set)

Written 2026-10-27 on `pc39`, tag `cc`. Not upstream code. The three case files
(`counter_cache_size-iscountercacheenabled-capacity--autonomous`, `...-getcachedcounter-...`, `...-putcachedcounter-...`)
share one run; each is audited, predicted and judged against its own B2f/B2g/B3f/B3g. The identical files are copied into
each case's harness folder; `analyze_*.py` take the case (`is`, `get`, `put`) as their first argument.

| File | Role |
|---|---|
| `CounterCacheCapTest.java` | unit tier: one JUnit class (`test/unit/org/apache/cassandra/db/`), parts U1 direct puts + helper, U2 `putCachedCounter`/`getCachedCounter` + heap + allocation, U3 production write path, U4 save/reload, U5 resize; writes `U<part> key=value` lines |
| `unit-run.sh` | `bash unit-run.sh <tree> <harness-dir> <outdir> <base|noguard>`: copies the test into the tree and runs `ant testsome` |
| `analyze_unit.py` | `analyze_unit.py <is|get|put> <unit.txt> [base|noguard]`, and `analyze_unit.py <case> <base unit.txt> compare <noguard unit.txt>` for the allocation comparison |
| `Jmx.java` | cache gauge reader and setter/saver over JMX (`once <scope>`, `save`, `set <counter|row|key> <MiB>`) |
| `cluster-run.py` | cluster tier driver: arms `c0 c1 c8 c64 cdef c8b rt64 r8 sv8 rl0 rl1 rl8` |
| `analyze_cluster.py` | `analyze_cluster.py <is|get|put> <outdir>` |
| `selfcheck.py` | independent re-parse of the raw files for the self-check |

The patched source copy `tree-noguard` is `copy-source.sh` plus three one-line edits in `ColumnFamilyStore.java`
(2501 and 2508 to `if (false)`, 3269 `> 0` to `>= 0`); its diff is saved with the run as `noguard.diff`.
Shakedowns (small N, deleted) ran before the freeze: they found that `counter_write` makes five cache entries per key, that
`-pop dist=uniform(...)` stalls for it, that the cache MBean is `org.apache.cassandra.db:type=Caches` and that its capacity
setters are attributes (all fixed in `cluster-run.py`/`Jmx.java` before run 1).
