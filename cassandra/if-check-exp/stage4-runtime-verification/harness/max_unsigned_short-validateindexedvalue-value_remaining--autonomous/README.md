# Harness - max_unsigned_short-validateindexedvalue-value_remaining--autonomous

Written 2026-10-28 on pc32 (stage 4), after the audit amendments B2i and B3i were frozen (`frozen-prediction.txt` = B2 ... B3 text of the case file, sha256 `a3cb3f0f...`; case file `647419b2...`). Idea reuse only from `../max-unsigned-short-validate-key-remaining--autonomous/` (a sibling constant); nothing of its conclusions is used.
Run copy: `~/s4-b2/c` (`copy-source.sh` of `cassandra/cassandra-5.0.9`, `ant build-test`; both tiers use it, one run at a time). Logs: `~/s4-b2-logs/<run>/{unit,cluster}/`. Node: 127.0.2.1, JMX 7270, native 9042, data on tmpfs `/dev/shm/s4-b2/node`.

| File | Tier | What it does |
|---|---|---|
| `IndexedValueLimitTest.java` | unit (B2) | CQLTester subclass (package `org.apache.cassandra.index.internal`, compiled outside the tree). Mode `bounds`: S = 1000 / 65533 / 65534 / 65535 / 65536 on an indexed and an unindexed text column, clustering blob column at 1000 / 65534 / 65535 / 65536 (indexed and unindexed), composite partition key probe (information). Mode `scale`: per N (and per indexed / unindexed) a fresh table, N inserts of S = 65534 distinct random base64 text, pool usage sampled after every insert (peak), index backing table memtable `owns()`, sstable counts before the explicit flush, `liveDiskSpaceUsed` after it. |
| `unit-run.sh [run] [quick]` | unit | compiles the test, runs `bounds` (stops if the boundary fails), `scale_default` (pool 2048 MiB, N = 100, 1000, 4000) and `scale_pool64` (64 MiB, N = 4000) in separate JVMs (`-Xmx4g`, JUnitCore, test yaml on local disk); `summary.txt` with EXPECTED lines |
| `analyze-unit.py <dir> bounds\|scale` | unit | EXPECTED lines (the frozen numbers of B2i) from the STAGE4 lines |
| `writer.py` | cluster | bundled Python driver: `schema <table> index\|noindex`, `write <table> <S> <N> <seed>`, `drop` |
| `cluster-run.py <run> [main\|quick]` | cluster (B3) | life 1 (`memtable_offheap_space` 512 MiB): boundary precheck, arms n1000 / n4000 / n16000 / s65535 / noidx4000 / s100; life 2 (256 MiB): n16000; `summary.txt`, `arms.jsonl`, `samples-*.csv`, `system.log.life{1,2}`; node stopped on any exit |
| `selfcheck.py <logs>/<run>` | both | independent re-parse of the raw outputs and node logs (does not import the run scripts) |
| `frozen-prediction.txt` | - | the frozen B2 and B3 text |

Shakedowns (`shake1`, not readings): unit quick (N = 100, 1000), cluster quick (300 and 50 inserts). They found no fault in the instruments; thresholds were fixed before them.
