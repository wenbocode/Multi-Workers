import hashlib
import json
import os
from pathlib import Path

import mw_version as version


def put(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_inventory_distinguishes_terminal_global_override_and_live_project(tmp_path, monkeypatch):
    home = tmp_path / "home"
    global_root = home / ".local/share/multi-workers"
    releases = global_root / "releases"
    active = put(releases / "active/packages/multi-workers/mw.py")
    old = put(releases / "old/packages/multi-workers/mw.py")
    put(releases / "incomplete/release-manifest.json", "{}")
    put(releases / "active/release-manifest.json", json.dumps({"commit": "b" * 40}))
    global_entry = put(global_root / "bin" / ("mw.cmd" if os.name == "nt" else "mw"), f'python "{active}"')
    local_entry = put(tmp_path / "workspace/.mw/bin/mw.cmd", f'call "{global_entry}"')
    monkeypatch.setattr(version.shutil, "which", lambda name: str(local_entry))
    monkeypatch.setenv("MW_PY", str(old))
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
    put(home / ".pi/agent/extensions/.mw-py-path", str(active))
    project = tmp_path / "project"
    put(project / ".agenticdoc/_index.parallel", "| key | active | EXECUTE | PC:20 |\n"
        "| stale | active | EXECUTE | PC:21 |\n| idle | idle | DONE | PC:30 |\n")
    put(project / ".mw/serve.meta", json.dumps({"pid": 10, "code_dir": str(active.parent)}))
    put(project / ".mw/releases/project-copy/packages/multi-workers/mw.py")
    monkeypatch.setattr(version, "process_runtimes", lambda pids: {10: version.runtime(active), 20: version.runtime(old)})
    # POSIX fixture uses the terminal launcher without the Windows delegate extension.
    if os.name != "nt":
        put(local_entry, f'python "{active}"')
    report = version.versions(project, home)
    assert report["terminal"]["entry"] == str(local_entry)
    assert report["terminal"]["release"] == report["global"]["release"] == "active"
    assert report["global_extension"]["commit"] == "b" * 40
    assert report["terminal"]["uses_global_default"] is True
    assert report["environment_override"]["release"] == "old"
    assert report["backend"]["observed"] is True
    assert report["pm"] == [
        {"key": "key", "pid": 20, **version.runtime(old), "uses_global_default": False},
        {"key": "stale", "pid": 21},
    ]
    assert report["installed_count"] == 2
    assert [item["release"] for item in report["installed"]] == ["active", "old"]
    assert report["project_release_count"] == 1
    assert report["project_releases"][0]["release"] == "project-copy"


def test_unknown_launchers_and_missing_runtimes_are_not_guessed(tmp_path, monkeypatch):
    launcher = put(tmp_path / "bin/mw.cmd", "unknown entry format")
    monkeypatch.setattr(version.shutil, "which", lambda name: str(launcher))
    monkeypatch.delenv("MW_PY", raising=False)
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
    report = version.versions(tmp_path, tmp_path)
    assert report["terminal"] == {"entry": str(launcher)}
    assert report["global"] is report["backend"] is None
    assert report["installed_count"] == 0


def test_registered_windows_cover_multiple_projects_and_preserve_unknown_versions(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    default = put(home / ".local/share/multi-workers/releases/global/packages/multi-workers/mw.py")
    local = put(tmp_path / "snapshot/packages/coding-agent/dist/cli.js")
    put(home / ".local/share/multi-workers/bin" / ("mw.cmd" if os.name == "nt" else "mw"), f'python "{default}"')
    monkeypatch.setattr(version.Path, "home", lambda: home)
    monkeypatch.setattr(version.socket, "gethostname", lambda: "host")
    monkeypatch.setattr(version.time, "time_ns", lambda: 20_000_000_000)
    monkeypatch.setattr(version, "process_runtimes", lambda pids: {20: version.runtime(local)})
    monkeypatch.setattr(version.shutil, "which", lambda name: None)
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
    spool = home / ".mw-pm-channel"
    for project, key, claim, at in (
            ("a", "first", "host:20", 19_000),
            ("b", "second", "host:21", 19_000),
            ("b", "expired", "host:22", 5_000)):
        name = hashlib.sha256(claim.encode()).hexdigest()
        put(spool / (project * 64) / key / f"{name}.json", json.dumps({
            "claim": claim, "binding": "12345678-1234-1234-1234-123456789012", "at": at,
        }))
    put(spool / ("b" * 64) / "forged" / f"{'c' * 64}.json", json.dumps({
        "claim": "host:99", "binding": "12345678-1234-1234-1234-123456789012", "at": 19_000,
    }))
    monkeypatch.setattr("sys.argv", ["mw_version.py", "--pi-window=99", f"--pi-cli={local}"])

    version.main()

    output = capsys.readouterr().out
    assert "全局默认 MW: global" in output
    assert "当前 pi 窗口（PID 99）: snapshot [different from global default]" in output
    assert "已注册在线窗口（2）" in output
    assert "first · aaaaaaaa · host:20: snapshot" in output
    assert "second · bbbbbbbb · host:21: runtime unavailable" in output
    assert "expired" not in output and "forged" not in output
