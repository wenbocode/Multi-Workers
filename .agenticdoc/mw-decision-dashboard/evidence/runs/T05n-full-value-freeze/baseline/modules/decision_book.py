"""decision_book.py — 决策本的生成、验收与档案（spec §14 AC-018/AC-019/AC-021）。

决策本（decision book）是 `decide` 接口的**输入文件**：``{schema_version,
decision_point, state, context?, notes}``。本模块提供三个面，规则全部复用既有
实现，避免「book 过了但 decide 拒了」的双标（design D-056）：

* :func:`scaffold_book` —— 按注册表生成骨架。键集合与顺序完全由配置决定
  （``decision_points.registry_snapshot()``，即 ``decide_registry.json`` 的生成源），
  值一律是**类型占位符**，``notes.evidence`` 为每个必填字段留同名待填项；
* :func:`check_book` —— 七类失败码的**封闭集合**验收：``book-schema`` /
  ``book-state``（缺必填 + 类型不符 + 多出注册表没有的键）/ ``book-placeholder`` /
  ``book-context`` / ``book-evidence`` / ``book-budget`` / ``book-secret``；
* :func:`append_book_receipt` —— 发送后落一条 book 档案行（``book_path`` +
  ``file_sha256`` + ``notes.evidence``）。

检查器**只报告，不修**（AC-019/D-057）：自动补字段等于把「编造」合法化。发送侧
（``mw decide ask/run --book``）先 :func:`check_book`，任一失败即拒绝发送（零 HTTP）。

``decisions.jsonl`` 的字段矩阵是封闭的且由 ``decide_archive.py`` 拥有（不在本卡的
写入面内），所以 book 档案落在独立的回执账本
``<project>/.agenticdoc/_autopilot/book-receipts.jsonl``：一行一次发送，携带
``book_path`` / ``file_sha256`` / ``notes.evidence`` 以及决策行可对照的
``decision_id`` / ``state_digest``。
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import decision
import decision_points

#: 决策本格式版本（``schema_version`` 顶层键，AC-018）。
BOOK_SCHEMA_VERSION = 2

#: 顶层键的**封闭集合**（``context`` 可选，其余必填；``notes.evidence`` 是证据面）。
BOOK_TOP_LEVEL_KEYS: tuple[str, ...] = (
    "schema_version",
    "decision_point",
    "state",
    "context",
    "notes",
)

#: 通用 state 身份字段：``decision_points._state_builder`` 对每个 dp 都会写这三个，
#: 因此即使注册表没把它们列进 ``required_state_fields``（dp25），它们也合法。
STRUCTURAL_STATE_FIELDS: tuple[str, ...] = (
    "schema_version",
    "decision_point",
    "questions_version",
)

#: 七个失败码（AC-019）。顺序即报告顺序。
ISSUE_CODES: tuple[str, ...] = (
    "book-schema",
    "book-state",
    "book-placeholder",
    "book-context",
    "book-evidence",
    "book-budget",
    "book-secret",
)

#: 证据引用：``<path>:<line>``（``<path>:<start>-<end>`` 取 start）。
_EVIDENCE_REF_RE = re.compile(r"^(?P<path>.+?):(?P<line>\d+)(?:-\d+)?$")
#: 视为「命令原文」的命令前缀（证据允许 ``cmd: <command>`` 或裸命令）。
_COMMAND_PREFIXES: tuple[str, ...] = (
    "cmd:",
    "rg ",
    "git ",
    "python ",
    "python3 ",
    "pytest ",
    "npm ",
    "node ",
    "pwsh ",
    "bash ",
    "ls ",
    "grep ",
    "find ",
    "wc ",
    "mw ",
)

#: 占位符字面量（大小写不敏感）。``<...>`` 包裹一律算占位符。
PLACEHOLDER_TOKENS: frozenset[str] = frozenset(
    {"tbd", "tba", "todo", "fixme", "xxx", "pending", "待填", "待补", "待定"}
)
_PLACEHOLDER_WRAP_RE = re.compile(r"^<[^<>]+>$")
#: ``book new`` 写入的空槽提示（占位符原文，便于 ``book check`` 识别）。
EVIDENCE_PLACEHOLDER = "<待填: path:line 或命令原文>"

#: 上下文槽位兜底表（AC-017）：单槽上限 + 形态（``text`` 字符 / ``items`` 条数）。
#: **运行时权威**是 W6 的 ``decision_context.CONTEXT_SLOTS``（``decide_for`` 按它
#: 截断/校验/脱敏）；本表只在它缺席时兜底，形状与它保持一致（槽位值就是内容，
#: 不是 ``{source, text}`` 包装）。
CONTEXT_SLOT_LIMITS: dict[str, tuple[str, int]] = {
    "task_excerpt": ("text", 1200),
    "change_summary": ("text", 800),
    "candidate_snippets": ("items", 5),
    "artifact_status": ("items", 24),
    "error_excerpt": ("text", 1500),
}
#: 每个 dp 允许的槽位兜底表（AC-017 的「生产者」列）。
DP_CONTEXT_SLOTS: dict[str, tuple[str, ...]] = {
    "dp1-dispatch-type": ("task_excerpt",),
    "dp2-checkpoint-split": ("change_summary", "artifact_status"),
    "dp3-worker-clarify": ("change_summary", "candidate_snippets"),
    "dp4-failure-handling": ("error_excerpt",),
    "dp6-qg-verdict": ("error_excerpt",),
    "dp7-gate-failure": ("error_excerpt",),
}
try:  # single source of truth: prefer the runtime table when it is importable
    import decision_context as _decision_context

    DP_CONTEXT_SLOTS = {
        dp_id: _decision_context.slot_names_for(dp_id)
        for dp_id in DP_CONTEXT_SLOTS
    }
except Exception:  # pragma: no cover - decision_context is a sibling module
    pass
#: ``context`` 总预算（序列化字节数，与 W6 的 2000 B state 预算同源计量）。
CONTEXT_TOTAL_LIMIT = 4000
#: 单条 candidate snippet 的文本上限（AC-017）。
CANDIDATE_TEXT_LIMIT = 200

#: 预算闸的缺省值（与 ``decision.DecisionConfig`` 的内置缺省一致）。
DEFAULT_MAX_STATE_PLUS_QUESTION_TOKENS = 32768
DEFAULT_MAX_TOTAL_TOKENS = 65536
DEFAULT_MAX_STATE_BYTES = 0

#: book 回执账本（相对 project_dir）。
RECEIPTS_RELATIVE_PATH = pathlib.Path(".agenticdoc") / "_autopilot" / "book-receipts.jsonl"


class BookError(ValueError):
    """装载期失败（JSON 不可解析 / 顶层键非法 / schema_version 不符）。

    ``issue`` 携带同一套 ``code``/``path``/``detail``，CLI 因此可以用一个表格
    同时打印装载失败与检查失败（不引入第二套失败词汇）。
    """

    def __init__(self, code: str, path: str, detail: str) -> None:
        if code not in ISSUE_CODES:
            raise ValueError(f"unknown book issue code {code!r}")
        self.issue = Issue(code=code, path=path, detail=detail)
        super().__init__(self.issue.format())


@dataclass(frozen=True)
class Issue:
    """一条验收失败：稳定失败码 + 定位 + 人类可读的说明。"""

    code: str
    path: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "detail": self.detail}

    def format(self) -> str:
        return f"{self.code} {self.path}: {self.detail}"


@dataclass
class BookReport:
    """``mw decide book check`` 的结果（一个文件可装一本或多本示例）。"""

    path: str
    sha256: str | None
    books: list[dict[str, Any]] = field(default_factory=list)

    @property
    def issues(self) -> list[Issue]:
        return [issue for book in self.books for issue in book["issues"]]

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def decision_points(self) -> list[str]:
        return [book["decision_point"] for book in self.books if book.get("decision_point")]

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "ok": self.ok,
            "books": [
                {
                    "label": book["label"],
                    "decision_point": book["decision_point"],
                    "ok": not book["issues"],
                    "issues": [issue.as_dict() for issue in book["issues"]],
                }
                for book in self.books
            ],
            "issues": [issue.as_dict() for issue in self.issues],
        }


# ---------------------------------------------------------------------------
# 注册表视图（配置是唯一权威：spec §14 AC-021）
# ---------------------------------------------------------------------------


def registry_points() -> dict[str, dict]:
    """``{dp_id: point}`` 的注册表视图（与 ``decide_registry.json`` 同源）。"""
    snapshot = decision_points.registry_snapshot()
    return {point["id"]: point for point in snapshot["points"]}


def required_fields(dp_id: str) -> list[dict]:
    """该 dp 的 ``required_state_fields``（``[{name, type, description}]``，有序）。"""
    point = registry_points().get(dp_id)
    if point is None:
        raise BookError("book-schema", "decision_point", f"unknown decision point {dp_id!r}")
    return list(point.get("required_state_fields") or ())


def required_state_paths(dp_id: str) -> tuple[str, ...]:
    """该 dp 必填的 state 路径（点号形式，顺序 == 注册表顺序）。"""
    return tuple(field["name"] for field in required_fields(dp_id))


def optional_fields(dp_id: str) -> list[dict]:
    """该 dp 的 ``optional_state_fields``（同一套字段形状，可空）。"""
    point = registry_points().get(dp_id)
    if point is None:
        raise BookError("book-schema", "decision_point", f"unknown decision point {dp_id!r}")
    return list(point.get("optional_state_fields") or ())


def optional_state_paths(dp_id: str) -> tuple[str, ...]:
    """该 dp 可选的 state 路径（闭集的一部分：合法但不必填、不需证据）。"""
    return tuple(field["name"] for field in optional_fields(dp_id))


def context_slots(dp_id: str) -> tuple[str, ...]:
    """该 dp 允许的上下文槽位。

    优先取 W6 的 ``decision_context``（``decide_for`` 的运行时权威），它缺席时才
    回退到本模块的 ``DP_CONTEXT_SLOTS``：能让 book 通过的槽位必须是发送时不会被
    截掉/判非法的槽位（D-056 的单一判定器）。
    """
    point = registry_points().get(dp_id)
    if point is None:
        raise BookError("book-schema", "decision_point", f"unknown decision point {dp_id!r}")
    declared = point.get("context_slots") or point.get("contextSlots")
    if isinstance(declared, (list, tuple)) and declared:
        return tuple(str(slot) for slot in declared)
    shared = _shared_context_slots(dp_id)
    if shared is not None:
        return shared
    return DP_CONTEXT_SLOTS.get(dp_id, ())


def _shared_context_slots(dp_id: str) -> tuple[str, ...] | None:
    """``decision_context``（W6 并行卡）的槽位表；不存在/不可用时返回 ``None``。

    只做只读探测：模块缺失、表缺失、表形状不符都静默回退到本模块的
    ``DP_CONTEXT_SLOTS``，绝不因为并行卡尚未落地而让 book 面不可用。
    """
    module = _context_module()
    if module is None:
        return None
    resolver = getattr(module, "slot_names_for", None)
    if callable(resolver):
        try:
            slots = resolver(dp_id)
        except Exception:  # noqa: BLE001 - 第三方表不参与本卡的失败面
            return None
        if isinstance(slots, (list, tuple)):
            return tuple(str(slot) for slot in slots)
    table = getattr(module, "CONTEXT_SLOTS", None)
    if isinstance(table, Mapping):
        return tuple(
            str(name)
            for name, spec in table.items()
            if isinstance(spec, Mapping) and dp_id in (spec.get("producers") or ())
        )
    return None


def _context_module() -> object | None:
    """``decision_context``（W6）；导入失败/损坏一律当作不存在。"""
    try:
        import decision_context  # type: ignore[import-not-found]  # W6 并行卡
    except Exception:  # noqa: BLE001 - 并行模块缺失/损坏都回退
        return None
    return decision_context


@dataclass(frozen=True)
class SlotSpec:
    """一个上下文槽位的形状：``text``（字符上限）或 ``items``（条数 + 单条上限）。"""

    kind: str
    limit: int
    item_max_chars: int = 0
    item_required: tuple[str, ...] = ()


def context_slot_spec(name: str) -> SlotSpec:
    """槽位形状（优先 W6 的 ``CONTEXT_SLOTS``，缺席时用本地兜底表）。"""
    module = _context_module()
    table = getattr(module, "CONTEXT_SLOTS", None) if module is not None else None
    spec = table.get(name) if isinstance(table, Mapping) else None
    if isinstance(spec, Mapping):
        if spec.get("type") == "array":
            return SlotSpec(
                "items",
                int(spec.get("max_items") or 0),
                int(spec.get("item_max_chars") or 0),
                tuple(str(key) for key in (spec.get("item_required") or ())),
            )
        return SlotSpec("text", int(spec.get("max_chars") or 0))
    fallback = CONTEXT_SLOT_LIMITS.get(name)
    if fallback is None:
        return SlotSpec("text", 0)
    kind, limit = fallback
    if kind == "items":
        required = ("path",) if name == "artifact_status" else ("text", "source")
        return SlotSpec("items", limit, CANDIDATE_TEXT_LIMIT, required)
    return SlotSpec("text", limit)


def context_evidence_key(slot: str) -> str:
    """已用槽位的来源证据键（AC-017：「每个槽位必须带 source」）。

    槽位值本身就是内容（与 ``decision_context`` 同形），所以来源不进槽位体，而是
    进 ``notes.evidence["context.<slot>"]``，与其它证据用同一套 ``path:line`` 规则。
    """
    return f"context.{slot}"


def field_type(dp_id: str, path: str) -> str | None:
    """注册表声明的该路径类型（``string|integer|number|boolean|array|object``）。"""
    for field in required_fields(dp_id):
        if field["name"] == path:
            return str(field["type"])
    return None


# ---------------------------------------------------------------------------
# 骨架生成
# ---------------------------------------------------------------------------


def type_placeholder(kind: str, description: str = "") -> object:
    """类型占位符：``<string: desc>`` / ``-1`` / ``-1.0`` / ``false`` / ``[]`` / ``{}``。"""
    hint = " ".join(str(description or "").split())
    if kind == "string":
        return f"<string: {hint}>" if hint else "<string>"
    if kind == "integer":
        return -1
    if kind == "number":
        return -1.0
    if kind == "boolean":
        return False
    if kind == "array":
        return []
    if kind == "object":
        return {}
    return f"<{kind}: {hint}>" if hint else f"<{kind}>"


def scaffold_book(dp_id: str) -> dict:
    """按注册表生成该 dp 的决策本骨架（不联网、不读工程现场，D-063）。

    ``state`` 的键集合与顺序 == ``required_state_fields``（外加
    :data:`STRUCTURAL_STATE_FIELDS` 这三个通用身份字段，其值直接预填为真实值）；
    其余字段一律是类型占位符，``notes.evidence`` 为每个必填字段留同名待填项，
    ``context`` 只为该 dp 允许的槽位留位。
    """
    point = registry_points().get(dp_id)
    if point is None:
        raise BookError("book-schema", "decision_point", f"unknown decision point {dp_id!r}")
    questions_version = str(point.get("questions_version") or "")
    # 通用身份字段：``decision_points._state_builder`` 对每个 dp 都会写这两个，
    # 因此骨架始终预填真实值（dp1/dp3 的注册表也把它们列为必填前两项，顺序不变）。
    state: dict[str, Any] = {"schema_version": BOOK_SCHEMA_VERSION, "decision_point": dp_id}
    evidence: dict[str, str] = {}
    required = required_state_paths(dp_id)
    for field_spec in required_fields(dp_id):
        name = field_spec["name"]
        if name == "schema_version":
            _set_path(state, name, BOOK_SCHEMA_VERSION)
        elif name == "decision_point":
            _set_path(state, name, dp_id)
        elif name == "questions_version":
            _set_path(state, name, questions_version)
        else:
            _set_path(state, name, type_placeholder(str(field_spec["type"]), str(field_spec.get("description") or "")))
        evidence[name] = EVIDENCE_PLACEHOLDER
    if "questions_version" not in required and questions_version:
        _set_path(state, "questions_version", questions_version)
    return {
        "schema_version": BOOK_SCHEMA_VERSION,
        "decision_point": dp_id,
        "state": state,
        "context": scaffold_context(dp_id),
        "notes": {"evidence": evidence},
    }


def scaffold_context(dp_id: str) -> dict:
    """该 dp 的上下文槽位骨架（``context`` 是可选面，空值 = 未使用）。

    值与 ``decision_context`` 同形：文本槽位是空串，数组槽位是空数组（不包一层
    ``{source, text}``）——已用槽位的来源写在 ``notes.evidence["context.<slot>"]``。
    这样骨架不用改形状就能直接被 ``decide_for`` 接受。
    """
    out: dict[str, Any] = {}
    for slot in context_slots(dp_id):
        out[slot] = [] if context_slot_spec(slot).kind == "items" else ""
    return out


# ---------------------------------------------------------------------------
# 装载
# ---------------------------------------------------------------------------


def load_book(path: pathlib.Path | str) -> dict:
    """装载一本决策本（单本）：JSON 可解析、顶层键封闭、``schema_version == 2``。

    失败抛 :class:`BookError`（``code=book-schema``）。检查器不在此处扩张：
    取值/类型/证据等由 :func:`check_book` 负责，装载只回答「这是不是一本书」。
    """
    source = pathlib.Path(path)
    data = _read_json(source)
    return _validate_book_shape(data, str(source))


def load_books(path: pathlib.Path | str) -> list[tuple[str | None, dict]]:
    """装载一个文件里的一本或多本（示例/Smoke 用的 ``{"books": {...}}`` 或数组）。"""
    source = pathlib.Path(path)
    data = _read_json(source)
    return _split_bundle(data, str(source))


def _read_json(source: pathlib.Path) -> object:
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise BookError("book-schema", str(source), f"cannot read: {exc}") from exc
    try:
        return json.loads(text)
    except ValueError as exc:
        raise BookError("book-schema", str(source), f"not valid JSON: {exc}") from exc


def _validate_book_shape(data: object, label: str) -> dict:
    if not isinstance(data, Mapping):
        raise BookError("book-schema", label, f"top level must be a JSON object, got {type(data).__name__}")
    unknown = sorted(set(data) - set(BOOK_TOP_LEVEL_KEYS))
    if unknown:
        raise BookError("book-schema", label, f"unknown top-level keys {unknown}")
    version = data.get("schema_version")
    if isinstance(version, bool) or version != BOOK_SCHEMA_VERSION:
        raise BookError(
            "book-schema", "schema_version", f"must be {BOOK_SCHEMA_VERSION}, got {version!r}"
        )
    dp_id = data.get("decision_point")
    if not isinstance(dp_id, str) or not dp_id.strip():
        raise BookError("book-schema", "decision_point", "must be a non-empty string")
    if dp_id not in registry_points():
        raise BookError("book-schema", "decision_point", f"unknown decision point {dp_id!r}")
    if not isinstance(data.get("state", {}), Mapping):
        raise BookError("book-schema", "state", "must be a JSON object")
    if "context" in data and not isinstance(data["context"], Mapping):
        raise BookError("book-schema", "context", "must be a JSON object")
    if "notes" in data and not isinstance(data["notes"], Mapping):
        raise BookError("book-schema", "notes", "must be a JSON object")
    return dict(data)


def _split_bundle(data: object, label: str) -> list[tuple[str | None, dict]]:
    if isinstance(data, list):
        return [(f"books[{index}]", _validate_book_shape(item, f"{label}[{index}]")) for index, item in enumerate(data)]
    if isinstance(data, Mapping) and "books" in data and set(data) == {"books"}:
        inner = data["books"]
        if isinstance(inner, Mapping):
            return [
                (str(name), _validate_book_shape(item, f"{label}:{name}"))
                for name, item in inner.items()
            ]
        if isinstance(inner, list):
            return [
                (f"books[{index}]", _validate_book_shape(item, f"{label}[{index}]"))
                for index, item in enumerate(inner)
            ]
        raise BookError("book-schema", label, "'books' must be an object or an array of books")
    return [(None, _validate_book_shape(data, label))]


def book_sha256(path: pathlib.Path | str) -> str | None:
    """文件字节的 sha256（读失败返回 ``None``：档案不因读失败而丢行）。"""
    try:
        return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# 验收（封闭集合 / 占位符 / 上下文 / 证据 / 预算 / 密钥）
# ---------------------------------------------------------------------------


def is_placeholder(value: object, kind: str | None = None, *, signed: bool = False) -> bool:
    """占位符判定（AC-019）：``<...>``、TBD/TODO/xxx、空串、负数、空数组/对象。

    布尔 ``false`` **不算**占位符：``progress.artifact_present=false`` 是真实取值，
    把它判成占位符会把合法决策本拦在外面。声明为 ``signed`` 的 integer
    （dp23 ``snapshot.delta_bytes``）**任何负数都是真实取值**（新规模减旧规模），
    因此骨架的 ``-1`` 在那里不再计为占位符；dp23 骨架仍因 ``size_bytes`` /
    ``sections_changed`` / 证据未填而被拒。
    """
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return True
        if _PLACEHOLDER_WRAP_RE.match(text):
            return True
        return text.lower() in PLACEHOLDER_TOKENS
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return False if signed else value < 0
    if isinstance(value, (list, dict)):
        return not value
    if value is None:
        return True
    return False


def type_matches(value: object, kind: str) -> bool:
    """JSON 原生类型匹配（``bool`` 不算 ``integer``/``number``）。"""
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "array":
        return isinstance(value, list)
    if kind == "object":
        return isinstance(value, Mapping)
    return False


def check_book(
    book: Mapping[str, Any],
    *,
    project_dir: pathlib.Path | str | None = None,
    repo_root: pathlib.Path | str | None = None,
    limits: Mapping[str, int] | None = None,
    redactor: object | None = None,
) -> list[Issue]:
    """验收一本决策本，返回失败列表（空 == 全过）。只报告，不修改入参。

    ``project_dir`` 用于解析预算闸（``.mw/decide.json`` 的 ``max_*``）；
    ``repo_root`` 是证据里相对路径的锚点（缺省取 ``project_dir`` 或当前目录的
    仓库根），``limits`` 允许调用方直接给闸值（测试/CI 用）。

    ``redactor`` 是**当次实际已知凭证集合**（``decision.known_secret_redactor(cfg)``：
    ``cfg.api_key`` / ``cfg.extras["api_key"]``、实际 Authorization、timi 凭证、
    env 规则 + Bearer/``sk-``）。生产入口（``mw decide ... --book``、observation
    seam）必须显式传入；省略时只剩 env/Bearer/``sk-`` 启发式，结果**不声称**
    完整 known 覆盖（T06 的参数义务）。值仅内存，不落盘、不回显。
    """
    issues: list[Issue] = []
    issues.extend(_check_schema(book, redactor=redactor))
    if any(issue.code == "book-schema" for issue in issues):
        return issues
    dp_id = str(book["decision_point"])
    state = dict(book.get("state") or {})
    required = required_state_paths(dp_id)

    flat = _flatten(state)
    issues.extend(_check_state_closed(dp_id, state, flat, required, redactor=redactor))
    issues.extend(_check_state_types(dp_id, state))
    issues.extend(_check_placeholders(dp_id, flat, required))
    issues.extend(_check_context(book, dp_id, redactor=redactor))
    issues.extend(
        _check_evidence(
            book,
            dp_id,
            required,
            project_dir=project_dir,
            repo_root=repo_root,
            redactor=redactor,
        )
    )
    issues.extend(_check_budget(book, dp_id, project_dir=project_dir, limits=limits))
    issues.extend(_check_secrets(book, redactor=redactor))
    return issues


def observation_book_issues(
    book: Mapping[str, Any],
    project_dir: pathlib.Path | str | None = None,
    *,
    redactor: object | None = None,
) -> tuple[tuple[str, str], ...]:
    """``(path, detail)`` for a book the observation seam must refuse (T05b F2).

    ``decision_points.decide_for`` cannot import this module (``decision_book``
    imports it), so it reaches this function through
    :func:`decision_points.register_book_validator`. The verdict is
    :func:`check_book`'s: one authority for the book contract, so an observation
    can never accept a book that ``mw decide book check`` refuses (schema, closed
    state, placeholders, evidence, budget, secrets).

    ``redactor`` is the seam's actual known-secret set for *this* call (F1);
    the registered validator signature is ``(book, project_dir, *, redactor)``.
    """
    if not isinstance(book, Mapping):
        return (("book", f"must be a JSON object, got {type(book).__name__}"),)
    return tuple(
        (issue.path, f"{issue.code}: {issue.detail}")
        for issue in check_book(book, project_dir=project_dir, redactor=redactor)
    )


def _check_schema(book: Mapping[str, Any], *, redactor: object | None = None) -> list[Issue]:
    if not isinstance(book, Mapping):
        return [Issue("book-schema", "book", f"must be a JSON object, got {type(book).__name__}")]
    issues: list[Issue] = []
    unknown = sorted(
        {
            _secret_scan_segment(key, redactor)
            for key in set(book) - set(BOOK_TOP_LEVEL_KEYS)
        }
    )
    if unknown:
        issues.append(Issue("book-schema", "book", f"unknown top-level keys {unknown}"))
    version = book.get("schema_version")
    if isinstance(version, bool) or version != BOOK_SCHEMA_VERSION:
        issues.append(
            Issue("book-schema", "schema_version", f"must be {BOOK_SCHEMA_VERSION}, got {version!r}")
        )
    dp_id = book.get("decision_point")
    if not isinstance(dp_id, str) or not dp_id.strip():
        issues.append(Issue("book-schema", "decision_point", "must be a non-empty string"))
    elif dp_id not in registry_points():
        issues.append(Issue("book-schema", "decision_point", f"unknown decision point {dp_id!r}"))
    if not isinstance(book.get("state"), Mapping):
        issues.append(Issue("book-schema", "state", "must be a JSON object"))
    if "context" in book and not isinstance(book["context"], Mapping):
        issues.append(Issue("book-schema", "context", "must be a JSON object"))
    notes = book.get("notes", {})
    if not isinstance(notes, Mapping):
        issues.append(Issue("book-schema", "notes", "must be a JSON object"))
    elif "evidence" in notes and not isinstance(notes["evidence"], Mapping):
        issues.append(Issue("book-schema", "notes.evidence", "must be a JSON object"))
    if isinstance(book.get("state"), Mapping) and "context" in book["state"] and book.get("context"):
        issues.append(
            Issue("book-schema", "context", "declared twice (top-level and state.context); keep one")
        )
    return issues


def _check_state_closed(
    dp_id: str,
    state: Mapping[str, Any],
    flat: Mapping[str, Any],
    required: Iterable[str],
    *,
    redactor: object | None = None,
) -> list[Issue]:
    """封闭键集合：缺必填 + 多出注册表没有的键，两个方向都报（AC-021/D-059）。

    未知键判定不在本模块再实现一套：``decision_points.state_unknown_key_issues``
    是唯一判定器（observation seam T05b F1 复用同一面），本函数只额外负责书侧的
    缺必填。三个身份值的等值与类型由同一纯检查
    ``decision_points.state_identity_issues`` 负责（T05c N2：书与 seam 不各造一套
    版本权威），在 :func:`_check_state_types` 里调用。
    """
    issues: list[Issue] = []
    for path in required:
        if path not in flat:
            issues.append(
                Issue("book-state", f"state.{path}", f"missing required field of {dp_id}")
            )
    for path, detail in decision_points.state_unknown_key_issues(
        dp_id, state, redactor=redactor
    ):
        issues.append(Issue("book-state", f"state.{path}", detail))
    return issues


def _check_state_types(
    dp_id: str, state: Mapping[str, Any]
) -> list[Issue]:
    """类型/枚举/max_items/元素长度/跨字段/身份：全部委托注册表（单一判定器）。

    ``decision_points.state_field_issues`` 只判断已声明且已出现的业务路径；缺必填
    由 :func:`_check_state_closed` 报，未知键也由它报。三个身份值的类型 + 等值走
    ``decision_points.state_identity_issues``（非 book 路径在 step5b 调同一个
    函数），所以这里不保留第二份 schema/questions_version 比对逻辑。
    """
    issues = [
        Issue("book-state", f"state.{path}", detail)
        for path, detail in decision_points.state_field_issues(dp_id, state)
    ]
    issues.extend(
        Issue("book-state", f"state.{path}", detail)
        for path, detail in decision_points.state_identity_issues(dp_id, state)
    )
    return issues


def _check_placeholders(
    dp_id: str, flat: Mapping[str, Any], required: Iterable[str]
) -> list[Issue]:
    issues: list[Issue] = []
    for path in required:
        if path not in flat:
            continue
        kind = field_type(dp_id, path)
        value = flat[path]
        if value is None:
            # AC-019: ``null`` on a required path is an unreplaced value whatever
            # the declared type (the typed check skips ``None`` by design, so the
            # placeholder scan is the gate that must not let it through).
            issues.append(
                Issue(
                    "book-placeholder",
                    f"state.{path}",
                    "required value is null; fill it from real evidence",
                )
            )
            continue
        if kind is not None and not type_matches(value, kind):
            continue  # 类型错由 book-state 报告，避免一条错误两种码
        spec = decision_points.STATE_FIELD_DESCRIPTIONS.get(path) or {}
        empty_is_value = spec.get("empty_is_value") is True
        if empty_is_value and isinstance(value, (list, dict)) and not value:
            # 注册表声明该字段的「空容器就是真实取值」（dp25 ``p0_open: []`` =
            # 「当前没有未关闭 P0」）。只豁免这一条 AC-019 规则：缺失由 closed-key 报，
            # null 就在上面拒绝，类型错由 book-state 报，元素里的占位文本在下面扫。
            continue
        if is_placeholder(value, kind, signed=bool(spec.get("signed"))):
            issues.append(
                Issue(
                    "book-placeholder",
                    f"state.{path}",
                    f"unreplaced placeholder {value!r}; fill it from real evidence",
                )
            )
            continue
        if empty_is_value and isinstance(value, list):
            issues.extend(_placeholder_element_issues(path, value))
    dp_value = flat.get("decision_point")
    if dp_value is not None and is_placeholder(dp_value):
        issues.append(
            Issue("book-placeholder", "state.decision_point", f"unreplaced placeholder {dp_value!r}")
        )
    qv = flat.get("questions_version")
    if qv is not None and is_placeholder(qv):
        issues.append(
            Issue("book-placeholder", "state.questions_version", f"unreplaced placeholder {qv!r}")
        )
    return issues


def _placeholder_element_issues(path: str, values: Iterable[object]) -> list[Issue]:
    """占位文本元素（仅限声明 ``empty_is_value`` 的数组字段）。

    该字段的「空」是真实取值，所以它的内容也必须真实：骨架留下的 ``<...>`` /
    TBD 元素不能跟着 flag 一起变成可发送材料。正常字段的数组元素规则不变
    （仍由 typed 契约的 ``item_type`` / ``item_max_bytes`` 管）。
    """
    issues: list[Issue] = []
    for index, item in enumerate(values):
        if not is_placeholder(item):
            continue
        issues.append(
            Issue(
                "book-placeholder",
                f"state.{path}[{index}]",
                "unreplaced placeholder element; fill it with a real value",
            )
        )
    return issues


def _check_context(
    book: Mapping[str, Any], dp_id: str, *, redactor: object | None = None
) -> list[Issue]:
    """上下文槽位：未知槽位 / 已用槽位无来源 / 超长 / 总预算。

    槽位形状与 ``decision_context`` 一致（值是内容本身）；来源由
    ``notes.evidence["context.<slot>"]`` 携带（AC-017 的「每个槽位必须带 source」）。
    """
    context = book.get("context")
    if not isinstance(context, Mapping):
        context = {}
    state_context = (
        (book.get("state") or {}).get("context")
        if isinstance(book.get("state"), Mapping)
        else None
    )
    if isinstance(state_context, Mapping):
        merged = dict(state_context)
        merged.update(context)
        context = merged
    if not context:
        return []
    notes = book.get("notes") if isinstance(book.get("notes"), Mapping) else {}
    evidence = notes.get("evidence") if isinstance(notes.get("evidence"), Mapping) else {}
    allowed = set(context_slots(dp_id))
    issues: list[Issue] = []
    used: list[str] = []
    for slot, content in context.items():
        path = f"context.{_secret_scan_segment(slot, redactor)}"
        if slot not in allowed:
            issues.append(
                Issue(
                    "book-context",
                    path,
                    f"slot not allowed for {dp_id} (allowed: {sorted(allowed) or 'none'})",
                )
            )
            continue
        if _is_empty_content(content):
            continue  # 空槽 = 未使用（context 是可选的，AC-017）
        used.append(str(slot))
        spec = context_slot_spec(slot)
        if spec.kind == "items":
            if not isinstance(content, list):
                issues.append(Issue("book-context", path, "slot must be an array"))
                continue
            if spec.limit and len(content) > spec.limit:
                issues.append(
                    Issue("book-context", path, f"{len(content)} items > limit {spec.limit}")
                )
            for index, item in enumerate(content):
                issues.extend(_check_context_item(spec, f"{path}[{index}]", item))
        else:
            if not isinstance(content, str):
                issues.append(Issue("book-context", path, "slot must be a string"))
                continue
            if spec.limit and len(content) > spec.limit:
                issues.append(
                    Issue("book-context", path, f"{len(content)} chars > limit {spec.limit}")
                )
        source = evidence.get(context_evidence_key(str(slot)))
        if not isinstance(source, str) or is_placeholder(source):
            issues.append(
                Issue(
                    "book-context",
                    f"notes.evidence.{context_evidence_key(str(slot))}",
                    "every used slot needs a source (notes.evidence['context.<slot>'] = path:line or command)",
                )
            )
    if issues:
        return issues
    total = len(decision._encode_state(dict(context)))
    if total > CONTEXT_TOTAL_LIMIT:
        return [
            Issue(
                "book-context",
                "context",
                f"{total} bytes > total limit {CONTEXT_TOTAL_LIMIT} (used: {used})",
            )
        ]
    return []


def _check_context_item(spec: SlotSpec, path: str, item: object) -> list[Issue]:
    if isinstance(item, str):
        if spec.item_max_chars and len(item) > spec.item_max_chars:
            return [
                Issue("book-context", path, f"{len(item)} chars > limit {spec.item_max_chars}")
            ]
        return []
    if not isinstance(item, Mapping):
        return [Issue("book-context", path, "must be a string or an object")]
    issues: list[Issue] = []
    for key in spec.item_required:
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            issues.append(Issue("book-context", f"{path}.{key}", "required and must be a string"))
    text = item.get("text")
    if isinstance(text, str) and spec.item_max_chars and len(text) > spec.item_max_chars:
        issues.append(
            Issue("book-context", f"{path}.text", f"{len(text)} chars > limit {spec.item_max_chars}")
        )
    return issues


def _is_empty_content(content: object) -> bool:
    if content is None:
        return True
    if isinstance(content, str):
        return not content.strip()
    if isinstance(content, (list, tuple, dict)):
        return not content
    return False


def _check_evidence(
    book: Mapping[str, Any],
    dp_id: str,
    required: Iterable[str],
    *,
    project_dir: pathlib.Path | str | None,
    repo_root: pathlib.Path | str | None,
    redactor: object | None = None,
) -> list[Issue]:
    notes = book.get("notes") if isinstance(book.get("notes"), Mapping) else {}
    evidence = notes.get("evidence") if isinstance(notes.get("evidence"), Mapping) else {}
    root = resolve_repo_root(project_dir, repo_root)
    issues: list[Issue] = []
    required_set = set(required)
    for path in required:
        if path not in evidence:
            issues.append(
                Issue("book-evidence", f"notes.evidence.{path}", "missing evidence for a required field")
            )
    # 可选字段的证据可给可不给（design §4.5），但给了就必须指向真实材料。
    allowed_field_keys = required_set | set(optional_state_paths(dp_id))
    allowed_context_keys = {
        context_evidence_key(slot) for slot in context_slots(dp_id)
    }
    for path, reference in evidence.items():
        entry_path = f"notes.evidence.{decision.safe_path_text(path, redactor)}"
        if path not in allowed_field_keys and path not in allowed_context_keys:
            issues.append(
                Issue(
                    "book-evidence",
                    entry_path,
                    "evidence key is neither a required field nor an allowed context slot",
                )
            )
            continue
        if is_placeholder(reference) or not isinstance(reference, str):
            issues.append(
                Issue(
                    "book-placeholder",
                    entry_path,
                    "evidence is still the scaffold placeholder; provide path:line or a command",
                )
            )
            continue
        problem = _evidence_problem(reference, root)
        if problem is not None:
            issues.append(Issue("book-evidence", entry_path, problem))
    return issues


def resolve_repo_root(
    project_dir: pathlib.Path | str | None, repo_root: pathlib.Path | str | None = None
) -> pathlib.Path:
    """证据相对路径的锚点：显式 ``repo_root`` > ``project_dir`` 的仓库根 > cwd 的仓库根。"""
    if repo_root is not None:
        return pathlib.Path(repo_root).resolve()
    base = pathlib.Path(project_dir).resolve() if project_dir is not None else pathlib.Path.cwd()
    for candidate in (base, *base.parents):
        if (candidate / ".git").exists():
            return candidate
    return base


def _evidence_problem(reference: str, root: pathlib.Path) -> str | None:
    """``path:line`` 可解析？命令原文直接接受。返回失败说明（``None`` == 通过）。"""
    text = reference.strip()
    lowered = text.lower()
    if any(lowered.startswith(prefix) for prefix in _COMMAND_PREFIXES):
        command = text[len("cmd:") :].strip() if lowered.startswith("cmd:") else text
        return None if command else "command evidence is empty"
    match = _EVIDENCE_REF_RE.match(text)
    if match is None:
        return "expected 'path:line' or a command (cmd: ...)"
    raw_path = match.group("path").strip()
    line = int(match.group("line"))
    candidate = pathlib.Path(raw_path)
    resolved = (candidate if candidate.is_absolute() else (root / candidate)).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return f"path {raw_path!r} is outside the repository {root}"
    if not resolved.is_file():
        return f"file {raw_path!r} does not exist"
    try:
        line_count = len(resolved.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError as exc:
        return f"cannot read {raw_path!r}: {exc}"
    if line < 1 or line > max(line_count, 1):
        return f"line {line} > {line_count} lines of {raw_path!r}"
    if line_count == 0:
        return f"line {line} points into an empty file {raw_path!r}"
    return None


def _limits(
    project_dir: pathlib.Path | str | None, limits: Mapping[str, int] | None
) -> dict[str, int]:
    if limits is not None:
        return {
            "max_state_plus_question_tokens": int(
                limits.get("max_state_plus_question_tokens", DEFAULT_MAX_STATE_PLUS_QUESTION_TOKENS)
            ),
            "max_total_tokens": int(limits.get("max_total_tokens", DEFAULT_MAX_TOTAL_TOKENS)),
            "max_state_bytes": int(limits.get("max_state_bytes", DEFAULT_MAX_STATE_BYTES)),
        }
    resolved = {
        "max_state_plus_question_tokens": DEFAULT_MAX_STATE_PLUS_QUESTION_TOKENS,
        "max_total_tokens": DEFAULT_MAX_TOTAL_TOKENS,
        "max_state_bytes": DEFAULT_MAX_STATE_BYTES,
    }
    if project_dir is None:
        return resolved
    try:
        cfg, _error = decision.DecisionConfig.from_project(project_dir)
    except Exception:  # noqa: BLE001 - 预算闸读配置失败必须是 fail-soft
        return resolved
    for key in resolved:
        value = getattr(cfg, key, None)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            resolved[key] = value
    return resolved


def _check_budget(
    book: Mapping[str, Any],
    dp_id: str,
    *,
    project_dir: pathlib.Path | str | None,
    limits: Mapping[str, int] | None,
) -> list[Issue]:
    """复用 ``decision._estimate_tokens`` + ``.mw/decide.json`` 的闸（AC-019）。"""
    resolved = _limits(project_dir, limits)
    state = dict(book.get("state") or {})
    state_bytes = decision._encode_state(state)
    state_text = state_bytes.decode("utf-8", errors="replace")
    state_tokens = decision._estimate_tokens(state_text)
    issues: list[Issue] = []
    ceiling = resolved["max_state_bytes"]
    if ceiling > 0 and len(state_bytes) > ceiling:
        issues.append(
            Issue("book-budget", "state", f"{len(state_bytes)} bytes > max_state_bytes={ceiling}")
        )
    question_tokens = 0
    for spec in decision_points.questions_map(dp_id).values():
        question_tokens += decision._estimate_tokens(json.dumps(spec, ensure_ascii=False, default=str))
    state_plus_question = state_tokens + max(
        (
            decision._estimate_tokens(json.dumps(spec, ensure_ascii=False, default=str))
            for spec in decision_points.questions_map(dp_id).values()
        ),
        default=0,
    )
    if state_plus_question > resolved["max_state_plus_question_tokens"]:
        issues.append(
            Issue(
                "book-budget",
                "state",
                f"state+longest question is {state_plus_question} tokens > "
                f"max_state_plus_question_tokens={resolved['max_state_plus_question_tokens']} (state={state_tokens})",
            )
        )
    total = state_tokens + question_tokens
    if total > resolved["max_total_tokens"]:
        issues.append(
            Issue(
                "book-budget",
                "state",
                f"request is {total} tokens > max_total_tokens={resolved['max_total_tokens']} "
                f"(state={state_tokens}, questions={question_tokens})",
            )
        )
    return issues


_SECRET_DETAIL = "credential-looking text; redact before sending"

#: 安全路径段：短标识符才原样使用；其他键（含 credential-looking 键）折叠为
#: ``<key>``，拒绝 detail/path 因此不回显恶意键文本或 secret 值。
_SAFE_PATH_SEGMENT_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _secret_scan_segment(key: object, redactor: object | None = None) -> str:
    """A dotted path segment that never echoes an arbitrary key text."""
    text = key if isinstance(key, str) else str(key)
    if _SAFE_PATH_SEGMENT_RE.fullmatch(text) and not decision.secret_hit(text, redactor):
        return text
    return "<key>"


def _iter_secret_texts(value: object, path: str, redactor: object | None = None):
    """递归 ``(path, text)``：每个字符串叶子**与每个对象键**。

    ``Mapping`` / ``list`` / ``tuple`` 都下探（覆盖嵌套对象、数组的数组、
    数组内的对象键）。与 :func:`_flatten` 分离：后者继续把数组当叶子，
    服务于 typed/closed 门（T05c 语义不变）。键路径用调用方的实际 known
    集合脱敏（``_secret_scan_segment``），恶意键不进入诊断。
    """
    if isinstance(value, Mapping):
        for key, child in value.items():
            segment = _secret_scan_segment(key, redactor)
            child_path = f"{path}.{segment}" if path else segment
            if isinstance(key, str) and key:
                yield child_path, key
            yield from _iter_secret_texts(child, child_path, redactor)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from _iter_secret_texts(child, f"{path}[{index}]", redactor)
    elif isinstance(value, str) and value:
        yield path, value


def _check_secrets(
    book: Mapping[str, Any], *, redactor: object | None = None
) -> list[Issue]:
    """Reject a book whose **actual send surface** carries a known secret (AC-019).

    The scan face is :func:`book_state` — the exact object ``mw decide ... --book``
    and the observation seam send — not a second projection of the book: a
    context item's undeclared key is sent, so it must be scanned too (review F2).
    :func:`_iter_secret_texts` walks every string value *and* every object key,
    including nested objects, arrays and arrays of arrays; the typed/closed
    ``_flatten`` gate keeps treating arrays as leaves (T05c semantics untouched).

    ``redactor`` is the call's actual known-secret set
    (:func:`decision.known_secret_redactor`). ``None`` only applies the existing
    env/Bearer/``sk-`` heuristic and does not claim the configured values.
    Diagnostics keep the book's own ``context.<slot>`` prefix while scanning the
    merged ``state.context`` subtree (:func:`_book_secret_path`).
    """
    issues: list[Issue] = []
    seen: set[str] = set()
    for path, text in _iter_secret_texts(book_state(book), "state", redactor):
        if path in seen or not text:
            continue
        if decision.secret_hit(text, redactor):
            seen.add(path)
            issues.append(Issue("book-secret", _book_secret_path(path), _SECRET_DETAIL))
    return issues


def _book_secret_path(path: str) -> str:
    """Keep the book's own diagnostics for the merged ``state.context`` subtree."""
    prefix = "state.context"
    if path == prefix:
        return "context"
    if path.startswith(prefix + "."):
        return "context." + path[len(prefix) + 1 :]
    return path


# ---------------------------------------------------------------------------
# 发送面：state 视图 + 回执
# ---------------------------------------------------------------------------


def book_state(book: Mapping[str, Any]) -> dict:
    """发送用的 state：书的 ``state`` + 顶层 ``context`` 合入 ``state.context``（AC-017）。

    槽位形状与 ``decision_context`` 一致（值是内容），空槽丢弃，未使用的骨架槽位
    不会变成线上字段。
    """
    state = dict(book.get("state") or {})
    context = book.get("context")
    if isinstance(context, Mapping):
        used = {
            slot: content
            for slot, content in context.items()
            if not _is_empty_content(content)
        }
        if used:
            merged = dict(state.get("context") or {}) if isinstance(state.get("context"), Mapping) else {}
            merged.update(used)
            state["context"] = merged
    return state


def book_meta(book: Mapping[str, Any], path: pathlib.Path | str, *, root: pathlib.Path | None = None) -> dict:
    """发送/回执用的 book 元数据（``path`` / ``file_sha256`` / ``evidence``）。"""
    source = pathlib.Path(path)
    display = str(source)
    if root is not None:
        try:
            display = source.resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            display = str(source)
    notes = book.get("notes") if isinstance(book.get("notes"), Mapping) else {}
    evidence = notes.get("evidence") if isinstance(notes.get("evidence"), Mapping) else {}
    return {
        "path": display,
        "file_sha256": book_sha256(source),
        "evidence": dict(evidence),
        "decision_point": book.get("decision_point"),
    }


def append_book_receipt(
    project_dir: pathlib.Path | str,
    *,
    meta: Mapping[str, Any],
    state: Mapping[str, Any],
    available: bool,
    reason: str | None = None,
    decision_id: str | None = None,
    transport: str | None = None,
    now: str | None = None,
) -> pathlib.Path:
    """追加一条 book 回执（``book_path`` + ``file_sha256`` + ``notes.evidence``）。

    ``decisions.jsonl`` 的字段矩阵是封闭的且不归本卡所有，所以 book 的输入元数据
    落在独立账本：一行一次「先验后发」的发送，事后可回答「这份档案用的是哪本书、
    哪个字节版本、哪些证据」。
    """
    path = pathlib.Path(project_dir) / RECEIPTS_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": now or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dp": meta.get("decision_point"),
        "decision_id": decision_id,
        "book_path": meta.get("path"),
        "file_sha256": meta.get("file_sha256"),
        "evidence": dict(meta.get("evidence") or {}),
        "state_digest": state_digest(state),
        "available": bool(available),
        "reason": reason,
        "transport": transport,
    }
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def state_digest(state: object) -> str | None:
    """与档案行同源的 state 摘要（优先用 ``decide_archive`` 的实现）。"""
    try:
        import decide_archive  # type: ignore[import-not-found]  # sibling

        digest = decide_archive.state_digest(state)
        if isinstance(digest, str):
            return digest
    except Exception:  # noqa: BLE001 - 回执不能因兄弟模块缺失而丢行
        pass
    try:
        payload = json.dumps(state, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:  # noqa: BLE001
        return None
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 文件级验收（CLI 面）
# ---------------------------------------------------------------------------


def check_book_file(
    path: pathlib.Path | str,
    *,
    project_dir: pathlib.Path | str | None = None,
    repo_root: pathlib.Path | str | None = None,
    limits: Mapping[str, int] | None = None,
    redactor: object | None = None,
) -> BookReport:
    """装载 + 验收一个文件（支持 ``{"books": {...}}`` 多本示例）。

    ``redactor`` 语义与 :func:`check_book` 相同：生产调用点传入当次实际已知
    凭证集合，离线调用可省略但不得声称完整 known 校验。
    """
    source = pathlib.Path(path)
    report = BookReport(path=str(source), sha256=book_sha256(source))
    try:
        books = load_books(source)
    except BookError as exc:
        report.books.append(
            {"label": None, "decision_point": None, "issues": [exc.issue]}
        )
        return report
    for label, book in books:
        issues = check_book(
            book,
            project_dir=project_dir,
            repo_root=repo_root,
            limits=limits,
            redactor=redactor,
        )
        report.books.append(
            {
                "label": label,
                "decision_point": book.get("decision_point"),
                "issues": issues,
            }
        )
    return report


# ---------------------------------------------------------------------------
# 路径工具（点号路径 ↔ 嵌套对象）
# ---------------------------------------------------------------------------


def _set_path(target: dict, dotted: str, value: object) -> None:
    parts = dotted.split(".")
    current = target
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def _flatten(value: object, prefix: str = "") -> dict[str, Any]:
    """嵌套对象 → ``{dotted_path: leaf}``（空对象/空数组作为叶子保留）。"""
    if isinstance(value, Mapping) and not value and not prefix:
        return {}
    if isinstance(value, Mapping) and value:
        out: dict[str, Any] = {}
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.update(_flatten(child, child_prefix))
        return out
    return {prefix: value}


# Register the book contract as the observation seam's (T05b F2) validator.
decision_points.register_book_validator(observation_book_issues)
