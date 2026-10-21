# Stage 4 — environment setup

The steps that worked on 2026-09-28. Follow the same steps for every later run, so every run uses the same versions.
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

JDK 11 is `build.xml`'s `java.default` (11 and 17 are both supported). No
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

Ports the node and agent use: 7000, 7199, 9042, and 9091 (Byteman `listener:true`); check they are free before a run. The second node's setup is in section 5. The node's data and logs are under the clone (`data/`, `logs/`), on local disk. Each run is driven by a script of its own that logs every command (see the stage-4 README, "Run 1").

## 5. More than one node

Some designs need a second node. Set it up like the first (sections 1 and 2), then `ant jar` instead of `ant build-test` if it
runs no tests (about 2.5 minutes). The control addresses are public and nodes run no firewall, so restrict the internode
port to the nodes in use (in-memory rules, gone on reboot; run on each node with `PEER` and `SELF` set to the two addresses;
read an address with `ip -br -4 addr show eno1`):

```bash
sudo iptables -A INPUT -p tcp --dport 7000 -s $PEER -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 7000 -s $SELF -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 7000 -j DROP
```

Undo: the same three commands with `-D` in place of `-A`, or reboot. In each node's `conf/cassandra.yaml` a ring needs the
same `cluster_name`, the seed node's control address under `seeds`, and each node's own control address as `listen_address`;
`rpc_address` can stay `localhost` when stress, `cqlsh` and `nodetool` run on the measured node.

## 6. Lessons that apply to any run

- **Starting a node.** Wait for `nodetool status` to show `UN` **and** `nodetool statusbinary` to print `running`; on a restart `UN`
  appears several seconds before the client port, and a client started in between fails with "Cannot connect". A script that starts
  a node should fail at once if the daemon dies during start (`pgrep`), not wait out its timeout.
- **A Byteman rule on a JDK class needs `boot:`.** A rule on `java.nio.ByteBuffer` (or any `java.*` class) runs in the bootstrap class
  loader, which cannot see Byteman's classes, so the JVM dies at start-up with `NoClassDefFoundError:
  org/jboss/byteman/rule/exception/EarlyReturnException`. Use `-javaagent:<byteman jar>=boot:<byteman jar>,script:<rules>,listener:true`.
  Rules on Cassandra classes do not need it.
- **`ssh -n` closes standard input**, so a script fed to `ssh host 'bash -s' <<EOF` silently does nothing: leave `-n` off when piping a
  script in, and keep it on for plain commands.
- **Run values as separate background ssh commands**, one after another; wait for each with a background `until` loop or the Monitor
  tool, not a foreground `sleep`.
- **Clocks.** The node's shell is in MDT while Cassandra's log lines are in UTC; use epoch milliseconds (`date +%s%3N`) to line things up.
- **Reading logs.** In `system.log` a level starts the line (`ERROR  [thread] ...`), so `grep ' ERROR '` finds nothing; use `grep '^ERROR'`.
- **`cassandra-stress`** prints `Total errors   :   0 [insert: 0]` and `Total partitions`; there is no `Total operation count` line. It prints
  every failed write's error (megabytes for a long failing run), so pull only its header and results block.
- **Rejected writes can be expensive to log.** A rejected write that logs an `ERROR` with a stack (about 1.7 KB) at full speed fills the
  log within seconds: throttle the writer.
- **A bulk write through the mapped commit log can stall every logged write for 10 to 16 s** at the first periodic sync; settle the node
  (probe until a run of prompt writes) before a control that depends on write latency.
- **`JVM_EXTRA_OPTS` is scoped to the `bin/cassandra` command**, never exported: an agent on a client JVM (`nodetool`, stress, `cqlsh`)
  would clash with the node's Byteman listener on port 9091.

## 7. Nodes (checked 2026-10-07; updated 2026-10-13 and 2026-10-20)

All three answered over SSH (`ssh -o BatchMode=yes jason92@<host> ...`, with the short names `pcNN.cloudlab.umass.edu`; the long `node0.jason92-…` names fail host-key
verification from the tool shell). CloudLab experiments expire, so check again before a run. A node's home may hold directories from earlier runs; they are not yours.
Work in a fresh directory named for your run, and never open, reuse or delete the others.

| Node | State | Use |
|---|---|---|
| `pc66` (`node0.jason92-317394...`, `198.22.255.77`) | 40 cores, 125 GiB, 49 GB free; JDK 11.0.32.1 and Ant 1.10.12 installed; `~/cassandra-run1` at `cassandra-5.0.9`; home holds earlier runs' directories | the quickest choice: sections 1 to 3 are done |
| `pc57` (`node0.jason92-319347...`, `198.22.255.67`, LAN `10.10.1.1`) | **set up 2026-10-13:** JDK 11.0.32.1, Ant 1.10.12, `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54210`), `ant build-test` successful in 1 min 42 s; logs `~/stage4-logs/{apt-install,clone,build-test}.log`; 32 cores, 251 GiB, ~56 GB free on `/`; passwordless `sudo`, Python 3.10 | sections 1 to 3 are done; the run node while `pc66` is unreachable |
| `pc50` (`node1.jason92-319347...`, `198.22.255.60`, LAN `10.10.1.2`) | **set up 2026-10-13**, same as `pc57` (`ant build-test` successful in 1 min 55 s); the two share the `10.10.1.0/24` LAN | second node for a ring (section 5), or a unit-tier node |

`pc57` and `pc50` were added to `~/.ssh/known_hosts` on 2026-10-13 (ECDSA key `SHA256:qDJ4amzV…`); on 2026-10-13 `pc66` timed out on port 22. They present the same ED25519 key as `pc66` (`SHA256:qkFN/SvBkCeQfIkD5YilK7WgBOUyfXwZPIEyp0Q9hYY`). Until added, use
`ssh-keyscan -t ed25519 pcNN.cloudlab.umass.edu > kh` and `ssh -o UserKnownHostsFile=kh …`. `pc80` and `pc72` (experiment `…-318546`) are no longer used: `pc80` refuses the key.

**2026-10-20:** `pc57` was the run node (32 cores, 251 GiB, about 47 GB free on `/`; Ubuntu 22.04, `5.15.0-187-generic`, JDK 11.0.32.1, Ant 1.10.12). A fresh clone `~/cassandra-run4` at `cassandra-5.0.9` (`b5f2a54210`) was built with `ant build-test` in 1 min 33 s; `~/cassandra-run1` holds untracked test files from earlier cases, so use a fresh clone per case. `pc50` answered over SSH with JDK 11 and a built `~/cassandra-run1` (55 GB free). `pc66` was not checked.

**2026-10-20 (late): experiment `jason92-320876`, four nodes — the current set.** The experiments above (`…-317394`, `…-319347`) were not checked again and should be taken as gone. All four nodes are 40 cores and 251 GiB, run Ubuntu 22.04.2 with `5.15.0-187-generic`, have passwordless `sudo`, and run no `CassandraDaemon`. Checked 2026-10-20 22:55 MDT.

| Node | Name | Control address | LAN (`enp3s0f0np0`) | State | Use |
|---|---|---|---|---|---|
| `pc07` | `node0.jason92-320876…` | `198.22.255.17` | `10.10.1.1` | JDK 11.0.32.1, Ant 1.10.12, `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54210`); `ant build-test` passed in 1 min 55 s (logs `~/stage4-logs/{apt-install,clone,build-test}.log`); 55 GB free on `/`; home holds `~/stage4-logs/bsf`, `~/stage4-harness-run/bsf`, `~/stage4-bsf` (the `batch_size_fail_threshold` run) | the run node: sections 1 to 3 are done; sessions run here directly (no ssh) |
| `pc12` | `node1.jason92-320876…` | `198.22.255.22` | **none:** the interface is absent, and `10.10.1.2` (`node1` in `/etc/hosts`) does not answer | **set up 2026-10-20:** JDK 11.0.32.1, Ant 1.10.12, `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54210`); `ant build` 58 s and `ant build-test` 50 s `BUILD SUCCESSFUL` (logs `~/stage4-logs/{precheck,apt-install,clone,build,build-test}.log`); 55 GB free on `/`; Python 3.10.12; `ulimit -n` is **1024** soft (1048576 hard; run `ulimit -n 100000` before starting a node) | a unit-tier node, or a ring member over the control addresses only (section 5's firewall rules) |
| `pc06` | `node2.jason92-320876…` | `198.22.255.16` | `10.10.1.3` | **set up 2026-10-20:** JDK 11.0.32.1, Ant 1.10.12, `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54210`); `ant build` 1 min 2 s and `ant build-test` 49 s `BUILD SUCCESSFUL` (logs `~/stage4-logs/{precheck,apt-install,clone,build,build-test}.log`); 55 GB free on `/`; Python 3.10.12; `ulimit -n` is **1024** soft (1048576 hard; run `ulimit -n 100000` before starting a node) | second node for a ring (section 5) over the LAN |
| `pc13` | `node3.jason92-320876…` | `198.22.255.23` | `10.10.1.4` | **set up 2026-10-20:** JDK 11.0.32.1, Ant 1.10.12, `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54210`); `ant build` 1 min 1 s and `ant build-test` 51 s `BUILD SUCCESSFUL` (logs `~/stage4-logs/{precheck,apt-install,clone,build,build-test}.log`); 55 GB free on `/`; Python 3.10.12; `ulimit -n` is **1024** soft (1048576 hard; run `ulimit -n 100000` before starting a node) | third node for a ring over the LAN |

`pc12`, `pc06` and `pc13` were set up on 2026-10-20 (sections 1 to 3). Use a fresh clone per case if `~/cassandra-run1` has been used. When feeding a script to `ssh … 'bash -s' < script`, give `ant` `</dev/null`: it reads standard input and swallows the rest of the script.

**SSH from `pc07`:**
- Peers: `ssh -o IdentitiesOnly=yes -i /proj/misconfiguration-PG0/.ssh/id_ed25519 jason92@pcNN.cloudlab.umass.edu` works.
- `ssh pcNN` alone **fails** with `Permission denied (publickey)`. `~/.ssh/config`'s `setup-node: peer` stanzas name `/proj/misconfiguration-PG0/.ssh/cluster_ed25519`, which the peers do not accept. Either pass `-i …/id_ed25519` as above, or add `cluster_ed25519.pub` to each peer's `~/.ssh/authorized_keys`.
- GitHub: `id_ed25519` works for `git push` (the `github.com` stanza).

## Logs

Run 1's logs are in `~/stage4-logs/` on the node, outside the repo:
`apt-install.log`, `clone.log`, `build-test.log`; the cluster tier's are in `~/stage4-logs/cluster/`.

## Undo

```bash
sudo apt-get remove -y openjdk-11-jdk ant && sudo apt-get autoremove -y
rm -rf ~/cassandra-run<N> ~/.m2 ~/stage4-logs
```
