"""Infrastructure preflight only. Never submits the scored task to a model."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path('/private/tmp/pi-opsgraph-v1.1')
SOLVER = ROOT / 'solver'
EVIDENCE = ROOT / 'evaluator'
OLD = Path('/private/tmp/pi-opsgraph-v1/evaluator')
PYTHON = '/Volumes/Parth Patel/PI/Pi_Engineering_CLI/.venv/bin/python'
BASE = 'f975fc13c14879f36236c4eb0f315d4c5159d243'
ENV = {k: os.environ[k] for k in ('PATH', 'HOME', 'USER', 'LANG') if k in os.environ}
ENV.update(PYTHONPATH=str(ROOT / 'runtime'), PYTHONDONTWRITEBYTECODE='1',
           TMPDIR=str(SOLVER / '.bench-tmp'), NO_COLOR='1', NEXT_TELEMETRY_DISABLED='1')
RESULTS = {}

def command(argv, label, sandbox=True):
    full = ['/usr/bin/sandbox-exec', '-f', str(ROOT / 'solver.sb'), *argv] if sandbox else argv
    start = time.monotonic()
    result = subprocess.run(full, cwd=SOLVER, env=ENV, capture_output=True, text=True, timeout=600)
    (EVIDENCE / (label + '.json')).write_text(json.dumps(dict(command=full, exit=result.returncode,
        seconds=time.monotonic()-start, stdout=result.stdout, stderr=result.stderr), indent=2))
    print(label, result.returncode, flush=True)
    return result

def cli(args, label):
    result = command([PYTHON, '-m', 'pi_app', *args, '--workspace', str(SOLVER), '--json', '--no-animate'], label)
    return json.loads(result.stdout)

def call(name, arguments, label):
    task = cli(['call', name, json.dumps(arguments)], label + '-proposal')
    pending = next(c for c in task['calls'] if c['status'] == 'pending')
    task = cli(['approve', task['id'], pending['hash']], label)
    assert task['calls'][-1]['status'] == 'done', task
    return task['calls'][-1]['result']

def main():
    (SOLVER / '.bench-tmp').mkdir(exist_ok=True)
    for name in ('hidden.mjs', 'rubric.json'):
        shutil.copy2(OLD / name, EVIDENCE / name)
        assert (OLD / name).read_bytes() == (EVIDENCE / name).read_bytes()
    production = '/Users/benchbrex/Documents/BeGuardit'
    before = {label: subprocess.check_output(['git', '-C', production, *args]) for label, args in
              [('head', ['rev-parse', 'HEAD']), ('status', ['status', '--porcelain=v1']), ('diff', ['diff', '--binary'])]}
    for label, data in before.items():
        (EVIDENCE / ('production-' + label + '.before')).write_bytes(data)
    assert command(['git', 'rev-parse', 'HEAD'], 'starting-head').stdout.strip() == BASE
    assert not command(['git', 'status', '--porcelain'], 'starting-status').stdout
    assert not command(['git', 'remote'], 'starting-remote').stdout
    config = json.loads((OLD / 'configuration.json').read_text())
    for name, argv in config['checks'].items():
        config['checks'][name] = [a.replace('/pi-opsgraph-v1/', '/pi-opsgraph-v1.1/') for a in argv[3:]]
    config['checks']['ui'][-1] = '--config=/private/tmp/pi-opsgraph-v1.1/playwright.config.cjs'
    assert all('sandbox-exec' not in ' '.join(v) for v in config['checks'].values())
    (SOLVER / '.pi-engineering').mkdir(exist_ok=True)
    (SOLVER / '.pi-engineering/config.json').write_text(json.dumps(config, indent=2))
    shutil.copy2(SOLVER / '.pi-engineering/config.json', EVIDENCE / 'configuration.json')
    assert command(['/usr/bin/true'], 'single-sandbox').returncode == 0
    assert command(['/bin/cat', str(EVIDENCE / 'rubric.json')], 'hidden-denied').returncode != 0
    assert command(['/bin/cat', production + '/package.json'], 'production-denied').returncode != 0
    assert command(['/usr/bin/touch', str(ROOT / 'forbidden-write')], 'outside-write-denied').returncode != 0
    read = call('workspace_read', {'path': 'AGENTS.md'}, 'workspace-read')
    assert read['content'] and read['hash']
    cli(['knowledge', 'add', 'app/page.tsx'], 'source-index')
    search = call('knowledge_search', {'query': 'import'}, 'workspace-search')
    assert search['observations'], search
    temporary = SOLVER / 'pi-preflight.txt'
    try:
        created = call('workspace_write', dict(path=temporary.name, content='preflight one\n', expected_hash='missing'), 'workspace-create')
        current = call('workspace_read', dict(path=temporary.name), 'workspace-hash')
        assert created['hash'] == current['hash']
        call('workspace_write', dict(path=temporary.name, content='preflight two\n', expected_hash=current['hash']), 'workspace-update')
        assert temporary.read_text() == 'preflight two\n'
    finally:
        temporary.unlink(missing_ok=True)
    for name in ['next-docs', 'public', 'lint', 'typecheck', 'build']:
        result = call('workspace_check', {'name': name}, 'check-' + name)
        RESULTS[name] = result
        if name == 'public':
            assert result['exit_code'] == 1 and 'ERR_MODULE_NOT_FOUND' in result['output']
        else:
            assert result['exit_code'] == 0, result
    assert (SOLVER / 'out/index.html').is_file()
    assert not command(['git', 'status', '--porcelain'], 'final-status').stdout
    assert command(['git', 'rev-parse', 'HEAD'], 'final-head').stdout.strip() == BASE
    for label, args in [('head', ['rev-parse', 'HEAD']), ('status', ['status', '--porcelain=v1']), ('diff', ['diff', '--binary'])]:
        assert subprocess.check_output(['git', '-C', production, *args]) == before[label]
    (EVIDENCE / 'preflight-results.json').write_text(json.dumps(RESULTS, indent=2))
    # Retain preflight receipts outside the future solver's accessible context.
    shutil.move(str(SOLVER / '.pi-engineering'), str(EVIDENCE / 'preflight-pi-state'))
    (SOLVER / '.pi-engineering').mkdir()
    shutil.copy2(EVIDENCE / 'configuration.json', SOLVER / '.pi-engineering/config.json')
    print('Core preflight passed; browser and hosted connectivity remain separately gated.', flush=True)

if __name__ == '__main__':
    main()
