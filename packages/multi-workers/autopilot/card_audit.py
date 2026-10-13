"""autopilot/card_audit.py — card traceability (sha256) + set consistency audit.

Task T-06 / AC-006 (key ``mw-dispatch-card-gate``).  Leaf module: stdlib plus
the existing ``mw_common`` helper, **read-only** on ``.agenticdoc`` (AC-008 —
it never writes a manifest; the digest record is its stdout).

Why
---
Before this gate a dispatch (``workers/<id>/task.md``) carried no reference to
the card (``tasks/*.md``) it was generated from, so an incident could not be
traced back to "which card justified this dispatch" (spec E5,
``evidence/research/spec-dispatch-path-20261012.md`` §2).  From disk alone the
audit answers three questions per key:

* **cards** — which ``tasks/*.md`` files exist; template/non-card files are
  excluded by the explicit ``is_card_file`` rule below (the corpus mixes
  ``T-NN-slug`` / ``Tn-slug`` / ``NNN-slug`` stems, so a positive "looks like a
  card" regex would drop real cards — the rule is a documented blacklist);
* **dispatched** — which card each ``workers/*/task.md`` names in its
  ``card_path:`` header, plus the EOL-insensitive sha256 of that card
  (``mw_common.sha256_eol_normalized`` — the freeze recipe: a CRLF/LF flip is
  not drift, but an equal-length content swap changes the digest, AC-006);
* **consistency** — ``missing_cards`` (a dispatch names a card absent from
  ``tasks/`` — AC-006 "卡片集合 ⊉ 派发集合 ⇒ 红并列差集"), ``tampered_cards``
  (a dispatch records a ``card_sha256:`` that no longer matches the card's
  current digest — AC-006 "等长替换篡改 ⇒ 红"), and the two unlisted buckets
  below. ``missing_cards`` and ``tampered_cards`` are **always** red.

``card_path`` header forms accepted (normalized to a key-relative
``tasks/<name>.md`` id): ``tasks/X.md``, ``<key>/tasks/X.md``,
``.agenticdoc/<key>/tasks/X.md``, a repo-root-relative path, or absolute.
Only the header region of ``task.md`` is read: body prose that merely mentions
``card_path`` (incident narratives do) must not count as a reference; the same
header-region rule governs the ``card_sha256:`` comparison.

Unlisted handling (T-12/F-06): a ``workers/*/task.md`` with no usable
``card_path:`` is either (a) a genuine card-less dispatch — the T-10 generator
injects the G-2 canonical headings, so it is not counted at all, keeping
``--strict`` usable after the cutover; (b) a **pre-boundary** historical row
(``unlisted_dispatches``, not red by default — strict is the migration switch);
or (c) a **post-boundary** row whose header is really missing
(``unlisted_after_boundary``, always red). The boundary constant and its
arithmetic are imported from ``launcher`` so the audit cannot drift from the
service gate.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

# Script-mode bootstrap: `python autopilot/card_audit.py` puts autopilot/ on
# sys.path, not its parent — mw_common lives in the parent.
_PARENT = pathlib.Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

import mw_common  # noqa: E402  (path bootstrapped above)

# T-12/F-06: the audit reuses the service gate's boundary constant and its
# arithmetic — one boundary, not a second one that can drift. `launcher`
# imports only `mw_common`, so this is not a cycle.
from launcher import (  # noqa: E402  (path bootstrapped above)
    ENVELOPE_ENFORCE_SINCE,
    envelope_enforce_since_epoch,
    has_canonical_envelope,
)

# Explicit non-card rule (card T-06: "排除模板/非卡文件须有明确规则"):
# a `tasks/*.md` file is a card unless its stem is underscore/dot-prefixed or
# is one of these well-known non-card names.  Everything else is a card —
# real stems look like `T-06-card-audit`, `T1-foo`, `001-bar`.
NON_CARD_STEMS = frozenset({"template", "readme", "index", "cards"})

# Header region: at most this many leading lines are inspected for `card_path:`.
HEADER_SCAN_LINES = 40

_CARD_PATH_RE = re.compile(r"^card_path\s*:\s*(?P<value>.*)$")
_CARD_SHA_RE = re.compile(r"^card_sha256\s*:\s*(?P<value>.*)$")
_HEADER_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.-]*)\s*:\s*(?P<value>.*)$")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def card_digest(path) -> str:
    """EOL-insensitive sha256 of a card file.

    Thin wrapper over :func:`mw_common.sha256_eol_normalized` (CRLF→LF before
    hashing), so a line-ending flip on checkout is not reported as drift while
    an equal-length content substitution is (AC-006 tamper判据).
    """
    return mw_common.sha256_eol_normalized(path)


def is_card_file(path) -> bool:
    """True when ``path`` is a card file per the explicit exclusion rule."""
    p = pathlib.Path(path)
    if p.suffix.lower() != ".md":
        return False
    stem = p.stem.lower()
    if stem.startswith("_") or stem.startswith("."):
        return False
    return stem not in NON_CARD_STEMS


def list_cards(key_dir) -> list[str]:
    """Sorted key-relative card ids (``tasks/<name>.md``) directly under ``tasks/``."""
    tasks_dir = pathlib.Path(key_dir) / "tasks"
    if not tasks_dir.is_dir():
        return []
    return sorted(
        f"tasks/{p.name}"
        for p in tasks_dir.iterdir()
        if p.is_file() and is_card_file(p)
    )


def _clean_ref(value: str) -> str:
    """Strip YAML quoting / trailing comments from a header value."""
    text = (value or "").strip()
    if " #" in text:
        text = text.split(" #", 1)[0].strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        text = text[1:-1].strip()
    return text


def _header_value(task_md, pattern: re.Pattern[str]) -> str:
    """Read one header-region value from a dispatch ``task.md``, or ``""``.

    Shared by :func:`parse_card_path` and :func:`parse_card_sha256`: YAML
    frontmatter (``---`` fenced) or leading ``key: value`` lines up to the
    first blank line / prose.  A body sentence mentioning the key is not a
    dispatch reference.
    """
    try:
        text = pathlib.Path(task_md).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""
    in_frontmatter = False
    seen_header = False
    for index, raw in enumerate(text.splitlines()[:HEADER_SCAN_LINES]):
        line = raw.strip()
        if index == 0 and line == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if line == "---":
                in_frontmatter = False
                continue
            match = pattern.match(line)
            if match:
                return _clean_ref(match.group("value"))
            continue
        if not line:
            if seen_header:
                break
            continue
        match = _HEADER_RE.match(line)
        if not match:
            break
        seen_header = True
        value = pattern.match(line)
        if value:
            return _clean_ref(value.group("value"))
    return ""


def parse_card_path(task_md) -> str:
    """Read the ``card_path:`` header value of a dispatch, or ``""``.

    Only the header region is inspected — YAML frontmatter (``---`` fenced) or
    leading ``key: value`` lines up to the first blank line / prose.  A body
    sentence mentioning ``card_path`` is not a dispatch reference.
    """
    return _header_value(task_md, _CARD_PATH_RE)


def parse_card_sha256(task_md) -> str:
    """Read the ``card_sha256:`` header value of a dispatch, or ``""``.

    Same header-region rule as :func:`parse_card_path`.  ``""`` means the
    dispatch recorded no digest (an older/hand-written row); the audit then has
    nothing to compare and does not invent a tamper finding.
    """
    return _header_value(task_md, _CARD_SHA_RE)


def _key_relative(path, key_dir) -> str:
    """``path`` as a posix id relative to ``key_dir``, or ``""`` when outside."""
    try:
        resolved = pathlib.Path(path).resolve()
        return resolved.relative_to(pathlib.Path(key_dir).resolve()).as_posix()
    except (ValueError, OSError):
        return ""


def card_id_from_ref(ref: str, key_dir) -> str:
    """Normalize a ``card_path`` value to a key-relative ``tasks/<name>.md`` id.

    Unresolvable/foreign refs are returned normalized-but-unresolved (still
    posix, no ``..``) so a diff can name them even when they do not exist.
    """
    raw = _clean_ref(ref)
    if not raw:
        return ""
    key_dir = pathlib.Path(key_dir)
    normalized = raw.replace("\\", "/")
    if normalized.startswith("/") or _DRIVE_RE.match(raw):
        candidate = pathlib.Path(raw)
        rel = _key_relative(candidate, key_dir)
        return rel if rel else candidate.as_posix()
    # accepted relative bases: key dir, .agenticdoc root, repo root.  Only an
    # existing candidate may claim an id — a non-existent path always
    # "relativizes" under the first base and would hide the real form.
    for base in (key_dir, key_dir.parent, key_dir.parent.parent):
        candidate = base / raw
        if not candidate.is_file():
            continue
        rel = _key_relative(candidate, key_dir)
        if rel:
            return rel
    # Unresolvable (missing / cross-key): strip the known prefixes syntactically
    # so the diff still names it in the same id space.
    for prefix in (f"{key_dir.parent.name}/{key_dir.name}/", f"{key_dir.name}/"):
        if normalized.startswith(prefix):
            return normalized[len(prefix):]
    return normalized


def _post_boundary(task_md, boundary_epoch: float) -> bool:
    """True when ``task.md``'s mtime is at/after the service boundary.

    History compatibility (P-07/P-09): a header-less dispatch whose file
    predates :data:`launcher.ENVELOPE_ENFORCE_SINCE` is a historical row; one
    written at/after it is a new header-less (or header-dropping) dispatch.
    The boundary instant comes from :func:`launcher.envelope_enforce_since_epoch`
    — same constant, same arithmetic (T-12/F-06).
    """
    try:
        mtime = pathlib.Path(task_md).stat().st_mtime
    except OSError:
        return True  # cannot prove it is old -> fail closed
    return mtime >= boundary_epoch


def _has_canonical_envelope(task_md) -> bool:
    """True when the task.md carries the G-2 canonical headings (same judge
    as the service gate, `launcher.has_canonical_envelope`)."""
    try:
        text = pathlib.Path(task_md).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return has_canonical_envelope(text)


def audit(agenticdoc_root, key) -> dict:
    """Card traceability + set consistency for ``key`` under ``agenticdoc_root``.

    Returns ``{"key", "cards", "dispatched", "missing_cards",
    "tampered_cards", "unlisted_dispatches", "unlisted_after_boundary",
    "digests"}`` where

    * ``cards`` / ``digests`` — sorted key-relative card ids and their sha256;
    * ``dispatched`` — list of ``{worker, card_path, card, in_cards}`` for
      every ``workers/*/task.md`` that names a card;
    * ``missing_cards`` — dispatched card ids absent from ``cards`` (the
      ``dispatched \\ cards`` diff, AC-006; always red);
    * ``tampered_cards`` — dispatches whose recorded ``card_sha256:`` no longer
      matches the card's current digest (AC-006 "等长替换篡改 ⇒ 红"; always
      red).  Each entry is ``{worker, task_key, card, recorded, current}``;
    * ``unlisted_dispatches`` — header-less dispatches **created before the
      boundary** (historical, not red unless ``--strict``);
    * ``unlisted_after_boundary`` — header-less dispatches created at/after the
      boundary and without the G-2 canonical envelope (a genuinely dropped
      reference/allocation, T-12/F-06; always red).  A card-less dispatch that
      carries the canonical headings (the T-10 generator shape) is not counted
      at all, so ``--strict`` does not become permanently unusable.
    """
    root = pathlib.Path(agenticdoc_root)
    key_dir = root / key
    cards = list_cards(key_dir)
    card_set = set(cards)
    digests = {card_id: card_digest(key_dir / card_id) for card_id in cards}

    dispatched: list[dict] = []
    missing: list[str] = []
    tampered: list[dict] = []
    unlisted: list[str] = []
    unlisted_after: list[str] = []
    boundary_epoch = envelope_enforce_since_epoch()
    workers_dir = key_dir / "workers"
    if workers_dir.is_dir():
        for worker_dir in sorted(p for p in workers_dir.iterdir() if p.is_dir()):
            task_md = worker_dir / "task.md"
            if not task_md.is_file():
                continue
            worker = f"workers/{worker_dir.name}"
            ref = parse_card_path(task_md)
            card_id = card_id_from_ref(ref, key_dir) if ref else ""
            if not card_id:
                if _has_canonical_envelope(task_md):
                    # Legitimate card-less dispatch (T-10 synthesized envelope):
                    # not a missing reference, so `--strict` stays usable.
                    pass
                elif _post_boundary(task_md, boundary_epoch):
                    unlisted_after.append(worker)
                else:
                    unlisted.append(worker)
                continue
            in_cards = card_id in card_set
            dispatched.append(
                {"worker": worker, "card_path": ref, "card": card_id, "in_cards": in_cards}
            )
            if not in_cards:
                missing.append(card_id)
                continue
            recorded = parse_card_sha256(task_md)
            current = digests.get(card_id, "")
            if recorded and recorded != current:
                tampered.append(
                    {
                        "worker": worker,
                        "task_key": worker_dir.name,
                        "card": card_id,
                        "recorded": recorded,
                        "current": current,
                    }
                )

    return {
        "key": key,
        "cards": cards,
        "dispatched": dispatched,
        "missing_cards": sorted(set(missing)),
        "tampered_cards": tampered,
        "unlisted_dispatches": sorted(unlisted),
        "unlisted_after_boundary": sorted(unlisted_after),
        "digests": digests,
    }


def has_findings(result: dict, strict: bool = False) -> bool:
    """A key is red on a missing/tampered card or a post-boundary unlisted
    dispatch — all unconditional.  Pre-boundary unlisted dispatches are red
    only under ``--strict`` (the migration switch, spec P-07)."""
    if result["missing_cards"] or result["tampered_cards"] or result["unlisted_after_boundary"]:
        return True
    return bool(strict and result["unlisted_dispatches"])


def _section(lines: list[str], title: str, entries: list[str]) -> None:
    lines.append(f"{title} ({len(entries)})")
    lines.extend(entries if entries else ["  (none)"])
    lines.append("")


def render(result: dict, strict: bool = False) -> str:
    """Human-readable report (no JSON; ``audit()`` is the machine interface)."""
    lines = [f"[card-audit] key={result['key']} strict={'yes' if strict else 'no'}", ""]
    _section(
        lines,
        "cards",
        [f"  {card_id:<46} sha256={result['digests'].get(card_id, '')}" for card_id in result["cards"]],
    )
    _section(
        lines,
        "dispatched",
        [
            f"  {d['worker']:<44} -> {d['card'] or '(unnamed)'} "
            f"[{'ok' if d['in_cards'] else 'MISSING'}]"
            for d in result["dispatched"]
        ],
    )
    _section(lines, "missing_cards", [f"  {card_id}" for card_id in result["missing_cards"]])
    _section(
        lines,
        "tampered_cards [always FAIL]",
        [
            f"  {t['worker']:<44} -> {t['card']} "
            f"recorded={t['recorded'][:12]} current={t['current'][:12]}"
            for t in result["tampered_cards"]
        ],
    )
    unlisted_note = "strict: FAIL" if strict else "not red (use --strict to fail)"
    _section(
        lines,
        f"unlisted_dispatches [{unlisted_note}]",
        [f"  {worker}" for worker in result["unlisted_dispatches"]],
    )
    _section(
        lines,
        "unlisted_after_boundary [always FAIL]",
        [f"  {worker}" for worker in result["unlisted_after_boundary"]],
    )
    verdict = "FAIL" if has_findings(result, strict) else "OK"
    lines.append(
        "summary: cards={cards} dispatched={dispatched} missing={missing} "
        "tampered={tampered} unlisted={unlisted} unlisted_after={unlisted_after} "
        "-> {verdict}".format(
            cards=len(result["cards"]),
            dispatched=len(result["dispatched"]),
            missing=len(result["missing_cards"]),
            tampered=len(result["tampered_cards"]),
            unlisted=len(result["unlisted_dispatches"]),
            unlisted_after=len(result["unlisted_after_boundary"]),
            verdict=verdict,
        )
    )
    return "\n".join(lines)


def main(argv=None) -> int:
    """CLI: ``python -X utf8 autopilot/card_audit.py --root .agenticdoc --key K [--strict]``.

    Exit codes: 0 = consistent, 1 = findings (missing/tampered card and
    post-boundary unlisted always; pre-boundary unlisted only with
    ``--strict``), 2 = usage/IO error (missing key dir).
    """
    parser = argparse.ArgumentParser(
        prog="card_audit",
        description="Card (tasks/*.md) traceability and dispatch-set consistency audit.",
    )
    parser.add_argument("--root", default=".agenticdoc", help="agenticdoc root (default: .agenticdoc)")
    parser.add_argument("--key", required=True, help="AgenticTask key to audit")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also fail on pre-boundary unlisted dispatches (migration switch)",
    )
    args = parser.parse_args(argv)

    root = pathlib.Path(args.root)
    if not (root / args.key).is_dir():
        print(f"[card-audit] key dir not found: {root / args.key}", file=sys.stderr)
        return 2
    result = audit(root, args.key)
    print(render(result, args.strict))
    return 1 if has_findings(result, args.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
