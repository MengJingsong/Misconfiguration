# Harness — DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE

Instruments for the case's §9 (stage 4), written 2026-10-15 after the step-0 audit froze §9a (`634e47fc…`). Results:
[`../../results/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE.md`](../../results/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md).
Copy the folder to the node (`~/stage4-harness-run/dob/`) and compare `md5sum` before a run. Unit tier in `~/cassandra-run3`,
cluster tier from `~/cassandra-run1` (both `b5f2a54`).

| File | What it is | Checked how |
|---|---|---|
| `DobRecycleTest.java` | Unit U1–U10 (package `org.apache.cassandra.io.util`): statics by reflection, one instance per thread, keep at *L* / replace at *L* + 1 with the direct-pool deltas, the grow policy, a parked vs a dead thread across GC, 8 threads, *L* = 64, `buffer(false)`, heap mode, and (with `-Dstage4.expect_init_failure=true`) the two invalid property values. Every probe on its own `FastThreadLocalThread`. | instrument run with the ledger attached |
| `unit-run.sh [instrument\|upstream\|harness\|all]` | One JVM per value (262,144 · 4,194,304 · 64 · default · onheap · the two invalid values); `instrument` attaches `dob-ledger.btm`. | — |
| `dob-ledger.btm` | Byteman ledger of every scratch buffer: `new`, `alloc`, `grow-free`, `close` (`cap pos limit L=`), `kept` (line 75), `replaced` (line 79), `closed`. | `TestScript: no errors`; the 9e step-0 known answer (`alloc 100050`, `grow-free 128`, `alloc 200100`, `grow-free 100050`, `close cap=200100`, `kept`, peak 300,150; `replaced cap=1048577` then `alloc size=128`) |
| `hold.btm` | Holds each `ks1` write 5 s at `CommitLog.add()` exit (after its scratch `close()`), writing `held tid= name=`. | `TestScript` |
| `ledger.py` | Replays the ledger: live bytes per instance, peaks, capacity after the last close, the total *R*. | the known answer above |
| `dob-writes.py` | Client, bundled Python driver, **protocol 4** (amendment (1)), *n* writes of *V* zero bytes sent at once. | `--probe` prints the protocol |
| `make-node-yaml.sh`, `Jmx.java` | The tag's yaml plus `write_request_timeout: 30000ms`, `native_transport_timeout: 30s`; `Jmx.java` from the `coordinator_read_size_fail_threshold` harness (direct pool `MemoryUsed`, `Count`). | — |
| `cluster-run.py <label> … \| report` | One fresh node start per label `L<value>-<batch>[-heap]` (9e): read-back, calibration (*P*), twin warm-up, idle 20 s, readings before / hold / after (/ persist), the batch's ledger analysis; `report` checks the staircase, the boundary pairs, the peaks across *L*, ×N, scenario C and arm H across labels. | shakedown (`~/stage4-logs/dob/shakedown1/`) |
