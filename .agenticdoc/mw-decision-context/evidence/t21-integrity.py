from pathlib import Path
import difflib,hashlib,json,re,sys
root=Path(__file__).resolve().parents[3]
evidence=root/'.agenticdoc/mw-decision-context/evidence'
before=(evidence/'t21-baseline-decision_dashboard.js').read_bytes()
after=(root/'packages/multi-workers/decision_dashboard.js').read_bytes()
assert hashlib.sha256(before).hexdigest()=='f7e2e19ee35eaa3e01ad2abf0c64d4585fddaae1f9b39d4650a93eaab5dbb90b'
assert before.count(b'\r\n')==after.count(b'\r\n')==0
old=before.decode('utf-8').splitlines(keepends=True)
new=after.decode('utf-8').splitlines(keepends=True)
(evidence/'t21-decision_dashboard.js.diff').write_bytes(''.join(difflib.unified_diff(old,new,fromfile='T21 baseline',tofile='T21 source')).encode('utf-8'))
regions=[dict(operation=tag,before_lines=[i1+1,i2],after_lines=[j1+1,j2]) for tag,i1,i2,j1,j2 in difflib.SequenceMatcher(None,old,new,autojunk=False).get_opcodes() if tag!='equal']
source=after.decode('utf-8')
block=source.split('    const explanations = {',1)[1].split('    };',1)[0]
keys={json.loads(m.group(1)) for m in re.finditer(r'^\s*("[^"\n]+"):',block,re.MULTILINE)}
sys.path.insert(0,str(root/'packages/multi-workers'))
import decision_history
record=decision_history.load_history(root).detail('h-883f5768718d808aaea8')
assert record is not None
coverage=[]
for node in record.workbench.nodes:
 detail=node.detail or {}
 basis=list(detail.get('basis',[]))+list((detail.get('policy_result') or {}).get('basis',[]))
 unknown=[value for value in basis if value not in keys]
 coverage.append(dict(node=node.id,recorded_sources=len(basis),mapped_sources=len(basis)-len(unknown)))
 assert not unknown,node.id
meta=dict(baseline_sha256=hashlib.sha256(before).hexdigest(),source_sha256=hashlib.sha256(after).hexdigest(),baseline_bytes=len(before),source_bytes=len(after),baseline_crlf=0,source_crlf=0,diff_regions=regions,actual_record_provenance_coverage=coverage,test_sha256=hashlib.sha256((root/'packages/multi-workers/test_decision_history_basis_ui.py').read_bytes()).hexdigest(),scope='baseline diff and LF integrity; reader-generated target provenance only, no stored free text or credentials')
(evidence/'t21-source-integrity.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
print(json.dumps(meta,indent=2))
