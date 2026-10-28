"""Rebuild the pre-T05g mw.py (working tree, before this card's wiring) in a temp dir."""

from __future__ import annotations

import os
import pathlib
import shutil

SRC = pathlib.Path(r"H:\git\Multi-Workers\packages\multi-workers\mw.py")
DST_DIR = pathlib.Path(os.environ["TEMP"]) / "t05g-attrib"
DST = DST_DIR / "mw.py"

text = SRC.read_text(encoding="utf-8")

PAIRS: list[tuple[str, str]] = [
    (
        """    payload: dict | None = None
    err: str | None = None
    # T05g: one config snapshot for the whole command. The book gate's
    # known-secret set and the client that resolves and sends the Authorization
    # value must come from this same read (T05e review N2); a new command reads
    # again, so a rotation is never half-applied inside one decision.
    cfg = _decide_config_snapshot(project_dir)
    book_source = getattr(args, "book", None)""",
        """    payload: dict | None = None
    err: str | None = None
    book_source = getattr(args, "book", None)""",
    ),
    (
        """        book_state_obj, book_meta, err = _book_gate(
            book_source, project_dir, flag="mw decide run", cfg=cfg
        )""",
        """        book_state_obj, book_meta, err = _book_gate(
            book_source, project_dir, flag="mw decide run"
        )""",
    ),
    (
        """    client = decision.DecisionClient(cfg, project_root=project_dir)
    if payload.get("questions"):""",
        """    cfg, _cfg_err = decision.DecisionConfig.from_project(project_dir)
    client = decision.DecisionClient(cfg, project_root=project_dir)
    if payload.get("questions"):""",
    ),
    (
        """    source = getattr(args, "file", None)
    # One snapshot for the command; ``check`` never constructs a client, so the
    # gate's known set is the only consumer of the config read here (T05g).
    cfg = _decide_config_snapshot(project_dir)
    report = decision_book.check_book_file(
        source,
        project_dir=project_dir,
        redactor=_book_secret_redactor(cfg),
    )""",
        """    source = getattr(args, "file", None)
    report = decision_book.check_book_file(
        source,
        project_dir=project_dir,
        redactor=_book_secret_redactor(project_dir),
    )""",
    ),
    (
        """    # T05g: the same single snapshot feeds the book gate and the client below.
    cfg = _decide_config_snapshot(project_dir)
    book_source = getattr(args, "book", None)""",
        """    book_source = getattr(args, "book", None)""",
    ),
    (
        """        state, book_meta, err = _book_gate(
            book_source, project_dir, flag="mw decide ask", cfg=cfg
        )""",
        """        state, book_meta, err = _book_gate(book_source, project_dir, flag="mw decide ask")""",
    ),
    (
        """    if cfg is None:
        # A config read that raised: the gate above already ran on the
        # env/Bearer/``sk-`` layers; the fallback stays disabled, so zero send.
        cfg = decision.DecisionConfig(project_root=project_dir)
    if cfg.unconfigured:""",
        """    cfg, _cfg_err = decision.DecisionConfig.from_project(project_dir)
    if cfg.unconfigured:""",
    ),
    (
        '''def _decide_config_snapshot(
    project_dir: pathlib.Path,
) -> decision.DecisionConfig | None:
    """Read ``.mw/decide.json`` exactly once for this command (T05g).

    The book gate's known-secret set and the client that resolves the
    Authorization value must come from one config read: two independent reads
    open a rotation window where a value rotated in between them is sent while
    the gate set still holds the old one (T05e review N2). Every command reads
    once, so the next command picks the rotation up.

    Fail-soft, like the gate it serves: a raising read yields ``None`` so the
    gate keeps the env/``Bearer``/``sk-`` layers (a broken config never skips
    the gate) and the caller falls back to an unconfigured transport, which
    sends nothing.
    """
    try:
        cfg, _error = decision.DecisionConfig.from_project(project_dir)
    except Exception:  # noqa: BLE001 - the gate must still run on a broken config
        return None
    return cfg


def _book_secret_redactor(cfg: object = None):
    """The known-secret set of *this* command for the book gate (T05e F1/T05g).

    ``cfg`` is the caller's single :class:`decision.DecisionConfig` snapshot
    (:func:`_decide_config_snapshot`) - the same object the transport client is
    built on, so the gate set and the sent Authorization value cannot come from
    two different config reads. Discovery stays in
    ``decision.known_secret_redactor`` (``cfg.api_key`` /
    ``cfg.extras["api_key"]``, the resolved timi credential and the env
    heuristics) and does not require the optional wire module (a disabled
    capture must not downgrade the gate). ``cfg=None`` keeps the env/Bearer/
    ``sk-`` layers instead of skipping the gate. Values stay in memory; nothing
    is logged.
    """
    return decision.known_secret_redactor(cfg)


def _book_gate(
    source: str,
    project_dir: pathlib.Path,
    *,
    flag: str,
    dp: str | None = None,
    cfg: decision.DecisionConfig | None = None,
) -> tuple[dict | None, dict | None, str | None]:''',
        '''def _book_secret_redactor(project_dir: pathlib.Path):
    """The project's actual known-secret set for the book gate (T05e F1).

    One authority with the wire capture: ``decision.known_secret_redactor``
    resolves ``cfg.api_key`` / ``cfg.extras["api_key"]`` (the actual
    Authorization value), the resolved timi credential and the existing env
    heuristics, and does not require the optional wire module (a disabled
    capture must not downgrade the gate). Fail-soft: a broken config still
    yields the env/Bearer/``sk-`` layers instead of skipping the gate. Values
    stay in memory; nothing is logged.
    """
    try:
        cfg, _error = decision.DecisionConfig.from_project(project_dir)
    except Exception:  # noqa: BLE001 - the gate must still run on a broken config
        cfg = None
    return decision.known_secret_redactor(cfg)


def _book_gate(
    source: str, project_dir: pathlib.Path, *, flag: str, dp: str | None = None
) -> tuple[dict | None, dict | None, str | None]:''',
    ),
    (
        """    密钥门用**当次项目配置的实际 known 集合**（T05e F1），不只看 env 启发式；
    ``cfg`` 是调用方逐命令读取的唯一快照（T05g），门与发送因此不会来自两次读。
    \"\"\"
    try:
        book = decision_book.load_book(source)
    except decision_book.BookError as exc:
        _book_print_issues([exc.issue], flag=flag, source=source)
        return None, None, exc.issue.format()
    issues = decision_book.check_book(
        book,
        project_dir=project_dir,
        redactor=_book_secret_redactor(cfg),
    )""",
        """    密钥门用**当次项目配置的实际 known 集合**（T05e F1），不只看 env 启发式。
    \"\"\"
    try:
        book = decision_book.load_book(source)
    except decision_book.BookError as exc:
        _book_print_issues([exc.issue], flag=flag, source=source)
        return None, None, exc.issue.format()
    issues = decision_book.check_book(
        book,
        project_dir=project_dir,
        redactor=_book_secret_redactor(project_dir),
    )""",
    ),
]

for new, old in PAIRS:
    count = text.count(new)
    assert count == 1, f"expected exactly one occurrence, got {count}: {new.splitlines()[0]!r}"
    text = text.replace(new, old, 1)

COMMENT = """    # One snapshot for the command; ``check`` never constructs a client, so the
    # gate's known set is the only consumer of the config read here (T05g).
"""
assert COMMENT not in text

DST_DIR.mkdir(parents=True, exist_ok=True)
DST.write_text(text, encoding="utf-8", newline="\n")

ref = DST_DIR / "decision_backends.py"
if not ref.exists():
    for name in ("decision.py", "decision_points.py", "decision_book.py", "decision_backends.py",
                 "decision_wire.py", "decision_context.py", "decide_archive.py", "mw_common.py"):
        shutil.copy2(SRC.parent / name, DST_DIR / name)
    shutil.copy2(SRC.parent / "decide_registry.json", DST_DIR / "decide_registry.json")

print("rebuilt pre-T05g mw.py:", DST)
print("contains _decide_config_snapshot:", "_decide_config_snapshot(" in text)
