from pathlib import Path
import json,re
root=Path(__file__).resolve().parents[3]
target='dp1-dispatch-type:a489216a-d9a4-4f3c-a7d5-6fe41e5ca3ee'
allowed={'consumed','executed','settled','start','record-start','lifecycle','research','record','answer-returned','association-bridge','dispatch-refused','rework','ok','pm'}
for number,line in enumerate((root/'.agenticdoc/_autopilot/decision-lifecycle.jsonl').read_bytes().splitlines(),1):
 try: row=json.loads(line)
 except ValueError: continue
 if row.get('decision_id')!=target: continue
 safe={'line':number}
 for key in ('stage','lifecycle','kind','answer','action','result','outcome','reason','initiator_role'):
  value=row.get(key)
  safe[key]=value if isinstance(value,str) and value in allowed else ('missing' if value is None else 'withheld')
 ts=row.get('ts')
 safe['ts']=ts if isinstance(ts,str) and re.fullmatch(r'[0-9T:.+Z-]+',ts) else 'withheld'
 print(json.dumps(safe,ensure_ascii=False))
