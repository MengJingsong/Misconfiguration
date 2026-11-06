# Harness — DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous

Stage-4 instruments for the case file
[`../../../../stage3-ai-deep-read/jingsong/cases/DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md`](../../../../stage3-ai-deep-read/jingsong/cases/DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md)
(amendments A1–A15). Results: [`../../results/DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md`](../../results/DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md).
Run on `pc41` with `RUN=/mydata/jingsong-s4/DF_getAvailable-getLocalPathForWrite-maxCapacity-run1`. Needs `sudo` (loop mounts).

| File | What it does |
|---|---|
| `TestLdaMaxCapacity.java` | Unit tier (B2). Copied into `hadoop-common/src/test/java/org/apache/hadoop/fs/` of both source copies. 10 blocks of 200 `getLocalPathForWrite(path, size, conf)` calls (`{dir0}` and `{dir0,dir1}` × 5 sizes); per call: outcome, directory, the number after "is" in the failure message, `getUsableSpace()` before/after, bytes written. Inputs from env `LDA_DIR0`, `LDA_DIR1`, `LDA_OUT`, `LDA_VARIANT`. |
| `unit-run.sh` | Makes `src-baseline` and `src-ablated` with `../../copy-source.sh`, deletes lines 528-530 in the ablated copy (checks: exactly 3 deleted lines), mounts the 256M/512M loop filesystems under `$RUN/mnt/`, runs baseline/ablated × 2 with `mvn -o test` in the module (no install), checks surefire counts, unmounts. `--compile-only` is the instrument check. |
| `unit-analyze.py` | Per-block readings from the four CSVs and the baseline-vs-ablated / rep-vs-rep comparison (χ² 2×2). |
| `cluster-run.py` | Cluster tier (B3): copies the distribution, writes the configuration, 1 GiB loop fs as the only NM local dir, NN/DN/RM/NM with `--daemon` on default ports, `hdfs dfsadmin -safemode wait` (A14), teragen once, terasort at L900/L300/L60 with a 0.5-s `df`/`du` sampler, application logs copied after each job (A15); then builds the ablated `hadoop-common` jar, swaps it in with all daemons stopped, and repeats. Stops every daemon of the run and unmounts on any exit. |
| `selfcheck.py` | Independent re-parse of the raw files: surefire XML and the allocator's own ERROR/history lines (unit); copied task syslogs, client logs, sample CSVs (cluster). |

Lessons from building it: the allocator logs the failure message first and the call's history after it; `Logger.setLevel(DEBUG)` in the test did not produce the allocator's DEBUG notes under the module's test logging (only the ERROR + history of failures appear); the AM's syslog also contains `org.apache.hadoop.mapred.MapTask` (in a failed task's stack trace), so the map container is found by the `MapTask` logger prefix; the NodeManager deletes non-aggregated container logs when it restarts.
