"""test_write_face.py - W-01/W-04: frozen corpus + boundary tests for the write-face operator.

Frozen corpus (read-only, owned by the PM):
  packages/multi-workers/test/fixtures/write-face-corpus.json
    parse       23 rows
    overlap     59 rows (overlap 34 / none 13 / reject 8 / serial_only 1 / unsupported 3)

Contract:
  .agenticdoc/mw-write-face-guard/evidence/research/design-glob-intersection-20261014.md
  sections 3.1 / 3.2 / 3.3 / 4.2 / 4.3 / 4.4
  .agenticdoc/mw-write-face-guard/design.md D-111 (rejection-shape precedence)
  and D-112 (syntax-blind entry splitting)

Run: cd packages/multi-workers; python -m pytest test_write_face.py -q
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import write_face as wf

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CORPUS_PATH = pathlib.Path(__file__).parent / "test" / "fixtures" / "write-face-corpus.json"

# An absolute path guaranteed not to be under the repo root (section 3.1 / P15).
OUTSIDE_ROOT = tempfile.mkdtemp(prefix="mw-write-face-outside-")

MAGIC = set("*?[]{}")


# ---------------------------------------------------------------------------
# corpus helpers
# ---------------------------------------------------------------------------


def _load_corpus() -> dict:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def _sub(text: str) -> str:
    return text.replace("$REPO", str(REPO_ROOT)).replace("$OUTSIDE", OUTSIDE_ROOT)


def _render_head(name: str, entries) -> str:
    """Render one head in either carrier form (design 3.1).

    The comma-separated single line is the production path, so multi-entry rows
    keep exercising the D-112 splitter.  An entry that itself contains a comma
    (e.g. the balanced `{b,c}` alternation of V20) cannot be spelled on a single
    line under D-112 - commas are never pattern content there - so such rows use
    the equivalent block-list form, where each list item is one entry.
    """
    values = [_sub(e) for e in entries]
    if any("," in v for v in values):
        return name + ":\n" + "".join(f"  - {v}\n" for v in values)
    return name + ": " + ", ".join(values) + "\n"


def _face(entries, base: str, case_insensitive: bool, deny=None):
    text = _render_head("write_face", entries)
    if deny:
        text += _render_head("write_face_deny", deny)
    return wf.parse_write_face(text, base=base, case_insensitive=case_insensitive)


CORPUS = _load_corpus()


# ---------------------------------------------------------------------------
# section 3.3 / 3.1 - parse corpus (16)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("row", CORPUS["parse"], ids=[r["name"] for r in CORPUS["parse"]])
def test_corpus_parse(row: dict) -> None:
    text = "\n".join(_sub(line) for line in row["head"])
    got = wf.parse_write_face(text, base=str(REPO_ROOT), case_insensitive=False)
    expect = row["expect"]
    if expect["kind"] == "entries":
        assert isinstance(got, wf.WriteFace), got
        assert list(got.allow_entries) == expect["entries"]
    elif expect["kind"] == "unknown":
        assert isinstance(got, wf.Undeclared), got
    else:
        assert isinstance(got, wf.Refused), got
        assert got.code == expect["code"]


def test_parse_block_list_form() -> None:
    # section 3.1: the optional YAML block-list form is equivalent.
    text = "write_face:\n  - a/**\n  - b/c.ts\n"
    got = wf.parse_write_face(text, base=str(REPO_ROOT), case_insensitive=False)
    assert isinstance(got, wf.WriteFace)
    assert list(got.allow_entries) == ["a/**", "b/c.ts"]


def test_parse_returns_normalized_segments() -> None:
    got = wf.parse_write_face("write_face: a/**/**", base=str(REPO_ROOT), case_insensitive=False)
    assert isinstance(got, wf.WriteFace)
    assert got.allow_entries == ("a/**",)
    first, second = got.allow[0].segments
    assert isinstance(first, wf.CharPattern)
    assert first.tokens == (wf.Lit("a"),)
    assert second == "**"


# ---------------------------------------------------------------------------
# section 4.4 - overlap corpus (49)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "row", CORPUS["overlap"], ids=[r["name"] for r in CORPUS["overlap"]]
)
def test_corpus_overlap(row: dict) -> None:
    ci = row["case_insensitive"]
    a = wf.Undeclared() if row["a"] is None else _face(row["a"], str(REPO_ROOT), ci, row.get("a_deny"))
    b = wf.Undeclared() if row["b"] is None else _face(row["b"], str(REPO_ROOT), ci, row.get("b_deny"))
    expect = row["expect"]
    kind = expect["kind"]

    if kind == "reject":
        side = expect["side"]
        face = a if side == "a" else b
        assert isinstance(face, wf.Refused), (row["name"], face)
        assert face.code == expect["code"]
        return

    if kind == "serial_only":
        side = expect["side"]
        face = a if side == "a" else b
        assert isinstance(face, wf.Undeclared), (row["name"], face)
        return

    assert isinstance(a, wf.WriteFace), (row["name"], a)
    assert isinstance(b, wf.WriteFace), (row["name"], b)
    result = wf.overlap(a, b)
    if kind == "overlap":
        assert isinstance(result, wf.Conflict), (row["name"], result)
        if expect.get("sample_globfree"):
            assert not (MAGIC & set(result.sample)), result.sample
            assert result.sample != ""
    elif kind == "unsupported":
        # D-006/D-111: no conflict provable and some side is undecidable;
        # callers treat this exactly like an overlap.
        assert isinstance(result, wf.Unsupported), (row["name"], result)
    else:
        assert result is None, (row["name"], result)


def test_corpus_unsupported_is_also_overlap() -> None:
    # The caller-facing predicate must map the fallback shape to "collides".
    a = _face(["src/[a-"], str(REPO_ROOT), False)
    b = _face(["src/x.ts"], str(REPO_ROOT), False)
    assert isinstance(a, wf.WriteFace) and isinstance(b, wf.WriteFace)
    res = wf.overlap(a, b)
    assert isinstance(res, wf.Unsupported), res
    assert wf.is_overlap(res)


def test_corpus_counts_frozen() -> None:
    assert len(CORPUS["parse"]) == 23
    assert CORPUS["counts"]["parse"] == 23
    assert len(CORPUS["overlap"]) == 59
    assert CORPUS["counts"]["overlap"] == 59
    kinds: dict[str, int] = {}
    for row in CORPUS["overlap"]:
        kind = row["expect"]["kind"]
        kinds[kind] = kinds.get(kind, 0) + 1
    assert kinds == {"overlap": 34, "none": 13, "reject": 8, "serial_only": 1, "unsupported": 3}


# ---------------------------------------------------------------------------
# D-112 - syntax-blind entry splitting (bracket-aware splitting is rejected)
# ---------------------------------------------------------------------------


def test_d112_unterminated_bracket_does_not_swallow_the_next_field() -> None:
    got = wf.parse_write_face(
        "write_face: src/[a-, src/ok.ts", base=str(REPO_ROOT), case_insensitive=False
    )
    assert isinstance(got, wf.WriteFace), got
    assert list(got.allow_entries) == ["src/[a-", "src/ok.ts"]


def test_d112_comma_is_never_pattern_content() -> None:
    got = wf.parse_write_face(
        "write_face: src/[a-, src/b].ts, src/ok.ts",
        base=str(REPO_ROOT),
        case_insensitive=False,
    )
    assert isinstance(got, wf.WriteFace), got
    assert list(got.allow_entries) == ["src/[a-", "src/b].ts", "src/ok.ts"]


def test_d112_unclosed_brace_still_splits() -> None:
    # P21: the fragment `b` is a legal literal and only *adds* an allow entry,
    # so the error direction is fail-closed.
    got = wf.parse_write_face(
        "write_face: src/{a,b", base=str(REPO_ROOT), case_insensitive=False
    )
    assert isinstance(got, wf.WriteFace), got
    assert list(got.allow_entries) == ["src/{a", "b"]


def test_d112_bracket_aware_split_would_merge_three_entries_into_one() -> None:
    # Counterexample for the rejected "bracket-aware split": a class-aware
    # scanner lets the unterminated `[` swallow `a-, src/b]`, collapsing the
    # three declared paths into the single entry below and losing two of them.
    bracket_aware_would_merge = ["src/[a-, src/b].ts"]
    got = wf.parse_write_face(
        "write_face: src/[a-, src/b].ts, src/ok.ts",
        base=str(REPO_ROOT),
        case_insensitive=False,
    )
    assert isinstance(got, wf.WriteFace), got
    assert list(got.allow_entries) != bracket_aware_would_merge
    assert len(got.allow_entries) == 3
    assert got.allow_entries[-1] == "src/ok.ts"


# ---------------------------------------------------------------------------
# D-111 - hard violations win; order independent (parse + intersection)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("head", "code"),
    [
        ("write_face: src/[a-, src/../y", wf.WRITE_FACE_ESCAPE),
        ("write_face: src/../y, src/[a-", wf.WRITE_FACE_ESCAPE),
        ("write_face: src/[a-, !src/x", wf.WRITE_FACE_INVALID_ENTRY),
        ("write_face: src/[a-, $OUTSIDE/x", wf.WRITE_FACE_OUTSIDE_BASE),
        ("write_face: $OUTSIDE/x, src/[a-", wf.WRITE_FACE_OUTSIDE_BASE),
    ],
)
def test_d111_parse_hard_violation_wins_regardless_of_order(head: str, code: str) -> None:
    got = wf.parse_write_face(_sub(head), base=str(REPO_ROOT), case_insensitive=False)
    assert isinstance(got, wf.Refused), got
    assert got.code == code


def test_d111_provable_conflict_wins_over_unsupported() -> None:
    a = _face(["src/[a-", "src/x.ts"], str(REPO_ROOT), False)
    b = _face(["src/x.ts"], str(REPO_ROOT), False)
    assert isinstance(a, wf.WriteFace) and isinstance(b, wf.WriteFace)
    res = wf.overlap(a, b)
    assert isinstance(res, wf.Conflict), res
    assert res.sample == "src/x.ts"
    assert not (MAGIC & set(res.sample))


def test_d111_unsupported_only_when_no_witness() -> None:
    a = _face(["src/[a-"], str(REPO_ROOT), False)
    b = _face(["src/x.ts"], str(REPO_ROOT), False)
    assert isinstance(a, wf.WriteFace) and isinstance(b, wf.WriteFace)
    res = wf.overlap(a, b)
    assert isinstance(res, wf.Unsupported), res
    assert res.reason == "unsupported-syntax"
    assert wf.is_overlap(res)


def test_d111_unsupported_entry_is_recorded_not_dropped() -> None:
    # P17/P22: an unsupported entry still lands in the allow list (it is the
    # face's "unknown" set), so the parse result is not empty and not a refusal.
    got = wf.parse_write_face(
        "write_face: src/[a-, src/ok.ts", base=str(REPO_ROOT), case_insensitive=False
    )
    assert isinstance(got, wf.WriteFace), got
    assert any(g.unsupported for g in got.allow)
    assert any(not g.unsupported for g in got.allow)


def test_d111_deferred_fallback_does_not_abort_the_pair_search() -> None:
    # Corpus-independent regression for the V58 defect class (a frozen corpus
    # row must not be the only guard): the first pair hits a state-machine
    # fallback (product-state limit), the next pair yields a provable witness.
    # The fallback must be deferred per pair, never abort the whole product.
    # `huge` is a *supported* entry (no glob metacharacters), so the trigger is
    # `_ConservativeUnknown`, not the unsupported-syntax slot.
    huge = "a/" * 255 + "a"  # 256 segments => (257)*(257) > MAX_PRODUCT_STATES
    a = _face([huge, "src/x.ts"], str(REPO_ROOT), False)
    b = _face([huge, "src/x.ts"], str(REPO_ROOT), False)
    assert isinstance(a, wf.WriteFace) and isinstance(b, wf.WriteFace)
    assert not any(g.unsupported for g in a.allow), a.allow
    res = wf.overlap(a, b)
    assert isinstance(res, wf.Conflict), res
    assert res.sample == "src/x.ts"
    assert not (MAGIC & set(res.sample))
    assert res.rule == "src/x.ts"
    assert res.other == "src/x.ts"

    # Reverse: with only the undecidable pair, the deferred fallback is still
    # reported as `Unsupported` (and therefore "collides").
    only = _face([huge], str(REPO_ROOT), False)
    assert isinstance(only, wf.WriteFace)
    fallback = wf.overlap(only, only)
    assert isinstance(fallback, wf.Unsupported), fallback
    assert fallback.reason == "glob-product-state-limit"
    assert wf.is_overlap(fallback)


# ---------------------------------------------------------------------------
# section 4.3 hard acceptance points - epsilon-NFA product
# ---------------------------------------------------------------------------


def _go(a: str, b: str, ci: bool = False) -> tuple[str, ...] | None | wf.Unsupported:
    return wf.globs_overlap([a], [b], case_insensitive=ci)


def test_double_star_self_loop_matches_two_segments() -> None:
    # `**` must have a self-loop (consume 1 segment), else this is a false NONE.
    witness = _go("**", "x/y")
    assert isinstance(witness, tuple), witness
    assert witness == ("x", "y")


def test_double_star_zero_segment_expansion() -> None:
    # `**` must expand to zero segments, else `a/**/b` vs `a/b` is a false NONE.
    witness = _go("a/**/b", "a/b")
    assert isinstance(witness, tuple), witness
    assert witness == ("a", "b")


def test_trailing_double_star_includes_bare_dir() -> None:
    witness = _go("a/**", "a")
    assert isinstance(witness, tuple), witness
    assert witness == ("a",)


def test_leading_double_star_vs_deep_path() -> None:
    witness = _go("**", "packages/x/y.ts")
    assert isinstance(witness, tuple), witness


def test_double_star_star_requires_one_segment() -> None:
    assert _go("a/**/*", "a") is None


def test_star_does_not_cross_slash() -> None:
    assert _go("a/*.ts", "a/b/c.ts") is None
    assert isinstance(_go("a/*.ts", "a/b.ts"), tuple)


# ---------------------------------------------------------------------------
# section 3.1 boundary: dot:true, case modes, in-segment `**`
# ---------------------------------------------------------------------------


def test_dot_segments_are_ordinary() -> None:
    assert isinstance(_go("**", ".agenticdoc/k/x.md"), tuple)
    assert isinstance(_go("a/**/*.ts", "a/.x/b.ts"), tuple)
    assert isinstance(_go("**", ".git/config"), tuple)


def test_case_insensitive_modes() -> None:
    assert isinstance(_go("a/**", "A/B", ci=True), tuple)
    assert _go("a/**", "A/B", ci=False) is None


def test_in_segment_double_star_behaves_as_star() -> None:
    assert isinstance(_go("a/**b", "a/xxb"), tuple)
    assert _go("a/**b", "a/x/b") is None


def test_literal_is_an_exact_node() -> None:
    assert _go("a", "a/b") is None
    assert _go(".agenticdoc/k/evidence", ".agenticdoc/k/evidence/report.md") is None


# ---------------------------------------------------------------------------
# section 3.2 - conservative fallback list: every item has a real trigger
# ---------------------------------------------------------------------------


def _unsupported(a: str, b: str, ci: bool = False) -> wf.Unsupported:
    res = _go(a, b, ci)
    assert isinstance(res, wf.Unsupported), res
    return res


@pytest.mark.parametrize(
    "pattern",
    ["!(a|b)", "+(a|b)", "*(a|b)", "?(a|b)", "[abc", "a]b"],
    ids=["extglob-negate", "extglob-plus", "extglob-star", "extglob-qmark", "class-unclosed", "stray-close"],
)
def test_unsupported_syntax_yields_unsupported(pattern: str) -> None:
    res = _unsupported(pattern, "x/y")
    assert res.reason == "unsupported-syntax"


def test_nested_brace_depth_limit() -> None:
    pattern = "p"
    for _ in range(wf.MAX_BRACE_DEPTH + 2):
        pattern = "{a," + pattern + "}"
    res = _unsupported(pattern, "x/y")
    assert res.reason == "unsupported-syntax"


def test_brace_expansion_count_limit() -> None:
    pattern = ",".join("{a,b}" for _ in range(12))
    res = _unsupported(pattern, "x/y")
    assert res.reason == "unsupported-syntax"


def test_segment_pattern_length_limit() -> None:
    pattern = "a" * (wf.MAX_TOKEN_RUN + 4)
    res = _unsupported(pattern, "x/y")
    assert res.reason == "unsupported-syntax"


def test_glob_product_state_limit() -> None:
    deep_a = "/".join(["a"] * (wf.MAX_GLOB_SEGMENTS // 2))
    deep_b = "/".join(["a"] * (wf.MAX_GLOB_SEGMENTS // 2))
    res = _unsupported(deep_a, deep_b)
    assert res.reason == "glob-product-state-limit"


def test_segment_pattern_state_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wf, "MAX_SEG_BFS_STATES", 1)
    res = _unsupported("ab", "ab")
    assert res.reason == "segment-pattern-state-limit"


def test_segment_probe_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wf, "_PROBE", ())
    # Two disjoint negated classes: no walkable probe character.
    res = _unsupported("[!a]", "[!b]")
    assert res.reason == "segment-pattern-probe-exhausted"


def test_absolute_outside_base_refused_at_parse() -> None:
    got = _face([OUTSIDE_ROOT + "/packages/x/**"], str(REPO_ROOT), False)
    assert isinstance(got, wf.Refused)
    assert got.code == wf.WRITE_FACE_OUTSIDE_BASE


def test_cross_base_comparison_is_unsupported() -> None:
    a = _face(["a/**"], str(REPO_ROOT), False)
    b = wf.parse_write_face("write_face: a/**", base=OUTSIDE_ROOT, case_insensitive=False)
    assert isinstance(a, wf.WriteFace) and isinstance(b, wf.WriteFace)
    res = wf.overlap(a, b)
    assert isinstance(res, wf.Unsupported)
    assert res.reason == "incomparable-base"


def test_case_mode_mismatch_is_unsupported() -> None:
    a = _face(["a/**"], str(REPO_ROOT), False)
    b = _face(["A/B"], str(REPO_ROOT), True)
    assert isinstance(a, wf.WriteFace) and isinstance(b, wf.WriteFace)
    res = wf.overlap(a, b)
    assert isinstance(res, wf.Unsupported)
    assert res.reason == "incomparable-case-mode"


def test_undeclared_is_not_passed_to_overlap() -> None:
    # D-003 serial-only: a missing head parses as Undeclared and never reaches
    # the operator (the caller marks the row serial-only).
    assert isinstance(
        wf.parse_write_face("# t\n- type: coding\n", base=str(REPO_ROOT), case_insensitive=False),
        wf.Undeclared,
    )


# ---------------------------------------------------------------------------
# section 3.2 - deny monotonicity (V37/V38)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "deny",
    [None, ["a/**"], ["a/b"]],
    ids=["no-deny", "deny-covers-everything", "deny-covers-the-exact-file"],
)
def test_deny_does_not_change_the_overlap_decision(deny) -> None:
    a = _face(["a/**"], str(REPO_ROOT), False, deny=deny)
    b = _face(["a/b"], str(REPO_ROOT), False)
    assert isinstance(a, wf.WriteFace) and isinstance(b, wf.WriteFace)
    res = wf.overlap(a, b)
    assert isinstance(res, wf.Conflict), res
    if deny:
        # deny is parsed and retained, but never subtracts from the decision
        assert a.deny, a.deny


# ---------------------------------------------------------------------------
# witness hygiene + no-fnmatch guard
# ---------------------------------------------------------------------------


def test_every_proven_witness_is_glob_free() -> None:
    pairs = [
        ("packages/x/**", "packages/x/y.ts", False),
        ("a/**", "a", False),
        ("**", ".agenticdoc/k/x.md", False),
        ("a/**/*.ts", "a/.x/b.ts", False),
        ("a/**", "A/B", True),
    ]
    for a, b, ci in pairs:
        res = _go(a, b, ci)
        assert isinstance(res, tuple), (a, b, res)
        sample = "/".join(res)
        assert sample != ""
        assert not (MAGIC & set(sample)), (a, b, sample)


def test_module_never_imports_fnmatch_or_pathlib_match() -> None:
    source = pathlib.Path(wf.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "fnmatch" not in imported
    # `pathlib` is not imported either, so its pure-path matcher cannot be used.
    assert "pathlib" not in imported
    assert "os" not in imported  # no os.path.normcase smuggling either
