# Harness — trie-pathreconstructor-keybytes-growth--autonomous

Stage-4 harness for the autonomous case file `TriePathReconstructor.keyBytes` (entry `TriePathReconstructor.java:33`); written 2026-10-25 on `pc07` (`node0`) by the autonomous stage-4 session, tag `tp33`. Not committed (the orchestrator commits).
Tree `~/s4-tp33` (`copy-source.sh`, `ant build-test`), node data `~/s4-tp33-run/`, logs `~/s4-tp33-logs/<run>/`. Ports: JMX 7210, Byteman listener 9110, native 9142, storage 7010 (SSL 7011), loopback `127.0.33.1`.
Frozen version and the audit: the results file [§1](../../results/trie-pathreconstructor-keybytes-growth--autonomous.md).

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `PathReconstructorSizeTest.java` | unit (B2) | One JUnit class (copied into `test/unit/org/apache/cassandra/db/tries/`): `TrieEntriesIterator` subclass exposing `keyBytes.length`; grid of key lengths L, raw `ByteComparable.fixedLength` paths and real `DecoratedKey` paths (random, no 0x00; all 0x00), ON_HEAP/OFF_HEAP, 3 repetitions; M control (L=100, M=10k/100k); N = 1, 8, 64 concurrent iterators with thread-allocated bytes. Prints `TP33` lines to `build/test/tp33-unit.txt`. | compiled and ran once (run 1a) |
| `unit-run.sh [run]` | unit | Copies the test in, `ant testsome`, collects output and JUnit XML, removes the test, runs the analyzer. | run 1a, 1b |
| `unit-analyze.py <tp33-unit.txt>` | unit | B2f (1)-(7) as `EXPECTED:` lines, the matched B2g row. R9 changed its zero-key checks after run 1a. | run 1a (before R9), 1b |
| `trie-growth.btm` | cluster | Byteman, observation only: `AFTER WRITE keyBytes` in `addPathByte` and `addPathBytes`; one trace line per growth (thread, iterator identity, new length). | shakedown (scale 50): lines written, lengths 64..65536 |
| `client.py` | cluster | Bundled Python driver, protocol 4: `schema`, `load` (t_big 60,000-byte keys without 0x00 seeded by index; t_small 16-byte keys), `scan` (R threads of `SELECT token(k), v`, fetch size 100, for N seconds), `keylen`. | shakedown |
| `Jmx.java` | cluster | JMX `get`/`poll` (copy of the range-tombstone harness' file). | shakedown |
| `cluster-run.py all \| <label>... \| down` | cluster | The B3 design as amended (R5, R6): per lifetime (H256, H1024, H64 heap_buffers; O256 offheap_objects) fresh node and data directory, Byteman agent, schema, loads, warm-up, scan phases R=1 and R=32 with flushes at 60 s and 120 s, t_small scan, JMX series every 2 s, class histogram every 15 s, `phases.csv` windows, `system.log` segment, stop by PID. `TP33_SCALE` divides the workload (shakedown). Waits for the native port to accept, not only `statusbinary` (shakedown found the node reports `running` several seconds early). | scaled shakedown (`TP33_SCALE=50`, H64 only, two attempts) |
| `cluster-analyze.py <dir> [unit.txt]` | cluster | B3f (a)-(d) as `EXPECTED:` lines and the B3g row; `c` read from the unit file. | scaled shakedown |
| `selfcheck.py unit \| cluster` | both | Independent re-parse of the raw files (own code, does not import the analyzers). | shakedown and run 1 |

Run order: `bash unit-run.sh run1b`; `TP33_RUN=run1 python3 -I cluster-run.py all`; `python3 -I cluster-analyze.py ~/s4-tp33-logs/run1/cluster`; `python3 -I selfcheck.py cluster ~/s4-tp33-logs/run1/cluster ~/s4-tp33-logs/run1b/unit/tp33-unit.txt`.
