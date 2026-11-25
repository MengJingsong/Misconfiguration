#!/usr/bin/env python3
"""U16 (2026-11-24): read `jcmd <pid> Thread.print` on stdin; print one line of fields:
rs rq rq_hex rq_fmt rq_cat put_blk ntr ntr_run st_phase aw_phase
rs     = ReadStage threads
rq     = ReadStage or Native-Transport-Requests threads with QueryCancelledException.<init> in the stack (concurrent abort
         renders, R_Q; amended 2026-11-24 after T-3: a local read can run inline on the NTR thread, Stage.maybeExecuteImmediately)
rq_hex / rq_fmt / rq_cat = of those, the top-most classifying frame is Hex.bytesToHex (or String.<init> /
         StringUTF16.compress / Hex.wrapCharArray) / String.format (Formatter) / StringConcatHelper or StringBuilder
put_blk = threads (any) in AsyncAppenderBase.put / ArrayBlockingQueue.put (appender queue full: caller blocks)
ntr / ntr_run = Native-Transport-Requests threads / of those RUNNABLE
st_phase = the ScheduledTasks thread in MonitoringTask: pop-hex | pop-fmt | pop | msg | log | mon | idle
aw_phase = AsyncAppender-Worker-ASYNCDEBUGLOG: thr-layout (ThrowableProxyConverter) | layout | encode | roll | write | idle"""
import sys
blocks = sys.stdin.read().split('\n\n')
rs = rq = hx = fm = cc = pb = ntr = run = 0
st = 'idle'; aw = 'idle'
for b in blocks:
    if 'AsyncAppenderBase.put' in b or 'ArrayBlockingQueue.put' in b:
        pb += 1
    if b.startswith('"ScheduledTasks') and 'MonitoringTask' in b:
        fr = [l.strip() for l in b.splitlines() if l.strip().startswith('at ')]
        if 'popOperations' in b:
            pre = ' '.join(fr[:[i for i, l in enumerate(fr) if 'popOperations' in l][0]])
            st = 'pop-hex' if 'Hex.bytesToHex' in pre else ('pop-fmt' if 'String.format' in pre or 'Formatter' in pre else 'pop')
        elif 'getLogMessage' in b: st = 'msg'
        elif 'ch.qos.logback' in b or 'slf4j' in b: st = 'log'
        else: st = 'mon'
        continue
    if b.startswith('"AsyncAppender-Worker-ASYNCDEBUGLOG'):
        if 'ThrowableProxyConverter' in b: aw = 'thr-layout'
        elif 'doLayout' in b: aw = 'layout'
        elif 'encode' in b: aw = 'encode'
        elif 'rollover' in b or 'Compress' in b or 'TimeBasedArchiveRemover' in b: aw = 'roll'
        elif 'FileOutputStream' in b or 'writeBytes' in b or 'ResilientOutputStreamBase' in b or 'OutputStreamAppender' in b: aw = 'write'
        continue
    if b.startswith('"Native-Transport-Requests'):
        ntr += 1
        if 'java.lang.Thread.State: RUNNABLE' in b: run += 1
    elif b.startswith('"ReadStage'):
        rs += 1
    else:
        continue
    if 'QueryCancelledException.<init>' not in b: continue
    rq += 1
    for line in b.splitlines():
        line = line.strip()
        if not line.startswith('at '): continue
        if 'Hex.bytesToHex' in line or 'java.lang.String.<init>' in line or 'StringUTF16.compress' in line or 'Hex.wrapCharArray' in line: hx += 1; break
        if 'java.lang.String.format' in line or 'java.util.Formatter' in line: fm += 1; break
        if 'StringConcatHelper' in line or 'StringConcatFactory' in line or 'StringBuilder' in line or 'AbstractStringBuilder' in line: cc += 1; break
        if 'QueryCancelledException.<init>' in line: break
print(rs, rq, hx, fm, cc, pb, ntr, run, st, aw)
