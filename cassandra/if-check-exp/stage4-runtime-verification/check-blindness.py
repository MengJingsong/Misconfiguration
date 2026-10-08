#!/usr/bin/env python3
"""Check that a stage-4 executor session stayed blind to the other path.

    python3 check-blindness.py --stem <stem> --for short
    python3 check-blindness.py --stem <stem> --for short --session <uuid>
    python3 check-blindness.py --stem <stem> --for short --transcript FILE [--workspace DIR]

Scans the tool calls (not the prompt) of Claude Code session transcripts for what
the executor of that path must not touch, and prints every hit. A hit is either
EXECUTED (the call ran) or REFUSED (the call failed or was denied; it shows the
executor tried). Exit status 1 if any call was executed, 0 otherwise: zero hits is
the pass, and refused attempts are notes to read.

By default it reads the newest transcript under ~/.claude/projects/ (any project
folder) and prints the first words of its first prompt so you can confirm it is the
executor's session; --session picks a session by id, --transcript a file. Give
--workspace (the executor's working directory) to also flag file-tool calls outside
it. `run-executor.py collect` imports this module and does all of this for you.

The long path now runs first, so only the short path's executor has to be blind; the
`--for long` list is kept for a case where it is wanted.
"""
import argparse, glob, json, os, pathlib, re, sys

# (label, regex) applied to what each tool call touches (see scan_text): its paths, URLs and command.
# Executor started INSIDE the repository (the manual flow of executor-prompts.md): its own calls name
# the repository, so only the other path's folders can be flagged.
SHORT_BLOCKED = [
    ('HANDOFF.md', r'HANDOFF'),
    ('the long path (stage 3)', r'stage3-ai-deep-read/long-path/'),
    ('the long path (stage 4)', r'stage4-runtime-verification/long-path/'),
    ('the comparison folder', r'comparison/'),
]
LONG_BLOCKED = [
    ('HANDOFF.md', r'HANDOFF'),
    ('the short path (stage 3)', r'stage3-ai-deep-read/short-path/'),
    ('the short path (stage 4)', r'stage4-runtime-verification/short-path/'),
    ('the comparison folder', r'comparison/'),
]
# Executor started in a prepared WORKSPACE outside the repository (`run-executor.py`): nothing of the
# repository may appear in any call, in any form, and neither may the shared-mount copy of it.
SHORT_BLOCKED_WORKSPACE = [
    ('HANDOFF.md', r'HANDOFF'),
    ('a long-path folder or file', r'long-path'),
    ('the comparison folder', r'comparison/'),
    ('the project repository by name', r'Misconfiguration'),
    ('the repository copy on the shared mount (anything under git-repos but cassandra-src)', r'git-repos(?!/cassandra-src)'),
    ('Claude Code state (transcripts, settings, history)', r'\.claude(?:/|\b)'),
    ('the project on GitHub or Google Docs', r'MengJingsong|docs\.google\.com'),
]
FILE_TOOLS = {'Read': ('file_path',), 'Write': ('file_path',), 'Edit': ('file_path',), 'NotebookEdit': ('notebook_path',),
              'Grep': ('path',), 'Glob': ('path',)}


def content_text(c):
    if isinstance(c, list):
        return ' '.join(x.get('text', '') for x in c if isinstance(x, dict))
    return c or ''


def read_transcript(path):
    """The tool calls of one transcript file, in order, each with its result: dicts with name, input, is_error, result."""
    calls, order = {}, []
    for line in open(path, encoding='utf-8', errors='replace'):
        try:
            e = json.loads(line)
        except Exception:
            continue
        msg = e.get('message') or {}
        content = msg.get('content')
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict):
                continue
            if e.get('type') == 'assistant' and c.get('type') == 'tool_use':
                calls[c['id']] = dict(name=c.get('name'), input=c.get('input', {}), is_error=None, result='')
                order.append(c['id'])
            elif e.get('type') == 'user' and c.get('type') == 'tool_result' and c.get('tool_use_id') in calls:
                calls[c['tool_use_id']].update(is_error=bool(c.get('is_error')), result=content_text(c.get('content'))[:300])
    return [calls[i] for i in order]


def first_prompt(path):
    for line in open(path, encoding='utf-8', errors='replace'):
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get('type') == 'user':
            m = e.get('message', {}).get('content')
            if isinstance(m, list):
                m = ' '.join(x.get('text', '') for x in m if isinstance(x, dict))
            return ' '.join((m or '').split())[:140]
    return '?'


def transcripts_for(session_ids=(), workspace=None):
    """Every transcript of the given sessions (and of any sub-agent they started), plus every
    session whose recorded working directory is the workspace or below it."""
    base = pathlib.Path('~/.claude/projects').expanduser()
    found = set()
    for sid in session_ids:
        found.update(base.glob(f'*/{sid}.jsonl'))
        found.update(base.glob(f'*/{sid}/**/*.jsonl'))
    if workspace:
        ws = str(pathlib.Path(workspace).resolve())
        for f in base.glob('*/*.jsonl'):
            try:
                with open(f, encoding='utf-8', errors='replace') as fh:
                    for _ in range(40):
                        cwd = (json.loads(fh.readline() or '{}')).get('cwd')
                        if cwd:
                            if cwd == ws or cwd.startswith(ws + os.sep):
                                found.add(f)
                            break
            except Exception:
                continue
    return sorted(found)


def strip_heredocs(cmd):
    """Drop here-document bodies: text a command writes into a file is not something it reads."""
    return re.sub(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\b", '<<HEREDOC', cmd, flags=re.S)


def scan_text(c):
    """The part of a tool call that says WHAT it touches: paths, URLs and commands, never the text a call
    writes into a file or the term a search looks for (the template's own words would trip the audit)."""
    i, n = c['input'], c['name']
    if n == 'Bash':
        return strip_heredocs(str(i.get('command', '')))
    if n in ('Write', 'Edit'):
        return str(i.get('file_path', ''))
    if n == 'NotebookEdit':
        return str(i.get('notebook_path', ''))
    if n == 'Read':
        return str(i.get('file_path', ''))
    if n == 'Grep':
        return ' '.join(str(i.get(k, '')) for k in ('path', 'glob'))
    if n == 'Glob':
        return ' '.join(str(i.get(k, '')) for k in ('path', 'pattern'))
    if n == 'WebFetch':
        return str(i.get('url', ''))
    return json.dumps(i, ensure_ascii=False)


def patterns(which, repo=None, workspace=None):
    if which == 'short' and workspace:
        pats = list(SHORT_BLOCKED_WORKSPACE)
        if repo:
            pats.append(('the local project repository path', re.escape(str(repo))))
    else:
        pats = list(SHORT_BLOCKED if which == 'short' else LONG_BLOCKED)
    return [(label, re.compile(rx)) for label, rx in pats]


def inside(path, base):
    p = os.path.realpath(os.path.join(base, os.path.expanduser(path)))
    b = os.path.realpath(base)
    if p == b or p.startswith(b + os.sep):
        return True
    # The session's own scratchpad (/tmp/claude-<uid>/<workspace path with every non-alphanumeric as '-'>/<session>/scratchpad)
    # is the harness's temp space for that session, not a way out of the workspace.
    enc = re.sub(r'[^A-Za-z0-9]', '-', b)
    if re.match(rf'^/tmp/claude-\d+/{re.escape(enc)}/[0-9a-f-]+/scratchpad(/|$)', p):
        return True
    return own_tool_results(base).match(p) is not None


def own_tool_results(workspace):
    """The session's own spilled tool output (~/.claude/projects/<workspace encoded>/<session>/tool-results/<file>):
    Claude Code writes a long command result there and the session reads its own output back. Only plain file names
    directly in that folder match, so the pattern cannot reach the rest of ~/.claude."""
    enc = re.sub(r'[^A-Za-z0-9]', '-', os.path.realpath(workspace))
    home = re.escape(os.path.expanduser('~'))
    return re.compile(rf'(?:{home}|~|\$HOME)/\.claude/projects/{re.escape(enc)}/[0-9a-f-]+/tool-results/[A-Za-z0-9_.-]+(?![A-Za-z0-9_./-])')


def scan_calls(calls, which='short', repo=None, workspace=None):
    """Return the hits: dicts with the call, why it was flagged, and executed/refused."""
    pats, hits = patterns(which, repo, workspace), []
    for c in calls:
        text = scan_text(c)
        if workspace:                                   # reading its own spilled output back is not a way out
            text = own_tool_results(workspace).sub('<own-tool-result>', text)
        why = [label for label, rx in pats if rx.search(text)]
        if workspace and c['name'] in FILE_TOOLS:
            for key in FILE_TOOLS[c['name']]:
                v = c['input'].get(key)
                if v and not inside(v, workspace):
                    why.append(f'{c["name"]} outside the workspace: {v}')
            pat = c['input'].get('pattern', '') if c['name'] == 'Glob' else ''
            if pat.startswith(('/', '~')) and not inside(re.split(r'[*?\[{]', pat)[0] or '/', workspace):
                why.append(f'Glob pattern outside the workspace: {pat}')
        if why:
            hits.append(dict(call=c, why=why, state='REFUSED' if c['is_error'] else 'EXECUTED'))
    return hits


def report(hits, out=print):
    for h in hits:
        c = h['call']
        out(f"  [{h['state']}] {c['name']}: {json.dumps(c['input'], ensure_ascii=False)[:200]}")
        out(f"             why: {'; '.join(h['why'])}" + (f" | result: {c['result'][:80]!r}" if h['state'] == 'REFUSED' else ''))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--stem', required=True)
    ap.add_argument('--for', dest='path', choices=['short', 'long'], required=True,
                    help="which path's executor the transcript belongs to")
    ap.add_argument('--transcript')
    ap.add_argument('--session', action='append', default=[], help='a session id (repeatable)')
    ap.add_argument('--workspace', help="the executor's working directory")
    ap.add_argument('--repo', default=str(pathlib.Path(__file__).resolve().parents[3]),
                    help='the local project repository (flagged by its path)')
    a = ap.parse_args()

    files = [pathlib.Path(a.transcript)] if a.transcript else transcripts_for(a.session, a.workspace)
    if not files:
        allf = glob.glob(os.path.expanduser('~/.claude/projects/*/*.jsonl'))
        if not allf:
            sys.exit('no transcripts found; pass --transcript FILE')
        files = [pathlib.Path(max(allf, key=os.path.getmtime))]
    total = executed = refused = 0
    for f in files:
        print(f'checking {f}\nfirst prompt: {first_prompt(f)!r}')
        hits = scan_calls(read_transcript(f), a.path, a.repo, a.workspace)
        report(hits)
        total += len(hits)
        executed += sum(h['state'] == 'EXECUTED' for h in hits)
        refused += sum(h['state'] == 'REFUSED' for h in hits)
        print()
    print(f'{executed} executed and {refused} refused tool call(s) touched what the {a.path}-path executor of {a.stem} must not touch'
          f' ({len(files)} transcript(s))')
    return 1 if executed else 0


if __name__ == '__main__':
    sys.exit(main())
