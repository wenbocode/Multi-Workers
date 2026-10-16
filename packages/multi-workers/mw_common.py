"""
mw_common.py 鈥?shared Multi-Workers core.

Single source for provider/credential config, route precheck, stale-entry
archival, and doctor diagnostics. Imported by mw.py and launcher.py so the
serve entry, the dispatcher, and both doctor frontends stay single-sourced
(design D-003/D-005 of mw-dispatch-reliability).

Credential config schema (providers.json):

    {
      "credentials": {
        "<name>": { "sources": [
          { "env": "VAR_NAME" },
          { "file": "~/path.toml", "format": "toml", "field": "auth.api_key" }
        ]}
      },
      "providers": {
        "<route>": {
          "port": 7001,                  # optional (direct routes have none)
          "base_url_env": "VAR",         # env var the worker sees as base URL
          "api_key_env": "VAR",          # env var the worker sees as key
          "credential": "<name>"         # credential chain to resolve
        }
      }
    }

Sources are tried in order; the first one that yields a value wins. `file`
sources support toml/json/plain plus a dotted `field` path. Adding a route is
a config-only change (AC-017).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import time
import sys
from typing import Mapping, NamedTuple, Sequence

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover - very old interpreters
    tomllib = None  # type: ignore[assignment]

try:
    import yaml  # PyYAML: implicit dep for target.yml (mw-dual-workspace D-010)
except ImportError:  # pragma: no cover - doctor reports this explicitly
    yaml = None  # type: ignore[assignment]

from autopilot import config as autopilot_config  # noqa: E402  (schema defaults, T-18)
from autopilot import effective_config  # noqa: E402  (layered config, D-002)
from autopilot import contract_guard  # noqa: E402  (G3 AC/VC identity, T-11)
from autopilot import gates as gate_protocol  # noqa: E402  (gate queue, T-13)
from autopilot import roadmap as roadmap_protocol  # noqa: E402  (validate_roadmap, AC-031)
from autopilot import timeline as autopilot_timeline  # noqa: E402  (beat watermark, T-08)

# Credential env vars that are never declared in providers.json but must still
# be stripped from every worker env (kept from the pre-schema launcher).
EXTRA_CREDENTIAL_VARS: frozenset[str] = frozenset([
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "TIMI_BASE_URL",
])

# Fallback credential/env wiring used when providers.json is missing or
# unreadable. Mirrors the shipped providers.json exactly.
_DEFAULT_CONFIG: dict = {
    "credentials": {
        "anthropic": {"sources": [{"env": "ANTHROPIC_API_KEY"}]},
        "anthropic-auth": {"sources": [{"env": "ANTHROPIC_AUTH_TOKEN"}]},
        "deepseek": {"sources": [{"env": "DEEPSEEK_API_KEY"}]},
        "timi": {"sources": [
            {"env": "TIMI_API_KEY"},
            {"file": "~/.pi/agent/auth.json", "format": "json", "field": "timi.key"},
        ]},
        "zai-coding-cn": {"sources": [
            {"env": "ZAI_CODING_CN_API_KEY"},
            {"file": "~/.pi/agent/auth.json", "format": "json", "field": "zai-coding-cn.key"},
        ]},
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
        "zai-coding-cn": {"api_key_env": "ZAI_CODING_CN_API_KEY", "credential": "zai-coding-cn"},
    },
}

# CLI name -> default route key when a task leaves `provider` empty.
# pi tasks default to the claude (proxied) route, claude tasks to claude-cli
# (oauth token), matching the pre-schema launcher behavior and dispatch-table.md.
CLI_DEFAULT_PROVIDER: dict[str, str] = {"pi": "claude", "claude": "claude-cli"}

# ── Dispatch model config (.mw/dispatch.yml) ─────────────────────────────
#
# Model values are `prefix/model-id` (e.g. timi/glm-5.3). The prefix is the
# USER-facing serving-channel namespace — deliberately NOT raw pi provider
# ids — and splits into two families:
#   * provider prefixes (direct connections, pi entries only):
#       timi -> pi provider "timi"
#       claude -> pi provider "anthropic"        (direct, no mw proxy)
#       codex -> pi provider "openai-codex"      (codex' own config)
#       deepseek -> pi provider "deepseek"       (direct, no mw proxy)
#       zai -> pi provider "zai-coding-cn"       (direct, no mw proxy)
#   * CLI prefixes (executor transports, must match the entry cli):
#       codex_cli -> codex exec, claude_cli -> claude CLI
# A bare model id (no prefix) keeps the entry's own (cli, provider) route.
# The TS side (agent-team-loop shared/dispatch-models.ts) mirrors
# PROVIDER_ID_TO_PREFIX; keep both maps in sync.
MODEL_PREFIX_TO_PI_PROVIDER: dict[str, str] = {
    "timi": "timi",
    "claude": "anthropic",
    "codex": "openai-codex",
    "deepseek": "deepseek",
    "zai": "zai-coding-cn",
}
PROVIDER_ID_TO_PREFIX: dict[str, str] = {v: k for k, v in MODEL_PREFIX_TO_PI_PROVIDER.items()}
CLI_PREFIX_TO_CLI: dict[str, str] = {
    "codex_cli": "codex",
    "claude_cli": "claude",
}
KNOWN_MODEL_PREFIXES = frozenset(MODEL_PREFIX_TO_PI_PROVIDER) | frozenset(CLI_PREFIX_TO_CLI)

# Configurable roles (mw model set <role>): main = the PM window itself;
# the rest map dispatch task types onto semantic buckets.
DISPATCH_ROLES = ("main", "coding", "review", "research", "vision")
TASK_TYPE_TO_ROLE: dict[str, str] = {
    "coding": "coding",
    "phase-writer": "coding",
    "repair": "coding",
    "roadmap-writer": "coding",
    "review": "review",
    "verifier": "review",
    "reviewer": "review",
    "research": "research",
    # mw-rag-integration T-09: PM-dispatched RAG research bucket, same model
    # role as research (mirror of TS DISPATCH_ROLE_BY_TYPE).
    "rag-research": "research",
    # mw-vision-role T-01: vision bucket (screenshot/diagram/visual analysis).
    "vision": "vision",
}

STALE_FILE_NAME = "_workers.stale.parallel"
STALE_REASON = "task.md not found"

# Entries in these statuses are history: a missing task.md is harmless (the dir
# may have been cleaned up), so only non-terminal entries get archived.
# `lost` (T-20/D-022) is terminal for the ledger too: the run is over, its
# outcome is simply unverified — keeping it out of this set would make every
# lost row permanent doctor noise and a permanent re-spawn candidate.
_TERMINAL_STATUSES = {"done", "failed", "needs-clarification", "lost"}


def iso_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


# 鈹€鈹€ Config loading 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def default_config() -> dict:
    """Deep-ish copy of the built-in default config."""
    return json.loads(json.dumps(_DEFAULT_CONFIG))


def load_providers(path: pathlib.Path | None) -> dict:
    """Load the providers+credentials config.

    Returns the normalized {"credentials": ..., "providers": ...} dict. Falls
    back to defaults when the file is missing or invalid. Legacy flat provider
    maps (pre-schema, api_key_env per route) are upgraded in memory.
    """
    if path is None or not path.exists():
        return default_config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_config()
    if not isinstance(data, dict):
        return default_config()
    if isinstance(data.get("credentials"), dict) and isinstance(data.get("providers"), dict):
        return data
    # Legacy schema: flat {route: {port, base_url_env, api_key_env}} map.
    credentials: dict = {}
    providers: dict = {}
    for name, cfg in data.items():
        if not isinstance(cfg, dict):
            continue
        env_name = cfg.get("api_key_env", "")
        if env_name:
            credentials[f"{name}-key"] = {"sources": [{"env": env_name}]}
            providers[name] = {**cfg, "credential": f"{name}-key"}
        else:
            providers[name] = dict(cfg)
    return {"credentials": credentials, "providers": providers}


# ── Dispatch model config (.mw/dispatch.yml + .mw/window-model) ───────────

def dispatch_config_path(project_root: pathlib.Path) -> pathlib.Path:
    return project_root / ".mw" / "dispatch.yml"


def window_model_path(project_root: pathlib.Path) -> pathlib.Path:
    return project_root / ".mw" / "window-model"


def load_dispatch_config(project_root: pathlib.Path) -> tuple[dict, str | None]:
    """Load .mw/dispatch.yml -> (config, error).

    config is {"models": {role: "prefix/model"}}; a missing file is ({}, None)
    (nothing configured). Any parse/validation problem returns ({}, message):
    model defaults are a convenience and must never block dispatching — the
    launcher falls through to the window model / per-cli defaults and doctor
    surfaces the error.

    The top-level `fallback_models` block is deliberately NOT part of this
    return value (its shape and fail-soft contract differ, and this mapping is
    a frozen consumers' contract). Read it with :func:`load_fallback_models`.
    """
    path = dispatch_config_path(project_root)
    if not path.exists():
        return {}, None
    import yaml  # PyYAML: implicit dep for target.yml (mw-dual-workspace D-010)

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return {}, f"dispatch.yml unreadable: {exc}"
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return {}, "dispatch.yml must be a mapping at top level"
    models = data.get("models", {})
    if not isinstance(models, dict):
        return {}, "dispatch.yml 'models' must be a mapping"
    cleaned: dict[str, str] = {}
    for role, value in models.items():
        if role not in DISPATCH_ROLES:
            return {}, f"dispatch.yml models has unknown role {role!r} (valid: {', '.join(DISPATCH_ROLES)})"
        if not isinstance(value, str) or not value.strip():
            return {}, f"dispatch.yml models.{role} must be a non-empty string"
        cleaned[role] = value.strip()
    return {"models": cleaned}, None


def read_window_model(project_root: pathlib.Path) -> str:
    """Last model recorded by a non-worker pi window (.mw/window-model,
    'prefix/model-id', last writer wins). '' when absent/unreadable."""
    try:
        first = window_model_path(project_root).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    return first[0].strip() if first else ""


def parse_model_value(value: str) -> tuple[str, str]:
    """'timi/glm-5.3' -> ('timi', 'glm-5.3'); 'glm-5.3' -> ('', 'glm-5.3')."""
    value = value.strip()
    if "/" not in value:
        return "", value
    prefix, _, model_id = value.partition("/")
    return prefix.strip(), model_id.strip()


def model_value_compatible(cli: str, value: str) -> bool:
    """Can `value` be applied to a queue entry with this cli?

    Bare ids are route-native (always compatible). Provider prefixes only
    apply to pi entries; *_cli prefixes only to their matching CLI. Unknown
    prefixes (e.g. a window-model recorded from an unmapped provider) are
    incompatible so resolution falls through to the next layer.
    """
    prefix, _model = parse_model_value(value)
    if not prefix:
        return True
    if prefix in MODEL_PREFIX_TO_PI_PROVIDER:
        return cli == "pi"
    if prefix in CLI_PREFIX_TO_CLI:
        return cli == CLI_PREFIX_TO_CLI[prefix]
    return False


def resolve_dispatch_model(
    *,
    cli: str,
    task_type: str,
    entry_model: str,
    config_models: dict,
    window_model: str,
) -> tuple[str, str]:
    """Resolve the model for one spawn: (value, source).

    Chain: task.md `model:` (explicit, returned as-is) > dispatch.yml role
    default > current window model > "" (per-cli hardcoded default).
    The implicit layers (config/window) skip values incompatible with the
    entry cli (see model_value_compatible); the explicit entry model is NOT
    filtered here — the launcher fails it loudly instead of silently
    re-routing (an explicit codex_cli/... on a pi task is a caller bug).
    """
    if entry_model.strip():
        return entry_model.strip(), "task"
    role = TASK_TYPE_TO_ROLE.get(task_type, "coding")
    candidate = config_models.get(role, "").strip()
    if candidate and model_value_compatible(cli, candidate):
        return candidate, f"config:{role}"
    if window_model.strip() and model_value_compatible(cli, window_model):
        return window_model.strip(), "window"
    return "", "default"


# ── Fallback model config (.mw/dispatch.yml top-level fallback_models) ────
#
# mw-model-error-perception D5/§3.3: per-task-type backup models the launcher
# injects into a worker (PI_WORKER_FALLBACK_MODELS) once its primary model is
# exhausted. The value lives in a TOP-LEVEL key rather than under `models:`
# because both readers (this module and TS shared/dispatch-models.ts)
# hard-validate `models.<role>` as a single-line string. Keys are the known
# worker task types (the `type:` values TASK_TYPE_TO_ROLE buckets); `main` is
# the PM window and has no worker fallback. Every list holds 1..4 `prefix/model`
# values (the same namespace as `models.<role>` and the `[MODEL_FALLBACK]`
# trace line), normalized to lowercase and de-duplicated. A missing key means
# "no fallback" — the worker behaves exactly as before.
FALLBACK_MAX_MODELS = 4
FALLBACK_TASK_TYPES = tuple(TASK_TYPE_TO_ROLE)

# Fallback prefix -> mw route name, for the doctor credential precheck. The pi
# provider ids (MODEL_PREFIX_TO_PI_PROVIDER: claude -> anthropic, ...) are NOT
# route_precheck keys; these are the providers.json / codex-native names the
# existing checker reports.
FALLBACK_PREFIX_TO_ROUTE: dict[str, str] = {
    "timi": "timi",
    "claude": "claude",
    "deepseek": "deepseek",
    "zai": "zai-coding-cn",
    "codex": "codex-native",
}

# Machine-readable error kind (style of _TARGET_KINDS): every
# validate_fallback_models / load_fallback_models error starts with this token
# so the launcher and doctor can branch on the kind instead of parsing prose.
FALLBACK_ERROR_KIND = "invalid-config"


def _fallback_error(message: str) -> tuple[dict[str, list[str]], str]:
    return {}, f"{FALLBACK_ERROR_KIND}: {message}"


def validate_fallback_models(raw: object) -> tuple[dict[str, list[str]], str | None]:
    """Pure validator for the top-level `fallback_models` value.

    Returns ``({task_type: [model, ...]}, None)`` or ``({}, message)`` where
    ``message`` starts with ``"invalid-config: "`` (machine-readable). A
    ``None`` value is not an error: absent/null means no fallback configured.
    """
    if raw is None:
        return {}, None
    if not isinstance(raw, dict):
        return _fallback_error(
            "dispatch.yml fallback_models must be a mapping of task type to model list"
        )
    cleaned: dict[str, list[str]] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            return _fallback_error(
                f"dispatch.yml fallback_models has a non-string task type {key!r}"
            )
        task_type = key.strip().lower()
        if task_type not in FALLBACK_TASK_TYPES:
            return _fallback_error(
                f"dispatch.yml fallback_models has unknown task type {key!r} "
                f"(valid: {', '.join(sorted(FALLBACK_TASK_TYPES))})"
            )
        if task_type in cleaned:
            return _fallback_error(
                f"dispatch.yml fallback_models has duplicate task type {key!r}"
            )
        if not isinstance(value, list):
            return _fallback_error(
                f"dispatch.yml fallback_models.{task_type} must be a list of "
                f"1..{FALLBACK_MAX_MODELS} 'prefix/model' strings"
            )
        if not 1 <= len(value) <= FALLBACK_MAX_MODELS:
            return _fallback_error(
                f"dispatch.yml fallback_models.{task_type} has {len(value)} entries "
                f"(must be 1..{FALLBACK_MAX_MODELS})"
            )
        normalized: list[str] = []
        seen: set[str] = set()
        for index, item in enumerate(value):
            where = f"dispatch.yml fallback_models.{task_type}[{index}]"
            if not isinstance(item, str) or not item.strip():
                return _fallback_error(f"{where} must be a non-empty 'prefix/model' string")
            if "\n" in item or "\r" in item:
                return _fallback_error(f"{where} must be a single line")
            prefix, model_id = parse_model_value(item)
            if not prefix or not model_id or "/" in model_id:
                return _fallback_error(
                    f"{where} must be 'prefix/model' (e.g. timi/glm-5.3), "
                    f"got {item.strip()!r}"
                )
            prefix = prefix.lower()
            if prefix in CLI_PREFIX_TO_CLI:
                return _fallback_error(
                    f"{where} uses the CLI transport prefix {prefix!r}; fallback "
                    "models must stay on the pi transport"
                )
            if prefix not in KNOWN_MODEL_PREFIXES:
                return _fallback_error(
                    f"{where} has unknown prefix {prefix!r} "
                    f"(valid: {', '.join(sorted(KNOWN_MODEL_PREFIXES))})"
                )
            # Case normalization + de-duplication (first occurrence wins).
            entry = f"{prefix}/{model_id.lower()}"
            if entry in seen:
                continue
            seen.add(entry)
            normalized.append(entry)
        if normalized:
            cleaned[task_type] = normalized
    return cleaned, None


def load_fallback_models(
    project_root: pathlib.Path,
) -> tuple[dict[str, list[str]], str | None]:
    """Read + validate the top-level `fallback_models` block of dispatch.yml.

    Same fail-soft contract as :func:`load_dispatch_config`: a missing file or
    absent key is ``({}, None)`` (no fallback), and any parse/validation
    problem is ``({}, "invalid-config: ...")`` that never blocks dispatching —
    doctor surfaces the error. The two keys are intentionally independent: a
    broken `models` block does not hide a usable `fallback_models` block (and
    vice versa).
    """
    path = dispatch_config_path(project_root)
    if not path.exists():
        return {}, None
    import yaml  # PyYAML: implicit dep for target.yml (mw-dual-workspace D-010)

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return {}, f"{FALLBACK_ERROR_KIND}: dispatch.yml unreadable: {exc}"
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return {}, f"{FALLBACK_ERROR_KIND}: dispatch.yml must be a mapping at top level"
    return validate_fallback_models(data.get("fallback_models"))


def fallback_models_for_task_type(fallbacks: dict, task_type: str) -> list[str]:
    """Backup models for one task: the exact `type:` key wins, else its role
    bucket (mirror of resolve_dispatch_model's TASK_TYPE_TO_ROLE bucketing).
    Unset -> [] (no fallback; behaviour is unchanged)."""
    task_type = (task_type or "").strip().lower()
    if task_type in fallbacks:
        return list(fallbacks[task_type])
    role = TASK_TYPE_TO_ROLE.get(task_type, "coding")
    return list(fallbacks.get(role, []))


# ── task.md header parsing (AC-005 single source) ──────────────────────────
#
# Mirror of the TS single source `shared/task-frontmatter.ts` (DRQ-3 / AC-005):
# the worker role is the FIRST `type:` of the header region, a BOM is stripped
# first, and nothing below the header may flip it. launcher.py / mw.py read the
# role from here; test_task_type_parity.py diffs this module against the real
# TS module through node on the golden fixture and the whole task.md corpus, so
# the two sides cannot drift silently.
#
# Boundary (TS parity, byte for byte):
#   1. strip a leading U+FEFF (Python str.strip() does not eat it;
#      launcher.py's old `^type:` regex therefore missed 7 historical books)
#      and report it;
#   2. fold \r\n/\r/U+2028/U+2029 to "\n" (T-19/C-15+C-16), drop one trailing empty, per-line trim;
#   3. first line `---` -> first later `---` (unclosed falls through); else the
#      first blank line; else the leading key/list-grammar run (truncated).

# ECMAScript String.prototype.trim() whitespace + line terminators. Python's
# str.strip() covers most of this but misses U+FEFF (which JS trims) and strips
# \x1c-\x1f / \x85 (which JS does not); the explicit set keeps both sides
# equal on hostile input.
_JS_TRIM_CHARS = (
    "\t\n\v\f\r \u00a0\ufeff\u2028\u2029"
    "\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u202f\u205f\u3000"
)

_HEADER_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*:")
_HEADER_LIST_ITEM_RE = re.compile(r"^-\s")
_TYPE_PREFIX = "type:"


class TaskHeaderRegion(NamedTuple):
    """Header line bounds (0-based, inclusive; start > end = no header).

    `fenced` = the first line opened a `---` block that closed; `truncated` =
    the region was cut by the header key grammar (no fence, no blank line);
    `byte_order_mark` = the raw text began with U+FEFF (stripped before
    parsing)."""

    start_line: int
    end_line: int
    fenced: bool
    truncated: bool
    byte_order_mark: bool


class TaskTypeReading(NamedTuple):
    """`type:` value with provenance (mirror of TS `TaskTypeReading`).

    `source` is one of `header` (value present), `invalid` (header line present
    but empty), `body` (only the body carries `type:`; value deliberately not
    returned), `missing` (neither). `bom_stripped` = the input began with a BOM."""

    type: str | None
    source: str
    bom_stripped: bool


def _split_task_lines(text: str) -> tuple[list[str], bool]:
    """Trimmed lines in ONE `\n` index space + BOM flag (mirror of TS
    `splitTaskLines`: CRLF/CR/U+2028/U+2029 fold to `\n`, trailing empty dropped)."""
    bom = text.startswith("\ufeff")
    lines = re.split(r"\r\n|[\r\n\u2028\u2029]", text[1:] if bom else text)
    if len(lines) > 1 and lines[-1] == "":
        lines.pop()
    return [line.strip(_JS_TRIM_CHARS) for line in lines], bom


def _region_from_lines(lines: list[str], bom: bool) -> TaskHeaderRegion:
    if lines[0] == "---":
        try:
            close = lines.index("---", 1)
        except ValueError:
            close = -1
        if close > 0:
            return TaskHeaderRegion(1, close - 1, True, False, bom)
    try:
        blank = lines.index("")
    except ValueError:
        blank = -1
    if blank >= 0:
        return TaskHeaderRegion(0, blank - 1, False, False, bom)
    end = 0
    while end < len(lines) and (_HEADER_KEY_RE.match(lines[end]) or _HEADER_LIST_ITEM_RE.match(lines[end])):
        end += 1
    return TaskHeaderRegion(0, end - 1, False, True, bom)


def read_task_header_region(text: str) -> tuple[list[str], TaskHeaderRegion]:
    """(trimmed lines, header region) for one task.md document."""
    lines, bom = _split_task_lines(text)
    return lines, _region_from_lines(lines, bom)


def read_task_header_scalar(text: str, key: str) -> str | None:
    """First `key:` value inside the header region (`""` present-but-empty,
    `None` absent); keys below the header boundary are never read."""
    lines, region = read_task_header_region(text)
    prefix = f"{key}:"
    for i in range(region.start_line, region.end_line + 1):
        line = lines[i]
        if line.startswith(prefix) and _HEADER_KEY_RE.match(line):
            return line[len(prefix):].strip(_JS_TRIM_CHARS)
    return None


def _body_type_lines(lines: list[str], region: TaskHeaderRegion) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for i in range(region.end_line + 1, len(lines)):
        line = lines[i]
        if line.startswith(_TYPE_PREFIX) and _HEADER_KEY_RE.match(line):
            out.append((i + 1, line[len(_TYPE_PREFIX):].strip(_JS_TRIM_CHARS)))
    return out


def read_task_type(text: str) -> TaskTypeReading:
    """Single-source `type:` reading (header first value wins, BOM stripped)."""
    lines, bom = _split_task_lines(text)
    region = _region_from_lines(lines, bom)
    for i in range(region.start_line, region.end_line + 1):
        line = lines[i]
        if line.startswith(_TYPE_PREFIX) and _HEADER_KEY_RE.match(line):
            value = line[len(_TYPE_PREFIX):].strip(_JS_TRIM_CHARS)
            if value == "":
                return TaskTypeReading(None, "invalid", bom)
            return TaskTypeReading(value, "header", bom)
    has_body_type = bool(_body_type_lines(lines, region))
    return TaskTypeReading(None, "body" if has_body_type else "missing", bom)


def scan_body_type_lines(text: str) -> list[tuple[int, str]]:
    """Every `type:` line below the header region, (1-based line, value)."""
    lines, region = read_task_header_region(text)
    return _body_type_lines(lines, region)


# ── RAG server config (.mw/rag-servers.yml + ~/.agents/rag-servers.yml) ────
#
# Two-layer server table (design D-003, T-06): a machine-level file shared
# across projects plus a project-level override, joined **field by field** —
# scalars and nested objects merge key by key (project wins per key), array
# fields (`sources`) are replaced wholesale, and `null` deletes a field.
# `origin` records `machine`/`project` per evaluated field path. `enabled` /
# `default_server` / `roles` / `phases` / `budgets` come from target.yml's
# `rag:` section. Validation problems are returned as an error string (never
# raised): RAG config is a convenience and must never block dispatching, the
# same contract as load_dispatch_config.
#
# YAML keys are snake_case; the TS reader (rag/config.ts, T-01) maps the
# table below to camelCase. Both sides assert RAG_FIELD_CAMEL so the two
# readings cannot drift.

RAG_MARKER_V1 = "<!-- mw-rag: v1 -->"
RAG_ADAPTER_DEFAULT = "overcode-v1"
RAG_TRANSPORT_VALUES = ("mcp", "skill", "both")
RAG_DEFAULT_MCP_TIMEOUT_MS = 180000
RAG_DEFAULT_SKILL_TIMEOUT_MS = 180000
RAG_DEFAULT_CHAT_BUDGET = 2
RAG_DEFAULT_TIME_BUDGET_S = 900
RAG_CITATION_SYNTAX = "<server>:<source>:<file_path>:<line>"
# Roles whose default `rewrite` is on when the server declares the capability
# (design D-004: spec/design/research class).
RAG_RESEARCH_ROLES = frozenset(("spec", "design", "research", "rag-research"))
# Phases whose default `rewrite` is on under the same rule (AC-006 "research
# roles/phases"); mirrors `isResearchPhase` in rag/adapter.ts so both sides
# resolve the same (server, source, rewrite) triple (T-19 / VC-111).
RAG_RESEARCH_PHASES = frozenset(("spec", "design"))

# YAML (snake_case) -> TS runtime (camelCase) field mapping (T-01 parity guard).
RAG_FIELD_CAMEL: dict[str, str] = {
    "token_env": "tokenEnv",
    "timeout_ms": "timeoutMs",
    "cli_entry": "cliEntry",
    "path_roots_file": "pathRootsFile",
    "default_server": "defaultServer",
    "chat_budget": "chatBudget",
    "time_budget_s": "timeBudgetS",
}

_RAG_LAYER_TOP_KEYS = ("servers",)
_RAG_SERVER_FIELDS = (
    "transport", "adapter", "path_roots_file", "sources", "capabilities", "mcp", "skill",
)
_RAG_NESTED_FIELDS: dict[str, tuple[str, ...]] = {
    "mcp": ("url", "token_env", "timeout_ms"),
    "skill": ("dir", "cli_entry", "timeout_ms"),
    "capabilities": ("graph", "chat", "rewrite"),
}
_RAG_TARGET_KEYS = ("enabled", "default_server", "roles", "phases", "budgets")
_RAG_ROLE_KEYS = ("server", "source", "require", "rewrite", "chat_budget", "time_budget_s")
_RAG_PHASE_KEYS = ("server", "source", "require", "rewrite")
_RAG_BUDGET_KEYS = ("chat_budget", "time_budget_s")
RAG_ENV_FILE = "MW_RAG_SERVERS_FILE"
RAG_ENV_HOME = "MW_RAG_SERVERS_HOME"
_MISSING = object()


def rag_servers_path(project_root: pathlib.Path | str) -> pathlib.Path:
    """Project-level RAG server table: <root>/.mw/rag-servers.yml."""
    return pathlib.Path(project_root) / ".mw" / "rag-servers.yml"


def machine_rag_servers_path(env: Mapping[str, str] | None = None) -> pathlib.Path | None:
    """Machine-level RAG server table (design D-013, cross-platform).

    Order: MW_RAG_SERVERS_FILE (whole-file override / test hook) ->
    MW_RAG_SERVERS_HOME + /.agents/rag-servers.yml -> $HOME -> $USERPROFILE.
    A candidate that does not exist yields None (that layer is empty); the
    directory is never created.
    """
    env = os.environ if env is None else env
    override = (env.get(RAG_ENV_FILE) or "").strip()
    if override:
        path = pathlib.Path(override)
        return path if path.exists() else None
    for var in (RAG_ENV_HOME, "HOME", "USERPROFILE"):
        home = (env.get(var) or "").strip()
        if not home:
            continue
        path = pathlib.Path(home) / ".agents" / "rag-servers.yml"
        if path.exists():
            return path
    return None


def _rag_validate_layer_entry(name: str, raw: object, label: str) -> str | None:
    if not isinstance(raw, dict):
        return f"{label}: server '{name}' must be a mapping"
    extra = [str(k) for k in raw if k not in _RAG_SERVER_FIELDS]
    if extra:
        return (
            f"{label}: server '{name}' has unknown key(s) {', '.join(extra)} "
            f"(valid: {', '.join(_RAG_SERVER_FIELDS)})"
        )
    for block, allowed in _RAG_NESTED_FIELDS.items():
        value = raw.get(block)
        if value is None:
            continue
        if not isinstance(value, dict):
            return f"{label}: server '{name}'.{block} must be a mapping"
        bad = [str(k) for k in value if k not in allowed]
        if bad:
            return (
                f"{label}: server '{name}'.{block} has unknown key(s) {', '.join(bad)} "
                f"(valid: {', '.join(allowed)})"
            )
    return None


def _rag_layer_servers(path: pathlib.Path, label: str) -> tuple[dict, str | None]:
    """Load one rag-servers.yml layer -> ({server: raw}, error)."""
    import yaml  # PyYAML: implicit dep for target.yml (mw-dual-workspace D-010)

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return {}, f"{label} unreadable: {exc}"
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return {}, f"{label} must be a mapping at top level"
    extra = [str(k) for k in data if k not in _RAG_LAYER_TOP_KEYS]
    if extra:
        return {}, f"{label}: unknown key(s) {', '.join(extra)} (valid: servers)"
    servers = data.get("servers") or {}
    if not isinstance(servers, dict):
        return {}, f"{label}: 'servers' must be a mapping of server name to entry"
    out: dict = {}
    for name, raw in servers.items():
        if not isinstance(name, str) or not name.strip():
            return {}, f"{label}: server names must be non-empty strings"
        error = _rag_validate_layer_entry(name, raw, label)
        if error:
            return {}, error
        out[name] = raw or {}
    return out, None


def _rag_target_section(project_root: pathlib.Path) -> tuple[dict, str | None]:
    """target.yml's `rag:` section -> (section, error); missing = empty."""
    path = target_yml_path(project_root)
    if not path.exists():
        return {}, None
    import yaml  # PyYAML: implicit dep for target.yml (mw-dual-workspace D-010)

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return {}, f"target.yml unreadable: {exc}"
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return {}, "target.yml must be a mapping at top level"
    section = data.get("rag")
    if section is None:
        return {}, None
    if not isinstance(section, dict):
        return {}, "target.yml 'rag' must be a mapping"
    extra = [str(k) for k in section if k not in _RAG_TARGET_KEYS]
    if extra:
        return {}, (
            f"target.yml rag: unknown key(s) {', '.join(extra)} "
            f"(valid: {', '.join(_RAG_TARGET_KEYS)})"
        )
    return section, None


def _rag_merge_server(name: str, machine_raw: dict, project_raw: dict) -> tuple[dict, dict]:
    """Per-field merge of one server (design D-003). Verified by VC-024."""
    origins: dict[str, str] = {}
    merged: dict = {}
    for field in _RAG_SERVER_FIELDS:
        in_machine = field in machine_raw
        in_project = field in project_raw
        if not in_machine and not in_project:
            continue
        machine_value = machine_raw.get(field) if in_machine else _MISSING
        project_value = project_raw.get(field) if in_project else _MISSING
        if in_project and project_value is None:
            merged[field] = None  # explicit delete
            origins[field] = "project"
            continue
        if in_machine and machine_value is None and not in_project:
            continue  # a machine-level null deletes nothing
        if field in _RAG_NESTED_FIELDS:
            nested: dict = {}
            if in_machine and machine_value is not _MISSING and machine_value is not None:
                nested.update(machine_value)
                for key in machine_value:
                    origins[f"{field}.{key}"] = "machine"
            if in_project and isinstance(project_value, dict):
                for key, value in project_value.items():
                    if value is None:
                        nested.pop(key, None)
                    else:
                        nested[key] = value
                    origins[f"{field}.{key}"] = "project"
            merged[field] = nested if nested else None
            continue
        if in_project:
            merged[field] = project_value
            origins[field] = "project"
        else:
            merged[field] = machine_value
            origins[field] = "machine"
    return merged, origins


def _rag_finalize_mcp(name: str, raw: object, transport: str) -> tuple[dict | None, str | None]:
    if raw is None:
        if transport in ("mcp", "both"):
            return None, f"rag server '{name}': transport '{transport}' requires mcp.url"
        return None, None
    if not isinstance(raw, dict):
        return None, f"rag server '{name}': mcp must be a mapping"
    url = raw.get("url")
    if not isinstance(url, str) or not url.strip():
        return None, f"rag server '{name}': mcp.url must be a non-empty string"
    token_env = raw.get("token_env")
    if token_env is not None and (not isinstance(token_env, str) or not token_env.strip()):
        return None, f"rag server '{name}': mcp.token_env must be a non-empty string or null"
    timeout = raw.get("timeout_ms", RAG_DEFAULT_MCP_TIMEOUT_MS)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
        return None, f"rag server '{name}': mcp.timeout_ms must be a positive integer"
    return {
        "url": url.strip(),
        "token_env": token_env.strip() if isinstance(token_env, str) else None,
        "timeout_ms": timeout,
    }, None


def _rag_finalize_skill(name: str, raw: object, transport: str) -> tuple[dict | None, str | None]:
    if raw is None:
        if transport in ("skill", "both"):
            return None, f"rag server '{name}': transport '{transport}' requires skill.cli_entry"
        return None, None
    if not isinstance(raw, dict):
        return None, f"rag server '{name}': skill must be a mapping"
    cli_entry = raw.get("cli_entry")
    if not isinstance(cli_entry, str) or not cli_entry.strip():
        return None, f"rag server '{name}': skill.cli_entry must be a non-empty string"
    directory = raw.get("dir")
    if directory is not None and (not isinstance(directory, str) or not directory.strip()):
        return None, f"rag server '{name}': skill.dir must be a non-empty string or null"
    timeout = raw.get("timeout_ms", RAG_DEFAULT_SKILL_TIMEOUT_MS)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
        return None, f"rag server '{name}': skill.timeout_ms must be a positive integer"
    return {
        "dir": directory.strip() if isinstance(directory, str) else None,
        "cli_entry": cli_entry.strip(),
        "timeout_ms": timeout,
    }, None


def _rag_finalize_capabilities(name: str, raw: object) -> tuple[dict, str | None]:
    caps = {"graph": False, "chat": False, "rewrite": False}
    if isinstance(raw, dict):
        for key in ("graph", "chat", "rewrite"):
            if key in raw:
                value = raw[key]
                if not isinstance(value, bool):
                    return caps, f"rag server '{name}': capabilities.{key} must be a boolean"
                caps[key] = value
    return caps, None


def _rag_path_roots_digest(project_root: pathlib.Path, value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = pathlib.Path(value)
    if not path.is_absolute():
        path = project_root / value
    try:
        if not path.is_file():
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _rag_finalize_server(
    name: str, merged: dict, origins: dict, project_root: pathlib.Path
) -> tuple[dict | None, str | None]:
    transport = merged.get("transport")
    if transport is None:
        transport = "mcp"
    if not isinstance(transport, str) or transport not in RAG_TRANSPORT_VALUES:
        return None, (
            f"rag server '{name}': transport must be one of {', '.join(RAG_TRANSPORT_VALUES)}"
        )
    adapter = merged.get("adapter")
    if adapter is None:
        adapter = RAG_ADAPTER_DEFAULT
    if adapter != RAG_ADAPTER_DEFAULT:
        return None, f"rag server '{name}': adapter must be '{RAG_ADAPTER_DEFAULT}'"
    path_roots_file = merged.get("path_roots_file")
    if path_roots_file is not None and (
        not isinstance(path_roots_file, str) or not path_roots_file.strip()
    ):
        return None, f"rag server '{name}': path_roots_file must be a non-empty string or null"
    sources = merged.get("sources")
    if sources is None:
        sources = []
    if not isinstance(sources, list) or any(
        not isinstance(item, str) or not item.strip() for item in sources
    ):
        return None, f"rag server '{name}': sources must be a list of non-empty strings"
    mcp, error = _rag_finalize_mcp(name, merged.get("mcp"), transport)
    if error:
        return None, error
    skill, error = _rag_finalize_skill(name, merged.get("skill"), transport)
    if error:
        return None, error
    capabilities, error = _rag_finalize_capabilities(name, merged.get("capabilities"))
    if error:
        return None, error
    return {
        "transport": transport,
        "adapter": adapter,
        "path_roots_file": path_roots_file.strip() if isinstance(path_roots_file, str) else None,
        "path_roots_digest": _rag_path_roots_digest(project_root, path_roots_file),
        "sources": list(sources),
        "capabilities": capabilities,
        "mcp": mcp,
        "skill": skill,
        "origin": origins,
    }, None


def _rag_visible(servers: dict) -> str:
    return ", ".join(sorted(servers)) if servers else "none"


def _rag_finalize_specs(
    label: str, raw: object, servers: dict, allowed: tuple[str, ...]
) -> tuple[dict | None, str | None]:
    if raw is None:
        return {}, None
    if not isinstance(raw, dict):
        return None, f"target.yml rag.{label} must be a mapping"
    out: dict = {}
    for name, spec in raw.items():
        if not isinstance(name, str) or not name.strip():
            return None, f"target.yml rag.{label} keys must be non-empty strings"
        if spec is None:
            spec = {}
        if not isinstance(spec, dict):
            return None, f"target.yml rag.{label}.{name} must be a mapping"
        extra = [str(k) for k in spec if k not in allowed]
        if extra:
            return None, (
                f"target.yml rag.{label}.{name} has unknown key(s) {', '.join(extra)} "
                f"(valid: {', '.join(allowed)})"
            )
        cleaned: dict = {}
        server = spec.get("server")
        if server is not None:
            if not isinstance(server, str) or not server.strip():
                return None, f"target.yml rag.{label}.{name}.server must be a non-empty string"
            if server not in servers:
                return None, (
                    f"unknown rag server '{server}' in rag.{label}.{name}.server "
                    f"(available: {_rag_visible(servers)})"
                )
            cleaned["server"] = server
        source = spec.get("source")
        if source is not None:
            if not isinstance(source, str) or not source.strip():
                return None, f"target.yml rag.{label}.{name}.source must be a non-empty string"
            cleaned["source"] = source
        for flag in ("require", "rewrite"):
            if flag in spec:
                value = spec[flag]
                if not isinstance(value, bool):
                    return None, f"target.yml rag.{label}.{name}.{flag} must be a boolean"
                cleaned[flag] = value
        for numkey in ("chat_budget", "time_budget_s"):
            if numkey in spec:
                value = spec[numkey]
                if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                    return None, (
                        f"target.yml rag.{label}.{name}.{numkey} must be a positive integer"
                    )
                cleaned[numkey] = value
        out[name] = cleaned
    return out, None


def _rag_finalize_budgets(raw: object) -> tuple[dict | None, str | None]:
    budgets = {
        "chat_budget": RAG_DEFAULT_CHAT_BUDGET,
        "time_budget_s": RAG_DEFAULT_TIME_BUDGET_S,
    }
    if raw is None:
        return budgets, None
    if not isinstance(raw, dict):
        return None, "target.yml rag.budgets must be a mapping"
    extra = [str(k) for k in raw if k not in _RAG_BUDGET_KEYS]
    if extra:
        return None, (
            f"target.yml rag.budgets has unknown key(s) {', '.join(extra)} "
            f"(valid: {', '.join(_RAG_BUDGET_KEYS)})"
        )
    for key in _RAG_BUDGET_KEYS:
        if key in raw:
            value = raw[key]
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                return None, f"target.yml rag.budgets.{key} must be a positive integer"
            budgets[key] = value
    return budgets, None


def _rag_finalize_target(section: dict, servers: dict) -> tuple[dict | None, str | None]:
    enabled_raw = section.get("enabled")
    if enabled_raw is None:
        enabled: list[str] = []
    elif isinstance(enabled_raw, list):
        enabled = []
        for item in enabled_raw:
            if not isinstance(item, str) or not item.strip():
                return None, "target.yml rag.enabled must be a list of non-empty server names"
            if item not in servers:
                return None, (
                    f"unknown rag server '{item}' in rag.enabled "
                    f"(available: {_rag_visible(servers)})"
                )
            enabled.append(item)
    else:
        return None, "target.yml rag.enabled must be a list of server names"
    default_server = section.get("default_server")
    if default_server is not None:
        if not isinstance(default_server, str) or not default_server.strip():
            return None, "target.yml rag.default_server must be a non-empty string"
        if default_server not in servers:
            return None, (
                f"unknown rag server '{default_server}' in rag.default_server "
                f"(available: {_rag_visible(servers)})"
            )
    roles, error = _rag_finalize_specs("roles", section.get("roles"), servers, _RAG_ROLE_KEYS)
    if error:
        return None, error
    phases, error = _rag_finalize_specs("phases", section.get("phases"), servers, _RAG_PHASE_KEYS)
    if error:
        return None, error
    budgets, error = _rag_finalize_budgets(section.get("budgets"))
    if error:
        return None, error
    return {
        "enabled": enabled,
        "default_server": default_server,
        "roles": roles,
        "phases": phases,
        "budgets": budgets,
    }, None


def load_rag_config(project_root: pathlib.Path | str) -> tuple[dict, str | None]:
    """Load the merged RAG config -> (config, error).

    config is {enabled, default_server, servers, roles, phases, budgets,
    fingerprint}; a missing machine/project layer is an empty layer and a
    missing `rag:` section means nothing is enabled. Any parse or validation
    problem returns ({}, message) and never blocks dispatching.
    """
    root = pathlib.Path(project_root)
    machine_path = machine_rag_servers_path()
    machine_servers: dict = {}
    if machine_path is not None:
        machine_servers, error = _rag_layer_servers(machine_path, "machine rag-servers.yml")
        if error:
            return {}, error
    project_servers: dict = {}
    project_path = rag_servers_path(root)
    if project_path.exists():
        project_servers, error = _rag_layer_servers(project_path, "project rag-servers.yml")
        if error:
            return {}, error
    section, error = _rag_target_section(root)
    if error:
        return {}, error
    servers: dict = {}
    for name in sorted(set(machine_servers) | set(project_servers)):
        merged, origins = _rag_merge_server(
            name, machine_servers.get(name, {}), project_servers.get(name, {})
        )
        entry, error = _rag_finalize_server(name, merged, origins, root)
        if error:
            return {}, error
        servers[name] = entry
    target, error = _rag_finalize_target(section, servers)
    if error:
        return {}, error
    config = {
        "enabled": target["enabled"],
        "default_server": target["default_server"],
        "servers": servers,
        "roles": target["roles"],
        "phases": target["phases"],
        "budgets": target["budgets"],
    }
    config["fingerprint"] = rag_fingerprint(config)
    return config, None


def rag_token_env_names(config: dict) -> set[str]:
    """Every declared `mcp.token_env` NAME (never its value).

    Used by the launcher to strip all declared RAG token envs from a worker
    env and to inject only the ones the enabled servers need (T-07, VC-013).
    """
    names: set[str] = set()
    for entry in (config.get("servers") or {}).values():
        if not isinstance(entry, dict):
            continue
        mcp = entry.get("mcp")
        if not isinstance(mcp, dict):
            continue
        name = mcp.get("token_env")
        if isinstance(name, str) and name.strip():
            names.add(name.strip())
    return names


def _rag_role_spec(config: dict, role: str) -> dict:
    spec = (config.get("roles") or {}).get(role)
    return spec if isinstance(spec, dict) else {}


def _rag_phase_spec(config: dict, phase: str) -> dict:
    spec = (config.get("phases") or {}).get(phase)
    return spec if isinstance(spec, dict) else {}


def _rag_required_for(config: dict, role: str, phase: str) -> bool:
    """required = role.require OR phase.require (union, no exception)."""
    return bool(_rag_role_spec(config, role).get("require")) or bool(
        _rag_phase_spec(config, phase).get("require")
    )


def _rag_resolve_defaults(config: dict, role: str, phase: str) -> tuple[str | None, str | None, bool]:
    """Resolve (server, source, rewrite): role > phase > default_server."""
    role_spec = _rag_role_spec(config, role)
    phase_spec = _rag_phase_spec(config, phase)
    server = role_spec.get("server") or phase_spec.get("server") or config.get("default_server")
    source = role_spec.get("source")
    if source is None:
        source = phase_spec.get("source")
    rewrite = role_spec.get("rewrite")
    if rewrite is None:
        rewrite = phase_spec.get("rewrite")
    if rewrite is None:
        entry = (config.get("servers") or {}).get(server or "")
        caps = (entry or {}).get("capabilities") if isinstance(entry, dict) else None
        rewrite = bool((caps or {}).get("rewrite")) and (
            role in RAG_RESEARCH_ROLES or phase in RAG_RESEARCH_PHASES
        )
    return server, source, bool(rewrite)


def _rag_budget(config: dict, role: str, task_meta: dict, key: str, fallback: int) -> int:
    """task.md header > role spec > rag.budgets > built-in default."""
    explicit = task_meta.get(key)
    if isinstance(explicit, int) and not isinstance(explicit, bool) and explicit > 0:
        return explicit
    role_value = _rag_role_spec(config, role).get(key)
    if isinstance(role_value, int) and not isinstance(role_value, bool) and role_value > 0:
        return role_value
    global_value = (config.get("budgets") or {}).get(key)
    if isinstance(global_value, int) and not isinstance(global_value, bool) and global_value > 0:
        return global_value
    return fallback


def render_rag_block(config: dict, task_meta: dict) -> str | None:
    """Render the task.md `<!-- mw-rag: v1 -->` block (design D-009).

    Returns None (writing not one byte) when `enabled` is empty — the
    structural zero-impact guarantee (D-014/AC-001). The render is a pure
    function of the config and task_meta; the TS renderRagBlock (T-04) emits
    the byte-identical text.
    """
    enabled = [
        name for name in (config.get("enabled") or [])
        if isinstance(name, str) and name.strip()
    ]
    if not enabled:
        return None
    if not isinstance(task_meta, dict):
        task_meta = {}
    task_type = str(task_meta.get("type") or "")
    # Unknown/absent `type:` falls back to coding (T-16 / D-105), the same rule
    # `roleForTaskType` uses on the TS side.
    role = str(task_meta.get("role") or TASK_TYPE_TO_ROLE.get(task_type, "coding"))
    phase = str(task_meta.get("phase") or "")
    server, source, rewrite = _rag_resolve_defaults(config, role, phase)
    lines = [
        RAG_MARKER_V1,
        f"[mw] RAG enabled: {', '.join(enabled)}",
    ]
    required_roles = sorted(
        name for name, spec in (config.get("roles") or {}).items()
        if isinstance(spec, dict) and spec.get("require")
    )
    if required_roles:
        lines.append(f"[mw] Required roles: {', '.join(required_roles)}")
    required_phases = sorted(
        name for name, spec in (config.get("phases") or {}).items()
        if isinstance(spec, dict) and spec.get("require")
    )
    if required_phases:
        lines.append(f"[mw] Required phases: {', '.join(required_phases)}")
    lines.append(f"[mw] Default server: {server or 'none'}")
    lines.append(f"[mw] Default source: {source or 'none'}")
    lines.append(f"[mw] Rewrite: {'true' if rewrite else 'false'}")
    lines.append(
        f"[mw] Chat budget: {_rag_budget(config, role, task_meta, 'chat_budget', RAG_DEFAULT_CHAT_BUDGET)}"
    )
    lines.append(
        f"[mw] Time budget: {_rag_budget(config, role, task_meta, 'time_budget_s', RAG_DEFAULT_TIME_BUDGET_S)}s"
    )
    lines.append(f"[mw] Citation syntax: {RAG_CITATION_SYNTAX}")
    lines.append(f"fingerprint={config.get('fingerprint') or rag_fingerprint(config, enabled)}")
    return "\n".join(lines)


def _rag_canonical(value: object) -> object:
    """Canonical JSON shape: sorted keys, no whitespace, ensure_ascii=False,
    integral floats normalized to int (TS/Py canonical-JSON parity)."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    if isinstance(value, dict):
        return {str(key): _rag_canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_rag_canonical(item) for item in value]
    return str(value)


def rag_fingerprint(config: dict, enabled: list[str] | None = None) -> str:
    """sha256 over the canonical static config (design D-009).

    Scope: the enabled servers' static fields + resolved path_roots file
    content digest + roles/phases + budgets. Excluded: probe/health state,
    session ids, capability corrections, and every field of a server that is
    not enabled, so an unrelated edit never fakes a config tear (VC-022).
    """
    names = list(config.get("enabled") or []) if enabled is None else list(enabled)
    servers = config.get("servers") or {}
    entries = []
    for name in sorted({str(item) for item in names}):
        entry = servers.get(name)
        if not isinstance(entry, dict):
            continue
        mcp = entry.get("mcp")
        skill = entry.get("skill")
        entries.append(_rag_canonical({
            "name": name,
            "transport": entry.get("transport"),
            "adapter": entry.get("adapter"),
            "mcp": None if not isinstance(mcp, dict) else {
                "url": mcp.get("url"),
                "token_env": mcp.get("token_env"),
                "timeout_ms": mcp.get("timeout_ms"),
            },
            "skill": None if not isinstance(skill, dict) else {
                "dir": skill.get("dir"),
                "cli_entry": skill.get("cli_entry"),
                "timeout_ms": skill.get("timeout_ms"),
            },
            "path_roots_file": entry.get("path_roots_file"),
            "path_roots_digest": entry.get("path_roots_digest"),
            "sources": list(entry.get("sources") or []),
            "capabilities": entry.get("capabilities") or {},
        }))
    payload = _rag_canonical({
        "enabled": sorted({str(item) for item in names}),
        "servers": entries,
        "default_server": config.get("default_server"),
        "roles": config.get("roles") or {},
        "phases": config.get("phases") or {},
        "budgets": config.get("budgets") or {},
    })
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# 鈹€鈹€ Credential resolution 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def _dig(data: object, dotted: str) -> object:
    """Follow a dotted path through nested dicts. Returns None on any miss."""
    cur: object = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _read_credential_file(raw_path: str, fmt: str, field: str) -> str | None:
    path = pathlib.Path(os.path.expanduser(raw_path))
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if fmt == "toml":
        if tomllib is None:
            return None
        try:
            data = tomllib.loads(text)
        except Exception:
            return None
        value = _dig(data, field) if field else data
        return value if isinstance(value, str) and value else None
    if fmt == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        value = _dig(data, field) if field else data
        return value if isinstance(value, str) and value else None
    # plain: whole trimmed file content
    return text.strip() or None


def resolve_credential(
    cred_cfg: dict | None,
    env: Mapping[str, str] | None = None,
) -> tuple[str | None, dict]:
    """Resolve a credential through its source chain (env -> file fallback).

    Returns (value, source) where source describes the winning source as
    {"kind": "env"|"file", ...} for precheck/doctor reporting, or {} when the
    credential could not be resolved.
    """
    if env is None:
        env = os.environ
    if not isinstance(cred_cfg, dict):
        return None, {}
    for src in cred_cfg.get("sources", []):
        if not isinstance(src, dict):
            continue
        env_name = src.get("env")
        if env_name:
            value = env.get(env_name)
            if value:
                return value, {"kind": "env", "name": env_name}
        file_path = src.get("file")
        if file_path:
            value = _read_credential_file(file_path, src.get("format", "plain"), src.get("field", ""))
            if value:
                return value, {
                    "kind": "file",
                    "path": file_path,
                    "field": src.get("field", ""),
                }
    return None, {}


def credential_env_names(config: dict) -> set[str]:
    """All env var names declared anywhere in the credential chains.

    Callers use this to derive the strip set for worker envs (AC-024/AC-025
    isolation semantics preserved).
    """
    names: set[str] = set()
    for cred in config.get("credentials", {}).values():
        if not isinstance(cred, dict):
            continue
        for src in cred.get("sources", []):
            if isinstance(src, dict) and src.get("env"):
                names.add(str(src["env"]))
    return names


def credential_inject_env(cred_cfg: dict | None) -> str | None:
    """The env var name a resolved credential is injected under in worker envs.

    Defaults to the first declared env source (the historical api_key_env).
    """
    if not isinstance(cred_cfg, dict):
        return None
    for src in cred_cfg.get("sources", []):
        if isinstance(src, dict) and src.get("env"):
            return str(src["env"])
    return None


def describe_missing(cred_cfg: dict | None) -> str:
    """Human-readable list of every source that failed, for logs/doctor."""
    if not isinstance(cred_cfg, dict) or not cred_cfg.get("sources"):
        return "no credential sources declared"
    parts: list[str] = []
    for src in cred_cfg.get("sources", []):
        if not isinstance(src, dict):
            continue
        if src.get("env"):
            parts.append(f"env {src['env']} unset")
        if src.get("file"):
            parts.append(f"file {src['file']} unreadable")
    return "; ".join(parts) if parts else "no credential sources declared"


# --- Protected agent config (cross-window files) ----------------------------
#
# Incident 2026-09-15: a running pi session cleared ~/.pi/agent/auth.json
# while other windows were live; every window lost its credentials
# ("Provider is not configured: timi") and several hung. These files are
# live config shared by ALL pi sessions, so framework code must never write
# them. Credential/model/settings changes belong to the user, outside pi
# (plain terminal, or `pi /login` which is a core flow, not the tool layer).
# The agent-side hard block lives in the agent-team-loop extension
# (shared/protected-config.ts); this is the Python-side mirror for any
# future framework write path.

#: Protected file names inside the pi agent config dir (oauth.json is the
#: legacy pre-migration credential store, same blast radius).
PROTECTED_AGENT_CONFIG_FILES: tuple[str, ...] = (
    "auth.json",
    "models.json",
    "settings.json",
    "oauth.json",
)

#: Mirrors ENV_AGENT_DIR in coding-agent src/config.ts (getAgentDir()).
AGENT_DIR_ENV = "PI_CODING_AGENT_DIR"


def agent_config_dir(env: Mapping[str, str] | None = None) -> pathlib.Path:
    """The effective pi agent config dir: the AGENT_DIR_ENV override
    (tilde-expanded) else ~/.pi/agent. Mirrors core getAgentDir(); env is
    injectable for tests (defaults to os.environ)."""
    if env is None:
        env = os.environ
    raw = env.get(AGENT_DIR_ENV, "")
    if raw:
        return pathlib.Path(os.path.expanduser(raw))
    return pathlib.Path.home() / ".pi" / "agent"


def is_protected_agent_config(path: str | os.PathLike[str], env: Mapping[str, str] | None = None) -> bool:
    """True when `path` targets a protected file (or an agent dir itself).

    Checked against BOTH the effective agent dir and the default ~/.pi/agent
    (defense-in-depth, matching the TS guard): an env override in the calling
    process does not un-protect the default location. Pure: ~ expansion and
    cwd-relative resolution only, no fs access, never raises.
    """
    p = pathlib.Path(os.path.expanduser(str(path))).resolve()
    candidates = {agent_config_dir(env).resolve(), (pathlib.Path.home() / ".pi" / "agent").resolve()}
    for agent_dir in candidates:
        if p == agent_dir:
            return True
        if any(p == agent_dir / name for name in PROTECTED_AGENT_CONFIG_FILES):
            return True
    return False


class ProtectedConfigError(RuntimeError):
    """Raised when framework code tries to modify a protected agent config
    file. No override exists on purpose: the fix is to not write the file."""


def assert_not_protected_agent_config(
    path: str | os.PathLike[str],
    action: str = "modify",
    env: Mapping[str, str] | None = None,
) -> None:
    """Guard for any future framework write path: raises before the write
    when the target is a protected agent config file."""
    if is_protected_agent_config(path, env):
        target = os.path.expanduser(str(path))
        raise ProtectedConfigError(
            f"refusing to {action} {target}: cross-window pi config file "
            f"({', '.join(PROTECTED_AGENT_CONFIG_FILES)} under the agent dir) shared "
            "by every live pi session (2026-09-15 incident: clearing auth.json "
            "broke all open windows). Framework code never writes these files; "
            "the user changes them outside pi (plain terminal / `pi /login`)."
        )


# --- pi shellPath auto-fill (fresh-machine shell bootstrap) -------------------
#
# Why: pi resolves the bash tool's shell per call as user-shellPath ->
# working WSL bash -> PowerShell -> error. A fresh machine has no shellPath
# (settings.json is user-owned; the agent tool layer is hard-blocked from
# writing it). When WSL bash is installed and working, pi picks it — and the
# Windows-side python the user bootstrapped with is invisible inside WSL, so
# the PM agent's `python .../advance_phase.py` path dies ("no shell").
# Pinning PowerShell makes the shell deterministic and consistent with that
# python.
#
# Policy exception (see assert_not_protected_agent_config): settings.json is
# a protected cross-window file, but these helpers run ONLY from explicit
# user-invoked commands (mw setup / bootstrap step 5 / doctor --fix) in a
# plain terminal — the sanctioned context for machine config. The write is
# an additive merge: fill only a missing/empty shellPath, replace only a
# stale one (file gone, e.g. settings copied from another machine), never
# touch any other key, never write a malformed file.

def detect_pi_shell_path() -> str | None:
    """Absolute PowerShell path to pin as pi's shellPath on Windows.

    Preference mirrors pi's getPowerShellConfig: pwsh.exe (7+) before the
    built-in powershell.exe. None on non-Windows (pi's Unix resolution —
    /bin/bash -> PATH bash -> sh — never fails, nothing to pin) and when no
    PowerShell is found."""
    if os.name != "nt":
        return None
    for name in ("pwsh.exe", "powershell.exe"):
        found = shutil.which(name)
        if found and pathlib.Path(found).is_file():
            return str(pathlib.Path(found))
    return None


def pi_settings_path(env: Mapping[str, str] | None = None) -> pathlib.Path:
    """pi's settings.json inside the effective agent config dir."""
    return agent_config_dir(env) / "settings.json"


def _write_pi_settings(settings: pathlib.Path, data: dict) -> None:
    """Merge-write pi settings.json (2-space indent, trailing newline).
    Parent dir created when missing (fresh machine, no ~/.pi/agent yet)."""
    settings.parent.mkdir(parents=True, exist_ok=True)
    tmp = settings.with_name(settings.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, settings)


# ensure_pi_shell_path result statuses (doctor section contract, mirrored by
# the TS DoctorJson.pi_shell): ok / filled / replaced / missing / broken /
# unreadable / not-applicable.
def _doctor_dispatch(project_dir: pathlib.Path) -> dict:
    """Dispatch model config section (mw-dispatch-models).

    A missing .mw/dispatch.yml is silent (nothing configured — the chain just
    falls through to the window model / per-cli defaults). A broken file is a
    suggestion, never an issue: model defaults are a convenience and must not
    flag the chain unhealthy.

    `images` is the per-role image capability ("yes"/"no"/"unknown", AC-010 /
    AC-015) and the single source the TS doctor renderer reads. It is only
    probed when the config parsed and lists at least one role: the missing-file
    early return must stay exactly {"exists": False}, and an unusable file
    carries no trustworthy role list.
    """
    path = dispatch_config_path(project_dir)
    section: dict = {"exists": path.exists()}
    if not path.exists():
        return section
    config, err = load_dispatch_config(project_dir)
    section["models"] = config.get("models", {})
    section["window_model"] = read_window_model(project_dir)
    if err:
        section["error"] = err
        return section
    # fallback_models (mw-model-error-perception D5) is read only once the file
    # parses: an unreadable/broken file is already reported through `error` and
    # must not also become a fallback ISSUE (a broken dispatch.yml stays
    # fail-soft). Only present keys are emitted, so an unconfigured project
    # keeps the historical section shape (JSON consumers stay unaffected).
    fallbacks, fallback_err = load_fallback_models(project_dir)
    if fallback_err:
        section["fallback_error"] = fallback_err
    elif fallbacks:
        section["fallback_models"] = fallbacks
    if section["models"]:
        section["images"] = {
            role: model_images(value) for role, value in sorted(section["models"].items())
        }
    return section


def ensure_pi_shell_path(
    env: Mapping[str, str] | None = None,
    fix: bool = False,
    detect=None,
) -> dict:
    """Check (and with fix=True, fill) pi's settings.json shellPath.

    Returns {"status", "settings", "shell_path", "detected", "detail"}:
      ok              configured and the shell file exists (or non-Windows)
      not-applicable  non-Windows platform — nothing to pin
      filled          fix wrote shellPath into a settings.json that lacked it
      replaced        fix replaced a stale shellPath (file missing on disk)
      missing         not configured and not fixed (no fix, or nothing detected)
      broken          configured but the shell file is gone and not fixed
      unreadable      settings.json exists but is malformed — NEVER written

    `detect` is injectable for cross-platform tests; it defaults to
    detect_pi_shell_path (Windows-only)."""
    settings = pi_settings_path(env)
    detected = (detect or detect_pi_shell_path)()
    result: dict = {
        "settings": str(settings),
        "shell_path": None,
        "detected": detected,
        "detail": "",
    }
    if detect is None and os.name != "nt":
        result["status"] = "not-applicable"
        result["detail"] = "unix shell resolution (/bin/bash -> PATH bash -> sh) never fails"
        return result

    if settings.is_file():
        try:
            data = json.loads(settings.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                raise ValueError("not a JSON object")
        except (OSError, ValueError) as exc:
            result["status"] = "unreadable"
            result["detail"] = (
                f"{settings}: {exc} — fix by hand; this tool never rewrites a malformed file"
            )
            return result
    else:
        data = {}

    current = data.get("shellPath")
    current = current.strip() if isinstance(current, str) else ""
    current = current or None
    result["shell_path"] = current
    if current and pathlib.Path(os.path.expanduser(current)).is_file():
        result["status"] = "ok"
        result["detail"] = "shellPath configured"
        return result

    if current:
        # Stale: file gone (settings copied from another machine) — pi's
        # getShellConfig throws 'Custom shell path not found'; bash tool dead.
        if fix and detected:
            data["shellPath"] = detected
            _write_pi_settings(settings, data)
            result["status"] = "replaced"
            result["shell_path"] = detected
            result["detail"] = f"stale shellPath '{current}' replaced with {detected}"
        else:
            result["status"] = "broken"
            result["detail"] = (
                f"shellPath '{current}' does not exist — the bash tool fails "
                "('Custom shell path not found')"
            )
        return result

    # Not configured.
    if fix and detected:
        data["shellPath"] = detected
        _write_pi_settings(settings, data)
        result["status"] = "filled"
        result["shell_path"] = detected
        result["detail"] = f"shellPath filled with {detected}"
    else:
        result["status"] = "missing"
        result["detail"] = "shellPath not configured" + (
            f" — detected {detected}; run 'mw setup' or 'mw.py doctor --fix' to pin it"
            if detected
            else " — no PowerShell detected; install one or set it by hand"
        )
    return result


# ── Model image-capability probe (`pi --list-models` snapshot) ─────────────
#
# The only Python-side answer to "can this model see images?", shared by
# `mw model set` (config-time refusal) and `mw model show` / `mw doctor`
# (three-state capability column). One full `pi --list-models` snapshot per
# process builds {(provider, model): images}; all callers are one-shot
# commands, no resident hot path (serve/launcher/conductor) touches this.
#
# Fail-open is the whole contract: "yes"/"no" only on an exact row match.
# Everything else — pi not on PATH, spawn failure, timeout, rc != 0, no data
# row, zero hits, CLI prefixes, bare ids — is "unknown", never "no". A
# missing row means an unauthenticated provider or an unknown model, not a
# model that rejects images.

MODEL_PROBE_TIMEOUT_S = 3.0  # doctor promises < 5s; measured probe 0.8-0.96s

# Process-local memo of the parsed snapshot. None = not probed yet; {} =
# probed and unavailable (stays unknown for the rest of the process). Injected
# which/run seams bypass the memo — they are test doubles that must vary.
_MODEL_IMAGE_SNAPSHOT: dict[tuple[str, str], str] | None = None

# context / max-out cells, e.g. 200K, 1M, 32.8K, 131.1K (dynamic widths).
_MODEL_SIZE_TOKEN = re.compile(r"^\d+(\.\d+)?[KM]$")


def _parse_model_rows(stdout: str) -> dict[tuple[str, str], str]:
    """Parse `pi --list-models` stdout -> {(provider, model): "yes"|"no"}.

    Rows are recognised by token shape, never by line number: the worker
    environment prepends `[worker] start ...` noise and the column widths are
    dynamic. The CLI's pattern search is fuzzy (a fragment matches several
    rows), so callers select by exact (provider, model) equality.
    """
    rows: dict[tuple[str, str], str] = {}
    for line in stdout.splitlines():
        tokens = line.split()
        if len(tokens) != 6:
            continue
        if not (_MODEL_SIZE_TOKEN.match(tokens[2]) and _MODEL_SIZE_TOKEN.match(tokens[3])):
            continue
        if tokens[4] not in ("yes", "no") or tokens[5] not in ("yes", "no"):
            continue
        rows[(tokens[0], tokens[1])] = tokens[5]
    return rows


def _probe_spawn_kwargs(platform: str | None = None) -> dict:
    """Console isolation for the probe child (mw-console-title-clobber).

    Windows: the child pi sets `process.title`, which lands on SetConsoleTitleW
    for the console it inherits from us. Without CREATE_NO_WINDOW every
    `/mw model show` / `/mw model set` / `/mw doctor` renamed the host pi window
    to "pi" (the TUI only re-asserts its own OSC title on a few events, so the
    dirty title stuck). launcher.py:1104 isolates the worker spawn the same way;
    this probe was the one spawn left without the flag. Non-Windows: no flags,
    behaviour unchanged. `platform` is a test seam.
    """
    if (platform or sys.platform) == "win32":
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW}  # type: ignore[attr-defined]
        return flags
    return {}


def _probe_model_rows(*, which=None, run=None) -> dict[tuple[str, str], str] | None:
    """One `pi --list-models` snapshot -> {(provider, model): images} | None.

    None means the probe is unavailable and every value must resolve to
    "unknown". `which`/`run` are injectable seams (defaults shutil.which /
    subprocess.run) for cross-platform tests, mirroring
    ensure_pi_shell_path(..., detect=None). pi is resolved through
    shutil.which: on Windows a bare ["pi", ...] fails with WinError 2 because
    Popen does not apply PATHEXT (launcher.py:_resolve_cli). The child is
    console-isolated (_probe_spawn_kwargs).
    """
    resolve = which or shutil.which
    spawn = run or subprocess.run
    try:
        pi_bin = resolve("pi")
    except OSError:
        return None
    if not pi_bin:
        return None
    try:
        result = spawn(  # noqa: S603 - resolved path, list args, no shell
            [pi_bin, "--list-models"],
            capture_output=True, text=True, encoding="utf-8",
            timeout=MODEL_PROBE_TIMEOUT_S,
            **_probe_spawn_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    rows = _parse_model_rows(result.stdout or "")
    return rows or None


def _model_capability(rows: dict[tuple[str, str], str], value: str) -> str:
    prefix, model_id = parse_model_value(value)
    provider = MODEL_PREFIX_TO_PI_PROVIDER.get(prefix, "")
    if not provider or not model_id:
        return "unknown"
    return rows.get((provider, model_id), "unknown")


def model_capabilities(values: Sequence[str], *, which=None, run=None) -> dict[str, str]:
    """One `pi --list-models` snapshot -> {value: "yes"|"no"|"unknown"}.

    Memoized per process (real probe only); never raises. Missing rows, an
    unavailable pi, timeouts and parse misses all fall back to "unknown".
    """
    global _MODEL_IMAGE_SNAPSHOT
    if which is None and run is None:
        if _MODEL_IMAGE_SNAPSHOT is None:
            _MODEL_IMAGE_SNAPSHOT = _probe_model_rows() or {}
        rows = _MODEL_IMAGE_SNAPSHOT
    else:
        rows = _probe_model_rows(which=which, run=run) or {}
    return {value: _model_capability(rows, value) for value in values}


def model_images(value: str, *, which=None, run=None) -> str:
    """Convenience single-value wrapper: 'timi/glm-5.3' -> "yes"|"no"|"unknown"."""
    return model_capabilities([value], which=which, run=run)[value]


# 鈹€鈹€ Route resolution 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def route_for(config: dict, cli: str, provider: str) -> dict:
    """Effective provider config for a (cli, provider) task route.

    Returns {"provider_key", "port", "base_url_env", "api_key_env",
    "credential"} with historical defaults when the route is undeclared.
    """
    cli = cli.lower()
    provider = (provider or "").strip()
    key = provider or CLI_DEFAULT_PROVIDER.get(cli, cli)
    cfg = config.get("providers", {}).get(key) or config.get("providers", {}).get(cli) or {}
    cred_name = cfg.get("credential") or key
    cred = config.get("credentials", {}).get(cred_name)
    api_key_env = cfg.get("api_key_env") or credential_inject_env(cred) or "ANTHROPIC_API_KEY"
    return {
        "provider_key": key,
        "port": cfg.get("port", 7001),
        "base_url_env": cfg.get("base_url_env", "ANTHROPIC_BASE_URL"),
        "api_key_env": api_key_env,
        "credential": cred_name,
    }


# 鈹€鈹€ Route precheck 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def route_precheck(config: dict, env: Mapping[str, str] | None = None) -> dict:
    """Credential availability snapshot for every dispatchable route.

    Returns {"routes": [...], "all_missing": bool}. Every route gets one entry:
    {"route", "available", "source", "missing"}. The codex-native route is
    checked via PATH lookup (it uses codex's own config, not env credentials).
    """
    if env is None:
        env = os.environ
    statuses: list[dict] = []
    for name, cfg in sorted(config.get("providers", {}).items()):
        if not isinstance(cfg, dict):
            continue
        cred_name = cfg.get("credential") or name
        cred = config.get("credentials", {}).get(cred_name)
        if cred is None:
            statuses.append({
                "route": name,
                "available": False,
                "source": {},
                "missing": f"credential '{cred_name}' not declared in config",
            })
            continue
        value, source = resolve_credential(cred, env)
        statuses.append({
            "route": name,
            "available": value is not None,
            "source": source,
            "missing": None if value is not None else describe_missing(cred),
        })
    codex_available = shutil.which("codex") is not None
    statuses.append({
        "route": "codex-native",
        "available": codex_available,
        "source": {"kind": "native"},
        "missing": None if codex_available else "codex binary not found on PATH",
    })
    return {"routes": statuses, "all_missing": all(not s["available"] for s in statuses)}


# 鈹€鈹€ File bus: _workers.parallel parse/serialize/lock/status 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def workers_path(project_dir: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(project_dir) / ".agenticdoc" / "_workers.parallel"


def stale_path(project_dir: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(project_dir) / ".agenticdoc" / STALE_FILE_NAME


ACKED_FILE_NAME = "_workers.acked"


def acked_path(project_dir: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(project_dir) / ".agenticdoc" / ACKED_FILE_NAME


def lock_path(project_dir: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(project_dir) / ".mw" / "workers.lock"


# `_workers.parallel` row width: 7 (legacy) .. 9 (model + origin) columns.
# Mirrors worker-store.ts WORKER_COLS_MIN/MAX — the two parsers must agree, or
# one side silently drops rows the other wrote (IN-3, AC-023).
WORKER_COLS_MIN = 7
WORKER_COLS_MAX = 9

# Optional queue-format header written by the TS store when it CREATES a file
# (`# mw-queue:v2`). Headerless files are v1; historical files are never
# rewritten just to gain a header (D-025).
QUEUE_HEADER_RE = re.compile(r"^#\s*mw-queue:v(\d+)\s*$")


def parse_worker_line(line: str) -> dict[str, str] | None:
    """One row -> dict, or ``None`` when it is not a 7..9 column row.

    The single-line mirror of the TS ``parseWorkerLine``: comment rows, blank
    rows and any other width yield ``None`` (the caller decides what that
    means: skip, report, or fail closed).
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    parts = [p.strip() for p in stripped.split("|")]
    if len(parts) < WORKER_COLS_MIN or len(parts) > WORKER_COLS_MAX:
        return None
    return {
        "task_key": parts[0],
        "status": parts[1],
        "cli": parts[2],
        "provider": parts[3],
        "task_path": parts[4],
        "dispatched_at": parts[5],
        "updated_at": parts[6],
        "model": parts[7] if len(parts) >= 8 else "",
        "origin": parts[8] if len(parts) == 9 else "",
    }


def read_workers_file_lines(path: pathlib.Path) -> list[str]:
    """Raw `_workers.parallel` lines in file order (no trailing newline artifact).

    Used by the slot-preserving writers: unlike :func:`parse_workers_file`,
    which drops every row it cannot read, the line list keeps unparsable and
    comment lines exactly as they are so a rewrite cannot delete them
    (AC-023, IN-3). An unreadable/missing file yields an empty list.
    """
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def _scan_worker_lines(path: pathlib.Path) -> list[tuple[str, dict[str, str] | None]]:
    """``[(raw_line, parsed_row_or_None)]`` in file order — the slot map every
    writer uses. A malformed row keeps its slot with ``None``."""
    return [(line, parse_worker_line(line)) for line in read_workers_file_lines(path)]


def parse_workers_queue(path: pathlib.Path) -> dict:
    """Parse `_workers.parallel` **without losing rows** (AC-023, T-18).

    Returns ``{"rows": [...], "unparsable": [...], "version": int}``:

    * ``rows`` — one dict per readable row (same shape as
      :func:`parse_workers_file`), in file order;
    * ``unparsable`` — one ``{"line": n, "cols": n, "text": raw}`` per
      non-comment line that is not a 7..9 column row, in file order;
    * ``version`` — 2 when the file carries a `# mw-queue:v2` header, else 1
      (headerless files are v1; nothing is backfilled, D-025).

    The Python mirror of the TS ``readQueue()``: the row count plus
    ``len(unparsable)`` always equals the number of non-comment lines, which
    is what makes "silent row drop" impossible to reintroduce.
    """
    rows: list[dict[str, str]] = []
    unparsable: list[dict] = []
    version = 1
    for index, line in enumerate(read_workers_file_lines(path), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            match = QUEUE_HEADER_RE.match(stripped)
            if match is not None:
                version = int(match.group(1))
            continue
        row = parse_worker_line(stripped)
        if row is None:
            unparsable.append({"line": index, "cols": len(stripped.split("|")), "text": stripped})
            continue
        rows.append(row)
    return {"rows": rows, "unparsable": unparsable, "version": version}


def parse_workers_file(path: pathlib.Path) -> list[dict[str, str]]:
    """Parse _workers.parallel.

    Column order is locked to the TS writer (worker-store.ts
    parseWorkerLine/serializeWorkerLine): ``task_key | status | cli | provider
    | task_path | dispatched_at | updated_at | model | origin``. Legacy
    7-column (no model) and 8-column (no origin) rows parse unchanged; a
    missing origin is the empty string, never a guessed value.

    Rows this function cannot read are dropped *from the returned list* —
    readers that must not lose them (dispatch guards, doctor, the writers)
    use :func:`parse_workers_queue` instead.
    """
    return parse_workers_queue(path)["rows"]


def serialize_entry(entry: dict[str, str]) -> str:
    """Serialize one row, appending the optional `origin` column last.

    The column is emitted only when set, so a rewrite keeps legacy 7/8-column
    rows byte-identical (no write-side migration of historical rows — D-019).
    """
    cols = [
        entry["task_key"],
        entry["status"],
        entry["cli"],
        entry["provider"],
        entry["task_path"],
        entry["dispatched_at"],
        entry["updated_at"],
        entry.get("model", ""),
    ]
    origin = str(entry.get("origin", "") or "").strip()
    if origin:
        cols.append(origin)
    return " | ".join(cols)


# ── Ack sidecar + run state + launcher bound (T-18 / AC-021, AC-023, D-022) ───
#
# `_workers.acked` is written by the TS AckStore (`taskKey | ackedAtIso`, one
# row per acked task) and was previously never read on the Python side, so an
# acked task could still be re-spawned after a queue rebuild (IN-3 amplifier
# F3). Reading is deliberately fail-safe: a missing file, a comment row, a
# wrong column count and an empty key/timestamp are all "no information" —
# the caller keeps judging by the ledger instead of skipping everything.

RUN_TERMINAL_STATUSES = frozenset({"done", "failed", "needs-clarification", "lost"})


def read_acked(project_dir: pathlib.Path) -> dict[str, str]:
    """``task_key -> ackedAtIso`` from `.agenticdoc/_workers.acked`.

    Fail-safe by contract (VC-031): the file is optional sidecar state, so
    nothing here may raise or invent an entry. Malformed rows are skipped,
    never treated as an acknowledgement.
    """
    try:
        content = acked_path(project_dir).read_text(encoding="utf-8")
    except OSError:
        return {}
    acked: dict[str, str] = {}
    for raw in content.splitlines():
        if not raw.strip():
            continue
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) != 2:
            continue
        task_key, acked_at = parts
        if not task_key or task_key.startswith("#") or not acked_at:
            continue
        acked[task_key] = acked_at
    return acked


def read_run_status(task_dir: pathlib.Path) -> str | None:
    """Raw `status` from a worker-written `run.json` (D-022), or ``None``.

    ``None`` means "no information" (missing file, unreadable JSON, non-object
    root, missing/empty status) — never a guess, so callers keep judging by the
    ledger instead of trusting an absent product. Forward-compatible with
    T-20's `run-store.ts`: only `status` is read and an unknown value is
    returned as-is for the caller to reject.
    """
    try:
        data = json.loads((pathlib.Path(task_dir) / "run.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    status = data.get("status")
    if not isinstance(status, str) or not status:
        return None
    return status


def mark_run_lost(task_dir: pathlib.Path) -> str | None:
    """Record ``status="lost"`` in a worker-written ``run.json`` (T-20/D-022).

    The launcher's ONLY write to run.json: the worker owns ``running`` and every
    terminal state, and the launcher may only ever add ``lost`` when a process
    that recorded itself as running is gone with no verified outcome. Everything
    else in the record (run_id, artifacts, supersedes, pid) is preserved
    verbatim — the scene stays intact for the human who has to decide next.

    Best-effort by contract: returns the written status, or ``None`` when there
    is nothing to update (no/invalid record) or the write failed. Never raises,
    so a broken product can never kill the poll loop.
    """
    path = pathlib.Path(task_dir) / "run.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    data["status"] = "lost"
    data["ended_at"] = iso_now()
    data.pop("exit", None)
    try:
        tmp_path = pathlib.Path(str(path) + ".tmp")
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        tmp_path.replace(path)
    except OSError:
        return None
    return "lost"


def launcher_max_workers(project_dir: pathlib.Path) -> int:
    """Effective launcher concurrency cap (T-18/D-027, AC-021).

    Always a bounded int >= 1. A missing/unreadable/out-of-range config falls
    back to the built-in default instead of ever meaning "unbounded": the
    IN-3 amplifier was exactly `max_workers = None` (F1), which let 66 workers
    run at once.
    """
    fallback = int(autopilot_config.DEFAULT_CONFIG["launcher_max_workers"])
    try:
        values = effective_config.load_effective(project_dir).values
    except Exception:  # noqa: BLE001 — a broken config must not kill the launcher
        return fallback
    limit = values.get("launcher_max_workers", fallback)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        return fallback
    return limit


# ── Worker attribution (D-019 / AC-021) ───────────────────────────────────────

WORKER_ORIGIN_CONDUCTOR = "conductor"
WORKER_ORIGIN_MANUAL = "manual"
WORKER_ORIGINS = (WORKER_ORIGIN_CONDUCTOR, WORKER_ORIGIN_MANUAL)

# `.agenticdoc/<key>/workers/<task>/task.md` — the queue-row path contract
# (dispatch.py `task_dir`). Paths are normalised to forward slashes first so
# Windows rows match too.
_WORKER_PATH_KEY_RE = re.compile(r"(?:^|/)\.agenticdoc/([^/]+)/workers/")


def worker_origin(row: dict[str, str]) -> str:
    """Queue-row provenance: ``conductor`` or ``manual``.

    Only the literal `conductor` cell makes a row a conductor dispatch. A
    missing column (legacy row), an empty cell and any unknown value all
    normalise to `manual`: fail-closed, and the reason the `ap-` task-key
    prefix can never resurrect the false signal on its own (AC-021/VC-028).
    """
    raw = str(row.get("origin", "") or "").strip().lower()
    return WORKER_ORIGIN_CONDUCTOR if raw == WORKER_ORIGIN_CONDUCTOR else WORKER_ORIGIN_MANUAL


def worker_path_key(task_path: str) -> str:
    """Project key from a `.agenticdoc/<key>/workers/...` path ("" otherwise).

    The path is the origin-independent anchor (VC-028 ``fallback=path``):
    legacy rows and conductor rows alike resolve their owner key this way.
    """
    match = _WORKER_PATH_KEY_RE.search(str(task_path or "").replace("\\", "/"))
    return match.group(1) if match else ""


def worker_owner_key(row: dict[str, str]) -> str:
    """Owner project key of one row: the key its `task_path` is filed under.

    Independent of `origin` — a manual row still groups under its key for the
    panel; it just never holds a conductor slot (`row_belongs_to`).
    """
    return worker_path_key(str(row.get("task_path", "")))


def worker_is_conductor(row: dict[str, str]) -> bool:
    """True only for rows written with ``origin: conductor``."""
    return worker_origin(row) == WORKER_ORIGIN_CONDUCTOR


def row_belongs_to(row: dict[str, str], key: str) -> bool:
    """Unified owner predicate (D-019): does this row hold `key`'s slot?

    `origin` decides first: a `manual` row — including every legacy row
    without the column — owns no autopilot slot. A conductor row owns the key
    its `task_path` anchors under. Neither branch consults the `ap-` task-key
    prefix, which is a false signal on its own (6 measured rows).
    """
    if not worker_is_conductor(row):
        return False
    return worker_owner_key(row) == key


# ── Synthetic claim axis (T-16 / AC-014 / D-013) ──────────────────────────────
#
# Route ① of AC-014: unattended autopilot must not equate "no human window has
# claimed the key" with "no owner ⇒ skip". The conductor takes the key over
# with a SYNTHETIC claim id written into the framework's existing claim cell
# (`_index.parallel` ClaimId, the axis `worker_owner_key`/`state.claim_state`
# already read) — no new file, no new column, no new format.
#
# The id carries the same `host:pid` tail every claim already has (both sides'
# liveness parsers are pid based), prefixed with the owner marker `autopilot@`
# so the synthetic/human distinction is a FIELD-LEVEL fact rather than an
# inference from the pid. Only ONE claim cell writer exists per key
# (`autopilot/index_parallel.py`), so the queue's single-writer invariant is
# untouched.

#: Owner marker of a conductor-owned (synthetic) claim id.
SYNTHETIC_CLAIM_PREFIX = "autopilot@"

#: Claim-cell values that mean "no claim" (framework writers use all three).
CLAIM_PLACEHOLDERS = ("", "—", "-")

_SYNTHETIC_CLAIM_RE = re.compile(r"^autopilot@([^:@]+):(\d+)$")


def synthetic_claim_id(host: str, pid: int) -> str:
    """`autopilot@<host>:<pid>` — the conductor's own claim identity."""
    return f"{SYNTHETIC_CLAIM_PREFIX}{host}:{int(pid)}"


def parse_synthetic_claim(claim_id: str) -> tuple[str, int] | None:
    """``(host, pid)`` of a synthetic claim id, or ``None`` when not one.

    Strict by construction: a human ``host:pid`` claim never matches (no
    prefix) and a malformed ``autopilot@`` value is not silently adopted as a
    claim (the caller treats ``None`` as "not a synthetic claim", and the
    existing fail-closed claim parsers keep handling it).
    """
    m = _SYNTHETIC_CLAIM_RE.match((claim_id or "").strip())
    if m is None:
        return None
    pid = int(m.group(2))
    if pid <= 0:
        return None
    return m.group(1), pid


def is_synthetic_claim(claim_id: str) -> bool:
    """True when the claim cell is owned by the conductor (T-16)."""
    return parse_synthetic_claim(claim_id) is not None


def read_serve_identity(project_dir: pathlib.Path) -> dict[str, int] | None:
    """`serve.meta` identity of the running service (T-13), or ``None``.

    Returns ``{"pid": int, "started_at_ms": int}``. The synthetic claim binds
    to `pid`, so a serve restart (pid changes) deterministically invalidates
    every claim the previous instance wrote — no wall-clock guess. Pure read:
    a missing/unreadable/schema-less meta yields ``None`` (the caller then
    falls back to the conductor's own pid plus pid liveness).
    """
    try:
        raw = (pathlib.Path(project_dir) / ".mw" / "serve.meta").read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    pid = data.get("pid")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return None
    started = data.get("started_at_ms")
    started_ms = started if isinstance(started, int) and not isinstance(started, bool) else 0
    return {"pid": pid, "started_at_ms": started_ms}


def acquire_lock(lock_file: pathlib.Path, retries: int = 20, base_delay: float = 0.05) -> None:
    """Exclusive lock via O_CREAT|O_EXCL. Same protocol as the TS side."""
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries + 1):
        try:
            fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return
        except FileExistsError:
            if attempt == retries:
                raise RuntimeError(f"Could not acquire lock at {lock_file} after {retries} retries")
            import time
            time.sleep(base_delay * (2 ** attempt))


def release_lock(lock_file: pathlib.Path) -> None:
    try:
        lock_file.unlink()
    except FileNotFoundError:
        pass


def _write_workers_file(path: pathlib.Path, lines: list[str]) -> None:
    """Atomically write `_workers.parallel` from **raw lines** (T-18/AC-023).

    Takes lines, not parsed rows: every unparsable/comment line the caller did
    not deliberately remove keeps its slot verbatim. The old row-shaped
    signature forced a full re-serialize from the parsed view, which silently
    deleted every row the parser could not read — the write half of IN-3
    (amplifier F4).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(lines) + "\n"
    tmp_path = pathlib.Path(str(path) + ".tmp")
    tmp_path.write_text(content, encoding="utf-8", newline="\n")
    tmp_path.replace(path)


def upsert_worker_row(path: pathlib.Path, row: dict[str, str]) -> None:
    """Insert/replace ONE row by task_key, every other line verbatim
    (AC-023) — the Python mirror of the TS ``upsert``.

    The caller owns the lock (``autopilot/dispatch.py`` takes
    ``.mw/workers.lock`` itself). An existing row is rewritten inside its own
    slot, a new one is appended; either way unparsable and legacy lines keep
    their slots, so a dispatcher write can never make a queue *look* empty.
    """
    task_key = row["task_key"]
    out: list[str] = []
    replaced = False
    for line, existing in _scan_worker_lines(path):
        if existing is not None and existing["task_key"] == task_key and not replaced:
            out.append(serialize_entry(row))
            replaced = True
            continue
        out.append(line)
    if not replaced:
        out.append(serialize_entry(row))
    _write_workers_file(path, out)


def update_status(project_dir: pathlib.Path, task_key: str, status: str) -> None:
    """Update one task's status under the file lock (launcher-side writer).

    Line-preserving (AC-023): only the matching row is rewritten, every other
    line — including rows no parser can read — is written back byte-identical.
    When the task has no row at all the file is left untouched: rewriting it
    from the parsed view would delete the very rows that make a queue look
    empty (IN-3).
    """
    wpath = workers_path(project_dir)
    lock = lock_path(project_dir)
    acquire_lock(lock)
    try:
        updated_at = iso_now()
        out: list[str] = []
        found = False
        for line, row in _scan_worker_lines(wpath):
            if row is not None and row["task_key"] == task_key:
                row["status"] = status
                row["updated_at"] = updated_at
                out.append(serialize_entry(row))
                found = True
            else:
                out.append(line)
        if not found:
            # Nothing to change. A fresh project gets the (empty) queue file
            # created — the caller must never crash on a missing .agenticdoc
            # (T-03 lesson) — but an existing file is left untouched: the old
            # unconditional rewrite is exactly what deleted unparsable rows
            # (IN-3/AC-023).
            if not wpath.exists():
                _write_workers_file(wpath, [])
            return
        _write_workers_file(wpath, out)
    finally:
        release_lock(lock)


def archive_stale_entries(project_dir: pathlib.Path) -> list[str]:
    """Move queue entries whose task.md no longer exists into the stale archive.

    Appends `original line | archived_at | reason` rows to
    `.agenticdoc/_workers.stale.parallel` (never truncated) and rewrites
    `_workers.parallel` without the stale rows. Idempotent; lock-protected.
    Returns the archived task keys.
    """
    wpath = workers_path(project_dir)
    spath = stale_path(project_dir)
    lock = lock_path(project_dir)
    if not wpath.exists():
        return []
    acquire_lock(lock)
    try:
        scanned = _scan_worker_lines(wpath)
        stale: list[dict[str, str]] = []
        kept: list[str] = []
        for line, row in scanned:
            if (
                row is not None
                and row["status"] not in _TERMINAL_STATUSES
                and not pathlib.Path(row["task_path"]).exists()
            ):
                stale.append(row)
                continue
            kept.append(line)
        if not stale:
            return []
        now = iso_now()
        spath.parent.mkdir(parents=True, exist_ok=True)
        with spath.open("a", encoding="utf-8") as fh:
            for entry in stale:
                fh.write(f"{serialize_entry(entry)} | {now} | {STALE_REASON}\n")
        _write_workers_file(wpath, kept)
        return [e["task_key"] for e in stale]
    finally:
        release_lock(lock)


# ── PID / port helpers (shared by mw.py serve/status/stop and doctor) ─────────

def pid_file(project_dir: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(project_dir) / ".mw" / "mw.pid"


def _is_alive_win32(pid: int) -> bool:
    """Read-only liveness check via Win32 OpenProcess + GetExitCodeProcess."""
    import ctypes
    import ctypes.wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _is_alive(pid: int) -> bool:
    if sys.platform == "win32":
        return _is_alive_win32(pid)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def check_pid(pid_path: pathlib.Path) -> int | None:
    """Live PID from a pid file, or None when absent/dead/malformed."""
    if not pid_path.exists():
        return None
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return pid if _is_alive(pid) else None


def port_is_bound(port: int) -> bool:
    """True if something is listening on 127.0.0.1:port."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def port_owner_pids(port: int) -> list[int]:
    """Best-effort netstat lookup of the PID(s) LISTENING on port."""
    cmd = ["netstat", "-ano"] if sys.platform == "win32" else ["netstat", "-an"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)  # noqa: S603
    except (OSError, subprocess.SubprocessError):
        return []
    pids: list[int] = []
    for line in (result.stdout or "").splitlines():
        if f":{port} " in line and "LISTEN" in line.upper():
            parts = line.split()
            try:
                pids.append(int(parts[-1]))
            except (ValueError, IndexError):
                continue
    return sorted(set(pids))


def global_ext_dir() -> pathlib.Path:
    """pi's global extensions dir: $PI_CODING_AGENT_DIR/extensions if set, else
    ~/.pi/agent/extensions (mirrors getAgentDir() in coding-agent config)."""
    env_dir = os.environ.get("PI_CODING_AGENT_DIR")
    base = pathlib.Path(env_dir).expanduser() if env_dir else (pathlib.Path.home() / ".pi" / "agent")
    return base / "extensions"


# ── Doctor ────────────────────────────────────────────────────────────────────

# Extension source dir, relative to this package (repo layout).
_EXT_SRC_DIR = (
    pathlib.Path(__file__).resolve().parent.parent
    / "coding-agent" / "src" / "extensions" / "agent-team-loop"
)
_TERMINAL_STATUSES = {"done", "failed", "needs-clarification", "lost"}


def doctor_fix(project_dir: pathlib.Path) -> list[str]:
    """Apply the auto-fixable findings. Returns human-readable action list.

    Auto-fixed: stale queue entries (archived), stale mw.pid (removed).
    Report-only (suggestions): expired bundle, orphan proxy."""
    actions: list[str] = []
    pfile = pid_file(project_dir)
    if pfile.exists() and check_pid(pfile) is None:
        try:
            pfile.unlink()
            actions.append(f"removed stale PID file: {pfile}")
        except OSError:
            pass
    archived = archive_stale_entries(project_dir)
    if archived:
        actions.append(f"archived stale entries: {', '.join(archived)}")
    return actions


def _doctor_service(project_dir: pathlib.Path) -> dict:
    pfile = pid_file(project_dir)
    pid = check_pid(pfile)
    return {
        "running": pid is not None,
        "pid": pid,
        "pid_file": str(pfile),
    }


def _doctor_proxy(config: dict) -> list[dict]:
    ports: list[dict] = []
    for name, cfg in sorted(config.get("providers", {}).items()):
        if isinstance(cfg, dict) and cfg.get("port"):
            port = int(cfg["port"])
            ports.append({"route": name, "port": port, "listening": port_is_bound(port)})
    return ports


def _doctor_orphan(service: dict, proxy: list[dict]) -> dict:
    if service["running"]:
        return {"detected": False, "ports": []}
    orphans = []
    for p in proxy:
        if p["listening"]:
            orphans.append({**p, "owner_pids": port_owner_pids(p["port"])})
    return {"detected": bool(orphans), "ports": orphans}


def read_log_tail(path: pathlib.Path, lines: int = 10) -> list[str]:
    """Last `lines` lines of a UTF-8 text log; empty when missing/unreadable."""
    try:
        content = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return content.splitlines()[-lines:]


def _doctor_proxy_log(project_dir: pathlib.Path) -> dict:
    """Crash forensics for .mw/proxy.log. The proxy is an optional child
    (spawned only when a port-routed provider has credentials), so a leftover
    traceback is the root cause behind 'port not listening' symptoms and must
    be surfaced, not just the symptom."""
    log_path = pathlib.Path(project_dir) / ".mw" / "proxy.log"
    if not log_path.exists():
        return {"exists": False, "tail": [], "traceback_count": 0, "last_error": None}
    lines = read_log_tail(log_path, 400)
    tb_idx = [i for i, l in enumerate(lines) if l.startswith("Traceback (most recent call last)")]
    last_error = None
    if tb_idx:
        # Exception message = first NON-INDENTED non-empty line after the last
        # traceback header (frame lines are indented; the message sits at column 0).
        for l in lines[tb_idx[-1] + 1 :]:
            if l.strip() and not l[0].isspace():
                last_error = l.strip()
                break
    return {
        "exists": True,
        "tail": lines[-10:],
        "traceback_count": len(tb_idx),
        "last_error": last_error,
    }


def _doctor_launcher_log(project_dir: pathlib.Path) -> dict:
    log_path = pathlib.Path(project_dir) / ".mw" / "launcher.log"
    if not log_path.exists():
        return {"exists": False, "tail": [], "error_count": 0, "fatal": False}
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {"exists": False, "tail": [], "error_count": 0, "fatal": False}
    error_count = sum(1 for l in lines if "spawn failed" in l or "poll error" in l)
    fatal = any("FATAL" in l for l in lines)
    return {"exists": True, "tail": lines[-10:], "error_count": error_count, "fatal": fatal}


_HEARTBEAT_LINE_RE = re.compile(r"^\[HEARTBEAT\] (\S+) task=")


def _parse_heartbeat_ts(hb: str) -> datetime.datetime:
    """Parse a heartbeat timestamp written by the TS side.

    appendHeartbeat emits Date.toISOString() (always `...Z`), but
    datetime.fromisoformat only accepts the `Z` designator on Python 3.11+ —
    on the stated 3.10 floor every real heartbeat would raise ValueError and
    the whole liveness feature would silently degrade to no-heartbeat
    (review M3). Normalize `Z` to `+00:00` before parsing.
    """
    return datetime.datetime.fromisoformat(hb.replace("Z", "+00:00", 1) if hb.endswith("Z") else hb)


def _last_heartbeat(task_dir: pathlib.Path) -> str | None:
    """ISO timestamp of the last [HEARTBEAT] line in a worker task's trace.log,
    or None when the file/line is absent (old bundle, just started)."""
    trace = task_dir / "trace.log"
    try:
        lines = trace.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        m = _HEARTBEAT_LINE_RE.match(line)
        if m:
            return m.group(1)
    return None


def worker_liveness(project_dir: pathlib.Path, stale_after_sec: int = 90) -> list[dict]:
    """Heartbeat-based liveness verdicts for RUNNING queue rows (design D-004).

    Verdicts: alive (last heartbeat within stale_after_sec), stale (older),
    no-heartbeat (running but no [HEARTBEAT] lines — old bundle or fresh
    start). Informational only: killing stuck workers stays with the
    worker-side 30-min watchdog (GC-4). Keep the 90s default in sync with the
    TS HEARTBEAT_STALE_MS constant in agent-team-loop/shared/heartbeat.ts.
    """
    entries = parse_workers_file(workers_path(project_dir))
    verdicts: list[dict] = []
    now = time.time()
    for e in entries:
        if e["status"] != "running":
            continue
        task_dir = pathlib.Path(e["task_path"]).parent
        hb = _last_heartbeat(task_dir)
        if hb is None:
            verdicts.append(
                {"task_key": e["task_key"], "last_heartbeat": None, "age_s": None, "verdict": "no-heartbeat"}
            )
            continue
        try:
            age_s = max(0, int(now - _parse_heartbeat_ts(hb).timestamp()))
        except ValueError:
            verdicts.append(
                {"task_key": e["task_key"], "last_heartbeat": hb, "age_s": None, "verdict": "no-heartbeat"}
            )
            continue
        verdict = "stale" if age_s > stale_after_sec else "alive"
        verdicts.append(
            {"task_key": e["task_key"], "last_heartbeat": hb, "age_s": age_s, "verdict": verdict}
        )
    return verdicts


# ── Terminal evidence / launcher beat (D-007/D-008, T-02) ─────────────────────

# Mirrors END_LINE_RE in agent-team-loop/shared/heartbeat.ts. Only a full
# `[END] <ts> exit=<n> elapsed=<n>s tools=<n> phases=<...>` line counts as
# terminal evidence (AC-012); the exit->status mapping itself lives in the
# launcher (T-08).
_END_LINE_RE = re.compile(r"^\[END\] (\S+) exit=(\d+) elapsed=(\d+)s tools=(\d+) phases=(\S+)$")
_TRACE_TAIL_BYTES = 64 * 1024


def parse_end_exit(task_dir: pathlib.Path) -> int | None:
    """Exit code from the last [END] line of a worker task's trace.log.

    Reads only the file tail (64KB, design section 9: stat + tail-read so
    polling stays cheap). Missing file or no [END] line -> None; the caller
    decides what unverifiable means (T-08). Later [END] lines win, mirroring
    the TS parse loop.
    """
    trace = pathlib.Path(task_dir) / "trace.log"
    try:
        with trace.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - _TRACE_TAIL_BYTES))
            tail = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    exit_code: int | None = None
    for line in tail.splitlines():
        m = _END_LINE_RE.match(line)
        if m:
            exit_code = int(m.group(2))
    return exit_code


# Launcher beat protocol (D-008): every poll overwrites
# .mw/launcher-beat.<pid> with a single `ts=<iso>` line. Before applying the
# silence rule (presumed dead), a launcher checks for another live launcher's
# fresh beat and yields. No lock: one small file per launcher, overwritten.
_BEAT_FILE_PREFIX = "launcher-beat."
_BEAT_FRESH_SEC = 30
_ORPHAN_DEAD_ENV = "PI_WORKER_ORPHAN_DEAD_MIN"
_DEFAULT_ORPHAN_DEAD_MIN = 90


def launcher_beat_write(project_dir: pathlib.Path, pid: int) -> None:
    """Refresh this launcher's beat file: .mw/launcher-beat.<pid>, single
    `ts=<iso>` (UTC) line, overwritten every poll (D-008)."""
    beat = pathlib.Path(project_dir) / ".mw" / f"{_BEAT_FILE_PREFIX}{pid}"
    beat.parent.mkdir(parents=True, exist_ok=True)
    beat.write_text(f"ts={iso_now()}\n", encoding="utf-8")


def other_live_launcher(project_dir: pathlib.Path, self_pid: int) -> bool:
    """True when another live launcher has a fresh beat (D-008).

    A beat file counts only when its pid is not ours, its ts is younger than
    30s, and the pid is alive (reuses _is_alive). Missing files, expired or
    unparseable beats, and dead pids all mean "no other live launcher", so
    the caller keeps the silence rule for itself. A beat proven expired
    whose pid is dead is unlinked along the way (hygiene, review S2: one
    stale file would otherwise accumulate per dead launcher; correctness is
    unaffected either way since expired beats are already ignored).
    """
    beat_dir = pathlib.Path(project_dir) / ".mw"
    now = time.time()
    for beat in beat_dir.glob(f"{_BEAT_FILE_PREFIX}*"):
        try:
            pid = int(beat.name[len(_BEAT_FILE_PREFIX):])
        except ValueError:
            continue  # malformed name; not ours to judge
        if pid == self_pid:
            continue
        try:
            content = beat.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.match(r"^ts=(\S+)", content.strip())
        if not m:
            continue
        try:
            ts = _parse_heartbeat_ts(m.group(1))
        except ValueError:
            continue
        if ts.tzinfo is None:  # spec 2.1: timestamps are UTC
            ts = ts.replace(tzinfo=datetime.timezone.utc)
        if now - ts.timestamp() >= _BEAT_FRESH_SEC:
            if not _is_alive(pid):  # expired AND dead: prune the leftover beat
                try:
                    beat.unlink(missing_ok=True)
                except OSError:
                    pass  # best-effort hygiene
            continue
        if _is_alive(pid):
            return True
    return False


def orphan_dead_after(env: Mapping[str, str] | None = None) -> int:
    """Silence-rule window in minutes (D-007): env PI_WORKER_ORPHAN_DEAD_MIN
    (int >= 1), default 90. Missing/0/negative/non-numeric values fall back
    to the default so a typo can never disable or zero the rule."""
    if env is None:
        env = os.environ
    try:
        minutes = int(env.get(_ORPHAN_DEAD_ENV, ""))
    except (TypeError, ValueError):
        return _DEFAULT_ORPHAN_DEAD_MIN
    if minutes < 1:
        return _DEFAULT_ORPHAN_DEAD_MIN
    return minutes


def task_dir_last_activity(task_dir: pathlib.Path) -> float | None:
    """Newest mtime among all files in a worker task directory (D-007 silence
    rule input). None when the directory is missing or holds no files."""
    task_dir = pathlib.Path(task_dir)
    if not task_dir.is_dir():
        return None
    newest: float | None = None
    try:
        entries = list(task_dir.iterdir())
    except OSError:
        return None
    for entry in entries:
        try:
            if not entry.is_file():
                continue
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        newest = mtime if newest is None else max(newest, mtime)
    return newest


def _queue_alarm_delta(project_dir: pathlib.Path) -> int:
    """Effective `queue_alarm_delta` for the doctor burst-shape criterion.

    Read-only and fail-soft: an unreadable/out-of-range config falls back to
    the built-in default instead of making the whole doctor run fail (the
    criteria must never depend on a writable or healthy config).
    """
    fallback = int(autopilot_config.DEFAULT_CONFIG["queue_alarm_delta"])
    try:
        values = effective_config.load_effective(pathlib.Path(project_dir)).values
    except Exception:  # noqa: BLE001 — doctor must still report the queue
        return fallback
    delta = values.get("queue_alarm_delta", fallback)
    if isinstance(delta, bool) or not isinstance(delta, int) or delta < 1:
        return fallback
    return delta


def _doctor_queue(project_dir: pathlib.Path) -> dict:
    queue = parse_workers_queue(workers_path(project_dir))
    entries = queue["rows"]
    non_terminal = [
        {
            "task_key": e["task_key"],
            "status": e["status"],
            "cli": e["cli"],
            "task_md_exists": pathlib.Path(e["task_path"]).exists(),
        }
        for e in entries if e["status"] not in _TERMINAL_STATUSES
    ]
    stale_count = sum(1 for e in non_terminal if not e["task_md_exists"])
    spath = stale_path(project_dir)
    archived_total = 0
    if spath.exists():
        try:
            archived_total = len(spath.read_text(encoding="utf-8").splitlines())
        except OSError:
            archived_total = 0
    # run-ledger-conflict (T-18/D-027, D-022): the product carries its own
    # terminal state; a non-terminal row whose `run.json` already ended is a
    # conflict, never a re-run candidate. Present only when T-20's run.json
    # exists, so this stays quiet on historical projects.
    run_ledger_conflict: list[dict] = []
    for e in entries:
        if e["status"] in _TERMINAL_STATUSES:
            continue
        run_status = read_run_status(pathlib.Path(e["task_path"]).parent)
        if run_status in RUN_TERMINAL_STATUSES:
            run_ledger_conflict.append(
                {
                    "task_key": e["task_key"],
                    "row_status": e["status"],
                    "run_status": run_status,
                    "task_path": e["task_path"],
                }
            )
    return {
        "non_terminal": non_terminal,
        "non_terminal_count": len(non_terminal),
        "rows_total": len(entries),
        "stale_count": stale_count,
        "archived_total": archived_total,
        "unparsable": queue["unparsable"],
        "unparsable_count": len(queue["unparsable"]),
        "version": queue["version"],
        "alarm_delta": _queue_alarm_delta(project_dir),
        "run_ledger_conflict": run_ledger_conflict,
    }


def _doctor_bundle() -> dict:
    bundle = global_ext_dir() / "agent-team-loop.js"
    if not bundle.exists():
        return {"available": False, "note": f"global bundle not found: {bundle}"}
    if not _EXT_SRC_DIR.is_dir():
        return {
            "available": True,
            "global_bundle_mtime": datetime.datetime.fromtimestamp(bundle.stat().st_mtime).isoformat(),
            "source_available": False,
            "stale": None,
            "note": "extension source not found next to mw package; cannot compare",
        }
    bundle_mtime = bundle.stat().st_mtime
    newest = max(f.stat().st_mtime for f in _EXT_SRC_DIR.rglob("*") if f.is_file())
    return {
        "available": True,
        "global_bundle_mtime": datetime.datetime.fromtimestamp(bundle_mtime).isoformat(),
        "source_newest_mtime": datetime.datetime.fromtimestamp(newest).isoformat(),
        "source_available": True,
        "stale": newest > bundle_mtime,
    }


#: AC-016 (mw-worktree-junction-guard, decisions D-15/D-18) activation
#: self-check marker set. Each marker is a literal only the G1/G6 guard emits
#: from its bundled decision code, so its presence in a bundle is evidence the
#: capability (not just its prescription text) was bundled:
#:
#:   * `reparse-point` - the guard's own `basis` vocabulary value (design §3.2:
#:     "basis values are a fixed vocabulary"): `scanVerdict` emits it whenever
#:     it classifies a target tree. Measured 2026-10-14: exactly 1 hit in a
#:     fresh esbuild of `index.ts`, absent before deployment.
#:   * `user_bash` - the G6/AC-014 hook registration (`pi.on("user_bash")`);
#:     measured 2 hits per bundle. D-18: the single `reparse-point` marker stayed
#:     green when the `user_bash` hook was deleted, so the decision marker alone
#:     cannot prove the `!`/RPC channel is guarded.
#:
#: `has_marker` is True only when *every* marker is present (D-18).
ACTIVATION_MARKERS: tuple[str, ...] = ("reparse-point", "user_bash")

#: The extension source directory that identifies a project as the checkout
#: owning this guard. The activation self-check only applies there: for an
#: arbitrary project the two deployment targets are not this key's artifacts,
#: and every frozen doctor test (`test_doctor_gates.py`, `test_serve_doctor.py`)
#: runs on a fixture outside the checkout, so a project-agnostic check would
#: flip their `healthy` assertions (and, with `PI_CODING_AGENT_DIR` scoped to a
#: fixture, report a "missing global bundle" that is not a deployment defect).
_EXT_SRC_REL = ("packages", "coding-agent", "src", "extensions", "agent-team-loop")


def _activation_bundle_paths(project_dir: pathlib.Path) -> list[pathlib.Path] | None:
    """The two AC-016 deployment targets, or ``None`` when the check does not
    apply to `project_dir` (see `_EXT_SRC_REL`).

    ① the tracked build artifact `packages/multi-workers/dist/extensions/`
    ``agent-team-loop.js``; ② the global/installed bundle
    ``<PI_CODING_AGENT_DIR|~/.pi/agent>/extensions/agent-team-loop.js``.
    """
    project_dir = pathlib.Path(project_dir)
    if not project_dir.joinpath(*_EXT_SRC_REL).is_dir():
        return None
    return [
        project_dir / "packages" / "multi-workers" / "dist" / "extensions"
        / "agent-team-loop.js",
        global_ext_dir() / "agent-team-loop.js",
    ]


def _activation_copy_role(path: pathlib.Path) -> str:
    """Which deployment copy a bundle path is (D-18 C9 wording fix).

    The two AC-016 targets have different roles and therefore different
    failure meanings: the tracked build artifact under
    ``packages/multi-workers/dist/extensions/`` is staging that pi never
    loads (a finding there means `mw build` has not run), while the copy
    under the pi agent dir is the bundle pi actually loads (a finding there
    means `mw build --install` has not run).
    """
    normalized = os.path.normcase(os.path.normpath(str(path)))
    dist_marker = os.path.normcase(os.path.join("multi-workers", "dist", "extensions"))
    return "dist" if dist_marker in normalized else "installed"


def _activation_fix(role: str) -> str:
    """Fix command for a copy's missing/absent guard (D-18 C9)."""
    return "mw build" if role == "dist" else "mw build --install"


def _activation_scan(bundle_paths) -> dict:
    """AC-016: does each bundle carry *every* G1/G6 capability marker?

    D-18: the markers are judged independently (`entry["markers"]`), and
    `entry["has_marker"]` is True only when all of them are present, so a
    bundle that dropped the `user_bash` hook is a finding even though the
    decision marker survives. `entry["missing_markers"]` names the absent
    ones for the issue/text faces.

    Fail-open-to-verdict: a stat/read/decoding failure never raises; the entry
    records the error and the per-marker verdicts stay ``None`` ("cannot
    confirm"), which the issue face renders as unverifiable rather than as
    "deployed". A missing file is a finding too (it is not silently skipped).
    """
    checked: list[dict] = []
    missing: list[str] = []
    for raw in bundle_paths:
        path = pathlib.Path(raw)
        entry: dict = {
            "path": str(path),
            "role": _activation_copy_role(path),
            "exists": False,
            "has_marker": None,
            "markers": {marker: None for marker in ACTIVATION_MARKERS},
            "missing_markers": [],
            "error": None,
        }
        try:
            entry["exists"] = os.path.lexists(str(path))
        except OSError as exc:  # pragma: no cover - os.path.lexists rarely raises
            entry["error"] = str(exc)
        if entry["exists"]:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError, ValueError) as exc:
                entry["error"] = str(exc)
            else:
                for marker in ACTIVATION_MARKERS:
                    entry["markers"][marker] = marker in text
                entry["missing_markers"] = [
                    marker for marker in ACTIVATION_MARKERS
                    if entry["markers"][marker] is not True
                ]
                entry["has_marker"] = not entry["missing_markers"]
        else:
            entry["error"] = "file missing"
        if entry["has_marker"] is not True:
            missing.append(str(path))
        checked.append(entry)
    return {
        "applicable": True,
        "markers": list(ACTIVATION_MARKERS),
        "checked": checked,
        "missing": missing,
        "ok": not missing,
    }


def _doctor_activation(project_dir: pathlib.Path) -> dict:
    """AC-016 activation section. Silent ``applicable: False`` outside the
    checkout that owns the extension source; otherwise `_activation_scan`."""
    paths = _activation_bundle_paths(project_dir)
    if paths is None:
        return {
            "applicable": False,
            "markers": list(ACTIVATION_MARKERS),
            "checked": [],
            "missing": [],
            "ok": True,
        }
    return _activation_scan(paths)


def _source_desc(source: dict) -> str:
    if not source:
        return "native"
    kind = source.get("kind")
    if kind == "env":
        return f"env {source.get('name')}"
    if kind == "file":
        return f"file {source.get('path')}"
    return str(kind or "unknown")


def _autopilot_effective_values(project_dir: pathlib.Path) -> tuple[dict, dict, list[str]]:
    """Effective autopilot config (project layer merged with the machine layer)
    -> (values, origins, diagnostics). Read-only: the machine layer is
    fail-soft, the project layer fail-closed (autopilot.effective_config)."""
    effective = effective_config.load_effective(project_dir)
    return effective.values, effective.origins, list(effective.diagnostics)


def _doctor_autopilot(project_dir: pathlib.Path) -> dict:
    """Autopilot verify config section (AC-008, D-011). Read-only: it never
    creates a directory or a file.

    xkey_verify_missing is the fail-loud condition: xkey_repair is explicitly
    enabled but the effective verify argv (project layer merged with the
    machine layer, then placeholder-expanded) is empty, so every xkey ticket
    would stall with verify_failed. Registered in doctor_report so both report
    paths (`mw doctor` and `mw bootstrap`) surface it."""
    project_dir = pathlib.Path(project_dir)
    config_file = project_dir / ".agenticdoc" / "_autopilot" / "config.json"
    section: dict = {
        "path": str(config_file),
        "exists": config_file.exists(),
        "xkey_repair": False,
        "xkey_verify_cmd": [],
        "xkey_verify_timeout_s": None,
        "xkey_verify_cwd": "",
        "xkey_verify_argv": [],
        "xkey_verify_missing": False,
        "origins": {},
        "diagnostics": [],
        "error": None,
    }
    try:
        values, origins, diagnostics = _autopilot_effective_values(project_dir)
    except Exception as exc:  # config.ConfigError or a T-02 machine-layer failure
        section["error"] = str(exc)
        return section
    section["xkey_repair"] = bool(values.get("xkey_repair"))
    cmd = [str(part) for part in (values.get("xkey_verify_cmd") or [])]
    section["xkey_verify_cmd"] = cmd
    section["xkey_verify_timeout_s"] = values.get("xkey_verify_timeout_s")
    section["xkey_verify_cwd"] = values.get("xkey_verify_cwd") or ""
    section["origins"] = origins
    section["diagnostics"] = diagnostics
    if cmd:
        try:
            section["xkey_verify_argv"] = render_argv(cmd, load_target_config(project_dir))
        except TargetConfigError as exc:
            section["error"] = f"{exc.kind}: {exc}"
    section["xkey_verify_missing"] = section["xkey_repair"] and not section["xkey_verify_argv"]
    return section


# ── Gate queue section (T-13 / AC-006, AC-012, AC-019, AC-031) ───────────────

# The single fallback literal every layer renders for a value the file family
# cannot supply (T-09 contract). Never prose, never a guess.
GATE_MISSING_SENTINEL = "unknown (no field)"

_GATE_DIR_REL = (".agenticdoc", "_autopilot", "gates")
_GATE_FILE_RE = re.compile(r"^gate-(\d+)\.md$")
# v2 decision fields a pending gate may be required to declare (design D6
# §D1.1). The actual requirement is PER KIND, expressed by the two frozen
# tuples below; `_GATE_PENDING_DECISION_FIELDS` stays the union of every
# candidate name (never emptied — the "someone bypassed the creator"
# detector reads the per-kind result of `_gate_missing_fields`).
#
# Universal requirement (T-20): `expires_at`/`default_action` carry AC-019's
# "no implicit permanent retention" rule and apply to EVERY schema-2 pending
# gate. Both creation sites (`conductor._create_gate` and the goal-change site
# in `tick`) stamp them through `conductor._stamp_gate_defaults`.
_GATE_UNIVERSAL_DECISION_FIELDS = ("expires_at", "default_action")

# `reason_code` is a machine-written proposition field (design.md:254 groups it
# with `machine_evidence` / `cause_class` / ...): the conductor writes it only
# where the machine itself renders a judgement. The pure human-decision kinds
# (stage-confirm / stage-close / goal-change / xkey-authorize) ask a person and
# `budget-exhausted`'s rule ("used == limit + credits" with blocking gaps) does
# not use it, so requiring it there is a guaranteed false positive. Only
# `stalled` always carries one: the 12 `mark_stalled` call sites in
# conductor.py stamp the frozen stall code (STALL_REASON_CODES, T-07).
_GATE_REASON_CODE_REQUIRED_KINDS = ("stalled",)

_GATE_PENDING_DECISION_FIELDS = (*_GATE_UNIVERSAL_DECISION_FIELDS, "reason_code")


def _gate_node(value: object, *, source: str, sentinel: bool = False) -> dict:
    """One JSON value node: value + its source anchor (D1/D7). A `None` value
    on a sentinel field additionally carries the fixed fallback literal."""
    node: dict = {"value": value, "source": source}
    if value is None and sentinel:
        node["sentinel"] = GATE_MISSING_SENTINEL
    return node


def _gate_node_value(node: object) -> object:
    """Unwrap a value node (tolerates a bare scalar)."""
    if isinstance(node, dict) and "value" in node:
        return node["value"]
    return node


def _gate_waited_text(waited_s: object) -> str:
    """`45s` / `3m` / `3.9h` / `15d` — the waited-time token shared by the
    doctor text line and the CLI card (same buckets as console.ts)."""
    seconds = max(0, int(waited_s or 0))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = seconds / 3600.0
    if hours < 48:
        return f"{round(hours, 1):.1f}h"
    return f"{round(seconds / 86400.0)}d"


def _gate_scope(gate: object) -> str:
    """`stage=N key=K` / `scope=none` — identical to the panel/card token."""
    parts: list[str] = []
    if gate.stage is not None:
        parts.append(f"stage={gate.stage}")
    if gate.key:
        parts.append(f"key={gate.key}")
    return " ".join(parts) if parts else "scope=none"


def _gate_evidence_path(project_dir: pathlib.Path, ref: str) -> pathlib.Path | None:
    """Resolve one `evidence_refs` entry (`kind:relpath[#sha][@mtime_ns]`)
    against `.agenticdoc/` first, then the project root (TS mirror:
    monitor.ts evidenceFilePath). Read-only; never creates anything."""
    body = re.sub(r"^[^:]*:", "", ref, count=1)
    rel = body.split("#")[0].split("@")[0]
    if not rel:
        return None
    for candidate in (project_dir / ".agenticdoc" / rel, project_dir / rel):
        try:
            if candidate.exists():
                return candidate
        except OSError:  # pragma: no cover - transient filesystem race
            continue
    return None


def _gate_created_epoch(created_at: str) -> float | None:
    """`created_at` as a POSIX timestamp, or None when unparsable."""
    probe = created_at[:-1] + "+00:00" if created_at.endswith("Z") else created_at
    try:
        parsed = datetime.datetime.fromisoformat(probe)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.timestamp()


def _roadmap_validation(project_dir: pathlib.Path) -> dict:
    """`validate_roadmap` visibility (AC-031 / VC-049): the doctor is the
    first production caller of the semantic validator besides
    roadmap_check.py. Read-only; a missing roadmap is not an error."""
    path = roadmap_protocol.roadmap_path(project_dir)
    section: dict = {
        "path": str(path),
        "exists": path.is_file(),
        "problems": [],
        "error": None,
    }
    if not section["exists"]:
        return section
    try:
        parsed = roadmap_protocol.load_roadmap(path)
    except roadmap_protocol.RoadmapError as exc:
        section["error"] = str(exc)
        return section
    except OSError as exc:
        section["error"] = str(exc)
        return section
    try:
        section["problems"] = [str(problem) for problem in roadmap_protocol.validate_roadmap(parsed)]
    except Exception as exc:  # pragma: no cover - defensive, must never raise
        section["error"] = str(exc)
    return section


def _gate_missing_fields(gate: object) -> list[str]:
    """Decision fields absent on a schema-2 PENDING gate. Legacy v1 files
    never report missing (I7 / G-D6-1: 34 historical answered gates must not
    flood the surface).

    The set is per kind (T-20): `expires_at`/`default_action` for every kind,
    `reason_code` only for :data:`_GATE_REASON_CODE_REQUIRED_KINDS`. A missing
    field stays an issue/alert (I2/I6), never a note — that is what keeps the
    "someone bypassed the creator" detector alive."""
    if gate.gate_schema != gate_protocol.GATE_SCHEMA_CURRENT:
        return []
    required = _GATE_UNIVERSAL_DECISION_FIELDS
    if gate.kind in _GATE_REASON_CODE_REQUIRED_KINDS:
        required = (*required, "reason_code")
    return [name for name in required if not getattr(gate, name, None)]


def _gate_drift(project_dir: pathlib.Path, gate: object) -> list[dict]:
    """Evidence rewritten after the gate was created (D5: mtime > created_at)."""
    created = _gate_created_epoch(gate.created_at)
    if created is None:
        return []
    drift: list[dict] = []
    for ref in gate.evidence_refs:
        path = _gate_evidence_path(project_dir, ref)
        if path is None:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:  # pragma: no cover - transient stat race
            continue
        if mtime > created:
            drift.append(
                {
                    "id": gate.id,
                    "path": str(path),
                    "mtime": datetime.datetime.fromtimestamp(
                        mtime, datetime.timezone.utc
                    ).isoformat(),
                    "created_at": gate.created_at,
                }
            )
    return drift


def _gate_pending_entry(
    project_dir: pathlib.Path, gate: object, answered: list, now: datetime.datetime
) -> dict:
    """One pending gate's machine face (design D6 §D3.3): every scalar carries
    a `source` or `formula+inputs`; an absent v2 value carries the sentinel."""
    source = f"gates/{gate.id}.md"
    created_epoch = _gate_created_epoch(gate.created_at)
    waited_s = (
        int(max(0.0, now.timestamp() - created_epoch)) if created_epoch is not None else None
    )
    evidence: list[dict] = []
    drift_detail: str | None = None
    for ref in gate.evidence_refs:
        path = _gate_evidence_path(project_dir, ref)
        record: dict = {
            "ref": ref,
            "path": str(path) if path is not None else None,
            "mtime": None,
            "bytes": None,
            "drift": False,
        }
        if path is not None:
            try:
                stat = path.stat()
                record["mtime"] = datetime.datetime.fromtimestamp(
                    stat.st_mtime, datetime.timezone.utc
                ).isoformat()
                record["bytes"] = stat.st_size
                if created_epoch is not None and stat.st_mtime > created_epoch:
                    record["drift"] = True
                    drift_detail = f"mtime={record['mtime']}, gate_created={gate.created_at}"
            except OSError:  # pragma: no cover - transient stat race
                pass
        evidence.append(record)

    same_scope = [
        h for h in answered if h.stage == gate.stage and (h.key or None) == (gate.key or None)
    ]
    same_scope.sort(key=lambda h: h.id)
    history = [
        {
            "gate_id": h.id,
            "kind": h.kind,
            "scope": _gate_scope(h),
            "status": h.status,
            "answered_at": h.answered_at,
            "note": h.note,
        }
        for h in same_scope
    ]
    return {
        "id": gate.id,
        "kind": gate.kind,
        "stage": gate.stage,
        "key": gate.key,
        "scope": _gate_scope(gate),
        "path": str(gate.path),
        "question": gate.question,
        "context_refs": list(gate.context_refs),
        "created_at": _gate_node(gate.created_at, source=f"{source}:created_at"),
        "waited_s": {
            "value": waited_s,
            "formula": "now - created_at",
            "inputs": ["now", f"{source}:created_at"],
        },
        "reason_code": _gate_node(gate.reason_code, source=f"{source}:reason_code", sentinel=True),
        "evidence": evidence,
        "drift_detail": drift_detail,
        "default_action": _gate_node(
            gate.default_action, source=f"{source}:default_action", sentinel=True
        ),
        "expires_at": _gate_node(gate.expires_at, source=f"{source}:expires_at", sentinel=True),
        "loop": gate.loop,
        "used_rounds": gate.used_rounds,
        "round_limit": gate.round_limit,
        "credits_used": gate.credits_used,
        "constraints": list(gate.constraints) if gate.constraints else None,
        "open_items": gate.open_items,
        "verdicts_final": gate.verdicts_final,
        "goal_sha256": gate.goal_sha256,
        "proposal_sha256": gate.proposal_sha256,
        "roadmap_validation": gate.roadmap_validation,
        "answer_source": gate.answer_source,
        "answer_entry": {
            "value": f"/autopilot gate {gate.id} approve|reject --note <text>",
            "source": "console.ts:195/208",
        },
        "history": history,
    }


# ── Cross-key prose-authorization scan (T-24 / VC-048, AC-031 / G11) ─────────
#
# The machine carrier for a cross-key repair authorization is an ANSWERED
# `xkey-authorize` gate: `conductor._xkey_ensure_gate` writes the request id
# into `context_refs` and the gate's answer is the authorization record. The
# path actually seen in production is a hand-written `decision:` line inside
# `_autopilot/evidence/cross-key-repair-request-*.md` (design D1 §6.2 P4). That
# path has no schema, so it can only be detected by a read-only scan - and it
# must be judged UNAUTHORIZED (fail-closed): prose never unlocks anything.

_CROSSKEY_EVIDENCE_REL = (".agenticdoc", "_autopilot", "evidence")
_CROSSKEY_REQUEST_FILE_RE = re.compile(r"^cross-key-repair-request-.*\.md$")
_CROSSKEY_REQUEST_ID_RE = re.compile(r"^\s*request_id\s*:\s*(?P<value>.+?)\s*$")
_CROSSKEY_REQUEST_STATUS_RE = re.compile(r"^\s*status\s*:\s*(?P<value>.+?)\s*$")
# `decision: <approved|rejected> by <who> at <ts>` (design D1 §6.2 P4),
# optionally wrapped in `**…**`. Anchored at the line start so the template
# line the request file itself prescribes (which carries `<approved|rejected>`
# / `<who>` placeholders inside backticks) is never mistaken for an answer.
_CROSSKEY_DECISION_RE = re.compile(
    r"^\s*\*{0,2}\s*decision\s*:\s*(?P<verdict>approved|rejected)\b"
    r"(?:\s*\([^)\n]*\))?\s+by\s+(?P<who>[^\s*]+)\s+at\s+(?P<at>[^\s*（(),，]+)",
    re.IGNORECASE,
)


def _crosskey_prose_decision(text: str) -> dict | None:
    """The hand-written authorization line of one request file, or None.

    Shape: `decision: <approved|rejected> by <who> at <ts>`, optionally wrapped
    in `**…**` (FM 20260925-n1: `**decision: approved (R1) by
    user-via-pm-window at 2026-09-26T03:04:05+00:00**`). This is the scan's
    ONLY prose detector - the T-24 reverse control monkeypatches it to None and
    the positive fixture must then go green, proving this predicate fires."""
    for line in text.splitlines():
        match = _CROSSKEY_DECISION_RE.match(line)
        if match is None:
            continue
        return {
            "verdict": match.group("verdict").lower(),
            "by": match.group("who"),
            "at": match.group("at"),
            "line": line.strip(),
        }
    return None


def _crosskey_field(text: str, pattern: re.Pattern[str]) -> str | None:
    """First `name: value` line matching `pattern`, value unbackticked."""
    for line in text.splitlines():
        match = pattern.match(line)
        if match is not None:
            value = match.group("value").strip().strip("`").strip()
            return value or None
    return None


def _crosskey_machine_carriers(gates_dir: pathlib.Path) -> dict[str, str]:
    """`request_id -> gate id` for every ANSWERED `xkey-authorize` gate.

    A pending gate is not a carrier: only the answer authorizes. Corrupt gate
    files are skipped here (the gate queue section reports them as parse
    errors); they never make a prose authorization look machine-backed."""
    carriers: dict[str, str] = {}
    if not gates_dir.is_dir():
        return carriers
    for entry in sorted(gates_dir.iterdir()):
        if gate_protocol.GATE_FILE_RE.match(entry.name) is None or not entry.is_file():
            continue
        try:
            gate = gate_protocol.parse(entry)
        except (gate_protocol.GateFormatError, OSError):
            continue
        if gate.kind != "xkey-authorize" or gate.status == "pending":
            continue
        if not gate.context_refs:
            continue
        carriers.setdefault(gate.context_refs[0], gate.id)
    return carriers


def _crosskey_prose_scan(project_dir: pathlib.Path) -> dict:
    """Read-only scan of the off-gate `cross-key-repair-request-*.md` path.

    One entry per request file under `.agenticdoc/_autopilot/evidence/`,
    judged on whether its authorization has a machine carrier (a linked,
    already-answered `xkey-authorize` gate). PROSE-ONLY (hand-written
    `decision:` line, no carrier) is the G11 gap: it is reported and
    `treated_as_authorized` stays False (fail-closed). Never writes, never
    creates/answers a gate, never changes xkey semantics."""
    evidence_dir = project_dir.joinpath(*_CROSSKEY_EVIDENCE_REL)
    section: dict = {
        "dir": str(evidence_dir),
        "exists": evidence_dir.is_dir(),
        "requests": [],
        "machine_authorized": 0,
        "prose_only": 0,
        "fail_closed": True,
        "error": None,
    }
    if not section["exists"]:
        return section
    try:
        entries = sorted(
            entry
            for entry in evidence_dir.iterdir()
            if entry.is_file() and _CROSSKEY_REQUEST_FILE_RE.match(entry.name) is not None
        )
    except OSError as exc:
        section["error"] = str(exc)
        return section
    carriers = _crosskey_machine_carriers(project_dir.joinpath(*_GATE_DIR_REL))
    for entry in entries:
        try:
            text = entry.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            section["requests"].append({
                "path": str(entry),
                "request_id": None,
                "status": None,
                "machine_authorized": False,
                "carrier_gate": None,
                "prose_decision": None,
                "authorization": "unreadable",
                "treated_as_authorized": False,
                "error": str(exc),
            })
            continue
        request_id = _crosskey_field(text, _CROSSKEY_REQUEST_ID_RE)
        decision = _crosskey_prose_decision(text)
        carrier = carriers.get(request_id) if request_id else None
        if carrier is not None:
            authorization = "machine"
        elif decision is not None:
            authorization = "prose"
        else:
            authorization = "none"
        section["requests"].append({
            "path": str(entry),
            "request_id": request_id,
            "status": _crosskey_field(text, _CROSSKEY_REQUEST_STATUS_RE),
            "machine_authorized": carrier is not None,
            "carrier_gate": carrier,
            "prose_decision": decision,
            "authorization": authorization,
            "treated_as_authorized": authorization == "machine",
        })
    section["machine_authorized"] = sum(
        1 for request in section["requests"] if request["machine_authorized"]
    )
    section["prose_only"] = sum(
        1 for request in section["requests"] if request["authorization"] == "prose"
    )
    return section


def _contract_guard_entry(project_dir: pathlib.Path, key: str) -> dict:
    """One key's G3 verdict, in the doctor/CLI wire shape.

    Reuses :func:`autopilot.contract_guard.evaluate` (T-04) as the single
    judgement - this function never re-derives freeze/diff/approval logic. The
    freeze path is project-relative (posix) and no timestamp is included, so
    the payload stays reproducible. Read-only: ``evaluate`` opens files for
    reading only. A corrupt gate queue propagates as ``ValueError``/``OSError``
    (the caller decides: doctor skips, the CLI fails loud).
    """
    project_dir = pathlib.Path(project_dir)
    key_dir = project_dir / ".agenticdoc" / key
    verdict = contract_guard.evaluate(
        key_dir, project_dir.joinpath(*_GATE_DIR_REL), key=key
    )
    return {
        "key": key,
        "freeze": contract_guard.freeze_path(key_dir)
        .relative_to(project_dir)
        .as_posix(),
        "no_anchor": bool(verdict.no_anchor),
        "changed_ids": list(verdict.changed_ids),
        "authorized": bool(verdict.ok),
        "carrier": verdict.carrier,
        "reasons": list(verdict.reasons),
    }


def _contract_guard_scan(project_dir: pathlib.Path) -> dict | None:
    """Per-key G3 verdicts for keys that carry a usable freeze sidecar.

    Returns ``None`` when no key has a freeze, so ``_doctor_gates`` never adds
    the ``contract_guard`` key and historical `--json`/text output stays
    byte-identical (P-018 / AC-013). Entries are sorted by key; every path is
    project-relative. Read-only: the scan never creates a file or directory
    (no `.tmp`, no lock). A corrupt gate queue cannot authorize anything, so
    the affected key is skipped here - its parse error is already an issue in
    the gate section (fail-closed reporting, no silent approval).
    """
    project_dir = pathlib.Path(project_dir)
    agenticdoc = project_dir / ".agenticdoc"
    try:
        key_dirs = sorted(
            (entry for entry in agenticdoc.iterdir() if entry.is_dir()),
            key=lambda entry: entry.name,
        )
    except OSError:  # pragma: no cover - transient filesystem race
        return None
    entries: list[dict] = []
    for key_dir in key_dirs:
        try:
            entry = _contract_guard_entry(project_dir, key_dir.name)
        except (ValueError, OSError):
            continue
        if entry.pop("no_anchor"):
            continue
        entries.append(entry)
    if not entries:
        return None
    return {
        "keys": entries,
        "unauthorized": sum(1 for entry in entries if not entry["authorized"]),
    }


# ── AC-001 / C8: `blocked_on_human` in the doctor gates section ──────────────
#
# Three-axis truth table, same source as the monitor panel (design DD-10):
#   1. pending gate > 0            — this section's `pending_count`
#   2. no non-terminal worker row  — `_doctor_queue()`'s `non_terminal_count`,
#                                    the TS `TERMINAL_WORKER_STATUSES` mirror
#                                    (monitor.ts:403-408: `pending` also counts
#                                    as in flight, not just `running`)
#   3. conductor tick fresh        — newest timeline `beat` younger than the
#                                    panel's stale bound (monitor.ts:698-704)
#
# The panel's file-only predicate is the two-axis `blockedOnHuman`
# (status-model.ts:1353), rendered when `!tickStale` (monitor.ts:829). Axis 3
# is evaluated here as a POSITIVE freshness test rather than the panel's
# `tickAgeMs === null => not stale`: a project with no timeline (the conductor
# never ran) must stay silent, which is what keeps historical doctor text
# byte-identical (I7 zero-perturbation) and matches "任一条不足 ⇒ false".

# The panel's stale floor (monitor.ts:698-704):
# `staleAfterMs = max(30_000, poll_interval_sec * 1000 * 5)`. `poll_interval_sec`
# is validated to 1..5 (autopilot/config.py `_INT_RANGES`), so `poll*5 <= 25s`
# and the bound is 30s for every valid config; the floor constant is reused
# verbatim so only a cadence-cap change can move it.
_PANEL_TICK_STALE_SEC = 30.0


def _conductor_tick_stale_after_sec(project_dir: pathlib.Path) -> float:
    """`max(30s, poll_interval_sec * 5)` — the monitor panel's stale bound.

    Read-only and fail-soft (same discipline as `_queue_alarm_delta`): an
    unreadable/out-of-range config falls back to the built-in default instead
    of taking the doctor run down."""
    fallback = int(autopilot_config.DEFAULT_CONFIG["poll_interval_sec"])
    try:
        values = effective_config.load_effective(pathlib.Path(project_dir)).values
    except Exception:  # noqa: BLE001 — doctor must still report the gate queue
        poll = fallback
    else:
        raw = values.get("poll_interval_sec", fallback)
        poll = raw if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 1 else fallback
    return max(_PANEL_TICK_STALE_SEC, float(poll) * 5.0)


def _conductor_tick_fresh(project_dir: pathlib.Path) -> bool:
    """True when the newest timeline `beat` is inside the panel's stale bound.

    Read-only: `autopilot.timeline.tail_events` opens the current timeline
    file for reading only and never creates it. A missing/unreadable timeline,
    a timeline without a `beat`, and an unparsable timestamp all mean "not
    fresh"."""
    path = autopilot_timeline.timeline_path(project_dir)
    for event in reversed(autopilot_timeline.tail_events(path)):
        if event.get("ev") != "beat":
            continue
        raw = event.get("ts")
        if not isinstance(raw, str) or not raw:
            return False
        try:
            stamp = _parse_heartbeat_ts(raw)
        except ValueError:
            return False
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=datetime.timezone.utc)
        age = datetime.datetime.now(datetime.timezone.utc) - stamp
        return age.total_seconds() <= _conductor_tick_stale_after_sec(project_dir)
    return False


def _blocked_on_human(project_dir: pathlib.Path, pending_count: int) -> bool:
    """The three-axis `blocked_on_human` verdict (C8, design DD-10), keyed
    per gate (T-11/AC-002/D2).

    Axis 2 is now per-key: a pending gate is explained away only by a
    non-terminal worker row filed under THAT gate's own key. A gate whose key
    cannot be resolved (the historical JCodingAss `stage-close` gates carry
    `key:`) is never explained away by another key's work (fail-open) — the
    same rule the conductor's reminder judgment uses, so the doctor surface
    and the reminder emitter can never contradict each other about which
    gates need a human. A missing queue or a missing key is a reason to SPEAK,
    never a reason to stay quiet.

    Axes are checked in order and short-circuit; any unmet axis yields False.
    Read-only: the queue read and the timeline tail are pure reads, so the
    doctor surface still creates nothing (AC-001 / VC-003).
    """
    if pending_count <= 0:
        return False
    # Re-derive the pending gates' keys from disk rather than widening this
    # function's signature: the doctor already parsed the queue, and the
    # re-read keeps the caller's `pending_count` axis byte-identical.
    gdir = pathlib.Path(project_dir).joinpath(*_GATE_DIR_REL)
    try:
        entries = sorted(entry for entry in gdir.iterdir() if entry.is_file())
    except OSError:
        entries = []
    pending_keys: list[str] = []
    for entry in entries:
        if _GATE_FILE_RE.match(entry.name) is None:
            continue
        try:
            gate = gate_protocol.parse(entry)
        except (gate_protocol.GateFormatError, OSError):
            continue
        if gate.status == "pending":
            pending_keys.append(gate.key or "")
    if not pending_keys:
        # The count says there is a pending gate but its key could not be
        # re-read (transient race / unreadable file): fail open toward
        # "a human is needed" instead of inventing an all-clear.
        pending_keys = [""]
    rows = parse_workers_queue(workers_path(project_dir))["rows"]
    in_flight_keys = {
        worker_owner_key(row)
        for row in rows
        if row.get("status") not in _TERMINAL_STATUSES
    }
    if all(key and key in in_flight_keys for key in pending_keys):
        return False
    return _conductor_tick_fresh(project_dir)


def _doctor_gates(project_dir: pathlib.Path) -> dict:
    """Gate queue section (AC-006/012/019/031). Read-only: it never creates a
    directory or a file; a missing gates directory is an empty queue.

    Fields (design D6 §D4.1): dir/exists/total/pending_count/schema_versions/
    parse_errors/pending[]/missing_fields[]/drift[]/replayed[]/error plus the
    AC-031 `roadmap_validation` visibility, the T-24/VC-048 `crosskey_prose`
    off-gate authorization scan, the T-11/AC-013 `contract_guard` section
    (present only for keys with a freeze sidecar) and the T-08/AC-001
    `blocked_on_human` boolean (contract C8)."""
    project_dir = pathlib.Path(project_dir)
    gates_dir = project_dir.joinpath(*_GATE_DIR_REL)
    section: dict = {
        "dir": str(gates_dir),
        "exists": gates_dir.is_dir(),
        "total": 0,
        "pending_count": 0,
        "schema_versions": {},
        "parse_errors": [],
        "pending": [],
        "missing_fields": [],
        "drift": [],
        "replayed": [],
        "roadmap_validation": _roadmap_validation(project_dir),
        "crosskey_prose": _crosskey_prose_scan(project_dir),
        "blocked_on_human": False,
        "error": None,
    }
    contract_section = _contract_guard_scan(project_dir)
    if contract_section is not None:
        section["contract_guard"] = contract_section
    # AC-003/R-4 (T-22): the three cases are distinct. A missing directory is
    # a legally empty queue; a path that exists but is not a readable
    # directory (regular file, EACCES, ...) is NOT "no queue" and surfaces as
    # `error` - the same verdict the TS monitor renders as
    # `gate-queue-unreadable`.
    try:
        raw_entries = gate_protocol.queue_entries(gates_dir)
    except gate_protocol.GateQueueUnreadable as exc:
        section["error"] = str(exc)
        return section
    if raw_entries is None:
        return section
    try:
        entries = sorted(entry for entry in raw_entries if entry.is_file())
    except OSError as exc:
        section["error"] = str(exc)
        return section

    parsed_gates: list = []
    for entry in entries:
        if _GATE_FILE_RE.match(entry.name) is None:
            continue
        section["total"] += 1
        try:
            parsed_gates.append(gate_protocol.parse(entry))
        except (gate_protocol.GateFormatError, OSError) as exc:
            section["parse_errors"].append({"path": str(entry), "error": str(exc)})

    for gate in parsed_gates:
        version = str(gate.gate_schema)
        section["schema_versions"][version] = section["schema_versions"].get(version, 0) + 1

    pending = [gate for gate in parsed_gates if gate.status == "pending"]
    answered = [gate for gate in parsed_gates if gate.status != "pending"]
    section["pending_count"] = len(pending)
    section["blocked_on_human"] = _blocked_on_human(project_dir, section["pending_count"])
    now = datetime.datetime.now(datetime.timezone.utc)
    for gate in pending:
        section["pending"].append(_gate_pending_entry(project_dir, gate, answered, now))
        missing = _gate_missing_fields(gate)
        if missing:
            section["missing_fields"].append({"id": gate.id, "fields": missing})
        section["drift"].extend(_gate_drift(project_dir, gate))
        prior = [
            h
            for h in answered
            if h.kind == gate.kind and h.stage == gate.stage and (h.key or None) == (gate.key or None)
        ]
        if prior:
            latest = max(prior, key=lambda h: h.id)
            section["replayed"].append(
                {
                    "id": gate.id,
                    "prior_gate": latest.id,
                    "kind": gate.kind,
                    "scope": _gate_scope(gate),
                }
            )
    return section


def _gates_text_alerted(section: dict) -> bool:
    """I7 zero-perturbation gate: the `gates:` text line appears only when at
    least one of I1-I6 (or the I9/T-24 prose-only cross-key alert) fired."""
    if section.get("parse_errors") or section.get("drift") or section.get("replayed"):
        return True
    # T-08 / AC-001 (C8): blocked-on-human is a first-class alert — a pending
    # gate with no in-flight worker and a live conductor must be visible with
    # its `BLOCKED_ON_HUMAN` suffix even when none of I1-I6 fired.
    if section.get("blocked_on_human"):
        return True
    if (section.get("crosskey_prose") or {}).get("prose_only"):
        return True
    # T-11 / AC-013: an unauthorized frozen-contract change is a fail-closed
    # alert, so the `gates:` text line must appear for it too. The key is only
    # present when a freeze sidecar exists (P-018).
    if (section.get("contract_guard") or {}).get("unauthorized"):
        return True
    missing_ids = {item["id"] for item in section.get("missing_fields") or []}
    for entry in section.get("pending") or []:
        if entry["id"] in missing_ids:
            return True
        if (_gate_node_value(entry.get("waited_s")) or 0) > 24 * 3600:
            return True
    return False


# AC-010 action (3) upgrade window (mw-worktree-junction-guard T-W09). A
# `collapse` event is only upgraded to an issue while it is at most one hour
# old: the launcher rewrites `.mw/tree-watch.json` on every sample, so a fresh
# event is the live fingerprint, while an old event is history. Keeping the
# event on disk after the window closes preserves the design §6.1 "event
# persists, still traceable" property without making every later `mw doctor`
# run permanently red (a stale alert is a new false-positive surface).
TREE_WATCH_ISSUE_WINDOW_SEC = 3600


def _doctor_issues(report: dict) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    suggestions: list[str] = []
    if not report["service"]["running"]:
        issues.append("mw service not running (workers will not be dispatched)")
    plog = report.get("proxy_log") or {}
    if plog.get("last_error"):
        crash = (
            f"proxy.log records {plog['traceback_count']} crash(es), last: {plog['last_error']}"
        )
        if not report["service"]["running"]:
            issues.append(crash)
        else:
            suggestions.append(crash)
    if report["queue"]["stale_count"]:
        issues.append(
            f"{report['queue']['stale_count']} stale queue entries (task.md missing) - "
            "run 'mw.py doctor --fix' or restart mw"
        )
    # Queue shape criteria (T-18/D-027, AC-021): all three are stateless reads
    # (no snapshot file, no write), so the read-only doctor surface can never
    # itself create the symptom it reports.
    queue_section = report["queue"]
    unparsable_count = int(queue_section.get("unparsable_count") or 0)
    if unparsable_count:
        first = (queue_section.get("unparsable") or [{}])[0]
        issues.append(
            f"queue-rows-unparsable: {unparsable_count} row(s) in _workers.parallel cannot be "
            f"read (first: line {first.get('line', '?')}, {first.get('cols', '?')} columns) - "
            "dispatch is refused while any row is unreadable (AC-020/AC-023); fix or delete "
            "the bad row, never rewrite the file from a parsed view"
        )
    rows_total = int(queue_section.get("rows_total") or 0)
    non_terminal_count = int(queue_section.get("non_terminal_count") or 0)
    alarm_delta = int(queue_section.get("alarm_delta") or 50)
    if rows_total > alarm_delta and non_terminal_count / rows_total > 0.9:
        issues.append(
            f"queue-burst-shape: {rows_total} rows of which {non_terminal_count} are "
            f"non-terminal (threshold {alarm_delta}, >90% non-terminal) - the IN-3 "
            "mass re-enqueue fingerprint; check the launcher's concurrency cap and the "
            "dispatch scan scope before restarting anything"
        )
    for conflict in queue_section.get("run_ledger_conflict") or []:
        issues.append(
            f"run-ledger-conflict: {conflict['task_key']} is '{conflict['row_status']}' in the "
            f"queue but its run.json already ended as '{conflict['run_status']}' - "
            "do not re-dispatch; converge the row (AC-022/D-022)"
        )
    if report["launcher_log"].get("fatal"):
        issues.append("launcher.log contains FATAL lines - inspect the tail")
    target = report.get("target")
    if target is not None:
        if target.get("error") is not None:
            err = target["error"]
            issues.append(f"target config error ({err['kind']}): {err['message']}")
        else:
            for check in target.get("checks") or []:
                if not check["ok"]:
                    issues.append(
                        f"target toolchain check failed: {check['name']} ({check['detail']})"
                    )
    autopilot = report.get("autopilot") or {}
    if autopilot.get("xkey_verify_missing"):
        issues.append(
            "autopilot xkey_repair is enabled but the effective verify command is "
            "empty - run 'mw autopilot verify set --project <dir> -- <argv...>'"
        )
    # Gate queue (T-13): I1-I6 alerts with fix strings; I7/I8 are handled by
    # the text layer / JSON-only information and never produce an issue.
    gates_section = report.get("gates") or {}
    if gates_section.get("error"):
        issues.append(
            f"gate queue unreadable ({gates_section['error']}) - inspect "
            f"{gates_section.get('dir')}"
        )
    for err in gates_section.get("parse_errors") or []:
        issues.append(
            f"gate file invalid: {err['path']} ({err['error']}) - "
            "fix the frontmatter or move the file out of _autopilot/gates"
        )
    missing_by_id = {item["id"]: list(item["fields"]) for item in gates_section.get("missing_fields") or []}
    for entry in gates_section.get("pending") or []:
        missing = set(missing_by_id.get(entry["id"], ()))
        if "expires_at" in missing or "default_action" in missing:
            issues.append(
                f"gate {entry['id']} ({entry['kind']}, {entry['scope']}) pending since "
                f"{_gate_node_value(entry['created_at'])} with no expires_at/default_action - "
                "set the default action or answer the gate "
                "(AC-019: no implicit permanent retention)"
            )
        waited = _gate_node_value(entry.get("waited_s")) or 0
        review = (
            f"gate {entry['id']} pending {int(waited // 3600)}h - run "
            f"'/autopilot gate {entry['id']} approve|reject --note <text>' or "
            "'/autopilot gates' to review"
        )
        if waited > 72 * 3600:
            issues.append(review)
        elif waited > 24 * 3600:
            suggestions.append(review)
        extra = missing - {"expires_at", "default_action"}
        if extra:
            suggestions.append(
                f"gate {entry['id']} is schema 2 but missing {', '.join(sorted(extra))} - "
                "the conductor fills them on the next write; rendering shows "
                f"'{GATE_MISSING_SENTINEL}'"
            )
    for drift in gates_section.get("drift") or []:
        suggestions.append(
            f"gate {drift['id']} evidence {drift['path']} was modified after the gate "
            f"(mtime {drift['mtime']} vs {drift['created_at']}) - re-derive the evidence "
            "before answering"
        )
    for replay in gates_section.get("replayed") or []:
        issues.append(
            f"gate {replay['id']} repeats ({replay['kind']}, {replay['scope']}) of answered "
            f"{replay['prior_gate']} - check gate consumption (D1) before answering"
        )
    # T-24 / VC-048 (G11): an off-gate `decision:` line with no answered
    # `xkey-authorize` carrier is prose-only. Report it and keep the
    # fail-closed verdict ("treated as unauthorized") - the issue only makes
    # it visible, it never unlocks anything.
    crosskey_section = gates_section.get("crosskey_prose") or {}
    for request in crosskey_section.get("requests") or []:
        if request.get("authorization") != "prose":
            continue
        decision = request.get("prose_decision") or {}
        label = request.get("request_id") or request.get("path")
        issues.append(
            f"cross-key repair request {label} is authorized by prose only "
            f"(decision: {decision.get('verdict')} by {decision.get('by')} at "
            f"{decision.get('at')}) with no answered xkey-authorize gate "
            f"({request.get('path')}) - treated as unauthorized (VC-048), raise/answer "
            "an xkey-authorize gate to authorize"
        )
    # T-11 / AC-013 (G3): frozen AC/VC text changed with no answered gate that
    # authorizes `contract-change` for the key. Same caliber as the queue-shape
    # criteria (T-18): report it and keep the fail-closed verdict (the done
    # transaction refuses); the issue only makes the refusal visible. The
    # `contract_guard` node exists only for freeze-carrying keys, so historical
    # projects stay silent (P-018).
    contract_section = gates_section.get("contract_guard") or {}
    for entry in contract_section.get("keys") or []:
        if entry.get("authorized"):
            continue
        changed = ", ".join(entry.get("changed_ids") or ()) or "?"
        issues.append(
            f"contract-guard: key {entry['key']} contract text changed without "
            f"authorization ({changed}) since the freeze ({entry.get('freeze')}) - "
            "advance-to-done refused; answer a gate with "
            'authorizes: ["contract-change"] or revert the AC/VC text'
        )
    roadmap_section = gates_section.get("roadmap_validation") or {}
    if roadmap_section.get("error"):
        suggestions.append(
            f"roadmap unusable ({roadmap_section['error']}) - run "
            "'python autopilot/roadmap_check.py --project <dir>'"
        )
    for problem in roadmap_section.get("problems") or []:
        suggestions.append(
            f"roadmap invalid: {problem} - validate_roadmap ran but the conductor does "
            "not enforce it yet"
        )
    if report["bundle"].get("stale"):
        suggestions.append(
            "extension bundle older than source - run '/mw build' or 'mw.py build --install'"
        )
    pi_shell = report.get("pi_shell") or {}
    if pi_shell.get("status") == "broken":
        issues.append(
            "pi settings.json shellPath points to a missing file - the bash "
            "tool fails ('Custom shell path not found'); run 'mw.py doctor --fix' "
            "to re-pin it"
        )
    elif pi_shell.get("status") == "unreadable":
        suggestions.append(f"pi settings.json unreadable: {pi_shell.get('detail')}")
    elif pi_shell.get("status") == "missing":
        suggestions.append(
            "pi shellPath not pinned - WSL bash may shadow the Windows python; "
            "run 'mw setup' or 'mw.py doctor --fix' to pin PowerShell"
        )
    dispatch = report.get("dispatch") or {}
    if dispatch.get("error"):
        suggestions.append(
            f"dispatch.yml unusable ({dispatch['error']}) - model defaults are "
            "ignored; fix or remove .mw/dispatch.yml"
        )
    # A role whose model cannot read images is a suggestion, never an issue:
    # dispatch defaults are a convenience, and an issue here would flip
    # summary.healthy and make every doctor run exit 1 (AC-010).
    # AC-010 scopes the capability verdict to the `vision` role only: the text
    # roles (main/coding/review/research) do not need image input (image tasks
    # are auto-routed or dispatched as `type: vision`), so flagging them would
    # be a false positive plus permanent noise on every doctor run.
    dispatch_images = dispatch.get("images") or {}
    for role_name, value in sorted((dispatch.get("models") or {}).items()):
        if role_name != "vision" or dispatch_images.get(role_name) != "no":
            continue
        suggestions.append(
            f"dispatch role {role_name} uses {value}, which cannot read images "
            f"(images=no) - run 'mw model set vision <vision-model>' and re-dispatch "
            f"with that role, or give '{role_name}' an image-capable model"
        )
    # fallback_models (mw-model-error-perception D5): a malformed block is an
    # ISSUE (unlike the fail-soft `models` default) — a bad fallback silently
    # degrades model-failure recovery, so doctor must surface it. A missing
    # route/credential is only a suggestion: the launcher's dispatch-time
    # precheck skips an unusable fallback, so it never blocks a worker.
    if dispatch.get("fallback_error"):
        issues.append(
            f"dispatch.yml fallback_models unusable ({dispatch['fallback_error']}) - "
            "fallback models will be ignored; fix or remove the block in .mw/dispatch.yml"
        )
    fallback_routes = {
        r["route"]: r for r in (report.get("credentials") or {}).get("routes", [])
    }
    for task_type, values in sorted((dispatch.get("fallback_models") or {}).items()):
        for value in values:
            prefix, _model = parse_model_value(value)
            route_name = FALLBACK_PREFIX_TO_ROUTE.get(prefix)
            route = fallback_routes.get(route_name) if route_name else None
            if route is None:
                suggestions.append(
                    f"dispatch fallback_models.{task_type} uses {value}, whose route "
                    f"({route_name or prefix}) is not configured - add it to providers.json "
                    "or remove the fallback"
                )
            elif not route.get("available"):
                suggestions.append(
                    f"dispatch fallback_models.{task_type} uses {value}, whose credential "
                    f"is missing ({route.get('missing')}) - the launcher skips it at dispatch "
                    "time; provide the credential or remove the fallback"
                )
    if report["orphan_proxy"]["detected"]:
        ports = ", ".join(str(p["port"]) for p in report["orphan_proxy"]["ports"])
        suggestions.append(
            f"proxy port(s) {ports} bound while mw not running (orphan) - "
            "start mw to adopt them or kill the owning process"
        )
    missing_routes = [
        f"{r['route']} ({r['missing']})" for r in report["credentials"]["routes"] if not r["available"]
    ]
    if missing_routes:
        suggestions.append(
            "routes without credentials (env of the mw process): " + "; ".join(missing_routes)
        )
    if report["launcher_log"].get("error_count"):
        suggestions.append(
            f"launcher.log has {report['launcher_log']['error_count']} error line(s) - inspect the tail"
        )
    # AC-009 (mw-worktree-junction-guard T-W03): a leftover junction pointing
    # into this repo is a real hazard (the incident form), and a registry entry
    # whose link vanished is a silent loss of the cleanup handle. One issue per
    # finding, carrying path + kind; an empty section adds nothing (reverse
    # control: a clean repo keeps rc unchanged).
    worktree_links = report.get("worktree_links") or {}
    for entry in worktree_links.get("leftover") or []:
        issues.append(
            f"worktree-leftover ({entry['kind']}): {entry['path']} -> {entry['target']} - "
            "a junction pointing into this repo survived its worktree; clear it with "
            "'mw worktree rm <worktree>' before it is reused or removed (AC-009)"
        )
    for entry in worktree_links.get("stale_entries") or []:
        issues.append(
            f"worktree-stale-entry ({entry['kind']}): registry entry {entry['path']} -> "
            f"{entry['target']} has no link on disk - re-run 'mw worktree add --link-deps' "
            "or drop the entry (AC-009)"
        )
    # AC-015 (mw-worktree-junction-guard T-W13/D-14): a corrupt/unreadable
    # registry is folded into the section by `_registry_domain`; without this
    # consumption the text face only printed on `count>0` and the issue list
    # ignored the field, so a broken registry was silent (contradicting design
    # §5.1 "bad file => raise, never silently read as an empty table"). The
    # error summary and the registry path are both in the issue because the
    # path is what a reader needs to fix or remove.
    registry_error = worktree_links.get("registry_error")
    if registry_error:
        issues.append(
            f"worktree-registry-error: {registry_error} - the junction registry at "
            f"{worktree_links.get('registry_path')} could not be read, so leftover-link "
            "detection is degraded (fail-closed); fix or remove the file (AC-015)"
        )
    # AC-016 (mw-worktree-junction-guard T-W13/D-15): activation self-check. A
    # bundle without the G1 capability marker means the guard exists in source
    # but is not deployed to the runtime pi actually loads. The section is only
    # built for a checkout owning the extension source
    # (`_activation_bundle_paths`); a minimal report without the key stays
    # silent. The serve-side half of AC-016 is covered by the existing
    # `serve code: STALE CODE` verdict in `mw.py cmd_doctor` - reused there,
    # not duplicated here.
    activation = report.get("activation") or {}
    if activation.get("applicable"):
        for entry in activation.get("checked") or []:
            if entry.get("has_marker") is True:
                continue
            role = entry.get("role") or "installed"
            fix = _activation_fix(role)
            if entry.get("exists") is False:
                detail = "bundle file missing"
            elif entry.get("error"):
                detail = f"unverifiable ({entry['error']})"
            else:
                # D-18: name the marker(s) that are actually absent so a reader
                # can tell a dropped `user_bash` hook from a dropped decision
                # marker instead of getting one generic "guard not deployed".
                names = ", ".join(
                    f"'{marker}'" for marker in entry.get("missing_markers") or []
                )
                detail = f"capability marker(s) absent: {names}"
            # D-18 C9: the two copies have different roles, so the same finding
            # means a different missing step. The dist copy is staging pi never
            # loads; only the installed copy is the runtime bundle.
            if role == "dist":
                meaning = (
                    "this is the tracked build artifact under packages/multi-workers/dist "
                    "(pi does not load this copy), so it only means 'mw build' has not run"
                )
            else:
                meaning = (
                    "this is the installed bundle pi actually loads, so it means "
                    "'mw build --install' has not run"
                )
            issues.append(
                f"guard-not-deployed: {entry.get('path')} - {detail}; {meaning}; "
                f"run '{fix}' (AC-016)"
            )
    # design §6.1 AC-010 action (3) (mw-worktree-junction-guard T-W09): the
    # resident watch already alarms on a tracked-file collapse, but the alarm
    # only reaches `.mw/launcher.log`. When the same sampling window also moved
    # the junction inventory (the incident fingerprint: teardown + reify), the
    # event is upgraded here so a `mw doctor` reader sees it and rc flips.
    # Fail-open-to-verdict, like the registry read above: a missing / corrupt /
    # wrong-typed state file or event is silently skipped, never raised - the
    # doctor must always produce a verdict. The project root is derived from
    # the adjacent `worktree_links.registry_path` (`<project>/.mw/...`); the
    # local `import tree_watch` follows the `import worktree_doctor` precedent
    # in `doctor_report` and keeps this consumption point self-contained.
    try:
        import tree_watch
    except ImportError:  # pragma: no cover - same-dir module, mirrors doctor_report
        tree_watch = None
    registry_path = worktree_links.get("registry_path")
    watched_project = (
        pathlib.Path(registry_path).parent.parent
        if isinstance(registry_path, str) and registry_path
        else None
    )
    state: dict = {}
    if tree_watch is not None and watched_project is not None:
        try:
            loaded = json.loads(
                tree_watch.state_path(watched_project).read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, ValueError):
            loaded = {}
        if isinstance(loaded, dict):
            state = loaded
    raw_events = state.get("events")
    if tree_watch is not None and watched_project is not None and isinstance(raw_events, list):
        now = time.time()
        for event in raw_events:
            if not isinstance(event, dict) or event.get("kind") != "collapse":
                continue
            ts = event.get("ts")
            if ts is None:
                # Older events carry no per-event stamp; the state file's
                # top-level `ts` is that sample's sampling time.
                ts = state.get("ts")
            if isinstance(ts, bool) or not isinstance(ts, (int, float)):
                continue
            age = now - float(ts)
            if age < 0 or age > TREE_WATCH_ISSUE_WINDOW_SEC:
                continue
            raw_delta = event.get("link_delta")
            if not isinstance(raw_delta, dict):
                continue
            counts = {
                key: raw_delta.get(key, 0) for key in ("removed", "changed", "added")
            }
            if any(isinstance(value, bool) or not isinstance(value, int) for value in counts.values()):
                continue
            if sum(counts.values()) <= 0:
                continue
            issues.append(
                f"tree-watch-collapse: tracked-file collapse (ts={ts}, "
                f"deleted_non_dist={event.get('deleted_non_dist')}, "
                f"delta={event.get('delta')}) with a same-window junction-inventory "
                f"change (removed/changed/added="
                f"{counts['removed']}/{counts['changed']}/{counts['added']}) - "
                "the AC-010 incident fingerprint (teardown + reify); inspect "
                f"{tree_watch.state_path(watched_project)} and clear leftovers with "
                "'mw worktree rm'"
            )
    return issues, suggestions


def doctor_report(
    project_dir: pathlib.Path,
    fix: bool = False,
    config: dict | None = None,
    stale_after_sec: int = 90,
    worktree_scan_roots: list[str] | None = None,
) -> dict:
    """Full diagnostic snapshot. Local-only checks (no network), <5s.

    Sections: service, proxy, proxy_log, orphan_proxy, launcher_log, queue,
    worker_liveness, credentials, bundle (+ fix when fix=True), summary.
    healthy=True iff no issues; worker_liveness is informational and never
    flips healthy/exit codes."""
    project_dir = pathlib.Path(project_dir)
    if config is None:
        config = load_providers(pathlib.Path(__file__).parent / "providers.json")
    report: dict = {}
    if fix:
        report["fix"] = {"applied": doctor_fix(project_dir)}
    report["service"] = _doctor_service(project_dir)
    report["proxy"] = _doctor_proxy(config)
    report["proxy_log"] = _doctor_proxy_log(project_dir)
    report["orphan_proxy"] = _doctor_orphan(report["service"], report["proxy"])
    report["launcher_log"] = _doctor_launcher_log(project_dir)
    report["queue"] = _doctor_queue(project_dir)
    report["worker_liveness"] = worker_liveness(project_dir, stale_after_sec)
    report["credentials"] = route_precheck(config, os.environ)
    report["bundle"] = _doctor_bundle()
    report["target"] = _doctor_target(project_dir)
    report["autopilot"] = _doctor_autopilot(project_dir)
    report["gates"] = _doctor_gates(project_dir)
    report["dispatch"] = _doctor_dispatch(project_dir)
    report["pi_shell"] = ensure_pi_shell_path(env=os.environ, fix=fix)
    if fix and report["pi_shell"].get("status") in ("filled", "replaced"):
        report["fix"]["applied"].append(
            f"pi settings.json shellPath {report['pi_shell']['status']}: "
            f"{report['pi_shell']['shell_path']}"
        )
    # AC-009 (mw-worktree-junction-guard T-W03): leftover junction scan. The
    # import is deliberately function-local: worktree_registry imports mw_common
    # at module top level, so a module-level import of worktree_doctor (which
    # imports worktree_registry) would close an import cycle. doctor_report is a
    # runtime entry point, so the local import is safe and cheap (sys.modules).
    import worktree_doctor
    report["worktree_links"] = worktree_doctor.build_section(
        project_dir, scan_roots=worktree_scan_roots
    )
    # AC-016 (T-W13/D-15): activation self-check for the two deployed bundles.
    # Built here (the doctor assembly face) so `_doctor_issues` only consumes a
    # section and remains silent when handed a minimal report.
    report["activation"] = _doctor_activation(project_dir)
    issues, suggestions = _doctor_issues(report)
    report["summary"] = {"healthy": not issues, "issues": issues, "suggestions": suggestions}
    return report


def format_doctor_text(report: dict) -> str:
    """Human-readable one-line-per-finding text output (doctor CLI)."""
    lines: list[str] = []
    svc = report["service"]
    lines.append(
        f"service: {'running (PID ' + str(svc['pid']) + ')' if svc['running'] else 'not running'}"
    )
    for p in report["proxy"]:
        lines.append(f"proxy: {p['route']} port {p['port']} {'LISTENING' if p['listening'] else 'not listening'}")
    avail_routes = {
        r["route"] for r in report.get("credentials", {}).get("routes", []) if r.get("available")
    }
    if report["proxy"] and not any(p["route"] in avail_routes for p in report["proxy"]):
        lines.append("proxy: disabled (no proxy-routed credentials; direct routes only)")
    plog = report.get("proxy_log") or {}
    if plog.get("last_error"):
        lines.append(f"proxy_log: {plog['traceback_count']} crash(es), last: {plog['last_error']}")
    else:
        lines.append("proxy_log: ok" if plog.get("exists") else "proxy_log: no log file")
    orphan = report["orphan_proxy"]
    if orphan["detected"]:
        ports = ", ".join(
            f"{p['port']} (pid {p.get('owner_pids')})" for p in orphan["ports"]
        )
        lines.append(f"orphan_proxy: ports {ports} bound while mw not running")
    else:
        lines.append("orphan_proxy: none")
    log = report["launcher_log"]
    if log["exists"]:
        lines.append(
            f"launcher_log: {log['error_count']} error line(s), fatal={log['fatal']} "
            f"(tail: {' | '.join(log['tail'][-3:])})"
        )
    else:
        lines.append("launcher_log: no log file")
    queue = report["queue"]
    queue_line = (
        f"queue: {queue['non_terminal_count']} non-terminal task(s), "
        f"{queue['stale_count']} stale, {queue['archived_total']} archived"
    )
    # Zero-perturbation: healthy queues keep the historical byte-identical line.
    if queue.get("unparsable_count"):
        queue_line += f", {queue['unparsable_count']} unparsable"
    lines.append(queue_line)
    liveness = report.get("worker_liveness", [])
    if liveness:
        alive = sum(1 for v in liveness if v["verdict"] == "alive")
        stale = [v["task_key"] for v in liveness if v["verdict"] == "stale"]
        no_hb = sum(1 for v in liveness if v["verdict"] == "no-heartbeat")
        parts = [f"alive {alive}"]
        if stale:
            parts.append(f"stale: {', '.join(stale)}")
        if no_hb:
            parts.append(f"no-heartbeat {no_hb}")
        lines.append("workers: " + ", ".join(parts))
    # Target workspace row (mw-dual-workspace D-011/D-013)
    target = report.get("target")
    if target is not None:
        if target.get("error") is not None:
            err = target["error"]
            lines.append(f"target: ERROR {err['kind']}: {err['message']}")
        else:
            cfg = target["config"]
            if cfg["mode"] == "partition":
                # mw-target-partition: parent/partition replace the game row
                # (game_root is null in partition mode); dual/single rows are
                # untouched (AC-016e text parity).
                roots = f"parent={cfg['parent_root']} partition={cfg['partition_root']}"
                named = cfg.get("roots") or {}
                if named:
                    roots += " roots=" + ",".join(f"{k}:{v}" for k, v in named.items())
            else:
                roots = f"game={cfg['game_root']}"
                if cfg["engine_root"]:
                    roots += f" engine={cfg['engine_root']}"
            lines.append(f"target: {cfg['mode']} (source {cfg['source']}) {roots}")
            checks = target.get("checks")
            if checks:
                state = ", ".join(
                    f"{c['name']} {'ok' if c['ok'] else 'FAIL: ' + c['detail']}" for c in checks
                )
                lines.append(f"target_toolchain: {state} ({target.get('probe_cache')})")
    # Conductor row (D-101, injected by mw.py cmd_doctor): informational —
    # not running simply means autopilot is disabled for this project.
    conductor = report.get("conductor")
    if conductor is not None:
        if conductor["running"]:
            lines.append(
                f"conductor: running (PID {conductor['pid']}, "
                f"last tick seq={conductor['last_seq']} ts={conductor['last_ts']})"
            )
        else:
            lines.append("conductor: not running")
    # Autopilot verify row: emitted only when the fail-loud condition holds,
    # so an xkey_repair=false project keeps the existing text output unchanged
    # (AC-012 zero-perturbation).
    autopilot = report.get("autopilot")
    if autopilot is not None and autopilot.get("xkey_verify_missing"):
        lines.append(
            "autopilot: xkey_repair enabled but verify command empty - "
            "run 'mw autopilot verify set --project <dir> -- <argv...>'"
        )
    # Gate queue row: emitted only when I1-I6 fire, so a fully healthy project
    # keeps the existing text output unchanged (I7 zero-perturbation).
    gates_section = report.get("gates")
    if gates_section is not None and _gates_text_alerted(gates_section):
        pending = gates_section.get("pending") or []
        oldest = max((_gate_node_value(e.get("waited_s")) or 0) for e in pending) if pending else 0
        crosskey_prose_only = (gates_section.get("crosskey_prose") or {}).get("prose_only") or 0
        prose_suffix = (
            f", {crosskey_prose_only} prose-only cross-key" if crosskey_prose_only else ""
        )
        contract_unauthorized = (
            (gates_section.get("contract_guard") or {}).get("unauthorized") or 0
        )
        contract_suffix = (
            f", {contract_unauthorized} contract-guard" if contract_unauthorized else ""
        )
        # T-08 / AC-001 (C8): the suffix is the only textual surface of
        # `blocked_on_human`; it appears iff the field is true.
        blocked_suffix = " BLOCKED_ON_HUMAN" if gates_section.get("blocked_on_human") else ""
        lines.append(
            f"gates: {gates_section['pending_count']} pending "
            f"({_gate_waited_text(oldest)} oldest, "
            f"{len(gates_section.get('parse_errors') or [])} parse error(s), "
            f"{len(gates_section.get('drift') or [])} drift{prose_suffix}{contract_suffix})"
            f"{blocked_suffix}"
        )
    # AC-009 (T-W03): leftover junction rows; emitted only when the section has
    # findings, so a clean repo keeps the historical text byte-identical.
    worktree_links = report.get("worktree_links")
    if worktree_links and worktree_links.get("count"):
        for entry in worktree_links.get("leftover") or []:
            lines.append(
                f"worktree_links: LEFTOVER ({entry['kind']}) {entry['path']} -> {entry['target']}"
            )
        for entry in worktree_links.get("stale_entries") or []:
            lines.append(
                f"worktree_links: STALE-ENTRY ({entry['kind']}) {entry['path']} -> {entry['target']}"
            )
    # AC-015 (T-W13/D-14): a corrupt registry must print even when `count==0`
    # (zero findings because the read failed is exactly the case that used to
    # be silent). Reverse control: a healthy/absent registry adds no line.
    if worktree_links and worktree_links.get("registry_error"):
        lines.append(
            f"worktree_links: REGISTRY-ERROR {worktree_links.get('registry_path')}: "
            f"{worktree_links['registry_error']}"
        )
    # AC-016 (T-W13/D-15): activation rows; emitted only for bundles without the
    # marker, so a deployed runtime keeps the historical output byte-identical.
    activation = report.get("activation")
    if activation and activation.get("applicable"):
        for entry in activation.get("checked") or []:
            if entry.get("has_marker") is True:
                continue
            # D-18 C9: name the right fix per copy (dist = staging, installed =
            # the runtime bundle pi loads).
            fix = _activation_fix(entry.get("role") or "installed")
            path = entry.get("path")
            if entry.get("exists") is False:
                lines.append(f"activation: MISSING {path} - run '{fix}'")
                continue
            if entry.get("error"):
                lines.append(
                    f"activation: UNVERIFIABLE ({entry['error']}) {path} - run '{fix}'"
                )
                continue
            # D-18: one row per absent marker, each naming the marker so the
            # missing `user_bash` hook is visible on its own.
            for marker in entry.get("missing_markers") or []:
                lines.append(
                    f"activation: MARKER-ABSENT '{marker}' {path} - run '{fix}'"
                )
    # pi shellPath row (fresh-machine shell bootstrap)
    pi_shell = report.get("pi_shell")
    if pi_shell is not None:
        status = pi_shell.get("status")
        if status == "ok":
            lines.append(f"pi_shell: {pi_shell.get('shell_path')}")
        elif status == "not-applicable":
            lines.append("pi_shell: not applicable (non-Windows)")
        else:
            lines.append(f"pi_shell: {status} — {pi_shell.get('detail')}")
    # dispatch model config row (silent when nothing is configured)
    dispatch = report.get("dispatch")
    if dispatch is not None and dispatch.get("exists"):
        if dispatch.get("error"):
            lines.append(f"dispatch: ERROR — {dispatch['error']}")
        else:
            capabilities = dispatch.get("images") or {}
            roles = ", ".join(
                f"{role}={value} images={capabilities.get(role) or 'unknown'}"
                for role, value in sorted((dispatch.get("models") or {}).items())
            ) or "no roles set"
            window = dispatch.get("window_model") or "(none recorded)"
            lines.append(f"dispatch: {roles}; window model {window}")
        # fallback row: emitted only when a fallback block exists, so an
        # unconfigured project keeps the historical text byte-identical.
        fallbacks = dispatch.get("fallback_models") or {}
        if dispatch.get("fallback_error"):
            lines.append(f"dispatch_fallback: ERROR — {dispatch['fallback_error']}")
        elif fallbacks:
            rendered = "; ".join(
                f"{task_type}={','.join(values)}"
                for task_type, values in sorted(fallbacks.items())
            )
            lines.append(f"dispatch_fallback: {rendered}")
    for r in report["credentials"]["routes"]:
        state = "available (" + _source_desc(r["source"]) + ")" if r["available"] else "missing (" + str(r["missing"]) + ")"
        lines.append(f"credentials: {r['route']} {state}")
    bundle = report["bundle"]
    if bundle.get("available"):
        if bundle.get("source_available"):
            lines.append(
                f"bundle: global mtime {bundle['global_bundle_mtime']}, "
                f"source newest {bundle['source_newest_mtime']}, stale={bundle['stale']}"
            )
        else:
            lines.append(f"bundle: global mtime {bundle['global_bundle_mtime']} ({bundle.get('note')})")
    else:
        lines.append(f"bundle: {bundle.get('note')}")
    if "fix" in report:
        applied = report["fix"]["applied"]
        lines.append("fix: " + ("; ".join(applied) if applied else "nothing to auto-fix"))
    summary = report["summary"]
    lines.append(f"summary: {'healthy' if summary['healthy'] else 'ISSUES: ' + '; '.join(summary['issues'])}")
    for s in summary["suggestions"]:
        lines.append(f"suggest: {s}")
    return "\n".join(lines)


# ── Dual-workspace target config (mw-dual-workspace D-002/D-010/D-011/D-014) ───

# Parity module: mirrors packages/coding-agent/src/extensions/agent-team-loop/
# shared/target-config.ts 1:1 (T-17 pattern). Field names in the returned dict
# are snake_case twins of the TS interface; parity is asserted by the shared
# fixtures under test/fixtures/target-config-cases/ (kind + key facts, not
# message text).

ENV_TARGET_GAME = "MW_TARGET_GAME"
ENV_TARGET_ENGINE = "MW_TARGET_ENGINE"
# mw-target-partition env overrides (spec §1.5 EP family; only honored when
# partition is the active mode — cross-family env is a rule-table row 3 error).
ENV_PARTITION_PARENT = "MW_PARTITION_PARENT"
ENV_PARTITION_ROOT = "MW_PARTITION_ROOT"

# Error kinds — the parity contract. Both sides raise these exact tokens.
_TARGET_KINDS = (
    "invalid-yaml",
    "invalid-config",
    "missing-field",
    "uproject-not-found",
    "ambiguous-uproject",
)


class TargetConfigError(Exception):
    """Fail-closed target.yml / env resolution error (see _TARGET_KINDS)."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def _tc_fail(kind: str, message: str) -> None:
    raise TargetConfigError(kind, message)


def _tc_require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or value.strip() == "":
        _tc_fail("invalid-config", f"target.yml: field '{field}' must be a non-empty string")
    return value


def _tc_optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _tc_require_string(value, field)


def _tc_string_array(value: object, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(
        not isinstance(e, str) or e.strip() == "" for e in value
    ):
        _tc_fail("invalid-config", f"target.yml: field '{field}' must be a list of non-empty strings")
    return list(value)


def _tc_normalize_root(raw: str, control_root: str) -> str:
    """Resolve against control_root, then realpath when it exists (junction/
    case folding parity with the TS normalizeRoot)."""
    resolved = os.path.normpath(os.path.join(control_root, raw))
    return str(pathlib.Path(resolved).resolve())


def target_yml_path(control_root: pathlib.Path | str) -> pathlib.Path:
    return pathlib.Path(control_root) / ".agenticdoc" / "target.yml"


def _tc_read_target_yml(control_root: str) -> dict:
    path = target_yml_path(control_root)
    if not path.exists():
        return {}
    if yaml is None:
        _tc_fail(
            "invalid-config",
            "PyYAML is required to read target.yml (mw doctor checks this); "
            "install it or unset MW_TARGET_GAME to stay in single mode",
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        _tc_fail("invalid-yaml", f"target.yml unreadable ({path}): {e}")
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as e:  # type: ignore[union-attr]
        _tc_fail("invalid-yaml", f"target.yml is not valid YAML ({path}): {e}")
    if parsed is None:
        # mw-target-partition FIX-10: a non-blank document that parses to
        # YAML null (`null` / `~`) is a non-mapping top level — fail closed
        # like the list/scalar shapes. Only a blank file (0 bytes, pure
        # whitespace, or a leading UTF-8 BOM with no content — the degenerate
        # Windows-editor shape) keeps the historical no-config shape (single).
        if text.strip() == "" or text.lstrip("\ufeff").strip() == "":
            return {}
        _tc_fail("invalid-config", "target.yml: top level must be a mapping")
    if not isinstance(parsed, dict):
        _tc_fail("invalid-config", "target.yml: top level must be a mapping")
    return parsed


def _tc_parse_toolchain(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        _tc_fail("invalid-config", "target.yml: 'toolchain' must be a mapping of name to command")
    out: dict[str, str] = {}
    for name, cmd in value.items():
        if not isinstance(cmd, str) or cmd.strip() == "":
            _tc_fail("invalid-config", f"target.yml: toolchain.{name} must be a non-empty string")
        out[str(name)] = cmd
    return out


def _tc_parse_ignore(value: object) -> dict:
    if value is None:
        return {"deny_globs": []}
    if not isinstance(value, dict):
        _tc_fail("invalid-config", "target.yml: 'ignore' must be a mapping")
    return {"deny_globs": _tc_string_array(value.get("deny_globs"), "ignore.deny_globs")}


def _tc_parse_contract(value: object) -> dict:
    if value is None:
        return {"forbidden_paths": [], "conventions": None, "docs": []}
    if not isinstance(value, dict):
        _tc_fail("invalid-config", "target.yml: 'contract' must be a mapping")
    conventions = value.get("conventions")
    if conventions is not None and not isinstance(conventions, str):
        _tc_fail("invalid-config", "target.yml: contract.conventions must be a string")
    return {
        "forbidden_paths": _tc_string_array(value.get("forbidden_paths"), "contract.forbidden_paths"),
        "conventions": conventions,
        "docs": _tc_string_array(value.get("docs"), "contract.docs"),
    }


# ── v2 single-file format (mw-target-partition spec §1.3/§1.5, design
# D-001..D-004) ──────────────────────────────────────────────────────────────

# Rule-table row 1: a v2 file (top-level `active:`) must not carry v1 flat
# fields alongside.
_V1_SHAPE_KEYS = ("mode", "game", "engine", "uproject")
# v2 top-level whitelist (AC-003(c)).
_V2_TOP_KEYS = frozenset(("active", "dual", "partition"))
# Mode-block whitelists (AC-003(d)/(e)).
_DUAL_BLOCK_KEYS = frozenset(("game", "engine", "vcs", "uproject", "toolchain", "ignore", "contract"))
_PARTITION_BLOCK_KEYS = frozenset(("parent", "partition", "vcs", "roots", "toolchain", "ignore", "contract"))
# roots key constraints (AC-003(f)).
_ROOTS_RESERVED = frozenset(("parent", "partition", "game", "engine", "uproject"))
_ROOTS_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
# Placeholder-shaped token in a partition toolchain command (AC-004).
_TOKEN_RE = re.compile(r"\{([A-Za-z0-9_-]+)\}")


def _tc_detect_shape(raw: dict, file_exists: bool) -> str:
    """File-shape judgment (design D-001) + rule-table row 1: "none" when no
    target.yml exists, "v2" when the top level has an `active:` key (a v1
    flat field alongside raises the mixed-format error), else "v1"."""
    if not file_exists:
        return "none"
    if "active" in raw:
        mixed = [k for k in _V1_SHAPE_KEYS if k in raw]
        if mixed:
            _tc_fail(
                "invalid-config",
                "target.yml: mixed format — 'active:' key (v2) together with v1 top-level "
                f"field(s) {', '.join(mixed)}; use either v2 (active + mode blocks) or "
                "v1 (flat fields), not both",
            )
        return "v2"
    return "v1"


def _decide_active_mode(
    file_shape: str,
    active: str | None,
    env_partition_parent: str | None,
    env_partition_root: str | None,
    env_target_game: str | None,
    env_target_engine: str | None,
) -> dict:
    """Spec §1.5 rule-table decision, rows 2-12 (row order is priority).

    Rows 1 and 4 are not expressible from these inputs and are enforced by
    the caller: row 1 (mixed format) in _tc_detect_shape, row 4 (active
    names a mode whose block is missing) when the caller parses the block
    this function points at.

    Returns {"mode": ..., "block": ...}: mode is the workspace mode for v2
    shapes, or "legacy" for rows 8/11/12 (the caller runs the pre-partition
    v1/env resolution unchanged); block names the v2 mode block to parse
    (rows 6/7) or None. Raises TargetConfigError(invalid-config) for rows
    2/3/10 with the table's message elements (illegal active value + enum /
    conflicting env names / missing env name)."""
    ep: list[str] = []
    if env_partition_parent is not None:
        ep.append(ENV_PARTITION_PARENT)
    if env_partition_root is not None:
        ep.append(ENV_PARTITION_ROOT)
    et: list[str] = []
    if env_target_game is not None:
        et.append(ENV_TARGET_GAME)
    if env_target_engine is not None:
        et.append(ENV_TARGET_ENGINE)

    if file_shape == "v2":
        if active is None or active not in ("single", "dual", "partition"):  # row 2
            shown = "null" if active is None else f"'{active}'"
            _tc_fail(
                "invalid-config",
                f"target.yml: 'active' must be one of 'single', 'dual', 'partition', got {shown}",
            )
        if active == "dual" and ep:  # row 3
            _tc_fail(
                "invalid-config",
                f"cross env: {', '.join(ep)} must not be set when active is 'dual' "
                "(dual mode uses MW_TARGET_GAME/MW_TARGET_ENGINE)",
            )
        if active == "partition" and et:  # row 3
            _tc_fail(
                "invalid-config",
                f"cross env: {', '.join(et)} must not be set when active is 'partition' "
                "(partition mode uses MW_PARTITION_PARENT/MW_PARTITION_ROOT)",
            )
        if active == "single" and (ep or et):  # row 3
            _tc_fail(
                "invalid-config",
                f"cross env: {', '.join(ep + et)} must not be set when active is 'single'",
            )
        if active == "single":  # row 5
            return {"mode": "single", "block": None}
        return {"mode": active, "block": active}  # rows 6/7
    if file_shape == "v1":
        if ep:  # row 3 (v1 clause)
            _tc_fail(
                "invalid-config",
                f"cross env: {', '.join(ep)} requires a v2 target.yml with "
                "'active: partition' (v1 format has no partition mode)",
            )
        return {"mode": "legacy", "block": None}  # row 8
    # file_shape == "none"
    if ep and et:  # row 3 (no-file clause)
        _tc_fail(
            "invalid-config",
            f"cross env: {', '.join(ep)} and {', '.join(et)} are mutually exclusive "
            "(partition env vs dual env); set only one family",
        )
    if len(ep) == 2:  # row 9
        return {"mode": "partition", "block": None}
    if len(ep) == 1:  # row 10
        missing = ENV_PARTITION_ROOT if env_partition_root is None else ENV_PARTITION_PARENT
        _tc_fail(
            "invalid-config",
            f"incomplete partition env activation: {missing} is not set "
            "(partition env requires both MW_PARTITION_PARENT and MW_PARTITION_ROOT)",
        )
    return {"mode": "legacy", "block": None}  # rows 11/12


def _tc_check_v2_top_whitelist(raw: dict) -> None:
    """AC-003(c): the v2 top level allows exactly active/dual/partition."""
    extra = [str(k) for k in raw if k not in _V2_TOP_KEYS]
    if extra:
        _tc_fail(
            "invalid-config",
            f"target.yml: unexpected top-level key(s) in v2 format: {', '.join(extra)} "
            "(allowed: active, dual, partition)",
        )


def _tc_v2_block(raw: dict, name: str) -> dict:
    """Rule-table row 4: active names a mode whose block must exist."""
    if name not in raw or raw.get(name) is None:
        _tc_fail("invalid-config", f"target.yml: active '{name}' but the '{name}' block is missing")
    block = raw[name]
    if not isinstance(block, dict):
        _tc_fail("invalid-config", f"target.yml: the '{name}' block must be a mapping")
    return block


def _tc_check_block_keys(block: dict, name: str, allowed: frozenset) -> None:
    """AC-003(d)/(e): mode-block whitelists (fields of the other mode — or
    any unknown key — inside a block are a structural error)."""
    extra = [str(k) for k in block if k not in allowed]
    if extra:
        _tc_fail(
            "invalid-config",
            f"target.yml: unexpected key(s) in the '{name}' block: {', '.join(extra)}",
        )


def _tc_parse_roots(value: object, control_root: str) -> dict[str, str]:
    """partition.roots (AC-001/AC-003(f)): name -> normalized path; names
    must match [A-Za-z0-9_-]+ and avoid the reserved names; relative paths
    anchor to the control root (same rule as game/engine)."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        _tc_fail("invalid-config", "target.yml: partition field 'roots' must be a mapping of name to path")
    out: dict[str, str] = {}
    for name, raw_path in value.items():
        if not isinstance(name, str):
            _tc_fail("invalid-config", "target.yml: roots keys must be strings")
        if name == "" or _ROOTS_NAME_RE.match(name) is None or name in _ROOTS_RESERVED:
            _tc_fail(
                "invalid-config",
                f"target.yml: roots key '{name}' is invalid (must match [A-Za-z0-9_-]+ and "
                "must not be a reserved name: parent, partition, game, engine, uproject)",
            )
        if not isinstance(raw_path, str) or raw_path.strip() == "":
            _tc_fail("invalid-config", f"target.yml: roots.{name} must be a non-empty string")
        out[name] = _tc_normalize_root(raw_path, control_root)
    return out


def _tc_check_root_relation(parent_root: str, partition_root: str) -> None:
    """AC-003(g): parent and partition must be distinct and non-nested
    (compared on the normalized roots, case-insensitive on Windows)."""
    a = os.path.normcase(os.path.normpath(parent_root))
    b = os.path.normcase(os.path.normpath(partition_root))
    if a == b or a.startswith(b + os.sep) or b.startswith(a + os.sep):
        _tc_fail(
            "invalid-config",
            f"target.yml: partition root relation is invalid — parent ({parent_root}) and "
            f"partition ({partition_root}) must not be equal or nested",
        )


def _load_partition_config(
    control_root: str,
    control_norm: str,
    parent_raw: object,
    partition_raw: object,
    env_parent: str | None,
    env_partition: str | None,
    roots_raw: object,
    vcs_raw: object,
    toolchain_raw: object,
    ignore_raw: object,
    contract_raw: object,
) -> dict:
    """Partition-mode assembly (rule-table rows 7/9): EP overlay over the
    block fields, required-field checks, roots + root-relation validation
    (field layer, applied after the row hit)."""
    if env_parent is not None:
        parent_raw = env_parent
    if env_partition is not None:
        partition_raw = env_partition
    if parent_raw is None:
        _tc_fail(
            "invalid-config",
            "target.yml: partition mode requires field 'parent' "
            "(partition block or env MW_PARTITION_PARENT)",
        )
    if partition_raw is None:
        _tc_fail(
            "invalid-config",
            "target.yml: partition mode requires field 'partition' "
            "(partition block or env MW_PARTITION_ROOT)",
        )
    parent = _tc_require_string(parent_raw, "parent")
    partition = _tc_require_string(partition_raw, "partition")
    parent_root = _tc_normalize_root(parent, control_root)
    partition_root = _tc_normalize_root(partition, control_root)
    roots = _tc_parse_roots(roots_raw, control_root)
    _tc_check_root_relation(parent_root, partition_root)
    return {
        "mode": "partition",
        "control_root": control_norm,
        "game_root": None,
        "engine_root": None,
        "parent_root": parent_root,
        "partition_root": partition_root,
        "roots": roots,
        "vcs": _tc_optional_string(vcs_raw, "vcs"),
        "uproject": None,
        "toolchain": _tc_parse_toolchain(toolchain_raw),
        "ignore": _tc_parse_ignore(ignore_raw),
        "contract": _tc_parse_contract(contract_raw),
        "source": "env" if (env_parent is not None or env_partition is not None) else "target-yml",
    }


def _load_legacy_config(
    control_root: str,
    raw: dict,
    env_game: str | None,
    env_engine: str | None,
) -> dict:
    """v1 / no-file resolution — the pre-partition logic, byte-identical
    (spec §1.5 rows 8/11/12; AC-013 zero-regression)."""
    file_mode = _tc_optional_string(raw.get("mode"), "mode")
    if file_mode is not None and file_mode not in ("dual", "single"):
        _tc_fail("invalid-config", f"target.yml: 'mode' must be 'dual' or 'single', got '{file_mode}'")
    file_game = _tc_optional_string(raw.get("game"), "game")
    file_engine = _tc_optional_string(raw.get("engine"), "engine")

    game_raw = env_game if env_game is not None else file_game
    engine_raw = env_engine if env_engine is not None else file_engine

    # File-internal contradictions fail closed before precedence applies
    # (same order as the TS side — see the 001 task evidence note).
    if file_mode == "single" and file_game is not None:
        _tc_fail("invalid-config", "target.yml: mode 'single' with a 'game' field is contradictory")
    if file_mode == "dual" and file_game is None and env_game is None:
        _tc_fail(
            "invalid-config",
            "target.yml: mode 'dual' requires a game root (field 'game' or env MW_TARGET_GAME)",
        )

    mode = "dual" if game_raw is not None else "single"
    if engine_raw is not None and mode == "single":
        _tc_fail("invalid-config", "target.yml: 'engine' requires dual mode (configure 'game' first)")

    control_norm = _tc_normalize_root(control_root, control_root)
    game_root = _tc_normalize_root(game_raw, control_root) if mode == "dual" else control_norm
    if env_game is not None:
        source = "env"
    elif game_raw is not None or file_mode is not None:
        source = "target-yml"
    else:
        source = "default"
    return {
        "mode": mode,
        "control_root": control_norm,
        "game_root": game_root,
        "engine_root": None if engine_raw is None else _tc_normalize_root(engine_raw, control_root),
        "vcs": _tc_optional_string(raw.get("vcs"), "vcs"),
        "uproject": _tc_optional_string(raw.get("uproject"), "uproject"),
        "toolchain": _tc_parse_toolchain(raw.get("toolchain")),
        "ignore": _tc_parse_ignore(raw.get("ignore")),
        "contract": _tc_parse_contract(raw.get("contract")),
        "source": source,
    }


def load_target_config(
    control_root: pathlib.Path | str,
    env: Mapping[str, str] | None = None,
) -> dict:
    """Resolve the workspace config for a control root (single choke point,
    mw-target-partition design D-001; mirrors resolveWorkspaceConfig()).

    Shape first (spec §1.5): no target.yml -> none; top-level `active:` key
    -> v2 (v1 flat fields alongside raise the mixed-format error, row 1);
    else v1. _decide_active_mode then applies rows 2-12 and dispatches:
    legacy (v1/env semantics, byte-identical to the pre-partition resolver
    — rows 8/11/12), v2 single (blocks parked, row 5), v2 dual (block fields
    + MW_TARGET_GAME/MW_TARGET_ENGINE overlay, row 6), or partition
    (block/env fields + MW_PARTITION_PARENT/MW_PARTITION_ROOT overlay,
    rows 7/9). Raises TargetConfigError on contradictory or unusable
    configuration (fail-closed, never a silent single fallback)."""
    control_root = str(control_root)
    if env is None:
        env = os.environ
    raw = _tc_read_target_yml(control_root)
    file_exists = target_yml_path(control_root).exists()

    env_game = (env.get(ENV_TARGET_GAME) or "").strip() or None
    env_engine = (env.get(ENV_TARGET_ENGINE) or "").strip() or None
    env_parent = (env.get(ENV_PARTITION_PARENT) or "").strip() or None
    env_partition = (env.get(ENV_PARTITION_ROOT) or "").strip() or None

    file_shape = _tc_detect_shape(raw, file_exists)
    active: str | None = None
    if file_shape == "v2":
        active_raw = raw.get("active")
        if isinstance(active_raw, str):
            active = active_raw
        elif active_raw is not None:
            active = str(active_raw)

    decision = _decide_active_mode(file_shape, active, env_parent, env_partition, env_game, env_engine)

    if decision["mode"] == "legacy":
        config = _load_legacy_config(control_root, raw, env_game, env_engine)
        config["parent_root"] = None
        config["partition_root"] = None
        config["roots"] = None
        return config

    control_norm = _tc_normalize_root(control_root, control_root)

    if decision["mode"] == "single":
        # Row 5: mode blocks are parked (not parsed, not validated); the
        # top-level whitelist still applies (AC-003(c)).
        _tc_check_v2_top_whitelist(raw)
        return {
            "mode": "single",
            "control_root": control_norm,
            "game_root": control_norm,
            "engine_root": None,
            "parent_root": None,
            "partition_root": None,
            "roots": None,
            "vcs": None,
            "uproject": None,
            "toolchain": {},
            "ignore": {"deny_globs": []},
            "contract": {"forbidden_paths": [], "conventions": None, "docs": []},
            "source": "target-yml",
        }

    if decision["mode"] == "dual":
        # Row 6: fields from the dual block; the ET overlay keeps the legacy
        # precedence rules (env > block).
        block = _tc_v2_block(raw, "dual")  # row 4
        _tc_check_v2_top_whitelist(raw)
        _tc_check_block_keys(block, "dual", _DUAL_BLOCK_KEYS)
        config = _load_legacy_config(
            control_root,
            {
                "mode": "dual",
                "game": block.get("game"),
                "engine": block.get("engine"),
                "vcs": block.get("vcs"),
                "uproject": block.get("uproject"),
                "toolchain": block.get("toolchain"),
                "ignore": block.get("ignore"),
                "contract": block.get("contract"),
            },
            env_game,
            env_engine,
        )
        config["parent_root"] = None
        config["partition_root"] = None
        config["roots"] = None
        return config

    # decision["mode"] == "partition"
    if file_shape == "v2":
        # Row 7: fields from the partition block, EP overlay on top.
        block = _tc_v2_block(raw, "partition")  # row 4
        _tc_check_v2_top_whitelist(raw)
        _tc_check_block_keys(block, "partition", _PARTITION_BLOCK_KEYS)
        return _load_partition_config(
            control_root,
            control_norm,
            block.get("parent"),
            block.get("partition"),
            env_parent,
            env_partition,
            block.get("roots"),
            block.get("vcs"),
            block.get("toolchain"),
            block.get("ignore"),
            block.get("contract"),
        )
    # Row 9: partition activated purely by env (no file).
    return _load_partition_config(
        control_root, control_norm, None, None, env_parent, env_partition, None, None, None, None, None
    )


def describe_target_error(exc: TargetConfigError, control_root: pathlib.Path | str) -> str:
    """Dynamic unusable-config description (mw-target-partition D-007): the
    historical 'target.yml is unusable' wrapper is kept byte-identical for
    v1 files and no-file workspaces; a v2 file (top-level `active:`) names
    its active value so the refusal says which mode was being resolved.
    Shared by launcher (_worker_cwd) and autopilot/dispatch (dispatch) so
    both call sites stay in lockstep (the literal carries no test
    assertions)."""
    control_root = str(control_root)
    try:
        raw = _tc_read_target_yml(control_root)
    except TargetConfigError:
        raw = None
    if raw is not None and "active" in raw:
        active_raw = raw.get("active")
        if isinstance(active_raw, str):
            active = active_raw
        elif active_raw is None:
            active = "null"
        else:
            active = str(active_raw)
        return f"target.yml is unusable (active: {active}) ({exc.kind}): {exc}"
    return f"target.yml is unusable ({exc.kind}): {exc}"


def discover_uproject(game_root: str, explicit: str | None = None) -> str:
    """Resolve {uproject} (D-014): explicit field wins (must exist on disk);
    otherwise exactly one *.uproject under the game root. 0 or many is an
    error carrying the count — never a guess."""
    if explicit is not None:
        p = os.path.normpath(os.path.join(game_root, explicit))
        if not os.path.exists(p):
            _tc_fail("uproject-not-found", f"explicit uproject '{explicit}' not found under game root {game_root}")
        return str(pathlib.Path(p).resolve())
    try:
        entries = os.listdir(game_root)
    except OSError as e:
        _tc_fail("invalid-config", f"game root is not readable ({game_root}): {e}")
    matches = [e for e in entries if e.lower().endswith(".uproject")]
    if len(matches) != 1:
        detail = f" ({', '.join(matches)})" if len(matches) > 1 else ""
        _tc_fail(
            "ambiguous-uproject",
            f"expected exactly one *.uproject under game root {game_root}, found {len(matches)}{detail}",
        )
    return str(pathlib.Path(os.path.join(game_root, matches[0])).resolve())


def render_toolchain_command(command: str, config: dict) -> str:
    """Render one toolchain command template (AC-004, fail-closed) with the
    token set dispatched by mode (design D-002): partition replaces
    {parent}/{partition}/{<root name>} and any other placeholder-shaped
    token (including {game}/{engine}/{uproject}) raises missing-field with
    the token and the original command; dual/single keep the current
    {game}/{engine}/{uproject} replacement — a token whose root is
    unconfigured raises with the field name and the original command, no
    game-root fallback."""
    if config["mode"] == "partition":
        return _render_partition_command(command, config)
    out = command
    if "{game}" in out:
        out = out.replace("{game}", config["game_root"])
    if "{engine}" in out:
        if config["engine_root"] is None:
            _tc_fail(
                "missing-field",
                f"toolchain command references {{engine}} but engine is not configured "
                f"(dual mode requires it): {command}",
            )
        out = out.replace("{engine}", config["engine_root"])
    if "{uproject}" in out:
        uproject = discover_uproject(config["game_root"], config.get("uproject"))
        out = out.replace("{uproject}", uproject)
    return out


def _partition_token_names(roots: dict | None) -> list[str]:
    """Defined token names for partition mode: {parent}, {partition} and the
    sorted {<root name>} tokens. Shared with render_argv so both build the
    same "defines:" list (the toolchain error text is unchanged)."""
    return ["{parent}", "{partition}"] + ["{" + n + "}" for n in sorted(roots or {})]


def _render_partition_command(command: str, config: dict) -> str:
    """partition-mode token set (AC-004): {parent}/{partition}/{<root name>};
    any leftover placeholder-shaped token is an undefined placeholder."""
    out = command
    if config["parent_root"] is not None:
        out = out.replace("{parent}", config["parent_root"])
    if config["partition_root"] is not None:
        out = out.replace("{partition}", config["partition_root"])
    roots = config.get("roots") or {}
    for name, root_path in roots.items():
        out = out.replace("{" + name + "}", root_path)
    leftover = _TOKEN_RE.search(out)
    if leftover is not None:
        defined = _partition_token_names(roots)
        _tc_fail(
            "missing-field",
            f"toolchain command references undefined placeholder '{leftover.group(0)}' "
            f"(partition mode defines: {', '.join(defined)}): {command}",
        )
    return out


# verify-argv token sets for the non-partition modes (partition is dynamic:
# {control} + _partition_token_names(roots)).
_VERIFY_ARGV_DEFINED: dict[str, tuple[str, ...]] = {
    "dual": ("{control}", "{game}", "{engine}", "{uproject}"),
    "single": ("{control}", "{game}", "{uproject}"),
}


def render_argv(cmd: list[str], config: dict) -> list[str]:
    """Render a verification argv template (AC-014), fail-closed.

    The token set is the workspace mode's root tokens plus {control} — a
    verify-argv-only selector, so the toolchain contract is untouched. Unlike
    render_toolchain_command (whole-string replace with silent passthrough),
    every element must be either a literal or exactly one placeholder, and
    each referenced token must be defined/configured for the mode. Raises
    TargetConfigError("missing-field") for embedded, undefined or
    unconfigured placeholders; the error text always carries the original
    element."""
    mode = config.get("mode")
    if mode == "partition":
        roots = config.get("roots") or {}
        defined = ["{control}"] + _partition_token_names(roots)
        values: dict[str, str | None] = {
            "control": config.get("control_root"),
            "parent": config.get("parent_root"),
            "partition": config.get("partition_root"),
        }
        for name, root_path in roots.items():
            values[name] = root_path
    else:
        mode = "dual" if mode == "dual" else "single"
        defined = list(_VERIFY_ARGV_DEFINED[mode])
        values = {
            "control": config.get("control_root"),
            "game": config.get("game_root"),
        }
        if mode == "dual":
            values["engine"] = config.get("engine_root")
        values["uproject"] = config.get("uproject")

    out: list[str] = []
    for element in cmd:
        match = _TOKEN_RE.fullmatch(element)
        if match is not None:
            name = match.group(1)
            if name not in values:
                _tc_fail(
                    "missing-field",
                    f"verification command references undefined placeholder '{match.group(0)}' "
                    f"(verify argv defines: {', '.join(defined)}): {element}",
                )
            if name == "uproject":
                out.append(discover_uproject(config.get("game_root"), config.get("uproject")))
                continue
            value = values[name]
            if value is None:
                _tc_fail(
                    "missing-field",
                    f"verification command references '{match.group(0)}' but it is not "
                    f"configured in {mode} mode: {element}",
                )
            out.append(str(value))
            continue
        if _TOKEN_RE.search(element) is not None:
            _tc_fail(
                "missing-field",
                "verification command placeholder must occupy a whole argv element: "
                f"{element}",
            )
        out.append(element)
    return out


def workspace_root(config: dict) -> str:
    """Worker workspace root for a resolved target config: partition mode
    anchors to the partition root, dual to the game root, single/legacy to the
    control root."""
    mode = config.get("mode")
    if mode == "partition":
        return config["partition_root"]
    if mode == "dual":
        return config["game_root"]
    return config["control_root"]


# ── Repo dist content anchors (mw-autopilot-verify-cli D-009, AC-009) ────────
# Cheap, build-free, read-only checks used by `mw update-env` (T-08) to keep
# the tracked artifacts from silently drifting behind their sources.

# Paths relative to the repository root (mw_common.py lives at
# packages/multi-workers/mw_common.py).
_REPO_STATUS_MODEL_REL = (
    "packages", "coding-agent", "src", "extensions", "agent-team-loop",
    "autopilot", "status-model.ts",
)
_REPO_BUNDLE_REL = (
    "packages", "multi-workers", "dist", "extensions", "agent-team-loop.js",
)
_REPO_CODING_AGENT_DIST_REL = ("packages", "coding-agent", "dist")

# Guard behaviour markers. Both must stay qualified: the bare substrings also
# occur in an esbuild path banner ("// .../xkey-gate-guard.ts") and in the
# environment variable name MW_XKEY_GATE_ROOT, so they cannot anchor.
_GATE_GUARD_MARKERS = ("xkey-gate-guard: blocked", "[XKEY_GATE]")

# Anchored on the assignment, never a bare string search: prose or a comment
# mentioning GATE_KINDS must not be mistaken for the enum itself.
_GATE_KINDS_ASSIGN_RE = re.compile(r"GATE_KINDS\s*=\s*\[(.*?)\]", re.DOTALL)
_STRING_LITERAL_RE = re.compile(r'"([^"\\]*)"')


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _gate_kinds_from_text(text: str) -> set[str]:
    """GATE_KINDS entries parsed from the `GATE_KINDS = [` assignment (empty
    set when no such assignment exists)."""
    match = _GATE_KINDS_ASSIGN_RE.search(text)
    if match is None:
        return set()
    return set(_STRING_LITERAL_RE.findall(match.group(1)))


def repo_bundle_anchor() -> dict:
    """A1b repo-bundle-vs-source content anchor (AC-009(b), D-009).

    The tracked repo bundle's GATE_KINDS set must equal the status-model.ts
    set and both guard behaviour markers must be present. stale=None when a
    side is missing (not a complete checkout); stale=False only when every
    check passed. Pure reads — no directory or file is created."""
    root = _repo_root()
    source = root.joinpath(*_REPO_STATUS_MODEL_REL)
    bundle = root.joinpath(*_REPO_BUNDLE_REL)
    if not source.is_file() or not bundle.is_file():
        return {"stale": None, "detail": "repo bundle or status-model source missing"}
    try:
        source_kinds = _gate_kinds_from_text(source.read_text(encoding="utf-8"))
        bundle_text = bundle.read_text(encoding="utf-8")
    except OSError as exc:
        return {"stale": None, "detail": f"cannot read repo bundle/source: {exc}"}
    if not source_kinds:
        return {"stale": None, "detail": "status-model.ts has no GATE_KINDS assignment"}
    bundle_kinds = _gate_kinds_from_text(bundle_text)
    problems: list[str] = []
    missing = sorted(source_kinds - bundle_kinds)
    extra = sorted(bundle_kinds - source_kinds)
    if missing:
        problems.append("kind set missing " + ", ".join(missing))
    if extra:
        problems.append("kind set has extra " + ", ".join(extra))
    missing_guards = [marker for marker in _GATE_GUARD_MARKERS if marker not in bundle_text]
    if missing_guards:
        problems.append("guard marker(s) missing: " + ", ".join(missing_guards))
    if problems:
        return {"stale": True, "detail": "repo bundle vs source: " + "; ".join(problems)}
    return {
        "stale": False,
        "detail": (
            f"repo bundle matches source (kind {len(source_kinds)} entries, "
            "guard markers present)"
        ),
    }


def sourcemap_drift() -> dict:
    """A2b dist sourcesContent anchor (AC-009(b), D-009).

    Every tracked *.map under packages/coding-agent/dist embeds its source text
    (inlineSources: true), so comparing sourcesContent against the file on disk
    detects content drift without a build. EOL is normalized (CRLF/CR -> LF):
    .gitattributes pins eol=lf, so an EOL-only flip is not drift. stale=None
    when the dist tree or the maps are absent; stale=True lists the first
    mismatches. Pure reads."""
    dist_root = _repo_root().joinpath(*_REPO_CODING_AGENT_DIST_REL)
    if not dist_root.is_dir():
        return {"stale": None, "detail": "packages/coding-agent/dist missing"}
    maps = sorted(dist_root.rglob("*.map"))
    if not maps:
        return {"stale": None, "detail": "no source maps under packages/coding-agent/dist"}
    mismatches: list[str] = []
    compared = 0
    for map_path in maps:
        try:
            data = json.loads(map_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            mismatches.append(f"{map_path}: unreadable map")
            continue
        sources = data.get("sources") or []
        contents = data.get("sourcesContent") or []
        for index, source in enumerate(sources):
            if index >= len(contents) or contents[index] is None:
                continue
            source_path = (map_path.parent / str(source)).resolve()
            if not source_path.is_file():
                continue
            try:
                with open(source_path, "r", encoding="utf-8", newline="") as handle:
                    actual = handle.read()
            except OSError:
                continue
            compared += 1
            actual_norm = actual.replace("\r\n", "\n").replace("\r", "\n")
            embedded_norm = str(contents[index]).replace("\r\n", "\n").replace("\r", "\n")
            if actual_norm != embedded_norm:
                mismatches.append(str(source_path))
    if mismatches:
        return {
            "stale": True,
            "detail": (
                f"{len(mismatches)} of {compared} embedded source(s) differ: "
                + ", ".join(mismatches[:5])
            ),
        }
    return {
        "stale": False,
        "detail": f"sourcesContent matches for {compared} source(s) across {len(maps)} map(s)",
    }


def toolchain_probe_path(project_dir: pathlib.Path | str) -> pathlib.Path:
    """Machine-local toolchain probe cache (mw-dual-workspace D-013)."""
    return pathlib.Path(project_dir) / ".mw" / "toolchain.json"


# ── Toolchain discipline helpers (dual-toolchain practice guide) ─────────────
# Scope: dual-mode UE game dev (game repo + engine source repo, MSVC/UBT) —
# target discovery and error signatures are UE/MSVC-specific; hashing is
# toolchain-agnostic.

def sha256_eol_normalized(path: pathlib.Path | str) -> str:
    """EOL-insensitive sha256 (practice §5.5): engine repos on
    core.autocrlf=input flip CRLF working files to LF on checkout/rebase
    without any content change — byte-exact hashing then reports false
    drift. Normalize CRLF→LF before hashing so freezes survive EOL flips
    (same recipe as the guide's freeze pipelines)."""
    data = pathlib.Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def discover_build_targets(game_root: pathlib.Path | str) -> list[dict]:
    """UE build target names from <game>/Source/*.Target.cs (practice §2.1:
    target names are read from the Target.cs files, never guessed — the
    class name must match the file name, *Editor = editor target). Returns
    [] when there is no Source dir (non-UE game roots)."""
    source = pathlib.Path(game_root) / "Source"
    if not source.is_dir():
        return []
    out: list[dict] = []
    for f in sorted(source.glob("*.Target.cs")):
        name = f.name[: -len(".Target.cs")]
        out.append({
            "name": name,
            "kind": "editor" if name.endswith("Editor") else "game",
            "file": str(f),
        })
    return out


# MSVC "error C2039", linker "LNK2001", UBT/MSBuild "error :" — the three
# signatures the practice guide's build acceptance greps for. Remote-executor
# retry noise ("Force local retry") deliberately does not match.
_BUILD_ERROR_RE = re.compile(r"error C\d{1,5}|LNK\d{4}|error :")


def scan_build_error_lines(text: str) -> list[str]:
    """Error-signature lines from a build log (practice §2.3-2: the exit
    code is necessary but not sufficient — 600+ green static assertions can
    still hide real C2039/UHT/LNK2001 defects only a real compile+link
    exposes; acceptance records exit 0 AND zero signature hits together)."""
    return [line for line in text.splitlines() if _BUILD_ERROR_RE.search(line)]


# ── Workspace-profile rendering (mw-target-partition AC-007/FIX-1) ─────────────

PROFILE_MARK_V2 = "<!-- mw-profile: v2 -->"


def render_partition_profile_md(config: dict, ignore_enforced: bool = True) -> str:
    """Render the partition workspace-profile block (AC-007) — the line
    protocol twin of the TS renderPartitionProfileBlock (task-dispatcher.ts):
    v2 marker + explicit mode line, then the same essentials shape the
    PM-side dispatcher writes, so a task.md carries the same profile block
    regardless of which side dispatched it (the TS dispatcher skips
    origin: conductor tasks, so the conductor must inject its own).

    ignore_enforced=False (the task carries its own deny_globs list) skips
    the firewall section — same rule as the TS render. Fail-closed (AC-004):
    an undefined toolchain placeholder raises TargetConfigError(missing-
    field) — the caller refuses the dispatch, never a half-rendered block."""
    lines = [
        PROFILE_MARK_V2,
        f"[mw] mode: {config['mode']}",
        "[mw] Workspace profile (target.yml essentials, injected at dispatch;",
        f"full file: {os.path.join(config['control_root'], '.agenticdoc', 'target.yml')})",
        f"Control workspace: {config['control_root']}",
        f"Parent root (extended workspace, writable): {config['parent_root']}",
        f"Partition root (worker cwd): {config['partition_root']}",
    ]
    roots = config.get("roots") or {}
    if roots:
        lines.append("Named roots:")
        for name, root_path in roots.items():
            lines.append(f"- {name}: {root_path}")
    toolchain = config.get("toolchain") or {}
    if toolchain:
        lines.append("Toolchain commands (placeholders resolved):")
        for name, command in toolchain.items():
            lines.append(f"- {name}: {render_toolchain_command(command, config)}")
    if ignore_enforced and (config.get("ignore") or {}).get("deny_globs"):
        lines.append("Context firewall (deny globs, enforced by the read-scope layer):")
        for glob in config["ignore"]["deny_globs"]:
            lines.append(f"- {glob}")
    contract = config.get("contract") or {}
    forbidden = contract.get("forbidden_paths") or []
    conventions = contract.get("conventions")
    docs = contract.get("docs") or []
    if forbidden or conventions is not None or docs:
        lines.append("Contract:")
        if forbidden:
            lines.append(f"- forbidden paths: {', '.join(forbidden)}")
        if conventions is not None:
            lines.append("- conventions:")
            for line in conventions.split("\n"):
                lines.append(f"  {line}")
        if docs:
            lines.append("- docs (references, not inlined):")
            for doc in docs:
                lines.append(f"  - {os.path.normpath(os.path.join(config['control_root'], doc))}")
    return "\n".join(lines)


def _probe_fingerprint(config: dict) -> str:
    """Resolved-config fingerprint for the probe cache (mw-target-partition
    D-009): active mode + the sorted set of normalized roots (game/engine/
    parent/partition/named). An active-key switch or an env override change
    moves the fingerprint even when target.yml's mtime did not, forcing a
    re-probe; identical resolutions serialize identically (sorted)."""
    roots: dict[str, str | None] = {
        "game": config["game_root"],
        "engine": config["engine_root"],
        "parent": config["parent_root"],
        "partition": config["partition_root"],
    }
    for root_name, root_path in (config.get("roots") or {}).items():
        roots[f"root:{root_name}"] = root_path
    return json.dumps({"mode": config["mode"], "roots": sorted(roots.items())}, sort_keys=True)


def probe_target_toolchain(config: dict) -> list[dict]:
    """Machine-level checks on a resolved target config (D-013): root
    readability, engine presence, {uproject} resolvability. Pure — the cache
    layer in _doctor_target decides whether to run them. Partition mode
    (mw-target-partition AC-009): parent/partition/named-root reachability
    (isdir) — no engine/uproject check (partition carries neither)."""
    checks: list[dict] = []
    if config["mode"] == "partition":
        for name, root_path in (
            ("parent_root", config["parent_root"]),
            ("partition_root", config["partition_root"]),
        ):
            checks.append({"name": name, "ok": os.path.isdir(root_path), "detail": root_path})
        for root_name, root_path in (config.get("roots") or {}).items():
            checks.append(
                {"name": f"root:{root_name}", "ok": os.path.isdir(root_path), "detail": root_path}
            )
        return checks
    game = config["game_root"]
    checks.append({"name": "game_root", "ok": os.path.isdir(game), "detail": game})
    if config["engine_root"] is not None:
        engine = config["engine_root"]
        checks.append({"name": "engine_root", "ok": os.path.isdir(engine), "detail": engine})
    needs_uproject = config["uproject"] is not None or any(
        "{uproject}" in cmd for cmd in config["toolchain"].values()
    )
    if needs_uproject:
        try:
            p = discover_uproject(game, config["uproject"])
            checks.append({"name": "uproject", "ok": True, "detail": p})
        except TargetConfigError as e:
            checks.append({"name": "uproject", "ok": False, "detail": f"{e.kind}: {e}"})
    return checks


def _doctor_target(project_dir: pathlib.Path) -> dict:
    """Target config + cached toolchain probe section (mw-dual-workspace D-013;
    mw-target-partition D-009).

    Probe results persist to .mw/toolchain.json and are reused while fresh
    — resolved-config fingerprint (active mode + normalized root set, so an
    active switch or env override invalidates) AND target.yml not newer
    than the probe timestamp — the machine property rarely changes once the
    project is set up. A cache without a fingerprint (pre-partition format)
    is stale once and re-probes (idempotent afterwards). Config load errors
    and failed probe checks become doctor issues; a single-mode default (no
    target.yml) has nothing to probe."""
    yml = target_yml_path(project_dir)
    section: dict = {"yaml_available": yaml is not None}
    try:
        config = load_target_config(project_dir)
    except TargetConfigError as e:
        section["config"] = None
        section["error"] = {"kind": e.kind, "message": str(e)}
        return section
    section["config"] = {
        "mode": config["mode"],
        "source": config["source"],
        "game_root": config["game_root"],
        "engine_root": config["engine_root"],
        "vcs": config["vcs"],
        "uproject": config["uproject"],
    }
    if config["mode"] == "partition":
        # AC-018(c): partition-only keys — dual/single/v1 sections keep the
        # exact key set (AC-016e golden).
        section["config"]["parent_root"] = config["parent_root"]
        section["config"]["partition_root"] = config["partition_root"]
        section["config"]["roots"] = config["roots"]
    if config["source"] == "default":
        section["checks"] = None
        return section

    cache = toolchain_probe_path(project_dir)
    yml_mtime = yml.stat().st_mtime if yml.exists() else 0.0
    fingerprint = _probe_fingerprint(config)
    cached: dict | None = None
    if cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached = None
    if (
        cached is not None
        and isinstance(cached.get("checks"), list)
        and cached.get("fingerprint") == fingerprint
        and cached.get("probed_at_epoch", 0.0) >= yml_mtime
    ):
        section["checks"] = cached["checks"]
        section["probe_cache"] = "fresh"
        return section

    checks = probe_target_toolchain(config)
    section["checks"] = checks
    section["probe_cache"] = "probed"
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps(
                {
                    "probed_at": iso_now(),
                    "probed_at_epoch": time.time(),
                    "fingerprint": fingerprint,
                    "checks": checks,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        section["probe_cache"] = "probed (cache write failed)"
    return section
