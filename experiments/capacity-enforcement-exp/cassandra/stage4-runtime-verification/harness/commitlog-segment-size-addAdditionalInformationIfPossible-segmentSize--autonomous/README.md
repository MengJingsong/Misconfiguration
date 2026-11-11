# Harness: commitlog_segment_size / `CommitLog.addAdditionalInformationIfPossible` (set A batch 10, tag sg)

Not upstream code. Run order: unit tier, then cluster tier. Tree per tier made with `copy-source.sh` (`~/s4-b10-sg-u` built with `ant build-test`, `~/s4-b10-sg-n` with `ant jar`); node pc07, port slot 2 (127.0.2.1, JMX 7120).

| File | Role |
|---|---|
| `SgAddInfoProbeTest.java` | unit test, copied to `test/unit/org/apache/cassandra/db/commitlog/`; calls the private method by reflection and `CommitLog.handleCommitError`, on a 4 GiB and a 16 MiB tmpfs; positive control = segment file length |
| `unit-run.sh <tree> <outdir>` | mounts the tmpfs pair (sudo), runs `ant testsome`, checks the EXPECTED lines, unmounts |
| `cluster-run.sh <outroot> <arm> <rep>` | one node start per arm (A1..A5, Z32, Z8): 16/64/1024 MiB tmpfs for the commit log, filler by `fallocate`, `cassandra-stress`, samplers, `analyze.py`; node, samplers and mount removed on any exit |
| `analyze.py <armdir>` | parses the arm's raw files, prints SUMMARY and EXPECTED lines (the B3f predictions) |
| `selfcheck.py` | independent second parse of the raw logs for the self-check |

Instrument checks (shakedowns, not readings): the unit test carries known answers (the tmpfs volume with total below the segment size must produce the text, the big volume must not); `cluster-run.sh` fails at once if the volume size, the effective yaml values (from the node's config dump), the filler or the free space are not as the arm says; `analyze.py` was checked against a shakedown directory.
Plateau criterion for Z arms, fixed before run 1: `max(TotalCommitLogSize) <= commitlog_total_space + one segment`, and `> 0`; without a cap the same stress would put about 2.2 GB through the commit log.
