"""test_autopilot_verify_cwd_table.py — T-09 (mw-autopilot-verify-cli).

cwd / placeholder truth table + E2 shape regression (AC-013 / AC-014,
VC-013 / VC-014).

The table drives the *consumer seam* the S4 verify stage actually uses:
``conductor._xkey_target_root`` (cwd) followed by
``conductor._xkey_verify_argv`` (argv) inside one ``TargetConfigError``
try/except — the exact prologue of ``conductor._xkey_run_verify``. Every row
asserts the exact expanded argv (element by element), the exact cwd, or the
exact failure kind + text shape, and that the verification runner was never
reached on a failure row. The runner here is a spy standing in for
``xkey.run_verification``; the real ticket/ledger fail-closed behaviour is
already covered end-to-end by ``test_autopilot_xkey_cwd.py``.

Write surface: this file only. No implementation file is touched; the
toolchain renderer is proven unchanged by running the shared parity fixture
runner from ``test_common_target_config.py`` in this same test run.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import mw_common  # noqa: E402
from autopilot import config, conductor  # noqa: E402


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


# ── fixtures: three-root partition / dual / single target.yml shapes ─────────

_PARTITION_YML = """\
active: partition
partition:
  parent: '{parent}'
  partition: '{partition}'
  roots:
    sdk: '{sdk}'
"""

_DUAL_YML = """\
active: dual
dual:
  game: '{game}'
  engine: '{engine}'
"""

_SINGLE_YML = "active: single\n"

_ROOTS = ("control", "parent", "partition", "sdk", "game", "engine")


def _fixture(tmp_path: pathlib.Path, mode: str) -> tuple[pathlib.Path, dict]:
    control = tmp_path / "control"
    parent = tmp_path / "parent"
    partition = tmp_path / "shard"
    sdk = tmp_path / "sdk"
    game = tmp_path / "game"
    engine = tmp_path / "engine"
    roots = {
        "control": control,
        "parent": parent,
        "partition": partition,
        "sdk": sdk,
        "game": game,
        "engine": engine,
    }
    for name in _ROOTS:
        roots[name].mkdir(parents=True, exist_ok=True)
    yml = control / ".agenticdoc" / "target.yml"
    yml.parent.mkdir(parents=True, exist_ok=True)
    if mode == "partition":
        yml.write_text(
            _PARTITION_YML.format(
                parent=parent.as_posix(),
                partition=partition.as_posix(),
                sdk=sdk.as_posix(),
            ),
            encoding="utf-8",
        )
    elif mode == "dual":
        yml.write_text(
            _DUAL_YML.format(game=game.as_posix(), engine=engine.as_posix()),
            encoding="utf-8",
        )
    elif mode == "single":
        yml.write_text(_SINGLE_YML, encoding="utf-8")
    else:  # pragma: no cover - table is internal
        raise AssertionError(f"unknown mode {mode!r}")
    return control, roots


def _expand(expected: list[str], roots: dict) -> list[str]:
    """Resolve the table's ``ROOT:<name>`` markers to real resolved paths."""
    out: list[str] = []
    for element in expected:
        if element.startswith("ROOT:"):
            out.append(str(roots[element[5:]].resolve()))
        else:
            out.append(element)
    return out


class _VerifySpy:
    """Stands in for ``xkey.run_verification``: records every run."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str]] = []

    def __call__(self, argv: list[str], cwd: str) -> None:
        self.calls.append((list(argv), cwd))


def _consume(
    control: pathlib.Path, cfg: dict, target_config: dict, spy: _VerifySpy
) -> tuple[mw_common.TargetConfigError | None, list[str] | None, str | None]:
    """Mirror ``conductor._xkey_run_verify``'s fail-closed prologue: resolve
    cwd + render argv inside one try/except; the runner is only reached when
    both succeed."""
    try:
        workspace = conductor._xkey_target_root(control, cfg, target_config)
        argv = conductor._xkey_verify_argv(cfg, target_config)
    except mw_common.TargetConfigError as exc:
        return exc, None, None
    spy(list(argv), str(workspace))
    return None, argv, str(workspace)


# ── the truth table ───────────────────────────────────────────────────────────
#
# Columns: mode x selector x argv template. ``cwd`` names the expected root;
# ``expect`` holds the exact expanded argv with ROOT:<name> markers; ``error``
# holds (kind, text-shape substrings). ``argv_kind`` drives the coverage meta
# test: none / single / multi / unknown / embedded.

_ROWS: list[dict] = [
    # ---- partition (control != partition != parent, all sibling roots) ----
    {
        "id": "partition-auto-0ph",
        "mode": "partition",
        "selector": "",
        "argv": ["python", "-m", "pytest", "-q"],
        "argv_kind": "none",
        "cwd": "partition",
        "expect": ["python", "-m", "pytest", "-q"],
    },
    {
        "id": "partition-auto-1ph-control",
        "mode": "partition",
        "selector": "",
        "argv": ["pytest", "{control}"],
        "argv_kind": "single",
        "cwd": "partition",
        "expect": ["pytest", "ROOT:control"],
    },
    {
        "id": "partition-control-1ph",
        "mode": "partition",
        "selector": "control",
        "argv": ["{control}"],
        "argv_kind": "single",
        "cwd": "control",
        "expect": ["ROOT:control"],
    },
    {
        "id": "partition-partition-1ph",
        "mode": "partition",
        "selector": "partition",
        "argv": ["{partition}"],
        "argv_kind": "single",
        "cwd": "partition",
        "expect": ["ROOT:partition"],
    },
    {
        "id": "partition-parent-1ph",
        "mode": "partition",
        "selector": "parent",
        "argv": ["{parent}"],
        "argv_kind": "single",
        "cwd": "parent",
        "expect": ["ROOT:parent"],
    },
    {
        "id": "partition-rootname-sdk-multi",
        "mode": "partition",
        "selector": "sdk",
        "argv": ["{control}", "{parent}", "{partition}", "{sdk}"],
        "argv_kind": "multi",
        "cwd": "sdk",
        "expect": ["ROOT:control", "ROOT:parent", "ROOT:partition", "ROOT:sdk"],
    },
    {
        "id": "partition-auto-multi",
        "mode": "partition",
        "selector": "",
        "argv": ["{control}", "{partition}"],
        "argv_kind": "multi",
        "cwd": "partition",
        "expect": ["ROOT:control", "ROOT:partition"],
    },
    {
        "id": "partition-auto-undefined-game",
        "mode": "partition",
        "selector": "",
        "argv": ["{game}"],
        "argv_kind": "unknown",
        "error": (
            "missing-field",
            [
                "undefined placeholder '{game}'",
                "verify argv defines: {control}, {parent}, {partition}, {sdk}",
                "{game}",
            ],
        ),
    },
    {
        "id": "partition-auto-undefined-python",
        "mode": "partition",
        "selector": "",
        "argv": ["python", "{python}"],
        "argv_kind": "unknown",
        "error": (
            "missing-field",
            [
                "undefined placeholder '{python}'",
                "verify argv defines: {control}, {parent}, {partition}, {sdk}",
                "{python}",
            ],
        ),
    },
    {
        "id": "partition-auto-embedded-partition",
        "mode": "partition",
        "selector": "",
        "argv": ["{partition}/tests"],
        "argv_kind": "embedded",
        "error": (
            "missing-field",
            [
                "placeholder must occupy a whole argv element",
                "{partition}/tests",
            ],
        ),
    },
    {
        "id": "partition-auto-embedded-control",
        "mode": "partition",
        "selector": "",
        "argv": ["x{control}"],
        "argv_kind": "embedded",
        "error": (
            "missing-field",
            [
                "placeholder must occupy a whole argv element",
                "x{control}",
            ],
        ),
    },
    {
        "id": "partition-unknown-selector-bogus",
        "mode": "partition",
        "selector": "bogus",
        "argv": ["{control}"],
        "argv_kind": "single",
        "error": (
            "invalid-config",
            [
                "xkey_verify_cwd:",
                "unknown root selector 'bogus'",
                "valid: control, partition, parent, sdk",
            ],
        ),
    },
    {
        "id": "partition-unconfigured-selector-engine",
        "mode": "partition",
        "selector": "engine",
        "argv": ["{engine}"],
        "argv_kind": "single",
        "error": (
            "invalid-config",
            [
                "unknown root selector 'engine'",
                "valid: control, partition, parent, sdk",
            ],
        ),
    },
    # ---- dual (default cwd = game root) ----
    {
        "id": "dual-auto-0ph",
        "mode": "dual",
        "selector": "",
        "argv": ["python", "-m", "pytest"],
        "argv_kind": "none",
        "cwd": "game",
        "expect": ["python", "-m", "pytest"],
    },
    {
        "id": "dual-auto-game-1ph",
        "mode": "dual",
        "selector": "",
        "argv": ["{game}"],
        "argv_kind": "single",
        "cwd": "game",
        "expect": ["ROOT:game"],
    },
    {
        "id": "dual-game-1ph",
        "mode": "dual",
        "selector": "game",
        "argv": ["{game}"],
        "argv_kind": "single",
        "cwd": "game",
        "expect": ["ROOT:game"],
    },
    {
        "id": "dual-engine-1ph",
        "mode": "dual",
        "selector": "engine",
        "argv": ["{engine}"],
        "argv_kind": "single",
        "cwd": "engine",
        "expect": ["ROOT:engine"],
    },
    {
        "id": "dual-control-multi",
        "mode": "dual",
        "selector": "control",
        "argv": ["{control}", "{game}", "{engine}"],
        "argv_kind": "multi",
        "cwd": "control",
        "expect": ["ROOT:control", "ROOT:game", "ROOT:engine"],
    },
    {
        "id": "dual-auto-undefined-partition",
        "mode": "dual",
        "selector": "",
        "argv": ["{partition}"],
        "argv_kind": "unknown",
        "error": (
            "missing-field",
            [
                "undefined placeholder '{partition}'",
                "verify argv defines: {control}, {game}, {engine}, {uproject}",
                "{partition}",
            ],
        ),
    },
    {
        "id": "dual-auto-embedded-game",
        "mode": "dual",
        "selector": "",
        "argv": ["{game}/Binaries"],
        "argv_kind": "embedded",
        "error": (
            "missing-field",
            [
                "placeholder must occupy a whole argv element",
                "{game}/Binaries",
            ],
        ),
    },
    {
        "id": "dual-unknown-selector-parent",
        "mode": "dual",
        "selector": "parent",
        "argv": ["{control}"],
        "argv_kind": "single",
        "error": (
            "invalid-config",
            [
                "unknown root selector 'parent'",
                "valid: control, game, engine",
            ],
        ),
    },
    {
        "id": "dual-unknown-selector-partition",
        "mode": "dual",
        "selector": "partition",
        "argv": ["{control}"],
        "argv_kind": "single",
        "error": (
            "invalid-config",
            [
                "unknown root selector 'partition'",
                "valid: control, game, engine",
            ],
        ),
    },
    # ---- single (default cwd = control root; game_root == control_root) ----
    {
        "id": "single-auto-0ph",
        "mode": "single",
        "selector": "",
        "argv": ["pytest", "-q"],
        "argv_kind": "none",
        "cwd": "control",
        "expect": ["pytest", "-q"],
    },
    {
        "id": "single-control-1ph",
        "mode": "single",
        "selector": "control",
        "argv": ["{control}"],
        "argv_kind": "single",
        "cwd": "control",
        "expect": ["ROOT:control"],
    },
    {
        "id": "single-auto-game-is-control",
        "mode": "single",
        "selector": "",
        "argv": ["{game}"],
        "argv_kind": "single",
        "cwd": "control",
        "expect": ["ROOT:control"],
    },
    {
        "id": "single-game-selector-is-control",
        "mode": "single",
        "selector": "game",
        "argv": ["{game}"],
        "argv_kind": "single",
        "cwd": "control",
        "expect": ["ROOT:control"],
    },
    {
        "id": "single-auto-undefined-partition",
        "mode": "single",
        "selector": "",
        "argv": ["{partition}"],
        "argv_kind": "unknown",
        "error": (
            "missing-field",
            [
                "undefined placeholder '{partition}'",
                "verify argv defines: {control}, {game}, {uproject}",
                "{partition}",
            ],
        ),
    },
    {
        "id": "single-auto-undefined-engine",
        "mode": "single",
        "selector": "",
        "argv": ["{engine}"],
        "argv_kind": "unknown",
        "error": (
            "missing-field",
            [
                "undefined placeholder '{engine}'",
                "verify argv defines: {control}, {game}, {uproject}",
                "{engine}",
            ],
        ),
    },
    {
        "id": "single-unknown-selector-partition",
        "mode": "single",
        "selector": "partition",
        "argv": ["{control}"],
        "argv_kind": "single",
        "error": (
            "invalid-config",
            [
                "unknown root selector 'partition'",
                "valid: control, game",
            ],
        ),
    },
    {
        "id": "single-auto-embedded-control",
        "mode": "single",
        "selector": "",
        "argv": ["{control}/x"],
        "argv_kind": "embedded",
        "error": (
            "missing-field",
            [
                "placeholder must occupy a whole argv element",
                "{control}/x",
            ],
        ),
    },
]


def test_truth_table_covers_required_dimensions() -> None:
    """Non-hollow guard: the table really spans mode x selector x argv kind."""
    assert len(_ROWS) >= 18, f"truth table has only {len(_ROWS)} rows"
    modes = {row["mode"] for row in _ROWS}
    assert modes == {"single", "dual", "partition"}, modes
    for mode in modes:
        selectors = {row["selector"] for row in _ROWS if row["mode"] == mode}
        # "" (auto) plus the enumerated root names the shell advertises.
        assert "" in selectors, (mode, selectors)
        assert {"control", "partition", "parent"} <= selectors or mode != "partition", (
            mode,
            selectors,
        )
    kinds = {row["argv_kind"] for row in _ROWS}
    assert kinds == {"none", "single", "multi", "unknown", "embedded"}, kinds
    modes_with_unknown = {row["mode"] for row in _ROWS if row["argv_kind"] == "unknown"}
    assert modes_with_unknown == {"single", "dual", "partition"}, modes_with_unknown
    modes_with_embedded = {
        row["mode"] for row in _ROWS if row["argv_kind"] == "embedded"
    }
    assert modes_with_embedded == {"single", "dual", "partition"}, modes_with_embedded
    _verify(
        "VC-013/014",
        table_rows=len(_ROWS),
        modes=sorted(modes),
        argv_kinds=sorted(kinds),
    )


@pytest.mark.parametrize("row", _ROWS, ids=[row["id"] for row in _ROWS])
def test_verify_cwd_placeholder_truth_table(
    tmp_path: pathlib.Path, row: dict
) -> None:
    control, roots = _fixture(tmp_path, row["mode"])
    target_config = mw_common.load_target_config(control, env={})
    assert target_config["mode"] == row["mode"], row["id"]
    cfg = config.default_config()
    cfg["xkey_verify_cwd"] = row["selector"]
    cfg["xkey_verify_cmd"] = list(row["argv"])

    spy = _VerifySpy()
    exc, argv, cwd = _consume(control, cfg, target_config, spy)

    if "error" in row:
        assert exc is not None, f"{row['id']}: expected {row['error']}, got {argv}"
        kind, contains = row["error"]
        assert exc.kind == kind, f"{row['id']}: kind {exc.kind!r} != {kind!r}: {exc}"
        for part in contains:
            assert part in str(exc), f"{row['id']}: {part!r} not in {str(exc)!r}"
        assert spy.calls == [], f"{row['id']}: verify must not run on a failure row"
    else:
        assert exc is None, f"{row['id']}: unexpected {exc.kind}: {exc}"
        expected_cwd = str(roots[row["cwd"]].resolve())
        expected_argv = _expand(row["expect"], roots)
        assert cwd == expected_cwd, f"{row['id']}: cwd {cwd!r} != {expected_cwd!r}"
        assert argv == expected_argv, f"{row['id']}: argv {argv!r} != {expected_argv!r}"
        assert spy.calls == [(expected_argv, expected_cwd)], row["id"]

    _verify(
        "VC-013/014",
        row=row["id"],
        mode=row["mode"],
        selector=row["selector"] or "auto",
        argv_kind=row["argv_kind"],
        outcome="fail-closed" if exc is not None else "expanded",
    )


# ── {control} is a verify-argv-only token, toolchain semantics untouched ─────


def test_control_token_is_verify_only(tmp_path: pathlib.Path) -> None:
    """``{control}`` is accepted by render_argv and refused by the toolchain
    renderer (which defines only {parent}/{partition}/{<root name>})."""
    control, roots = _fixture(tmp_path, "partition")
    target_config = mw_common.load_target_config(control, env={})

    assert mw_common.render_argv(["{control}"], target_config) == [
        str(roots["control"].resolve())
    ]

    with pytest.raises(mw_common.TargetConfigError) as excinfo:
        mw_common.render_toolchain_command("build {control}", target_config)
    assert excinfo.value.kind == "missing-field"
    text = str(excinfo.value)
    assert "toolchain command references undefined placeholder '{control}'" in text
    defines = text.split("partition mode defines:", 1)[1].split(")", 1)[0]
    assert "{parent}" in defines and "{partition}" in defines and "{sdk}" in defines
    assert "{control}" not in defines
    _verify(
        "VC-014",
        control_token_verify_argv="accepted",
        control_token_toolchain="missing-field",
    )


def test_toolchain_unknown_placeholder_passthrough_unchanged(
    tmp_path: pathlib.Path,
) -> None:
    """The pre-existing dual/single quirk (undefined placeholder passes
    through verbatim) is preserved; verify argv itself stays fail-closed."""
    control, _roots = _fixture(tmp_path, "dual")
    target_config = mw_common.load_target_config(control, env={})
    assert (
        mw_common.render_toolchain_command("run {python}", target_config)
        == "run {python}"
    )
    with pytest.raises(mw_common.TargetConfigError) as excinfo:
        mw_common.render_argv(["{python}"], target_config)
    assert excinfo.value.kind == "missing-field"
    assert "undefined placeholder '{python}'" in str(excinfo.value)
    _verify(
        "VC-014",
        toolchain_unknown_passthrough="verbatim",
        verify_argv_unknown="missing-field",
    )


def test_unconfigured_token_reports_mode_and_element(tmp_path: pathlib.Path) -> None:
    """A token that exists in the mode's set but has no configured root
    (dual without an engine) fails closed with the "not configured" shape."""
    control = tmp_path / "control"
    game = tmp_path / "game"
    control.mkdir()
    game.mkdir()
    (control / ".agenticdoc").mkdir(parents=True)
    (control / ".agenticdoc" / "target.yml").write_text(
        f"active: dual\ndual:\n  game: '{game.as_posix()}'\n", encoding="utf-8"
    )
    target_config = mw_common.load_target_config(control, env={})
    assert target_config["mode"] == "dual"
    assert target_config["engine_root"] is None
    with pytest.raises(mw_common.TargetConfigError) as excinfo:
        mw_common.render_argv(["{engine}"], target_config)
    assert excinfo.value.kind == "missing-field"
    text = str(excinfo.value)
    assert "references '{engine}' but it is not configured in dual mode" in text
    assert "{engine}" in text
    _verify("VC-014", unconfigured_token="engine", kind=excinfo.value.kind)


# ── E2 shape regression (active: partition, control != partition) ────────────

_E2_PARTITION = pathlib.Path(r"H:\git\E2Feature")
_E2_PARENT = pathlib.Path(r"E:\UEMigrator")


def test_e2_shape_partition_control_distinct(tmp_path: pathlib.Path) -> None:
    """Always-on E2 shape: ``active: partition`` with control/partition/parent
    three distinct sibling roots. The degenerate control == partition case
    (see test_autopilot_xkey_cwd.py) cannot prove the anchoring fix; this one
    can."""
    control, roots = _fixture(tmp_path, "partition")
    distinct = {
        str(roots["control"].resolve()),
        str(roots["partition"].resolve()),
        str(roots["parent"].resolve()),
    }
    assert len(distinct) == 3, distinct  # control != partition != parent
    target_config = mw_common.load_target_config(control, env={})
    assert target_config["mode"] == "partition"
    assert conductor.resolve_verify_cwd("", target_config) == str(
        roots["partition"].resolve()
    )
    assert conductor.resolve_verify_cwd("partition", target_config) == str(
        roots["partition"].resolve()
    )
    assert conductor.resolve_verify_cwd("control", target_config) == str(
        roots["control"].resolve()
    )
    assert conductor.resolve_verify_cwd("parent", target_config) == str(
        roots["parent"].resolve()
    )
    _verify(
        "VC-013",
        e2_shape="partition",
        roots_distinct="true",
        auto_cwd="partition",
        control_cwd=str(roots["control"].resolve()),
    )


@pytest.mark.skipif(
    not (_E2_PARTITION.exists() and _E2_PARENT.exists()),
    reason="E2 live workspace not present on this machine",
)
def test_e2_live_real_paths(tmp_path: pathlib.Path) -> None:
    """Capability-gated live anchor (absolute paths): partition =
    H:\\git\\E2Feature, parent = E:\\UEMigrator. Skipped only when the
    workspace is absent; the core truth table is never skipped with it."""
    control = tmp_path / "control"
    control.mkdir()
    (control / ".agenticdoc").mkdir(parents=True)
    (control / ".agenticdoc" / "target.yml").write_text(
        "active: partition\n"
        "partition:\n"
        f"  parent: '{_E2_PARENT.as_posix()}'\n"
        f"  partition: '{_E2_PARTITION.as_posix()}'\n",
        encoding="utf-8",
    )
    target_config = mw_common.load_target_config(control, env={})
    assert target_config["mode"] == "partition"
    assert conductor.resolve_verify_cwd("", target_config) == str(
        _E2_PARTITION.resolve()
    )
    assert conductor.resolve_verify_cwd("partition", target_config) == str(
        _E2_PARTITION.resolve()
    )
    assert conductor.resolve_verify_cwd("parent", target_config) == str(
        _E2_PARENT.resolve()
    )
    _verify(
        "VC-013",
        e2_live="partition",
        cwd=str(_E2_PARTITION.resolve()),
        parent=str(_E2_PARENT.resolve()),
    )


# ── proof the toolchain renderer is unchanged (VC-014) ──────────────────────


def test_toolchain_parity_cases_still_green(tmp_path: pathlib.Path) -> None:
    """Runs the shared cross-language parity fixture set from
    ``test_common_target_config.py`` in this same test run: every
    ``render_toolchain_command`` expectation must still hold."""
    import test_common_target_config as parity  # noqa: PLC0415 (local test import)

    case_dirs = sorted(p for p in parity._FIXTURES.iterdir() if p.is_dir())
    assert len(case_dirs) >= 14, f"expected >=14 parity cases, found {len(case_dirs)}"
    for case_dir in case_dirs:
        case_tmp = tmp_path / case_dir.name
        case_tmp.mkdir()
        parity._run_case(case_dir, case_tmp)
    _verify(
        "VC-014",
        toolchain_parity_cases=len(case_dirs),
        render_toolchain_unchanged="true",
    )
