"""
test_init_source.py — mw init framework source resolution (priority order).

Covers the _resolve_framework_source contract:
  --sync-agentictask override > mw checkout's own framework repo > .tmp cache
  (auto-cloned from the default remote when missing).
Hermetic: tmp dirs + monkeypatched module state; no network, no real clones.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw


def _framework_repo(path: pathlib.Path) -> pathlib.Path:
    """A minimal valid-looking framework source (install.py present)."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "install.py").write_text("# installer\n", encoding="utf-8")
    return path


class TestResolveFrameworkSource:
    def test_sync_override_wins(self, tmp_path, monkeypatch):
        sync = _framework_repo(tmp_path / "sync")
        checkout = _framework_repo(tmp_path / "checkout")
        monkeypatch.setattr(mw, "_checkout_framework_dir", lambda: checkout)
        assert mw._resolve_framework_source(str(sync)) == sync.resolve()

    def test_checkout_repo_preferred_over_cache(self, tmp_path, monkeypatch):
        checkout = _framework_repo(tmp_path / "checkout")
        cache = _framework_repo(tmp_path / "cache")
        monkeypatch.setattr(mw, "_checkout_framework_dir", lambda: checkout)
        monkeypatch.setattr(mw, "_TMP_AGENTICTASK", cache)
        assert mw._resolve_framework_source(None) == checkout

    def test_cache_fallback_when_no_checkout_repo(self, tmp_path, monkeypatch):
        # checkout dir exists but carries no install.py → not a valid source
        empty_checkout = tmp_path / "checkout"
        empty_checkout.mkdir()
        cache = _framework_repo(tmp_path / "cache")
        monkeypatch.setattr(mw, "_checkout_framework_dir", lambda: empty_checkout)
        monkeypatch.setattr(mw, "_TMP_AGENTICTASK", cache)
        assert mw._resolve_framework_source(None) == cache

    def test_auto_clone_when_both_missing(self, tmp_path, monkeypatch, capsys):
        empty_checkout = tmp_path / "checkout"
        empty_checkout.mkdir()
        cache = tmp_path / "cache"  # missing entirely → must be auto-cloned
        monkeypatch.setattr(mw, "_checkout_framework_dir", lambda: empty_checkout)
        monkeypatch.setattr(mw, "_TMP_AGENTICTASK", cache)
        calls = []

        def fake_pull(remote, *, force, branch=mw._DEFAULT_AGENTICTASK_BRANCH):  # noqa: ARG001
            calls.append((remote, force))
            _framework_repo(cache)
            return True, "fake clone"

        monkeypatch.setattr(mw, "_pull_agentictask", fake_pull)
        assert mw._resolve_framework_source(None) == cache
        assert calls == [(mw._DEFAULT_AGENTICTASK_REMOTE, False)]
        assert "auto-pull" in capsys.readouterr().out

    def test_checkout_dir_is_repo_root_based(self, monkeypatch):
        root = pathlib.Path("X:/fake-mw-root")
        monkeypatch.setattr(mw, "_repo_root", lambda: root)
        assert mw._checkout_framework_dir() == root / ".agents" / "skills" / "agentic-task"
