# Harness — write_buffer_size-append-hint--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 `fe0f472f…`, see the results file
[§1](../../results/write_buffer_size-append-hint--autonomous.md)). Written 2026-10-28 on `pc29`, run from a `copy-source.sh` copy `~/s4-hwb/base`
(`cassandra-5.0.9`, `ant build-test`) and three variant copies `~/s4-hwb/var-*` (`cp -a` of the built base, the line
`HintsWriteExecutor.java:50` edited by `sed`, `ant jar`, constant confirmed with `javap -constants`). Logs go to
`~/s4-hwb/logs/write_buffer_size-append-hint--autonomous/<run>/` on the node, outside the repo. The two sibling cases (hints_write_buffer_size-append-hint_remaining and
write_buffer_size-append-hint) share the same constant; their harnesses are copies of one design with different cell lists.

| File | Tier | What it does |
|---|---|---|
| `WriteBufferProbeTest.java` | unit (B2) | package `org.apache.cassandra.hints`; `unit-run.sh` copies it into the copy's `test/unit/…/hints/`. Opens a counting subclass of `HintsWriter` (same steps as `HintsWriter.create`), passes its own direct aggregation buffer of N = 64 KiB · 256 KiB · 1 MiB to `newSession`, appends opaque direct entries of H + 12 bytes, compares every append with a model of `Session.append`, checks the file byte for byte, and runs the controls. `STAGE4 append/case/check/info` lines. |
| `unit-run.sh [run]` | unit | runs the probe with `ant testsome` (GC log), then upstream `HintsReaderTest`; `summary.txt`. `--remove` deletes the copied test. |
| `hwb.btm` | cluster | Byteman, observation only, on node A: slab creations, writers waiting at the pool cap, sampled `Session.append(ByteBuffer)` (entry vs buffer capacity), counters of appends / oversize appends / channel writes / direct channel writes / refusals, printed at each `Session.close`. |
| `client.py`, `Jmx.java` | cluster | bundled Python driver (protocol 4, CL ONE, whitelist A), and a JMX client (get / query / poll), both from the earlier `WRITE_BUFFER_SIZE-append-remaining` harness. |
| `make-node-yaml.sh` | cluster (B3a) | per-node conf under `~/s4-hwb/n-hwb2/<A\|B>/`: the tag's yaml plus B3a's lines and the arm's overrides; loopback A = 127.0.0.2 (JMX 7102), B = 127.0.0.3 (JMX 7103); `MaxDirectMemorySize=1g`, NMT. |
| `cluster-run.py main\|analyze\|down\|list` | cluster (B3e) | builds 64 KiB · 256 KiB · 1 MiB x payloads 1 KiB · 400 KiB x 2 reps (order shuffled, seed 20261028) plus the controls; A restarted on the arm's build before each arm, hints cleared, 1-s sampler (direct pool, heap, `TotalHints`, RSS, `.hints` files), baseline, 1 GiB of values, settle of three flush periods, NMT before/after; `EXPECTED:` lines in `summary.txt`; `arms.json`; resumable. |
| `selfcheck.py <run1 dir>` | both | independent re-parse of the raw run-1 files; copied to `results/write_buffer_size-append-hint--autonomous/run1/` with its output. |

Instrument checks (not readings): unit shakedown1/2 (known-answer: 349 and 333 checks, defects fixed in the test), cluster shakedown1
(`HWB_BYTES=64 MiB`, 4 arms, case 1 only). Run order: `~/s4-hwb/chain.sh` (unit, then cluster, one background job).
