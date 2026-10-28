from pathlib import Path
import datetime,hashlib,json,os,subprocess,sys,tempfile
root=Path(__file__).resolve().parents[3]
source=root/'packages/multi-workers'
out=root/'.agenticdoc/mw-decision-context/evidence/t21-workbench-compare'
out.mkdir(exist_ok=True)
results=[]
original=hashlib.sha256((source/'decision_dashboard.js').read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix='t21-workbench-compare-') as temp:
 for label in ('baseline','current'):
  work=Path(temp)/label/'packages/multi-workers'
  work.mkdir(parents=True)
  for path in source.rglob('*'):
   if not path.is_file() or '__pycache__' in path.parts or '.pytest_cache' in path.parts: continue
   relative=path.relative_to(source)
   if path.suffix!='.py' and not (len(relative.parts)==1 and path.suffix in ('.html','.css','.js')) and relative.parts[0]!='decide_cases': continue
   destination=work/relative
   destination.parent.mkdir(parents=True,exist_ok=True)
   destination.write_bytes(path.read_bytes())
  if label=='baseline':
   (work/'decision_dashboard.js').write_bytes((out.parent/'t21-baseline-decision_dashboard.js').read_bytes())
  env=os.environ.copy()
  for key in list(env):
   if any(part in key.upper() for part in ('API_KEY','TOKEN','SECRET','PASSWORD')) or key.upper() in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','TIMI_BASE_URL','PI_WORKER_TASK'): env.pop(key,None)
  home=Path(temp)/(label+'-home'); home.mkdir()
  env.update(HOME=str(home),USERPROFILE=str(home),PI_CODING_AGENT_DIR=str(home/'agent'),PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
  cmd=[sys.executable,'-X','utf8','-m','pytest','-q',str(work/'test_decision_context_workbench.py')+'::test_dom_v2_record_opens_ten_node_dag_and_legacy_record_stays_log_only']
  started=datetime.datetime.now(datetime.timezone.utc).isoformat()
  result=subprocess.run(cmd,cwd=work,env=env,capture_output=True,timeout=120)
  (out/(label+'.stdout.log')).write_bytes(result.stdout)
  (out/(label+'.stderr.log')).write_bytes(result.stderr)
  results.append(dict(label=label,argv=cmd,exit=result.returncode,utc_start=started,utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat()))
  sys.stdout.buffer.write(result.stdout)
assert original==hashlib.sha256((source/'decision_dashboard.js').read_bytes()).hexdigest()
(out/'metadata.json').write_text(json.dumps(dict(results=results,source_unchanged=True),indent=2),encoding='utf-8')
