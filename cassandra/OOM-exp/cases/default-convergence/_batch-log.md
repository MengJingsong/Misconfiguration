# Default-value convergence playbook — batch log

Append one entry per playbook run, per [`../../default-value-convergence-playbook.md`](../../default-value-convergence-playbook.md).
Same format as [`../convergence/_batch-log.md`](../convergence/_batch-log.md), plus the default-arithmetic verdict for each group surveyed.

## Shared-budget group status

Independent of the original convergence playbook's table: a group exhausted there (raised values) is a separate question at defaults. Statuses as in the original (**open**, **exhausted**, **parked**, **skipped**, **deferred (causal-chain, not picked)**), plus **cannot converge at defaults** (the default arithmetic shows no budget where each is safe alone and the sum exceeds it; state the arithmetic).

**Rule: disk is skipped (carried over from the original playbook's 2026-11-02 request).** Do not pick a disk-group combination until it is lifted here.

| Shared budget | Constraints tried | Status | Why |
|---|---|---|---|
| On-heap JVM heap | none yet | **open** | Not surveyed at defaults. |
| Off-heap/direct memory | none yet | **open** | Not surveyed at defaults. Note: `row_cache_size` (0MiB) and the chunk cache (`file_cache_enabled: false`) are off by default in 5.0.9. |
| Disk | none | **skipped** (carried over, 2026-11-02 request) | See the original batch log. |

*(no runs yet)*
