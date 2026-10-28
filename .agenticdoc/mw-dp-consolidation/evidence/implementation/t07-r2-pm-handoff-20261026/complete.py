"""Preserve initial verifier failure and generate corrected fresh completion runner."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
assert sys.dont_write_bytecode
(HERE/'first-check-failure.md').write_text('Initial check.py exited 1 before any tests: before-bytes uses packages__multi-workers__<name>, not basename. Directory read confirmed actual files; no product failure. Initial script/inventory retained; fresh completion below changes only evidence coordinates.\n',encoding='utf-8')
text=(HERE/'check.py').read_text(encoding='utf-8')
text=text.replace("KEY=HERE.parents[2];", "KEY=HERE.parents[3];")
text=text.replace("(WORKER/'before-bytes'/name)","(WORKER/'before-bytes'/rel.replace('/','__'))")
text=text.replace("str(HERE/'bootstrap.py')","str(HERE.parent/'bootstrap.py')").replace("str(HERE/'probe.py')","str(HERE.parent/'probe.py')").replace("(HERE/'probe.json')","(HERE.parent/'probe.json')")
out=HERE/'completion';out.mkdir(exist_ok=True)
(out/'check.py').write_text(text,encoding='utf-8',newline='\n')
print(out/'check.py')
