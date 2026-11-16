# Node smoke test — ms0625 (Utah m400, aarch64), 2026-11-16

**Question.** Can a Utah m400 node (ARM) run Cassandra 5.0.9 with the native paths the OOM cases depend
on, under a cgroup v2 budget, and serve a workload? **Answer: yes (passed).** Run by
[`smoke.sh`](smoke.sh) on the node itself; full log in [`smoke.log`](smoke.log).

| Check | Result |
|---|---|
| Node | `ms0625.utah.cloudlab.us` (node0 of `jason92-326377`): aarch64 APM X-Gene, 8 cores, 62 GiB RAM, 8 GiB swap on, Ubuntu 22.04.1, `5.15.0-191-generic` ([`inventory.txt`](inventory.txt)) |
| Toolchain | `openjdk-11-jdk` 11.0.33, Ant 1.10.12 from apt |
| Source | repository `systems/cassandra/source/` (repo HEAD `01bed5a7`) copied with `copy-source.sh` to `/mydata/oom-smoke/cassandra-run1` |
| Build | `ant jar` BUILD SUCCESSFUL in 5 min 18 s (about 2× the x86 nodes); `build/lib/jars` has `netty-transport-native-epoll-4.1.130.Final-linux-aarch_64.jar` |
| Budget | `systemd-run --user --scope -p MemoryMax=4096M -p MemorySwapMax=0`; JVM in the scope (`memory.max` 4 GiB, `memory.swap.max` 0); heap 2 GiB (G1), `MaxDirectMemorySize` 1024 MiB effective ([`vm-flags.txt`](vm-flags.txt)) |
| Start | CQL listening after 52 s; `nodetool status` UN, `statusbinary` running |
| Native libraries | `Netty using native Epoll event loop`; 51 threads in `epollWait`, 0 in NIO select; `JNA mlockall successful`; SIGAR not loaded (no aarch64 library; startup checks only) ([`native-lines.txt`](native-lines.txt)) |
| Warnings | 5 WARN, 0 ERROR: free disk 38 GiB, jemalloc not installed, JMX local only, `vm.max_map_count` 65530, new host ID ([`warn-error.txt`](warn-error.txt)). jemalloc and `max_map_count` are the same on `pc96` (not installed / 65530) |
| Workload | stress write n=200,000, 32 threads: 6,701 op/s, mean 4.6 ms, p99 19.7 ms, 0 errors; read n=100,000: 4,765 op/s, mean 6.6 ms, p99 27.2 ms, 0 errors (client on the same node) |
| Memory | heap 793 / 2048 MB after the workload; cgroup `memory.current` 2.64 GiB, `memory.events` all 0; `memory.peak` is absent on kernel 5.15 |
| cgroup OOM | separately, a 400 MiB Python allocation in a 200 MiB user scope with swap 0 was memcg-OOM-killed, recorded in `dmesg` and the user journal |
| Cleanup | daemon, stress and scope all gone after the run |

**Notes for runs on these nodes.**

- A separate platform from the x86 nodes: never mix within one case's matched arms; record `aarch64`.
- The default (auto) `MaxDirectMemorySize` is ¼ of RAM (`cassandra-env.sh`): 15,872 MiB here.
- The user manager tears down `--user` scopes when the last session closes: keep the ssh session open
  or enable linger for the run (see `cases/_run-log.md`).
- The other four nodes (`ms0640`, `ms0604`, `ms0611`, `ms0617`) are not set up yet.
