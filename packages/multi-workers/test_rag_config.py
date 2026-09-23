"""
test_rag_config.py — L0/L1 tests for the Python RAG config layer (T-06,
VC-024 / VC-013): two-layer per-field merge + origins, validation, token env
name set, cross-platform machine path, block rendering against the golden
fixture, and the D-009 static fingerprint scope.

Fixtures live in test/fixtures/rag/ so the TS side (T-01/T-04) can consume
the identical inputs; test/fixtures/rag-block.golden.md is the byte contract
both sides render.
"""
import hashlib
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common as mc  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "test" / "fixtures"
RAG_FIXTURES = FIXTURES / "rag"
MACHINE_FIXTURE = (RAG_FIXTURES / "machine-servers.yml").resolve()
PROJECT_FIXTURE = RAG_FIXTURES / "project-servers.yml"
TARGET_FIXTURE = RAG_FIXTURES / "target.yml"
PHASE_ONLY_TARGET = RAG_FIXTURES / "phase-only-target.yml"
ROOTS_FIXTURE = RAG_FIXTURES / "rag-roots.json"
GOLDEN_BLOCK = FIXTURES / "rag-block.golden.md"

# The fixed task the golden block is rendered for.
GOLDEN_TASK_META = {"type": "coding", "role": "coding", "phase": "execute"}


def _verify(tag: str, **kv: object) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


class RagConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self._env = mock.patch.dict(os.environ, {"MW_RAG_SERVERS_FILE": str(MACHINE_FIXTURE)})
        self._env.start()
        self.addCleanup(self._env.stop)

    # ── helpers ──────────────────────────────────────────────────────────

    def _copy_fixture(self, src: pathlib.Path, dst: pathlib.Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst)

    def _load_fixture(
        self, *, project: bool = True, target: bool = True, roots: bool = True
    ) -> tuple[dict, str | None]:
        if project:
            self._copy_fixture(PROJECT_FIXTURE, self.root / ".mw" / "rag-servers.yml")
        if target:
            self._copy_fixture(TARGET_FIXTURE, self.root / ".agenticdoc" / "target.yml")
        if roots:
            self._copy_fixture(ROOTS_FIXTURE, self.root / ".mw" / "rag-roots.json")
        return mc.load_rag_config(self.root)

    def _write_project_layer(self, text: str) -> None:
        path = self.root / ".mw" / "rag-servers.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_target(self, text: str) -> None:
        path = self.root / ".agenticdoc" / "target.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _snapshot(self) -> list[str]:
        return sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))

    # ── VC-024: two-layer per-field merge + origins ──────────────────────

    def test_vc024_merge_matrix(self) -> None:
        config, error = self._load_fixture()
        self.assertIsNone(error)
        a = config["servers"]["A"]
        # Project value wins; everything else is inherited from the machine layer.
        self.assertEqual(a["mcp"]["url"], "http://127.0.0.1:9840/mcp")
        self.assertEqual(a["mcp"]["token_env"], "OVERCODE_MCP_TOKEN")
        self.assertEqual(a["mcp"]["timeout_ms"], 180000)
        self.assertEqual(a["capabilities"], {"graph": True, "chat": True, "rewrite": True})
        self.assertEqual(a["sources"], ["docs", "code"])
        self.assertEqual(a["skill"]["cli_entry"], "python overcode_cli.py")
        self.assertEqual(a["transport"], "both")
        # origin is per field.
        self.assertEqual(a["origin"]["mcp.url"], "project")
        for field in (
            "mcp.token_env",
            "mcp.timeout_ms",
            "capabilities.graph",
            "capabilities.chat",
            "capabilities.rewrite",
            "sources",
            "skill.dir",
            "skill.cli_entry",
            "skill.timeout_ms",
            "transport",
            "adapter",
            "path_roots_file",
        ):
            self.assertEqual(a["origin"][field], "machine", field)

        # Array replace: project `sources: []` clears instead of inheriting.
        # Null delete: project `skill: null` removes the machine block.
        # `transport: mcp` keeps the config valid after the skill block goes.
        self._write_project_layer(
            "servers:\n  A:\n    transport: mcp\n    sources: []\n    skill: null\n"
        )
        config2, error2 = self._load_fixture(project=False)
        self.assertIsNone(error2)
        a2 = config2["servers"]["A"]
        self.assertEqual(a2["sources"], [])
        self.assertEqual(a2["origin"]["sources"], "project")
        self.assertIsNone(a2["skill"])
        self.assertEqual(a2["origin"]["skill"], "project")
        self.assertEqual(a2["transport"], "mcp")
        self.assertEqual(a2["origin"]["transport"], "project")
        self.assertEqual(a2["mcp"]["url"], "http://127.0.0.1:9740/mcp")  # machine value restored
        self.assertEqual(a2["origin"]["mcp.url"], "machine")

        # The untouched machine server B keeps its own values and origins.
        b = config["servers"]["B"]
        self.assertEqual(b["mcp"]["url"], "http://127.0.0.1:9741/mcp")
        self.assertEqual(b["origin"]["mcp.url"], "machine")
        self.assertEqual(b["sources"], [])
        self.assertIsNone(b["skill"])

        _verify(
            "VC-024",
            field_merge="true",
            array_replace="true",
            null_delete="true",
            origin_per_field="true",
        )

    def test_field_camel_mapping_table(self) -> None:
        """The two-side mapping table (YAML snake -> TS camel) is explicit so
        the TS reader cannot drift (T-06 note / T-01 parity)."""
        self.assertEqual(
            mc.RAG_FIELD_CAMEL,
            {
                "token_env": "tokenEnv",
                "timeout_ms": "timeoutMs",
                "cli_entry": "cliEntry",
                "path_roots_file": "pathRootsFile",
                "default_server": "defaultServer",
                "chat_budget": "chatBudget",
                "time_budget_s": "timeBudgetS",
            },
        )

    def test_nested_merge_one_key_at_a_time(self) -> None:
        self._write_project_layer(
            "servers:\n  A:\n    capabilities:\n      graph: false\n"
        )
        config, error = self._load_fixture(project=False)
        self.assertIsNone(error)
        a = config["servers"]["A"]
        self.assertEqual(a["capabilities"], {"graph": False, "chat": True, "rewrite": True})
        self.assertEqual(a["origin"]["capabilities.graph"], "project")
        self.assertEqual(a["origin"]["capabilities.chat"], "machine")
        self.assertEqual(a["origin"]["capabilities.rewrite"], "machine")

    # ── VC-013: token env NAMES only, values never leak ──────────────────

    def test_vc013_token_env_names_only(self) -> None:
        config, error = self._load_fixture()
        self.assertIsNone(error)
        names = mc.rag_token_env_names(config)
        self.assertEqual(names, {"OVERCODE_MCP_TOKEN"})
        self.assertTrue(all(isinstance(name, str) for name in names))

        # The value only exists in the environment; it must not appear in any
        # rendered artifact or error message.
        os.environ["OVERCODE_MCP_TOKEN"] = "SECRET123"
        try:
            block = mc.render_rag_block(config, GOLDEN_TASK_META)
            self.assertIsNotNone(block)
            self.assertNotIn("SECRET123", block)
            self.assertNotIn("SECRET123", repr(names))
            self._write_target("rag:\n  enabled: [Z]\n")
            _config_bad, bad_error = mc.load_rag_config(self.root)
            self.assertIsNotNone(bad_error)
            self.assertIn("'Z'", bad_error)
            self.assertNotIn("SECRET123", bad_error)
        finally:
            del os.environ["OVERCODE_MCP_TOKEN"]
        self.assertEqual(mc.rag_token_env_names({"servers": {"A": {"mcp": {"token_env": "X"}}}}), {"X"})
        self.assertEqual(mc.rag_token_env_names({"servers": {"A": {"mcp": None}}}), set())

        # argv cleanliness is measured on the real spawn path in
        # test_rag_launcher.py::test_spawn_keeps_rag_token_out_of_argv.
        _verify("VC-013", secret_hits=0, argv_clean="measured_in:test_rag_launcher", error_redacted="true")

    # ── rendering: golden + zero-impact ──────────────────────────────────

    def test_golden_block_and_idempotent(self) -> None:
        config, error = self._load_fixture()
        self.assertIsNone(error)
        expected = GOLDEN_BLOCK.read_text(encoding="utf-8")
        block = mc.render_rag_block(config, GOLDEN_TASK_META)
        self.assertEqual(block, expected)
        # Re-rendering the same config/task is byte-identical.
        self.assertEqual(mc.render_rag_block(config, GOLDEN_TASK_META), block)
        self.assertEqual(
            hashlib.sha256(expected.encode("utf-8")).hexdigest(),
            "00f85e646e30d577f434c6e1967a704c65966163a01d1bf4de9630c9717d4035",
        )

    def test_unknown_type_falls_back_to_coding_role(self) -> None:
        """T-16 / D-105: an unregistered `type:` uses the `coding` role spec
        (not the raw type string), mirroring TS `roleForTaskType`."""
        self._copy_fixture(PROJECT_FIXTURE, self.root / ".mw" / "rag-servers.yml")
        self._copy_fixture(ROOTS_FIXTURE, self.root / ".mw" / "rag-roots.json")
        self._write_target(
            "rag:\n"
            "  enabled: [A, B]\n"
            "  default_server: A\n"
            "  roles:\n"
            "    coding:\n"
            "      server: B\n"
        )
        config, error = mc.load_rag_config(self.root)
        self.assertIsNone(error)
        # Registered type -> coding role spec.
        known = mc.render_rag_block(config, {"type": "coding"})
        self.assertIn("[mw] Default server: B", known)
        # Unregistered type -> same coding role spec, not `default_server`.
        unknown = mc.render_rag_block(config, {"type": "foobar"})
        self.assertIn("[mw] Default server: B", unknown)
        # The raw fallback would have picked `default_server: A`, so this is
        # the discriminating assertion for the D-105 change.
        self.assertNotIn("[mw] Default server: A", unknown)
        self.assertEqual(unknown, known)
        _verify("VC-105", py_render_role="coding", type_literal="foobar", server="B")

    def test_render_none_when_disabled_and_writes_nothing(self) -> None:
        self._write_target("rag:\n  enabled: []\n")
        before = self._snapshot()
        config, error = mc.load_rag_config(self.root)
        self.assertIsNone(error)
        self.assertEqual(config["enabled"], [])
        self.assertIsNone(mc.render_rag_block(config, GOLDEN_TASK_META))
        self.assertIsNone(mc.render_rag_block(config, {}))
        self.assertEqual(self._snapshot(), before)

        # No target.yml rag section at all is also "nothing enabled".
        self.root.joinpath(".agenticdoc", "target.yml").unlink()
        config2, error2 = mc.load_rag_config(self.root)
        self.assertIsNone(error2)
        self.assertEqual(config2["enabled"], [])
        self.assertIsNone(mc.render_rag_block(config2, GOLDEN_TASK_META))

    def test_required_union_and_resolved_defaults(self) -> None:
        config, error = self._load_fixture()
        self.assertIsNone(error)
        self.assertTrue(mc._rag_required_for(config, "review", "execute"))  # role only
        self.assertTrue(mc._rag_required_for(config, "coding", "design"))  # phase only
        self.assertFalse(mc._rag_required_for(config, "coding", "execute"))
        self.assertEqual(mc._rag_resolve_defaults(config, "coding", "execute"), ("A", None, False))
        self.assertEqual(mc._rag_resolve_defaults(config, "review", "execute"), ("A", "docs", False))
        # research role: chat/time budgets from the role and rewrite defaulted on.
        self.assertEqual(mc._rag_resolve_defaults(config, "research", "design"), ("A", "docs", True))

    def test_vc111_phase_only_default_parity(self) -> None:
        """T-19: the phase-declared server (A) must survive
        `default_server` (B, no rewrite capability) and a research *phase* alone
        must trip the rewrite default; the TS `resolveDefaults` loads the very
        same fixture and asserts the same triple."""
        self._copy_fixture(PHASE_ONLY_TARGET, self.root / ".agenticdoc" / "target.yml")
        config, error = mc.load_rag_config(self.root)
        self.assertIsNone(error)
        block = mc.render_rag_block(config, {"type": "coding", "phase": "design"})
        self.assertIsNotNone(block)
        lines = (block or "").split("\n")
        server_line = next(line for line in lines if line.startswith("[mw] Default server: "))
        source_line = next(line for line in lines if line.startswith("[mw] Default source: "))
        rewrite_line = next(line for line in lines if line.startswith("[mw] Rewrite: "))
        self.assertEqual(server_line, "[mw] Default server: A")
        self.assertEqual(source_line, "[mw] Default source: docs")
        self.assertEqual(rewrite_line, "[mw] Rewrite: true")
        # Report the parsed values, not the expectation literals (VC-109).
        _verify(
            "VC-111",
            server=server_line.removeprefix("[mw] Default server: "),
            source=source_line.removeprefix("[mw] Default source: "),
            rewrite=rewrite_line.removeprefix("[mw] Rewrite: "),
        )

    def test_load_footprint_is_read_only(self) -> None:
        self._copy_fixture(PROJECT_FIXTURE, self.root / ".mw" / "rag-servers.yml")
        self._copy_fixture(TARGET_FIXTURE, self.root / ".agenticdoc" / "target.yml")
        before = self._snapshot()
        config, error = mc.load_rag_config(self.root)
        self.assertIsNone(error)
        mc.render_rag_block(config, GOLDEN_TASK_META)
        self.assertEqual(self._snapshot(), before)

    # ── D-013: cross-platform machine path ───────────────────────────────

    def test_machine_path_resolution_d013(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td) / "home"
            other = pathlib.Path(td) / "other"
            for base in (home, other):
                (base / ".agents").mkdir(parents=True)
                (base / ".agents" / "rag-servers.yml").write_text(
                    "servers: {}\n", encoding="utf-8"
                )
            # MW_RAG_SERVERS_FILE wins over MW_RAG_SERVERS_HOME.
            with mock.patch.dict(
                os.environ,
                {
                    "MW_RAG_SERVERS_FILE": str(MACHINE_FIXTURE),
                    "MW_RAG_SERVERS_HOME": str(other),
                    "HOME": str(home),
                    "USERPROFILE": str(home),
                },
                clear=True,
            ):
                self.assertEqual(mc.machine_rag_servers_path(), MACHINE_FIXTURE)
            # MW_RAG_SERVERS_HOME (directory override) beats HOME.
            with mock.patch.dict(
                os.environ, {"MW_RAG_SERVERS_HOME": str(other), "HOME": str(home)}, clear=True
            ):
                self.assertEqual(
                    mc.machine_rag_servers_path(), other / ".agents" / "rag-servers.yml"
                )
            # HOME then USERPROFILE.
            with mock.patch.dict(os.environ, {"HOME": str(home)}, clear=True):
                self.assertEqual(
                    mc.machine_rag_servers_path(), home / ".agents" / "rag-servers.yml"
                )
            with mock.patch.dict(os.environ, {"USERPROFILE": str(home)}, clear=True):
                self.assertEqual(
                    mc.machine_rag_servers_path(), home / ".agents" / "rag-servers.yml"
                )
            # A missing layer resolves to None and is never created.
            missing = pathlib.Path(td) / "nope"
            with mock.patch.dict(
                os.environ, {"MW_RAG_SERVERS_HOME": str(missing)}, clear=True
            ):
                self.assertIsNone(mc.machine_rag_servers_path())
            self.assertFalse(missing.exists())
            # An explicit FILE override pointing at a missing file is empty,
            # not a fall-through to HOME.
            with mock.patch.dict(
                os.environ,
                {"MW_RAG_SERVERS_FILE": str(missing / "x.yml"), "HOME": str(home)},
                clear=True,
            ):
                self.assertIsNone(mc.machine_rag_servers_path())

    # ── D-009: fingerprint scope ─────────────────────────────────────────

    def test_fingerprint_scope(self) -> None:
        config, error = self._load_fixture()
        self.assertIsNone(error)
        base = config["fingerprint"]
        self.assertEqual(mc.rag_fingerprint(config), base)  # stable
        self.assertEqual(mc.rag_fingerprint(config, list(config["enabled"])), base)

        # Enabled server url change -> different.
        self._write_project_layer(
            "servers:\n  A:\n    mcp:\n      url: http://127.0.0.1:9999/mcp\n"
        )
        changed_url, _ = self._load_fixture(project=False)
        self.assertNotEqual(changed_url["fingerprint"], base)

        # path_roots file CONTENT change -> different.
        self._copy_fixture(PROJECT_FIXTURE, self.root / ".mw" / "rag-servers.yml")
        roots_path = self.root / ".mw" / "rag-roots.json"
        roots_path.write_text('{"engine": "/tmp/changed"}\n', encoding="utf-8")
        changed_roots, _ = self._load_fixture(project=False, roots=False)
        self.assertNotEqual(changed_roots["fingerprint"], base)

    def test_fingerprint_ignores_unenabled_server(self) -> None:
        machine = self.root / "machine.yml"
        machine.write_text(
            MACHINE_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
        )
        with mock.patch.dict(os.environ, {"MW_RAG_SERVERS_FILE": str(machine)}):
            self._write_target(
                "rag:\n  enabled: [A]\n  default_server: A\n"
                "  roles:\n    review:\n      server: A\n      require: true\n"
            )
            self._copy_fixture(PROJECT_FIXTURE, self.root / ".mw" / "rag-servers.yml")
            self._copy_fixture(ROOTS_FIXTURE, self.root / ".mw" / "rag-roots.json")
            first, error = mc.load_rag_config(self.root)
            self.assertIsNone(error)
            # B is not enabled: editing it must not move the fingerprint.
            machine.write_text(
                machine.read_text(encoding="utf-8").replace(
                    "http://127.0.0.1:9741/mcp", "http://127.0.0.1:9999/mcp"
                ),
                encoding="utf-8",
            )
            second, error2 = mc.load_rag_config(self.root)
            self.assertIsNone(error2)
            self.assertEqual(first["fingerprint"], second["fingerprint"])

    # ── validation errors (never raised, always returned) ────────────────

    def test_validation_errors(self) -> None:
        self._write_target("rag:\n  enabled: [Z]\n")
        _config, error = mc.load_rag_config(self.root)
        self.assertIsNotNone(error)
        self.assertIn("unknown rag server 'Z'", error)
        self.assertIn("available: A, B", error)

        self._write_target("rag:\n  enabled: ['']\n")
        _config, error = mc.load_rag_config(self.root)
        self.assertIn("non-empty", error)

        self._write_target("rag:\n  enabled: [A]\n  default_server: Z\n")
        _config, error = mc.load_rag_config(self.root)
        self.assertIn("unknown rag server 'Z'", error)

        self._write_target(
            "rag:\n  enabled: [A]\n  roles:\n    review:\n      server: Z\n"
        )
        _config, error = mc.load_rag_config(self.root)
        self.assertIn("unknown rag server 'Z'", error)

        self._write_target("rag:\n  enabled: [A]\n  bogus: 1\n")
        _config, error = mc.load_rag_config(self.root)
        self.assertIn("bogus", error)

        # mcp declared but no url.
        self._write_target("rag:\n  enabled: [A]\n")
        self._write_project_layer("servers:\n  A:\n    mcp: null\n")
        _config, error = mc.load_rag_config(self.root)
        self.assertIn("requires mcp.url", error)

        # skill declared but no cli_entry (a project-only server so nothing
        # is inherited from a machine-level skill block).
        self._write_project_layer(
            "servers:\n  C:\n    transport: skill\n    skill:\n      dir: skills/x\n"
        )
        _config, error = mc.load_rag_config(self.root)
        self.assertIn("skill.cli_entry", error)

        # Unknown key inside a server entry.
        self._write_project_layer("servers:\n  A:\n    bogus: 1\n")
        _config, error = mc.load_rag_config(self.root)
        self.assertIn("unknown key(s) bogus", error)

        # Malformed YAML is an error, never an exception.
        self._write_project_layer("servers: [unclosed\n")
        _config, error = mc.load_rag_config(self.root)
        self.assertIsNotNone(error)


if __name__ == "__main__":
    unittest.main()
