from pathlib import Path
import datetime,json,os,subprocess,sys,tempfile
root=Path(__file__).resolve().parents[3]
out=root/'.agenticdoc/mw-decision-context/evidence/t22-ts'
out.mkdir(exist_ok=True)
label=sys.argv[1]
files=sys.argv[2:] or ['test/suite/decision-task-state.test.ts']
results=[]
with tempfile.TemporaryDirectory(prefix='t22-ts-home-') as home:
 env=os.environ.copy()
 for key in list(env):
  if any(part in key.upper() for part in ('API_KEY','TOKEN','SECRET','PASSWORD')) or key.upper() in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','TIMI_BASE_URL','PI_WORKER_TASK'):env.pop(key,None)
 env.update(HOME=home,USERPROFILE=home,PI_CODING_AGENT_DIR=str(Path(home)/'agent'),NO_COLOR='1')
 for index,file in enumerate(files):
  command=['node','../../node_modules/vitest/dist/cli.js','--run',file]
  started=datetime.datetime.now(datetime.timezone.utc).isoformat()
  result=subprocess.run(command,cwd=root/'packages/coding-agent',env=env,capture_output=True,timeout=180)
  (out/f'{label}-{index}.stdout.log').write_bytes(result.stdout);(out/f'{label}-{index}.stderr.log').write_bytes(result.stderr)
  results.append(dict(argv=command,exit=result.returncode,utc_start=started,utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat()))
  sys.stdout.buffer.write(result.stdout);sys.stderr.buffer.write(result.stderr)
(out/f'{label}-metadata.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
sys.exit(int(any(row['exit'] for row in results)))
