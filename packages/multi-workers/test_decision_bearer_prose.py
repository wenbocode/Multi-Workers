"""Offline regression for the Bearing dp-pm-steer credential refusal."""

from pathlib import Path

import pytest

import decision
import decision_backends
import decision_points


@pytest.mark.parametrize(
    ("requirements", "known_value", "blocked"),
    [
        pytest.param(
            "browser context加真实受限Bearer header由真实DOM触发请求，走生产TransportAuth优先Bearer；凭据只内存。",
            None, False, id="original-prose",
        ),
        pytest.param(
            "browser context加真实受限Bearer [REDACTED_HEADER_TERM]由真实DOM触发请求，凭据只内存。",
            None, False, id="historical-placeholder",
        ),
        pytest.param("Authorization: Bearer header", None, True, id="explicit-header"),
        pytest.param('{"Authorization": "Bearer header"}', None, True, id="quoted-header"),
        pytest.param("Use Bearer header.fixture-token", None, True, id="bearer-value"),
        pytest.param("Use Bearer header", "header", True, id="known-value"),
    ],
)
def test_pm_steer_bearer_prose_gate(
    tmp_path: Path, requirements: str, known_value: str | None, blocked: bool,
) -> None:
    entry = "dp-pm-steer"
    material = {
        "task_goal": "verify browser behavior",
        "task_requirements": requirements,
        "task_deliverables": "test report",
        "pm_decision_background": "the remaining test needs a scoped fixture",
    }
    preparation = {
        "prepared_at": "2026-11-20T00:00:00+00:00",
        "basis_catalog": [{
            "id": "b-browser",
            "text": "the remaining work is browser verification",
            "material_refs": ["task_requirements"],
            "applies_to": list(decision_points.resolve_entry_choices(entry, material)),
        }],
    }
    selection = next(iter(decision_backends.prepared_selection_options(entry, material, preparation)))
    backend = decision.FakeBackend([decision.BackendOutcome(
        available=True, reason=None, retryable=False, latency_ms=1,
        answers={"decision_selection": {"value": selection, "confidence": 0.9}},
    )])
    config = decision.DecisionConfig(enabled=True, project_root=tmp_path)
    config.api_key = known_value or "bearing-fixture-api-key"
    snapshot = decision.credential_snapshot(config, env={}, auth_path=tmp_path / "no-auth.json")
    client = decision.DecisionClient(config, backend=backend)

    with decision.use_credential_snapshot(snapshot):
        result = client.request_prepared(entry, material, preparation, actor_role="pm")

    if blocked:
        assert result["reason"] == decision.REASON_INPUT_INCOMPLETE
        assert result["issues"] == [{
            "field": "material", "issue": "contains credential-looking evidence; redact before sending",
        }]
        assert backend.calls == []
    else:
        assert result["available"], result
        assert len(backend.calls) == 1
        assert backend.calls[0]["state"]["material"]["task_requirements"] == requirements
