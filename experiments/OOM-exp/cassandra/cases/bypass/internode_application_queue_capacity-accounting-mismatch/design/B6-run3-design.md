# B6 run 3 design — complete V1/V4 for runs 1 and 2 (2026-11-11)

Written before any run-3 reading. Purpose: test B6 runs 1 and 2 against the promotion rule
V1–V5 of the protocol's *Verification status (amended 2026-11-11)*. No new mechanism, payload or
setting is introduced; both earlier conditions are rerun unchanged with their own harnesses.

## Gaps being closed

| Run | Fixed condition | Have | Missing |
|---|---|---|---|
| 1 | V or S at 2 GiB (other 8 GiB), Byteman slow V, 60 s write + native timeouts, Python client 1 process, map 1000 cells, 90 s | failing 3/3 + 3/3, blob control 0/3 + 0/3, dumps kept | **V4**: 8 MiB endpoint reserves ran n = 1 per side |
| 2 | V at 8 GiB, 30 s disk stall t = 20–150 s, default timeouts, 4 coordinators, Java client, map 1000 cells | map stall **2** clean-start runs (P1 probe reported separately), blob control 0/3 at 8 GiB, GC logs | **V1**: a third clean-start map-stall run; **V4**: receive reserve 8 MiB ran n = 1 |

## Arms (clean start each, in this order)

Run-2 condition (`harness-run2/arm.sh`, results under `/mydata/b6/runs2/`):

1. `R3B_V8g_map_stall_r3` — the failing condition, third clean-start repeat; also the same-day positive.
   Heap dump on OOM enabled (only acts at OOM).
2. `R3B_V8g_map_stall_rsv8m_r2`, `_r3`, `_r4` — `internode_application_receive_queue_reserve_endpoint_capacity=8MiB`
   on all instances, as run 2's `R2_V8g_map_stall_rsv8m`.

Run-1 condition (`harness/arm.sh` for failing, `harness/armx.sh` for interventions, results under `/mydata/b6/runs/`):

3. `R3A_B_S2g_map_pos` — failing condition, same-day positive (coordinator at 2 GiB). Dumps on.
4. `R3A_C_S2g_map_rsv8m_r2`, `_r3`, `_r4` — send and receive endpoint reserves 8 MiB, 60 s timeouts, as run 1's `C_S2g_map_rsv8m`.
5. `R3A_B_V2g_map_pos` — failing condition, same-day positive (replica at 2 GiB). Dumps on.
6. `R3A_C_V2g_map_rsv8m_r2`, `_r3`, `_r4` — as run 1's `C_V2g_map_rsv8m`.

Intervention arms run with `HEAPDUMP=0`, as in runs 1–2.

## Predictions and decision rule

- Positives reproduce their earlier outcome: run-1 positives heap-OOM; `R3B_..._r3` meets the
  service-loss criterion (≥ 90% of wall time in Full GC over ≥ 60 s; run 2 saw 97–99%) or OOMs.
- Interventions: no OOM, no Full GC window meeting the service-loss criterion, in each arm.
- **Promotion** (protocol V4): reserve arms succeed 3/3 fresh at each condition (n = 4 with the
  earlier run). Any failing intervention arm keeps the run a candidate; report n/N.
- If a same-day positive does **not** reproduce, the earlier failing runs are not reused as
  equivalent; the run stays a candidate and the discrepancy is reported.

## Measurements

As in runs 1–2 (queue counters via `system_views`, client FINAL counts, outcome markers), plus, for
every arm, from the GC log (`harness-run3/gcpeak.sh`, non-intrusive): Full GC count, **peak
occupancy after a Full GC** (the live-heap measure) and the service-loss check. Occupancy after a
young pause is not used as a live bound: when to-space is exhausted it includes old-generation
garbage (validation on run 2's reserve arm: 99.8% after a young pause, 21.6% after its Full GC). For the interventions, record client throughput and
sender overload / receiver throttled counts: the reserve protects by **shedding** writes to the slow
replica (run 1: ≈ 55k of 66k dropped), which is reported as protective rejection, not as free.

## Labels and deviations (unchanged from runs 1–2)

Hints off, key/counter cache 0, single host on loopback, `num_tokens: 1`. Run 1 additionally:
Byteman delay, `concurrent_writes: 2` on V, 60 s timeouts, 2 GiB heap → `diagnostic`. Run 2's
conditions label (`deployment` vs `diagnostic`, because of hints off) is decided separately.

## Stopping budget

12 arms, about 75 min. Abort on two consecutive RING FAILs. No escalation after an OOM. At the
end: `ctl.sh stop all` for both harnesses, slow-disk delay 0, `pgrep java` empty.
