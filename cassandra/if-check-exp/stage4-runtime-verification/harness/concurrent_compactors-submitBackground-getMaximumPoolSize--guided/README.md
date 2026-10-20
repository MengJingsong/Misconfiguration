# Harness — concurrent_compactors-submitBackground-getMaximumPoolSize--guided

Instruments for the case's section 9 (stage 4); written 2026-10-20 after the design audit (results §1.1).

| File | What it is |
|---|---|
| `ConcurrentCompactorsProbeTest.java` | Unit tier. Package `org.apache.cassandra.db.compaction`; 8 tables × 4 SSTables per pool size 1 · 2 · 4 · 8, every `CompactionTask.runMayThrow` held by a Byteman rule; reads the executor's active count and maximum pool size by reflection and the held tasks' summed input bytes. |
| `unit-run.sh [suffix]` | Copies the test into the clone (`~/cassandra-run4`) and runs it with `ant testsome`; output `~/stage4-logs/cc/unit[-suffix]/`. |
| `cluster-run.py prepare` / `run <label>` | Cluster tier. `prepare`: 40 GiB loop ext4, one node, 8 tables × 4 SSTables × 256 MiB (random values, compression off), backup of the data directory on the same filesystem. `run`: restore, start (yaml `concurrent_compactors`, `autocompaction_on_startup_enabled: false`), `setcompactionthroughput 16`, enable autocompaction on all tables at once, 2-s sampler of `ks1` bytes and `system_views.sstable_tasks`; labels `idle n1 n2a n2b n2c n4 n8 ctl8 ctl8r ctl8a`. |
| `run-all.sh <labels>` | Runs labels in order. |
| `Jmx.java` | JMX getter (copied from the `max_space_usable…` harness). |

Needs `sudo` (loop mount), Python 3.9+, the bundled driver in the clone's `lib/`. Copy the folder to `~/stage4-harness-run/cc` before a run. Run order used: `idle`, `n2a n1 n4 n8 ctl8 n2b n2c`, then `ctl8r ctl8a` after the control amendment. The filesystem image (about 25 GB) is deleted after a run; `prepare` rebuilds it in about 4 minutes.
