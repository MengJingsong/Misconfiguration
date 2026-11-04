# if-check-exp — Hadoop

The **Hadoop** instance of `if-check-exp`.

| Stage | Status |
|---|---|
| 1 — structural (CodeQL) | **done 2026-11-04**: [`stage1-codeql-preprocessing/README.md`](stage1-codeql-preprocessing/README.md) (10,842-row corpus) |
| 2 — lexical banding | not started |
| 3 — deep read | not started |
| 4 — runtime verification | not started |

The method is system-agnostic and documented once at the experiment root:

- [`../README.md`](../README.md) — results format spec (Targets 1 + 2)
- [`../stage1-codeql-preprocessing/README.md`](../stage1-codeql-preprocessing/README.md) — structural narrowing (CodeQL)
- [`../stage2-ai-preprocessing/`](../stage2-ai-preprocessing/) — lexical banding (playbook, bands spec)
- [`../stage3-ai-deep-read/`](../stage3-ai-deep-read/) — semantic read (playbooks, templates)
- [`../stage4-runtime-verification/`](../stage4-runtime-verification/) — runtime verification protocol

The Cassandra instance under [`../cassandra/`](../cassandra/) is the worked
example to mirror.

## To populate (Hadoop)

Produce per-stage output under this folder, mirroring the Cassandra layout:

```
hadoop/
├── stage1-codeql-preprocessing/  README.md (scope, database, counts; CSVs are gitignored)
├── stage2-ai-preprocessing/   bands.csv
├── stage3-ai-deep-read/       cases/, _INDEX.md, writeup CSVs, predicted-*.md, ...
└── stage4-runtime-verification/  results/, harness/<case>/, case-notes.md, environment.md, ...
```

Source: the pinned Hadoop tree at
[`../../../systems/hadoop/source/`](../../../systems/hadoop/source/) (`apache/hadoop` @
`rel/release-3.4.2`). Stage 1's queries are in
[`../../../codeql-queries/hadoop/`](../../../codeql-queries/hadoop/queries/if-check-exp/README.md).
Every `file:line` citation is pinned to `rel/release-3.4.2`, exactly as the
Cassandra instance pins to `cassandra-5.0.9`.
