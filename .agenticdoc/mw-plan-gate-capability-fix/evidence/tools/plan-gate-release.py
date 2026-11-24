import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('release_tools', ROOT / '.tmp/dp-window-release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
release.TAG = 'mw-plan-gate-capability-20261124'
release.OLD = release.GLOBAL / 'releases/mw-remaining-closeout-20261124'
release.NEW = release.GLOBAL / 'releases' / release.TAG
release.STAGE = ROOT / '.tmp/plan-gate-release-stage'
release.MANIFEST = release.NEW / 'release-manifest.json'
EVIDENCE = ROOT / '.agenticdoc/mw-plan-gate-capability-fix/evidence'
FILES = ['packages/coding-agent/src/extensions/agent-team-loop/shared/agentic-scripts.ts',
         'packages/coding-agent/test/extensions/agentic-scripts-plan-gate.test.ts']

def prepare():
    release.STAGE.mkdir()
    hashes = {}
    for name in FILES:
        data = (ROOT / name).read_bytes()
        target = release.STAGE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        hashes[name] = release.digest(data)
    record = {'base': release.git('rev-parse', 'HEAD').decode().strip(), 'paths': hashes, 'conflicts': []}
    (release.STAGE / 'stage.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    (EVIDENCE / 'source-inputs.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    release.clone_tree()

def check():
    release.check_candidate()
    staged = json.loads((release.STAGE / 'stage.json').read_bytes())
    commit = release.git('rev-parse', 'HEAD').decode().strip()
    assert release.git('rev-parse', commit + '^').decode().strip() == staged['base']
    for name, sha in staged['paths'].items():
        assert release.digest((ROOT / name).read_bytes()) == sha
        assert release.digest((release.NEW / name).read_bytes()) == sha
        assert release.normalized((ROOT / name).read_bytes()) == release.git('show', f'{commit}:{name}')
    compiled = release.NEW / 'packages/coding-agent/dist/extensions/agent-team-loop/shared/agentic-scripts.js'
    probe = subprocess.run(['node', str(ROOT / '.tmp/plan-gate-probe.cjs'), str(compiled), str(EVIDENCE / 'eight-projects-installed.json')], cwd=ROOT)
    assert probe.returncode == 0
    old = json.loads((release.OLD / 'release-manifest.json').read_bytes())
    manifest = {
        'release_id': release.TAG, 'phase': 'candidate-verified', 'commit': commit,
        'base_commit': staged['base'], 'parent_release': str(release.OLD),
        'included_keys': old['included_keys'] + ['mw-plan-gate-capability-fix'],
        'agentic_task_commit': '84bbc2788c9555b350821056f206a698dc6db375',
        'source_overlay': staged['paths'], 'pi_version': '0.83.0',
        'artifacts': {p.as_posix(): release.digest((release.NEW / p).read_bytes()) for p in (
            release.MW, release.PI, release.BUNDLE, compiled.relative_to(release.NEW))},
    }
    release.save_manifest(manifest)
    (EVIDENCE / 'candidate.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')

{'prepare': prepare, 'build': release.build, 'check': check, 'activate': release.activate}[sys.argv[1]]()
