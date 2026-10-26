# Harness — hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 in the results file
[§1](../../results/hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous.md)). Written 2026-10-25 after the step-0
audit and before any run-1 reading. Run on `pc07` (local, node0 of `jason92-320876`) from the tree `~/s4-hw` (made by
`copy-source.sh`, `ant build-test` done), node data in `~/s4-hw-data/{A,B,C}` (local disk, wiped per lifetime), logs in
`~/s4-hw-logs/<run>/`. Ports of this agent: JMX 7814 (A) · 7815 (B) · 7816 (C; not the assigned 7214, see finding 3), Byteman 9114 (A), native 9146, storage 7014,
loopback 127.0.14.1 (A) · .2 (B) · .3 (C, `P2` only). Adapted from the `max_mutation_size-allocateBytes-slabCapacity--autonomous`
harness (client, `Jmx.java`, node yaml, runner); the differences are the ports, the per-pid-file stop (no host-wide
`CassandraDaemon` test: the node is shared), the one-workload-per-lifetime design and the Byteman rules.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `CompressedHintsWriterCapProbeTest.java` | unit (B2) | Package `org.apache.cassandra.hints`. Drives `CompressedHintsWriter` through `HintsWriter.create` and `Session.append` and reads the private `compressionBuffer` by reflection. One `STAGE4 check <name> ok\|MISMATCH` line per relation: `lz4-bound`, `asc-<S>` (six sizes), `seq`, `filesize`, `n-1/4/16`, `uncompressed`, `compressible`, `deflate`, `cap-boundary`, `cap-formula`, `slab-control-32/128` (list at the head of the file). | shakedowns 1 and 2 (compiles, all checks run) |
| `unit-run.sh <run>` | unit | Upstream `HintsCompressionTest`, `HintsBufferTest`, then the probe with `-Dstage4.out -Dstage4.dir -XX:MaxDirectMemorySize=1g`. | the shakedowns |
| `hw.btm` | cluster (B3d) | Byteman on A, observation only: `opened`, `cbuf` (every `CompressedHintsWriter.writeBuffer`: writer identity, `bb.remaining()` at entry, `compressionBuffer.capacity()` and `isDirect()` at exit), `closed` (`HintsWriter.close`), `created` (new `HintsBuffer` slab), `direct` (every `allocateDirect` of ≥ 1 MiB, with stack). `boot:` for the last rule. | `TestScript` (type-checks all six rules); the shakedown trace |
| `make-node-yaml.sh <A\|B\|C> [k=v …]` | cluster (B3a) | `~/s4-hw-data/<node>/conf`: the tag's yaml plus the node's address, ports, 4 tokens, `SimpleSnitch`, seed 127.0.14.1:7014, local directories, `hinted_handoff_enabled true`, `write_request_timeout 30000ms`, `native_transport_timeout 60000ms`, then the arm's lines; `hints_compression=LZ4Compressor` writes the list block; JMX port; `-XX:MaxDirectMemorySize=2g`. | yaml tail in the summary; `system_views.settings` read-back |
| `client.py` | cluster (B3c) | Bundled Python driver, protocol 4, port 9146, one host, no retries: `schema <host> <rf>`, `settings`, `bulk` (S: n INSERTs of 1,024 B), `big` (L: n INSERTs of 8 MiB incompressible values, 4 in flight). | the shakedowns |
| `Jmx.java` | cluster (B3d) | JMX client (`get`, `query`, `poll`), copied unchanged from the `max_mutation_size` harness. | the shakedowns |
| `cluster-run.py <arm> \| analyze \| down` | cluster (B3e) | One node lifetime per call (see its docstring), `summary.txt` with `EXPECTED:` lines, `phases.json`, `samples.csv`, `hw.trace`. `analyze` writes the cross-arm relations. | shakedowns 1 and 2 (`HW_N` lowered) |

**Shakedown findings, before any run-1 reading (2026-10-25; shakedown data is not a reading).**
1. Unit shakedown 1: 18 of 19 checks passed; the `deflate` check had required the pool to stay flat, but `FileChannel.write` of a
   heap buffer caches a temporary direct buffer of the write size in the JDK (pool +4,187,406 B for a 4 MiB heap compression
   buffer). The pool delta is now printed as information; the buffer's `isDirect()` is the check. The check is an extra of the
   audit (B2 amendment 4), not a B2f/B2g row.
2. Cluster shakedown 1 (`D1`, 12 hints): `system_views.settings` shows `hints_compression` as null even when compression is on
   (the writer trace shows a `CompressedHintsWriter`), so the read-back expectation was dropped and compression is read from the
   trace. `HintsService.shutdownBlocking` closes the open writers at node stop, so the trace is now read before A is stopped
   (otherwise the live-writer count is 0).
3. JMX port collision (cluster shakedown 3): the assigned JMX port 7214 is also used by another agent's node on this host
   (the runner found `127.0.0.1:7214` busy on one start attempt, and a `nodetool -p 7214 drain` from that agent's script drained
   this harness's node A seconds after it came up). To keep from draining or stopping each other's nodes, this harness uses JMX
   7814 (A) · 7815 (B) · 7816 (C) instead of 7214; every other assigned port is unchanged. Case file B3 amendment 2 says the same.
4. A third node cannot bootstrap while the second is joining (shakedown 2: C died at start); `P2` now starts B, waits for UN,
   then starts C.

**Reading rules, fixed before run 1 (case file, B3 amendment items 4 and 5; not tuned to readings).** Marks: baseline = the
sample 1.5 s after the idle baseline mark (after B is seen DN and `GC.run` twice and 10 s); end = the sample 1.5 s after the mark
set 25 s after the workload, `GC.run` twice and 10 s. `dPool` = direct `MemoryUsed` at the end mark minus at the baseline.
`Corr` = the sum of `created` slab sizes whose timestamp is at or after the baseline mark. `X(arm) = (dPool_arm − Corr_arm) −
(dPool_U − Corr_U)` for the L lifetimes and against `US` for `S`. Band 2 MiB. The trace gives each buffer exactly: the quantity
under test is read there; the pool is the real-resource reading.

Run order (run 1), each lifetime its own background job:

```bash
H=<repo>/cassandra/if-check-exp/stage4-runtime-verification/harness/hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous
bash $H/unit-run.sh run1
for a in US S U D1 D2 F1 H1 P2 M128; do HW_RUN=run1 python3 -I $H/cluster-run.py $a; done
HW_RUN=run1 python3 -I $H/cluster-run.py analyze
```
