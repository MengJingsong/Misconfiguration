# Run-3 evidence excerpts — read this first

**VOID columns (sampler bug, found 2026-11-10):** in `probe3-N4-fixed150.txt`, `burst-N8-fixed300.txt`
and `threads-N8-1200.txt` the `using=`, `reserve=`, `throttled=` (and `expired=`) values are **always 0
because of a parsing bug** (awk summed the `|` separator fields `$4/$6/$8` of cqlsh output). The
`heap`/`heapMiB` values in those files are also invalid (nodetool parse). Only `MutPending=` (tpstats
column 3) is valid in them.

**Authoritative queue data:** `G3-queue-reparse.txt` — the raw `arms/<arm>/queue.log` written by
`arm3.sh`, re-parsed correctly. `qfinal-probe-allzero.txt` is an *end-of-arm* snapshot after load
stopped (queues drained), not evidence that queues never filled.
