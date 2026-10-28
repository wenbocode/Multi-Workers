"""Fresh assigned-only T06/T07 check before PM handoff recording."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[1];WT=KEY/'implementation-worktree';PKG=WT/'packages/multi-workers'
OUT=HERE/'s2-r2-fresh-recheck-20261027';assert not OUT.exists();OUT.mkdir()
def inventory():return {p.relative_to(WT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in WT.rglob('*') if p.is_file()}
before=inventory();env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT') if k in os.environ}
for name in ('HOME','USERPROFILE','TEMP','TMP','TMPDIR','APPDATA','LOCALAPPDATA','PROJECT_ROOT'):
    p=OUT/'fixture'/name.lower();p.mkdir(parents=True);env[name]=str(p)
env.update({'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','PYTHONNOUSERSITE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'})
rows=[]
for key,file,count in [('T06','test_dp_consolidation_concurrency.py',73),('T07','test_dp_consolidation_recovery.py',35)]:
    argv=[sys.executable,'-B','-m','pytest','-p','no:cacheprovider','-q',file]
    r=subprocess.run(argv,cwd=PKG,env=env,capture_output=True)
    (OUT/(key+'.stdout')).write_bytes(r.stdout);(OUT/(key+'.stderr')).write_bytes(r.stderr)
    print(key,'rc=',r.returncode);print(r.stdout.decode('utf-8'));print(r.stderr.decode('utf-8'))
    rows.append({'task':key,'argv':argv,'rc':r.returncode,'expected_passed':count})
    assert r.returncode==0 and (str(count)+' passed').encode() in r.stdout
assert before==inventory()
result={'observed_at':datetime.now(timezone.utc).isoformat(),'source':'agent-report','commands':rows,'mirror_files':len(before),'verification_net_changes':[],'product_hashes':{p:s for p,s in before.items() if p in ('packages/multi-workers/decision_validity.py','packages/multi-workers/test_dp_consolidation_concurrency.py','packages/multi-workers/decision_policy.py','packages/multi-workers/test_dp_consolidation_recovery.py')}}
(OUT/'check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))
