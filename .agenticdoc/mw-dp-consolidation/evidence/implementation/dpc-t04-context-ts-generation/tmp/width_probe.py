import json
import unicodedata
from pathlib import Path

doc = json.loads(
    (
        Path(r"H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\implementation-worktree\packages\multi-workers\decide_registry.json")
    ).read_text(encoding="utf-8")
)


def wide(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in ("W", "F") else 1 for char in text)


rows = []
for record in doc["retired"]:
    for key in ("description", "note"):
        line = '\t\t%s: "%s",' % (key, record[key])
        rows.append((wide(line), len(line), record["id"], key))
rows.sort()
for row in rows[-6:]:
    print(row)
print("max wide/len:", rows[-1][0], rows[-1][1])

prep = doc["preparation"]
for key, value in (
    ("keys", ", ".join('"%s"' % item for item in prep["keys"])),
    ("basisItemKeys", ", ".join('"%s"' % item for item in prep["basis_item_keys"])),
    ("basisSource", '"%s"' % prep["basis_source"]),
    ("independentOf", '"%s"' % prep["independent_of"]),
    ("basisStateField", '"preparation.basis_catalog"'),
):
    line = "\t%s: %s," % (key, value)
    print(wide(line), line)
print("types:")
for line in (
    'export type DecideRegistryEntryKind = "fixed" | "dynamic-candidates" | "route-targets";',
    'export type DecideRegistryRoleScope = "pm" | "worker";',
):
    print(wide(line), line)
