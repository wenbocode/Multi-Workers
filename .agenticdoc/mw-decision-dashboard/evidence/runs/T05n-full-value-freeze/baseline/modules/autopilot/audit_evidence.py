"""audit_evidence.py — L1 mechanical evidence audit for one key (goal-autopilot T-08).

CLI::

    python autopilot/audit_evidence.py --key <key> [--project <dir>]

Emits a JSON dossier on stdout::

    {key, phase_edge, ac_list[], decision_map[{decision, evidence_files[]}],
     gaps[{item, rule, severity}], generated_at}

Exit codes: 0 = no gaps (evidence complete), 1 = gaps present.

L1 is strictly mechanical — existence and reference-closure checks only, no
semantic judgment (semantic verdicts belong to the L2 verifier). Standalone
CLI: no conductor required, no other autopilot module imported; all paths come
from explicit arguments.

Inputs (under {project}/.agenticdoc/{key}/):
- spec.md     AC checklist: `| AC-NNN | description |` table rows. Blockquote
              errata notes and prose AC mentions are not table rows and never
              enter ac_list (locked-errata format safe).
- design.md   Decision points (D-NNN): `### D-NNN` headers plus first-column
              D-NNN rows of the summary decision table (union = decision_map
              key set). Fenced code blocks are skipped when reading structure.
- evidence/   Research 留底 etc. A file maps to a decision when the decision's
              text cites it (`evidence/....md|.txt`) or when the file content
              cites the decision (D-NNN appears in it).
- pm-state.md Optional; the current `- Phase:` line becomes phase_edge
              (null when unreadable — never an error).

Gap rules:
- spec-missing (blocking)             spec.md absent.
- evidence-ref-missing (blocking)     a literal evidence/ citation in spec.md
                                      or design.md has no file; template refs
                                      containing { } * < > placeholders are
                                      skipped (not literal citations).
- research-evidence-missing (blocking) at the SPEC phase edge the framework
                                      gate requires evidence/research/spec-*.md
                                      >= 1, at the DESIGN edge
                                      evidence/research/design-*.md >= 1
                                      (mirrors advance_phase.py GATES); an
                                      empty glob = missing research 留底.
- decision-without-evidence (non-blocking) a decision maps to no evidence
                                      file; whether it needs one is semantic
                                      and deferred to L2.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

AGENTICDOC_DIR = ".agenticdoc"

_AC_ID_RE = re.compile(r"AC-\d{3}")
_DECISION_ID_RE = re.compile(r"D-\d{3}")
_DECISION_HEADER_RE = re.compile(r"^#{2,6}\s+(D-\d{3})\b")
_ANY_HEADING_RE = re.compile(r"^#{1,6}\s")
_PHASE_LINE_RE = re.compile(r"^\s*-\s*Phase:[ \t]*(\S.*?)[ \t]*$", re.MULTILINE)
# Literal `evidence/...md|txt` citations; not preceded by a path/name character
# (avoids matching nested or embedded variants) and not followed by an
# alphanumeric (avoids matching `foo.md5`).
_EVIDENCE_REF_RE = re.compile(r"(?<![0-9A-Za-z_./-])evidence/\S*?\.(?:md|txt)(?![0-9A-Za-z])")
_PLACEHOLDER_CHARS = frozenset("{}*<>")

# Current phase edge -> required research evidence glob (mirrors
# advance_phase.py GATES: entering design needs spec research 留底, entering
# plan needs design research 留底). Other edges add no new research file.
_RESEARCH_GLOBS = {
    "SPEC": "evidence/research/spec-*.md",
    "DESIGN": "evidence/research/design-*.md",
}


def _read_text(path: Path) -> str:
    """UTF-8 text of a file; empty string when unreadable (audit never crashes)."""
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def _structural_lines(text: str) -> list[str]:
    """Lines outside fenced code blocks (``` toggles); markdown structure in
    quoted example blocks is not structure of the document itself."""
    lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append(line)
    return lines


def _split_table_row(line: str) -> list[str] | None:
    """Stripped cells of a markdown table row; None for non-table lines."""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def extract_ac_list(spec_text: str) -> list[str]:
    """AC checklist from spec.md: AC-NNN table rows, document order, deduped.

    Blockquote errata notes (``> - AC-020 ...``) and prose mentions are not
    table rows and are excluded, so the locked-errata spec format parses clean.
    """
    ac_list: list[str] = []
    seen: set[str] = set()
    for line in _structural_lines(spec_text):
        cells = _split_table_row(line)
        if not cells or _AC_ID_RE.fullmatch(cells[0]) is None:
            continue
        if cells[0] in seen:
            continue
        seen.add(cells[0])
        ac_list.append(cells[0])
    return ac_list


def _extract_decisions(design_text: str) -> dict[str, str]:
    """decision_id -> text corpus (its `### D-NNN` section + summary-table row).

    The decision key set is the union of D-NNN section headers and first-column
    D-NNN rows of the summary decision table. Section text runs from the header
    to the next markdown heading; the matching summary table row is appended.
    """
    lines = _structural_lines(design_text)
    corpora: dict[str, list[str]] = {}
    index = 0
    while index < len(lines):
        header = _DECISION_HEADER_RE.match(lines[index])
        if header is None:
            index += 1
            continue
        corpus = corpora.setdefault(header.group(1), [])
        index += 1
        while index < len(lines) and _ANY_HEADING_RE.match(lines[index]) is None:
            corpus.append(lines[index])
            index += 1
    for line in lines:
        cells = _split_table_row(line)
        if cells and _DECISION_ID_RE.fullmatch(cells[0]):
            corpora.setdefault(cells[0], []).append(line)
    return {decision_id: "\n".join(parts) for decision_id, parts in corpora.items()}


def extract_evidence_refs(text: str) -> list[str]:
    """Literal `evidence/...` file citations in document order, deduped.

    Template/glob references (containing { }, *, <, >) are skipped — they name
    a pattern (e.g. ``evidence/quality-gate-report-{date}.md``), not a file.
    """
    refs: list[str] = []
    for match in _EVIDENCE_REF_RE.finditer(text):
        ref = match.group(0)
        if any(char in ref for char in _PLACEHOLDER_CHARS):
            continue
        if ref not in refs:
            refs.append(ref)
    return refs


def _index_evidence(evidence_dir: Path, key_dir: Path) -> tuple[list[str], dict[str, str]]:
    """All files under evidence/ as key-dir-relative POSIX paths + contents."""
    files: list[str] = []
    contents: dict[str, str] = {}
    if evidence_dir.is_dir():
        for path in sorted(evidence_dir.rglob("*")):
            if path.is_file():
                rel = path.relative_to(key_dir).as_posix()
                files.append(rel)
                contents[rel] = _read_text(path)
    return files, contents


def build_decision_map(
    decisions: dict[str, str],
    evidence_files: list[str],
    evidence_contents: dict[str, str],
    key_dir: Path,
) -> list[dict[str, object]]:
    """Each D-NNN -> evidence files cited by the decision or citing it."""
    decision_map: list[dict[str, object]] = []
    for decision_id, corpus in decisions.items():
        mapped: set[str] = set()
        # Direction 1: the decision's text cites an existing evidence file.
        for ref in extract_evidence_refs(corpus):
            if (key_dir / ref).is_file():
                mapped.add(ref)
        # Direction 2: an evidence file's content cites the decision.
        mention = re.compile(r"(?<![0-9A-Za-z-])" + re.escape(decision_id) + r"(?![0-9])")
        for rel in evidence_files:
            if mention.search(evidence_contents[rel]):
                mapped.add(rel)
        decision_map.append({"decision": decision_id, "evidence_files": sorted(mapped)})
    return decision_map


def _extract_phase_edge(pm_state_path: Path) -> str | None:
    """Current `- Phase:` value from pm-state.md; null when unreadable."""
    text = _read_text(pm_state_path)
    if not text:
        return None
    match = _PHASE_LINE_RE.search(text)
    return match.group(1) if match else None


def build_dossier(key: str, project: Path) -> dict[str, object]:
    """Assemble the L1 audit dossier for {project}/.agenticdoc/{key}."""
    key_dir = project / AGENTICDOC_DIR / key
    spec_path = key_dir / "spec.md"

    spec_text = _read_text(spec_path)
    design_text = _read_text(key_dir / "design.md")
    phase_edge = _extract_phase_edge(key_dir / "pm-state.md")

    gaps: list[dict[str, str]] = []
    if not spec_path.is_file():
        gaps.append({"item": "spec.md", "rule": "spec-missing", "severity": "blocking"})

    ac_list = extract_ac_list(spec_text)
    evidence_files, evidence_contents = _index_evidence(key_dir / "evidence", key_dir)
    decision_map = build_decision_map(
        _extract_decisions(design_text), evidence_files, evidence_contents, key_dir
    )

    # Reference closure: every literal evidence/ citation must resolve to a file.
    for ref in extract_evidence_refs(spec_text + "\n" + design_text):
        if not (key_dir / ref).is_file():
            gaps.append({"item": ref, "rule": "evidence-ref-missing", "severity": "blocking"})

    # Research 留底 existence at the phase edges that require it.
    research_glob = _RESEARCH_GLOBS.get((phase_edge or "").strip().upper())
    if research_glob and not list(key_dir.glob(research_glob)):
        gaps.append(
            {"item": research_glob, "rule": "research-evidence-missing", "severity": "blocking"}
        )

    for entry in decision_map:
        if not entry["evidence_files"]:
            gaps.append(
                {
                    "item": str(entry["decision"]),
                    "rule": "decision-without-evidence",
                    "severity": "non-blocking",
                }
            )

    return {
        "key": key,
        "phase_edge": phase_edge,
        "ac_list": ac_list,
        "decision_map": decision_map,
        "gaps": gaps,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audit_evidence.py",
        description=(
            "L1 mechanical evidence audit: JSON dossier with AC list, "
            "decision->evidence map and gap list (exit 0 = no gaps, 1 = gaps)."
        ),
    )
    parser.add_argument("--key", required=True, help="key directory name under .agenticdoc/")
    parser.add_argument(
        "--project", default=".", help="project root containing .agenticdoc/ (default: cwd)"
    )
    args = parser.parse_args(argv)

    dossier = build_dossier(args.key, Path(args.project))
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):  # pragma: no cover - exotic stdout only
        pass
    json.dump(dossier, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 1 if dossier["gaps"] else 0


if __name__ == "__main__":
    sys.exit(main())
