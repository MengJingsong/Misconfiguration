#!/usr/bin/env python3
"""Generate the B2c Test-2 classes (N = 2, 3, 6) and the B2h control class from the upstream
CommitLogSegmentBackpressureTest, as the case file's B2c sed loop does, plus the print points of
audit amendment M2 (pre-writer, plateau1, after-sleep, plateau2, final; control: ctl-5s, ctl-6s,
ctl-after-discard, final).

usage: gen_test2.py <CommitLogSegmentBackpressureTest.java> <out-dir>
"""
import re
import sys

SRC, OUT = sys.argv[1], sys.argv[2]
src = open(SRC).read()

HELPER = '''
    static void cap(String label, int n)
    {
        java.lang.management.BufferPoolMXBean d = null;
        for (java.lang.management.BufferPoolMXBean b : java.lang.management.ManagementFactory.getPlatformMXBeans(java.lang.management.BufferPoolMXBean.class))
            if (b.getName().equals("direct"))
                d = b;
        AbstractCommitLogSegmentManager m = CommitLog.instance.segmentManager;
        System.out.println("CAP " + CLS + " " + label + " N=" + n
                           + " active=" + m.getActiveSegments().size()
                           + " pool=[" + m.getBufferPool() + "]"
                           + " directUsed=" + d.getMemoryUsed()
                           + " directCount=" + d.getCount()
                           + " t=" + System.currentTimeMillis());
    }

'''


def must_sub(pattern, repl, text, count=1):
    new, k = re.subn(pattern, repl, text, count=count)
    if k != count:
        raise SystemExit(f"pattern {pattern!r}: {k} matches, expected {count}")
    return new


def common(text, cls, n):
    text = text.replace("CommitLogSegmentBackpressureTest", cls)
    text = must_sub(r"setCommitLogMaxCompressionBuffersPerPool\(3\)", f"setCommitLogMaxCompressionBuffersPerPool({n})", text)
    text = must_sub(r"i < 20", "i < 60", text)
    text = must_sub(r"(public class \w+\n\{\n)", lambda m: m.group(1) + '    static final String CLS = "' + cls + '";\n' + HELPER, text)
    text = must_sub(r"(\n(\s*)allowSync\.acquire\(\);)", lambda m: m.group(1) + "\n" + m.group(2) + f'cap("pre-writer", {n});', text)
    text = must_sub(r"(\n(\s*)// Allow the CommitLog\.sync to perform normally\.)", lambda m: "\n" + m.group(2) + f'cap("final", {n});' + m.group(1), text)
    return text


def capclass(n):
    cls = f"CommitLogBufferCap{n}Test"
    t = src
    # the case file's sed: spinAssertEquals(3, -> (N, (all); assertEquals(3, -> (N, (first remaining)
    t = t.replace("spinAssertEquals(3,", f"spinAssertEquals({n},")
    t = must_sub(r"assertEquals\(3,", f"assertEquals({n},", t)
    t = common(t, cls, n)
    spins = [m.end() for m in re.finditer(r"Util\.spinAssertEquals\(\d+, \(\) -> clsm\.getActiveSegments\(\)\.size\(\), 5\);", t)]
    if len(spins) != 2:
        raise SystemExit("expected 2 spin assertions")
    t = t[:spins[1]] + f'\n            cap("plateau2", {n});' + t[spins[1]:]
    t = t[:spins[0]] + f'\n            cap("plateau1", {n});' + t[spins[0]:]
    t = must_sub(r"(Thread\.sleep\(1000\);)", r'\1' + f'\n            cap("after-sleep", {n});', t)
    return cls, t


def ctlclass():
    n = 3
    cls = "CommitLogBufferCapCtlTest"
    t = common(src, cls, n)
    t = must_sub(r"(DatabaseDescriptor\.setCommitLogCompression\(new ParameterizedClass\(\"LZ4Compressor\", ImmutableMap\.of\(\)\)\);)",
                 r"\1\n        DatabaseDescriptor.setCommitLogCompression(null); // B2h control: no compression -> legacy resolves to mmap", t)
    spin = r"Util\.spinAssertEquals\(3, \(\) -> clsm\.getActiveSegments\(\)\.size\(\), 5\);"
    t = must_sub(spin, 'Thread.sleep(5000);\n            cap("ctl-5s", 3);', t)
    t = must_sub(r"(Thread\.sleep\(1000\);)", r'\1' + '\n            cap("ctl-6s", 3);', t)
    t = must_sub(r"\n\s*Assert\.assertEquals\(3, clsm\.getActiveSegments\(\)\.size\(\)\);", "", t)
    t = must_sub(spin, 'Thread.sleep(5000);\n            cap("ctl-after-discard", 3);', t)
    return cls, t


for cls, text in [capclass(2), capclass(3), capclass(6), ctlclass()]:
    with open(f"{OUT}/{cls}.java", "w") as f:
        f.write(text)
    print("wrote", cls)
