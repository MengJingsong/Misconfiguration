# Harness — column_index_cache_size-indexSamples-cacheSizeThreshold

Instruments for the case's section 9 (stage 4), as amended by the step-0 audit of 2026-10-14. Written 2026-10-14 after the
freeze. The results are in
[`../../results/column_index_cache_size-indexSamples-cacheSizeThreshold.md`](../../results/column_index_cache_size-indexSamples-cacheSizeThreshold.md).

| File | What it is | Checked how |
|---|---|---|
| `ColumnIndexThresholdTest.java` | Unit tier. Package `org.apache.cassandra.io.sstable.format.big`; copy it into `test/unit/org/apache/cassandra/io/sstable/format/big/` of a clone at `cassandra-5.0.9`. Builds partitions with the real `BigFormatPartitionWriter` (one block per row: 1,024-byte values, `column_index_size` 1 KiB), creates the entry as `BigTableWriter` does, serializes it and deserializes it at each read-time threshold. Prints `STAGE4 check`, `row`, `read`, `boundary`, `info` lines (stdout and `-Dstage4.out`). | `javac` against the clone's classpath before the run; its own consistency checks (`S` the same for every write-time threshold, `size − S` = the three-term `h`) |
| `unit-run.sh [upstream\|harness\|all]` | Runs upstream `RowIndexEntryTest` and the harness test: `~/stage4-logs/cics/unit/`. | — |
| `index-trace.btm` | Byteman observation rules (`write`, `read`, `fetch`, joined per thread with link maps); see the file's header for the line formats. | Byteman `TestScript`: six rules, no errors (also re-run by `cluster-run.py` before every start) |
| `Jmx.java` | JMX client: `get` several attributes in one JVM start, `set` an attribute with a typed value (`int:2`) and read it back, `setonly` a write-only attribute (`KeyCacheCapacityInMB`, `long:256`), `invoke` a one-argument operation. | the instrument run sets `ColumnIndexCacheSizeInKiB` and sets `KeyCacheCapacityInMB` (the instrument run fails if the `Capacity` gauge does not follow) |
| `histo.sh <pid> <out>` | The census: `jcmd GC.class_histogram` (a full collection), then `GC.heap_info`; prints the live counts and bytes of `RowIndexEntry$IndexedEntry`, `$ShallowIndexedEntry`, `IndexInfo`, `RowIndexEntry`, and the heap used. | parses at the instrument step |
| `make-node-yaml.sh <label>` | The tag's yaml with `column_index_size: 4KiB` and `key_cache_size: 8MiB`; the knob stays at the shipped 2 KiB. | prints its diff into the log |
| `send-cql.py` | Bundled Python driver, protocol 5: `probe`, `load` (single-partition unlogged batches of 32 rows, random 1 KiB values), `read` (one point read per partition at a fixed `ck`). | `probe` prints the protocol |
| `cluster-run.py instrument\|run` | The cluster tier (9e as amended): `instrument` is the shakedown, `run` is run 1. Logs `session.log`, `summary.txt` (`EXPECTED:` lines), `readings.csv` (one row per pass), `index.trace`, `histo/`. Stops on a failed instrument or dataset check; stops the node on any exit. | the instrument mode |

Copy the folder to the node (`~/stage4-harness-run/cics`) and compare `md5sum` before a run. The node's clone is `~/cassandra-run1` at
commit `b5f2a54` (`cassandra-5.0.9`).
