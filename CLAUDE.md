# Repo instructions for Claude Code

## Hadoop if-check-exp stage 3 and 4 (two people)

If the user says "this is Yang" or "this is Jingsong" (any case) and asks about Hadoop if-check-exp
stage 3/4:

1. Read `HANDOFF.md`, that person's `HANDOFF-<Name>.md`, and
   `experiments/if-check-exp/hadoop/PROCEDURE.md`. The Cassandra parts of the handoffs do not apply.
2. "start the next batch of N cases" → follow PROCEDURE.md section "Start the next batch of N" on
   that person's `queue.csv`. Use fresh subagents per unit, one source copy outside the repo.
   Do not touch the other person's folders or `stage2-ai-preprocessing/bands.csv`.
3. "summarize the result status" → run `experiments/if-check-exp/hadoop/status.py <name>` and
   report per PROCEDURE.md.
4. Stage 4 has no Hadoop environment/harness yet: stop after stage 3 and say so; do not invent one.
5. Commit/push only when asked.
