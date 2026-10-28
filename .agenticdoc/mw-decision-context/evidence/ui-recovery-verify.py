from pathlib import Path
import os,sys,subprocess,tempfile,json,datetime
root=Path(__file__).resolve().parents[3]
out=root/'.agenticdoc/mw-decision-context/evidence/ui-recovery'
label=sys.argv[1]
files=sys.argv[2:] or ['test_decision_dashboard_assets.py','test_decision_context_workbench.py','test_decision_dashboard_contracts.py','test_decision_context_readable_ui.py']
results=[]
with tempfile.TemporaryDirectory(prefix='dc-ui-pm-') as home:
 env=os.environ.copy()
 for k in list(env):
  if any(s in k.upper() for s in ('API_KEY','TOKEN','SECRET','PASSWORD')) or k.upper() in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','TIMI_BASE_URL','PI_WORKER_TASK'):
   env.pop(k,None)
 env.update(HOME=home,USERPROFILE=home,PI_CODING_AGENT_DIR=str(Path(home)/'agent'),PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
 for file in files:
  cmd=[sys.executable,'-X','utf8','-m','pytest','-q',str(root/'packages/multi-workers'/file)]
  started=datetime.datetime.now(datetime.timezone.utc).isoformat()
  r=subprocess.run(cmd,cwd=root,env=env,capture_output=True,timeout=360)
  ended=datetime.datetime.now(datetime.timezone.utc).isoformat()
  name=file.split('::')[0].removesuffix('.py')
  (out/f'{label}-{name}.stdout.log').write_bytes(r.stdout)
  (out/f'{label}-{name}.stderr.log').write_bytes(r.stderr)
  row=dict(argv=cmd,cwd=str(root),utc_start=started,utc_end=ended,exit=r.returncode)
  results.append(row)
  print(file,r.returncode,r.stdout.decode('utf-8',errors='replace')[-2200:])
(out/f'{label}-metadata.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
sys.exit(int(any(r['exit'] for r in results)))
