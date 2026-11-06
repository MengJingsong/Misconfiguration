# If-Check Cases (Hadoop, Jingsong's share) — Master Index

Case files written from Jingsong's band A/B/C queue ([`queue.csv`](queue.csv)), one fresh autonomous agent per unit
([`../../PROCEDURE.md`](../../PROCEDURE.md)), with the Hadoop [`../playbook-autonomous.md`](../playbook-autonomous.md) and
[`../_TEMPLATE-autonomous.md`](../_TEMPLATE-autonomous.md). Format as the Cassandra index; outcome classes per
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md#outcome-class).

**Source:** apache/hadoop @ tag `rel/release-3.4.2` (commit `84e8b89`)

## 1. Master Index

| Constraint (→ case file) | Agent | Queue order | Band | Estimate | Stage 4 | Outcome class |
|---|---|---|---|---|---|---|
| [`DF.getAvailable()` (free space, `LocalDirAllocator.java:528`)](cases/DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md) | A | 1 | A | negative | [Confirmed — does not cap (unit and cluster, 2026-11-06)](../../stage4-runtime-verification/jingsong/results/DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md) | true negative |
| [`RawPathHandle.MAX_SIZE`](cases/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous.md) | A | 2 | A | positive | [Confirmed — caps (unit; cluster as the no-daemon `hadoop jar` alternative, 2026-11-06)](../../stage4-runtime-verification/jingsong/results/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous.md) | true positive |
| [`fs.s3a.prefetch.block.count`](cases/fs.s3a.prefetch.block.count-acquireHelper-size--autonomous.md) | A | 3 | A | positive | [Not confirmed (unit and cluster: frozen heap tolerances missed; counter capped exactly, 2026-11-06)](../../stage4-runtime-verification/jingsong/results/fs.s3a.prefetch.block.count-acquireHelper-size--autonomous.md) | undetermined |
| [`fs.s3a.prefetch.max.blocks.count`](cases/fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.md) | A | 4 | A | positive | [Confirmed — caps (unit and cluster, 2026-11-06)](../../stage4-runtime-verification/jingsong/results/fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.md) | true positive |
| [`TFile` `MAX_KEY_SIZE` (`BoundedByteArrayOutputStream` limit)](cases/MAX_KEY_SIZE-write-limit--autonomous.md) | A | 5 | A | negative | [Confirmed — does not cap (unit; cluster n/a, 2026-11-06)](../../stage4-runtime-verification/jingsong/results/MAX_KEY_SIZE-write-limit--autonomous.md) | true negative |

## 4. Autonomous files — sha256 at filing

| File | sha256 | Filed |
|---|---|---|
| `DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md` | `91fee9d40d5324f3db89bf95b3a9c97dd9eb361f660ee294cd75b9d93ebecfa9` | 2026-11-06 |
| `RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous.md` | `e99136da0175e31016987efb9f946a52fa922efbcef6761ead69800776974127` | 2026-11-06 |
| `fs.s3a.prefetch.block.count-acquireHelper-size--autonomous.md` | `a31a6adfb29b46adadeffb96876a084d83d5cf915b8cc84d02a1f17a484c942b` | 2026-11-06 |
| `fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.md` | `33c11116e6d482e0e4a0905528e99b6d5d560468ce983089d60c299a91354ef3` | 2026-11-06 |
| `MAX_KEY_SIZE-write-limit--autonomous.md` | `4f3911cd75ba7160d73dac1f4cfd7e354a9e8be853dd9b72891bbea0d8d62224` | 2026-11-06 |
| `DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md` | `bb46249b9cc14bb5ec2f88281de2e0c69eead97d6aaa731c71937a913191a05d` | 2026-11-06, after stage-4 audit amendments A1–A13; frozen version, unit tier ran on it ([results](../../stage4-runtime-verification/jingsong/results/DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md)) |
| `DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md` | `8bd5cc94b71a30bc43f3ce3bb2d96d8bb49607d379bb127ab32a59d87ca61293` | 2026-11-06, runbook-defect amendments A14–A15 (cluster tier restarted); prediction/conclusion tables unchanged ([results](../../stage4-runtime-verification/jingsong/results/DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md)) |
| `DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md` | `9993691fc54ccdc95398197b72c9746351b7faea1b3638ed67b7bf81653d0df3` | 2026-11-06, D2 stage-4 result added ([results](../../stage4-runtime-verification/jingsong/results/DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md)) |
| `RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous.md` | `67839a9231a4532c540103453d5c76d7f183f657b12c753dba57ef9da961836d` | 2026-11-06, after stage-4 audit amendments A1–A7; frozen version ([results](../../stage4-runtime-verification/jingsong/results/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous.md)) |
| `RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous.md` | `0bf0627ad493a923a83cd6789e55334428677336fc1b0aa77f8cb941399fc6a6` | 2026-11-06, D2 stage-4 result added ([results](../../stage4-runtime-verification/jingsong/results/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous.md)) |
| `fs.s3a.prefetch.block.count-acquireHelper-size--autonomous.md` | `8c7ae49646cdb796a2e433df04eb27fabff64b634fac610e6fb74344800acb32` | 2026-11-06, after stage-4 audit amendments A1–A9; frozen version, unit tier ran on it ([results](../../stage4-runtime-verification/jingsong/results/fs.s3a.prefetch.block.count-acquireHelper-size--autonomous.md)) |
| `fs.s3a.prefetch.block.count-acquireHelper-size--autonomous.md` | `6b9a4850a89f7cdfced055ae371d5eb75723b1507083f23aa498e60816ce9f9c` | 2026-11-06, runbook-defect amendments A10–A11 (cluster tier restarted); prediction/conclusion tables unchanged ([results](../../stage4-runtime-verification/jingsong/results/fs.s3a.prefetch.block.count-acquireHelper-size--autonomous.md)) |
| `fs.s3a.prefetch.block.count-acquireHelper-size--autonomous.md` | `b32b1259baf8ac7851d4a06f42ba277ca454b5f8553226999fe14c289492b547` | 2026-11-06, D1/D2 stage-4 feedback added ([results](../../stage4-runtime-verification/jingsong/results/fs.s3a.prefetch.block.count-acquireHelper-size--autonomous.md)) |
| `fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.md` | `33757ad15d04db66aedc0f10f3f2df33faf67d890ba98e8b9d1925612d32b5d4` | 2026-11-06, after stage-4 audit amendments A1–A7; frozen version ([results](../../stage4-runtime-verification/jingsong/results/fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.md)) |
| `fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.md` | `a03e64963bbbb16ab9df6f94916fde098f152620d0c9628f49d680742453def3` | 2026-11-06, runbook-defect amendments A8–A9 (bucket name, reader retry); prediction/conclusion tables unchanged ([results](../../stage4-runtime-verification/jingsong/results/fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.md)) |
| `fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.md` | `4439f62729d6e390c02d365dc46a18cf232c9455cf13699c1820ca4ac2cf78f7` | 2026-11-06, D1/D2 stage-4 feedback added ([results](../../stage4-runtime-verification/jingsong/results/fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.md)) |
| `MAX_KEY_SIZE-write-limit--autonomous.md` | `585ee2f6837d5c47ec8009f406ffbd9766a6d1b7c87526ce07b697b4991339d8` | 2026-11-06, after stage-4 audit amendments A1–A7; frozen version ([results](../../stage4-runtime-verification/jingsong/results/MAX_KEY_SIZE-write-limit--autonomous.md)) |
| `MAX_KEY_SIZE-write-limit--autonomous.md` | `ce6dbf60b493acf98065d151efaf4e5e1c12d71c2b4140da3ae06ac71dce0126` | 2026-11-06, D2 stage-4 result added ([results](../../stage4-runtime-verification/jingsong/results/MAX_KEY_SIZE-write-limit--autonomous.md)) |
