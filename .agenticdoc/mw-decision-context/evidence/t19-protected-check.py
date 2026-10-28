"""Run full check on a byte-exact copy of the working tree, not foreign files."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[3]
out = root / '.agenticdoc/mw-decision-context/evidence/t19-check'
out.mkdir(exist_ok=True)
listed = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=root, capture_output=True, check=True).stdout
paths = sorted(set(p.decode('utf-8') for p in listed.split(b'\0') if p))
manifest = {}
with tempfile.TemporaryDirectory(prefix='dc-t19-check-') as temp:
    work = Path(temp) / 'repo'
    work.mkdir()
    for relative in paths:
        source = root / relative
        if not source.is_file() or source.is_symlink():
            continue
        body = source.read_bytes()
        dest = work / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        manifest[relative] = hashlib.sha256(body).hexdigest()
    # The checker ignores node_modules. Reuse installed packages read-only;
    # no install/lifecycle/build command is run.
    linked = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(work / 'node_modules'), str(root / 'node_modules')], capture_output=True)
    if linked.returncode:
        raise RuntimeError(linked.stderr.decode(errors='replace'))
    env = os.environ.copy()
    for key in list(env):
        if any(s in key.upper() for s in ('API_KEY', 'TOKEN', 'SECRET', 'PASSWORD')) or key.upper() in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'TIMI_BASE_URL', 'PI_WORKER_TASK'):
            env.pop(key, None)
    home = Path(temp) / 'home'
    home.mkdir()
    env.update(HOME=str(home), USERPROFILE=str(home), PI_CODING_AGENT_DIR=str(home / 'agent'), NO_COLOR='1')
    cmd = ['cmd.exe', '/d', '/c', 'npm run check']
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    result = subprocess.run(cmd, cwd=work, env=env, capture_output=True, timeout=600)
    ended = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (out / 'stdout.log').write_bytes(result.stdout)
    (out / 'stderr.log').write_bytes(result.stderr)
    formatted = [p for p, digest in manifest.items() if (work / p).is_file() and hashlib.sha256((work / p).read_bytes()).hexdigest() != digest]
    for relative in formatted:
        dest = out / 'formatter-output' / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((work / relative).read_bytes())
    source_changed = [p for p, digest in manifest.items() if not (root / p).is_file() or hashlib.sha256((root / p).read_bytes()).hexdigest() != digest]
    meta = dict(argv=cmd, cwd=str(work), utc_start=started, utc_end=ended, exit=result.returncode, copied_files=len(manifest), formatter_changes=formatted, original_changed_during_check=source_changed, scope='full npm run check, copied working tree; no formatter result applied to source')
    (out / 'metadata.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    (out / 'source-hashes.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    print(json.dumps(meta, indent=2))
    # Remove only our temporary junction, not its target.
    subprocess.run(['cmd.exe', '/d', '/c', 'rmdir', str(work / 'node_modules')], check=True)
    sys.exit(result.returncode)
