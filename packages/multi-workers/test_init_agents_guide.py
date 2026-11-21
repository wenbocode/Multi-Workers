"""Exercise project guide installation through the same CLI used by auto-init."""

import pathlib
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

PACKAGE = pathlib.Path(__file__).resolve().parent
MARKER = "<!-- mw:agent-collaboration-version: 3 -->"


@pytest.fixture
def project(tmp_path, monkeypatch):
    for name in ("MW_TARGET_GAME", "MW_TARGET_ENGINE", "MW_PARTITION_PARENT", "MW_PARTITION_ROOT"):
        monkeypatch.delenv(name, raising=False)
    agent = tmp_path / "pi"
    (agent / "extensions").mkdir(parents=True)
    (agent / "extensions" / "agent-team-loop.js").touch()
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(agent))
    target = tmp_path / "development project"
    target.mkdir()
    return target


def init(project, *options):
    return subprocess.run(
        [sys.executable, str(PACKAGE / "mw.py"), "init", "--project", str(project), *options],
        cwd=project.parent, capture_output=True, text=True, check=True,
    )


def test_new_project_uses_shipped_guide(project):
    claude = project / "CLAUDE.md"
    claude.write_bytes(b"# Existing project instructions\n")
    # Exercise the default framework branch with a local, offline installer.
    framework = project.parent / "framework"
    framework.mkdir()
    (framework / "install.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    result = init(project, "--sync-agentictask", str(framework))
    installed = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert installed == (PACKAGE / "templates" / "AGENTS.md").read_text(encoding="utf-8")
    assert MARKER in installed and "CLAUDE.md" in installed
    codex = project / ".agenticdoc" / "templates" / "codex_doc.md"
    assert codex.read_text(encoding="utf-8") == (PACKAGE / "templates" / "codex_doc.md").read_text(encoding="utf-8")
    assert "仅供 Codex PM 使用" in codex.read_text(encoding="utf-8")
    assert "Workflow: codex-lite" in installed and "PM mode: mw" in installed
    assert "spec → design → plan → tasks → execute → verify → done" in installed
    assert "- Workflow: codex-lite" in codex.read_text(encoding="utf-8")
    assert "- Claim-Id: codex" in codex.read_text(encoding="utf-8")
    for section in ("目标", "范围", "验收标准", "接续须知"):
        assert f"## {section}" in codex.read_text(encoding="utf-8")
    assert claude.read_bytes() == b"# Existing project instructions\n"
    assert str(project / "AGENTS.md") in result.stdout
    assert "status: draft" in (project / ".agenticdoc" / "goal.md").read_text(encoding="utf-8")
    assert "Worker dispatch requires an explicit workspace mode" in result.stdout
    assert "single/default cannot dispatch" in result.stdout
    assert "active: single" in result.stdout
    assert "mw target set" in result.stdout and "mw partition set" in result.stdout
    assert str(project / ".agenticdoc" / "target.yml") in result.stdout
    assert not (project / ".agenticdoc" / "target.yml").exists()
    assert not (project.parent / "AGENTS.md").exists()


@pytest.mark.parametrize(("encoding", "bom"), [
    ("utf-8", b""), ("utf-8", b"\xef\xbb\xbf"), ("utf-16-le", b"\xff\xfe"),
])
def test_existing_project_prose_and_edits_survive_reinit(project, encoding, bom):
    original = bom + "# 项目\r\n须遵守这些规则。".encode(encoding)
    guide = project / "AGENTS.md"
    guide.write_bytes(original)
    init(project, "--no-framework")
    merged = guide.read_bytes()
    assert merged.startswith(original + "\r\n\r\n".encode(encoding))
    section = merged[len(original):].decode(encoding)
    assert section.count(MARKER) == 1
    assert "\n" not in section.replace("\r\n", "")
    edited = merged.replace("每个 key 选择一个 PM".encode(encoding), "项目定制的 PM 选择".encode(encoding))
    assert edited != merged
    guide.write_bytes(edited)
    init(project, "--no-framework")
    assert guide.read_bytes() == edited


def test_parallel_init_appends_once(project):
    # AGENTS.MD is another spelling the pi context loader already recognizes.
    guide = project / "AGENTS.MD"
    guide.write_bytes(b"# Project rules\n\n")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(init, project, "--no-framework") for _ in range(2)]
        for future in futures:
            future.result()
    contents = guide.read_text(encoding="utf-8")
    assert contents.startswith("# Project rules\n\n## Multi-Workers")
    assert contents.count(MARKER) == 1
    assert len([p for p in project.iterdir() if p.name.lower() == "agents.md"]) == 1


def test_upgrade_keeps_legacy_section_and_project_codex_notes(project):
    guide = project / "AGENTS.md"
    original = b"# Custom rules\r\nLegacy user edits\r\n<!-- mw:agent-collaboration -->\r\n"
    guide.write_bytes(original)
    template = project / ".agenticdoc" / "templates" / "codex_doc.md"
    template.parent.mkdir(parents=True)
    template.write_bytes(b"# Project Codex template\n")
    key = project / ".agenticdoc" / "existing"
    key.mkdir()
    note = key / "codex_doc.md"
    note.write_bytes(b"# Work in progress\n")
    init(project, "--no-framework")
    upgraded = guide.read_bytes()
    assert upgraded.startswith(original)
    assert upgraded.decode().count(MARKER) == 1
    init(project, "--no-framework")
    assert guide.read_bytes() == upgraded
    assert template.read_bytes() == b"# Project Codex template\n"
    assert note.read_bytes() == b"# Work in progress\n"


@pytest.mark.parametrize(("encoding", "bom"), [
    ("utf-8", b""), ("utf-8", b"\xef\xbb\xbf"), ("utf-16-le", b"\xff\xfe"),
])
def test_v2_upgrade_appends_one_authoritative_guide_and_preserves_edits(project, encoding, bom):
    guide = project / "AGENTS.md"
    original = bom + (
        "# 项目自定义规则\r\n保留此处的修改。\r\n\r\n"
        "## Multi-Workers 协作约定\r\n旧版内的项目定制。\r\n"
        "<!-- mw:agent-collaboration-version: 2 -->\r\n"
    ).encode(encoding)
    guide.write_bytes(original)
    init(project, "--no-framework")
    upgraded = guide.read_bytes()
    assert upgraded.startswith(original)
    text = upgraded[len(bom):].decode(encoding)
    assert text.count(MARKER) == 1
    assert text.count("<!-- mw:agent-collaboration-version: 2 -->") == 1
    assert "本节取代前面版本化的 MW 协作章节" in text
    assert "普通 MW 派发仍检查原 SDD 文档" in text
    assert "Workflow: codex-lite" in text
    assert "\n" not in text.replace("\r\n", "")
    init(project, "--no-framework")
    assert guide.read_bytes() == upgraded


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_exact_shipped_v2_codex_template_upgrades_without_rewriting_key(project, newline):
    legacy = (PACKAGE / "test" / "fixtures" / "codex_doc_v2.md").read_text(encoding="utf-8")
    template = project / ".agenticdoc" / "templates" / "codex_doc.md"
    template.parent.mkdir(parents=True)
    template.write_bytes(legacy.replace("\n", newline).encode("utf-8"))
    key_note = project / ".agenticdoc" / "existing" / "codex_doc.md"
    key_note.parent.mkdir()
    key_note.write_bytes(legacy.encode("utf-8"))
    init(project, "--no-framework")
    assert template.read_text(encoding="utf-8") == (PACKAGE / "templates" / "codex_doc.md").read_text(encoding="utf-8")
    assert key_note.read_bytes() == legacy.encode("utf-8")
    installed = template.read_bytes()
    init(project, "--no-framework")
    assert template.read_bytes() == installed


@pytest.mark.parametrize(("encoding", "bom"), [("utf-8", b""), ("utf-16-le", b"\xff\xfe")])
def test_modified_v2_codex_template_is_project_owned(project, encoding, bom):
    legacy = (PACKAGE / "test" / "fixtures" / "codex_doc_v2.md").read_text(encoding="utf-8")
    template = project / ".agenticdoc" / "templates" / "codex_doc.md"
    template.parent.mkdir(parents=True)
    custom = bom + (legacy + "\n项目增加的验收要求。\n").encode(encoding)
    template.write_bytes(custom)
    init(project, "--no-framework")
    assert template.read_bytes() == custom


@pytest.mark.parametrize("family", ["target", "partition"])
@pytest.mark.parametrize("action", ["clear", "off"])
def test_missing_workspace_config_actions_explain_dispatch_requirement(project, family, action):
    result = subprocess.run(
        [sys.executable, str(PACKAGE / "mw.py"), family, action, "--project", str(project)],
        cwd=project.parent, capture_output=True, text=True, check=True,
    )
    assert "Worker dispatch requires an explicit workspace mode" in result.stdout
    assert "single/default cannot dispatch" in result.stdout
    assert "active: single" in result.stdout
    assert "mw target set" in result.stdout and "mw partition set" in result.stdout
    assert not (project / ".agenticdoc").exists()


@pytest.mark.parametrize("family", ["target", "partition"])
def test_clearing_last_workspace_mode_explains_dispatch_requirement(project, family):
    target = project.parent / "target"
    target.mkdir()
    command = [sys.executable, str(PACKAGE / "mw.py"), family]
    options = ["--game", str(target)] if family == "target" else [
        "--parent", str(target), "--partition", str(project),
    ]
    subprocess.run(
        [*command, "set", "--project", str(project), *options],
        cwd=project.parent, capture_output=True, text=True, check=True,
    )
    assert (project / ".agenticdoc" / "target.yml").is_file()
    result = subprocess.run(
        [*command, "clear", "--project", str(project)],
        cwd=project.parent, capture_output=True, text=True, check=True,
    )
    assert "Worker dispatch requires an explicit workspace mode" in result.stdout
    assert "single/default cannot dispatch" in result.stdout
    assert "active: single" in result.stdout
    assert not (project / ".agenticdoc" / "target.yml").exists()
