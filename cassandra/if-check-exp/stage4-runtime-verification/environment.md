# Stage 4 — environment setup

The steps that worked on 2026-09-28 (run 1 of `memtable_heap_space`). Follow
the same steps for run 2 and later cases, so every run uses the same versions.
Safety rules are in [`README.md`](README.md#running-safely-on-shared-infrastructure).

## Node

| Field | Value |
|---|---|
| Node | `node0.jason92-317394.misconfiguration-pg0.cloudlab.umass.edu` |
| OS / kernel | Ubuntu 22.04.2 LTS / `5.15.0-187-generic` |
| CPU / RAM | 40 cores / 125 GiB |
| Local disk | `/dev/sda3`, ext3, 63 GB (home directory lives here) |
| Shared disk | `/proj/misconfiguration-PG0`, NFS — never build or write run data here |

## 1. Install JDK 11 and Ant

A fresh node has no JDK or Ant, and its apt package lists are empty.

```bash
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y openjdk-11-jdk ant
```

Check:

```bash
java -version      # openjdk version "11.0.32.1" 2026-08-18
ant -version       # Apache Ant(TM) version 1.10.12
which jcmd jstack  # /usr/bin/jcmd, /usr/bin/jstack
```

JDK 11 is `build.xml`'s `java.default` (11 and 17 are both supported). These
are the same versions as the 2026-09-16 `HeapPoolTest` run on pc80. No
`JAVA_HOME` was needed: the package makes JDK 11 the `java` alternative.

## 2. Clone the source to local disk

Clone from the shared clone. Never build in the shared clone itself.

```bash
git clone --branch cassandra-5.0.9 /proj/misconfiguration-PG0/git-repos/cassandra-src ~/cassandra-run<N>
git -C ~/cassandra-run<N> rev-parse HEAD      # b5f2a54210d541339c2e7c17a794195cac0e67c2
git -C ~/cassandra-run<N> describe --tags     # cassandra-5.0.9
```

Use a separate clone per run (`~/cassandra-run1`, `~/cassandra-run2`), so
neither run's build or copied test files affect the other.

## 3. Build the tests

```bash
cd ~/cassandra-run<N>
ant build-test
```

- Took **2 min 24 s** and ended `BUILD SUCCESSFUL`.
- Needs internet: it downloads dependencies from Maven Central into `~/.m2`
  (148 MB). The build output in `build/` is 216 MB.
- Expected noise: `Option UseConcMarkSweepGC was deprecated` warnings. The
  `error_prone` lines are dependency names, not errors.

`ant testsome -Dtest.name=<class>` builds whatever is missing on its own, but
building first separates a build failure from a test failure.

## 4. Cluster tier (added 2026-09-29)

Nothing more to install: `ant build-test` (section 3) already builds what the cluster tier needs. Checked on node0:

| Tool | State |
|---|---|
| `tools/bin/cassandra-stress` | works from the clone (`build/classes/stress`) |
| `bin/cqlsh` | 6.2.0, runs on the system Python 3.10.12 |
| Byteman | `build/lib/jars/byteman-4.0.20.jar` and `byteman-submit-4.0.20.jar`, from the build itself |
| `bin/nodetool sjk mx -mg -b <bean> -f <one attribute>` | works; `-f` takes a single attribute, and each call starts a JVM |
| `jcmd <pid> GC.run`, `GC.heap_info`, `Thread.print` | work (same user) |

Ports the node and agent use: 7000, 7199, 9042, and 9091 (Byteman `listener:true`); check they are free before a run. The second node's setup is in section 5. The node's data and logs are under the clone (`data/`, `logs/`), on local disk. Runs are driven by a script that logs to `~/stage4-logs/cluster/<value>/`; see the case's `run1/cluster-run.sh`.

## 5. Second node for the cluster tier (added 2026-09-30)

`MAX_HINT_BUFFERS` needs a second node that has joined the ring and then been
stopped, so that node 1 writes hints for it (case §9c). Node 1 is node0 above;
node 2 is a separate CloudLab experiment on the same control subnet. Nothing on
node 2 is measured.

| Field | Node 1 | Node 2 |
|---|---|---|
| CloudLab node | `node0.jason92-317394` (`pc66`) | `node0.jason92-318546` (`pc80`) |
| Control address (`eno1`) | `198.22.255.77` | `198.22.255.91` |
| Tree | `~/cassandra-run1` | `~/cassandra-node2` |
| OS, cores, RAM, disk | Ubuntu 22.04.2, 40 cores, 125 GiB, 63 GB | the same |

The addresses belong to these experiments and change if they are rebuilt; read
them again with `ip -br -4 addr show eno1`. Node 2 also has an experiment LAN
(`10.10.1.1`), which node 1 does not; the ring uses the control addresses.

**Node 2 setup** — sections 1 and 2 unchanged (JDK 11.0.32.1, Ant 1.10.12, a
local clone named `~/cassandra-node2` at `b5f2a54`), then `ant jar` instead of
`ant build-test`, because node 2 runs no tests: **2 min 27 s**, `BUILD SUCCESSFUL`,
`build/` 217 MB, `~/.m2` 148 MB.

**Configuration.** Three lines in each node's `conf/cassandra.yaml`; everything
else stays at the tag's defaults (start from `conf/cassandra.yaml`, not
`cassandra_latest.yaml`):

```
cluster_name: 'stage4-hints'                 # both nodes
      - seeds: "198.22.255.77:7000"          # both nodes: node 1 is the seed
listen_address: <the node's own control address>
```

`rpc_address` stays `localhost`, so the client port (9042) and JMX (7199) listen
on `127.0.0.1` only. Stress, `cqlsh` and `nodetool` all run on node 1, as before.
Node 1's clone was reset for this: the heap run's two edits are saved in
`~/stage4-logs/heap-run-cassandra.yaml.diff` and its old `data/` was moved to
`data.heap-run-2026-09-29` (2.4 GB). A per-run change on top of these three lines
(for example the second-knob arm's `max_mutation_size`) goes in the run's
`cassandra.yaml` diff, which every run records.

**Firewall.** The control addresses are public and neither node runs a firewall,
so the internode port is restricted to the two nodes (in-memory rules, gone on
reboot; run on each node with `PEER` and `SELF` set to the two addresses):

```bash
sudo iptables -A INPUT -p tcp --dport 7000 -s $PEER -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 7000 -s $SELF -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 7000 -j DROP
```

Undo: the same three commands with `-D` in place of `-A`, or reboot.

**Checked 2026-09-30.** A setup check, not a stage-4 reading. Logs are in
`~/stage4-logs/hints/second-node/` on node 1 and `~/stage4-logs/second-node/` on
node 2.

| Step | Result |
|---|---|
| Node 1 alone | `UN` after about 42 s; 7000 on `198.22.255.77`, 9042 and 7199 on `127.0.0.1` |
| Node 2 started | both `UN` after about 60 s |
| `keyspace1`, RF = 2, `cassandra-stress write n=1000` | 0 errors; both nodes own 100% |
| Node 2 stopped (`nodetool stopdaemon`) | node 1 shows it `DN` within about 4 s |
| Node 1 restarted alone, node 2 still stopped; `write n=2000`, 1 KiB columns, 16 threads | 0 errors; `TotalHints` 0 → 2000; a 10.4 MB hint file named for node 2's host ID, about 5.2 KB per hint; `HintsInProgress` 0 |
| Both stopped; `data/` and `logs/` removed | no daemon on either; 0 `ERROR` lines in either `system.log` |

**Starting node 1 for a run.** Wait for `nodetool status` to show `UN` **and**
`nodetool statusbinary` to print `running`. On a restart `UN` appears first (about
9 s) and the client port a few seconds later; a stress client started in between
fails with "Cannot connect".

**Ring procedure**, as in case §9c: the first time only, start both nodes, wait
for two `UN`, create `keyspace1` with RF = 2 and write the stress table, stop node 2
and wait until node 1 shows it `DN`. After that node 2 stays stopped with its data
untouched, and each capacity value restarts node 1 only. Both trees were left with
no `data/` or `logs/`; `results/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS/run1/ring.sh` (run from the workstation, once) performs the first-time step and leaves both nodes stopped, and `run1/cluster-run.sh` then restarts node 1 alone for every capacity value.

**Used for the cluster tier, 2026-09-30** (`MAX_HINT_BUFFERS`, results §4). `run1/ring.sh` formed the ring (two `UN` after 85 s, 2.5 min in
all) and left both nodes stopped. `run1/cluster-run.sh value <label>` then ran each capacity value, about 2.5 min each (`ROWS`, `THREADS`,
`HOLD_MS`, `B_SECONDS`, `A_TIMEOUT` are overridable environment variables). Every value started node 1 alone with the ring's `data/` in place
and stopped it at the end; the script removes `data/hints/*`, moves `logs/` aside, and puts the yaml back to the tag plus the three ring edits.
Lessons that generalize:

- **A Byteman rule on a JDK class needs `boot:`.** A rule on `java.nio.ByteBuffer` (or any `java.*` class) runs in the bootstrap class loader,
  which cannot see Byteman's classes, so the JVM dies in start-up with `NoClassDefFoundError: org/jboss/byteman/rule/exception/EarlyReturnException`.
  Use `-javaagent:<byteman jar>=boot:<byteman jar>,script:<rules>,listener:true`. Rules on Cassandra classes do not need it.
  `run1/diag-alloc/diag-alloc.btm` (one line per `allocateDirect` call, with the stack) is a working example.
- A script that starts a node should fail at once if the daemon dies during start (`pgrep`), not wait out its 240 s timeout.
- Run the values as separate background ssh commands, one after another; a failed value stops its own stress client and node 1, and the next
  can start at once.

**State after the run.** Both nodes are stopped and no stress client is left. Node0's `~/cassandra-run1/data/` (4.4 GB) holds the ring (`keyspace1`, 4.2 GB of
table data from the stress writes) and the diagnostic's hints (226 MB); `logs/` is the diagnostic's; `data.heap-run-2026-09-29/` (2.4 GB) is still there. `pc80`'s `~/cassandra-node2/data/`
is the ring member's data and must stay while this ring is used. To start a value again: nothing to reset, the script does it. To rebuild the ring:
delete `data/` on both nodes and run `ring.sh`. The internode-port firewall rules are in place on both (in memory; re-apply if a node reboots).

**Undo (node 2).** `sudo apt-get remove -y openjdk-11-jdk ant && sudo apt-get autoremove -y`;
`rm -rf ~/cassandra-node2 ~/.m2 ~/stage4-logs`; and the firewall rules above.

## Logs

Run 1's logs are in `~/stage4-logs/` on the node, outside the repo:
`apt-install.log`, `clone.log`, `build-test.log`; the cluster tier's are in `~/stage4-logs/cluster/`.

## Undo

```bash
sudo apt-get remove -y openjdk-11-jdk ant && sudo apt-get autoremove -y
rm -rf ~/cassandra-run<N> ~/.m2 ~/stage4-logs
```
