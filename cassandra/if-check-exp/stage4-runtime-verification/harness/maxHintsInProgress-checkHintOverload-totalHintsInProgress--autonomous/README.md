# Harness — maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 `af8d24c2…`, see the results file
[§1](../../results/maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous.md)). Written 2026-10-21 after the
step-0 audit, on `pc07` (`node0.jason92-320876`), run from a copy `~/stage4-harness-run/mhp/` (md5 in
`~/stage4-logs/mhp/harness.md5`). Logs go to `~/stage4-logs/mhp/<run>/` on the node, outside the repo.

**Two builds, two clones.** Original: `~/cassandra-mhp` (`cassandra-5.0.9`, `b5f2a54210`, `ant build-test`; no change under
`src/`). Positive control: `~/cassandra-mhp-patched`, made with `cp -a ~/cassandra-mhp ~/cassandra-mhp-patched`, then exactly
[`hintsInProgress-LoadingCache.diff`](hintsInProgress-LoadingCache.diff) (B2a item 5: the per-destination counter container
becomes a Guava `LoadingCache`, and `getHintsInProgressFor` calls `get` instead of `load`), then `ant jar build-test`
(`BUILD SUCCESSFUL`, `~/stage4-logs/mhp/build-patched.log`). Both runners check the build they use with `javap`: the field
type of `StorageProxy.hintsInProgress` is `CacheLoader` in the original jar and classes and `LoadingCache` in the patched ones.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `hintsInProgress-LoadingCache.diff` | both | The positive-control patch, `git diff` of the patched clone against the tag. | `javap` of both jars and both `build/classes/main` |
| `HintOverloadCheckTest.java` | unit (B2) | B2e step 1's class with audit amendment R2 (the mutation built through `PartitionUpdate.SimpleBuilder`, `HintsService` imported, one `INFO` line). Package `org.apache.cassandra.service` (copied into the clone's `test/unit/…/service/`). L ∈ {1, 128, 1000, MAX}; MutationStage blocked by `getConcurrentWriters()` latch tasks; 2000 × (`checkHintOverload` by reflection, then `submitHint`) with a 64 KiB blob; `RESULT` and `DRAINED` lines. The same file in both builds. | `javac` against the original clone (no error) |
| `unit-run.sh <orig\|fixed> [run]` | unit | `javap` field check, copies the test, `ant testsome`, keeps `ant.log` and the JUnit XML, writes `lines.txt` and `summary.txt`. The test JVM prints `System.out` through a logger that logs each piece of a `printf` as its own line (results §3, H1): the script joins the pieces back into lines. | run 1 and a repeat (`run1-rep2`) |
| `jmx.jsh` | cluster (B3d) | The filed jshell JMX script, unchanged: `MODE=set` sets `MaxHintsInProgress` and reads it back; `MODE=sample` writes `ms,limit,hintsInProgress,mutationPending,unavailables,heapUsed` every 200 ms until `<OUT>.stop` exists. | shakedown1/2 |
| `Jmx.java` | cluster | Copied from the `WRITE_BUFFER_SIZE` harness: `get` for the before/after `TotalHints`, write `Unavailables` and `HintsInProgress`; `poll` for G1 Old Gen `CollectionUsage` and `Usage` every 1 s (results §3, D1: `jstat` cannot attach to a node run with `-XX:+PerfDisableSharedMem`). | shakedown2 |
| `cluster-run.py <run…> \| all \| analyze \| down` | cluster (B3e) | Per run O-1 · O-128 · O-MAX · F-1 · F-MAX: fresh node copies `~/stage4-mhp/<RUN>/<run>/{n1,n2}` of the build (rsync without `.git`, `data/`, `logs/`, `build/test`), B3a's yaml lines (`concurrent_writes: 2`, the cluster name, addresses, seed), JMX 7221/7222 (R3); n1 then n2, two `UN`; schema by the stress command with n=1000; n2 killed, `DN`; L set and read back; samplers; stress n=1,000,000 with `-errors ignore retries=0` (R4), 400 threads; 30 s; the log grep (R5: 0 expected), hint bytes, stress's totals, JMX before/after; both nodes killed by PID, the run's processes checked gone (R6), logs copied, node copies removed. `EXPECTED:` lines per B3f; `analyze` writes the cross-run relations X1–X8. | shakedown1 (O-1, F-1 at n=50,000), shakedown2 (O-1, the old-gen poll) |
| `selfcheck.py` | both | Independent re-parse of the raw run-1 files (copied to `results/<stem>/run1/` with its output). | — |

Run order (run 1):

```bash
H=~/stage4-harness-run/mhp
bash $H/unit-run.sh orig run1; bash $H/unit-run.sh fixed run1          # repeat: run1-rep2
MHP_RUN=run1 python3 $H/cluster-run.py all; MHP_RUN=run1 python3 $H/cluster-run.py analyze   # one background job, ~30 min
```

Addresses and ports (shared host, environment deviation): n1 = 127.0.0.21 (JMX 7221, seed, measured), n2 = 127.0.0.22
(JMX 7222). 127.0.0.23, 7223 and the Byteman ports 19221/19222 were reserved for this run and not used (no Byteman rule).
