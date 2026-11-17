# Harness: recheck claim of slab-region-size-region-allocate-capacity--autonomous (2026-11-17)

Tests the recheck's **Stage-4 claim to add** (one 1 MiB on-heap slab region per written table, uncounted by
`memtable_heap_space`). Design: the case file's section "Stage-4 design for the recheck claim (2026-11-17)".
Results: `../../results/slab-region-size-region-allocate-capacity--autonomous--recheck-2026-11-17.md`.

| File | Use |
|---|---|
| `run.py <arm>` | One node lifetime on pc91 (arms `H2048`, `U2048`, `H256`, `H64`): conf, `bin/cassandra -f` with `MAX_HEAP_SIZE=8G` inside `systemd-run --user --scope -p MemoryMax=12G -p MemorySwapMax=0`, read-back checks, 401 tables, steps `s0pre` (diagnostic), `s0`, `c1`, `s50`..`s400` (and `pc` in `H64`), measurement M after each, node stopped and checked. Logs to `/mydata/s4/slabrc-logs/<SR_RUN>/<arm>/`. |
| `client.py` | Bundled Python driver (protocol 4): `probe`, `settings`, `schema`, `one`, `fill`. |
| `analyze.py <logs dir>` | Readings, P1–P7, validity and the matched conclusions row (literals typed from the frozen section). |
| `Jmx.java` | JMX reader, copied unchanged from the `slab-region-size-region-allocate-capacity--autonomous` harness. |
| `HoldBytes.java`, `instrument-check.sh` | Known-answer check of the class-histogram reading (K x `byte[1048576]` = K x 1,048,592 B). |

Paths on pc91: tree `/mydata/s4/slabrc` (`cp -a` of `/mydata/s4/cassandra-base`), harness copy `/mydata/s4/slabrc-harness`,
run data `/mydata/s4/slabrc-run` (removed after each lifetime). Run all four:
`for a in H2048 U2048 H256 H64; do python3 -I run.py $a || break; done`, then `python3 -I analyze.py /mydata/s4/slabrc-logs/run1`.
