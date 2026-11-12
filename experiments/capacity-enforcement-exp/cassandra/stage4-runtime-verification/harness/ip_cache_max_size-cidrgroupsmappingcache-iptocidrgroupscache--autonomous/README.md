# Harness — ip_cache_max_size-cidrgroupsmappingcache-iptocidrgroupscache--autonomous

Stage-4 harness for the autonomous case file (`CIDRGroupsMappingCache.java:59-60`, Caffeine `maximumSize` of
`ipToCidrGroupsCache`); written 2026-11-12 on `apt179` (shared node; ports 7300/7301/7499/9342, amendment AM2).
Frozen versions and the audit are in the results file (`../../results/ip_cache_max_size-cidrgroupsmappingcache-iptocidrgroupscache--autonomous.md`, section 1).

Layout on the node: `WORK=/mydata/jingsong-cass-s4/o04`; `$WORK/src` is a `copy-source.sh` copy (`ant build-test`, then `ant jar`);
this folder is synced to `$WORK/harness`; client classes are compiled in `$WORK/tools`; node data in `$WORK/data`; logs in `$WORK/logs/<run>/`.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `IpCacheMaxSizeProbeTest.java` | unit (B2) | The case file's B2e test class, verbatim. | shakedown `max` in {0, 1000}, n = 2000 |
| `unit-run.sh <run> [values] [n]` | unit | copies the probe into the tree, one `ant testsome` (fresh JVM) per value, rebuilds the PROBE lines, removes the probe | shakedown |
| `unit-extract.py` | unit | The test JVM's stdout goes through a logger and `printf` arguments arrive as separate log lines; this rebuilds the PROBE lines from the fragments of `unit-<M>.log` (the junit XML holds none). | shakedown: rebuilt lines match the fragments by eye |
| `unit-analyze.py` | unit | B2f/B2g as `EXPECTED:` lines (tolerances from section D, AM4) | shakedown (reports missing values) |
| `configure.py` | cluster (B3) | B3a yaml edits (PasswordAuthenticator, `cidr_authorizer` block with K, directories) and AM2 ports, on a pristine `conf/` (`git checkout -- conf/...` first) | shakedown K=1000; each edit asserts exactly one match |
| `JmxProbe.java`, `NativeProbe.java` | cluster | B3e step 6 (W1) and step 9 (W2) as filed, with the port as an extra argument (AM2); JmxProbe also prints the first and last result | shakedown: W1 3000 lookups → `[lo]`, W2 50 logins |
| `cluster-run.sh <run> <K> [w1n] [w2m] [settle-s]` | cluster | B3e steps 1-10 for one K: port check, configure, wipe, start (1 GiB heap), wait `UN` + `statusbinary` `running`, cqlsh, group `lo`, histograms base1/base2 60 s apart, heap_info, W1, w1/heap_info, w1b after 60 s, flush, W2, stop; trap stops the node on any exit | shakedown K=1000, w1n 3000, w2m 50, settle 5 s |
| `cluster-all.sh <run>` | cluster | K = 100, 100000, 1000000 in order, then `cluster-analyze.py` | — |
| `cluster-analyze.py <run-dir>` | cluster | B3f/B3g as `EXPECTED:` lines: deltas vs `base2` for `Inet4Address`, `InetAddressHolder`, `ConcurrentHashMap$Node`, the Caffeine node class with the largest jump (`PSMS`); heap Δ = histogram `Total` (AM3), `heap_info` beside it; matched rows | shakedown |
| `selfcheck.py <run-dir>` | both | re-reads the raw files with its own parsing (log fragments paired by position; histogram rows by column split) and the node's `system.log` | run on run 1 |

Shakedown finding (instrument only): the B2e grep of `PROBE` in the junit XML finds nothing in this build, because stdout is
routed through the test logger and split per `printf` argument; `unit-extract.py` handles it (results §3, D1).
