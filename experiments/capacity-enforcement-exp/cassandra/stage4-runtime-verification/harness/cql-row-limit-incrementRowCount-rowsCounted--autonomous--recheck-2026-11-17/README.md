# Harness: cql-row-limit-incrementRowCount-rowsCounted--autonomous — recheck claim (2026-11-17)

Implements the case file's section "Stage-4 design for the recheck claim (2026-11-17)" (S1-S5). Not upstream code.
Node `pc75`, run directory `/mydata/s4/rowlim-rc/` (tree `tree/` = `cp -a /mydata/s4/cassandra-base`, node data `node/`,
driver `drv/`, logs `logs/{load,K,U,C}/`, harness copy `harness/`). Ports 7000, 7199 (JMX), 9042 on 127.0.0.1.
`Jmx.java` is copied unchanged from `../cql-row-limit-incrementRowCount-rowsCounted--autonomous/`.

| File | What it does |
|---|---|
| `setup.sh` | Copies the tree, unzips the bundled Python driver, copies this folder to `<run>/harness`, records versions and md5s (`logs/setup.log`). |
| `probes.btm` | Three Byteman rules (no listener): PR at exit of `ReadResponse$LocalDataResponse.build` (keyspace `ks`; logs serialized size and buffer capacity), PC at exit of `ResultSetBuilder.build()` (result of `ks` with >= 8 rows; logs row count), PA at exit of `LocalReadSizeTooLargeException.<init>`. Each writes a start line to `-Ds4rc.marker`, sleeps `-Ds4rc.pause_ms` (8000), writes an end line. |
| `rc-run.py` | `load` (no agent): 3 tables x 600 rows (16 KiB / 128 KiB / 1 MiB), flush, major compaction, `count(*)`. `life K` (instrument check), `life U` (shipped guardrails), `life C` (`read_thresholds_enabled: true`, `local_read_size_fail_threshold: 40MiB`). Every lifetime runs the node as `systemd-run --user --scope -p MemoryMax=12G -p MemorySwapMax=0 bin/cassandra -f` with `MAX_HEAP_SIZE=8G`, samples the scope's `memory.current` every 1 s, and the JMX allocation counter every 25 ms (`Jmx.java`). Per query: histogram B (`jcmd GC.class_histogram`, a full GC), 2 s, client query; for each probe start line a histogram; after the client, 2 s, histogram B2. A histogram is `inside` if it ended before the probe's end line. First-trigger checks exit 3. Stops the node (`nodetool drain`, SIGTERM) on every exit. |
| `client.py` | Driver 3.29.0, protocol 4, `schema_metadata_enabled=False`, `token_metadata_enabled=False`: `load`, and `q <table> <L|none> <fetch|none>` (unpaged, or first page only). |
| `analyze.py` | Medians per arm of H_R, H_C, H_A (histogram total minus B) and A; EXPECTED lines for R1-R5 of S6, the model bands, the refute and invalid checks, and the matched S7 row. |

**Instrument checks (not readings):**
1. Byteman `TestScript` type-checks all three rules against the built jars: `TestScript: no errors` (`run1/bmcheck.txt`).
2. Lifetime K (2026-11-17, after the freeze): L(32, 128 KiB) and P(128, 1 MiB) once each: both probes fired on each query (PR on `ReadStage-2`, PC on `Native-Transport-Requests-1`), every histogram ended inside its pause (histograms take about 0.4 to 1 s), the client got 32 and 128 rows, no ERROR, `oom_kill 0`.
3. Found while writing the harness: `bin/cassandra -f` writes no pidfile (only the background mode does), so `rc-run.py` finds the daemon by its command line; the load lifetime ran with the first version and its node was drained and stopped by hand (logged in the results file); `memory.events` is now read before the stop.
