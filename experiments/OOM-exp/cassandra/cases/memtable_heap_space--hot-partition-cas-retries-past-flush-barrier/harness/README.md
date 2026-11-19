# B18 stage-2 harness (pc75, 2026-11-18)

Synced to `/mydata/s4/b18-w4/harness/` on pc75 (directory amendment A1: `/mydata/s4/b18-w4` instead of `/mydata/b18`).
Built from C6's harness (`../memtable_heap_space-slab-region--written-table-multiplicity/harness/`) and the stage-4
`LoadGen.java` of `excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous`.

| File | Role |
|---|---|
| `HotGen.java` | load: 4 source IPs (127.0.0.11–14, bound via `NettyOptions.afterBootstrapInitialized`) × 9 threads, unlogged single-partition batches of R rows × 8,192 B, `hot` (pk = 1) or `perthread`; 1 s sleep after an error; optional global rate (MiB/s) for the Crm fallback |
| `Jmx.java` | C6's JMX reader; `poll` at 500 ms for the sampler |
| `client.py` | admin client (bundled Python driver): probe, `system_views.settings` read-back, schema |
| `run.py` | one node lifetime (`life <label> <T|C|I|Crm> <2G|4G|8G> [R] [rate]`, `shakedown`, `down`) |
| `plan.sh`, `after.sh`, `plan-*.txt` | sequence runner (no new lifetime after 17:20 America/New_York), chaining |
| `hprof_scan.py` | C6's scanner + shallow-bytes histogram by class (`classes_top`, `classes_named`) |
| `HoldRegions.java`, `instrument-check.sh` | scanner known-answer check (40 regions, 40 near-regions, 1,000 `HoldRegions$Marker`): passed 2026-11-18 |
| `analyze.py` | per-lifetime readings (§2.6/§2.7) as JSON lines |
| `logback-client.xml` | HotGen driver logging at WARN |

Launch: `( setsid nohup bash harness/plan.sh harness/plan-h2.txt < /dev/null > logs/plan-h2.out 2>&1 & )` from
`/mydata/s4/b18-w4`. Logs: `/mydata/s4/b18-w4/logs/<label>/`.
