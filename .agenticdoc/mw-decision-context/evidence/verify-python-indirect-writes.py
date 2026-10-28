"""Read-only reconstruction of two r2 indirect writes from archived snapshots."""
import ast
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[3]
evidence = root / '.agenticdoc/mw-decision-context/workers/dc-t08-python-integration-r2/evidence'

def literal_assignments(script):
    values = {}
    for node in ast.parse(script).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {'old', 'new', 'REMOVE', 'NEW'}:
                    values[target.id] = ast.literal_eval(node.value)
    return values

rows = []
for filename, script in [('decision_dashboard.js', 'patch_dashboard_js.py'), ('test_decide_sign_auto.py', 'rewrite_sign_auto_tests.py')]:
    before = (evidence / 'snapshot/files' / filename).read_bytes()
    text = before.decode('utf-8')
    values = literal_assignments((evidence / script).read_text(encoding='utf-8'))
    if filename.endswith('.js'):
        assert text.count(values['old']) == 1
        text = text.replace(values['old'], values['new'], 1)
    else:
        for name in values['REMOVE']:
            start = text.index(f'\ndef {name}(') + 1
            match = re.search(r'\n(?=(?:def |# -{10,}))', text[start:])
            end = len(text) if match is None else start + match.start() + 1
            text = text[:start] + text[end:]
        text = text.rstrip('\n') + '\n' + values['NEW']
    # Archived scripts used Path.write_text on Windows with default newline.
    reconstructed = text.replace('\n', '\r\n').encode('utf-8')
    actual = (root / 'packages/multi-workers' / filename).read_bytes()
    row = {'path': f'packages/multi-workers/{filename}', 'actor_script': script,
           'before_sha256': hashlib.sha256(before).hexdigest(), 'before_bytes': len(before),
           'after_sha256': hashlib.sha256(actual).hexdigest(), 'after_bytes': len(actual),
           'reconstructed_matches_actual': reconstructed == actual,
           'lf_reconstruction_matches': text.encode('utf-8') == actual}
    rows.append(row)
result = {'utc': datetime.now(timezone.utc).isoformat(), 'method': 'AST literal extraction, archived rewrite replay in memory, no source writes', 'rows': rows}
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if all(row['reconstructed_matches_actual'] or row['lf_reconstruction_matches'] for row in rows) else 1)
