# Harness — DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace

Instruments for the case's §9 (stage 4), written 2026-10-15 after the design audit (results
[§1](../../results/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace--guided.md)). Run from a clone at `cassandra-5.0.9`
(`$CASSANDRA_HOME`, default `~/cassandra-run3`); node copy `~/stage4-harness-run/dds/`.

| File | What it is | Checked how |
|---|---|---|
| `WriteDirectoryGuardTest.java` | Unit tier (9e steps 2.1–2.5), package `org.apache.cassandra.db.compaction.writers`, `CQLTester` + `BMUnitRunner`; the partitioner from `-Dstage4.partitioner`; a `@BMRule` stubs `Directories$DataDirectory.getAvailableSpace()` to the static `STUB` when ≥ 0. Prints `STAGE4 [<partitioner>] check …` lines. | the instrument run (results §1.2) |
| `unit-run.sh [suffix]` | Copies the test, runs upstream `CompactionAwareWriterTest` and the harness test once per partitioner; the BMUnit agent on port 19091. Output `~/stage4-logs/dds/unit[-suffix]/`. | — |
| `guard-trace.btm` | Observation rules: `guard est= avail= refused=` (the comparison's operands), `switch positions=` (each writer and its path), `writeable size= table=` (the second check site). | `TestScript: no errors`, re-run before every start |
| `make-node-yaml.sh <B\|A> <m>` | `~/stage4-dds/conf`: the tag's yaml plus partitioner, one token, directories, `concurrent_compactors: 1`, `min_free_space_per_drive`. | yaml tail echoed into the summary |
| `cluster-run.py <run> <label>` | One label per call (13 labels, 9b): fresh 4 GiB loop ext4 at `/mnt/stage4-dds`, start with the trace, 8 inputs, ballast to *U*, JMX switch, idle control, background trigger, 0.5 s sampler, `EXPECTED:` lines. Output `~/stage4-logs/dds/<run>/<label>/`. Needs `sudo` for the mount. | shakedown 1 (results §1.2) |
| `Jmx.java` | JMX client (`invoke` a boolean operation, `get`), from the `max_space…` harness. | — |
