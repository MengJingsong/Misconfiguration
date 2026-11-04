# Harness — block_size-add-blockindex--autonomous

Stage-4 harness for the autonomous case file `block_size-add-blockindex--autonomous` (frozen sha256 `2e4ad670a96e...`, see the results file [section 1](../../results/block_size-add-blockindex--autonomous.md)).
Written 2026-10-28 for `pc39` (JDK 11, Ant 1.10, 40 cores, 251 GiB). Builds: `~/s4-b34/base` (`copy-source.sh` copy of `cassandra/cassandra-5.0.9/` at repository
commit `b68711e5`, `ant build-test` then `ant jar`) and variant copies (`cp -a` of the built base, one constant edited by `sed`, the files that inline it touched, `ant jar`,
constant confirmed with `javap -constants`): `v-num64`, `v-num1m` (NumericValuesWriter BLOCK_SIZE / MONOTONIC_BLOCK_SIZE = 64 / 64 and 2^20 / 2^20), `v-post32`, `v-post512`
(PostingsWriter.BLOCK_SIZE), `v-max1m`, `v-max8k`, `v-max28` (AbstractBlockPackedWriter.MAX_BLOCK_SIZE = 2^20, 2^13, 2^28), `v-tpb124` (TokenTreeBuilder.TOKENS_PER_BLOCK = 124);
the sed patches are in the run1 excerpts (`build-patches/`). Shared with the three sibling cases written in the same session: the builds, the seed data directories
(`~/s4-b34/seeds`), and the cluster engine `cluster-run.py` (identical file in the four folders; the case is taken from the folder name). Full logs on the node under
`~/s4-b34/logs/<key>/` (outside the repo).

| File | Tier | What it does |
|---|---|---|
| `BlockPackedProbe.java` | unit (B2) | package `...sai.disk.v1.bitpack`; one (writer kind, blockSize, N) per JVM; counting subclass over `flushBlock`, a sink that retains nothing, thread-allocated bytes of the constructor, `blockValues.length`, `blockIndex` sampled after every add, `[J` row of the class histogram (MBean `gcClassHistogram`), metadata size; control mode `ctl` (a growing `long[]`). `STAGE4` lines. |
| `unit-run.sh [label]` | unit | the matrix: kinds plain / mono x sizes 32, 100 (invalid), 64, 128, 16384, 2^20, 2^24 (N = 10 x 2^24) and N = bs - 1 for 128 / 16384 / 2^20; two repetitions; three control sizes; `summary.txt`. |
| `analyze_unit.py <dir> [out]` | unit | readings table and `EXPECTED` lines for B2f. |
| `cluster-run.py seed <rows> / arm <label> / all` | cluster (B3, amended) | seed load (8 processes, bundled python driver), arms A-3M, B-num64, C-num1m, A-750k, A2-3M, ctl-seg16 (restore seed, node on the arm's jar with the Byteman ledger, 500 ms JMX sampler (`Sampler.java`), CREATE INDEX x2, wait, `rebuild_index` x2, count queries, stop). |
| `ledger-bitpack.btm`, `Sampler.java` | cluster | Byteman ledger (one line per AbstractBlockPackedWriter construction with `blockValues.length`, one per `checkBlockSize` call), JMX sampler (SAI buffer gauges, heap). |
| `analyze_cluster.py [root] [out]` | cluster | readings and `EXPECTED` lines for B3f / B3g. |
| `selfcheck.py <unit dir> [<cluster root>]` | both | independent re-parse of the raw files; copied with its output to `results/block_size-add-blockindex--autonomous/run1/`. |
Instrument checks before run 1 (not readings, disclosed in results section 2): unit probe shakedown (one cell); cluster engine shakedown on a 20,000-row seed with the
`v-num64` build (SAI) and the `v-tpb124` build (SASI), logs `~/s4-b34/logs/shakedown/`.
