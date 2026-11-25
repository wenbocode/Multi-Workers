"""Per-key write-journal aggregation (mw-key-write-journal)."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

import change_set

KEY = "sample-key"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    key_dir = tmp_path / ".agenticdoc" / KEY
    key_dir.mkdir(parents=True)
    return tmp_path


def write(project: Path, rel: str, text: str = "content\n") -> None:
    target = project / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def achieved(project: Path, body: str) -> None:
    (project / ".agenticdoc" / KEY / "achieved.md").write_text(
        "## 系统行为变化\nChanged behavior.\n\n## 修改面\n" + body + "\n\n## 遗留\nNone.\n",
        encoding="utf-8")


def journal(project: Path, *events: dict) -> None:
    path = project / ".agenticdoc" / KEY / change_set.JOURNAL_NAME
    path.write_text("".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events), encoding="utf-8")


def trace(project: Path, task: str, *lines: str) -> None:
    folder = project / ".agenticdoc" / KEY / "workers" / task
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "trace.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


def load(project: Path) -> dict:
    return json.loads((project / ".agenticdoc" / KEY / change_set.CHANGE_SET_JSON).read_text(encoding="utf-8"))


def test_finalize_merges_all_three_sources_and_pins_closure_hashes(project: Path) -> None:
    write(project, "src/a.ts", "a\n")
    write(project, "src/b.ts", "b\n")
    write(project, "src/c.ts", "c\n")
    achieved(project, "- `src/a.ts` PM edit\n- `src/b.ts` worker edit\n- `src/c.ts` declared only\n")
    journal(project,
            {"ts": "2026-01-01T00:00:00+00:00", "key": KEY, "source": "pm-tool-result",
             "tool": "edit", "path": "src/a.ts"},
            {"ts": "2026-01-01T00:01:00+00:00", "key": KEY, "source": "pm-tool-result",
             "tool": "edit", "path": "src/a.ts"},
            {"ts": "2026-01-01T00:02:00+00:00", "key": KEY, "source": "unresolved",
             "tool": "bash", "pattern": "bash-target", "target": "$OUT"},
            {"ts": "2026-01-01T00:03:00+00:00", "key": KEY, "source": "pm-tool-result",
             "tool": "write", "path": ".agenticdoc/sample-key/evidence/report.md"})
    trace(project, "t-001", "[WRITE_FILE] path=src/b.ts",
          "[WRITE_UNRESOLVED] pattern=dynamic target=$DEST")
    result = change_set.finalize(project, KEY)

    data = load(project)
    assert data["method"] == "write-events" and data["excluded"] == [".agenticdoc/**"]
    assert [item["path"] for item in data["files"]] == ["src/a.ts", "src/b.ts", "src/c.ts"]
    by_path = {item["path"]: item for item in data["files"]}
    assert by_path["src/a.ts"]["sources"] == ["pm-declared", "pm-tool-result"]
    assert by_path["src/a.ts"]["first_write"] == "2026-01-01T00:00:00+00:00"
    assert by_path["src/a.ts"]["last_write"] == "2026-01-01T00:01:00+00:00"
    assert by_path["src/a.ts"]["sha256"] == hashlib.sha256((project / "src/a.ts").read_bytes()).hexdigest()
    assert by_path["src/b.ts"]["sources"] == ["pm-declared", "worker-trace"]
    assert by_path["src/b.ts"]["workers"] == ["t-001"]
    assert by_path["src/c.ts"]["sources"] == ["pm-declared"]
    assert data["coverage"]["machine_sources"] == ["pm-tool-result", "worker-trace"]
    assert data["coverage"]["excluded_agenticdoc_count"] == 1
    assert data["coverage"]["unresolved_count"] == 2
    assert data["coverage"]["complete"] is False
    assert result["files"] == ["src/a.ts", "src/b.ts", "src/c.ts"]
    markdown = (project / ".agenticdoc" / KEY / change_set.CHANGE_SET_MD).read_text(encoding="utf-8")
    assert "`src/a.ts`" in markdown and "coverage" in markdown


def test_declared_only_never_claims_complete_coverage(project: Path) -> None:
    write(project, "docs/guide.md")
    achieved(project, "- `docs/guide.md` edited by the PM\n")
    change_set.finalize(project, KEY)
    data = load(project)
    assert data["coverage"]["machine_sources"] == []
    assert data["coverage"]["complete"] is False
    assert "仅 PM 结案声明" in data["coverage"]["note"]
    assert data["files"][0]["sources"] == ["pm-declared"]


@pytest.mark.parametrize(("unobserved_path", "declared_file_exists"), [
    ("src/unobserved.ts", True),
    ("src/unobserved.ts", False),
    ("src/editor layout.ts", True),
    ("src/未观察.ts", True),
    ("Makefile", True),
    ("src/editor.ts，", True),
])
def test_unobserved_declaration_keeps_coverage_incomplete(
    project: Path, unobserved_path: str, declared_file_exists: bool,
) -> None:
    write(project, "src/observed.ts")
    if declared_file_exists:
        write(project, unobserved_path)
    achieved(project, f"- `src/observed.ts`\n- `{unobserved_path}`\n")
    change_set.record(project, KEY, "edit", "src/observed.ts")

    result = change_set.finalize(project, KEY)
    data = load(project)

    assert data["coverage"]["complete"] is False
    assert data["coverage"]["declared_paths_missing_from_machine"] == [unobserved_path]
    assert data["coverage"]["machine_paths_missing_from_declared"] == []
    unobserved = next(item for item in data["files"] if item["path"] == unobserved_path)
    assert unobserved["exists"] is declared_file_exists
    markdown = Path(result["markdown"]).read_text(encoding="utf-8")
    assert f"声明中缺少机器记录的路径：{unobserved_path}" in markdown


def test_all_agenticdoc_paths_are_excluded(project: Path) -> None:
    achieved(project, "- `.agenticdoc/sample-key/evidence/x.md` is process state\n")
    journal(project, {"ts": "2026-01-01T00:00:00+00:00", "key": KEY, "source": "pm-tool-result",
                      "tool": "write", "path": ".agenticdoc/sample-key/evidence/x.md"})
    trace(project, "t-001", "[WRITE_FILE] path=.agenticdoc/_index.parallel")
    change_set.finalize(project, KEY)
    data = load(project)
    assert data["files"] == []
    assert data["coverage"]["excluded_agenticdoc_count"] == 3


def test_machine_path_missing_from_declared_is_reported(project: Path) -> None:
    write(project, "src/a.ts")
    write(project, "src/b.ts")
    achieved(project, "- `src/a.ts`\n")
    journal(project, {"ts": "2026-01-01T00:00:00+00:00", "key": KEY, "source": "pm-tool-result",
                      "tool": "edit", "path": "src/b.ts"})
    change_set.finalize(project, KEY)
    data = load(project)
    assert data["coverage"]["machine_paths_missing_from_declared"] == ["src/b.ts"]
    assert data["coverage"]["complete"] is False
    assert "src/b.ts" in [item["path"] for item in data["files"]]


def test_require_declared_rejects_missing_or_empty_section(project: Path) -> None:
    (project / ".agenticdoc" / KEY / "achieved.md").write_text("## 系统行为变化\nChanged.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="修改面"):
        change_set.finalize(project, KEY, require_declared=True)
    achieved(project, "Prose only, no path token here.\n")
    with pytest.raises(ValueError, match="修改面"):
        change_set.finalize(project, KEY, require_declared=True)


def test_explicit_no_write_statement_is_allowed(project: Path) -> None:
    achieved(project, "无改动。\n")
    change_set.finalize(project, KEY, require_declared=True)
    data = load(project)
    assert data["files"] == []
    assert data["coverage"]["declared_no_write_acknowledged"] is True


def test_declared_parser_ignores_prose_quoted_diffs_and_tables(project: Path) -> None:
    text = ("## 修改面\n\n| 文件 | 说明 |\n| --- | --- |\n| `src/a.ts` | edited |\n\n"
            "```diff\n--- a/src/fake.ts\n+++ b/src/fake.ts\n```\n\n"
            "见 task.md 与 `src/b.ts` 的定义；禁止改 src/forbidden.ts。\n\n## 遗留\nNone.\n")
    paths, acknowledged = change_set.declared_paths(text)
    assert paths == ["src/a.ts", "src/b.ts"]
    assert acknowledged is False


def test_declared_parser_keeps_explicit_root_file_and_windows_paths() -> None:
    text = "## 修改面\n\n| 路径 | 说明 |\n| --- | --- |\n| `Dockerfile` | Update image |\n"
    text += "- `src\\editor layout.ts`\n最后状态是 `DONE`。\n"
    paths, acknowledged = change_set.declared_paths(text)
    assert paths == ["Dockerfile", "src/editor layout.ts"]
    assert acknowledged is False


def test_record_appends_one_event_and_skips_process_state(project: Path) -> None:
    written = change_set.record(project, KEY, "edit", "src/a.ts", ts="2026-01-01T00:00:00+00:00")
    assert written["skipped"] is False and written["event"]["path"] == "src/a.ts"
    skipped = change_set.record(project, KEY, "write", ".agenticdoc/sample-key/evidence/x.md")
    assert skipped["skipped"] is True
    lines = (project / ".agenticdoc" / KEY / change_set.JOURNAL_NAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_cli_finalize_exit_zero(project: Path) -> None:
    import subprocess
    write(project, "src/a.ts")
    achieved(project, "- `src/a.ts`\n")
    cli = Path(change_set.__file__).resolve()
    result = subprocess.run([sys.executable, "-B", str(cli), "finalize", "--project", str(project),
                             "--key", KEY], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert json.loads(result.stdout)["files"] == ["src/a.ts"]
