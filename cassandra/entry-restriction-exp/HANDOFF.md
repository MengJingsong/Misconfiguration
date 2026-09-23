# Entry-Restriction Exp — Handoff

Start-here brief for a session picking up `entry-restriction-exp`. Read this,
then [`README.md`](README.md) for the full format spec.

## Status: paused, not abandoned (as of 2026-09-23)

**Several pairs have been found and written up.** Work then stopped by
decision so effort could go to the sibling experiment
[`../if-check-exp/`](../if-check-exp/README.md), which is the repo's active
folder. **This folder may be resumed in the future** — nothing here is
withdrawn or superseded, and the recorded pairs stand as finished results.

A session should **not** start new work here unless Jingsong asks for it.

## What this folder is

Part of the **misconfiguration** research project, scoped to **Apache
Cassandra 5.0.9**, covering **Target 1 + Target 2** (see the repo-root
[`README.md`](../../README.md) §0 for the three project-wide targets;
Target 3, bypass analysis, is out of scope here though each pair seeds it via
its `Bypass Potential` field).

**Unit of record: the entry-restriction pair.** An *entry point* is a
resource constraint (config, hardcoded constant, variable type). A single
entry point may restrict resource usage at several code locations; each
`(entry point, one restriction location)` combination is recorded
independently as a pair.

**Method: constraint-first AI deep read.** A session reads the Cassandra
source and traces *forward* — from where the constraint is declared or
initialised, following the value to the places it actually restricts
something. Every real pair is then **manually checked** before being
recorded.

This is the mirror image of `if-check-exp`, which traces *backward* from the
code that enforces a limit to the constraint's declaration. Both serve
Targets 1 + 2; neither is a subset of the other, and they are **deliberately
not cross-referenced** — a line may legitimately appear in both.

> **`if-check-exp`'s stage numbers do not apply here.** That folder numbers
> its working stages (structural → lexical → semantic) to say how strongly a
> line has been evidenced. This folder has no such ladder: it is deep reading
> plus manual confirmation throughout. What this folder calls **code-trace
> steps** are the named hops along one constraint's code flow — a different
> thing entirely.

## Entry points covered

| Entry point | Pairs | Notes |
|---|---|---|
| `memtable_heap_space` | 2 | Restriction 1: soft threshold triggering an async flush of the largest memtable. Restriction 2: hard limit that blocks the write thread on a wait queue. |
| `memtable_flush_writers` | 3 | Thread-pool size capping concurrent flushes — a *weak proxy* for throughput. Also: the flush-task queue is unbounded (`Integer.MAX_VALUE`) and untunable, so tasks pile up in memory rather than being throttled. |
| `file_cache_size` | 2 | Restriction 1: weight bound on the `ChunkCache` LRU — soft and self-correcting, since a miss inserts unconditionally and eviction runs afterward, so it can be exceeded under concurrent miss load. Restriction 2: hard check in the buffer pool, but on refusal the caller falls back to *untracked* direct allocation. |

See [`_INDEX.md`](_INDEX.md) for the authoritative per-pair table.

## Where things live

- **Repo:** `MengJingsong/Misconfiguration` on GitHub.
- **Folder:** `cassandra/entry-restriction-exp/`
  - `README.md` — format spec: the pair concept, required fields, naming,
    code-trace steps, failure modes checked per pair.
  - `_INDEX.md` — master index of every pair.
  - `_TEMPLATE-summary.md` / `_TEMPLATE-codepath.md` — the two files each
    pair is written as.
  - `<entry_point>/` — one folder per entry point.
- **Cassandra source:** `/proj/misconfiguration-PG0/git-repos/cassandra-src`,
  a clone of `apache/cassandra` at tag `cassandra-5.0.9`. Confirm with
  `git describe --tags`. **Always grep/read the local clone to verify a line
  number** — every `file:line` here is pinned to that tag and will drift on
  any other checkout.

## Working preferences

- **Plan before editing.** For changes to rules, naming, scope or folder
  structure, give an opinion or an update plan first and wait for Jingsong's
  go-ahead. Small factual fixes don't need this.
- **Commit and push only on request**, and separately — never either
  unprompted.
- **Sync before restructuring.** Jingsong also uploads files to GitHub
  directly; `git fetch` and compare with `origin/main` before renaming or
  reorganizing. If local edits exist, stash, fast-forward, then re-apply.

## Related context

- **Google Docs** — [*Meeting Summary*](https://docs.google.com/document/d/1tldFFEk28qtQD0QdsnC2Br-BisTyOUp8OCwG1SZ_6Jk/edit) (per-meeting decisions and next steps) and [*Progress Report*](https://docs.google.com/document/d/1gMRFwaTvgahSiRi10ad_Y3CLDkxyF1QTYkAhZ4be4x8/edit) (running log of entry points, cases and findings). A session with the Google Drive connector enabled can read them directly.
- **Sibling experiment:** [`../if-check-exp/`](../if-check-exp/README.md) —
  the currently active folder, with its own `HANDOFF.md` at the repo root.
