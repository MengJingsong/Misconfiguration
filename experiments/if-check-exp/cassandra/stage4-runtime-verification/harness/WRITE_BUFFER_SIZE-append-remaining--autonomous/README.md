# Harness — WRITE_BUFFER_SIZE-append-remaining--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 `55bf043e…`, see the results file
[§1](../../results/WRITE_BUFFER_SIZE-append-remaining--autonomous.md)). Written 2026-10-20 after the step-0 audit, on
`pc07` (`node0.jason92-320876`), run from a copy `~/stage4-harness-run/wbs/` against `~/cassandra-run1`
(`cassandra-5.0.9`, `b5f2a54210`, `ant build-test`). Logs go to `~/stage4-logs/wbs/<run>/` on the node, outside the repo.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `WriteBufferProbeTest.java` | unit (B2) | Package `org.apache.cassandra.hints`; `unit-run.sh` copies it into the clone's `test/unit/org/apache/cassandra/hints/`. One `ks.t (k int PRIMARY KEY, v blob)` hint per size *S* (1 · 100 · 255 · 257 · 400 · 600 KiB · 1 · 4 · 15 MiB), reused for every append; 20 warm-up appends, then *N* = 64 (S ≤ 255 KiB) or 8 measured. Variant **H** `append(Hint)`; **H64** the same with a 64 KiB buffer at 100 KiB; **B** `append(ByteBuffer)` with the entry in a heap buffer (B2e step 4 as filed); **D** (supplementary) the entry as laid out by `HintsBuffer.Allocation.write`, in a direct buffer. Per append: the thread's allocated bytes (`ThreadMXBean`), `buffer.remaining()`, the file length. Per case: `getBytesWritten`, file length after close, `HintsReader` read-back, the direct pool (reported only). Every case twice. Positive control `HintsBuffer.create(1 MiB).allocate(…)`: 400 KiB as filed (cannot refuse, results §3 D1), 600 KiB, 100 KiB, and the pair at `capacity/2`. `STAGE4 append/case/check` lines. | `javac` against the clone; shakedown1 (266 checks, the filed 400 KiB control the only mismatch) |
| `unit-run.sh [run]` | unit | The probe test (test heap 1 GiB, GC log), then upstream `HintsReaderTest`; `summary.txt`. `--remove` deletes the copied test from the clone. | — |
| `wbs.btm` | cluster | Byteman, observation only, on node A: `created=` (each 32 MiB slab, from the `MAX_HINT_BUFFERS` harness), `waiting` (the pool's `take()`), `app` (each `Session.append(ByteBuffer)`: entry size against the buffer), `wr` (each channel write; `buf=false` a hint written directly), `refuse` (a `shouldHint` refusal with the operand and the limit, from the `max_hints_size_per_host` harness), `flush`. | `TestScript`: 8 rules type-checked, no errors |
| `client.py` | cluster (B3c) | Bundled Python driver, **protocol 4** (v5 large requests leave direct buffers behind), whitelist A, CL ONE: `probe`, `schema <ks>` (RF 2), `drop <ks>`, `write <ks> <size> <bytes> <conc> …` (one random value per call; every key logged; stops after `max_s` or 20 consecutive failures). | the shakedown |
| `Jmx.java` | cluster | JMX client: `get`, `setint` (the live per-host limit, read back), `query`, `poll`. | the shakedown |
| `make-node-yaml.sh <A\|B>` | cluster (B3a) | `~/stage4-wbs/<node>/conf`: the tag's conf plus B3a's lines (`num_tokens: 1`, hints on, `max_hint_window: 3h`, `max_hints_file_size: 128MiB`, `hints_flush_period: 1000ms`, `max_hints_size_per_host: 0MiB`), loopback A = 127.0.0.2 (JMX 7102, seed), B = 127.0.0.3 (JMX 7103), `-XX:MaxDirectMemorySize=1g`, NMT summary. | the yaml tail in `summary.txt` |
| `cluster-run.py main \| mhb1 <rep> \| analyze \| down` | cluster (B3e) | `main`: control with B up, B stopped, 100 KiB · 1 MiB · 8 MiB × 2 reps (2 GiB each: 1 GiB at 1 in flight, 1 GiB at 8), then the per-host limit 64 MiB (live) × 2 with 1 MiB; reset before each arm (R2: drop keyspace, clear snapshots, `truncatehints` until no file). `mhb1 <rep>`: a lifetime with `-Dcassandra.MAX_HINT_BUFFERS=1` on A, one 1 MiB arm, halves bounded at 90 s, three thread dumps. 1 s sampler of A (direct pool, heap, `TotalHints`, the `.hints` files). `EXPECTED:` lines in `summary.txt`; `arms.json`, `samples-jmx.csv`, `hints.csv`, `wbs.trace`, keys, NMT, dumps, logs. `analyze`: cross-arm relations (X1–X4). | the shakedown (`WBS_RUN=shakedown1`, 128 MiB per arm) |
| `selfcheck.py` | both | Independent re-parse of the raw run-1 files (copied to `results/<stem>/run1/` with its output). | — |

Run order (run 1):

```bash
H=~/stage4-harness-run/wbs
$H/unit-run.sh run1
python3 $H/cluster-run.py main; python3 $H/cluster-run.py mhb1 1; python3 $H/cluster-run.py mhb1 2; python3 $H/cluster-run.py analyze   # one background job
```
