"""Rebuild the pre-T05e baseline of the four touched files in a temp copy.

Every operation is anchored on text that exists exactly once. After all
reversals each file's SHA256 must equal the hash recorded in baseline-hashes.txt
before the first edit. That proves the temp copy is the real pre-fix source, so
the cold-start RED run against it is a real RED, not a simulation.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

ROOT = pathlib.Path(sys.argv[1])
BASELINE = {
    "decision.py": "917706c22b2f9cd6008e1012a9bc14162256b35b52ee35f2178c669ceb1ea8d2",
    "decision_book.py": "e2140aad87ef4303d1650fd3c7dbcdb061bce648d9f92553bbe2608af54aec04",
    "decision_points.py": "27ccffebb9c37f82ebad3b0ace55d8780b23939532f55c917229837f6c48ee30",
    "mw.py": "5214794799ae680d816a6d7acf4ffc8c114899f073653207e25bdfaf3091fff2",
}

# --- original (pre-fix) blocks -------------------------------------------------

ORIG_CREDENTIAL_REDACTOR = '''def credential_redactor(
    cfg: object = None,
    *,
    extra_secrets: Sequence[str] = (),
    env: Mapping[str, str] | None = None,
    auth_path: pathlib.Path | str | None = None,
):
    """Build the injected known-secret set for wire capture (design §9 / RQ5).

    Includes the actual Authorization value (``cfg.api_key`` or
    ``cfg.extras["api_key"]``), the resolved timi credential (env
    ``TIMI_API_KEY`` or ``~/.pi/agent/auth.json`` ``timi.key``), the existing
    env credential heuristics and the Bearer / ``sk-`` regex layers. Returns
    ``None`` when the side ledger is unavailable (capture stays off). Never
    logs, returns or persists a credential value.
    """
    wire = _wire_module()
    if wire is None:
        return None
    secrets: list[str] = [value for value in extra_secrets if isinstance(value, str)]
    secrets.extend(_credential_values())
    if cfg is not None:
        for holder in (cfg, getattr(cfg, "extras", None)):
            if holder is None:
                continue
            if isinstance(holder, Mapping):
                value = holder.get("api_key")
            else:
                value = getattr(holder, "api_key", None)
            if isinstance(value, str):
                secrets.append(value)
    try:
        import decision_backends

        resolved = decision_backends.resolve_timi_api_key(
            dict(env) if env is not None else None,
            pathlib.Path(auth_path) if auth_path is not None else None,
        )
    except Exception:  # noqa: BLE001 - a missing credential must not break capture
        resolved = None
    if isinstance(resolved, str):
        secrets.append(resolved)
    cleaned: list[str] = []
    for value in secrets:
        if not isinstance(value, str):
            continue
        for candidate in (value, value.strip()):
            if len(candidate) >= _MIN_SECRET_LEN and candidate not in cleaned:
                cleaned.append(candidate)
    return _CredentialRedactor(exact=wire.SubstringRedactor(cleaned))
'''

ORIG_CHECK_BOOK = '''def check_book(
    book: Mapping[str, Any],
    *,
    project_dir: pathlib.Path | str | None = None,
    repo_root: pathlib.Path | str | None = None,
    limits: Mapping[str, int] | None = None,
) -> list[Issue]:
    """验收一本决策本，返回失败列表（空 == 全过）。只报告，不修改入参。

    ``project_dir`` 用于解析预算闸（``.mw/decide.json`` 的 ``max_*``）；
    ``repo_root`` 是证据里相对路径的锚点（缺省取 ``project_dir`` 或当前目录的
    仓库根），``limits`` 允许调用方直接给闸值（测试/CI 用）。
    """
    issues: list[Issue] = []
    issues.extend(_check_schema(book))
    if any(issue.code == "book-schema" for issue in issues):
        return issues
    dp_id = str(book["decision_point"])
    state = dict(book.get("state") or {})
    required = required_state_paths(dp_id)

    flat = _flatten(state)
    issues.extend(_check_state_closed(dp_id, state, flat, required))
    issues.extend(_check_state_types(dp_id, state))
    issues.extend(_check_placeholders(dp_id, flat, required))
    issues.extend(_check_context(book, dp_id))
    issues.extend(_check_evidence(book, dp_id, required, project_dir=project_dir, repo_root=repo_root))
    issues.extend(_check_budget(book, dp_id, project_dir=project_dir, limits=limits))
    issues.extend(_check_secrets(book, state))
    return issues


def observation_book_issues(
    book: Mapping[str, Any],
    project_dir: pathlib.Path | str | None = None,
) -> tuple[tuple[str, str], ...]:
    """``(path, detail)`` for a book the observation seam must refuse (T05b F2).

    ``decision_points.decide_for`` cannot import this module (``decision_book``
    imports it), so it reaches this function through
    :func:`decision_points.register_book_validator`. The verdict is
    :func:`check_book`'s: one authority for the book contract, so an observation
    can never accept a book that ``mw decide book check`` refuses (schema, closed
    state, placeholders, evidence, budget, secrets).
    """
    if not isinstance(book, Mapping):
        return (("book", f"must be a JSON object, got {type(book).__name__}"),)
    return tuple(
        (issue.path, f"{issue.code}: {issue.detail}")
        for issue in check_book(book, project_dir=project_dir)
    )


def _check_schema(book: Mapping[str, Any]) -> list[Issue]:
    if not isinstance(book, Mapping):
        return [Issue("book-schema", "book", f"must be a JSON object, got {type(book).__name__}")]
    issues: list[Issue] = []
    unknown = sorted(set(book) - set(BOOK_TOP_LEVEL_KEYS))
    if unknown:
        issues.append(Issue("book-schema", "book", f"unknown top-level keys {unknown}"))
'''

ORIG_SECRETS = '''def _check_secrets(book: Mapping[str, Any], state: Mapping[str, Any]) -> list[Issue]:
    """复用 ``decision._redact`` 的检测面：脱敏会改动 == 命中凭据（AC-019）。

    遍历用 :func:`_iter_secret_texts`（递归 dict/list 的字符串值与对象键），
    与 :func:`_flatten` 的「数组整体作叶子」规则**分离**：typed/closed 门保持
    T05c 语义，密钥门下探数组元素——dp25 的 ``escalated_reasons`` /
    ``engine_violations`` 与 dp3 ``local_candidates`` 项内的 key 都是真实发送体。
    识别面只复用既有三类（env ``*_API_KEY``/``*_TOKEN``/``*_KEY``/``*_SECRET``/
    ``*_PASSWORD`` 的已知值、``Bearer``、``sk-``），不声称覆盖未知 secret。
    """
    issues: list[Issue] = []
    seen: set[str] = set()
    for path, text in _iter_secret_texts(state, "state"):
        if path in seen or not text:
            continue
        if decision._redact(text) != text:
            seen.add(path)
            issues.append(Issue("book-secret", path, _SECRET_DETAIL))
    context = book.get("context") if isinstance(book.get("context"), Mapping) else {}
    for slot, content in context.items():
        for text in _context_strings(content):
            if text and decision._redact(text) != text:
                issues.append(
                    Issue(
                        "book-secret",
                        f"context.{_secret_scan_segment(slot)}",
                        _SECRET_DETAIL,
                    )
                )
                break
    return issues


def _context_strings(content: object) -> list[str]:
    """槽位值里的所有可能外发字符串（文本/条目字段），用于密钥扫描。"""
    out: list[str] = []
    if isinstance(content, str):
        out.append(content)
    elif isinstance(content, (list, tuple)):
        for item in content:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, Mapping):
                out.extend(
                    str(item[key])
                    for key in ("text", "label", "source", "path")
                    if isinstance(item.get(key), str)
                )
    return out
'''

ORIG_BOOK_GATE = '''def _book_gate(
    source: str, project_dir: pathlib.Path, *, flag: str, dp: str | None = None
) -> tuple[dict | None, dict | None, str | None]:
    """先验后发：装载 + `check_book` + 组发送用的 state。

    返回 ``(state, meta, error)``；``error`` 非空时 ``state`` 为 ``None``，调用方
    必须立即 exit 2 —— 检查失败绝不落到 `DecisionClient`（零 HTTP/零 spawn）。
    """
    try:
        book = decision_book.load_book(source)
    except decision_book.BookError as exc:
        _book_print_issues([exc.issue], flag=flag, source=source)
        return None, None, exc.issue.format()
    issues = decision_book.check_book(book, project_dir=project_dir)
'''

# --- operations ---------------------------------------------------------------

OPS: dict[str, list[tuple]] = {}

OPS["decision.py"] = [
    ("replace", '    "known_credential_values",\n    "known_secret_redactor",\n    "safe_path_text",\n    "secret_hit",\n', ""),
    ("replace", "no value is logged or stored\n    (``repr`` deliberately hides the exact set too).", "no value is logged or stored."),
    ("replace", "    exact: object = field(repr=False)\n", "    exact: object\n"),
    (
        "span",
        "def known_credential_values(",
        '        for segment in text.split(".")\n    )\n',
        ORIG_CREDENTIAL_REDACTOR,
    ),
]

OPS["decision_book.py"] = [
    (
        "span",
        "def check_book(",
        '    if unknown:\n        issues.append(Issue("book-schema", "book", f"unknown top-level keys {unknown}"))\n',
        ORIG_CHECK_BOOK,
    ),
    (
        "replace",
        "def _check_state_closed(\n    dp_id: str,\n    state: Mapping[str, Any],\n    flat: Mapping[str, Any],\n    required: Iterable[str],\n    *,\n    redactor: object | None = None,\n) -> list[Issue]:",
        "def _check_state_closed(\n    dp_id: str, state: Mapping[str, Any], flat: Mapping[str, Any], required: Iterable[str]\n) -> list[Issue]:",
    ),
    (
        "replace",
        "    for path, detail in decision_points.state_unknown_key_issues(\n        dp_id, state, redactor=redactor\n    ):",
        "    for path, detail in decision_points.state_unknown_key_issues(dp_id, state):",
    ),
    (
        "replace",
        "def _check_context(\n    book: Mapping[str, Any], dp_id: str, *, redactor: object | None = None\n) -> list[Issue]:",
        "def _check_context(book: Mapping[str, Any], dp_id: str) -> list[Issue]:",
    ),
    ("replace", '        path = f"context.{_secret_scan_segment(slot, redactor)}"', '        path = f"context.{slot}"'),
    (
        "replace",
        "    repo_root: pathlib.Path | str | None,\n    redactor: object | None = None,\n) -> list[Issue]:",
        "    repo_root: pathlib.Path | str | None,\n) -> list[Issue]:",
    ),
    (
        "replace",
        '        entry_path = f"notes.evidence.{decision.safe_path_text(path, redactor)}"',
        '        entry_path = f"notes.evidence.{path}"',
    ),
    (
        "replace",
        'def _secret_scan_segment(key: object, redactor: object | None = None) -> str:\n    """A dotted path segment that never echoes an arbitrary key text."""\n    text = key if isinstance(key, str) else str(key)\n    if _SAFE_PATH_SEGMENT_RE.fullmatch(text) and not decision.secret_hit(text, redactor):\n        return text\n    return "<key>"',
        'def _secret_scan_segment(key: object) -> str:\n    """A dotted path segment that never echoes an arbitrary key text."""\n    text = key if isinstance(key, str) else str(key)\n    if _SAFE_PATH_SEGMENT_RE.fullmatch(text) and decision._redact(text) == text:\n        return text\n    return "<key>"',
    ),
    (
        "span",
        "def _check_secrets(",
        "        return \"context.\" + path[len(prefix) + 1 :]\n    return path\n",
        ORIG_SECRETS,
    ),
    (
        "replace",
        "    limits: Mapping[str, int] | None = None,\n    redactor: object | None = None,\n) -> BookReport:",
        "    limits: Mapping[str, int] | None = None,\n) -> BookReport:",
    ),
    (
        "replace",
        '    """装载 + 验收一个文件（支持 ``{"books": {...}}`` 多本示例）。\n\n    ``redactor`` 语义与 :func:`check_book` 相同：生产调用点传入当次实际已知\n    凭证集合，离线调用可省略但不得声称完整 known 校验。\n    """',
        '    """装载 + 验收一个文件（支持 ``{"books": {...}}`` 多本示例）。"""',
    ),
    (
        "replace",
        "        issues = check_book(\n            book,\n            project_dir=project_dir,\n            repo_root=repo_root,\n            limits=limits,\n            redactor=redactor,\n        )",
        "        issues = check_book(\n            book, project_dir=project_dir, repo_root=repo_root, limits=limits\n        )",
    ),
    ("replace", "def _iter_secret_texts(value: object, path: str, redactor: object | None = None):", "def _iter_secret_texts(value: object, path: str):"),
    (
        "replace",
        "    服务于 typed/closed 门（T05c 语义不变）。键路径用调用方的实际 known\n    集合脱敏（``_secret_scan_segment``），恶意键不进入诊断。\n",
        "    服务于 typed/closed 门（T05c 语义不变）。\n",
    ),
    ("replace", "            segment = _secret_scan_segment(key, redactor)", "            segment = _secret_scan_segment(key)"),
    ("replace", "            yield from _iter_secret_texts(child, child_path, redactor)", "            yield from _iter_secret_texts(child, child_path)"),
    ('replace', '            yield from _iter_secret_texts(child, f"{path}[{index}]", redactor)', '            yield from _iter_secret_texts(child, f"{path}[{index}]")'),
]

OPS["decision_points.py"] = [
    (
        "replace",
        "def state_unknown_key_issues(\n    dp_id: str,\n    state: Mapping,\n    *,\n    allow_context: bool = False,\n    redactor: object | None = None,\n) -> tuple[tuple[str, str], ...]:",
        "def state_unknown_key_issues(\n    dp_id: str,\n    state: Mapping,\n    *,\n    allow_context: bool = False,\n) -> tuple[tuple[str, str], ...]:",
    ),
    (
        "replace",
        "    paths are the *only* widening (no caller-supplied allowance any more, T05c).\n\n    Returned paths are display paths: the closed-key decision is still made on\n    the raw flattened key (so field associations and the legal set do not\n    change), but a segment that is arbitrary text or known-secret material is\n    reported as ``<key>`` (``decision.safe_path_text``). ``redactor`` is the\n    call's actual known-secret set (F3/T05e); ``None`` keeps the env/Bearer/\n    ``sk-`` heuristic.\n    \"\"\"",
        "    paths are the *only* widening (no caller-supplied allowance any more, T05c).\n    \"\"\"",
    ),
    (
        "replace",
        "        parent_of_required = any(item.startswith(path + \".\") for item in required_set)\n        display = decision.safe_path_text(path, redactor)\n        if parent_of_required:\n            holding = sorted(\n                item for item in required_set if item.startswith(path + \".\")\n            )\n            issues.append((display, f\"must be an object holding {holding}\"))\n        else:\n            issues.append(\n                (display, \"not in required_state_fields (closed key set)\")\n            )",
        "        parent_of_required = any(item.startswith(path + \".\") for item in required_set)\n        if parent_of_required:\n            holding = sorted(\n                item for item in required_set if item.startswith(path + \".\")\n            )\n            issues.append((path, f\"must be an object holding {holding}\"))\n        else:\n            issues.append(\n                (path, \"not in required_state_fields (closed key set)\")\n            )",
    ),
    (
        "replace",
        "    sent_state: Mapping,\n    project: pathlib.Path,\n    redactor: object | None = None,\n) -> tuple[tuple[str, str], ...]:",
        "    sent_state: Mapping,\n    project: pathlib.Path,\n) -> tuple[tuple[str, str], ...]:",
    ),
    ("replace", "        for path, detail in validator(book, project, redactor=redactor):", "        for path, detail in validator(book, project):"),
    (
        "replace",
        "        # The display paths are sanitized with this call's actual known-secret\n        # set (F3/T05e), built only on the refusal path so a legal decision does\n        # not resolve a credential it never echoes.\n        unknown_keys = state_unknown_key_issues(\n            dp_point.id,\n            state,\n            allow_context=True,\n        )\n        if unknown_keys:\n            unknown_keys = state_unknown_key_issues(\n                dp_point.id,\n                state,\n                allow_context=True,\n                redactor=decision.known_secret_redactor(cfg),\n            )\n        contract_issues += unknown_keys",
        "        contract_issues += state_unknown_key_issues(\n            dp_point.id,\n            state,\n            allow_context=True,\n        )",
    ),
    (
        "replace",
        "        book_issues = _observation_book_issues(\n            book,\n            dp_point=dp_point,\n            sent_state=state,\n            project=project,\n            redactor=decision.known_secret_redactor(cfg),\n        )",
        "        book_issues = _observation_book_issues(\n            book, dp_point=dp_point, sent_state=state, project=project\n        )",
    ),
    (
        "replace",
        "\n\n    The registered callable is invoked as\n    ``validator(book, project_dir, *, redactor=<this call's known-secret set>)``\n    (T05e F1); a validator that cannot prove the configured known secrets must\n    refuse rather than silently accept.\n    \"\"\"",
        "\n    \"\"\"",
    ),
    (
        "replace",
        "    unvalidated book is never snapshotted as material.\n\n    ``redactor`` is this call's actual known-secret set\n    (``decision.known_secret_redactor(cfg)``: cfg/Authorization values, the\n    resolved timi credential, env rules + Bearer/``sk-``); it is handed to the\n    registered validator so the observation gate checks the same values the\n    transport is configured with, not only the env heuristic (T05e F1).\n    \"\"\"",
        '    unvalidated book is never snapshotted as material.\n    """',
    ),
]

OPS["mw.py"] = [
    (
        "span",
        "def _book_secret_redactor(",
        "        redactor=_book_secret_redactor(project_dir),\n    )\n",
        ORIG_BOOK_GATE,
    ),
    (
        "replace",
        "    report = decision_book.check_book_file(\n        source,\n        project_dir=project_dir,\n        redactor=_book_secret_redactor(project_dir),\n    )",
        "    report = decision_book.check_book_file(source, project_dir=project_dir)",
    ),
]


def apply(text: str, ops: list[tuple]) -> str:
    for index, op in enumerate(ops):
        if op[0] == "replace":
            _, new, old = op
            count = text.count(new)
            if count != 1:
                raise SystemExit(f"replace {index}: matched {count} times")
            text = text.replace(new, old, 1)
        else:
            _, start, end, replacement = op
            if text.count(start) != 1:
                raise SystemExit(f"span {index}: start matched {text.count(start)} times")
            begin = text.index(start)
            stop = text.index(end, begin)
            stop += len(end)
            text = text[:begin] + replacement + text[stop:]
    return text


for name, ops in OPS.items():
    path = ROOT / name
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    text = apply(text, ops)
    data = text.replace("\n", newline).encode("utf-8")
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    expected = BASELINE[name]
    print(f"{name}: {digest} {'OK' if digest == expected else 'MISMATCH'}")
    if digest != expected:
        sys.exit(1)
