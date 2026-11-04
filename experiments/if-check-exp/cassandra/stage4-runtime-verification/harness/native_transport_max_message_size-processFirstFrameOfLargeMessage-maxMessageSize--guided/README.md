# Harness — native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided

Instruments for the case's §9 (stage 4), written 2026-10-20 after the step-0 audit (frozen §9 hash `14c3b5fd…`, results file
§1). Run from a copy on the node, `~/stage4-harness-run/nms/` on `pc06`; both run scripts write the harness `md5sum` into
their `summary.txt`. Clone `$CASSANDRA_HOME` (default `~/cassandra-run1`); node folders `~/stage4-nms/`; logs `~/stage4-logs/nms/`.

| File | Tier | What it is | Checked how |
|---|---|---|---|
| `NativeMessageSizeHoldTest.java` | unit | `CQLTester` in-process server and a raw protocol-v5 client on a plain socket (hand-written CRC frames, `Crc.crc32()`). For limits 1 · 4 · 16 MiB (set live, after the in-flight limits 256 MiB and queue capacity 128 MiB): requests of body *L* + 1, *L*, *L* − 1 and the cluster tier's 8 MiB-blob request, every frame but the last sent; the server's `CQLMessageHandler` (via the `ConnectionTracker`) is read on its event loop: `largeMessage` present, `tooBig`, buffers kept and their bytes, `received`; `RequestDiscarded`; then the last frame and the response; a 64 KiB request after each limit. Readings as `STAGE4 reading` lines; it asserts only instrument conditions. A QUERY `SELECT … WHERE pk = 0 AND v = ? ALLOW FILTERING` (no write, so the unit yaml's small `max_mutation_size` does not interfere). | compiled against the clone before run 1; its own checks (handler found, hold reached, response received) |
| `unit-run.sh [run]` | unit | Upstream `MessageSizeLimitTest`, then the harness test; `unit-summary.py` tabulates. Output `~/stage4-logs/nms/<run>/unit/`. | — |
| `unit-summary.py <harness.out>` | unit | Table of the readings; the kept bytes of the 8 MiB request per limit against R2's bands. | — |
| `hold-client.py` | cluster | The raw v5 client of 9c (`hold_large_request.py`): *N* connections, PREPARE of `INSERT INTO ks.t (pk, v) VALUES (?, ?)` on connection 0, a 64 KiB control EXECUTE, an idle period (the baseline), then per connection a thread that writes every frame but the last of one EXECUTE with an 8 MiB blob; `HELD` when all are written or a connection has stalled 3 s (paused by the server); hold; then per connection the last frame and the response; a 64 KiB follow-up. Uses the bundled driver's `SegmentCodec` and message encoders only (`drv.py`). | shakedown 1 |
| `drv.py` | cluster | The bundled Python driver on `sys.path` (from the `networking_cache_size` harness). | — |
| `nms.btm` | cluster | Byteman, observation only: `lm` (a CQL `LargeMessage` built, its size and the knob read then), `toobig`, `ffl` (`processFirstFrameOfLargeMessage` result; `false` = paused), `acq` (capacity outcome for a request above 131,071 B), `frm` (per frame: `tooBig`, overload, buffers kept), `done`. | `TestScript`: 6 rules type checked, no errors (`~/stage4-logs/nms/instrument/testscript.log`); `Submit -l` lists 6 rules at every node start |
| `cluster-run.py [run] [label …]` | cluster | One node lifetime per label: `k16`, `k4`, `k1` (9e A, B), `kdef` (knob unset, supplementary), `ref`, `ctl` (9f R1); `shake-*` labels for the shakedown only (2 MiB request, 5 s hold; values of no 9a arm). Per label: 200 ms JMX poll of the networking pool (`Size`, `UsedSize`, `OverflowSize`), `java.nio` direct and `RequestDiscarded`; at 5 s of the hold `RssAnon` and NMT summary; the reading is `Size` at 5 s of the hold minus the median `Size` with the connection(s) idle (R2). `EXPECTED:`, `READING`, `SUMMARY` and a computed `ROW` line in `summary.txt`. Output `~/stage4-logs/nms/<run>/cluster/<label>/`. | its own set-up checks stop the run on failure |
| `make-node-yaml.sh [key=value …]` | cluster | `~/stage4-nms/conf` from the tag's conf (loopback, data under `~/stage4-nms/data`) plus the label's keys (from the `batch_size_fail_threshold` harness). | the yaml tail and the startup config dump are written to `summary.txt` |
| `Jmx.java` | cluster | JMX reader (`get`, `poll`) from the `batch_size_fail_threshold` harness. | — |

Run order (run 1, 2026-10-20, node `pc06`):

```bash
H=~/stage4-harness-run/nms
$H/unit-run.sh run1
ulimit -n 100000; python3 $H/cluster-run.py run1        # background job; about 15 min
```
