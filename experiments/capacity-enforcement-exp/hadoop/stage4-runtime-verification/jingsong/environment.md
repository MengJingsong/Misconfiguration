# Stage 4 — Hadoop environment (Jingsong's share)

Set up 2026-11-06 on three nodes Jingsong named for this work (`pc41`, `pc39`, `pc29`), following
Yang's [`../yang/environment.md`](../yang/environment.md) (same build, different paths and nodes).
Safety rules: [`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md#running-safely-on-shared-infrastructure)
(read "Cassandra" there as "Hadoop"). Scripts here: [`setup-node.sh`](setup-node.sh) (§1–3 on one node) and
[`copy-source.sh`](copy-source.sh) (same as Yang's).

## Before a run / moving to another node

Before a stage-4 run, check `hostname` against the Node table and that
`/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2/bin/hadoop` exists on the node. If not,
run `setup-node.sh` on the node (it installs JDK 8 + Maven if absent, creates `/mydata/jingsong-s4` with
`sudo` because `/mydata` is root-owned on a fresh node, copies the source and runs the **full** build;
never resume a dist build with `-rf`, see Yang's §3). Then update the Node table (dated).

## Nodes (2026-11-06)

All three: CloudLab experiment `jason92-323989` (`*.misconfiguration-pg0.cloudlab.umass.edu`),
Ubuntu 22.04.2 LTS, kernel `5.15.0-198-generic`, 40 cores, 251 GiB RAM, user `jason92`.

| Node | Experiment name | Local disk for runs | Root disk | Built |
|---|---|---|---|---|
| `pc41` (the local node) | `node0` | `/mydata` (754 GB, ~697 GB free after the build) | `/dev/sda3` 63 GB, ~23 GB free | 2026-11-06, 25:29 min, BUILD SUCCESS |
| `pc39` | `node1` | `/mydata` (754 GB, ~708 GB free after the build) | `/dev/sda3` 63 GB, ~54 GB free | 2026-11-06, 30:21 min, BUILD SUCCESS |
| `pc29` | `node2` | `/mydata` (754 GB, ~708 GB free after the build) | `/dev/sda3` 63 GB, ~54 GB free | 2026-11-06, 30:31 min, BUILD SUCCESS |

- **`pc41` is also Yang's stage-4 node** (`node0`, `/mydata/yang-s4/`, same Unix user and the same
  `~/.m2`). Never touch `/mydata/yang-s4/`. Before starting daemons on `pc41`, check `ss -ltn` and `jps`
  for a run of Yang's; if one is up, use non-default ports for every daemon (record them in the results
  file) or run on `pc39`/`pc29`. Jingsong's build re-installed the identical `3.4.2` artifacts into the
  shared `~/.m2`.
- SSH: `ssh pc39`, `ssh pc29` from `pc41` work (stanzas in `~/.ssh/config`, shared deploy key). SSH to
  `localhost` does **not** (no key): start daemons with `hdfs --daemon start …` / `yarn --daemon start …`,
  not `start-dfs.sh`/`start-yarn.sh`.
- `/proj/misconfiguration-PG0` (NFS) is mounted on all three: the repository and its scripts are
  reachable from each node. Never build or write run data there.
- `ulimit -n` is 1024 on `pc39`/`pc29`: raise it in the shell that starts daemons if a case needs more.

## 1. Tools

| Tool | Version | Path |
|---|---|---|
| JDK 8 (build and run) | `1.8.0_504` | `/usr/lib/jvm/java-8-openjdk-amd64` — set `JAVA_HOME` to this |
| JDK 11 (default `java` on all three) | `11.0.32.1` | not used for Hadoop runs. `JAVA_HOME` is not set in a non-login `ssh pcNN '<cmd>'` shell: export it to the JDK 8 path every time |
| Maven | 3.6.3 | `/usr/bin/mvn` |

On `pc39`/`pc29` JDK 8 and Maven were installed by `setup-node.sh` (`apt-get install openjdk-8-jdk maven`)
on 2026-11-06. Maven Central is reachable from the nodes. `jq` is not installed (use `python3 -I`).

## 2. Copy the source to local disk

Never build in the repository's `systems/hadoop/source/`.

```bash
git -C <repo> status --short systems/hadoop/source        # must print nothing
<repo>/experiments/capacity-enforcement-exp/hadoop/stage4-runtime-verification/jingsong/copy-source.sh /mydata/jingsong-s4/<dir>
```

One copy per case and run (`/mydata/jingsong-s4/<stem>-run1/`) for anything that adds test files. The
base copy `/mydata/jingsong-s4/hadoop-base/` holds the built distribution; do not add files to it.

## 3. Build (once per node, 2026-11-06, repository commit `38acb6bf`)

```bash
cd /mydata/jingsong-s4/hadoop-base
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 YARN_IGNORE_ENGINES=true
mvn -B install -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true -T 8   # log: /mydata/jingsong-s4/build-base-full.log
```

Distribution: `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2/` (and `.tar.gz`).
Check: `bin/hadoop version` → `Hadoop 3.4.2`; `share/hadoop/yarn/` has 19 jars.

| Node | Result |
|---|---|
| `pc41` | BUILD SUCCESS, 25:29 min; `Hadoop 3.4.2`; 19 YARN jars |
| `pc39` | BUILD SUCCESS, 30:21 min; `Hadoop 3.4.2`; 19 YARN jars |
| `pc29` | BUILD SUCCESS, 30:31 min; `Hadoop 3.4.2`; 19 YARN jars |

The `YARN_IGNORE_ENGINES=true` and "surefire failures do not fail `mvn test`" notes in Yang's §3 apply:
read surefire counts, not exit codes. All modules are in `~/.m2/repository` as `3.4.2` on each node, so a
per-case copy can run `mvn -pl <module> test -Dtest=<Class>#<method>` without a full build.

## 4. Cluster tier (pseudo-distributed, one node)

As Yang's §4 with `/mydata/jingsong-s4/<stem>-run1/` in place of `/mydata/yang-s4/…`:
copy the distribution per case (`cp -a <dist> /mydata/jingsong-s4/<stem>-run1/hadoop`), put
`HADOOP_CONF_DIR`, logs, PIDs, `hadoop.tmp.dir` and all data/local/log dirs under the run folder,
`hdfs namenode -format -nonInteractive`, start/stop each daemon with `--daemon`. `cp -r` the
configuration (`etc/hadoop/shellprofile.d` is a directory). Two cases on one node need separate run
folders and ports. **After every run:** no Hadoop daemon or container left
(`ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode|[R]esourceManager|[N]odeManager'`).

## Undo

`rm -rf /mydata/jingsong-s4/<stem>-run*/` removes a case's working tree, data and logs.
`/mydata/jingsong-s4/hadoop-base/` and `~/.m2/repository/org/apache/hadoop/*/3.4.2/` are the shared build.
