# Harness — tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous

Stage-4 harness for the autonomous case file (audit freeze sha256 `4c289eb0…`, amendments A1-A8, 2026-10-26; results file
[`../../results/tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous.md`](../../results/tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous.md)).
Written 2026-10-26 on `pc07` (node0) from the closed twin `../tombstone_failure_threshold-countTombstone-tombstones--autonomous/`
(same knob, same code path; its `HeapPoll`, `ThreadAlloc`, `JfrBuf` are copied unchanged). Port slot 1: node at 127.0.1.1
(storage 7000, native 9042), JMX 7110. Trees: unit `~/s4-b10-tf-src` (`ant build-test`), cluster `~/s4-b10-tf-n` (`ant jar`), both from
`copy-source.sh`. Logs `~/s4-b10-tf-logs/<run>/`; node data on tmpfs `/dev/shm/s4-b10-tf`.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `TombstoneFailureThresholdMetricsRecordingTest.java` | unit | B2 with A1-A4: pk 0 = N row deletions, pk 1 = live rows; sweep T in {1000, 10000, 100000, N, 200000, MAX}, 5 reads each, thread-allocated bytes, response size, tombstone metrics; then the 1 MiB `local_read_size_fail_threshold` control. | shakedown 1-2 (N = 1200): count T+1, metrics, control aborts (LRS) |
| `unit-run.sh [run] [shakedown]` | unit | copies the test into the tree, `ant testsome`, collects `tfm-unit.tsv` and the junit XML, cleans up, runs `unit-analyze.py`. | shakedown |
| `unit-analyze.py` | unit | criteria c1-c6 and the control as `EXPECTED:` lines, the matched B2g row. | shakedown |
| `cluster-run.py all \| down` | cluster | A5-A7: setup lifetime (schema, ingest, flush, first-trigger check), one lifetime per T, size variant, live control, 1 MiB control lifetime; node stopped on any exit. | shakedown at N = 20,000 and N = 100,000 (found the `statusbinary` "not running" match, the paging defect of the control reads, the OOM regex) |
| `cluster-analyze.py <dir>` | cluster | b1-b3, controls, variant ratio as `EXPECTED:` lines, `readings.csv`, the matched row. | shakedown |
| `HeapPoll.java`, `ThreadAlloc.java`, `JfrBuf.java` | cluster | heap pools over JMX every 250 ms; node-wide allocated bytes; JFR allocation listing. | twin's checks, plus the shakedown |
| `selfcheck.py <unit-dir> <cluster-dir> <jfr-dir>` | both | independent re-parse of the raw files. | run on the shakedown logs |
