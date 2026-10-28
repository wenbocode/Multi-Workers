"""Cross-language parity for the review-split switch (T-05).

The authority is the TS module
``packages/coding-agent/src/extensions/agent-team-loop/shared/review-split.ts``
(claim-driven-review-orchestration T-01): same constants, same precedence
(env > config > default), same diagnostic strings. This module is the Python
half of the parity table and reads the SAME corpus the TS suite reads —
``packages/coding-agent/test/suite/fixtures/review-split-cases.json``
(``review-split-mode.test.ts``) — so the two languages are compared through
one shared table, never through hand-copied constants.

Corpus format (one case per JSON object):

* ``name``  — stable case id
* ``env``   — the env map handed to the resolver (``MW_REVIEW_SPLIT`` or empty)
* ``config``— ``null`` = no config file, a string = written verbatim (corrupt
  JSON fixtures), anything else = JSON-encoded into ``.mw/review-split.json``
* ``expect``— the exact ``mode`` / ``source`` / ``invalid`` triple

Also covered here (the T-05 acceptance item): the CLI view
(``mw review-split status --json``) exposes the config rejection reason, and
``autopilot.review_split.set_review_split`` keeps the atomic/no-op contract
that ``mw review-split set`` relied on.

Run: cd packages/multi-workers && python -X utf8 -m pytest -q test_review_split_parity.py
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))  # noqa: E402

import mw  # noqa: E402
from autopilot import review_split  # noqa: E402

ENV_VAR = "MW_REVIEW_SPLIT"

#: The single corpus both languages read (TS: `test/suite/review-split-mode.test.ts`).
CASES_FILE = (
    _HERE.parent / "coding-agent" / "test" / "suite" / "fixtures" / "review-split-cases.json"
)
TS_TEST_FILE = _HERE.parent / "coding-agent" / "test" / "suite" / "review-split-mode.test.ts"
MW_PY = pathlib.Path(mw.__file__)

CASES = json.loads(CASES_FILE.read_text(encoding="utf-8"))

#: Scenarios the card requires the table to cover (at least these 9).
REQUIRED_CASES = (
    "default-no-env-no-config",
    "env-on",
    "env-uppercase-plan",
    "env-illegal-no-config",
    "config-plan",
    "env-on-overrides-config-plan",
    "config-broken-json",
    "config-v2-unsupported",
    "config-mode-illegal",
)


def _case(case: dict) -> str:
    return case["name"]


def _write_config(project: pathlib.Path, config: object) -> None:
    """Materialize the case's config exactly as the TS suite does."""
    if config is None:
        return
    path = review_split.review_split_config_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        config
        if isinstance(config, str)
        else json.dumps(config, ensure_ascii=False, separators=(",", ":"))
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def _run_cli(*argv: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = {name: value for name, value in os.environ.items() if name != ENV_VAR}
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(MW_PY), *argv],
        capture_output=True,
        encoding="utf-8",
        timeout=300,
        env=env,
    )


# -- corpus shape -----------------------------------------------------------


def test_corpus_covers_the_required_scenarios() -> None:
    assert isinstance(CASES, list)
    assert len(CASES) >= 9, f"corpus too small: {len(CASES)} cases"
    names = [_case(case) for case in CASES]
    assert len(set(names)) == len(names), f"duplicate case names: {names}"
    missing = [name for name in REQUIRED_CASES if name not in names]
    assert not missing, f"missing required cases: {missing}"
    for case in CASES:
        assert set(case) == {"name", "env", "config", "expect"}, case
        assert set(case["expect"]) == {"mode", "source", "invalid"}, case
        assert set(case["env"]) <= {ENV_VAR}, case
        assert case["expect"]["mode"] in review_split.REVIEW_SPLIT_MODES, case
        assert case["expect"]["source"] in ("env", "config", "default"), case


def test_ts_suite_reads_this_exact_corpus() -> None:
    """Parity is only real while both sides load the same file."""
    text = TS_TEST_FILE.read_text(encoding="utf-8")
    assert "fixtures/review-split-cases.json" in text


# -- per-case parity --------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=_case)
def test_case_matches_shared_table(case: dict, tmp_path: pathlib.Path) -> None:
    project = tmp_path.resolve()
    _write_config(project, case["config"])

    state = review_split.resolve_review_split(project, env=case["env"])

    # The Python contract: exactly these four keys, always present.
    assert set(state) == {"mode", "source", "config_path", "invalid"}
    assert state["config_path"] == str(review_split.review_split_config_path(project))
    assert (state["mode"], state["source"], state["invalid"]) == (
        case["expect"]["mode"],
        case["expect"]["source"],
        case["expect"]["invalid"],
    ), case["name"]


@pytest.mark.parametrize("case", CASES, ids=_case)
def test_resolution_is_a_pure_read(case: dict, tmp_path: pathlib.Path) -> None:
    project = tmp_path.resolve()
    _write_config(project, case["config"])
    config_path = review_split.review_split_config_path(project)
    before = config_path.read_bytes() if config_path.exists() else None
    tree_before = sorted(p.relative_to(project).as_posix() for p in project.rglob("*"))

    review_split.resolve_review_split(project, env=case["env"])
    review_split.resolve_review_split(project, env=case["env"])

    after = config_path.read_bytes() if config_path.exists() else None
    assert after == before
    assert sorted(p.relative_to(project).as_posix() for p in project.rglob("*")) == tree_before


def test_default_resolution_creates_nothing(tmp_path: pathlib.Path) -> None:
    project = tmp_path.resolve()
    state = review_split.resolve_review_split(project, env={})
    assert (state["mode"], state["source"], state["invalid"]) == ("off", "default", None)
    assert list(project.iterdir()) == []


# -- tolerance (never throws) ----------------------------------------------


def test_resolver_degrades_on_hostile_paths(tmp_path: pathlib.Path) -> None:
    # A project path that is a regular file: `.mw/...` is ENOTDIR = "no config".
    file_project = tmp_path / "not-a-dir"
    file_project.write_text("x", encoding="utf-8")
    state = review_split.resolve_review_split(file_project, env={})
    assert (state["mode"], state["source"], state["invalid"]) == ("off", "default", None)

    # Booby-trapped config: the config path is a directory (EISDIR = no config).
    dir_project = tmp_path / "dir-config"
    review_split.review_split_config_path(dir_project).mkdir(parents=True)
    state = review_split.resolve_review_split(dir_project, env={})
    assert (state["mode"], state["source"], state["invalid"]) == ("off", "default", None)

    # Non-string env payload and non-object project argument never raise.
    assert review_split.resolve_review_split(tmp_path, env={ENV_VAR: 3})["invalid"] == "3"
    assert review_split.resolve_review_split(tmp_path, env={ENV_VAR: None})["source"] == "default"


# -- set_review_split ------------------------------------------------------


@pytest.mark.parametrize("mode", review_split.REVIEW_SPLIT_WIRED_MODES)
def test_set_writes_versioned_config_and_round_trips(mode: str, tmp_path: pathlib.Path) -> None:
    project = tmp_path.resolve()
    written = review_split.set_review_split(project, mode)
    config_path = review_split.review_split_config_path(project)
    assert written == {"mode": mode, "config_path": str(config_path)}

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["v"] == 1
    assert payload["mode"] == mode
    assert payload["updated"].endswith("Z") and len(payload["updated"]) == 20
    assert not config_path.with_name(config_path.name + ".tmp").exists()

    state = review_split.resolve_review_split(project, env={})
    assert (state["mode"], state["source"], state["invalid"]) == (mode, "config", None)


def test_set_normalizes_case_and_whitespace(tmp_path: pathlib.Path) -> None:
    project = tmp_path.resolve()
    assert review_split.set_review_split(project, "  PLAN ")["mode"] == "plan"
    assert json.loads(review_split.review_split_config_path(project).read_text("utf-8"))[
        "mode"
    ] == "plan"


def test_set_rejects_illegal_mode_without_side_effects(tmp_path: pathlib.Path) -> None:
    project = tmp_path.resolve()
    (project / "a.txt").write_text("keep\n", encoding="utf-8")
    before = sorted(p.relative_to(project).as_posix() for p in project.rglob("*"))

    with pytest.raises(ValueError):
        review_split.set_review_split(project, "maybe")

    assert sorted(p.relative_to(project).as_posix() for p in project.rglob("*")) == before
    assert not (project / ".mw").exists()


# -- CLI view (T-05 bug #1: silent bad-config diagnosis) --------------------


def test_cli_json_reports_broken_config(tmp_path: pathlib.Path) -> None:
    project = tmp_path.resolve()
    config_path = review_split.review_split_config_path(project)
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{ broken json", encoding="utf-8", newline="\n")

    proc = _run_cli("review-split", "status", "--json", "--project", str(project))
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    assert doc == {
        "mode": "off",
        "source": "default",
        "config_path": str(config_path),
        "invalid_env": None,
        "invalid": "config-invalid-json",
        "wired": True,
    }

    text = _run_cli("review-split", "status", "--project", str(project))
    assert text.returncode == 0, text.stderr
    assert text.stdout.strip() == (
        f"review-split: mode=off source=default config={config_path}"
        " invalid=config-invalid-json"
    )


def test_cli_wrappers_delegate_to_the_shared_module() -> None:
    """`mw.py` keeps only thin wrappers (the conductor cannot import the CLI)."""
    assert mw._REVIEW_SPLIT_MODES == review_split.REVIEW_SPLIT_MODES
    assert mw._REVIEW_SPLIT_DEFAULT == review_split.REVIEW_SPLIT_DEFAULT
    assert mw._REVIEW_SPLIT_ENV == review_split.REVIEW_SPLIT_ENV
    for removed in ("_review_split_from_config",):
        assert not hasattr(mw, removed), f"{removed} should live in autopilot.review_split"
