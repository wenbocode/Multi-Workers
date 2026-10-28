"""Guard tests for packages/multi-workers/mw_console_guard (W-04a, mw-console-storm-hardening).

ac_refs:
  - goal.md: mw 后台服务常驻运行 (guard 保护 serve 树 spawn 不再弹窗)
  - spec.md AC-005 (guard OR 语义 + 显式 flag 不动), AC-006 (未激活零副作用),
    AC-007 (posix guard no-op, platform seam 注入)
  - design.md D-003 (mw_console_guard/ 包契约) / D-004 (守卫测试段),
    VC-005 / VC-006 / VC-007
  - evidence/research/design-guard-injection-mechanics-20261015.md Q2/Q3:
    popen_init_name 判据 (patched/__init__)、观测入参断言 (captured Popen)、
    fail-open 注入异常 (injected-brake-inside-apply)
  - mw_common.py:1572 platform seam 测试模式先例 (_probe_spawn_kwargs(platform=...))

Assertion groups (task card) and AC/VC mapping:
  | group | assert set                                      | AC   | VC  |
  |-------|-------------------------------------------------|------|-----|
  | 1     | 激活语义: creationflags=0 OR'd NO_WINDOW; 显式   | AC-005 | VC-005 |
  |       | CREATE_NEW_CONSOLE / DETACHED_PROCESS 原样;      |       |     |
  |       | kwargs (stdout/stderr/cwd/env) 透传              |       |     |
  | 2     | 未激活零副作用: Popen.__init__.__name__=="__init__" | AC-006 | VC-006 |
  |       | (sitecustomize 经 subprocess 加载 + 直接 import) |       |     |
  | 3     | 幂等: 重复 _activate() 同对象不重 wrap            | AC-005 | VC-005 |
  | 4     | fail-open: 注入异常 _apply -> 原 __init__ + 单行  | AC-006 | VC-006 |
  |       | stderr 告警 + _patched 未置位                    |       |     |
  | 5     | platform seam: posix (os.name) no-op +           | AC-007 | VC-007 |
  |       | hasattr(subprocess, CREATE_NO_WINDOW) 分支注入  |       |     |
  | 6     | 子进程隔离: 每用例 sys.executable -c + env 注入,  | all   | all  |
  |       | 测试进程全局 subprocess 状态零污染               |       |     |

Mechanics:
  - Every behavioural case runs in its own interpreter (sys.executable -c) with
    controlled env (PYTHONPATH / MW_CONSOLE_GUARD stripped, then re-injected per
    case): the guard patches the *child's* global subprocess, never the test
    process. test_isolation_parent_process_subprocess_unpatched closes the loop.
  - Group 1 observes the actual value handed to the Popen constructor via a
    FakePopen spy installed BEFORE guard activation (guard captures the spy as
    its `orig`, so the observed creationflags is the post-OR value) - matches
    RQ-3's "观测入参" criterion. No real processes are spawned by group 1.
  - subprocess.run is covered by the same patch (run constructs Popen
    internally; RQ-3 Q2 verified empirically) - noted, not re-spawned here.
  - Assertion messages carry quantified values (creationflags in hex).
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

GUARD_DIR = pathlib.Path(__file__).parent / "mw_console_guard"
SKIP_NO_WINDOW = not hasattr(subprocess, "CREATE_NO_WINDOW")

# ---------------------------------------------------------------------------
# Child-process plumbing (group 6: per-case isolation)
# ---------------------------------------------------------------------------

_CHILD_PREFIX = """
import os
import sys
import subprocess
sys.path.insert(0, sys.argv[1])  # mw_console_guard dir
"""


def _run_child(code: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run `code` in a fresh interpreter with a sanitized env.

    PYTHONPATH and MW_CONSOLE_GUARD are stripped so no stray sitecustomize or
    auto-activation leaks in; each case re-injects what it needs.
    """
    child_env = os.environ.copy()
    child_env.pop("PYTHONPATH", None)
    child_env.pop("MW_CONSOLE_GUARD", None)
    if env:
        child_env.update(env)
    return subprocess.run(
        [sys.executable, "-c", code, str(GUARD_DIR)],
        env=child_env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _assert_child(
    proc: subprocess.CompletedProcess,
    *,
    expect_stdout: str,
    stderr_contains: str | None = None,
    stderr_single_line: bool = False,
) -> None:
    assert proc.returncode == 0, "child failed (rc=%d):\n%s" % (proc.returncode, proc.stderr)
    assert expect_stdout in proc.stdout, (
        "child stdout missing %r:\n%s" % (expect_stdout, proc.stdout)
    )
    if stderr_contains is not None:
        assert stderr_contains in proc.stderr, (
            "child stderr missing %r:\n%s" % (stderr_contains, proc.stderr)
        )
    if stderr_single_line:
        assert len(proc.stderr.strip().splitlines()) == 1, (
            "child stderr not single line:\n%s" % proc.stderr
        )


# ---------------------------------------------------------------------------
# Group 1 (VC-005 / AC-005): activation semantics - observed input assertion
# ---------------------------------------------------------------------------

_ACT_SETUP = _CHILD_PREFIX + """
observed = {}
def fake_init(self, *args, creationflags=0, **kwargs):
    observed["creationflags"] = creationflags
    observed["kwargs"] = dict(kwargs)
class FakePopen:
    __init__ = fake_init
subprocess.Popen = FakePopen
os.environ["MW_CONSOLE_GUARD"] = "1"
import mw_console_guard
"""


@pytest.mark.skipif(SKIP_NO_WINDOW, reason="Windows-only: subprocess.CREATE_NO_WINDOW absent")
def test_activation_zero_creationflags_gets_no_window() -> None:
    code = _ACT_SETUP + """
NO_WINDOW = subprocess.CREATE_NO_WINDOW
subprocess.Popen(["probe"], creationflags=0)
assert observed["creationflags"] == NO_WINDOW, (
    "creationflags=0 -> observed 0x%x, expected 0x%x"
    % (observed["creationflags"], NO_WINDOW))
print("ZERO observed=0x%x expected=0x%x" % (observed["creationflags"], NO_WINDOW))
"""
    proc = _run_child(code)
    _assert_child(proc, expect_stdout="ZERO observed=0x8000000 expected=0x8000000")
    print("activation: creationflags=0 -> CREATE_NO_WINDOW (%s)" % proc.stdout.strip(), flush=True)


@pytest.mark.skipif(SKIP_NO_WINDOW, reason="Windows-only: subprocess.CREATE_NO_WINDOW absent")
def test_activation_explicit_new_console_untouched() -> None:
    code = _ACT_SETUP + """
NEW_CONSOLE = subprocess.CREATE_NEW_CONSOLE
subprocess.Popen(["probe"], creationflags=NEW_CONSOLE)
assert observed["creationflags"] == NEW_CONSOLE, (
    "explicit CREATE_NEW_CONSOLE rewritten: observed 0x%x, expected 0x%x"
    % (observed["creationflags"], NEW_CONSOLE))
print("NEW_CONSOLE observed=0x%x expected=0x%x" % (observed["creationflags"], NEW_CONSOLE))
"""
    proc = _run_child(code)
    _assert_child(proc, expect_stdout="NEW_CONSOLE observed=0x10 expected=0x10")
    print("activation: explicit CREATE_NEW_CONSOLE untouched (%s)" % proc.stdout.strip(), flush=True)


@pytest.mark.skipif(SKIP_NO_WINDOW, reason="Windows-only: subprocess.CREATE_NO_WINDOW absent")
def test_activation_explicit_detached_untouched() -> None:
    code = _ACT_SETUP + """
DETACHED = subprocess.DETACHED_PROCESS
subprocess.Popen(["probe"], creationflags=DETACHED)
assert observed["creationflags"] == DETACHED, (
    "explicit DETACHED_PROCESS rewritten: observed 0x%x, expected 0x%x"
    % (observed["creationflags"], DETACHED))
print("DETACHED observed=0x%x expected=0x%x" % (observed["creationflags"], DETACHED))
"""
    proc = _run_child(code)
    _assert_child(proc, expect_stdout="DETACHED observed=0x8 expected=0x8")
    print("activation: explicit DETACHED_PROCESS untouched (%s)" % proc.stdout.strip(), flush=True)


@pytest.mark.skipif(SKIP_NO_WINDOW, reason="Windows-only: subprocess.CREATE_NO_WINDOW absent")
def test_activation_kwargs_passthrough() -> None:
    code = _ACT_SETUP + """
kwargs_case = {
    "stdout": subprocess.DEVNULL,
    "stderr": subprocess.DEVNULL,
    "cwd": os.getcwd(),
    "env": {"A": "B"},
}
subprocess.Popen(["probe"], creationflags=0, **kwargs_case)
assert observed["kwargs"] == kwargs_case, (
    "kwargs not passed through: observed %r, expected %r"
    % (observed["kwargs"], kwargs_case))
assert observed["creationflags"] == subprocess.CREATE_NO_WINDOW, (
    "creationflags with kwargs not OR'd: 0x%x" % observed["creationflags"])
print("KWARGS passthrough=ok creationflags=0x%x" % observed["creationflags"])
"""
    proc = _run_child(code)
    _assert_child(proc, expect_stdout="KWARGS passthrough=ok creationflags=0x8000000")
    print("activation: kwargs stdout/stderr/cwd/env passthrough (%s)" % proc.stdout.strip(), flush=True)


# ---------------------------------------------------------------------------
# Group 2 (VC-006 / AC-006): inactive zero side effects
# ---------------------------------------------------------------------------

def test_inactive_sitecustomize_subprocess_noop() -> None:
    """sitecustomize loaded via PYTHONPATH with MW_CONSOLE_GUARD unset -> no-op."""
    code = _CHILD_PREFIX + """
sc_loaded = "sitecustomize" in sys.modules
import mw_console_guard
name = subprocess.Popen.__init__.__name__
assert sc_loaded, "sitecustomize not loaded via PYTHONPATH"
assert name == "__init__", "inactive guard patched Popen: %s" % name
assert mw_console_guard._patched is False, "inactive guard set _patched"
print("INACTIVE sc_loaded=%s name=%s patched=%s" % (sc_loaded, name, mw_console_guard._patched))
"""
    proc = _run_child(code, env={"PYTHONPATH": str(GUARD_DIR)})
    _assert_child(proc, expect_stdout="INACTIVE sc_loaded=True name=__init__ patched=False")
    print("inactive: sitecustomize loaded, zero side effects (%s)" % proc.stdout.strip(), flush=True)


def test_inactive_direct_import_noop() -> None:
    """Direct `import mw_console_guard` (no sitecustomize) with env unset -> no-op."""
    code = _CHILD_PREFIX + """
import mw_console_guard  # env unset -> module-level activation gate no-op
name = subprocess.Popen.__init__.__name__
assert name == "__init__", "inactive direct import patched Popen: %s" % name
assert mw_console_guard._patched is False, "_patched set by no-op import"
print("DIRECT name=%s patched=%s" % (name, mw_console_guard._patched))
"""
    proc = _run_child(code)
    _assert_child(proc, expect_stdout="DIRECT name=__init__ patched=False")
    print("inactive: direct import no-op (%s)" % proc.stdout.strip(), flush=True)


# ---------------------------------------------------------------------------
# Group 3 (VC-005 / AC-005): idempotent activation
# ---------------------------------------------------------------------------

@pytest.mark.skipif(SKIP_NO_WINDOW, reason="Windows-only: subprocess.CREATE_NO_WINDOW absent")
def test_idempotent_repeated_activate() -> None:
    code = _CHILD_PREFIX + """
os.environ["MW_CONSOLE_GUARD"] = "1"
import mw_console_guard  # auto-activation at import
first = subprocess.Popen.__init__
mw_console_guard._activate()
mw_console_guard._activate()
mw_console_guard._activate()
assert subprocess.Popen.__init__ is first, (
    "repeated _activate() re-wrapped Popen.__init__ (identity changed)")
assert mw_console_guard._patched is True, "_patched not set after activation"
# real spawn through the patched wrapper (smoke: wrapper still delegates)
rc = subprocess.Popen([sys.executable, "-c", "pass"], creationflags=0).wait()
assert rc == 0, "real spawn through patched wrapper failed: rc=%d" % rc
print("IDEMPOTENT same_obj=%s patched=%s real_rc=%d"
      % (subprocess.Popen.__init__ is first, mw_console_guard._patched, rc))
"""
    proc = _run_child(code)
    _assert_child(proc, expect_stdout="IDEMPOTENT same_obj=True patched=True real_rc=0")
    print("idempotent: repeated _activate() keeps one wrapper (%s)" % proc.stdout.strip(), flush=True)


# ---------------------------------------------------------------------------
# Group 4 (VC-006 / AC-006): fail-open on injected _apply exception
# ---------------------------------------------------------------------------

def test_fail_open_apply_exception() -> None:
    """Injected _apply exception at import-time activation -> fail-open.

    Mirrors RQ-3's mw_console_guard_broken variant: exec a fresh module whose
    _apply raises. Activation must happen during exec (module-level gate) so
    `sys` is still bound before the module's trailing `del os, sys`.
    """
    code = _CHILD_PREFIX + r"""
import pathlib
source = pathlib.Path(sys.argv[1], "mw_console_guard.py").read_text(encoding="utf-8")
broken = source.replace(
    "def _apply():",
    "def _apply():\n    raise RuntimeError('injected-brake-inside-apply')")
ns = {"__name__": "mw_console_guard_broken"}
os.environ["MW_CONSOLE_GUARD"] = "1"
exec(compile(broken, "mw_console_guard_broken.py", "exec"), ns)
name = subprocess.Popen.__init__.__name__
assert name == "__init__", "fail-open left Popen patched: %s" % name
assert ns["_patched"] is False, "_patched set despite failed patch"
print("FAILOPEN name=%s patched=%s" % (name, ns["_patched"]))
"""
    proc = _run_child(code)
    _assert_child(
        proc,
        expect_stdout="FAILOPEN name=__init__ patched=False",
        stderr_contains="mw_console_guard: patch failed",
        stderr_single_line=True,
    )
    print("fail-open: original __init__ + single-line warning (%s)" % proc.stderr.strip(), flush=True)


# ---------------------------------------------------------------------------
# Group 5 (VC-007 / AC-007): platform seam
# ---------------------------------------------------------------------------

def test_platform_seam_posix_gate() -> None:
    """os.name != 'nt' -> module-level activation gate never fires."""
    code = _CHILD_PREFIX + """
os.name = "posix"  # simulate non-Windows
os.environ["MW_CONSOLE_GUARD"] = "1"
import mw_console_guard
name = subprocess.Popen.__init__.__name__
assert name == "__init__", "posix gate failed: %s" % name
assert mw_console_guard._patched is False, "posix gate activated guard"
print("POSIXGATE name=%s patched=%s" % (name, mw_console_guard._patched))
"""
    proc = _run_child(code)
    _assert_child(proc, expect_stdout="POSIXGATE name=__init__ patched=False")
    print("platform seam: posix (os.name) gate no-op (%s)" % proc.stdout.strip(), flush=True)


def test_platform_seam_no_attr_branch() -> None:
    """hasattr(subprocess, 'CREATE_NO_WINDOW') False -> _apply early-returns."""
    code = _CHILD_PREFIX + """
import mw_console_guard  # env unset -> import no-op
if hasattr(subprocess, "CREATE_NO_WINDOW"):
    del subprocess.CREATE_NO_WINDOW  # simulate non-Windows / ancient stdlib
result = mw_console_guard._apply()
name = subprocess.Popen.__init__.__name__
assert result is True, "hasattr-noop _apply returned %r" % (result,)
assert name == "__init__", "hasattr-noop _apply patched Popen: %s" % name
print("NOATTR result=%s name=%s" % (result, name))
"""
    proc = _run_child(code)
    _assert_child(proc, expect_stdout="NOATTR result=True name=__init__")
    print("platform seam: hasattr(..., CREATE_NO_WINDOW) branch no-op (%s)" % proc.stdout.strip(), flush=True)


# ---------------------------------------------------------------------------
# Group 6: parent process global subprocess state stays pristine
# ---------------------------------------------------------------------------

def test_isolation_parent_process_subprocess_unpatched() -> None:
    name = subprocess.Popen.__init__.__name__
    assert name == "__init__", (
        "test process subprocess.Popen polluted by a test: %s" % name
    )
    print("isolation: test-process Popen.__init__ unpatched (name=%s)" % name, flush=True)
