# Harness: repair-session-space-histogram-add-values--autonomous

Stage-4 harness for the case `stage3-ai-deep-read/cases/repair-session-space-histogram-add-values--autonomous.md` (amendments dated 2026-10-26 in its section D).
Port slot 2 on pc12: loopback 127.0.2.1 / 127.0.2.2, JMX 7120 / 7121, native 9042 on 127.0.2.1 only. Work tree `~/s4-b7-hv/c509` (copy-source.sh + `ant build-test`), logs `~/s4-b7-hv-logs`, node data `/dev/shm/s4-b7-hv`.

| File | Use |
|---|---|
| `freeze-hash.py` | sha256 of B2f-g + B3f-g and of the whole case file (recorded in results §1 before any run) |
| `HistogramBudgetProbe.java` | unit tier: `direct` (HistogramBuilder alone), `tree` (ValidationManager's budget arithmetic incl. the int wrap, MerkleTrees.addMerkleTree + init, histogramOfRowCountPerLeaf with thread-allocated bytes), `known` (known-answer driver for the JFR check) |
| `unit-run.sh <tree> <out> [check]` | compile + run every (S, RF, D) in its own JVM; `check` = instrument check only |
| `unit-analyze.py` | EXPECTED lines for the B2f predictions from the RESULT lines |
| `make-node-yaml.sh` | node conf dir (loopback address, tokens +-2^62, ports, tmpfs dirs) |
| `cluster-run.py` | two-node setup, stress load, runs r1..r5, r1b; JFR + jstat + debug.log excerpts; stops on a failed first-trigger check; nodes stopped on any exit |
| `jfr-sizes.py` | exact byte sizes of `HistogramBuilder.add` allocations from a `.jfr` (jfr print --json) |
| `cluster-analyze.py`, `selfcheck.py` | EXPECTED lines for B3f from the raw files; independent re-parse for the self-check |

Instrument check (2026-10-26, before run 1): `known 5000 20000 1000000` under JFR (settings=profile) with `-XX:-ResizeTLAB -XX:TLABSize=16k` reports every `HistogramBuilder.add` array from 2,576 B to 10,485,776 B, including 40,976 / 163,856 / 10,485,776 B; without the TLAB options it reports only arrays >= 327,696 B, which would miss the S = 8 array (163,856 B) and the D = 12 array (40,976 B). `values.length` for n = 10, 11, 1,000,000 matched the formula (10, 20, 1,310,720).
