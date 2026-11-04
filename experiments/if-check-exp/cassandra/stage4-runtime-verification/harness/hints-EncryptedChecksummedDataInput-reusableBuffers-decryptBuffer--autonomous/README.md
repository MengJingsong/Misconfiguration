# Harness — hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous

Stage-4 harness for the autonomous case file (frozen: whole-file sha256 `0ed9ab6f...` after the audit amendments of 2026-10-26; prediction/conclusion tables
`b4c841be...`, see the results file [§1](../../results/hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous.md)). Run on `pc12`
from `~/stage4-harness-run/ec/` against the copy `~/s4-ec` (`copy-source.sh`, `ant build-test`). Logs: `~/stage4-logs/ec/<run>/` on the node. Adapted from the
`hints-CompressedChecksummedDataInput-readBuffer-uncompressedSize` harness (client, Jmx, node yaml, run script).

| File | Tier | What it does |
|---|---|---|
| `EcProbe.java` | unit + producer | Package `org.apache.cassandra.hints`. `read`: writes an encrypted hints file with the production `EncryptedHintsWriter` (descriptor params from `EncryptionContextGenerator`, test keystore, one Session), parses the raw 8-byte block headers (enc, plain), reads it with `HintsReader` on a fresh `FastThreadLocalThread`, prints the thread-local `reusableBuffers` capacity (reflection) and the reader buffer per page, thread-allocated bytes; `forged` rewrites the file to header 512 MiB/512 MiB + 5 junk bytes. `noshrink`: big then small file, same thread. `c1`: `HintsBuffer.allocate(600 KiB)` in a 1 MiB slab must throw, then reads a 600 KiB block. `produce`: the cluster tier's file writer (table `ks.t` with the fixed ID, file named for B's host id; `forged` / `plain` variants). |
| `unit-run.sh [run] [shake]` | unit | One fresh JVM per case (-Xmx2g), 3 repeats of S1-S4 and S6, S3 at max_mutation_size 4 MiB and 1 MiB, S5, noshrink, C1; `summary.txt`. |
| `make-node-yaml.sh <A\|B> <mm KiB\|default>` | cluster | Node dirs under `~/s4-ec-run`, loopback A 127.0.33.2 (JMX 7333, native 9355, storage 7033), B 127.0.33.3 (7334, 9356, 7034), key_provider block with the test keystore, `max_hints_delivery_threads 1`; **deviation:** `enabled: false` (true makes 5.0.9 fail at start on the encrypted commit log: `AbstractCommitLogSegmentManager.java:125` assert, `commitlog_disk_access_mode` refused). |
| `ec.btm`, `EcHelper.java` | cluster | Byteman (port 9333, A only): `in`/`out`/`exc` per `readBuffer()` with the thread-local capacity, reader buffer capacity and thread-allocated bytes. |
| `hprof_big.py` | cluster | Scans a live heap dump for `byte[]` lengths (checked on a known 3,000,000 / 250,944 pair). |
| `client.py`, `Jmx.java` | cluster | Python driver (protocol 4; `schemaid` creates `ks.t WITH ID`), JMX getter. |
| `cluster-run.py cell\|pos\|all\|down` | cluster | Cell: A+B, schema, B's host id, A stopped, file produced into A's hints dir, A restarted with Byteman, dispatch awaited, live heap dumps at +10/+30/+150 s, `EXPECTED:` lines. `pos`: 200 x 1 MiB hinted writes with `max_hints_file_size` default vs 4 MiB. |
| `selfcheck.py <unit dir> <cluster dir>` | both | Independent re-parse of the raw files; evaluates every frozen prediction. |

Order: `ulimit -n 100000; unit-run.sh run1b` (run1 had a harness defect in `c1`, see results §3), then `EC_RUN=run1 python3 cluster-run.py all`, then `selfcheck.py`.
