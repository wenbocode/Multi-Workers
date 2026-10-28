"""Read-only PM verification of terminal hashes and final test log totals."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import re
import json

root = Path(__file__).resolve().parents[3]
base = root / '.agenticdoc/mw-decision-context/workers'
results = {'utc': datetime.now(timezone.utc).isoformat(), 'hash_checks': [], 'test_logs': []}
for task, rel in [('dc-t08-ts-integration-r2', 'evidence/final-hashes.txt'), ('dc-t08-python-integration-r2', 'evidence/sha256_final.txt')]:
    text = (base/task/rel).read_text(encoding='utf-8-sig')
    for line in text.splitlines():
        m = re.fullmatch(r'([A-Fa-f0-9]{64})\s+(\d+)\s+(packages/.*)', line.strip())
        if not m:
            if line.strip():
                results['hash_checks'].append({'task':task,'unparsed':line})
            continue
        expected, size, name = m.groups()
        data = (root/name).read_bytes()
        results['hash_checks'].append({'task':task,'path':name,'matches':hashlib.sha256(data).hexdigest().lower()==expected.lower() and len(data)==int(size)})
for task, pattern in [('dc-t08-ts-integration-r2','evidence/green-*.log'),('dc-t08-python-integration-r2','evidence/inventory/final/*.log')]:
    for path in sorted((base/task).glob(pattern)):
        text = path.read_text(encoding='utf-8-sig')
        counts = re.findall(r'(\d+) passed', text)
        results['test_logs'].append({'task':task,'path':str(path.relative_to(root)),'passed':int(counts[-1]) if counts else None,'failed_summary':bool(re.search(r'\d+ failed',text))})
print(json.dumps(results, ensure_ascii=False, indent=2))
raise SystemExit(1 if any(row.get('matches') is False or 'unparsed' in row for row in results['hash_checks']) else 0)
