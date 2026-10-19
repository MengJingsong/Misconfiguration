# Harness — memtable_heap_space

| File | What it is | Where it goes in the local clone |
|---|---|---|
| `HeapPoolTest.java` | Unit test for the case's unit tier (§9c). Not upstream. | `test/unit/org/apache/cassandra/utils/memory/HeapPoolTest.java` |
| `escape-hatch.btm` | Byteman rule for the cluster tier (§9d, bypass volume). Logs one line per allocation forced past the limit. | Not copied: loaded with `-javaagent` at node start (§9e). |

**Origin.** Restored verbatim from the Java block in
`git show e90423c^:cassandra/if-check-exp/memtable/memtable_heap_space-tryAllocate-limit.md`
(lines 245–403 of that file). It is the test run on 2026-09-16 on pc80.
The untracked copy in the shared `cassandra-src` clone differs from it in one
comment line only (an older case-file name); the code is identical.

**`escape-hatch.btm` — checked 2026-09-29, before any cluster run,** against
the `cassandra-5.0.9` build (Byteman 4.0.20, from the build's own
`build/lib/jars/`):

| Check | Result |
|---|---|
| Byteman `TestScript` (parse and type-check against the compiled classes) | no errors |
| Known answer: `HeapPoolTest` run with the rule attached (`-Dtest.jvm.args`) | 2 tests passed; exactly one line, `forced=1 limit=100` — the escape-hatch test forces 1 byte, the blocking test forces none |
| Injection report: `Submit -l` with `listener:true`, once the class is initialized | lists `trigger method: …MemtableAllocator$SubAllocator.allocated(long)` |

These check the instrument, not the case; they are not stage-4 readings.
