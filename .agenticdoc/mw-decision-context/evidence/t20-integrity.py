from pathlib import Path
import difflib,hashlib,json
root=Path(__file__).resolve().parents[3]
out=root/'.agenticdoc/mw-decision-context/evidence'
rows={}
for name in ('decision_history.py','decision_dashboard.js'):
 before=(out/'t20-baseline'/name).read_bytes()
 after=(root/'packages/multi-workers'/name).read_bytes()
 delta=''.join(difflib.unified_diff(before.decode('utf-8').splitlines(keepends=True),after.decode('utf-8').splitlines(keepends=True),fromfile='t20-baseline/'+name,tofile=name))
 (out/('t20-'+name+'.diff')).write_text(delta,encoding='utf-8',newline='')
 row={'baseline_sha256':hashlib.sha256(before).hexdigest(),'current_sha256':hashlib.sha256(after).hexdigest(),'before_bytes':len(before),'after_bytes':len(after),'before_crlf':before.count(b'\r\n'),'after_crlf':after.count(b'\r\n')}
 if name=='decision_history.py':
  expected=before.replace(b'"answer": _free("receipt", "consumed.answer", row.get("answer"), sanitizer),\n',b'"answer": _free("receipt", "consumed.answer", row.get("answer"), sanitizer),\n            "reason": _free("receipt", "consumed.reason", row.get("reason"), sanitizer),\n').replace(b'"result": _free("action", "executed.result", row.get("result"), sanitizer),\n',b'"result": _free("action", "executed.result", row.get("result"), sanitizer),\n                "reason": _free("action", "executed.reason", row.get("reason"), sanitizer),\n')
  assert expected==after,'history bytes outside the two reason insertions changed'
  row['exact_two_insertion_replay']=True
 else:
  assert before.count(b'\r\n')==after.count(b'\r\n')==0
  row['utf8_lf_preserved']=True
 rows[name]=row
(out/'t20-source-integrity.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
print(json.dumps(rows,indent=2))
