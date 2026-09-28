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

## Logs

Run 1's logs are in `~/stage4-logs/` on the node, outside the repo:
`apt-install.log`, `clone.log`, `build-test.log`.

## Undo

```bash
sudo apt-get remove -y openjdk-11-jdk ant && sudo apt-get autoremove -y
rm -rf ~/cassandra-run<N> ~/.m2 ~/stage4-logs
```
