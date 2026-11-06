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
   (keep one environment, dated). **Jingsong** has a Hadoop stage-4
   environment on nodes `pc41` (the local node, shared with Yang), `pc39`, `pc29`
   (`experiments/if-check-exp/hadoop/stage4-runtime-verification/jingsong/environment.md`, set up 2026-11-06):
   run stage 4 the same way, run data on `/mydata/jingsong-s4/`, one case per node at a time where possible
   (remote nodes via `ssh pcNN`); a node missing `/mydata/jingsong-s4/hadoop-base` is set up with its `setup-node.sh`.
5. **Commit and push automatically** (no need to ask) when a batch finishes (stage 3, plus stage 4
   where it runs), and after any other change to that person's Hadoop files. Commit to `main` only
   the files of this work (that person's folders, their `HANDOFF-<Name>.md`, shared Hadoop docs you
   changed); leave unrelated working-tree changes uncommitted. `git pull --rebase --autostash origin main`
   before `git push origin main` (both people push to `main`). Report the commit hash.
