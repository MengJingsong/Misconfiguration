# Harness — max_array_length-checkmaxleafnodecount-numleaves--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 `6482c2b5…`). Written 2026-10-28 on `pc32`. Run copy `~/s4-b34` (unit) and `~/s4-b34-vB` (cluster: the unmodified tree
plus `stage4.Alloc` in its jar, made by the sibling harness `max_points_in_leaf_node…/make-variants.sh`).

| File | Tier | What it does |
|---|---|---|
| `LeafCountProbe.java` | unit (B2) | package `…v1.bbtree`; `BlockBalancedTreeWriter(B, M).write` into a counting discarding `IndexOutput`; no-op `Callback` that forces GC and records retained heap at E/4, E/2, E-1 leaves; N = number or `L`, `L-1`, `L-5` with `L = floor(ArrayUtil.MAX_ARRAY_LENGTH / B) + 1`. Prints `PARAMS` and `RESULT`. |
| `unit-run.sh <copy> <out> [full\|check]` | unit | one JVM per run, `-Xmx12g`, SerialGC: A (B=24) and A' (B=16) at M=1024 N=50e6; B=1 MiB L-1/L x3, L-5; B=262144 and 4096 L-1/L; control B=24 M=1024 vs M=1 at N=1e6. |
| `Alloc.java`, `alloc.btm`, `Jmx.java`, `nodelib.py`, `analyze_cluster.py` | cluster | as in the sibling harness (analysis splits flush/rebuild windows and bytes_per_value 8/24). |
| `profile-t2.yaml` | cluster | `ks.t2 (id bigint, vb bigint, vd decimal)`. |
| `cluster-run.py <label> <rows> <buffer MiB> <slot>` | cluster | one node (4 GiB G1): table and both SAI indexes, autocompaction off, stress load, flush, `rebuild_index` of both; heap and `SegmentBufferSpaceUsedBytes` samplers; segment counts from `system_views.sai_sstable_index_segments`. |
| `chain.sh <slot>` | cluster | R5, R20a, R40, R20b, C32 (32 MiB). |
| `selfcheck.py` | both | independent re-parse against the frozen predictions. |
