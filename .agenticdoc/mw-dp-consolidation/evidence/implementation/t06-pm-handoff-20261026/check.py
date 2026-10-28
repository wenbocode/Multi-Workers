"""Fresh PM T06 verification; evidence-only writes, peer-aware inventory."""
from __future__ import annotations
import ast
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
HERE = Path(__file__).resolve().parent
KEY = HERE.parents[2]
WT = KEY/'implementation-worktree'
PKG = WT/'packages/multi-workers'
ROOT = KEY.parents[1]
OWN = {'packages/multi-workers/decision_validity.py':'64b9b9e1060aab955a4d0428385e2d450ae94826d1a548088c65f5874c049eb1','packages/multi-workers/test_dp_consolidation_concurrency.py':'c9dc013110de702f733b5ec292c1d62ccdaa93d7ffb4fa7ffcec9101c2a97349'}
FRONTIER = set(OWN) | {'packages/multi-workers/decision_policy.py','packages/multi-workers/test_dp_consolidation_recovery.py','packages/multi-workers/decision.py','packages/multi-workers/decision_backends.py','packages/multi-workers/test_dp_consolidation_materials.py'}
assert sys.dont_write_bytecode and not (HERE/'check.json').exists()
def sha(b):
    return hashlib.sha256(b).hexdigest()
def inventory():
    return {p.relative_to(WT).as_posix():sha(p.read_bytes()) for p in WT.rglob('*') if p.is_file()}
def save(name, value):
    (HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
before = inventory()
save('before-inventory.json',before)
files=[]
for rel, expected in OWN.items():
    b=(WT/rel).read_bytes()
    assert sha(b)==expected
    assert not (ROOT/rel).exists()
    dest=HERE/'before-bytes'/rel
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(b)
    files.append({'path':rel,'sha256':sha(b),'bytes':len(b),'crlf':b.count(b'\r\n'),'bare_lf':b.count(b'\n')-b.count(b'\r\n'),'live_exists':False})
source=(PKG/'decision_validity.py').read_text(encoding='utf-8')
tree=ast.parse(source)
imports=sorted({node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node,ast.ImportFrom) and node.module} | {alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node,ast.Import) for alias in node.names})
assert set(imports)<= {'__future__','collections','dataclasses','hashlib','json','posixpath','re','types','typing'}
functions={n.name:n.lineno for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
fixture=HERE/'fixture'
env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR') if k in os.environ}
for name in ('HOME','USERPROFILE','TEMP','TMP','TMPDIR'):
    p=fixture/name.lower()
    p.mkdir(parents=True,exist_ok=True)
    env[name]=str(p)
(fixture/'project').mkdir(parents=True,exist_ok=True)
env.update({'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1'})
commands=[]
for label, args in [('pm-green',[str(HERE/'bootstrap.py'),'tests']),('pm-literal',['-m','pytest','-p','no:cacheprovider','-q','test_dp_consolidation_concurrency.py']),('pm-probe',[str(HERE/'bootstrap.py'),'probes'])]:
    argv=[sys.executable,'-B',*args]
    r=subprocess.run(argv,cwd=PKG,env=env,capture_output=True)
    (HERE/(label+'.stdout')).write_bytes(r.stdout)
    (HERE/(label+'.stderr')).write_bytes(r.stderr)
    print(label,'rc=',r.returncode);print(r.stdout.decode('utf-8'));print(r.stderr.decode('utf-8'))
    commands.append({'label':label,'argv':argv,'cwd':str(PKG),'rc':r.returncode})
    assert r.returncode==0
    if label in ('pm-green','pm-literal'):
        assert b'65 passed' in r.stdout
after=inventory()
save('after-inventory.json',after)
assert before==after
for rel in OWN:
    p=HERE/'after-bytes'/rel
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes((WT/rel).read_bytes())
diff=''.join(''.join(difflib.unified_diff([], (WT/rel).read_text(encoding='utf-8').splitlines(keepends=True),fromfile='/dev/null',tofile='b/'+rel)) for rel in OWN).encode('utf-8')
(HERE/'pm-full.diff').write_bytes(diff)
frontier=json.loads((KEY/'evidence/implementation/s2-frontier-pre-dispatch-20261026/mirror-inventory.json').read_text(encoding='utf-8'))
base={p:m['sha256'] for p,m in frontier.items()}
drift=sorted(p for p in set(base)|set(after) if base.get(p)!=after.get(p))
outside=[p for p in drift if p not in FRONTIER]
assert len(outside)==14 and all(p.endswith('.pyc') for p in outside)
for rel in outside:
    p=HERE/'out-of-face-bytes'/rel
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes((WT/rel).read_bytes())
result={'observed_at':datetime.now(timezone.utc).isoformat(),'commands':commands,'files':files,'imports':imports,'function_lines':functions,'baseline_files':len(base),'before_files':len(before),'after_files':len(after),'verification_net_changes':[],'drift_from_frontier':drift,'out_of_face_drift':outside,'out_of_face_bytes_saved':True,'pyc_attribution':'existence independently observed; T08 self-report, not exclusive process authorship','pm_diff_bytes':len(diff),'pm_diff_sha256':sha(diff),'semantic_handoff_verified':False,'full_live_or_historical_no_write_audit':False}
save('check.json',result)
print(json.dumps(result,ensure_ascii=False,indent=2))
