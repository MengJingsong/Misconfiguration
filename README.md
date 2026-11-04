# misconfiguration

> **Always check [`HANDOFF.md`](HANDOFF.md) first.** It tells you which personal handoff file to
> use: **Jingsong Meng** → [`HANDOFF-Jingsong.md`](HANDOFF-Jingsong.md), **Yang Wang** →
> [`HANDOFF-Yang.md`](HANDOFF-Yang.md). Common notes go in `HANDOFF.md`; personal handoff
> instructions go in your own file.

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

Each experiment folder covers some subset. An experiment is **a method, not a
system**: its README, templates and playbooks are system-agnostic, and its
findings for each system live in a per-system subfolder (`<exp>/cassandra/`,
`<exp>/hadoop/`). The two `*-exp` folders below both cover **Target 1 +
Target 2 together** — each result names a constraint *and* shows the code that
enforces it — and both leave Target 3 out of scope, noting bypass-relevant
observations in passing for later use. `OOM-exp` carries out **Target 3**,
taking the constraints `if-check-exp` found as its input:

| Folder | Status | Direction |
|---|---|---|
| [`experiments/if-check-exp/`](experiments/if-check-exp/README.md) | **active** | backward: from the enforcing check → the constraint's declaration |
| [`experiments/entry-restriction-exp/`](experiments/entry-restriction-exp/README.md) | paused | forward: from the constraint's declaration → the places it restricts |
| [`experiments/OOM-exp/`](experiments/OOM-exp/README.md) | **active** | Target 3: drive a test node OOM using `if-check-exp`'s constraints (convergence, bypass) |

**Systems covered.** Most completed work is **Cassandra** and lives under each
experiment's `cassandra/` subfolder. **Hadoop** has started: its source is vendored
(`systems/hadoop/source/`, 3.4.2) and `if-check-exp` stage 1 is done
([`experiments/if-check-exp/hadoop/stage1-codeql-preprocessing/`](experiments/if-check-exp/hadoop/stage1-codeql-preprocessing/README.md));
stage 2 is done (9,684 units banded; `hadoop/stage2-ai-preprocessing/`).
The other Hadoop subfolders (`<exp>/hadoop/`) are still empty.

`if-check-exp` and `entry-restriction-exp` are deliberately **not
cross-referenced** — a line may legitimately appear in both. `OOM-exp` is the
one folder that intentionally depends on another (`if-check-exp`).

**Targets are not stages.** An experiment folder may number its own *working
stages* (`if-check-exp` has three: structural → lexical → semantic). Those
numbers describe how strongly a finding has been evidenced inside that
folder; they do not map onto the target numbers above. See
[`experiments/if-check-exp/README.md`](experiments/if-check-exp/README.md) §1.1.

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

## 2. Workspace layout

### 2.1 This repo's own layout

Two axes: **experiments** (methods, system-agnostic) and **systems** (the
software each method is applied to). Per-system findings live where the two
cross, under `experiments/<exp>/<system>/`.

```
experiments/                 <- methods; each README/template/playbook is system-agnostic
├── if-check-exp/            <- Target 1+2 (active): method docs + stage{1..4}/ specs
│   ├── cassandra/           <-   Cassandra findings: cases, results, harness runs, CSVs
│   └── hadoop/              <-   Hadoop findings: stages 1–2 done (2026-11-04), stages 3–4 empty
├── entry-restriction-exp/   <- Target 1+2 (paused): method docs + templates
│   ├── cassandra/           <-   Cassandra codepath/summary cases
│   └── hadoop/              <-   scaffold (empty)
└── OOM-exp/                 <- Target 3 (active): method docs + playbooks
    ├── cassandra/           <-   Cassandra convergence/bypass cases
    └── hadoop/              <-   scaffold (empty)
systems/
├── cassandra/
│   ├── source/              <- pinned apache/cassandra @ tag cassandra-5.0.9 (unmodified)
│   ├── build-dist/          <- 4-node cluster install/run scripts (orchestrator + remotes)
│   └── conf/                <- stock config baseline to diff against
└── hadoop/
    ├── source/              <- pinned apache/hadoop @ tag rel/release-3.4.2 (unmodified)
    ├── build-src/           <- Hadoop source build scripts (JDK8 + Maven + protobuf)
    └── conf/                <- stock config baseline (to populate)
codeql-queries/              <- CodeQL packs: cassandra/, hadoop/, common/ (stage 1 of if-check-exp)
config/                      <- repo_layout.sh (local refs), environment.sh.example (external refs)
README.md  HANDOFF*.md       <- this file and the start-here briefs
```

Adding a new system means adding a `systems/<system>/` tree and a
`<exp>/<system>/` subfolder under each experiment — the method docs are not
duplicated.

### 2.2 On CloudLab

This repo is checked out under a persistent, project-shared CloudLab
mount, alongside other resources that are **not** part of this repo:

```
/proj/misconfiguration-PG0/          <- shared workspace, survives node/allocation expiry
├── git-repos/
│   └── cassandra-src/               <- older git clone of apache/cassandra (tag cassandra-5.0.9);
│                                        superseded by this repo's systems/cassandra/source/
│                                        (see below); NOT tracked by this repo
├── tools/codeql/                    <- CodeQL CLI bundle, used by codeql-queries/; NOT tracked by this repo
├── codeql-dbs/                      <- compiled CodeQL databases (e.g. cassandra-db), built from
│                                        the Cassandra source by codeql-queries/; NOT tracked by this repo
├── tarfiles/                        <- downloaded release tarballs (gitignored equivalent; lives outside this repo)
├── exp/, deltas/, groups/, images/, logs/, rpms/, templates/, tiplogs/
                                      <- CloudLab platform-managed scaffold dirs, not ours
```

`git-repos/` exists because CloudLab's shared mount doesn't allow creating
directories directly under `/proj/`, so the `cassandra-src` source clone lives
one level down instead.

**Cassandra source.** Since 2026-10-22 the source is part of this repo:
`systems/cassandra/source/` is the `apache/cassandra` tree at tag
`cassandra-5.0.9`, unmodified (exported with `git archive`; its own
`.gitattributes` keeps the bytes as upstream). Both Cassandra experiment
folders check every `file:line` against it and codeql-queries/ builds its
databases from it. Never build in it or add files to it; copy it to local disk
first (`experiments/if-check-exp/cassandra/stage4-runtime-verification/environment.md` §2).
Records dated before 2026-10-22 name the `cassandra-src` clone, which held the
same files.

**Hadoop source.** Since 2026-11-04 the Hadoop source is part of this repo too:
`systems/hadoop/source/` is the `apache/hadoop` tree at tag `rel/release-3.4.2`
(commit `84e8b89`), unmodified, exported with `git archive`. Its tree hash equals
upstream's root tree (`41e2128`), so every path, mode and byte matches. Unlike
Cassandra, upstream ships its own `.gitattributes` files, which are kept as they are
(they normalize line endings only, and upstream stores no CRLF files). Hadoop
`file:line` citations are checked against this tree. As with Cassandra, never build
in it or add files to it: copy it to local disk first. Upstream's own `.gitignore`
applies inside it (`*.patch`, `**/.keep`, ...), so a re-import must `git add -f`
the 12 upstream files those patterns hide. The release tarball that
`systems/hadoop/build-src/` downloads (`hadoop-3.4.2-src.tar.gz`) is a separate
artifact; cite the git tree, not the tarball.

**Checkout location.** The repo was removed from the shared mount on 2026-10-06 so that the short path's
stage-4 executor, which every node could reach through that mount, could not read the long path's files. That
reason ended on 2026-10-19, when the blind executor and the leakage controls were removed (stage 3 now has an
autonomous and a guided agent, and stage 4 runs every case file in one folder), so a checkout under `git-repos/` is
allowed again. What the old copy held that is not on GitHub (`config/environment.sh`, the gitignored CodeQL results,
a `.claude/` folder) is archived at `/proj/misconfiguration-PG0/tarfiles/repo-copy-untracked-2026-10-06.tgz`.

## 3. Path configuration: local refs vs. external refs

Scripts under `systems/` and `experiments/` need two different kinds of path
information, kept in separate config files at the repo root so each can
change independently:

### 3.1 Local refs — `config/repo_layout.sh`

- **`config/repo_layout.sh`** (committed) — **local refs**: paths
  *relative to this repo's own root* (e.g. where `build-dist` and `build-src`
  live under `systems/cassandra/`/`systems/hadoop/`, and where each experiment
  lives under `experiments/`). Edit this only when folders are renamed/moved
  *inside* this repo.

### 3.2 External refs — `config/environment.sh`

- **`config/environment.sh`** (gitignored — copy from
  `config/environment.sh.example`, see §1 above) — **external refs**:
  facts about *where this checkout is deployed* (the shared-mount path,
  the Cassandra source location (`CASSANDRA_SRC`), `/mydata` install paths,
  node hostnames/IPs, Cassandra version). Edit this whenever the repo is
  loaded into a new environment or CloudLab allocation swaps node
  hostnames/IPs (`orchestrator/check-ips.sh` rewrites the `CLUSTER_IP`
  block in this file automatically).

### 3.3 How scripts use them

Every script sources both files (discovering `$REPO_ROOT` via its own
location, then `config/repo_layout.sh` and `config/environment.sh` under
it), so path changes only ever need editing in one of these two files,
never scattered across individual scripts.

## 4. Experiments (`experiments/`)

Each experiment is a **method** (README format spec, templates, playbooks,
stage structure) that is system-agnostic. Per-system findings live under
`<exp>/<system>/`; today that is `<exp>/cassandra/` (populated) and
`<exp>/hadoop/` (scaffold, empty).

### 4.1 `experiments/if-check-exp/`, `experiments/entry-restriction-exp/`

- **`experiments/if-check-exp/`** (active) and
  **`experiments/entry-restriction-exp/`** (paused) — static code-path
  inventories of a system's resource-limit checks, approached from opposite
  directions (§0). Each has its own `README.md` (format spec) and its own
  start-here brief: the root [`HANDOFF.md`](HANDOFF.md) for `if-check-exp`,
  and [`experiments/entry-restriction-exp/HANDOFF.md`](experiments/entry-restriction-exp/HANDOFF.md)
  for the paused one.

  `if-check-exp` organises its work as **three stages by evidence standard** —
  structural (CodeQL) → lexical (rows only) → semantic (source open). The stage
  method docs live at the experiment root; each stage's per-system output lives
  under `<exp>/<system>/<stage>/`. Every cited line is checked against that
  system's pinned source (for Cassandra, `systems/cassandra/source/`).
  **Behavioral verification (running a trigger into the disallow branch) is out
  of scope** as of 2026-09-23: a case's evidence is its traced code path.

### 4.2 `experiments/OOM-exp/`

- **`experiments/OOM-exp/`** (active) — **Target 3**: drive a test node out of
  memory using the constraints `if-check-exp` found, via convergence (several
  usages reaching capacity at once) and bypass (getting past a single check).
  Method docs and playbooks live at the root; per-system cases under
  `OOM-exp/<system>/cases/`.

### 4.3 `codeql-queries/`

- **`codeql-queries/`** — CodeQL query packs (one per target: `cassandra/`,
  `hadoop/`, plus shared `common/`). The Cassandra pack is **stage 1** of
  `if-check-exp`: it mechanically narrows candidate if-checks, with no keyword
  list (see its own [`README.md`](codeql-queries/README.md)). Runs against the
  compiled databases under `codeql-dbs/` described above; its CSV output is
  gitignored and regenerated per machine. The Hadoop pack runs the same chain
  (shared logic in `common/lib/IfCheckCore.qll`) against `codeql-dbs/hadoop-db`.
  (This folder predates the restructure and keeps its own per-target split; it
  is not moved under `systems/`.)

## 5. Systems (`systems/`)

Per-system source, build tooling and config baseline. A new system is added
here alongside a `<exp>/<system>/` subfolder under each experiment.

### 5.1 `systems/cassandra/`

- **`systems/cassandra/source/`** — the pinned `apache/cassandra` tree at tag
  `cassandra-5.0.9` (see §2.2). Never build in it or add files to it.
- **`systems/cassandra/build-dist/`** — orchestrator (control-machine) and
  remote (per-node) scripts to install/configure/start/stop a 4-node Cassandra
  **5.0.9** binary distribution cluster.
- **`systems/cassandra/conf/`** — reference copies of a stock Cassandra config
  set: `cassandra.yaml`, `cassandra-env.sh`, `jvm17-server.options`. Kept as
  the untouched baseline to diff an experiment's config against. No script
  reads them, and nothing is generated from them.

  **Caveat (checked 2026-09-24):** `cassandra-env.sh` and
  `jvm17-server.options` are byte-identical to `conf/` at the pinned tag
  `cassandra-5.0.9`, but **`cassandra.yaml` is not** — it is missing sections
  that 5.0.9 ships (e.g. the `paxos_variant` block), so it predates the
  pinned tag. It was committed in `56a7d0b`, before the repo pinned 5.0.9.
  Re-copy it from `systems/cassandra/source/conf/` before treating it as the
  5.0.9 baseline.

### 5.2 `systems/hadoop/`

- **`systems/hadoop/build-src/`** — Hadoop source build scripts (JDK8 + Maven
  + protobuf 2.5.0).
- **`systems/hadoop/source/`** — the pinned `apache/hadoop` tree at tag
  `rel/release-3.4.2` (see §2.2). Never build in it or add files to it.
- **`systems/hadoop/conf/`** — placeholder (empty) for a stock Hadoop config
  baseline, to be populated when the experiments are applied to Hadoop.
