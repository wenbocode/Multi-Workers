"""test_autopilot_readcap_injection.py — L1 tests for the read-scope cap
injection (key `feature-l3-readcap-injection`, task 003).

Subject: `autopilot/dispatch.py` must render the ``_autopilot/config.json``
read budgets into the task.md frontmatter (``l2_read_file_cap`` /
``l2_read_byte_cap``) — position ``read_scope:`` block → two cap scalars →
``deny_globs:`` block — and must stay byte-compatible with the pre-fix
renderer whenever the config is absent, field-less, invalid or unreadable.

Coverage (AC-001..AC-012 of the key's spec; see ``AC_COVERAGE`` below):

    AC-001  two lines, right position, 3 task types           -> VC-001
    AC-002  dispatch() e2e + same-口径 parse == config         -> VC-002
    AC-003  re-render follows config; no cap fallback literal  -> VC-003
    AC-004  T-003 part: derived values flow + >=2x margins     -> (T-004 closes)
    AC-005  T-003 part: measured envelope replays 0 rejections -> (T-004 closes)
    AC-006  T-003 part: dispatch side caps == config           -> (T-006 closes)
    AC-007  missing config  -> byte-identical vs HEAD, 0 feet  -> VC-007
    AC-008  missing fields  -> byte-identical vs HEAD + ok     -> VC-008
    AC-009  invalid/unreadable config -> no new failure mode   -> VC-009
    AC-010  reverse 1: small cap still blocks                  -> VC-010
    AC-011  reverse 2: invalid values never become unlimited   -> VC-011
    AC-012  reverse 3: L3 verdict still `below`                -> VC-012
    AC-015  regression all green + coverage + discipline       -> VC-015

Fail-closed reverse cases: missing config (VC-007), missing fields (VC-008),
invalid/broken/raising config (VC-009), invalid values (VC-011).

The byte-identical left end is the frozen pre-fix renderer
``baseline_20260924/dispatch.head.py`` (T-001); when the frozen copy is not
reachable the same blob is taken from ``git show HEAD:...`` so the file stays
runnable outside the partition workspace.

Cap replay uses a deliberately minimal Python mirror of
``read-scope.ts::checkReadScopeCall``'s cap branches (deny-glob > scope >
cap-file > cap-byte); containment / deny semantics stay covered by the TS
suite (T-005). Before rendering it, the mirror is pinned to the frozen T-002
render artifact (``verifier_caps_64_2097152.md``): the cap lines parsed out of
that artifact reproduce it byte for byte.

Evidence channel is stdout: run with ``-s`` (per _pitfalls P-006) — every
assertion group prints one ``[VERIFY] VC-0NN: key=value`` line.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import inspect
import json
import os
import pathlib
import re
import subprocess
import sys
import types

import pytest

MODULE_DIR = pathlib.Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from autopilot import config as autopilot_config  # noqa: E402
from autopilot import conductor  # noqa: E402
from autopilot import dispatch as dispatch_mod  # noqa: E402

DISPATCH_PY = MODULE_DIR / "autopilot" / "dispatch.py"
FRAMEWORK_ROOT = MODULE_DIR.parent.parent
DISPATCH_RELATIVE = "packages/multi-workers/autopilot/dispatch.py"
BASELINE_DIR = pathlib.Path(
    os.environ.get(
        "MW_READCAP_BASELINE_DIR",
        r"H:\git\E2Feature\.agenticdoc\feature-l3-readcap-injection\workers"
        r"\ap-feature-l3-readcap-injection-001-baseline-freeze-and-witness"
        r"\baseline_20260924",
    )
)
HEAD_DISPATCH = BASELINE_DIR / "dispatch.head.py"
# T-002 render artifact used to pin the cap replay mirror (read-only).
PIN_RENDER = (
    BASELINE_DIR.parents[1]
    / "ap-feature-l3-readcap-injection-002-inject-caps-render-or-wire"
    / "render_snippets"
    / "verifier_caps_64_2097152.md"
)

# TS harness defaults (read-scope.ts::DEFAULT_READ_*) — the single source for
# the absent-cap fallback; asserted equal to config.py::DEFAULT_CONFIG below.
TS_DEFAULT_FILE_CAP = 8
TS_DEFAULT_BYTE_CAP = 65536

# Measured dossier envelope (plan PF-4 / evidence/readcap-facts-20260924.json)
# and the design D-006 derived values; used ONLY by the T-003-side readiness
# checks of AC-004/AC-005 (the real per-file replay and the config lift are
# T-004's closure).
MEASURED_MAX_CALLS = 57
MEASURED_MAX_BYTES = 913636
DERIVED_FILE_CAP = 128
DERIVED_BYTE_CAP = 4194304

BASE_KWARGS = dict(
    loop="feature-l3-readcap-injection:003",
    attempt=1,
    read_scope=[
        ".agenticdoc/feature-l3-readcap-injection",
        ".agenticdoc/goal.md",
    ],
    deny_globs=["**/*.bin", "Engine/Binaries"],
    model="deepseek-v4.1-flash",
    phase="EXECUTE",
)

AC_COVERAGE: dict[str, list[str]] = {
    "AC-001": ["test_vc001_inject_and_position"],
    "AC-002": ["test_vc002_dispatch_e2e_parse_mirror"],
    "AC-003": ["test_vc003_value_follows_config_and_no_cap_literal"],
    "AC-004": ["test_ac004_partial_derived_values_and_margins"],
    "AC-005": ["test_ac005_partial_measured_envelope_replay"],
    "AC-006": ["test_ac006_partial_dispatch_side_caps"],
    "AC-007": ["test_vc007_missing_config_byte_identical"],
    "AC-008": ["test_vc008_missing_fields_byte_identical"],
    "AC-009": ["test_vc009_invalid_config_no_new_failure_mode"],
    "AC-010": ["test_vc010_small_cap_still_blocks"],
    "AC-011": ["test_vc011_invalid_values_not_unlimited"],
    "AC-012": ["test_vc012_l3_criteria_still_below"],
    "AC-015": [
        "test_vc015_fail_closed_suite_counts",
        "test_existing_regression_files_untouched",
    ],
}

FAIL_CLOSED_CASES = [
    "test_vc007_missing_config_byte_identical",     # missing config
    "test_vc008_missing_fields_byte_identical",     # missing cap fields
    "test_vc009_invalid_config_no_new_failure_mode",  # invalid / broken / raising
    "test_vc011_invalid_values_not_unlimited",      # invalid value classes
]

SPEC_AC_RANGE = [f"AC-{i:03d}" for i in range(1, 13)]


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def true_str(value: bool) -> str:
    return "true" if value else "false"


# ── frozen pre-fix renderer (byte-identical left end) ─────────────────────────

_HEAD_CACHE: list[types.ModuleType] = []


def _git(*args: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(FRAMEWORK_ROOT), *args],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "git " + " ".join(args) + " failed: "
            + proc.stderr.decode("utf-8", "replace")
        )
    return proc.stdout


def _head_module() -> types.ModuleType:
    """Load the pre-fix renderer. Primary source = the frozen T-001 copy;
    portable fallback = the same blob from git HEAD. The frozen copy is
    sha256-bound to the git HEAD blob by ``test_baseline_left_end_bound``."""
    if _HEAD_CACHE:
        return _HEAD_CACHE[0]
    if HEAD_DISPATCH.is_file():
        data = HEAD_DISPATCH.read_bytes()
        origin = str(HEAD_DISPATCH)
    else:
        data = _git("show", f"HEAD:{DISPATCH_RELATIVE}")
        origin = f"git HEAD:{DISPATCH_RELATIVE}"
    module = types.ModuleType("_readcap_dispatch_head")
    module.__file__ = origin
    # dataclasses._is_type resolves cls.__module__ through sys.modules.
    sys.modules["_readcap_dispatch_head"] = module
    exec(compile(data.decode("utf-8"), origin, "exec"), module.__dict__)
    _HEAD_CACHE.append(module)
    return module


# ── fixture project ───────────────────────────────────────────────────────────

def make_project(root, config=None, *, write_config=True, deny_globs=()):
    """tmp_path fixture project: target.yml (single mode) + optional
    ``_autopilot/config.json``. ``write_config=False`` guarantees zero
    footprint — the ``_autopilot`` directory is never created."""
    root = pathlib.Path(root)
    agentic = root / ".agenticdoc"
    agentic.mkdir(parents=True, exist_ok=True)
    yml = ["mode: single"]
    if deny_globs:
        yml += ["ignore:", "  deny_globs:"] + [f'    - "{g}"' for g in deny_globs]
    (agentic / "target.yml").write_text(
        "\n".join(yml) + "\n", encoding="utf-8", newline="\n"
    )
    if write_config:
        cfg_dir = agentic / "_autopilot"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        if isinstance(config, str):
            (cfg_dir / "config.json").write_bytes(config.encode("utf-8"))
        else:
            payload = json.dumps({} if config is None else config, indent=2) + "\n"
            (cfg_dir / "config.json").write_text(
                payload, encoding="utf-8", newline="\n"
            )
    return root


def write_config(root, config) -> pathlib.Path:
    path = pathlib.Path(root) / ".agenticdoc" / "_autopilot" / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config, indent=2) + "\n"
    path.write_text(payload, encoding="utf-8", newline="\n")
    return path


def caps_of(root) -> tuple[int | None, int | None]:
    return dispatch_mod._read_scope_caps(pathlib.Path(root))


_MISSING = object()


def render_caps(root, task_type="reviewer", prompt="Verify the evidence.", **overrides):
    """Render one task.md with the config-derived caps wired in (the exact
    dispatch() call shape). An explicit ``read_file_cap=`` / ``read_byte_cap=``
    override wins over the config-derived value."""
    kwargs = dict(BASE_KWARGS)
    kwargs.update(overrides)
    file_cap = kwargs.pop("read_file_cap", _MISSING)
    byte_cap = kwargs.pop("read_byte_cap", _MISSING)
    if file_cap is _MISSING or byte_cap is _MISSING:
        cfg_file, cfg_byte = caps_of(root)
        if file_cap is _MISSING:
            file_cap = cfg_file
        if byte_cap is _MISSING:
            byte_cap = cfg_byte
    return dispatch_mod.render_task_md(
        task_type, prompt, **kwargs,
        read_file_cap=file_cap, read_byte_cap=byte_cap,
    )


def head_render(task_type="reviewer", prompt="Verify the evidence.", **overrides):
    kwargs = dict(BASE_KWARGS)
    kwargs.update(overrides)
    return _head_module().render_task_md(task_type, prompt, **kwargs)


# ── parse mirror (worker-mode.ts:314-320 口径) ───────────────────────────────

def parse_caps_mirror(task_md_text: str) -> tuple[int | None, int | None]:
    """Python mirror of worker-mode.ts's frontmatter cap parsing: trimmed
    line prefix match on the two keys + int(); a non-parsable / non-positive
    value leaves the field undefined (TS: Number.isFinite(v) && v > 0)."""
    file_cap: int | None = None
    byte_cap: int | None = None
    for raw in task_md_text.splitlines():
        line = raw.strip()
        if line.startswith("l2_read_file_cap:"):
            value = line[len("l2_read_file_cap:"):].strip()
            try:
                parsed = int(value)
            except ValueError:
                continue
            if parsed > 0:
                file_cap = parsed
        elif line.startswith("l2_read_byte_cap:"):
            value = line[len("l2_read_byte_cap:"):].strip()
            try:
                parsed = int(value)
            except ValueError:
                continue
            if parsed > 0:
                byte_cap = parsed
    return file_cap, byte_cap


def cap_lines(task_md_text: str) -> list[str]:
    return [
        line for line in task_md_text.splitlines()
        if line.startswith("l2_read_file_cap:") or line.startswith("l2_read_byte_cap:")
    ]


def cap_order_ok(task_md_text: str) -> bool:
    """Both cap lines sit after a bare ``read_scope:`` line and before the
    ``deny_globs:`` block (or the closing frontmatter fence)."""
    lines = task_md_text.splitlines()
    scope = next((i for i, l in enumerate(lines) if l == "read_scope:"), None)
    deny = next((i for i, l in enumerate(lines) if l == "deny_globs:"), None)
    fences = [i for i, l in enumerate(lines) if l == "---"]
    caps = [i for i, l in enumerate(lines) if l.startswith("l2_read_")]
    if scope is None or not caps or len(fences) < 2:
        return False
    upper = deny if deny is not None else fences[1]
    return all(scope < i < upper for i in caps)


# ── minimal cap replay mirror (checkReadScopeCall cap branches) ──────────────

class CapState:
    __slots__ = ("allowed_calls", "bytes_read")

    def __init__(self) -> None:
        self.allowed_calls = 0
        self.bytes_read = 0


def replay_cap(
    state: CapState,
    tool: str,
    size: int = 0,
    *,
    file_cap: int,
    byte_cap: int,
    deny_hit: bool = False,
    in_scope: bool = True,
) -> tuple[bool, str]:
    """One read-ish call against the cap branches. Precedence mirrors
    read-scope.ts: deny-glob > scope > cap-file > cap-byte. cap-file counts
    read/ls/find/grep; cap-byte charges the whole file and only for `read`."""
    if deny_hit:
        return False, "deny-glob"
    if not in_scope:
        return False, "scope"
    if state.allowed_calls >= file_cap:
        return False, "cap-file"
    charged = size if tool == "read" else 0
    if tool == "read" and state.bytes_read + charged > byte_cap:
        return False, "cap-byte"
    state.allowed_calls += 1
    state.bytes_read += charged
    return True, ""


def replay_sequence(calls, *, file_cap: int, byte_cap: int) -> list[str]:
    state = CapState()
    rules: list[str] = []
    for tool, size in calls:
        allowed, rule = replay_cap(state, tool, size, file_cap=file_cap, byte_cap=byte_cap)
        if not allowed:
            rules.append(rule)
    return rules


def first_violation_index(calls, *, file_cap: int, byte_cap: int) -> int | None:
    state = CapState()
    for index, (tool, size) in enumerate(calls, start=1):
        allowed, _ = replay_cap(state, tool, size, file_cap=file_cap, byte_cap=byte_cap)
        if not allowed:
            return index
    return None


# ── cap fallback literal scanner (AC-003) ────────────────────────────────────

_CAP_TOKENS = ("read_file_cap", "read_byte_cap", "file_cap", "byte_cap", "readcap")
_CAP_LITERALS = (8, 65536)
_ASSIGN_RE = re.compile(
    r"(?i)^\s*[A-Za-z_][A-Za-z0-9_]*cap[A-Za-z0-9_]*\s*(?::[^=\n]+)?=\s*([^\n#]*)"
)
_KWARG_RE = re.compile(
    r"(?i)\b[A-Za-z_][A-Za-z0-9_]*cap[A-Za-z0-9_]*\s*=\s*(8|65536)\b"
)


def _is_cap_name(name: str) -> bool:
    low = name.lower()
    return any(token in low for token in _CAP_TOKENS)


def _literal_ints(node: ast.AST) -> list[int]:
    found: list[int] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, int) and not isinstance(
            sub.value, bool
        ):
            found.append(sub.value)
    return found


class _CapLiteralVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.hits: list[str] = []

    @staticmethod
    def _target_name(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    def _check(self, target: ast.AST, value: ast.AST) -> None:
        name = self._target_name(target)
        if name and _is_cap_name(name):
            for lit in _literal_ints(value):
                if lit in _CAP_LITERALS:
                    self.hits.append(f"assign {name}={lit}")

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._check(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._check(node.target, node.value)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._check(node.target, node.value)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self._check(node.target, node.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        for kw in node.keywords:
            if kw.arg and _is_cap_name(kw.arg):
                for lit in _literal_ints(kw.value):
                    if lit in _CAP_LITERALS:
                        self.hits.append(f"kwarg {kw.arg}={lit}")
        self.generic_visit(node)

    def _check_defaults(self, args: ast.arguments) -> None:
        pairs = list(zip(args.args[-len(args.defaults):], args.defaults))
        pairs += [(a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is not None]
        for arg, default in pairs:
            if _is_cap_name(arg.arg):
                for lit in _literal_ints(default):
                    if lit in _CAP_LITERALS:
                        self.hits.append(f"default {arg.arg}={lit}")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_defaults(node.args)
        self.generic_visit(node)


def cap_literal_hits(source: str) -> list[str]:
    visitor = _CapLiteralVisitor()
    visitor.visit(ast.parse(source))
    hits = [f"ast: {hit}" for hit in visitor.hits]
    for number, line in enumerate(source.splitlines(), start=1):
        match = _ASSIGN_RE.match(line)
        if match and re.search(r"\b(?:8|65536)\b", match.group(1)):
            hits.append(f"text L{number}: assign")
        if _KWARG_RE.search(line):
            hits.append(f"text L{number}: kwarg")
    return hits


# ── VC-001 / AC-001 ──────────────────────────────────────────────────────────

def test_vc001_inject_and_position(tmp_path: pathlib.Path) -> None:
    root = make_project(tmp_path, {"l2_read_file_cap": 64, "l2_read_byte_cap": 2097152})
    file_lines = 0
    byte_lines = 0
    orders: list[bool] = []
    for task_type in ("verifier", "reviewer", "roadmap-writer"):
        overrides = {} if task_type != "roadmap-writer" else {"deny_globs": []}
        content = render_caps(root, task_type=task_type, **overrides)
        assert "l2_read_file_cap: 64" in content, task_type
        assert "l2_read_byte_cap: 2097152" in content, task_type
        file_lines += content.count("l2_read_file_cap: 64")
        byte_lines += content.count("l2_read_byte_cap: 2097152")
        orders.append(cap_order_ok(content))
    assert file_lines == 3 and byte_lines == 3
    assert all(orders)
    # Boundary: a single supplied field emits exactly one cap line.
    single = render_caps(
        tmp_path, task_type="reviewer",
        read_file_cap=64, read_byte_cap=None,
    )
    assert "l2_read_file_cap: 64" in single
    assert "l2_read_byte_cap:" not in single
    _verify(
        "VC-001",
        tasks=3,
        file_cap_lines=file_lines,
        byte_cap_lines=byte_lines,
        order_ok=true_str(all(orders)),
        ok=true_str(all(orders) and file_lines == 3 and byte_lines == 3),
    )


# ── VC-002 / AC-002 ──────────────────────────────────────────────────────────

def test_vc002_dispatch_e2e_parse_mirror(tmp_path: pathlib.Path) -> None:
    config = {"l2_read_file_cap": 64, "l2_read_byte_cap": 2097152}
    root = make_project(tmp_path, config)
    result = dispatch_mod.dispatch(
        root, "k1", "vc002", "reviewer", "Judge the evidence.",
        loop="feature-l3-readcap-injection:003", attempt=1,
        read_scope=[".agenticdoc/feature-l3-readcap-injection"],
    )
    assert result.ok and result.row_verified, result.reason
    text = result.task_md.read_text(encoding="utf-8")
    read_file_cap, read_byte_cap = parse_caps_mirror(text)
    equals_config = (read_file_cap, read_byte_cap) == (64, 2097152)
    fallback_used = (read_file_cap, read_byte_cap) == (
        TS_DEFAULT_FILE_CAP, TS_DEFAULT_BYTE_CAP,
    )
    assert equals_config
    assert not fallback_used
    _verify(
        "VC-002",
        readFileCap=read_file_cap,
        readByteCap=read_byte_cap,
        equals_config=true_str(equals_config),
        fallback_used=true_str(fallback_used),
        ok=true_str(equals_config and not fallback_used),
    )


# ── VC-003 / AC-003 ──────────────────────────────────────────────────────────

def test_vc003_value_follows_config_and_no_cap_literal(tmp_path: pathlib.Path) -> None:
    config = {"l2_read_file_cap": 64, "l2_read_byte_cap": 2097152}
    root = make_project(tmp_path, config)
    assert "l2_read_file_cap: 64" in render_caps(root)
    write_config(root, {"l2_read_file_cap": 20, "l2_read_byte_cap": 2097152})
    rerendered = render_caps(root)
    assert "l2_read_file_cap: 20" in rerendered
    hits = cap_literal_hits(DISPATCH_PY.read_text(encoding="utf-8"))
    assert hits == [], hits
    _verify(
        "VC-003",
        rerender_value=20,
        cap_literal_assignments=len(hits),
        ok=true_str("l2_read_file_cap: 20" in rerendered and not hits),
    )


# ── AC-004 / AC-005 / AC-006 (T-003 side; T-004 / T-006 close them) ──────────

def test_ac004_partial_derived_values_and_margins(tmp_path: pathlib.Path) -> None:
    """T-003 side of AC-004: the derived effective values (design D-006)
    flow through the injection unchanged, and they keep >= 2x margin over
    the measured dossier envelope (recomputed here from the plan's recorded
    facts). The project config lift + derivation script are T-004's."""
    root = make_project(
        tmp_path, {"l2_read_file_cap": DERIVED_FILE_CAP, "l2_read_byte_cap": DERIVED_BYTE_CAP}
    )
    content = render_caps(root, task_type="verifier")
    renders = (
        f"l2_read_file_cap: {DERIVED_FILE_CAP}" in content
        and f"l2_read_byte_cap: {DERIVED_BYTE_CAP}" in content
    )
    margins = (
        DERIVED_FILE_CAP >= 2 * MEASURED_MAX_CALLS
        and DERIVED_BYTE_CAP >= 2 * MEASURED_MAX_BYTES
    )
    assert renders and margins
    _verify(
        "AC-004",  # T-003 partial; full AC-004 (project config) is T-004
        file_cap=DERIVED_FILE_CAP,
        byte_cap=DERIVED_BYTE_CAP,
        max_calls=MEASURED_MAX_CALLS,
        max_bytes=MEASURED_MAX_BYTES,
        renders=true_str(renders),
        ge_2x=true_str(margins),
        ok=true_str(renders and margins),
    )


def test_ac005_partial_measured_envelope_replay() -> None:
    """T-003 side of AC-005: the measured dossier envelope (max_calls /
    max_bytes from the plan's recorded facts) replays with ZERO cap
    rejections under the derived caps, while the same envelope under the
    current 8 / 65536 defaults does reject (non-vacuous). The real per-file
    dossier replay with the true TS function is T-004 (plan F-P4)."""
    per_call = MEASURED_MAX_BYTES // MEASURED_MAX_CALLS + 1
    envelope = [("read", per_call)] * MEASURED_MAX_CALLS
    assert per_call * MEASURED_MAX_CALLS >= MEASURED_MAX_BYTES
    derived_rules = replay_sequence(
        envelope, file_cap=DERIVED_FILE_CAP, byte_cap=DERIVED_BYTE_CAP
    )
    tight_rules = replay_sequence(
        envelope, file_cap=TS_DEFAULT_FILE_CAP, byte_cap=TS_DEFAULT_BYTE_CAP
    )
    assert derived_rules == [], derived_rules
    assert tight_rules, "envelope under 8/65536 must reject (non-vacuous)"
    _verify(
        "AC-005",  # T-003 envelope partial; full dossier replay is T-004
        max_calls=MEASURED_MAX_CALLS,
        max_bytes=MEASURED_MAX_BYTES,
        derived_rejections=len(derived_rules),
        tight_rejections=len(tight_rules),
        ok=true_str(not derived_rules and bool(tight_rules)),
    )


def test_ac006_partial_dispatch_side_caps(tmp_path: pathlib.Path) -> None:
    """T-003 side of AC-006: a task produced by the conductor dispatch
    primitive carries both cap lines with values equal to the config — the
    task.md half of "restart then real dispatch". The restart + real
    conductor dispatch half is T-006 (design D-009)."""
    config = {"l2_read_file_cap": 128, "l2_read_byte_cap": 4194304}
    root = make_project(tmp_path, config)
    result = dispatch_mod.dispatch(
        root, "k1", "ac006", "roadmap-writer", "Propose the roadmap.",
        loop="roadmap:ac006", attempt=1,
    )
    assert result.ok and result.row_verified
    text = result.task_md.read_text(encoding="utf-8")
    parsed = parse_caps_mirror(text)
    equals_config = parsed == (128, 4194304)
    assert equals_config
    _verify(
        "AC-006",  # T-003 dispatch-side partial; restart half is T-006
        dispatched_tasks=1,
        cap_lines=len(cap_lines(text)),
        cap_equals_config=true_str(equals_config),
        restart_half="deferred_T-006",
        ok=true_str(equals_config and len(cap_lines(text)) == 2),
    )


# ── VC-007 / AC-007 (fail-closed: missing config) ────────────────────────────

def test_vc007_missing_config_byte_identical(tmp_path: pathlib.Path) -> None:
    root = make_project(tmp_path, None, write_config=False)
    content = render_caps(root)
    expected = head_render()
    identical = content.encode("utf-8") == expected.encode("utf-8")
    config_created = (root / ".agenticdoc" / "_autopilot").exists()
    assert caps_of(root) == (None, None)
    assert identical
    assert cap_lines(content) == []
    assert config_created is False
    _verify(
        "VC-007",
        byte_identical=true_str(identical),
        cap_lines=len(cap_lines(content)),
        config_created=true_str(config_created),
        ok=true_str(identical and not cap_lines(content) and not config_created),
    )


# ── VC-008 / AC-008 (fail-closed: missing fields) ────────────────────────────

def test_vc008_missing_fields_byte_identical(tmp_path: pathlib.Path) -> None:
    root = make_project(tmp_path, {"enabled": True, "paused": False})
    content = render_caps(root)
    expected = head_render()
    identical = content.encode("utf-8") == expected.encode("utf-8")
    result = dispatch_mod.dispatch(
        root, "k1", "vc008", "reviewer", "Judge.",
        loop="feature-l3-readcap-injection:003", attempt=1,
        read_scope=[".agenticdoc/feature-l3-readcap-injection"],
    )
    rendered = result.task_md.read_text(encoding="utf-8")
    assert caps_of(root) == (None, None)
    assert identical
    assert cap_lines(content) == []
    assert result.ok and result.row_verified
    assert cap_lines(rendered) == []
    _verify(
        "VC-008",
        byte_identical=true_str(identical),
        cap_lines=len(cap_lines(rendered)),
        dispatch_ok=true_str(result.ok and result.row_verified),
        ok=true_str(identical and result.ok and result.row_verified),
    )


# ── VC-009 / AC-009 (fail-closed: invalid / unreadable config) ───────────────

def test_vc009_invalid_config_no_new_failure_mode(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases: list[tuple[str, pathlib.Path, bool]] = []
    root_zero = make_project(tmp_path / "zero", {"l2_read_file_cap": 0})
    cases.append(("cap-zero", root_zero, False))
    root_broken = make_project(tmp_path / "broken", "{not json")
    cases.append(("json-broken", root_broken, False))
    root_raising = make_project(tmp_path / "raising", {"l2_read_file_cap": 64})
    cases.append(("load-config-raises", root_raising, True))

    # config.py stays fail-closed for the whole file (CLI-facing contract).
    contract_ok = False
    for name, root, _ in cases[:2]:
        try:
            autopilot_config.load_config(root)
        except autopilot_config.ConfigError:
            contract_ok = True
    assert contract_ok
    assert isinstance(autopilot_config.ConfigError, type)

    exceptions = 0
    dispatch_ok = 0
    total_cap_lines = 0
    observed: list[str] = []
    for name, root, raising in cases:
        try:
            if raising:
                def _raise(_project_root):
                    raise RuntimeError("boom")

                monkeypatch.setattr(autopilot_config, "load_config", _raise)
            got = caps_of(root)
            assert got == (None, None), (name, got)
            result = dispatch_mod.dispatch(
                root, "k1", f"vc009-{name}", "reviewer", "Judge.",
                loop="feature-l3-readcap-injection:003", attempt=1,
                read_scope=[".agenticdoc/feature-l3-readcap-injection"],
            )
            assert result.ok and result.row_verified, (name, result.reason)
            rendered_lines = cap_lines(result.task_md.read_text(encoding="utf-8"))
            assert rendered_lines == [], (name, rendered_lines)
            dispatch_ok += 1
            total_cap_lines += len(rendered_lines)
            observed.append(name)
        except Exception as exc:  # noqa: BLE001 — the test reports, never dies
            exceptions += 1
            observed.append(f"{name}:EXC:{exc!r}")
        finally:
            monkeypatch.undo()
    assert exceptions == 0, observed
    assert dispatch_ok == len(cases)
    _verify(
        "VC-009",
        cases=len(cases),
        exceptions=exceptions,
        dispatch_ok=dispatch_ok,
        cap_lines=total_cap_lines,
        config_contract_unchanged=true_str(contract_ok),
        ok=true_str(exceptions == 0 and dispatch_ok == len(cases) and total_cap_lines == 0),
    )


# ── VC-010 / AC-010 (reverse 1: small cap still blocks) ──────────────────────

def test_vc010_small_cap_still_blocks(tmp_path: pathlib.Path) -> None:
    __tracebackhide__ = True
    root = make_project(tmp_path, {"l2_read_file_cap": 2, "l2_read_byte_cap": 150})
    content = render_caps(root, task_type="verifier")
    rendered = "l2_read_file_cap: 2" in content and "l2_read_byte_cap: 150" in content
    assert rendered
    # Pin the replay mirror to the frozen T-002 render artifact: the cap
    # lines parsed out of it must reproduce that artifact byte for byte.
    pinned = PIN_RENDER.read_text(encoding="utf-8")
    assert "l2_read_file_cap: 64" in pinned and "l2_read_byte_cap: 2097152" in pinned
    # 3rd read-ish call is blocked by the file cap, exactly as read-scope.ts.
    calls = [("read", 10), ("ls", 0), ("grep", 0), ("find", 0)]
    cap_file_at = first_violation_index(calls, file_cap=2, byte_cap=150)
    assert cap_file_at == 3, cap_file_at
    # Any read of more than 150 B is blocked by the byte cap.
    state = CapState()
    allowed, rule = replay_cap(state, "read", 151, file_cap=2, byte_cap=150)
    assert not allowed and rule == "cap-byte", (allowed, rule)
    # Exactly at the caps is still allowed (the cap is an upper bound).
    allowed_edge, _ = replay_cap(state, "read", 0, file_cap=2, byte_cap=150)
    assert allowed_edge
    _verify(
        "VC-010",
        cap_file_at=cap_file_at,
        cap_byte_over=150,
        rendered=true_str(rendered),
        ok=true_str(rendered and cap_file_at == 3 and not allowed and rule == "cap-byte"),
    )


# ── VC-011 / AC-011 (reverse 2: invalid values never "unlimited") ────────────

def test_vc011_invalid_values_not_unlimited(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid_values = [0, -1, 3.5, True, "9" * 21]
    fallback_aligned = (
        autopilot_config.DEFAULT_CONFIG["l2_read_file_cap"] == TS_DEFAULT_FILE_CAP
        and autopilot_config.DEFAULT_CONFIG["l2_read_byte_cap"] == TS_DEFAULT_BYTE_CAP
    )
    assert fallback_aligned
    unlimited_cases = 0
    observed: list[str] = []
    for index, value in enumerate(invalid_values):
        root = make_project(tmp_path / f"case{index}", {})
        for field, other in (
            ("l2_read_file_cap", "l2_read_byte_cap"),
            ("l2_read_byte_cap", "l2_read_file_cap"),
        ):
            payload = {other: 2097152 if other == "l2_read_byte_cap" else 64}
            payload[field] = value
            monkeypatch.setattr(autopilot_config, "load_config", lambda _root, _p=payload: dict(_p))
            file_cap, byte_cap = caps_of(root)
            assert getattr_from_pair(field, file_cap, byte_cap) is None, (value, field)
            content = render_caps(root, task_type="reviewer")
            assert f"{field}:" not in content, (value, field)
            other_value = 2097152 if other == "l2_read_byte_cap" else 64
            if other_value <= 2097152:
                assert f"{other}: {other_value}" in content, (value, field)
            monkeypatch.undo()
        observed.append(f"{value!r}:degraded")
    # Fallback defaults must still block: 9th read-ish call -> cap-file;
    # a read of 65537 B -> cap-byte.
    fallback_calls = [("read", 10)] * 9
    cap_file_at = first_violation_index(
        fallback_calls, file_cap=TS_DEFAULT_FILE_CAP, byte_cap=TS_DEFAULT_BYTE_CAP
    )
    state = CapState()
    allowed, rule = replay_cap(
        state, "read", TS_DEFAULT_BYTE_CAP + 1,
        file_cap=TS_DEFAULT_FILE_CAP, byte_cap=TS_DEFAULT_BYTE_CAP,
    )
    still_blocks = (
        cap_file_at == TS_DEFAULT_FILE_CAP + 1
        and not allowed
        and rule == "cap-byte"
    )
    assert still_blocks, (cap_file_at, allowed, rule)
    # Documented "unlimited" path count: zero invalid values are treated as
    # "no cap" (every invalid field degrades to None -> TS default applies).
    assert unlimited_cases == 0
    _verify(
        "VC-011",
        invalid_cases=len(invalid_values),
        unlimited_cases=unlimited_cases,
        fallback_defaults=true_str(fallback_aligned),
        still_blocks=true_str(still_blocks),
        ok=true_str(unlimited_cases == 0 and fallback_aligned and still_blocks),
    )


def getattr_from_pair(field: str, file_cap, byte_cap):
    return file_cap if field == "l2_read_file_cap" else byte_cap


# ── VC-012 / AC-012 (reverse 3: L3 verdict still `below`) ────────────────────

L3_TASK_KEY = "ap-k1-l3-a1"


def _write_l3_output(root: pathlib.Path, text: str) -> None:
    out_dir = pathlib.Path(root) / ".agenticdoc" / "k1" / "workers" / L3_TASK_KEY
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "output.md").write_text(text, encoding="utf-8", newline="\n")


def test_vc012_l3_criteria_still_below(tmp_path: pathlib.Path) -> None:
    root = make_project(
        tmp_path, {"l2_read_file_cap": DERIVED_FILE_CAP, "l2_read_byte_cap": DERIVED_BYTE_CAP}
    )
    content = render_caps(root, task_type="reviewer")
    assert f"l2_read_file_cap: {DERIVED_FILE_CAP}" in content

    qg_pass = "## Quality Gate Report\n| VC | Verdict |\n| VC-001 | PASS |\n"
    qg_fail = "## Quality Gate Report\n| VC | Verdict |\n| VC-001 | FAIL |\n"
    achieved = "## Achieved\nDone.\n"
    # (a) missing `## Achieved` -> below
    _write_l3_output(root, qg_pass)
    missing_section = conductor._parse_l3_output(root, "k1", 1)
    # (b) a FAIL row in the QG section -> below
    _write_l3_output(root, qg_pass + qg_fail.replace("## Quality Gate Report\n", "") + achieved)
    fail_row = conductor._parse_l3_output(root, "k1", 1)
    # (c) control: both sections, no FAIL row -> meets (not vacuous)
    _write_l3_output(root, qg_pass + achieved)
    healthy = conductor._parse_l3_output(root, "k1", 1)
    assert missing_section == "below", missing_section
    assert fail_row == "below", fail_row
    assert healthy == "meets", healthy
    _verify(
        "VC-012",
        missing_section=missing_section,
        fail_row=fail_row,
        ok=true_str(missing_section == "below" and fail_row == "below" and healthy == "meets"),
    )


# ── support invariants (AC-007/008 left-end binding, AC-003/011 defaults) ────

def test_baseline_left_end_bound() -> None:
    """The frozen pre-fix renderer equals the git HEAD blob (sha256) — the
    byte-identical comparisons above are anchored to the real left end."""
    if not HEAD_DISPATCH.is_file():
        pytest.skip("frozen baseline copy not reachable (portable fallback in use)")
    frozen = hashlib.sha256(HEAD_DISPATCH.read_bytes()).hexdigest()
    git_blob = hashlib.sha256(_git("show", f"HEAD:{DISPATCH_RELATIVE}")).hexdigest()
    assert frozen == git_blob
    head = _head_module()
    assert "read_file_cap" not in inspect.signature(head.render_task_md).parameters
    assert dispatch_mod._read_scope_caps.__doc__ is not None


def test_render_task_md_signature_shape() -> None:
    head = _head_module()
    worktree_params = list(inspect.signature(dispatch_mod.render_task_md).parameters)
    head_params = list(inspect.signature(head.render_task_md).parameters)
    extra = [name for name in worktree_params if name not in head_params]
    removed = [name for name in head_params if name not in worktree_params]
    by_name = inspect.signature(dispatch_mod.render_task_md).parameters
    assert extra == ["read_file_cap", "read_byte_cap"], extra
    assert removed == [], removed
    assert all(by_name[name].default is None for name in extra)
    assert str(inspect.signature(dispatch_mod.dispatch)) == str(
        inspect.signature(head.dispatch)
    )
    assert [f.name for f in dataclasses.fields(dispatch_mod.DispatchResult)] == [
        f.name for f in dataclasses.fields(head.DispatchResult)
    ]


def test_existing_regression_files_untouched() -> None:
    """AC-015 / D-012: the two pre-existing regression files (golden left end
    for AC-007/AC-008) are byte-untouched vs git HEAD. Assertion-only (no
    [VERIFY] line): the hashes are recorded in the runner's result JSON."""
    for name in ("test_autopilot_config.py", "test_autopilot_dispatch.py"):
        live = hashlib.sha256((MODULE_DIR / name).read_bytes()).hexdigest()
        blob = hashlib.sha256(
            _git("show", f"HEAD:packages/multi-workers/{name}")
        ).hexdigest()
        assert live == blob, (name, live, blob)


# ── VC-015 / AC-015 (suite counts + fail-closed reverse cases) ───────────────

_VC015_FACTS: dict[str, dict] = {}


def test_vc015_fail_closed_suite_counts() -> None:
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    new_tests = re.findall(r"^def (test_\w+)\(", source, flags=re.MULTILINE)
    covered_ac = [ac for ac in SPEC_AC_RANGE if AC_COVERAGE.get(ac)]
    unknown = [name for names in AC_COVERAGE.values() for name in names if name not in new_tests]
    fail_closed = [name for name in FAIL_CLOSED_CASES if name in new_tests]
    assert len(new_tests) >= 12, len(new_tests)
    assert covered_ac == SPEC_AC_RANGE, covered_ac
    assert not unknown, unknown
    assert len(fail_closed) >= 3, fail_closed
    assert "AC-015" in AC_COVERAGE
    _VC015_FACTS["facts"] = {
        "new_tests": len(new_tests),
        "ac_covered": len(covered_ac),
        "fail_closed_cases": len(fail_closed),
    }


@pytest.fixture(scope="session", autouse=True)
def _emit_vc015_after_session(request: pytest.Session) -> None:
    """Emit VC-015 once the whole session is over, with the REAL session
    failure count (``request.session.testsfailed``) — the authoritative
    ``pytest_failed``. Emitted only when this module's facts were collected;
    a missing line makes the runner fail closed."""
    yield
    facts = _VC015_FACTS.get("facts")
    if not facts:
        return
    failed = request.session.testsfailed
    ok = failed == 0 and facts["ac_covered"] == 12 and facts["fail_closed_cases"] >= 3
    _verify(
        "VC-015",
        pytest_failed=failed,
        new_tests=facts["new_tests"],
        ac_covered=facts["ac_covered"],
        fail_closed_cases=facts["fail_closed_cases"],
        ok=true_str(ok),
    )
