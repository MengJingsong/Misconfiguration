#!/usr/bin/env python3
"""usage: unit-analyze.py <unit dir>   Reads rep1..rep3 .probe files, prints EXPECTED lines for B2f/B2g with the definitions of
amendments U3/U4 (frozen sha256 d75be538...). A NO is a recorded reading, not a change of the prediction."""
import re, sys, os
D = sys.argv[1]
yes = no = 0
def exp(desc, cond):
    global yes, no
    if cond: yes += 1
    else: no += 1
    print(f'EXPECTED: {desc} — {"yes" if cond else "NO"}')
def kv(line):
    return {k: v for k, v in re.findall(r'(\w+)=(\S+)', line)}
reps = {}
for r in ('rep1', 'rep2', 'rep3'):
    p = f'{D}/{r}.probe'
    if not os.path.exists(p): continue
    L = open(p, errors='replace').read().splitlines()
    reps[r] = {'probe': [kv(l) | {'variant': l.split()[1]} for l in L if l.startswith('PROBE ') and not l.startswith('PROBE-')],
               'ctrl': [kv(l) for l in L if l.startswith('CTRL ')],
               'resize': [(re.search(r'step=\[(.*?)\]', l).group(1), kv(l)) for l in L if l.startswith('RESIZE step')],
               'fin': [l for l in L if l.startswith('RESIZE finished') or l.startswith('PROBE-END')],
               'done': [kv(l) for l in L if l.startswith('PROBE-DONE')]}
exp(f'three reps present and each ended (PROBE-END): {sorted(reps)}', len(reps) == 3 and all(any(x.startswith('PROBE-END') for x in v['fin']) for v in reps.values()))
for r, v in reps.items():
    A = [x for x in v['probe'] if x['variant'] == 'A']; B = [x for x in v['probe'] if x['variant'] == 'B']
    exp(f'{r} variant A: 4 rows, variant B: 4 rows, control 3 rows, resize steps 8', len(A) == 4 and len(B) == 4 and len(v['ctrl']) == 3 and len(v['resize']) == 8)
    for x in A:
        n, T = int(x['n']), int(x['T'])
        exp(f'{r} A n={n}: maxPool={n}, active=min(n,T)={min(n,T)}, pending=T-n={T-n} (read {x["maxPool"]}/{x["active"]}/{x["pending"]})', int(x['maxPool']) == n and int(x['active']) == min(n, T) and int(x['pending']) == T - n)
        exp(f'{r} A n={n}: registry = {n} MiB and |heapDelta - n| <= 8 (registry {x["registryMiB"]}, heapDelta {x["heapDeltaMiB"]})', int(x['registryMiB']) == n and abs(float(x['heapDeltaMiB']) - n) <= 8)
        exp(f'{r} A n={n}: no rejection (submitErr 0) and longest execute <= 100 ms (read {x["submitErr"]}, {int(x["maxSubmitUs"])/1000:.1f} ms)', int(x['submitErr']) == 0 and int(x['maxSubmitUs']) <= 100000)
        exp(f'{r} A n={n}: pool threads <= n + 8 (read {x["poolThreads"]})', int(x['poolThreads']) <= n + 8)
    for x in B:
        n, T = int(x['n']), int(x['T'])
        exp(f'{r} B n={n}: active=min(n,T), pending=T-n (read {x["active"]}/{x["pending"]})', int(x['active']) == min(n, T) and int(x['pending']) == T - n)
        exp(f'{r} B n={n}: T <= heapDelta <= T+8 with T={T} (read {x["heapDeltaMiB"]})', T <= float(x['heapDeltaMiB']) <= T + 8)
        exp(f'{r} B n={n}: no rejection, longest execute <= 100 ms (read {x["submitErr"]}, {int(x["maxSubmitUs"])/1000:.1f} ms)', int(x['submitErr']) == 0 and int(x['maxSubmitUs']) <= 100000)
    if B:
        hs = [float(x['heapDeltaMiB']) for x in B]
        exp(f'{r} B: heapDelta max-min across n <= 5 MiB (read {max(hs)-min(hs):.1f})', max(hs) - min(hs) <= 5)
    if A:
        nm = {int(x['n']): int(x['nmtThreadDeltaKB']) for x in A}
        exp(f'{r} A: NMT Thread committed(n=128) - (n=1) <= 32 MiB (read {(nm[128]-nm[1])/1024:.1f} MiB)', nm[128] - nm[1] <= 32 * 1024)
    for c in v['ctrl']:
        n = int(c['n'])
        exp(f'{r} control n={n}: queue 64, accepted n+64={n+64}, rejected T-n-64={600-n-64} (read {c["queue"]}/{c["accepted"]}/{c["rejected"]})', int(c['queue']) == 64 and int(c['accepted']) == n + 64 and int(c['rejected']) == 600 - n - 64)
        exp(f'{r} control n={n}: heapDelta in [n+62, n+72] (read {c["heapDeltaMiB"]})', n + 62 <= float(c['heapDeltaMiB']) <= n + 72)
    S = {k: x for k, x in v['resize']}
    if len(S) == 8:
        exp(f'{r} resize: 4->32 raises active to 32 (read {S["set 4->32"]["active"]})', int(S['set 4->32']['active']) == 32)
        for k in ('set 32->32 (line 384 no-op)', 'set 32->32 again'):
            exp(f'{r} resize {k}: listenerCalls and "Resized" lines unchanged from 4->32 ({S[k]["listenerCalls"]}/{S[k]["resizedLogLines"]} vs {S["set 4->32"]["listenerCalls"]}/{S["set 4->32"]["resizedLogLines"]})', S[k]['listenerCalls'] == S['set 4->32']['listenerCalls'] and S[k]['resizedLogLines'] == S['set 4->32']['resizedLogLines'])
        exp(f'{r} resize: 4->32 gave one listener call and one log line (read {S["set 4->32"]["listenerCalls"]}/{S["set 4->32"]["resizedLogLines"]})', S['set 4->32']['listenerCalls'] == '1' and S['set 4->32']['resizedLogLines'] == '1')
        k = 'set 32->8 (32 tasks running)'
        exp(f'{r} resize: shrink to 8 leaves the 32 running tasks running (active {S[k]["active"]}, finished {S[k]["finished"]}, listener {S[k]["listenerCalls"]}, lines {S[k]["resizedLogLines"]})', int(S[k]['active']) == 32 and S[k]['finished'] == '0' and S[k]['listenerCalls'] == '2' and S[k]['resizedLogLines'] == '2')
        print('RECORDED (not predicted): ' + '; '.join(f'{k}: active={x["active"]} pending={x["pending"]} started={x["started"]} finished={x["finished"]}' for k, x in v['resize']))
# repeat agreement (U4a)
if len(reps) == 3:
    def sig(v): return [(x['variant'], x['n'], x['maxPool'], x['active'], x['pending']) for x in v['probe']]
    sigs = [sig(v) for v in reps.values()]
    exp('U4a: active/pending/maxPool identical in the three reps', sigs[0] == sigs[1] == sigs[2])
    worst = 0.0
    for i in range(len(reps['rep1']['probe'])):
        hs = [float(v['probe'][i]['heapDeltaMiB']) for v in reps.values()]
        worst = max(worst, max(hs) - min(hs))
    exp(f'U4a: heapDelta differs between reps by <= 5 MiB (worst {worst:.1f})', worst <= 5)
print(f'SUMMARY: {yes} yes, {no} NO')
