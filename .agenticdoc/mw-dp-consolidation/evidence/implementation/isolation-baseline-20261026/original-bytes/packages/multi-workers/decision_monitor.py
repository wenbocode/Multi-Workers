"""decision_monitor.py - standalone local monitor service (mw-decision-dashboard T10).

The dashboard needs a small interactive service that can show project history
and run explicit DP test submissions without borrowing ``mw serve``'s
credentials or lifecycle (design D-001). This module owns exactly that
*process-level* half:

* **port/lifecycle identity** - deterministic candidates inside
  ``43170..43269``, bind-and-hold with Windows exclusivity
  (``SO_EXCLUSIVEADDRUSE``), a no-secret ``.mw/decide-monitor.json`` identity
  file, the control token in the separate ``.mw/decide-monitor.secret``, and a
  ``.mw/decide-monitor.start.lock`` owned through :mod:`mw_common`'s
  ``O_CREAT|O_EXCL`` protocol with the owner's PID start time;
* **conservative recovery** - a crashed instance may only be moved aside when
  all three conditions hold inside the start lock: its recorded owner is
  *provably* dead, the recorded loopback port answers an explicit
  ``ECONNREFUSED`` (the Windows ``WSAECONNREFUSED``/10061 equivalent included),
  and the identity still matches on a second read. A timeout, an unknown probe
  error, a successful connection (even to an unrelated process) or a recycled
  PID keeps the state and returns a manual recovery guide; alive, unprobeable,
  malformed state is never touched. Live incompatible instances are replaced
  only by an explicit CLI open after authenticated shutdown and process-exit
  proof under the start lock. ``recover_stale``
  refuses to run without a verifiable :class:`StartLockGuard` (a bare call
  takes the lock itself) and re-checks the state/secret identity between steps
  so a freshly published secret is never moved;
* **token roles** - a 256-bit control token (health/shutdown/new window code),
  in-memory page tokens minted by a single-use 60s boot code, and long-lived
  tokens that never appear in a URL or an argv;
* **the HTTP boundary** - exact ``Host``, exact ``Origin`` for POSTs, a closed
  ``Sec-Fetch-Site`` set, a 256 KiB body cap, no CORS and no cookies, a fixed
  route set with no file-path routing, and response envelopes
  ``{ok, data, error{code,message,issues}, capture_status}``;
* **read/playground seams** - history comes from the read-only T07 fold behind
  a mandatory credential redactor (fail-closed when none is configured), the DP
  registry is exposed read-only, and every playground route is a *dependency
  injection* point: without a T06 provider the routes answer
  ``playground-unavailable`` and make zero model calls. Only an explicit
  ``/api/test/submit`` can ever reach the provider.

Nothing here executes a business action or writes a production ledger. Command
startup builds one in-memory credential redactor for safe historical text; no
history GET, poll, health check or import discovers credentials. Window launching
is reduced to argv construction plus an injectable spawner that reports explicit
failure instead of a false success. The dashboard assets and CLI wiring belong
to T11/T12.

Failure shapes are always explicit (``MonitorError.kind``): ``range-exhausted``,
``start-lock-conflict``, ``instance-live``, ``instance-unresponsive``,
``instance-unknown``, ``incompatible-instance``, ``stop-failed``,
``starter-failed``, ``health-failed``.
"""

from __future__ import annotations

import contextlib
import dataclasses
import errno
import hashlib
import hmac
import http.server
import json
import os
import pathlib
import re
import secrets
import socket
import socketserver
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Iterator, Mapping, Sequence

import decision
import decision_history
import decision_points
import decision_wire
import mw_common

# ── Contract constants (design §4.2/§9) ─────────────────────────────────────

HOST = "127.0.0.1"
PORT_RANGE: tuple[int, int] = (43170, 43269)
PROTOCOL_VERSION = 1
STATE_SCHEMA = 1
STATE_DIR = ".mw"
STATE_NAME = "decide-monitor.json"
SECRET_NAME = "decide-monitor.secret"
START_LOCK_NAME = "decide-monitor.start.lock"

BODY_LIMIT_BYTES = 256 * 1024
BOOT_CODE_TTL_S = 60.0
START_LOCK_BUDGET_S = 0.25
START_LOCK_RETRIES = 5
START_LOCK_BASE_DELAY = 0.008
HEALTH_WAIT_S = 5.0
HEALTH_TIMEOUT_S = 1.0
START_TOLERANCE_MS = 5_000
TOKEN_BYTES = 32
LISTEN_BACKLOG = 64

#: A stale-port observation must be long enough for Windows to report
#: ``WSAECONNREFUSED`` on a closed loopback port (the RST may follow a retry).
PROBE_TIMEOUT_S = 3.0
#: The only error numbers that prove a *refused* loopback connection: POSIX
#: ``ECONNREFUSED`` and the Windows ``WSAECONNREFUSED`` (10061) equivalent.
REFUSED_ERRNOS = frozenset({errno.ECONNREFUSED, 10061})
PORT_PROBE_RESULTS = ("refused", "connected", "unknown")

DEFAULT_PAGE_LIMIT = decision_history.DEFAULT_PAGE_LIMIT

CAPTURE_STATES = ("disabled", "unavailable", "enabled")
TRANSPORT_STATES = ("ok", "rate-limited", "unavailable", "unknown")
SEC_FETCH_SITE_ALLOWED = ("same-origin", "none")

#: Single header carrying either token role; the role is resolved server-side.
TOKEN_HEADER = "X-MW-Monitor-Token"

_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "connect-src 'self'; img-src 'self'; base-uri 'none'; "
    "form-action 'none'; frame-ancestors 'none'"
)

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_SUBMIT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

SUBMIT_KEYS = frozenset({"dp", "book", "submit_id", "observe_only", "retry_of", "questions"})
#: Fields a page must never be able to smuggle in (AC-017). The monitor never
#: executes business actions or edits authorization, so these are refused before
#: any provider is consulted.
FORBIDDEN_KEYS = frozenset(
    {
        "act",
        "acted",
        "action",
        "apply",
        "args",
        "archive",
        "authority",
        "authorization",
        "authorize",
        "executor",
        "exec",
        "project",
        "project_id",
        "actor",
        "write_path",
        "book_path",
        "command",
    }
)

#: Mandatory T06 provider duties behind ``/api/test/submit`` (AC-017). The
#: monitor only refuses obvious *structural* smuggling (below); the provider
#: must still validate the whole book with ``decision_book.check_book``.
PLAYGROUND_PROVIDER_OBLIGATIONS = (
    "call decision_book.check_book(book, project_dir=control_root) before any model call",
    "closed key set: refuse unknown top-level and state keys (the registry is the authority)",
    "declared types, enums, max_items and cross-field rules from the registry",
    "placeholder/evidence/budget checks: an unfilled book is never sent",
    "secret scan (book-secret): credential-looking text is refused before the wire",
    "observe-only: never execute a business action, executor call or authorization change",
)

#: State identity fields every dp's builder writes (``STRUCTURAL_STATE_FIELDS``
#: in ``decision_book``); they are legal even when the registry omits them.
_STATE_STRUCTURAL_FIELDS = frozenset({"schema_version", "decision_point", "questions_version"})

#: Fixed static route -> shipped asset file (the file is the single source; the
#: monitor never keeps a second inline copy of the page).
ASSET_DIR = pathlib.Path(__file__).resolve().parent
ASSET_FILES: dict[str, str] = {
    "/": "decision_dashboard.html",
    "/app.css": "decision_dashboard.css",
    "/app.js": "decision_dashboard.js",
}
ASSET_CONTENT_TYPES: dict[str, str] = {
    "/": "text/html; charset=utf-8",
    "/app.css": "text/css; charset=utf-8",
    "/app.js": "text/javascript; charset=utf-8",
}


def load_static_assets() -> dict[str, tuple[str, str]]:
    """Read the shipped dashboard assets (UTF-8 text, fixed route set)."""
    assets: dict[str, tuple[str, str]] = {}
    for path, name in ASSET_FILES.items():
        text = (ASSET_DIR / name).read_text(encoding="utf-8")
        assets[path] = (ASSET_CONTENT_TYPES[path], text)
    return assets


STATIC_ASSETS: dict[str, tuple[str, str]] = load_static_assets()

# ── Offline workbench cases (design §4.5 / D007) ────────────────────────────

#: The *only* four synthetic cases the workbench ships. The table is the whole
#: lookup: a caller never supplies a path, a filename or a directory, and the
#: directory is never scanned, so the route cannot be pointed elsewhere.
CASE_VERSION = 1
DECIDE_CASES_DIR = ASSET_DIR / "decide_cases"
CASE_IDS: dict[str, str] = {
    "dp1-dispatch-type": "dp1.json",
    "dp2-checkpoint-split": "dp2.json",
    "dp3-worker-clarify": "dp3.json",
    "dp25-signoff-conclusion": "dp25.json",
}
_CASE_SHELL_KEYS = frozenset({"case_version", "dp", "title", "note", "questions", "book"})


# ── Errors ──────────────────────────────────────────────────────────────────


class MonitorError(RuntimeError):
    """An explicit lifecycle refusal (``kind`` is the machine-readable part)."""

    def __init__(
        self,
        kind: str,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
        guide: Sequence[str] | None = None,
    ) -> None:
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message
        self.details = dict(details or {})
        self.guide = list(guide or [])

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "message": self.message,
            "details": dict(self.details),
            "guide": list(self.guide),
        }


class _ApiError(Exception):
    """One refused HTTP request (never carries a credential).

    ``data`` is only used by the *provider* busy case: HTTP 409 must still show
    the page what the provider said (no submission was written, no model call
    was made) instead of an opaque error. Every other refusal carries ``None``.
    """

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        issues: Sequence[str] | None = None,
        data: object = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.issues = list(issues or [])
        self.data = data


class CaseError(RuntimeError):
    """A refused offline case read (``kind`` is the machine-readable part).

    Kinds: ``case-unknown`` (not one of the four ids), ``case-unsafe`` (the
    fixed slot escaped its directory / became a symlink), ``case-missing``
    (the shipped file is absent or unreadable) and ``case-invalid`` (the file
    is not a well-formed case shell). The message never echoes file content.
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message


# ── Offline case loading (fixed table, no caller path) ──────────────────────


def _case_directory(cases_dir: pathlib.Path | str | None) -> pathlib.Path:
    return DECIDE_CASES_DIR if cases_dir is None else pathlib.Path(cases_dir).resolve()


def _case_file_path(dp_id: object, cases_dir: pathlib.Path | str | None = None) -> pathlib.Path:
    """The one legal file for ``dp_id``; every other shape is refused."""
    if not isinstance(dp_id, str) or dp_id not in CASE_IDS:
        raise CaseError("case-unknown", "not one of the four offline workbench cases")
    directory = _case_directory(cases_dir)
    path = directory / CASE_IDS[dp_id]
    try:
        resolved = path.resolve(strict=False)
    except OSError as exc:  # pragma: no cover - platform path failure
        raise CaseError("case-unsafe", "the case path could not be resolved") from exc
    # The resolved slot must stay directly inside the fixed directory, so a
    # symlinked file/directory (or a replaced parent) cannot redirect the read.
    if resolved.parent != directory:
        raise CaseError("case-unsafe", "the case file resolves outside the fixed case directory")
    if path.is_symlink() or resolved.is_symlink():
        raise CaseError("case-unsafe", "case files must not be symlinks")
    return path


def _read_case_bytes(path: pathlib.Path) -> bytes:
    """Read the shipped bytes and re-check the opened file's identity."""
    try:
        before = os.lstat(path)
    except FileNotFoundError as exc:
        raise CaseError("case-missing", "the case file is not shipped in this build") from exc
    except OSError as exc:
        raise CaseError("case-missing", "the case file is unreadable") from exc
    if stat.S_ISLNK(before.st_mode):
        raise CaseError("case-unsafe", "case files must not be symlinks")
    try:
        with open(path, "rb") as handle:
            after = os.fstat(handle.fileno())
            if (after.st_dev, after.st_ino, after.st_size) != (
                before.st_dev,
                before.st_ino,
                before.st_size,
            ):
                raise CaseError("case-unsafe", "the case file changed identity while it was opened")
            return handle.read()
    except CaseError:
        raise
    except FileNotFoundError as exc:
        raise CaseError("case-missing", "the case file is not shipped in this build") from exc
    except OSError as exc:
        raise CaseError("case-missing", "the case file is unreadable") from exc


def _validate_case(raw: bytes, dp_id: str) -> dict:
    """Validate the case *shell*; ``title``/``note`` stay outside the book.

    ``questions`` (T10) is the case's complete native question set: the same
    strict DP mapping / type / instructions / criteria gate the observation path
    applies, checked against the case state that would be sent. A slugged or
    hand-edited shell that does not carry it is refused instead of silently
    falling back to a second question source.
    """
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise CaseError("case-invalid", "the case file is not valid UTF-8 JSON") from exc
    if not isinstance(parsed, dict) or set(parsed) != _CASE_SHELL_KEYS:
        raise CaseError(
            "case-invalid",
            "the case shell must be exactly case_version/dp/title/note/questions/book",
        )
    if parsed.get("case_version") != CASE_VERSION:
        raise CaseError("case-invalid", f"case_version must be {CASE_VERSION}")
    if parsed.get("dp") != dp_id:
        raise CaseError("case-invalid", "the case file names a different decision point")
    title = parsed.get("title")
    note = parsed.get("note")
    if not isinstance(title, str) or not title.strip():
        raise CaseError("case-invalid", "the case title is missing")
    if not isinstance(note, str) or not note.strip():
        raise CaseError("case-invalid", "the case note is missing")
    book = parsed.get("book")
    if not isinstance(book, dict):
        raise CaseError("case-invalid", "case.book must be a JSON object")
    if book.get("decision_point") != dp_id:
        raise CaseError("case-invalid", "case.book names a different decision point")
    if not isinstance(book.get("state"), dict):
        raise CaseError("case-invalid", "case.book.state must be a JSON object")
    questions = parsed.get("questions")
    if not isinstance(questions, dict):
        raise CaseError("case-invalid", "case.questions must be a JSON object")
    try:
        issues = decision_points.question_override_issues(dp_id, questions, book["state"])
    except decision.DecisionInputError as exc:
        raise CaseError("case-invalid", "the case names an unregistered decision point") from exc
    if issues:
        # Field paths and registry-owned text only: never a submitted value.
        detail = "; ".join(f"{path}: {issue}" for path, issue in issues)
        raise CaseError("case-invalid", f"the case questions are not legal ({detail})"[:400])
    serialised = json.dumps(book, ensure_ascii=False, sort_keys=True)
    if title in serialised or note in serialised:
        raise CaseError("case-invalid", "the shell title/note leaked into the sent book")
    questions_text = json.dumps(questions, ensure_ascii=False, sort_keys=True)
    if questions_text in serialised:
        raise CaseError("case-invalid", "the shell questions leaked into the sent book")
    return parsed


def load_case(
    dp_id: str, *, cases_dir: pathlib.Path | str | None = None
) -> dict:
    """Read one fixed-slot offline case (no model, no credential, no write).

    ``cases_dir`` exists only so tests can prove the containment/symlink rules;
    the HTTP route always uses :data:`DECIDE_CASES_DIR`.
    """
    path = _case_file_path(dp_id, cases_dir)
    return _validate_case(_read_case_bytes(path), dp_id)


def case_book_bytes(book: Mapping[str, object]) -> bytes:
    """Canonical JSON bytes of a case book (the object actually handed on)."""
    return json.dumps(book, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def case_book_digest(book: Mapping[str, object]) -> str:
    """SHA-256 of :func:`case_book_bytes` (integrity only, never a secrecy proof)."""
    return hashlib.sha256(case_book_bytes(book)).hexdigest()


# ── Identity ────────────────────────────────────────────────────────────────


def _compute_code_fingerprint() -> str:
    """Hash the monitor source and fixed shipped UI assets, with length framing."""
    digest = hashlib.sha256()
    sources = [("decision_monitor.py", pathlib.Path(__file__))]
    sources.extend((name, ASSET_DIR / name) for name in sorted(ASSET_FILES.values()))
    for name, path in sources:
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise MonitorError(
                "instance-unknown",
                f"cannot fingerprint the monitor source asset {name}; compatibility is unknown",
            ) from exc
        label = name.encode("utf-8")
        digest.update(len(label).to_bytes(8, "big"))
        digest.update(label)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()[:16]


CODE_FINGERPRINT = _compute_code_fingerprint()


def code_fingerprint() -> str:
    """Import-time fingerprint of monitor source + shipped UI (health identity)."""
    return CODE_FINGERPRINT


def _mw_dir(control_root: pathlib.Path | str) -> pathlib.Path:
    return pathlib.Path(control_root) / STATE_DIR


def state_path(control_root: pathlib.Path | str) -> pathlib.Path:
    return _mw_dir(control_root) / STATE_NAME


def secret_path(control_root: pathlib.Path | str) -> pathlib.Path:
    return _mw_dir(control_root) / SECRET_NAME


def start_lock_path(control_root: pathlib.Path | str) -> pathlib.Path:
    return _mw_dir(control_root) / START_LOCK_NAME


@dataclasses.dataclass(frozen=True)
class InstanceIdentity:
    """The no-secret identity published in ``.mw/decide-monitor.json``."""

    project_id: str
    instance_id: str
    pid: int
    pid_start_ms: int | None
    port: int
    protocol_version: int = PROTOCOL_VERSION
    code_fingerprint: str = CODE_FINGERPRINT
    schema: int = STATE_SCHEMA

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "protocol_version": self.protocol_version,
            "project_id": self.project_id,
            "instance_id": self.instance_id,
            "pid": self.pid,
            "pid_start_ms": self.pid_start_ms,
            "port": self.port,
            "code_fingerprint": self.code_fingerprint,
        }


_TEXT_STATE_FIELDS = ("project_id", "instance_id", "code_fingerprint")
_INT_STATE_FIELDS = ("pid", "port", "protocol_version")


def _identity_problem(raw: object) -> str | None:
    """Why ``raw`` is not a usable identity document (``None`` = usable)."""
    if not isinstance(raw, dict):
        return "instance state is not a JSON object"
    if raw.get("schema") != STATE_SCHEMA:
        return f"instance state has an unsupported schema ({raw.get('schema')!r})"
    for name in _TEXT_STATE_FIELDS:
        value = raw.get(name)
        if not isinstance(value, str) or not value:
            return f"instance state field {name!r} is missing or not a string"
    for name in _INT_STATE_FIELDS:
        value = raw.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return f"instance state field {name!r} is missing or not a positive integer"
    start = raw.get("pid_start_ms")
    if start is not None and (isinstance(start, bool) or not isinstance(start, int)):
        return "instance state field 'pid_start_ms' is not an integer"
    return None


def identity_from_state(
    raw: Mapping[str, object], *, control_root: pathlib.Path | str | None = None
) -> InstanceIdentity:
    """Validated identity from a state document, or an explicit refusal."""
    problem = _identity_problem(dict(raw))
    if problem is not None:
        raise MonitorError(
            "instance-unknown",
            problem,
            details={"problem": problem},
            guide=recovery_guide(control_root) if control_root is not None else [],
        )
    return InstanceIdentity(
        project_id=str(raw["project_id"]),
        instance_id=str(raw["instance_id"]),
        pid=int(raw["pid"]),  # type: ignore[arg-type]
        pid_start_ms=None if raw.get("pid_start_ms") is None else int(raw["pid_start_ms"]),  # type: ignore[arg-type]
        port=int(raw["port"]),  # type: ignore[arg-type]
        protocol_version=int(raw["protocol_version"]),  # type: ignore[arg-type]
        code_fingerprint=str(raw["code_fingerprint"]),
        schema=int(raw["schema"]),  # type: ignore[arg-type]
    )


def recovery_guide(control_root: pathlib.Path | str) -> list[str]:
    """Manual recovery steps for every ``unknown``/conflict exit.

    Conservative recovery never deletes or kills; when it refuses, the operator
    needs the exact files and the safe order of operations.
    """
    root = pathlib.Path(control_root)
    return [
        "confirm no monitor process is running for this project (Task Manager / ps: 'decision_monitor')",
        f"if and only if none is running, delete {state_path(root)} and {secret_path(root)} manually",
        "if a process is still running, stop it with 'mw decide monitor stop' instead of deleting its state",
        "then reopen the dashboard with 'mw decide monitor'",
    ]


# ── State / secret publication ──────────────────────────────────────────────


def read_state(control_root: pathlib.Path | str) -> tuple[dict | None, str | None]:
    """``(state, problem)``: ``(None, None)`` when no state file exists."""
    path = state_path(control_root)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, None
    except (OSError, UnicodeDecodeError):
        return None, f"instance state {path} is unreadable; treating it as unknown"
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None, f"instance state {path} is not valid JSON; treating it as unknown"
    problem = _identity_problem(parsed)
    if problem is not None:
        return None, problem
    return parsed, None


def _atomic_write(path: pathlib.Path, data: bytes, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    fd = os.open(str(tmp), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600 if mode is not None else 0o644)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:  # pragma: no cover - a zero write is an OS failure
                raise OSError(f"short write to {tmp}")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        if mode is not None and sys.platform != "win32":
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def publish_state(control_root: pathlib.Path | str, identity: InstanceIdentity) -> pathlib.Path:
    """Atomically publish the identity document (never any token)."""
    path = state_path(control_root)
    payload = json.dumps(identity.as_dict(), sort_keys=True, ensure_ascii=False) + "\n"
    _atomic_write(path, payload.encode("utf-8"))
    return path


def publish_secret(control_root: pathlib.Path | str, token: str) -> pathlib.Path:
    """Atomically publish the control token (owner-only mode on POSIX)."""
    if not isinstance(token, str) or not token:
        raise ValueError("control token must be a non-empty string")
    path = secret_path(control_root)
    _atomic_write(path, (token + "\n").encode("utf-8"), mode=0o600)
    return path


def read_secret(control_root: pathlib.Path | str) -> str | None:
    try:
        token = secret_path(control_root).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return token or None


def generate_token() -> str:
    """A 256-bit random token as lowercase hex."""
    return secrets.token_hex(TOKEN_BYTES)


# ── Tokens and roles ────────────────────────────────────────────────────────


@dataclasses.dataclass
class TokenStore:
    """Control token plus in-memory single-use boot codes and page tokens."""

    control_token: str = dataclasses.field(default_factory=generate_token)
    clock: Callable[[], float] = time.monotonic
    page_tokens: dict[str, float] = dataclasses.field(default_factory=dict)
    boot_codes: dict[str, float] = dataclasses.field(default_factory=dict)

    def role_for(self, token: object) -> str | None:
        if not isinstance(token, str) or not token:
            return None
        if self.control_token and hmac.compare_digest(token, self.control_token):
            return "control"
        for candidate in self.page_tokens:
            if hmac.compare_digest(token, candidate):
                return "page"
        return None

    def issue_boot_code(self) -> str:
        now = self.clock()
        expired = [
            code
            for code, issued in self.boot_codes.items()
            if now - issued > BOOT_CODE_TTL_S
        ]
        for code in expired:
            self.boot_codes.pop(code, None)
        code = generate_token()
        self.boot_codes[code] = now
        return code

    def redeem_boot_code(self, code: object) -> str | None:
        """Exchange one fresh code for a page token; every failure is ``None``."""
        if not isinstance(code, str) or not code:
            return None
        issued = self.boot_codes.pop(code, None)
        if issued is None:
            return None
        if self.clock() - issued > BOOT_CODE_TTL_S:
            return None
        token = generate_token()
        self.page_tokens[token] = self.clock()
        return token


# ── Port binding ────────────────────────────────────────────────────────────


def _new_listener_socket() -> socket.socket:
    """A loopback listener with the strongest exclusivity the OS offers.

    Windows defaults to ``SO_EXCLUSIVEADDRUSE`` deliberately: ``SO_REUSEADDR``
    there lets a second process steal a bound port. POSIX explicitly disables
    ``SO_REUSEADDR`` instead (there is no exclusive-addr option).
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if sys.platform == "win32" and exclusive is not None:
            sock.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    except OSError:
        sock.close()
        raise
    return sock


def port_candidates(
    project_id: str, port_range: tuple[int, int] = PORT_RANGE
) -> tuple[int, ...]:
    """Deterministic candidate order: project hash picks the start offset."""
    start, end = int(port_range[0]), int(port_range[1])
    if start <= 0 or end < start:
        raise ValueError(f"invalid port range {port_range!r}")
    size = end - start + 1
    digest = hashlib.sha256(str(project_id).encode("utf-8")).digest()
    offset = int.from_bytes(digest[:4], "big") % size
    return tuple(start + (offset + index) % size for index in range(size))


def bind_listener(
    *,
    project_id: str,
    port_range: tuple[int, int] = PORT_RANGE,
    host: str = HOST,
) -> tuple[socket.socket, int]:
    """Bind-and-hold the first free candidate; never probe-then-release."""
    attempted: list[dict[str, object]] = []
    for port in port_candidates(project_id, port_range):
        sock = _new_listener_socket()
        try:
            sock.bind((host, port))
            sock.listen(LISTEN_BACKLOG)
        except OSError as exc:
            sock.close()
            attempted.append({"port": port, "error": exc.__class__.__name__})
            continue
        return sock, port
    raise MonitorError(
        "range-exhausted",
        (
            f"every port in {port_range[0]}..{port_range[1]} is already bound on {host}; "
            "no process was stopped - free a port or stop the other monitor"
        ),
        details={
            "port_range": [int(port_range[0]), int(port_range[1])],
            "attempted": attempted[:20],
            "attempted_count": len(attempted),
        },
        guide=[
            "find the listener with 'netstat -ano | findstr <port>' (Windows) or 'ss -lptn'",
            "stop that program yourself, or wait for it to exit",
            "rerun 'mw decide monitor' - it never kills an unrelated process",
        ],
    )


# ── Start lock and conservative recovery ────────────────────────────────────


def _require_project_match(identity: InstanceIdentity, control_root: pathlib.Path) -> None:
    """A state document from another project is never recovered or reused."""
    expected = decision_wire.project_id_for(control_root)
    if identity.project_id != expected:
        raise MonitorError(
            "incompatible-instance",
            (
                f"{state_path(control_root)} belongs to project {identity.project_id}, "
                f"not to this control root ({expected}); nothing was moved"
            ),
            details={"expected_project_id": expected, "recorded_project_id": identity.project_id},
            guide=recovery_guide(control_root),
        )


def _move_aside(path: pathlib.Path, *, suffix: str) -> pathlib.Path | None:
    """Rename ``path`` to an isolated stale name, never overwriting evidence."""
    source = pathlib.Path(path)
    if not source.exists():
        return None
    base = source.with_name(f"{source.name}.stale-{suffix}")
    target = base
    counter = 1
    while target.exists():
        target = base.with_name(f"{base.name}.{counter}")
        counter += 1
    os.replace(source, target)
    return target


def _release_own_start_lock(lock: pathlib.Path) -> None:
    """Release only a lock that still carries this process' identity."""
    owner = mw_common.read_lock_owner(lock)
    if owner is None:
        return
    if owner["pid"] != os.getpid():
        return
    recorded_start = owner["start_ms"]
    current = mw_common.process_start_ms(os.getpid())
    if (
        recorded_start is not None
        and current is not None
        and abs(current - recorded_start) > START_TOLERANCE_MS
    ):
        return
    mw_common.release_lock(lock)


@dataclasses.dataclass(frozen=True)
class StartLockGuard:
    """Proof that *this* process holds the start lock for ``control_root``.

    Recovery must never move files based on a bare function call: the caller
    passes the guard returned by :func:`start_lock`, and every destructive step
    re-verifies it (owner PID + start time, still the same file).
    """

    control_root: pathlib.Path
    path: pathlib.Path
    pid: int
    start_ms: int | None

    def verify(self) -> None:
        """Raise ``start-lock-conflict`` unless this guard still owns the lock."""
        if self.pid != os.getpid():
            raise MonitorError(
                "start-lock-conflict",
                "the start-lock guard does not belong to this process; nothing was moved",
                details={"lock": str(self.path), "guard_pid": self.pid},
                guide=recovery_guide(self.control_root),
            )
        owner = mw_common.read_lock_owner(self.path)
        if (
            owner is None
            or owner["pid"] != self.pid
            or owner["start_ms"] != self.start_ms
        ):
            raise MonitorError(
                "start-lock-conflict",
                (
                    f"{self.path} is no longer held by this process; "
                    "the remaining recovery steps were not performed"
                ),
                details={"lock": str(self.path), "guard_pid": self.pid, "owner": owner},
                guide=recovery_guide(self.control_root),
            )


def _acquire_start_lock(
    lock: pathlib.Path,
    *,
    budget_s: float,
    alive_state_probe: Callable[[int], str] | None,
) -> None:
    deadline = time.monotonic() + max(budget_s, 0.0)
    try:
        mw_common.acquire_lock(
            lock,
            retries=START_LOCK_RETRIES,
            base_delay=START_LOCK_BASE_DELAY,
            deadline_s=max(budget_s, 0.0),
        )
        return
    except RuntimeError:
        pass
    state = mw_common.lock_owner_state(lock, alive_state_probe=alive_state_probe)
    root = lock.parent.parent
    if state["state"] == "dead":
        owner = mw_common.read_lock_owner(lock)
        if (
            owner is None
            or owner["pid"] != state["pid"]
            or owner["start_ms"] != state["start_ms"]
        ):
            # TOCTOU: the lock was replaced after it was classified dead.
            raise MonitorError(
                "start-lock-conflict",
                f"the identity of {lock} changed while it was inspected; nothing was moved",
                details={key: state[key] for key in ("state", "pid", "start_ms", "detail")},
                guide=recovery_guide(root),
            )
        _move_aside(lock, suffix=str(owner["pid"]))
        remaining = max(0.0, deadline - time.monotonic())
        try:
            mw_common.acquire_lock(
                lock,
                retries=START_LOCK_RETRIES,
                base_delay=START_LOCK_BASE_DELAY,
                deadline_s=remaining,
            )
            return
        except RuntimeError as exc:
            raise MonitorError(
                "start-lock-conflict",
                f"another starter claimed {lock} after the dead owner was moved aside ({exc})",
                details=state,
                guide=recovery_guide(root),
            ) from exc
    raise MonitorError(
        "start-lock-conflict",
        (
            f"another starter holds {lock} ({state['detail']}); "
            "no state, secret or process was touched"
        ),
        details={key: state[key] for key in ("state", "pid", "start_ms", "detail")},
        guide=recovery_guide(root),
    )


@contextlib.contextmanager
def start_lock(
    control_root: pathlib.Path | str,
    *,
    budget_s: float = START_LOCK_BUDGET_S,
    alive_state_probe: Callable[[int], str] | None = None,
) -> Iterator[StartLockGuard]:
    """Hold the start lock and yield a verifiable guard (never a bare path)."""
    root = pathlib.Path(control_root)
    lock = start_lock_path(root)
    lock.parent.mkdir(parents=True, exist_ok=True)
    _acquire_start_lock(lock, budget_s=budget_s, alive_state_probe=alive_state_probe)
    try:
        record = mw_common.write_lock_owner(lock)
    except Exception:
        mw_common.release_lock(lock)
        raise
    guard = StartLockGuard(
        control_root=root,
        path=lock,
        pid=int(record["pid"]),
        start_ms=record["start_ms"],
    )
    try:
        yield guard
    finally:
        _release_own_start_lock(lock)


def classify_connect_error(exc: BaseException) -> str:
    """Map a socket failure to ``refused`` | ``unknown`` (never a guess).

    Only an explicit refusal counts. ``ECONNREFUSED`` and the Windows
    ``WSAECONNREFUSED``/10061 code are the design's proof; a timeout, an
    access/ACL refusal (EPERM/EACCES), a reset or any other error proves nothing
    and must keep the recorded state.
    """
    if isinstance(exc, ConnectionRefusedError):
        return "refused"
    code = getattr(exc, "winerror", None)
    if code is None:
        code = getattr(exc, "errno", None)
    return "refused" if code in REFUSED_ERRNOS else "unknown"


def probe_recorded_port(port: int, *, timeout: float = PROBE_TIMEOUT_S) -> dict[str, object]:
    """Observe the recorded loopback port: refused, connected, or unknown.

    The result never carries a token or response body - only the classification,
    the port and an error number/class name, so it is safe to record verbatim.
    """
    observation: dict[str, object] = {
        "result": "unknown",
        "port": int(port),
        "errno": None,
        "detail": None,
    }
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(float(timeout))
        sock.connect((HOST, int(port)))
    except OSError as exc:
        result = classify_connect_error(exc)
        observation["result"] = result
        observation["errno"] = getattr(exc, "winerror", None) or getattr(exc, "errno", None)
        observation["detail"] = "connection refused" if result == "refused" else type(exc).__name__
    except (OverflowError, ValueError) as exc:  # a recorded port out of range proves nothing
        observation["detail"] = type(exc).__name__
    else:
        observation["result"] = "connected"
        observation["detail"] = "a listener answered on the recorded port"
    finally:
        sock.close()
    return observation


def _port_observation(port: int, probe: Callable[[int], str] | None = None) -> dict[str, object]:
    """The real probe, or an injected one (tests); both produce the same shape."""
    if probe is None:
        return probe_recorded_port(port)
    try:
        result = probe(int(port))
    except Exception:  # noqa: BLE001 - a broken probe proves nothing
        result = "unknown"
    if result not in PORT_PROBE_RESULTS:
        result = "unknown"
    return {"result": result, "port": int(port), "errno": None, "detail": "injected probe"}


def _file_identity(path: pathlib.Path) -> tuple[int, int, int] | None:
    """Stable identity of one material file (inode/size/mtime) or ``None``."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return (int(stat.st_ino), int(stat.st_size), int(stat.st_mtime_ns))


def _identity_liveness(
    identity: InstanceIdentity,
    *,
    alive_state_probe: Callable[[int], str] | None = None,
    start_ms_probe: Callable[[int], int | None] | None = None,
) -> str:
    """``alive`` | ``dead`` | ``unknown``; only ``dead`` permits recovery."""
    probe = alive_state_probe or mw_common.process_alive_state
    start_probe = start_ms_probe or mw_common.process_start_ms
    try:
        liveness = probe(identity.pid)
    except Exception:  # noqa: BLE001 - a broken probe proves nothing
        return "unknown"
    if liveness not in ("alive", "dead"):
        return "unknown"
    if liveness == "dead":
        return "dead"
    if identity.pid_start_ms is None:
        return "unknown"
    try:
        observed = start_probe(identity.pid)
    except Exception:  # noqa: BLE001 - a broken probe proves nothing
        return "unknown"
    if observed is None:
        return "unknown"
    if abs(observed - identity.pid_start_ms) > START_TOLERANCE_MS:
        return "unknown"
    return "alive"


def recover_stale(
    control_root: pathlib.Path | str,
    *,
    guard: StartLockGuard | None = None,
    alive_state_probe: Callable[[int], str] | None = None,
    start_ms_probe: Callable[[int], int | None] | None = None,
    port_probe: Callable[[int], str] | None = None,
    lock_budget_s: float = START_LOCK_BUDGET_S,
) -> dict[str, object]:
    """Move a crashed instance's state/secret aside, one identity-checked step at a time.

    Three conditions must hold under the start lock (design D-001/AC-007):

    1. the recorded PID is *provably* dead (``_identity_liveness``);
    2. the recorded port answers an explicit ``ECONNREFUSED``/10061
       (:func:`probe_recorded_port`); a timeout, an unrelated listener or any
       other error is ``unknown`` and keeps the state;
    3. the identity still matches on a re-read inside the lock.

    ``guard`` is the verifiable proof of the lock. A bare call acquires the
    start lock itself (and releases it afterwards); a call made with a stale or
    foreign guard is refused before anything is moved. The order stays
    state-then-secret: after the state move the state/secret identities are
    re-read, and a newly published state or a rewritten secret stops the
    process with ``secret_preserved=True`` instead of moving fresh material.
    """
    root = pathlib.Path(control_root)
    if guard is None:
        with start_lock(
            root, budget_s=lock_budget_s, alive_state_probe=alive_state_probe
        ) as acquired:
            return _recover_stale_locked(
                root,
                acquired,
                alive_state_probe=alive_state_probe,
                start_ms_probe=start_ms_probe,
                port_probe=port_probe,
            )
    guard.verify()
    return _recover_stale_locked(
        root,
        guard,
        alive_state_probe=alive_state_probe,
        start_ms_probe=start_ms_probe,
        port_probe=port_probe,
    )


def _recover_stale_locked(
    root: pathlib.Path,
    guard: StartLockGuard,
    *,
    alive_state_probe: Callable[[int], str] | None = None,
    start_ms_probe: Callable[[int], int | None] | None = None,
    port_probe: Callable[[int], str] | None = None,
) -> dict[str, object]:
    guard.verify()
    state, problem = read_state(root)
    if problem is not None:
        raise MonitorError(
            "instance-unknown", problem, details={"problem": problem}, guide=recovery_guide(root)
        )
    moved: list[str] = []
    if state is None:
        # An orphan secret can only exist if publication was interrupted before
        # the state was written; nobody can be serving it, so isolate it.
        guard.verify()
        if _move_aside(secret_path(root), suffix="orphan") is not None:
            moved.append("secret")
        return {
            "recovered": False,
            "instance_id": None,
            "moved": moved,
            "guide": [],
            "liveness": None,
            "port_probe": None,
        }

    identity = identity_from_state(state, control_root=root)
    _require_project_match(identity, root)
    liveness = _identity_liveness(
        identity, alive_state_probe=alive_state_probe, start_ms_probe=start_ms_probe
    )
    if liveness == "alive":
        raise MonitorError(
            "instance-live",
            f"PID {identity.pid} is alive and owns {state_path(root)}; refusing to move its state",
            details={"state": state, "liveness": liveness},
            guide=recovery_guide(root),
        )
    if liveness == "unknown":
        raise MonitorError(
            "instance-unknown",
            f"cannot prove PID {identity.pid} is dead; refusing to move the recorded state",
            details={"state": state, "liveness": liveness},
            guide=recovery_guide(root),
        )

    observation = _port_observation(identity.port, port_probe)
    if observation["result"] != "refused":
        raise MonitorError(
            "instance-unknown",
            (
                f"the recorded port {identity.port} did not refuse a loopback connection "
                f"(probe={observation['result']}); only an explicit ECONNREFUSED with a "
                "provably dead owner permits recovery, so the state was kept"
            ),
            details={"state": state, "liveness": liveness, "port_probe": observation},
            guide=recovery_guide(root),
        )

    # Condition 3: re-read the identity inside the lock (TOCTOU) before moving.
    confirmed, problem2 = read_state(root)
    if (
        problem2 is not None
        or confirmed is None
        or identity_from_state(confirmed, control_root=root) != identity
    ):
        raise MonitorError(
            "instance-unknown",
            "the instance state changed while recovery was being decided; nothing was moved",
            details={"state": confirmed, "liveness": liveness, "port_probe": observation},
            guide=recovery_guide(root),
        )

    secret_before = _file_identity(secret_path(root))
    guard.verify()
    _move_aside(state_path(root), suffix=identity.instance_id)
    moved.append("state")

    # Step 2 re-check: a state that reappeared (or a rewritten secret) belongs
    # to a new instance; the remaining material must be preserved untouched.
    after, after_problem = read_state(root)
    if after_problem is not None or after is not None:
        raise MonitorError(
            "instance-unknown",
            (
                "a new instance state appeared after the stale state was moved; "
                "its secret/state were left in place"
            ),
            details={
                "moved": list(moved),
                "secret_preserved": True,
                "state": after,
                "liveness": liveness,
                "port_probe": observation,
            },
            guide=recovery_guide(root),
        )
    if _file_identity(secret_path(root)) != secret_before:
        raise MonitorError(
            "instance-unknown",
            (
                "the secret changed after the stale state was moved; it was left in place "
                "instead of being moved with this recovery"
            ),
            details={
                "moved": list(moved),
                "secret_preserved": True,
                "liveness": liveness,
                "port_probe": observation,
            },
            guide=recovery_guide(root),
        )

    guard.verify()
    if _move_aside(secret_path(root), suffix=identity.instance_id) is not None:
        moved.append("secret")
    return {
        "recovered": True,
        "instance_id": identity.instance_id,
        "moved": moved,
        "guide": [],
        "liveness": liveness,
        "port_probe": observation,
    }


# ── Health probe ────────────────────────────────────────────────────────────


def health(port: int, token: str, *, timeout: float = HEALTH_TIMEOUT_S) -> dict | None:
    """The health document, or ``None`` for any failure (no exception leak)."""
    request = urllib.request.Request(
        f"http://{HOST}:{int(port)}/api/health",
        headers={TOKEN_HEADER: str(token)},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - loopback only
            raw = response.read()
    except (urllib.error.URLError, OSError, ValueError):
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def identity_matches(data: object, identity: InstanceIdentity) -> bool:
    """Full identity comparison: project, instance, protocol, code, PID start."""
    if not isinstance(data, dict):
        return False
    for name in ("project_id", "instance_id", "code_fingerprint"):
        if data.get(name) != getattr(identity, name):
            return False
    for name in ("protocol_version", "pid", "port"):
        if data.get(name) != getattr(identity, name):
            return False
    expected_start = identity.pid_start_ms
    observed_start = data.get("pid_start_ms")
    if expected_start is not None:
        if isinstance(observed_start, bool) or not isinstance(observed_start, int):
            return False
        if abs(observed_start - expected_start) > START_TOLERANCE_MS:
            return False
    return True


def wait_health(
    port: int,
    token: str | None,
    identity: InstanceIdentity,
    *,
    timeout_s: float = HEALTH_WAIT_S,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[bool, str | None]:
    """Poll until the endpoint reports *this* identity; timeout proves nothing."""
    if token is None:
        return False, "the control token is missing, so health cannot be authenticated"
    deadline = time.monotonic() + timeout_s
    last = "no response"
    while True:
        data = health(port, token)
        if data is not None:
            if identity_matches(data, identity):
                return True, None
            last = "the health endpoint reports a different identity"
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False, last
        sleep(min(0.05, remaining))


# ── HTTP layer ──────────────────────────────────────────────────────────────


def _redact_text(redactor: object | None, text: object) -> str:
    if redactor is None:
        return "<unavailable>"
    try:
        return redactor.redact(str(text)).text  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - an unusable redactor is fail-closed
        return "<redaction-failed>"


def _redact_payload(payload: object, redactor: object | None) -> object:
    """Redact every string in a response payload (keys stay structural)."""
    if redactor is None:
        return payload
    if isinstance(payload, str):
        return _redact_text(redactor, payload)
    if isinstance(payload, Mapping):
        return {key: _redact_payload(value, redactor) for key, value in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [_redact_payload(item, redactor) for item in payload]
    return payload


_CAPTURE_RANK = {None: 0, "ok": 1, "partial": 2, "failed": 3}


def _worst_capture_status(statuses: Sequence[object]) -> str | None:
    best: str | None = None
    for status in statuses:
        if status not in _CAPTURE_RANK:
            continue
        if _CAPTURE_RANK[status] > _CAPTURE_RANK[best]:  # type: ignore[index]
            best = status  # type: ignore[assignment]
    return best


def _redaction_summary(records: Sequence[object], redactor: object | None) -> dict[str, object]:
    """Snapshot-level free-text policy, aggregated from the per-record marks."""
    marks = [
        record.get("redaction")
        for record in records
        if isinstance(record, Mapping) and isinstance(record.get("redaction"), Mapping)
    ]
    return {
        "enabled": redactor is not None,
        "records_with_substitutions": sum(
            1 for mark in marks if mark.get("substitutions")  # type: ignore[union-attr]
        ),
        "records_with_truncation": sum(
            1 for mark in marks if mark.get("truncated_fields")  # type: ignore[union-attr]
        ),
        "records_with_omissions": sum(
            1 for mark in marks if mark.get("omitted_fields")  # type: ignore[union-attr]
        ),
    }


def _ok_envelope(data: object, capture_status: str | None = None) -> dict[str, object]:
    return {"ok": True, "data": data, "error": None, "capture_status": capture_status}


def _error_envelope(exc: _ApiError) -> dict[str, object]:
    return {
        "ok": False,
        "data": exc.data,
        "error": {"code": exc.code, "message": exc.message, "issues": list(exc.issues)},
        "capture_status": None,
    }


def _safe_names(names: Sequence[str]) -> list[str]:
    """Echo field names only when they look like identifiers (never payloads)."""
    return [name if isinstance(name, str) and _SAFE_NAME.match(name) else "<unnamed>" for name in names]


def _json_object(body: bytes) -> dict:
    if not body:
        return {}
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise _ApiError(400, "invalid-body", "the request body must be UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise _ApiError(400, "invalid-body", "the request body must be a JSON object")
    return parsed


def _closed_json(
    body: bytes,
    *,
    allowed: frozenset[str],
    forbidden: frozenset[str] = frozenset(),
) -> dict:
    raw = _json_object(body)
    refused = sorted(set(raw) & set(forbidden))
    if refused:
        raise _ApiError(
            400,
            "forbidden-field",
            "the monitor refuses execution/authorization fields: "
            + ", ".join(_safe_names(refused)),
            issues=_safe_names(refused),
        )
    unknown = sorted(set(raw) - set(allowed) - set(forbidden))
    if unknown:
        raise _ApiError(
            400,
            "unknown-field",
            "unknown field(s): " + ", ".join(_safe_names(unknown)),
            issues=_safe_names(unknown),
        )
    return raw


def _book_state_scope(dp: str) -> tuple[set[str], set[str], set[str]]:
    """Registered state paths for ``dp``: full paths, container prefixes, free subtrees.

    ``decision_points`` is the same registry authority ``decision_book``
    consumes, so this never invents a second field vocabulary. Declared
    ``object`` fields (dp1 ``history``) own their whole subtree, exactly like
    ``decision_book._check_state_closed`` accepts descendants of an optional
    object.
    """
    required = set(decision_points.REQUIRED_STATE_FIELDS.get(dp, ()))
    optional = set(decision_points.OPTIONAL_STATE_FIELDS.get(dp, ()))
    full = required | optional | set(_STATE_STRUCTURAL_FIELDS)
    free = {
        path
        for path in full
        if (decision_points.STATE_FIELD_DESCRIPTIONS.get(path) or {}).get("type") == "object"
    }
    prefixes: set[str] = set()
    for path in full:
        parts = path.split(".")
        for index in range(1, len(parts)):
            prefixes.add(".".join(parts[:index]))
    return full, prefixes, free


def _scan_smuggled_keys(
    node: object,
    prefix: str,
    full: set[str],
    prefixes: set[str],
    free: set[str],
    found: list[str],
) -> None:
    """Collect forbidden key names that are *not* registered typed business fields."""
    if isinstance(node, Mapping):
        for key, value in node.items():
            name = str(key)
            path = f"{prefix}.{name}" if prefix else name
            if (
                name in FORBIDDEN_KEYS
                and path not in full
                and path not in prefixes
                and not any(path.startswith(f"{item}.") for item in free)
            ):
                found.append(path)
            if path in free:
                continue  # a declared object subtree is the provider's closed-set concern
            if path in full and path not in prefixes:
                continue  # a declared typed value: the provider owns its type/shape
            _scan_smuggled_keys(value, path, full, prefixes, free, found)
        return
    if isinstance(node, (list, tuple)):
        for item in node:
            _scan_smuggled_keys(item, prefix, full, prefixes, free, found)


def _smuggled_book_paths(book: Mapping[str, object], dp: str) -> list[str]:
    """Defense-in-depth scan of the submitted book (AC-017 / VC-015).

    This is *not* ``check_book``: it only refuses execution/authorization key
    names that the dp's registry does not declare, at any nesting level. Real
    typed fields whose names merely look forbidden (dp12 ``action.command``,
    dp24 ``project.path``, dp1 ``history`` subtrees) are left for the provider,
    so a legitimate book is never blocked by this seam.
    """
    full, prefixes, free = _book_state_scope(dp)
    found: list[str] = []
    state = book.get("state")
    _scan_smuggled_keys(state, "", full, prefixes, free, found)
    for key, value in book.items():
        if key == "state":
            continue
        name = str(key)
        if name in FORBIDDEN_KEYS:
            found.append(name)
        _scan_smuggled_keys(value, name, set(), set(), set(), found)
    return found


def _split_request_path(raw: str) -> tuple[str, dict[str, str]]:
    """Path + query with traversal refused before any routing decision."""
    if not raw.startswith("/"):
        raise _ApiError(404, "not-found", "unknown route")
    path, _, query_text = raw.partition("?")
    if "#" in path:
        path = path.split("#", 1)[0]
    decoded = urllib.parse.unquote(path)
    if "\x00" in decoded or "\\" in decoded or ".." in decoded.split("/"):
        raise _ApiError(404, "not-found", "unknown route")
    query: dict[str, str] = {}
    if query_text:
        for key, value in urllib.parse.parse_qsl(query_text, keep_blank_values=True):
            if key in query:
                raise _ApiError(400, "invalid-filter", f"duplicate query parameter {key!r}")
            query[key] = value
    return decoded, query


_ROUTES: dict[str, dict[str, tuple[str, str, str | None]]] = {
    "/api/health": {"GET": ("control", "health", None)},
    "/api/window": {"POST": ("control", "window", None)},
    "/api/shutdown": {"POST": ("control", "shutdown", None)},
    "/api/bootstrap": {"POST": ("public", "bootstrap", None)},
    "/api/history": {"GET": ("page", "history", None)},
    "/api/dps": {"GET": ("page", "dps", None)},
    "/api/test/scaffold": {"POST": ("page", "scaffold", None)},
    "/api/test/cases": {"GET": ("page", "test-cases", None)},
    "/api/test/validate": {"POST": ("page", "validate", None)},
    "/api/test/submit": {"POST": ("page", "submit", None)},
    "/api/test/history": {"GET": ("page", "test-history", None)},
}
_PREFIX_ROUTES: tuple[tuple[str, dict[str, tuple[str, str, str]]], ...] = (
    ("/api/history/", {"GET": ("page", "history-detail", "opaque")}),
    ("/api/test/submissions/", {"GET": ("page", "submission", "submission_id")}),
)


def _match_route(method: str, path: str) -> tuple[str, str, dict[str, str]]:
    exact = _ROUTES.get(path)
    if exact is not None:
        if method not in exact:
            raise _ApiError(405, "method-not-allowed", f"{method} is not allowed on {path}")
        role, action, _param = exact[method]
        return role, action, {}
    for prefix, methods in _PREFIX_ROUTES:
        if not path.startswith(prefix) or path == prefix:
            continue
        segment = path[len(prefix) :]
        if not segment or "/" in segment:
            continue
        if method not in methods:
            raise _ApiError(405, "method-not-allowed", f"{method} is not allowed on {path}")
        role, action, param = methods[method]
        return role, action, {param: segment}
    raise _ApiError(404, "not-found", "unknown route")


class _MonitorHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Threaded HTTP server serving on an already bound/held listener."""

    daemon_threads = True
    block_on_close = False
    allow_reuse_address = False

    def __init__(
        self,
        address: tuple[str, int],
        handler_class: type[http.server.BaseHTTPRequestHandler],
        *,
        instance: "MonitorInstance",
    ) -> None:
        self.instance = instance
        super().__init__(address, handler_class, bind_and_activate=False)
        listener = instance.listener
        if listener is None:
            raise RuntimeError("the monitor listener is missing; bind before serving")
        self.socket.close()
        self.socket = listener
        self.server_address = listener.getsockname()
        self.server_name = str(self.server_address[0])
        self.server_port = int(self.server_address[1])
        self.server_activate()


class _MonitorHandler(http.server.BaseHTTPRequestHandler):
    """One request: host/role/origin checks, then a handler from the closed set."""

    server_version = "mw-decide-monitor"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    timeout = 15

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib signature
        # No access log: request lines can contain ids and the service is local.
        return

    @property
    def monitor(self) -> "MonitorInstance":
        return self.server.instance  # type: ignore[attr-defined,no-any-return]

    # -- verb entry points -------------------------------------------------

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def do_HEAD(self) -> None:
        self._handle("HEAD")

    def do_PUT(self) -> None:
        self._handle("PUT")

    def do_DELETE(self) -> None:
        self._handle("DELETE")

    def do_PATCH(self) -> None:
        self._handle("PATCH")

    def do_OPTIONS(self) -> None:
        self._handle("OPTIONS")

    # -- dispatch ----------------------------------------------------------

    def _handle(self, method: str) -> None:
        try:
            path, query = _split_request_path(self.path)
            self._check_host()
            if method == "GET" and path in STATIC_ASSETS:
                self._send_static(path)
                return
            data, capture_status = self._dispatch(method, path, query)
        except _ApiError as exc:
            self._send_json(exc.status, _error_envelope(exc))
            return
        except Exception as exc:  # noqa: BLE001 - never leak internals to the page
            self._send_json(
                500,
                _error_envelope(_ApiError(500, "internal-error", type(exc).__name__)),
            )
            return
        self._send_json(200, _ok_envelope(data, capture_status))

    def _dispatch(self, method: str, path: str, query: dict[str, str]) -> tuple[object, str | None]:
        role_required, action, params = _match_route(method, path)
        token = self.headers.get(TOKEN_HEADER)
        role = self.monitor.tokens.role_for(token)
        if role_required != "public":
            if role is None:
                raise _ApiError(
                    401,
                    "missing-token" if not token else "invalid-token",
                    "a valid monitor token is required",
                )
            if role != role_required:
                raise _ApiError(
                    403,
                    "wrong-role",
                    f"this route requires the {role_required} token",
                )
        require_origin = role_required in ("public", "page") and method == "POST"
        self._check_origin(require_origin=require_origin)
        body = self._read_body() if method == "POST" else b""
        handler = getattr(self, f"_act_{action.replace('-', '_')}")
        return handler(query=query, params=params, body=body)

    def _check_host(self) -> None:
        host = self.headers.get("Host")
        if host != self.monitor.host_header:
            raise _ApiError(
                403,
                "host-not-allowed",
                f"requests must target the exact loopback Host {self.monitor.host_header}",
            )

    def _check_origin(self, *, require_origin: bool) -> None:
        fetch_site = self.headers.get("Sec-Fetch-Site")
        if fetch_site is not None and fetch_site.strip() not in SEC_FETCH_SITE_ALLOWED:
            raise _ApiError(
                403,
                "cross-site-blocked",
                "cross-site and same-site browser requests are refused",
            )
        origin = self.headers.get("Origin")
        if origin is None:
            if require_origin:
                raise _ApiError(
                    403,
                    "origin-not-allowed",
                    f"the exact Origin {self.monitor.origin} is required for this request",
                )
            return
        if origin != self.monitor.origin:
            raise _ApiError(
                403,
                "origin-not-allowed",
                f"the exact Origin {self.monitor.origin} is required for this request",
            )

    def _read_body(self) -> bytes:
        if self.headers.get("Transfer-Encoding"):
            raise _ApiError(
                400, "chunked-unsupported", "chunked request bodies are not supported"
            )
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return b""
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise _ApiError(400, "invalid-body", "Content-Length must be an integer") from exc
        if length < 0:
            raise _ApiError(400, "invalid-body", "Content-Length must not be negative")
        if length > BODY_LIMIT_BYTES:
            raise _ApiError(
                413,
                "body-too-large",
                f"request bodies are limited to {BODY_LIMIT_BYTES} bytes",
            )
        data = self.rfile.read(length) if length else b""
        if len(data) != length:
            raise _ApiError(400, "invalid-body", "the request body was shorter than Content-Length")
        return data

    # -- responses ---------------------------------------------------------

    def _security_headers(self) -> None:
        self.send_header("Content-Security-Policy", _CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")

    def _send_json(self, status: int, payload: Mapping[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.send_header("Connection", "close")
        self.end_headers()
        with contextlib.suppress(OSError):
            self.wfile.write(body)
        self.close_connection = True

    def _send_static(self, path: str) -> None:
        content_type, text = STATIC_ASSETS[path]
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.send_header("Connection", "close")
        self.end_headers()
        with contextlib.suppress(OSError):
            self.wfile.write(body)
        self.close_connection = True

    # -- read routes -------------------------------------------------------

    def _act_health(self, *, query: dict[str, str], params: dict[str, str], body: bytes):
        del query, params, body
        return self.monitor.health_payload(), None

    def _act_window(self, *, query: dict[str, str], params: dict[str, str], body: bytes):
        del query, params
        _closed_json(body, allowed=frozenset())
        return {"url": self.monitor.new_window_url(), "expires_in_s": BOOT_CODE_TTL_S}, None

    def _act_shutdown(self, *, query: dict[str, str], params: dict[str, str], body: bytes):
        del query, params
        _closed_json(body, allowed=frozenset())
        self.monitor.request_shutdown()
        return {"stopping": True}, None

    def _act_bootstrap(self, *, query: dict[str, str], params: dict[str, str], body: bytes):
        del query, params
        raw = _closed_json(body, allowed=frozenset({"code"}))
        token = self.monitor.tokens.redeem_boot_code(raw.get("code"))
        if token is None:
            raise _ApiError(
                401,
                "bad-boot-code",
                "the boot code is unknown, already used, or expired; reopen the window from the CLI",
            )
        return {"page_token": token}, None

    def _history_snapshot(self):
        deps = self.monitor.deps
        try:
            # ``redact=None`` is T07's documented fail-closed mode: unprovable
            # free text is withheld and counted, never echoed raw.
            return deps.load_history(self.monitor.control_root)
        except decision_history.HistoryError as exc:
            raise _ApiError(400, "invalid-filter", str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - a read failure is explicit, never fake data
            raise _ApiError(
                503,
                "history-unavailable",
                f"the history fold failed ({type(exc).__name__})",
            ) from exc

    def _act_history(self, *, query: dict[str, str], params: dict[str, str], body: bytes):
        del params, body
        snapshot = self._history_snapshot()
        unknown = sorted(
            set(query)
            - {"key", "dp", "source", "status", "scope", "limit", "offset"}
        )
        if unknown:
            raise _ApiError(
                400,
                "unknown-query",
                "unknown query parameter(s): " + ", ".join(_safe_names(unknown)),
            )
        try:
            page = snapshot.page(
                key=query.get("key") or None,
                dp=query.get("dp") or None,
                source=query.get("source") or None,
                status=query.get("status") or None,
                scope=query.get("scope") or "production",
                limit=self._int_param(query, "limit", DEFAULT_PAGE_LIMIT),
                offset=self._int_param(query, "offset", 0),
            )
        except decision_history.HistoryError as exc:
            raise _ApiError(400, "invalid-filter", str(exc)) from exc
        redactor = self.monitor.deps.redactor
        records = [_redact_payload(record.as_dict(), redactor) for record in page.records]
        # T06 owns the workbench/facets projection; the route only forwards it
        # (absent -> null, never re-derived or guessed here).
        facets = _facets_payload(getattr(page, "facets", None))
        data = {
            "records": records,
            "total": page.total,
            "limit": page.limit,
            "offset": page.offset,
            "has_more": page.has_more,
            "facets": facets,
            "filters": dict(page.filters),
            "filters_withheld": list(page.filters_withheld),
            "filters_basis": list(page.filters_basis),
            "stats": snapshot.stats.as_dict(),
            "warnings": list(snapshot.warnings[:20]),
            "redaction": _redaction_summary(records, redactor),
        }
        capture_status = _worst_capture_status(
            [record.get("capture_status") for record in records]  # type: ignore[union-attr]
        )
        return _redact_payload(data, redactor), capture_status

    def _act_history_detail(
        self, *, query: dict[str, str], params: dict[str, str], body: bytes
    ):
        del body
        if query:
            raise _ApiError(400, "unknown-query", "history detail takes no query parameters")
        snapshot = self._history_snapshot()
        opaque = params.get("opaque", "")
        if not decision_history.OPAQUE_ID_PATTERN.match(opaque):
            # An opaque id is a handle, never a path or a raw decision id.
            raise _ApiError(404, "not-found", "unknown record handle")
        record = snapshot.detail(opaque)
        if record is None:
            raise _ApiError(404, "not-found", "unknown record handle")
        payload = _redact_payload(record.as_dict(detail=True), self.monitor.deps.redactor)
        return payload, record.capture_status

    def _act_dps(self, *, query: dict[str, str], params: dict[str, str], body: bytes):
        del params, body
        if query:
            raise _ApiError(400, "unknown-query", "the registry route takes no query parameters")
        snapshot = decision_points.registry_snapshot()
        config = decision_points.load_points_config(self.monitor.control_root)
        points: list[dict[str, object]] = []
        for point in snapshot["points"]:
            effective = config.effective(decision_points.get_decision_point(str(point["id"])))
            points.append(
                {
                    "id": point["id"],
                    "tier": point["tier"],
                    "default_enabled": point["default_enabled"],
                    "default_mode": point["default_mode"],
                    "questions_version": point["questions_version"],
                    "enabled": effective.enabled,
                    "mode": effective.mode,
                    "config_source": effective.source,
                    "executor": point["executor"],
                    "wired": point["wired"],
                    "required_state_fields": point["required_state_fields"],
                    "optional_state_fields": point["optional_state_fields"],
                    "questions": point["questions"],
                }
            )
        deps = self.monitor.deps
        data = {
            "schema": snapshot["schema"],
            "points": points,
            "transport": {"state": deps.transport_state, "detail": deps.transport_detail},
            "config": {"layer": config.layer, "warnings": list(config.warnings[:20])},
            # The DP test page needs the same budget the book gate applies and the
            # explicit observe-only contract; neither is a registry field.
            "budget": {"max_state_bytes": decision_points.MAX_STATE_BYTES},
            "observe_only": True,
        }
        return _redact_payload(data, deps.redactor), None

    # -- playground seam (T06 injects the provider) ------------------------

    def _playground(self) -> object:
        deps = self.monitor.deps
        redactor = deps.resolve_redactor(self.monitor.control_root)
        if redactor is None:
            # Without the credential redactor a response could not be made safe,
            # so the seam fails closed *before* any provider (or model) is used.
            raise _ApiError(
                503,
                "playground-redactor-unavailable",
                "the playground is disabled because no credential redactor is configured; no model call was made",
            )
        playground = deps.resolve_playground(self.monitor.control_root)
        if playground is None:
            raise _ApiError(
                503,
                "playground-unavailable",
                "the DP test playground is not wired in this build; no model call was made",
            )
        return playground

    def _provider_call(self, describe: str, call: Callable[[object], object]) -> object:
        playground = self._playground()
        try:
            return call(playground)
        except Exception as exc:  # noqa: BLE001 - the page sees an explicit failure
            raise _ApiError(
                502,
                "playground-error",
                f"{describe} failed: "
                + _redact_text(self.monitor.deps.redactor, f"{type(exc).__name__}: {exc}"),
            ) from exc

    # -- offline workbench cases (read-only, zero model/credential) ---------

    def _act_test_cases(self, *, query: dict[str, str], params: dict[str, str], body: bytes):
        """The four shipped synthetic cases (page role, GET, read-only).

        No path, filename or directory is ever taken from the caller: ``dp`` is
        an optional id filter over :data:`CASE_IDS`. Loading a case reads the
        fixed file only - no credential snapshot, no transport, no model, no
        write - so the page can load/edit a book before any explicit submit.
        """
        del params, body
        unknown = sorted(set(query) - {"dp"})
        if unknown:
            raise _ApiError(
                400,
                "unknown-query",
                "unknown query parameter(s): " + ", ".join(_safe_names(unknown)),
            )
        wanted = query.get("dp")
        if wanted is not None and wanted not in CASE_IDS:
            raise _ApiError(400, "invalid-filter", "'dp' is not one of the four offline case ids")
        ids = [wanted] if wanted else list(CASE_IDS)
        cases: list[dict[str, object]] = []
        for dp in ids:
            try:
                case = load_case(dp)
            except CaseError as exc:
                status = 400 if exc.kind == "case-unknown" else 503
                raise _ApiError(status, exc.kind, exc.message) from exc
            book = case["book"]
            cases.append(
                {
                    "dp": dp,
                    "title": case["title"],
                    "note": case["note"],
                    "questions": case["questions"],
                    "book": book,
                    "sha256": case_book_digest(book),
                    "bytes": len(case_book_bytes(book)),
                }
            )
        data = {"case_version": CASE_VERSION, "source": "offline", "cases": cases}
        return _redact_payload(data, self.monitor.deps.redactor), None

    def _act_scaffold(self, *, query: dict[str, str], params: dict[str, str], body: bytes):
        del query, params
        raw = _closed_json(body, allowed=frozenset({"dp"}))
        dp = self._require_str(raw, "dp")
        result = self._provider_call("scaffold", lambda playground: playground.scaffold(dp))  # type: ignore[attr-defined]
        return _redact_payload(result, self.monitor.deps.redactor), None

    def _act_validate(self, *, query: dict[str, str], params: dict[str, str], body: bytes):
        del query, params
        raw = _closed_json(body, allowed=frozenset({"dp", "book", "questions"}))
        dp = self._require_str(raw, "dp")
        book = raw.get("book")
        if not isinstance(book, dict):
            raise _ApiError(400, "invalid-field", "'book' must be a JSON object")
        questions = self._optional_questions(raw)
        if questions is None:
            result = self._provider_call(
                "validate", lambda playground: playground.validate(dp, book)  # type: ignore[attr-defined]
            )
        else:
            result = self._provider_call(
                "validate",
                lambda playground: playground.validate(dp, book, questions),  # type: ignore[attr-defined]
            )
        return _redact_payload(result, self.monitor.deps.redactor), None

    @staticmethod
    def _optional_questions(raw: Mapping[str, object]) -> dict | None:
        """The observation-only ``questions`` field, or ``None`` when absent.

        Structural refusal only: the provider owns the strict DP mapping /
        type / instructions / criteria gate and the DP's legal choice set. The
        monitor refuses execution/authorization key names at any nesting level
        so a question cannot become a second authorization channel.
        """
        if "questions" not in raw:
            return None
        questions = raw.get("questions")
        if not isinstance(questions, dict):
            raise _ApiError(400, "invalid-field", "'questions' must be a JSON object")
        found: list[str] = []
        _scan_smuggled_keys(questions, "questions", set(), set(), set(), found)
        if found:
            names = _safe_names(found[:8])
            raise _ApiError(
                400,
                "forbidden-field",
                "the monitor refuses execution/authorization fields inside the questions: "
                + ", ".join(names),
                issues=names,
            )
        return questions

    def _act_submit(self, *, query: dict[str, str], params: dict[str, str], body: bytes):
        """Explicit observe-only submission (the only route that can reach T06).

        T06 provider obligations (also exported as
        :data:`PLAYGROUND_PROVIDER_OBLIGATIONS`): it MUST call
        ``decision_book.check_book`` (closed keys, types, enums, placeholder/
        evidence/budget, secret scan) before any model call, and it MUST NOT
        execute an action or change authorization. This seam adds a registry-
        aware nested refusal for execution/authorization keys; it is not a
        replacement for ``check_book``.
        """
        del query, params
        raw = _closed_json(body, allowed=SUBMIT_KEYS, forbidden=FORBIDDEN_KEYS)
        missing = [name for name in ("dp", "book", "submit_id") if name not in raw]
        if missing:
            raise _ApiError(
                400, "missing-field", "missing field(s): " + ", ".join(_safe_names(missing)),
                issues=_safe_names(missing),
            )
        dp = self._require_str(raw, "dp")
        try:
            decision_points.get_decision_point(dp)
        except decision.DecisionInputError as exc:
            # Unknown ids are refused before any provider call; a broken registry
            # (any other exception) must surface as an internal error instead.
            raise _ApiError(
                400,
                "invalid-field",
                "'dp' is not a registered decision point; no provider was called",
            ) from exc
        submit_id = self._require_str(raw, "submit_id")
        if not _SUBMIT_ID_PATTERN.match(submit_id):
            raise _ApiError(400, "invalid-field", "'submit_id' must be a short opaque identifier")
        book = raw.get("book")
        if not isinstance(book, dict):
            raise _ApiError(400, "invalid-field", "'book' must be a JSON object")
        smuggled = _smuggled_book_paths(book, dp)
        if smuggled:
            names = _safe_names(smuggled[:8])
            raise _ApiError(
                400,
                "forbidden-field",
                "the monitor refuses execution/authorization fields inside the book: "
                + ", ".join(names),
                issues=names,
            )
        if raw.get("observe_only") is not True:
            raise _ApiError(
                400,
                "invalid-field",
                "'observe_only' must be true: the monitor never executes a business action",
            )
        retry_of = raw.get("retry_of")
        if retry_of is not None and not isinstance(retry_of, str):
            raise _ApiError(400, "invalid-field", "'retry_of' must be a submission id")
        request: dict[str, object] = {
            "dp": dp,
            "book": book,
            "submit_id": submit_id,
            "observe_only": True,
        }
        questions = self._optional_questions(raw)
        if questions is not None:
            request["questions"] = questions
        if isinstance(retry_of, str):
            request["retry_of"] = retry_of
        result = self._provider_call(
            "submit", lambda playground: playground.submit(request)  # type: ignore[attr-defined]
        )
        redacted = _redact_payload(result, self.monitor.deps.redactor)
        if isinstance(redacted, Mapping) and redacted.get("busy") is True:
            # A second concurrent submission is a *refusal*, not a success: the
            # card requires 409 (never HTTP 200) so the page cannot render it as
            # an accepted test call. The provider payload is attached because it
            # carries the honest facts (nothing queued, zero model call).
            raise _ApiError(
                409,
                "busy",
                "one submission is already running: nothing was queued and no model "
                "call was made",
                issues=["busy"],
                data=redacted,
            )
        return redacted, None

    def _act_submission(self, *, query: dict[str, str], params: dict[str, str], body: bytes):
        del query, body
        submission_id = params.get("submission_id", "")
        if not _SUBMIT_ID_PATTERN.match(submission_id):
            raise _ApiError(404, "not-found", "unknown submission id")
        result = self._provider_call(
            "submission", lambda playground: playground.submission(submission_id)  # type: ignore[attr-defined]
        )
        if result is None:
            raise _ApiError(404, "not-found", "unknown submission id")
        return _redact_payload(result, self.monitor.deps.redactor), None

    def _act_test_history(self, *, query: dict[str, str], params: dict[str, str], body: bytes):
        del query, params, body
        result = self._provider_call(
            "test history", lambda playground: playground.history()  # type: ignore[attr-defined]
        )
        return _redact_payload(result, self.monitor.deps.redactor), None

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _int_param(query: Mapping[str, str], name: str, default: int) -> int:
        if name not in query:
            return default
        try:
            return int(query[name])
        except ValueError as exc:
            raise _ApiError(
                400, "invalid-filter", f"{name} must be an integer"
            ) from exc

    @staticmethod
    def _require_str(raw: Mapping[str, object], name: str) -> str:
        value = raw.get(name)
        if not isinstance(value, str) or not value:
            raise _ApiError(400, "invalid-field", f"'{name}' must be a non-empty string")
        return value


# ── Dependencies (T07 read side, T06 playground, redactor) ──────────────────


def _facets_payload(facets: object) -> dict[str, object] | None:
    """The T06 facets object as a JSON mapping (``None`` when absent).

    T06 ships :class:`decision_history.HistoryFacets` (a frozen dataclass with
    ``as_dict``); the route forwards it verbatim and never recomputes keys/dps.
    """
    if facets is None:
        return None
    as_dict = getattr(facets, "as_dict", None)
    if callable(as_dict):
        try:
            payload = as_dict()
        except Exception:  # noqa: BLE001 - a broken projection is reported as absent
            return None
        return dict(payload) if isinstance(payload, Mapping) else None
    if isinstance(facets, Mapping):
        return dict(facets)
    return None


@dataclasses.dataclass
class MonitorDeps:
    """Injected collaborators; every default is the honest, non-executing one.

    ``playground`` is the explicit injection point (tests always inject a
    provider or a factory). ``playground_factory`` is the *lazy* production
    wiring: the provider is created at most once per control root, on the first
    playground route, never at import and never while reading history, and it
    resolves no credential by itself. Command entry points install the shipped
    factories and opt into a startup response-redactor snapshot; a bare instance
    retains explicit injection. ``mw decide monitor`` needs no manual wiring.

    ``playground`` (when injected) must honour
    :data:`PLAYGROUND_PROVIDER_OBLIGATIONS`: ``decision_book.check_book`` first
    (closed key set, declared types/enums, placeholder/evidence/budget, secret
    scan), then an observe-only submission that never executes an action or
    edits authorization. The monitor's nested key refusal is defense in depth,
    not a substitute for that validation.
    """

    redactor: object | None = None
    history_loader: Callable[[pathlib.Path], object] | None = None
    playground: object | None = None
    playground_factory: Callable[[pathlib.Path], object] | None = None
    redactor_factory: Callable[[pathlib.Path], object | None] | None = None
    redactor_on_start: bool = False
    capture_state: str = "disabled"
    capture_detail: str | None = None
    transport_state: str = "unknown"
    transport_detail: str | None = None
    _resolved_playgrounds: dict[str, object] = dataclasses.field(
        default_factory=dict, repr=False, compare=False
    )
    _resolved_redactors: dict[str, object] = dataclasses.field(
        default_factory=dict, repr=False, compare=False
    )
    _playground_lock: threading.Lock = dataclasses.field(
        default_factory=threading.Lock, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if self.capture_state not in CAPTURE_STATES:
            raise ValueError(
                f"capture_state must be one of {CAPTURE_STATES}, got {self.capture_state!r}"
            )
        if self.transport_state not in TRANSPORT_STATES:
            raise ValueError(
                f"transport_state must be one of {TRANSPORT_STATES}, got {self.transport_state!r}"
            )

    def resolve_playground(self, control_root: pathlib.Path) -> object | None:
        """The injected provider, else the one lazily created for this root.

        "One provider per control root": the resolved object is cached and the
        same instance serves every route, so the provider's own busy guard and
        ``submit_id`` de-duplication stay meaningful. Nothing is resolved here
        but the root path: no credential, no transport, no model.
        """
        if self.playground is not None:
            return self.playground
        factory = self.playground_factory
        if factory is None:
            return None
        key = str(pathlib.Path(control_root).resolve())
        with self._playground_lock:
            existing = self._resolved_playgrounds.get(key)
            if existing is not None:
                return existing
            created = factory(pathlib.Path(key))
            self._resolved_playgrounds[key] = created
            return created

    def resolve_redactor(self, control_root: pathlib.Path) -> object | None:
        """The injected redactor, else the one lazily built for this root.

        Command startup resolves this once before serving any request. Bare
        injected dependencies keep the playground-only lazy contract. Neither
        path discovers credentials at import, on health or on a history read.
        Startup freezes the result in instance-local deps, including failure,
        so subsequent playground/history reads cannot retry discovery.
        """
        if self.redactor is not None:
            return self.redactor
        factory = self.redactor_factory
        if factory is None:
            return None
        key = str(pathlib.Path(control_root).resolve())
        with self._playground_lock:
            if key in self._resolved_redactors:
                return self._resolved_redactors[key]
            created = factory(pathlib.Path(key))
            self._resolved_redactors[key] = created
            return created

    def load_history(self, control_root: pathlib.Path) -> object:
        """The T07 fold, with this instance's redactor injected for its text policy.

        ``decision_history.load_history(..., redact=...)`` owns the free-text
        contract (redact+clip with a redactor, fail-closed omission without):
        the monitor never re-implements or bypasses it.
        """
        if self.history_loader is not None:
            return self.history_loader(control_root)
        return decision_history.load_history(control_root, redact=self.redactor)


# ── The instance ────────────────────────────────────────────────────────────


def _playground_detail(deps: MonitorDeps) -> str | None:
    if deps.redactor is None and deps.redactor_factory is None:
        return "no credential redactor is configured, so the playground stays closed"
    if deps.playground is None and deps.playground_factory is None:
        return "no DP test playground is injected or configured for this build"
    return None


def default_playground_factory(control_root: pathlib.Path) -> object:
    """The shipped lazy provider (imported here, so no import-time side effects).

    ``DecisionPlayground`` resolves the control root and nothing else: no
    credential, no transport, no model call. The provider's own submission path
    stays the only thing that can reach the decision chain.
    """
    import decision_playground

    return decision_playground.DecisionPlayground(control_root)


def default_redactor_factory(control_root: pathlib.Path) -> object | None:
    """The shipped response redactor, resolved at explicit command startup.

    Built from the project's config plus one frozen credential snapshot of this
    root; credential values stay in memory. Never resolved at import, on health,
    on history GET or polling; bare injected deps may retain lazy playground use.
    """
    import decision

    cfg = decision.DecisionConfig.from_project(control_root)[0]
    # History can contain either the config key or the local timi credential;
    # config precedence must not skip the latter in this read-side known set.
    # One discovery freezes the local/env leg, then the redactor unions cfg.
    snapshot = decision.credential_snapshot()
    return decision.credential_redactor(cfg, snapshot=snapshot)


def default_monitor_deps() -> MonitorDeps:
    """The command-path dependencies (``serve`` / ``ensure_instance``).

    These entry points opt into a startup response-redactor snapshot, while the
    playground provider stays lazy. A bare ``MonitorDeps()`` or a directly
    constructed ``MonitorInstance`` retains explicit injection (no provider,
    no redactor -> playground 503). Compatible reuse never resolves credentials.
    """
    return MonitorDeps(
        playground_factory=default_playground_factory,
        redactor_factory=default_redactor_factory,
        redactor_on_start=True,
    )


class MonitorInstance:
    """One bound monitor service (listener + identity + HTTP server thread)."""

    def __init__(
        self,
        control_root: pathlib.Path | str,
        *,
        deps: MonitorDeps | None = None,
        clock: Callable[[], float] | None = None,
        port_range: tuple[int, int] = PORT_RANGE,
        host: str = HOST,
    ) -> None:
        self.raw_root = pathlib.Path(control_root)
        self.control_root, self.root_source = mw_common.resolve_control_root(
            control_root, require_control=True
        )
        self.control_root = pathlib.Path(self.control_root)
        self.project_id = decision_wire.project_id_for(self.control_root)
        self.deps = deps if deps is not None else MonitorDeps()
        self.port_range = port_range
        self.host = host
        self.tokens = TokenStore(clock=clock or time.monotonic)
        self.listener: socket.socket | None = None
        self.port: int | None = None
        self.identity: InstanceIdentity | None = None
        self.recovery: dict[str, object] | None = None
        self._server: _MonitorHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._boot_code: str | None = None
        self._stopped = False

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> "MonitorInstance":
        if self.identity is not None:
            return self
        listener, port = bind_listener(
            project_id=self.project_id, port_range=self.port_range, host=self.host
        )
        self.listener = listener
        self.port = port
        if self.deps.redactor_on_start:
            try:
                redactor = self.deps.resolve_redactor(self.control_root)
            except Exception:  # noqa: BLE001 - never expose credential discovery errors
                redactor = None
            # Keep the snapshot instance-local (deps templates can span roots).
            # Disable its factory even on failure: GETs cannot retry discovery.
            self.deps = dataclasses.replace(
                self.deps, redactor=redactor, redactor_factory=None
            )
        identity = InstanceIdentity(
            project_id=self.project_id,
            instance_id=secrets.token_hex(8),
            pid=os.getpid(),
            pid_start_ms=mw_common.process_start_ms(os.getpid()),
            port=port,
        )
        self.identity = identity
        # Secret first, then the identity document: an interruption in between
        # leaves an orphan secret that recovery isolates (never a state that
        # claims a token nobody holds).
        publish_secret(self.control_root, self.tokens.control_token)
        publish_state(self.control_root, identity)
        try:
            self._server = _MonitorHTTPServer(
                (self.host, port), _MonitorHandler, instance=self
            )
        except Exception:
            with contextlib.suppress(OSError):
                listener.close()
            # A published identity without a serving socket must not linger as
            # "alive but unresponsive" state; the process is still us, but it
            # never served.
            self._remove_own_files()
            raise
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": 0.02},
            name="decide-monitor-http",
            daemon=True,
        )
        self._thread.start()
        self._boot_code = self.tokens.issue_boot_code()
        return self

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        server, thread, listener = self._server, self._thread, self.listener
        if server is not None:
            with contextlib.suppress(Exception):
                server.shutdown()
        # Remove our identity files before the port closes, so "port free"
        # implies "state gone" for callers polling the listener.
        self._remove_own_files()
        if server is not None:
            with contextlib.suppress(Exception):
                server.server_close()
        if thread is not None:
            thread.join(timeout=5.0)
        if listener is not None and listener.fileno() != -1:
            with contextlib.suppress(OSError):
                listener.close()

    def request_shutdown(self) -> None:
        """Stop from a handler thread *after* the response has been flushed."""
        instance = self

        def _stop() -> None:
            time.sleep(0.05)
            instance.stop()

        threading.Thread(target=_stop, name="decide-monitor-stop", daemon=True).start()

    def _remove_own_files(self) -> None:
        if self.identity is None:
            # Never started: its files (if any) belong to somebody else.
            return
        state, problem = read_state(self.control_root)
        if problem is not None:
            return
        if state is not None:
            if state.get("instance_id") != self.identity.instance_id:
                return
            with contextlib.suppress(FileNotFoundError, OSError):
                state_path(self.control_root).unlink()
        else:
            # The state is already gone; leave any secret to orphan recovery so a
            # concurrently starting instance's fresh secret is never deleted.
            return
        with contextlib.suppress(FileNotFoundError, OSError):
            secret_path(self.control_root).unlink()

    def serve_forever(self) -> None:
        self.start()
        thread = self._thread
        if thread is None:
            return
        with contextlib.suppress(KeyboardInterrupt):
            while thread.is_alive():
                thread.join(timeout=0.2)

    # -- identity properties ----------------------------------------------

    def _require_identity(self) -> InstanceIdentity:
        if self.identity is None or self.port is None:
            raise RuntimeError("the monitor instance has not been started")
        return self.identity

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    @property
    def origin(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def host_header(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def control_token(self) -> str:
        return self.tokens.control_token

    @property
    def boot_code(self) -> str:
        if self._boot_code is None:
            raise RuntimeError("the monitor instance has no boot code yet")
        return self._boot_code

    def new_boot_code(self) -> str:
        return self.tokens.issue_boot_code()

    def bootstrap_url(self) -> str:
        return window_url(self._require_identity().port, self.boot_code)

    def new_window_url(self) -> str:
        return window_url(self._require_identity().port, self.new_boot_code())

    def health_payload(self) -> dict[str, object]:
        identity = self._require_identity()
        return {
            "schema": identity.schema,
            "protocol_version": identity.protocol_version,
            "project_id": identity.project_id,
            "instance_id": identity.instance_id,
            "pid": identity.pid,
            "pid_start_ms": identity.pid_start_ms,
            "port": identity.port,
            "code_fingerprint": identity.code_fingerprint,
            "capture": {
                "state": self.deps.capture_state,
                "detail": self.deps.capture_detail,
            },
            "playground": {
                "state": "wired"
                if (
                    (self.deps.redactor is not None or self.deps.redactor_factory is not None)
                    and (
                        self.deps.playground is not None
                        or self.deps.playground_factory is not None
                    )
                )
                else "unavailable",
                "detail": _playground_detail(self.deps),
            },
            "transport": {
                "state": self.deps.transport_state,
                "detail": self.deps.transport_detail,
            },
        }


@dataclasses.dataclass
class AttachedInstance:
    """A healthy instance owned by another caller (reuse path; never rewritten)."""

    control_root: pathlib.Path
    identity: InstanceIdentity
    control_token: str = dataclasses.field(repr=False)
    deps: MonitorDeps = dataclasses.field(default_factory=MonitorDeps)

    @property
    def port(self) -> int:
        return self.identity.port

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}/"

    @property
    def origin(self) -> str:
        return f"http://{HOST}:{self.port}"

    @property
    def host_header(self) -> str:
        return f"{HOST}:{self.port}"

    def new_window_url(self) -> str:
        data = _post_json(self.port, "/api/window", token=self.control_token, body={})
        url = data.get("url")
        if not isinstance(url, str) or not url:
            raise MonitorError("window-unavailable", "the instance did not return a window URL")
        return url

    def stop(self) -> dict[str, object]:
        """Authenticated shutdown; the result says what actually happened.

        T08 contract: ``stopped`` is True only when the loopback port provably
        answers ``ECONNREFUSED`` afterwards. A refused/failed shutdown request or
        an inconclusive probe returns ``stopped=False`` with a non-empty
        ``detail``. This method never kills a process and never deletes the
        attached instance's state/secret: a still-recorded state is reported as
        ``state="retained"`` for the operator/CLI to decide.
        """
        detail: str | None = None
        try:
            _post_json(self.port, "/api/shutdown", token=self.control_token, body={})
        except MonitorError as exc:
            detail = f"the instance refused the shutdown request ({exc.message})"
        except (OSError, ValueError) as exc:
            detail = f"the shutdown request failed ({type(exc).__name__})"

        observation = probe_recorded_port(self.port)
        if detail is None and observation["result"] == "connected":
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                time.sleep(0.05)
                observation = probe_recorded_port(self.port)
                if observation["result"] != "connected":
                    break
        if observation["result"] != "refused":
            if detail is None:
                detail = (
                    f"the monitor port {self.port} could not be proven closed "
                    f"(probe={observation['result']})"
                )
            return {
                "stopped": False,
                "detail": detail,
                "port": self.port,
                "instance_id": self.identity.instance_id,
                "port_probe": observation["result"],
                "state": "unknown",
            }

        # The port is gone. If the recorded state still names this instance it is
        # a crash residue and stays in place (never deleted by the stop caller).
        deadline = time.monotonic() + 2.0
        state_status = "retained"
        while True:
            state, problem = read_state(self.control_root)
            if problem is not None:
                state_status = "retained"
                break
            if state is None:
                state_status = "absent"
                break
            if state.get("instance_id") != self.identity.instance_id:
                state_status = "foreign"
                break
            if time.monotonic() >= deadline:
                state_status = "retained"
                break
            time.sleep(0.02)
        if state_status == "retained":
            detail = detail or (
                f"the port closed but {state_path(self.control_root)} still names this instance"
            )
        return {
            "stopped": True,
            "detail": detail,
            "port": self.port,
            "instance_id": self.identity.instance_id,
            "port_probe": observation["result"],
            "state": state_status,
        }


def _post_json(
    port: int,
    path: str,
    *,
    token: str,
    body: Mapping[str, object],
    origin: str | None = None,
    timeout: float = 5.0,
) -> dict:
    payload = json.dumps(dict(body)).encode("utf-8")
    request = urllib.request.Request(
        f"http://{HOST}:{int(port)}{path}",
        data=payload,
        headers={TOKEN_HEADER: token, "Content-Type": "application/json"},
        method="POST",
    )
    if origin is not None:
        request.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - loopback only
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise MonitorError(
            "instance-refused",
            f"the instance refused {path} with HTTP {exc.code}",
        ) from exc
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise MonitorError("instance-refused", f"the instance returned a non-JSON reply to {path}") from exc
    if not isinstance(parsed, dict) or parsed.get("ok") is not True:
        raise MonitorError("instance-refused", f"the instance refused {path}")
    data = parsed.get("data")
    return data if isinstance(data, dict) else {}


# ── Orchestration ───────────────────────────────────────────────────────────


def _replacement_files_absent(root: pathlib.Path) -> bool:
    """Only missing files prove absence; suppressed metadata errors do not."""
    state, problem = read_state(root)
    if problem is not None or state is not None:
        return False
    try:
        secret_path(root).lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


def _stop_for_replacement(
    root: pathlib.Path,
    identity: InstanceIdentity,
    token: str,
    deps: MonitorDeps,
    guard: StartLockGuard,
    *,
    alive_state_probe: Callable[[int], str] | None,
    start_ms_probe: Callable[[int], int | None] | None,
    sleep: Callable[[float], None],
) -> dict[str, object]:
    """Authenticated shutdown + literal process exit; never kill or move files."""
    guard.verify()
    confirmed, problem = read_state(root)
    if (
        problem is not None
        or confirmed is None
        or identity_from_state(confirmed, control_root=root) != identity
        or read_secret(root) != token
        or identity.pid == os.getpid()
        or _identity_liveness(
            identity, alive_state_probe=alive_state_probe, start_ms_probe=start_ms_probe
        ) != "alive"
    ):
        raise MonitorError(
            "instance-unknown",
            "the recorded identity/secret changed or its process cannot safely be replaced; no shutdown sent",
            guide=recovery_guide(root),
        )
    attached = AttachedInstance(root, identity, token, deps)
    try:
        result = attached.stop()
    except (MonitorError, OSError, ValueError) as exc:
        raise MonitorError(
            "stop-failed", "authenticated shutdown failed; no replacement was started",
            details={"previous": identity.as_dict()}, guide=recovery_guide(root),
        ) from exc
    replacement = {
        "previous": identity.as_dict(),
        "stop": result,
        "process_exit_confirmed": False,
    }
    if (
        not isinstance(result, dict)
        or result.get("stopped") is not True
        or result.get("detail") is not None
        or result.get("port_probe") != "refused"
        or result.get("state") != "absent"
        or result.get("instance_id") != identity.instance_id
        or result.get("port") != identity.port
    ):
        raise MonitorError(
            "stop-failed",
            "shutdown was rejected or not fully confirmed; no replacement was started",
            details={"replacement": replacement}, guide=recovery_guide(root),
        )
    deadline = time.monotonic() + 10.0
    while True:
        guard.verify()
        if not _replacement_files_absent(root):
            raise MonitorError(
                "instance-unknown",
                "state/secret remained or reappeared after shutdown; no replacement was started",
                details={"replacement": replacement}, guide=recovery_guide(root),
            )
        liveness = _identity_liveness(
            identity, alive_state_probe=alive_state_probe, start_ms_probe=start_ms_probe
        )
        if liveness == "dead":
            replacement["process_exit_confirmed"] = True
            break
        remaining = deadline - time.monotonic()
        if liveness == "unknown" or remaining <= 0:
            raise MonitorError(
                "stop-failed",
                "the old process could not be proven exited; no replacement was started",
                details={"replacement": replacement, "liveness": liveness},
                guide=recovery_guide(root),
            )
        sleep(min(0.05, remaining))
    # A foreign listener or publisher appearing during the exit wait is not ours.
    guard.verify()
    observation = probe_recorded_port(identity.port)
    if observation["result"] != "refused" or not _replacement_files_absent(root):
        raise MonitorError(
            "instance-unknown",
            "the port or recorded files changed after process exit; no replacement was started",
            details={"replacement": replacement}, guide=recovery_guide(root),
        )
    return replacement


def _default_starter(
    control_root: pathlib.Path,
    deps: MonitorDeps,
    port_range: tuple[int, int],
    clock: Callable[[], float] | None,
) -> MonitorInstance:
    return MonitorInstance(
        control_root, deps=deps, port_range=port_range, clock=clock
    ).start()


def ensure_instance(
    control_root: pathlib.Path | str,
    *,
    deps: MonitorDeps | None = None,
    port_range: tuple[int, int] = PORT_RANGE,
    starter: Callable[
        [pathlib.Path, MonitorDeps, tuple[int, int], Callable[[], float] | None], MonitorInstance
    ]
    | None = None,
    clock: Callable[[], float] | None = None,
    health_wait_s: float = HEALTH_WAIT_S,
    replace_incompatible: bool = False,
    alive_state_probe: Callable[[int], str] | None = None,
    start_ms_probe: Callable[[int], int | None] | None = None,
    port_probe: Callable[[int], str] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> MonitorInstance | AttachedInstance:
    """Start/reuse, or opt into authenticated graceful incompatible replacement.

    Default callers still refuse live incompatible instances. Only CLI open opts
    in; the held start lock covers identity/auth, stop, literal old-process exit,
    publication and health. No recorded process is killed or live file removed.
    """
    root, _source = mw_common.resolve_control_root(control_root, require_control=True)
    root = pathlib.Path(root)
    use_deps = deps if deps is not None else default_monitor_deps()
    start = starter or _default_starter
    with start_lock(root, alive_state_probe=alive_state_probe) as guard:
        state, problem = read_state(root)
        if problem is not None:
            raise MonitorError(
                "instance-unknown",
                problem,
                details={"problem": problem},
                guide=recovery_guide(root),
            )
        report: dict[str, object] | None = None
        replacement: dict[str, object] | None = None
        if state is not None:
            identity = identity_from_state(state, control_root=root)
            _require_project_match(identity, root)
            compatible = (
                identity.protocol_version == PROTOCOL_VERSION
                and identity.code_fingerprint == CODE_FINGERPRINT
            )
            liveness = _identity_liveness(
                identity,
                alive_state_probe=alive_state_probe,
                start_ms_probe=start_ms_probe,
            )
            if liveness == "alive":
                if not compatible and not replace_incompatible:
                    raise MonitorError(
                        "incompatible-instance",
                        (
                            f"a monitor instance for {root} is running with protocol "
                            f"{identity.protocol_version} / code {identity.code_fingerprint} "
                            f"(this build: {PROTOCOL_VERSION} / {CODE_FINGERPRINT}); "
                            "it will not be replaced - stop it first"
                        ),
                        details={"state": state},
                        guide=recovery_guide(root),
                    )
                token = read_secret(root)
                if token is not None:
                    data = health(identity.port, token)
                    if data is not None and identity_matches(data, identity):
                        if compatible:
                            return AttachedInstance(
                                control_root=root,
                                identity=identity,
                                control_token=token,
                                deps=use_deps,
                            )
                        replacement = _stop_for_replacement(
                            root, identity, token, use_deps, guard,
                            alive_state_probe=alive_state_probe,
                            start_ms_probe=start_ms_probe, sleep=sleep,
                        )
                if replacement is None:
                    raise MonitorError(
                        "instance-unresponsive",
                        (
                            f"PID {identity.pid} is alive and owns {state_path(root)}, but its "
                            "health endpoint did not answer with the recorded identity; state and "
                            "secret were left in place"
                        ),
                        details={"state": state},
                        guide=recovery_guide(root),
                    )
            if liveness == "unknown":
                raise MonitorError(
                    "instance-unknown",
                    (
                        f"cannot prove whether PID {identity.pid} is dead; refusing to reuse or "
                        "move the recorded state"
                    ),
                    details={"state": state},
                    guide=recovery_guide(root),
                )
            if replacement is None:
                report = recover_stale(
                    root,
                    guard=guard,
                    alive_state_probe=alive_state_probe,
                    start_ms_probe=start_ms_probe,
                    port_probe=port_probe,
                )
        else:
            report = recover_stale(
                root,
                guard=guard,
                alive_state_probe=alive_state_probe,
                start_ms_probe=start_ms_probe,
                port_probe=port_probe,
            )

        guard.verify()
        try:
            instance = start(root, use_deps, port_range, clock)
        except (MonitorError, OSError, ValueError) as exc:
            if replacement is None:
                raise
            raise MonitorError(
                "starter-failed",
                "the old instance exited, but starting its replacement failed",
                details={"replacement": replacement, "cause": type(exc).__name__},
                guide=recovery_guide(root),
            ) from exc
        if replacement is not None:
            instance.replacement = replacement
        if report:
            instance.recovery = report
        ok, detail = wait_health(
            instance.port,
            instance.control_token,
            instance._require_identity(),
            timeout_s=health_wait_s,
            sleep=sleep,
        )
        if not ok:
            raise MonitorError(
                "health-failed",
                (
                    f"the new instance on port {instance.port} did not answer its own health "
                    f"check ({detail}); its state was left in place because a timeout does not "
                    "prove the process is dead"
                ),
                details={
                    "instance_id": instance._require_identity().instance_id,
                    "port": instance.port,
                    "replacement": replacement,
                },
                guide=recovery_guide(root),
            )
        return instance


def serve(
    control_root: pathlib.Path | str,
    *,
    deps: MonitorDeps | None = None,
    port_range: tuple[int, int] = PORT_RANGE,
) -> int:
    """Blocking entry point for the CLI's child process (T08 wires the spawn)."""
    instance = MonitorInstance(
        control_root,
        deps=deps if deps is not None else default_monitor_deps(),
        port_range=port_range,
    )
    instance.start()
    try:
        instance.serve_forever()
    finally:
        instance.stop()
    return 0


# ── Window primitives (argv only; no browser is started here) ────────────────


def window_url(port: int, boot_code: str) -> str:
    """The page URL: the single-use boot code lives in the fragment only."""
    if not isinstance(boot_code, str) or not boot_code:
        raise ValueError("boot_code must be a non-empty string")
    return f"http://{HOST}:{int(port)}/#boot={boot_code}"


def browser_candidates() -> tuple[str, ...]:
    """Chromium-based executables worth probing (no shell, no PATH lookup)."""
    env = os.environ
    paths: list[str] = []
    for base in (env.get("PROGRAMFILES"), env.get("PROGRAMFILES(X86)"), env.get("LOCALAPPDATA")):
        if not base:
            continue
        paths.append(str(pathlib.Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"))
        paths.append(str(pathlib.Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"))
    paths.extend(("/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"))
    return tuple(dict.fromkeys(paths))


def detect_browser(
    *,
    candidates: Sequence[str] | None = None,
    exists: Callable[[str], bool] | None = None,
) -> str | None:
    """First supported Chromium executable, or ``None`` (never a guess)."""
    paths = browser_candidates() if candidates is None else tuple(candidates)
    file_exists = exists or os.path.isfile
    for path in paths:
        try:
            if file_exists(path):
                return path
        except Exception:  # noqa: BLE001 - a broken probe is just "absent"
            continue
    return None


def build_chromium_argv(
    executable: str, *, port: int, boot_code: str, profile_dir: pathlib.Path | str
) -> list[str]:
    """``--app=`` argv with an isolated profile; never routed through a shell."""
    return [
        str(executable),
        f"--app={window_url(port, boot_code)}",
        f"--user-data-dir={pathlib.Path(profile_dir)}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-extensions",
    ]


def launch_app_window(
    *,
    executable: str | None,
    port: int,
    boot_code: str,
    profile_dir: pathlib.Path | str,
    spawn: Callable[[list[str]], object] | None = None,
) -> dict[str, object]:
    """Best-effort app-window spawn; a spawn is never reported as a window.

    ``spawned=True`` proves only that the spawner returned without an error.
    ``visibility`` is always ``not-verified`` in that case: this module cannot
    see a real Chrome/Edge window, so VC-006 stays with T12/T14. A failed spawn
    returns ``spawned=False``/``visibility=not-opened`` with the exact reason and
    a reopen guide; no browser is ever started by the tests.
    """
    url = window_url(port, boot_code)
    guide = [
        "install Google Chrome or Microsoft Edge, or point the CLI at a Chromium executable",
        f"the dashboard URL is {url.partition('#')[0]} - reopen it with 'mw decide monitor'",
        "the monitor keeps running when the window closes; stop it with 'mw decide monitor stop'",
    ]
    if not executable:
        return {
            "spawned": False,
            "visibility": "not-opened",
            "mode": None,
            "url": url,
            "argv": [],
            "reason": "no Chromium-based Chrome or Edge executable was found",
            "guide": guide,
        }
    argv = build_chromium_argv(
        executable, port=port, boot_code=boot_code, profile_dir=profile_dir
    )
    runner = spawn if spawn is not None else subprocess.Popen
    try:
        runner(argv)
    except OSError as exc:
        return {
            "spawned": False,
            "visibility": "not-opened",
            "mode": None,
            "url": url,
            "argv": argv,
            "reason": f"failed to start {executable}: {exc}",
            "guide": guide,
        }
    except Exception as exc:  # noqa: BLE001 - a spawn failure is reported, not hidden
        return {
            "spawned": False,
            "visibility": "not-opened",
            "mode": None,
            "url": url,
            "argv": argv,
            "reason": f"failed to start {executable}: {type(exc).__name__}",
            "guide": guide,
        }
    return {
        "spawned": True,
        "visibility": "not-verified",
        "mode": "app",
        "url": url,
        "argv": argv,
        "reason": None,
        "guide": [],
    }
