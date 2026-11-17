# Recheck flags — OOM leads from phase 1 (Cassandra)

Started 2026-11-16. One row per **OOM-lead flag** written by a guided case's §8a or by a recheck
([`playbook-guided.md`](../../stage3-ai-deep-read/playbook-guided.md) §3.2 and §5). A flag says real
memory can exceed what a constraint governs; it is a lead for OOM-exp, not a result. OOM-exp records
which flags it took up, and what they became, in its own case files.

**Mode:** `blind` (picked from phase 1 alone, OOM-exp not read) or `back-link` (named by a back-link
row for a verified OOM-exp case). Only `blind` flags count toward how well phase 1 predicts phase 2.

| Date | Case file | Question | Mechanism (one line) | Mode |
|---|---|---|---|---|
