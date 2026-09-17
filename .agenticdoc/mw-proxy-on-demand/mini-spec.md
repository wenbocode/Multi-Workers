# Mini-Spec: mw-proxy-on-demand

- Date: 2026-09-16
- Mode: pm mini fast path (direct execution, no plan/tasks)
- Deps: agent-team-loop（无扩展改动；本任务纯 Python）
- 来源：用户报告——新机器（F:\MW，Python 3.14）mw serve 起不来：proxy_multi.py
  `import timi_proxy_cli` ModuleNotFoundError → proxy 子进程即死 → serve 监督循环
  把 proxy 死亡当致命条件 → 1 秒内自杀（PID/serve.meta 清理，PM 稳定窗播报
  启动未确认）。用户判定：本仓库不应依赖该私有包。

## Problem

proxy 只服务端口型路由（claude/claude-cli/deepseek，上游指向 timi 网关），
且需要私有包 timi-proxy-cli（本机 0.1.0 本地安装，不在公开 PyPI）。直连路由
（timi 走 auth.json/api key、codex-native 走 PATH）完全不经过 proxy。新机器
只有 timi 凭证时，proxy 对可用路由毫无作用，却因 import 失败拖死整个服务
（timi-gpt-pi-routing task 006 VC-012 的「子进程退出 → serve 退出」语义在
proxy 上过严）。

## Change

1. `mw.py cmd_serve`：预检后计算 `proxy_routes`（available 且 providers 配置
   含 port 的路由）。无代理路由凭证 → 不 spawn proxy，日志
   `proxy disabled; direct routes only (timi / codex-native)`；启动行
   `proxy=disabled`。有代理路由 → 维持原有 share-or-spawn 与致命退出语义，
   但死亡时打 `FATAL: proxy exited (code N); .mw/proxy.log tail:` + 尾部
   15 行（`mw_common.read_log_tail` 新增）。
2. `mw_common.py`：新增 `read_log_tail`、`_doctor_proxy_log`（解析最后一次
   traceback 后首个列 0 非空行 = 异常消息）；`doctor_report` 增 `proxy_log`
   节；`format_doctor_text` 增 `proxy: disabled`（无代理路由凭证时）与
   `proxy_log:` 行；`_doctor_issues`：服务未运行 + 崩溃日志 → issue（根因
   指向 ModuleNotFoundError 等），服务运行中 → suggestion。
3. 测试：`test_proxy_service.py` TestServeSupervision 加 autouse
   ANTHROPIC_API_KEY（真实 providers.json 的 claude 路由），保住 VC-012
   生命周期测试的 proxy-spawn 路径（否则队列错位、launcher 用例死循环）；
   `test_serve_doctor.py` 更新 `len(spawned) == 2 → 1`（仅 timi 凭证），
   新增 proxy-spawn、proxy-death-fatal-with-tail、doctor proxy_log 根因
   三个用例。
4. README（multi-workers）：组成表 + serve 行说明代理按需启动。

## Files

- packages/multi-workers/mw.py
- packages/multi-workers/mw_common.py
- packages/multi-workers/test_proxy_service.py
- packages/multi-workers/test_serve_doctor.py
- packages/multi-workers/README.md
- packages/multi-workers/CHANGELOG.md

## Acceptance Criteria

| AC | 内容 | 验证 |
| --- | --- | --- |
| AC-001 | 仅 timi 凭证：serve 不 spawn proxy、正常启动、日志注明 disabled | pytest |
| AC-002 | 有代理路由凭证：proxy 照常 spawn，死亡仍致命且带退出码+日志尾 | pytest |
| AC-003 | doctor 在服务未运行 + proxy.log 崩溃时把异常行列为 issue | pytest（CLI 子进程） |
| AC-004 | 既有生命周期/doctor/bootstrap 用例无回归（含队列对位修复） | 全量 pytest |

## Result

- AC-001/002：`test_logs_every_route_and_starts`（改断言 spawned==1 +
  disabled 日志）、新增 `test_proxy_spawned_when_proxy_route_available`
  （spawned==2）与 `test_proxy_death_is_fatal_with_log_tail`（rc=1 +
  `FATAL: proxy exited (code 1)` + `ModuleNotFoundError` 行入 mw.log）。
- AC-003：`test_proxy_log_crash_surfaces_root_cause`（doctor CLI 真子进程，
  exit 1、issues 含 `ModuleNotFoundError: No module named 'timi_proxy_cli'`、
  文本含 `proxy_log: 1 crash(es)` 与 `proxy: disabled`）。首版解析把缩进的
  File 行当异常行，已修（首个列 0 非空行）。
- AC-004：`test_serve_doctor + test_proxy_service` 27/27；包级全量
  433 passed, 8 deselected（原 430 + 新增 3）。
- 纯 Python 改动，无 TS/dist 重建需求；扩展 /mw doctor 对新 JSON 节安全
  （mw-runner.ts 最小类型视图 + 整体 cast，增量键被忽略）。
- 状态：完成。
