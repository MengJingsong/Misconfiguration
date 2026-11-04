# Harness — SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS

Stage-4 instruments for the long-path case
[`SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS`](../../../stage3-ai-deep-read/cases/SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS--guided.md)
(§9, amended 2026-10-15). Written 2026-10-15 after §9a was frozen (`1088e8cd…`). Results:
[`../../results/SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS.md`](../../results/SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS--guided.md).

| File | What it is |
|---|---|
| `MaterializedKeysLimitTest.java` | Unit tier U1–U5 (`CQLTester`, package `org.apache.cassandra.index.sai.cql`); STAGE4 check lines to `-Dstage4.out` |
| `unit-trace.btm` | Unit rules: the `mat-trace.btm` lines handed to the test's recorder, and the list at the refusal to `measure()` (U2) |
| `unit-run.sh` | `unit-run.sh [upstream\|harness\|all]`, output `~/stage4-logs/mmk/$MMK_RUN/unit/` |
| `mat-trace.btm` | Node rules (1)–(7) of 9c: `limit=`, `mat refuse`, `mat exit`, `ann`, `hybrid`, `pairs`, `processed= reads=` to `-Dstage4.mat.out` |
| `hold.btm`, `Mmk.java` | Holds at points a (refusal), b (allowed list), c (after the top-k loop), gated by `/tmp/mmk-hold-<p>`; `Mmk` is the gate, on the boot class path |
| `make-node-yaml.sh` | The node's own `CASSANDRA_CONF` and directories under `~/stage4-mmk` with 9b's timeouts |
| `histo.sh` | `jcmd GC.class_histogram` (full GC) and the five classes of §7 |
| `mmkdata.py`, `driver.py` | Seeds and rows of `ks.t` and `ks.far` (by rank); the bundled cqlsh driver |
| `load.py`, `query.py` | Schema and load (once); one or *Q* hybrid / ANN-only queries, rows checked against *M*, `--trace` events |
| `Jmx.java` | Read-only JMX (copied from the `native_transport_receive_queue_capacity` harness): `TotalPartitionReads` side reading |
| `cluster-run.py` | `load`, `value <L>`, `down`; `EXPECTED:` lines in `summary.txt`; the node is stopped on any exit |

**Instrument checks (2026-10-15).** `TestScript` type-checks `mat-trace.btm` and `hold.btm` against the built classes with no error
(after `Mmk` replaced a `new` expression). Unit shakedown 1 found two defects (the second Byteman agent of `SAITester`; the
parameterized upstream test), fixed; unit shakedown 2: 83/83 checks, every line kind recorded (`mat refuse` 13, `mat exit` 24,
`ann` 13, `hybrid` 11, `pairs` 12, `processed=`/`reads=` 24). Shakedowns are not readings.

```bash
MMK_RUN=run1 ./unit-run.sh all
MMK_RUN=run1 ./cluster-run.py load
for v in 1000 4000 16000 64000 0 2147483647; do MMK_RUN=run1 ./cluster-run.py value $v; done
```
