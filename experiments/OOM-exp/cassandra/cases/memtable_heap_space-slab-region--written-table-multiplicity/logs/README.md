# C6 stage-2 logs (2026-11-18)

Full logs stay on pc91 under `/mydata/s4/c6-w2/logs/<label>/`; per-lifetime excerpts were built on the node in
`/mydata/s4/c6-w2/excerpts/<label>/` by `../harness/excerpts.sh`. At ≈ 04:04 America/New_York every UMass node (pc91, pc84,
pc72, pc99, pc75) stopped answering, before the excerpts could be copied here. `analyze-captured.jsonl` holds the
`analyze.py` / `run.py` readings as they were printed in the stage-2 session (copied from the session's tool output;
the stdout list of JVM-argument lines is trimmed). If the node comes back, copy `/mydata/s4/c6-w2/excerpts/` here.

| File | Content |
|---|---|
| `analyze-captured.jsonl` | one JSON object per lifetime / build as captured (full for H2-T-1, H2-T-2, H2-C-1, H2-I-1, H4-T-1; the key fields for the others) |
| `oom-traces-captured.txt` | the OOM-dump thread traces printed by `hprof_scan.py` (H2-T-2, H4-T-1) and the `stdout.txt` OOM lines |
