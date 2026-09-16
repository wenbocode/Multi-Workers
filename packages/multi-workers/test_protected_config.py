"""
test_protected_config.py - protected agent-config guard tests (mw-protected-config-guard).

Incident 2026-09-15: a running pi session cleared ~/.pi/agent/auth.json while
other windows were live; every window lost its credentials ("Provider is not
configured: timi"). Rule under test: framework Python code can never target
the shared agent config files with a write; the tool-layer hard block is
tested in packages/coding-agent/test/extensions/agent-team-loop-protected-config.test.ts.

Hermetic: no real file is written; every path check is pure resolution.
"""

import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common

HOME = pathlib.Path.home()
DEFAULT_AGENT_DIR = HOME / ".pi" / "agent"


class TestAgentConfigDir:
    def test_default_is_home_pi_agent(self) -> None:
        assert mw_common.agent_config_dir({}) == DEFAULT_AGENT_DIR

    def test_env_override_absolute_and_tilde(self) -> None:
        alt = HOME / "agent-alt"
        assert mw_common.agent_config_dir({mw_common.AGENT_DIR_ENV: str(alt)}) == alt
        assert mw_common.agent_config_dir({mw_common.AGENT_DIR_ENV: "~/agent-alt"}) == alt


class TestIsProtectedAgentConfig:
    def test_protected_files_in_all_spellings(self) -> None:
        for name in mw_common.PROTECTED_AGENT_CONFIG_FILES:
            assert mw_common.is_protected_agent_config(str(DEFAULT_AGENT_DIR / name))
            assert mw_common.is_protected_agent_config(f"~/.pi/agent/{name}")
        # The agent dir itself (rm -rf semantics) is protected too.
        assert mw_common.is_protected_agent_config("~/.pi/agent")

    def test_custom_agent_dir_env(self) -> None:
        custom = str(HOME / "agent-custom")
        env = {mw_common.AGENT_DIR_ENV: custom}
        assert mw_common.is_protected_agent_config(custom + "/auth.json", env)
        # Defense-in-depth parity with the TS guard: the default ~/.pi/agent
        # stays protected even when the effective dir points elsewhere.
        assert mw_common.is_protected_agent_config("~/.pi/agent/models.json", env)

    def test_non_protected_targets(self) -> None:
        # cwd-relative names, sibling dirs, and agentDir non-config content.
        assert not mw_common.is_protected_agent_config("src/index.ts")
        assert not mw_common.is_protected_agent_config("auth.json")
        assert not mw_common.is_protected_agent_config("~/.pi/agent-alt/auth.json")
        assert not mw_common.is_protected_agent_config("~/.pi/agentx/auth.json")
        assert not mw_common.is_protected_agent_config(str(DEFAULT_AGENT_DIR / "sessions" / "x.json"))
        assert not mw_common.is_protected_agent_config(
            str(DEFAULT_AGENT_DIR / "extensions" / "agent-team-loop.js")
        )

    @pytest.mark.skipif(os.name != "nt", reason="win32 path case-insensitivity")
    def test_windows_case_insensitive(self) -> None:
        assert mw_common.is_protected_agent_config(str(DEFAULT_AGENT_DIR / "AUTH.JSON"))


class TestAssertNotProtected:
    def test_raises_for_protected_with_guidance(self) -> None:
        with pytest.raises(mw_common.ProtectedConfigError, match="cross-window"):
            mw_common.assert_not_protected_agent_config("~/.pi/agent/auth.json", action="delete")
        with pytest.raises(mw_common.ProtectedConfigError, match="pi /login"):
            mw_common.assert_not_protected_agent_config("~/.pi/agent/settings.json")

    def test_passes_for_normal_targets(self) -> None:
        mw_common.assert_not_protected_agent_config("packages/multi-workers/mw.py", action="edit")
        mw_common.assert_not_protected_agent_config("~/.pi/agent/extensions/bundle.js", action="write")
