"""
launcher.py — Multi-Workers task launcher.

Polls _workers.parallel for pending tasks and spawns worker processes.
Managed by mw serve; do not run directly in production.

mw-dispatch-reliability changes (design D-001/D-004):
- A task whose credentials/route cannot be resolved is marked failed with the
  reason persisted to its worker.log; it never kills the launcher loop.
- Each poll archives queue entries whose task.md no longer exists.
- Credential resolution and the file bus live in mw_common (single source).

mw-widget-terminal-lifecycle (T-08, AC-012/AC-013):
- Each poll refreshes the launcher beat (.mw/launcher-beat.<pid>) and
  reconciles orphaned running rows (running but not in running_procs):
  positive terminal evidence (an [END] line, or a lone output.md from an old
  bundle) applies unconditionally; evidence-less rows fail as presumed dead
  after the silence window, yielding to another live launcher's fresh beat
  (design D-006~D-008).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common
import tree_watch
from autopilot import config as autopilot_config
from mw_common import (
    acquire_lock as _acquire_lock,
    load_providers as _load_providers,
    lock_path as _lock_path,
    parse_workers_file as _parse_workers_file,
    release_lock as _release_lock,
    serialize_entry as _serialize_entry,
    update_status as _update_status,
    workers_path as _workers_path,
)

DEFAULT_POLL_INTERVAL: int = 5  # seconds — AC-001: must be <= 5

# ── Worker log helper ─────────────────────────────────────────────────────────

def _worker_log_path(entry: dict[str, str]) -> pathlib.Path:
    return pathlib.Path(entry["task_path"]).parent / "worker.log"


def _record_spawn_failure(entry: dict[str, str], msg: str) -> None:
    """Persist the spawn failure reason into the task's worker.log.

    The CLI never ran, so without this the failed status would be unexplained
    (AC-001: the reason must name the missing credential source).
    """
    try:
        log_path = _worker_log_path(entry)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"[launcher] spawn failed ({mw_common.iso_now()}): {msg}\n")
    except OSError:
        pass  # best-effort; the launcher.log line still carries the reason


def _record_envelope_failure(
    entry: dict[str, str],
    reason: str,
    guidance: list[str] | None = None,
) -> None:
    """Persist an envelope refusal into the task's worker.log (T-03/T-14).

    The exact line required by the card is
    ``[launcher] envelope missing: <items> (<path>)`` — the queue row only
    carries a status, so without this the failed row would be undiagnosable.
    T-14 adds optional ``guidance`` lines (one actionable upgrade pointer for
    the skew/legacy branches) written right after the reason. Never raises
    (best-effort, same family as _record_spawn_failure).
    """
    try:
        log_path = _worker_log_path(entry)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"[launcher] {reason}\n")
            for line in guidance or []:
                fh.write(f"[launcher] {line}\n")
            # T-09: a row with no creation timestamp is judged fail-closed and
            # can never show up in the boundary arithmetic afterwards, so
            # stamp the inspection time into the same failure record.
            if not _row_created_raw(entry):
                fh.write(
                    f"[launcher] envelope created={mw_common.iso_now()} "
                    "(row carried no creation timestamp)\n"
                )
    except OSError:
        pass
    print(f"[launcher] {entry['task_key']}: {reason}", file=sys.stderr, flush=True)


def _record_reconcile(entry: dict[str, str], reason: str) -> None:
    """Persist a reconcile decision into the task's worker.log.

    Same family as _record_spawn_failure: a status flip without a persisted
    reason is undiagnosable after the fact (AC-012/AC-013 both require the
    reconcile reason line in worker.log).
    """
    try:
        log_path = _worker_log_path(entry)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"[launcher] reconcile ({mw_common.iso_now()}): {reason}\n")
    except OSError:
        pass  # best-effort; the queue row still carries the terminal status


# ── Provider / env helpers ────────────────────────────────────────────────────

def _stripped_env(config: dict, rag_config: dict | None = None) -> dict[str, str]:
    """Base env for a worker: full inherit minus every declared credential.

    Strip set = all env names declared in credential chains + legacy extras +
    every provider base_url_env (AC-024/AC-025 isolation semantics). When a
    RAG config is supplied, every declared ``mcp.token_env`` NAME is stripped
    as well (T-07/D-010): this stays the single ``env.pop`` point in
    production code, and ``inject_rag_env`` re-adds only the enabled subset
    afterwards. ``rag_config=None`` (or no declared names) keeps the output
    byte-identical to the pre-RAG launcher.
    """
    env = dict(os.environ)
    if rag_config is not None:
        for var in mw_common.rag_token_env_names(rag_config):
            env.pop(var, None)
    for var in mw_common.credential_env_names(config):
        env.pop(var, None)
    for var in mw_common.EXTRA_CREDENTIAL_VARS:
        env.pop(var, None)
    for cfg in config.get("providers", {}).values():
        if isinstance(cfg, dict) and cfg.get("base_url_env"):
            env.pop(str(cfg["base_url_env"]), None)
    return env


def _resolve_entry_model(
    entry: dict[str, str], project_dir: pathlib.Path
) -> tuple[str, str]:
    """Resolve this spawn's model via the dispatch chain.

    task.md `model:` > .mw/dispatch.yml role default > .mw/window-model > ""
    (per-cli hardcoded default, applied in _build_command). Returns
    (model_value, source) with source for diagnostics. A broken dispatch.yml
    never blocks the spawn — it warns once per spawn on stderr (→ mw.log) and
    the chain falls through.
    """
    config, err = mw_common.load_dispatch_config(project_dir)
    if err:
        print(
            f"[launcher] Warning: {err} — model defaults fall back to the "
            "window model / per-cli defaults",
            file=sys.stderr,
        )
    task_type, task_model = _read_task_md_fields(entry["task_path"])
    return mw_common.resolve_dispatch_model(
        cli=entry["cli"].lower(),
        task_type=task_type,
        entry_model=task_model,
        config_models=config.get("models", {}),
        window_model=mw_common.read_window_model(project_dir),
    )


def _read_task_md_fields(task_path: str) -> tuple[str, str]:
    """(type, model) interface lines from a task.md (CRLF-tolerant).

    task.md is the single source of truth for the EXPLICIT per-task model: the
    queue row's model column is a display transport filled by the TS side, and
    a conductor orphan reinsert rewrites it to "" — reading task.md here keeps
    an explicit model: line effective through every path. ('', '') when the
    file is unreadable (the spawn then fails on the missing file anyway).

    `type:` comes from the AC-005 single source `mw_common.read_task_type`
    (T-14): first `type:` of the header region, BOM stripped, never a body
    line. The role must not be decided by any other reading, and this callsite
    shares the function with the worker's `parseTaskMd` / the PM's dispatch
    judgement."""
    try:
        content = pathlib.Path(task_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "", ""
    task_type = mw_common.read_task_type(content).type or ""
    model_m = re.search(r"^model:[ \t]*(\S+)[ \t\r]*$", content, flags=re.MULTILINE)
    return (task_type, model_m.group(1) if model_m else "")


def _model_override_note(
    entry: dict[str, str], project_dir: pathlib.Path, model_value: str, model_source: str
) -> str:
    """One launcher.log line when a task.md `model:` beats a configured role
    default (mw-dispatch-role-escape D-008/AC-009).

    Evidence only: the spawn keeps using the explicit value (the resolution
    chain is unchanged). Without this line the deviation is invisible — the
    only trace of it was the generic `source=task` in the spawn line."""
    if model_source != "task":
        return ""
    task_type, _task_model = _read_task_md_fields(entry["task_path"])
    role = mw_common.TASK_TYPE_TO_ROLE.get(task_type, "coding")
    config, err = mw_common.load_dispatch_config(project_dir)
    if err:
        return ""
    configured = str(config.get("models", {}).get(role, "")).strip()
    requested = model_value.strip()
    if not configured or configured == requested:
        return ""
    return (
        f"[launcher] {entry['task_key']}: model-override "
        f"task={requested} config:{role}={configured}"
    )


def _effective_entry(entry: dict[str, str], model_value: str) -> dict[str, str]:
    """Apply a resolved model value to a queue entry.

    A provider prefix (timi/claude/codex/deepseek/zai) overrides the pi entry's
    provider — the direct connection replaces the original route (this is how
    an unset role inherits the PM window's model across providers). A *_cli
    prefix must match the entry cli (the cli itself never changes: tool
    allowlists / watchdog / [MODEL] badge are pi worker-mode features). Bare
    ids keep the entry route untouched.
    """
    prefix, model_id = mw_common.parse_model_value(model_value)
    if not prefix:
        return {**entry, "model": model_value.strip()}
    if prefix in mw_common.MODEL_PREFIX_TO_PI_PROVIDER:
        if entry["cli"].lower() != "pi":
            raise RuntimeError(
                f"model {model_value!r} needs a pi entry, but the task's cli is "
                f"{entry['cli']!r} — fix the task.md model: line or the cli"
            )
        return {**entry, "model": model_id, "provider": mw_common.MODEL_PREFIX_TO_PI_PROVIDER[prefix]}
    if prefix in mw_common.CLI_PREFIX_TO_CLI:
        expected = mw_common.CLI_PREFIX_TO_CLI[prefix]
        if entry["cli"].lower() != expected:
            raise RuntimeError(
                f"model {model_value!r} needs a {expected} entry, but the task's "
                f"cli is {entry['cli']!r} — fix the task.md model: line or the cli"
            )
        # The CLI transport owns its own auth; a stale provider column from
        # the queue row must not leak into route validation (codex rejects
        # any provider but ""/"codex").
        return {**entry, "model": model_id, "provider": ""}
    raise RuntimeError(
        f"model {model_value!r} has unknown prefix {prefix!r} "
        f"(valid: {', '.join(sorted(mw_common.KNOWN_MODEL_PREFIXES))})"
    )


def _build_env(
    entry: dict[str, str], config: dict, rag_config: dict | None = None
) -> dict[str, str]:
    """Build the environment dict for a worker process (AC-002~004, AC-008~010, AC-024).

    ``rag_config`` only widens the credential strip set (``_stripped_env``);
    RAG injection itself is the post-step ``inject_rag_env`` so none of the
    six return paths below needs to know about RAG (D-010)."""
    cli = entry["cli"].lower()
    provider = entry.get("provider", "").strip()

    # Pi + timi: use Timi credentials directly (no localhost proxy) (AC-008).
    # Source chain: env TIMI_API_KEY → pi's own ~/.pi/agent/auth.json.
    if cli == "pi" and provider == "timi":
        cred = config.get("credentials", {}).get("timi")
        value, _source = mw_common.resolve_credential(cred, os.environ)
        if value is None:
            raise RuntimeError(
                f"Timi credential is not available ({mw_common.describe_missing(cred)})."
            )
        env = _stripped_env(config, rag_config)
        env["TIMI_API_KEY"] = value
        if "TIMI_BASE_URL" in os.environ:
            env["TIMI_BASE_URL"] = os.environ["TIMI_BASE_URL"]
        task_path = pathlib.Path(entry["task_path"])
        env["PI_WORKER_TASK"] = str(task_path.resolve())
        return env

    # Pi + zai-coding-cn (model prefix zai/...): direct provider connection,
    # same shape as the timi branch. Source chain: env ZAI_CODING_CN_API_KEY
    # → pi's own ~/.pi/agent/auth.json (field zai-coding-cn.key). No base URL
    # passthrough: the pi provider pins the coding endpoint.
    if cli == "pi" and provider == "zai-coding-cn":
        cred = config.get("credentials", {}).get("zai-coding-cn")
        value, _source = mw_common.resolve_credential(cred, os.environ)
        if value is None:
            raise RuntimeError(
                f"zai-coding-cn credential is not available "
                f"({mw_common.describe_missing(cred)})."
            )
        env = _stripped_env(config, rag_config)
        env["ZAI_CODING_CN_API_KEY"] = value
        task_path = pathlib.Path(entry["task_path"])
        env["PI_WORKER_TASK"] = str(task_path.resolve())
        return env

    # Pi + openai-codex (model prefix codex/...): direct native provider —
    # codex's own config carries the auth, so only strip proxy credentials
    # (same isolation policy as the codex CLI branch below).
    if cli == "pi" and provider == "openai-codex":
        env = _stripped_env(config, rag_config)
        task_path = pathlib.Path(entry["task_path"])
        env["PI_WORKER_TASK"] = str(task_path.resolve())
        return env

    # Pi + anthropic / deepseek (model prefixes claude/... deepseek/...):
    # DIRECT provider connections — no mw proxy base URL. The credential is
    # injected from the same provider chain the proxy route uses; an explicit
    # *_BASE_URL in the serve environment passes through (custom gateway).
    if cli == "pi" and provider in ("anthropic", "deepseek"):
        credential_name = provider
        key_env = "ANTHROPIC_API_KEY" if provider == "anthropic" else "DEEPSEEK_API_KEY"
        base_env = "ANTHROPIC_BASE_URL" if provider == "anthropic" else "DEEPSEEK_BASE_URL"
        cred = config.get("credentials", {}).get(credential_name)
        value, _source = mw_common.resolve_credential(cred, os.environ)
        if value is None:
            raise RuntimeError(
                f"{provider} credential is not available for the direct route "
                f"({mw_common.describe_missing(cred)})."
            )
        env = _stripped_env(config, rag_config)
        env[key_env] = value
        if base_env in os.environ:
            env[base_env] = os.environ[base_env]
        task_path = pathlib.Path(entry["task_path"])
        env["PI_WORKER_TASK"] = str(task_path.resolve())
        return env

    # Codex: native provider, remove all proxy credentials (AC-010)
    if cli == "codex":
        if provider not in ("", "codex"):
            raise RuntimeError(
                f"Codex workers support only an empty provider or 'codex', got {provider!r}"
            )
        return _stripped_env(config, rag_config)

    # Generic port-based proxy path (pi empty provider, claude, deepseek, ...)
    route = mw_common.route_for(config, cli, provider)
    cred = config.get("credentials", {}).get(route["credential"])
    value, _source = mw_common.resolve_credential(cred, os.environ)
    if value is None:
        raise RuntimeError(
            f"Required credential for route '{route['provider_key']}' is not available "
            f"({mw_common.describe_missing(cred)})."
        )

    env = _stripped_env(config, rag_config)
    env[route["base_url_env"]] = f"http://localhost:{route['port']}"
    env[route["api_key_env"]] = value

    # Pi worker also needs PI_WORKER_TASK (AC-002)
    if cli == "pi":
        task_path = pathlib.Path(entry["task_path"])
        env["PI_WORKER_TASK"] = str(task_path.resolve())

    return env


def inject_rag_env(
    env: dict[str, str], entry: dict[str, str], project_dir: pathlib.Path
) -> None:
    """Post-step after ``_build_env``: inject the enabled servers' RAG env.

    Values are read from THIS process's environment (the serve environment)
    and written only into the child ``env`` — the token never reaches
    task.md / trace.log / worker.log / argv. RAG config that is absent,
    unreadable or has an empty ``enabled`` list injects NOTHING, so a
    RAG-less worker's env stays item-for-item identical to the pre-RAG
    launcher (AC-001/D-010). ``entry`` is accepted for call-site symmetry
    with the spawn path; nothing here is task-specific yet.
    """
    rag_config, _error = mw_common.load_rag_config(project_dir)
    enabled = [
        name for name in (rag_config.get("enabled") or [])
        if isinstance(name, str) and name.strip()
    ]
    if not enabled:
        return
    servers = rag_config.get("servers") or {}
    for name in enabled:
        server = servers.get(name)
        if not isinstance(server, dict):
            continue
        mcp = server.get("mcp")
        if not isinstance(mcp, dict):
            continue
        token_env = mcp.get("token_env")
        if not isinstance(token_env, str) or not token_env.strip():
            continue
        value = os.environ.get(token_env.strip())
        if value:
            env[token_env.strip()] = value


def _exit_to_status(exit_code: int) -> str:
    """Map worker exit code to _workers.parallel status (AC-006)."""
    if exit_code == 0:
        return "done"
    if exit_code == 2:
        return "needs-clarification"
    return "failed"


def _reap_status(
    task_dir: pathlib.Path | None, exit_code: int, task_key: str
) -> str:
    """Product-first terminal status for a reaped worker (AC-006 / DD-06).

    The worker-written ``run.json`` is the product, so a terminal ``status``
    there outranks the process exit code: an exit 0 whose run recorded
    ``needs-clarification`` must not land in the queue as ``done`` (the G-f
    gap). When there is no terminal run state -- no ``run.json``, unreadable
    JSON, or a non-terminal ``running``/``pending`` -- the historical
    :func:`_exit_to_status` mapping applies unchanged (zero back-fill,
    byte-identical to the pre-AC-006 launcher).

    A terminal run state that disagrees with the exit code is reported once
    on stderr -- which ``mw serve`` captures into ``.mw/launcher.log``
    (mw.py:334) -- with the task key, both values and the value actually
    used, so the PM can audit the decision after the fact. Never raises,
    never touches stdout (the ``mw doctor`` JSON contract) and never writes
    ``run.json`` (the worker owns it; ``read_run_status`` is the single
    reader shared with the T-20 stale reconcile).
    """
    from_exit = _exit_to_status(exit_code)
    if task_dir is None:
        return from_exit
    run_status = mw_common.read_run_status(task_dir)
    if run_status not in mw_common.RUN_TERMINAL_STATUSES:
        return from_exit
    if run_status != from_exit:
        print(
            f"[launcher] {task_key}: reap status conflict "
            f"run.json={run_status} exit={exit_code} (exit-status={from_exit}) "
            f"used={run_status}",
            file=sys.stderr,
            flush=True,
        )
    return run_status


def _reap_task_dirs(project_dir: pathlib.Path) -> dict[str, pathlib.Path]:
    """``task_key -> task dir`` from the live queue rows (reap reads run.json).

    Best-effort like every other ledger read: an unreadable/absent queue file
    yields no map, and each reaped row then falls back to its exit code
    exactly as before. The first row wins (``task_key`` is unique in
    practice).
    """
    dirs: dict[str, pathlib.Path] = {}
    for entry in _parse_workers_file(_workers_path(project_dir)):
        key = entry.get("task_key")
        task_path = entry.get("task_path")
        if key and task_path and key not in dirs:
            dirs[key] = pathlib.Path(task_path).parent
    return dirs


def _require_task_file(task_path: str) -> pathlib.Path:
    """Validate the task file exists; return its Path.

    Raises RuntimeError with a clear reason so _spawn records it into the
    task's worker.log (design D-001 isolation semantics).
    """
    p = pathlib.Path(task_path)
    if not p.exists():
        raise RuntimeError(f"task.md not found: {task_path}")
    return p


def _validate_task_path(project_dir: pathlib.Path, task_path: str) -> None:
    """Enforce the worker-task location contract.

    Valid: <project>/.agenticdoc/{ownerKey}/workers/<task_key>/task.md or
    <project>/.agenticdoc/_scratch/workers/<task_key>/task.md. The .agenticdoc
    root belongs to AgenticTask keys; task dirs found there (OverCode
    pch-migration-s1 incident: hand-written task.md + queue rows at the root
    bypassed dispatch_worker's workerTaskDir placement) must be rejected
    loudly instead of spawned.
    """
    agentic = (project_dir / ".agenticdoc").resolve()
    p = pathlib.Path(task_path).resolve()
    try:
        rel = p.relative_to(agentic)
    except ValueError:
        raise RuntimeError(f"task path is outside .agenticdoc: {task_path}") from None
    parts = rel.parts
    ok = (
        len(parts) == 4
        and parts[1] == "workers"
        and parts[3] == "task.md"
        and (parts[0] == "_scratch" or not parts[0].startswith(("_", ".")))
    )
    if not ok:
        raise RuntimeError(
            f"invalid worker-task location: {rel} - tasks must live under "
            ".agenticdoc/{key}/workers/<task_key>/task.md (or _scratch/workers/...); "
            "the .agenticdoc root belongs to AgenticTask keys"
        )


# ── Dispatch envelope gate (G-3, mw-dispatch-card-gate T-03) ──────────────────
#
# The service layer is the only queue consumer that sees all four dispatch
# producers (dispatch_worker, /worker, conductor direct writes, hand-written
# rows), so it re-checks the envelope contract on its own — no TS import. The
# constants and the judgement below are a line-for-line Python mirror of the
# frozen TS leaf `packages/coding-agent/src/extensions/agent-team-loop/shared/
# dispatch-card.ts` (T-01); the shared source is the card corpus research
# (evidence/research/spec-card-format-corpus-20261012.md §0.2). A parity test
# drives the real TS module through node and diffs the two verdicts, so the
# mirror cannot drift silently (P-04).
#
# Migration rule (T-03 signal, superseded by T-09's time boundary): T-03
# judged only cards that declared a signal (a canonical G-2 section heading or
# a `card_path:` header), which left exactly the two tool-bypassing producers
# — conductor direct writes and hand-written rows — uncovered, since they
# simply omit the signal. T-09 keeps that signal definition
# (:func:`_envelope_declaring`, now inert) but moves the decision to the queue
# row's creation time versus ENVELOPE_ENFORCE_SINCE: before the boundary a
# historical dispatch is exempt; at/after it every row is judged (fail-closed).
# The strict-titles over-refusal that motivated the original opt-in is handled
# by the cutover date (history is never re-judged), not by the signal.

# Cutover boundary for the service-layer envelope gate (T-09). A queue row
# created before this UTC date is a historical dispatch and stays exempt
# (P-07/P-09); a row created at/after it is judged whether or not the card
# declares a signal. This is a one-time migration boundary, not a runtime
# toggle: it is deliberately a constant (no env knob) so a stray environment
# variable cannot silently disable the gate.
ENVELOPE_ENFORCE_SINCE: str = "2026-10-12"

ENVELOPE_SECTIONS: tuple[str, ...] = ("context", "requirements", "deliverables")

ENVELOPE_SECTION_LABELS: dict[str, str] = {
    "context": "上下文",
    "requirements": "要求",
    "deliverables": "交付格式",
}

# Heading families, ordered (first hit wins): deliverables > context >
# requirements (mirror of ENVELOPE_HEADING_FAMILIES).
ENVELOPE_HEADING_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("deliverables", (
        "交付物", "交付", "预期产出", "预期产物", "产物", "输出", "证据格式",
        "证据", "报告要求", "回执", "Deliverable", "Expected Output", "Artifact",
    )),
    ("context", (
        "背景", "上下文", "问题", "现状", "动机", "根因", "缺陷", "偏差",
        "目标", "描述", "输入", "前置", "范围",
        "Context", "Motivation", "Rationale", "Why", "Goal", "Objective",
        "Description", "Input", "Scope",
    )),
    ("requirements", (
        "要求", "任务", "契约", "验收", "验证", "完成判定", "完成判据", "判据",
        "行为", "测试", "接口", "用例", "协议", "内容", "标准", "做法", "策略",
        "断言", "规范", "编码", "对照", "反例", "反向", "必须", "实现", "步骤",
        "改动", "变更", "Acceptance Criteria", "Requirement", "Expected Behavior",
        "[VERIFY]", "AC ", "VC ", "TDD",
    )),
)

# Paragraph-semantic fallback hints, scanned line-wise over the whole text.
ENVELOPE_BODY_HINTS: dict[str, re.Pattern[str]] = {
    "context": re.compile(r"背景|动机|原因|由于|因为|现状|痛点|为什么|为何|根因"),
    "requirements": re.compile(r"AC-\d+|VC-\d+", re.IGNORECASE),
    "deliverables": re.compile(r"report\.md|progress\.md|output\.md|evidence/|回执"),
}

# Bullet/field key predicates for the paragraph-semantic fallback.
ENVELOPE_BULLET_KEYS: dict[str, re.Pattern[str]] = {
    "context": re.compile(r"^(背景|动机|问题|现状|范围|规格|目的|前提)$"),
    "requirements": re.compile(r"要求|规格|验收|必须|步骤|实现|改动|协议|契约|条件"),
    "deliverables": re.compile(r"产物|交付|佐证|证据|输出|结果|报告"),
}

# Type-specific extra item names (design §1.2), in reporting order.
CODING_EXTRA_SECTIONS: tuple[str, ...] = ("写入允许面", "写入禁止面", "验收命令", "改动历史")
RESEARCH_EXTRA_SECTIONS: tuple[str, ...] = ("唯一证据文件",)
REVIEW_EXTRA_SECTIONS: tuple[str, ...] = ("审计目标", "未覆盖面声明")

TYPE_EXTRA_SECTIONS: dict[str, tuple[str, ...]] = {
    "coding": CODING_EXTRA_SECTIONS,
    "research": RESEARCH_EXTRA_SECTIONS,
    "review": REVIEW_EXTRA_SECTIONS,
}

# Legitimate PM-dispatchable roles with no T-01 extra rules: they pass the
# extras check instead of being reported as unknown (the design §1.2 extras
# for them are out of T-01's card scope, so the service layer must not invent
# a stricter rule — P-04).
TYPES_WITHOUT_EXTRA_RULES: tuple[str, ...] = ("vision", "rag-research")

# Single-source dispatch type vocabulary (mirror of the TS
# `DISPATCH_TYPE_VOCABULARY` in `shared/dispatch-card.ts`, T-07/P-08). Every
# in-use role is known; `type_extras_missing` only names a genuinely unknown
# value. The Python mirror must move with the TS tuple or the T-27 cross-
# language parity test goes red (T-07 owns the TS side, this file owns the
# mirror — its write surface forbids launcher.py).
DISPATCH_TYPE_VOCABULARY: tuple[str, ...] = (
    "coding", "review", "research", "rag-research", "vision",
    "verifier", "reviewer", "repair", "phase-writer", "roadmap-writer", "codex",
)

# Item-name patterns for type_extras_missing; keys mirror TYPE_EXTRA_SECTIONS.
TYPE_EXTRA_PATTERNS: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    "coding": (
        ("写入允许面", re.compile(r"写入允许面|允许写入|允许写|写入范围|写面|write_scope|allow[-_ ]?write", re.IGNORECASE)),
        ("写入禁止面", re.compile(r"写入禁止面|禁止写入|禁止写|不得写|写入禁区|禁止范围|deny[-_ ]?write|forbid", re.IGNORECASE)),
        ("验收命令", re.compile(r"验收命令|验证命令|验收标准|验收判据|验收方式|验收|完成判据|acceptance", re.IGNORECASE)),
        ("改动历史", re.compile(r"改动历史|改动清单|变更历史|写入事件|trace\.log|write[-_ ]?history|change[-_ ]?log", re.IGNORECASE)),
    ),
    "research": (
        ("唯一证据文件", re.compile(r"唯一证据文件|唯一证据|唯一产物|仅此一写|sole[-_ ]?evidence", re.IGNORECASE)),
    ),
    "review": (
        ("审计目标", re.compile(r"审计目标|审计问题|审计对象|审计范围|审计维度|问题域|要回答|audit[-_ ]?(target|scope|question)", re.IGNORECASE)),
        ("未覆盖面声明", re.compile(r"未覆盖面|未覆盖声明|未覆盖范围|未及范围|未查看|未探索|未涉及|not[-_ ]?covered|out[-_ ]?of[-_ ]?scope", re.IGNORECASE)),
    ),
}

_HEADING_RE = re.compile(r"^(#{2,6})\s+(.*)$")
_BULLET_LABEL_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\*\*)?([^:：]{1,48}?)(?:\*\*)?\s*[:：]")
_FIELD_LABEL_RE = re.compile(r"^\s*(?:\*\*)?([A-Za-z_][A-Za-z0-9_.-]{0,40})(?:\*\*)?\s*:")
_CARD_TYPE_RE = re.compile(r"(?:^|[\s|｜>*+-])type:\s*([^\s|｜]+)")
_ENVELOPE_CARD_PATH_RE = re.compile(r"^card_path:[ \t]*\S", re.MULTILINE)
# The exact headings the G-2 generator injects (T-02): their presence is the
# new-dispatch opt-in. Legacy/conductor task.md files do not carry them, so
# they stay exempt (design P-03: over-refusal is a contract violation too).
_ENVELOPE_CANONICAL_HEADING_RE = re.compile(
    r"^[ \t]*#{2,6}[ \t]*(?:上下文|要求|交付格式)[ \t]*#*[ \t]*$", re.MULTILINE
)


def _envelope_split_lines(text: str) -> list[str]:
    """Same newline folding as the TS `splitLines` (BOM strip, CR/CRLF/U+2028
    /U+2029 -> LF, drop one trailing empty line, trim every line)."""
    body = text[1:] if text.startswith("\ufeff") else text
    lines = re.sub(r"\r\n?|[\u2028\u2029]", "\n", body).split("\n")
    if len(lines) > 1 and lines[-1] == "":
        lines.pop()
    return [line.strip() for line in lines]


def _read_card_type(lines: list[str]) -> str:
    """First `type:` in the card prologue (lines before the first H2+ heading).

    A body-level `type:` never flips the role (mirror of the TS `readCardType`
    / the F-10 body-type exclusion)."""
    end = len(lines)
    for i, line in enumerate(lines):
        if _HEADING_RE.match(line):
            end = i
            break
    for i in range(end):
        match = _CARD_TYPE_RE.search(lines[i])
        if match:
            return match.group(1).strip()
    return ""


def _strip_numbering(text: str) -> str:
    """Strip a leading `1.` / `1.2.` / `(2)` / `A.` / `一、` numbering prefix."""
    out = text.strip()
    out = re.sub(r"^[（(]\s*[0-9A-Za-z一二三四五六七八九十]+\s*[)）]\s*", "", out)
    out = re.sub(r"^[0-9]+(?:\.[0-9]+)*\s*[.、)）]\s*", "", out)
    out = re.sub(r"^[A-Za-z]\s*[.、)）]\s*", "", out)
    out = re.sub(r"^[一二三四五六七八九十]+\s*[、.)）]\s*", "", out)
    return out.strip()


def _classify_heading(heading: str) -> str | None:
    """First heading family the heading belongs to (deliverables > context > req)."""
    lower = heading.lower()
    for section, tokens in ENVELOPE_HEADING_FAMILIES:
        for token in tokens:
            if lower.startswith(token.lower()):
                return section
    return None


def _label_of(line: str) -> str | None:
    """A bullet/field label in the card (`- 允许写：…`, `write_scope: …`)."""
    bullet = _BULLET_LABEL_RE.match(line)
    if bullet:
        return bullet.group(1).strip()
    field = _FIELD_LABEL_RE.match(line)
    if field:
        return field.group(1).strip()
    return None


def _any_label_matches(lines: list[str], key_re: re.Pattern[str]) -> bool:
    for line in lines:
        label = _label_of(line)
        if label is not None and key_re.search(label):
            return True
    return False


def _collect_headings(lines: list[str]) -> list[tuple[int, str, int]]:
    """(level, stripped text, line index) for every H2..H6 heading."""
    headings: list[tuple[int, str, int]] = []
    for i, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match:
            headings.append((len(match.group(1)), _strip_numbering(match.group(2)), i))
    return headings


def _body_semantic_hit(section: str, lines: list[str]) -> bool:
    if any(ENVELOPE_BODY_HINTS[section].search(line) for line in lines):
        return True
    return _any_label_matches(lines, ENVELOPE_BULLET_KEYS[section])


def _detect_sections(lines: list[str]) -> dict[str, str]:
    """Wide (T1e) detection: a heading family with a non-empty body, else the
    paragraph-semantic fallback (body hint or bullet/field key)."""
    detected: dict[str, str] = {section: "" for section in ENVELOPE_SECTIONS}
    headings = _collect_headings(lines)
    for i, (level, text, line_no) in enumerate(headings):
        section = _classify_heading(text)
        if section is None or detected[section] != "":
            continue
        end = len(lines)
        for j in range(i + 1, len(headings)):
            if headings[j][0] <= level:
                end = headings[j][2]
                break
        if any(lines[k] != "" for k in range(line_no + 1, end)):
            detected[section] = f"heading:{text}"
    for section in ENVELOPE_SECTIONS:
        if detected[section] == "" and _body_semantic_hit(section, lines):
            detected[section] = "semantics"
    return detected


def inspect_envelope(text: str) -> tuple[bool, list[str], str, dict[str, str]]:
    """(ok, missing, type, detected) — Python mirror of the TS `inspectEnvelope`.

    Judgement only; the caller decides the action. A missing `type:` and every
    undetected section are named by their stable key (`type`, `context`, ...).
    """
    lines = _envelope_split_lines(text)
    task_type = _read_card_type(lines)
    detected = _detect_sections(lines)
    missing: list[str] = []
    if task_type == "":
        missing.append("type")
    for section in ENVELOPE_SECTIONS:
        if detected[section] == "":
            missing.append(section)
    return (not missing, missing, task_type, detected)


def type_extras_missing(task_type: str, text: str) -> list[str]:
    """Item names for the declared type's missing extras (mirror of TS).

    A known vocabulary role without extra rules (`vision`, `rag-research`, and
    the runtime registry roles `verifier` / `repair` / `phase-writer` / ... )
    passes; only a genuinely unknown type returns `["unknown-type:<type>"]`.
    """
    patterns = TYPE_EXTRA_PATTERNS.get(task_type)
    if patterns is None:
        # P-08 (T-07): every in-use role is in the single-source vocabulary, so
        # it passes the extras check; only a genuinely unknown value is named.
        return [] if task_type in DISPATCH_TYPE_VOCABULARY else [f"unknown-type:{task_type}"]
    lines = _envelope_split_lines(text)
    missing: list[str] = []
    for item, pattern in patterns:
        if item in text:
            continue
        if _any_label_matches(lines, pattern):
            continue
        heading_hit = False
        for line in lines:
            heading = _HEADING_RE.match(line)
            if heading and pattern.search(_strip_numbering(heading.group(2))):
                heading_hit = True
                break
        if not heading_hit:
            missing.append(item)
    return missing


def has_canonical_envelope(text: str) -> bool:
    """True when `text` carries a G-2 canonical section heading.

    The canonical `上下文 / 要求 / 交付格式` triple is the shape every current
    generator injects (T-02 `writeDispatchTaskMd`, T-10 `render_task_md`), so a
    task.md carrying it has been through a live writer (or was forged that
    way). Public and shared with `card_audit.audit()` (T-12/F-06) so the service
    boundary and the traceability audit cannot drift on the "this is a
    new-shape dispatch" signal.
    """
    return _ENVELOPE_CANONICAL_HEADING_RE.search(text) is not None


def _envelope_declaring(text: str) -> bool:
    """True when the card declares the envelope signal (canonical heading or
    a `card_path:` header).

    Historical only: T-09 moved the *decision to judge* from this signal to
    the row's creation time versus :data:`ENVELOPE_ENFORCE_SINCE`
    (:func:`_envelope_enforced`), because the signal itself was the loophole
    — a card that simply omitted both shapes bypassed the gate. The function
    is retained as the named definition of the signal (audits/tests) and is
    no longer consulted by :func:`_envelope_refusal`.
    """
    if _ENVELOPE_CARD_PATH_RE.search(text):
        return True
    return has_canonical_envelope(text)


def _row_created_raw(entry: dict[str, str]) -> str:
    """The row's creation timestamp (raw string), or "" when it has none.

    T-12/F-03: the `created` field was dead code — `mw_common.parse_worker_line`
    never produces that key and no writer stamps it — so the priority branch is
    removed rather than kept unexercised. `dispatched_at` is the one creation
    time every producer writes. `updated_at` stays deliberately absent: reaps
    and reconciles rewrite it, so it is not a creation time and must not move a
    historical row past the cutover.
    """
    return (entry.get("dispatched_at") or "").strip()


def envelope_enforce_since_epoch() -> float:
    """`ENVELOPE_ENFORCE_SINCE` as a POSIX timestamp (UTC midnight).

    Public so `card_audit` (T-12/F-06) uses the same constant and the same
    arithmetic as the service gate — one boundary, not two.
    """
    ts = _parse_utc_ts(ENVELOPE_ENFORCE_SINCE)
    # The constant is a module literal; a parse failure would be a bug, but
    # fail closed (every row judged) rather than silently open the gate.
    return ts.timestamp() if ts is not None else 0.0


def _envelope_enforced(entry: dict[str, str]) -> bool:
    """True when this pending row must pass the envelope gate (T-09/T-12).

    The decision is the row's creation time versus
    :data:`ENVELOPE_ENFORCE_SINCE`, cross-checked against the artifact because
    the bare row timestamps are hand-writable plain text in
    `_workers.parallel` (T-12/F-03):

    * a task.md that already carries a G-2 canonical heading has been through a
      current generator, so the row is judged unconditionally;
    * a task.md whose mtime is later than the row's own `dispatched_at` cannot
      predate the dispatch, so the row timestamp is not trusted and the row is
      judged unconditionally;
    * otherwise a row created before the boundary is a historical dispatch and
      stays exempt; at/after it every row is judged.

    A row with no parseable creation time cannot prove it is old, so it is
    judged (fail-closed).
    """
    task_path = (entry.get("task_path") or "").strip()
    task_md = pathlib.Path(task_path) if task_path else None
    text = ""
    if task_md is not None:
        try:
            text = task_md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
    if text and has_canonical_envelope(text):
        return True
    created = _parse_utc_ts(_row_created_raw(entry))
    if created is None:
        return True
    if task_md is not None:
        try:
            mtime = task_md.stat().st_mtime
        except OSError:
            mtime = None
        if mtime is not None and mtime > created.timestamp():
            return True
    return created.timestamp() >= envelope_enforce_since_epoch()


def _envelope_missing_items(text: str) -> tuple[list[str], list[str], list[str], str]:
    """(missing_keys, extras, display_items, task_type) — the T-09 naming.

    ``display_items`` is what the row reason and worker.log carry: the
    localized section labels plus the raw extra names (mirror of the T-03
    format). Single source so the T-09 reason text cannot drift between
    :func:`_envelope_refusal` and the T-14 classifier.
    """
    _ok, missing, task_type, _detected = inspect_envelope(text)
    extras = type_extras_missing(task_type, text) if task_type else []
    items = [
        ENVELOPE_SECTION_LABELS[item] if item in ENVELOPE_SECTION_LABELS
        else ("type:" if item == "type" else item)
        for item in missing
    ]
    items.extend(extras)
    return (missing, extras, items, task_type)


# ── Producer identity / version skew (mw-dispatch-card-gate T-14, AC-009) ─────
#
# The gate above lives in the *global* service (this file) while the injection
# that satisfies it lives in each project's framework copy
# (`autopilot/dispatch.py::render_task_md`): two version domains (P-10). A
# service that enforces the gate while a project copy is still old refuses
# every dispatch of that key, which is indistinguishable from autopilot being
# dead (incident `autopilot-producer-paralysis-20261012`: 675 done / 33 failed
# / 0 pending / 0 running, queue file untouched for two days). T-14 keeps the
# fail-closed default and adds: (b) a *distinguishable, loud* skew verdict with
# an upgrade pointer, (c) the same loud guidance for a legacy/unknown producer,
# one aggregate alarm per key per poll, an explicit default-off escape hatch
# that injects a canonical skeleton, and a narrowed blast radius (a skew only
# ever affects the one rejected row).

# Machine-readable producer identity line written by the dispatch producer in
# the task.md header area: `envelope_producer: <producer-id>@<version>` (T-13).
# Missing => legacy/unknown producer (branch c).
_ENVELOPE_PRODUCER_LINE_RE = re.compile(
    r"^[ \t]*envelope_producer[ \t]*:[ \t]*(\S+)[ \t]*$", re.MULTILINE
)

# Baseline a producer version is compared against: the same cutover boundary
# that gates enforcement (single source — deliberately no second date).
ENVELOPE_PRODUCER_BASELINE: str = ENVELOPE_ENFORCE_SINCE

# Dotted-numeric producer versions (`0.83.0`) are compared against the pi
# framework release this service ships with — the existing version source the
# producer identity is expected to use (`packages/coding-agent/package.json`,
# lockstep with the multi-workers service). "" when the file is unavailable,
# in which case a numeric version is *not provably* old and the row keeps the
# plain `envelope missing` refusal: a current producer is never mislabelled as
# skew (which would re-create the paralysis this card exists to prevent).
_FRAMEWORK_PACKAGE_JSON = (
    pathlib.Path(__file__).resolve().parent.parent / "coding-agent" / "package.json"
)


def _framework_version() -> str:
    """pi framework version from the existing source, or "" when unavailable."""
    try:
        data = json.loads(_FRAMEWORK_PACKAGE_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    version = data.get("version") if isinstance(data, dict) else None
    return version.strip() if isinstance(version, str) else ""


ENVELOPE_PRODUCER_BASELINE_SEMVER: str = _framework_version()

# Calendar stamp (`2026-10-12`, `2026-10-12T14:03:00Z`) or dotted numeric
# release (`0.83.0`). The two families are never compared against each other.
_PRODUCER_DATE_RE = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?Z?"
)
_PRODUCER_NUMERIC_RE = re.compile(r"\d+(?:\.\d+)*")


def producer_identity(text: str) -> tuple[str, str]:
    """(producer_id, version) from the identity line, or ("", "").

    The PM-fixed contract is `envelope_producer: <id>@<version>`; a line whose
    value carries no `@` still proves a producer identity exists (branch b),
    it just has no comparable version. Callers that need "is there a line at
    all" (to separate branch b from branch c) use
    :func:`has_producer_identity`.
    """
    match = _ENVELOPE_PRODUCER_LINE_RE.search(text)
    if match is None:
        return ("", "")
    raw = match.group(1)
    producer_id, sep, version = raw.partition("@")
    return (producer_id, version if sep else "")


def has_producer_identity(text: str) -> bool:
    """True when the card carries the machine-readable producer identity line."""
    return _ENVELOPE_PRODUCER_LINE_RE.search(text) is not None


def _producer_version_key(version: str) -> tuple[int, tuple[int, ...]] | None:
    """Orderable key for a recognized producer version, or None.

    Family 0 = calendar stamp (compared to :data:`ENVELOPE_PRODUCER_BASELINE`),
    family 1 = dotted numeric release (compared to
    :data:`ENVELOPE_PRODUCER_BASELINE_SEMVER`). Anything else is unrecognized —
    including the all-zero placeholder `0.0.0`: a producer that cannot read its
    own version source renders it (C-31, the bundled extension cannot resolve
    `package.json`), so it is a *missing* version, never a release older than
    the baseline.
    """
    text = version.strip()
    if not text:
        return None
    date_match = _PRODUCER_DATE_RE.fullmatch(text)
    if date_match:
        y, mo, d, hh, mm, ss = date_match.groups()
        return (0, (int(y), int(mo), int(d), int(hh or 0), int(mm or 0), int(ss or 0)))
    if _PRODUCER_NUMERIC_RE.fullmatch(text):
        parts = tuple(int(part) for part in text.split("."))
        if not any(parts):
            return None  # `0.0.0` / `0` => version source unreadable
        return (1, parts)
    return None


def producer_version_is_unknown(version: str) -> bool:
    """True when `version` is the all-zero/no-version placeholder (C-31).

    `0.0.0` and the empty version (an identity line without `@<version>`) are
    not comparable releases. They keep the fail-closed `envelope missing`
    refusal and are annotated `producer-version-unknown` in the reason so the
    state is explicable; they are never labelled `producer-skew`.
    """
    text = version.strip()
    if text == "":
        return True
    if not _PRODUCER_NUMERIC_RE.fullmatch(text):
        return False
    return not any(int(part) for part in text.split("."))


# The annotating token for an all-zero/absent producer version (C-31): it keeps
# the reason greppable without re-introducing the false `producer-skew` label.
_PRODUCER_VERSION_UNKNOWN_MARKER = "producer-version-unknown"


def producer_version_before_baseline(version: str) -> bool:
    """True only when `version` is *provably* older than the service baseline.

    Provable means the same recognized family on both sides: a calendar stamp
    older than :data:`ENVELOPE_PRODUCER_BASELINE`, or a dotted numeric release
    older than :data:`ENVELOPE_PRODUCER_BASELINE_SEMVER`. An unknown shape — or
    a numeric release with no known framework version to compare to — is not
    provably old, so the row keeps the plain `envelope missing` refusal
    (fail-closed, never a false skew label on a current producer).
    """
    key = _producer_version_key(version)
    if key is None:
        return False
    family, parts = key
    baseline = (
        ENVELOPE_PRODUCER_BASELINE if family == 0 else ENVELOPE_PRODUCER_BASELINE_SEMVER
    )
    base = _producer_version_key(baseline)
    return base is not None and base[0] == family and parts < base[1]


# Escape hatch (T-14 requirement 3, default OFF via the config key). The marker
# keeps the injection idempotent across polls.
_ENVELOPE_FALLBACK_MARKER = "<!-- mw-envelope-fallback -->"
_ENVELOPE_FALLBACK_AUDIT = "[ENVELOPE_FALLBACK]"
_ENVELOPE_FALLBACK_SECTION_BODY = (
    f"{_ENVELOPE_FALLBACK_AUDIT} 服务层兜底注入：原 producer 未提供本段。"
    "这是让该行可 spawn 的最小骨架，不是任务内容，也不改变任何写面判据；"
    "请以任务卡与 PM 指令为准，并在升级 producer 后重新派发。"
)
_ENVELOPE_FALLBACK_EXTRA_LINES: dict[str, str] = {
    "写入允许面": f"{_ENVELOPE_FALLBACK_AUDIT} 写入允许面: 服务层兜底骨架（原 producer 未声明；写面判据不变）",
    "写入禁止面": f"{_ENVELOPE_FALLBACK_AUDIT} 写入禁止面: 服务层兜底骨架（原 producer 未声明；写面判据不变）",
    "验收命令": f"{_ENVELOPE_FALLBACK_AUDIT} 验收命令: 服务层兜底骨架（原 producer 未声明）",
    "改动历史": f"{_ENVELOPE_FALLBACK_AUDIT} 改动历史: 服务层兜底骨架（原 producer 未声明）；trace.log 写入事件",
    "唯一证据文件": f"{_ENVELOPE_FALLBACK_AUDIT} 唯一证据文件: 服务层兜底骨架（原 producer 未声明）",
    "审计目标": f"{_ENVELOPE_FALLBACK_AUDIT} 审计目标: 服务层兜底骨架（原 producer 未声明）",
    "未覆盖面声明": f"{_ENVELOPE_FALLBACK_AUDIT} 未覆盖面声明: 服务层兜底骨架（原 producer 未声明）",
}


def _upgrade_pointer() -> str:
    """One-line actionable fix for a version-domain mismatch (AC-009b)."""
    return (
        "upgrade this project's framework copy (the renderer that writes "
        "task.md — normally the installed agent-team-loop bundle / the "
        "project's autopilot/dispatch.py) and re-dispatch; or set "
        "`envelope_fallback: true` in .agenticdoc/_autopilot/config.json "
        "(default off) to let the service inject a canonical skeleton for this run"
    )


def classify_envelope_refusal(entry: dict[str, str]) -> dict | None:
    """Full T-14 classification of one card's envelope gate outcome.

    None => branch (a): the card passes and may spawn. Otherwise a dict whose
    ``kind`` is one of

    * ``"skew"`` (b) — a producer identity line whose version predates the
      service baseline: the reason is a greppable ``failed(producer-skew ...)``
      plus a one-line upgrade pointer;
    * ``"legacy"`` (c) — no identity line at all: T-09 fail-closed is
      unchanged, but the refusal is loud (guidance written next to it);
    * ``"missing"`` — an identity line that is not provably old: the plain
      T-09 refusal, unchanged. An all-zero/absent version (`0.0.0`, C-31) lands
      here with a `producer-version-unknown` annotation (never `skew`).

    ``missing_keys``/``extras``/``items`` keep the T-09 naming;
    ``text``/``task_type`` feed the escape-hatch injection. A file that exists
    but cannot be read returns None (the missing/unreadable-file semantics are
    not the envelope's concern).
    """
    task_path = entry["task_path"]
    try:
        text = pathlib.Path(task_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    missing_keys, extras, items, task_type = _envelope_missing_items(text)
    if not items:
        return None
    producer_id, version = producer_identity(text)
    producer = f"{producer_id}@{version}" if has_producer_identity(text) else ""
    if not has_producer_identity(text):
        kind = "legacy"
    elif producer_version_before_baseline(version):
        kind = "skew"
    else:
        kind = "missing"
    if kind == "skew":
        reason = (
            f"failed(producer-skew {producer} baseline={ENVELOPE_PRODUCER_BASELINE}): "
            f"envelope missing: {', '.join(items)} ({task_path})"
        )
        guidance = [
            "envelope-skew guidance: producer "
            f"{producer} predates the service baseline {ENVELOPE_PRODUCER_BASELINE} "
            f"and its task.md has no canonical envelope — {_upgrade_pointer()}"
        ]
    elif kind == "legacy":
        reason = f"envelope missing: {', '.join(items)} ({task_path})"
        guidance = [
            "envelope guidance: task.md carries neither a canonical envelope nor an "
            "`envelope_producer:` identity line (legacy/unknown producer) — "
            f"{_upgrade_pointer()}"
        ]
    else:
        unknown_note = (
            f" {_PRODUCER_VERSION_UNKNOWN_MARKER}"
            if producer_version_is_unknown(version)
            else ""
        )
        reason = (
            f"envelope missing: {', '.join(items)} ({task_path}) "
            f"[producer={producer}{unknown_note} not provably older than baseline="
            f"{ENVELOPE_PRODUCER_BASELINE}]"
        )
        guidance = []
    return {
        "kind": kind,
        "reason": reason,
        "producer": producer,
        "baseline": ENVELOPE_PRODUCER_BASELINE,
        "guidance": guidance,
        "text": text,
        "task_type": task_type,
        "missing_keys": missing_keys,
        "extras": extras,
        "items": items,
    }


def _envelope_refusal(entry: dict[str, str]) -> str | None:
    """The envelope refusal line for one card, or None when it passes.

    Judgement only — the caller owns the failed row + the worker.log write.
    The caller first decides *whether* to judge (:func:`_envelope_enforced`,
    the T-09 time boundary); this function no longer consults the card's own
    signal, so a legacy-shaped card at/after the boundary is judged too. A
    file that exists but cannot be read is left to the existing spawn path
    (the missing/unreadable-file semantics are not the envelope's concern).

    T-14: the reason is the branch-specific string from
    :func:`classify_envelope_refusal` — branch (c) keeps the exact T-09 text,
    branch (b) is the greppable ``failed(producer-skew ...)`` line.
    """
    verdict = classify_envelope_refusal(entry)
    return None if verdict is None else verdict["reason"]


def envelope_fallback_inject(text: str) -> str | None:
    """Canonical-envelope skeleton for a refused card, or None when the card
    cannot be made compliant without inventing facts (missing/unknown `type:`).

    Only the *missing* pieces are appended, never a rewrite: the card's own
    frontmatter (including `allow_foreign_write:`) and body are untouched, so
    the hatch affects the envelope judgement only. The result is re-judged
    before it is returned; a skeleton that still fails yields None and the
    caller stays fail-closed.
    """
    if _ENVELOPE_FALLBACK_MARKER in text:
        return text  # already injected by an earlier poll (idempotent)
    missing_keys, extras, _items, task_type = _envelope_missing_items(text)
    if "type" in missing_keys or task_type == "":
        return None
    if task_type not in DISPATCH_TYPE_VOCABULARY:
        return None
    additions: list[str] = [_ENVELOPE_FALLBACK_MARKER]
    for section in ENVELOPE_SECTIONS:
        if section in missing_keys:
            additions += [
                "",
                f"## {ENVELOPE_SECTION_LABELS[section]}",
                "",
                _ENVELOPE_FALLBACK_SECTION_BODY,
            ]
    for item in extras:
        line = _ENVELOPE_FALLBACK_EXTRA_LINES.get(item)
        if line is None:
            return None
        additions += ["", line]
    if len(additions) == 1:
        return None  # nothing to inject
    injected = text.rstrip("\n") + "\n" + "\n".join(additions) + "\n"
    _ok, missing_after, type_after, _detected = inspect_envelope(injected)
    extras_after = type_extras_missing(type_after, injected) if type_after else []
    if missing_after or extras_after:
        return None
    return injected


def _record_envelope_fallback(entry: dict[str, str], verdict: dict) -> None:
    """Audit one hatch-allowed row (T-14 requirement 3): a greppable
    `[ENVELOPE_FALLBACK]` fact in the task's worker.log."""
    line = (
        f"{_ENVELOPE_FALLBACK_AUDIT} {mw_common.iso_now()} {entry['task_key']} "
        f"kind={verdict['kind']} producer={verdict['producer'] or '(none)'} "
        f"baseline={verdict['baseline']} injected=canonical-envelope-skeleton "
        "(envelope_fallback=true; envelope judgement only — write-face judgement unchanged)"
    )
    try:
        log_path = _worker_log_path(entry)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"[launcher] {line}\n")
    except OSError:
        pass
    print(f"[launcher] {entry['task_key']}: {line}", file=sys.stderr, flush=True)


def _try_envelope_fallback(
    entry: dict[str, str], verdict: dict, project_dir: pathlib.Path
) -> bool:
    """Apply the T-14 escape hatch: inject + audit; True means "let it spawn".

    Only (b) skew and (c) legacy are down-gradable; the plain `missing`
    verdict is a producer that is not provably old and keeps the default
    refusal. Any failure (hatch off, uninjectable card, write error, skeleton
    still non-compliant) returns False so the caller records the refusal and
    the row goes `failed` — never a silent spawn.
    """
    if verdict["kind"] not in ("skew", "legacy"):
        return False
    if not autopilot_config.envelope_fallback_enabled(project_dir):
        return False
    injected = envelope_fallback_inject(verdict["text"])
    if injected is None:
        return False
    try:
        pathlib.Path(entry["task_path"]).write_text(injected, encoding="utf-8")
    except OSError:
        return False
    _record_envelope_fallback(entry, verdict)
    return True


def _emit_envelope_skew_alarms(
    skew_rows: dict[str, list[tuple[dict[str, str], str]]],
) -> None:
    """One aggregate alarm per key per poll (T-14 requirement 2).

    `skew_rows` maps owner key -> the rejected skew rows of THIS poll. Exactly
    one line per key (never one per row), carrying the key, the row count, the
    producer identities, the baseline and the upgrade pointer. Written to
    stderr — which `mw serve` captures into `.mw/launcher.log`, the existing
    doctor-readable diagnostic surface — and persisted once into the first
    row's trace.log and worker.log, because launcher.log is truncated per serve
    session and the queue row itself carries no reason text.
    """
    for key in sorted(skew_rows):
        rows = skew_rows[key]
        producers = sorted({producer for _entry, producer in rows if producer})
        line = (
            f"[ENVELOPE-SKEW] key={key} refused_rows={len(rows)} "
            f"producer={', '.join(producers) or '(unknown)'} "
            f"baseline={ENVELOPE_PRODUCER_BASELINE} "
            f"(service framework {ENVELOPE_PRODUCER_BASELINE_SEMVER or 'unknown'}) — "
            "project framework copy did not inject the canonical envelope, its "
            "dispatches are refused (fail-closed, other rows/keys unaffected). "
            + _upgrade_pointer()
        )
        print(f"[launcher] {line}", file=sys.stderr, flush=True)
        first = rows[0][0]
        try:
            _record_trace_line(first, f"[LAUNCHER] {mw_common.iso_now()} {line}")
            log_path = _worker_log_path(first)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"[launcher] {line}\n")
        except Exception:  # noqa: BLE001 — an alarm must never break the poll
            pass  # best-effort; stderr/launcher.log already carries it


def _starter_prompt(task_path: str) -> str:
    """Build the short ASCII turn-starter pointing the worker at its task file.

    The full task body must NEVER travel through argv. On Windows the npm
    `.cmd` shims re-expand `%*` through cmd.exe: any quote / & / | / > sequence
    in a body-sized argument re-tokenizes into shell fragments. Verified
    failure mode (OverCode pch-migration-s1-refactor-2): a task containing
    `rg -n \"pch_out_dir.*\" ...` made cmd execute that fragment
    (\"'pch_out_dir.*' 不是内部或外部命令\") and the worker received a truncated
    prompt, replied with \"请提供具体任务\" and idled out. Flattening newlines
    does not help — quote parity decides, not line breaks. The worker reads the
    self-contained task.md itself instead (pi: PI_WORKER_TASK env is already
    set by _build_env and the worker-side extension reads it; claude/codex:
    the starter names the absolute path and their read tools fetch it).
    """
    p = _require_task_file(task_path)
    return (
        f"Read your task file at {p.resolve()} and execute it end-to-end. "
        "It is self-contained: full instructions, context and acceptance "
        "criteria. Do not ask for the task body; report results when done. "
        "Your final reply MUST open with a one-line conclusion: status plus "
        "key result or blocker."
    )


def _resolve_cli(name: str) -> str:
    """Resolve a worker CLI name to a full executable path.

    On Windows, pi/claude/codex are installed as npm `.cmd` shims. subprocess
    with shell=False calls CreateProcess, which only appends `.exe` to a bare
    name — so ["codex", ...] fails with FileNotFoundError (WinError 2) and every
    worker is marked "failed", i.e. no agent can be invoked. shutil.which honors
    PATHEXT and returns the `.cmd` path, which Popen can execute directly.
    On POSIX this is a harmless PATH lookup that returns the same name's path.
    """
    resolved = shutil.which(name)
    if resolved is None:
        raise RuntimeError(
            f"Worker CLI {name!r} not found on PATH. Install it or add it to PATH."
        )
    return resolved


def _build_command(entry: dict[str, str]) -> list[str]:
    cli = entry["cli"].lower()
    provider = entry.get("provider", "").strip()
    # Model semantics: entry["model"] may carry a resolved prefix from
    # _effective_entry — a provider prefix has already remapped `provider`
    # (e.g. claude/x -> anthropic), so the flag below follows it. Empty model
    # keeps the historical per-cli default. Model is just a CLI flag; the
    # provider / credential wiring in _build_env is unchanged, so the model
    # must be compatible with the route that (cli, provider) resolves to.
    model = entry.get("model", "").strip()
    task_path = entry["task_path"]
    starter = _starter_prompt(task_path)
    if cli == "pi":
        if provider == "timi":
            return ["pi", "--provider", "timi", "--model", model or "glm-5.3", "-p", starter]
        # Direct non-timi providers (anthropic / openai-codex / deepseek /
        # zai-coding-cn, set via model prefixes): explicit --provider so the
        # flag can never ride on pi's default-provider resolution.
        if provider in ("anthropic", "openai-codex", "deepseek", "zai-coding-cn"):
            if not model:
                raise RuntimeError(
                    f"pi provider {provider!r} requires an explicit model "
                    "(no per-route default is hardcoded for direct providers)"
                )
            return ["pi", "--provider", provider, "--model", model, "-p", starter]
        # Extension reads task.md via PI_WORKER_TASK; -p passes a short starter
        # pointing at the task file (never the body — see _starter_prompt).
        cmd = ["pi"]
        if model:
            cmd += ["--model", model]
        cmd += ["-p", starter]
        return cmd
    elif cli == "codex":
        if provider not in ("", "codex"):
            raise RuntimeError(
                f"Codex workers support only an empty provider or 'codex', got {provider!r}"
            )
        return ["codex", "exec", "-m", model or "gpt-5.6-sol", starter]
    elif cli == "claude":
        cmd = ["claude"]
        if model:
            cmd += ["--model", model]
        cmd += ["-p", starter]
        return cmd
    else:
        return [cli, starter]


# ── Orphan reconcile (AC-012/AC-013, design D-006~D-008) ──────────────────────

def _parse_utc_ts(raw: str) -> datetime.datetime | None:
    """Parse a UTC ISO timestamp carrying `+00:00` or `Z` (spec §5 pitfall).

    The TS side writes Date.toISOString() (`...Z`) while the Python side
    writes iso_now() (`...+00:00`); datetime.fromisoformat only accepts `Z`
    on Python 3.11+, so normalize before parsing. Naive values are read as
    UTC (spec 2.1). Unparseable/empty -> None.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        ts = datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.timezone.utc)
    return ts


def _row_last_activity(entry: dict[str, str], task_dir: pathlib.Path) -> float | None:
    """Epoch seconds of the newest silence-rule evidence for one queue row:
    max(newest task-dir file mtime, row updated_at).

    updated_at parse failure falls back to dispatched_at; when both are
    unparseable there is no timestamp evidence at all and the caller skips
    the row rather than guessing (AC-013).
    """
    row_ts: datetime.datetime | None = None
    for field in ("updated_at", "dispatched_at"):
        row_ts = _parse_utc_ts(entry.get(field, ""))
        if row_ts is not None:
            break
    if row_ts is None:
        return None
    dir_last = mw_common.task_dir_last_activity(task_dir)
    if dir_last is None:
        return row_ts.timestamp()
    return max(dir_last, row_ts.timestamp())


def _reconcile_orphans(
    project_dir: pathlib.Path,
    running_procs: dict[str, subprocess.Popen[bytes]],
) -> None:
    """Converge orphaned running rows to a terminal status (AC-012/AC-013).

    An orphan row is status==running with task_key not in running_procs —
    spawned by another launcher, or by one that has since died. Own rows are
    never touched (the reap path owns them). Positive evidence (an [END]
    line, or a lone output.md from an old bundle) applies unconditionally
    every poll; the silence rule (presumed dead) additionally yields to
    another live launcher's fresh beat (D-008).

    T-20/D-022 adds the product-carried state: a worker-written `run.json`
    outranks the ledger row. A terminal `run.json` converges the row to that
    exact status (the row merely lagged), and an active `run.json` whose process
    is gone converges to `lost` — the launcher may only ADD `lost`, never
    fabricate done/failed, and never touches the artifacts (the scene is what
    the human needs to judge a run whose outcome was never verified).
    """
    for entry in _parse_workers_file(_workers_path(project_dir)):
        if entry["status"] != "running":
            continue
        key = entry["task_key"]
        if key in running_procs:
            continue  # own row: never touched by reconcile
        task_dir = pathlib.Path(entry["task_path"]).parent
        end_exit = mw_common.parse_end_exit(task_dir)
        run_status = mw_common.read_run_status(task_dir)
        if end_exit is not None:
            status = _exit_to_status(end_exit)
            reason = f"reconcile: [END] exit={end_exit} (orphaned row)"
        elif run_status in mw_common.RUN_TERMINAL_STATUSES:
            # The product already ended the run; the row only lagged (e.g. the
            # launcher died between the worker's terminal write and the reap).
            status = run_status
            reason = f"reconcile: run.json status={run_status} (orphaned row)"
        elif run_status in ("running", "pending"):
            # The run recorded itself as live and its process is gone: the
            # outcome is unverified. `output.md` proves the terminal write path
            # ran, so no silence window is needed there (its absence is what the
            # window protects against — a live run owned by another launcher).
            if not (task_dir / "output.md").exists():
                last = _row_last_activity(entry, task_dir)
                if last is None:
                    continue  # no parseable activity evidence — never guess
                age_min = (time.time() - last) / 60.0
                if age_min < mw_common.orphan_dead_after():
                    continue  # within the silence window: keep running
                if mw_common.other_live_launcher(project_dir, os.getpid()):
                    print(
                        f"[launcher] reconcile: silence rule yielded for {key!r} "
                        "(another live launcher holds a fresh beat)",
                        file=sys.stderr,
                        flush=True,
                    )
                    continue
            mw_common.mark_run_lost(task_dir)
            status = "lost"
            reason = f"reconcile: run.json status={run_status}, process gone, outcome unverified (scene preserved)"
        elif (task_dir / "output.md").exists():
            status = "failed"
            reason = "reconcile: completed without END marker, status unverifiable — read output.md"
        else:
            # Silence rule (AC-013): no terminal evidence at all.
            last = _row_last_activity(entry, task_dir)
            if last is None:
                continue  # no parseable activity evidence — never guess
            age_min = (time.time() - last) / 60.0
            if age_min < mw_common.orphan_dead_after():
                continue  # within the silence window: keep running
            if mw_common.other_live_launcher(project_dir, os.getpid()):
                print(
                    f"[launcher] reconcile: silence rule yielded for {key!r} "
                    "(another live launcher holds a fresh beat)",
                    file=sys.stderr, flush=True,
                )
                continue
            status = "failed"
            reason = f"reconcile: presumed dead (no activity for {int(age_min)}m)"
        _record_reconcile(entry, reason)
        try:
            _update_status(project_dir, key, status)
        except Exception as exc:  # noqa: BLE001 — never kill the poll loop
            print(
                f"[launcher] reconcile status update failed for {key!r}: {exc}",
                file=sys.stderr, flush=True,
            )


# ── Main loop ─────────────────────────────────────────────────────────────────

# ── Workspace-profile tear check (mw-target-partition D-007/D-013, AC-020) ────

_PROFILE_MARK_V1 = "<!-- mw-profile: v1 -->"
_PROFILE_MARK_V2 = "<!-- mw-profile: v2 -->"
_PROFILE_MODE_RE = re.compile(r"^\[mw\] mode: (single|dual|partition)[ \t]*$", re.MULTILINE)
# The legacy (v1-marker) renderer emits this line only for dual injections
# — it is what separates dual from single-injected v1 blocks (which carry
# no mode line at all).
_V1_DUAL_LINE_RE = re.compile(r"^Game root: ", re.MULTILINE)
# Block-head window (mw-target-partition FIX-11): the mode line must sit
# within the first _PROFILE_HEAD_WINDOW lines after the marker line —
# blank and comment lines (`<!-- ... -->` / `#`) are tolerated inside the
# window, but a mode line beyond it means an orphaned marker (malformed).
_PROFILE_HEAD_WINDOW = 8


def _task_profile_mode(task_path: str) -> str | None:
    """Workspace mode recorded in a task.md profile block (D-013): a v2
    marker carries an explicit `[mw] mode: X` line; a v1 marker carries no
    mode line — the legacy renderer emits the `Game root:` line only for
    dual injections, which separates dual from single-injected v1 blocks
    (reading every v1 block as dual would fail-closed legit single+sections
    tasks, an injecting dispatch shape that predates partition). No marker
    at all = no profile block (legal — nothing to compare).

    mw-target-partition FIX-3 (fail-closed): a v2 marker whose block head
    (the first non-blank, non-comment line after the marker line) is not a
    parseable mode line is a MALFORMED block, not "no profile" — returning
    None here would let the spawn pass as un-profiled and silently re-cwd
    on an active switch. Raises RuntimeError ("profile malformed") instead;
    the head-only search also keeps a stray `[mw] mode:` anywhere else in
    the file from masking a malformed block.

    mw-target-partition FIX-11 (tolerance): blank lines and comment lines
    (starting with `<!--` or `#`) between the marker and the mode line are
    skipped, but only within the block-head window (the first
    _PROFILE_HEAD_WINDOW lines after the marker) — the generators never
    emit that shape today, yet a hand-annotated block stays parseable; a
    head that overflows the window is still malformed (never an
    un-profiled pass)."""
    try:
        content = pathlib.Path(task_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    v2 = content.find(_PROFILE_MARK_V2)
    if v2 != -1:
        after_marker = content[v2 + len(_PROFILE_MARK_V2) :]
        rest_of_marker_line = after_marker.split("\n", 1)
        head = rest_of_marker_line[1] if len(rest_of_marker_line) > 1 else ""
        mode_line: str | None = None
        for line in head.split("\n")[:_PROFILE_HEAD_WINDOW]:
            stripped = line.strip()
            if stripped == "" or stripped.startswith(("<!--", "#")):
                continue
            mode_line = line
            break
        m = _PROFILE_MODE_RE.match(mode_line) if mode_line is not None else None
        if m is None:
            raise RuntimeError(
                "task.md v2 profile malformed (expected '[mw] mode: <single|dual|partition>' "
                "as the first line after the '<!-- mw-profile: v2 -->' marker) — "
                "spawn refused; re-dispatch the task"
            )
        return m.group(1)
    v1 = content.find(_PROFILE_MARK_V1)
    if v1 != -1:
        return "dual" if _V1_DUAL_LINE_RE.search(content, v1) is not None else "single"
    return None


def _record_trace_line(entry: dict[str, str], line: str) -> None:
    """Append a launcher-side lifecycle line to the task's trace.log.

    A config-torn refusal (AC-020) never spawns a worker, so trace.log —
    the file the PM reads for worker state — must still carry the terminal
    evidence. A plain `[LAUNCHER]` line is inert to the [START]/[END]/
    [HEARTBEAT] parsers (mw_common / autopilot.state)."""
    try:
        trace = pathlib.Path(entry["task_path"]).parent / "trace.log"
        trace.parent.mkdir(parents=True, exist_ok=True)
        with trace.open("a", encoding="utf-8") as fh:
            fh.write(f"{line}\n")
    except OSError:
        pass  # best-effort; worker.log and the queue row still carry the reason


def _check_config_tear(entry: dict[str, str], config: dict) -> None:
    """AC-020 (fail-closed): the task.md profile block records the workspace
    mode at dispatch time. If the active mode was switched before spawn, the
    recorded profile (roots, toolchain renders) is stale and the spawn cwd
    would silently move (partition root <-> game root <-> control root) —
    refuse the spawn, mark the task failed with 'config torn' + both mode
    names, and leave the evidence in trace.log (D-013). No profile block =
    no recorded mode = nothing to compare (pre-partition tasks stay legal)."""
    recorded = None
    try:
        recorded = _task_profile_mode(entry["task_path"])
    except RuntimeError as exc:
        # FIX-3: malformed v2 block — same terminal evidence as a tear.
        _record_trace_line(entry, f"[LAUNCHER] {mw_common.iso_now()} {exc}")
        raise
    if recorded is None or recorded == config["mode"]:
        return
    reason = (
        f"config torn: task.md profile mode '{recorded}' != active mode "
        f"'{config['mode']}' (target.yml active switched after dispatch) — "
        "spawn refused; re-dispatch the task"
    )
    _record_trace_line(entry, f"[LAUNCHER] {mw_common.iso_now()} {reason}")
    raise RuntimeError(reason)


_RAG_FINGERPRINT_RE = re.compile(r"^fingerprint=(\S+)[ \t\r]*$", re.MULTILINE)


def _task_rag_fingerprint(task_path: str) -> str | None:
    """Recorded `fingerprint=` inside a task.md mw-rag block.

    None = no block at all (nothing to compare — zero behavior change). An
    empty string = marker present but no fingerprint line, i.e. a malformed
    block; the caller fails closed on it (same shape as the profile FIX-3
    malformed-block refusal).
    """
    try:
        content = pathlib.Path(task_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    idx = content.find(mw_common.RAG_MARKER_V1)
    if idx == -1:
        return None
    match = _RAG_FINGERPRINT_RE.search(content, idx)
    return match.group(1) if match else ""


def check_rag_tear(entry: dict[str, str], project_dir: pathlib.Path) -> None:
    """VC-022 (fail-closed): the task.md `<!-- mw-rag: v1 -->` block records
    the RAG static-config fingerprint at dispatch time (design D-009). If the
    enabled servers' static config (url / token_env NAME / skill / sources /
    capabilities / roles / phases / budgets) or the path_roots file CONTENT
    changed before spawn, the worker would silently query a different
    knowledge base — refuse the spawn with 'config torn (rag)' and leave the
    [LAUNCHER] evidence in trace.log, exactly like _check_config_tear. No rag
    block = nothing recorded = nothing to compare (RAG-less tasks stay
    legal); probe/health state and un-enabled servers never move the
    fingerprint, so a service restart (or editing a disabled server) does
    not tear.
    """
    recorded = _task_rag_fingerprint(entry["task_path"])
    if recorded is None:
        return  # no rag block: zero behavior change
    rag_config, _error = mw_common.load_rag_config(project_dir)
    current = mw_common.rag_fingerprint(rag_config)
    if recorded and recorded == current:
        return
    reason = (
        f"config torn (rag): task.md fingerprint={recorded or '(missing)'} != "
        f"current {current} (the enabled RAG server config or the path_roots "
        "file content changed after dispatch) — spawn refused; re-dispatch "
        "the task"
    )
    _record_trace_line(entry, f"[LAUNCHER] {mw_common.iso_now()} {reason}")
    raise RuntimeError(reason)


def _poll_once(
    project_dir: pathlib.Path,
    config: dict,
    running_procs: dict[str, subprocess.Popen[bytes]],
    log_handles: dict[str, object],
    pending_queue: list[dict[str, str]],
    max_workers: int | None,
    tree_watcher: tree_watch.TreeWatch | None = None,
) -> None:
    """One launcher poll cycle: beat, archive stale, reap, reconcile, discover, spawn."""
    # D-008: refresh this launcher's beat first — it is how another
    # launcher's silence rule knows we are live (and ours knows of them).
    mw_common.launcher_beat_write(project_dir, os.getpid())

    # G4 tree watch (AC-010/AC-011): the sampler is cadence-gated inside
    # TreeWatch (6 polls by default, PI_TREE_WATCH_SEC override, 0 = off) and
    # never raises. `tree_watcher is None` for direct _poll_once callers
    # (tests) keeps them side-effect free.
    if tree_watcher is not None:
        try:
            tree_watch.emit_alarms(tree_watcher.tick())
        except Exception as exc:  # noqa: BLE001 — a sampler must never break the poll
            print(f"[launcher] tree watch error (continuing): {exc}", file=sys.stderr, flush=True)

    # T-18/D-027 (AC-021): `None` resolves to the configured cap, never to
    # "unbounded". A direct `_poll_once(..., None)` caller is bounded too, so
    # the IN-3 amplifier (66 concurrent workers) cannot come back through a
    # forgotten argument.
    limit = max_workers if max_workers is not None else mw_common.launcher_max_workers(project_dir)

    # Capture the pre-archive view so the "task.md not found" archive stays
    # observable (requirement 3: the stale path must not be silent).
    pre_archive = _parse_workers_file(_workers_path(project_dir))
    archived = mw_common.archive_stale_entries(project_dir)
    if archived:
        paths = {e["task_key"]: e["task_path"] for e in pre_archive}
        for key in archived:
            print(
                f"[launcher] archived stale (task.md not found): {key} "
                f"({paths.get(key, '?')})",
                file=sys.stderr, flush=True,
            )

    # Reap finished processes
    finished = [k for k, p in running_procs.items() if p.poll() is not None]
    # AC-006/DD-06: reap reads the product (run.json) before the exit code.
    reap_dirs = _reap_task_dirs(project_dir) if finished else {}
    for key in finished:
        proc = running_procs.pop(key)
        code = proc.returncode if proc.returncode is not None else 1
        status = _reap_status(reap_dirs.get(key), code, key)
        _update_status(project_dir, key, status)
        # Close the per-task worker.log handle now the process has exited.
        lh = log_handles.pop(key, None)
        if lh is not None:
            try:
                lh.close()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass
        # Drain queue now a slot is free
        if pending_queue:
            next_entry = pending_queue.pop(0)
            _spawn(next_entry, project_dir, config, running_procs, log_handles)

    # Reconcile orphaned running rows (AC-012/AC-013): after reap (rows just
    # reaped are already terminal) and before discover/spawn.
    _reconcile_orphans(project_dir, running_procs)

    # Discover new pending tasks
    entries = _parse_workers_file(_workers_path(project_dir))
    # Ack convergence (T-18/D-027, AC-023): an acked task already finished —
    # its row only looks non-terminal because a queue rebuild rewrote it
    # (IN-3). Converge it to `done` and never spawn it again. This is the
    # fail-closed direction: a stale ack costs one skipped spawn of a task the
    # PM has already absorbed, while a missed ack costs a full re-run.
    acked = mw_common.read_acked(project_dir)
    for entry in entries:
        key = entry["task_key"]
        if key not in acked or entry["status"] in mw_common._TERMINAL_STATUSES:
            continue
        # Prefer the product's own verdict when it wrote one (D-022); fall back
        # to `done` (ack only happens for a terminal task).
        run_status = mw_common.read_run_status(pathlib.Path(entry["task_path"]).parent)
        converged = run_status if run_status in mw_common.RUN_TERMINAL_STATUSES else "done"
        try:
            _update_status(project_dir, key, converged)
            entry["status"] = converged
            print(
                f"[launcher] {key}: acked at {acked[key]} but the queue row was "
                f"non-terminal — converged to {converged} (AC-023)",
                file=sys.stderr,
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 — never mask the poll loop
            print(f"[launcher] {key}: ack convergence failed: {exc}", file=sys.stderr, flush=True)
    # T-14 requirement 2: skew refusals of THIS poll, grouped by owner key, so
    # the alarm is one aggregate line per key instead of one per row.
    skew_rows: dict[str, list[tuple[dict[str, str], str]]] = {}
    for entry in entries:
        key = entry["task_key"]
        fallback_verdict: dict | None = None
        if entry["status"] != "pending":
            continue
        if key in running_procs:
            continue  # AC-008: no duplicate spawn
        if key in acked:
            continue  # AC-023: acked tasks are never re-spawned
        # Location contract (D-001 isolation): reject root-level / misplaced
        # task dirs loudly instead of spawning them.
        try:
            _validate_task_path(project_dir, entry["task_path"])
        except RuntimeError as exc:
            _record_spawn_failure(entry, str(exc))
            try:
                _update_status(project_dir, key, "failed")
            except Exception:  # noqa: BLE001 — never mask the poll loop
                pass
            continue
        # G-3 service-layer envelope fallback (T-03): the only layer that sees
        # conductor direct writes and hand-written queue rows. A non-compliant
        # card is never spawned and never silently archived — the row goes
        # failed and the reason is persisted to the task's worker.log.
        # T-09: the judge applies to every row created at/after the cutover
        # boundary, not only to cards that happen to declare a signal.
        if _envelope_enforced(entry):
            verdict = classify_envelope_refusal(entry)
            if verdict is not None:
                # T-14 requirement 3: the explicit, default-off escape hatch
                # injects a canonical skeleton + audits and lets the row spawn.
                if _try_envelope_fallback(entry, verdict, project_dir):
                    fallback_verdict = verdict
                else:
                    _record_envelope_failure(
                        entry, verdict["reason"], verdict["guidance"]
                    )
                    try:
                        _update_status(project_dir, key, "failed")
                    except Exception:  # noqa: BLE001 — never mask the poll loop
                        pass
                    if verdict["kind"] == "skew":
                        skew_rows.setdefault(
                            mw_common.worker_owner_key(entry), []
                        ).append((entry, verdict["producer"]))
                    # T-14 requirement 4: a refusal only ever affects THIS row —
                    # no return/raise, so the same key's other rows and every
                    # other key keep being polled in this same cycle.
                    continue
        if len(running_procs) >= limit:
            if not any(q["task_key"] == key for q in pending_queue):
                pending_queue.append(entry)  # AC-007
            continue
        _spawn(entry, project_dir, config, running_procs, log_handles)
        if fallback_verdict is not None:
            # Re-append the audit fact: _spawn truncates worker.log, so the
            # pre-spawn write in _try_envelope_fallback does not survive the
            # normal (immediately spawned) path.
            _record_envelope_fallback(entry, fallback_verdict)
    if skew_rows:
        _emit_envelope_skew_alarms(skew_rows)


def run(
    project_dir: pathlib.Path,
    poll_interval: int = DEFAULT_POLL_INTERVAL,
    max_workers: int | None = None,
    dry_run: bool = False,
    providers_path: pathlib.Path | None = None,
    port_overrides: dict[str, int] | None = None,
) -> None:
    """Main launcher loop. Runs until interrupted.

    Concurrency is always bounded (T-18/D-027, AC-021): an explicit
    ``max_workers`` wins (CLI > task.md header > config > default), otherwise
    the effective `launcher_max_workers` applies — `None` is never
    "unbounded".
    """
    config = _load_providers(providers_path or (pathlib.Path(__file__).parent / "providers.json"))
    max_workers = max_workers if max_workers is not None else mw_common.launcher_max_workers(project_dir)
    # G4: one sampler per launcher run; its poll counter lives across ticks.
    tree_watcher = tree_watch.TreeWatch(project_dir, poll_interval)

    # Apply port overrides from CLI (--pi-port, --claude-port, etc.)
    if port_overrides:
        for provider_key, port in port_overrides.items():
            if provider_key in config.get("providers", {}):
                config["providers"][provider_key] = {
                    **config["providers"][provider_key], "port": port,
                }

    # task_key -> Popen
    running_procs: dict[str, subprocess.Popen[bytes]] = {}
    # task_key -> open worker.log handle (closed when the process is reaped)
    log_handles: dict[str, object] = {}
    # Queue for tasks waiting on the max_workers limit
    pending_queue: list[dict[str, str]] = []

    if dry_run:
        _dry_run(project_dir, config)
        return

    print(
        f"[launcher] max_workers={max_workers} (bounded; AC-021)",
        file=sys.stderr,
        flush=True,
    )

    while True:
        try:
            _poll_once(
                project_dir, config, running_procs, log_handles, pending_queue,
                max_workers, tree_watcher,
            )
        except Exception as exc:  # noqa: BLE001 — one bad poll must never kill the loop
            print(f"[launcher] poll error (continuing): {exc}", file=sys.stderr, flush=True)

        time.sleep(poll_interval)


def _worker_target_config(project_dir: pathlib.Path) -> dict:
    """Load the spawn-gating target config (mw-target-partition D-007): the
    error wrapper is shape-dynamic (mw_common.describe_target_error — v1/no
    file keeps the historical 'target.yml is unusable' text, a v2 file
    names its active mode)."""
    try:
        return mw_common.load_target_config(project_dir)
    except mw_common.TargetConfigError as e:
        raise RuntimeError(mw_common.describe_target_error(e, project_dir)) from None


def _worker_cwd(project_dir: pathlib.Path, config: dict | None = None) -> pathlib.Path:
    """Workspace spawn root (mw-dual-workspace D-001; mw-target-partition
    D-007): worker cwd is the game root in dual mode, the partition root in
    partition mode, the control workspace in single mode. Fail closed: an
    unusable target.yml refuses the spawn (recorded per-task by _spawn's
    isolation handler) instead of silently falling back to the control
    root. Callers that already resolved the config (the tear check in
    _spawn) pass it through — one load per spawn."""
    cfg = config if config is not None else _worker_target_config(project_dir)
    if cfg["mode"] == "dual":
        return pathlib.Path(cfg["game_root"])
    if cfg["mode"] == "partition":
        return pathlib.Path(cfg["partition_root"])
    return project_dir


def _spawn(
    entry: dict[str, str],
    project_dir: pathlib.Path,
    config: dict,
    running_procs: dict[str, subprocess.Popen[bytes]],
    log_handles: dict[str, object] | None = None,
) -> None:
    """Spawn one worker. Any per-task failure marks it failed and continues.

    Design D-001: a missing credential (or any other per-task error) is
    isolated to the task — it can never take down the launcher or mw serve.
    """
    try:
        # Spawn gate (mw-target-partition D-007): the target config decides
        # both the tear check (AC-020) and the cwd — loaded once, before any
        # per-task side effect, so a torn/broken config never reaches
        # model/env/command building.
        target_config = _worker_target_config(project_dir)
        _check_config_tear(entry, target_config)
        check_rag_tear(entry, project_dir)
        model_value, model_source = _resolve_entry_model(entry, project_dir)
        effective = _effective_entry(entry, model_value)
        # RAG static-config strip set (T-07/D-010): declared token env NAMES
        # are removed by _build_env; the enabled subset is re-added by the
        # post-step so none of _build_env's six return paths needs RAG code.
        rag_config, _rag_error = mw_common.load_rag_config(project_dir)
        env = _build_env(effective, config, rag_config)
        inject_rag_env(env, effective, project_dir)
        cmd = _build_command(effective)
        print(
            f"[launcher] {entry['task_key']}: model={model_value or '(route default)'} source={model_source}",
            flush=True,
        )
        override_note = _model_override_note(entry, project_dir, model_value, model_source)
        if override_note:
            print(override_note, flush=True)
        # Resolve the CLI binary to a full path so Windows npm `.cmd` shims are
        # found (CreateProcess only appends `.exe`). See _resolve_cli.
        cmd[0] = _resolve_cli(cmd[0])
        # Capture worker stdout+stderr into a per-task worker.log for diagnosability
        log_file = None
        try:
            log_file = open(_worker_log_path(entry), "wb")  # noqa: SIM115 — closed at reap (or below)
        except OSError:
            log_file = None
        # subprocess.Popen with list args (no shell=True — AC-023); cwd is the
        # game root in dual mode / the partition root in partition mode, else
        # the control workspace (D-001/D-007) — relative tool paths stay
        # anchored to the target project.
        spawn_kwargs: dict = {
            "env": env, "cwd": str(_worker_cwd(project_dir, target_config)),
            "stdout": log_file if log_file is not None else subprocess.DEVNULL,
            "stderr": subprocess.STDOUT if log_file is not None else subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            spawn_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        proc = subprocess.Popen(cmd, **spawn_kwargs)  # noqa: S603
        running_procs[entry["task_key"]] = proc
        if log_file is not None:
            # Keep the handle open until the process is reaped (run() closes it).
            # Without a tracker (e.g. unit tests), close now — the child kept its own fd.
            if log_handles is not None:
                log_handles[entry["task_key"]] = log_file
            else:
                log_file.close()
        _update_status(project_dir, entry["task_key"], "running")
    except Exception as exc:  # noqa: BLE001 — per-task isolation (design D-001)
        msg = str(exc)
        print(f"[launcher] spawn failed for {entry['task_key']!r}: {msg}", file=sys.stderr, flush=True)
        _record_spawn_failure(entry, msg)
        try:
            _update_status(project_dir, entry["task_key"], "failed")
        except Exception as exc2:  # noqa: BLE001 — never mask the loop
            print(f"[launcher] status update failed for {entry['task_key']!r}: {exc2}", file=sys.stderr, flush=True)


def _mask_env_value(key: str, value: str) -> str:
    lower = key.lower()
    if "key" in lower or "token" in lower or "secret" in lower or "password" in lower:
        return "***"
    return value


def _dry_run(project_dir: pathlib.Path, config: dict) -> None:
    entries = _parse_workers_file(_workers_path(project_dir))
    pending = [e for e in entries if e["status"] == "pending"]
    for entry in pending:
        try:
            cmd = _build_command(entry)
            rag_config, _rag_error = mw_common.load_rag_config(project_dir)
            env = _build_env(entry, config, rag_config)
            inject_rag_env(env, entry, project_dir)
        except Exception as exc:  # noqa: BLE001 — report, do not crash
            print(f"[DRY-RUN] {entry['task_key']}: cannot build ({exc})")
            continue
        relevant_keys = [k for k in env if k not in os.environ or env[k] != os.environ.get(k)]
        env_display = " ".join(f"{k}={_mask_env_value(k, env[k])}" for k in relevant_keys)
        # Truncate long prompts in command display
        display_cmd = list(cmd)
        if len(display_cmd) > 2 and len(display_cmd[-1]) > 120:
            display_cmd[-1] = display_cmd[-1][:120] + "..."
        print(f"[DRY-RUN] {env_display} {' '.join(display_cmd)}")
        print(f"  task.md: {entry['task_path']}")


# ── CLI entry ─────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-Workers launcher")
    parser.add_argument("--project", required=True, help="Project directory")
    parser.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL)
    parser.add_argument(
        "--max-workers", type=int, default=None,
        help="Concurrency cap; default = launcher_max_workers from "
             ".agenticdoc/_autopilot/config.json, else 8 (AC-021: never unbounded)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--providers", default=None, help="Path to providers.json")
    # Port overrides: map provider key to proxy port (mirrors mw serve flags)
    parser.add_argument("--pi-port", type=int, default=None, help="Override pi provider proxy port")
    parser.add_argument("--claude-port", type=int, default=None, help="Override claude-cli provider proxy port")
    parser.add_argument("--deepseek-port", type=int, default=None, help="Override deepseek provider proxy port")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    project = pathlib.Path(args.project).resolve()
    providers_path = pathlib.Path(args.providers) if args.providers else None
    port_overrides: dict[str, int] = {}
    if args.pi_port is not None:
        port_overrides["claude"] = args.pi_port  # pi CLI uses the "claude" provider key
    if args.claude_port is not None:
        port_overrides["claude-cli"] = args.claude_port
    if args.deepseek_port is not None:
        port_overrides["deepseek"] = args.deepseek_port
    run(
        project_dir=project,
        poll_interval=args.poll_interval,
        max_workers=args.max_workers,
        dry_run=args.dry_run,
        providers_path=providers_path,
        port_overrides=port_overrides or None,
    )
