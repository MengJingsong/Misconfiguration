#!/usr/bin/env python3
"""B7 arm table: per arm, C (JMX Capacity), K (Caffeine weightedSize from the dump), entries, U (exclusive set of the
cache's BoundedLocalCache from hprof_holders.py), U/K, U/C, per-entry weight and heap, plus the sustained (idle,
churn) K readings and the PSMW node counts in the idle/churn class histograms.
Usage: python3 -I table.py /mydata/b7/logs <arm> [<arm> ...]   (standard library only)"""
import sys, re, os

def rd(p):
    try:
        return open(p, errors='replace').read()
    except OSError:
        return ''

def main():
    base = sys.argv[1]
    print("\t".join("arm cache C_MiB K_MiB entries U_MiB U/K U/C w_B u_B K_idle K_churn PSMW_idle PSMW_churn U/C_churn_est".split()))
    for arm in sys.argv[2:]:
        d = os.path.join(base, arm)
        s = rd(os.path.join(d, 'summary.txt'))
        rep = rd(os.path.join(d, 'hprof-report.txt'))
        cache = 'counter' if 'cache=counter' in s else 'key'
        hname = 'counter_cache' if cache == 'counter' else 'key_cache'
        cname = 'counterCache' if cache == 'counter' else 'keyCache'
        m = re.search(r'Holder %s \(1 root objects\): exclusive reachable set: \d+ objects, ([\d.]+) MiB' % hname, rep)
        U = float(m.group(1)) if m else float('nan')
        m = re.search(r'^%s -> .*:\n\s+(\{.*\})' % cname, rep, re.M)
        K = maxi = float('nan')
        if m:
            dd = eval(m.group(1), {})
            K = dd['weightedSize'] / 1048576.0; maxi = dd['maximum'] / 1048576.0
        def kr(tag):
            m = re.search(r'^K\[%s\] \S+ capacity=(\d+) size=(\d+) entries=(\d+)' % tag, s, re.M)
            return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
        f = kr('fill'); i = kr('idle'); c = kr('churn')
        C = f[0] / 1048576.0 if f else maxi
        ent = f[2] if f else 0
        def psmw(tag):
            m = re.search(r'^histo %s \(cache classes\):.*?com.github.benmanes.caffeine.cache.PSMW (\d+)' % tag, s, re.M)
            return int(m.group(1)) if m else ''
        w = K * 1048576 / ent if ent else float('nan')
        u = U * 1048576 / ent if ent else float('nan')
        # U at the churn reading estimated as churn K + entries_churn * (u - w) (per-entry overhead from the dump)
        uc = ((c[1] + c[2] * (u - w)) / 1048576.0 / C) if c else float('nan')
        print("%s\t%s\t%.1f\t%.2f\t%d\t%.2f\t%.3f\t%.3f\t%.0f\t%.0f\t%s\t%s\t%s\t%s\t%.3f" % (
            arm, cache, C, K, ent, U, U / K if K else float('nan'), U / C, w, u,
            "%.2f" % (i[1] / 1048576.0) if i else '', "%.2f" % (c[1] / 1048576.0) if c else '',
            psmw('idle'), psmw('churn'), uc))

if __name__ == '__main__':
    main()
