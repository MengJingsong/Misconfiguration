# Harness — permissions_cache_max_entries-initcache-entrycount--autonomous

Stage-4 harness for the autonomous case file (`AuthCache.java:344-346`, `.maximumSize(getMaxEntries())` on `PermissionsCache`);
written 2026-11-12 for node `apt138` (shared node; ports 7300/7301/9342, JMX 7499). Frozen versions and the audit are in the
results file (`../../results/permissions_cache_max_entries-initcache-entrycount--autonomous.md`, section 1).
Working tree on the node: `/mydata/jingsong-cass-s4/o03/src` (a `copy-source.sh` copy, `ant build-test`); harness copy
`/mydata/jingsong-cass-s4/o03/harness/`; run data `/mydata/jingsong-cass-s4/o03/<run>/`.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `PermissionsCacheMaxEntriesProbeTest.java` | unit (B2) | the case file's B2e.1 test class, verbatim | unit shakedown (renamed copy, N = 300, arms m100 and m100000) |
| `unit-run.sh <run> [shakedown]` | unit | copies the probe into the tree, one `ant testsome -Dtest.methods=<arm>` per arm (one JVM each), collects the junit XML and the test log, removes the probe source and classes, runs `collect-probe.py` and `unit-analyze.py` | shakedown |
| `collect-probe.py` | unit | runbook defect D1: test-JVM `System.out` goes to `build/test/logs/<jdk>/TEST-<class>.log` in one log line per `write()`; rejoins each `PROBE` record | first shakedown found 0 PROBE lines; the rejoined shakedown records match the raw log by eye |
| `unit-analyze.py` | unit | B2f/B2g with AM3/AM4 thresholds as `EXPECTED` lines; matched B2g row | shakedown |
| `mkconf.py` | cluster | writes an arm's `cassandra.yaml` from the pristine copy (B3a + AM1/AM2: PasswordAuthenticator, CassandraAuthorizer, validity, update interval, `permissions_cache_max_entries`, ports, directories) | asserts every edited key was found; `yaml.diff` kept per arm |
| `drop_roles.py` | cluster | the B3c driver, port 9342 | cluster shakedown (N = 50) |
| `cluster-run.sh <run> [shakedown]` | cluster | B3e per arm (M1000, M5000, M100000 + shrink to 1000, off): fresh node, wait for `statusbinary` and `LIST ROLES`, baseline `EstimatedSize` (`nodetool sjk mx`), `GC.class_histogram`, `GC.heap_info`; workload; readings after; vtable count; stop by own PID; node directory removed after each arm | cluster shakedown (N = 50: ES 14 -> 64, +51 RoleResource) |
| `cluster-analyze.py <run>/cluster [--shakedown]` | cluster | B3f/B3g with AM5 thresholds as `EXPECTED` lines; matched B3g row | shakedown |
| `selfcheck.py <run-dir>` | both | re-parses the raw test log, junit XML, histograms, session, `system.log` and driver output with its own code | its first version mis-split log lines (double space after `INFO`) and found no unit record; fixed, then reproduced every number |
