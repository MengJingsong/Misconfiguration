# misconfiguration

Research repo for Cassandra/Hadoop memory-throttling misconfiguration
experiments (CloudLab-based).

## 1. Setup

Before running any script in this repo on a machine/allocation for the
first time:

```bash
cp config/environment.sh.example config/environment.sh
```

Then edit `config/environment.sh` and fill in real values for this
environment (shared-mount path, node hostnames/IPs, Cassandra version,
etc. — see the file's comments). This file is gitignored, so it's never
committed and never overwrites anyone else's values; `check-ips.sh` can
also rewrite its `CLUSTER_IP` block automatically after a CloudLab
allocation swap.

## 2. Workspace layout (on CloudLab)

This repo is checked out under a persistent, project-shared CloudLab
mount, alongside other resources that are **not** part of this repo:

```
/proj/misconfiguration-PG0/          <- shared workspace, survives node/allocation expiry
├── git-repos/
│   ├── misconfiguration/            <- THIS repo (what you're reading)
│   └── cassandra-src/               <- git clone of apache/cassandra (tag cassandra-5.0.9),
│                                        used by cassandra/if-check-exp for unit-test verification
│                                        and by codeql-queries/ for database builds;
│                                        NOT tracked by this repo
├── tools/codeql/                    <- CodeQL CLI bundle, used by codeql-queries/; NOT tracked by this repo
├── codeql-dbs/                      <- compiled CodeQL databases (e.g. cassandra-db), built from
│                                        cassandra-src by codeql-queries/; NOT tracked by this repo
├── tarfiles/                        <- downloaded release tarballs (gitignored equivalent; lives outside this repo)
├── exp/, deltas/, groups/, images/, logs/, rpms/, templates/, tiplogs/
                                      <- CloudLab platform-managed scaffold dirs, not ours
```

`git-repos/` exists because CloudLab's shared mount doesn't allow creating
directories directly under `/proj/`, so both git repos this project uses
(`misconfiguration` itself, and the separate `cassandra-src` source clone)
live as siblings one level down instead.

## 3. Path configuration: local refs vs. external refs

Scripts under `cassandra/` and `hadoop/` need two different kinds of path
information, kept in separate config files at the repo root so each can
change independently:

### 3.1 Local refs — `config/repo_layout.sh`

- **`config/repo_layout.sh`** (committed) — **local refs**: paths
  *relative to this repo's own root* (e.g. where `build-cassandra-dist`,
  `build-hadoop-src` live within `cassandra/`/`hadoop/`). Edit this only
  when folders are renamed/moved *inside* this repo.

### 3.2 External refs — `config/environment.sh`

- **`config/environment.sh`** (gitignored — copy from
  `config/environment.sh.example`, see §1 above) — **external refs**:
  facts about *where this checkout is deployed* (the shared-mount path,
  the separate `cassandra-src` clone's location, `/mydata` install paths,
  node hostnames/IPs, Cassandra version). Edit this whenever the repo is
  loaded into a new environment or CloudLab allocation swaps node
  hostnames/IPs (`orchestrator/check-ips.sh` rewrites the `CLUSTER_IP`
  block in this file automatically).

### 3.3 How scripts use them

Every script sources both files (discovering `$REPO_ROOT` via its own
location, then `config/repo_layout.sh` and `config/environment.sh` under
it), so path changes only ever need editing in one of these two files,
never scattered across individual scripts.

## 4. Experiment folders

### 4.1 `cassandra/build-cassandra-dist/`

- **`cassandra/build-cassandra-dist/`** — orchestrator (control-machine)
  and remote (per-node) scripts to install/configure/start/stop a 4-node
  Cassandra **5.0.9** binary distribution cluster.

### 4.2 `cassandra/entry-restriction-exp/`, `cassandra/if-check-exp/`

- **`cassandra/entry-restriction-exp/`**, **`cassandra/if-check-exp/`** —
  static code-path inventories of Cassandra's resource-limit checks (see
  each folder's own `README.md`, and this repo's root [`HANDOFF.md`](HANDOFF.md)
  for `if-check-exp`'s start-here brief). `if-check-exp` checks its cited
  line numbers against the `cassandra-src` clone described above; its
  *behavioral* verification step (running a trigger into the disallow
  branch) is currently deferred by decision — see that folder's `README.md`
  §7.5.

### 4.3 `codeql-queries/`

- **`codeql-queries/`** — CodeQL query packs (one per target: `cassandra/`,
  `hadoop/`) used to mechanically discover candidate if-checks for
  `cassandra/if-check-exp` (see its own [`README.md`](codeql-queries/README.md)).
  Runs against the compiled databases under `codeql-dbs/` described above.

### 4.4 `hadoop/build-hadoop-src/`

- **`hadoop/build-hadoop-src/`** — Hadoop source build scripts (JDK8 +
  Maven + protobuf 2.5.0).
