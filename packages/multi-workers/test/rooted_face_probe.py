"""Read-only TS/Python rooted-face parity probe; JSON stdin/stdout, no providers."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from autopilot import write_face as wf


def main() -> None:
    case = json.load(sys.stdin)
    options = dict(base=case["base"], roots=case["roots"], case_insensitive=True)
    face = wf.parse_write_face("write_face:\n" + "\n".join("  - " + item for item in case["entries"]), **options)
    same = wf.parse_write_face("write_face: " + case["base"] + "/src/a.cpp", **options)
    different = wf.parse_write_face("write_face: E:/Controlo/src/a.cpp", base=case["base"], roots=["E:/Controlo"], case_insensitive=True)
    assert isinstance(face, wf.WriteFace) and isinstance(same, wf.WriteFace) and isinstance(different, wf.WriteFace)
    print(json.dumps(dict(entries=face.allow_entries, overlap=wf.is_overlap(wf.overlap(face, same)), different=wf.is_overlap(wf.overlap(face, different)))))


if __name__ == "__main__":
    main()
