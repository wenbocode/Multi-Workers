from pathlib import Path
import difflib,hashlib,json
root=Path(__file__).resolve().parents[3]
out=root/'.agenticdoc/mw-decision-context/evidence'
rows={}
for name in ('decision_monitor.py','test_decision_dashboard_playground.py'):
 before=(out/'t20-startup-baseline'/name).read_bytes()
 after=(root/'packages/multi-workers'/name).read_bytes()
 row={'baseline_sha256':hashlib.sha256(before).hexdigest(),'current_sha256':hashlib.sha256(after).hexdigest(),'before_bytes':len(before),'after_bytes':len(after),'before_crlf':before.count(b'\r\n'),'after_crlf':after.count(b'\r\n')}
 if name=='decision_monitor.py':
  start=b'from __future__ import annotations'
  deps=b'@dataclasses.dataclass\nclass MonitorDeps:'
  instance=b'class MonitorInstance:'
  method=b'    def start(self) -> "MonitorInstance":'
  stop=b'    def stop(self) -> None:'
  assert before[before.index(start):before.index(deps)]==after[after.index(start):after.index(deps)]
  assert before[before.index(instance):before.index(method)]==after[after.index(instance):after.index(method)]
  assert before[before.index(stop,before.index(method)):]==after[after.index(stop,after.index(method)):]
  row['unchanged_outside_intro_deps_factory_start']=True
  row['http_body_rejection_region_byte_exact']=True
 else:
  start=b'from __future__ import annotations'
  method=b'def test_the_command_path_wiring_serves_the_whole_dp_flow'
  following=b'def test_dps_route_lists_all_25_typed_contracts_without_a_provider'
  prefix=after[after.index(start):after.index(method)].replace(b'import socket\n',b'')
  assert before[before.index(start):before.index(method)]==prefix
  assert before[before.index(following):]==after[after.index(following):]
  row['unchanged_outside_intro_socket_import_default_path_test']=True
 assert before.count(b'\r\n')==after.count(b'\r\n')==0
 delta=''.join(difflib.unified_diff(before.decode('utf-8').splitlines(keepends=True),after.decode('utf-8').splitlines(keepends=True),fromfile='t20-startup-baseline/'+name,tofile=name))
 (out/('t20-startup-'+name+'.diff')).write_text(delta,encoding='utf-8',newline='')
 rows[name]=row
 new=root/'packages/multi-workers/test_decision_monitor_history_redactor.py'
rows['test_decision_monitor_history_redactor.py']={'new_file_sha256':hashlib.sha256(new.read_bytes()).hexdigest()}
(out/'t20-startup-source-integrity.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
print(json.dumps(rows,indent=2))
