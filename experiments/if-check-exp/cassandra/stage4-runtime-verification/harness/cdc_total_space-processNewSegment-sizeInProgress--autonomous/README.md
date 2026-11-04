# Harness — cdc_total_space-processNewSegment-sizeInProgress--autonomous

Not upstream; derived from the harness of `cdc_total_space-deleteOldLinkedCDCCommitLogSegment-bytesToFree--autonomous` (same constraint). Run from a local `copy-source.sh` copy of `cassandra-5.0.9` (never the shared one). Copy this folder to the node, `sha256sum -c SHA256SUMS`.

| File | What it is |
|---|---|
| `CdcTotalSpaceProbeTest.java` | Unit tier (case B2). Package `org.apache.cassandra.db.commitlog`; copied to `test/unit/org/apache/cassandra/db/commitlog/`. Writes 37 mutations of S/3 = 11,184,810 B (>= 384 MiB) to a CDC table (or, as a control, a non-CDC table), counting rejections as attempts; reads `cdc_raw` (links, index files, bytes), the tracker by reflection and the segment state at every mutation and segment boundary, with a 5 ms sampler for peaks; flushes both tables at the end and reads again (`afterFlush2s`, `final`, `walkSum`, `du`). Settings `-Dstage4.cdc.*` (class comment). Sets S = 32 MiB and `max_mutation_size` = 16 MiB itself (the unit yaml has 5 MiB / 2.5 MiB). |
| `cdc-verdict.btm` | Byteman observation rules (unchanged): `pre`/`post` of `processNewSegment`, `deleteOld`, `reject`. |
| `cdc-sampler.py` | 50 ms `cdc_raw` sampler (`.csv`, `.events`, `.summary`). |
| `cdc-rows-64k.yaml`, `plain-rows-64k.yaml` | cassandra-stress profiles: 64 KiB blob rows into `k.t` (`cdc = true`) and `k.tp` (`cdc = false`). |
| `unit-run.sh` | `check` or `all`: {blocking, non-blocking} x N = 96, 192, 1024 x 3 repeats + the non-CDC-table controls (N = 96, both modes, 2 repeats). One JVM per cell; adds the DEBUG logger for line 351 to the copy's `test/conf/logback-test.xml`. |
| `cluster-run.sh` | One cell per node start (`<nb|b><cap>-r<rep>`, `plainnb128-r1`, `chk-b160`) or `all`. The node has its own loopback address 127.0.0.37 and JMX port 7237 (another agent shares the host); data under `~/s4-cdc/run`; `MAX_HEAP_SIZE=1G`, `commitlog_total_space: 2048MiB`. 2 GiB of 64 KiB rows at 200 rows/s, `nodetool flush` every 10 s, 30 s wait, final reading; blocking cells then delete the two oldest links and probe. Kills only its own PID. |
| `unit-readings.py`, `cluster-readings.py` | Copies from the earlier harness (observation only); not used for the verdict, see `results/<stem>/run1/selfcheck.py`. |

Checked 2026-10-25 on pc12: `unit-run.sh check` (N = 96 non-blocking: 37 accepted, 11 `Freed up` lines, Byteman `post`/`deleteOld` lines, reading lines complete) and `cluster-run.sh chk-b160` (blocking cap 160 MiB, 6144 rows: forbidden segments, `Rejecting mutation` WARN, 4 links, release by deleting two links accepted on probe 2, node stopped). Shakedowns, not readings.

2026-10-25 run note: the first launch of `cluster-run.sh all` exited 126 for every cell (execute bit lost on the node; `"$0"`); the script now calls `bash "$0"` and `SHA256SUMS` was regenerated before the cluster tier restarted. `unit-run.sh` ran with its first version. A copy of the harness that ran is on `pc12:~/s4-cdc/harness`.
