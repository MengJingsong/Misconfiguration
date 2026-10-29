# Harness — tokens_per_block-add-pos--autonomous

Stage-4 harness for the autonomous case file `tokens_per_block-add-pos--autonomous` (frozen sha256 `ae30cf1d22af...`, see the results file [section 1](../../results/tokens_per_block-add-pos--autonomous.md)).
Written 2026-10-28 for `pc39` (JDK 11, Ant 1.10, 40 cores, 251 GiB). Builds: `~/s4-b34/base` (`copy-source.sh` copy of `cassandra/cassandra-5.0.9/` at repository
commit `b68711e5`, `ant build-test` then `ant jar`) and variant copies (`cp -a` of the built base, one constant edited by `sed`, the files that inline it touched, `ant jar`,
constant confirmed with `javap -constants`): `v-num64`, `v-num1m` (NumericValuesWriter BLOCK_SIZE / MONOTONIC_BLOCK_SIZE = 64 / 64 and 2^20 / 2^20), `v-post32`, `v-post512`
(PostingsWriter.BLOCK_SIZE), `v-max1m`, `v-max8k`, `v-max28` (AbstractBlockPackedWriter.MAX_BLOCK_SIZE = 2^20, 2^13, 2^28), `v-tpb124` (TokenTreeBuilder.TOKENS_PER_BLOCK = 124);
the sed patches are in the run1 excerpts (`build-patches/`). Shared with the three sibling cases written in the same session: the builds, the seed data directories
(`~/s4-b34/seeds`), and the cluster engine `cluster-run.py` (identical file in the four folders; the case is taken from the folder name). Full logs on the node under
`~/s4-b34/logs/<key>/` (outside the repo).

| File | Tier | What it does |
|---|---|---|
| `TokenTreeCapProbe.java` | unit (B2) | package `...sasi.disk`; `tree` mode: `DynamicTokenTreeBuilder` with N ascending tokens, tokenCount, numBlocks, serializedSize, written bytes, a walk of every level (max tokens per interior node / leaf), allocation and retained heap (median of 5 GCs); `ctl` mode: `OnDiskIndexBuilder.estimatedMemoryUse()` for M distinct terms. The constant is read reflectively from the loaded interface. |
| `unit-run.sh [label]` | unit | arms stock (`base`) and v124 (`v-tpb124`), N = 248, 249, 2480, 61504, 246016 (-Xmx512m), M = 1e3, 1e5, 1e6 (-Xmx2g), 3 repetitions; upstream `TokenTreeTest`. |
| `analyze_unit.py <dir> [out]` | unit | readings and `EXPECTED` lines. |
| `cluster-run.py`, `Sampler.java`, `analyze_cluster.py` | cluster | SASI (`sasi_indexes_enabled: true`, heap 1 GiB): seed `sasi.t (pk bigint, c text = 'q', u text unique hex)`; arms S-1M, S-500k, T124-1M, T124-500k, ctl-opt16; per arm `c_idx` (CONTAINS) then `u_idx` (PREFIX), directory watcher at 20 Hz for temp segment files. |
| `selfcheck.py <unit dir> [<cluster root>]` | both | independent re-parse. |
Instrument checks before run 1 (not readings, disclosed in results section 2): unit probe shakedown (one cell); cluster engine shakedown on a 20,000-row seed with the
`v-num64` build (SAI) and the `v-tpb124` build (SASI), logs `~/s4-b34/logs/shakedown/`.
