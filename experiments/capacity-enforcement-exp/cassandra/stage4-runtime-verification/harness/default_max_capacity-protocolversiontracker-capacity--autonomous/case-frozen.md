# ProtocolVersionTracker.DEFAULT_MAX_CAPACITY — verification solution  <!-- file: cases/default_max_capacity-protocolversiontracker-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (capacity-set: each per-version cache gets `maximumSize(capacity)`), **linked**: [`ProtocolVersionTracker.java:51`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ProtocolVersionTracker.java#L51) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `positive`: the constant sets Caffeine `maximumSize(100)` on each of the six per-protocol-version caches that hold one entry per distinct client IP ever seen; with no other eviction or expiry, this cap is the only bound on that history's heap (at most 6 × 100 entries, 4 × 100 reachable). The bounded object is small (on the order of tens of KB at the cap) and grows without it only under client-address churn, so its effect is visible on the object, not on whole-node heap. |
| Ground | — |

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3). Use a permalink at the pinned tag.
> Here the target is a capacity-set place, so "the if statement" is read as the given line
> (L51); the actual comparison against the limit lives in the Caffeine library (A3).

## A. Constraint trace

**A1. The constraint.**
- Name: `ProtocolVersionTracker.DEFAULT_MAX_CAPACITY`.
- Kind: compile-time constant (`private static final int`).
- Declared: [`ProtocolVersionTracker.java:36`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ProtocolVersionTracker.java#L36) — `private static final int DEFAULT_MAX_CAPACITY = 100;`
- Unit: number of cache entries (one entry = one client `InetAddress` → last-seen time `Long`) **per protocol version**.
- Default: 100, a literal. The class Javadoc states the intent: "tracks the last 100 connections per protocol version" (`ProtocolVersionTracker.java:31-33`).
- Flow: the package-private no-arg constructor `ProtocolVersionTracker()` (`:40-43`) passes it to the private `ProtocolVersionTracker(int capacity)` (`:45-54`), which for **every** `ProtocolVersion` value (`V1..V6`, `ProtocolVersion.java:42-47`, i.e. 6 caches) builds `Caffeine.newBuilder().maximumSize(capacity).build(...)` (`:51-52`).
- How it can be set: **not settable** — no yaml key, no `-D` property, no JMX. Changing it needs a source edit and rebuild (or, in a unit test, reflection on the private `(int)` constructor). The only runtime control is `nodetool clientstats --clear-history` (JMX `StorageServiceMBean.clearConnectionHistory`, `StorageServiceMBean.java:1108` → `CassandraDaemon.java:868-870` → `NativeTransportService.java:200-203` → `Server.java:178-181` → `ProtocolVersionTracker.clear()` `:81-84`), which empties the caches but does not change the cap.
- One tracker per `Server.ConnectionTracker` instance (`Server.java:286`), i.e. one per native-transport server (normally one per node).

**A2. What it caps.**
- Resource: **heap** (on-heap Caffeine `BoundedLocalCache` per version: `ConcurrentHashMap` table + Caffeine node objects + `InetAddress` keys + boxed `Long` values, plus the frequency sketch Caffeine sizes from the maximum).
- Quantity compared against the limit: the cache's size (entry count; with no weigher, weight = 1 per entry), i.e. the number of distinct client IP addresses retained for that protocol version.
- Bound implied: at most 100 entries × 6 versions = 600 entries. `V1`/`V2` are rejected at decode (`ProtocolVersion.decode`, `ProtocolVersion.java:102-129`; supported set is `V3,V4,V5,V6`, `:66`), so at most 400 are reachable through the server. `V3` additionally needs `native_transport_allow_older_protocols: true` (default, `conf/cassandra.yaml:1056`); `V6` needs the `USE_BETA` header flag (`Envelope.java:461-462`).
- Rough size at the cap (estimate, not measured): about 150–200 bytes per entry (Caffeine node + CHM node/slot + `Inet4Address` with its holder + `Long`) → ≈ 60–80 KB for 400 entries, plus fixed per-cache overhead. Without the cap, one entry per distinct client address ever seen per version, never removed.

**A3. Mechanism.**
1. A client opens a TCP connection to the native port and sends `STARTUP`. `InitialConnectionHandler.decode` case `STARTUP` (`InitialConnectionHandler.java:97-104`) calls `factory.newConnection(channel, inbound.header.version)` when the channel has no connection yet.
2. `Server.connectionFactory.newConnection` (`Server.java:74-80`) creates a `ServerConnection`, whose `Connection` constructor calls `tracker.addConnection(channel, this)` (`Connection.java:34-41`).
3. `Server.ConnectionTracker.addConnection` (`Server.java:296-302`) adds the channel to `allChannels` and, if the remote address is an `InetSocketAddress`, calls `protocolVersionTracker.addConnection(remoteIP, version)`.
4. `ProtocolVersionTracker.addConnection` (`ProtocolVersionTracker.java:56-59`) does `clientsByProtocolVersion.get(version).put(addr, currentTimeMillis())`. Keyed by IP only (port is dropped), so reconnects from the same IP overwrite one entry.
5. **The capacity-set line** [`ProtocolVersionTracker.java:51`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ProtocolVersionTracker.java#L51): `maximumSize(capacity)` makes each cache a Caffeine size-bounded cache. The check itself is inside Caffeine 3.1.8 (`.build/parent-pom-template.xml:1059-1061`): after a write, `BoundedLocalCache` runs maintenance that evicts while the weighted size exceeds the maximum (`evictEntries` / `evictFromMain` in `BoundedLocalCache.java`, Caffeine v3.1.8).
6. Outcome at the limit: an entry is evicted (silently; no log, no metric). Caffeine's W-TinyLFU admission may evict the **newcomer** instead of the oldest entry when the newcomer's sketch frequency is not higher than the victim's, so the retained set is not strictly "the last 100" as the Javadoc says, but the **size** is bounded either way.
7. Overshoot paths:
   - Maintenance is asynchronous by default (on `ForkJoinPool.commonPool()`; no executor is set here), so the size can **temporarily** exceed 100 between a `put` and the drain of Caffeine's write buffer. Caffeine documents this ("the cache may evict an entry before this limit is exceeded or temporarily exceed the threshold while evicting").
   - Six independent caches: the total is 6 × cap, not cap.
   - No bypass: `addConnection` is the only writer (`grep` for `protocolVersionTracker` finds `Server.java:174,180,286,301` only).
8. Readers: `getAll()` / `getAll(version)` (`:61-79`) copy all entries into a fresh `ArrayList<ClientStat>` on each call; used by `Server.recentClientStats()` (`Server.java:172-175`) → `ClientMetrics` gauge `ClientsByProtocolVersion` (`ClientMetrics.java:128`, `:192-201`) → `nodetool clientstats --by-protocol` (`tools/nodetool/ClientStats.java:59-85`). These lists are transient and bounded by the same cap.

**A4. Other consumers.** Outside this constraint's control, per-client heap is also held by:
- `Server.ConnectionTracker.allChannels` / event `groups` (`Server.java:284-293`) — live channels, bounded only by `native_transport_max_concurrent_connections[_per_ip]` (`conf/cassandra.yaml:1048,1052`, default -1 = unlimited).
- `ClientResourceLimits.PER_ENDPOINT_ALLOCATORS` (`ClientResourceLimits.java:50-60`) — per-IP allocators, removed when released.
- Each live connection's Netty pipeline buffers and `ServerConnection`/`ClientState`.
- Other Caffeine caches on the node (auth caches, prepared statements), which share Caffeine's node classes in heap histograms.
These dwarf the tracker for live connections; the tracker is the only one that keeps state for **disconnected** clients.

**A5. Evidence beyond the source.**
- `CHANGES.txt:1822`: "List clients by protocol versions `nodetool clientstats --by-protocol` (CASSANDRA-14335)" — the feature that introduced the tracker. https://issues.apache.org/jira/browse/CASSANDRA-14335
- Existing unit test `test/unit/org/apache/cassandra/transport/ProtocolVersionTrackerTest.java` (only ≤10 entries; never reaches the cap).
- Caffeine `Caffeine.maximumSize` Javadoc (v3.1.8), on temporary overshoot and eviction policy: https://www.javadoc.io/doc/com.github.ben-manes.caffeine/caffeine/3.1.8/com.github.benmanes.caffeine.cache/com/github/benmanes/caffeine/cache/Caffeine.html#maximumSize(long)
- Caffeine eviction design (W-TinyLFU admission): https://github.com/ben-manes/caffeine/wiki/Efficiency
- Native protocol v4 spec (frame header and STARTUP body, used to write the cluster-tier client): `doc/native_protocol_v4.spec` in the tree, https://github.com/apache/cassandra/blob/cassandra-5.0.9/doc/native_protocol_v4.spec

## B. Verification solution

**B1. Claim under test.** The number of client-address entries the native-transport protocol-version tracker retains, and the heap they occupy, stop growing at `DEFAULT_MAX_CAPACITY` (100) per protocol version no matter how many distinct client IPs connect; with the cap raised, the same workload makes them grow one per distinct IP. The claim is wrong if, after maintenance has drained, any version's entry count exceeds 100 (or the tracker's retained heap keeps growing linearly past 100 distinct IPs per version) on the stock build.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11 (`java -version` 11.x), Apache Ant ≥ 1.10.
- Copy the tree to local disk, never build in the shared copy: `rsync -a <source>/ /local/c509-unit/ && cd /local/c509-unit && ant jar` (produces `build/classes/main` and `build/lib/jars/*`).
- Test program (new file, only in the local copy): `/local/c509-unit/s3probe/org/apache/cassandra/transport/PvtProbe.java` — same package so it can call the package-private `addConnection`/`getAll`.
- Compile: `javac -cp "build/classes/main:build/lib/jars/*" -d s3probe/classes s3probe/org/apache/cassandra/transport/PvtProbe.java`
- Run: `java -Xms2g -Xmx2g -XX:+UseG1GC -cp "s3probe/classes:build/classes/main:build/lib/jars/*" org.apache.cassandra.transport.PvtProbe <capacity> <N>`
- *Stage-4 amendment S4-A1 (2026-11-25, before any reading; B2f/B2g unchanged):* paths for the extension-set nodes: `/local/` is
  `/mydata/jingsong-cass-s4/o134/`. The unit copy is `cp -a /mydata/s4/cassandra-base` (already built with `ant build-test`, per
  `environment.md`) instead of `rsync` + `ant jar`; the classpath above is unchanged.
- *Stage-4 amendment S4-A2 (2026-11-25, before any reading):* every unit run uses `-Xms4g -Xmx4g` instead of `2g`, the option the
  note under B2c allows, applied to all arms so the JVM is identical across capacities and the MAX_VALUE second pass runs for every N.

**B2b. Knobs.**
- `capacity` ∈ {`100` (stock, via the no-arg constructor), `1000`, `Integer.MAX_VALUE` (uncapped positive control)} — the last two through reflection on the private `ProtocolVersionTracker(int)` constructor. 100 is the claim; 1000 checks the bound tracks the value; MAX_VALUE shows what the same workload does with no binding cap.
- `N` (distinct client addresses written to `V4`) ∈ {50, 100, 101, 1 000, 10 000, 1 000 000}: below, at, just above, and far above the cap; 1 000 000 makes the uncapped heap difference large enough for a heap-used reading (≈ 150–200 MB uncapped vs ≈ flat capped).

**B2c. Workload.** For i in 0..N-1: `pvt.addConnection(InetAddress.getByAddress(new byte[]{10,(byte)(i>>16),(byte)(i>>8),(byte)i}), ProtocolVersion.V4)` (no DNS). For N > 100 this is > cap distinct keys, so the limit is reached once N = 100 and passed for every N ≥ 101. A second pass writes N/2 addresses into each of `V3`, `V5`, `V6` to show the per-version (×versions) total.

`PvtProbe.main` outline (write it exactly):
```java
package org.apache.cassandra.transport;
import java.lang.reflect.*; import java.net.InetAddress; import java.util.*;
import com.github.benmanes.caffeine.cache.Cache;
public class PvtProbe {
  public static void main(String[] a) throws Exception {
    int cap = Integer.parseInt(a[0]); int n = Integer.parseInt(a[1]);
    ProtocolVersionTracker pvt;
    if (cap == 100) pvt = new ProtocolVersionTracker();
    else { Constructor<ProtocolVersionTracker> c = ProtocolVersionTracker.class.getDeclaredConstructor(int.class);
           c.setAccessible(true); pvt = c.newInstance(cap); }
    Field f = ProtocolVersionTracker.class.getDeclaredField("clientsByProtocolVersion"); f.setAccessible(true);
    Map<ProtocolVersion, Cache<?,?>> caches = (Map) f.get(pvt);
    long h0 = heapAfterGc();
    for (int i = 0; i < n; i++) {
      pvt.addConnection(addr(i), ProtocolVersion.V4);
      if ((i & 0xFFF) == 0) { long raw = caches.get(ProtocolVersion.V4).estimatedSize(); if (raw > maxRaw) maxRaw = raw; }
    }
    caches.values().forEach(Cache::cleanUp);
    long h1 = heapAfterGc();
    System.out.printf("cap=%d n=%d maxRawBeforeCleanup=%d V4.estimatedSize=%d V4.getAll=%d all=%d heapDeltaBytes=%d%n",
        cap, n, maxRaw, caches.get(ProtocolVersion.V4).estimatedSize(), pvt.getAll(ProtocolVersion.V4).size(),
        pvt.getAll().size(), h1 - h0);
    for (ProtocolVersion v : new ProtocolVersion[]{ProtocolVersion.V3, ProtocolVersion.V5, ProtocolVersion.V6})
      for (int i = 0; i < n / 2; i++) pvt.addConnection(addr(i + 20_000_000), v);
    caches.values().forEach(Cache::cleanUp);
    for (ProtocolVersion v : ProtocolVersion.values()) System.out.printf("%s=%d ", v, pvt.getAll(v).size());
    System.out.printf("total=%d%n", pvt.getAll().size());
    System.out.println(pvt.hashCode()); // keep pvt reachable until here
  }
  static long maxRaw = 0;
  static InetAddress addr(int i) throws Exception { return InetAddress.getByAddress(new byte[]{10,(byte)(i>>16),(byte)(i>>8),(byte)i}); }
  static long heapAfterGc() throws Exception { for (int k = 0; k < 3; k++) { System.gc(); Thread.sleep(200); }
    Runtime r = Runtime.getRuntime(); return r.totalMemory() - r.freeMemory(); }
}
```
(For N = 1 000 000 the V3/V5/V6 pass adds 1.5 M more puts; for capacity MAX_VALUE run that pass only for N ≤ 10 000 to stay inside 2 GB, or raise `-Xmx` to 4g.)

**B2d. Observables and instruments.**
- Check operand: `Cache.estimatedSize()` of the `V4` cache after `cleanUp()` (exact once maintenance has run), cross-checked with `getAll(V4).size()`.
- Overshoot: `maxRawBeforeCleanup` sampled every 4096 puts (shows asynchronous lag; informational only).
- Per-version and total entry counts after the second pass.
- Heap delta: used heap after 3 × `System.gc()` before vs after the writes (coarse; meaningful only for N = 1 000 000).
- Not directly observable: which addresses Caffeine chose to keep (not part of the claim).

**B2e. Procedure.**
1. Build as in B2a.
2. For each `capacity` in {100, 1000, 2147483647} and each `N` in {50, 100, 101, 1000, 10000, 1000000}: run the `java` command; append stdout to `/local/c509-unit/s3probe/results.txt`. Run each combination 3 times.
3. Additionally run `ant testsome -Dtest.name=org.apache.cassandra.transport.ProtocolVersionTrackerTest` once to confirm the stock behaviour below the cap is unchanged.
4. Delete `/local/c509-unit` when done (or keep only `results.txt`).

**B2f. Predictions.**
- `capacity = 100`: `V4.estimatedSize` = `getAll(V4).size()` = min(N, 100): 50, 100, 100, 100, 100, 100. Per-version after the second pass: `V3 = V5 = V6 = min(N/2, 100)`, `V1 = V2 = 0`, total ≤ 400. Heap delta for N = 1 000 000: no growth proportional to N (within a few MB of the N = 1000 delta).
- `capacity = 1000`: min(N, 1000): 50, 100, 101, 1000, 1000, 1000.
- `capacity = MAX_VALUE`: exactly N for every N; heap delta for N = 1 000 000 on the order of 150–200 MB (≈ 150–200 B/entry), i.e. at least 50× the capped run's delta.
- `maxRawBeforeCleanup` may exceed the cap by a small amount for large N (asynchronous maintenance); it must not grow with N.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| After `cleanUp()`, size = min(N, cap) for cap 100 and 1000; per-version ≤ cap; heap flat at cap 100 while MAX_VALUE grows ~linearly | Claim supported: the constant bounds the tracker's entries and heap per version |
| Any cap-100 run has `estimatedSize` or `getAll(V4).size()` > 100 after `cleanUp()` | Claim wrong: the cap does not bound the operand |
| Cap-100 heap delta at N = 10⁶ comparable to the MAX_VALUE delta | Claim wrong for memory: something other than the entry count grows (e.g. sketch or retained keys) |
| Size < min(N, cap) by a large margin (e.g. stuck near 1) | Eviction is more aggressive than the cap; cap still bounds, but the "last 100" behaviour is broken; record as a finding |
| `maxRawBeforeCleanup` grows with N without bound | Maintenance never catches up under this write rate; the bound is only eventual — record, re-run with a pause before sampling |
| MAX_VALUE run does not grow with N | Workload/control broken (not confirmed); fix before reading the capped runs |

**B2h. Controls.**
- Uncapped run (MAX_VALUE) with the same workload is the positive control: it shows the workload moves entries and heap where no cap binds.
- Cap 1000 shows the bound follows the value, not a coincidental 100.
- Below-cap N (50) shows entries are actually recorded (rules out a no-op tracker).
- `cleanUp()` before reading rules out asynchronous-maintenance artefacts; 3 runs per point rule out GC noise in heap deltas.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node (a single Cassandra instance is enough: the tracker is per node and per native server), JDK 11, Ant.
- Two local copies, each built with `ant jar`:
  - `/local/c509-stock` — unmodified tag.
  - `/local/c509-uncapped` — positive control: in `src/java/org/apache/cassandra/transport/ProtocolVersionTracker.java` change line 36 to `private static final int DEFAULT_MAX_CAPACITY = 1_000_000;` (only in this copy).
- Configuration for each copy, in its `conf/cassandra.yaml`: `cluster_name: s3probe`, `listen_address: 127.0.0.1`, `rpc_address: 127.0.0.1`, `native_transport_port: 9042`, `native_transport_allow_older_protocols: true`, `data_file_directories: [/local/s3data/data]`, `commitlog_directory: /local/s3data/commitlog`, `hints_directory: /local/s3data/hints`, `saved_caches_directory: /local/s3data/saved_caches`, `cdc_raw_directory: /local/s3data/cdc_raw` (local disk; a few hundred MB at most). Authentication stays default (`AllowAllAuthenticator`) so `STARTUP` gets `READY`.
- JVM: `export MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M` before `bin/cassandra -f -R` (run in background with `-p /local/s3data/pid`).
- *Stage-4 amendment S4-A1 (2026-11-25, before any reading; B3f/B3g unchanged):* `/local/` is `/mydata/jingsong-cass-s4/o134/`.
  Both copies are `cp -a /mydata/s4/cassandra-base`; the uncapped copy then gets the line-36 edit and `ant jar`. Instrument
  check: `javap -c -p -constants` on the no-arg constructor shows `bipush 100` (stock) and `ldc int 1000000` (uncapped) in both the
  jar `bin/cassandra` loads and `build/classes/main`.
- Client: a standalone raw-socket Java program `/local/s3client/StartupFlood.java` (no Cassandra classes needed):
```java
import java.io.*; import java.net.*;
public class StartupFlood {
  // args: protoVersion(3|4|5|6) firstHostIndex count
  public static void main(String[] a) throws Exception {
    int v = Integer.parseInt(a[0]), first = Integer.parseInt(a[1]), n = Integer.parseInt(a[2]);
    byte[] body = startupBody();
    for (int i = first; i < first + n; i++) {
      InetAddress src = InetAddress.getByAddress(new byte[]{127, (byte)(1 + (i >> 16)), (byte)(i >> 8), (byte)i});
      try (Socket s = new Socket()) {
        s.bind(new InetSocketAddress(src, 0));
        s.connect(new InetSocketAddress("127.0.0.1", 9042), 5000);
        s.setSoTimeout(5000);
        DataOutputStream out = new DataOutputStream(s.getOutputStream());
        out.writeByte(v); out.writeByte(v == 6 ? 0x10 : 0x00); out.writeShort(1); out.writeByte(0x01); out.writeInt(body.length); out.write(body); out.flush();
        DataInputStream in = new DataInputStream(s.getInputStream());
        int rv = in.readUnsignedByte(); in.readUnsignedByte(); in.readShort(); int op = in.readUnsignedByte();
        if (op != 0x02) System.err.println("src " + src + " got opcode " + op + " version byte " + rv);
      }
    }
  }
  static byte[] startupBody() throws IOException {
    ByteArrayOutputStream b = new ByteArrayOutputStream(); DataOutputStream d = new DataOutputStream(b);
    d.writeShort(1); writeStr(d, "CQL_VERSION"); writeStr(d, "3.0.0"); return b.toByteArray();
  }
  static void writeStr(DataOutputStream d, String s) throws IOException { byte[] x = s.getBytes("UTF-8"); d.writeShort(x.length); d.write(x); }
}
```
  Compile: `javac -d /local/s3client /local/s3client/StartupFlood.java`. Every `127.x.y.z` address is on `lo` on Linux, so no interface configuration is needed. Source addresses start at `127.1.0.0`, avoiding `127.0.0.1`.

**B3b. Knobs.**
- Build: stock (cap 100) vs uncapped control (cap 1 000 000). The constant is not settable at runtime, so the knob is the build.
- Distinct source IPs per version N ∈ {50, 100, 150, 1 000, 20 000}, driven on `V4`; then 1 000 each on `V3`, `V5`, `V6`. 20 000 gives an uncapped retained-heap delta of a few MB, large enough to see in a class histogram.

**B3c. Workload.** Sequential connect → `STARTUP` → `READY` → close, one connection per distinct source IP. Each connection adds exactly one tracker entry for that IP and version (A3 steps 1-4). For N ≥ 101 the per-version limit is reached and passed. At the expected rate (a few hundred to a few thousand handshakes/s on loopback) 20 000 connections take well under a few minutes; total driving time per build < 10 minutes. Connections are closed at once, so live-channel state (A4) returns to baseline; only the tracker keeps state for disconnected clients.

**B3d. Observables and instruments.**
- Usage-side operand on the real node: per-version row count of `bin/nodetool clientstats --by-protocol | awk 'NR>3 && NF>=3 {print $1}' | sort | uniq -c` (rows = tracker entries; the gauge reads `getAll()` directly).
- Actual resource (heap held by the tracker): `jcmd <pid> GC.class_histogram > hist-<label>.txt` (forces a full GC, live objects only) before and after each step. Read the instance-count and byte deltas of `java.net.Inet4Address`, `java.net.InetAddress$InetAddressHolder`, `java.lang.Long`, and the Caffeine node class used by size-bounded strong-key/strong-value caches (identify it in the uncapped control: the `com.github.benmanes.caffeine.cache.*` class whose count rises by ≈ N, expected name `PSMS`). Sum their byte deltas = tracker retained-heap delta.
- Whole-process: `jcmd <pid> GC.heap_info` and RSS (`ps -o rss= -p <pid>`) for context only; the tracker's capped footprint is far below their noise.
- Not directly observable: exact retained size of the tracker alone without a heap-dump analyser; the histogram delta approximates it (other activity is kept idle during the run).

**B3e. Procedure.** For each build (stock, then uncapped), with `C=/local/c509-<build>`:
1. `rm -rf /local/s3data && mkdir -p /local/s3data`; start: `cd $C && MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M bin/cassandra -R -p /local/s3data/pid`; wait until `bin/nodetool status` shows `UN` and `bin/nodetool info | grep 'Native Transport active: true'`.
2. `PID=$(cat /local/s3data/pid)`; `bin/nodetool clientstats --clear-history`; wait 30 s; `jcmd $PID GC.class_histogram > /local/s3data/h0.txt`; record `nodetool clientstats --by-protocol` → `r0.txt`.
3. For N in 50, 100, 150, 1000, 20000 (cumulative targets on V4, using fresh addresses each step)
   *(Stage-4 amendment S4-A3, 2026-11-25, before any reading: step 1's readiness wait is `nodetool statusbinary` = `running` and `nodetool status`
   shows `UN` (the `environment.md` §6 rule), with `ulimit -n 100000` and a port check first; nodetool uses `-h 127.0.0.1 -p 7199`; the node
   is started with `setsid nohup bin/cassandra -R -p …/pid`. Fresh addresses per step means `first` = the previous target (0, 50, 100, 150, 1000).
   B3d's per-version row count is taken as the lines matching `^[0-9]+/v` grouped by their first field, which is the awk filter's intent
   without depending on the line number of the header.)*
   : `java -cp /local/s3client StartupFlood 4 <first> <N - previous>`; wait 10 s; `nodetool clientstats --by-protocol > r-v4-$N.txt`; `jcmd $PID GC.class_histogram > h-v4-$N.txt`.
4. `java -cp /local/s3client StartupFlood 3 100000 1000`; same for 5 (first 200000) and 6 (first 300000); wait 10 s; record `r-all.txt`, `h-all.txt`.
5. Repeat the 20 000-step reconnect with the **same** first 20 000 addresses on V4 once more → `r-repeat.txt` (keying by IP: count must not change).
6. `bin/nodetool clientstats --clear-history`; record `r-clear.txt`, `h-clear.txt`.
7. Stop: `kill $(cat /local/s3data/pid)`; wait for exit; `pgrep -f CassandraDaemon` must print nothing.
8. Compute per-version row counts and histogram deltas vs `h0.txt` for the classes in B3d.

**B3f. Predictions.**
- Stock build: V4 rows after cumulative N = 50, 100, 150, 1000, 20000 → 50, 100, 100, 100, 100. After step 4: V3 = V5 = V6 = 100 (v6 shown as `v6-beta`), total 400. Step 5: unchanged. Step 6: 0. Histogram deltas of `Inet4Address` / node class / `Long` vs h0: rise with N up to ≈ 100 (V4) and ≈ 400 (all versions), then flat; summed byte delta at the end on the order of 60–80 KB and not growing from N = 1000 to N = 20 000.
- Uncapped build: V4 rows = N exactly (50, 100, 150, 1000, 20000); after step 4 total = 23 000; histogram node-class and `Inet4Address` counts rise by ≈ 23 000 vs h0, summed byte delta on the order of 3.5–4.5 MB; after step 6 the deltas return near 0.
- Relation: stock end-state retained delta ≤ 1/40 of the uncapped one at N = 20 000.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Stock: per-version rows plateau at 100 and histogram deltas plateau; uncapped: rows = N and deltas grow ~linearly with N | Claim supported: the constant caps the tracker's heap on a real node |
| Stock: any version shows > 100 rows after the 10 s settle, or deltas keep growing from N = 1000 to 20 000 | Claim wrong: the cap does not bound the real node's tracker |
| Stock rows plateau but histogram deltas keep growing | Something else retains per-IP state (A4, e.g. `PER_ENDPOINT_ALLOCATORS`); tracker capped but node per-client heap not — record which class grows |
| Uncapped rows do not grow past 100 | Control failed (stale build or wrong jar on classpath); not confirmed |
| Rows stay below N even for N < 100, or `StartupFlood` reports non-READY opcodes | Workload not registering (auth enabled, wrong version byte, `allow_older_protocols` false); not confirmed |
| Step 5 increases rows | Keying is not by IP as traced; record as a mechanism error |

**B3h. Controls.**
- Uncapped build with identical workload and config: positive control that the same workload moves usage where the cap does not bind.
- Below-cap steps (N = 50) show each distinct IP adds one entry.
- `--clear-history` at start and end: baseline is zero and the histogram delta returns, tying the delta to the tracker.
- No other clients or traffic during the run (single node, no driver sessions) so histogram deltas are not from other Caffeine caches; connections are closed so live-channel structures (A4) return to baseline.
- Repeat with the same addresses (step 5) checks the IP-keying part of the mechanism.

**B4. Risks and cleanup.**
- Disk: only `/local/s3data` (local, < 1 GB) and the two local build copies (~1–2 GB each). Never use shared storage; never build in the shared source tree.
- Ports: 9042, 7000, 7199 on 127.0.0.1; make sure no other Cassandra is running on the node first (`ss -ltnp | grep -E ':(9042|7000|7199)\b'`).
- Sockets: 20 000 client sockets enter TIME_WAIT on distinct source IPs; harmless, they expire in ~60 s.
- Processes: after each build's run, `kill` the Cassandra PID, then `pgrep -f CassandraDaemon` and `pgrep -f StartupFlood|PvtProbe` must print nothing.
- Cleanup: `rm -rf /local/s3data /local/c509-unit /local/c509-stock /local/c509-uncapped /local/s3client` after copying out results.

## C. Sources read

src/java/org/apache/cassandra/transport/ProtocolVersionTracker.java
src/java/org/apache/cassandra/transport/Server.java
src/java/org/apache/cassandra/transport/Connection.java
src/java/org/apache/cassandra/transport/InitialConnectionHandler.java
src/java/org/apache/cassandra/transport/ProtocolVersion.java
src/java/org/apache/cassandra/transport/Envelope.java
src/java/org/apache/cassandra/transport/ClientResourceLimits.java
src/java/org/apache/cassandra/transport/ClientStat.java
src/java/org/apache/cassandra/transport/SimpleClient.java
src/java/org/apache/cassandra/metrics/ClientMetrics.java
src/java/org/apache/cassandra/tools/nodetool/ClientStats.java
src/java/org/apache/cassandra/tools/NodeProbe.java
src/java/org/apache/cassandra/service/NativeTransportService.java
src/java/org/apache/cassandra/service/StorageService.java
src/java/org/apache/cassandra/service/StorageServiceMBean.java
src/java/org/apache/cassandra/service/CassandraDaemon.java
src/java/org/apache/cassandra/utils/Clock.java
src/java/org/apache/cassandra/utils/ObjectSizes.java
test/unit/org/apache/cassandra/transport/ProtocolVersionTrackerTest.java
conf/cassandra.yaml
build.xml
.build/parent-pom-template.xml
.build/cassandra-deps-template.xml
CHANGES.txt
NEWS.txt
(URLs below cited from prior knowledge, not fetched in this session; no network access was used)
https://issues.apache.org/jira/browse/CASSANDRA-14335
https://www.javadoc.io/doc/com.github.ben-manes.caffeine/caffeine/3.1.8/com.github.benmanes.caffeine.cache/com/github/benmanes/caffeine/cache/Caffeine.html#maximumSize(long)
https://github.com/ben-manes/caffeine/wiki/Efficiency
doc/native_protocol_v4.spec (in-tree copy; header layout used for StartupFlood)
doc/native_protocol_v5.spec (STARTUP stays unframed in v5)

## D. Stage-4 feedback

none yet
