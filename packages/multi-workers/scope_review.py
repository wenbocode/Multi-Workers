"""Fail-closed admission for SDD keys with a spec_goal scope contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import mw_common

REVIEW_FILE = "scope-review.json"
KEY = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
ANCHOR = re.compile(r"(?:AC|FLOW)-\d+")


def read(path: Path) -> str:
    if path.resolve() != path:
        raise ValueError(f"{path.name}: expected a key-local file")
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return ""


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def visible(markdown: str) -> str:
    lines = []
    fence = ""
    for line in re.sub(r"<!--[\s\S]*?(?:-->|$)", "", markdown).splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            if marker and marker[1].startswith(fence) and line.strip() == marker[1]:
                fence = ""
        elif marker:
            fence = marker[1]
        else:
            lines.append(line)
    return "\n".join(lines)


def section(text: str, level: int, heading: str) -> str | None:
    match = re.search(rf"^ {{0,3}}#{{{level}}}[ \t]+{heading}[ \t]*#*[ \t]*$", text, re.M)
    if match is None:
        return None
    content = text[match.end():]
    return re.split(rf"^ {{0,3}}#{{1,{level}}}[ \t]+", content, maxsplit=1, flags=re.M)[0].strip()


def approved(review: object, label: str, anchors: set[str]) -> dict:
    if not isinstance(review, dict) or review.get("verdict") != "approve":
        raise ValueError(f"{label}: scope review approval required")
    ref = review.get("anchor")
    if not isinstance(ref, str) or ref not in anchors:
        raise ValueError(f"{label}: scope review must cite an existing AC or necessary FLOW")
    if any(not isinstance(review.get(field), str) or not review[field].strip()
           for field in ("entry", "failure", "minimum")):
        raise ValueError(f"{label}: scope review must state the real entry, failure if omitted and minimum work")
    return review


class Scope:
    def __init__(self, key_dir: Path):
        self.key_dir = key_dir
        self.reviews: dict | None = None
        self.task_anchors: dict[str, set[str]] = {}
        if KEY.fullmatch(key_dir.name) is None or key_dir.name.endswith("."):
            raise ValueError("invalid key for scope review")
        spec = visible(read(key_dir / "spec.md"))
        alignment = section(spec, 2, r"(?:§0(?:[ \t]+[^\n]*)?|(?i:Goal Alignment))")
        goal = section(alignment or "", 3, "spec_goal") or ""
        file = key_dir / REVIEW_FILE
        if alignment is None and not file.exists():
            return
        labels = ("目标: ", "范围边界: ", "停止条件: ")
        lines = goal.splitlines()
        if (len(lines) != 4 or lines[0] != f"Goal ID: {key_dir.name}/GOAL-01"
                or any(not line.startswith(label) or not line[len(label):].strip()
                       for label, line in zip(labels, lines[1:]))):
            raise ValueError("spec_goal requires Goal ID, 目标, 范围边界 and 停止条件")
        if "[NEEDS-CONFIRMATION]" in goal:
            raise ValueError("resolve spec_goal clarification before proceeding")
        self.plan = read(key_dir / "plan.md")
        goal_hash, plan_hash = sha(goal), sha(self.plan)
        reviews = json.loads(read(file) or "{}")
        if (not isinstance(reviews, dict) or reviews.get("goal_sha256") != goal_hash
                or reviews.get("plan_sha256") != plan_hash):
            raise ValueError(f"{REVIEW_FILE}: review current goal_sha256={goal_hash} and plan_sha256={plan_hash}")
        design = visible(read(key_dir / "design.md"))
        paths = section(design, 3, "必要功能路径") or ""
        self.anchors = set(re.findall(
            r"^[ \t]*(?:\|\s*|[-*+]\s+|#{1,6}\s+)?`?(AC-\d+)`?(?=[ \t]*[|:：]|[ \t]|$)", spec, re.M,
        ))
        self.anchors.update(re.findall(r"^\s*\|\s*`?(FLOW-\d+)\b", paths, re.M))
        self.reviews = reviews

    def review(self, group: str, name: str, value: str | None = None) -> dict:
        items = self.reviews.get(group) if self.reviews is not None else None
        item = items.get(name) if isinstance(items, dict) else None
        label = f"{group}/{name}" + (f" (sha256={value})" if value is not None else "")
        item = approved(item, label, self.anchors)
        if value is not None and item.get("sha256") != value:
            raise ValueError(f"{label}: reviewed content changed")
        return item

    def check_plan(self) -> None:
        if self.reviews is None:
            return
        plan = visible(self.plan)
        roster = section(plan, 2, "保留任务")
        coverage = section(plan, 2, "闭环覆盖") or ""
        if not roster:
            raise ValueError("missing 保留任务 for scope review")
        task_anchors = {}
        for line in roster.splitlines():
            row = re.match(r"^\s*\|\s*`?([\w.-]+)`?\s*\|", line)
            if not row or row[1] in {"任务", "ID", "Task"} or set(row[1]) == {"-"}:
                continue
            name = row[1]
            review = self.review("plan", name)
            matching = {
                match[1] for line in coverage.splitlines()
                if (match := re.match(r"^\s*\|\s*`?((?:AC|FLOW)-\d+)`?\s*\|([^|]+)\|", line))
                and name in {part.strip(" `") for part in match[2].split(",")}
            }
            if review["anchor"] not in matching:
                raise ValueError(f"plan/{name}: scope anchor must map to this task in 闭环覆盖")
            task_anchors[Path(name).stem.casefold().removeprefix("t-")] = matching
        if not task_anchors:
            raise ValueError("scope review requires at least one retained task")
        self.task_anchors = task_anchors

    def check_card(self, ref: str, pin: str | None) -> dict:
        if not re.fullmatch(r"tasks/(?:[\w.-]+/)*[\w.-]+\.md", ref) or any(
            part in {".", ".."} for part in ref.split("/")
        ):
            raise ValueError("scope review requires a task card under tasks/")
        card = self.key_dir / ref
        exact = mw_common.sha256_eol_normalized(card) if card.resolve() == card else ""
        if not exact or (pin and pin != exact):
            raise ValueError(f"{ref}: card is unavailable or changed")
        return self.review("cards", ref, exact)


def plan_refusal(key_dir: Path) -> str | None:
    try:
        Scope(key_dir).check_plan()
    except (OSError, ValueError) as exc:
        return f"scope-review: {exc}"
    return None


if __name__ == "__main__":
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("key")
    parser.add_argument("--advance", action="store_true", help="run the checked PLAN → TASKS transition")
    args = parser.parse_args()
    if KEY.fullmatch(args.key) is None or args.key.endswith("."):
        parser.error("invalid key")
    if args.advance:
        from autopilot.advance import advance

        code, out, err = advance(args.key, "tasks", args.project.resolve())
        sys.stdout.write(out)
        sys.stderr.write(err)
        sys.exit(code)
    if refusal := plan_refusal(args.project.resolve() / ".agenticdoc" / args.key):
        parser.exit(1, refusal + "\n")
