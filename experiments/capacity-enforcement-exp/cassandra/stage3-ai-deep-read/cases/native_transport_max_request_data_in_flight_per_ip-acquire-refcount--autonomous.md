# native_transport_max_request_data_in_flight_per_ip — verification solution  <!-- file: cases/native_transport_max_request_data_in_flight_per_ip-acquire-refcount--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (the `Allocator.acquire()` reference-count check), **linked**: [`ClientResourceLimits.java:167`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ClientResourceLimits.java#L167) — `return 0 < refCount.updateAndGet(i -> i < 0 ? i : i + 1);` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `negative`. Line 167 checks a reference count against 0. It does not compare bytes against a limit. It decides whether a new client connection shares the live per-IP `Allocator`, which holds the per-IP in-flight budget. The reference count drops when a channel closes, even while that channel's requests still hold bytes, so a client that reconnects from the same IP gets a fresh per-IP counter that starts at 0. Per-IP in-flight request data (heap and off-heap) can therefore rise to about k × the per-IP limit. Only the global limit bounds it. |
| Ground | (1) The operand `refCount` is a connection count. No limit applies to it, and it bounds no memory-significant object: it keeps at most one live `Allocator` (a few hundred bytes) per IP. (2) The per-IP byte limit that line 167 serves is reset across connection generations. Release happens on `channelInactive` ([PreV5Handlers.java:258](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PreV5Handlers.java#L258); V5: `AbstractMessageHandler.java:500` → `PipelineConfigurator.java:308`). Requests that are queued or executing still hold bytes on the now-dead allocator, and those bytes return only on flush (`PreV5Handlers.java:105-110`). A reconnect after `refCount` reached -1 fails the line-167 check, so `getAllocatorForEndpoint` builds a new `Allocator` whose endpoint `Concurrent` limit has `using = 0` (`ClientResourceLimits.java:54-58, 157-163`). |

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3). Use a permalink at the pinned tag.
> Here the "if statement" is the given line, the boolean return of `acquire()` that
> `getAllocatorForEndpoint` branches on (`ClientResourceLimits.java:55`).

## A. Constraint trace

**A1. The constraint.**
- **Name:** `native_transport_max_request_data_in_flight_per_ip`. Its deprecated alias is `native_transport_max_concurrent_requests_in_bytes_per_ip` (`@Replaces`, `Config.java:295`).
- **Kind:** configuration entry. The line-167 operand, `Allocator.refCount` (`ClientResourceLimits.java:148`), is an internal `AtomicInteger` with no limit. The constraint involved is the per-IP byte limit that each `Allocator` carries (`ClientResourceLimits.java:160`, `new ResourceLimits.Concurrent(getEndpointLimit())`).
- **Declared:** [`Config.java:296`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L296), `public volatile DataStorageSpec.LongBytesBound native_transport_max_request_data_in_flight_per_ip = null;`
- **Unit:** bytes (`DataStorageSpec.LongBytesBound`; accepts `B`/`KiB`/`MiB`/`GiB`).
- **Default:** `null` in `Config`. `DatabaseDescriptor.java:654-657` then sets it to `Runtime.getRuntime().maxMemory() / 40`, which is 2.5% of max heap (for example 51.2 MiB at `-Xmx2G`). The global sibling `native_transport_max_request_data_in_flight` defaults to `maxMemory()/10` (`DatabaseDescriptor.java:649-652`).
- **How to set:** the `cassandra.yaml` key (not present in the shipped `conf/cassandra.yaml`, so it must be added), which needs a restart. It can also be changed at runtime through JMX `org.apache.cassandra.db:type=StorageService` attribute `NativeTransportMaxConcurrentRequestsInBytesPerIp` (`StorageServiceMBean.java:684-685`, `StorageService.java:7062-7065` → `ClientResourceLimits.setEndpointLimit`, `ClientResourceLimits.java:84-91`). That setter updates the existing allocators and also the value future allocators read (`DatabaseDescriptor.java:3367-3377`; `-1` restores the default).
- **Validation:** `native_transport_max_message_size` must not exceed it (`DatabaseDescriptor.java:914-915`). The default max message size is `min(max_mutation_size, global, per_ip)` (`DatabaseDescriptor.java:3237-3245`).

**A2. What it caps.**
- **Intended resource:** heap and off-heap memory held by native-protocol (CQL) request bodies that have been read and not yet answered, summed per client IP.
- **Compared quantity:** `ResourceLimits.Concurrent.using`, the sum of `Envelope.Header.bodySizeInBytes` for admitted requests (V4: `PreV5Handlers.java:153, 157, 182`). For V5 it is the part of the bytes above the per-connection `native_transport_receive_queue_capacity` (`AbstractMessageHandler.java:461-474`).
- **What line 167 compares:** `refCount` (a count of connections from this IP) against 0. It returns false when the allocator has already been retired (`refCount == -1`).
- **Memory held per admitted V4 request:** the direct-memory `Envelope` body, which is retained until flush (`PreV5Handlers.java:105-106`; channel allocator `CBUtil.allocator`, a pooled direct allocator, `CBUtil.java:60`, `PipelineConfigurator.java:138`). It also holds a heap copy of every bound value (`CBUtil.readBoundValue`, `CBUtil.java:480`, `ByteBuffer.wrap(readRawBytes(...))`, reached from `QueryOptions.java:626`).

**A3. Mechanism.**
1. **Connection start.** On `STARTUP`, `InitialConnectionHandler.java:111` calls `ClientResourceLimits.getAllocatorForEndpoint(remoteAddress)`.
2. **Find or create.** `getAllocatorForEndpoint` (`ClientResourceLimits.java:50-60`) loops. Each pass does `computeIfAbsent(endpoint, Allocator::new)` and then `if (result.acquire()) return result;`. Otherwise it removes that stale entry and retries.
3. **The check at line 167.** [`ClientResourceLimits.java:167`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ClientResourceLimits.java#L167): `return 0 < refCount.updateAndGet(i -> i < 0 ? i : i + 1);`
   - **True** (the allocator is live, `refCount >= 0` before the call): the count is incremented and the connection shares this allocator. All connections from the IP then draw on one endpoint `Concurrent` (one per-IP budget) and on the shared `GLOBAL_LIMIT` (`ClientResourceLimits.java:42, 161`).
   - **False** (`refCount == -1`): the allocator was retired by `release()` (`ClientResourceLimits.java:174-178`; `1 → -1`, then the map entry is removed). The caller removes it (line 58) and creates a **new** allocator whose endpoint limit starts at `using = 0`.
4. **Who decrements.** The count goes down when a channel closes, whatever bytes are still in flight:
   - V4: `LegacyDispatchHandler.channelInactive` → `endpointPayloadTracker.release()` (`PreV5Handlers.java:256-264`).
   - V5: `AbstractMessageHandler.channelInactive` → `onClosed.call` (`AbstractMessageHandler.java:490-501`) → `resourceProvider.release()` (`PipelineConfigurator.java:308`, `ClientResourceLimits.java:291-294`).
5. **The byte check itself** (not at line 167):
   - `EndpointAndGlobal.tryAllocate` (`ResourceLimits.java:263-273`) calls `Concurrent.tryAllocate`, which rejects when `next > limit` (`ResourceLimits.java:138`).
   - V4 with throw-on-overload (the client sent STARTUP option `THROW_ON_OVERLOAD=1`, `StartupMessage.java:111`): the request is discarded with `OverloadedException` (`PreV5Handlers.java:157-160`).
   - V4 default: the bytes are force-allocated anyway and the channel is paused (`PreV5Handlers.java:182-187`), which overshoots by up to one message per connection.
   - V5: the bytes are charged only above the per-connection receive queue capacity (`AbstractMessageHandler.java:421-459, 461-474`). Messages are then rejected or queued (`CQLMessageHandler.java:200-223, 693-704`).
6. **Release.** After a response is flushed, the bytes go back to the **same** allocator object the connection holds (`PreV5Handlers.java:105-110`; V5 `AbstractMessageHandler.releaseCapacity`). If that allocator was retired meanwhile, its endpoint counter is no longer in `PER_ENDPOINT_ALLOCATORS`, and new connections never see it.
7. **Bypass and overshoot paths for the per-IP cap:**
   - **(a) Reconnect generations** (the subject of this case): close every connection from an IP while requests are queued, then reconnect. Per-IP in-flight ≈ (bytes still held by retired allocators) + L.
   - **(b) V4 pause mode:** +1 message per connection.
   - **(c) V5:** each connection's `native_transport_receive_queue_capacity` (default 1 MiB, `Config.java:302`) is outside the endpoint reserve, so per-IP ≈ L + n_conn × 1 MiB.
   - **(d) V5 STARTUP:** body force-allocated (`InitialConnectionHandler.java:119`).
   - The global `GLOBAL_LIMIT` is shared by every allocator, retired or not, so it still binds in (a).

**A4. Other consumers.**
- Request bytes from other IPs. They share the global limit but not this per-IP limit.
- The per-connection V5 receive queue (`native_transport_receive_queue_capacity`).
- Response encoding buffers, which are not counted (V4 responses are encoded on flush, `PreV5Handlers.java:91-97`).
- Objects created while executing requests: mutations, memtable, read results.
- Netty's pooled-arena retention: freed direct chunks stay committed.
- Cassandra's `BufferPool` / chunk cache, and internode messaging.

**A5. Evidence beyond the source.**
- `CHANGES.txt:2097` "Prevent client requests from blocking on executor task queue (CASSANDRA-15013)". This is where per-endpoint in-flight tracking for native clients was introduced. https://issues.apache.org/jira/browse/CASSANDRA-15013 (not opened in this session).
- `CHANGES.txt:1591` "Make native_transport_max_concurrent_requests_in_bytes updatable (CASSANDRA-15519)".
- `CHANGES.txt:1344` / `NEWS.txt:704` (CASSANDRA-15299, V5 framing and the `ResourceProvider` path).
- `test/unit/org/apache/cassandra/transport/ClientResourceLimitsTest.java:165` depends on the line-167 true branch. It fetches the live connection's allocator through `getAllocatorForEndpoint` to signal its wait queue. No in-tree test covers the reconnect / retired-allocator case.

## B. Verification solution

**B1. Claim under test.** The per-IP in-flight request data that the line-167 allocator lifecycle hands out is **not** held to `native_transport_max_request_data_in_flight_per_ip = L`. Suppose all connections from one IP close while their admitted requests are still queued, and the client reconnects k times. Then the node holds request data from that IP (the gauge `RequestsSize`, and the matching heap plus direct memory) of up to ≈ k·L, bounded only by the global limit `native_transport_max_request_data_in_flight`. The claim is wrong if the per-IP total stays ≤ L (+ one message per connection) across reconnect generations while no other connection from that IP is open.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11 and Ant, in a private copy of the tag on local disk:
  ```
  export S4=/local/<you>/s4-crl      # local disk, >= 20 GiB free; never under the shared tree
  rsync -a <shared cassandra-5.0.9 source>/ $S4/src/
  cd $S4/src && ant realclean && ant jar build-test
  ```
- The test source goes in `$S4/src/test/unit/org/apache/cassandra/transport/AllocatorRefCountTest.java`. It must be in that package because `Allocator`, `acquire`, `tryAllocate`, `release` and `endpointUsing` are package-private or private.
- JVM options: the `ant testsome` defaults (test `cassandra.yaml` from `test/conf`).

**B2b. Knobs.**
- The per-IP limit is `L ∈ {600 B, 1 MiB, 64 MiB}`:
  - 600 B is the value `ClientResourceLimitsTest` uses.
  - 1 MiB is a typical single large message.
  - 64 MiB is the cluster-tier value.
- It is set with `ClientResourceLimits.setEndpointLimit(L)`. The global limit `G` is set with `ClientResourceLimits.setGlobalLimit(G)`:
  - main runs: `G = 10·L`, so global does not bind for k ≤ 3;
  - positive control: `G = 1.5·L`.
- The generation count is `k ∈ {1, 2, 3}`.

**B2c. Workload.**
- One test IP, `InetAddress.getByName("127.0.0.2")`, so no real connection interferes.
- Generation `g`:
  1. `a_g = getAllocatorForEndpoint(ip)` (line 167 runs).
  2. `a_g.tryAllocate(L)`. This must return `SUCCESS`: L ≤ L, so the endpoint budget is now exactly full.
  3. `a_g.tryAllocate(1)` must return `INSUFFICIENT_ENDPOINT`. This is the in-generation positive control: L+1 > L, so the cap binds on a live allocator.
  4. `a_g.release()`, which simulates `channelInactive` **without** returning the L bytes (the requests are "still executing").
- After k generations the bytes charged against the IP sum to k·L. For k = 3, 3·L ≤ G = 10·L, so the global limit never binds.
- Cleanup: `a_g.release(L)` for every g, which returns the counters to 0 and avoids `UnrecoverableIllegalStateException`, `ResourceLimits.java:160-168`.

**B2d. Observables and instruments.**
- `refCount` of each allocator, read by reflection on the field `refCount` (`ClientResourceLimits.java:148`). This is the line-167 operand.
- The return value of private `acquire()`, called by reflection on a retired allocator.
- `a_g.endpointUsing()` (`ClientResourceLimits.java:221-224`).
- `ClientResourceLimits.getCurrentGlobalUsage()` (the same value as the `RequestsSize` metric, `ClientMetrics.java:129`).
- `ClientResourceLimits.getCurrentIpUsage().getMax()` (live allocators only, as in `RequestsSizeByIpDistribution`, `ClientResourceLimits.java:93-101`).
- Identity: `assertSame` / `assertNotSame`.
- Every observable is read synchronously after each step. Nothing at this tier measures actual memory (there are no buffers); that is B3.

**B2e. Procedure.**
1. Write the test class below. Each `@Test` does the following.
   - **Setup:** `@BeforeClass DatabaseDescriptor.daemonInitialization();`. This must run before `ClientResourceLimits` is first touched, because its static `GLOBAL_LIMIT` reads `DatabaseDescriptor`.
   - **`sharingWhileLive` (line 167 true branch):**
     1. Set L and G.
     2. `a = get(ip)`; check `refCount(a) == 1`.
     3. `b = get(ip)`; check `assertSame(a, b)` and `refCount == 2`.
     4. `a.tryAllocate(L) == SUCCESS`, then `b.tryAllocate(1) == INSUFFICIENT_ENDPOINT` (one budget for the IP).
     5. `b.release()` (count goes to 1), then `a.release(L)` and `a.release()` (count goes to -1).
     6. Check `refCount(a) == -1` and `acquire(a) == false`. The false branch leaves the count at -1.
   - **`reconnectGenerations` (claim):**
     1. For g = 1..k, run the B2c generation and record `a_g`, `getCurrentGlobalUsage()` and `getCurrentIpUsage().getMax()`.
     2. Check `assertNotSame(a_g, a_{g-1})`.
     3. Finally check `getCurrentGlobalUsage() == k·L` and `Σ_g a_g.endpointUsing() == k·L`.
     4. Cleanup per B2c.
   - **`anchorKeepsCap` (control):**
     1. `anchor = get(ip)` and keep it, so `refCount ≥ 1` for the whole test.
     2. Run the k generations. Each `get(ip)` must return `anchor` (`assertSame`).
     3. Generation 2's `tryAllocate(L)` must return `INSUFFICIENT_ENDPOINT`, and the global usage stays L.
   - **`globalStillBinds` (positive control):**
     1. Set `G = 1.5·L` and run k = 2.
     2. Generation 2's `tryAllocate(L)` must return `INSUFFICIENT_GLOBAL`, and `tryAllocate(L/2)` must return `SUCCESS`. Global usage = 1.5·L.
   - Parameterise over L ∈ {600, 1048576, 67108864}, either with a loop inside each test or with JUnit `Parameterized`. Reset with `setEndpointLimit(3000000000L)` and `setGlobalLimit(5000000000L)` in `@After`, as `ClientResourceLimitsTest.tearDown` does.
2. Run `cd $S4/src && ant testsome -Dtest.name=org.apache.cassandra.transport.AllocatorRefCountTest`.
3. Read the results in `build/test/output/TEST-org.apache.cassandra.transport.AllocatorRefCountTest.xml`. Log each recorded value with `System.out.printf` so the XML carries the numbers.

**B2f. Predictions** (for every L):

| Test | k | `getCurrentGlobalUsage()` | `getCurrentIpUsage().getMax()` | identity |
|---|---|---|---|---|
| reconnectGenerations | 1 | L | ≈ L (bucketed) | — |
| reconnectGenerations | 2 | 2·L | 0 / empty (no live allocator) | `a_2 ≠ a_1` |
| reconnectGenerations | 3 | 3·L | 0 / empty | all distinct |
| anchorKeepsCap | 3 | L | ≈ L | all `== anchor` |
| globalStillBinds (G = 1.5L) | 2 | 1.5·L | — | `a_2 ≠ a_1` |

`refCount` after `release()` of the last holder is -1, and `acquire()` on it returns false.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `reconnectGenerations` global usage = k·L with distinct allocators, `anchorKeepsCap` holds at L, `globalStillBinds` at 1.5·L | Claim confirmed at the unit tier: per-IP accounting resets on reconnect, and only the global limit binds |
| `get(ip)` after the last `release()` returns the old allocator, or `tryAllocate(L)` in generation 2 returns `INSUFFICIENT_ENDPOINT` without an anchor | Claim refuted: usage follows the per-IP knob across generations |
| `anchorKeepsCap` also reaches k·L | The line-167 true branch does not give sharing; the mechanism is mis-traced (claim's explanation wrong) |
| In-generation `tryAllocate(1)` does not return `INSUFFICIENT_ENDPOINT`, or `globalStillBinds` does not stop at 1.5·L | Positive control did not move: not confirmed; the harness or limits are not set as intended |

**B2h. Controls.**
- The anchor run differs from the main run only in whether `refCount` can reach -1. That isolates line 167's role.
- The in-generation `tryAllocate(1)` shows the per-IP limit does bind on a live allocator, so the overshoot is not a broken limit.
- `globalStillBinds` shows that what remains bounds the total.
- A separate IP (127.0.0.2) keeps the test's own connections (none here) off the counters.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node with JDK 11, running from `$S4/src` built as in B2a (`ant jar`).
- All runtime directories are under `$S4/run` on local disk:
  ```
  mkdir -p $S4/run/{data,commitlog,saved_caches,hints,cdc,logs}
  cd $S4/src
  # ports off defaults so a shared host is not disturbed
  sed -i 's/^JMX_PORT="7199"/JMX_PORT="17199"/' conf/cassandra-env.sh
  ```
- Append to `$S4/src/conf/cassandra.yaml` (after removing the same keys if present):
  ```yaml
  cluster_name: s4crl
  data_file_directories: [/local/<you>/s4-crl/run/data]
  commitlog_directory: /local/<you>/s4-crl/run/commitlog
  saved_caches_directory: /local/<you>/s4-crl/run/saved_caches
  hints_directory: /local/<you>/s4-crl/run/hints
  cdc_raw_directory: /local/<you>/s4-crl/run/cdc
  listen_address: 127.0.0.1
  rpc_address: 127.0.0.1
  storage_port: 17000
  native_transport_port: 19042
  seed_provider: [{class_name: org.apache.cassandra.locator.SimpleSeedProvider, parameters: [{seeds: "127.0.0.1:17000"}]}]
  native_transport_max_threads: 1          # one executor thread so admitted requests queue
  native_transport_timeout: 120s           # queued requests are not answered early as timed out
  native_transport_max_request_data_in_flight_per_ip: 64MiB   # knob, B3b
  native_transport_max_request_data_in_flight: 1GiB           # knob, B3b
  ```
- JVM:
  ```
  export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M
  export CASSANDRA_LOG_DIR=$S4/run/logs
  export JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -javaagent:$S4/byteman-4.0.20.jar=script:$S4/slow.btm"
  ```
- Byteman 4.0.20 is the version pinned in `.build/parent-pom-template.xml:40`. Take `build/test/lib/jars/byteman-4.0.20.jar` after `ant build-test`, or download it from https://repo1.maven.org/maven2/org/jboss/byteman/byteman/4.0.20/byteman-4.0.20.jar into `$S4/`.
- The rule `$S4/slow.btm` slows only large client requests on the executor thread (the 6-argument `Dispatcher.processRequest`, `Dispatcher.java:459`, never runs on the event loop):
  ```
  RULE slow large native requests
  CLASS org.apache.cassandra.transport.Dispatcher
  METHOD processRequest(io.netty.channel.Channel, org.apache.cassandra.transport.Message$Request, org.apache.cassandra.transport.Dispatcher$FlushItemConverter, java.lang.Object, org.apache.cassandra.transport.ClientResourceLimits$Overload, org.apache.cassandra.transport.Dispatcher$RequestTime)
  AT ENTRY
  IF $2.getSource() != null && $2.getSource().header.bodySizeInBytes > 65536
  DO Thread.sleep(500)
  ENDRULE
  ```
- Start with `bin/cassandra -p $S4/run/pid`, then wait for `bin/nodetool -p 17199 status` to show `UN`. Check that the Byteman rule loaded: `grep -i byteman $S4/run/logs/system.log`, or check that the B3e step 3 timing shows about 0.5 s per request.

**B3b. Knobs.**
- `native_transport_max_request_data_in_flight_per_ip` L ∈ {32 MiB, 64 MiB}. Two values show that the reached total scales with L, not with a fixed number. Both are well above the noise of pooled buffers, and both fit 3 generations under G.
- `native_transport_max_request_data_in_flight` G is 1 GiB for the main runs and 96 MiB (1.5 × 64 MiB) for the positive control.
- Generation count k ∈ {1, 3}.
- Anchor connection: absent or present.
- All of these are set in the yaml, and the node is restarted between runs. Alternatively, set L or G at runtime with `bin/nodetool -p 17199 sjk mx -b org.apache.cassandra.db:type=StorageService -ms -f NativeTransportMaxConcurrentRequestsInBytesPerIp -v <bytes>` (and `NativeTransportMaxConcurrentRequestsInBytes`).

**B3c. Workload.**
- Before each run, create the schema with cqlsh, then exit cqlsh so its connection closes:
  ```
  bin/cqlsh 127.0.0.1 19042 -e "CREATE KEYSPACE IF NOT EXISTS s4 WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE IF NOT EXISTS s4.blobs (k int PRIMARY KEY, v blob);"
  ```
- The client `$S4/gen.py` uses only the Python 3 stdlib. It speaks CQL protocol v4 over one raw socket.
  1. It sends STARTUP with `CQL_VERSION=3.0.0, THROW_ON_OVERLOAD=1`. Throw mode makes the server reject over-limit requests exactly at `next > limit` (`PreV5Handlers.java:157-160`) instead of pausing the channel, so per-allocator in-flight is ≤ L exactly.
  2. It sets `SO_LINGER(1,0)`, so the process exit sends RST. That makes `channelInactive` fire promptly.
  3. It pipelines N = 80 QUERY frames `INSERT INTO s4.blobs (k, v) VALUES (?, ?)`, each with a 1 048 576-byte blob, from a writer thread. A reader thread drains responses and prints a count of RESULT (0x08) and ERROR (0x00) frames.
  4. Then it sleeps until it is killed.

  ```python
  import socket, struct, sys, threading, time, os
  host, port, gen = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); N = int(sys.argv[4]) if len(sys.argv) > 4 else 80
  s = socket.create_connection((host, port)); s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
  def frame(stream, op, body): return struct.pack('>BBhBi', 4, 0, stream, op, len(body)) + body
  def string(x): b = x.encode(); return struct.pack('>H', len(b)) + b
  def lstring(x): b = x.encode(); return struct.pack('>i', len(b)) + b
  def recv_frame():
      h = b''
      while len(h) < 9: h += s.recv(9 - len(h))
      _, _, st, op, ln = struct.unpack('>BBhBi', h); body = b''
      while len(body) < ln: body += s.recv(ln - len(body))
      return st, op, body
  s.sendall(frame(0, 0x01, struct.pack('>H', 2) + string('CQL_VERSION') + string('3.0.0') + string('THROW_ON_OVERLOAD') + string('1')))
  assert recv_frame()[1] == 0x02, 'expected READY'
  blob = os.urandom(1048576); q = lstring('INSERT INTO s4.blobs (k, v) VALUES (?, ?)')
  def body(k): return q + struct.pack('>HB', 1, 0x01) + struct.pack('>H', 2) + struct.pack('>i', 4) + struct.pack('>i', gen * 100000 + k) + struct.pack('>i', len(blob)) + blob
  cnt = {0x08: 0, 0x00: 0}
  def reader():
      while True:
          st, op, b = recv_frame(); cnt[op] = cnt.get(op, 0) + 1
          print(f'gen{gen} t={time.time():.1f} op={op:#x} ok={cnt[0x08]} err={cnt[0x00]}', flush=True)
  threading.Thread(target=reader, daemon=True).start()
  for k in range(1, N + 1): s.sendall(frame(k, 0x07, body(k)))
  print(f'gen{gen} sent {N}', flush=True); time.sleep(3600)
  ```
- **Arithmetic** (L = 64 MiB = 67 108 864, G = 1 GiB):
  - Body = 4 + 41 (query long string) + 2 (consistency) + 1 (flags) + 2 (value count) + 4+4 (int value) + 4 (blob length) + 1 048 576 = 1 048 638 bytes, so floor(L/body) = **63** admitted per generation. The other 17 get `OverloadedException` immediately.
  - With one executor thread at ≥ 0.5 s per request, one generation drains in ≥ 31.5 s.
  - Schedule: gen 1 at t = 0, killed at t = 3 s; gen 2 at t = 4 s, killed at t = 7 s; gen 3 at t = 8 s.
  - At t ≈ 9 s at most ⌈9/0.5⌉ = 18 requests are done, so in flight ≈ 3·63 − 18 = 171 requests ≈ **171 MiB ≈ 2.7·L**. That is < G, so the global limit does not bind.
  - For L = 32 MiB: 31 per generation, so ≈ 93 − 18 = 75 MiB ≈ 2.3·L.
- **Duration:** ≈ 100 s per run (3·63·0.5 s drain) plus start-up.
- **Disk:** ≤ 3·63 MiB ≈ 190 MiB of memtable/commitlog/sstables per run.

**B3d. Observables and instruments.** Sample every 1 s from t = −5 s to the end of the drain. Log to `$S4/run/samples-<run>.tsv` with a wall-clock timestamp.
- **In-flight bytes, all IPs:**
  ```
  bin/nodetool -p 17199 sjk mx -b org.apache.cassandra.metrics:type=Client,name=RequestsSize -mg -f Value
  ```
  This is `getCurrentGlobalUsage`, which includes retired allocators.
- **Live per-IP maximum:**
  ```
  bin/nodetool -p 17199 sjk mx -b org.apache.cassandra.metrics:type=Client,name=RequestsSizeByIpDistribution -mg -f Max
  ```
  This covers live allocators only.
- **Connection state:** `bin/nodetool -p 17199 clientstats` (open native connections and their address) and the metric `type=Client,name=Connections`.
- **Actual off-heap:** `jcmd $(cat $S4/run/pid) VM.native_memory summary`, category `Other` committed. Netty's pooled direct arenas and direct buffers are allocated through `Unsafe` and are counted there on JDK 11. The pool retains freed chunks, so read the peak and compare it with the pre-run baseline.
- **Actual heap:** `jcmd <pid> GC.heap_info`, sampled every 1 s. Also take one `jcmd <pid> GC.run` followed by `GC.heap_info` at t ≈ 9.5 s, which is the predicted peak, to get live heap after a full GC. The bound-value heap copies (`CBUtil.java:480`) are reachable from queued tasks.
- **Client logs:** count of admitted (RESULT) and rejected (ERROR) frames per generation.
- **Cannot be observed directly:**
  - per-retired-allocator usage (it is out of the map, so use `RequestsSize − RequestsSizeByIpDistribution.Max`);
  - exact retained bytes per request inside Netty's arenas.

**B3e. Procedure** (per run):
1. Do the B3a yaml for this run's knobs, start the node, wait for `UN`, and create the schema (B3c). Check that `clientstats` shows **no** native connection.
2. Record baselines: `RequestsSize` (expect 0), NMT `Other`, and heap after `GC.run`.
3. Start the sampler loop (B3d) in the background, writing to the TSV.
4. Run the generations:
   - **Main (k = 3, no anchor):**
     1. `python3 $S4/gen.py 127.0.0.1 19042 1 > $S4/run/gen1.log & P1=$!`, `sleep 3`, `kill -9 $P1`.
     2. Poll `nodetool clientstats` until no connection from 127.0.0.1 is listed (≤ 1 s).
     3. Repeat with gen 2 at t ≈ 4 s, kill at t ≈ 7 s, then gen 3 at t ≈ 8 s. Leave gen 3 running.
   - **k = 1:** only gen 1, left running.
   - **Anchor control:** before gen 1, start `python3 $S4/gen.py 127.0.0.1 19042 0 0 > $S4/run/anchor.log & PA=$!` (N = 0: STARTUP only, then idle). Run the k = 3 sequence. Kill `PA` only after the drain.
   - **Global control:** G = 96 MiB, L = 64 MiB, k = 3, no anchor.
5. Wait until `RequestsSize` returns to 0 (drain ≤ 100 s), then stop the sampler and `kill -9` any remaining gen process.
6. Stop the node: `kill $(cat $S4/run/pid)`, then wait for exit. Check that `pgrep -f "s4-crl"` prints nothing.
7. Between runs, `rm -rf $S4/run/{data,commitlog,saved_caches,hints,cdc}/*`.

Run order: L = 64 MiB {k = 1, k = 3, anchor, global control}, then L = 32 MiB {k = 1, k = 3}.

**B3f. Predictions** (peak over the run; "msg" = 1 048 638 B):

| Run | L | G | `RequestsSize` peak | `ByIp.Max` peak | NMT `Other` peak − baseline | heap after GC at peak − baseline |
|---|---|---|---|---|---|---|
| k = 1 | 64 MiB | 1 GiB | 63 msg ≈ 63 MiB (≤ L) | ≈ 63 MiB | ≈ 63 MiB (± 16 MiB) | ≈ 63 MiB (± 16 MiB) |
| k = 3 | 64 MiB | 1 GiB | **≥ 2·L = 128 MiB**, expected ≈ 160–175 MiB | ≤ L (≈ 63 MiB) | ≥ 0.8 × `RequestsSize` peak | ≥ 0.8 × `RequestsSize` peak |
| anchor, k = 3 | 64 MiB | 1 GiB | ≤ L (≤ 63 msg) | ≤ L | ≈ k = 1 run | ≈ k = 1 run |
| global ctl, k = 3 | 64 MiB | 96 MiB | ≤ 96 MiB (≤ 91 msg) | ≤ L | ≤ 96 MiB + 16 | ≤ 96 MiB + 16 |
| k = 1 | 32 MiB | 1 GiB | ≈ 31 MiB | ≈ 31 MiB | ≈ 31 MiB | ≈ 31 MiB |
| k = 3 | 32 MiB | 1 GiB | **≥ 2·L = 64 MiB**, expected ≈ 70–80 MiB | ≤ L | tracks `RequestsSize` | tracks `RequestsSize` |

Client admits per generation: 63 (L = 64 MiB) / 31 (L = 32 MiB) without an anchor. In the anchor run, gens 2–3 admit only as many as gen 1 has drained (≈ 6–8 each).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| k = 3 `RequestsSize` peak ≥ 2·L while `ByIp.Max` ≤ L, with memory rising with it; anchor run ≤ L; global control ≤ 1.5·L | Claim confirmed: per-IP usage does not follow L across reconnect generations; the line-167 lifecycle is the cause; only G binds |
| k = 3 peak ≤ L + one msg per connection, without an anchor | Claim refuted: usage follows the per-IP knob |
| k = 3 peak ≥ 2·L but NMT `Other` and heap do not rise above the k = 1 run | The accounting overshoots but the memory claim is not shown (buffers released early); report as partial |
| Anchor run also ≥ 2·L | Sharing via line 167 is not what bounds per-IP; mechanism mis-traced |
| Global control does not stop at ≤ 96 MiB, or k = 1 exceeds L | Positive control failed: the limits are not in effect (yaml not loaded or wrong port); not confirmed |
| `clientstats` still lists gen g after the kill, or k = 3 admits < 63 in gens 2–3 | Limit never reset (channel not closed, or gen 1 drained too fast: check the Byteman sleep); not confirmed, so rerun with a longer sleep |

**B3h. Controls.**
- The **anchor** run is the same workload with one idle connection from the IP. `refCount` then never reaches -1, so line 167 always returns true and the allocator is shared. It isolates the reconnect path.
- The **global control** shows the same workload is capped where a limit does bind.
- **k = 1** gives the single-generation baseline for memory noise.
- Two L values show that the overshoot scales with L.
- Throw-on-overload removes the pause-mode overshoot (A3 step 7b). V4 removes the V5 per-connection queue allowance (A3 step 7c).
- Ensure no other native client (cqlsh, drivers) runs during a run: check `clientstats` at B3e step 1.

**B4. Risks and cleanup.**
- **Disk:** all node data, commitlog and hints live under `$S4/run` on local disk (≤ 2 GiB total over all runs). Clear it between runs (B3e step 7) and remove it with `rm -rf $S4` at the end.
- Nothing is built in or written to the shared source tree.
- **Ports** 17000/19042/17199 avoid the defaults on a shared host.
- **Processes:** the node (pidfile) and the gen.py processes (`kill -9 $P1 $P2 $P3 $PA`) are killed. The sampler loop is stopped with `kill %1`. Finally check `pgrep -af 'CassandraDaemon|gen.py|s4-crl'`, which must be empty. Unit tier: `ant testsome` forks a JVM that exits on completion; check `pgrep -af junit`.
- **Memory:** a 2 GiB heap plus ≤ ~400 MiB direct.

## C. Sources read

- ~/writeup-ext/playbook-autonomous.md
- ~/writeup-ext/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/transport/ClientResourceLimits.java
- src/java/org/apache/cassandra/transport/InitialConnectionHandler.java
- src/java/org/apache/cassandra/transport/PreV5Handlers.java
- src/java/org/apache/cassandra/transport/PipelineConfigurator.java
- src/java/org/apache/cassandra/transport/CQLMessageHandler.java (grep of capacity paths)
- src/java/org/apache/cassandra/transport/Dispatcher.java
- src/java/org/apache/cassandra/transport/SimpleClient.java
- src/java/org/apache/cassandra/transport/CBUtil.java
- src/java/org/apache/cassandra/transport/messages/StartupMessage.java
- src/java/org/apache/cassandra/net/AbstractMessageHandler.java
- src/java/org/apache/cassandra/net/ResourceLimits.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/cql3/QueryOptions.java (line 626)
- src/java/org/apache/cassandra/metrics/ClientMetrics.java
- src/java/org/apache/cassandra/service/StorageService.java, StorageServiceMBean.java
- test/unit/org/apache/cassandra/transport/ClientResourceLimitsTest.java
- conf/cassandra.yaml, conf/cassandra-env.sh
- CHANGES.txt, NEWS.txt
- .build/parent-pom-template.xml (Byteman version), build.xml (`testsome`, `stress-build`)
- tools/stress/src/org/apache/cassandra/stress/settings/SettingsMode.java, SettingsErrors.java (considered, not used)

## D. Stage-4 feedback

`none yet`
