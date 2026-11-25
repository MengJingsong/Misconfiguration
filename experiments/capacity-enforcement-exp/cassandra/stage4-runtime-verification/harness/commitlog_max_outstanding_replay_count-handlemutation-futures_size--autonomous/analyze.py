#!/usr/bin/env python3
"""Analysis for case o100 (B2f/B2g, B3f/B3g with S4-A3/S4-A4 thresholds). Re-parses the raw files only.
Usage: analyze.py <o100 dir>   (expects unit/run1/run-*.log and cluster/<label>/{samples.jsonl,system.log,jvm-args.txt})"""
import datetime as dt, glob, json, os, re, statistics as st, sys

base = sys.argv[1]
out = []
P = lambda s: (out.append(s), print(s))

# ---------------- unit ----------------
P("== UNIT (B2) ==")
U = {}
for f in sorted(glob.glob(f"{base}/unit/run1/run-*.log")):
    lab = os.path.basename(f)[4:-4]
    txt = open(f, errors="replace").read()
    m = re.search(r"RESULT (count_cap=.*?peak_pending_bytes=\d+)", txt)
    if not m:
        P(f"{lab}: NO RESULT"); continue
    d = dict(kv.split("=") for kv in m.group(1).split())
    d = {k: int(v) for k, v in d.items()}
    U[lab] = d
    P(f"{lab}: " + " ".join(f"{k}={v}" for k, v in d.items()))
ok_rows = True
for C in (16, 256, 4096):
    labs = [l for l in U if l.startswith(f"C{C}-")]
    pq = [U[l]["peak_queue"] for l in labs]
    ny = [U[l]["peak_not_yet_run"] for l in labs]
    hd = [U[l]["handled"] for l in labs]
    cc = [U[l]["count_cap"] for l in labs]
    lo = {16: 0, 256: 250, 4096: 4000}[C]
    e = all(q == C + 1 for q in pq) and len(pq) == 3
    P(f"EXPECTED C={C}: repeats={len(pq)} count_cap={cc} peak_queue={pq} (= {C+1}: {e}); not_yet_run={ny} (<= {C+1}, >= {lo}: "
      f"{all(lo <= x <= C + 1 for x in ny)}); handled={hd} (>= 20000: {all(h >= 20000 for h in hd)})")
    ok_rows &= e and all(h >= 20000 for h in hd) and all(c == C for c in cc)
cb = U.get("ctlBytes"); cf = U.get("ctlFast")
if cb:
    P(f"EXPECTED ctlBytes: peak_queue={cb['peak_queue']} (<= 410: {cb['peak_queue'] <= 410}; B2f ~70-110), "
      f"peak_pending_bytes={cb['peak_pending_bytes']} (<= 4096 + one entry)")
if cf:
    P(f"EXPECTED ctlFast: peak_queue={cf['peak_queue']} (<= 410: {cf['peak_queue'] <= 410}; B2f expected < 100)")
if ok_rows and cb and cb["peak_queue"] <= 410:
    P("UNIT MATCH: B2g row 1 (Confirmed, caps)" + ("" if cf and cf["peak_queue"] <= 410 else " + S4-A3 added row (control 2 not small)"))
else:
    P("UNIT MATCH: not row 1 -- inspect")

# ---------------- cluster ----------------
P("\n== CLUSTER (B3) ==")
ts_re = re.compile(r"^\w+\s+\[[^\]]+\]\s+(\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d,\d{3})")


def logtimes(path, obs_ms):
    """epoch ms of first 'Replaying' and of 'Log replay complete'; the log's zone chosen against observed times."""
    first = done = None; n = mms = None
    for line in open(path, errors="replace"):
        if first is None and "Replaying " in line:
            first = ts_re.match(line).group(1)
        if "Log replay complete" in line:
            done = ts_re.match(line).group(1)
            m = re.search(r"Log replay complete, (\d+) replayed mutations in (\d+) ms", line)
            if m: n, mms = int(m.group(1)), int(m.group(2))
    if first is None or done is None:
        return None
    def ep(s, tz):
        t = dt.datetime.strptime(s.replace("T", " "), "%Y-%m-%d %H:%M:%S,%f")
        return int(t.replace(tzinfo=tz).timestamp() * 1000)
    best = None
    for tz in (dt.timezone.utc, dt.datetime.now().astimezone().tzinfo):
        a = ep(first, tz)
        if best is None or abs(a - obs_ms) < abs(best[0] - obs_ms):
            best = (a, ep(done, tz))
    return best[0], best[1], n, mms


R = {}
fm = lambda v: 'n/a' if v is None else f'{v/1e6:.1f}'
for d in sorted(glob.glob(f"{base}/cluster/*-r[12]")):
    lab = os.path.basename(d)
    sp = f"{d}/samples.jsonl"
    if not os.path.exists(sp) or not os.path.exists(f"{d}/system.log"):
        P(f"{lab}: missing files"); continue
    recs = [json.loads(l) for l in open(sp)]
    evs = {r["event"]: r["t_ms"] for r in recs if "event" in r}
    smp = [r for r in recs if "event" not in r and "total_b" in r]
    lt = logtimes(f"{d}/system.log", evs.get("replaying_seen", smp[0]["t_ms"] if smp else 0))
    if not lt:
        P(f"{lab}: no replay window in system.log"); continue
    t0, t1, n, mms = lt
    in_win = [r for r in smp if r["t_ms"] < t1]
    q0, q1 = t0 + 0.25 * (t1 - t0), t0 + 0.75 * (t1 - t0)
    pl = [r for r in in_win if q0 <= r["t_ms"] <= q1]
    args = open(f"{d}/jvm-args.txt").read().split() if os.path.exists(f"{d}/jvm-args.txt") else []
    cnt = next((a.split("=")[1] for a in args if "replay_count=" in a), "default")
    byt = next((a.split("=")[1] for a in args if "replay_bytes=" in a), "default")
    bm = any("byteman" in a for a in args)
    rl = next((a.split("=")[1] for a in args if "replayList" in a), "-")
    med = lambda k: st.median([r[k] for r in pl]) if pl else None
    res = dict(lab=lab, count=cnt, bytes=byt, byteman=bm, replayList=rl, N=n, ms=mms, window_s=(t1 - t0) / 1000,
               samples=len(in_win), plateau=len(pl),
               task_max=max([r["task_n"] for r in in_win], default=None), task_med=med("task_n"),
               mut_max=max([r["mut_n"] for r in in_win], default=None), mut_med=med("mut_n"),
               live_med=med("total_b"), used_med=(med("heap_used_k") or 0) * 1024 if pl else None,
               series=[r["task_n"] for r in in_win], mutstage_pending=[(r.get("mutstage") or [None] * 4)[2] if isinstance(r.get("mutstage"), list) else None for r in in_win])
    R[lab] = res
    P(f"{lab}: count={cnt} bytes={byt} byteman={bm} replayList={rl} N={n} replay_ms={mms} window={res['window_s']:.1f}s "
      f"samples={len(in_win)} plateau={len(pl)} task max={res['task_max']} med={res['task_med']} mut max={res['mut_max']} "
      f"med={res['mut_med']} live_med={fm(res['live_med'])}MB used_med={fm(res['used_med'])}MB")
    P(f"   task series {res['series']}")
    P(f"   MutationStage pending {res['mutstage_pending']}")

P("\n-- B3f checks --")
for r in (1, 2):
    g = lambda l: R.get(f"{l}-r{r}")
    a, b, c = g("C1024"), g("C16384"), g("C131072")
    if not (a and b and c):
        P(f"repeat {r}: incomplete"); continue
    for x, C, lo in ((a, 1024, 900), (b, 16384, 14000), (c, 131072, 110000)):
        P(f"r{r} C{C}: max {x['task_max']} <= {C+1}+10: {x['task_max'] <= C + 11}; plateau median {x['task_med']} >= {lo}: "
          f"{x['task_med'] is not None and x['task_med'] >= lo}; |mut_med - task_med| = {abs((x['mut_med'] or 0) - (x['task_med'] or 0))} <= 500")
    e16 = (b["live_med"] - a["live_med"]) / (b["task_med"] - a["task_med"])
    e131 = (c["live_med"] - a["live_med"]) / (c["task_med"] - a["task_med"])
    P(f"r{r} live heap medians MB: {a['live_med']/1e6:.1f} < {b['live_med']/1e6:.1f} < {c['live_med']/1e6:.1f}: "
      f"{a['live_med'] < b['live_med'] < c['live_med']}; e16={e16:.0f} B, e131={e131:.0f} B, ratio {e16/e131:.2f} (0.7-1.3 -> stable: "
      f"{0.7 <= e16 / e131 <= 1.3}); dheap C131072-C1024 = {(c['live_med']-a['live_med'])/1e6:.1f} MB (B3f +78-260 MB)")
    u16 = (b["used_med"] - a["used_med"]) / (b["task_med"] - a["task_med"]); u131 = (c["used_med"] - a["used_med"]) / (c["task_med"] - a["task_med"])
    P(f"r{r} secondary (GC.heap_info used) medians MB: {a['used_med']/1e6:.1f} / {b['used_med']/1e6:.1f} / {c['used_med']/1e6:.1f}; e16={u16:.0f} e131={u131:.0f}")
    x = g("ctlBytes")
    if x: P(f"r{r} ctlBytes: max {x['task_max']} <= 65536: {x['task_max'] <= 65536}; live_med {x['live_med']/1e6:.1f} MB (C16384 {b['live_med']/1e6:.1f}, C131072 {c['live_med']/1e6:.1f})")
    x = g("ctlFast")
    if x: P(f"r{r} ctlFast: max {x['task_max']} (<= 65536: {x['task_max'] <= 65536}; B3f expected < 5000); live_med {fm(x['live_med'])} MB; samples in window {x['samples']}")
    x = g("ctlFull")
    if x: P(f"r{r} ctlFull: N={x['N']} >= 300000: {x['N'] is not None and x['N'] >= 300000}")
    P(f"r{r} C131072 max {c['task_max']} > 1.5 x C16384 max {b['task_max']}: {c['task_max'] > 1.5 * b['task_max']}")

open(f"{base}/analysis.txt", "w").write("\n".join(out) + "\n")
