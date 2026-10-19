# run 1 — internode_application_send_queue_capacity

Run 1 of stage 4, 2026-10-07 23:44 – 2026-10-08 00:19 on `pc66`. Verdict: **Confirmed at both tiers, no run 2** (results file §4, §5, §8).

## What is here (small excerpts; full logs stay on the node)

- `selfcheck.py` — the independent re-parser. Re-derives every figure from the **raw** `send-trace.txt` (Byteman
  `acquire`/`config` lines) and `readings.csv` (JMX), and tests them against the frozen §9a prediction typed into the
  script, not against the run script's own `EXPECTED:` lines. Also cross-checks each number against `scenarios.csv`.
- `selfcheck.out` — its output from run 1 (**exit 0**: 0 load-bearing failures, 0 disagreements with the run script,
  4 recorded scenario-A calibration misses reproduced).
- `unit/summary.txt`, `cluster/<label>/{summary.txt,scenarios.csv}` — the derived tables per label (9 cluster labels
  `c512k c1m c4m c16m defres nohold c1 c2 peer`, plus `unit`).

## Re-running the self-check

It reads the **full raw logs**, which stay on the node, not in the repo. On `pc66`:

```
python3 -I selfcheck.py            # defaults to ~/stage4-logs/ssq
python3 -I selfcheck.py <RAW_DIR>  # or point it at another copy of the per-label log dirs
```

Each `<RAW_DIR>/<label>/` must hold `send-trace.txt`, `readings.csv`, `scenarios.csv`, `summary.txt` and
`<scenario>/poll.csv`; `<RAW_DIR>/unit/summary.txt` for the unit tier. CloudLab nodes are rebuilt from scratch, so if
`pc66` is reprovisioned the raw logs are gone and `selfcheck.py` can only re-check the small excerpts here, not the
trace — `selfcheck.out` is then the record of the run-1 self-check.

## Key raw-log line formats (for a reader without the harness)

- `send-trace.txt`, acquire line (one per `OutboundConnection.acquireCapacity` exit):
  `acquire type=<ConnType> peer=/<ip>:<port> count=<n> bytes=<M> outcome=<SUCCESS|INSUFFICIENT_ENDPOINT|INSUFFICIENT_GLOBAL> pending=<after> pendingCount=<n> overloaded=<n> endpoint_using=<n> global_using=<n> ms=<epoch>`
- `send-trace.txt`, config line (one per connection built): `config type=… peer=… capacity=… endpoint=… global=… ms=…`
- `readings.csv`: `ts_ms,tag,peer,attr,value` — JMX Connection metrics tagged by phase (`idle`, `<sc>-pre/-late/-drained`, `probe-before/-after`, `holdcheck-*`).
