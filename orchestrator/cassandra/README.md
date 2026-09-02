# orchestrator/cassandra

Driver scripts for bringing up a 4-node Cassandra cluster from a **control
machine** (e.g. WSL) that has SSH access to the experiment nodes but does
**not** have `/proj` mounted. These scripts never touch Cassandra directly —
they SSH out to each node and invoke the per-node scripts in
[`scripts/build-cassandra-dist`](../../scripts/build-cassandra-dist), which
live on shared NFS storage (`/proj/misconfiguration-PG0`) and run there.

## Files

- **`config.sh`** — shared config, sourced by the other scripts (not run
  directly). Defines:
  - `SSH_USER` / `PREFIX` / `POSTFIX` — how to reach each node from the
    control machine (`<prefix>.cloudlab.umass.edu`).
  - `CLUSTER_IP` — each node's experiment-LAN IP (`10.10.1.x`), used for
    Cassandra's `listen_address`/`broadcast_address`/seeds. Only routable
    inside the experiment, not from the control machine.
  - `SEED_INDEXES` — which nodes act as Cassandra seeds.
  - `REMOTE_SCRIPTS_DIR` / `REMOTE_CASSANDRA_HOME` — absolute paths on the
    nodes (deliberately not sourced from `~/.bashrc` over SSH — see comment
    in the file for why).
  - Helper functions `ssh_node`, `is_seed`, `seeds_string`.

- **`check-ips.sh`** — discovers each node's current experiment-LAN IP by
  SSHing in and inspecting interfaces, then rewrites the `CLUSTER_IP` block
  in `config.sh` in place (keeping a `config.sh.bak` of the previous
  version). Safe to re-run any time, e.g. after a CloudLab experiment swap
  changes the LAN addresses.

- **`build-cluster.sh`** — installs and configures Cassandra on all 4 nodes:
  1. Runs `build-cassandra-dist/step1.sh` on node0 first, to prime the
     shared tarball download on NFS.
  2. Runs `step1.sh` on the remaining nodes in parallel.
  3. Runs `build-cassandra-dist/step2.sh` on every node sequentially, to
     write each node's `cassandra.yaml` with the right seeds/addresses.
  4. Both steps are idempotent — safe to re-run after a partial failure.

- **`start-cluster.sh`** — starts the Cassandra daemon on every node via
  `build-cassandra-dist/step3.sh`:
  1. Starts the seed nodes (`SEED_INDEXES` in `config.sh`) one at a time,
     waiting for each to report itself `UN` (Up/Normal) in `nodetool
     status` before starting the next -- starting seeds concurrently on a
     brand new cluster risks a gossip/schema race during bootstrap.
  2. Starts the remaining (non-seed) nodes in parallel once all seeds are
     up, then waits for each of those to report `UN` too.
  3. Prints final cluster-wide `nodetool status` from node0.
  4. Idempotent -- re-running skips any node where Cassandra is already
     running (`step3.sh` checks its pidfile).

## Usage

Run from the control machine, with SSH access to all 4 nodes already
working (keys distributed via `scripts/DistributeSSHKey.sh` on each node):

```bash
cd orchestrator/cassandra

# Only needed once, or after node IPs change (e.g. experiment swap):
./check-ips.sh

# Install + configure Cassandra on all 4 nodes:
./build-cluster.sh

# Start the Cassandra daemon on all 4 nodes (seeds first, then the rest):
./start-cluster.sh
```

## Prerequisites

- Passwordless SSH from the control machine to every node
  (`ssh jason92@<prefix>.cloudlab.umass.edu`).
- `/proj/misconfiguration-PG0` present and up to date on every node (it's
  the same NFS mount shared across the cluster, so a single `git pull`
  there updates all nodes at once).
