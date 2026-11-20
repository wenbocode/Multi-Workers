"""Dual Engine authorization at the real Python/Codex dispatch boundary."""
import json
import os
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import mw_common
from autopilot import dispatch, write_face

PROBE = pathlib.Path(__file__).resolve().parent / "engine_policy_probe.py"

#: The three build-artifact directories frozen by design §4 (relative to the
#: configured Engine repository root).
ARTIFACT_SUFFIXES = (
    "Engine/Intermediate/Build",
    "Engine/Saved/UnrealBuildTool",
    "Engine/Saved/Logs",
)

#: One realistic generated file per artifact directory (source UBT writes
#: `SourceFileCache.bin` under Intermediate/Build).
ARTIFACT_FILES = (
    "Engine/Intermediate/Build/SourceFileCache.bin",
    "Engine/Saved/UnrealBuildTool/BuildConfiguration.xml",
    "Engine/Saved/Logs/UnrealBuildTool.log",
)

#: Still denied under engine_writable=false: the wide Engine/Game parents,
#: wildcard artifact parents, source/build/config/binaries, the marker file and
#: path escapes.  A build-artifact exception is a literal-prefix exception,
#: never "intersects the Engine root" and never a UBT command-name exemption.
DENIED_ENTRIES = (
    "Engine/**",
    "Engine/Intermediate/**",
    "Engine/Saved/**",
    "Engine/Intermediate/Build*",
    "Engine/Intermediate/BuildX/Generated.bin",
    "Engine/Source/Engine.cpp",
    "Engine/Build/Build.version",
    "Engine/Config/BaseEngine.ini",
    "Engine/Binaries/Win64/UnrealEditor.exe",
    "Engine/InstalledBuild.txt",
    "Engine/Intermediate/Build/../Source/Engine.cpp",
    "Game/**",
)


def quiet_env(monkeypatch):
    for name in ("MW_TARGET_GAME", "MW_TARGET_ENGINE", "MW_PARTITION_PARENT", "MW_PARTITION_ROOT"):
        monkeypatch.delenv(name, raising=False)


def junction(link: pathlib.Path, target: pathlib.Path) -> None:
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(target, target_is_directory=True)


def dual_workspace(tmp_path, name, *, writable=None):
    """A v2 dual control root with the Engine repo rooted inside the Game root
    (`Game/Engine`), so a `Game/**` glob provably covers Engine."""
    root = tmp_path / name
    game = root / "Game"
    engine = game / "Engine"
    engine.mkdir(parents=True)
    cards = root / ".agenticdoc" / "policy" / "tasks"
    cards.mkdir(parents=True)
    block = {"game": str(game), "engine": str(engine)}
    if writable is not None:
        block["engine_writable"] = writable
    (root / ".agenticdoc" / "target.yml").write_text(
        json.dumps({"active": "dual", "dual": block}), encoding="utf-8")
    return {"control": root, "game": game, "engine": engine, "cards": cards}


def send(ws, stem, entries):
    (ws["cards"] / (stem + ".md")).write_text(
        "type: coding\n\n## 上下文\nContext.\n\n## 要求\nWork.\n\n"
        "## 交付格式\nReport.\n\n## 写入允许面\n"
        + "\n".join("- `" + entry + "`" for entry in entries) + "\n", encoding="utf-8")
    return dispatch.dispatch(ws["control"], "policy", stem, "phase-writer", "Work.", loop="test", attempt=1)


def queue_rows(ws):
    return mw_common.parse_workers_file(mw_common.workers_path(ws["control"]))


@pytest.mark.parametrize("writable", [None, False, True])
def test_dispatch_engine_policy(tmp_path, monkeypatch, writable):
    quiet_env(monkeypatch)
    ws = dual_workspace(tmp_path, "control", writable=writable)
    control, game, engine = ws["control"], ws["game"], ws["engine"]

    engine_result = send(ws, "engine", [str(engine / "Source" / "Engine.cpp")])
    if writable is True:
        assert engine_result.ok, engine_result.reason
    else:
        assert not engine_result.ok
        assert engine_result.reason.startswith("write-face-read-only")
        assert not mw_common.workers_path(control).exists()
        assert not (control / ".agenticdoc" / "policy" / "workers").exists()
        assert send(ws, "broad", [str(game) + "/**"]).reason.startswith("write-face-read-only")
        assert not mw_common.workers_path(control).exists()
    game_result = send(ws, "game", [str(game / "Plugin.cpp")])
    assert game_result.ok, game_result.reason
    text = game_result.task_md.read_text(encoding="utf-8")
    assert "Game writes: enabled" in text
    if writable is True:
        assert "Engine source writes: enabled" in text
        assert "UBT builds:" not in text
        assert "Plan direct Engine changes only within the approved scope" in text
        assert "never overrides project/task constraints" in text
        assert "Engine extension policy (mandatory)" not in text
    else:
        assert "Engine source writes: read-only" in text
        assert "Never copy or fork Engine source" in text
        assert "UBT builds: allowed without enabling Engine source writes." in text


@pytest.mark.parametrize("writable", [None, False])
@pytest.mark.parametrize("suffix", ARTIFACT_SUFFIXES)
@pytest.mark.parametrize("shape", ["glob", "exact"])
def test_dispatch_accepts_declared_build_artifacts(tmp_path, monkeypatch, writable, suffix, shape):
    """VC-002/VC-004: an exactly declared UBT artifact path and the three
    directory globs pass the real Python dispatch admission."""
    quiet_env(monkeypatch)
    ws = dual_workspace(tmp_path, "case-" + suffix.replace("/", "-") + "-" + shape, writable=writable)
    target = ws["engine"] / pathlib.PurePosixPath(suffix)
    entry = str(target) + "/**" if shape == "glob" else str(target / "Generated.bin")
    result = send(ws, "build-artifact", [entry])
    assert result.ok, result.reason
    assert result.row_verified
    text = result.task_md.read_text(encoding="utf-8")
    assert "write_face: " + entry in text  # the declared face survives verbatim
    assert "UBT builds: allowed without enabling Engine source writes." in text
    assert "UBT build permission does not allow rebuilding UBT itself" in text
    assert "Static command guards are not an OS sandbox." in text
    rows = queue_rows(ws)
    assert [row.get("task_key") for row in rows] == [dispatch.task_key_for("policy", "build-artifact")]
    print(f"[VERIFY] VC-002: artifact_dispatch=PASS shape={shape} writable={writable} suffix={suffix}")


@pytest.mark.parametrize("suffix", ARTIFACT_SUFFIXES)
def test_dispatch_keeps_engine_root_narrow_with_true(tmp_path, monkeypatch, suffix):
    """VC-006: engine_writable=true keeps its existing wider semantics; the
    artifact exception adds nothing and the UBT lines stay out of the profile."""
    quiet_env(monkeypatch)
    ws = dual_workspace(tmp_path, "wide-" + suffix.replace("/", "-"), writable=True)
    result = send(ws, "source", [str(ws["engine"] / "Engine" / "Source" / "Engine.cpp")])
    assert result.ok, result.reason
    text = result.task_md.read_text(encoding="utf-8")
    assert "Engine source writes: enabled" in text
    assert "UBT builds:" not in text


@pytest.mark.parametrize("entry", DENIED_ENTRIES)
def test_dispatch_denies_wide_source_and_marker_paths(tmp_path, monkeypatch, entry):
    """VC-003/VC-005: wide parents, wildcard artifact parents, source/build/
    config/binaries, the marker file and escapes stay refused with zero side
    effects even though the three artifact directories are admitted."""
    quiet_env(monkeypatch)
    ws = dual_workspace(tmp_path, "denied", writable=False)
    if entry.startswith("Game/"):
        declared = (ws["game"] / pathlib.PurePosixPath(entry.split("/", 1)[1])).as_posix()
    else:
        declared = (ws["engine"] / pathlib.PurePosixPath(entry)).as_posix()
    result = send(ws, "denied", [declared])
    assert not result.ok, f"{entry} was admitted"
    assert result.reason.startswith(
        ("write-face-read-only", "write-face-escape", "write-face-outside-base")), result.reason
    assert not mw_common.workers_path(ws["control"]).exists()
    assert not (ws["control"] / ".agenticdoc" / "policy" / "workers").exists()
    print(f"[VERIFY] VC-003/VC-005: broad_and_source_denied=PASS entry={entry}")


def test_dispatch_denies_artifact_junction_escapes(tmp_path, monkeypatch):
    """VC-005: the literal exception is not realpath-migrated into a new
    writable root; an artifact root or sub-path junction that leaves it (into
    Engine source or outside every configured root) stays refused."""
    quiet_env(monkeypatch)
    ws = dual_workspace(tmp_path, "junctions", writable=False)
    engine = ws["engine"]
    build = engine / "Engine" / "Intermediate" / "Build"
    build.parent.mkdir(parents=True)
    source = engine / "Engine" / "Source"
    source.mkdir(parents=True)
    try:
        junction(build, source)
        result = send(ws, "root-escape", [str(build / "SourceFileCache.bin")])
        assert not result.ok
        assert result.reason.startswith("write-face-read-only"), result.reason
        build.rmdir()
        build.mkdir()
        junction(build / "Link", source)
        result = send(ws, "subpath-escape", [str(build / "Link" / "Engine.cpp")])
        assert not result.ok
        assert result.reason.startswith("write-face-read-only"), result.reason
        print("[VERIFY] VC-005: junction_escape_denied=PASS roots=build,subpath")
    finally:
        for link in (build / "Link", build):
            if link.exists() and os.name == "nt":
                link.rmdir()
        build.mkdir(parents=True, exist_ok=True)


def test_same_build_artifact_stays_conflict(tmp_path, monkeypatch):
    """VC-003: the artifact exception does not weaken concurrency: a second
    same-owner declaration of the same artifact directory still conflicts."""
    quiet_env(monkeypatch)
    ws = dual_workspace(tmp_path, "conflict", writable=False)
    build = ws["engine"] / "Engine" / "Intermediate" / "Build"
    first = send(ws, "one", [str(build) + "/**"])
    assert first.ok, first.reason
    queue = mw_common.workers_path(ws["control"]).read_bytes()
    second = send(ws, "two", [str(build / "Other.obj")])
    assert not second.ok
    assert second.reason.startswith("write-face-overlap"), second.reason
    assert mw_common.workers_path(ws["control"]).read_bytes() == queue
    assert not (ws["control"] / ".agenticdoc" / "policy" / "workers"
                / dispatch.task_key_for("policy", "two")).exists()
    print("[VERIFY] VC-003: artifact_conflict=PASS reason=" + second.reason.split(" ")[0])


def test_engine_build_artifact_roots_are_literal_suffixes():
    """AC-001/AC-002 frozen helper: three literal anchors, joined only."""
    roots = mw_common.engine_build_artifact_roots(os.path.join("D:" + os.sep, "UE"))
    assert [root.replace("\\", "/") for root in roots] == [
        "D:/UE/Engine/Intermediate/Build",
        "D:/UE/Engine/Saved/UnrealBuildTool",
        "D:/UE/Engine/Saved/Logs",
    ]
    assert mw_common.engine_build_artifact_roots("") == []


def test_write_face_requires_complete_literal_prefix_not_intersection(tmp_path):
    """VC-002/VC-003 at the parser boundary: only a glob fully inside an
    allowed directory passes; a merely intersecting or wildcard-parent glob
    does not, and omitting the option keeps the original behaviour."""
    engine = tmp_path / "EngineRepo"
    (engine / "Engine").mkdir(parents=True)
    base = str(tmp_path)
    roots = [base]
    readonly = [str(engine)]
    allowed = mw_common.engine_build_artifact_roots(str(engine))
    parse = lambda entry, **kw: write_face.parse_write_face(
        "write_face: " + entry, base=base, case_insensitive=True, roots=roots,
        canonicalize=dispatch.canonical_write_face_path, read_only_roots=readonly, **kw)

    admitted = str(engine / "Engine" / "Intermediate" / "Build") + "/**"
    assert isinstance(parse(admitted, read_only_allowed_roots=allowed), write_face.WriteFace)
    assert isinstance(parse(str(engine / "Engine" / "Saved" / "Logs" / "UBT.log"),
                            read_only_allowed_roots=allowed), write_face.WriteFace)
    for entry in (
        str(engine) + "/**",
        str(engine / "Engine" / "Intermediate") + "/**",
        str(engine / "Engine" / "Intermediate" / "Build*"),
        str(engine / "Engine" / "Saved" / "UnrealBuildTool.bak") + "/**",
    ):
        refused = parse(entry, read_only_allowed_roots=allowed)
        assert isinstance(refused, write_face.Refused), entry
        assert refused.code == write_face.WRITE_FACE_READ_ONLY, entry
    # No option -> unchanged behaviour (the wide Engine declaration is refused).
    assert parse(str(engine) + "/**").code == write_face.WRITE_FACE_READ_ONLY
    # An allowed root outside every configured root is not a new whitelist.
    outside = str(tmp_path.parent / "elsewhere" / "Engine" / "Intermediate" / "Build")
    assert parse(admitted, read_only_allowed_roots=[outside]).code == write_face.WRITE_FACE_READ_ONLY


def test_single_and_partition_keep_no_artifact_exception(tmp_path, monkeypatch):
    """VC-006: single/partition profiles carry neither the Engine policy nor a
    UBT exception; their existing root semantics do not widen."""
    quiet_env(monkeypatch)
    control = tmp_path / "single"
    control.mkdir()
    (control / ".agenticdoc").mkdir()
    (control / ".agenticdoc" / "target.yml").write_text("active: single\n", encoding="utf-8")
    cards = control / ".agenticdoc" / "policy" / "tasks"
    cards.mkdir(parents=True)
    (cards / "one.md").write_text(
        "type: coding\n\n## 上下文\nC.\n\n## 要求\nW.\n\n## 交付格式\nR.\n\n## 写入允许面\n- `src/a.cpp`\n",
        encoding="utf-8")
    single = dispatch.dispatch(control, "policy", "one", "phase-writer", "W.", loop="test", attempt=1)
    assert single.ok, single.reason
    single_text = single.task_md.read_text(encoding="utf-8")
    assert "UBT builds:" not in single_text
    assert "Engine source writes:" not in single_text

    parent = tmp_path / "parent"
    partition = tmp_path / "shard"
    for root in (parent, partition):
        root.mkdir()
    control = tmp_path / "partition"
    control.mkdir()
    (control / ".agenticdoc").mkdir()
    (control / ".agenticdoc" / "target.yml").write_text(json.dumps(
        {"active": "partition", "partition": {"parent": str(parent), "partition": str(partition)}}),
        encoding="utf-8")
    cards = control / ".agenticdoc" / "policy" / "tasks"
    cards.mkdir(parents=True)
    (cards / "one.md").write_text(
        "type: coding\n\n## 上下文\nC.\n\n## 要求\nW.\n\n## 交付格式\nR.\n\n## 写入允许面\n- `"
        + str(partition / "src" / "a.cpp") + "`\n", encoding="utf-8")
    shard = dispatch.dispatch(control, "policy", "one", "phase-writer", "W.", loop="test", attempt=1)
    assert shard.ok, shard.reason
    partition_text = shard.task_md.read_text(encoding="utf-8")
    assert "UBT builds:" not in partition_text
    assert dispatch.write_face_read_only_allowed_roots(mw_common.load_target_config(control)) == []
    print("[VERIFY] VC-006: boundary_preserved=PASS single=none partition=none")


def test_policy_probe_matches_production_policy_and_admission(tmp_path, monkeypatch):
    """VC-001/VC-002 parity probe: the helper the TS suite consumes reports the
    same policy text, the derived exception roots and the same admission."""
    quiet_env(monkeypatch)
    ws = dual_workspace(tmp_path, "probe", writable=False)
    build = ws["engine"] / "Engine" / "Intermediate" / "Build"
    entries = [
        str(build / "SourceFileCache.bin"),
        str(build) + "/**",
        str(ws["engine"] / "Engine" / "Source" / "Engine.cpp"),
        str(ws["engine"]) + "/**",
    ]
    env = {key: value for key, value in os.environ.items()
           if key not in ("MW_TARGET_GAME", "MW_TARGET_ENGINE", "MW_PARTITION_PARENT", "MW_PARTITION_ROOT")}
    result = subprocess.run([sys.executable, "-B", str(PROBE)], input=json.dumps(
        {"control": str(ws["control"]), "entries": entries}),
        capture_output=True, text=True, env=env, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    config = mw_common.load_target_config(ws["control"], env={})
    assert data["writable"] is False
    assert data["lines"] == mw_common.dual_engine_policy_lines(config)
    assert data["profile"] == mw_common.render_dual_profile_md(config)
    assert [root.replace("\\", "/") for root in data["artifact_roots"]] == [
        root.replace("\\", "/") for root in mw_common.engine_build_artifact_roots(str(ws["engine"]))]
    assert data["faces"] == ["declared", "declared", "write-face-read-only", "write-face-read-only"]
    print("[VERIFY] VC-001/VC-002: policy_parity_probe=PASS lines+profile+faces")
