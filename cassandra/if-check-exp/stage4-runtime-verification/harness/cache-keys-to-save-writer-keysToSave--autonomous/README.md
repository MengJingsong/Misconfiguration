# Harness — cache-keys-to-save-writer-keysToSave--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 in the results file
[§1](../../results/cache-keys-to-save-writer-keysToSave--autonomous.md)). Written 2026-10-26 after the step-0 audit and before any run-1
reading. Host `pc12`; unit tree `~/s4-b7-ck` (`copy-source.sh`, `ant build-test`), node tree `~/s4-b7-ck-n` (`copy-source.sh`, `ant jar`; no `ant`
after the node first starts); port slot 5: loopback 127.0.5.1, storage 7000, native 9042, JMX 7150. Node data on tmpfs `/dev/shm/s4-b7-ck`;
logs `~/s4-b7-ck-logs/<run>/`.

| File | Tier | What it does |
|---|---|---|
| `KeysToSaveWriterTest.java` | unit (B2) | `CQLTester` test in `org.apache.cassandra.cache`, copied into the unit tree by `unit-run.sh`. 1000 rows flushed to one sstable; each K in 1, 100, 500, 1000, 0, MAX, 2000: clear, fresh saved-cache files, re-read all N keys via `SSTableReader.getPosition` (100 hot keys 5 more times), assert `size() == N` (first K stops the run if not), `submitWrite(K).get()`, log count from a logback appender (`Saved KeyCache (n items)`), `File.length()` of `-g.db/.crc/.metadata`, `size()`/`weightedSize()` before and after, `clear(); loadSaved()` reload count and which keys came back. Then the counter-cache repeat (K = 100, 0). Writes `$STAGE4_OUT/unit.txt`. |
| `unit-run.sh <tree> <outdir> [N]` | unit | copies the test in, `ant testsome`, runs `analyze_unit.py`. N defaults to 1000; other values are shakedown only. |
| `analyze_unit.py`, `known-answer-unit.txt` | unit | EXPECTED lines for B2f/B2g. `known-answer-unit.txt` is a synthetic result (hdr 40 B, 100 B per entry): the analyzer must print 0 MISMATCH on it and flag a copy in which K=100 writes 150 entries (instrument check). |
| `Jmx.java` | cluster | JMX client: `get`, `set` (int attribute), `invoke` (no-argument operation), `poll`. Replaces `jmxterm`, which is not installed. |
| `make-node-yaml.sh` | cluster | node yaml: tag's `cassandra.yaml` plus this node's lines (127.0.5.1, tmpfs dirs, `key_cache_size`, `key_cache_save_period: 1h`, row and counter caches 0) and the arm's overrides. |
| `cluster-run.py <arm>` | cluster (B3e) | `main`, `ctl20`, `yaml10k` (see its docstring); `down`, `clean`. |
| `analyze_cluster.py` | cluster | EXPECTED lines for B3f/B3g from the arms' `results.json`. |
| `selfcheck.py` | both | independent re-parse of the raw logs. |

**Reading rules, fixed before run 1 (not tuned to readings)** are in the docstrings of `analyze_unit.py` and `analyze_cluster.py`. In short: the cluster
populates the key cache by uniform read passes until it holds at least 700,000 entries (the spec asks for 300,000; 700,000 makes the 20 MiB control's
entry ratio unambiguous); K is set through JMX attribute `KeyCacheKeysToSave` and the save is triggered through JMX operation `saveCaches`;
the saved file is read with `os.path.getsize` once the `Saved KeyCache` log line has appeared; heap is sampled every 100 ms and recorded as
information only.

Run order (run 1), each as its own background job:

```bash
H=<repo>/cassandra/if-check-exp/stage4-runtime-verification/harness/cache-keys-to-save-writer-keysToSave--autonomous
bash $H/unit-run.sh ~/s4-b7-ck ~/s4-b7-ck-logs/run1/unit 1000
for a in main ctl20 yaml10k; do CK_RUN=run1 python3 -I $H/cluster-run.py $a; done
python3 -I $H/analyze_cluster.py ~/s4-b7-ck-logs/run1/cluster
```
