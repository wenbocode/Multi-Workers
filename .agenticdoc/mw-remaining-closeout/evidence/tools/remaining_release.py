"""Freeze the explicitly scoped closeout files over the current installed release."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('release_tools', ROOT / '.tmp/dp-window-release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
release.TAG = 'mw-remaining-closeout-20261124'
release.OLD = release.GLOBAL / 'releases/mw-dual-roots-4bcdbccd5'
release.NEW = release.GLOBAL / 'releases' / release.TAG
release.STAGE = ROOT / '.tmp/remaining-release-stage'
release.MANIFEST = release.NEW / 'release-manifest.json'
EVIDENCE = ROOT / '.agenticdoc/mw-remaining-closeout/evidence'

def prepare():
    release.STAGE.mkdir()
    names = subprocess.check_output(['git', '-c', 'core.longpaths=true', 'ls-files', '-m', '-o', '--exclude-standard', '--', 'packages', 'AGENTS.md', 'biome.json', 'scripts/check-ts-relative-imports.mjs'], cwd=ROOT).decode().splitlines()
    hashes = {}
    for name in sorted(set(names)):
        if any(part in Path(name).parts for part in ('.tmp', '.agenticdoc', '_r8_tmp_exact')):
            continue
        if '/dist/' in name and not name.startswith('packages/ai/dist/providers/data/'):
            continue
        if '/fixtures/dp-continuity-offline-key-l2/runs/' in name:
            continue
        source = ROOT / name
        if not source.is_file():
            raise RuntimeError('Scoped source missing: ' + name)
        data = source.read_bytes()
        target = release.STAGE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        hashes[name] = release.digest(data)
    record = {'base': release.git('rev-parse', 'HEAD').decode().strip(), 'paths': hashes, 'conflicts': []}
    (release.STAGE / 'stage.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    (EVIDENCE / 'scoped-files.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    release.clone_tree()
    print('Frozen source files:', len(hashes), flush=True)

def check():
    release.check_candidate()
    record = json.loads((release.STAGE / 'stage.json').read_bytes())
    assert all(release.digest((ROOT / file).read_bytes()) == checksum for file, checksum in record['paths'].items())
    assert all(release.digest((release.NEW / file).read_bytes()) == checksum for file, checksum in record['paths'].items())
    manifest = {
        'release_id': release.TAG, 'phase': 'candidate-verified', 'commit': release.git('rev-parse', 'HEAD').decode().strip(),
        'base_commit': record['base'], 'parent_release': str(release.OLD),
        'included_keys': ['mw-lean-execution', 'mw-dual-additional-write-roots', 'mw-remaining-closeout', 'mw-signoff-freeze-metadata', 'ue-frame-install-generate', 'mw-runtime-version', 'mw-pi-version', 'mw-zai-glm54', 'mw-duty-followup'],
        'source_overlay': record['paths'], 'pi_version': '0.83.0',
        'source_check_model_data': '2026-11-18T11:33:22.509Z', 'runtime_model_data': '2026-11-24T03:09:36.062Z',
        'artifacts': {p.as_posix(): release.digest((release.NEW / p).read_bytes()) for p in (release.MW, release.PI, release.BUNDLE)},
    }
    release.save_manifest(manifest)
    (EVIDENCE / 'candidate.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')

def activate():
    release.activate()

{'prepare': prepare, 'build': release.build, 'check': check, 'activate': activate}[sys.argv[1]]()
