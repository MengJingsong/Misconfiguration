# Harness — cdc_total_space

| File | What it is | Where it goes |
|---|---|---|
| `CdcTotalSpaceCeilingTest.java` | Unit test for the case's unit tier (case §9e). Not upstream. Package `org.apache.cassandra.db.commitlog`, because it uses package-private `awaitManagementTasksCompletion()` and `allocatingFrom()`. | `test/unit/org/apache/cassandra/db/commitlog/CdcTotalSpaceCeilingTest.java` in a local clone, never the shared `cassandra-src` |
| `cdc-verdict.btm` | Byteman rules, observation only: the creation trace (`pre`, `post`), the non-blocking deletion pass (`deleteOld`) and a rate-limited `reject` line (formats in the file and in case §9d). | Loaded at node start with `-javaagent`, or attached to the unit test with `-Dtest.jvm.args` |
| `cdc-sampler.py` | Lists `cdc_raw` 20 times a second: `.csv` (links, apparent and allocated bytes, index files, gap), `.events` (a line per file that appears or disappears), `.summary`. | Run in the background on the node, from node start to stop |
| `cdc-consumer.sh` | Emulates a CDC consumer: deletes the link and index of every segment whose index says `COMPLETED`. `once` or `loop <seconds>`. | Release step and consumer control (case §9e) |
| `cdc-analyze.py` | Reads a creation trace and a link timeline: checks the verdict formula `FORBIDDEN ⇔ blocking and S + pre.sip > A` for every creation, sets the counter against the files that existed just before each creation (a stale counter), names the creations that made a link beyond *k*, and (cluster) prints the links at each phase, the plateau and the peak. | Run on each run's folder (the cluster runner does) |
| `cdc-rows.yaml`, `plain-rows.yaml` | `cassandra-stress` user profiles: 1 MiB rows into `stage4cdc.cdc_rows` (`WITH cdc = true`), 64 KiB rows into `stage4cdc.plain_rows` (`WITH cdc = false`, the control). | `cassandra-stress user profile=<file>` (case §9c) |

**Test settings** (system properties, via `-Dtest.jvm.args`): `stage4.cdc.totalSpaceMiB` (*A*, required),
`stage4.cdc.segmentMiB` (*S*, default 32: the unit yaml has 5 MiB, the node default is 32),
`stage4.cdc.mode` (`blocking` or `nonblocking`), `stage4.unit.out` (a file that also receives the `STAGE4` lines).
Commands are in case §9c and §9e; `results/cdc_total_space-processNewSegment-allowance/run1/unit-run.sh` runs the matrix.

**What the test does.** Starts the commit log afresh with the chosen *S* and *A*, creates a CDC and a non-CDC table, reads the idle
floor, writes 1 MiB CDC rows until the first `CDCWriteException`, and at that point reads the files in `cdc_raw`, the counter (by
reflection and from the message) and the segment's state. It then tries ten more writes, writes a non-CDC row, deletes the links as a
consumer would and waits for a CDC write to be accepted again. The non-blocking variant writes until at least *k* + 10 links have
existed and checks that none was rejected and that *L* stayed at or under *k* + 1. **A check that does not hold is recorded
(`check MISMATCH`) and the test goes on**, failing at the end; every link that appears or disappears is logged (`linkEvent`,
`linkCount`) so `cdc-analyze.py` can set the counter against the files.

**Checked 2026-10-01 on `pc80`** (NODE1, JDK 11.0.32, Byteman 4.0.20 from the build's own `build/lib/jars/`), against the
`cassandra-5.0.9` build:

| Check | Result |
|---|---|
| Byteman `TestScript` on `cdc-verdict.btm` | four rules, no errors |
| `cdc-sampler.py` and `cdc-consumer.sh`, known-answer test | passed (results §1.2) |
| `CdcTotalSpaceCeilingTest` at *A* = 144, 16 (blocking) and 80 (non-blocking), with the trace attached | ran every step; at *A* = 144 it recorded a mismatch (5 links, a stale counter, see results §1.2) |
| `cdc-analyze.py` on those traces | verdict formula held for every creation |

These check the instruments, not the case; they are not stage-4 readings.

**Two things the instrument checks taught (results §3).** The test must record a mismatch and go on, or the steps after it lose their
readings. And the analysis must take the peak from per-tick counts, not from add and remove events, which share a tick.
