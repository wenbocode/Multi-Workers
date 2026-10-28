from pathlib import Path
path=Path(__file__).resolve().parents[3]/'packages/multi-workers/mw.py'
body=path.read_bytes();old=b'unknown = [name for name in raw if name not in decision_lifecycle.META_KEYS]';new=old.replace(b'META_KEYS',b'META_ALLOWED_KEYS')
assert body.count(old)==1
path.write_bytes(body.replace(old,new,1))
