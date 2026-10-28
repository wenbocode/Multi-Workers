from pathlib import Path
import sys,json
root=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(root/'packages/multi-workers'))
import decision_history
record=decision_history.load_history(root).detail('h-883f5768718d808aaea8')
assert record is not None
# Reader-generated provenance only; no stored answers/reasons/materials/captures or credentials.
for node in record.workbench.nodes:
 detail=node.detail or {}
 policy=detail.get('policy_result') or {}
 print(json.dumps({'node':node.id,'basis':detail.get('basis',[]),'policy_basis':policy.get('basis',[]),'recorded_confidence':policy.get('confidence') if isinstance(policy.get('confidence'),(int,float)) else None,'recorded_threshold':policy.get('min_confidence') if isinstance(policy.get('min_confidence'),(int,float)) else None},ensure_ascii=False))
