# Harness — max_recursive_key_length-addterm-term--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 `3e5aa37e…`). Written 2026-10-28 on `pc32`. Run copy `~/s4-b34`; node variant `~/s4-b34-vZ` (`make-variant.sh`).

| File | Tier | What it does |
|---|---|---|
| `TrieIndexProbe.java` | unit (B2) | package `org.apache.cassandra.index.sai.memory`; `term L N`: N distinct random ASCII terms of L bytes into a fresh `TrieMemoryIndex` (mock text index as in `TrieMemoryIndexTest`); sums `add()` returns, reads `sizeOnHeap`/`sizeOffHeap` of `data` by reflection, route counters when an overlay provides them; `guard T L…`: guardrail control. |
| `make-overlays.sh <copy>` | unit/cluster | builds `<copy>/build/overlay-{instr,z0,z1,zi0}`: a recompiled `TrieMemoryIndex.class` from a patched copy of the source (counters; constant 0; constant 100000; both). |
| `unit-run.sh <copy> <out> [full\|check]` | unit | one JVM per run (`-Xmx2g -Xss512k`): 6 L x 2 passes x builds stock/z0/z1/instr/zi0 x 3 repetitions, plus the guard control 3 times. |
| `make-variant.sh <copy>` | cluster | `cp -a` copy whose jar holds the `z0` overlay class (the node runs from the jar). |
| `cluster-run.py <label> <S\|Z> <heap\|off> <L> <rows> <slot> [guard]` | cluster | one node (2 GiB G1): table and SAI index, `cassandra-stress user` (v text, size fixed(L)), 60 s idle, then tablestats, JMX `MemtableIndexBytes`, `GC.run` + heap_info, RSS, oversize-term warnings. |
| `chain.sh <slot>` | cluster | the 15 runs of amendment C2. |
| `selfcheck.py`, `Jmx.java`, `nodelib.py` | both | independent re-parse; JMX query client; node helper. |
