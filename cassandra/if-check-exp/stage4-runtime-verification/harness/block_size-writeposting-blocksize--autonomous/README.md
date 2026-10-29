# Harness — block_size-writeposting-blocksize--autonomous

Stage-4 harness for the autonomous case file `block_size-writeposting-blocksize--autonomous` (frozen sha256 `e560c7fb2407...`, see the results file [section 1](../../results/block_size-writeposting-blocksize--autonomous.md)).
Written 2026-10-28 for `pc39` (JDK 11, Ant 1.10, 40 cores, 251 GiB). Builds: `~/s4-b34/base` (`copy-source.sh` copy of `cassandra/cassandra-5.0.9/` at repository
commit `b68711e5`, `ant build-test` then `ant jar`) and variant copies (`cp -a` of the built base, one constant edited by `sed`, the files that inline it touched, `ant jar`,
constant confirmed with `javap -constants`): `v-num64`, `v-num1m` (NumericValuesWriter BLOCK_SIZE / MONOTONIC_BLOCK_SIZE = 64 / 64 and 2^20 / 2^20), `v-post32`, `v-post512`
(PostingsWriter.BLOCK_SIZE), `v-max1m`, `v-max8k`, `v-max28` (AbstractBlockPackedWriter.MAX_BLOCK_SIZE = 2^20, 2^13, 2^28), `v-tpb124` (TokenTreeBuilder.TOKENS_PER_BLOCK = 124);
the sed patches are in the run1 excerpts (`build-patches/`). Shared with the three sibling cases written in the same session: the builds, the seed data directories
(`~/s4-b34/seeds`), and the cluster engine `cluster-run.py` (identical file in the four folders; the case is taken from the folder name). Full logs on the node under
`~/s4-b34/logs/<key>/` (outside the repo).

| File | Tier | What it does |
|---|---|---|
| `PostingsBlockProbe.java` | unit (B2) | package `...sai.disk.v1.postings`; real `IndexOutputWriter` on local disk, `PostingsWriter(IndexOutputWriter, int)` through its private constructor by reflection, lists of N ascending postings with a fixed stride; thread-allocated bytes, returned summary offsets (data bytes), file length, `[J` / `[B` histogram rows. |
| `unit-run.sh [label]` | unit | bs 16 / 128 / 1024 x N 1,000 / 100,000 / 1,000,000 (stride 3), M = 1,000 lists of 50, wide-stride control; two repetitions; upstream `PostingsTest` as a known answer. |
| `analyze_unit.py <dir> [out]` | unit | readings and `EXPECTED` lines: the block model of B5.2, retained heap window, linearity, control. |
| `cluster-run.py`, `ledger-postings.btm`, `Sampler.java`, `analyze_cluster.py` | cluster | arms P128-3M, P32-3M, P512-3M, P128-750k, P128b-3M (noise), ctl-seg16; ledger = PostingsWriter construction with `deltaBuffer.length`. |
| `selfcheck.py <unit dir> [<cluster root>]` | both | independent re-parse. |
Instrument checks before run 1 (not readings, disclosed in results section 2): unit probe shakedown (one cell); cluster engine shakedown on a 20,000-row seed with the
`v-num64` build (SAI) and the `v-tpb124` build (SASI), logs `~/s4-b34/logs/shakedown/`.
