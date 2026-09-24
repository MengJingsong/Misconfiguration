# misconfiguration

Research repo for the **misconfiguration** project: Cassandra/Hadoop
memory-throttling misconfiguration experiments (CloudLab-based).

## 0. Project overview — the three targets

The whole project works toward three targets. They are **project scope,
shared by every experiment folder** in this repo — not owned by any one of
them:

| Target | Question |
|---|---|
| **Target 1** | Identify all resource constraints (config, hardcoded constants, variable types, ...) that limit memory/CPU usage. |
| **Target 2** | Show *how* each constraint restricts usage, via the exact code path. |
| **Target 3** | Investigate bypass methods that could lead to resource exhaustion. |

Each experiment folder covers some subset. The two Cassandra folders both
cover **Target 1 + Target 2 together** — each result names a constraint *and*
shows the code that enforces it — and both leave Target 3 out of scope,
noting bypass-relevant observations in passing for later use:

| Folder | Status | Direction |
|---|---|---|
| [`cassandra/if-check-exp/`](cassandra/if-check-exp/README.md) | **active** | backward: from the enforcing check → the constraint's declaration |
| [`cassandra/entry-restriction-exp/`](cassandra/entry-restriction-exp/README.md) | paused | forward: from the constraint's declaration → the places it restricts |

They are deliberately **not cross-referenced** — a line may legitimately
appear in both.

**Targets are not stages.** An experiment folder may number its own *working
stages* (`if-check-exp` has three: structural → lexical → semantic). Those
numbers describe how strongly a finding has been evidenced inside that
folder; they do not map onto the target numbers above. See
[`cassandra/if-check-exp/README.md`](cassandra/if-check-exp/README.md) §1.1.

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
│                                        read by both Cassandra experiment folders (every
│                                        file:line is checked against it) and used by
│                                        codeql-queries/ for database builds;
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

- **`cassandra/if-check-exp/`** (active) and
  **`cassandra/entry-restriction-exp/`** (paused) — static code-path
  inventories of Cassandra's resource-limit checks, approached from opposite
  directions (§0). Each has its own `README.md` (format spec) and its own
  start-here brief: the root [`HANDOFF.md`](HANDOFF.md) for `if-check-exp`,
  and [`cassandra/entry-restriction-exp/HANDOFF.md`](cassandra/entry-restriction-exp/HANDOFF.md)
  for the paused one.

  `if-check-exp` organises its work as **three stages by evidence standard** —
  structural (CodeQL) → lexical (rows only) → semantic (source open) — with
  one folder each. Every cited line is checked against the `cassandra-src`
  clone described above. **Behavioral verification (running a trigger into
  the disallow branch) is out of scope** as of 2026-09-23: a case's evidence
  is its traced code path.

### 4.3 `codeql-queries/`

- **`codeql-queries/`** — CodeQL query packs (one per target: `cassandra/`,
  `hadoop/`). The Cassandra pack is **stage 1** of `if-check-exp`: it
  mechanically narrows candidate if-checks, with no keyword list (see its own
  [`README.md`](codeql-queries/README.md)). Runs against the compiled
  databases under `codeql-dbs/` described above; its CSV output is
  gitignored and regenerated per machine. The Hadoop pack is scaffold only.

### 4.4 `cassandra/original-conf/`

- **`cassandra/original-conf/`** — reference copies of a stock Cassandra
  config set: `cassandra.yaml`, `cassandra-env.sh`, `jvm17-server.options`.
  Kept as the untouched baseline to diff an experiment's config against. No
  script reads them, and nothing is generated from them.

  **Caveat (checked 2026-09-24):** `cassandra-env.sh` and
  `jvm17-server.options` are byte-identical to `conf/` at the pinned tag
  `cassandra-5.0.9`, but **`cassandra.yaml` is not** — it is missing sections
  that 5.0.9 ships (e.g. the `paxos_variant` block), so it predates the
  pinned tag. It was committed in `56a7d0b`, before the repo pinned 5.0.9.
  Re-copy it from `cassandra-src/conf/` before treating it as the 5.0.9
  baseline.

### 4.5 `hadoop/build-hadoop-src/`

- **`hadoop/build-hadoop-src/`** — Hadoop source build scripts (JDK8 +
  Maven + protobuf 2.5.0).
