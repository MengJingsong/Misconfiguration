# Data-flow tracing playbook (lead source)

Read [verification-protocol.md](verification-protocol.md) first. This is a **lead
source**, not a direction (see [README](README.md#lead-sources)): it starts from
where memory is held, not from where a capacity check is, so it also finds memory
that capacity-enforcement-exp cannot see because no check guards it. Leads are run with the
convergence or bypass playbooks or as unprotected-accumulation cases and
classified by the common protocol. Outputs live under `<system>/leads/dataflow/`.
Added 2026-11-10. B6 (send-queue accounting mismatch) is the first lead found
this way.

## Goal

For each core data flow, list every place bytes accumulate, what bounds each
holder, and whether a reachable, legitimate workload can push the held bytes past
that bound or past the budget. One flow per file; finish a flow before starting
the next.

## Flows

Name flows by the path data takes. Starting lists (extend as needed):

- **Cassandra:** client request intake (native transport) · coordinator write ·
  coordinator read · internode messaging · replica mutation stage → memtable →
  flush · read path and caches · compaction · repair (validation, Merkle trees,
  streaming) · hints · gossip/schema.
- **Hadoop:** NameNode RPC and namespace/block map · DataNode write pipeline and
  block reports · MapReduce shuffle and merge · YARN ResourceManager application
  state · JobHistory · IPC call queue and responses.

Use the same names in the [JIRA survey](jira-mining-playbook.md) `flow` column, so
flows can be ranked by how many real OOMs they caused.

## Procedure

1. **Empirical pass (cheap, first).** Run a realistic workload for the flow at
   modest and high load. Take heap class histograms (and direct/native metrics)
   at steady state and under backlog (slow consumer, slow replica, paused stage).
   Classes whose live bytes grow with load or backlog mark the holders to trace.
2. **Static pass.** From the flow's entry point, follow the data to each holder:
   queues, collections, buffers, caches, per-connection/request/thread state,
   objects kept until a callback or timeout. Include copies (deserialized vs
   serialized, compressed vs uncompressed) as separate holders.
3. **Holder table.** One row per holder:

   | Column | Content |
   |---|---|
   | Holder | Class/field and pinned source location |
   | Unit held | Objects, serialized bytes, buffers; heap / direct / native |
   | Owner and multiplicity | Per request/connection/thread/table/peer/process; what bounds the count |
   | Lifetime | Released when processed, flushed, acknowledged, timed out, evicted |
   | Bound | **config cap** (name) · **constant** · **implicit** (concurrency × size, timeout × rate) · **wrong unit** (charged quantity ≠ memory held) · **none** |
   | capacity-enforcement-exp link | The capacity case for this check, if any |
   | Lead | none / convergence / bypass / unprotected, with a one-line hypothesis |

4. **Rank** leads by (bytes reachable per legitimate operation) × (how many
   operations or owners can be simultaneously live) and by the JIRA survey's
   count for the flow. Turn the top leads into campaign-plan rows.

## What counts as a finding

A holder with a bound goes to the convergence or bypass playbook as usual. A
holder with **no** applicable bound is an *unprotected* result (protocol,
*Classification by measurement*); it is a finding only if the workload stays
within documented guardrails, protocol limits and accepted configuration, and
the excess comes from the system's own accumulation (retention, copies,
amplification, backlog), not from the client simply sending more data than it
has been told the system accepts. Record whether the project documents the
behavior as by design. "Large input causes large memory" alone is not a finding.

## Output and handoff

- `<system>/leads/dataflow/<flow>.md`: flow diagram or ordered path, workload and
  histogram evidence, the holder table, ranked leads and open questions.
- Campaign-plan rows for leads, with `source: flow:<flow>` and normal C/B IDs
  (or a U ID for an unprotected-accumulation case, filed in the status-first
  folders like any other case).
- An entry in `<system>/cases/_run-log.md` per traced flow.

Commit/push only when requested.
