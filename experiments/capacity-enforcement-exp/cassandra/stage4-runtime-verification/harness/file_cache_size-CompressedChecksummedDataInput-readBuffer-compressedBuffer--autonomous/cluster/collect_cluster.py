#!/usr/bin/env python3
"""collect_cluster.py <logroot> : re-parses raw sampler.csv/phases.txt of every label; independent of summarize.py."""
import sys, os, csv, re
root = sys.argv[1]
MiB = 1 << 20
cols = ["epoch_ms","capacity","size","used","overflow","pooled","direct_used","direct_count","rss_anon","heap_used","net_size","net_overflow"]
def load(p):
    rows = []
    for r in list(csv.reader(open(p)))[1:]:
        if len(r) == len(cols) and r[1] != "ERR":
            try: rows.append(dict(zip(cols, map(int, r))))
            except ValueError: pass
    return rows
for lab in sorted(os.listdir(root)):
    d = f"{root}/{lab}"
    if not os.path.exists(f"{d}/sampler.csv") or not os.path.exists(f"{d}/phases.txt"): continue
    ph = dict(re.findall(r"(\w+)=(\d+)", open(f"{d}/phases.txt").read()))
    ph = {k: int(v) for k, v in ph.items()}
    rows = load(f"{d}/sampler.csv")
    print(f"=== {lab}: samples={len(rows)} phases={ph}")
    cap = rows[0]["capacity"]
    if "T_DISP0" in ph:
        t0, t1 = ph["T_DISP0"], ph["T_END"]
        pre = [r for r in rows if r["epoch_ms"] < t0][-1]
        win = [r for r in rows if t0 <= r["epoch_ms"] <= t1]
        disp = [r for r in win if r["epoch_ms"] <= ph["T_DISP1"] + 2000]
        nf = ph.get("hints_files")
        pk = lambda k, w=win: max(r[k] for r in w)
        print(f" capacity={cap} hints_files={nf} pre_dispatch: direct={pre['direct_used']} overflow={pre['overflow']} pooled={pre['pooled']} rss_anon={pre['rss_anon']}")
        print(f" dispatch window ({(ph['T_DISP1']-t0)/1000:.0f}s): peak_direct={pk('direct_used')} (+{pk('direct_used')-pre['direct_used']} over pre) peak_overflow={pk('overflow')} (+{pk('overflow')-pre['overflow']}) last_overflow={win[-1]['overflow']} peak_pooled={pk('pooled')} peak_rss_anon={pk('rss_anon')} (+{pk('rss_anon')-pre['rss_anon']}) last_direct={win[-1]['direct_used']}")
        print(f" overflow gain per hints file read = {(win[-1]['overflow']-pre['overflow'])/nf:.0f} B ; expected ~1.05*(6291456+~100)-4096 = {int(1.05*6291556-4096)}")
        print(f" peak_overflow / capacity = {pk('overflow')/cap:.1f}")
    else:
        t0, t1 = ph["T_R0"], ph["T_R1"]
        win = [r for r in rows if t0 <= r["epoch_ms"] <= t1]
        pk = lambda k: max(r[k] for r in win)
        print(f" capacity={cap} peak_pooled={pk('pooled')} peak_size={pk('size')} peak_overflow={pk('overflow')} peak_used={pk('used')} last_overflow={win[-1]['overflow']} peak_direct={pk('direct_used')}")
        # pooled can be transiently off because Size and Overflow are read separately: also report the 5th-largest
        ps = sorted((r['pooled'] for r in win), reverse=True)
        print(f" pooled top5={ps[:5]} median={ps[len(ps)//2]}; samples with pooled>0: {sum(1 for r in win if r['pooled']>0)}/{len(win)}; overflow>0: {sum(1 for r in win if r['overflow']>0)}/{len(win)}")
