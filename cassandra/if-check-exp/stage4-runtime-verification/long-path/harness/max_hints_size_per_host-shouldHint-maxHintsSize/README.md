# Harness — max_hints_size_per_host-shouldHint-maxHintsSize

Stage-4 harness for the case's §9 (frozen §9 hash `cf5c0601…`, §9a `c91d82d6…`, see the results file
[§1](../../results/max_hints_size_per_host-shouldHint-maxHintsSize.md)). Written 2026-10-14 by the long-path AI session,
after the step-0 audit. Run from a copy on the node, `~/stage4-harness-run/mhs/`; the run script logs the harness `md5sum`.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `ShouldHintSizeTest.java` | unit | **Package `org.apache.cassandra.hints`** (9c said `service`; `Hint.Serializer` and `HintsBuffer.ENTRY_OVERHEAD_SIZE` are package-private, and `StorageProxy` is public); copy into `test/unit/org/apache/cassandra/hints/`. Real hints through `HintsService.instance.write()`, flushed with `flushAndFsyncBlockingly()`, fake dead endpoints with host ids as in `StorageProxyTest.shouldHintTest()`, one endpoint per step. Steps 1, 2, 4 (limit 0 with 2 MiB on disk → `true`; 1 MiB → `false`; 0 again → `true`), 3 (the operand filled to exactly 1,048,576 B → `true`; limit 1,048,575 B through the raw config → `false`; one more hint → `false`), 5 (after every flush the operand equals the files' `length()`), 6 (hints buffered past the limit do not move the operand or the verdict until the flush). Prints `STAGE4 check <name> expected=… actual=… ok\|MISMATCH`; fails at the end on any mismatch. | `javac` against the clone; `unit-run.sh instrument` |
| `unit-run.sh [upstream\|harness\|instrument\|all]` | unit | Upstream `StorageProxyTest`; the harness test; `instrument` runs it with `should-hint.btm`. Output `~/stage4-logs/mhs/unit[-instrument]/`. | — |
| `should-hint.btm` | both | Byteman, observation only: `decide ep= result= checked= limit= ms=` at the exit of `shouldHint(Replica, boolean)`, with `checked`/`limit` captured after the check's own `getTotalHintsSize()` call (`-1` when the guard skipped it); `site send ep= result= key= ms=` at the primary decision point; `flush host= size= ms=` at each `HintsWriter.Session.close()`; `roll host= ms=` at `HintsStore.closeWriter()`. | `TestScript`: no errors; the instrument run; `Submit -l` on N1 |
| `write-load.py` | cluster | The writer: bundled driver, protocol 5, whitelist N1, CL `ONE`, `INSERT INTO ks.t (pk, v)` with a fresh `pk` and 5,120 random bytes per row, 200 rows/s, ≤ 32 in flight; logs every `pk` and outcome; `count <host>` reads every `pk` at `ONE`. Also `probe`, `schema`. | the shakedown |
| `Jmx.java` | cluster | JMX client on 127.0.0.1: `get`, `setint` with read-back, `query <pattern> <attr>`. | the shakedown |
| `make-node-yaml.sh <N1\|N2\|N3>` | cluster | Builds `~/stage4-mhs/<node>/conf` (loopback address, JMX port 7102–7104, one evenly spaced Murmur3 token, directories, `max_hint_window: 24h`, `hints_flush_period: 1000ms`). | the yaml tail is echoed into the log |
| `cluster-run.py run\|down` | cluster | One lifetime (9e as amended): wipe, ring, schema, control, N3 down, 16 · 64 · 256 MiB (A until the first refusal for N3, B 90 s), N2 down, 64 MiB two-host arm, `0` for 600 s, the read-back (throttle 0, drain, each host read alone), every node stopped. A 1 s sampler of per-host `.hints` bytes (`du.csv`). `EXPECTED:` lines in `summary.txt`; `arms.csv`, `counters.csv`, `phases.csv`, `keys/<phase>.csv`, `readback/`, a copy of N1's trace. Stops on a failed set-up or instrument check, stopping every node. `MHS_VALUES`, `MHS_TWO`, `MHS_B`, `MHS_CTRL`, `MHS_DEFAULT_S`, `MHS_LOGS` override the run-1 settings for a shakedown. | the shakedown (`~/stage4-logs/mhs/shakedown*`) |

Run order:

```bash
H=~/stage4-harness-run/mhs
$H/unit-run.sh all
$H/cluster-run.py run      # about 30 min; read ~/stage4-logs/mhs/run1/summary.txt
```
