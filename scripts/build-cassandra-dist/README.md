# scripts/build-cassandra-dist

Per-node scripts that install and configure a binary distribution of
Apache Cassandra 5.0.7. These run **on each experiment node**, not on the
control machine — they're normally invoked over SSH by
[`orchestrator/cassandra/build-cluster.sh`](../../orchestrator/cassandra),
but can also be run directly on a node if you're logged in there.

They read/write local node state (`/mydata`) but download the shared
tarball from `/proj/.../tarfiles`, which is NFS-shared across the cluster —
so the download only needs to happen once, from whichever node runs
`step1.sh` first.

## Files

- **`step1.sh`** — install Cassandra:
  - Installs `openjdk-17-jdk` and `ant` via apt.
  - Downloads `apache-cassandra-5.0.7-bin.tar.gz` into
    `/proj/misconfiguration-PG0/tarfiles` (or `/proj/Misconfiguration` as a
    fallback) if it isn't already there.
  - Extracts it to `/mydata/apache-cassandra-5.0.7` if not already
    extracted.
  - Appends `JAVA_HOME_17`, `CASSANDRA_HOME`, `PATH`, and
    `CASSANDRA_USE_JDK17` exports to `~/.bashrc` (idempotent — won't
    duplicate lines on re-run).
  - Opens the Cassandra ports needed for a cluster via `ufw`: `7000`
    (inter-node), `9042` (native/CQL client), `7199` (JMX).
  - Idempotent: safe to re-run; skips any step already done.

- **`step2.sh`** — configure `cassandra.yaml` for this node:
  ```
  step2.sh <seeds> <node_ip>
  # e.g. step2.sh "10.10.1.1:7000,10.10.1.2:7000" "10.10.1.3"
  ```
  Backs up `/mydata/apache-cassandra-5.0.7/conf/cassandra.yaml` to
  `cassandra.yaml.bak`, then `sed`s in:
  - `seeds` (cluster-wide, same value on every node)
  - `listen_address`, `broadcast_address`, `broadcast_rpc_address` (this
    node's IP)
  - `rpc_address` (always `0.0.0.0`, so the native transport binds on all
    interfaces)

- **`step3.sh`** — start the Cassandra daemon on this node:
  - No-ops if Cassandra is already running (checks the pidfile).
  - Launches `$CASSANDRA_HOME/bin/cassandra -p cassandra.pid`, backgrounded
    via `nohup` with stdio redirected/closed so it survives the SSH
    session that launched it closing.
  - Logs: stdout/stderr to `$CASSANDRA_HOME/logs/cassandra-stdout.log`,
    Cassandra's own logs (including `system.log`) under
    `$CASSANDRA_HOME/logs/`.

## Usage

Normally you don't call these directly — run
[`orchestrator/cassandra/build-cluster.sh`](../../orchestrator/cassandra)
from the control machine instead, which SSHes in and runs both steps with
the right arguments on every node in the right order.

To run manually on a single node (e.g. for debugging):

```bash
bash scripts/build-cassandra-dist/step1.sh
bash scripts/build-cassandra-dist/step2.sh "<seeds>" "<this-node-ip>"
bash scripts/build-cassandra-dist/step3.sh
```

## Prerequisites

- `sudo` (passwordless, for `apt-get`/`ufw`).
- `/proj/misconfiguration-PG0` (or `/proj/Misconfiguration`) mounted and
  containing this repo.
- `/mydata` present and writable (local per-node disk, not shared).
