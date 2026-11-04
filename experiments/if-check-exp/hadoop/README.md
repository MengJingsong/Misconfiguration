# if-check-exp — Hadoop (scaffold)

Empty placeholder for the **Hadoop** instance of `if-check-exp`. No analysis
has been done yet.

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
├── stage2-ai-preprocessing/   bands.csv
├── stage3-ai-deep-read/       cases/, _INDEX.md, writeup CSVs, predicted-*.md, ...
└── stage4-runtime-verification/  results/, harness/<case>/, case-notes.md, environment.md, ...
```

Prerequisites: pin the Hadoop source under
[`../../../systems/hadoop/source/`](../../../systems/hadoop/source/), build the
Hadoop CodeQL database, and fill in the (currently scaffold-only) Hadoop query
pack at [`../../../codeql-queries/hadoop/`](../../../codeql-queries/hadoop/).
Every `file:line` citation is pinned to the Hadoop source ref, exactly as the
Cassandra instance pins to `cassandra-5.0.9`.
