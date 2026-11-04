# Stage 4 — environment of the advisor's machine (`advisor-run`)

The advisor's stage-4 runs use this machine, not the CloudLab nodes in [`environment.md`](environment.md). Results from the two
are not compared; every results file records its own §2. Safety rules are in [`README.md`](README.md#running-safely-on-shared-infrastructure);
paths below replace the CloudLab ones (`~/cassandra-run<N>`, `~/stage4-logs`).

## Node (step E, recorded 2026-10-24)

| Field | Value |
|---|---|
| Node | `yangwang-mbp` (the advisor's laptop), single host |
| OS / kernel | macOS 27.0.1 (build 26A434) / Darwin 27.0.0, arm64 (Apple T6000) |
| CPU / RAM | 10 cores / 32 GiB |
| Disk | internal SSD, APFS (`/dev/disk3s1`), 460 GiB, about 163 GiB free on 2026-10-24 |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64), `$(/usr/libexec/java_home -v 11)`; `jcmd`, `jmap`, `jstack`, `jps` in its `bin/` |
| Ant | 1.10.18 (`/opt/homebrew/bin/ant`) |
| Python | 3.8.11 (`/opt/homebrew/bin/python3`); `bin/cqlsh` works |
| Loopback | `127.0.0.1`–`127.0.0.3` on `lo0` (`.2` and `.3` added by the user with `sudo ifconfig lo0 alias 127.0.0.N up` on 2026-10-24; gone after a reboot — re-check with `ifconfig lo0` before a ring run) |
| Free ports (2026-10-24) | 7000, 7199, 9042, 9091 |

## Machine-specific constraints

- **No `mkdir` in `$HOME`** (a policy on this machine; `Operation not permitted` even outside the tool sandbox). All stage-4 files live
  under **`W=~/Library/Caches/stage4`**: run clones `$W/cassandra-run<N>`, logs `$W/logs/`, Maven cache `$W/m2`, a fake home `$W/home`.
- **Network goes through a proxy at `localhost:10054`.** Java ignores the `*_proxy` variables and the Maven resolver ignores JVM proxy
  properties, so `$W/env.sh` passes both, and `$W/home/.m2/settings.xml` holds the resolver's proxy and `localRepository`.
- **No `setsid`.** Start a node as a tracked background process (`bin/cassandra -f > log 2>&1 < /dev/null`, run in the background) or
  with `nohup … &` followed by a `disown`; a subshell `( … & )` launched from a short-lived shell was killed with it.
- **No tmpfs, and no writable disk image** (checked 2026-10-24 by the `cdc_total_space` run): `hdiutil create` fails with
  `Operation not permitted`; `diskutil image create --fs APFS` creates and mounts an image but nothing can be written to the mounted
  volume. A design that needs a filesystem of fixed, known size cannot run that arm here: record it as `not run: no fixed-size
  filesystem on this machine`.
- **The tool sandbox** blocks writes outside the repo: commands that touch `$W` run unsandboxed.
- The built version string is `5.0.9-SNAPSHOT` (a build from the tag without the release flag); the clone is at `b5f2a54210`, tag `cassandra-5.0.9`.

## Setup (done 2026-10-24)

```bash
source ~/Library/Caches/stage4/env.sh       # sets W, JAVA_HOME, PATH, ANT_OPTS (user.home=$W/home + proxy)
git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run<N>
git -C $W/cassandra-run<N> rev-parse HEAD   # b5f2a54210d541339c2e7c17a794195cac0e67c2
cd $W/cassandra-run<N> && ant -Dlocal.repository=$W/m2 build-test
```

`$W/env.sh`:

```bash
export W=~/Library/Caches/stage4
export JAVA_HOME=$(/usr/libexec/java_home -v 11)
export PATH=$JAVA_HOME/bin:$PATH
export ANT_OPTS="-Duser.home=$W/home -Dhttps.proxyHost=localhost -Dhttps.proxyPort=10054 -Dhttp.proxyHost=localhost -Dhttp.proxyPort=10054"
```

Do not put `-Dhttp.nonProxyHosts=a|b` in `ANT_OPTS`: the `ant` launcher splits it and the JVM prints its usage.

## Smoke check (2026-10-24, clone `$W/cassandra-run1`, not used by any case)

- `ant build-test`: `BUILD SUCCESSFUL` in 1 min 53 s; `$W/m2` 143 MB, `build/` 213 MB. Log `$W/logs/build-test-run1.log`.
- `bin/cassandra -f` with `MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M`: `Startup complete`; `nodetool status` `UN 127.0.0.1`; `nodetool statusbinary`
  `running`; `cqlsh` `select release_version from system.local` → `5.0.9-SNAPSHOT`; `jcmd <pid> GC.heap_info` works. Stopped with
  `pkill -f CassandraDaemon`; `ps -eo command | grep '[C]assandraDaemon'` empty afterwards. Log `$W/logs/smoke-node.out`.
