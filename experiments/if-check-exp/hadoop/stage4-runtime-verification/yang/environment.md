# Stage 4 — Hadoop environment (Yang's share)

Set up 2026-11-06 on the local node, which Yang named for this work. This is the first Hadoop
stage-4 environment. `PROCEDURE.md` and `CLAUDE.md` said stage 4 waits until an environment exists,
and this file is that environment, written at Yang's request. Safety rules:
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md#running-safely-on-shared-infrastructure)
(read "Cassandra" there as "Hadoop"; this file and [`copy-source.sh`](copy-source.sh) replace the
Cassandra ones for Hadoop).

## Moving to another node

This file describes **one** node. Before a stage-4 run, check `hostname` against the Node table below
and that `/mydata/yang-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2/bin/hadoop` exists. If either
fails, set the node up again before running anything:

1. §1 tools: JDK 8 and Maven 3.3+ (`sudo apt-get install -y openjdk-8-jdk maven` on Ubuntu if absent).
2. Pick a local disk of ~20 GB free or more (not NFS, not `/proj`); if it is not `/mydata`, use the same
   layout under it and say so here.
3. §2 `copy-source.sh <local-disk>/yang-s4/hadoop-base`, then §3's **full** build (~30 min, needs
   Maven Central; about 10 GB with `~/.m2`). Check `share/hadoop/yarn/` has ~19 jars.
4. Replace the Node table and tool versions below with the new node's (dated), so the file still
   describes the one node in use. Earlier results files keep their own environment record.

## Node

| Field | Value |
|---|---|
| Node | `node0.jason92-323989.misconfiguration-pg0.cloudlab.umass.edu` (the local node) |
| OS / kernel | Ubuntu 22.04.2 LTS / `5.15.0-198-generic` |
| CPU / RAM | 40 cores / 251 GiB |
| Local disk for runs | `/mydata` (`/dev/mapper/emulab-node0--bs`, 754 GB, ~709 GB free after the build) |
| Root disk | `/dev/sda3`, 63 GB (home directory and `~/.m2`); not for run data |
| Shared disk | `/proj/misconfiguration-PG0`, NFS — never build or write run data here |
| SSH to localhost | **not** set up (no passwordless key). Start daemons with `hdfs --daemon start …` / `yarn --daemon start …`, not `start-dfs.sh`/`start-yarn.sh`. |

## 1. Tools (already installed on this node)

| Tool | Version | Path |
|---|---|---|
| JDK 8 (build and run) | `1.8.0_504` | `/usr/lib/jvm/java-8-openjdk-amd64` — set `JAVA_HOME` to this |
| JDK 11 (default `java`) | `11.0.32.1` | `/usr/lib/jvm/java-11-openjdk-amd64` — not used for Hadoop runs |
| Maven | 3.6.3 | `/usr/bin/mvn` |
| `jcmd`, `jstat`, `jps` | with each JDK | use the JDK 8 ones (`$JAVA_HOME/bin/…`) against JDK 8 daemons |

`BUILDING.txt:4-8` asks for JDK 1.8 and Maven 3.3+. Maven Central is reachable from the node.

## 2. Copy the source to local disk

Never build in the repository's `systems/hadoop/source/`.

```bash
git -C <repo> status --short systems/hadoop/source        # must print nothing
<repo>/experiments/if-check-exp/hadoop/stage4-runtime-verification/yang/copy-source.sh /mydata/yang-s4/<dir>
git -C /mydata/yang-s4/<dir> describe --tags               # rel/release-3.4.2 (local one-commit baseline)
```

Use a separate copy per case and run (`/mydata/yang-s4/<stem>-run1/`) for anything that adds test
files. The base copy `/mydata/yang-s4/hadoop-base/` holds the built distribution (§3); do not add
files to it.

## 3. Build (done once, 2026-11-06, from repository commit `bd784dba`)

```bash
cd /mydata/yang-s4/hadoop-base
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export YARN_IGNORE_ENGINES=true      # see the note below
mvn -B install -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true -T 8
```

- **Result (final, 2026-11-06):** a full build with `YARN_IGNORE_ENGINES=true` set from the start: BUILD
  SUCCESS in 26 min (`/mydata/yang-s4/build-base-full.log`). Distribution:
  `/mydata/yang-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2/` (and `.tar.gz`). `bin/hadoop version`
  → `Hadoop 3.4.2`; `share/hadoop/yarn/` has 19 YARN jars incl. `hadoop-yarn-applications-distributedshell-3.4.2.jar`.
  All modules are installed to `~/.m2/repository` as `3.4.2`, so a per-case copy can build and test one
  module with `mvn -pl <module> test -Dtest=<Class>#<method>` without a full build. **Surefire failures do
  not fail the build step's exit code in every setup: read the surefire report counts** (lesson from the
  first case, see [`case-notes.md`](case-notes.md)).
- **Do not resume a dist build with `-rf`.** The first attempt (no `YARN_IGNORE_ENGINES`) failed at the
  catalog webapp; resuming with `-rf :hadoop-yarn-applications-catalog-webapp` gave BUILD SUCCESS but a
  distribution with **no YARN module jars** (the YARN assembly only packages modules in the current
  reactor). The first case (order 2) ran on that distribution with YARN jars copied in from `~/.m2` by its
  `cluster-run.py`; its results are unaffected. Logs of those builds: `build-base.log`, `build-base-2.log`,
  `build-base-3.log` under `/mydata/yang-s4/`.
- **Node-engine workaround.** Without `YARN_IGNORE_ENGINES=true` the build fails at
  `hadoop-yarn-applications-catalog-webapp` (`yarn install`: `color@5.0.3: The engine "node" is
  incompatible with this module. Expected version ">=18". Got "12.22.1"`). The pinned
  frontend plugin installs Node 12, and an npm dependency has since moved to Node 18. The variable
  only makes yarn v1 skip that check; no Hadoop source or pom is changed. The webapp is the YARN app
  catalog UI, which no case uses. (`hadoop-yarn-project` depends on its war, so it cannot just be
  skipped.)
- `ERROR: <module> has missing dependencies: …` lines from the dist layout check (`hadoop-aliyun`,
  `dynamometer`, …) are warnings; the build still succeeds.
- Distributed shell jar: `<dist>/share/hadoop/yarn/hadoop-yarn-applications-distributedshell-3.4.2.jar`
  (also in `~/.m2`). MapReduce examples: `<dist>/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.4.2.jar`.

## 4. Cluster tier (pseudo-distributed, one node)

- Copy the distribution per case: `cp -a <dist> /mydata/yang-s4/<stem>-run1/hadoop` so its `etc/hadoop`
  can be edited without touching the base.
- `HADOOP_CONF_DIR`, `HADOOP_LOG_DIR`, `HADOOP_PID_DIR`, `hadoop.tmp.dir`, `dfs.namenode.name.dir`,
  `dfs.datanode.data.dir`, `yarn.nodemanager.local-dirs`, `yarn.nodemanager.log-dirs` all go under
  `/mydata/yang-s4/<stem>-run1/`.
- Start: `hdfs --daemon start namenode|datanode`, `yarn --daemon start resourcemanager|nodemanager`
  (after `hdfs namenode -format -nonInteractive`). Stop each with `--daemon stop`.
- Default ports (8020/9870/9864/9866/8088/8030–8032/8042) were free on 2026-11-06; check with
  `ss -ltn` before starting.
- Users: simple auth; a "user" is set with `HADOOP_USER_NAME=<name>` on the client side.
- **After every run:** `jps` (JDK 8) and `ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode|[R]esourceManager|[N]odeManager'`
  must show no Hadoop daemon or container left.

## Undo

`rm -rf /mydata/yang-s4/<stem>-run*/` removes a case's working tree, daemons' data and logs.
`/mydata/yang-s4/hadoop-base/` and `~/.m2/repository/org/apache/hadoop/*/3.4.2/` are the shared
build; keep them for later cases.
