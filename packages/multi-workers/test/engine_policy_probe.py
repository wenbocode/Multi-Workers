"""Hermetic TS/Python policy probe; receives a temporary control root on stdin."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import mw_common
from autopilot import dispatch
from autopilot import write_face


def main() -> None:
    data = json.load(sys.stdin)
    control = pathlib.Path(data["control"])
    try:
        config = mw_common.load_target_config(control, env={})
    except mw_common.TargetConfigError as exc:
        print(json.dumps({"error": exc.kind}))
        return
    allowed = dispatch.write_face_read_only_allowed_roots(config)
    faces = []
    for entry in data.get("entries", []):
        result = dispatch.parse_workspace_write_face(control, "write_face: " + entry, config)
        faces.append(result.code if isinstance(result, write_face.Refused) else "declared")
    print(json.dumps({
        "writable": config.get("engine_writable", False),
        "lines": mw_common.dual_engine_policy_lines(config),
        "profile": mw_common.render_dual_profile_md(config),
        "artifact_roots": allowed,
        "faces": faces,
    }))


if __name__ == "__main__":
    main()
