# Harness: native_protocol_v1_v2_collection_size_limit-writesize-size--autonomous

Stage-4 instruments for `cases/native_protocol_v1_v2_collection_size_limit-writesize-size--autonomous.md` (sha256 and amendments in the results file §1). Run node `pc41`, run copy `~/s4-b34/src`.

| File | Tier | What |
|---|---|---|
| `CollectionSizeProbeTest.java` | unit | JUnit test copied into `test/unit/.../cql3/functions/types/`: `TypeCodec.list(TypeCodec.blob()).serialize(list, V2|V3|V4)` for N = 65535, 65536, 200000, payload 1 B and 100 B, 3 reps; prints `STAGE4 cell` (exception or exact length, count field, thread-allocated bytes). |
| `unit-run.sh` | unit | runs it with `ant testsome` (`-Xmx512m`; the build's test JVM uses CMS, so `-XX:+UseSerialGC` of B2a cannot be added: runbook defect 1). |
| `make-node.sh`, `cs.btm`, `cluster-run.py <label> default|control`, `chain.sh` | cluster | one node, `user_defined_functions_enabled`; Byteman on `CodecUtils.pack/writeSize`; `default`: V2 probe, workload W (plain `set<int>` N = 1000/65536/500000), workload U (Java UDF returning `list<int>`, clients v4 and v3); `control`: second node start with `collection_size_fail_threshold: 200KiB`, the W inserts. |
| `selfcheck.py` | both | re-parses the raw logs and re-tests the cited numbers. |

Logs: `~/s4-b34/logs/collection_size_limit/<run>/`.
