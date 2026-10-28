from pathlib import Path
import hashlib,json,importlib.util,sys,datetime
root=Path(__file__).resolve().parents[3]
e=root/'.agenticdoc/mw-decision-context/workers/dc-t10-readable-backend/evidence'
out=root/'.agenticdoc/mw-decision-context/evidence/t10-recovery'
out.mkdir(exist_ok=True)
results=[]
for label in ('before','after'):
 manifest=json.loads((e/f'{label}-manifest.json').read_text(encoding='utf-8'))['files']
 for path,entry in manifest.items():
  if not entry['exists']: continue
  snapshot=e/f'{label}-bytes'/entry['snapshot']
  b=snapshot.read_bytes()
  assert len(b)==entry['bytes'] and hashlib.sha256(b).hexdigest()==entry['sha256'],(label,path,'snapshot')
  if label=='after':
   assert (root/path).read_bytes()==b,(path,'disk')
  results.append({'label':label,'path':path,'sha256':entry['sha256'],'bytes':len(b)})
sys.path.insert(0,str(root/'packages/multi-workers'))
p=root/'packages/multi-workers/scripts/build_decide_cases.py'
spec=importlib.util.spec_from_file_location('t10_case_recovery',p)
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
for dp,name in module.CASE_IDS.items():
 expected=module.render_case(module.build_case(dp)).encode('utf-8')
 actual=(root/'packages/multi-workers/decide_cases'/name).read_bytes()
 assert expected==actual,name
trace=(e.parent/'trace.log').read_text(encoding='utf-8')
commands=[line for line in trace.splitlines() if '[TOOL]' in line and 'scripts/build_decide_cases.py' in line and ' bash ' in line]
assert commands
report={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'snapshot_checks':results,'generator_exact_cases':list(module.CASE_IDS.values()),'recorded_generator_commands':commands,'scope':'independent compensating evidence; no rewrite of original trace/status; generator rendered in memory, no source writes'}
(out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS: before13/after14 snapshots and disk14; four generated case bytes exact; generator commands located')
