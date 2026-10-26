# Harness — transition-bytes-collector-add-buffer-length--autonomous

Stage-4 harness for the autonomous case file `Walker.TransitionBytesCollector.add` (entry `Walker.java:442`); written 2026-10-26 on `pc07` (`node0`) by the autonomous stage-4 session, tag `tc`. Not committed (the orchestrator commits).
Tree `~/s4-b7-tc` (`copy-source.sh`, `ant build-test`), node data `~/s4-b7-tc-run/`, logs `~/s4-b7-tc-logs/<run>/`. Port slot 1: loopback `127.0.1.1`, JMX 7110, Byteman listener 19110, native 9042, storage 7000/7001.
Frozen version and the audit: the results file [§1](../../results/transition-bytes-collector-add-buffer-length--autonomous.md).

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `CollectorGrowthTest.java` | unit (B2) | One JUnit class (copied into `test/unit/org/apache/cassandra/io/tries/`): standalone `TransitionBytesCollector` fed L `add()` calls (and L pops), one-key tries of L bytes read by `TrieTermsDictionaryReader.getMaxTerm()/getMinTerm()` (thread-allocated bytes) and by the test class `TrieTermsIterator` (collecting=true; capacity by reflection), simulation of `ArrayUtil.grow` (Lucene 9.7.0) for the expected capacity and arrays allocated, SAI term-size guardrail at 1KiB/8KiB/64KiB (`failsOn` on probe sizes), `new byte[L]` allocation control. L in {8,32,33,1024,8192,65535}, 3 repetitions, 131072 and 1048576 standalone. Prints `TC` lines. | shakedown 1 (compiled, ran, analyzer ran) |
| `unit-run.sh [run]` | unit | Copies the test in, `ant testsome` (writes `tc-unit.txt`, `tc-env.txt`), runs the same class under `JUnitCore` with `-Xmx256m` and `-Xmx512m` using the recorded class path and JVM arguments, removes the test, runs the analyzer. | shakedown 1 |
| `unit-analyze.py <dir>` | unit | B2f (1)-(3), the controls, the matched B2g row, as `EXPECTED:` lines. | shakedown 1 (two analyzer expectation slips fixed: `true` vs `True`; the drained iterator's `pos` is -1, not 0) |
| `collector.btm` | cluster | Byteman, observation only: `COLL` lines for every construction / `add` of the collector (first 20 and every 1000th), `LIVE` lines for `Walker`, `ValueIterator`, `TrieTermsDictionaryReader` constructions (liveness of the instrument). | `instr-check.sh` (below) |
| `instr-check.sh <run>` | cluster instrument | Runs the unit test under the same rules: the collector is used there, so COLL lines must appear. | shakedown 1: ctor n up to 43,000, add n up to 540,810,000, LIVE lines present |
| `client.py` | cluster | Bundled Python driver, protocol 4: `schema` (as the superuser: keyspace, w1..w4 with SAI on v, ordinary role `tcw`), `load` (counts guardrail rejections, continues), `read` (point reads and SAI `v = ?` queries, per-table hit counts). | shakedowns 2-6 |
| `cluster-run.py all \| <label>... \| down` | cluster | Lifetimes T1k, T8k, T64k (bti) and BIG (big): fresh node and data dir, Byteman agent, PasswordAuthenticator, W1-W4 loads, flush, compact, 180 s reads, class histogram after each phase, `du`, `system.log` segment, node stopped by PID. `TC_SCALE` divides the workload (shakedown). | shakedowns 2-6 (see results §1) |
| `cluster-analyze.py <dir>` | cluster | B3f (a)-(d) as `EXPECTED:` lines and the matched B3g row. | shakedown 6 |
| `selfcheck.py unit \| cluster <dir>` | both | Independent re-parse of the raw files (own code, does not import the analyzers; recomputes the Lucene growth in 4 lines). | shakedown |

Run order: `bash unit-run.sh run1`; `TC_RUN=run1 python3 -I cluster-run.py all`; `python3 -I cluster-analyze.py ~/s4-b7-tc-logs/run1/cluster`; `python3 -I selfcheck.py unit ~/s4-b7-tc-logs/run1/unit` and `... cluster ~/s4-b7-tc-logs/run1/cluster`.
