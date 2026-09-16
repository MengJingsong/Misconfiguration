# misconfiguration

Research repo for Cassandra/Hadoop memory-throttling misconfiguration
experiments (CloudLab-based).

## Workspace layout (on CloudLab)

This repo is checked out under a persistent, project-shared CloudLab
mount, alongside other resources that are **not** part of this repo:

```
/proj/misconfiguration-PG0/          <- shared workspace, survives node/allocation expiry
├── git-repos/
│   ├── misconfiguration/            <- THIS repo (what you're reading)
│   └── cassandra-src/               <- git clone of apache/cassandra (tag cassandra-5.0.9),
│                                        used by cassandra/if-check-exp for unit-test verification;
│                                        NOT tracked by this repo
├── tarfiles/                        <- downloaded release tarballs (gitignored equivalent; lives outside this repo)
├── exp/, deltas/, groups/, images/, logs/, rpms/, templates/, tiplogs/
                                      <- CloudLab platform-managed scaffold dirs, not ours
```

`git-repos/` exists because CloudLab's shared mount doesn't allow creating
directories directly under `/proj/`, so both git repos this project uses
(`misconfiguration` itself, and the separate `cassandra-src` source clone)
live as siblings one level down instead.

## Path configuration: local refs vs. external refs

Scripts under `cassandra/` and `hadoop/` need two different kinds of path
information, kept in separate config files at the repo root so each can
change independently:

- **`config/repo_layout.sh`** (committed) — **local refs**: paths
  *relative to this repo's own root* (e.g. where `build-cassandra-dist`,
  `oom-exp`, `build-hadoop-src` live within `cassandra/`/`hadoop/`). Edit
  this only when folders are renamed/moved *inside* this repo.

- **`config/environment.sh`** (gitignored — copy from
  `config/environment.sh.example`) — **external refs**: facts about
  *where this checkout is deployed* (the shared-mount path, the separate
  `cassandra-src` clone's location, `/mydata` install paths, node
  hostnames/IPs, Cassandra version). Edit this whenever the repo is
  loaded into a new environment or CloudLab allocation swaps node
  hostnames/IPs (`orchestrator/check-ips.sh` rewrites the `CLUSTER_IP`
  block in this file automatically).

Every script sources both files (discovering `$REPO_ROOT` via its own
location, then `config/repo_layout.sh` and `config/environment.sh` under
it), so path changes only ever need editing in one of these two files,
never scattered across individual scripts.

## Experiment folders

- **`cassandra/build-cassandra-dist/`** — orchestrator (control-machine)
  and remote (per-node) scripts to install/configure/start/stop a 4-node
  Cassandra **5.0.9** binary distribution cluster.
- **`cassandra/oom-exp/`** — tombstone-flood OOM experiment against a
  running cluster.
- **`cassandra/entry-restriction-exp/`**, **`cassandra/if-check-exp/`** —
  static code-path inventories of Cassandra's resource-limit checks (see
  each folder's own `README.md`/`HANDOFF.md`); `if-check-exp` verifies
  cases against the `cassandra-src` clone described above.
- **`hadoop/build-hadoop-src/`** — Hadoop source build scripts (JDK8 +
  Maven + protobuf 2.5.0).
