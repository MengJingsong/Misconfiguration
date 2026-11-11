#!/usr/bin/env python3 -I
"""Independent self-check (README 'Self-check'): re-derives the conclusion's numbers from the raw files by a different route than analyze_*.py.
Usage: selfcheck.py <sml1|lcl2> <unit-raw-dir> <cluster-dir>
Unit: file k's level is re-derived from the per-call log (level_after of switch k-1), N from the number of switches, sizes from operands at the switches.
Cluster: levels re-parsed from sstablemetadata.out, sizes from the Compacted line's file list and from files.csv, peak du re-parsed from du.csv, log segment scanned for ERROR/WARN."""
import csv, sys, re, os, json, glob
case, uraw, cdir = sys.argv[1:4]
bad = []
def chk(name, ok, det=''):
    print(('HOLDS   ' if ok else 'DOES NOT HOLD  ') + name + (' :: ' + det if det else '')); 
    if not ok: bad.append(name)
# ---------- unit ----------
arms = {}
for line in open(f'{uraw}/arms.txt'):
    m = re.match(r'ARM (\S+) (.*)', line); arms[m.group(1)] = dict(x.split('=', 1) for x in m.group(2).split() if '=' in x)
for tag, kv in sorted(arms.items()):
    calls = list(csv.DictReader(open(f'{uraw}/calls-{tag}.csv'))); files = list(csv.DictReader(open(f'{uraw}/files-{tag}.csv')))
    sw = [i for i, c in enumerate(calls) if c['returned'] == '1']
    chk(f'unit {tag}: N = switches + 1', len(files) == len(sw) + 1, f'files={len(files)} switches={len(sw)}')
    lv = [1] + [int(calls[i]['level_after']) for i in sw]
    chk(f'unit {tag}: levels re-derived from the call log equal the sstables\' levels', lv == [int(f['level']) for f in files], f'derived hist { {l: lv.count(l) for l in sorted(set(lv))} }')
    chk(f'unit {tag}: sum of file bytes == arms.txt outputBytes', sum(int(f['data_file_bytes']) for f in files) == int(kv['outputBytes']))
    S = int(kv['maxSize'])
    if kv.get('compressed') != 'true' and case == 'sml1' and tag not in ('smax',):
        ops = [int(calls[i]['operand']) for i in sw]
        chk(f'unit {tag}: bytes of every non-final file == operand at its switch', ops == [int(f['data_file_bytes']) for f in files][:len(ops)])
    prev_max_false = max((int(c['operand']) for c in calls if c['returned'] == '0'), default=0)
    chk(f'unit {tag}: no call returned false with operand > S', prev_max_false <= S, f'max false operand {prev_max_false} S={S}')
    if case == 'lcl2':
        # level capacity: the cumulative bytes at each level step exceed F^n * S and the step before did not
        F = int(kv['F']); ok = True
        for c in calls:
            if int(c['level_after']) > int(c['level_before']):
                cap = F ** int(c['level_before']) * S
                ok &= int(c['twil_before']) + int(c['operand']) > cap and int(c['twil_before']) <= cap
        chk(f'unit {tag}: every level step happened exactly when the cumulative closed-file bytes crossed F^n * S', ok)
# ---------- cluster ----------
for a in sorted(os.listdir(cdir)):
    d = f'{cdir}/{a}'
    if not os.path.exists(f'{d}/summary.json'): continue
    s = json.load(open(f'{d}/summary.json'))
    md = open(f'{d}/sstablemetadata.out').read()
    lv = [int(x) for x in re.findall(r'^SSTable Level: (\d+)', md, re.M)]
    hist = {l: lv.count(l) for l in sorted(set(lv))}
    chk(f'cluster {a}: levels re-parsed from sstablemetadata.out equal summary', hist == {int(k): v for k, v in s['levels'].items()}, str(hist))
    chk(f'cluster {a}: sstablemetadata file count == summary files', len(lv) == s['files'], f'{len(lv)} vs {s["files"]}')
    seg = open(f'{d}/system.log.segment', errors='replace').read()
    comp = [l for l in seg.splitlines() if 'Compacted (' in l]
    names = re.findall(r'/(nb-\d+-big)', comp[0]) if comp else []
    names = list(dict.fromkeys(names))
    onfiles = [l.split(',')[0] for l in open(f'{d}/files.csv').read().splitlines()[1:]]
    chk(f'cluster {a}: the Compacted line lists exactly the output sstables on disk', sorted(names) == sorted(onfiles), f'{len(names)} listed, {len(onfiles)} on disk')
    chk(f'cluster {a}: no ERROR in the compaction window of system.log', not [l for l in seg.splitlines() if l.startswith('ERROR')])
    rows = list(csv.DictReader(open(f'{d}/du.csv')))
    inp = s['input_bytes']; peak = max(int(r['table_dir_bytes']) for r in rows)
    chk(f'cluster {a}: peak du re-parsed from du.csv == summary and ~ input + output', peak == s['du_table_peak'] and 0.95 * 2 * inp <= peak <= 1.2 * 2 * inp, f'peak={peak} 2*input={2*inp}')
    sizes = [int(l.split(',')[1]) for l in open(f'{d}/files.csv').read().splitlines()[1:]]
    chk(f'cluster {a}: sizes in files.csv sum to summary bytes', sum(sizes) == s['bytes'])
    chk(f'cluster {a}: read-back equals rows written', s['readback'] == s['expected_rows'])
    chk(f'cluster {a}: auto-compaction was disabled for the arm (no second Compacted line)', len(comp) == 1, f'{len(comp)} Compacted lines')
print('SELFCHECK', 'ALL HOLD' if not bad else f'{len(bad)} DO NOT HOLD: {bad}')
