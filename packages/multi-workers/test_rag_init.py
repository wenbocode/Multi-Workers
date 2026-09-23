"""
test_rag_init.py — L1 tests for `mw rag init` (T-21 / VC-201, VC-202, VC-203,
VC-204, VC-205, VC-207, VC-208).

Hermetic: every run points MW_RAG_SERVERS_HOME (and HOME/USERPROFILE) at a
temp dir, so the user's real ~/.agents/rag-servers.yml is never read or
written. The subprocess tests run `mw.py` for real (stdin=DEVNULL) so the
zero-interaction contract (D-206) is exercised end to end.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common as mc  # noqa: E402
import rag_templates as rt  # noqa: E402

MW_PY = pathlib.Path(__file__).parent / "mw.py"
SERVERS_REL = pathlib.Path(".mw") / "rag-servers.yml"
TARGET_REL = pathlib.Path(".agenticdoc") / "target.yml"
ROOTS_REL = pathlib.Path(".mw") / "rag-roots.json"
# The 15 field paths the servers template must document (AC-204/VC-205).
SERVER_FIELD_NAMES = (
    "transport", "adapter", "path_roots_file", "sources",
    "capabilities", "graph", "chat", "rewrite",
    "mcp", "url", "token_env", "timeout_ms",
    "skill", "dir", "cli_entry",
)


def _verify(tag: str, **kv: object) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _line_with(text: str, needle: str) -> str:
    for line in text.splitlines():
        if needle in line:
            return line
    raise AssertionError(f"no line contains {needle!r}")


def _init_source_slice() -> str:
    """The `mw rag init` implementation plus its helpers (for the no-input scan)."""
    text = (pathlib.Path(__file__).parent / "mw.py").read_text(encoding="utf-8")
    start = text.index("def _rag_machine_write_path")
    end = text.index("def cmd_rag(")
    return text[start:end]


class RagInitTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = pathlib.Path(self._tmp.name)
        self.root = base / "project"
        self.root.mkdir()
        self.home = base / "home"
        self.home.mkdir()
        self._env = mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "USERPROFILE": str(self.home),
                "MW_RAG_SERVERS_HOME": str(self.home),
                "MW_RAG_SERVERS_FILE": "",
            },
            clear=False,
        )
        self._env.start()
        self.addCleanup(self._env.stop)

    # ── helpers ─────────────────────────────────────────────────────────

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self._run_at(self.root, *args)

    def _run_at(self, project: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(MW_PY), "rag", "init", f"--project={project}", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=60,
            env=dict(os.environ),
        )

    def _snapshot(self) -> dict[str, str]:
        snap: dict[str, str] = {}
        for path in sorted(self.root.rglob("*")):
            if path.is_file():
                snap[str(path.relative_to(self.root))] = _sha(path)
        return snap

    def _machine_path(self) -> pathlib.Path:
        return self.home / ".agents" / "rag-servers.yml"

    def _servers_template(self, transport: str = "mcp") -> str:
        return rt.render_servers_template(
            rt.DEFAULT_SERVER,
            rt.DEFAULT_MCP_URL,
            rt.DEFAULT_TOKEN_ENV,
            transport,
            rt.DEFAULT_SKILL_DIR,
            rt.DEFAULT_SKILL_CLI_ENTRY,
            active_roots=True,
        )

    # ── VC-201 ───────────────────────────────────────────────────────────

    def test_vc201_clean_project_creates_a_usable_config(self) -> None:
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        servers = self.root / SERVERS_REL
        target = self.root / TARGET_REL
        self.assertTrue(servers.is_file())
        self.assertTrue(target.is_file())

        config, error = mc.load_rag_config(self.root)
        self.assertIsNone(error)
        self.assertIn("example", config["servers"])

        listed = subprocess.run(
            [sys.executable, str(MW_PY), "rag", "list", f"--project={self.root}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=60,
            env=dict(os.environ),
        )
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("enabled: (none)", listed.stdout)
        self.assertTrue((self.root / ROOTS_REL).is_file())
        _verify(
            "VC-201",
            created=len(self._snapshot()),
            list_exit=listed.returncode,
            enabled="(none)",
            servers=len(config["servers"]),
        )

    # ── VC-202 ───────────────────────────────────────────────────────────

    def test_vc202_rerun_refuses_then_force_rewrites(self) -> None:
        self.assertEqual(self._run().returncode, 0)
        before = self._snapshot()

        rerun = self._run()
        self.assertEqual(rerun.returncode, 1)
        after_rerun = self._snapshot()
        self.assertEqual(after_rerun, before)  # bytes untouched

        forced = self._run("--force", "--server=renamed")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        after = self._snapshot()
        servers_changed = after[str(SERVERS_REL)] != before[str(SERVERS_REL)]
        target_changed = after[str(TARGET_REL)] != before[str(TARGET_REL)]
        self.assertTrue(servers_changed)
        self.assertTrue(target_changed)
        self.assertIn("renamed:", (self.root / SERVERS_REL).read_text(encoding="utf-8"))
        _verify(
            "VC-202",
            rerun_exit=rerun.returncode,
            rerun_untouched=int(after_rerun == before),
            force_exit=forced.returncode,
            servers_sha_changed=int(servers_changed),
            target_sha_changed=int(target_changed),
        )

    # ── VC-203 ───────────────────────────────────────────────────────────

    def test_vc203_dry_run_and_print_are_pure_reads(self) -> None:
        self.assertEqual(self._run().returncode, 0)
        before = self._snapshot()

        dry = self._run("--dry-run", "--force")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertEqual(self._snapshot(), before)

        printed = self._run("--print")
        self.assertEqual(printed.returncode, 0, printed.stderr)
        self.assertEqual(self._snapshot(), before)
        self.assertIn("servers:", printed.stdout)
        self.assertIn("rag:", printed.stdout)
        self.assertNotIn("wrote ", printed.stdout)
        _verify(
            "VC-203",
            dry_exit=dry.returncode,
            print_exit=printed.returncode,
            tree_equal=int(self._snapshot() == before),
            print_has_servers=int("servers:" in printed.stdout),
            print_has_rag=int("rag:" in printed.stdout),
        )

    # ── VC-204 ───────────────────────────────────────────────────────────

    def test_vc204_zero_interaction(self) -> None:
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)

        init_slice = _init_source_slice()
        self.assertNotIn("input(", init_slice)
        self.assertNotIn("sys.stdin", init_slice)
        templates = (pathlib.Path(__file__).parent / "rag_templates.py").read_text(encoding="utf-8")
        self.assertNotIn("input(", templates)
        self.assertNotIn("sys.stdin", templates)
        _verify(
            "VC-204",
            subprocess_exit=result.returncode,
            input_hits=0,
            stdin_hits=0,
        )

    # ── VC-205 ───────────────────────────────────────────────────────────

    def test_vc205_field_coverage_and_transport_blocks(self) -> None:
        mcp_text = self._servers_template("mcp")
        for name in SERVER_FIELD_NAMES:
            self.assertIn(name, mcp_text, f"missing field name {name!r}")
        self.assertTrue(_line_with(mcp_text, "cli_entry:").lstrip().startswith("#"))
        self.assertFalse(_line_with(mcp_text, "url:").lstrip().startswith("#"))

        skill_text = self._servers_template("skill")
        self.assertTrue(_line_with(skill_text, "url:").lstrip().startswith("#"))
        self.assertFalse(_line_with(skill_text, "cli_entry:").lstrip().startswith("#"))

        both_text = self._servers_template("both")
        self.assertFalse(_line_with(both_text, "url:").lstrip().startswith("#"))
        self.assertFalse(_line_with(both_text, "cli_entry:").lstrip().startswith("#"))

        target_text = rt.render_target_rag_template("example", False, False)
        for key in ("enabled", "default_server", "roles", "phases", "budgets",
                    "server", "source", "require", "rewrite",
                    "chat_budget", "time_budget_s"):
            self.assertIn(key, target_text, f"target template missing {key!r}")
        self.assertIn("role.require OR phase.require", target_text)
        self.assertIn("capabilities.rewrite: true", target_text)
        self.assertIn("design != DESIGN", target_text)
        _verify(
            "VC-205",
            fields=len(SERVER_FIELD_NAMES),
            mcp_cli_commented=int(_line_with(mcp_text, "cli_entry:").lstrip().startswith("#")),
            skill_url_commented=int(_line_with(skill_text, "url:").lstrip().startswith("#")),
            both_active=int(not _line_with(both_text, "url:").lstrip().startswith("#")),
        )

    # ── VC-207 ───────────────────────────────────────────────────────────

    def test_vc207_machine_layer_is_hermetic_and_refuses_rerun(self) -> None:
        result = self._run("--machine")
        self.assertEqual(result.returncode, 0, result.stderr)
        machine = self._machine_path()
        self.assertTrue(machine.is_file())
        self.assertEqual(machine.read_text(encoding="utf-8"), self._servers_template("mcp"))
        self.assertTrue(str(machine).startswith(str(self.home)))
        sha_before = _sha(machine)

        rerun = self._run("--machine")
        self.assertEqual(rerun.returncode, 1)
        self.assertEqual(_sha(machine), sha_before)

        # A second, empty project proves the existing machine layer alone blocks
        # the write: nothing from that project is created either.
        other = pathlib.Path(self._tmp.name) / "project2"
        other.mkdir()
        blocked = self._run_at(other, "--machine")
        self.assertEqual(blocked.returncode, 1)
        self.assertFalse((other / SERVERS_REL).exists())
        self.assertEqual(_sha(machine), sha_before)
        _verify(
            "VC-207",
            machine_written=int(machine.is_file()),
            machine_under_temp_home=int(str(machine).startswith(str(self.home))),
            rerun_exit=rerun.returncode,
            machine_only_refusal=blocked.returncode,
        )

    # ── VC-208 ───────────────────────────────────────────────────────────

    def test_vc208_default_roots_template_resolves_citations(self) -> None:
        """The default template must be usable as-is: `engine` points at the
        project, so a citation whose file really exists audits as ok/0 findings."""
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        roots = self.root / ROOTS_REL
        self.assertTrue(roots.is_file())
        parsed = json.loads(roots.read_text(encoding="utf-8"))
        self.assertIn("_README", parsed)
        self.assertEqual(parsed["engine"], ".")

        servers_text = (self.root / SERVERS_REL).read_text(encoding="utf-8")
        active = [
            line for line in servers_text.splitlines()
            if line.strip().startswith("path_roots_file:")
        ]
        self.assertEqual(len(active), 1, f"expected one active field, got {active}")

        config, error = mc.load_rag_config(self.root)
        self.assertIsNone(error)
        digest = config["servers"]["example"]["path_roots_digest"]
        self.assertTrue(digest)

        # End-to-end: the audit must resolve a citation against the template.
        (self.root / "src").mkdir()
        (self.root / "src" / "foo.ts").write_text("export const x = 1;\n", encoding="utf-8")
        docs = self.root / ".agenticdoc" / "probe" / "rag"
        docs.mkdir(parents=True)
        (docs / "note.md").write_text("see example:docs:engine::src/foo.ts:1\n", encoding="utf-8")
        audited = subprocess.run(
            [sys.executable, str(MW_PY), "rag", "audit", f"--project={self.root}", "--json"],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60,
            encoding="utf-8", errors="replace",
            env=dict(os.environ),
        )
        report = json.loads(audited.stdout)
        self.assertEqual(len(report["citations"]), 1)
        self.assertEqual(report["missing"], [])
        self.assertEqual(report["unverified"], [])
        self.assertEqual(audited.returncode, 0, audited.stdout)
        _verify(
            "VC-208",
            roots_written=int(roots.is_file()),
            digest_len=len(digest),
            citations=len(report["citations"]),
            missing=len(report["missing"]),
            unverified=len(report["unverified"]),
            audit_exit=audited.returncode,
        )

    def test_vc208_no_roots_keeps_the_field_inactive(self) -> None:
        """--no-roots: the file is absent, so the field must stay commented out
        (an active reference to a missing file would break every citation)."""
        result = self._run("--no-roots")
        self.assertEqual(result.returncode, 0, result.stderr)
        roots = self.root / ROOTS_REL
        self.assertFalse(roots.is_file())
        text = (self.root / SERVERS_REL).read_text(encoding="utf-8")
        active = [
            line for line in text.splitlines()
            if line.strip().startswith("path_roots_file:")
        ]
        self.assertEqual(active, [], f"dangling active field: {active}")
        self.assertIn("# path_roots_file: .mw/rag-roots.json", text)

        config, error = mc.load_rag_config(self.root)
        self.assertIsNone(error)
        self.assertIsNone(config["servers"]["example"]["path_roots_file"])
        self.assertIsNone(config["servers"]["example"]["path_roots_digest"])
        _verify(
            "VC-208-noROOTS",
            active_path_roots=len(active),
            digest_is_none=int(config["servers"]["example"]["path_roots_digest"] is None),
        )

    # ── extra contracts ──────────────────────────────────────────────────

    def test_print_is_three_parseable_segments(self) -> None:
        result = self._run("--print")
        self.assertEqual(result.returncode, 0, result.stderr)
        segments: list[list[str]] = []
        current: list[str] | None = None
        for line in result.stdout.splitlines(keepends=True):
            if line.startswith("# ===== file: "):
                current = []
                segments.append(current)
            elif current is not None:
                current.append(line)
        self.assertEqual(len(segments), 3)
        parsed = [yaml.safe_load("".join(seg)) for seg in segments]
        self.assertEqual(set(parsed[0]), {"servers"})
        self.assertEqual(set(parsed[1]), {"rag"})
        self.assertIn("_README", parsed[2])
        _verify(
            "VC-203-print",
            segments=len(segments),
            servers_key=int("servers" in parsed[0]),
            rag_key=int("rag" in parsed[1]),
        )

    def test_enable_writes_enabled_and_default_server(self) -> None:
        result = self._run("--enable")
        self.assertEqual(result.returncode, 0, result.stderr)
        config, error = mc.load_rag_config(self.root)
        self.assertIsNone(error)
        self.assertEqual(config["enabled"], ["example"])
        self.assertEqual(config["default_server"], "example")
        _verify("VC-201-enable", enabled=config["enabled"], default=config["default_server"])

    def test_only_machine_skips_project_files(self) -> None:
        result = self._run("--only-machine")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self._machine_path().is_file())
        self.assertFalse((self.root / SERVERS_REL).exists())
        self.assertFalse((self.root / TARGET_REL).exists())
        self.assertFalse((self.root / ROOTS_REL).exists())

    def test_machine_and_only_machine_conflict(self) -> None:
        result = self._run("--machine", "--only-machine")
        self.assertEqual(result.returncode, 1)
        self.assertIn("mutually exclusive", result.stderr)


if __name__ == "__main__":
    unittest.main()
