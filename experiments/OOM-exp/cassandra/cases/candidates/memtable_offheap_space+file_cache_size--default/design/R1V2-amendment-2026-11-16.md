# R1-V amendment 6 (re-review re-run): family A on `pc96`, 2026-11-16

**Written:** 2026-11-16 16:50 EST, before any reading on `pc96`. Parent design: [`R1V-design.md`](R1V-design.md)
(§1–§8, amendments 1–5). Reason: researcher V7 re-review (case file, note at the top): condition B gives the heap
60 % of the container, the 5.0.9 docs and `cassandra-env.sh` put it at ≤ 50 %. This re-run measures **family A
only (heap = 50 % of the container, L = 2 × heap, direct = heap/2)**.

## What stays the same

- Build: Cassandra **5.0.9**, tree `b796bcfda7c9640fa41257544a9fe62c1aec634a` (= the original run's tree `b796bcfd…`).
  Copied with `rsync` from `/mydata/b6/cassandra` (tag `cassandra-5.0.9`, HEAD `f2de695`, clean tracked tree,
  built 2026-11-10, `apache-cassandra-5.0.9-SNAPSHOT.jar` sha256 `db3e6c30…`) to `/mydata/r1v2/cassandra`.
  **Difference:** the original used a copy of `~/cassandra-c1` (HEAD `7cb9cc7`); the commit hash differs
  (different import of the same tag), the source tree hash is identical. Different build of the same tree.
- yaml: exactly two lines (`memtable_allocation_type: offheap_objects`, `file_cache_enabled: true`); every capacity
  unset; controls by configuration (`M_only`: `file_cache_enabled` default false; `F_only`: `heap_buffers`);
  intervention lowers only `file_cache_size` (64 MiB at heap ≤ 1536, as amendment 3/§6).
- Workload: preload 800k writes (32 threads) → flush + disable autocompaction → 10,000-read fill (`N_FILL=10000`,
  amendment 2) → 2M-write burst, 64 threads, ≤ 240 s → 30 s hold. Instruments as before (2 s JMX poller outside the
  cgroup, NMT summary, `/proc` + cgroup every 5 s). Endpoint: kernel memcg OOM-kill of the JVM or a JVM OOME.

## What changes (platform change, recorded)

| | apt149 (2026-11-12) | pc96 (this re-run) |
|---|---|---|
| CPU | APT r320, 16 hardware threads (1 socket) | 2 × Xeon E5-2667 v2 (32 threads, 2 NUMA nodes) |
| RAM | 15.9 GiB | 125.8 GiB |
| Disk under `/mydata` | LVM on rotational disk | LVM on rotational disk (`sda`, ROTA=1) |
| OS / kernel / glibc / JDK | Ubuntu 22.04, 5.15.0-198, 2.35, OpenJDK 11.0.33 | same |
| Pinning | none (16 threads) | **victim JVM, `cassandra-stress` and the poller pinned with `taskset` to NUMA node 0 (CPUs 0,2,…,30 = 16 hardware threads)**, so `availableProcessors` (GC/compaction/flush thread counts) equals apt149's 16 |

Harness v3 ([`../harness/oom-run3.sh`](../harness/oom-run3.sh), [`run-all3.sh`](../harness/run-all3.sh)): v2 plus
run dir `/mydata/r1v2`, scope prefix `oom-r1v2-`, process matches limited to this run dir (pc96 is shared), the
`taskset` pinning, and the affinity read back into each arm's `summary.txt`. **pc96 arms are counted
separately; no pc96 arm is pooled with an apt149 arm in any V1/V2/V4 count.**

## Arms and order (time cap 3 h wall: 16:44–19:44 EST; no new arm after ≈ 19:15, readings stop 19:29)

All family A: L = 2 × H, direct = H/2. Names `P<H>-<arm>-<n>` (`P` = pc96, to keep them apart from apt149's `A…`).

1. `P768-converge-1`, `P896-converge-1` (bisection start), `P1536-converge-1`, `P768-converge-2`.
2. Bisection step 2: **960** if 896 failed, **832** if 896 survived (×1).
3. `P768-converge-3`, `P1536-converge-2`, `P1536-converge-3`.
4. ×3 at the largest failing heap found in 768–1024 (repeats to 3; to 5 if mixed, protocol step 6, as far as time allows).
5. Only if some level reaches 3/3 or a clear rate: at that level `M_only` ×3, `F_only` ×3, `int_F64` ×3 (pc96).
   If the converge rate stays low (≤ 1/3) the controls are not run; the rate is the result.

**Predictions** (from apt149's family-A peaks, assuming the same per-heap non-heap total): heap 768 converge ≈ 96 %
of L with occasional kills; 832–896 ≈ 94–95 %; 1024 ≈ 92 %; 1536 ≈ 89 % (survive). A heap = 50 % 3/3 failure is
**not** predicted; if none occurs that is the result (rates and the largest failing heap are reported).

## Amendment 6a (2026-11-16 17:00 EST, after the first pc96 arm, before any other reading)

- The first arm (started 16:54 as `P768-converge-1`, **renamed `P768g32-converge-1`**) ran with
  `-XX:ParallelGCThreads=32 -XX:ConcGCThreads=32`: `cassandra-env.sh` counts cores from `/proc/cpuinfo` (32 on pc96)
  and ignores `taskset`. apt149's R1-V JVMs had 16 (`../logs/smoke/smoke-H*-jvm-args.txt`). That arm was killed by
  the kernel memcg OOM-killer ≈ 12 s into the preload (anon-rss 1553 MiB; chunk pool 88 of 192, memtable K 64 of
  192). It is a **supplementary reading (32 GC threads), not counted** in any P768 converge count.
- **Change:** with pinning, the harness passes `-XX:ParallelGCThreads=16 -XX:ConcGCThreads=16` via `JVM_EXTRA_OPTS`
  (appended last, so it overrides the env script), the value `cassandra-env.sh` computes on a 16-thread host such
  as apt149; checked in each arm's `jvm-args.txt`. NMT GC at idle: 126 → 94 MiB (= apt149's 94).
- `P896-converge-1` (first attempt, 32 GC threads) was stopped during its idle phase, before any workload: **void**
  (`void-P896-converge-1-stopped-idle`).
- **Platform difference that remains (recorded, not changed):** idle RssAnon at heap 768 is ≈ 1200 MiB on pc96
  vs ≈ 1030 MiB on apt149 (+≈ 170 MiB) with the same JVM flags and 16 GC threads. NMT: total committed 1086 vs
  1039 MiB; thread stacks committed 52 vs 6 MiB (84 threads in both); the rest of the gap is outside NMT. No THP
  (`AnonHugePages` 0; THP `madvise`). So pc96 starts each arm closer to L than apt149 did; this is a property of
  the platform and is reported with the results.
- Arm order unchanged (list restarted 17:00 with `P768-converge-1`, `P896-converge-1`, `P1536-converge-1`,
  `P768-converge-2`).

## Amendment 6b (2026-11-16 17:25 EST, resume after an early hand-back; before any further reading)

- The run was stopped at 17:22 by an early hand-back (not a researcher stop); `P768-M_only-1` was stopped mid-burst
  and is **void** (`void-P768-M_only-1-stopped-burst`). The coordinator resumed it at 17:23; readings stop 19:30 EST, filing by 19:45.
- Readings so far (amendment 6/6a): P768 converge 3/3 killed; P896, P960, P1024 killed 1/1 each.
- **Order from here** (`list-4.txt`, same harness v3, 16 GC threads, node-0 pinning): at heap 768 / L 1536
  `M_only-1`, `F_only-1`, `int_F64-1`, `M_only-2`, `F_only-2`, `int_F64-2`, `M_only-3`, `F_only-3`, `int_F64-3`
  (V2, V4); then `P1536-converge-1..3`; then `P1024-converge-2..3` (largest failing heap). A guard creates
  `/mydata/r1v2/STOP` at 19:18 so no arm starts that cannot finish by ≈ 19:30.
- **17:24 EST:** the session was again forced to hand back 40 s after `list-4.txt` started; `P768-M_only-1` (second attempt) was stopped during startup/idle, before any workload: **void** (`void-P768-M_only-1b-stopped-start`). No arm of list 4 produced a reading; `STOP` is back in place. To resume: `cd /mydata/r1v2 && rm STOP && N_FILL=10000 nohup bash run-all3.sh list-4.txt > logs/run-4b.log 2>&1 < /dev/null &` (move the void folder aside first).
