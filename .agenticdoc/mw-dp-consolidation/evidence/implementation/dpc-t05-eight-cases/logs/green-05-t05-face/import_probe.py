import hashlib, importlib.util, json, pathlib, sys
sys.path.insert(0, sys.argv[1])
out = {}
for name in ("decision_lifecycle", "decision_task_state", "decision_wire", "decision_book", "decision_points"):
    spec = importlib.util.find_spec(name)
    origin = pathlib.Path(spec.origin).resolve()
    out[name] = {
        "imported_from": str(origin),
        "sha256": hashlib.sha256(origin.read_bytes()).hexdigest(),
    }
print(json.dumps(out, indent=2))
