from pathlib import Path
import os,sys,subprocess,tempfile,json,datetime
root=Path(__file__).resolve().parents[3]
out=root/'.agenticdoc/mw-decision-context/evidence/t20-startup-chunked-compare2'
out.mkdir(exist_ok=False)
rows=[]
with tempfile.TemporaryDirectory(prefix='dc-t20-chunked-') as temp:
 work=Path(temp)/'package'; work.mkdir()
 package=root/'packages/multi-workers'
 for source in package.rglob('*.py'):
  relative=source.relative_to(package)
  target=work/relative
  target.parent.mkdir(parents=True,exist_ok=True)
  target.write_bytes(source.read_bytes())
 for name in ('decide_registry.json','decide_book_template.json'):
  (work/name).write_bytes((package/name).read_bytes())
 for name in ('decision_dashboard.html','decision_dashboard.css','decision_dashboard.js'):
  (work/name).write_bytes((root/'packages/multi-workers'/name).read_bytes())
 env=os.environ.copy()
 for k in list(env):
  if any(s in k.upper() for s in ('API_KEY','TOKEN','SECRET','PASSWORD')) or k.upper() in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','TIMI_BASE_URL','PI_WORKER_TASK'):
   env.pop(k,None)
 env.update(HOME=str(Path(temp)/'home'),USERPROFILE=str(Path(temp)/'home'),PI_CODING_AGENT_DIR=str(Path(temp)/'home/agent'),PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
 for version in ('baseline','current'):
  source=root/'.agenticdoc/mw-decision-context/evidence/t20-startup-baseline/decision_monitor.py' if version=='baseline' else root/'packages/multi-workers/decision_monitor.py'
  (work/'decision_monitor.py').write_bytes(source.read_bytes())
  for attempt in range(3):
   cmd=[sys.executable,'-X','utf8','-m','pytest','-q','test_decision_monitor.py::test_body_limit_and_chunked_rejection']
   start=datetime.datetime.now(datetime.timezone.utc).isoformat()
   result=subprocess.run(cmd,cwd=work,env=env,capture_output=True,timeout=60)
   label=f'{version}-{attempt+1}'
   (out/(label+'.stdout.log')).write_bytes(result.stdout)
   (out/(label+'.stderr.log')).write_bytes(result.stderr)
   rows.append(dict(version=version,attempt=attempt+1,argv=cmd,utc_start=start,exit=result.returncode))
   print(label,result.returncode,result.stdout.decode('utf-8',errors='replace'))
   if result.returncode not in (0,1):
    (out/'collection-failure.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    sys.exit(result.returncode)
(out/'metadata.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
