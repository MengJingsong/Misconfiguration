# If-Check Cases (Hadoop, Yang's share) — Master Index

Case files written from Yang's band-D recheck queue ([`queue.csv`](queue.csv)): a unit the recheck
promotes to A/B/C gets an autonomous case file ([`../../PROCEDURE.md`](../../PROCEDURE.md)). Format as the
Cassandra index ([`../../../cassandra/stage3-ai-deep-read/_INDEX.md`](../../../cassandra/stage3-ai-deep-read/_INDEX.md));
outcome classes per [`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md#outcome-class).

**Source:** apache/hadoop @ tag `rel/release-3.4.2` (commit `84e8b89`)

**Method note (2026-11-06).** From batch 2 on, autonomous agents get the Hadoop
[`../playbook-autonomous.md`](../playbook-autonomous.md) and [`../_TEMPLATE-autonomous.md`](../_TEMPLATE-autonomous.md).
The first case (queue order 2) predates them: its agent got the Cassandra playbook and template
unchanged, the README §6.1 naming rule and a short Hadoop substitution note (tag, permalinks, config
keys, JDK + Maven); the Hadoop playbook folds that note in, so the case is not re-run.

## 1. Master Index

| Constraint (→ case file) | Agent | Queue order | Promoted band | Estimate | Stage 4 | Outcome class |
|---|---|---|---|---|---|---|
| [`yarn.scheduler.capacity.<queue-path>.capacity`](cases/yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous.md) | A | 2 | A | negative | [Confirmed — does not cap](../../stage4-runtime-verification/yang/results/yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous.md) (unit and cluster, 2026-11-06) | true negative |

## 4. Autonomous files — sha256 at filing

| File | sha256 | Filed |
|---|---|---|
| `yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous.md` | `f1ba76bb888db0e1d41a2d81267e2ee6d80ef755edeb76da8176a40d0931f781` | 2026-11-06 |
| `yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous.md` | `660ebeee5c7cfb63e41c1e051a567c3bd4e134cf17c80057dead0c81682d8273` | 2026-11-06, after the stage-4 audit amendments D1 (A1–A8); frozen version for stage 4 ([results](../../stage4-runtime-verification/yang/results/yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous.md) §1) |
| `yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous.md` | `7b2dfe1c47520183006423f32d2981a39a2a0083d8f586c8b5b98db052ee73eb` | 2026-11-06, runbook-defect amendment A9 (B2e step 1, how u3's AM is launched); B1 and the B2f–B2g / B3f–B3g tables unchanged ([results](../../stage4-runtime-verification/yang/results/yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous.md) §3) |
| `yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous.md` | `1afc50c92ada184b083f1c6a176db4665ae5a04c8cfdc20dd530e0c09126280a` | 2026-11-06, runbook-defect amendment A10 (B3a, `cp -r` of the configuration); B1 and the B2f–B2g / B3f–B3g tables unchanged (results §3) |
