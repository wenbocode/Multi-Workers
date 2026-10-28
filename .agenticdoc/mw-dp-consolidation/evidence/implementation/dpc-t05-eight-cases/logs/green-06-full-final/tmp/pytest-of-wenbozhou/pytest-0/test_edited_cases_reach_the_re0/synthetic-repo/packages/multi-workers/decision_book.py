"""decision_book.py — 八入口决策本的准备、严格验收与档案（T09 / design D-002A）。

决策本（decision book）是八入口决策的**输入文件**。它按 design D-002A 分三层：

* ``material`` —— **业务材料**，只装模型需要判断的业务事实。它的键集合、类型、
  枚举、数组上限、跨字段事实、候选集合与 sign-key 三数组全部由
  :mod:`decision_points`（唯一权威）判定，本模块不复制第二套规则；
* ``preparation`` —— PM 在下发前准备的**依据**（D012A）：
  ``basis_catalog``（每项 ``{id, text, material_refs, applies_to}``）+
  ``prepared_at``。模型在同一次请求里选择其中一项作为理由；失败 reason、概率或
  PM note 都不是依据，因此不在这里；
* 本地 ``meta`` —— key/task_key/trigger_id/真实角色/logical_id，只留在本地，
  **永不发送**，因此不是业务材料的一部分。

另外两个可选面：``context``（可裁剪的工程摘录，槽位由
:mod:`decision_context` 单源决定）和 ``notes.evidence``（每个必填业务字段一条真实
``path:line`` 或命令）。

三条硬规则：

1. **非法状态先拒绝**：业务材料不合法时不再评判依据（依据无法对一个含缺陷的
   材料作出真实引用判断），报出的缺陷就是第一个真实缺陷；
2. **退役编号先拒绝**：25 个旧编号在 material/preparation/replay 之前就被拒绝，
   且拒绝措辞只说明 disposition，绝不映射成别名。旧 ``state`` 形状与自带
   ``questions`` 的决策本同样是历史，一律拒绝而不是升级或绕行；
3. **检查器只报告，不修**：自动补字段等于把「编造」合法化。

检查器与 :func:`decision.DecisionClient.request_prepared` 是同一次判断的两端：
本模块的 :func:`prepare_request` 只在完全没有 issue 时给出
``(material, preparation)``，发送侧再用同一批 registry 校验器复核一次。
"""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import decision
import decision_context
import decision_points

#: 决策本格式版本（顶层 ``schema_version``）。3 = material/meta/preparation 分层；
#: 2（旧 ``state`` 形状）是历史，只读不升级。
BOOK_SCHEMA_VERSION = 3

#: 顶层键的**封闭集合**：``context``/``meta``/``notes`` 可选，其余必填。
BOOK_TOP_LEVEL_KEYS: tuple[str, ...] = (
    "schema_version",
    "decision_point",
    "material",
    "preparation",
    "meta",
    "context",
    "notes",
)

#: 旧合同的顶层键：出现即拒绝（历史只读，不恢复旧调用）。
LEGACY_TOP_LEVEL_KEYS: tuple[str, ...] = ("state",)

#: 本地 meta 的封闭键集合（身份/关联；永不进入 material/preparation/发送体）。
META_KEYS: tuple[str, ...] = (
    "key",
    "task_key",
    "trigger_id",
    "actor_role",
    "logical_id",
)

#: ``notes`` 的封闭键集合：只承载证据引用。
NOTES_KEYS: tuple[str, ...] = ("evidence",)

#: 验收失败码。前七个是旧合同的封闭集合（保留语义，不删除）；后两个是本卡新增
#: 分层的词（依据/本地 meta 各有自己的失败面，不能伪装成业务材料或证据）。
ISSUE_CODES: tuple[str, ...] = (
    "book-schema",
    "book-state",
    "book-preparation",
    "book-meta",
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
#: 依据目录的单条占位符（id/text/refs/applies_to 任一留空都不可发送）。
BASIS_PLACEHOLDER = "<待填: 本依据引用的真实材料事实>"
BASIS_ID_PLACEHOLDER = "<待填: 依据 ID>"
BASIS_CHOICE_PLACEHOLDER = "<待填: 适用的选择 ID>"
PREPARED_AT_PLACEHOLDER = "<待填: ISO-8601 含时区>"

#: ``context`` 的总预算（与 W6 的 4000 B 同源）。
CONTEXT_TOTAL_LIMIT = decision_context.CONTEXT_MAX_BYTES

#: 预算闸的缺省值（与 ``decision.DecisionConfig`` 的内置缺省一致）。
DEFAULT_MAX_STATE_PLUS_QUESTION_TOKENS = 32768
DEFAULT_MAX_TOTAL_TOKENS = 65536
DEFAULT_MAX_STATE_BYTES = 0

#: book 回执账本（相对 project_dir）。
RECEIPTS_RELATIVE_PATH = pathlib.Path(".agenticdoc") / "_autopilot" / "book-receipts.jsonl"

#: 安全路径段：短标识符才原样使用；其他键折叠为 ``<key>``。
_SAFE_PATH_SEGMENT_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _safe_detail_text(value: object, redactor: object | None = None) -> str:
    """``repr`` of a caller-supplied value that never echoes known-secret text.

    The detail stays concrete (the real value is what makes a refusal
    actionable); only material the injected redactor knows collapses to
    ``<redacted>``, the value-side twin of :func:`decision.safe_path_text`.
    """
    text = value if isinstance(value, str) else str(value)
    if text and decision.secret_hit(text, redactor):
        return "<redacted>"
    return repr(value)


def _safe_key_names(
    keys: Iterable[object], redactor: object | None = None
) -> list[str]:
    """Sorted display names for caller-supplied keys (secret/odd keys → ``<key>``)."""
    return sorted({decision.safe_path_text(key, redactor) for key in keys})


def _json_type_name(value: object) -> str:
    """JSON type name of a parsed value (the type, never the value itself)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (list, tuple)):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return type(value).__name__


def _is_schema_version(value: object) -> bool:
    """True only for the real JSON integer ``3``.

    ``3.0``, ``True`` and ``"3"`` are different JSON values, not the schema
    version: a float/boolean/string must be refused instead of matching ``==``.
    """
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value == BOOK_SCHEMA_VERSION
    )


class BookError(ValueError):
    """装载期失败（JSON 不可解析 / 顶层键非法 / 退役 ID / 版本不符）。

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
                    "ok": book["ok"],
                    "issues": [issue.as_dict() for issue in book["issues"]],
                }
                for book in self.books
            ],
            "issues": [issue.as_dict() for issue in self.issues],
        }


@dataclass(frozen=True)
class PreparedRequest:
    """A book that passed every gate: exactly the layers a request may send.

    ``meta`` is local only (it never enters ``material``/``preparation``), and
    ``layers()`` hands out copies so a caller cannot mutate the book through the
    prepared request.
    """

    decision_point: str
    material: dict
    preparation: dict
    meta: dict
    book_path: str | None = None
    file_sha256: str | None = None
    evidence: dict = field(default_factory=dict)

    def layers(self) -> tuple[dict, dict]:
        """``(material, preparation)`` — the two sendable layers, deep-copied."""
        return copy.deepcopy(self.material), copy.deepcopy(self.preparation)


# ---------------------------------------------------------------------------
# 注册表视图（配置是唯一权威：一个判定器，不复制业务规则）
# ---------------------------------------------------------------------------


def _require_active(dp_id: object, redactor: object | None = None) -> str:
    """Resolve one active entry; a retired/unknown id becomes a ``BookError``.

    ``decision_points.require_active_dp`` is the one authority: the refusal names
    the retired disposition and never the successor, because mapping an old id to
    its successor would be an alias.
    """
    try:
        decision_points.require_active_dp(dp_id)  # type: ignore[arg-type]
    except decision.DecisionInputError as exc:
        detail = str(exc)
        if is_retired(dp_id):
            raise BookError("book-schema", "decision_point", detail) from exc
        raise BookError(
            "book-schema",
            "decision_point",
            f"unknown decision point id {_safe_detail_text(dp_id, redactor)}; the "
            "eight active entries are the only book targets",
        ) from exc
    return str(dp_id)


def is_retired(dp_id: object) -> bool:
    """True when ``dp_id`` is one of the 25 retired pre-consolidation ids."""
    return decision_points.is_retired_dp(dp_id)


def registry_points() -> dict[str, dict]:
    """``{dp_id: point}`` 的注册表视图（与 ``decide_registry.json`` 同源）。

    只读视图；调用方（如 autopilot 的决策卡校验）用它读活动入口的字段/问题，
    渲染一律回到 :func:`decision_points.registry_snapshot`，本模块不另存一份。
    """
    snapshot = decision_points.registry_snapshot()
    return {point["id"]: point for point in snapshot["points"]}


def required_state_paths(dp_id: str) -> tuple[str, ...]:
    """该入口必填的业务材料路径（注册表顺序；身份字段不在其中）。"""
    _require_active(dp_id)
    return tuple(decision_points.REQUIRED_STATE_FIELDS.get(dp_id, ()))


def optional_state_paths(dp_id: str) -> tuple[str, ...]:
    """该入口声明的可选业务材料路径（合法但不必填、不需证据）。"""
    _require_active(dp_id)
    return tuple(decision_points.OPTIONAL_STATE_FIELDS.get(dp_id, ()))


def required_fields(dp_id: str) -> list[dict]:
    """该入口的 ``required_state_fields``（``[{name,type,description,...}]``，有序）。

    导出形状复用 :func:`decision_points.snapshot_field_dict`（与 registry/TS 同一
    渲染器），所以 book 面、生成物和发送面看到的是同一份字段合同。
    """
    return [
        decision_points.snapshot_field_dict(path)
        for path in required_state_paths(dp_id)
    ]


def optional_fields(dp_id: str) -> list[dict]:
    """该入口的 ``optional_state_fields``（同一套字段形状，可空）。"""
    return [
        decision_points.snapshot_field_dict(path)
        for path in optional_state_paths(dp_id)
    ]


def field_type(dp_id: str, path: str) -> str | None:
    """注册表声明的该路径类型（``string|integer|number|boolean|array|object``）。"""
    _require_active(dp_id)
    spec = decision_points.STATE_FIELD_DESCRIPTIONS.get(path)
    return str(spec["type"]) if isinstance(spec, Mapping) else None


def context_slots(dp_id: str) -> tuple[str, ...]:
    """该入口允许的上下文槽位（:mod:`decision_context` 单源，无本地兜底表）。"""
    _require_active(dp_id)
    return tuple(decision_context.slot_names_for(dp_id))


@dataclass(frozen=True)
class SlotSpec:
    """一个上下文槽位的形状：``text``（字符上限）或 ``items``（条数 + 单条上限）。"""

    kind: str
    limit: int
    item_max_chars: int = 0
    item_required: tuple[str, ...] = ()


def context_slot_spec(name: str) -> SlotSpec:
    """槽位形状（唯一来源：:mod:`decision_context` 的 ``CONTEXT_SLOTS``）。

    一个未知槽位返回零上限的 ``text`` 形状；它本来就会被「slot not allowed」
    拒绝，所以这里不发明第二个白名单。
    """
    spec = decision_context.slot_spec(name)
    if not isinstance(spec, Mapping):
        return SlotSpec("text", 0)
    if spec.get("type") == "array":
        return SlotSpec(
            "items",
            int(spec.get("max_items") or 0),
            int(spec.get("item_max_chars") or 0),
            tuple(str(key) for key in (spec.get("item_required") or ())),
        )
    return SlotSpec("text", int(spec.get("max_chars") or 0))


def context_evidence_key(slot: str) -> str:
    """已用槽位的来源证据键（AC-017：「每个槽位必须带 source」）。"""
    return f"context.{slot}"


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


def scaffold_material(dp_id: str) -> dict:
    """该入口的业务材料骨架：键集合 == 注册表必填路径，值一律是类型占位符。"""
    material: dict[str, Any] = {}
    for path in required_state_paths(dp_id):
        spec = decision_points.STATE_FIELD_DESCRIPTIONS.get(path) or {}
        _set_path(
            material,
            path,
            type_placeholder(str(spec.get("type") or "string"), str(spec.get("description") or "")),
        )
    return material


def scaffold_preparation(dp_id: str) -> dict:
    """该入口的依据骨架（占位符；``book check`` 一定判它未填）。

    依据是必需、完整、独立的：没有真实 ``basis_catalog`` 与 ``prepared_at`` 就
    不能发送；骨架只给出形状，不替 PM 编造理由。
    """
    _require_active(dp_id)
    return {
        "basis_catalog": [
            {
                "id": BASIS_ID_PLACEHOLDER,
                "text": BASIS_PLACEHOLDER,
                "material_refs": [BASIS_PLACEHOLDER],
                "applies_to": [BASIS_CHOICE_PLACEHOLDER],
            }
        ],
        "prepared_at": PREPARED_AT_PLACEHOLDER,
    }


def scaffold_context(dp_id: str) -> dict:
    """该入口的上下文槽位骨架（``context`` 可选，空值 = 未使用）。"""
    out: dict[str, Any] = {}
    for slot in context_slots(dp_id):
        out[slot] = [] if context_slot_spec(slot).kind == "items" else ""
    return out


def scaffold_book(dp_id: str) -> dict:
    """按注册表生成该入口的决策本骨架（不联网、不读工程现场，D-063）。

    骨架永远不是可发送材料：material/preparation 全是占位符。``meta`` 不在骨架
    里 —— 本地身份是真实生产者的事实，模板不能发明一个。
    """
    dp_id = _require_active(dp_id)
    return {
        "schema_version": BOOK_SCHEMA_VERSION,
        "decision_point": dp_id,
        "material": scaffold_material(dp_id),
        "preparation": scaffold_preparation(dp_id),
        "context": scaffold_context(dp_id),
        "notes": {
            "evidence": {
                path: EVIDENCE_PLACEHOLDER for path in required_state_paths(dp_id)
            }
        },
    }


# ---------------------------------------------------------------------------
# 装载
# ---------------------------------------------------------------------------


def load_book(path: pathlib.Path | str, *, redactor: object | None = None) -> dict:
    """装载一本决策本（单本）：JSON 可解析 + 顶层形状/身份合法。

    失败抛 :class:`BookError`（``code=book-schema``）。装载只回答「这是不是一本
    八入口的书」，取值/依据/证据等由 :func:`check_book` 负责。
    """
    source = pathlib.Path(path)
    data = _read_json(source)
    issues = _schema_issues(data, redactor=redactor)
    if issues:
        first = issues[0]
        raise BookError(first.code, first.path, first.detail)
    return dict(data)  # type: ignore[arg-type]


def load_books(
    path: pathlib.Path | str, *, redactor: object | None = None
) -> list[tuple[str | None, dict]]:
    """装载一个文件里的一本或多本（示例/Smoke 用的 ``{"books": {...}}`` 或数组）。"""
    source = pathlib.Path(path)
    data = _read_json(source)
    return _split_bundle(data, str(source), redactor=redactor)


def _read_json(source: pathlib.Path) -> object:
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise BookError("book-schema", str(source), f"cannot read: {exc}") from exc
    try:
        return json.loads(text)
    except ValueError as exc:
        raise BookError("book-schema", str(source), f"not valid JSON: {exc}") from exc


def _schema_issues(data: object, redactor: object | None = None) -> list[Issue]:
    """Top-level shape + identity: the one gate both ``load`` and ``check`` use.

    A retired id is refused here, before material/preparation/replay: the refusal
    names only the disposition (never the successor) because an old id is history,
    not an alias. The pre-consolidation ``state`` shape and a book-supplied
    ``questions`` set are refused too: they are exactly the two legacy shortcuts
    that would bypass the active entry's contract.
    """
    if not isinstance(data, Mapping):
        return [
            Issue(
                "book-schema",
                "book",
                f"top level must be a JSON object, got {type(data).__name__}",
            )
        ]
    issues: list[Issue] = []
    legacy = [key for key in LEGACY_TOP_LEVEL_KEYS if key in data]
    if legacy:
        issues.append(
            Issue(
                "book-schema",
                legacy[0],
                "the legacy book contract ('state') is read-only history; the "
                "eight-entry book carries 'material' (business facts) and "
                "'preparation' (basis_catalog/prepared_at) instead of one 'state'",
            )
        )
    if "questions" in data:
        issues.append(
            Issue(
                "book-schema",
                "questions",
                "a book may not carry its own question set: the active entry's "
                "registered questions are the only source (legacy questions never "
                "substitute for the active gate)",
            )
        )
    unknown = (
        set(data) - set(BOOK_TOP_LEVEL_KEYS) - set(LEGACY_TOP_LEVEL_KEYS) - {"questions"}
    )
    if unknown:
        issues.append(
            Issue(
                "book-schema",
                "book",
                f"unknown top-level keys {_safe_key_names(unknown, redactor)}",
            )
        )
    version = data.get("schema_version")
    if not _is_schema_version(version):
        issues.append(
            Issue(
                "book-schema",
                "schema_version",
                f"must be {BOOK_SCHEMA_VERSION}, got "
                f"{_safe_detail_text(version, redactor)}",
            )
        )
    dp_id = data.get("decision_point")
    if not isinstance(dp_id, str) or not dp_id.strip():
        issues.append(
            Issue("book-schema", "decision_point", "must be a non-empty string")
        )
    elif decision_points.is_retired_dp(dp_id):
        record = decision_points.retired_dp(dp_id)
        disposition = record.disposition if record is not None else "retired"
        issues.append(
            Issue(
                "book-schema",
                "decision_point",
                f"retired decision point id {_safe_detail_text(dp_id, redactor)} "
                f"({disposition}): not callable; "
                "old ids are read-only history, not aliases",
            )
        )
    else:
        try:
            decision_points.require_active_dp(dp_id)
        except decision.DecisionInputError:
            issues.append(
                Issue(
                    "book-schema",
                    "decision_point",
                    f"unknown decision point id {_safe_detail_text(dp_id, redactor)}; "
                    "the eight active entries are the only book targets",
                )
            )
    for key in ("material", "preparation"):
        if key not in data:
            issues.append(
                Issue("book-schema", key, f"required top-level key {key!r} is missing")
            )
        elif not isinstance(data[key], Mapping):
            issues.append(Issue("book-schema", key, "must be a JSON object"))
    for key in ("meta", "context"):
        if key in data and not isinstance(data[key], Mapping):
            issues.append(Issue("book-schema", key, "must be a JSON object"))
    if "notes" in data:
        notes = data["notes"]
        if not isinstance(notes, Mapping):
            issues.append(Issue("book-schema", "notes", "must be a JSON object"))
        else:
            unknown_notes = set(notes) - set(NOTES_KEYS)
            if unknown_notes:
                issues.append(
                    Issue(
                        "book-schema",
                        "notes",
                        f"unknown notes keys {_safe_key_names(unknown_notes, redactor)}; "
                        f"{list(NOTES_KEYS)} is the only notes face of the book contract",
                    )
                )
            if "evidence" in notes and not isinstance(notes["evidence"], Mapping):
                issues.append(
                    Issue("book-schema", "notes.evidence", "must be a JSON object")
                )
    return issues


def _split_bundle(
    data: object, label: str, redactor: object | None = None
) -> list[tuple[str | None, dict]]:
    if isinstance(data, list):
        return [
            (f"books[{index}]", _load_shape(item, f"{label}[{index}]", redactor=redactor))
            for index, item in enumerate(data)
        ]
    if isinstance(data, Mapping) and "books" in data and set(data) == {"books"}:
        inner = data["books"]
        if isinstance(inner, Mapping):
            return [
                (str(name), _load_shape(item, f"{label}:{name}", redactor=redactor))
                for name, item in inner.items()
            ]
        if isinstance(inner, list):
            return [
                (f"books[{index}]", _load_shape(item, f"{label}[{index}]", redactor=redactor))
                for index, item in enumerate(inner)
            ]
        raise BookError("book-schema", label, "'books' must be an object or an array of books")
    return [(None, _load_shape(data, label, redactor=redactor))]


def _load_shape(
    item: object, label: str, redactor: object | None = None
) -> dict:
    issues = _schema_issues(item, redactor=redactor)
    if issues:
        first = issues[0]
        raise BookError(first.code, first.path, first.detail)
    return dict(item)  # type: ignore[arg-type]


def book_sha256(path: pathlib.Path | str) -> str | None:
    """文件字节的 sha256（读失败返回 ``None``：档案不因读失败而丢行）。"""
    try:
        return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# 验收（封闭集合 / 占位符 / 依据 / 上下文 / 证据 / 预算 / 密钥）
# ---------------------------------------------------------------------------


def is_placeholder(value: object, kind: str | None = None, *, signed: bool = False) -> bool:
    """占位符判定：``<...>``、TBD/TODO/xxx、空串、负数、空数组/对象。

    布尔 ``false`` **不算**占位符：``images_required=false`` 是真实取值。声明为
    ``signed`` 的 integer（dp23 ``snapshot.delta_bytes``）任何负数都是真实取值。
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

    检查顺序就是拒绝顺序：

    1. ``book-schema``：顶层形状/版本/身份（退役 ID 在这里就结束，零材料解析）；
    2. ``book-meta``：本地身份与真实角色的资格（不授权，只判资格）；
    3. ``book-state``：业务材料（缺失/未知键/类型/枚举/跨字段/候选/三数组）；
    4. ``book-preparation``：独立完整的依据目录与 ``prepared_at``；
    5. 占位符、``context``、证据、预算、密钥。

    第 3 步一见缺陷就返回（第 4 步不再评判）：依据的 ``material_refs`` 无法对一个
    含缺陷的材料成立，hard 判定必须是第一个真实缺陷，不能伪造第二个。
    """
    schema = _schema_issues(book, redactor=redactor)
    if schema:
        return schema
    dp_id = str(book["decision_point"])
    material = book.get("material")
    preparation = book.get("preparation")
    assert isinstance(material, Mapping)  # schema gate guarantees it
    assert isinstance(preparation, Mapping)

    issues: list[Issue] = []
    issues.extend(_check_meta(book, dp_id, redactor=redactor))
    material_issues = _check_material(book, dp_id, redactor=redactor)
    issues.extend(material_issues)
    if material_issues:
        return issues
    issues.extend(_check_preparation(book, dp_id, material))
    issues.extend(_check_placeholders(book, dp_id, material, preparation, redactor=redactor))
    issues.extend(_check_context(book, dp_id, redactor=redactor))
    issues.extend(
        _check_evidence(
            book,
            dp_id,
            project_dir=project_dir,
            repo_root=repo_root,
            redactor=redactor,
        )
    )
    issues.extend(_check_budget(book, dp_id, limits=limits))
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
    can never accept a book that ``mw decide book check`` refuses.
    """
    if not isinstance(book, Mapping):
        return (("book", f"must be a JSON object, got {type(book).__name__}"),)
    return tuple(
        (issue.path, f"{issue.code}: {issue.detail}")
        for issue in check_book(book, project_dir=project_dir, redactor=redactor)
    )


def _check_meta(
    book: Mapping[str, Any], dp_id: str, *, redactor: object | None = None
) -> list[Issue]:
    """Local identity: closed keys, non-empty strings, real-role eligibility.

    ``meta`` is optional (a material-only book stays legal), but when it is present
    it is judged completely: a wrong/unknown role is a refusal, and it grants
    nothing (the request entry re-checks the bound actor).
    """
    if "meta" not in book:
        return []
    meta = book.get("meta")
    if not isinstance(meta, Mapping):
        return [Issue("book-meta", "meta", "must be a JSON object")]
    issues: list[Issue] = []
    unknown = sorted(
        {
            _secret_scan_segment(key, redactor)
            for key in set(meta) - set(META_KEYS)
        }
    )
    if unknown:
        issues.append(
            Issue(
                "book-meta",
                "meta",
                f"unknown meta keys {unknown}; local identity is "
                f"{list(META_KEYS)} only",
            )
        )
    for key in META_KEYS:
        if key not in meta:
            continue
        value = meta.get(key)
        if not isinstance(value, str) or not value.strip():
            issues.append(
                Issue("book-meta", f"meta.{key}", "must be a non-empty string")
            )
    if "actor_role" in meta:
        for _path, detail in decision_points.role_issues(dp_id, meta.get("actor_role")):
            issues.append(Issue("book-meta", "meta.actor_role", detail))
    return issues


def _check_material(
    book: Mapping[str, Any], dp_id: str, *, redactor: object | None = None
) -> list[Issue]:
    """业务材料：注册表校验器 + 分层封闭（身份/关联键属于 meta，不属于材料）。"""
    material = book.get("material")
    if not isinstance(material, Mapping):
        return [Issue("book-state", "material", "must be a JSON object")]
    issues = [
        Issue("book-state", f"material.{path}", detail)
        for path, detail in decision_points.entry_material_issues(dp_id, material)
    ]
    forbidden = set(decision_points.STATE_IDENTITY_PATHS) | set(
        decision_points.AUDIT_STATE_PATHS
    )
    for path in _flatten(dict(material)):
        if path not in forbidden:
            continue
        segment = _secret_scan_segment(path, redactor)
        issues.append(
            Issue(
                "book-state",
                f"material.{segment}",
                "is local identity/association meta; it belongs in the book's "
                "'meta' block and is never business material",
            )
        )
    return issues


def _check_preparation(
    book: Mapping[str, Any], dp_id: str, material: Mapping[str, Any]
) -> list[Issue]:
    """PM 准备的依据：完整目录 + 真实引用 + 适用选择 + 带时区的 ``prepared_at``。"""
    preparation = book.get("preparation")
    if not isinstance(preparation, Mapping):
        return [Issue("book-preparation", "preparation", "must be a JSON object")]
    return [
        Issue("book-preparation", _layer_path("preparation", path), detail)
        for path, detail in decision_points.preparation_issues(
            dp_id, preparation, material
        )
    ]


def _layer_path(prefix: str, path: str) -> str:
    """Prefix a layer-relative issue path once (the registry may already name it)."""
    if path == prefix or path.startswith(prefix + "."):
        return path
    return f"{prefix}.{path}"


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


def _string_leaves(value: object, prefix: str = "") -> Iterable[tuple[str, str]]:
    """Every string leaf of ``value`` with its dotted path (used for placeholders)."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            yield from _string_leaves(child, child_prefix)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from _string_leaves(child, f"{prefix}[{index}]")
    elif isinstance(value, str):
        yield prefix, value


def _check_placeholders(
    book: Mapping[str, Any],
    dp_id: str,
    material: Mapping[str, Any],
    preparation: Mapping[str, Any],
    *,
    redactor: object | None = None,
) -> list[Issue]:
    """骨架占位符：必填业务字段 + 依据目录/时间戳。

    ``null`` 在必填路径上是「未替换的值」，无论声明类型（typed 检查按设计跳过
    ``None``，占位符扫描就是必须拦下它的那道门）。声明 ``empty_is_value`` 的数组
    （``[]`` 是真实无）只豁免这一条规则：缺失由 closed-key 报、``null`` 上面拒绝、
    类型错由 book-state 报，元素里的占位文本仍在下面扫。
    """
    issues: list[Issue] = []
    flat = _flatten(dict(material))
    for path in required_state_paths(dp_id):
        if path not in flat:
            continue
        kind = field_type(dp_id, path)
        value = flat[path]
        if value is None:
            issues.append(
                Issue(
                    "book-placeholder",
                    f"material.{path}",
                    "required value is null; fill it from real evidence",
                )
            )
            continue
        if kind is not None and not type_matches(value, kind):
            continue  # 类型错由 book-state 报告，避免一条错误两种码
        spec = decision_points.STATE_FIELD_DESCRIPTIONS.get(path) or {}
        empty_is_value = spec.get("empty_is_value") is True
        if empty_is_value and isinstance(value, (list, dict)) and not value:
            continue
        if is_placeholder(value, kind, signed=bool(spec.get("signed"))):
            issues.append(
                Issue(
                    "book-placeholder",
                    f"material.{path}",
                    f"unreplaced placeholder {_safe_detail_text(value, redactor)}; "
                    "fill it from real evidence",
                )
            )
            continue
        if empty_is_value and isinstance(value, list):
            issues.extend(_placeholder_element_issues(f"material.{path}", value))
    for path, text in _string_leaves(preparation, "preparation"):
        if not is_placeholder(text):
            continue
        issues.append(
            Issue(
                "book-placeholder",
                path,
                "the preparation is still the scaffold placeholder; prepare a real "
                "basis_catalog/prepared_at",
            )
        )
    return issues


def _placeholder_element_issues(path: str, values: Iterable[object]) -> list[Issue]:
    """占位文本元素（仅限声明 ``empty_is_value`` 的数组字段）。"""
    issues: list[Issue] = []
    for index, item in enumerate(values):
        if not is_placeholder(item):
            continue
        issues.append(
            Issue(
                "book-placeholder",
                f"{path}[{index}]",
                "unreplaced placeholder element; fill it with a real value",
            )
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


def _check_context(
    book: Mapping[str, Any], dp_id: str, *, redactor: object | None = None
) -> list[Issue]:
    """上下文槽位：未知槽位 / 已用槽位无来源 / 超长 / 总预算。"""
    context = book.get("context")
    if not isinstance(context, Mapping) or not context:
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
            continue  # 空槽 = 未使用（context 是可选的）
        used.append(str(slot))
        spec = context_slot_spec(str(slot))
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
                    "every used slot needs a source (notes.evidence['context.<slot>'] "
                    "= path:line or command)",
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


def _check_evidence(
    book: Mapping[str, Any],
    dp_id: str,
    *,
    project_dir: pathlib.Path | str | None,
    repo_root: pathlib.Path | str | None,
    redactor: object | None = None,
) -> list[Issue]:
    """每个必填业务字段一条真实证据；可选字段/上下文槽位给了就必须指向真实材料。"""
    notes = book.get("notes") if isinstance(book.get("notes"), Mapping) else {}
    evidence = notes.get("evidence") if isinstance(notes.get("evidence"), Mapping) else {}
    root = resolve_repo_root(project_dir, repo_root)
    issues: list[Issue] = []
    required = required_state_paths(dp_id)
    for path in required:
        if path not in evidence:
            issues.append(
                Issue(
                    "book-evidence",
                    f"notes.evidence.{path}",
                    "missing evidence for a required field",
                )
            )
    allowed_field_keys = set(required) | set(optional_state_paths(dp_id))
    allowed_context_keys = {context_evidence_key(slot) for slot in context_slots(dp_id)}
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
        problem = _evidence_problem(reference, root, redactor=redactor)
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


def _evidence_problem(
    reference: str, root: pathlib.Path, redactor: object | None = None
) -> str | None:
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
    display = _safe_detail_text(raw_path, redactor)
    line = int(match.group("line"))
    candidate = pathlib.Path(raw_path)
    resolved = (candidate if candidate.is_absolute() else (root / candidate)).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return f"path {display} is outside the repository {root}"
    if not resolved.is_file():
        return f"file {display} does not exist"
    try:
        line_count = len(resolved.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError as exc:
        return f"cannot read {display}: {exc}"
    if line < 1 or line > max(line_count, 1):
        return f"line {line} > {line_count} lines of {display}"
    if line_count == 0:
        return f"line {line} points into an empty file {display}"
    return None


def _limits(limits: Mapping[str, int] | None) -> dict[str, int]:
    """The book's size gates: explicit test/CI values win over the package defaults.

    The book is an offline artifact, so it never re-reads ``.mw/decide.json``: the
    runtime budget belongs to the transport (``request_prepared``), and a book
    check must not depend on the caller's live config.
    """
    if limits is None:
        return {
            "max_state_plus_question_tokens": DEFAULT_MAX_STATE_PLUS_QUESTION_TOKENS,
            "max_total_tokens": DEFAULT_MAX_TOTAL_TOKENS,
            "max_state_bytes": DEFAULT_MAX_STATE_BYTES,
        }
    return {
        "max_state_plus_question_tokens": int(
            limits.get("max_state_plus_question_tokens", DEFAULT_MAX_STATE_PLUS_QUESTION_TOKENS)
        ),
        "max_total_tokens": int(limits.get("max_total_tokens", DEFAULT_MAX_TOTAL_TOKENS)),
        "max_state_bytes": int(limits.get("max_state_bytes", DEFAULT_MAX_STATE_BYTES)),
    }


def _check_budget(
    book: Mapping[str, Any],
    dp_id: str,
    *,
    limits: Mapping[str, int] | None,
) -> list[Issue]:
    """The same token/byte gates as the decide layer, on the whole send surface.

    Material + preparation are sent together by ``request_prepared`` and are never
    truncated: over budget is a refusal, not a silent cut of the core evidence.
    """
    resolved = _limits(limits)
    material = book.get("material")
    preparation = book.get("preparation")
    projected = (
        decision_points.model_state_for(dp_id, dict(material))
        if isinstance(material, Mapping)
        else {}
    )
    payload = {"material": projected, "preparation": dict(preparation or {})}
    state_bytes = decision._encode_state(payload)
    state_text = state_bytes.decode("utf-8", errors="replace")
    state_tokens = decision._estimate_tokens(state_text)
    issues: list[Issue] = []
    ceiling = resolved["max_state_bytes"]
    if ceiling > 0 and len(state_bytes) > ceiling:
        issues.append(
            Issue(
                "book-budget",
                "material",
                f"{len(state_bytes)} bytes > max_state_bytes={ceiling}",
            )
        )
    question_tokens = sum(
        decision._estimate_tokens(json.dumps(spec, ensure_ascii=False, default=str))
        for spec in decision_points.questions_map(dp_id).values()
    )
    longest_question = max(
        (
            decision._estimate_tokens(json.dumps(spec, ensure_ascii=False, default=str))
            for spec in decision_points.questions_map(dp_id).values()
        ),
        default=0,
    )
    if state_tokens + longest_question > resolved["max_state_plus_question_tokens"]:
        issues.append(
            Issue(
                "book-budget",
                "material",
                f"material+preparation with the longest question is "
                f"{state_tokens + longest_question} tokens > "
                f"max_state_plus_question_tokens="
                f"{resolved['max_state_plus_question_tokens']}",
            )
        )
    if state_tokens + question_tokens > resolved["max_total_tokens"]:
        issues.append(
            Issue(
                "book-budget",
                "material",
                f"request is {state_tokens + question_tokens} tokens > "
                f"max_total_tokens={resolved['max_total_tokens']}",
            )
        )
    return issues


_SECRET_DETAIL = "credential-looking text; redact before sending"


def _secret_scan_segment(key: object, redactor: object | None = None) -> str:
    """A dotted path segment that never echoes an arbitrary key text."""
    text = key if isinstance(key, str) else str(key)
    if _SAFE_PATH_SEGMENT_RE.fullmatch(text) and not decision.secret_hit(text, redactor):
        return text
    return "<key>"


def _iter_secret_texts(value: object, path: str, redactor: object | None = None):
    """递归 ``(path, text)``：每个字符串叶子**与每个对象键**。"""
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
    """Reject a book whose persisted business layers carry a known secret.

    The book is written to disk, so the scan face is every persisted business layer
    (``material``, ``preparation``, ``context`` and the local ``meta``) — not only
    the projected model body: a value the allowlist would drop is still plaintext
    at rest. ``notes.evidence`` holds ``path:line``/command references, not
    business text, so it is not scanned as a secret carrier.
    """
    issues: list[Issue] = []
    seen: set[str] = set()
    for layer in ("material", "preparation", "context", "meta"):
        if layer not in book:
            continue
        for path, text in _iter_secret_texts(book[layer], layer, redactor):
            if path in seen or not text:
                continue
            if decision.secret_hit(text, redactor):
                seen.add(path)
                issues.append(Issue("book-secret", path, _SECRET_DETAIL))
    return issues


# ---------------------------------------------------------------------------
# 发送面：分层视图 + 准备好的请求 + 回执
# ---------------------------------------------------------------------------


def book_material(book: Mapping[str, Any]) -> dict:
    """The business layer only (deep-copied; never contains ``meta``)."""
    material = book.get("material")
    return copy.deepcopy(dict(material)) if isinstance(material, Mapping) else {}


def book_preparation(book: Mapping[str, Any]) -> dict:
    """The PM-prepared basis layer only (deep-copied)."""
    preparation = book.get("preparation")
    return copy.deepcopy(dict(preparation)) if isinstance(preparation, Mapping) else {}


def book_meta_dict(book: Mapping[str, Any]) -> dict:
    """The local identity layer only (deep-copied; never sent)."""
    meta = book.get("meta")
    return copy.deepcopy(dict(meta)) if isinstance(meta, Mapping) else {}


def book_state(book: Mapping[str, Any]) -> dict:
    """Local state view: business material + the used ``context`` slots.

    ``context`` is the engineered, cuttable block of the decide layer, so it rides
    under ``state["context"]`` exactly like every other producer's local state.
    Empty scaffold slots are dropped; ``meta`` never enters this view.
    """
    state = book_material(book)
    context = book.get("context")
    if isinstance(context, Mapping):
        used = {
            str(slot): copy.deepcopy(content)
            for slot, content in context.items()
            if not _is_empty_content(content)
        }
        if used:
            state[decision_context.CONTEXT_KEY] = used
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


def prepare_request(
    source: Mapping[str, Any] | pathlib.Path | str,
    *,
    project_dir: pathlib.Path | str | None = None,
    repo_root: pathlib.Path | str | None = None,
    limits: Mapping[str, int] | None = None,
    redactor: object | None = None,
) -> tuple[PreparedRequest | None, tuple[Issue, ...]]:
    """Gate one book into the exact layers a prepared request may send.

    Returns ``(prepared, ())`` only when :func:`check_book` reports nothing; any
    issue returns ``(None, issues)``, so a caller that honours this result never
    prepares a request from illegal material. ``source`` is a book object or a
    path; a path carries its byte sha into the result (the receipt joins on it).
    """
    book: dict | None = None
    book_path: str | None = None
    sha: str | None = None
    if isinstance(source, Mapping):
        book = dict(source)
    else:
        path = pathlib.Path(source)
        try:
            book = load_book(path, redactor=redactor)
        except BookError as exc:
            return None, (exc.issue,)
        book_path = str(path)
        sha = book_sha256(path)
    issues = tuple(
        check_book(
            book,
            project_dir=project_dir,
            repo_root=repo_root,
            limits=limits,
            redactor=redactor,
        )
    )
    if issues:
        return None, issues
    notes = book.get("notes") if isinstance(book.get("notes"), Mapping) else {}
    evidence = notes.get("evidence") if isinstance(notes.get("evidence"), Mapping) else {}
    return (
        PreparedRequest(
            decision_point=str(book["decision_point"]),
            material=book_material(book),
            preparation=book_preparation(book),
            meta=book_meta_dict(book),
            book_path=book_path,
            file_sha256=sha,
            evidence=dict(evidence),
        ),
        (),
    )


def prepare_stdin_request(
    payload: str | bytes | Mapping[str, Any],
    *,
    project_dir: pathlib.Path | str | None = None,
    repo_root: pathlib.Path | str | None = None,
    limits: Mapping[str, int] | None = None,
    redactor: object | None = None,
) -> tuple[PreparedRequest | None, tuple[Issue, ...]]:
    """The stdin preparer: exactly one request, no file, no argv state.

    ``payload`` is the raw stdin text (or an already-parsed object). A JSON parse
    failure and a multi-book ``{"books": ...}`` bundle are refusals with a
    concrete issue: stdin carries one request, so there is no implicit "first
    book" default.
    """
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", errors="replace")
    if isinstance(payload, str):
        try:
            data: object = json.loads(payload)
        except ValueError as exc:
            return None, (
                Issue("book-schema", "<stdin>", f"not valid JSON: {exc}"),
            )
    else:
        data = payload
    if isinstance(data, Mapping) and set(data) == {"books"}:
        return None, (
            Issue(
                "book-schema",
                "book",
                "stdin carries exactly one request; a 'books' bundle is a file "
                "format, not a request",
            ),
        )
    if not isinstance(data, Mapping):
        return None, (
            Issue(
                "book-schema",
                "book",
                "stdin carries exactly one book object; got a JSON "
                f"{_json_type_name(data)}, which is not a request (stdin is never "
                "a file path, an array of books or a scalar)",
            ),
        )
    return prepare_request(
        data,  # type: ignore[arg-type]
        project_dir=project_dir,
        repo_root=repo_root,
        limits=limits,
        redactor=redactor,
    )


def append_book_receipt(
    project_dir: pathlib.Path | str,
    *,
    meta: Mapping[str, Any],
    state: Mapping[str, Any],
    preparation: Mapping[str, Any] | None = None,
    available: bool,
    reason: str | None = None,
    decision_id: str | None = None,
    transport: str | None = None,
    now: str | None = None,
) -> pathlib.Path:
    """追加一条 book 回执（``book_path`` + ``file_sha256`` + ``notes.evidence``）。

    ``decisions.jsonl`` 的字段矩阵是封闭的且不归本卡所有，所以 book 的输入元数据
    落在独立账本：一行一次「先验后发」的发送，事后可回答「这份档案用的是哪本书、
    哪个字节版本、哪些证据」。``material_digest``/``preparation_digest`` 分别指向
    两层；``state_digest`` 与 material 摘要同值（旧读取面）。
    """
    path = pathlib.Path(project_dir) / RECEIPTS_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    material_digest = state_digest(state)
    row = {
        "ts": now or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dp": meta.get("decision_point"),
        "decision_id": decision_id,
        "book_path": meta.get("path"),
        "file_sha256": meta.get("file_sha256"),
        "evidence": dict(meta.get("evidence") or {}),
        "state_digest": material_digest,
        "material_digest": material_digest,
        "preparation_digest": state_digest(dict(preparation)) if preparation is not None else None,
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
    """装载 + 验收一个文件（支持 ``{"books": {...}}`` 多本示例）。"""
    source = pathlib.Path(path)
    report = BookReport(path=str(source), sha256=book_sha256(source))
    try:
        books = load_books(source, redactor=redactor)
    except BookError as exc:
        report.books.append(
            {
                "label": None,
                "decision_point": None,
                "ok": False,
                "issues": [exc.issue],
            }
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
                "ok": not issues,
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


# Register the book contract as the observation seam's (T05b F2) validator.
decision_points.register_book_validator(observation_book_issues)
