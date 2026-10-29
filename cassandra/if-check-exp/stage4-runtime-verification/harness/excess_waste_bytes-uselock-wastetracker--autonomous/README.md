# Harness: the EXCESS_WASTE_* cases (AtomicBTreePartition), stage 4

Written 2026-10-28 on node pc39 (run copy `~/s4-ew` from `copy-source.sh`, `ant build-test`; patched class directories `~/s4-ew-var/<variant>/`).
One code base for four case files (each has its own harness folder with identical code and its own README, results file and logs):
`excess_waste_bytes-updatewastedallocationtracker-wastedbytes`, `excess_waste_bytes-uselock-wastetracker`,
`excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2`, `excess_waste_offset-updatewastedallocationtracker-delta` (all `--autonomous`).
The constant is `private static final` and inlined, so it is varied by recompiling one class; nothing is edited in `cassandra/cassandra-5.0.9/`.

| File | Role |
|---|---|
| `mkvariant.sh <name> <literal|stock> [instrument]` | compiles a copy of `AtomicBTreePartition.java` with the literal at `:63` replaced and `S4Waste` calls added, into `~/s4-ew-var/<name>/` |
| `S4Waste.java` | counters (CAS attempts, failures and the failed attempt's `heapSize`, locked-branch attempts and failures, tracker calls and bytes, first flips to the sentinel); one CSV line a second when `-Dstage4.wastelog=<file>`; the first line records the loaded constant |
| `WasteProbe.java`, `unit-run.sh`, `unit-all.sh <case>` | unit tier: modes `direct burst refill stream account cont control memo`; reflection on the private tracker method and fields; a nested write inside the merge forces a failed CAS |
| `LoadGen.java`, `Jmx.java`, `cluster-run.py`, `cells.py`, `chain.sh <case>` | cluster tier: one node lifetime per cell (variant, workload WA..WG/W1, pool size), the cells of each case in a fixed shuffled order |
| `selfcheck.py <case>` | re-parses the raw logs of the case's runs and checks the readings used in the results file |

Run: `mkvariant.sh` for each variant, `unit-all.sh <case>`, then `chain.sh <case>` (120 s a cell). Full logs stay on the node under `~/stage4-logs/ew/`.
The unit probe must be started with the current directory on local disk (`unit-run.sh` does): the unit yaml writes under `build/test/` in the current directory.
