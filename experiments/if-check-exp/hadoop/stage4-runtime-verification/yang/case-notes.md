# Stage 4 — notes from the closed Hadoop cases (Yang's share)

Read after the protocol, [`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md), and the node
setup, [`environment.md`](environment.md). Short lessons for later Hadoop cases; one entry per closed case.

| Case (stem) | Verdict | Outcome class | Results |
|---|---|---|---|
| `yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous` | unit Confirmed, cluster Confirmed — does not cap | true negative | [results](results/yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous.md) |

## Environment lessons (2026-11-06, first Hadoop case)

1. **The base distribution has no YARN module jars.** `/mydata/yang-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2/share/hadoop/yarn/`
   holds only `lib/`, `sources/`, `timelineservice/lib/` and the like; the RM/NM jars are missing (the resumed base build's assembly
   left them out; four YARN jars sit in `share/hadoop/tools/lib/` only). A cluster tier copies the distribution per case and adds the
   3.4.2 YARN main jars from `~/.m2` (`hadoop-yarn-{api,client,common,registry,server-*,services-*,applications-*}`), plus
   `hadoop-yarn-server-timelineservice-3.4.2.jar` into `share/hadoop/yarn/timelineservice/`. With that, `hdfs`/`yarn --daemon start`
   work. `cluster-run.py` in this case's harness does it (`YARN_JARS`). `environment.md` does not say this yet.
   **Fixed 2026-11-06 (later):** the gap came from resuming the build with `-rf`; the base was rebuilt in full
   and now has all 19 YARN jars (`environment.md` §3), so later cases need no `~/.m2` jar copy.
2. **`jq` is not installed**; parse REST JSON with `python3 -I`.
3. **`cp $HADOOP_HOME/etc/hadoop/* conf/` needs `-r`** (`etc/hadoop/shellprofile.d` is a directory; plain `cp` exits 1).
4. **The RM module's tests run from a per-case copy in about 20 s per class** (`mvn -B test -Dtest=<Class>` in
   `hadoop-yarn-server-resourcemanager`, JDK 8, artifacts from `~/.m2`); `test-compile` alone takes about 20 s.
5. **The Hadoop build ignores test failures**: `mvn test` returns 0 with failing tests. A run script must read the surefire count
   (`Tests run: N, Failures: 0, Errors: 0`), not the exit code.
6. A pseudo-distributed cluster (NN, DN, RM, NM 12 GB) is up in about 20 s; an RM restart with the NM left running re-registers the
   node in about 26 s. Full C1–C4 cycle with three distributed-shell apps per run took 13 minutes.

## Method lessons

1. **`MockRM.launchAndRegisterAM` sends exactly two node heartbeats** (`MockRM.java:915-927`), and the capacity scheduler here assigns
   one container per heartbeat. With several apps submitted, the heartbeats go to the earlier apps' AMs and the target attempt stays
   SCHEDULED. Heartbeat until the attempt is ALLOCATED, then `rm.sendAMLaunched(...)`, `am.registerAppAttempt()`.
2. **The auto-queue policy logs its operand.** With
   `log4j.logger.org.apache.hadoop.yarn.server.resourcemanager.scheduler.capacity.queuemanagement=DEBUG`, the monitor
   (`QueueManagementDynamicEditPolicy`, every 1.5 s) prints `absCapacity, leafQueueAbsoluteCapacity, deactivatedCapacity,
   absChildActivatedCapacity, availableCapacity` for the managed parent: a direct cluster-side observation of the check's operand.
   After apps are killed `deactivatedCapacity` becomes non-zero; slice the log to the sampling window only.
3. **Distributed shell as a memory workload**: `-shell_script hog.sh` (which `exec`s `python3 hog.py ifchk-<user>`) gives one tagged
   process per container; `pgrep -f "hog.py ifchk-<u>"` + `ps -o rss=` measures RSS exactly (600 MiB payload → 607.9 MiB); a client
   per user with `HADOOP_USER_NAME=<u>`. Killed apps make the client log "Application failed to complete successfully" — expected.
4. For a negative estimate on a scheduler share, a **second knob that binds on the same resource** (here the template's
   `maximum-capacity`) is a cheap positive control with the same workload.

Harness to borrow from: `harness/yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous/`
(`cluster-run.py`: prechecks, distribution completion, instrument check, waits with timeouts, teardown on any exit; `selfcheck.py`:
independent re-parse of raw files).
