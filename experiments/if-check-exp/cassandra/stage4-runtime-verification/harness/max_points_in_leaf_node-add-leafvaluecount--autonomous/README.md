# Harness — max_points_in_leaf_node-add-leafvaluecount--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 `b08bf27e…`, see the results file). Written 2026-10-28 on `pc32`. Run copy `~/s4-b34` (`copy-source.sh` of
`cassandra/cassandra-5.0.9` at repository commit `b68711e5`, `ant build-test`); cluster variants `~/s4-b34-vA/vB/vC` (`make-variants.sh`).
**Trap (found while building the variants):** the node runs from `build/apache-cassandra-5.0.9-SNAPSHOT.jar` (`bin/cassandra.in.sh`), not from `build/classes/main`, so recompiled
classes and the Byteman helper `stage4.Alloc` must be put into the jar (`jar uf`, done by `make-variants.sh`); the constant is also inlined into `NumericIndexWriter`, so both classes are recompiled.

| File | Tier | What it does |
|---|---|---|
| `LeafProbe.java` | unit (B2) | package `…v1.bbtree`; compiled by `unit-run.sh` into `<copy>/build/probe`. `cell M N B`: `NumericIndexWriter(M, B).writeCompleteSegment` over N sorted B-byte terms (warm-up discarded), prints `CELL` (leaf count, component lengths, thread-allocated bytes), `LEAFPOST` (heap retained by the private `LeafCallback`) and `SCRATCH` (heap retained by a reflectively built `LeafWriter`). `reject`, `alloc`: controls. |
| `unit-run.sh <copy> <out> [full\|check]` | unit | one JVM per cell (`-Xmx3g`, SerialGC): M in 16/128/1024/8192/65536 x N in 1e5/1e6/4e6 (B=4), B=16 at N=1e6, 2 more repeats of (1024, 1e6), N=0 for M in 16/1024/65536, rejects, `new long[k]` control. |
| `make-variants.sh <copy>` | cluster | `cp -a` variants A (128), B (1024), C (16384): edits line 96 in the copy's `src/`, recompiles the two classes, updates the copy's jar, adds `stage4.Alloc`. |
| `Alloc.java`, `alloc.btm` | cluster | Byteman observation: `WCS_ENTER`/`WCS_EXIT` per `NumericIndexWriter.writeCompleteSegment` with thread-allocated bytes and the returned component attributes. |
| `profile-t.yaml`, `Jmx.java`, `nodelib.py` | cluster | stress profile (`ks.t (id bigint, v int)`), JMX poller (from the `max_region_size` harness), node helper (own conf, loopback address and JMX port per slot, GC log, heap sampler). |
| `cluster-run.py <label> <A\|B\|C> <rows> <buffer MiB> <slot>` | cluster | one node: create table and SAI index, `cassandra-stress user`, `nodetool flush`, `rebuild_index`; samplers; `readings.txt`. The SegmentBufferSpaceUsedBytes JMX poll was added while the chain was running (runs B2, B8a, A2 have no `segbuf.csv`). |
| `chain.sh <slot>` | cluster | the nine runs: B2, B8a, A2, A8, C2, C8, B8b, B8c, B8ctl16 (16 MiB). |
| `analyze_cluster.py`, `selfcheck.py` | both | independent re-parse of the raw files against the frozen predictions; PASS/FAIL/NOTE. |
