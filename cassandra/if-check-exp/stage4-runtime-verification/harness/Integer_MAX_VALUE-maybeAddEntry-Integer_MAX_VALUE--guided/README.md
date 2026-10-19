# Harness — Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE

Instruments for the case's §9 (stage 4), written 2026-10-15 after the design audit (results
[§1](../../results/Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE--guided.md)). Clone `$CASSANDRA_HOME` (default `~/cassandra-run3`);
node copy `~/stage4-harness-run/imv/`.

| File | What it is |
|---|---|
| `IndexSummaryCapTest.java` | Unit U1 (`:204` at the real limit, six (*K*, *N*, interval) values) and U2 (`:108` at its boundary), package `org.apache.cassandra.io.sstable.indexsummary`; keys whose first 8 bytes are the index (ordered under the unit `ByteOrderedPartitioner`); log events captured with a logback `ListAppender`. |
| `IndexSummaryMovedLimitTest.java` | Unit U3: `BMUnitRunner`, one method per moved limit (8 · 32 · 128 MiB, offset 0) with the same offsets as the `.btm` files. |
| `unit-run.sh [suffix]` | U0 upstream `IndexSummaryTest`, then the two harness tests; BMUnit agent port 19091. Output `~/stage4-logs/imv/unit[-suffix]/`. |
| `summary-trace.btm` | Observation rules: `writer`, `init`, `refused`, `built`, `rebuild` (added: the loader's rebuild at start-up), `scan` (per-thread skip counter of the index scan). |
| `moved-limit-8.btm`, `-32.btm`, `-128.btm` | `return $! + (2^31 − 1 − L)` at the exit of `getEntrySize(DecoratedKey)`, submitted per table over the agent listener (port 19091). |
| `imvdrv.py`, `load-keys.py`, `read-keys.py` | Driver helpers; key *i* = `Random(seed × 10000019 + i).randbytes(K)` (no key file, amended 2026-10-15); the reader gets ranks from one `token(k)` scan and point-reads 5 low and 5 high ranks, joining each read to its `scan` lines. |
| `cluster-run.py <run> life1 [tables] \| armE` | Lifetime 1 (probe instrument check, `c32`, `big`, the moved tables, restart check) and arm E (lifetimes 2–4). 24 GiB heap; `~/stage4-imv/`. Output `~/stage4-logs/imv/<run>/<label>/`. |
| `Jmx.java` | JMX get client with a port argument (from the `repair_session_space` harness). |
