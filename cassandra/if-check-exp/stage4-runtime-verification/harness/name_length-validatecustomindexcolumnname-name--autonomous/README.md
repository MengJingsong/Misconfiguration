# Harness - name_length-validatecustomindexcolumnname-name--autonomous

Written 2026-10-28 on pc32 (stage 4), after the audit amendments B2i and B3i were frozen (`frozen-prediction.txt`, sha256 `8d201203...`; case file `40b4934e...`).
Run copy: `~/s4-b2/c` (`copy-source.sh` of `cassandra/cassandra-5.0.9`, `ant build-test`). Logs: `~/s4-b2-logs/<run>/{unit,cluster}/`. Node: 127.0.2.1, JMX 7270, native 9042, data on tmpfs `/dev/shm/s4-b2/node`, `sasi_indexes_enabled: true`.

| File | Tier | What it does |
|---|---|---|
| `NameLengthProbeTest.java` | unit (B2) | CQLTester subclass (package `org.apache.cassandra.cql3`, compiled outside the tree). Mode `names`: column length L in {1, 47, 48, 49, 64, 200} x {custom SASI, plain} x 3 repeats; records CREATE TABLE / CREATE INDEX accept or reject (with the exception text), loads 10,000 rows of a 100-char hex value, records memtable `owns()`, live data size, heap, and the byte sum of the table directories after flush. Mode `rows`: row-count control (plain, L = 10, N = 1000 / 10,000 / 100,000) and the unindexed baseline. |
| `unit-run.sh [run]` | unit | compiles the test, runs both modes in separate JVMs (`-Xmx4g`, JUnitCore, test yaml on local disk with `sasi_indexes_enabled: true`, `memtable_heap_space: 2048MiB`); `summary.txt` with EXPECTED lines |
| `analyze-unit.py <dir> names\|rows` | unit | EXPECTED lines (the frozen numbers of B2i) |
| `writer.py` | cluster | bundled Python driver: `schema <table> <L> <custom\|plain\|none>` (reports the CREATE INDEX outcome), `indexcount`, `write <table> <L> <N> <seed>` (128 in flight), `drop` |
| `cluster-run.py <run> [main\|quick]` | cluster (B3) | life A (`memtable_heap_space` 256 MiB): custom40 / 48 / 49 / 100, plain40 / 48 / 100, none40, each 500,000 rows (2,000,000 in the frozen text of B3c; reduced by B3i.3, see its 2026-10-28 amendment) then `nodetool flush` and `compact`; lives B (128 MiB) and C (512 MiB): plain48; `summary.txt`, `arms.jsonl`, `samples-*.csv`, `system.log.life{A,B,C}`; node stopped on any exit. `NL_ROWS` overrides N (default 500,000). |
| `selfcheck.py <logs>/<run>` | both | independent re-parse of the raw outputs and node logs |
| `frozen-prediction.txt` | - | the frozen B2 and B3 text |

Shakedowns (`shake1`, not readings): unit full run (found one harness fault: a `java.io.File` vs Cassandra `File` type in the directory sum), cluster quick (20,000 rows: about 4,000 rows/s, so 2,000,000 rows is about 8 minutes per arm, under the 12 minute limit of B3i.3).
