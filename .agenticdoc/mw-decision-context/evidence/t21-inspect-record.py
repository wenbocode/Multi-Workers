from pathlib import Path
import sys,json
root=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(root/'packages/multi-workers'))
import decision_history
record=decision_history.load_history(root).detail('h-883f5768718d808aaea8')
if record is None:
 print('not found');sys.exit(1)
public=record.as_dict(detail=True)
selected={key:public.get(key) for key in ('opaque_id','decision_id','task_key','dp','key','ts','status','workbench','redaction')}
print(json.dumps(selected,ensure_ascii=False,indent=2))
