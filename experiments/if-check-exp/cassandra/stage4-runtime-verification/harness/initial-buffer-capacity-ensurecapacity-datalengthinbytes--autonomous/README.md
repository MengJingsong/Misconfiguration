# Harness — initial-buffer-capacity-ensurecapacity-datalengthinbytes--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 in the results file
[§1](../../results/initial-buffer-capacity-ensurecapacity-datalengthinbytes--autonomous.md)). Written 2026-10-26 after the step-0 audit and
before any run-1 reading. Run on `pc12` from the tree `~/s4-b7-ie` (`copy-source.sh`, `ant build-test`), node data on tmpfs
`/dev/shm/s4-b7-ie-data` (wiped per lifetime), logs in `~/s4-b7-ie-logs/<run>/`. Port slot 3: loopback 127.0.3.1, JMX 7130, Byteman 19130,
native 9042, storage 7000 (both on 127.0.3.1 only).

| File | Tier | What it does |
|---|---|---|
| `EnsureCapacityProbe.java` | unit (B2) | Plain `main` (not `ant testsome`, which overrides `-Xmx`). Calls the public `ByteSourceInverse.readBytes(ByteSource,int)` / `getUnescapedBytes`; reads the calling thread's allocated bytes; compares with a mirror of the doubling code (sum of align8(16+len) over every array). Sets: `small` (128m), `full` (1g, up to 64<<20), `big` (4g, 1<<30 and (1<<30)+1). Instrument checks first (`ensureCapacity` known answers by reflection, `Arrays.copyOf` baseline, mirror known answer), then the sweep (initial 32), the `initialBufferCapacity` knob, `initial 0` (info), the escaped path, retained heap, and the positive control `copyBytes` with M = N-1, N, N+5. `STAGE4 check <name> ok\|MISMATCH` lines. Each point: 5 warm-ups, then the median of 5 (3 for N >= 16 MiB) measurements; all values printed. |
| `unit-run.sh <run>` | unit | Compiles the probe (no file is added to the tree), runs the three sets, prints EXPECTED lines. |
| `ec.btm`, `Ec.java` | cluster (B3d) | Byteman, observation only: per `readBytes(ByteSource,int)` call the thread's allocated bytes, the result length, the first caller outside `ByteSourceInverse`; `rbexc` when the call throws. `Ec` goes on the boot class path. |
| `JfrSum.java` | cluster | JDK 11 has no `jdk.ObjectAllocationSample` (JDK 16+) and no `jfr` summary of stacks; reads `jdk.ObjectAllocationInNewTLAB` (weight tlabSize) and `OutsideTLAB` (allocationSize) and reports the share whose stack holds `ensureCapacity` / `readBytes`. |
| `Jmx.java`, `client.py` | cluster | JMX reader (copied from the hints harness); protocol-4 driver with password authentication (`ready`, `setup`, `load`, `big`, `query`). |
| `cluster-run.py <arm>` | cluster (B3e) | One lifetime per arm; arms `k16 k1k k32k k64k k16m k64km k16n k64kn ctl` (`warm` = shakedown). `selfcheck.py` re-parses the raw files. |

**Reading rules, fixed before run 1.** A call's allocation is the Byteman line's `bytes`; its decoded size is `len`. Retained live heap =
`GC.class_histogram` total (full GC) at the end minus the baseline, after `nodetool invalidatekeycache`. The EXPECTED lines in
`cluster-run.py` (written before the first reading) are the case's B3f relations turned into thresholds: `len` of the `SegmentMetadata.write`
calls within [K, 1.02K+64]; allocation per call at most 5.2 x len; no `rbexc`; JFR share under `ensureCapacity` below 1 percent;
no client error and no ERROR log line for a legal K; in arm `ctl` all twenty 4 KiB-value inserts are rejected at fail threshold 1 KiB.
Retained heap and disk are compared across K in the self-check (B3f: no change attributable to the decode buffer; the case gives no
number, so the comparison is: difference between K = 65535 and K = 16 under 16 MiB).

Run order (run 1), each lifetime its own background job:

```bash
H=<repo>/cassandra/if-check-exp/stage4-runtime-verification/harness/initial-buffer-capacity-ensurecapacity-datalengthinbytes--autonomous
bash $H/unit-run.sh run1
for a in k16 k1k k32k k64k k16m k64km k16n k64kn ctl; do EC_RUN=run1 python3 -I $H/cluster-run.py $a; done
python3 -I $H/selfcheck.py run1
```
