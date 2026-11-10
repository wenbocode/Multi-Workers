"""Exercise project guide installation through the same CLI used by auto-init."""

import pathlib
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

PACKAGE = pathlib.Path(__file__).resolve().parent
MARKER = "<!-- mw:agent-collaboration-version: 2 -->"


@pytest.fixture
def project(tmp_path, monkeypatch):
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
    assert "PM mode: codex" in installed and "PM mode: mw" in installed
    assert claude.read_bytes() == b"# Existing project instructions\n"
    assert str(project / "AGENTS.md") in result.stdout
    assert "status: draft" in (project / ".agenticdoc" / "goal.md").read_text(encoding="utf-8")
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
