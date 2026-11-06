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
4. Stage 4: **Yang** has a Hadoop stage-4 environment on the local node
   (`experiments/if-check-exp/hadoop/stage4-runtime-verification/yang/environment.md`, set up 2026-11-06).
   For Yang, run stage 4 for each case file of the batch per PROCEDURE.md step 5 (one fresh agent per
   case, run data on `/mydata/yang-s4/`, nothing left running). **First check the node:** if this is
   not the node in that `environment.md`, or `/mydata/yang-s4/hadoop-base` (the built distribution) is
   missing, set the node up per its §1–3 first (install JDK 8 + Maven if absent, `copy-source.sh`,
   full build with `YARN_IGNORE_ENGINES=true`, never resumed with `-rf`) and update its Node table
   (keep one environment, dated). **Jingsong** has no environment yet:
   stop after stage 3 and say so; do not invent one (Jingsong may model one on Yang's when nodes are named).
5. Commit/push only when asked.
