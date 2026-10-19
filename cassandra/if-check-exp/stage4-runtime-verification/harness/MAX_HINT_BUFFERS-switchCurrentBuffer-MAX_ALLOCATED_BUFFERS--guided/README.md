# Harness — MAX_HINT_BUFFERS

| File | What it is | Where it goes |
|---|---|---|
| `HintsPoolCeilingTest.java` | Unit test for the case's unit tier (case §9e). Not upstream. Package `org.apache.cassandra.hints`, because the pool is package-private. | `test/unit/org/apache/cassandra/hints/HintsPoolCeilingTest.java` in a local clone, never the shared `cassandra-src` |
| `hints-pool.btm` | Byteman rules, observation only: the `created` and `waiting` trace lines (formats in the file and in case §9d). | Loaded at node start with `-javaagent`, or attached to the unit test with `-Dtest.jvm.args` |
| `hold-flush.btm` | Byteman rule, the trigger: delays every `HintsWriteExecutor$FlushBufferTask.run()` by `stage4.hold.ms` and logs a `hold` line. | Loaded and unloaded at run time with `Submit` / `Submit -u` (case §9e) |

**Test settings** (system properties, via `-Dtest.jvm.args`): `cassandra.MAX_HINT_BUFFERS` (*n*, 2 or more),
`stage4.hints.bufferSize` (bytes, default 1 MiB), `stage4.unit.out` (optional file that also receives the
`STAGE4` lines). Commands are in case §9c and §9e.

**What the test does.** It drives a `HintsBufferPool` of real direct buffers until one writer waits at the
check, then asserts: the pool holds exactly *n* buffers, the JVM's direct `Count` is up by *n* and
`MemoryUsed` by `n × bufferSize`, nothing changes over 2 s, recycling one buffer releases the writer without
a new buffer, and every hint written is found in exactly one buffer.

**Two things the instrument check taught (2026-09-30, results §3).**

- The baseline must follow a **writer warm-up**. The first `Mutation.serializedSize()` on a thread creates a
  128-byte direct scratch buffer (`Mutation.java:453`), which would otherwise show as `Count` +1 and
  `MemoryUsed` +128 inside the deltas. The test warms the writer thread up, settles with a GC, then takes the
  baseline.
- The same scratch buffer exists on every hint-writing thread, so in the cluster tier `Count` is reported,
  not asserted.

**Checked 2026-09-30 on node0** (`pc66`, JDK 11.0.32, Byteman 4.0.20 from the build's own `build/lib/jars/`),
against the `cassandra-5.0.9` build:

| Check | Result |
|---|---|
| Byteman `TestScript` on both `.btm` files | no errors |
| `HintsPoolCeilingTest` at *n* = 3, 1 MiB buffers, with `hints-pool.btm` attached | passed; trace has `created=1,2,3` (each `max=3`) and `waiting` lines |
| `hold-flush.btm`, functional | passed 2026-09-30 on node0 with node 2 on `pc80` (results §1.2, `instrument-check/hold-check.sh`): the held flush is seen in a thread dump, and the unload releases it |

These check the instruments, not the case; they are not stage-4 readings.
