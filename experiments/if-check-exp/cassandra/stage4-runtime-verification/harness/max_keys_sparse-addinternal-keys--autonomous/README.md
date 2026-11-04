# Harness: max_keys_sparse-addinternal-keys--autonomous

Stage-4 instruments for the case file `cases/max_keys_sparse-addinternal-keys--autonomous.md` (sha256 and amendments in `results/max_keys_sparse-addinternal-keys--autonomous.md` §1). Run node `pc41`, run copy `~/s4-b34/src` (`copy-source.sh` of `cassandra/cassandra-5.0.9/`, then `ant build-test`); nothing is added to `cassandra/cassandra-5.0.9/`.

| File | Tier | What |
|---|---|---|
| `SparseKeysProbeTest.java` | unit | JUnit test copied into the run copy's `test/unit/.../index/sasi/disk/`. Builds `OnDiskIndexBuilder(UTF8Type, Int32Type, SPARSE|PREFIX)` cells (K keys per term, T terms; 3 reps), prints `STAGE4 cell` lines (estimate vs T*116+T*K*108, thread-allocated bytes, finish outcome, file length) and the B2h segmenting control (`STAGE4 control`, 8 MiB rule). |
| `unit-run.sh` | unit | copies the probe, runs it with `ant testsome` (`-Xmx512m`), then the upstream `OnDiskIndexTest` as a sanity run, writes `summary.txt`. `--remove` deletes the copied test. |
| `make-node.sh` | cluster | builds a one-node `conf/` (local disk, 127.0.0.1) from the run copy's yaml plus extra lines. |
| `mks.btm` | cluster | Byteman rule at `OnDiskIndexBuilder.finish(sasi Descriptor, File)` printing `MKS_BUILD terms= est= mode= file=` for every index build (the builder's own counter). |
| `cluster-run.py` | cluster | one node start (`sasi_indexes_enabled`, 1 GiB G1 heap, Byteman); six tables K=5/6/1000 x SPARSE/PREFIX with 60 000 rows flushed once; the `max_compaction_flush_memory_in_mb` 1 vs 64 control; readings in `readings.txt`. Stops the node on any exit. |
| `chain.sh` | cluster | runs `cluster-run.py main`. |
| `selfcheck.py` | both | re-parses the raw logs (`test.out`, `stdout.txt`, `system.log`, `datalist.txt`) and re-tests every number the results file cites. |

Instrument checks before run 1: the unit probe's estimate equals the file's formula in every cell and the upstream `OnDiskIndexTest` passes (12 tests); the Byteman rule is parse-checked with `org.jboss.byteman.check.TestScript` (the first version named the wrong `Descriptor` class and did not match; fixed before run 1, see results §2/§3).
Run `chain.sh` / `unit-run.sh` on the run node; logs go to `~/s4-b34/logs/max_keys_sparse/<run>/`.
