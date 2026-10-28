"""Isolate the artifact delta introduced by the new ``empty_is_value`` metadata.

Checks (1) the checked-in JSON equals the export writer's document (wiring
merged), (2) exactly one field carries the flag, (3) the TS bytes equal a fresh
generator render, and (4) the render *without* the flag differs only inside the
``p0_open`` field block (written to ``registry-without-flag.generated.ts``).
"""

from __future__ import annotations

import copy
import difflib
import json
import pathlib
import sys

MW = pathlib.Path("packages/multi-workers").resolve()
sys.path.insert(0, str(MW))
sys.path.insert(0, str(MW / "scripts"))

import decision_points as dpts  # noqa: E402
import gen_decide_registry_ts as gen  # noqa: E402
import mw  # noqa: E402

out = pathlib.Path(
    ".agenticdoc/mw-decision-dashboard/evidence/runs/T05h-dp25-empty-value"
).resolve()

current_json_text = (MW / "decide_registry.json").read_text(encoding="utf-8")
current_json = json.loads(current_json_text)
writer_doc, missing, error = mw._dp_export_doc()

flagged = [
    f"{point['id']}/{field['name']}"
    for point in current_json["points"]
    for field in point["required_state_fields"] + point["optional_state_fields"]
    if "empty_is_value" in field
]
p0 = [
    field
    for point in current_json["points"]
    if point["id"] == "dp25-signoff-conclusion"
    for field in point["required_state_fields"]
    if field["name"] == "p0_open"
][0]

snapshot = dpts.registry_snapshot()
stripped = copy.deepcopy(snapshot)
for point in stripped["points"]:
    for field in point["required_state_fields"] + point["optional_state_fields"]:
        field.pop("empty_is_value", None)
without_ts = gen.render(stripped)
current_ts = gen.output_path().read_text(encoding="utf-8")
(out / "registry-without-flag.generated.ts").write_text(
    without_ts, encoding="utf-8", newline="\n"
)
ts_diff = [
    line
    for line in difflib.unified_diff(
        without_ts.splitlines(), current_ts.splitlines(), "without-flag", "current", lineterm="", n=0
    )
]

print("flagged fields:", flagged)
print("p0_open export:", json.dumps(p0, ensure_ascii=False, sort_keys=True))
print("checked-in json == writer doc:", current_json == writer_doc, missing, error)
print("generator render == checked-in ts:", gen.render() == current_ts)
print("ts unified diff (n=0):")
for line in ts_diff:
    print(line)
