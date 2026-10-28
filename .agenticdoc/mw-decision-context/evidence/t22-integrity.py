from pathlib import Path
import difflib,hashlib,json
root=Path(__file__).resolve().parents[3]
out=root/'.agenticdoc/mw-decision-context/evidence'
manifest=json.loads((out/'t22-baseline/manifest.json').read_text(encoding='utf-8'))
rows=[]
for item in manifest:
 path=item['path'];before=(out/'t22-baseline'/path).read_bytes();after=(root/path).read_bytes()
 assert hashlib.sha256(before).hexdigest()==item['sha256']
 assert bool(before.count(b'\r\n'))==bool(after.count(b'\r\n')),path
 assert after.count(b'\n')==after.count(b'\r\n') if item['crlf'] else b'\r' not in after,path
 diff=''.join(difflib.unified_diff(before.decode('utf-8').splitlines(keepends=True),after.decode('utf-8').splitlines(keepends=True),fromfile=path+'.t22-before',tofile=path,n=3))
 (out/('t22-'+Path(path).name+'.diff')).write_text(diff,encoding='utf-8',newline='')
 rows.append(dict(path=path,before_bytes=len(before),after_bytes=len(after),after_sha256=hashlib.sha256(after).hexdigest(),before_crlf=item['crlf'],after_crlf=after.count(b'\r\n'),diff_hunks=sum(line.startswith('@@') for line in diff.splitlines())))
result=dict(scope='Eight source baselines, UTF-8 diff artifacts and newline assertions; not a claim about every foreign file across the whole session',files=rows)
(out/'t22-source-integrity.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
