import json
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path('packages/multi-workers').resolve()))
import decision_history
snapshot = decision_history.load_history(pathlib.Path.cwd())
for record in snapshot.records:
    if record.task_key != 'dc-dag-acceptance-20261023':
        continue
    public = record.as_dict(detail=True)
    wb = public.get('workbench', {})
    print(json.dumps({
        'opaque_id': public.get('opaque_id'),
        'decision_id': public.get('decision_id'),
        'task_key': public.get('task_key'),
        'workbench': wb,
    }, ensure_ascii=False, indent=2))
