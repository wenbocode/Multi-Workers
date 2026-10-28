"""Independent AC052 replay control; real isolated writer, synthetic ledger only."""
from __future__ import annotations

import decision_lifecycle as lifecycle
import decision_wire as wire


def test_an_earlier_recorded_executed_event_can_replay_after_a_later_settlement(tmp_path):
    before = dict(status='running', observed_at='2026-10-27T08:00:00+00:00', source='agent-report', completed=None, remaining=[], blockers=None)
    earlier = dict(before, observed_at='2026-10-27T09:00:00+00:00')
    later = dict(before, observed_at='2026-10-27T10:00:00+00:00')
    meta = lifecycle.DecisionMeta.create('pm-replay-fixture', task_key='synthetic-task', initiator_role='pm', logical_id='pm-r2-replay-fixture', task_before=before)
    store = lifecycle.LifecycleStore.test(tmp_path / 'synthetic-ledger', project_id='synthetic-project', redact=wire.SubstringRedactor(['synthetic-known-secret-value']))
    decision_id = 'dp-pm-steer:' + meta.logical_id
    assert lifecycle.record_start(store, meta, decision_id=decision_id).recorded
    args = dict(decision_id=decision_id, action='record', result='synthetic recorded fact; no real action', task_after=earlier, event_id='pm-r2-replay-executed')
    first = lifecycle.record_executed(store, meta, **args)
    assert first.status == 'written'
    assert lifecycle.record_settled(store, meta, decision_id=decision_id, outcome='ok', task_after=later, event_id='pm-r2-replay-settled').recorded
    saved = store.sink.read_bytes()
    again = lifecycle.record_executed(store, meta, **args)
    assert again.status == 'duplicate' and again.recorded
    assert again.event_id == first.event_id
    assert store.sink.read_bytes() == saved
    assert not store.error_sink.exists()
    assert not store.sink.with_name(store.sink.name + '.lock').exists()
