import collections, json, pathlib
root=pathlib.Path(__file__).resolve().parents[3]
for name in ('decisions.jsonl','decision-lifecycle.jsonl'):
    path=root/'.agenticdoc/_autopilot'/name
    counts=collections.Counter()
    for line in path.read_bytes().splitlines():
        try: row=json.loads(line)
        except ValueError: continue
        if str(row.get('decision_id','')).split(':',1)[0] not in ('dp1-dispatch-type','dp2-checkpoint-split','dp3-worker-clarify','dp25-signoff-conclusion'): continue
        fields=('answer','action','result','reason','answer_source','actor')
        # Shapes and presence only: never emit record text, identities or credentials.
        shape=tuple((field,type(row.get(field)).__name__,bool(row.get(field))) for field in fields)
        counts[(row.get('kind'),row.get('lifecycle'),shape)]+=1
    print(name)
    for (kind,stage,shape), count in counts.items():
        print(json.dumps({'kind':kind,'stage':stage,'fields':shape,'count':count}))
