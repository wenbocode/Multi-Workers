"""Bounded decide_prepare handoff. This module never calls a decision service."""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import os
import pathlib
import re
from collections.abc import Callable, Mapping
from itertools import combinations

import decision_backends
import decision_file_evidence
import decision_material_sources
import decision_model_context
import decision_points
import decision_signoff_result
import decision_source_scope
import mw_common


PROFILE = "bounded-v1"
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
SOURCE_PATH = re.compile(r"[^\\:\x00-\x1f]+\Z")
STATE_FILE = "prepare.json"
MAX_STATE_BYTES = 1024 * 1024
PREPARE_PROVIDERS = frozenset({"anthropic", "deepseek", "openai", "toa", "zhient", "zai-coding-cn"})


class Refusal(ValueError):
    def __init__(self, status: str, detail: str):
        super().__init__(detail)
        self.status = status


def instant(value: str) -> float:
    stamp = datetime.datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError("expected an absolute deadline")
    return stamp.timestamp()


def _sha(value: object) -> str:
    return decision_signoff_result.canonical_sha256(value)


def _object(path: pathlib.Path) -> dict:
    with path.open("rb") as handle:
        raw = handle.read(MAX_STATE_BYTES + 1)
    if len(raw) > MAX_STATE_BYTES:
        raise Refusal("rejected", "preparation metadata exceeds the read limit")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise Refusal("rejected", "invalid preparation metadata")
    return value


def _read(path: pathlib.Path, cap: int, charge: Callable[[int], None] | None = None) -> tuple[bytes, str]:
    lexical = pathlib.Path(os.path.abspath(path))
    resolved = path.resolve(strict=True)
    if lexical != resolved or not resolved.is_file():
        raise Refusal("rejected", "source must be a regular file at its approved path")
    with resolved.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if before.st_size > cap:
            raise Refusal("budget-exhausted", "source exceeds the inherited read allowance")
        if charge is not None:
            charge(before.st_size)
        raw = handle.read(min(cap, before.st_size) + 1)
        after = os.fstat(handle.fileno())
    current = resolved.stat()
    signature = lambda value: (value.st_dev, value.st_ino, value.st_mtime_ns, value.st_size)
    if signature(before) != signature(after) or signature(after) != signature(current) or path.resolve() != resolved:
        raise Refusal("stale", "source changed during the read")
    if len(raw) > cap:
        raise Refusal("budget-exhausted", "source exceeds the inherited read allowance")
    return raw, hashlib.sha256(raw).hexdigest()


def _source_path(root: pathlib.Path, raw: str) -> pathlib.Path:
    segments = raw.split("/")
    if not SOURCE_PATH.fullmatch(raw) or any(
        part in ("", ".", "..") or part.startswith(".") or part.casefold() in ("auth.json", "credentials.json")
        for part in segments
    ):
        raise Refusal("rejected", "source handles require explicit non-credential project files")
    return root.joinpath(*segments)


def spawn_model(root: pathlib.Path, task_path: pathlib.Path, envelope: str) -> str:
    """Recheck the same grant and card before the launcher loads any credential."""
    task_dir = task_path.resolve().parent
    key = task_dir.parent.parent.name
    header = mw_common.read_task_header_scalar
    card = header(envelope, "card_path") or ""
    pin = header(envelope, "card_sha256")
    if (
        task_dir != root.resolve() / ".agenticdoc" / key / "workers" / task_dir.name
        or header(envelope, "prepare_profile") != PROFILE
        or mw_common.read_task_type(envelope).type != "decide_prepare"
        or not re.fullmatch(r"tasks/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.md", card)
    ):
        raise Refusal("rejected", "restricted preparation requires a canonical dispatched task")
    card_path = task_dir.parent.parent / card
    card_bytes, _ = _read(card_path, MAX_STATE_BYTES)
    requested = header(card_bytes.decode("utf-8-sig"), "model")
    if (
        not requested or requested != header(envelope, "prepare_model")
        or header(card_bytes.decode("utf-8-sig"), "prepare_profile") != PROFILE
        or mw_common.sha256_eol_normalized(card_path) != pin
    ):
        raise Refusal("stale", "restricted preparation card or requested model changed")
    grant_path = root / ".agenticdoc/_runtime/fixed-child-budgets" / key / f"{task_dir.name}.json"
    if grant_path.resolve() != grant_path or grant_path.with_suffix(".json.started").exists():
        raise Refusal("rejected", "restricted preparation has no unused fixed allocation")
    grant = _object(grant_path)
    prepare = grant.get("prepare")
    if (
        grant.get("pin") != pin or grant.get("card") != card or grant.get("task") != task_dir.name
        or type(grant.get("steps")) is not int or grant["steps"] < 1
        or str(grant["steps"]) != header(envelope, "fixed_child_steps")
        or grant.get("deadline") != header(envelope, "fixed_child_deadline")
        or not isinstance(prepare, dict) or prepare.get("model") != requested or not prepare.get("parent_matter_ref")
        or instant(grant["deadline"]) <= datetime.datetime.now(datetime.timezone.utc).timestamp()
    ):
        raise Refusal("budget-exhausted", "the original fixed allocation is missing, expired or changed")
    return requested


def _binding(root: pathlib.Path, key: str, task: str) -> tuple[pathlib.Path, dict, dict, list[str]]:
    if not TOKEN.fullmatch(key) or not TOKEN.fullmatch(task):
        raise Refusal("rejected", "invalid preparation key or task")
    key_dir = root / ".agenticdoc" / key
    task_dir = key_dir / "workers" / task
    if task_dir.resolve() != task_dir or not task_dir.is_dir():
        raise Refusal("rejected", "preparation run directory is unavailable")
    envelope, envelope_sha = _read(task_dir / "task.md", MAX_STATE_BYTES)
    envelope = envelope.decode("utf-8-sig")
    header = mw_common.read_task_header_scalar
    if mw_common.read_task_type(envelope).type != "decide_prepare" or header(envelope, "prepare_profile") != PROFILE:
        raise Refusal("rejected", "task is outside the restricted preparation profile")
    card_ref = header(envelope, "card_path") or ""
    if not re.fullmatch(r"tasks/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.md", card_ref):
        raise Refusal("rejected", "preparation requires a pinned dispatch card")
    card_path = key_dir / card_ref
    card_bytes, _ = _read(card_path, MAX_STATE_BYTES)
    pin = mw_common.sha256_eol_normalized(card_path)
    if pin != header(envelope, "card_sha256"):
        raise Refusal("stale", "the preparation dispatch card changed")
    card = card_bytes.decode("utf-8-sig")
    if header(card, "prepare_profile") != PROFILE or not re.search(r"`parent_matter_ref`\s*[:：]", card):
        raise Refusal("rejected", "the pinned card has no original budget binding")
    grant_path = root / ".agenticdoc/_runtime/fixed-child-budgets" / key / f"{task}.json"
    if grant_path.resolve() != grant_path:
        raise Refusal("rejected", "fixed allocation is outside its original path")
    grant = _object(grant_path)
    run = _object(task_dir / "run.json")
    if (
        grant.get("task") != task or grant.get("card") != card_ref or grant.get("pin") != pin
        or type(grant.get("steps")) is not int or str(grant["steps"]) != header(envelope, "fixed_child_steps")
        or grant["steps"] < 1 or grant.get("deadline") != header(envelope, "fixed_child_deadline")
        or run.get("task_key") != task or run.get("owner_key") != key or run.get("kind") != "decide_prepare"
        or not isinstance(run.get("run_id"), str) or not isinstance(run.get("pid"), int)
        or _read(grant_path.with_suffix(".json.started"), 40)[0].decode() != str(run["pid"])
    ):
        raise Refusal("stale", "the preparation run and fixed allocation differ")
    model = header(envelope, "prepare_model") or ""
    dp = header(card, "prepare_dp") or ""
    point = decision_points.require_active_dp(dp)
    requested = header(card, "model")
    prepare = grant.get("prepare")
    if (
        not requested or model != requested or not isinstance(prepare, dict)
        or prepare.get("model") != model or prepare.get("dp") != dp
        or not prepare.get("parent_matter_ref") or not prepare.get("budget_ref")
    ):
        raise Refusal("rejected", "the preparation model is not the pinned route")
    sources = [item.strip() for item in (header(card, "prepare_sources") or "").split(",")]
    if len(sources) > 16 or len(sources) != len(set(sources)):
        raise Refusal("rejected", "source handles must be unique and bounded")
    for source in sources:
        _source_path(root, source)
    parent_run = header(envelope, "parent_worker_run")
    parent_card_sha = None
    if dp == "dp-w-check-task":
        parent_task = (parent_run or "").split("@", 1)[0]
        if not TOKEN.fullmatch(parent_task) or parent_task == task:
            raise Refusal("rejected", "reachability preparation requires the actual parent Worker run")
        parent_dir = key_dir / "workers" / parent_task
        if parent_dir.resolve() != parent_dir:
            raise Refusal("rejected", "actual Worker parent directory cannot be resolved")
        parent_record = _object(parent_dir / "run.json")
        if (
            parent_record.get("run_id") != parent_run or parent_record.get("status") != "running"
            or parent_record.get("task_key") != parent_task or parent_record.get("owner_key") != key
        ):
            raise Refusal("stale", "the original Worker run changed or ended")
        scope = decision_source_scope.load_worker_source_scope(root, bound_task=parent_dir / "task.md")
        if scope is None:
            raise Refusal("rejected", "the original Worker scope cannot be read")
        for source in sources:
            scope.check_path(_source_path(root, source))
        parent_card_sha = scope.dependency["sha256"]
    return task_dir, {
        "run_id": run["run_id"], "task": task, "key": key, "dp": point.id, "card": card_ref, "card_sha256": pin,
        "envelope_sha256": envelope_sha, "allocation_sha256": _sha(grant), "deadline": grant["deadline"],
        "max_steps": grant["steps"], "requested_model": requested, "model": model,
        "parent_matter_ref": prepare["parent_matter_ref"], "budget_ref": prepare["budget_ref"],
        "parent_run": parent_run, "parent_card_sha256": parent_card_sha,
    }, run, sources


def _current_sources(root: pathlib.Path, state: dict, cap: int) -> None:
    for observed in state["sources"].values():
        raw, digest = _read(_source_path(root, observed["path"]), cap - state["bytes"])
        state["bytes"] += len(raw)
        if digest != observed["sha256"]:
            raise Refusal("stale", "approved source changed since collection")


def _charge_original_read(root: pathlib.Path, binding: dict, size: int) -> None:
    parent_run = binding["parent_run"]
    if binding["dp"] != "dp-w-check-task" or not parent_run:
        return
    parent_task = parent_run.split("@", 1)[0]
    doc = root / ".agenticdoc"
    parent_card = doc / binding["key"] / "workers" / parent_task / "task.md"
    scope = decision_source_scope.load_worker_source_scope(root, bound_task=parent_card)
    if scope is None or scope.dependency["sha256"] != binding["parent_card_sha256"]:
        raise Refusal("stale", "the original Worker scope changed")
    if scope.scope is None:
        return
    file = doc / "_runtime/read-allowance" / binding["key"] / f"{parent_task}.json"
    decision_signoff_result.assert_safe_target(doc, file)
    if not file.is_file():
        raise Refusal("needs-evidence", "the live original Worker read allowance is unavailable")
    lock = file.with_suffix(".json.lock")
    lease = mw_common.acquire_lock(lock, deadline_s=1, delete_on_close=os.name == "nt")
    try:
        allowance = _object(file)
        calls, used = allowance.get("calls"), allowance.get("bytes")
        if (
            allowance.get("run_id") != parent_run or allowance.get("scope_sha256") != binding["parent_card_sha256"]
            or type(calls) is not int or calls < 0
            or type(used) is not int or used < 0
        ):
            raise Refusal("stale", "the live original Worker read allowance belongs to another run")
        if calls >= scope.file_cap or used + size > scope.byte_cap:
            raise Refusal("budget-exhausted", "the original Worker's cumulative read allowance would be exceeded")
        allowance.update(calls=calls + 1, bytes=used + size)
        decision_signoff_result._atomic_write_text(doc, file, json.dumps(allowance) + "\n")
    finally:
        if lease is None:
            mw_common.release_lock(lock)
        else:
            os.close(lease)


def _draft(payload: dict, binding: dict) -> dict:
    material, preparation = payload.get("material"), payload.get("preparation")
    if not isinstance(material, dict) or not isinstance(preparation, dict):
        raise Refusal("needs-evidence", "compose needs typed material and preparation")
    draft = {"material": material, "preparation": preparation}
    if len(json.dumps(draft, ensure_ascii=False).encode("utf-8")) > MAX_STATE_BYTES // 2:
        raise Refusal("rejected", "draft exceeds the preparation artifact limit")
    protocol = "worker" if binding["dp"] == "dp-w-check-task" else "pm"
    issues = decision_points.prepared_request_issues(binding["dp"], material, preparation, actor_role=protocol)
    if issues and not decision_points.only_candidate_coverage_issues(issues):
        status = decision_model_context.auto_preparation_status(issues) if binding["dp"] == "dp-auto" else None
        raise Refusal(status or "needs-evidence", "; ".join(f"{field}: {detail}" for field, detail in issues))
    return draft


def _prepared_input(root: pathlib.Path, state: dict) -> dict:
    """Replace approved citations with their captured text, without opening another file."""
    draft = copy.deepcopy(state["draft"])
    material, preparation = draft["material"], draft["preparation"]
    context = preparation.get("model_context", {})
    if not isinstance(context, Mapping) or not isinstance(context.get("references", {}), Mapping):
        raise Refusal("needs-evidence", "model context and references must be objects")
    refs = dict(context.get("references", {}))
    snapshots = {
        os.path.normcase(str(root / observed["path"])): observed for observed in state["sources"].values()
    }

    def excerpt(path: str, start: int | None, end: int | None, field: str) -> str:
        if not isinstance(path, str):
            raise Refusal("needs-evidence", f"{field}: expected a cited file path")
        lexical = os.path.normcase(os.path.abspath(root / path.replace("\\", "/")))
        captured = snapshots.get(lexical)
        if captured is None:
            raise Refusal("needs-evidence", f"{field}: cite an already-read approved source handle")
        lines = captured["text"].splitlines(keepends=True)
        first, last = 1 if start is None else start, len(lines) if end is None else end
        if type(first) is not int or type(last) is not int or not 1 <= first <= last <= len(lines):
            raise Refusal("needs-evidence", f"{field}: cited line range is outside the approved source")
        return "".join(lines[first - 1:last]).strip()

    for name, ref in refs.items():
        if isinstance(ref, Mapping) and "path" in ref:
            field = f"preparation.model_context.references.{name}"
            lines = ref.get("lines", {})
            if set(ref) - {"kind", "path", "lines"} or not isinstance(lines, Mapping) or set(lines) not in (set(), {"start", "end"}):
                raise Refusal("needs-evidence", f"{field}: expected a file and optional inclusive range")
            refs[name] = {"kind": ref.get("kind"), "text": excerpt(ref["path"], lines.get("start"), lines.get("end"), field)}
    for index, cite in enumerate(decision_material_sources._references(material, preparation=preparation), 1):
        name = f"prepared-source-{index}"
        if name in refs:
            raise Refusal("needs-evidence", "prepare reference name collides with a collected source")
        refs[name] = {"kind": "approved-source-excerpt", "text": excerpt(cite.path, cite.start, cite.end, cite.field)}
    if refs:
        preparation["model_context"] = {**context, "references": refs}
    return {"dp": state["binding"]["dp"], **draft, "evidence_refs": []}


def _projection(root: pathlib.Path, state: dict) -> dict:
    binding = state["binding"]
    draft = _prepared_input(root, state)
    dp, preparation = binding["dp"], draft["preparation"]
    material = decision_points.model_state_for(dp, draft["material"])
    coverage_issues = decision_points.basis_catalog_issues(
        dp, preparation["basis_catalog"], material, require_complete=True,
    )
    options = decision_backends.prepared_selection_options(
        dp, material, preparation, diagnostic_only=decision_points.only_candidate_coverage_issues(coverage_issues),
    )
    questions = decision_backends.build_prepared_questions(dp, material, preparation, options=options)
    try:
        projected = decision_points.prepared_model_request(
            dp, material, preparation, questions, root, key=binding["key"], options=options, evidence_refs=[],
            coverage_issues=coverage_issues,
        )
    except decision_material_sources.SourceMaterialError as error:
        status = decision_model_context.auto_preparation_status(error.issues) if dp == "dp-auto" else None
        raise Refusal(status or "needs-evidence", "; ".join(f"{field}: {detail}" for field, detail in error.issues)) from error
    return {
        "decision_input": draft,
        "pair_map": projected.pair_map,
        "references": projected.get("references"),
        "desc": projected.get("desc"),
        "desc_measurement": decision_model_context.describe_measurement(projected["desc"]),
        "contract_files": projected.file_evidence,
        "projection_sha256": _sha({"state": projected, "questions": questions}),
    }


def _admit_absorber(binding: dict, caller_role: str, parent_run: str | None) -> None:
    required = binding["parent_run"] if binding["dp"] == "dp-w-check-task" else None
    if required is None and caller_role == "pm":
        return
    if required and caller_role != "pm" and parent_run == required:
        return
    raise Refusal("rejected", "preparation must be absorbed by the original PM or the actual parent Worker")


def operate(root: pathlib.Path, payload: dict, *, key: str, task: str, role: str, caller_task: pathlib.Path | None) -> dict:
    action = payload.get("action")
    task_dir, binding, run, approved = _binding(root, key, task)
    parent = _object(caller_task.parent / "run.json")["run_id"] if caller_task is not None else None
    if action == "absorb":
        _admit_absorber(binding, role, parent)
        if run.get("status") not in {"running", "done"} or run.get("aborted"):
            raise Refusal("stale", "the publishing Worker was cancelled or failed")
    elif caller_task != task_dir / "task.md" or run["status"] != "running" or payload.get("effective_model") != binding["model"]:
        raise Refusal("rejected", "only the bound preparation Worker and pinned model can advance this run")
    if instant(binding["deadline"]) <= datetime.datetime.now(datetime.timezone.utc).timestamp():
        raise Refusal("budget-exhausted", "the original fixed allocation has expired")
    file = task_dir / STATE_FILE
    decision_signoff_result.assert_safe_target(task_dir, file)
    lock = file.with_suffix(".lock")
    lease = mw_common.acquire_lock(lock, deadline_s=1, delete_on_close=os.name == "nt")
    try:
        if file.exists():
            state = _object(file)
            if state.get("binding") != binding:
                raise Refusal("stale", "the prepared state belongs to another run, claim allocation or card revision")
        elif action == "begin":
            scope = decision_source_scope.load_worker_source_scope(root)
            if scope is None or not scope.scope:
                raise Refusal("rejected", "the preparation Worker has no authorized read scope")
            state = {"binding": binding, "phase": "new", "sources": {}, "reads": 0, "bytes": 0, "steps": 0,
                     "file_cap": int(scope.file_cap), "byte_cap": int(scope.byte_cap), "audit": []}
        else:
            raise Refusal("out-of-order", "begin is required before advancing the preparation")
        if action != "absorb":
            if state["steps"] >= binding["max_steps"]:
                raise Refusal("budget-exhausted", "the original fixed step allowance has been spent")
            state["steps"] += 1
        result = _transition(root, state, payload, approved)
        if instant(binding["deadline"]) <= datetime.datetime.now(datetime.timezone.utc).timestamp():
            raise Refusal("budget-exhausted", "the original fixed allocation expired during this operation")
        state["audit"].append({"action": action, "phase": state["phase"], "status": result["preparation_status"]})
        document = json.dumps(state, ensure_ascii=False) + "\n"
        if len(document.encode("utf-8")) > MAX_STATE_BYTES:
            raise Refusal("rejected", "the complete preparation artifact exceeds its storage limit")
        decision_signoff_result._atomic_write_text(task_dir, file, document)
        return {**result, "phase": state["phase"], "budget": {
            "allocation_sha256": binding["allocation_sha256"], "deadline": binding["deadline"],
            "steps_used": state["steps"], "steps_limit": binding["max_steps"],
        }, "dp_result": None}
    finally:
        if lease is None:
            mw_common.release_lock(lock)
        else:
            os.close(lease)


def _transition(root: pathlib.Path, state: dict, payload: dict, approved: list[str]) -> dict:
    action, phase = payload.get("action"), state["phase"]
    next_phase = {
        "begin": ("new", "bound"),
        "read": (("bound", "collecting", "prerequisites", "drafted", "discriminability", "validated"), "collecting"),
        "check_inputs": ("collecting", "prerequisites"), "compose": (("prerequisites", "drafted"), "drafted"),
        "check_discriminability": ("drafted", "discriminability"), "validate": ("discriminability", "validated"),
        "publish": ("validated", "published"), "absorb": (("published", "absorbed"), "absorbed"),
    }.get(action)
    result = {"preparation_status": "ready"}
    try:
        if next_phase is None or phase not in ((next_phase[0],) if isinstance(next_phase[0], str) else next_phase[0]):
            raise Refusal("out-of-order", f"{action} is unavailable while preparation is {phase}")
        if action == "begin":
            result["handles"] = {str(number): name for number, name in enumerate(approved, 1)}
        elif action == "read":
            handles = {str(number): name for number, name in enumerate(approved, 1)}
            handle = payload.get("handle")
            if not isinstance(handle, str) or handle not in handles:
                raise Refusal("rejected", "source handle is not part of the pinned dispatch")
            if state["reads"] >= state["file_cap"]:
                raise Refusal("budget-exhausted", "the original read call cap has been spent")
            source = _source_path(root, handles[handle])
            scope = decision_source_scope.load_worker_source_scope(root)
            if scope is None or not scope.scope:
                raise Refusal("rejected", "original read scope is unavailable")
            scope.check_path(source)
            state["reads"] += 1
            raw, digest = _read(
                source, state["byte_cap"] - state["bytes"],
                lambda size: _charge_original_read(root, state["binding"], size),
            )
            state["bytes"] += len(raw)
            body = raw.decode("utf-8-sig")
            if not body.strip() or any(ord(char) < 32 and char not in "\t\r\n" for char in body):
                raise Refusal("rejected", "approved source must contain readable UTF-8 text")
            for stale in ("draft", "comparison", "quality", "revision"):
                state.pop(stale, None)
            state["sources"][handle] = {"path": handles[handle], "sha256": digest, "bytes": len(raw), "text": body}
            result.update({"handle": handle, "text": body, "sha256": digest})
        elif action == "check_inputs":
            if len(state["sources"]) != len(approved):
                raise Refusal("needs-evidence", "read every declared source or return the exact missing handle")
            _current_sources(root, state, state["byte_cap"])
            binding = state["binding"]
            if binding["dp"] == "dp-sign-key":
                key = binding["key"]
                key_dir = root / ".agenticdoc" / key
                review = decision_signoff_result.current_review_binding(key_dir, key)
                result["quality_gate"] = decision_signoff_result.model_quality_gate(key_dir, key, review)
        elif action == "compose":
            state["draft"] = _draft(payload, state["binding"])
        elif action == "check_discriminability":
            projection = _projection(root, state)
            pair_map = projection["pair_map"]
            state["comparison"] = {"draft_sha256": _sha(state["draft"]), "sources_sha256": _sha(state["sources"]),
                                   "pair_map": pair_map, "pairs": [
                                       {"wires": [left, right], "different": [
                                           field for field in ("choice", "finding_ids", "remaining_ids", "basis_text")
                                           if pair_map[left].get(field) != pair_map[right].get(field)
                                       ]}
                                       for left, right in combinations(pair_map, 2)
                                   ]}
            if any(not comparison["different"] for comparison in state["comparison"]["pairs"]):
                raise Refusal("equivalent", "at least one prepared pair has the same business action and reasons")
            result["comparison"] = state["comparison"]
        else:
            _current_sources(root, state, state["byte_cap"])
            if action == "validate":
                state["quality"] = _projection(root, state)
            revision = _sha({name: state[name] for name in ("binding", "draft", "sources", "comparison", "quality")})
            if action == "validate":
                state["revision"] = revision
                result["revision"] = revision
            elif (
                revision != state.get("revision") or payload.get("revision") != revision
                or decision_file_evidence.check_file_evidence(state["quality"]["contract_files"]).changed
            ):
                raise Refusal("stale", "revision or source contract changed since validation")
            elif action == "publish":
                result["revision"] = revision
                result["preparation_status"] = "published"
            else:
                semantic = payload.get("semantic_check")
                if not isinstance(semantic, str) or not semantic.strip() or len(semantic) > 1200:
                    raise Refusal("needs-evidence", "record the original owner's concrete semantic verification")
                if "semantic_check" not in state:
                    state["semantic_check"] = semantic.strip()
                result.update({"preparation_status": "accepted", "revision": revision,
                               "decision_input": state["quality"]["decision_input"],
                               "source_manifest": {handle: {field: value for field, value in item.items() if field != "text"}
                                                   for handle, item in state["sources"].items()},
                               "quality": {key: value for key, value in state["quality"].items() if key != "decision_input"}})
        state["phase"] = next_phase[1]
    except (Refusal, OSError, ValueError, KeyError, TypeError) as error:
        result = {"preparation_status": error.status if isinstance(error, Refusal) else "rejected", "detail": str(error)}
    return result
