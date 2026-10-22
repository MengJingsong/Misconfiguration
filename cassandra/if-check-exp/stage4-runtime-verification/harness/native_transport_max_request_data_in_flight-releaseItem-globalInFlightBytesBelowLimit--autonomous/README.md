# Harness — native_transport_max_request_data_in_flight · releaseItem (`PreV5Handlers.java:127`), autonomous

Used for run 1 on 2026-10-22 (`pc12`, clone `~/cassandra-pv5` at `cassandra-5.0.9`). Results:
`../../results/native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous.md`.

| File | Use |
|---|---|
| `PreV5InflightCapTest.java` | the case's B2e unit test, verbatim except one added import (`ErrorMessage`, harness fix H1); copied to `test/unit/org/apache/cassandra/transport/` |
| `unit-run.sh` | copies the test, runs `ant testsome`, extracts the `U,` lines |
| `v4load.py`, `InflightProbe.java` | B3a client (raw protocol V4) and JMX probe, verbatim |
| `cluster-run.sh LABEL L C THROW MODE` | one cluster run, B3e steps 1–9 with the audit amendments and fix D1 (`commitlog_segment_size: 1536MiB`, `max_mutation_size: 16MiB`) |
| `cluster-all.sh` | the seven runs in order; stops at a run without a summary |
| `reduce.py RUN_DIR` | B3e step 9 readings |

Copy to `~/stage4-harness-run/pv5/`, `javac InflightProbe.java`, then `bash unit-run.sh` and `bash cluster-all.sh` (≈ 2 h: each
group-commit node start takes ≈ 7 min).
