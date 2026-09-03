# oom-exp/exp1 — Tombstone Flood

Reproduces a documented real-world Cassandra failure (tombstone-scan OOM,
similar to [CASSANDRA-8559](https://issues.apache.org/jira/browse/CASSANDRA-8559))
against our own self-controlled cluster: flood a single partition with
tombstones, then force the coordinator to materialize all of them into
heap at once with an unbounded scan.

## Files

- **`remotes/`** — runs on a node (invoked over SSH); **`orchestrator/`** —
  runs on the control machine (SSHes/connects out to the nodes), same split
  as [`../../build-cassandra-dist`](../../build-cassandra-dist). Everything
  in this experiment is a control-machine script, so it all lives under
  `orchestrator/` except `remotes/step2b.sh` (see "Deploying the relaxed
  guardrails" below).

- **`orchestrator/setup.py`** — one-time schema setup. Connects to
  `<NODE_IP>` (a node's public hostname, e.g. `pc66.cloudlab.umass.edu` —
  reachable from the control machine; the internal `10.10.1.x` addresses
  are not) and creates keyspace `oomtest` (RF=1) with two tables: `wide`
  (used by `tombstone_flood.py`) and `bigpart` (reserved for a separate
  huge-partition test). Idempotent (`CREATE ... IF NOT EXISTS`).
  ```bash
  python3 orchestrator/setup.py <NODE_IP>
  ```

- **`orchestrator/tombstone_flood.py`** — the experiment itself. Talks CQL
  directly to `<NODE_IP>:9042` for the read/write workload, and separately
  shells out to `ssh jason92@<NODE_IP> nodetool ...` for heap monitoring —
  both from the control machine, using the same passwordless SSH set up
  for `../../build-cassandra-dist/orchestrator/*.sh`.
  ```bash
  python3 orchestrator/tombstone_flood.py <NODE_IP> [--rows N] [--blob-size N] \
      [--concurrency N] [--auto-adjust] [--skip-phase-5]
  ```

## How it works

Target table: `oomtest.wide (pk int, ck int, val blob, PRIMARY KEY (pk, ck))`.
Everything lands in a single wide partition (`pk = 1`), which is the
point — Cassandra has to hold the whole partition's tombstones in the
coordinator's heap at once when it's scanned unpaged.

**Pre-flight:** reads current heap usage via `nodetool info`, then
estimates two things: how much heap the write phase itself needs
(`rows × (blob_size + ~200B row overhead)`) and how much the tombstone
scan needs (`rows × ~200B` per tombstone — a live cell's on-disk value
size doesn't matter, tombstones cost roughly the same in heap regardless).
If the write phase alone would eat >80% of available heap, it warns (and
with `--auto-adjust`, halves the row count and retries) — the intent is a
heap that survives phases 1-4 comfortably but reliably OOMs on phase 5.

**Phase 1 — Write:** insert `--rows` (default 800,000) rows with a small
`--blob-size` (default 8B) blob each, asynchronously at `--concurrency`
(default 256), in 50K-row batches. A background thread polls
`nodetool info`/`gcstats` every 2s during this phase so a write-phase OOM
(a different, unintended failure) can be told apart from the intended
scan-phase OOM. `--skip-phase-5` stops here, to validate the write path
in isolation.

**Phase 2 — Flush:** `nodetool flush oomtest wide`, pushing the live rows
out of the memtable and onto SSTables.

**Phase 3 — Delete:** delete every row just written (same
batched/concurrent approach as Phase 1) — each becomes a tombstone.

**Phase 4 — Flush:** flush again, so the tombstones are on disk, not
sitting in the memtable.

**Phase 5 — Scan (the attack):** `SELECT * FROM wide WHERE pk = 1` with
paging disabled (`fetch_size=None`) at `CL=ONE`. This forces the
coordinator to load every tombstone for the partition into heap in one
shot. Heap is monitored throughout; the result is classified as OOM
(success), timeout (possible OOM — server may be GC-thrashing), or an
unexpected clean scan (heap was bigger than assumed, tombstones got
compacted away, or row count was too low).

## Guardrails this experiment relies on being relaxed

Cassandra's own safety nets would normally stop this before it reaches
OOM. `../updated-conf` (vs. Cassandra's defaults in `../../original-conf`)
relaxes the ones that matter here:

| Setting | Default | Relaxed to | Why |
|---|---|---|---|
| `tombstone_warn_threshold` / `tombstone_failure_threshold` | 1000 / 100000 | `2147483647` (effectively off) | so the query isn't aborted before it OOMs |
| `MAX_HEAP_SIZE` (cassandra-env.sh) | half of system RAM | `512M` | makes OOM reachable without absurd row counts |
| `read_request_timeout` / `range_request_timeout` / `request_timeout` | 5s / 10s / 10s | 60s / 120s / 120s | client shouldn't give up before the server actually OOMs |
| `autocompaction_on_startup_enabled` | (on) | `false` | tombstones shouldn't get compacted away mid-experiment (the script also calls `nodetool disableautocompaction` itself) |
| `dump_heap_on_uncaught_exception`, `-Dcassandra.printHeapHistogramOnOutOfMemoryError=true` | off | on | capture evidence when it happens |

The plan (see the "Progress Report" doc) is to get a reliable OOM under
this relaxed config, then progressively tighten each guardrail back
toward its default and re-run, to find the point where the guardrail
actually stops the attack.

## Deploying the relaxed guardrails

`../updated-conf/{cassandra.yaml,cassandra-env.sh}` also carries a
hardcoded single-node address (left over from an earlier single-node
experiment) and unrelated tuning not documented above, so it isn't copied
onto nodes wholesale. Instead, [`remotes/step2b.sh`](remotes/step2b.sh)
sed-patches just the 5 guardrails in the table above onto each node
(after `../../build-cassandra-dist/remotes/step2.sh` has already set that
node's addressing), and
[`orchestrator/apply-relaxed-conf.sh`](orchestrator/apply-relaxed-conf.sh)
runs it across all 4 nodes and restarts the cluster:

```bash
cd orchestrator
./apply-relaxed-conf.sh
```

Verified deployed on the 4-node cluster as of 2026-09-03 (`nodetool info`
on node0 reports `Heap Memory (MB): .../512.00`, and all 5 guardrail
values above are confirmed patched into every node's `conf/cassandra.yaml`
/ `cassandra-env.sh`).

## Known issues (as of 2026-09-03)

1. `oomtest` keyspace doesn't exist yet on the cluster — run
   `orchestrator/setup.py <NODE_IP>` before `tombstone_flood.py`.
2. Phase 5 of `tombstone_flood.py` has not yet actually been run against
   the relaxed-guardrail cluster to confirm it OOMs as designed — the
   config deployment above is done, but the experiment itself is still
   unverified end-to-end. The default `--rows 800000` was likely tuned
   against a much larger heap than the 512M this cluster now runs at:
   `preflight_checks()` estimates ~456MB available (512M heap minus a
   56MB metaspace allowance) against only ~153MB of tombstones at
   800,000 rows (`rows × 200B`), and will print
   `Phase 5 may NOT OOM ... Consider shrinking heap to ~203MB` at
   startup. It only *suggests* shrinking the heap, though — it doesn't
   suggest raising `--rows` to compensate, and doesn't do so
   automatically the way `--auto-adjust` does for the opposite (Phase 1
   too heavy) case. Since live rows and tombstones cost about the same
   per-row heap in this script's model, raising `--rows` enough to
   guarantee Phase 5 OOMs risks pushing Phase 1's write pressure over its
   own 80%-of-available warning threshold too — worth deciding
   deliberately (higher `--rows`, or a smaller pinned heap) before the
   real run rather than trusting the default.

Fixed in the same pass as the above (2026-09-03): `tombstone_flood.py`'s
`from cassandra import OperationTimedOut, NoHostAvailable, ConnectionShutdown`
was wrong for cassandra-driver 3.29.3 — only `OperationTimedOut` actually
lives in the top-level `cassandra` package; `NoHostAvailable` is in
`cassandra.cluster` and `ConnectionShutdown` is in `cassandra.connection`.
The script would have failed on import on any real driver install; never
caught because the driver had never actually been installed anywhere
before now.
