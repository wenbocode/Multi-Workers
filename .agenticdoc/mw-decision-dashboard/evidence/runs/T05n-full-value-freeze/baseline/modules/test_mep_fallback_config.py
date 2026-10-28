"""T-06 (mw-model-error-perception) — fallback config layer + `mw model` key preservation.

Covers the assertion surface of AC-008/AC-009 on the Python config side:

* `mw_common.validate_fallback_models` / `load_fallback_models` /
  `fallback_models_for_task_type` (format / task-type keys / 1..4 bound /
  CLI-transport rejection / fail-soft read).
* the three `_model_write` callsites in `mw.cmd_model` (set / clear <role> /
  clear all) must not silently drop the top-level `fallback_models` key
  (mw.py `_dispatch_extra_keys` read-modify-write).
* `mw doctor` dispatch section: a malformed block is an ISSUE, a missing
  route / credential is a SUGGESTION (never blocks the launcher precheck).

Hermetic: every project lives under `tmp_path`, credentials come from the
in-test providers dict plus monkeypatched env vars, no network.
"""
import argparse
import pathlib
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw
import mw_common


# ── hermetic providers snapshot (mirrors test_dispatch_models._HERMETIC_CONFIG) ──

_HERMETIC_CONFIG = {
    "credentials": {
        "anthropic": {"sources": [{"env": "ANTHROPIC_API_KEY"}]},
        "anthropic-auth": {"sources": [{"env": "ANTHROPIC_AUTH_TOKEN"}]},
        "deepseek": {"sources": [{"env": "DEEPSEEK_API_KEY"}]},
        "timi": {"sources": [{"env": "TIMI_API_KEY"}]},
    },
    "providers": {
        "claude": {
            "port": 7001, "base_url_env": "ANTHROPIC_BASE_URL",
            "api_key_env": "ANTHROPIC_API_KEY", "credential": "anthropic",
        },
        "deepseek": {
            "port": 7004, "base_url_env": "DEEPSEEK_BASE_URL",
            "api_key_env": "DEEPSEEK_API_KEY", "credential": "deepseek",
        },
        "timi": {"api_key_env": "TIMI_API_KEY", "credential": "timi"},
    },
}


def _write_dispatch(root: pathlib.Path, body: str) -> pathlib.Path:
    (root / ".mw").mkdir(exist_ok=True)
    path = root / ".mw" / "dispatch.yml"
    path.write_text(body, encoding="utf-8")
    return path


def _read_dispatch(root: pathlib.Path) -> dict:
    return yaml.safe_load((root / ".mw" / "dispatch.yml").read_text(encoding="utf-8"))


def _model_args(root: pathlib.Path, action: str, role: str = "", value: str = "",
                *, force: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(root), model_action=action, role=role, value=value, force=force,
    )


def _emit_verify(capsys: pytest.CaptureFixture[str], line: str) -> None:
    with capsys.disabled():
        print(line, flush=True)


# ── validate_fallback_models (pure) ────────────────────────────────────────────


class TestValidateFallbackModels:
    def test_absent_is_not_an_error(self) -> None:
        assert mw_common.validate_fallback_models(None) == ({}, None)

    def test_valid_mapping_is_normalized_and_deduplicated(self) -> None:
        cleaned, err = mw_common.validate_fallback_models({
            "CODING": [" TIMI/GLM-5.3 ", "Timi/GLM-5.3", "claude/claude-sonnet-5"],
        })
        assert err is None
        assert cleaned == {"coding": ["timi/glm-5.3", "claude/claude-sonnet-5"]}

    def test_max_bound_is_four(self) -> None:
        assert mw_common.FALLBACK_MAX_MODELS == 4
        ok, err = mw_common.validate_fallback_models({
            "coding": ["timi/a", "timi/b", "timi/c", "timi/d"],
        })
        assert err is None and ok["coding"] == ["timi/a", "timi/b", "timi/c", "timi/d"]
        over, err = mw_common.validate_fallback_models({
            "coding": ["timi/a", "timi/b", "timi/c", "timi/d", "timi/e"],
        })
        assert over == {} and err is not None and "5 entries" in err

    def test_empty_list_rejected(self) -> None:
        cleaned, err = mw_common.validate_fallback_models({"coding": []})
        assert cleaned == {}
        assert err is not None and "0 entries" in err

    def test_non_mapping_rejected(self) -> None:
        cleaned, err = mw_common.validate_fallback_models(["timi/x"])
        assert cleaned == {}
        assert err is not None and "must be a mapping" in err

    def test_unknown_task_type_rejected(self) -> None:
        # `main` is the PM window and has no worker fallback; a typo is an error.
        for key in ("villain", "main"):
            cleaned, err = mw_common.validate_fallback_models({key: ["timi/x"]})
            assert cleaned == {} and err is not None and "unknown task type" in err, key

    def test_value_must_be_list(self) -> None:
        cleaned, err = mw_common.validate_fallback_models({"coding": "timi/x"})
        assert cleaned == {} and err is not None and "must be a list" in err

    @pytest.mark.parametrize("bad", ["", "   ", 123, ["timi/a", ""]])
    def test_empty_or_non_string_entry_rejected(self, bad: object) -> None:
        cleaned, err = mw_common.validate_fallback_models({"coding": [bad]})
        assert cleaned == {} and err is not None

    def test_multiline_entry_rejected(self) -> None:
        cleaned, err = mw_common.validate_fallback_models({"coding": ["timi/a\nb"]})
        assert cleaned == {} and err is not None and "single line" in err

    def test_malformed_prefix_model_shape_rejected(self) -> None:
        for value in ("timi", "timi/a/b"):
            cleaned, err = mw_common.validate_fallback_models({"coding": [value]})
            assert cleaned == {} and err is not None and "prefix/model" in err, value

    def test_cli_transport_prefix_rejected(self) -> None:
        cleaned, err = mw_common.validate_fallback_models({"coding": ["codex_cli/gpt-5.6-sol"]})
        assert cleaned == {} and err is not None and "CLI transport prefix" in err

    def test_unknown_prefix_rejected(self) -> None:
        cleaned, err = mw_common.validate_fallback_models({"coding": ["openrouter/x"]})
        assert cleaned == {} and err is not None and "unknown prefix" in err

    def test_every_error_is_machine_readable(self) -> None:
        for raw in (["x"], {"villain": ["timi/x"]}, {"coding": []}, {"coding": "x"},
                    {"coding": ["codex_cli/x"]}, {"coding": ["openrouter/x"]}):
            _cleaned, err = mw_common.validate_fallback_models(raw)
            assert err is not None and err.startswith("invalid-config: "), raw


# ── load_fallback_models (file) ────────────────────────────────────────────────


class TestLoadFallbackModels:
    def test_missing_file_is_no_fallback(self, tmp_path: pathlib.Path) -> None:
        assert mw_common.load_fallback_models(tmp_path) == ({}, None)

    def test_absent_key_is_no_fallback(self, tmp_path: pathlib.Path) -> None:
        _write_dispatch(tmp_path, "models:\n  coding: timi/glm-5.3\n")
        assert mw_common.load_fallback_models(tmp_path) == ({}, None)

    def test_valid_block_is_read(self, tmp_path: pathlib.Path) -> None:
        _write_dispatch(tmp_path, "fallback_models:\n  coding: [timi/glm-5.4]\n")
        fallbacks, err = mw_common.load_fallback_models(tmp_path)
        assert err is None and fallbacks == {"coding": ["timi/glm-5.4"]}

    def test_invalid_block_is_fail_soft(self, tmp_path: pathlib.Path) -> None:
        _write_dispatch(tmp_path, "fallback_models:\n  coding: nope\n")
        fallbacks, err = mw_common.load_fallback_models(tmp_path)
        assert fallbacks == {} and err is not None and err.startswith("invalid-config: ")

    def test_broken_yaml_is_fail_soft(self, tmp_path: pathlib.Path) -> None:
        _write_dispatch(tmp_path, "fallback_models: [broken\n")
        fallbacks, err = mw_common.load_fallback_models(tmp_path)
        assert fallbacks == {} and err is not None and "unreadable" in err

    def test_non_mapping_top_level_is_fail_soft(self, tmp_path: pathlib.Path) -> None:
        _write_dispatch(tmp_path, "- just\n- a\n- list\n")
        fallbacks, err = mw_common.load_fallback_models(tmp_path)
        assert fallbacks == {} and err is not None and "top level" in err

    def test_invalid_models_block_does_not_hide_a_valid_fallback_block(
        self, tmp_path: pathlib.Path,
    ) -> None:
        # The two keys are independent (load_dispatch_config is models-only): a
        # validation error in `models` must not suppress a usable fallback block.
        _write_dispatch(
            tmp_path,
            "models:\n  villain: timi/x\nfallback_models:\n  review: [timi/glm-5.4]\n",
        )
        config, config_err = mw_common.load_dispatch_config(tmp_path)
        fallbacks, fallback_err = mw_common.load_fallback_models(tmp_path)
        assert config_err and "villain" in config_err
        assert fallback_err is None and fallbacks == {"review": ["timi/glm-5.4"]}


# ── fallback_models_for_task_type (exact key then role bucket) ─────────────────


class TestFallbackModelsForTaskType:
    def test_exact_type_wins(self) -> None:
        fallbacks = {"coding": ["timi/coding"], "phase-writer": ["timi/phase"]}
        assert mw_common.fallback_models_for_task_type(fallbacks, "phase-writer") == ["timi/phase"]

    def test_role_bucket_covers_sibling_types(self) -> None:
        fallbacks = {"coding": ["timi/coding"], "review": ["timi/review"]}
        for task_type in ("repair", "roadmap-writer", "coding"):
            assert mw_common.fallback_models_for_task_type(fallbacks, task_type) == ["timi/coding"]
        for task_type in ("verifier", "reviewer", "review"):
            assert mw_common.fallback_models_for_task_type(fallbacks, task_type) == ["timi/review"]

    def test_unset_returns_empty(self) -> None:
        assert mw_common.fallback_models_for_task_type({}, "coding") == []
        assert mw_common.fallback_models_for_task_type({"review": ["timi/r"]}, "coding") == []

    def test_unknown_type_falls_to_coding_bucket(self) -> None:
        assert mw_common.fallback_models_for_task_type(
            {"coding": ["timi/c"]}, "not-a-type") == ["timi/c"]

    def test_returned_list_is_a_copy(self) -> None:
        fallbacks = {"coding": ["timi/c"]}
        got = mw_common.fallback_models_for_task_type(fallbacks, "coding")
        got.append("timi/mutated")
        assert fallbacks["coding"] == ["timi/c"]


# ── `_model_write` key preservation (mw.py callsites) ──────────────────────────

_DISPATCH_WITH_FALLBACK = (
    "models:\n"
    "  coding: timi/glm-5.3\n"
    "fallback_models:\n"
    "  coding: [timi/glm-5.4, claude/claude-sonnet-5]\n"
    "note: keep-me\n"
)


class TestModelWritePreservesFallbackKey:
    """mw.py:3524/3539/3553 (current lines 3556/3571/3585) rewrite dispatch.yml
    as a whole file. Each of the three paths must read-modify-write instead."""

    def test_set_preserves_fallback_and_other_top_level_keys(self, tmp_path: pathlib.Path) -> None:
        _write_dispatch(tmp_path, _DISPATCH_WITH_FALLBACK)
        assert mw.cmd_model(_model_args(tmp_path, "set", "review", "deepseek/deepseek-chat")) == 0
        data = _read_dispatch(tmp_path)
        assert data["fallback_models"] == {
            "coding": ["timi/glm-5.4", "claude/claude-sonnet-5"],
        }
        assert data["note"] == "keep-me"
        assert data["models"] == {"coding": "timi/glm-5.3", "review": "deepseek/deepseek-chat"}

    def test_clear_role_preserves_fallback(self, tmp_path: pathlib.Path) -> None:
        _write_dispatch(tmp_path, _DISPATCH_WITH_FALLBACK)
        assert mw.cmd_model(_model_args(tmp_path, "clear", "coding")) == 0
        data = _read_dispatch(tmp_path)
        assert data["fallback_models"] == {
            "coding": ["timi/glm-5.4", "claude/claude-sonnet-5"],
        }
        assert data["note"] == "keep-me"
        # The last role left no `models` mapping; the untouched keys remain.
        assert "models" not in data

    def test_clear_all_keeps_only_the_untouched_keys(self, tmp_path: pathlib.Path) -> None:
        _write_dispatch(tmp_path, _DISPATCH_WITH_FALLBACK)
        assert mw.cmd_model(_model_args(tmp_path, "clear", "all")) == 0
        data = _read_dispatch(tmp_path)
        assert "models" not in data
        assert data["fallback_models"] == {
            "coding": ["timi/glm-5.4", "claude/claude-sonnet-5"],
        }
        assert data["note"] == "keep-me"
        # The preserved key is still readable by the launcher's single reader.
        fallbacks, err = mw_common.load_fallback_models(tmp_path)
        assert err is None and fallbacks["coding"][0] == "timi/glm-5.4"

    def test_sequential_writes_keep_the_key_every_time(self, tmp_path: pathlib.Path) -> None:
        _write_dispatch(tmp_path, _DISPATCH_WITH_FALLBACK)
        assert mw.cmd_model(_model_args(tmp_path, "set", "review", "timi/glm-5.3-air")) == 0
        assert mw.cmd_model(_model_args(tmp_path, "clear", "review")) == 0
        assert mw.cmd_model(_model_args(tmp_path, "set", "research", "timi/glm-5.3-air")) == 0
        data = _read_dispatch(tmp_path)
        assert data["fallback_models"]["coding"] == ["timi/glm-5.4", "claude/claude-sonnet-5"]
        assert data["note"] == "keep-me"

    def test_dispatch_extra_keys_lifts_everything_but_models(self, tmp_path: pathlib.Path) -> None:
        path = _write_dispatch(tmp_path, _DISPATCH_WITH_FALLBACK)
        extra = mw._dispatch_extra_keys(path)
        assert set(extra) == {"fallback_models", "note"}

    def test_dispatch_extra_keys_is_empty_for_missing_or_broken_files(self, tmp_path: pathlib.Path) -> None:
        assert mw._dispatch_extra_keys(tmp_path / ".mw" / "dispatch.yml") == {}
        path = _write_dispatch(tmp_path, "models: [broken\n")
        assert mw._dispatch_extra_keys(path) == {}


# ── doctor fallback checks ─────────────────────────────────────────────────────


class TestDoctorFallback:
    def test_valid_block_is_visible_and_clean(self, tmp_path: pathlib.Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TIMI_API_KEY", "timi-test")
        _write_dispatch(tmp_path, "fallback_models:\n  coding: [timi/glm-5.4]\n")
        report = mw_common.doctor_report(tmp_path, fix=False, config=_HERMETIC_CONFIG)
        assert report["dispatch"]["fallback_models"] == {"coding": ["timi/glm-5.4"]}
        assert "fallback_error" not in report["dispatch"]
        assert not any("fallback_models" in s for s in report["summary"]["issues"])
        assert not any("fallback_models" in s for s in report["summary"]["suggestions"])
        assert "dispatch_fallback: coding=timi/glm-5.4" in mw_common.format_doctor_text(report)

    def test_malformed_block_is_an_issue(self, tmp_path: pathlib.Path) -> None:
        _write_dispatch(tmp_path, "fallback_models:\n  coding: nope\n")
        report = mw_common.doctor_report(tmp_path, fix=False, config=_HERMETIC_CONFIG)
        assert report["dispatch"]["fallback_error"].startswith("invalid-config: ")
        assert any("fallback_models unusable" in i for i in report["summary"]["issues"])
        assert "dispatch_fallback: ERROR" in mw_common.format_doctor_text(report)

    def test_unconfigured_project_keeps_the_section_and_text_unchanged(
        self, tmp_path: pathlib.Path,
    ) -> None:
        _write_dispatch(tmp_path, "models:\n  coding: timi/glm-5.3\n")
        report = mw_common.doctor_report(tmp_path, fix=False, config=_HERMETIC_CONFIG)
        assert "fallback_models" not in report["dispatch"]
        assert "fallback_error" not in report["dispatch"]
        assert "dispatch_fallback" not in mw_common.format_doctor_text(report)

    def test_unknown_route_is_a_suggestion_not_an_issue(self, tmp_path: pathlib.Path) -> None:
        # `zai` has no provider declared in the hermetic config.
        _write_dispatch(tmp_path, "fallback_models:\n  coding: [zai/glm-x]\n")
        report = mw_common.doctor_report(tmp_path, fix=False, config=_HERMETIC_CONFIG)
        assert not any("fallback_models" in i for i in report["summary"]["issues"])
        suggestions = [s for s in report["summary"]["suggestions"] if "fallback_models" in s]
        assert len(suggestions) == 1 and "not configured" in suggestions[0]

    def test_missing_credential_is_a_suggestion(self, tmp_path: pathlib.Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
        _write_dispatch(tmp_path, "fallback_models:\n  coding: [claude/claude-sonnet-5]\n")
        report = mw_common.doctor_report(tmp_path, fix=False, config=_HERMETIC_CONFIG)
        assert not any("fallback_models" in i for i in report["summary"]["issues"])
        suggestions = [s for s in report["summary"]["suggestions"] if "fallback_models" in s]
        assert len(suggestions) == 1 and "credential" in suggestions[0] and "missing" in suggestions[0]

    def test_fallback_error_is_not_swallowed_by_a_broken_models_block(
        self, tmp_path: pathlib.Path,
    ) -> None:
        # A broken dispatch.yml already reports `dispatch.error`; the fallback
        # reader stays silent on that file so it cannot double-report.
        _write_dispatch(tmp_path, "models: [broken\nfallback_models:\n  coding: [timi/x]\n")
        report = mw_common.doctor_report(tmp_path, fix=False, config=_HERMETIC_CONFIG)
        assert report["dispatch"]["error"]
        assert "fallback_error" not in report["dispatch"]

    def test_verify_vc_mep_config(self, tmp_path: pathlib.Path,
                                  monkeypatch: pytest.MonkeyPatch,
                                  capsys: pytest.CaptureFixture[str]) -> None:
        monkeypatch.setenv("TIMI_API_KEY", "timi-test")
        _write_dispatch(tmp_path, _DISPATCH_WITH_FALLBACK)
        preserved = []
        for action, role, value in (("set", "review", "timi/glm-5.3-air"),
                                    ("clear", "review", ""),
                                    ("clear", "all", "")):
            assert mw.cmd_model(_model_args(tmp_path, action, role, value)) == 0
            preserved.append(mw_common.dispatch_config_path(tmp_path).read_text(encoding="utf-8"))
        kept = all("fallback_models" in text for text in preserved)
        assert kept
        report = mw_common.doctor_report(tmp_path, fix=False, config=_HERMETIC_CONFIG)
        _emit_verify(
            capsys,
            f"[VERIFY] VC-MEP-CONFIG: fallback_key_preserved={str(kept).lower()} "
            f"doctor_fallback={'yes' if report['dispatch'].get('fallback_models') else 'no'}",
        )
