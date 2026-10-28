from pathlib import Path
import json,os,subprocess,sys,tempfile
root=Path(__file__).resolve().parents[3]
out=root/'.agenticdoc/mw-decision-context/evidence/t22-typecheck'
if len(sys.argv)>1:out=out/sys.argv[1]
out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='t22-types-home-') as home:
 env=os.environ.copy()
 for key in list(env):
  if any(part in key.upper() for part in ('API_KEY','TOKEN','SECRET','PASSWORD')) or key.upper() in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','TIMI_BASE_URL','PI_WORKER_TASK'):env.pop(key,None)
 env.update(HOME=home,USERPROFILE=home,PI_CODING_AGENT_DIR=str(Path(home)/'agent'),NO_COLOR='1')
 command=['node','node_modules/@typescript/native-preview/bin/tsgo.js','--noEmit']
 result=subprocess.run(command,cwd=root,env=env,capture_output=True,timeout=180)
 (out/'stdout.log').write_bytes(result.stdout);(out/'stderr.log').write_bytes(result.stderr)
 (out/'metadata.json').write_text(json.dumps(dict(argv=command,exit=result.returncode,scope='standalone noEmit, not downstream full-check pass'),indent=2),encoding='utf-8')
 sys.stdout.buffer.write(result.stdout);sys.stderr.buffer.write(result.stderr)
sys.exit(result.returncode)
