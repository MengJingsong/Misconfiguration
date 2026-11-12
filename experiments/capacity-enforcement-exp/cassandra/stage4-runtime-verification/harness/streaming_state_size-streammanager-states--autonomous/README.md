# Harness — streaming_state_size-streammanager-states--autonomous

Stage-4 harness for the autonomous case file (`StreamManager.java:268-282`, the Guava `states` cache with
`maximumWeight(streaming_state_size)`); written 2026-11-11 on the local node0 (shared; this run: loopback 127.0.0.21/.22,
storage 7300, ssl 7301, native 9342, JMX 7499/7498). Frozen versions and the audit are in the results file
(`../../results/streaming_state_size-streammanager-states--autonomous.md`, section 1).
Working tree (made by `copy-source.sh`, `ant build-test`): `/mydata/jingsong-cass-s4/o53/src`; node trees `n1`, `n2` are `cp -a`
copies of it (`prepare-nodes.sh`). Logs: `/mydata/jingsong-cass-s4/o53/{shakedown,run1}/`.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `StreamingStateCapTest.java` | unit (B2) | The case file's B2a test with N = 5000 (S4-A2); prints `O53 EMPTY= TIMEUUID_SIZE= w= N=` and, every 250 inserts, `retained`, `weightNow`, jamm `deep` per (addPeer, size) | shakedown at N = 500 (renamed copy). The first shakedown found that `printf(...%n)` is split over several log lines by the test logger; the test prints one `String.format` per line since. |
| `unit-run.sh [run] [shakedown]` | unit | copies the test into the tree, `ant testsome`, keeps `test.log` (from `build/test/logs/_jdk11/`) and the junit XML, removes the test and its classes, runs `unit-analyze.py` | shakedown |
| `unit-analyze.py` | unit | B2f/B2g as amended (S4-A3, S4-A4) as `EXPECTED:` lines; prints the matched row | shakedown |
| `prepare-nodes.sh` | cluster | makes `n1`, `n2` from the built tree and keeps pristine `cassandra.yaml.orig`, `cassandra-env.sh.orig` | run once |
| `set-yaml.py` | cluster | writes a node's yaml from the pristine copy (replace or append top-level keys; seeds line) | shakedown (yaml copies kept per label) |
| `cluster-run.sh <run> <label> <size> <stats> <rebuilds> <every>` | cluster | two nodes (S4-A5, S4-A6), schema + 100 rows at `CONSISTENCY ALL`, flush, the rebuild loop, samples (vtable `count(*)` with cqlsh, `jcmd GC.class_histogram` StreamingState count, `nodetool info` heap), final vtable and histogram; stops on a busy port, a node that dies or does not come up, a ring not 2 x UN, or a wrong `Storing streaming state … for size` line; both nodes killed by saved PID on any exit | shakedown at 40MiB, 3 rebuilds: 1/2/3 states on each node, histogram = vtable. It found that Cassandra deletes its `-p` pid file at shutdown, so the stop routine lost the PID; the PID is saved once the node is up (`n<k>.pidsave`) since. |
| `cluster-all.sh [run]` | cluster | runs the four labels of S4-A7 one after another: s16k, s32k, s4m, s4m-nostats (150 rebuilds, samples every 25) | — |
| `cluster-analyze.py <run-dir>` | cluster | B3f/B3g as amended (S4-A8, S4-A9), w and d taken from the unit tier's lines; prints the matched row | written before the cluster run produced a reading |
| `selfcheck.py <run-dir>` | both | independent re-parse of the raw files (junit XML, raw `test.log`, `samples.csv` vs `summary.txt`, final histogram and vtable files, `rebuilds.csv`, `system.log` plan counts) | results section 5 |
