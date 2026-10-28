from pathlib import Path
root=Path(__file__).resolve().parent
original=(root/'t20-startup-protected-check.py').read_bytes()
assert b't20-startup-check' in original
(root/'t22-protected-check.py').write_bytes(original.replace(b't20-startup-check',b't22-check'))
(root/'t22-protected-check-final.py').write_bytes(original.replace(b't20-startup-check',b't22-check-final'))
