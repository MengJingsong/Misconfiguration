#!/usr/bin/env python3
"""Independent re-parse of the raw run-1 files of block_packed_max_block_size-checkblocksize-blocksize--autonomous (regexes on the raw text).
usage: selfcheck.py <unit-dir> [<cluster-root>]"""
import glob, os, re, sys

bad = 0


def chk(name, ok, detail=''):
    global bad
    print(('PASS ' if ok else 'FAIL ') + name + (' :: ' + detail if detail else ''))
    bad += (not ok)


ud = sys.argv[1]
txt = {os.path.basename(f)[:-4]: open(f).read() for f in glob.glob(ud + '/*.out')}
chk('unit: 210 cell outputs (2 arms x 3 reps x (18 writer + 7 check + 10 reader))', len(txt) == 210, str(len(txt)))
s = open(ud + '/summary.txt').read()
chk('unit: all cells exit 0; upstream SAICodecUtilsTest 16 tests pass; no daemon', s.count('exit=0') >= 211 and 'Tests run: 16, Failures: 0, Errors: 0' in s and 'no CassandraDaemon' in s)
for arm, mx in (('stock', 1 << 27), ('patched', 1 << 28)):
    for rep in (1, 2, 3):
        for kind in ('plain', 'mono'):
            for bs in (64, 128, 16384, 1 << 20, 1 << 26, 1 << 27, 1 << 28):
                t = txt[f'{arm}-r{rep}-writer_{kind}_{bs}_{arm}']
                acc = 'writer-accepted' in t
                chk(f'{arm} r{rep} {kind} {bs}: {"accepted" if bs <= mx else "rejected"} by the {mx}-bound build', acc == (bs <= mx))
                if acc:
                    a = int(re.search(r'ctorAlloc=(\d+)', t).group(1))
                    chk(f'{arm} r{rep} {kind} {bs}: allocation ~ 8 x bs', 8 * bs + 16 <= a <= 8 * bs + 2016, str(a))
                else:
                    chk(f'{arm} r{rep} {kind} {bs}: rejected without a big allocation', int(re.search(r'ctorAlloc=(\d+)', t).group(1)) < 100000)
            for bs, msg in ((32, 'must be >= 64'), (96, 'power of two')):
                chk(f'{arm} r{rep} {kind} {bs}: rejected with "{msg}"', msg in txt[f'{arm}-r{rep}-writer_{kind}_{bs}_{arm}'])
    for rep in (1, 2, 3):
        for kind in ('plain', 'mono'):
            for bs in (99, 1 << 28):
                t = txt[f'{arm}-r{rep}-reader_{kind}_{bs}_1000000000']
                al = int(re.search(r'alloc=(\d+)', t).group(1))
                if bs == 99 or arm == 'stock':
                    chk(f'{arm} r{rep} {kind} reader {bs}: IllegalArgumentException and < 1 MB allocated', 'IllegalArgumentException' in t and al < 1_000_000, str(al))
                else:
                    chk(f'{arm} r{rep} {kind} reader {bs}: passes the raised bound', 'IllegalArgumentException' not in t)
            t = txt[f'{arm}-r{rep}-reader_{kind}_64_1000000000']
            chk(f'{arm} r{rep} {kind} reader 64: passes the check and allocates arrays (> 50 MB)', int(re.search(r'alloc=(\d+)', t).group(1)) > 50_000_000)
for kind in ('plain', 'mono'):
    for bs in (128, 16384):
        a = int(re.search(r'ctorAlloc=(\d+)', txt[f'stock-r1-writer_{kind}_{bs}_stock']).group(1)); b = int(re.search(r'ctorAlloc=(\d+)', txt[f'patched-r1-writer_{kind}_{bs}_patched']).group(1))
        chk(f'{kind} {bs}: ctorAlloc equal in stock and patched-bound builds', a == b, f'{a} {b}')
if len(sys.argv) > 2:
    cr = sys.argv[2]
    summ = open(cr + '/summary.txt').read()
    tot = {}
    for lab in ('S-750k', 'S-1500k', 'S-3M', 'M1m-3M', 'ctl-seg16'):
        led = [l.split() for l in open(f'{cr}/{lab}/ledger.txt') if l.startswith('BPW')]
        chk(f'cluster {lab}: BPW lengths only 128 and 16384, largest 16384', {int(x[1]) for x in led} == {128, 16384} and len(led) % 5 == 0, f'{len(led)} lines')
        fl = open(f'{cr}/{lab}/files-{lab}-after-build.txt').read()
        tot[lab] = sum(int(l.split('\t')[1]) for l in fl.splitlines() if '\t' in l)
        seg = summ.split(f'ARM {lab} start')[1].split(f'ARM {lab} STOPPED')[0]
        chk(f'cluster {lab}: VERIFY OK', re.search(r'VERIFY.* OK\s*$', seg, re.M) is not None)
    chk('cluster: S-3M and M1m-3M component bytes identical', open(f'{cr}/S-3M/files-S-3M-after-build.txt').read().replace('S-3M', 'X') == open(f'{cr}/M1m-3M/files-M1m-3M-after-build.txt').read().replace('M1m-3M', 'X'))
    chk('cluster: bytes 750k : 1.5M : 3M = 1 : 2 : 4 within 15 %', abs(tot['S-1500k'] / tot['S-750k'] - 2) <= 0.3 and abs(tot['S-3M'] / tot['S-750k'] - 4) <= 0.6, f"{tot['S-1500k'] / tot['S-750k']:.2f} {tot['S-3M'] / tot['S-750k']:.2f}")
    m8 = open(f'{cr}/M8k-750k/stdout-trace.txt', errors='replace').read() + open(f'{cr}/M8k-750k/errors.txt', errors='replace').read()
    chk('cluster M8k-750k: checkBlockSize called with max 8192 and 16384 and the range message appears', 'CHK 16384 64 8192' in m8 and 'must be >= 64 and <= 8192, got 16384' in m8)
    g = lambda lab: max(int(l.split(',')[1]) for l in open(f'{cr}/{lab}/gauges-{lab}.csv').read().splitlines()[1:] if l.count(',') == 5)
    fl = lambda lab: len([l for l in open(f'{cr}/{lab}/flush-lines.txt') if 'Global limit' in l])
    chk('cluster control: 16 MiB arm peak <= 20 MiB; default arm > 32 MiB; more limit-flush lines in the 16 MiB arm (B5.8)', g('ctl-seg16') <= 20 * 1048576 < 32 * 1048576 < g('S-3M') and fl('ctl-seg16') > fl('S-3M'), f"{g('ctl-seg16')} {g('S-3M')} {fl('ctl-seg16')} {fl('S-3M')}")
print(f'SELFCHECK total FAIL={bad}')
sys.exit(1 if bad else 0)
