#!/usr/bin/env python3
"""Run the stage-3 short path for one case, end to end (README steps 1 to 6).

    python3 run-case.py run  --stem memtable_heap_space-tryAllocate-limit
    python3 run-case.py run  --stem <stem> --pointer src/java/...:123 --feed 3a
    python3 run-case.py file --stem memtable_heap_space-tryAllocate-limit
    python3 run-case.py run  --stem <stem> --dry-run

`run`  prepares a clean workspace, builds the prompt, launches the isolated
       writer with the flags fixed by isolation-test.py, extracts the solution
       and audits it. It files nothing.
`file` copies an audited solution into cases/, fills the header row, and adds
       the _INDEX.md row with its sha256. It refuses unless the audit passed
       (or `--accept-review` after you read every REVIEW item). `--supersede`
       files a new version of a case that already has a solution: the old file
       is renamed `<stem>--vN.md` (content untouched) and marked superseded in
       the index. Nothing is committed, ever.

`run` refuses to start unless the isolation test passed with the SAME flags
and allowlist. A failed or review-needed attempt is kept and never edited; run
again with `--attempt N` for a fresh directory.
"""
import argparse, datetime, hashlib, importlib.util, json, os, pathlib, re, shutil, subprocess, sys, time

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('isolation_test', HERE / 'isolation-test.py')
it = importlib.util.module_from_spec(spec)
spec.loader.exec_module(it)

RUN_ROOT = it.DEFAULT_WORK.parent                       # ~/short-path-run
PRESETS = {  # entry pointers: file:line of the capacity check only, relative to the clone root
    'memtable_heap_space-tryAllocate-limit':
        ('src/java/org/apache/cassandra/utils/memory/MemtablePool.java:156', '3b'),
}
PROJECT_WORDS = ['mengjingsong', 'misconfiguration', 'if-check', 'handoff', 'long-path',
                 'short-path', 'stage4', 'stage-4', 'docs.google.com']
SCAN = re.compile(r'(stage[ -]?[34]\b|long[ -]path|short[ -]path|hand-?off|results? file|\brun ?[12]\b|'
                  r'harness|HeapPoolTest|if-check|misconfiguration|MengJingsong)', re.I)
PROMPT_TAIL = ('\n---\nEntry pointer: {pointer}\n\n'
               'Return the completed skeleton as your final message.\n')


def case_dir(stem, attempt):
    return RUN_ROOT / (stem if attempt == 1 else f'{stem}--attempt{attempt}')


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- preconditions

def check_isolation_report():
    rep = it.DEFAULT_WORK / 'isolation-test-report.txt'
    if not rep.exists():
        sys.exit(f'no isolation report at {rep}: run isolation-test.py first')
    lines = rep.read_text(encoding='utf-8').splitlines()
    flags = next((l[len('flags: '):] for l in lines if l.startswith('flags: ')), '')
    allow = next((l for l in lines if l.startswith('allowlist ')), '')
    result = next((l for l in lines if l.startswith('RESULT:')), 'RESULT: ?')
    cell = next((l[len('index cell: '):] for l in lines if l.startswith('index cell: ')), '')
    if not result.startswith(('RESULT: PASS')):
        sys.exit(f'the isolation test did not pass ({result}); fix it and rerun isolation-test.py')
    if flags != ' '.join(it.run_flags()) or not allow.startswith(f'allowlist {it.ALLOWLIST_VERSION}:'):
        sys.exit('the flags or allowlist changed since the isolation test passed: rerun isolation-test.py')
    return dict(path=str(rep), result=result, cell=cell)


def build_prompt(pointer):
    brief = (HERE / 'BRIEF.md').read_text(encoding='utf-8')
    tmpl = (HERE / '_TEMPLATE.md').read_text(encoding='utf-8')
    static = (brief + tmpl).lower()
    leaks = [w for w in PROJECT_WORDS if w in static]
    if leaks:
        sys.exit(f'BRIEF.md/_TEMPLATE.md mention project words {leaks}: they must stay self-contained')
    return brief + '\n' + tmpl + PROMPT_TAIL.format(pointer=pointer), tmpl


def check_pointer(src, pointer):
    m = re.fullmatch(r'(.+):(\d+)', pointer)
    if not m:
        sys.exit(f'entry pointer {pointer!r} must look like path/to/File.java:123')
    f, n = src / m.group(1), int(m.group(2))
    if not f.is_file():
        sys.exit(f'entry pointer file not found in the clone: {f}')
    if n > len(f.read_text(encoding='utf-8', errors='replace').splitlines()):
        sys.exit(f'entry pointer line {n} is past the end of {f.name}')


# ---------------------------------------------------------------- the writer run

def run_writer(src, prompt, log, errlog, extra, timeout):
    cmd = ['claude', '-p', *it.run_flags(), '--output-format', 'stream-json', '--verbose', *extra]
    t0, n = time.time(), 0
    with open(log, 'w', encoding='utf-8') as out, open(errlog, 'w', encoding='utf-8') as err:
        p = subprocess.Popen(cmd, cwd=src, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True)
        p.stdin.write(prompt); p.stdin.close()
        for line in p.stdout:
            out.write(line); out.flush()
            try: e = json.loads(line)
            except Exception: continue
            if e.get('type') == 'assistant':
                for c in e.get('message', {}).get('content', []) or []:
                    if isinstance(c, dict) and c.get('type') == 'tool_use':
                        n += 1
                        arg = json.dumps(c.get('input', {}))[:90]
                        print(f'  [{int(time.time() - t0) // 60:02d}:{int(time.time() - t0) % 60:02d}] #{n} {c["name"]} {arg}', flush=True)
            if time.time() - t0 > timeout:
                p.kill()
                print(f'  timeout after {timeout}s: writer killed', flush=True)
                break
        p.wait()
    return time.time() - t0


# ---------------------------------------------------------------- audits

def audit(src, res, solution, template_text):
    A = []   # (id, status, note)
    calls = res['calls']
    # 1: files and tools
    bad, tried = [], []
    for c in calls:
        if c['name'] not in it.TOOLS:
            bad.append(f"forbidden tool {c['name']}")
        elif it.outside(c, src):
            (tried if c['denied'] else bad).append(f"{c['name']} {json.dumps(c['input'])[:100]}")
    A.append(('A1 files/tools', 'FAIL' if bad else 'PASS',
              ('; '.join(bad[:5]) if bad else 'every call stayed inside the clone / allowlist')
              + (f' | {len(tried)} denied attempt(s) outside, e.g. {tried[0]}' if tried else '')))
    # 1b: web
    urls = [c['input'].get('url', '') for c in calls if c['name'] == 'WebFetch']
    proj = [u for u in urls if any(w in u.lower() for w in PROJECT_WORDS)]
    off = [u for u, c in zip(urls, [c for c in calls if c['name'] == 'WebFetch']) if not it.host_ok(u)]
    st = 'FAIL' if proj else 'REVIEW' if off else 'PASS'
    A.append(('A1b web', st, (f'URL names the project: {proj}' if proj else
                              f'tried non-allowlisted hosts (denied): {off[:3]}' if off else
                              f'{len(urls)} fetch(es), all allowlisted')))
    # 2: content scan, skipping lines that are the template's own text
    norm = lambda s: re.sub(r'\s+', ' ', s).strip()
    tmpl = norm(template_text)
    hits = [(i + 1, l.strip()) for i, l in enumerate(solution.splitlines())
            if SCAN.search(l) and norm(l) not in tmpl]
    A.append(('A2 content scan', 'REVIEW' if hits else 'PASS',
              ('; '.join(f'line {i}: {t[:100]!r}' for i, t in hits[:6]) + (f' (+{len(hits) - 6} more)' if len(hits) > 6 else ''))
              if hits else 'no stage-4 / project vocabulary'))
    # 3: completeness and consistency
    missing, na = [h for h in [f'A{i}' for i in range(1, 6)] + ['B1', 'B4']
                   if not re.search(rf'\b{h}\b', solution)], []
    for tier, nxt in (('B2', 'B3'), ('B3', 'B4')):
        m = re.search(rf'^#+\s*{tier}\.[^\n]*\n(.*?)(?=^#+\s*{nxt}\.|^\*\*{nxt}\.|\Z)', solution, re.M | re.S)
        if not m:
            missing.append(tier)
            continue
        body = m.group(1)
        items = [f'{tier}{c}' for c in 'abcdefgh']
        absent = [h for h in items if not re.search(rf'\b{h}\b', body)]
        if absent and re.search(r'n/a\s*:(?!\s*`?<reason>)\s*\S', body, re.I):
            na.append(tier)                       # a tier declared not doable, with a reason
        else:
            missing += absent
    if not re.search(r'^#+\s*C\.', solution, re.M): missing.append('C')
    A.append(('A3 completeness', 'FAIL' if missing else 'PASS',
              f'missing sections: {missing}' if missing else
              'A1-A5, B1, B2a-h, B3a-h, B4 and C present' + (f' ({", ".join(na)} declared n/a)' if na else '')))
    blob = ' '.join(json.dumps(c['input']) for c in calls)
    csec = re.split(r'^#+\s*C\.[^\n]*\n', solution, flags=re.M)
    unread = []
    for l in (csec[1].splitlines() if len(csec) > 1 else []):
        tok = re.sub(r'^[\s\-\*\d\.\)]+', '', l).strip().strip('`').split(' ')[0].strip('`,;')
        if tok and ('/' in tok or tok.startswith('http')) and os.path.basename(tok.rstrip('/')) not in blob:
            unread.append(tok)
    cited = set(re.findall(r'https?://[^\s)>\]`"\']+', solution))
    fetched = ' '.join(urls)
    notf = sorted(u for u in cited if u.rstrip('.,;') not in fetched and not any(u.startswith(f) for f in urls if f))
    A.append(('A3b consistency', 'REVIEW' if unread or notf else 'PASS',
              ('; '.join(([f'section C lists paths never read: {unread[:4]}'] if unread else [])
                         + ([f'URLs cited but never fetched (from memory?): {notf[:4]}'] if notf else [])))
              or 'section C and cited URLs match the tool-call log'))
    overall = 'FAIL' if any(a[1] == 'FAIL' for a in A) else 'REVIEW' if any(a[1] == 'REVIEW' for a in A) else 'PASS'
    return A, overall


# ---------------------------------------------------------------- commands

def cmd_run(a):
    stem = a.stem
    pointer, feed = a.pointer or '', a.feed or ''
    if stem in PRESETS:
        pointer, feed = pointer or PRESETS[stem][0], feed or PRESETS[stem][1]
    if not pointer or not feed:
        sys.exit('this case has no preset: give --pointer <file:line> and --feed 3a|3b')
    cdir = case_dir(stem, a.attempt)
    prompt, tmpl = build_prompt(pointer)
    flags = ' '.join(it.run_flags())
    if a.dry_run:
        print(f'case dir : {cdir}\npointer  : {pointer}  (feed {feed})\nflags    : {flags}\n--- prompt tail ---')
        print('\n'.join(prompt.splitlines()[-6:]))
        print(f'--- prompt is {len(prompt)} chars; nothing was run')
        return 0
    if not shutil.which('claude'):
        sys.exit('`claude` not found on PATH')
    iso = check_isolation_report()
    if cdir.exists():
        sys.exit(f'{cdir} already exists; attempts are never reused: pass --attempt {a.attempt + 1}')
    src = it.ensure_workspace(cdir)
    check_pointer(src, pointer)
    (cdir / 'prompt.md').write_text(prompt, encoding='utf-8')
    ver = subprocess.run(['claude', '--version'], text=True, capture_output=True).stdout.strip()
    extra = ['--model', a.model] if a.model else []
    print(f'case {stem}  attempt {a.attempt}\nentry pointer {pointer}\nisolation: {iso["result"]} ({iso["path"]})\nrunning the writer (this can take many minutes) ...')
    dur = run_writer(src, prompt, cdir / 'run.jsonl', cdir / 'run.stderr', extra, a.timeout)

    res = it.parse((cdir / 'run.jsonl').read_text(encoding='utf-8'))
    if res['error']:
        sys.exit(f"\nthe writer did not complete: {res['error']}\nlogs in {cdir}")
    (cdir / 'tool-calls.txt').write_text('\n'.join(f"{c['name']} {json.dumps(c['input'])}" for c in res['calls']) + '\n', encoding='utf-8')
    (cdir / 'solution.md').write_text(res['final'], encoding='utf-8')
    A, overall = audit(src, res, res['final'], tmpl)
    by_tool = {}
    for c in res['calls']: by_tool[c['name']] = by_tool.get(c['name'], 0) + 1
    meta = dict(stem=stem, pointer=pointer, feed=feed, attempt=a.attempt, model=res['model'], cli=ver,
                date=str(datetime.date.today()), seconds=int(dur), solution_sha256=sha256(cdir / 'solution.md'),
                isolation_cell=iso['cell'], isolation_report=iso['path'], overall=overall,
                audits=[dict(id=x, status=s, note=n) for x, s, n in A], calls=by_tool)
    (cdir / 'audit.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    lines = [f'short-path run  {stem}  attempt {a.attempt}  {datetime.datetime.now().astimezone():%Y-%m-%d %H:%M %Z}',
             f'entry pointer {pointer}  feed {feed}', f'{ver}  model {res["model"]}  {int(dur) // 60} min', f'flags: {flags}',
             f'isolation: {iso["result"]}  | {iso["cell"]}', f'tool calls: {by_tool}', '']
    lines += [f'{x:<17} {s:<7} {n}' for x, s, n in A]
    lines += ['', f'AUDIT: {overall}']
    lines.append({'PASS': f'next: python3 {HERE.name}/run-case.py file --stem {stem}' + (f' --attempt {a.attempt}' if a.attempt > 1 else ''),
                  'REVIEW': f'read solution.md for every REVIEW item above; if all are fine: file --stem {stem}'
                            + (f' --attempt {a.attempt}' if a.attempt > 1 else '') + ' --accept-review',
                  'FAIL': f'discard this attempt (keep {cdir}); rerun with --attempt {a.attempt + 1}. Never edit the solution.'}[overall])
    rep = '\n'.join(lines)
    (cdir / 'run-report.txt').write_text(rep + '\n', encoding='utf-8')
    print('\n' + rep + f'\n\nfiles: {cdir}/{{solution.md,run-report.txt,audit.json,run.jsonl,tool-calls.txt}}')
    return 0 if overall != 'FAIL' else 1


def cmd_file(a):
    cdir = case_dir(a.stem, a.attempt)
    try: meta = json.loads((cdir / 'audit.json').read_text(encoding='utf-8'))
    except OSError: sys.exit(f'no audit.json in {cdir}: run `run` first')
    sol = cdir / 'solution.md'
    if sha256(sol) != meta['solution_sha256']:
        sys.exit('solution.md changed since it was audited: a solution is never edited. Discard and rerun.')
    if meta['overall'] == 'FAIL':
        sys.exit('the audit failed: this attempt is discarded, not filed')
    if meta['overall'] == 'REVIEW' and not a.accept_review:
        sys.exit('the audit needs review: read the REVIEW items in run-report.txt, then pass --accept-review')
    sp = pathlib.Path(a.short_path_dir) if a.short_path_dir else HERE
    stem_out = a.stem + ('--r2' if a.r2 else '')
    dest = sp / 'cases' / (stem_out + '.md')
    idx = sp / '_INDEX.md'
    old_dest = None
    if dest.exists():
        if not a.supersede:
            sys.exit(f'{dest} already exists: a filed solution is never replaced. '
                     'To file a new version, pass --supersede (the old one is renamed --vN, not edited).')
        n = 1
        while (sp / 'cases' / f'{stem_out}--v{n}.md').exists():
            n += 1
        old_dest = sp / 'cases' / f'{stem_out}--v{n}.md'
    text = sol.read_text(encoding='utf-8')
    row = f"| Session / date | {meta['model']}, {meta['cli']}, {meta['date']}, attempt {meta['attempt']} |"
    if re.search(r'^\|\s*Session / date\s*\|.*$', text, re.M):
        text = re.sub(r'^\|\s*Session / date\s*\|.*$', lambda m: row, text, count=1, flags=re.M)
    else:
        text = re.sub(r'^(#[^\n]*\n)', lambda m: m.group(1) + f"\n*Session / date: {meta['model']}, {meta['cli']}, {meta['date']}, attempt {meta['attempt']}*\n", text, count=1)
    lines = idx.read_text(encoding='utf-8').splitlines()
    hdr = next(i for i, l in enumerate(lines) if l.startswith('| Stem'))
    if 'Status' not in lines[hdr]:                     # migrate older indexes: add a Status column
        lines[hdr] += ' Status |'
        lines[hdr + 1] += '---|'
        for i in range(hdr + 2, len(lines)):
            if lines[i].startswith('|'): lines[i] += ' current |'
    if old_dest:
        for i in range(hdr + 2, len(lines)):
            cells = lines[i].split('|')
            if lines[i].startswith('|') and cells[1].strip() == stem_out:
                cells[1] = f' {old_dest.stem} '
                cells[-2] = f' superseded {meta["date"]} by `{dest.name}` '
                lines[i] = '|'.join(cells)
        old_dest_txt = dest.read_text(encoding='utf-8')
        dest.rename(old_dest)
        assert old_dest.read_text(encoding='utf-8') == old_dest_txt
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(text if text.endswith('\n') else text + '\n', encoding='utf-8')
    digest = sha256(dest)
    audit_cell = 'pass' if meta['overall'] == 'PASS' else 'pass (reviewed)'
    new = (f"| {stem_out} | `{meta['pointer']}` | {meta['feed']} | {meta['date']} | `{digest}` | "
           f"{meta['model']} | {meta['isolation_cell']} | {audit_cell} | pending | current |")
    last = max(i for i, l in enumerate(lines) if l.startswith('|'))
    lines.insert(last + 1, new)
    idx.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'filed {dest}\nsha256 {digest}\nadded a row to {idx}' + (f'\nthe previous solution was renamed to {old_dest.name} and marked superseded' if old_dest else '') + '\nNothing is committed: commit when you are ready.')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run'); f = sub.add_parser('file')
    for s in (r, f):
        s.add_argument('--stem', required=True)
        s.add_argument('--attempt', type=int, default=1)
    r.add_argument('--pointer', help='file:line relative to the clone root (default: the preset)')
    r.add_argument('--feed', choices=['3a', '3b'])
    r.add_argument('--model', default='')
    r.add_argument('--timeout', type=int, default=3600, help='seconds before the writer is killed')
    r.add_argument('--dry-run', action='store_true')
    f.add_argument('--accept-review', action='store_true')
    f.add_argument('--r2', action='store_true', help='file as <stem>--r2.md (a noise-check run)')
    f.add_argument('--supersede', action='store_true', help='file a new version: rename the existing <stem>.md to --vN and mark it superseded')
    f.add_argument('--short-path-dir', help=argparse.SUPPRESS)
    a = ap.parse_args()
    return cmd_run(a) if a.cmd == 'run' else cmd_file(a)


if __name__ == '__main__':
    sys.exit(main())
