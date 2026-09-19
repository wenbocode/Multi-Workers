"""
test_target_baseline.py — golden baseline for the CURRENT target-config
behavior (mw-target-partition T-00, spec AC-016, design D-011 + VC-016).

Recorded BEFORE any partition implementation lands: two samples — (a) a full
v1 dual target.yml and (b) no target.yml (single) — are run through the
current pipeline and every observable output is captured to a golden file:

  a. load_target_config legacy projection — the 10 v1 fields
     (mode/control_root/game_root/engine_root/vcs/uproject/toolchain/
     ignore/contract/source). Keys the resolver may grow later are outside
     the AC-016 contract: the projection takes exactly these 10.
  b. launcher._worker_cwd return value for the sample control root.
  c. autopilot.dispatch._expand_read_scope sample expansion (relative
     entries like "src/" plus one absolute entry).
  e. `python mw.py target show` stdout in the sample control root.
  f. `python mw.py doctor --json` target section JSON (timestamp-like keys
     stripped — none exist today; kept so a future clock field cannot flake
     the byte-exact baseline).

(d — the task.md profile injection block — is injected on the TS side only;
see packages/coding-agent/test/extensions/agent-team-loop-baseline.test.ts,
whose dual sample yml mirrors DUAL_YML below byte-for-byte. Keep both in
sync when editing either.)

Golden protocol (AC-016): a missing golden file is written and the test
PASSES with a "RECORDED" line; an existing golden is compared BYTE-EXACT
after replacing the sample control root's absolute path with "<CTRL>" —
everything else must match to the byte. A mismatch prints a diff summary
and fails the test. To re-record a baseline, delete the golden file and
re-run.

The samples deliberately place game/engine/docs under the control root and
use RELATIVE yml roots, so every recorded path normalizes to <CTRL>/... and
the golden stays machine-independent.
"""
import difflib
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import launcher
import mw_common
from autopilot.dispatch import _expand_read_scope
from mw_common import (
    ENV_TARGET_ENGINE,
    ENV_TARGET_GAME,
    load_target_config,
)

_PKG_ROOT = pathlib.Path(__file__).resolve().parent.parent
_MW_PY = _PKG_ROOT / "mw.py"
GOLDEN_DIR = pathlib.Path(__file__).resolve().parent / "golden" / "target-baseline"

_CTRL = "<CTRL>"

# The 10 legacy (v1) fields the AC-016 projection covers.
_PROJECTION_FIELDS = (
    "mode",
    "control_root",
    "game_root",
    "engine_root",
    "vcs",
    "uproject",
    "toolchain",
    "ignore",
    "contract",
    "source",
)

# Full v1 dual sample (AC-016): every bootstrap field plus the three
# hand-maintained sections, with {game}/{engine}/{uproject} toolchain
# placeholders, deny_globs and a contract section. Mirrored byte-for-byte as
# DUAL_YML in packages/coding-agent/test/extensions/agent-team-loop-baseline.
# test.ts — keep both sides in sync.
DUAL_YML = """\
# mw-target-partition AC-016 baseline sample: full v1 dual target.yml.
mode: dual
game: game
engine: engine
vcs: git
uproject: MyGame.uproject
toolchain:
  build_editor: '"{engine}/Engine/Build/BatchFiles/Build.bat" MyGameEditor Win64 Development -project="{uproject}"'
  regen: 'python {game}/Tools/regen.py --engine {engine}'
ignore:
  deny_globs:
    - "**/*.uasset"
    - "**/DerivedDataCache/**"
contract:
  forbidden_paths:
    - "**/Generated/*"
  conventions: |
    Line one of the conventions.
    Line two of the conventions.
  docs:
    - docs/contract-notes.md
"""


@pytest.fixture(autouse=True)
def _no_target_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No env overrides leak into the recorded resolution (fail-loud, not
    silently re-recorded from a polluted environment)."""
    monkeypatch.delenv(ENV_TARGET_GAME, raising=False)
    monkeypatch.delenv(ENV_TARGET_ENGINE, raising=False)


def _make_control(tmp_path: pathlib.Path, name: str) -> pathlib.Path:
    control = tmp_path / name
    control.mkdir()
    return control


def _write_dual_sample(control: pathlib.Path) -> None:
    (control / "game").mkdir()
    (control / "game" / "MyGame.uproject").write_text("{}", encoding="utf-8")
    (control / "engine").mkdir()
    (control / "docs").mkdir()
    (control / "docs" / "contract-notes.md").write_text("# contract notes\n", encoding="utf-8")
    yml = mw_common.target_yml_path(control)
    yml.parent.mkdir(parents=True, exist_ok=True)
    yml.write_text(DUAL_YML, encoding="utf-8")


def _normalize(value: object, ctrl_real: str) -> object:
    """Replace the sample control root's absolute path with <CTRL>; every
    other byte must match exactly (AC-016 path normalization)."""
    if isinstance(value, str):
        return value.replace(ctrl_real, _CTRL)
    if isinstance(value, list):
        return [_normalize(v, ctrl_real) for v in value]
    if isinstance(value, dict):
        return {k: _normalize(v, ctrl_real) for k, v in value.items()}
    return value


# Timestamp-like doctor keys (probed_at / *_epoch / mtime / ...). None exist
# in the current target section; the scrub keeps the baseline immune to
# future clock fields.
_TS_KEY_RE = re.compile(r"(?:^|_)(at|ts|epoch|mtime)(?:$|_)|timestamp", re.IGNORECASE)


def _scrub_timestamps(value: object) -> object:
    if isinstance(value, dict):
        return {k: _scrub_timestamps(v) for k, v in value.items() if not _TS_KEY_RE.search(k)}
    if isinstance(value, list):
        return [_scrub_timestamps(v) for v in value]
    return value


def _run_mw(args: list[str], control: pathlib.Path, tmp_path: pathlib.Path) -> subprocess.CompletedProcess:
    """Run `python mw.py <args> --project <control>` in a hermetic env."""
    env = dict(os.environ)
    env.pop(ENV_TARGET_GAME, None)
    env.pop(ENV_TARGET_ENGINE, None)
    # P-002: keep every agent-config access (reads included) inside the
    # sample tmp root — the test never touches ~/.pi/agent.
    agent_home = tmp_path / "agent-home"
    agent_home.mkdir(exist_ok=True)
    env["PI_CODING_AGENT_DIR"] = str(agent_home)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(_MW_PY), *args, "--project", str(control)],
        capture_output=True,
        cwd=str(_PKG_ROOT),
        env=env,
        check=False,
    )


def _record(name: str, control: pathlib.Path, tmp_path: pathlib.Path) -> dict:
    """Capture the six Py-side observable outputs for one sample (AC-016)."""
    # The resolved control root is the normalization key: every pipeline
    # path (roots, renders, doctor details) derives from it.
    ctrl_real = pathlib.Path(control).resolve()
    config = load_target_config(control, env={})

    scope = ["src/", "Docs/", str(ctrl_real / "Content")]
    show = _run_mw(["target", "show"], control, tmp_path)
    assert show.returncode == 0, show.stderr.decode("utf-8", errors="replace")
    doctor = _run_mw(["doctor", "--json"], control, tmp_path)
    assert doctor.returncode in (0, 1), doctor.stderr.decode("utf-8", errors="replace")
    report = json.loads(doctor.stdout.decode("utf-8"))

    record = {
        "sample": name,
        "a_projection": {field: config[field] for field in _PROJECTION_FIELDS},
        "b_worker_cwd": str(launcher._worker_cwd(ctrl_real)),
        "c_expand_read_scope": _expand_read_scope(scope, config, ctrl_real),
        "e_target_show_stdout": show.stdout.decode("utf-8"),
        "f_doctor_target": _scrub_timestamps(report["target"]),
    }
    return _normalize(record, str(ctrl_real))


def _golden_check(name: str, record: dict) -> str:
    """Record-if-missing / byte-exact-compare golden gate (AC-016)."""
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    path = GOLDEN_DIR / f"{name}.json"
    current = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    rel = path.relative_to(_PKG_ROOT)
    if not path.exists():
        path.write_bytes(current)  # UTF-8, no BOM
        print(f"[BASELINE] RECORDED: {rel} ({len(record) - 1} entries)")
        return "RECORDED"
    golden = path.read_bytes()
    if golden == current:
        print(f"[BASELINE] MATCH: {rel}")
        return "MATCH"
    diff = difflib.unified_diff(
        golden.decode("utf-8", errors="replace").splitlines(),
        current.decode("utf-8", errors="replace").splitlines(),
        fromfile=f"golden/{name}.json",
        tofile="current",
        lineterm="",
    )
    print(f"[BASELINE] MISMATCH: {rel}")
    print("\n".join(list(diff)[:60]))
    pytest.fail(f"target baseline {name!r} differs from the golden file (AC-016)")


# ── samples ───────────────────────────────────────────────────────────────────


def test_baseline_dual(tmp_path: pathlib.Path) -> None:
    """Full v1 dual target.yml: legacy projection, game-root worker cwd,
    scope expansion anchored at the game root, target show + doctor JSON."""
    control = _make_control(tmp_path, "dual-control")
    _write_dual_sample(control)
    status = _golden_check("dual", _record("dual", control, tmp_path))
    assert status in ("RECORDED", "MATCH")
    print(f"[VERIFY] VC-016: baseline_dual={'identical' if status == 'MATCH' else 'recorded'}")


def test_baseline_single(tmp_path: pathlib.Path) -> None:
    """No target.yml: single-mode defaults across the same observable set."""
    control = _make_control(tmp_path, "single-control")
    status = _golden_check("single", _record("single", control, tmp_path))
    assert status in ("RECORDED", "MATCH")
    print(f"[VERIFY] VC-016: baseline_single={'identical' if status == 'MATCH' else 'recorded'}")
