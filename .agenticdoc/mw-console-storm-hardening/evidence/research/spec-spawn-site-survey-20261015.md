# Research: Multi-Workers 框架 spawn 面普查（spec）

> date: 2026-10-15
> 决策问题: 支撑 spec §1 范围（L0 框架自身除雷的边界）、§1.3 场景 A、§3 AC-002 的审计面
> 方法: git grep 全量 `subprocess.(run|Popen|check_output)` + 逐站点读上下文（caller 链 + 现有 flag），均为本日实测

## 发现

### 框架自身同款地雷

- `packages/multi-workers/mw.py:506`（`cmd_start`，`mw start` 子命令）:
  `creationflags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW`
  → 与事故完全相同的互斥组合，CREATE_NO_WINDOW 被静默忽略，`mw serve` 进程**无控制台**。
  今天未爆是因为 serve 的全部直接子进程恰好都显式带 flag（见下）——安全性靠"每处都记得"的约定维持，非结构性。

### serve（无控制台树）首层 spawn 现状：均已打 flag

| 站点 | flag | 备注 |
|------|------|------|
| `mw.py:231` conductor spawn | `**spawn_kwargs`（CREATE_NO_WINDOW，:334 处构造） | 隐藏控制台 |
| `mw.py:376` proxy spawn | 同上 | 隐藏控制台 |
| `mw.py:393` launcher spawn | 同上 | 隐藏控制台 |
| `mw.py:4441` `_git` | CREATE_NO_WINDOW | serve 启动身份采集（`_git_head_oid`→`_git`）经此，已隔离 |

### serve 树内可达、当前无 flag 的站点（前台 CLI 专属，边界靠惯例）

| 站点 | caller（今日） | 风险 |
|------|----------------|------|
| `mw.py:1127` `_toolchain_run`（**shell=True**） | `mw ue-toolchain run`（前台） | 若被 serve 侧调用即弹窗 |
| `mw.py:4389` `_git_short_commit`（check_output） | pull/push-agentictask（前台） | 同上 |
| `mw.py:4951` `_install_framework` | init/bootstrap（前台） | 同上 |
| `mw.py:4737/4762` node esbuild / npm build | `mw build --install`（前台） | 同上 |
| `mw.py:5137/5166` `_run_stream`/`_run_capture` | bootstrap/npm（前台） | 同上 |
| `mw_common.py:2313` `port_owner_pids`（netstat） | doctor（前台） | 同上 |
| `autopilot/advance.py:92,181`、`conductor.py:2922`、`xkey.py:1301` | conductor（隐藏控制台树内）→ 子进程**继承**隐藏控制台，当前安全 | 结构性安全，属第二层继承 |

### 二层继承已正确覆盖的范围

- conductor / launcher / proxy 均持隐藏控制台 → 其子进程（advance_phase、worker、netstat 等）`creationflags=0` 时继承隐藏控制台，不弹窗。
- worker（pi）由 launcher 以 CREATE_NO_WINDOW 拉起 → bash/git 子进程继承 → 已正确（mw-console-title-clobber key 建立的先例）。

## 结论 → 决策映射

- L0 的最小充分改动 = `cmd_start` 去 `DETACHED_PROCESS`（保留 CREATE_NO_WINDOW|CREATE_NEW_PROCESS_GROUP）+ serve stdio 重定向到 serve log。改完后 serve 拥有隐藏控制台，**全树从"无控制台（每代需显式 flag）"变"隐藏控制台（继承自动兜底）"**，漏加 flag 的未来站点也不再弹窗（支撑 AC-001/AC-002 的结构性论证）。
- serve 树可达站点需全量清点成审计表（design 阶段产出），作为 AC-002 的检查面。
- 框架内除 `cmd_start` 外无第二处 DETACHED_PROCESS（grep 证实），守卫测试初始 allowlist 为空（支撑 AC-002 可行性）。
