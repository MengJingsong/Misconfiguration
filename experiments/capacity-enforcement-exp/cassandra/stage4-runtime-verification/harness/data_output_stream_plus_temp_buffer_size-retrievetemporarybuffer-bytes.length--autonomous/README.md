# Harness — data_output_stream_plus_temp_buffer_size-retrievetemporarybuffer-bytes.length--autonomous

Stage-4 instruments for the case file of the same name (B2 unit tier, B3 cluster tier, amendments A1-A5).
Work directory on the node: `/mydata/jingsong-cass-s4/o43` (`src/` = `copy-source.sh` copy of 5.0.9, `ant build-test`).

| File | Use |
|---|---|
| `TempBufferProbe.java` | B2a probe, verbatim from the case file (extracted with awk from the frozen file) |
| `unit-run.sh` | B2e: compiles the probe, one 1 GiB JVM per P ∈ {4096, default, 1048576, 16777216}; logs `run1/unit/unit-<P>.log` |
| `unit-analyze.py` | compares the unit logs with B2f (exact lengths, `len ≤ P`) and the A3 heapDelta tolerance; prints PASS/FAIL per check |
| `setup-conf.sh` | B3a + A2: edits the copy's `conf/cassandra.yaml` and `conf/cassandra-env.sh` (ports 7300/7301/9342, JMX 7499, 127.0.0.1, `offheap_buffers`, serializing row cache 1 GiB, memtable spaces) from saved `.orig` copies |
| `cluster-run.sh <label> <P|default> <alloc>` | B3e for one value: fresh node (`MAX_HEAP_SIZE=4G`, `MAX_DIRECT_MEMORY_SIZE=2G`, `JVM_EXTRA_OPTS` only on `bin/cassandra`), `jinfo`, 64 × 4 MiB writes, tablestats, `nodetool info` before/after reads, `GC.class_histogram` H0/H1, JFR (profile) around the 32-way read pass, `jfr print --json`, teardown by PID (trap) and leftover check |
| `o43.py` | B3c workload script, as filed except port 9342 (A2) |
| `jfr-parse.py` | counts JFR `ObjectAllocationOutsideTLAB`/`InNewTLAB` events whose stack contains `retrieveTemporaryBuffer`; array length = `allocationSize − 16` |
| `JfrParseCheck.java` | known-answer check of `jfr-parse.py` (5 × 3 MiB inside a method named `retrieveTemporaryBuffer` + one 2 MiB elsewhere → parser reported 5 events, length 3145728, 5 threads; header 16 B) |
| `cluster-analyze.py` | compares cluster readings with B3f/B3g (ΔH, misses on the read pass, SSTable count, temp-buffer allocations and sizes vs P) |

Instrument faults found before or during run 1: `jfr-parse.py` first compared `allocationSize` (which includes the 16-byte
array header) with P; fixed to the array length after the known-answer check, before any case reading. Runbook defect D1
(driver zip path) is in the results file §3.
