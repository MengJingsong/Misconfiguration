# Harness — native_transport_max_request_data_in_flight_per_ip · `DatabaseDescriptor.java:3369`, autonomous

Run 1 on 2026-10-26, `pc12`, working tree `~/s4-b8-pi` (from `copy-source.sh`, `ant build-test`), run copies in `~/s4-b8-pi-harness/` (`SHA256SUMS`), logs `~/s4-b8-pi-logs/`. Port slot 4 (`127.0.4.1`, JMX 7140; Byteman has no listener, so no agent port is used).

| File | Use |
|---|---|
| `PerIpInFlightLimitTest.java` | unit tier (B2): copied to `test/unit/org/apache/cassandra/transport/`; prints `U,<arm>,...` lines; asserts only that every answerable request was answered. Arm Z is the instrument check (limit 1 GiB), not a reading. |
| `unit-check.sh`, `unit-run.sh [LABEL]` | compile check; the unit run (moves the test node's internode ports to `127.0.4.1:7042/17042` in the working tree's `test/conf/cassandra.yaml` so it cannot clash with other cases on the node) |
| `loadgen.py` | cluster client: 64 python-driver `Cluster` objects, synchronous INSERT loops, protocol 4 or 5; optional second source address |
| `hold.btm` | Byteman rule, the 5 s write hold (hold-fixed setting) |
| `PiProbe.java`, `JmxSet.java` | JMX sampler (200 ms) and the r9 live-limit setter |
| `cluster-run.sh` | one node run (B3e with the audit amendments); stops the node by PID on any exit |
| `cluster-all.sh` | runs r1..r9 in order, stops at a run without a summary |
| `reduce.py` | per-run readings |

Driver scripts: `cluster-all.sh` started r1 (loadgen with a barrier); it was stopped after r1 had begun because with the cap at 8 MiB only 2
requests are in flight and a run takes about 21 min (512 / 2 x 5 s), so `cluster-all2.sh` waited for r1 and ran on; r2 attempt 1 then hung in
the python driver's connect phase (one of 64 connections never came up, the barrier broke, no load was sent), so `loadgen.py` was changed to
fail a run that does not connect all workers (exit 3) and `cluster-all3.sh` ran r2..r9 with up to three attempts each. r1 used the barrier version
of `loadgen.py` (64 of 64 connected, 512 of 512 ok). r7 and r9 use 4 INSERTs per thread (the other runs 8). `selfcheck.py` is the step-4 re-parse.
