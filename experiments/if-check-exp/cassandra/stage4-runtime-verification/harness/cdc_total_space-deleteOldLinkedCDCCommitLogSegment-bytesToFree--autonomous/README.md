# Harness — cdc_total_space-deleteOldLinkedCDCCommitLogSegment-bytesToFree--autonomous

Not upstream; run from a local clone of `cassandra-5.0.9` (never the shared one). Copy this folder to the node, `sha256sum -c SHA256SUMS`.

| File | What it is |
|---|---|
| `CdcCapProbeTest.java` | Unit tier (case B2). Package `org.apache.cassandra.db.commitlog`; copy to `test/unit/org/apache/cassandra/db/commitlog/` of the clone. Writes 8 MiB mutations (CDC table, or a non-CDC table) for `volumeMiB`, reads `cdc_raw` (links, index files, du-equivalent bytes), the tracker (by reflection) and the segment state at every row and segment boundary, with a 5 ms sampler for peak links and bytes. Settings are `-Dstage4.cdc.*` (see the class comment). Sets segment size 32 MiB and `max_mutation_size` 16 MiB itself (the unit yaml has 5 MiB / 2.5 MiB). |
| `cdc-verdict.btm` | Byteman observation rules (unchanged copy from the guided harness): creation trace `pre`/`post`, `deleteOld` (the target method's exit: `bytesToFree`, remaining bytes), `reject`. |
| `cdc-sampler.py`, `cdc-consumer.sh` | 50 ms `cdc_raw` sampler (`.csv`, `.events`, `.summary`); consumer emulator (not used by this file's run). |
| `cdc-rows-64k.yaml`, `plain-rows-64k.yaml` | cassandra-stress profiles: 64 KiB blob rows into `stage4cdc.cdc_rows` (`cdc = true`) and `stage4cdc.plain_rows` (`cdc = false`). |
| `unit-run.sh` | `check` (n=48, not in the matrix) or `all`: blocking and non-blocking x n = 64/128/256/512 x 3 repeats, plus the B2h controls (n=4096 both modes, `cdc_enabled=false`, non-CDC table both modes, 1 s wait). One JVM per cell. |
| `cluster-run.sh` | One cell per node start (`<b|nb><cap>-r<rep>`, `plainb128-r<rep>`, `cdcoff128-r1`, `chk-b160`) or `all`. Local disk under `~/cdcrun`, `MAX_HEAP_SIZE=2G`, `commitlog_total_space: 1024MiB`, `memtable_heap_space: 1024MiB`. Workload about 3 x cap of 64 KiB rows in 120 s; blocking runs then do B3e step 6 (delete the two oldest links, probe, 1000 more rows) and step 7 (refill, switch `CDCBlockWrites` to false over JMX, probe, 3072 rows). |
| `unit-readings.py`, `cluster-readings.py` | Print one table row per cell from the raw files (observation only). |

Checked 2026-10-22 on pc12: `unit-run.sh check` (after two harness faults, results §3) and `cluster-run.sh chk-b160` (a 160 MiB cap, not in the matrix) ran end to end; Byteman rules fired (pre/post/deleteOld/reject lines); the sampler, `du` loop, JMX set and read-back, and the node stop worked.
