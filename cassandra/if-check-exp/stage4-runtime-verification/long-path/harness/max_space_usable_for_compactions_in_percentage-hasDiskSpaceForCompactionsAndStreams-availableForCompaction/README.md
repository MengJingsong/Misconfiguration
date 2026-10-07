# Harness — max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction

Instruments for the case's section 9 (stage 4). Written 2026-10-07 from the case's 9c table, after the design audit (results
[§1.1](../../results/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md)).
The results are in the same file.

| File | What it is | Checked how |
|---|---|---|
| `CompactionBudgetTest.java` | Unit tier, **the check alone**. Package `org.apache.cassandra.db`; copy into `test/unit/org/apache/cassandra/db/` of a clone at `cassandra-5.0.9`. Drives `Directories.getAvailableSpaceForCompactions(FileStore)` and the static `hasDiskSpaceForCompactionsAndStreams(Map, Map, Function)` against stub stores; 9e unit steps 2.1 to 2.7. Prints `STAGE4 check …` and `STAGE4 info` lines (stdout and `-Dstage4.out`). | its own checks are exact arithmetic on the stub (`round((U − 50 MiB) × pct)`); the instrument run is recorded in the results file |
| `CompactionLadderTest.java` | Unit tier, **the decision point**. Package `org.apache.cassandra.db.compaction`; copy into `test/unit/org/apache/cassandra/db/compaction/`. A real major compaction on 8 real SSTables, the table's `Directories` wrapped to read a stub store of fixed *U* (the technique of upstream `PartialCompactionsTest`); the expected ladder is **simulated from the SSTables' `onDiskLength()`** and compared with the debug lines, the three counters, the warnings and the live SSTables at `B / total` = 1.5, 0.8, 0.4, 0.1. Added at the 2026-10-07 audit. | the simulation is the 9a/§5 algorithm re-implemented from the spec; the planned outcomes 0, 2, 5, abort are asserted against it |
| `unit-run.sh [suffix]` | Copies both tests into the clone and runs `DirectoriesTest`, `CompactionsBytemanTest`, `PartialCompactionsTest`, `CompactionBudgetTest`, `CompactionLadderTest`, one `ant testsome` each; `~/stage4-logs/mscp/unit[-suffix]/{run.out,ant-*.log,summary.txt}`. | — |
| `cluster-run.py <label>` | Cluster tier, one script per label (`d95 f15 f08 f04 f01 inflight`): fresh 4 GiB loop-mounted ext4, **two node starts** (build the inputs at the default; read the Data.db lengths and `df`; compute `pct`; start with it), the 500 ms sampler (`du`, `df`, `system_views.sstable_tasks`), the trigger(s), `debug.log` parsed between byte offsets, the counters over JMX, the ladder simulated from the lengths, `EXPECTED:` lines. Writes `summary.txt`, `passes.csv`, `triggers.csv`, `samples.csv`, `session.log` to `~/stage4-logs/mscp/<label>/`. **Replaces the case's `build-inputs.sh` and `compaction-sampler.sh`.** | the first trigger of every run is its own instrument check (the run stops if its pass lines do not match the simulation or `available` is more than 1 MiB from the expected B); a dataset check stops the run before any `pct` is computed |
| `Jmx.java` | JMX client (`get` several attributes in one JVM start; `invoke` an operation with one boolean; `set`). Compiled by the run script. | the counters are read at start-up (0 each) before the first trigger; the `invoke` return code is checked before H1 |
| `make-node-yaml.sh <pct\|default>` | `conf/cassandra.yaml` from the tag plus `data_file_directories: [/mnt/stage4-data/data]` and, unless `default`, the knob. | the yaml tail is echoed into the log |

Copy the folder to the node (`~/stage4-harness-run/mscp`) before a run. The node's clone is `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54210`).
The cluster tier needs `sudo` (loop mount), Python 3.9+ (`random.randbytes`) and the bundled driver in the clone's `lib/`.

```bash
# unit tier
~/stage4-harness-run/mscp/unit-run.sh
# cluster tier: one label per call, in the background, then read ~/stage4-logs/mscp/<label>/summary.txt
nohup ~/stage4-harness-run/mscp/cluster-run.py f08 > /dev/null 2>&1 &
```

Labels and what they run: `d95` scenario A at the default `pct`; `f15` A; `f08`, `f04` B; `f01` C, then H1 and H2 (the hatch); `inflight` I1 and I2.
