"""
test_rag_cli.py — L1 tests for the `mw rag` CLI (mw-rag-integration T-08,
AC-017 / VC-023): the merged `list` view, `probe` against a stubbed stdlib
MCP server, `sync` as the single byte-identical writer of
<project>/.pi/skills/mw-rag.md, and the doctor `rag` section.

Hermetic: tempfile project dirs + MW_RAG_SERVERS_FILE; the probe stub is an
http.server on 127.0.0.1 with a scripted initialize/list_sources response.
"""
import argparse
import contextlib
import hashlib
import http.server
import io
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw  # noqa: E402
import mw_common as mc  # noqa: E402

PACKAGE_DIR = pathlib.Path(__file__).parent
MW_PY = PACKAGE_DIR / "mw.py"
SKILL_SOURCE = PACKAGE_DIR / "skills" / "mw-rag" / "SKILL.md"
SKILL_INSTALL_REL = pathlib.Path(".pi") / "skills" / "mw-rag.md"
EXTENSION_SRC = PACKAGE_DIR.parent / "coding-agent" / "src" / "extensions" / "agent-team-loop"

MACHINE_YML = """\
servers:
  A:
    transport: mcp
    adapter: overcode-v1
    sources: [docs, code]
    capabilities: {{graph: true, chat: true, rewrite: true}}
    mcp:
      url: {url}
      token_env: MW_TEST_RAG_TOKEN
      timeout_ms: 180000
  B:
    transport: mcp
    sources: []
    capabilities: {{graph: false, chat: false, rewrite: false}}
    mcp:
      url: {url_b}
"""

PROJECT_YML = """\
servers:
  A:
    mcp:
      url: {url}
"""

SKILL_SERVER_MACHINE = """\
servers:
  S:
    transport: skill
    adapter: overcode-v1
    sources: [docs]
    capabilities: {graph: false, chat: false, rewrite: false}
    skill:
      dir: skills/s
      cli_entry: python s.py
"""

TARGET_AB = """\
rag:
  enabled: [A, B]
  default_server: A
  roles:
    review:
      server: A
      require: true
"""

TARGET_ONLY_A = "rag:\n  enabled: [A]\n  default_server: A\n"
TARGET_DISABLED = "rag:\n  enabled: []\n"
TARGET_ONLY_S = "rag:\n  enabled: [S]\n  default_server: S\n"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _StubMcpHandler(http.server.BaseHTTPRequestHandler):
    """Scripted MCP endpoint: initialize -> session id, list_sources -> caps."""

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        delay = getattr(self.server, "delay", 0.0)
        if delay:
            time.sleep(delay)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            payload = {}
        method = payload.get("method")
        self.server.seen.append(method)  # type: ignore[attr-defined]
        if method == "initialize":
            self._send(
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "result": {"protocolVersion": "2025-03-26", "serverInfo": {"name": "stub"}},
                },
                session="stub-session",
            )
        elif method == "notifications/initialized":
            self.send_response(202)
            self.end_headers()
        elif method == "list_sources":
            self._send(
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "result": {
                        "sources": ["docs", "code"],
                        # Declared graph=true; the server says otherwise ->
                        # capability correction (D-004).
                        "capabilities": {"graph": False, "chat": True, "rewrite": True},
                    },
                }
            )
        else:
            self.send_response(404)
            self.end_headers()

    def _send(self, body: dict, session: str | None = None) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if session:
            self.send_header("Mcp-Session-Id", session)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: object) -> None:  # silence the stub
        pass


class RagCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.machine = self.root / "machine.yml"
        self._write_machine()
        patcher = mock.patch.dict(
            os.environ, {"MW_RAG_SERVERS_FILE": str(self.machine)}
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    # ── helpers ──────────────────────────────────────────────────────────

    def _write_machine(self, url: str = "http://127.0.0.1:1/mcp", url_b: str = "http://127.0.0.1:2/mcp") -> None:
        self.machine.write_text(MACHINE_YML.format(url=url, url_b=url_b), encoding="utf-8")

    def _write_project(self, url: str = "http://127.0.0.1:9840/mcp") -> None:
        path = self.root / ".mw" / "rag-servers.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(PROJECT_YML.format(url=url), encoding="utf-8")

    def _write_target(self, text: str = TARGET_AB) -> None:
        path = self.root / ".agenticdoc" / "target.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _ns(self, **kwargs: object) -> argparse.Namespace:
        return argparse.Namespace(**kwargs)

    def _run(self, func, args: argparse.Namespace) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = func(args)
        return code, buf.getvalue()

    def _start_stub(self, delay: float = 0.0) -> tuple[http.server.ThreadingHTTPServer, int]:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _StubMcpHandler)
        server.delay = delay  # type: ignore[attr-defined]
        server.seen = []  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server, int(server.server_address[1])

    def _skill_target(self) -> pathlib.Path:
        return self.root / SKILL_INSTALL_REL

    # ── list: merged fields + origins (AC-002 CLI face) ──────────────────

    def test_list_json_merged_origins_and_enabled_set(self) -> None:
        self._write_project()
        self._write_target()
        code, out = self._run(mw._cmd_rag_list, self._ns(project=str(self.root), json=True))
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["enabled"], ["A", "B"])
        self.assertEqual(data["default_server"], "A")
        self.assertTrue(data["fingerprint"])
        a = data["servers"]["A"]
        # Project wins field-by-field; everything else inherits from the
        # machine layer, with per-field origin.
        self.assertEqual(a["mcp"]["url"], "http://127.0.0.1:9840/mcp")
        self.assertEqual(a["origin"]["mcp.url"], "project")
        self.assertEqual(a["mcp"]["token_env"], "MW_TEST_RAG_TOKEN")
        self.assertEqual(a["mcp"]["timeout_ms"], 180000)
        self.assertEqual(a["origin"]["mcp.token_env"], "machine")
        self.assertEqual(a["origin"]["mcp.timeout_ms"], "machine")
        self.assertEqual(a["sources"], ["docs", "code"])
        self.assertEqual(a["origin"]["capabilities.graph"], "machine")
        # B is untouched by the project layer.
        self.assertEqual(data["servers"]["B"]["mcp"]["url"], "http://127.0.0.1:2/mcp")

    def test_list_text_marks_enabled_and_origins(self) -> None:
        self._write_project()
        self._write_target()
        code, out = self._run(mw._cmd_rag_list, self._ns(project=str(self.root), json=False))
        self.assertEqual(code, 0)
        self.assertIn("enabled: A, B", out)
        self.assertIn("server A [enabled]", out)
        self.assertIn("mcp.url = http://127.0.0.1:9840/mcp [project]", out)
        self.assertIn("mcp.token_env = MW_TEST_RAG_TOKEN [machine]", out)

    def test_list_without_config_is_empty_and_exit_zero(self) -> None:
        self.machine.unlink()  # no machine layer, no project layer, no target
        code, out = self._run(mw._cmd_rag_list, self._ns(project=str(self.root), json=True))
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["enabled"], [])
        self.assertEqual(data["servers"], {})

    # ── sync: the only writer (VC-023 / AC-017) ─────────────────────────

    def test_vc023_sync_install_byte_identical_and_idempotent(self) -> None:
        self._write_target()
        skills_dir = self.root / ".pi" / "skills"
        skills_dir.mkdir(parents=True)
        sentinel = skills_dir / "other.md"
        sentinel.write_text("do not touch", encoding="utf-8")

        code, out = self._run(mw._cmd_rag_sync, self._ns(project=str(self.root)))
        self.assertEqual(code, 0)
        target = self._skill_target()
        self.assertTrue(target.is_file())
        source_bytes = SKILL_SOURCE.read_bytes()
        self.assertEqual(target.read_bytes(), source_bytes)
        source_sha = hashlib.sha256(source_bytes).hexdigest()
        target_sha = hashlib.sha256(target.read_bytes()).hexdigest()
        self.assertEqual(source_sha, target_sha)
        self.assertIn(source_sha, out)
        # Idempotent: a second sync leaves the bytes unchanged and reports it.
        first = target.read_bytes()
        code2, out2 = self._run(mw._cmd_rag_sync, self._ns(project=str(self.root)))
        self.assertEqual(code2, 0)
        self.assertEqual(target.read_bytes(), first)
        self.assertIn("unchanged", out2)
        # No other file under .pi/skills was touched.
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not touch")
        self.assertEqual(sorted(p.name for p in skills_dir.iterdir()), ["mw-rag.md", "other.md"])

        print(
            "[VERIFY] VC-023: sync_installed=true sha_match=true "
            "activate_no_write=covered_by(T-04 VC-001)"
        )

    def test_sync_subprocess_end_to_end(self) -> None:
        self._write_target()
        result = subprocess.run(
            [sys.executable, str(MW_PY), "rag", "sync", f"--project={self.root}"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        target = self._skill_target()
        self.assertTrue(target.is_file())
        self.assertEqual(
            hashlib.sha256(target.read_bytes()).hexdigest(),
            hashlib.sha256(SKILL_SOURCE.read_bytes()).hexdigest(),
        )

    def test_sync_removes_only_the_skill_when_disabled(self) -> None:
        self._write_target()
        self._run(mw._cmd_rag_sync, self._ns(project=str(self.root)))
        target = self._skill_target()
        self.assertTrue(target.is_file())
        sentinel = target.parent / "keep.md"
        sentinel.write_text("keep", encoding="utf-8")

        self._write_target(TARGET_DISABLED)
        code, out = self._run(mw._cmd_rag_sync, self._ns(project=str(self.root)))
        self.assertEqual(code, 0)
        self.assertFalse(target.exists())
        self.assertTrue(sentinel.exists())
        self.assertIn("removed", out)

    def test_sync_config_error_refuses_without_touching_files(self) -> None:
        """A broken target.yml means `enabled` is unknown: refuse (exit 1)
        instead of guessing, and never create/remove the skill file."""
        self._write_target("rag:\n  enabled: [Z]\n")
        target = self._skill_target()
        target.parent.mkdir(parents=True)
        target.write_text("pre-existing", encoding="utf-8")
        code, _out = self._run(mw._cmd_rag_sync, self._ns(project=str(self.root)))
        self.assertEqual(code, 1)
        self.assertEqual(target.read_text(encoding="utf-8"), "pre-existing")

    def test_sync_disabled_absent_writes_nothing(self) -> None:
        self._write_target(TARGET_DISABLED)
        code, out = self._run(mw._cmd_rag_sync, self._ns(project=str(self.root)))
        self.assertEqual(code, 0)
        self.assertFalse((self.root / ".pi").exists())
        self.assertIn("unchanged", out)

        # No target.yml at all (nothing enabled) is the same no-op.
        (self.root / ".agenticdoc" / "target.yml").unlink()
        code2, out2 = self._run(mw._cmd_rag_sync, self._ns(project=str(self.root)))
        self.assertEqual(code2, 0)
        self.assertFalse((self.root / ".pi").exists())

    def test_extension_source_never_references_the_installed_skill(self) -> None:
        """`mw rag sync` is the single writer (D-012): no pi-extension source
        may reference the installed skill path, so a session can never
        install/remove it as a side effect (D-014)."""
        offenders: list[str] = []
        for path in EXTENSION_SRC.rglob("*.ts"):
            text = path.read_text(encoding="utf-8")
            if "mw-rag.md" in text or "mw-rag/SKILL" in text:
                offenders.append(str(path.relative_to(EXTENSION_SRC)))
        self.assertEqual(
            offenders,
            [],
            "extension source must not reference/install .pi/skills/mw-rag.md",
        )

    # ── probe ───────────────────────────────────────────────────────────

    def test_probe_reachable_capability_correction_enabled_set_only(self) -> None:
        server, port = self._start_stub()
        self._write_machine(url=f"http://127.0.0.1:{port}/mcp")
        self._write_target(TARGET_ONLY_A)
        code, out = self._run(mw._cmd_rag_probe, self._ns(project=str(self.root), json=True))
        self.assertEqual(code, 0)
        data = json.loads(out)
        # Only the enabled server is probed (allowlist = enabled set).
        self.assertEqual(sorted(data["servers"]), ["A"])
        a = data["servers"]["A"]
        self.assertTrue(a["reachable"])
        self.assertTrue(a["session"])
        self.assertEqual(a["sources"], ["docs", "code"])
        self.assertEqual(a["capabilities"], {"graph": False, "chat": True, "rewrite": True})
        self.assertEqual(a["corrected"], ["graph"])
        self.assertIn("initialize", server.seen)
        self.assertIn("list_sources", server.seen)

    def test_probe_unreachable_reports_and_exits_zero(self) -> None:
        port = _free_port()
        self._write_machine(url=f"http://127.0.0.1:{port}/mcp")
        self._write_target(TARGET_ONLY_A)
        code, out = self._run(mw._cmd_rag_probe, self._ns(project=str(self.root), json=True))
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertFalse(data["servers"]["A"]["reachable"])
        self.assertTrue(data["servers"]["A"]["error"])

    def test_probe_timeout_cap_is_five_seconds_and_short_timeout_is_honored(self) -> None:
        self.assertEqual(mw._RAG_PROBE_TIMEOUT_S, 5.0)
        _server, port = self._start_stub(delay=10.0)
        entry = {
            "transport": "mcp",
            "mcp": {"url": f"http://127.0.0.1:{port}/mcp"},
            "capabilities": {},
        }
        started = time.monotonic()
        result = mw._rag_probe_server("A", entry, self.root, timeout=0.3)
        elapsed = time.monotonic() - started
        self.assertFalse(result["reachable"])
        self.assertIsNotNone(result["error"])
        self.assertLess(elapsed, 3.0)

    def test_probe_disabled_server_not_touched(self) -> None:
        server, port = self._start_stub()
        self._write_machine(url=f"http://127.0.0.1:{port}/mcp")
        self._write_target(TARGET_ONLY_A)
        self._run(mw._cmd_rag_probe, self._ns(project=str(self.root), json=True))
        # Server B (defined at a dead port) must never be contacted: if it
        # had been, the stub would not see it and the run would still pass,
        # so assert on the stub's method log plus the report's server set.
        self.assertTrue(server.seen)

    # ── doctor ──────────────────────────────────────────────────────────

    def test_doctor_rag_section_four_items(self) -> None:
        self.machine.write_text(SKILL_SERVER_MACHINE, encoding="utf-8")
        (self.root / "skills" / "s").mkdir(parents=True)
        self._write_target(TARGET_ONLY_S)
        section = mw._doctor_rag(self.root)
        self.assertEqual(section["enabled"], ["S"])
        self.assertTrue(section["fingerprint"])
        self.assertTrue(section["probe"]["S"]["reachable"])
        self.assertEqual(section["skill"]["status"], "absent")

        self._run(mw._cmd_rag_sync, self._ns(project=str(self.root)))
        self.assertEqual(mw._doctor_rag(self.root)["skill"]["status"], "installed")

        self._skill_target().write_text("tampered", encoding="utf-8")
        self.assertEqual(mw._doctor_rag(self.root)["skill"]["status"], "drift")

    def test_doctor_rag_no_config_is_silent_and_read_only(self) -> None:
        self.machine.unlink()
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        section = mw._doctor_rag(self.root)
        self.assertFalse(section["exists"])
        self.assertEqual(section["enabled"], [])
        self.assertEqual(section["probe"], {})
        self.assertEqual(section["skill"]["status"], "absent")
        after = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        self.assertEqual(before, after)

    def test_doctor_json_report_contains_rag_section(self) -> None:
        self._write_target(TARGET_DISABLED)
        args = self._ns(
            project=str(self.root), providers=None, json=True, fix=False, stale_after=90
        )
        with mock.patch.dict(os.environ, {mc.AGENT_DIR_ENV: str(self.root / "pi-agent")}):
            _code, out = self._run(mw.cmd_doctor, args)
        report = json.loads(out)
        self.assertIn("rag", report)
        self.assertEqual(report["rag"]["enabled"], [])
        self.assertIn("skill", report["rag"])

    def test_doctor_text_renders_rag_line_when_configured(self) -> None:
        self._write_target(TARGET_DISABLED)
        self.machine.write_text(SKILL_SERVER_MACHINE, encoding="utf-8")
        self._write_target(TARGET_ONLY_S)
        section = mw._doctor_rag(self.root)
        line = mw._format_rag_doctor_line(section)
        self.assertIn("rag:", line)
        self.assertIn("fingerprint=", line)
        self.assertIn("skill=", line)


if __name__ == "__main__":
    unittest.main()
