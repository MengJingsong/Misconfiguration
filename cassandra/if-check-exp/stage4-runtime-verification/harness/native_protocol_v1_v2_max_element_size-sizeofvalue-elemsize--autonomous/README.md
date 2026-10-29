# Harness: native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize--autonomous

Stage-4 instruments for `cases/native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize--autonomous.md` (sha256 and amendments in the results file §1). Run node `pc41`, run copy `~/s4-b34/src`.

| File | Tier | What |
|---|---|---|
| `ElementSizeProbeTest.java` | unit | JUnit test copied into `test/unit/.../cql3/functions/types/`: `CodecUtils.pack(ByteBuffer[N] of S bytes, N, V2|V3|V4)` for S = 65535, 65536, 8 MiB; N = 100 at S = 65535; the N = 1..1000 payload control; null element; 3 reps; thread-allocated bytes per call. |
| `unit-run.sh` | unit | runs it with `ant testsome` (`-Xmx512m`). |
| `make-node.sh`, `es.btm`, `cluster-run.py <label> default|control`, `chain.sh` | cluster (the file's alternative) | one node, `user_defined_functions_enabled`; Byteman on `CodecUtils.sizeOfValue/pack`; `default`: V2 probe, workload W (plain `set<blob>`, 100 rows per element size 65535 / 65536 / 1 MiB), workload U (Java UDF returning `list<blob>` with one S-byte element, clients v4 and v3); `control`: second node start with `column_value_size_fail_threshold: 512KiB`. The tier does not reach line 250 (V1/V2 branch); it shows the V3+ branch evaluated and node usage. |
| `selfcheck.py` | both | re-parses the raw logs and re-tests the cited numbers. |

Logs: `~/s4-b34/logs/max_element_size/<run>/`.
