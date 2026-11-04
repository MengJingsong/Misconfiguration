# Harness - max-unsigned-short-prepare-boundTerms--autonomous

Frozen text in `frozen-prediction.txt` (B2f-B2g and B3f-B3g after the audit amendments of 2026-10-26; sha256 `ce36eedc...`). Written on pc07 (node0); trees `~/s4-b9-bt/u` (unit, `ant build-test`) and `~/s4-b9-bt/c` (node, `ant jar`), both `copy-source.sh` copies. Logs: `~/s4-b9-bt-logs/<run>/`. Port slot 3: 127.0.3.1, JMX 7130, native 9042 on that address; node data on tmpfs `/dev/shm/s4-b9-bt/node`.

| File | Tier | What it does |
|---|---|---|
| `PrepareMarkerLimitTest.java` | unit (B2) | CQLTester subclass: calibration of M = 1, 10, 1000, 65535 (weight, bind count, or size-gate rejection), boundary M = 65536, then load loops for M = 10, 1000, 65535 up to offered weight 4 x cap; `STAGE4 check` lines (OK / MISMATCH) |
| `unit-run.sh [run] [sizes]` | unit | one `ant testsome` JVM per cache size (default 10 1 100 MiB), yaml copy per size; stops if a JVM's boundary check fails; `summary.txt` |
| `cluster-run.py <run> <MiB> <M>` / `down` | cluster (B3) | one node lifetime per (cache size, M): knob read-back, schema, baseline histogram, repeat control, 65536 first-trigger check (M = 65535), load with 5 s samples and stop rule, 70 s settle, final histogram, log scan; `summary.txt` with EXPECTED lines |
| `chain.sh <run> [first]` | cluster | the nine arms in sequence, then `down`; `first` runs only the 10 MiB / 65535 arm |
| `prep-load.py` | cluster | bundled Python driver client (protocol 4): `setup`, `load`, `boundary`, `dup`, `rows` |
| `drv.py`, `Jmx.java` | cluster | driver loader and JMX reader, copied from the `prepared_statements_cache_size` harness |
| `selfcheck.py <logs>/run1` | both | re-parses the raw outputs and recomputes every number the results file cites |

Instrument checks (not readings), run `shake1`: the unit class at 1 MiB (15 checks OK; compile, the 65536 message, the size gate, one-entry-per-prepare) and the cluster arm 10 MiB / 65535 (knob read-back, schema, 65536 rejection through the driver, load, stop rule, histogram, log scan, clean stop).
