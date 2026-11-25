# Applies B2f (S4-A3) and B2g (S4-A4) to wmresult.txt. usage: python3 analyze_unit.py wmresult.txt
import sys, re
rows = {}
for line in open(sys.argv[1]):
    lab, rest = line.split(' ', 1)
    d = dict(re.findall(r'(\w+)=(\[.*\]|\S+)', rest))
    rows[lab] = d
I = lambda d, k: int(d[k])
KiB = 1024
print('label high B K R produced pendSettled pendMax writable band_lo band_hi in_band')
for lab, d in rows.items():
    K, R, P = I(d,'K'), I(d,'R'), I(d,'pendingSettled')
    lo, hi = K*R - 64*KiB, K*(R+192)
    print(lab, d['high'], d['B'], K, R, d['produced'], P, d['pendingMax'], d['writable'], lo, hi, lo <= P <= hi, 'open=' + d['open'], 'gate=' + d['gate'], 'cfgHigh=' + d['cfgHigh'], 'clientBytes=' + d['clientBytes'])
g = lambda h, B, K: rows.get('h%d-B%d-K%d' % (h, B, K))
reps = [I(rows[l], 'pendingSettled') for l in rows if l.startswith('rep')] + [I(g(32768,65536,256),'pendingSettled')]
spread = max(reps) - min(reps); n = max(64*KiB, 2*spread)
print('\nrepeat pendingSettled', reps, 'spread', spread, 'noise n', n)
ok_band = ok_flat = ok_scale = True
for B in (16384, 65536, 262144):
    for K in (64, 256):
        s = g(32768, B, K); P = I(s,'pendingSettled'); R = I(s,'R')
        inb = K*R - 64*KiB <= P <= K*(R+192) and s['writable'] == 'false'
        ok_band &= inb
        d1 = I(g(1048576,B,K),'pendingSettled') - P; d64 = I(g(67108864,B,K),'pendingSettled') - P
        fl = abs(d1) <= n and abs(d64) <= n; ok_flat &= fl
        print('B=%d K=%d stock P=%d (K*R=%d) inband=%s | P(1MiB)-P=%d P(64MiB)-P=%d flat=%s | w1=%s w64=%s' % (B, K, P, K*R, inb, d1, d64, fl, g(1048576,B,K)['writable'], g(67108864,B,K)['writable']))
    r = I(g(32768,B,256),'pendingSettled') / I(g(32768,B,64),'pendingSettled'); ok_scale &= 3.5 <= r <= 4.5
    print('  B=%d ratio K256/K64 = %.3f' % (B, r))
for K in (64, 256):
    print('  K=%d ratio B64K/B16K = %.3f, B256K/B64K = %.3f' % (K, I(g(32768,65536,K),'pendingSettled')/I(g(32768,16384,K),'pendingSettled'), I(g(32768,262144,K),'pendingSettled')/I(g(32768,65536,K),'pendingSettled')))
c = rows['ctl-reads-h32768-B65536-K256']; P = I(c,'pendingSettled')
ok_reads = P <= 64*KiB and c['clientBytes'] == c['produced']
print('\nclient-reads: P=%d clientBytes=%s produced=%s -> holds=%s' % (P, c['clientBytes'], c['produced'], ok_reads))
ok_gate = True
for B in (65536, 262144):
    c = rows['ctl-gate-autoread-B%d-K256' % B]; P = I(c,'pendingSettled'); R = int(round(I(c,'produced') / max(1, I(c,'produced') // (B+71)))) if False else B + 71
    stock = I(g(32768,B,256),'pendingSettled'); Rs = I(g(32768,B,256),'R')
    bound = 32*KiB + 4*(Rs+192)
    h = P <= bound and P <= 0.02*stock and I(c,'produced') < 256*Rs
    ok_gate &= h
    print('gate autoread B=%d: P=%d pMax=%s bound=%d 2%%stock=%.0f produced=%s (K*R=%d) autoRead=%s pipeline=%s -> holds=%s' % (B, P, c['pendingMax'], bound, 0.02*stock, c['produced'], 256*Rs, c['autoRead'], c['pipeline'], h))
c = rows.get('diag-gate-asfiled-B65536-K256')
if c: print('diag as-filed gate: P=%s produced=%s autoRead=%s pipeline=%s (not used for verdict)' % (c['pendingSettled'], c['produced'], c['autoRead'], c['pipeline']))
print('\nSUMMARY stock_in_band=%s flat_in_mark=%s follows_workload=%s reads_ctl=%s gate_ctl=%s' % (ok_band, ok_flat, ok_scale, ok_reads, ok_gate))
print('B2g ->', 'row 1/4: Confirmed - does not cap' if all([ok_band, ok_flat, ok_scale, ok_reads, ok_gate]) else 'see rows')
