#!/usr/bin/env python3
"""Independent re-parse of the raw files of the run: triggers.csv of the labels sweep-p and range (usage operand u from the Byteman trace, the ratio r,
the verdict lines, nodetool exit, ERROR lines), the REJECT lines of summary.txt, and the unit .out files. Recomputes admit = (u + r <= 1) itself.
usage on the node: selfcheck.py [~/s4b-logs/hdr2]"""
import csv, json, os, re, sys
csv.field_size_limit(10**7)
R = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/s4b-logs/hdr2')
bad = 0
def chk(name, ok, detail=''):
    global bad
    bad += (not ok)
    print(('PASS ' if ok else 'FAIL ') + name + (' | ' + detail if detail else ''))
for lab in ('sweep-p', 'range'):
    n = 0
    for row in csv.DictReader(open(f'{R}/run1/{lab}/triggers.csv')):
        knob, r = row['knob_node'], row['r']
        if not knob:
            continue
        usage = json.loads(row['u_line']); verdict = json.loads(row['admit_lines']); errs = json.loads(row['error_lines'])
        rc = int(row['exit'])
        if r == 'NaN':
            rr = float('nan')
        else:
            rr = float(r)
        u = usage[knob][0][0] if usage[knob] else None
        want_admit = not (u + rr > 1) if u is not None else None
        nodes_v = [v for nd in verdict for v in verdict[nd]]
        got_admit = all(nodes_v) and len(nodes_v) == 2
        n_err = sum(len(v) for v in errs.values())
        chk(f'{lab} {row["trigger"]}: admit == (u + r <= 1) with u={u} r={r}', want_admit == got_admit and (rc == 0) == got_admit and n_err == (0 if got_admit else 1), f'rc={rc} verdicts={verdict} errors={n_err}')
        n += 1
    print(f'  ({lab}: {n} triggers with a ratio holder)')
for lab in ('range', 'valid'):
    s = open(f'{R}/run1/{lab}/summary.txt').read()
    rej = re.findall(r'REJECT (N[12]) write (\S+): SETFAIL .*Value must be >= 0 and <= 1 for repair_disk_headroom_reject_ratio', s)
    print(f'  {lab}: {len(rej)} rejected writes with the range text')
    if lab == 'range':
        chk('range: 12 rejected writes (2 holders x 2 triggers x 3 values), all with the range text', len(rej) == 12)
        chk('range: every read-back after a rejected write was 0.5', len(re.findall(r'the ratio stays 0.5 \(read 0.5\) — yes', s)) == 12)
        chk('range: NaN accepted and repair admitted', 'KNOB N2 set NaN read back NaN' in s and 'R-NaN: repair admitted by both nodes' in s and 'R-NaN: repair admitted by both nodes (two admit=true), exit 0, no Rejecting line — yes' in s)
    else:
        chk('valid: yaml 1.5 read back 1.5, repair refused with (-50.00%)', 'above threshold (-50.00%)' in s and 'node 2 started with yaml 1.5; JMX reads 1.5 — yes' in s)
        chk('valid: JMX write of 1.5 refused with the range text', 'V JMX write 1.5: SETFAIL' in s and 'Value must be >= 0 and <= 1' in s)
# unit
U = R + '/unit'
for f, n in (('S1-S2.out', 45), ('U1-U2-U4a.out', 92), ('U4b.out', 36), ('U3.out', 7)):
    t = open(f'{U}/{f}').read()
    ok = len(re.findall(r'^STAGE4 check .* ok$', t, re.M))
    chk(f'unit {f}: {n} checks ok, 0 MISMATCH', ok == n and 'MISMATCH' not in t, f'ok={ok}')
t = open(U + '/S1-S2.out').read()
chk('unit S1: NaN stored (getter NaN)', 'S1_accept_NaN allocated_bytes_of_the_setter_call=0 getter=NaN' in t)
print('FAILS', bad)
sys.exit(1 if bad else 0)
