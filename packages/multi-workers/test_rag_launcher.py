"""
test_rag_launcher.py — L1/L2 tests for the launcher-side RAG integration
(T-07, AC-003 / AC-009, VC-022): token env strip/inject symmetry, the D-009
static-fingerprint tear check on the spawn path, and the conductor task.md
block injection (golden parity + idempotence).

Fixtures are shared with test_rag_config.py (test/fixtures/rag/) so the Python
and TS sides consume identical inputs; test/fixtures/rag-block.golden.md is the
byte contract both sides render.
"""
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import launcher  # noqa: E402
import mw_common as mc  # noqa: E402
from autopilot import dispatch as dispatch_mod  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "test" / "fixtures"
RAG_FIXTURES = FIXTURES / "rag"
MACHINE_FIXTURE = (RAG_FIXTURES / "machine-servers.yml").resolve()
PROJECT_FIXTURE = RAG_FIXTURES / "project-servers.yml"
TARGET_FIXTURE = RAG_FIXTURES / "target.yml"
ROOTS_FIXTURE = RAG_FIXTURES / "rag-roots.json"
GOLDEN_BLOCK = FIXTURES / "rag-block.golden.md"
GOLDEN_BLOCK_TEXT = GOLDEN_BLOCK.read_text(encoding="utf-8")
GOLDEN_TASK_META = {"type": "coding", "role": "coding", "phase": "execute"}

# A providers.json-shaped config whose credential set is fully known, so the
# strip assertions are exact (mirrors the fixture in test_launcher.py).
_PROVIDERS = {
    "credentials": {
        "anthropic": {"sources": [{"env": "ANTHROPIC_API_KEY"}]},
        "anthropic-auth": {"sources": [{"env": "ANTHROPIC_AUTH_TOKEN"}]},
        "deepseek": {"sources": [{"env": "DEEPSEEK_API_KEY"}]},
        "timi": {"sources": [{"env": "TIMI_API_KEY"}]},
        "zai-coding-cn": {"sources": [{"env": "ZAI_CODING_CN_API_KEY"}]},
    },
    "providers": {
        "claude": {
            "port": 7001, "base_url_env": "ANTHROPIC_BASE_URL",
            "api_key_env": "ANTHROPIC_API_KEY", "credential": "anthropic",
        },
        "claude-cli": {
            "port": 7003, "base_url_env": "ANTHROPIC_BASE_URL",
            "api_key_env": "ANTHROPIC_AUTH_TOKEN", "credential": "anthropic-auth",
        },
        "deepseek": {
            "port": 7004, "base_url_env": "DEEPSEEK_BASE_URL",
            "api_key_env": "DEEPSEEK_API_KEY", "credential": "deepseek",
        },
        "timi": {"api_key_env": "TIMI_API_KEY", "credential": "timi"},
        "zai-coding-cn": {
            "api_key_env": "ZAI_CODING_CN_API_KEY", "credential": "zai-coding-cn",
        },
    },
}

# Custom machine table: A is enabled by the target below, B is not — B's token
# env name exists only to prove credential isolation (GC) of the inject step.
_CUSTOM_MACHINE = """\
servers:
  A:
    transport: mcp
    mcp:
      url: http://127.0.0.1:9740/mcp
      token_env: OVERCODE_MCP_TOKEN
  B:
    transport: mcp
    mcp:
      url: http://127.0.0.1:9741/mcp
      token_env: DISABLED_MCP_TOKEN
"""
_CUSTOM_TARGET = "rag:\n  enabled: [A]\n  default_server: A\n"


def _verify(tag: str, **kv: object) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


class RagLauncherTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        # Machine layer is a per-test copy so a test may edit it (un-related
        # server change) without touching the shared fixture.
        self.machine = self.root / "machine-rag-servers.yml"
        shutil.copy(MACHINE_FIXTURE, self.machine)
        self._env = mock.patch.dict(os.environ, {"MW_RAG_SERVERS_FILE": str(self.machine)})
        self._env.start()
        self.addCleanup(self._env.stop)

    # ── helpers ──────────────────────────────────────────────────────────

    def _copy(self, src: pathlib.Path, dst: pathlib.Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst)

    def _fixture_project(self, *, project: bool = True, target: bool = True, roots: bool = True) -> None:
        if project:
            self._copy(PROJECT_FIXTURE, self.root / ".mw" / "rag-servers.yml")
        if target:
            self._copy(TARGET_FIXTURE, self.root / ".agenticdoc" / "target.yml")
        if roots:
            self._copy(ROOTS_FIXTURE, self.root / ".mw" / "rag-roots.json")

    def _load(self) -> dict:
        config, error = mc.load_rag_config(self.root)
        self.assertIsNone(error)
        return config

    def _write_task(self, body: str, name: str = "ap-k1-t07") -> pathlib.Path:
        task = self.root / ".agenticdoc" / "k1" / "workers" / name / "task.md"
        task.parent.mkdir(parents=True, exist_ok=True)
        task.write_text(body, encoding="utf-8", newline="\n")
        return task

    def _entry(self, task: pathlib.Path) -> dict[str, str]:
        return {
            "cli": "pi", "provider": "timi", "task_path": str(task),
            "task_key": task.parent.name, "status": "pending",
            "dispatched_at": "2026-08-14T00:00:00+00:00",
            "updated_at": "2026-08-14T00:00:00+00:00", "model": "",
        }

    def _rag_task(self, config: dict, name: str = "ap-k1-t07") -> pathlib.Path:
        content = dispatch_mod.render_task_md(
            "coding", "Do the RAG work.", loop="L", attempt=1,
            rag_config=config, task_meta=GOLDEN_TASK_META,
        )
        return self._write_task(content, name)


# ── AC-009: env injection + credential isolation ──────────────────────────────

class TestInjectRagEnv(RagLauncherTest):
    def test_injects_only_enabled_tokens(self) -> None:
        (self.root / ".agenticdoc").mkdir(parents=True, exist_ok=True)
        (self.root / ".agenticdoc" / "target.yml").write_text(_CUSTOM_TARGET, encoding="utf-8")
        self.machine.write_text(_CUSTOM_MACHINE, encoding="utf-8")
        entry = self._entry(self._write_task("type: coding\n"))
        env = {"PATH": "x"}
        with mock.patch.dict(os.environ, {
            "OVERCODE_MCP_TOKEN": "SECRET-A",
            "DISABLED_MCP_TOKEN": "SECRET-B",
        }):
            launcher.inject_rag_env(env, entry, self.root)
        self.assertEqual(env["OVERCODE_MCP_TOKEN"], "SECRET-A")
        # The declared token of an un-enabled server never leaves serve (GC).
        self.assertNotIn("DISABLED_MCP_TOKEN", env)
        # The token value is env-only: never in task.md, trace.log or worker.log.
        task_text = pathlib.Path(entry["task_path"]).read_text(encoding="utf-8")
        self.assertNotIn("SECRET-A", task_text)
        _verify("VC-013", secret_hits=0, enabled="A", disabled_token_absent="true")

    def test_enabled_servers_still_inject_their_tokens(self) -> None:
        self._fixture_project()
        entry = self._entry(self._write_task("type: coding\n"))
        env: dict[str, str] = {}
        with mock.patch.dict(os.environ, {"OVERCODE_MCP_TOKEN": "SECRET-A"}):
            launcher.inject_rag_env(env, entry, self.root)
        self.assertEqual(env["OVERCODE_MCP_TOKEN"], "SECRET-A")

    def test_disabled_or_absent_config_injects_nothing(self) -> None:
        entry = self._entry(self._write_task("type: coding\n"))
        # No target.yml / project layer -> enabled == [].
        env: dict[str, str] = {"PATH": "x"}
        launcher.inject_rag_env(env, entry, self.root)
        self.assertEqual(env, {"PATH": "x"})
        # Explicit enabled: [] is the same no-op.
        (self.root / ".agenticdoc").mkdir(parents=True, exist_ok=True)
        (self.root / ".agenticdoc" / "target.yml").write_text("rag:\n  enabled: []\n", encoding="utf-8")
        env2: dict[str, str] = {"PATH": "x"}
        launcher.inject_rag_env(env2, entry, self.root)
        self.assertEqual(env2, {"PATH": "x"})
        _verify("VC-001", injected_vars=0)


# ── strip surface: _stripped_env stays the single env.pop point ───────────────

class TestStrippedEnv(RagLauncherTest):
    _CREDS = {
        "TIMI_API_KEY": "timi",
        "ZAI_CODING_CN_API_KEY": "zai",
        "ANTHROPIC_API_KEY": "anthropic",
        "ANTHROPIC_AUTH_TOKEN": "anthropic-auth",
        "DEEPSEEK_API_KEY": "deepseek",
        "OPENAI_API_KEY": "openai",
        "OVERCODE_MCP_TOKEN": "rag-secret",
    }

    def test_strips_provider_and_rag_credentials(self) -> None:
        self._fixture_project()
        config = self._load()
        with mock.patch.dict(os.environ, self._CREDS):
            env = launcher._stripped_env(_PROVIDERS, config)
        for name in self._CREDS:
            self.assertNotIn(name, env, name)
        _verify("VC-013", provider_creds=0, rag_token_envs=0)

    def test_no_rag_config_is_pre_change_golden(self) -> None:
        golden_input = {
            "KEEP_ME": "1",
            "TIMI_API_KEY": "timi",
            "ANTHROPIC_BASE_URL": "http://proxy",
            "OVERCODE_MCP_TOKEN": "rag-secret",
        }
        with mock.patch.dict(os.environ, golden_input, clear=True):
            before = launcher._stripped_env(_PROVIDERS, None)
            unchanged = launcher._stripped_env(
                _PROVIDERS, {"enabled": [], "servers": {}}
            )
        # No RAG config: the declared RAG token env is NOT stripped (pre-change
        # behavior), and an empty config is byte-identical to None.
        self.assertEqual(before, {"KEEP_ME": "1", "OVERCODE_MCP_TOKEN": "rag-secret"})
        self.assertEqual(unchanged, before)

    def test_declared_rag_token_stripped_even_when_disabled(self) -> None:
        # rag_token_env_names covers every declared server, enabled or not.
        self._fixture_project()
        config = self._load()
        config = {**config, "enabled": []}
        with mock.patch.dict(os.environ, self._CREDS):
            env = launcher._stripped_env(_PROVIDERS, config)
        self.assertNotIn("OVERCODE_MCP_TOKEN", env)


# ── VC-022: static-config fingerprint tear check ──────────────────────────────

class TestCheckRagTear(RagLauncherTest):
    def test_matching_fingerprint_passes(self) -> None:
        self._fixture_project()
        config = self._load()
        task = self._rag_task(config)
        launcher.check_rag_tear(self._entry(task), self.root)  # no raise
        self.assertFalse((task.parent / "trace.log").exists())

    def test_enabled_url_change_is_torn(self) -> None:
        self._fixture_project()
        config = self._load()
        task = self._rag_task(config)
        (self.root / ".mw" / "rag-servers.yml").write_text(
            "servers:\n  A:\n    mcp:\n      url: http://127.0.0.1:9999/mcp\n",
            encoding="utf-8",
        )
        with self.assertRaises(RuntimeError) as ctx:
            launcher.check_rag_tear(self._entry(task), self.root)
        self.assertIn("config torn (rag)", str(ctx.exception))
        trace = (task.parent / "trace.log").read_text(encoding="utf-8")
        self.assertIn("[LAUNCHER]", trace)
        self.assertIn("config torn (rag)", trace)
        self.assertNotIn("rag-secret", trace)
        _verify("VC-022", torn_refused="true", unrelated_change_ok="true", health_excluded="true")

    def test_path_roots_content_change_is_torn(self) -> None:
        self._fixture_project()
        config = self._load()
        task = self._rag_task(config)
        (self.root / ".mw" / "rag-roots.json").write_text(
            '{"engine": "/tmp/changed"}\n', encoding="utf-8"
        )
        with self.assertRaises(RuntimeError, msg="path_roots content change must tear"):
            launcher.check_rag_tear(self._entry(task), self.root)

    def test_unenabled_server_change_is_not_torn(self) -> None:
        self._fixture_project(project=False, target=False)
        (self.root / ".agenticdoc").mkdir(parents=True, exist_ok=True)
        (self.root / ".agenticdoc" / "target.yml").write_text(_CUSTOM_TARGET, encoding="utf-8")
        config = self._load()
        task = self._rag_task(config)
        base = config["fingerprint"]
        # B is not enabled: editing its URL must not move the fingerprint.
        self.machine.write_text(
            self.machine.read_text(encoding="utf-8").replace(
                "http://127.0.0.1:9741/mcp", "http://127.0.0.1:9999/mcp"
            ),
            encoding="utf-8",
        )
        changed = self._load()
        self.assertEqual(changed["fingerprint"], base)
        launcher.check_rag_tear(self._entry(task), self.root)  # no raise

    def test_health_state_and_restart_are_not_tears(self) -> None:
        self._fixture_project()
        config = self._load()
        task = self._rag_task(config)
        # A service restart leaves no file changed -> spawn passes.
        launcher.check_rag_tear(self._entry(task), self.root)
        # Probe/health fields are outside the D-009 scope: adding them to a
        # loaded config never moves the fingerprint.
        health = json.loads(json.dumps(config))
        health["servers"]["A"]["health"] = {"ok": False, "probe_ms": 4321}
        health["servers"]["A"]["probe"] = {"reachable": False}
        self.assertEqual(mc.rag_fingerprint(health), config["fingerprint"])

    def test_no_rag_block_is_zero_behavior_change(self) -> None:
        self._fixture_project()
        task = self._write_task("type: coding\nNo RAG here.\n", name="plain")
        # Even with a torn config file, an un-blocked task is never compared.
        self.machine.write_text(
            self.machine.read_text(encoding="utf-8").replace(
                "http://127.0.0.1:9740/mcp", "http://127.0.0.1:9999/mcp"
            ),
            encoding="utf-8",
        )
        launcher.check_rag_tear(self._entry(task), self.root)  # no raise
        self.assertFalse((task.parent / "trace.log").exists())

    def test_malformed_block_without_fingerprint_fails_closed(self) -> None:
        self._fixture_project()
        task = self._write_task(
            "type: coding\n\n" + mc.RAG_MARKER_V1 + "\n[mw] RAG enabled: A\n"
        )
        with self.assertRaises(RuntimeError, msg="malformed rag block must fail closed"):
            launcher.check_rag_tear(self._entry(task), self.root)


# ── conductor task.md injection (golden parity + idempotence) ─────────────────

class TestDispatchRagBlock(RagLauncherTest):
    def test_render_matches_golden_and_is_idempotent(self) -> None:
        self._fixture_project()
        config = self._load()
        text = dispatch_mod.render_task_md(
            "coding", "Do the RAG work.", loop="L", attempt=1,
            rag_config=config, task_meta=GOLDEN_TASK_META,
        )
        self.assertTrue(text.endswith(GOLDEN_BLOCK_TEXT + "\n"))
        # Re-rendering the same input is byte-identical.
        again = dispatch_mod.render_task_md(
            "coding", "Do the RAG work.", loop="L", attempt=1,
            rag_config=config, task_meta=GOLDEN_TASK_META,
        )
        self.assertEqual(again, text)
        # An already-embedded block is replaced wholesale, not duplicated.
        embedded = dispatch_mod.render_task_md(
            "coding", "Do the RAG work.\n\n" + GOLDEN_BLOCK_TEXT,
            loop="L", attempt=1, rag_config=config, task_meta=GOLDEN_TASK_META,
        )
        self.assertEqual(embedded, text)
        self.assertEqual(embedded.count(mc.RAG_MARKER_V1), 1)
        _verify("VC-022", golden_bytes=len(GOLDEN_BLOCK_TEXT.encode("utf-8")), idempotent="true")

    def test_no_rag_config_appends_nothing(self) -> None:
        plain = dispatch_mod.render_task_md("coding", "p", loop="L", attempt=1)
        self.assertNotIn(mc.RAG_MARKER_V1, plain)
        disabled = dispatch_mod.render_task_md(
            "coding", "p", loop="L", attempt=1,
            rag_config={"enabled": [], "servers": {}},
        )
        self.assertNotIn(mc.RAG_MARKER_V1, disabled)

    def test_profile_block_precedes_rag_block(self) -> None:
        self._fixture_project()
        config = self._load()
        profile = "<!-- mw-profile: v2 -->\n[mw] mode: partition"
        text = dispatch_mod.render_task_md(
            "coding", "p", loop="L", attempt=1,
            profile_block=profile, rag_config=config, task_meta=GOLDEN_TASK_META,
        )
        self.assertLess(text.index("<!-- mw-profile: v2 -->"), text.index(mc.RAG_MARKER_V1))
        self.assertTrue(text.endswith(GOLDEN_BLOCK_TEXT + "\n"))

    def test_dispatch_end_to_end_is_stable(self) -> None:
        self._fixture_project()
        first = dispatch_mod.dispatch(
            self.root, "k1", "t07", "repair", "Do the RAG work.",
            loop="L", attempt=1,
        )
        self.assertTrue(first.ok and first.row_verified)
        text = first.task_md.read_text(encoding="utf-8")  # type: ignore[union-attr]
        self.assertIn(mc.RAG_MARKER_V1, text)
        self.assertTrue(text.endswith(GOLDEN_BLOCK_TEXT + "\n"))
        # Re-dispatch over the existing task.md is byte-identical.
        second = dispatch_mod.dispatch(
            self.root, "k1", "t07", "repair", "Do the RAG work.",
            loop="L", attempt=1,
        )
        self.assertTrue(second.ok)
        self.assertEqual(second.task_md.read_text(encoding="utf-8"), text)  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()


# ── spawn-path integration (VC-022: the refusal, not just the check) ──────────

def test_spawn_refuses_torn_rag_config(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """A task.md rag fingerprint that no longer matches the current static
    config must never reach Popen: _spawn's per-task isolation marks it
    failed and both worker.log and trace.log carry 'config torn (rag)'."""
    machine = tmp_path / "machine-rag-servers.yml"
    shutil.copy(MACHINE_FIXTURE, machine)
    monkeypatch.setenv("MW_RAG_SERVERS_FILE", str(machine))
    (tmp_path / ".mw").mkdir(parents=True, exist_ok=True)
    shutil.copy(PROJECT_FIXTURE, tmp_path / ".mw" / "rag-servers.yml")
    shutil.copy(ROOTS_FIXTURE, tmp_path / ".mw" / "rag-roots.json")
    (tmp_path / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    shutil.copy(TARGET_FIXTURE, tmp_path / ".agenticdoc" / "target.yml")

    config, error = mc.load_rag_config(tmp_path)
    assert error is None
    content = dispatch_mod.render_task_md(
        "coding", "Do the RAG work.", loop="L", attempt=1,
        rag_config=config, task_meta=GOLDEN_TASK_META,
    )
    task = tmp_path / ".agenticdoc" / "test-key" / "workers" / "t001" / "task.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text(content, encoding="utf-8", newline="\n")

    # Config moves AFTER dispatch: enabled server A's url changes -> torn.
    (tmp_path / ".mw" / "rag-servers.yml").write_text(
        "servers:\n  A:\n    mcp:\n      url: http://127.0.0.1:9999/mcp\n",
        encoding="utf-8",
    )

    providers_path = tmp_path / "providers.json"
    providers_path.write_text(json.dumps(_PROVIDERS), encoding="utf-8")
    providers = launcher._load_providers(providers_path)
    entry = {
        "task_key": "t001", "status": "pending", "cli": "pi", "provider": "timi",
        "model": "", "task_path": str(task),
        "dispatched_at": "2026-09-19T00:00:00+00:00",
        "updated_at": "2026-09-19T00:00:00+00:00",
    }
    (tmp_path / ".agenticdoc" / "_workers.parallel").write_text(
        mc.serialize_entry(entry) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
    monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
    popped: list[list[str]] = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda cmd, **kw: popped.append(cmd))

    running: dict = {}
    launcher._spawn(entry, tmp_path, providers, running)  # isolated: no exception
    assert "t001" not in running
    assert popped == []  # Popen never reached
    worker_log = (task.parent / "worker.log").read_text(encoding="utf-8")
    assert "config torn (rag)" in worker_log
    trace = (task.parent / "trace.log").read_text(encoding="utf-8")
    assert "[LAUNCHER]" in trace and "config torn (rag)" in trace
    statuses = {e["task_key"]: e["status"] for e in mc.parse_workers_file(
        mc.workers_path(tmp_path)
    )}
    assert statuses["t001"] == "failed"
    _verify("VC-022", torn_refused="true", unrelated_change_ok="true", health_excluded="true")


# ── VC-013 argv: the token is env-only, never on the command line ─────────────

def test_spawn_keeps_rag_token_out_of_argv(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """T-11 discharge of VC-013's `argv_clean` sub-item (T-07/T-08 dispatch
    side): on the real spawn path the token value reaches the child through
    `env` only, and the argv list handed to Popen must not contain it."""
    machine = tmp_path / "machine-rag-servers.yml"
    shutil.copy(MACHINE_FIXTURE, machine)
    monkeypatch.setenv("MW_RAG_SERVERS_FILE", str(machine))
    (tmp_path / ".mw").mkdir(parents=True, exist_ok=True)
    shutil.copy(PROJECT_FIXTURE, tmp_path / ".mw" / "rag-servers.yml")
    shutil.copy(ROOTS_FIXTURE, tmp_path / ".mw" / "rag-roots.json")
    (tmp_path / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    shutil.copy(TARGET_FIXTURE, tmp_path / ".agenticdoc" / "target.yml")

    config, error = mc.load_rag_config(tmp_path)
    assert error is None
    content = dispatch_mod.render_task_md(
        "coding", "Do the RAG work.", loop="L", attempt=1,
        rag_config=config, task_meta=GOLDEN_TASK_META,
    )
    task = tmp_path / ".agenticdoc" / "test-key" / "workers" / "t013" / "task.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text(content, encoding="utf-8", newline="\n")

    providers_path = tmp_path / "providers.json"
    providers_path.write_text(json.dumps(_PROVIDERS), encoding="utf-8")
    providers = launcher._load_providers(providers_path)
    entry = {
        "task_key": "t013", "status": "pending", "cli": "pi", "provider": "timi",
        "model": "", "task_path": str(task),
        "dispatched_at": "2026-09-19T00:00:00+00:00",
        "updated_at": "2026-09-19T00:00:00+00:00",
    }
    (tmp_path / ".agenticdoc" / "_workers.parallel").write_text(
        mc.serialize_entry(entry) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
    monkeypatch.setenv("OVERCODE_MCP_TOKEN", "SECRET123")
    monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
    spawned: list[tuple[list[str], dict]] = []

    class _FakeProc:
        pid = 4242

    def _fake_popen(cmd, **kw):
        spawned.append((list(cmd), kw.get("env", {})))
        return _FakeProc()

    monkeypatch.setattr(launcher.subprocess, "Popen", _fake_popen)

    running: dict = {}
    launcher._spawn(entry, tmp_path, providers, running)
    assert "t013" in running, "spawn must reach Popen on a matching fingerprint"
    assert len(spawned) == 1
    cmd, env = spawned[0]
    assert all("SECRET123" not in part for part in cmd), cmd
    assert "SECRET123" not in " ".join(cmd)
    assert env["OVERCODE_MCP_TOKEN"] == "SECRET123"
    for artifact in (task, task.parent / "worker.log", task.parent / "trace.log"):
        text = artifact.read_text(encoding="utf-8") if artifact.exists() else ""
        assert "SECRET123" not in text, artifact
    _verify(
        "VC-013", secret_hits=0, argv_clean="true", token_in_env="true",
        measured="spawn-argv",
    )
