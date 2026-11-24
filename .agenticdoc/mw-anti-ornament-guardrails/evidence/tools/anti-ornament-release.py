import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('release_tools', ROOT / '.tmp/dp-window-release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
COMMIT_SHORT = 'a575737ba'
release.TAG = 'mw-anti-ornament-' + COMMIT_SHORT
release.OLD = release.GLOBAL / 'releases/mw-lean-followup-a06b380a7'
release.NEW = release.GLOBAL / 'releases' / release.TAG
release.STAGE = ROOT / '.tmp/anti-ornament-release-stage'
release.MANIFEST = release.NEW / 'release-manifest.json'
EVIDENCE = ROOT / '.agenticdoc/mw-anti-ornament-guardrails/evidence'
FILES = [
    'packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts',
    'packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts',
    'packages/coding-agent/test/extensions/agent-team-loop.test.ts',
    'packages/multi-workers/templates/AGENTS.md',
    'packages/multi-workers/test_init_agents_guide.py',
    'packages/multi-workers/docs/plan-closure.md',
    'packages/multi-workers/docs/dual-toolchain-practice-guide.md',
]
MARKERS = ['代码不变量与反粉饰护栏', '禁止要求自写证据一致性对账脚本']


def has_marker(text, marker):
    # esbuild escapes non-ASCII string literals as \uXXXX.
    return marker in text or json.dumps(marker)[1:-1].lower() in text.lower()


def commit_id():
    return release.git('rev-parse', COMMIT_SHORT).decode().strip()


def prepare():
    release.STAGE.mkdir()
    hashes = {}
    for name in FILES:
        data = release.git('show', f'{commit_id()}:{name}')
        target = release.STAGE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        hashes[name] = release.digest(data)
    record = {'base': release.git('rev-parse', commit_id() + '^').decode().strip(), 'paths': hashes, 'conflicts': []}
    (release.STAGE / 'stage.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / 'source-inputs.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    release.clone_tree()


def check():
    release.check_candidate()
    staged = json.loads((release.STAGE / 'stage.json').read_bytes())
    commit = commit_id()
    for name, sha in staged['paths'].items():
        assert release.digest((release.NEW / name).read_bytes()) == sha, name
        assert release.normalized((release.NEW / name).read_bytes()) == release.git('show', f'{commit}:{name}'), name
    bundle = (release.NEW / release.BUNDLE).read_text(encoding='utf-8')
    assert all(has_marker(bundle, marker) for marker in MARKERS), 'bundle lacks the new guardrail text'
    old = json.loads((release.OLD / 'release-manifest.json').read_bytes())
    manifest = {
        'release_id': release.TAG, 'phase': 'candidate-verified', 'commit': commit,
        'base_commit': staged['base'], 'parent_release': str(release.OLD),
        'included_keys': old['included_keys'] + ['mw-anti-ornament-guardrails'],
        'agentic_task_commit': 'abed2de', 'source_overlay': staged['paths'], 'pi_version': '0.83.0',
        'artifacts': {p.as_posix(): release.digest((release.NEW / p).read_bytes()) for p in (
            release.MW, release.PI, release.BUNDLE)},
    }
    release.save_manifest(manifest)
    (EVIDENCE / 'candidate.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


def verify():
    env = dict(__import__('os').environ, PYTHONDONTWRITEBYTECODE='1')
    shim = release.GLOBAL / 'bin/mw.cmd'
    out = subprocess.check_output([str(shim), 'version', '--json'], cwd=ROOT, env=env)
    version = json.loads(out)
    assert version['global']['release'] == release.TAG and version['global']['commit'] == commit_id(), version['global']
    assert version['global_extension']['release'] == release.TAG and version['global_extension']['uses_global_default']
    manifest = json.loads((release.NEW / 'release-manifest.json').read_bytes())
    assert manifest['phase'] == 'user-global-installed-and-verified'
    import hashlib
    for name, checksum in manifest['artifacts'].items():
        assert hashlib.sha256((release.NEW / name).read_bytes()).hexdigest() == checksum, name
    for name, checksum in manifest['global_install_sha256'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == checksum, name
    ext = Path.home() / '.pi/agent/extensions' / release.BUNDLE.name
    assert all(has_marker(ext.read_text(encoding='utf-8'), m) for m in MARKERS), 'global extension lacks guardrail'
    result = {'release': release.TAG, 'commit': commit_id(), 'global': version['global'],
              'global_extension': version['global_extension'], 'backup': manifest['backup']}
    (EVIDENCE / 'installed.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))


{'prepare': prepare, 'build': release.build, 'check': check, 'activate': release.activate, 'verify': verify}[sys.argv[1]]()
