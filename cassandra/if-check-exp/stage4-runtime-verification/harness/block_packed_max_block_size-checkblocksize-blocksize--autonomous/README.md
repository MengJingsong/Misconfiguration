# Harness — block_packed_max_block_size-checkblocksize-blocksize--autonomous

Stage-4 harness for the autonomous case file `block_packed_max_block_size-checkblocksize-blocksize--autonomous` (frozen sha256 `90ea9f2c57e9...`, see the results file [section 1](../../results/block_packed_max_block_size-checkblocksize-blocksize--autonomous.md)).
Written 2026-10-28 for `pc39` (JDK 11, Ant 1.10, 40 cores, 251 GiB). Builds: `~/s4-b34/base` (`copy-source.sh` copy of `cassandra/cassandra-5.0.9/` at repository
commit `b68711e5`, `ant build-test` then `ant jar`) and variant copies (`cp -a` of the built base, one constant edited by `sed`, the files that inline it touched, `ant jar`,
constant confirmed with `javap -constants`): `v-num64`, `v-num1m` (NumericValuesWriter BLOCK_SIZE / MONOTONIC_BLOCK_SIZE = 64 / 64 and 2^20 / 2^20), `v-post32`, `v-post512`
(PostingsWriter.BLOCK_SIZE), `v-max1m`, `v-max8k`, `v-max28` (AbstractBlockPackedWriter.MAX_BLOCK_SIZE = 2^20, 2^13, 2^28), `v-tpb124` (TokenTreeBuilder.TOKENS_PER_BLOCK = 124);
the sed patches are in the run1 excerpts (`build-patches/`). Shared with the three sibling cases written in the same session: the builds, the seed data directories
(`~/s4-b34/seeds`), and the cluster engine `cluster-run.py` (identical file in the four folders; the case is taken from the folder name). Full logs on the node under
`~/s4-b34/logs/<key>/` (outside the repo).

| File | Tier | What it does |
|---|---|---|
| `BlockSizeBoundProbe.java` | unit (B2) | package `...sai.disk.v1.bitpack`; modes `writer` (construct, add 3 x bs capped at 2^22, finish), `check` (`SAICodecUtils.checkBlockSize` alone), `reader` (BlockPackedReader / MonotonicBlockPackedReader on a forged `NumericValuesMeta`, null FileHandle). MIN / MAX read reflectively from the loaded class. |
| `unit-run.sh [label]` | unit | arms stock (`base`, -Xmx3g) and patched (`v-max28`, -Xmx6g), 3 repetitions, 9 writer sizes x 2 kinds, 7 check values, 5 reader forgeries x 2 kinds; upstream `SAICodecUtilsTest`. |
| `analyze_unit.py <dir> [out]` | unit | readings and `EXPECTED` lines. |
| `cluster-run.py`, `ledger-bitpack.btm`, `Sampler.java`, `analyze_cluster.py` | cluster | arms S-750k, S-1500k, S-3M (stock), M1m-3M (`v-max1m`), M8k-750k (`v-max8k`), ctl-seg16. |
| `selfcheck.py <unit dir> [<cluster root>]` | both | independent re-parse. |
Instrument checks before run 1 (not readings, disclosed in results section 2): unit probe shakedown (one cell); cluster engine shakedown on a 20,000-row seed with the
`v-num64` build (SAI) and the `v-tpb124` build (SASI), logs `~/s4-b34/logs/shakedown/`.
