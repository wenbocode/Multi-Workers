# Task 006: mw serve fail-closed child supervision

## 基本信息
- Stage: 2
- 代码状态: 未开始
- 验证状态: 未验证
- 负责 Agent: TBD
- ac_refs: [AC-012]
- vc_refs: [VC-012]

## 描述
当前 `mw.py` 的 `cmd_serve` 在子进程退出后继续运行，且 `_check_pid` / `cmd_stop` 在 Windows 上使用 `os.kill(pid, 0)` 发信号（不安全）。需要：

1. **Fail-closed supervision**：serve 循环用 `poll()` 检测子进程退出，发现任意子进程意外退出后：terminate 另一个，等待最多 10s，force-kill 残存进程，移除 PID 文件，非零退出。
2. **Stop-request file**：`mw stop` 写 `.mw/mw.stop`，`mw serve` 循环轮询该文件作为有意停止信号（零退出），启动前清除旧的 stop 文件。
3. **跨平台 liveness**：`_check_pid` 在 Windows 使用 `ctypes` + `OpenProcess + GetExitCodeProcess`（read-only）；在 POSIX 使用 `os.kill(pid, 0)`。
4. **mw stop timeout**：等待最多 30s 检查 parent 是否退出；超时返回非零，不强杀 parent。
5. **POSIX SIGTERM** 仍为有意停止路径，Windows 使用 stop-request file。

## 输入
- 依赖文件: `packages/multi-workers/mw.py`（cmd_serve, _check_pid, cmd_stop）
- AC 约束:
  > AC-012: unexpected child exit → 非零 service exit + cleanup；.mw/mw.stop 请求、KeyboardInterrupt、POSIX SIGTERM → 零退出；cleanup terminate+wait 10s+force-kill；mw stop 不强杀 parent，30s 超时返回非零。

## 实现要点

### _is_alive_win32(pid) — Windows-only liveness
```python
import ctypes
import ctypes.wintypes

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259

def _is_alive_win32(pid: int) -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
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
```

### _check_pid 改造
```python
def _check_pid(pid_path: pathlib.Path) -> int | None:
    if not pid_path.exists():
        return None
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None
    try:
        if sys.platform == "win32":
            return pid if _is_alive_win32(pid) else None
        os.kill(pid, 0)
        return pid
    except (ProcessLookupError, PermissionError, OSError):
        return None
```

### Stop-request file helpers
```python
def _stop_request_path(project_dir: pathlib.Path) -> pathlib.Path:
    return project_dir / ".mw" / "mw.stop"

def _write_stop_request(project_dir: pathlib.Path) -> None:
    p = _stop_request_path(project_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("stop", encoding="utf-8")

def _clear_stop_request(project_dir: pathlib.Path) -> None:
    try:
        _stop_request_path(project_dir).unlink()
    except FileNotFoundError:
        pass
```

### cmd_serve 改造
```python
# 启动前清除旧 stop 文件
_clear_stop_request(project_dir)

# 注册 POSIX SIGTERM（有意停止）
intentional_stop = threading.Event()
if sys.platform != "win32":
    def _on_sigterm(signum, frame):
        intentional_stop.set()
    signal.signal(signal.SIGTERM, _on_sigterm)

# 主循环
try:
    while True:
        if intentional_stop.is_set():
            break
        if _stop_request_path(project_dir).exists():
            _clear_stop_request(project_dir)
            intentional_stop.set()
            break
        # 检查子进程存活
        proxy_exit = proxy_proc.poll()
        launcher_exit = launcher_proc.poll()
        if proxy_exit is not None or launcher_exit is not None:
            # 意外退出 → fail closed
            # intentional_stop 不设置，finally 以非零退出
            break
        time.sleep(1)
except KeyboardInterrupt:
    intentional_stop.set()
finally:
    # cleanup: terminate + wait 10s + force-kill
    exit_code = 0 if intentional_stop.is_set() else 1
    for proc in (launcher_proc, proxy_proc):
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                try: proc.wait(timeout=5)
                except: pass
            except Exception:
                pass
    _remove_pid(pid_path)
    _clear_stop_request(project_dir)
    return exit_code
```

### cmd_stop 改造
```python
def cmd_stop(args):
    project_dir = pathlib.Path(args.project).resolve()
    pid_path = _pid_path(project_dir)
    pid = _check_pid(pid_path)
    if pid is None:
        print("[mw stop] not running"); return 0
    _write_stop_request(project_dir)
    # 等待最多 30s
    for _ in range(60):
        time.sleep(0.5)
        if _check_pid(pid_path) is None:
            print(f"[mw stop] stopped PID {pid}"); return 0
    print(f"[mw stop] warning: process {pid} did not exit in 30s")
    return 1
```

## 预期产出
- 修改 `packages/multi-workers/mw.py`（cmd_serve, cmd_stop, _check_pid, 新增 helpers）
- 在 `packages/multi-workers/test_proxy_service.py` 中追加 VC-012 lifecycle 测试：
  - startup failure（proxy spawn 失败）→ 非零退出
  - single child runtime exit → 非零退出
  - simultaneous exits → 非零退出
  - stop-file shutdown → 零退出
  - KeyboardInterrupt → 零退出
  - stale stop-file cleanup on startup
  - PID file removed after exit
  - stop-timeout returns nonzero without parent termination
- 验证方式: `python -m pytest packages/multi-workers/test_proxy_service.py -q`
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本 | 状态 |
|----|------|---------|---------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
