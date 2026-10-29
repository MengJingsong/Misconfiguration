# Harness — table_name_length-validatetablename-name_length--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 in the results file [§1](../../results/table_name_length-validatetablename-name_length--autonomous.md)). Written 2026-10-28 on `pc29`
(JDK 11.0.32.1, Ant 1.10.12). Built in a `copy-source.sh` copy `~/s4-b2/base` (`cassandra-5.0.9`, `ant build-test`, never in the repository's
tree). Logs go to `~/s4-b2/logs/table_name_length-validatetablename-name_length--autonomous/<run>/{unit,cluster}/` and node directories to `~/s4-b2/run/tbl/<label>/` on the node, outside the repo.
The two NAME_LENGTH cases (keyspace names, table names) share the constant's design; their harnesses are the same scripts with a different
probe test and a `--case` switch (`ks` | `tbl`) in `cluster-run.py`/`selfcheck.py`.

| File | Tier | What it does |
|---|---|---|
| `TableNameLengthProbeTest.java` | unit (B2) | package `org.apache.cassandra.schema`; `unit-run.sh` copies it into the copy's `test/unit/…/schema/`. Validates table names of length 1 · 48 · 100 · 221 · 222 · 223 · 255 (message, directory-name length 255 at 222, assertion status), then sizes N tables x 3 reps and a 50-column control. `STAGE4 check/case/size` lines. Deep size = a reflective walk with jamm's shallow `measure` (B5 item 1: `ObjectSizes.measureDeep` stops at `@Unmetered` `TableMetadata`, runbook defect D1); `ObjectSizes.measureDeep` printed beside it. |
| `unit-run.sh <stem> [run]` | unit | runs the probe with `ant testsome` (GC log), then the upstream `TableMetadataTest` as a sanity run; `summary.txt`. `<stem> --remove` deletes the copied test. |
| `make-node.sh <dir> [k=v ...]` | cluster (B3a) | one node on 127.0.0.1 (JMX 7199) with every directory under `<dir>` on local disk; the shipped yaml plus the extra keys. |
| `client.py` | cluster | the build's bundled Python driver (protocol 4, CL ONE): `ddl`, `write`, `one`, `try-ks`, `try-tbl`, `probe`. |
| `Jmx.java` | cluster | JMX client (`get`, `poll`), from the `write_buffer_size-append-hint` harness. |
| `cluster-run.py --case tbl [--tag run1] arms\|control\|analyze\|all` | cluster (B3e) | arms A1 B1 A2 B2 (500 tables x 1000 rows; short = 8, long = 222 characters), control C64 / C256, each on a fresh node; flush, compaction idle, settle, `jcmd GC.run`, JMX heap used, `GC.class_histogram` Total, `du`, directory-name lengths, the rejection attempt; `<label>.json`, `summary.txt` with `EXPECTED` lines; resumable; node stopped and checked on any exit. |
| `selfcheck.py --case tbl` | both | independent re-parse of the raw run-1 files (not the json); copied with its output to `results/table_name_length-validatetablename-name_length--autonomous/run1/`. |

Instrument checks (not readings): unit shakedowns (known-answer, defect D1 found there), cluster shakedown `shake1` (6 targets x 2000 rows, 300000-row control).
