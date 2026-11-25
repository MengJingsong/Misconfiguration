# Stage 4 — Hadoop environment (Jingsong's share)

Set up 2026-11-06 on three nodes Jingsong named for this work (`pc41`, `pc39`, `pc29`), following
Yang's [`../yang/environment.md`](../yang/environment.md) (same build, different paths and nodes).
**Current nodes (2026-11-24):** `pc91`, `pc82`, `pc72`, `pc75`, `pc99`, each set up with [`setup-node.sh`](setup-node.sh);
the 2026-11-06 nodes are gone (see "Nodes").
Safety rules: [`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md#running-safely-on-shared-infrastructure)
(read "Cassandra" there as "Hadoop"). Scripts here: [`setup-node.sh`](setup-node.sh) (§1–3 on one node) and
[`copy-source.sh`](copy-source.sh) (same as Yang's).

## Before a run / moving to another node

Before a stage-4 run, check `hostname` against the Node table and that
`/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2/bin/hadoop` exists on the node. If not,
run `setup-node.sh` on the node (it installs JDK 8 + Maven if absent, creates `/mydata/jingsong-s4` with
`sudo` because `/mydata` is root-owned on a fresh node, copies the source and runs the **full** build;
never resume a dist build with `-rf`, see Yang's §3). Then update the Node table (dated).

## Nodes (2026-11-24)

All five: CloudLab experiment `jason92-326665` (`nodeN.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu`,
`pcNN.cloudlab.umass.edu`), Ubuntu 22.04.2 LTS, kernel `5.15.0-203-generic`, 125 GiB RAM, user `jason92`. Each was set
up on 2026-11-24 with `setup-node.sh` (JDK 8 + Maven installed, source copied, full build); build times below are the
`build-base-full.time` line on the node (`ssh <node> cat /mydata/jingsong-s4/build-base-full.time`).

| Node | Experiment name | Cores | Local disk for runs | Root disk | Built |
|---|---|---|---|---|---|
| `pc91` | `node0` | 32 | `/mydata` (753 GB, ~706 GB free) | `/dev/sda3` 63 GB, ~54 GB free | 2026-11-24, 1457 s (24:17 min), BUILD SUCCESS |
| `pc82` | `node1` | 40 | `/mydata` (753 GB, ~705 GB free) | `/dev/sda3` 63 GB, ~54 GB free | 2026-11-24, 1869 s (31:09 min), BUILD SUCCESS |
| `pc72` | `node2` | 40 | `/mydata` (753 GB, ~707 GB free) | `/dev/sda3` 63 GB, ~54 GB free | 2026-11-24, 1996 s (33:16 min), BUILD SUCCESS |
| `pc75` | `node3` | 40 | `/mydata` (753 GB, ~703 GB free) | `/dev/sda3` 63 GB, ~54 GB free | 2026-11-24, 1858 s (30:58 min), BUILD SUCCESS |
| `pc99` | `node4` | 32 | `/mydata` (753 GB, ~695 GB free) | `/dev/sda3` 63 GB, ~54 GB free | 2026-11-24, 1478 s (24:38 min), BUILD SUCCESS |

Free space as checked after the 2026-11-24 runs (run folders included).

- **The 2026-11-06 nodes `pc41`, `pc39`, `pc29` (experiment `jason92-323989`) are gone**, with their run folders. They
  had built in 25:29, 30:21 and 30:31 min. `pc41` was shared with Yang; none of the current nodes is.
- The session node (`node0.jason92-327358`, not in the table) reaches all five with `ssh pcNN`. SSH to `localhost` on a
  node does **not** work: start daemons with `hdfs --daemon start …` / `yarn --daemon start …`, not
  `start-dfs.sh`/`start-yarn.sh`.
- `/proj/misconfiguration-PG0` (NFS) is mounted on the nodes: the repository and its scripts are reachable from each.
  Never build or write run data there.
- `ulimit -n` is 1024 on all five: raise it in the shell that starts daemons if a case needs more.
- `pc75` also has `cmake`, `zlib1g-dev`, `libssl-dev` and `pkg-config` (installed 2026-11-24 for the native build of the
  `CachePoolInfo_limit` case, which needed `libhadoop` for `mlock`); **2026-11-25:** `pc91` (order 12) and `pc82` (order 23)
  have them too, installed for the same native build; `pc72` and `pc99` do not.
- **2026-11-25 (deferred stage 4 of orders 6–25):** 15 cases ran on `pc91`, `pc82`, `pc72`, `pc75`; each run left only
  small logs and its harness in `/mydata/jingsong-s4/<stem>-run1/` (a few MB each; order 20's are 16 MB on `pc72`). Orders
  6, 14 and 22 did not run: **`pc99`'s node lock `/mydata/s4/NODE-LOCK` is held by `jingsong-o70-stage4` (2026-11-24
  21:54 MST)**, left by a Cassandra extension session that returned no result; no process runs on `pc99` (checked
  2026-11-25 09:10 EST). Confirm it is stale and remove it (`ssh pc99 'rm -rf /mydata/s4/NODE-LOCK'`) before using `pc99`.
  `pc99` also still holds order 13's interrupted run folder of 2026-11-24
  (`/mydata/jingsong-s4/dfs.client.write.byte-array-manager.count-limit-recycle-maxAllocated-run1`; order 13 finished on
  `pc75`), which can be deleted.
- One case per node at a time. Run folders of the interrupted 2026-11-24 batch are listed in `HANDOFF-Jingsong.md`
  (Hadoop log, 2026-11-24) and in the stage-3 `_INDEX.md` rows.

## 1. Tools

| Tool | Version | Path |
|---|---|---|
| JDK 8 (build and run) | `1.8.0_514` (2026-11-24 nodes; `1.8.0_504` on the 2026-11-06 nodes) | `/usr/lib/jvm/java-8-openjdk-amd64` — set `JAVA_HOME` to this |
| JDK 11 (default `java` on the nodes) | `11.0.33` (2026-11-24; was `11.0.32.1`) | not used for Hadoop runs. `JAVA_HOME` is not set in a non-login `ssh pcNN '<cmd>'` shell: export it to the JDK 8 path every time |
| Maven | 3.6.3 | `/usr/bin/mvn` |

On every node JDK 8 and Maven are installed by `setup-node.sh` (`apt-get install openjdk-8-jdk maven`)
when absent (2026-11-24 on the five current nodes). Maven Central is reachable from the nodes. `jq` is not installed (use `python3 -I`).

## 2. Copy the source to local disk

Never build in the repository's `systems/hadoop/source/`.

```bash
git -C <repo> status --short systems/hadoop/source        # must print nothing
<repo>/experiments/capacity-enforcement-exp/hadoop/stage4-runtime-verification/jingsong/copy-source.sh /mydata/jingsong-s4/<dir>
```

One copy per case and run (`/mydata/jingsong-s4/<stem>-run1/`) for anything that adds test files. The
base copy `/mydata/jingsong-s4/hadoop-base/` holds the built distribution; do not add files to it.

## 3. Build (once per node; first 2026-11-06 at repository commit `38acb6bf`, current nodes 2026-11-24)

```bash
cd /mydata/jingsong-s4/hadoop-base
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 YARN_IGNORE_ENGINES=true
mvn -B install -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true -T 8   # log: /mydata/jingsong-s4/build-base-full.log
```

Distribution: `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2/` (and `.tar.gz`).
Check: `bin/hadoop version` → `Hadoop 3.4.2`; `share/hadoop/yarn/` has 19 jars.

| Node | Result |
|---|---|
| `pc91` (2026-11-24) | BUILD SUCCESS, 1457 s (Maven wall clock 24:04 min); `Hadoop 3.4.2`; 19 YARN jars |
| `pc82` (2026-11-24) | BUILD SUCCESS, 1869 s (31:06 min); `Hadoop 3.4.2`; 19 YARN jars |
| `pc72` (2026-11-24) | BUILD SUCCESS, 1996 s (33:04 min); `Hadoop 3.4.2`; 19 YARN jars |
| `pc75` (2026-11-24) | BUILD SUCCESS, 1858 s (30:55 min); `Hadoop 3.4.2`; 19 YARN jars |
| `pc99` (2026-11-24) | BUILD SUCCESS, 1478 s (24:26 min); `Hadoop 3.4.2`; 19 YARN jars |

The 2026-11-06 builds on `pc41`/`pc39`/`pc29` (gone) took 25:29, 30:21 and 30:31 min.

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
