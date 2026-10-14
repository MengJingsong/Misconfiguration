# Harness — memtable_offheap_space

Written 2026-10-13 (stage-4 step 1) for the case's §9 as amended by the step-0 audit (§9 hash `cebea151…`).

| File | What it is | Where it goes |
|---|---|---|
| `NativePoolTest.java` | Unit tier, §9e step 2: a `NativePool` with a 100 B off-heap limit; fill, park (thread state + timed get), counter unchanged, release wakes, forced through when blocking, discard. Writes `STAGE4` lines to `-Dstage4.out`. | `test/unit/org/apache/cassandra/utils/memory/` in the run clone |
| `unit-run.sh` | Runs upstream `NativeAllocatorTest`, then `NativePoolTest`; output `~/stage4-logs/mos/unit/`. | run from the harness copy |
| `escape-hatch.btm` | Byteman: one line per allocation forced past the limit (`MemtableAllocator$SubAllocator.allocated(long)`). Copied from the `memtable_heap_space` harness; comments only differ. Keep lines whose `limit` is the off-heap knob in bytes. | `-javaagent` at node start |
| `region-ledger.btm` | Byteman: one line per `NativeAllocator$Region` built (= one JNA `malloc`), per region freed (race stash overflow, discard), and at each `setDiscarded()` entry with the memtable's `owns`. NMT cannot see this memory (`MemoryUtil.allocate()` is `Native.malloc()`). | `-javaagent`, second `script:` |
| `ledger.py` | Reads the ledger: `L_idle`, `max L` in a window, per-discard `P_m`, `A_m` and the 9a bound. | run on the ledger file |
| `cluster-run.py` | `instrument` (the unit test with both rules; known answer `forced=10 limit=100`, one 8,192 B region, `owns=110`), `value <label> <arm>` (one node run: config, start, idle, A, B, C, stop, trace, ledger, `RssAnon` sampler), `down`. | run from the harness copy on the node |

Node copy: `~/stage4-harness-run/mos/` (compare `md5sum` with the repo before run 1). Logs: `~/stage4-logs/mos/<run>/`.
