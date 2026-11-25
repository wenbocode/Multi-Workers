"""Frozen-release driver for commit 9ac9847a5 on top of mw-anti-ornament-a575737ba.

Same flow as .agenticdoc/mw-anti-ornament-guardrails/evidence/tools/anti-ornament-release.py:
overlay the commit's package files onto a clone of the active release, build inside the
clone, verify, switch the user-global entry points with a rollback copy, then verify again.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_tools', ROOT / '.tmp/dp-window-release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
COMMIT_SHORT = '9ac9847a5'
release.TAG = 'mw-anti-ornament-followup-' + COMMIT_SHORT
release.OLD = release.GLOBAL / 'releases/mw-anti-ornament-a575737ba'
release.NEW = release.GLOBAL / 'releases' / release.TAG
release.STAGE = ROOT / '.tmp/anti-ornament-followup-release-stage'
release.MANIFEST = release.NEW / 'release-manifest.json'
EVIDENCE = ROOT / '.agenticdoc/mw-anti-ornament-followup/evidence'
FILES = [
    'AGENTS.md',
    'packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts',
    'packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts',
    'packages/coding-agent/test/extensions/agent-team-loop.test.ts',
    'packages/multi-workers/templates/AGENTS.md',
    'packages/multi-workers/test_init_agents_guide.py',
    'packages/multi-workers/docs/plan-closure.md',
]
# Text that must be in the new bundle, and text that must be gone from it.
PRESENT = ['反粉饰护栏', '禁止自写证据一致性或哈希对账脚本', '至少经真实入口调用一次']
ABSENT = ['须成对撤销', '失效解绑', '复杂改动另派独立评审']


def has_marker(text, marker):
    # esbuild escapes non-ASCII string literals as \uXXXX.
    return marker in text or json.dumps(marker)[1:-1].lower() in text.lower()


def commit_id():
    return release.git('rev-parse', COMMIT_SHORT).decode().strip()


def bundle_text(root):
    return (root / release.BUNDLE).read_text(encoding='utf-8')


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


def build():
    old = bundle_text(release.OLD)
    report = {'old_present': {m: has_marker(old, m) for m in PRESENT},
              'old_absent': {m: has_marker(old, m) for m in ABSENT}}
    # The baseline must still carry every phrase this commit removes.
    assert all(report['old_absent'].values()), report
    release.build()
    new = bundle_text(release.NEW)
    report['new_present'] = {m: has_marker(new, m) for m in PRESENT}
    report['new_absent'] = {m: has_marker(new, m) for m in ABSENT}
    assert all(report['new_present'].values()) and not any(report['new_absent'].values()), report
    (EVIDENCE / 'bundle-markers.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))


def check():
    release.check_candidate()
    staged = json.loads((release.STAGE / 'stage.json').read_bytes())
    commit = commit_id()
    for name, sha in staged['paths'].items():
        assert release.digest((release.NEW / name).read_bytes()) == sha, name
        assert release.normalized((release.NEW / name).read_bytes()) == release.git('show', f'{commit}:{name}'), name
    old = json.loads((release.OLD / 'release-manifest.json').read_bytes())
    pi_version = json.loads((release.NEW / release.PI.parents[1] / 'package.json').read_bytes())['version']
    assert pi_version == old['pi_version'], pi_version
    manifest = {
        'release_id': release.TAG, 'phase': 'candidate-verified', 'commit': commit,
        'base_commit': staged['base'], 'parent_release': str(release.OLD),
        'included_keys': old['included_keys'] + ['mw-anti-ornament-followup'],
        'agentic_task_commit': '1828e98', 'source_overlay': staged['paths'], 'pi_version': pi_version,
        'artifacts': {p.as_posix(): release.digest((release.NEW / p).read_bytes()) for p in (
            release.MW, release.PI, release.BUNDLE)},
    }
    release.save_manifest(manifest)
    (EVIDENCE / 'candidate.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


def verify():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    shim = release.GLOBAL / 'bin/mw.cmd'
    out = subprocess.check_output([str(shim), 'version', '--json'], cwd=ROOT, env=env)
    version = json.loads(out)
    assert version['global']['release'] == release.TAG and version['global']['commit'] == commit_id(), version['global']
    assert version['global_extension']['release'] == release.TAG and version['global_extension']['uses_global_default']
    manifest = json.loads((release.NEW / 'release-manifest.json').read_bytes())
    assert manifest['phase'] == 'user-global-installed-and-verified'
    for name, checksum in manifest['artifacts'].items():
        assert hashlib.sha256((release.NEW / name).read_bytes()).hexdigest() == checksum, name
    for name, checksum in manifest['global_install_sha256'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == checksum, name
    ext = Path.home() / '.pi/agent/extensions' / release.BUNDLE.name
    text = ext.read_text(encoding='utf-8')
    assert all(has_marker(text, m) for m in PRESENT), 'global extension lacks the new text'
    assert not any(has_marker(text, m) for m in ABSENT), 'global extension still carries removed text'
    result = {'release': release.TAG, 'commit': commit_id(), 'global': version['global'],
              'global_extension': version['global_extension'], 'backup': manifest['backup'],
              'installed_at_utc': manifest['installed_at_utc']}
    (EVIDENCE / 'installed.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))


{'prepare': prepare, 'build': build, 'check': check, 'activate': release.activate, 'verify': verify}[sys.argv[1]]()
