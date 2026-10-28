"""Reproduce the write-face carrier that the dispatched task.md actually declares.

Read-only diagnosis (no product writes). It runs the *shipped* dispatch extractor
on the card's ``## 写入允许面`` section and the *shipped* parser on the task.md
head, so the mismatch below is not an opinion about the contract: it is the same
two functions the dispatcher and the worker guard use.
"""

from __future__ import annotations

import json
import pathlib
import sys

EVIDENCE = pathlib.Path(__file__).resolve().parents[1]
KEY_ROOT = EVIDENCE.parents[3]  # .agenticdoc/mw-dp-consolidation
COPY_ROOT = KEY_ROOT / "implementation-worktree"
PKG = COPY_ROOT / "packages" / "multi-workers"
KEY = KEY_ROOT.name
CARD = KEY_ROOT / "tasks" / "isolated" / "T05-eight-cases-r2.md"
TASK = KEY_ROOT / "workers" / "dpc-t05-eight-cases-r2" / "task.md"

sys.path.insert(0, str(PKG))

import autopilot.dispatch as dispatch  # noqa: E402
import autopilot.write_face as write_face  # noqa: E402


def frontmatter_entries(text: str) -> list[str]:
    """The card's own ``write_face:`` frontmatter list (the card's stated face)."""
    lines = text.splitlines()
    if lines[0].strip() != "---":
        return []
    entries: list[str] = []
    in_face = False
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("write_face:"):
            in_face = True
            rest = line.split(":", 1)[1].strip()
            if rest and rest != "-":
                entries.append(rest)
            continue
        if in_face:
            if line.startswith((" ", "\t")) and line.strip().startswith("-"):
                entries.append(line.strip()[1:].strip())
                continue
            break
    return entries


def section_body(text: str, title: str) -> str:
    """Body of one ``## <title>`` card section (up to the next ``## ``)."""
    lines = text.splitlines()
    collected: list[str] = []
    active = False
    for line in lines:
        if line.startswith("## "):
            active = line[3:].strip() == title
            continue
        if active:
            collected.append(line)
    return "\n".join(collected).strip()


def task_head(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("write_face:"):
            return line.split(":", 1)[1].strip()
    return ""


def previous_card_control() -> dict:
    """The原 T05 card: its section is a bullet list, so its head carried 12 entries.

    Same extractor, same renderer, same dispatcher: only the card body changed.
    """
    card = KEY_ROOT / "tasks" / "isolated" / "T05-eight-cases.md"
    task = KEY_ROOT / "workers" / "dpc-t05-eight-cases" / "task.md"
    body = section_body(card.read_text(encoding="utf-8"), "写入允许面")
    entries = dispatch._card_write_face_entries(
        {"extras": [{"title": "写入允许面", "body": body}]}
    ) or []
    head = task_head(task.read_text(encoding="utf-8"))
    return {
        "card": str(card),
        "task": str(task),
        "extracted_entry_count": len(entries),
        "extracted_entries": entries,
        "rendered_head_entry_count": len(write_face._split_single_line(head)),
        "head_is_the_extracted_list": write_face._split_single_line(head) == entries,
    }


def main() -> int:
    card_text = CARD.read_text(encoding="utf-8")
    task_text = TASK.read_text(encoding="utf-8")

    stated = frontmatter_entries(card_text)
    body = section_body(card_text, "写入允许面")
    # The dispatcher reads the SECTION body, never the frontmatter list.
    extracted = dispatch._card_write_face_entries(
        {"extras": [{"title": "写入允许面", "body": body}]}
    )
    head = task_head(task_text)
    parsed = write_face.parse_write_face(
        "write_face: " + head,
        base=str(KEY_ROOT.parent),
        case_insensitive=(sys.platform == "win32"),
    )
    parsed_entries = (
        list(parsed.allow_entries) if isinstance(parsed, write_face.WriteFace) else []
    )

    def contained(path: str) -> bool:
        """Is the product path inside the declared face? (glob containment)."""
        for entry in parsed_entries:
            prefix = entry[:-3] if entry.endswith("/**") else entry
            if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
                return True
        return False

    products = [row.strip() for row in stated if row]
    rows = [
        {
            "path": path,
            "in_frontmatter": True,
            "in_dispatched_head": contained(path),
        }
        for path in products
    ]
    payload = {
        "source": "agent-report",
        "card": str(CARD),
        "task": str(TASK),
        "card_frontmatter_entry_count": len(stated),
        "card_frontmatter_entries": stated,
        "card_section_body": body,
        "dispatcher_extracted_entries": extracted,
        "task_md_write_face_head": head,
        "parsed_head_kind": type(parsed).__name__,
        "parsed_head_entries": parsed_entries,
        "products_outside_dispatched_face": [
            row["path"] for row in rows if not row["in_dispatched_head"]
        ],
        "product_rows": rows,
        "previous_card_control": previous_card_control(),
        "conclusion": (
            "the card's ## 写入允许面 body lists only the evidence glob, so the "
            "dispatched task.md head does not contain the eleven product paths the "
            "card frontmatter declares; the runtime write-scope guard therefore "
            "refuses every product edit"
        ),
    }
    (EVIDENCE / "blocker").mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "blocker" / "face-mismatch.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in payload.items() if k != "product_rows"}, ensure_ascii=False, indent=2))
    print("products outside the dispatched face:", len(payload["products_outside_dispatched_face"]), "/", len(products))
    return 0


if __name__ == "__main__":
    sys.exit(main())
